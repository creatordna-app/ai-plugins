"""All on-screen graphics, rendered with Pillow as transparent PNGs.

Everything is drawn at SS x resolution and downsampled with LANCZOS, which gives
clean anti-aliased text, rounded corners and soft shadows at any output size.
"""
import os
import re

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

from .common import FONT_DIR, hex_rgba

SS = 2  # supersampling factor

THEMES = {
    "dark":  {"bg": "#111114E0", "fg": "#FFFFFF", "muted": "#A1A1AA", "border": "#FFFFFF1A", "shadow": 110, "weight": "SemiBold"},
    "light": {"bg": "#FFFFFFF5", "fg": "#0A0A0B", "muted": "#52525B", "border": "#0000000D", "shadow": 70, "weight": "SemiBold"},
    "glass": {"bg": "#FFFFFF30", "fg": "#FFFFFF", "muted": "#F4F4F5", "border": "#FFFFFF66", "shadow": 60, "weight": "SemiBold"},
    "bold":  {"bg": None,        "fg": "#FFFFFF", "muted": "#FFFFFFCC", "border": "#FFFFFF00", "shadow": 120, "weight": "ExtraBold", "size": 1.3},
    "minimal": {"bg": "#00000000", "fg": "#FFFFFF", "muted": "#E4E4E7", "border": "#00000000", "shadow": 0, "weight": "Bold",
                "text_shadow": True},
}

# Background presets: a 3x3 colour mesh that is upscaled bicubically into a soft gradient.
BACKGROUNDS = {
    "aurora":   ["#1E1B4B", "#4C1D95", "#831843", "#312E81", "#6D28D9", "#BE185D", "#1E1B4B", "#5B21B6", "#9D174D"],
    "sunset":   ["#7C2D12", "#C2410C", "#F59E0B", "#9A3412", "#EA580C", "#FBBF24", "#831843", "#DB2777", "#F97316"],
    "ocean":    ["#082F49", "#0C4A6E", "#155E75", "#0E7490", "#0891B2", "#06B6D4", "#164E63", "#0369A1", "#22D3EE"],
    "mint":     ["#064E3B", "#047857", "#10B981", "#065F46", "#059669", "#34D399", "#022C22", "#0F766E", "#2DD4BF"],
    "midnight": ["#020617", "#0F172A", "#1E1B4B", "#0F172A", "#1E293B", "#312E81", "#020617", "#0F172A", "#1E1B4B"],
    "graphite": ["#09090B", "#18181B", "#27272A", "#18181B", "#27272A", "#3F3F46", "#09090B", "#18181B", "#27272A"],
    "peach":    ["#FED7AA", "#FBCFE8", "#DDD6FE", "#FDE68A", "#FECACA", "#C7D2FE", "#FEF3C7", "#FBCFE8", "#BAE6FD"],
    "paper":    ["#FAFAF9", "#F5F5F4", "#E7E5E4", "#F5F5F4", "#FAFAF9", "#F5F5F4", "#E7E5E4", "#F5F5F4", "#FAFAF9"],
    "candy":    ["#F472B6", "#A78BFA", "#60A5FA", "#FB7185", "#C084FC", "#38BDF8", "#FDA4AF", "#818CF8", "#67E8F9"],
}
LIGHT_BACKGROUNDS = {"peach", "paper", "candy"}

_font_cache = {}


def font(px, weight="SemiBold", path=None):
    """Load a font. Defaults to bundled Inter (variable); `path` may be any .ttf/.otf."""
    key = (int(px), weight, path)
    if key in _font_cache:
        return _font_cache[key]
    p = path or os.path.join(FONT_DIR, "Inter.ttf")
    f = ImageFont.truetype(p, int(px))
    if path is None or p.endswith("Inter.ttf"):
        try:
            f.set_variation_by_name(weight)
        except Exception:
            pass
    _font_cache[key] = f
    return f


# ---------- backgrounds & framing ----------------------------------------------------------

def background(size, spec):
    """spec: preset name | '#hex' | 'image:/path' | {'type':'gradient','colors':[...9 or 4...]}"""
    W, H = size
    if isinstance(spec, dict):
        colors = spec.get("colors") or BACKGROUNDS["aurora"]
    elif isinstance(spec, str) and spec.startswith("#"):
        return Image.new("RGB", size, hex_rgba(spec)[:3])
    elif isinstance(spec, str) and spec.startswith("image:"):
        img = Image.open(os.path.expanduser(spec[6:])).convert("RGB")
        s = max(W / img.width, H / img.height)
        img = img.resize((int(img.width * s + 1), int(img.height * s + 1)), Image.LANCZOS)
        l, t = (img.width - W) // 2, (img.height - H) // 2
        return img.crop((l, t, l + W, t + H))
    else:
        colors = BACKGROUNDS.get(spec or "aurora", BACKGROUNDS["aurora"])
    n = 3 if len(colors) >= 9 else 2
    mesh = Image.new("RGB", (n, n))
    for i in range(n * n):
        mesh.putpixel((i % n, i // n), hex_rgba(colors[i])[:3])
    small = mesh.resize((64, max(2, int(64 * H / W))), Image.BICUBIC).filter(ImageFilter.GaussianBlur(6))
    img = small.resize(size, Image.BICUBIC)
    # a little grain prevents banding once h264 quantises the gradient
    noise = Image.effect_noise(size, 12).convert("RGB")
    return Image.blend(img, ImageChops.add(img, noise, scale=1, offset=-128), 0.06)


def rounded_mask(size, radius, ss=4):
    W, H = size
    m = Image.new("L", (W * ss, H * ss), 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, W * ss - 1, H * ss - 1], radius * ss, fill=255)
    return m.resize(size, Image.LANCZOS)


def frame_overlay(canvas, box, radius, bg_spec, shadow=True, border=True):
    """Canvas-sized RGBA: background + shadow with a rounded transparent hole where the video sits."""
    W, H = canvas
    x, y, w, h = box
    img = background(canvas, bg_spec).convert("RGBA")
    if shadow:
        sh = Image.new("L", canvas, 0)
        blur = max(8, int(min(W, H) * 0.03))
        ImageDraw.Draw(sh).rounded_rectangle([x, y + blur // 2, x + w, y + h + blur // 2], radius, fill=150)
        sh = sh.filter(ImageFilter.GaussianBlur(blur))
        img = Image.composite(Image.new("RGBA", canvas, (0, 0, 0, 255)), img, sh)
    hole = Image.new("L", canvas, 255)
    hole.paste(ImageChops.invert(rounded_mask((w, h), radius)), (x, y))
    img.putalpha(hole)
    if border:
        ring = Image.new("RGBA", ((w + 4) * SS, (h + 4) * SS), (0, 0, 0, 0))
        ImageDraw.Draw(ring).rounded_rectangle([0, 0, ring.width - 1, ring.height - 1], (radius + 2) * SS,
                                               outline=(255, 255, 255, 40), width=2 * SS)
        ring = ring.resize((w + 4, h + 4), Image.LANCZOS)
        img.alpha_composite(ring, (x - 2, y - 2))
    return img


# ---------- text layout ---------------------------------------------------------------------

def _runs(text):
    """'Click *New Project*' -> [('Click ', False), ('New Project', True)]"""
    out = []
    for i, part in enumerate(re.split(r"\*([^*]+)\*", text)):
        if part:
            out.append((part, i % 2 == 1))
    return out


def _words(text):
    """Split into words; each word is a list of (chunk, accent) so '*dark*:' stays one word."""
    words, cur = [], []
    for chunk, acc in _runs(text):
        parts = re.split(r"(\s+)", chunk)
        for part in parts:
            if not part:
                continue
            if part.isspace():
                if cur:
                    words.append(cur)
                    cur = []
            else:
                cur.append((part, acc))
    if cur:
        words.append(cur)
    return words


def _word_w(word, fnt):
    return sum(fnt.getlength(c) for c, _ in word)


def _wrap(text, fnt, max_w):
    space = fnt.getlength(" ")
    lines, cur, cur_w = [], [], 0
    for wd in _words(text):
        ww = _word_w(wd, fnt)
        add = ww + (space if cur else 0)
        if cur and cur_w + add > max_w:
            lines.append(cur)
            cur, cur_w = [], 0
            add = ww
        cur.append(wd)
        cur_w += add
    if cur:
        lines.append(cur)
    return lines, space


def _line_w(line, fnt, space):
    return sum(_word_w(w, fnt) for w in line) + space * (len(line) - 1)


def _draw_lines(d, lines, fnt, space, x, y, lh, fg, accent, align_w=None, shadow_layer=None):
    for line in lines:
        lx = x
        if align_w is not None:
            lx = x + (align_w - _line_w(line, fnt, space)) / 2
        for word in line:
            for chunk, acc in word:
                if shadow_layer is not None:
                    shadow_layer.text((lx, y), chunk, font=fnt, fill=(0, 0, 0, 200))
                d.text((lx, y), chunk, font=fnt, fill=accent if acc else fg)
                lx += fnt.getlength(chunk)
            lx += space
        y += lh
    return y


def _with_shadow(layer, strength, blur, dy):
    """Composite a soft drop shadow (from layer alpha) underneath layer."""
    if strength <= 0:
        return layer
    a = layer.getchannel("A").point(lambda v: v * strength // 255)
    sh = Image.new("RGBA", layer.size, (0, 0, 0, 0))
    sh.putalpha(a)
    sh = sh.filter(ImageFilter.GaussianBlur(blur))
    out = Image.new("RGBA", layer.size, (0, 0, 0, 0))
    out.alpha_composite(sh, (0, dy))
    out.alpha_composite(layer)
    return out


# ---------- captions ------------------------------------------------------------------------

def caption(text, canvas_size, theme="dark", accent="#6366F1", step=None, sub=None, max_w_frac=0.8,
            font_path=None, scale=1.0, align="center"):
    """Pill caption. Returns (RGBA image, (pad_x, pad_y)) where pad is the shadow margin around the pill."""
    th = dict(THEMES.get(theme, THEMES["dark"]))
    acc = hex_rgba(accent)
    fg = hex_rgba(th["fg"])
    base = min(canvas_size) * 0.034 * th.get("size", 1.0) * scale
    fs = int(base * SS)
    f = font(fs, th["weight"], font_path)
    fsub = font(int(fs * 0.72), "Medium", font_path)
    pad_x, pad_y = int(fs * 0.85), int(fs * 0.55)
    badge = int(fs * 1.35) if step is not None else 0
    gap = int(fs * 0.5) if badge else 0
    max_text_w = canvas_size[0] * max_w_frac * SS - 2 * pad_x - badge - gap
    lines, space = _wrap(text, f, max_text_w)
    lh = int(fs * 1.28)
    sub_lines, sub_space = _wrap(sub, fsub, max_text_w) if sub else ([], 0)
    slh = int(fs * 0.72 * 1.35)
    text_w = max([_line_w(l, f, space) for l in lines] + [_line_w(l, fsub, sub_space) for l in sub_lines] + [1])
    text_h = lh * len(lines) + (int(fs * 0.25) + slh * len(sub_lines) if sub_lines else 0) - int(fs * 0.28)
    inner_h = max(text_h, badge)
    pw, ph = int(pad_x * 2 + badge + gap + text_w), int(pad_y * 2 + inner_h)
    if theme == "minimal":
        pad_x = pad_y = int(fs * 0.2)
        pw, ph = int(pad_x * 2 + badge + gap + text_w), int(pad_y * 2 + inner_h)

    m = int(fs * 1.2)  # margin for shadow
    layer = Image.new("RGBA", (pw + 2 * m, ph + 2 * m), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    bg = hex_rgba(th["bg"]) if th["bg"] else acc
    radius = int(min(ph / 2, fs * 0.9)) if len(lines) + len(sub_lines) > 1 else ph // 2
    d.rounded_rectangle([m, m, m + pw, m + ph], radius, fill=bg,
                        outline=hex_rgba(th["border"]), width=max(1, SS))
    tx = m + pad_x
    if badge:
        by = m + (ph - badge) // 2
        bfill = (255, 255, 255, 255) if theme == "bold" else acc
        d.ellipse([tx, by, tx + badge, by + badge], fill=bfill)
        bf = font(int(badge * 0.55), "Bold", font_path)
        s = str(step)
        bcol = acc if theme == "bold" else (255, 255, 255, 255)
        d.text((tx + badge / 2, by + badge / 2), s, font=bf, fill=bcol, anchor="mm")
        tx += badge + gap
    ty = m + (ph - text_h) // 2 - int(fs * 0.08)
    accent_col = (255, 243, 176, 255) if theme in ("bold", "glass") else acc
    tshadow = None
    if th.get("text_shadow"):
        tl = Image.new("RGBA", layer.size, (0, 0, 0, 0))
        tshadow = ImageDraw.Draw(tl)
    aw = text_w if align == "center" else None
    y = _draw_lines(d, lines, f, space, tx, ty, lh, fg, accent_col, aw, tshadow)
    if sub_lines:
        _draw_lines(d, sub_lines, fsub, sub_space, tx, y + int(fs * 0.25) - int(fs * 0.28) + int(fs * 0.28),
                    slh, hex_rgba(th["muted"]), accent_col, aw)
    if tshadow is not None:
        tl = tl.filter(ImageFilter.GaussianBlur(fs * 0.12))
        tl.alpha_composite(layer)
        layer = tl
    layer = _with_shadow(layer, th["shadow"], fs * 0.35, int(fs * 0.18))
    out = layer.resize((layer.width // SS, layer.height // SS), Image.LANCZOS)
    return out, (m // SS, m // SS)


# ---------- callouts (drawn in source-video pixel space) -------------------------------------

def callout(shape, src_size, x, y, w=0.0, h=0.0, label=None, label_pos="auto", accent="#6366F1",
            theme="dark", font_path=None):
    """Returns (RGBA image, (left, top)) in source-video pixels."""
    SW, SH = src_size
    u = SW / 1920.0            # unit relative to a 1080p-wide frame
    acc = hex_rgba(accent)
    cx, cy = x * SW, y * SH
    elems = []                 # (image, left, top)

    if shape in ("ring", "spotlight", "dot"):
        r = (max(w, h) * SW / 2) if (w or h) else 34 * u
        lw = max(3, int(5 * u))
        size = int((r + lw * 4) * 2)
        im = Image.new("RGBA", (size * SS, size * SS), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        c = size * SS / 2
        rr = r * SS
        if shape == "dot":
            d.ellipse([c - rr * 0.35, c - rr * 0.35, c + rr * 0.35, c + rr * 0.35], fill=acc)
        d.ellipse([c - rr, c - rr, c + rr, c + rr], fill=acc[:3] + (46,), outline=acc, width=lw * SS)
        im = _with_shadow(im, 90, 6 * u * SS, int(2 * u * SS))
        im = im.resize((size, size), Image.LANCZOS)
        elems.append((im, int(cx - size / 2), int(cy - size / 2)))
        target = (cx - r, cy - r, cx + r, cy + r)
    elif shape == "box":
        bw, bh = w * SW, h * SH
        lw = max(3, int(4 * u))
        m = lw * 4
        im = Image.new("RGBA", (int((bw + 2 * m) * SS), int((bh + 2 * m) * SS)), (0, 0, 0, 0))
        ImageDraw.Draw(im).rounded_rectangle([m * SS, m * SS, (m + bw) * SS, (m + bh) * SS], int(12 * u * SS),
                                             fill=acc[:3] + (28,), outline=acc, width=lw * SS)
        im = _with_shadow(im, 80, 6 * u * SS, int(2 * u * SS))
        im = im.resize((int(bw + 2 * m), int(bh + 2 * m)), Image.LANCZOS)
        left, top = int(cx - bw / 2 - m), int(cy - bh / 2 - m)
        elems.append((im, left, top))
        target = (cx - bw / 2, cy - bh / 2, cx + bw / 2, cy + bh / 2)
    else:
        target = (cx, cy, cx, cy)

    if label:
        lab, pad = caption(label, (1920, 1080), theme=theme, accent=accent, max_w_frac=0.3,
                           font_path=font_path, scale=0.8)
        lab = lab.resize((int(lab.width * u), int(lab.height * u)), Image.LANCZOS)
        px, py = pad[0] * u, pad[1] * u
        gap = 14 * u
        pos = label_pos
        if pos == "auto":
            pos = "below" if y < 0.35 else "above"
        lw_, lh_ = lab.width - 2 * px, lab.height - 2 * py
        tx0, ty0, tx1, ty1 = target
        mid = (tx0 + tx1) / 2
        if pos == "above":
            left, top = mid - lw_ / 2, ty0 - gap - lh_
        elif pos == "below":
            left, top = mid - lw_ / 2, ty1 + gap
        elif pos == "left":
            left, top = tx0 - gap - lw_, (ty0 + ty1) / 2 - lh_ / 2
        else:
            left, top = tx1 + gap, (ty0 + ty1) / 2 - lh_ / 2
        left = min(max(left, 8 * u), SW - lw_ - 8 * u)
        top = min(max(top, 8 * u), SH - lh_ - 8 * u)
        elems.append((lab, int(left - px), int(top - py)))

    L = min(e[1] for e in elems)
    T = min(e[2] for e in elems)
    R = max(e[1] + e[0].width for e in elems)
    B = max(e[2] + e[0].height for e in elems)
    out = Image.new("RGBA", (R - L, B - T), (0, 0, 0, 0))
    for im, l, t in elems:
        out.alpha_composite(im, (l - L, t - T))
    return out, (L, T)


# ---------- title / outro cards --------------------------------------------------------------

def title_card(canvas, title, subtitle=None, cta=None, logo=None, bg_spec="aurora", accent="#6366F1",
               font_path=None, kicker=None):
    W, H = canvas
    img = background(canvas, bg_spec).convert("RGBA")
    light = isinstance(bg_spec, str) and bg_spec in LIGHT_BACKGROUNDS
    fg = (10, 10, 11, 255) if light else (255, 255, 255, 255)
    muted = (82, 82, 91, 255) if light else (228, 228, 231, 220)
    layer = Image.new("RGBA", (W * SS, H * SS), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    u = min(W, H) * SS
    blocks = []  # (kind, payload, height)
    if logo and os.path.exists(os.path.expanduser(logo)):
        lg = Image.open(os.path.expanduser(logo)).convert("RGBA")
        lh = int(u * 0.12)
        lg = lg.resize((int(lg.width * lh / lg.height), lh), Image.LANCZOS)
        blocks.append(("img", lg, lh + int(u * 0.04)))
    maxw = W * SS * 0.82
    if kicker:
        fk = font(int(u * 0.028), "SemiBold", font_path)
        blocks.append(("kicker", (kicker.upper(), fk), int(u * 0.028 * 1.9)))
    ft = font(int(u * 0.075), "Bold", font_path)
    tl, ts = _wrap(title, ft, maxw)
    blocks.append(("text", (tl, ft, ts, fg, int(u * 0.075 * 1.12)), int(u * 0.075 * 1.12) * len(tl)))
    if subtitle:
        fs_ = font(int(u * 0.034), "Medium", font_path)
        sl, ss_ = _wrap(subtitle, fs_, maxw * 0.9)
        blocks.append(("gap", None, int(u * 0.025)))
        blocks.append(("text", (sl, fs_, ss_, muted, int(u * 0.034 * 1.4)), int(u * 0.034 * 1.4) * len(sl)))
    if cta:
        blocks.append(("gap", None, int(u * 0.05)))
        fc = font(int(u * 0.032), "SemiBold", font_path)
        blocks.append(("cta", (cta, fc), int(u * 0.032 * 2.4)))
    total = sum(b[2] for b in blocks)
    y = (H * SS - total) / 2
    acc = hex_rgba(accent)
    for kind, p, h in blocks:
        if kind == "img":
            layer.alpha_composite(p, (int((W * SS - p.width) / 2), int(y)))
        elif kind == "kicker":
            txt, fk = p
            d.text((W * SS / 2, y), txt, font=fk, fill=acc if light else (255, 255, 255, 190), anchor="ma")
        elif kind == "text":
            lines, f, sp, col, lh = p
            accent_col = acc if light else (255, 243, 176, 255)
            yy = y
            for line in lines:
                lx = (W * SS - _line_w(line, f, sp)) / 2
                for word in line:
                    for chunk, a in word:
                        d.text((lx, yy), chunk, font=f, fill=accent_col if a else col)
                        lx += f.getlength(chunk)
                    lx += sp
                yy += lh
        elif kind == "cta":
            txt, fc = p
            tw = fc.getlength(txt)
            bw, bh = tw + u * 0.07, h * 0.82
            x0 = (W * SS - bw) / 2
            d.rounded_rectangle([x0, y, x0 + bw, y + bh], bh / 2,
                                fill=(255, 255, 255, 255) if not light else acc)
            d.text((W * SS / 2, y + bh / 2), txt, font=fc,
                   fill=(10, 10, 11, 255) if not light else (255, 255, 255, 255), anchor="mm")
        y += h
    layer = _with_shadow(layer, 0 if light else 70, u * 0.01, int(u * 0.004))
    img.alpha_composite(layer.resize((W, H), Image.LANCZOS))
    return img.convert("RGB")
