"""Render an edit plan (JSON) to one or more finished videos with a single ffmpeg pass each.

All times in the plan are SOURCE-recording seconds (what you see in contact sheets);
the renderer maps them onto the output timeline after trims, cuts and speed changes.
"""
import os
import shutil
import subprocess
import sys
import tempfile

from .common import clamp, die, need_bin, probe, run
from . import graphics

ASPECTS = {"16:9": (1920, 1080), "9:16": (1080, 1920), "1:1": (1080, 1080), "4:5": (1080, 1350),
           "4:3": (1440, 1080), "21:9": (2520, 1080)}
QUALITY = {"draft": ("veryfast", 23), "standard": ("medium", 18), "high": ("slow", 15)}


# ---------- timeline ------------------------------------------------------------------------

def build_segments(plan, duration):
    trim = plan.get("trim") or {}
    t0 = clamp(float(trim.get("start", 0)), 0, duration)
    t1 = clamp(float(trim.get("end", duration) or duration), t0, duration)
    bounds = {t0, t1}
    cuts = [(float(a), float(b)) for a, b in plan.get("cuts", [])]
    speeds = [(float(s["start"]), float(s["end"]), float(s["speed"])) for s in plan.get("speed", [])]
    for a, b in cuts:
        bounds.update([clamp(a, t0, t1), clamp(b, t0, t1)])
    for a, b, _ in speeds:
        bounds.update([clamp(a, t0, t1), clamp(b, t0, t1)])
    pts = sorted(bounds)
    segs = []
    for a, b in zip(pts, pts[1:]):
        if b - a < 0.02:
            continue
        mid = (a + b) / 2
        if any(ca <= mid < cb for ca, cb in cuts):
            continue
        sp = 1.0
        for sa, sb, s in speeds:
            if sa <= mid < sb:
                sp = s
        if segs and abs(segs[-1][2] - sp) < 1e-6 and abs(segs[-1][1] - a) < 1e-6:
            segs[-1] = (segs[-1][0], b, sp)
        else:
            segs.append((a, b, sp))
    if not segs:
        die("plan leaves nothing to render (check trim/cuts)")
    return segs


class Timeline:
    def __init__(self, segs):
        self.segs = segs
        self.out_starts = []
        acc = 0.0
        for a, b, s in segs:
            self.out_starts.append(acc)
            acc += (b - a) / s
        self.duration = acc

    def map(self, t):
        """source seconds -> output seconds (times inside cuts snap to the next kept frame)."""
        for (a, b, s), o in zip(self.segs, self.out_starts):
            if t < a:
                return o
            if t <= b:
                return o + (t - a) / s
        return self.duration


# ---------- expressions ---------------------------------------------------------------------

def _num(v):
    return f"{v:.5f}".rstrip("0").rstrip(".") or "0"


def keyframe_expr(keys, initial, dur, var="t"):
    """keys: [(t_out, value)] -> ffmpeg expression with smootherstep transitions of `dur` seconds."""
    pieces = []  # (until, expr)
    prev = initial
    last_end = -1e9
    for t, v in keys:
        t = max(t, last_end)
        if abs(v - prev) < 1e-6:
            continue
        pieces.append((t, _num(prev)))
        p = f"clip(({var}-{_num(t)})/{_num(dur)},0,1)"
        ease = f"({p}*{p}*{p}*({p}*({p}*6-15)+10))"
        pieces.append((t + dur, f"({_num(prev)}+({_num(v - prev)})*{ease})"))
        prev = v
        last_end = t + dur
    expr = _num(prev)
    for until, e in reversed(pieces):
        expr = f"if(lt({var},{_num(until)}),{e},{expr})"
    return expr


# ---------- layout --------------------------------------------------------------------------

def canvas_size(out):
    if "size" in out:
        w, h = [int(v) for v in str(out["size"]).lower().split("x")]
        return w, h
    w, h = ASPECTS.get(out.get("aspect", "16:9"), ASPECTS["16:9"])
    res = int(out.get("resolution", 1080))
    k = res / 1080
    return int(w * k) // 2 * 2, int(h * k) // 2 * 2


def layout(canvas, src, style):
    """Return inner video box (x, y, w, h) on the canvas."""
    W, H = canvas
    sw, sh = src
    if style.get("background", "aurora") == "none":
        return 0, 0, W, H
    pad = float(style.get("padding", 0.06))
    vertical = H > W * 1.1
    avail_w = W - 2 * int(W * pad) if not vertical else W - 2 * int(W * pad * 0.6)
    avail_h = H - 2 * int(H * pad) if not vertical else int(H * 0.62)
    narrow = W / H < 1.3 and sw > sh * 1.2        # landscape recording on a 1:1 / 4:5 / 9:16 canvas
    fit = style.get("fit") or ("cover" if narrow else "contain")
    if narrow and fit == "cover":
        # a big window that follows the zoom focus instead of a tiny letterboxed frame
        aspect = float(style.get("vertical_box_aspect", 1.0 if vertical else 1.3))
        iw = avail_w
        ih = min(avail_h, iw / aspect)
    elif fit == "cover":
        iw, ih = avail_w, avail_h
    else:
        s = min(avail_w / sw, avail_h / sh)
        iw, ih = sw * s, sh * s
    iw, ih = int(iw) // 2 * 2, int(ih) // 2 * 2
    x = (W - iw) // 2
    y = (H - ih) // 2 if not vertical else int(H * 0.40 - ih / 2)
    y = max(y, int(H * 0.08)) if vertical else y
    return x, y, iw, ih


# ---------- render --------------------------------------------------------------------------

def render(plan, only=None, still=None, quality=None, keep_temp=False, base_dir="."):
    need_bin("ffmpeg")
    src_path = os.path.expanduser(plan["input"])
    if not os.path.isabs(src_path):
        src_path = os.path.join(base_dir, src_path)
    info = probe(src_path)
    segs = build_segments(plan, info["duration"])
    tl = Timeline(segs)
    style = dict(plan.get("style") or {})
    outs = plan.get("outputs") or [{"aspect": "16:9", "path": "demo.mp4"}]
    if only:
        outs = [o for o in outs if o.get("aspect") in only or o.get("path") in only] or outs[:1]
    results = []
    for out in outs:
        tmp = tempfile.mkdtemp(prefix="pdv_")
        try:
            path = _render_one(plan, out, style, info, src_path, segs, tl, tmp, still, quality, base_dir)
            results.append(path)
        finally:
            if keep_temp:
                print(f"temp files kept in {tmp}", file=sys.stderr)
            else:
                shutil.rmtree(tmp, ignore_errors=True)
    return results


def _render_one(plan, out, style, info, src_path, segs, tl, tmp, still, quality, base_dir):
    # per-output overrides: an output may carry its own zoom/captions/callouts/intro/outro/style
    plan = dict(plan)
    for key in ("zoom", "captions", "callouts", "intro", "outro"):
        if key in out:
            plan[key] = out[key]
    style = {**style, **(out.get("style") or {})}
    W, H = canvas_size(out)
    sw, sh = info["width"], info["height"]
    fps = float(out.get("fps") or style.get("fps") or 60)
    accent = style.get("accent", "#6366F1")
    theme = style.get("theme", "dark")
    font_path = style.get("font")
    if font_path:
        font_path = os.path.expanduser(font_path)
    bg_spec = style.get("background", "aurora")
    box = layout((W, H), (sw, sh), style)
    bx, by, iw, ih = box
    framed = bg_spec != "none"

    inputs = [["-i", src_path]]
    fc = []

    def add_image(img, name, dur):
        p = os.path.join(tmp, name)
        img.save(p)
        inputs.append(["-loop", "1", "-framerate", _num(fps), "-t", _num(dur), "-i", p])
        return len(inputs) - 1

    # 1) source normalisation + callouts (source time)
    cur = "src0"
    fc.append(f"[0:v]setpts=PTS-STARTPTS,fps={_num(fps)},format=yuv420p[{cur}]")
    for i, c in enumerate(plan.get("callouts", [])):
        img, (L, T) = graphics.callout(c.get("shape", "ring"), (sw, sh), float(c["x"]), float(c["y"]),
                                       float(c.get("w", 0)), float(c.get("h", 0)), c.get("text"),
                                       c.get("label_pos", "auto"), c.get("accent", accent),
                                       c.get("theme", theme), font_path)
        s, e = float(c["start"]), float(c["end"])
        d = max(0.4, e - s)
        k = add_image(img, f"callout_{i}.png", d)
        fd = min(0.25, d / 3)
        fc.append(f"[{k}:v]format=rgba,fade=t=in:st=0:d={_num(fd)}:alpha=1,"
                  f"fade=t=out:st={_num(d - fd)}:d={_num(fd)}:alpha=1,setpts=PTS-STARTPTS+{_num(s)}/TB[co{i}]")
        fc.append(f"[{cur}][co{i}]overlay=x={L}:y={T}:eof_action=pass:enable='between(t,{_num(s)},{_num(e)})'[srcc{i}]")
        cur = f"srcc{i}"

    # 2) trims / cuts / speed changes in ONE stream: select the kept source frames, then remap
    #    their timestamps with a piecewise-linear source->output function. (split+trim+concat
    #    would buffer every full-res frame of later segments in memory.)
    keep = "+".join(f"between(t,{_num(a)},{_num(b)})" for a, b, _ in segs)
    remap = _num(tl.duration)
    for (a, b, s), o in reversed(list(zip(segs, tl.out_starts))):
        remap = f"if(lt(T,{_num(b)}),{_num(o)}+(T-{_num(a)})/{_num(s)},{remap})"
    fc.append(f"[{cur}]select='{keep}',setpts='({remap})/TB',fps={_num(fps)}[cat]")

    # 3) zoom & pan (output time)
    zk, xk, yk = [], [], []
    lx, ly = 0.5, 0.5
    for kf in sorted(plan.get("zoom", []), key=lambda k: k["at"]):
        t = tl.map(float(kf["at"]))
        z = clamp(float(kf.get("scale", 1.0)), 1.0, 4.0)
        lx = float(kf.get("x", lx))
        ly = float(kf.get("y", ly))
        zk.append((t, z)); xk.append((t, lx)); yk.append((t, ly))
    zd = float(style.get("zoom_duration", 0.8))
    Z = keyframe_expr(zk, 1.0, zd, var="it")
    CX = keyframe_expr(xk, 0.5, zd, var="it")
    CY = keyframe_expr(yk, 0.5, zd, var="it")
    # Supersample to 2x the box (cover), then zoompan down: pan/zoom steps are half an output
    # pixel, which keeps slow moves smooth. (scale eval=frame + crop breaks: crop keeps the
    # first frame's size when dimensions change mid-stream.)
    ss = 2
    pw, ph = iw * ss, ih * ss
    fc.append(f"[cat]scale={pw}:{ph}:force_original_aspect_ratio=increase:flags=lanczos,crop={pw}:{ph},"
              f"zoompan=z='{Z}':x='clip(({CX})*iw-iw/zoom/2,0,iw-iw/zoom)':"
              f"y='clip(({CY})*ih-ih/zoom/2,0,ih-ih/zoom)':d=1:s={iw}x{ih}:fps={_num(fps)},setsar=1[zoomed]")
    cur = "zoomed"
    body_d = tl.duration

    # 4) background framing
    if framed:
        radius = int(float(style.get("radius", 22)) * min(W, H) / 1080)  # px at 1080p
        base = graphics.background((W, H), bg_spec)
        kb = add_image(base, "bg.png", body_d + 1)
        kf_ = add_image(graphics.frame_overlay((W, H), box, radius, bg_spec, style.get("shadow", True),
                                               style.get("border", True)), "frame.png", body_d + 1)
        fc.append(f"[{kb}:v]format=yuv420p[bgv]")
        fc.append(f"[bgv][{cur}]overlay=x={bx}:y={by}:shortest=1[fr0]")
        fc.append(f"[fr0][{kf_}:v]overlay=0:0:shortest=1[framed]")
        cur = "framed"

    # 5) captions (output time)
    vertical = H > W * 1.1
    anim = style.get("caption_animation", "slide")
    for i, c in enumerate(plan.get("captions", [])):
        s = tl.map(float(c["start"]))
        e = tl.map(float(c["end"]))
        e = max(e, s + float(c.get("min_duration", 1.4)))
        e = min(e, body_d)
        d = e - s
        if d <= 0.2:
            continue
        img, (px, py) = graphics.caption(c["text"], (W, H), c.get("theme", theme), c.get("accent", accent),
                                         c.get("step"), c.get("sub"), font_path=font_path,
                                         scale=float(c.get("scale", style.get("caption_scale", 1.0))))
        k = add_image(img, f"cap_{i}.png", d)
        pos = c.get("position", style.get("caption_position", "bottom"))
        cw, ch = img.width - 2 * px, img.height - 2 * py
        x = (W - cw) // 2 - px
        if isinstance(pos, (list, tuple)):
            x = int(pos[0] * W - cw / 2) - px
            y = int(pos[1] * H - ch / 2) - py
        elif pos == "top":
            y = (int(by + H * 0.05) if framed and not vertical else int(H * 0.06)) - py
            if vertical and framed:
                y = max(int(H * 0.03), by - ch - int(H * 0.025)) - py
        elif pos == "center":
            y = (H - ch) // 2 - py
        else:
            if vertical and framed:
                y = by + ih + int(H * 0.03) - py
            elif framed:
                y = by + ih - ch - int(H * 0.05) - py
            else:
                y = H - ch - int(H * 0.07) - py
        fd = min(0.3, d / 4)
        fc.append(f"[{k}:v]format=rgba,fade=t=in:st=0:d={_num(fd)}:alpha=1,"
                  f"fade=t=out:st={_num(d - fd)}:d={_num(fd)}:alpha=1,setpts=PTS-STARTPTS+{_num(s)}/TB[cp{i}]")
        if anim == "slide":
            off = int(H * 0.02)
            yexp = f"{y}+{off}*pow(1-clip((t-{_num(s)})/0.4,0,1),3)"
        else:
            yexp = str(y)
        fc.append(f"[{cur}][cp{i}]overlay=x={x}:y='{yexp}':eof_action=pass:"
                  f"enable='between(t,{_num(s)},{_num(e)})'[cap{i}]")
        cur = f"cap{i}"

    # 6) intro / outro
    xf = float(style.get("transition", 0.5))
    total = body_d
    fc.append(f"[{cur}]format=yuv420p,setsar=1[body]")
    cur = "body"
    intro_d = 0.0
    if plan.get("intro"):
        it = plan["intro"]
        intro_d = float(it.get("duration", 2.5))
        card = _card_image(it, (W, H), base_dir) or graphics.title_card(
            (W, H), it.get("title", ""), it.get("subtitle"), it.get("cta"),
            it.get("logo"), it.get("background", bg_spec if framed else "midnight"),
            accent, font_path, it.get("kicker"))
        k = add_image(card, "intro.png", intro_d)
        fc.append(f"[{k}:v]format=yuv420p,setsar=1[intro]")
        fc.append(f"[intro][{cur}]xfade=transition=fade:duration={_num(xf)}:offset={_num(intro_d - xf)}[wi]")
        cur = "wi"
        total = intro_d + body_d - xf
    if plan.get("outro"):
        ot = plan["outro"]
        od = float(ot.get("duration", 3.0))
        card = _card_image(ot, (W, H), base_dir) or graphics.title_card(
            (W, H), ot.get("title", ""), ot.get("subtitle"), ot.get("cta"),
            ot.get("logo"), ot.get("background", bg_spec if framed else "midnight"),
            accent, font_path, ot.get("kicker"))
        k = add_image(card, "outro.png", od)
        fc.append(f"[{k}:v]format=yuv420p,setsar=1[outro]")
        fc.append(f"[{cur}][outro]xfade=transition=fade:duration={_num(xf)}:offset={_num(total - xf)}[wo]")
        cur = "wo"
        total = total + od - xf
    fade_out = float(style.get("fade_out", 0))
    if fade_out:
        fc.append(f"[{cur}]fade=t=out:st={_num(total - fade_out)}:d={_num(fade_out)}[vf]")
        cur = "vf"
    vout = cur

    # 7) audio
    audio_cfg = plan.get("audio") or {}
    alabels = []
    lead = intro_d - xf if intro_d else 0.0
    if info["has_audio"] and audio_cfg.get("keep", True) and still is None:
        for i, (a, b, s) in enumerate(segs):
            chain = f"[0:a]atrim=start={_num(a)}:end={_num(b)},asetpts=PTS-STARTPTS"
            if abs(s - 1) > 1e-6:
                rem = s
                while rem > 2.0:
                    chain += ",atempo=2.0"
                    rem /= 2.0
                chain += f",atempo={_num(rem)}"
                if not audio_cfg.get("keep_sped_up", False):
                    chain += ",volume=0"
            fc.append(chain + f"[as{i}]")
        fc.append("".join(f"[as{i}]" for i in range(len(segs))) + f"concat=n={len(segs)}:v=0:a=1,"
                  f"volume={_num(float(audio_cfg.get('volume', 1.0)))},"
                  f"adelay={int(lead * 1000)}:all=1[srca]")
        alabels.append("srca")
    music = audio_cfg.get("music")
    if music and still is None:
        mp = os.path.expanduser(music)
        if not os.path.isabs(mp):
            mp = os.path.join(base_dir, mp)
        inputs.append(["-stream_loop", "-1", "-i", mp])
        k = len(inputs) - 1
        mv = float(audio_cfg.get("music_volume", 0.25))
        mf = float(audio_cfg.get("music_fade", 2.0))
        fc.append(f"[{k}:a]atrim=0:{_num(total)},asetpts=PTS-STARTPTS,volume={_num(mv)},"
                  f"afade=t=in:d=0.8,afade=t=out:st={_num(max(0, total - mf))}:d={_num(mf)}[mus]")
        alabels.append("mus")
    aout = None
    if len(alabels) == 2:
        fc.append("[srca][mus]amix=inputs=2:duration=first:normalize=0[aout]")
        aout = "aout"
    elif alabels:
        aout = alabels[0]
    if aout:
        fc.append(f"[{aout}]apad,atrim=0:{_num(total)}[afinal]")
        aout = "afinal"

    # 8) encode
    out_path = os.path.expanduser(out.get("path", "demo.mp4"))
    if not os.path.isabs(out_path):
        out_path = os.path.join(base_dir, out_path)
    os.makedirs(os.path.dirname(os.path.abspath(out_path)) or ".", exist_ok=True)
    graph = ";\n".join(fc)
    gpath = os.path.join(tmp, "graph.txt")
    with open(gpath, "w") as f:
        f.write(graph)

    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-stats"]
    for a in inputs:
        cmd += a
    cmd += ["-/filter_complex", gpath, "-map", f"[{vout}]"]
    if still is not None:
        root, _ = os.path.splitext(out_path)
        out_path = f"{root}.still-{_num(float(still))}s.png"
        cmd += ["-ss", _num(float(still)), "-frames:v", "1", "-update", "1", out_path]
    else:
        if aout:
            cmd += ["-map", f"[{aout}]", "-c:a", "aac", "-b:a", "192k"]
        q = quality or style.get("quality", "standard")
        if q == "fast-hw":
            cmd += ["-c:v", "h264_videotoolbox", "-b:v", f"{int(W * H * fps / 1e6 * 0.12)}M"]
        else:
            preset, crf = QUALITY.get(q, QUALITY["standard"])
            cmd += ["-c:v", "libx264", "-preset", preset, "-crf", str(crf)]
        cmd += ["-pix_fmt", "yuv420p", "-r", _num(fps), "-t", _num(total), "-movflags", "+faststart"]
        gif = out_path.lower().endswith(".gif")
        target = out_path[:-4] + ".tmp.mp4" if gif else out_path
        cmd += [target]
    print(f"rendering {out.get('aspect', '')} {W}x{H} @ {_num(fps)}fps, {total:.1f}s -> {out_path}", file=sys.stderr)
    res = subprocess.run(cmd, stderr=subprocess.PIPE, text=True)
    if res.returncode != 0 and "-/filter_complex" in cmd and "Unrecognized option" in res.stderr:
        i = cmd.index("-/filter_complex")
        cmd[i] = "-filter_complex_script"   # ffmpeg < 7
        res = subprocess.run(cmd, stderr=subprocess.PIPE, text=True)
    if res.returncode != 0:
        die(f"ffmpeg failed:\n{res.stderr[-3000:]}\n(filter graph: {gpath}; re-run with --keep-temp to inspect)")
    if still is None and out_path.lower().endswith(".gif"):
        gw = int(out.get("gif_width", min(960, W)))
        gfps = int(out.get("gif_fps", 15))
        run(["ffmpeg", "-v", "error", "-y", "-i", target, "-vf",
             f"fps={gfps},scale={gw}:-1:flags=lanczos,split[a][b];[a]palettegen=stats_mode=diff[p];"
             f"[b][p]paletteuse=dither=sierra2_4a", out_path])
        os.remove(target)
    return out_path


def _card_image(card, size, base_dir):
    """Intro/outro given as a ready-made image (`"image": "intro.png"`), scaled to cover the canvas."""
    path = card.get("image")
    if not path:
        return None
    path = os.path.expanduser(path)
    if not os.path.isabs(path):
        path = os.path.join(base_dir, path)
    if not os.path.exists(path):
        die(f"intro/outro image not found: {path}")
    return graphics.background(size, "image:" + path)
