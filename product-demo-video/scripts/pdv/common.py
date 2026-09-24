"""Shared helpers: ffmpeg/ffprobe wrappers, paths, small math utilities."""
import json
import os
import shutil
import subprocess
import sys

SKILL_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
ASSETS = os.path.join(SKILL_ROOT, "assets")
FONT_DIR = os.path.join(ASSETS, "fonts")


def die(msg, code=1):
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(code)


def use_bundled_ffmpeg():
    """Fall back to the static ffmpeg/ffprobe from the `static-ffmpeg` package (installed by
    `demo.py setup`) when they aren't on PATH. Downloads the binaries on first use."""
    if shutil.which("ffmpeg") and shutil.which("ffprobe"):
        return
    try:
        import static_ffmpeg
    except ImportError:
        return
    static_ffmpeg.add_paths(weak=True)


def need_bin(name):
    use_bundled_ffmpeg()
    path = shutil.which(name)
    if not path:
        die(f"'{name}' not found. Run `python3 {os.path.join(SKILL_ROOT, 'scripts', 'demo.py')} setup` "
            f"to install it automatically.")
    return path


def run(cmd, capture=False, quiet=False):
    if not quiet:
        print("$ " + " ".join(_shq(c) for c in cmd[:12]) + (" ..." if len(cmd) > 12 else ""), file=sys.stderr)
    res = subprocess.run(cmd, capture_output=True, text=not capture or capture == "text")
    if res.returncode != 0:
        err = res.stderr if isinstance(res.stderr, str) else res.stderr.decode("utf-8", "replace")
        die(f"command failed ({cmd[0]}):\n{err[-4000:]}")
    return res.stdout


def _shq(s):
    s = str(s)
    return s if s and all(c.isalnum() or c in "-_./:=" for c in s) else "'" + s.replace("'", "'\\''") + "'"


def probe(path):
    need_bin("ffprobe")
    if not os.path.exists(path):
        die(f"input not found: {path}")
    out = run(["ffprobe", "-v", "error", "-print_format", "json", "-show_streams", "-show_format", path],
              capture="text", quiet=True)
    info = json.loads(out)
    v = next((s for s in info["streams"] if s.get("codec_type") == "video"), None)
    if not v:
        die("no video stream in input")
    a = next((s for s in info["streams"] if s.get("codec_type") == "audio"), None)
    num, den = (v.get("avg_frame_rate") or v.get("r_frame_rate") or "30/1").split("/")
    fps = float(num) / float(den or 1) if float(den or 1) else 30.0
    w, h = int(v["width"]), int(v["height"])
    rot = 0
    for sd in v.get("side_data_list", []) or []:
        if "rotation" in sd:
            rot = int(sd["rotation"])
    if abs(rot) in (90, 270):
        w, h = h, w
    dur = float(info["format"].get("duration") or v.get("duration") or 0)
    return {"path": path, "width": w, "height": h, "fps": round(fps, 3), "duration": round(dur, 3),
            "has_audio": a is not None, "vcodec": v.get("codec_name")}


def load_json(path):
    with open(path) as f:
        return json.load(f)


def save_json(obj, path):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w") as f:
        json.dump(obj, f, indent=2)
        f.write("\n")


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def fmt_t(t):
    m, s = divmod(max(0.0, t), 60)
    return f"{int(m)}:{s:05.2f}"


def hex_rgba(value, alpha=None):
    """'#RRGGBB', '#RRGGBBAA', or [r,g,b(,a)] -> (r,g,b,a)."""
    if isinstance(value, (list, tuple)):
        r, g, b = value[:3]
        a = value[3] if len(value) > 3 else 255
    else:
        s = value.lstrip("#")
        if len(s) == 3:
            s = "".join(c * 2 for c in s)
        r, g, b = int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)
        a = int(s[6:8], 16) if len(s) == 8 else 255
    if alpha is not None:
        a = int(round(alpha * 255)) if alpha <= 1 else int(alpha)
    return (r, g, b, a)
