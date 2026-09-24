#!/usr/bin/env python3
"""product-demo: turn a raw screen recording into a polished product demo video.

  demo.py setup                                install Pillow + ffmpeg (no admin rights needed)
  demo.py doctor                               check ffmpeg / Pillow
  demo.py analyze REC.mov [-o work/]           activity + contact sheets + draft plan
  demo.py frame REC.mov 12.5 [-o f.png]        one frame with a 0-1 coordinate grid
  demo.py render plan.json [--still 4.0]       render outputs (or a single preview still)
  demo.py timeline plan.json                   where captions/zooms land in the output
  demo.py styles [-o dir/]                     preview sheet of themes and backgrounds
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from pdv import analyze as A  # noqa: E402
    from pdv import graphics as G  # noqa: E402
    from pdv import render as R  # noqa: E402
except ImportError as e:  # Pillow missing: only `setup` / `doctor` can run
    A = G = R = None
    MISSING = e
from pdv.common import die, fmt_t, load_json, probe, save_json, use_bundled_ffmpeg  # noqa: E402


def cmd_setup(_):
    import shutil
    import subprocess
    pkgs = ["Pillow"]
    if not (shutil.which("ffmpeg") and shutil.which("ffprobe")):
        pkgs.append("static-ffmpeg")
    pip = [sys.executable, "-m", "pip", "install", "--quiet", "--disable-pip-version-check"]
    if sys.prefix == sys.base_prefix:  # not in a virtualenv
        pip.append("--user")
    print(f"installing {', '.join(pkgs)} ...")
    if subprocess.run(pip + pkgs).returncode != 0:
        # Homebrew / Debian Pythons refuse --user installs without this flag (PEP 668)
        if subprocess.run(pip + ["--break-system-packages"] + pkgs).returncode != 0:
            die("pip install failed; try: python3 -m pip install " + " ".join(pkgs))
    # fresh interpreter so the newly installed packages are importable; downloads ffmpeg if needed
    sys.exit(subprocess.run([sys.executable, os.path.abspath(__file__), "doctor"]).returncode)


def cmd_doctor(_):
    import shutil
    import subprocess
    use_bundled_ffmpeg()
    ok = True
    for b in ("ffmpeg", "ffprobe"):
        p = shutil.which(b)
        print(f"{b:8} {'OK  ' + p if p else 'MISSING'}")
        ok &= bool(p)
    if shutil.which("ffmpeg"):
        v = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True).stdout.split("\n")[0]
        print(f"         {v}")
        enc = subprocess.run(["ffmpeg", "-hide_banner", "-encoders"], capture_output=True, text=True).stdout
        print(f"libx264  {'OK' if 'libx264' in enc else 'MISSING (install a full ffmpeg build)'}")
        ok &= "libx264" in enc
    try:
        import PIL
        print(f"Pillow   OK  {PIL.__version__}")
    except ImportError:
        print("Pillow   MISSING  ->  run: demo.py setup")
        ok = False
    sys.exit(0 if ok else 1)


def cmd_analyze(a):
    out = a.out or os.path.join(os.path.dirname(os.path.abspath(a.input)), "demo-work")
    an = A.analyze(a.input, out, sample_fps=a.sample_fps, sheet_every=a.every)
    plan = A.draft_plan(an, idle_speed=a.idle_speed, idle_mode=a.idle_mode, max_zoom=a.max_zoom,
                        aspect=a.aspect)
    plan["outputs"][0]["path"] = os.path.join(out, plan["outputs"][0]["path"])
    plan_path = os.path.join(out, "plan.json")
    if os.path.exists(plan_path) and not a.force:
        plan_path = os.path.join(out, "plan.draft.json")
    save_json(plan, plan_path)
    v = an["video"]
    print(f"video     {v['width']}x{v['height']} @ {v['fps']}fps, {fmt_t(v['duration'])}, audio={v['has_audio']}")
    print(f"events    {len(an['events'])} activity bursts")
    for e in an["events"]:
        print(f"  {e['start']:7.2f}-{e['end']:7.2f}s  {e['kind']:6}  focus x{e['center'][0]:.2f} y{e['center'][1]:.2f}")
    print(f"idle      " + (", ".join(f"{s:.1f}-{t:.1f}s" for s, t in an["idle"]) or "none"))
    print("sheets    " + "\n          ".join(s["path"] + f"  ({s['from']}-{s['to']}s, every {s['every']}s)"
                                           for s in an["contact_sheets"]))
    print(f"plan      {plan_path}")


def cmd_frame(a):
    out = a.out or f"frame_{a.t:.2f}.png"
    print(A.grab_frame(a.input, a.t, out, grid=not a.no_grid))


def cmd_render(a):
    plan = load_json(a.plan)
    base = os.path.dirname(os.path.abspath(a.plan))
    paths = R.render(plan, only=a.only, still=a.still, quality=a.quality, keep_temp=a.keep_temp, base_dir=base)
    for p in paths:
        if p.endswith(".png"):
            print(p)
        else:
            info = probe(p)
            print(f"{p}  ({info['width']}x{info['height']}, {info['duration']:.1f}s, "
                  f"{os.path.getsize(p) / 1e6:.1f} MB)")


def cmd_timeline(a):
    plan = load_json(a.plan)
    src = os.path.expanduser(plan["input"])
    if not os.path.isabs(src):
        src = os.path.join(os.path.dirname(os.path.abspath(a.plan)), src)
    info = probe(src)
    segs = R.build_segments(plan, info["duration"])
    tl = R.Timeline(segs)
    xf = float((plan.get("style") or {}).get("transition", 0.5))
    lead = float(plan["intro"].get("duration", 2.5)) - xf if plan.get("intro") else 0.0
    o = lambda t: tl.map(t) + lead
    print(f"source {fmt_t(info['duration'])} -> body {tl.duration:.2f}s (+intro offset {lead:.2f}s)")
    print("segments (source -> output):")
    for (s, e, sp), st in zip(segs, tl.out_starts):
        print(f"  {s:7.2f}-{e:7.2f}s  x{sp:<5g} -> {st + lead:6.2f}-{st + lead + (e - s) / sp:6.2f}s")
    for k in plan.get("zoom", []):
        print(f"zoom    @{k['at']:6.2f}s -> {o(float(k['at'])):6.2f}s  scale {k.get('scale', 1)}")
    for c in plan.get("captions", []):
        print(f"caption {c['start']:6.2f}-{c['end']:6.2f}s -> {o(float(c['start'])):6.2f}-{o(float(c['end'])):6.2f}s  {c['text']}")
    for c in plan.get("callouts", []):
        print(f"callout {c['start']:6.2f}-{c['end']:6.2f}s -> {o(float(c['start'])):6.2f}-{o(float(c['end'])):6.2f}s  {c.get('text') or c.get('shape')}")


def cmd_styles(a):
    from PIL import Image, ImageDraw
    out = a.out or "."
    os.makedirs(out, exist_ok=True)
    W = 1920
    names = list(G.BACKGROUNDS)
    tw, th = 480, 270
    sheet = Image.new("RGB", (W, (len(names) + 3) // 4 * (th + 50) + 20), (18, 18, 20))
    d = ImageDraw.Draw(sheet)
    for i, n in enumerate(names):
        x, y = 20 + (i % 4) * (tw), 20 + (i // 4) * (th + 50)
        sheet.paste(G.background((tw - 20, th), n), (x, y))
        d.text((x, y + th + 8), n, font=G.font(24, "SemiBold"), fill=(240, 240, 240))
    p1 = os.path.join(out, "backgrounds.png")
    sheet.save(p1)
    themes = list(G.THEMES)
    bg = G.background((W, 200 * len(themes) + 40), "aurora").convert("RGBA")
    for i, t in enumerate(themes):
        img, _ = G.caption(f"Theme *{t}*: click New Project to start", (1920, 1080), t, "#6366F1", step=i + 1,
                           sub="optional sub-line for extra detail")
        bg.alpha_composite(img, ((W - img.width) // 2, 20 + i * 200))
    p2 = os.path.join(out, "themes.png")
    bg.convert("RGB").save(p2)
    print(p1)
    print(p2)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("setup").set_defaults(fn=cmd_setup)
    sub.add_parser("doctor").set_defaults(fn=cmd_doctor)

    p = sub.add_parser("analyze")
    p.add_argument("input")
    p.add_argument("-o", "--out")
    p.add_argument("--sample-fps", type=float, default=4.0)
    p.add_argument("--every", type=float, help="contact-sheet interval seconds (auto)")
    p.add_argument("--idle-speed", type=float, default=6.0)
    p.add_argument("--idle-mode", choices=["speed", "cut"], default="speed")
    p.add_argument("--max-zoom", type=float, default=2.0)
    p.add_argument("--aspect", default="16:9")
    p.add_argument("--force", action="store_true", help="overwrite existing plan.json")
    p.set_defaults(fn=cmd_analyze)

    p = sub.add_parser("frame")
    p.add_argument("input")
    p.add_argument("t", type=float)
    p.add_argument("-o", "--out")
    p.add_argument("--no-grid", action="store_true")
    p.set_defaults(fn=cmd_frame)

    p = sub.add_parser("render")
    p.add_argument("plan")
    p.add_argument("--only", nargs="*", help="render only these aspects/paths")
    p.add_argument("--still", type=float, help="write one PNG at this OUTPUT time instead of a video")
    p.add_argument("--quality", choices=(list(R.QUALITY) if R else []) + ["fast-hw"])
    p.add_argument("--keep-temp", action="store_true")
    p.set_defaults(fn=cmd_render)

    p = sub.add_parser("timeline")
    p.add_argument("plan")
    p.set_defaults(fn=cmd_timeline)

    p = sub.add_parser("styles")
    p.add_argument("-o", "--out")
    p.set_defaults(fn=cmd_styles)

    a = ap.parse_args()
    if R is None and a.cmd not in ("setup", "doctor"):
        die(f"{MISSING}. Run `python3 {os.path.abspath(__file__)} setup` first.")
    a.fn(a)


if __name__ == "__main__":
    main()
