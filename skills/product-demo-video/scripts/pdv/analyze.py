"""Recording analysis: activity detection, focus regions, contact sheets, draft edit plan.

Pure Python + ffmpeg (no numpy/opencv) so the skill runs anywhere.
"""
import os
import subprocess

from PIL import Image, ImageDraw

from .common import clamp, die, fmt_t, need_bin, probe, save_json
from . import graphics

AW = 160            # analysis frame width (px)
PIX_THR = 16        # gray-level delta that counts as "changed"
IDLE_FRAC = 0.0012  # changed-pixel fraction below which a sample is idle


def _gray_frames(path, sample_fps, width, height):
    cmd = ["ffmpeg", "-v", "error", "-i", path, "-vf",
           f"fps={sample_fps},scale={width}:{height}:flags=area,format=gray",
           "-f", "rawvideo", "-"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    size = width * height
    while True:
        buf = proc.stdout.read(size)
        if len(buf) < size:
            break
        yield buf
    proc.wait()


def _diff(prev, cur, w, h):
    """Return (changed_fraction, trimmed bbox (x0,y0,x1,y1) normalized or None)."""
    cols = [0] * w
    rows = [0] * h
    total = 0
    for y in range(h):
        off = y * w
        rc = 0
        pa = prev[off:off + w]
        ca = cur[off:off + w]
        for x in range(w):
            d = pa[x] - ca[x]
            if d > PIX_THR or d < -PIX_THR:
                cols[x] += 1
                rc += 1
        rows[y] = rc
        total += rc
    if total == 0:
        return 0.0, None
    return total / (w * h), (_trim(cols, total) + _trim(rows, total), (w, h))


def _trim(hist, total, pct=0.03):
    cut = total * pct
    acc, lo = 0, 0
    for i, v in enumerate(hist):
        acc += v
        if acc > cut:
            lo = i
            break
    acc, hi = 0, len(hist) - 1
    for i in range(len(hist) - 1, -1, -1):
        acc += hist[i]
        if acc > cut:
            hi = i
            break
    return (lo, hi + 1)


def analyze(input_path, outdir, sample_fps=4.0, sheet_every=None):
    need_bin("ffmpeg")
    info = probe(input_path)
    os.makedirs(outdir, exist_ok=True)
    w = AW
    h = max(2, int(round(AW * info["height"] / info["width"] / 2)) * 2)

    samples = []
    prev = None
    for i, frame in enumerate(_gray_frames(input_path, sample_fps, w, h)):
        t = round(i / sample_fps, 3)
        if prev is None:
            samples.append({"t": t, "act": 0.0, "bbox": None})
        else:
            frac, bb = _diff(prev, frame, w, h)
            nb = None
            if bb:
                (x0, x1, y0, y1), _ = bb
                nb = [round(x0 / w, 4), round(y0 / h, 4), round(x1 / w, 4), round(y1 / h, 4)]
            samples.append({"t": t, "act": round(frac, 5), "bbox": nb})
        prev = frame

    events = _events(samples, sample_fps, info["duration"])
    idle = _idle_ranges(events, info["duration"])
    sheets = contact_sheets(input_path, outdir, info, every=sheet_every)

    analysis = {
        "input": os.path.abspath(input_path),
        "video": info,
        "sample_fps": sample_fps,
        "events": events,
        "idle": idle,
        "contact_sheets": sheets,
        "samples": samples,
    }
    save_json(analysis, os.path.join(outdir, "analysis.json"))
    return analysis


def _events(samples, sfps, duration, gap=0.75):
    """Group active samples into events with a union focus bbox."""
    events, cur = [], None
    for s in samples:
        active = s["act"] >= IDLE_FRAC
        if active:
            if cur and s["t"] - cur["end"] <= gap:
                cur["end"] = s["t"]
                cur["_s"].append(s)
            else:
                if cur:
                    events.append(cur)
                cur = {"start": max(0.0, s["t"] - 1 / sfps), "end": s["t"], "_s": [s]}
    if cur:
        events.append(cur)

    out = []
    for e in events:
        ss = e.pop("_s")
        boxes = [s["bbox"] for s in ss if s["bbox"]]
        bb = [min(b[0] for b in boxes), min(b[1] for b in boxes),
              max(b[2] for b in boxes), max(b[3] for b in boxes)] if boxes else [0, 0, 1, 1]
        area = (bb[2] - bb[0]) * (bb[3] - bb[1])
        peak = max(s["act"] for s in ss)
        kind = "local" if area < 0.22 and peak < 0.12 else "global"
        out.append({
            "start": round(e["start"], 2), "end": round(min(duration, e["end"] + 1 / sfps), 2),
            "kind": kind, "peak": round(peak, 4),
            "focus": [round(v, 3) for v in bb],
            "center": [round((bb[0] + bb[2]) / 2, 3), round((bb[1] + bb[3]) / 2, 3)],
        })
    return out


def _idle_ranges(events, duration, min_len=1.0):
    idle, t = [], 0.0
    for e in events:
        if e["start"] - t >= min_len:
            idle.append([round(t, 2), round(e["start"], 2)])
        t = max(t, e["end"])
    if duration - t >= min_len:
        idle.append([round(t, 2), round(duration, 2)])
    return idle


def contact_sheets(input_path, outdir, info, every=None, cols=4, per_sheet=12, tile_w=480):
    dur = info["duration"]
    if not every:
        every = clamp(round(dur / 36, 1), 0.5, 5.0)
    fdir = os.path.join(outdir, "frames")
    os.makedirs(fdir, exist_ok=True)
    for f in os.listdir(fdir):
        os.remove(os.path.join(fdir, f))
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", input_path, "-vf",
                    f"fps=1/{every},scale={tile_w}:-2", "-q:v", "4",
                    os.path.join(fdir, "f_%04d.jpg")], check=True)
    files = sorted(os.listdir(fdir))
    sheets = []
    font = graphics.font(22, "SemiBold")
    for si in range(0, len(files), per_sheet):
        chunk = files[si:si + per_sheet]
        tiles = [Image.open(os.path.join(fdir, f)).convert("RGB") for f in chunk]
        tw, th = tiles[0].size
        rows = (len(tiles) + cols - 1) // cols
        pad = 8
        sheet = Image.new("RGB", (cols * (tw + pad) + pad, rows * (th + pad) + pad), (24, 24, 27))
        d = ImageDraw.Draw(sheet)
        for i, tile in enumerate(tiles):
            x = pad + (i % cols) * (tw + pad)
            y = pad + (i // cols) * (th + pad)
            sheet.paste(tile, (x, y))
            t = (si + i) * every  # fps=1/N emits the frame nearest to k*N
            label = f"{t:.1f}s"
            bw = d.textlength(label, font=font) + 16
            d.rounded_rectangle([x + 6, y + 6, x + 6 + bw, y + 38], 8, fill=(0, 0, 0))
            d.text((x + 14, y + 9), label, font=font, fill=(255, 255, 255))
        p = os.path.join(outdir, f"sheet_{len(sheets) + 1:02d}.jpg")
        sheet.save(p, quality=85)
        sheets.append({"path": p, "from": round(si * every, 2),
                       "to": round((si + len(chunk) - 1) * every, 2), "every": every})
    return sheets


def grab_frame(input_path, t, out, grid=True, width=1600):
    """Single frame, optionally with a normalized 0-1 coordinate grid (for placing callouts)."""
    need_bin("ffmpeg")
    tmp = out + ".raw.png"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(t), "-i", input_path, "-frames:v", "1",
                    "-vf", f"scale={width}:-2", tmp], check=True)
    img = Image.open(tmp).convert("RGB")
    os.remove(tmp)
    if grid:
        d = ImageDraw.Draw(img, "RGBA")
        f = graphics.font(18, "SemiBold")
        W, H = img.size
        for i in range(1, 10):
            x, y = W * i / 10, H * i / 10
            d.line([(x, 0), (x, H)], fill=(255, 0, 80, 110), width=1)
            d.line([(0, y), (W, y)], fill=(255, 0, 80, 110), width=1)
            for lbl, pos in ((f"x{i / 10:.1f}", (x + 3, 3)), (f"y{i / 10:.1f}", (3, y + 2))):
                tw = d.textlength(lbl, font=f)
                d.rectangle([pos[0] - 2, pos[1], pos[0] + tw + 2, pos[1] + 22], fill=(0, 0, 0, 170))
                d.text(pos, lbl, font=f, fill=(255, 255, 255, 255))
        d.text((W - 150, H - 30), f"t={fmt_t(t)}", font=f, fill=(255, 255, 0, 255))
    img.save(out)
    return out


def draft_plan(analysis, idle_speed=6.0, idle_mode="speed", max_zoom=2.0, aspect="16:9"):
    """Turn analysis into a reasonable starting edit plan. Claude then refines it."""
    dur = analysis["video"]["duration"]
    events = analysis["events"]
    if not events:
        die("no on-screen activity detected; is the recording blank?")
    start = max(0.0, events[0]["start"] - 0.4)
    end = min(dur, events[-1]["end"] + 1.0)

    cuts, speed = [], []
    for a, b in analysis["idle"]:
        a, b = max(a, start), min(b, end)
        if b - a < 1.2:
            continue
        lo, hi = round(a + 0.35, 2), round(b - 0.35, 2)
        if hi - lo < 0.5:
            continue
        if idle_mode == "cut":
            cuts.append([lo, hi])
        else:
            speed.append({"start": lo, "end": hi, "speed": idle_speed})

    zooms = []
    for i, e in enumerate(events):
        if e["kind"] != "local" or e["end"] - e["start"] < 0.6:
            if zooms and zooms[-1]["scale"] > 1:
                zooms.append({"at": round(max(e["start"] - 0.3, 0), 2), "scale": 1.0})
            continue
        x0, y0, x1, y1 = e["focus"]
        bw, bh = max(x1 - x0, 0.02), max(y1 - y0, 0.02)
        z = clamp(min(0.5 / bw, 0.5 / bh), 1.0, max_zoom)
        if z < 1.25:
            continue
        cx, cy = e["center"]
        prev = zooms[-1] if zooms else None
        if prev and prev["scale"] > 1 and abs(prev.get("x", .5) - cx) < 0.08 and abs(prev.get("y", .5) - cy) < 0.08:
            continue
        zooms.append({"at": round(max(e["start"] - 0.3, 0), 2), "scale": round(z, 2), "x": cx, "y": cy})
        nxt = events[i + 1] if i + 1 < len(events) else None
        if not nxt or nxt["start"] - e["end"] > 1.5:
            zooms.append({"at": round(e["end"] + 0.4, 2), "scale": 1.0})
    # drop keyframes that would fire less than 1s apart (keeps motion calm)
    calm = []
    for k in zooms:
        if calm and k["at"] - calm[-1]["at"] < 1.0:
            calm[-1] = k if k["scale"] > 1 else calm[-1]
            continue
        calm.append(k)

    return {
        "input": analysis["input"],
        "trim": {"start": round(start, 2), "end": round(end, 2)},
        "cuts": cuts,
        "speed": speed,
        "zoom": calm,
        "captions": [],
        "callouts": [],
        "intro": None,
        "outro": None,
        "style": {"theme": "dark", "accent": "#6366F1", "background": "aurora"},
        "outputs": [{"aspect": aspect, "path": "demo-" + aspect.replace(":", "x") + ".mp4"}],
        "_events": [{"start": e["start"], "end": e["end"], "kind": e["kind"], "center": e["center"]}
                    for e in events],
    }
