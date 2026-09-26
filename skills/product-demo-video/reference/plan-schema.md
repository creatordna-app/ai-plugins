# plan.json reference

All times are **source-recording seconds**. Coordinates `x`, `y`, `w`, `h` are **0–1 fractions**
of the source frame (use `demo.py frame REC t` to read them off a grid).

```jsonc
{
  "input": "/abs/or/relative/to/plan/recording.mov",

  "trim":  { "start": 0.4, "end": 37.0 },          // keep only this range
  "cuts":  [[12.0, 18.5]],                          // remove ranges entirely
  "speed": [{ "start": 4.4, "end": 30.6, "speed": 10 }],   // fast-forward ranges

  "zoom": [                                         // camera keyframes; eased transitions
    { "at": 0.4,  "scale": 1.7, "x": 0.40, "y": 0.72 }, // zoom to point (x,y = centre)
    { "at": 2.3,  "scale": 1.5, "x": 0.53, "y": 0.36 }, // pans smoothly from previous
    { "at": 30.8, "scale": 1.0 }                         // back to full view
  ],

  "captions": [
    {
      "start": 0.5, "end": 2.2,
      "text": "Click *New project* in Acme",   // *word* = accent colour
      "step": 1,                                      // optional numbered badge
      "sub": "Takes about 10 seconds",                // optional second line
      "position": "bottom",                           // bottom | top | center | [x, y] (canvas 0-1)
      "theme": "dark", "accent": "#7C3AED",           // optional per-caption overrides
      "scale": 1.0,                                   // text size multiplier
      "min_duration": 1.4                             // output seconds (extends end if too short)
    }
  ],

  "callouts": [
    { "start": 0.9, "end": 2.1, "shape": "box",  "x": 0.35, "y": 0.53, "w": 0.16, "h": 0.036 },
    { "start": 5.0, "end": 7.0, "shape": "ring", "x": 0.82, "y": 0.10, "text": "Share", "label_pos": "below" }
    // shape: box | ring | dot | none (label only). label_pos: auto | above | below | left | right
    // ring radius: w (fraction of width) or default ~34px@1080p
  ],

  "intro": { "kicker": "PRODUCT NAME", "title": "Headline with *accent*", "subtitle": "One line",
             "logo": "/path/logo.png", "duration": 2.6, "background": "aurora" },
  "outro": { "title": "Try *Product*", "subtitle": "…", "cta": "product.com", "duration": 3.0 },

  "style": {
    "theme": "dark",            // dark | light | glass | bold | minimal
    "accent": "#6366F1",
    "background": "aurora",     // aurora sunset ocean mint midnight graphite peach paper candy
                                // | "#101014" | "image:/path/bg.jpg" | {"colors":[9 hex]} | "none" (full-bleed)
    "padding": 0.06,            // frame padding (fraction of canvas)
    "radius": 22,               // corner radius, px at 1080p
    "shadow": true, "border": true,
    "fit": "contain",           // contain | cover (default cover for landscape→portrait)
    "vertical_box_aspect": 1.0, // w/h of the video window on portrait canvases
    "caption_position": "bottom",
    "caption_animation": "slide", // slide | fade
    "caption_scale": 1.0,
    "zoom_duration": 0.8,       // seconds per camera move
    "transition": 0.5,          // intro/outro crossfade seconds
    "fade_out": 0,              // fade the very end to black (seconds)
    "font": null,               // path to .ttf/.otf (default bundled Inter)
    "fps": 60,
    "quality": "standard"       // draft | standard | high | fast-hw (VideoToolbox, macOS)
  },

  "audio": {
    "keep": true,               // keep recording audio if present
    "keep_sped_up": false,      // audible during speed-ups (chipmunk) — usually false
    "volume": 1.0,
    "music": "/path/music.mp3", // looped + faded; optional
    "music_volume": 0.25,
    "music_fade": 2.0
  },

  "outputs": [
    { "aspect": "16:9", "path": "out/demo-16x9.mp4" },
    { "aspect": "9:16", "path": "out/demo-9x16.mp4",
      "zoom": [ { "at": 0.4, "scale": 1.3, "x": 0.4, "y": 0.7 } ],   // per-output overrides:
      "style": { "caption_scale": 1.1 } },                              // zoom captions callouts intro outro style
    { "aspect": "1:1", "path": "out/demo-1x1.mp4", "resolution": 1080 },
    { "aspect": "16:9", "path": "out/demo.gif", "gif_width": 960, "gif_fps": 15 }
  ]
  // aspect: 16:9 9:16 1:1 4:5 4:3 21:9, or "size": "2560x1440". resolution: short side (1080 default, 1440, 2160)
}
```

Relative paths (input, outputs, music) resolve against the plan file's folder.
Keys starting with `_` are ignored (the draft stores detected `_events` there for reference).
