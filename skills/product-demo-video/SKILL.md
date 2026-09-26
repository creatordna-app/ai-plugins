---
name: product-demo-video
description: Turn a raw screen recording (.mov/.mp4) into a polished product demo video — trims dead time, speeds up waiting/loading, auto-zooms and pans onto the action, adds step captions, callouts, intro/outro title cards, background frame, music, and exports 16:9 / 9:16 / 1:1 / GIF. Use when the user wants a product demo, feature walkthrough, launch video, tutorial clip or social video from a screen recording, or asks to add on-screen text/instructions to a recording.
---

# Product demo video

You are the editor. The scripts do the heavy lifting (analysis + rendering with ffmpeg and
Pillow); your job is to **look at the recording, understand the story, and write a good edit
plan**. All tooling lives in `scripts/demo.py` inside this skill's folder (the folder that
contains this SKILL.md). Below it is called `DEMO`:

```bash
DEMO="python3 <this skill's folder>/scripts/demo.py"
```

## Workflow

Many users are not technical. Talk in plain language (no "ffmpeg", "JSON", "CLI" unless they
use those words), never ask them to run terminal commands, and do setup yourself.

### 0. Preflight (once)
Run `$DEMO doctor`. If anything is MISSING, run `$DEMO setup` yourself. It pip-installs
Pillow and a portable ffmpeg (no admin rights or Homebrew needed; the first run downloads
~70 MB), then re-checks. Tell the user only "Setting up the video tools (one-time, ~1 min)".
If setup fails (e.g. no network), explain the problem in one plain sentence.

If the user attached/uploaded the recording, use that file's path. If they only describe it,
ask them to drag the video file into the chat.

### 1. Get the brief (keep it to one short message, use defaults for anything unanswered)
- Recording path (required).
- What product / what should a viewer take away? (1 line)
- Formats: default `16:9`; offer `9:16` (Reels/Shorts/TikTok), `1:1`, `4:5`, `.gif`.
- Text: step captions (default on), intro title + outro CTA (ask for the CTA text/URL), callouts.
- Look: theme (`dark` default, `light`, `glass`, `bold`, `minimal`), background preset, accent colour
  (use the product's brand colour if known), optional logo PNG, optional music file.

### 2. Analyze
```bash
$DEMO analyze REC.mov -o <workdir>          # workdir default: <rec dir>/demo-work
```
Outputs `analysis.json`, contact sheets `sheet_XX.jpg` (timestamped thumbnails), and a
`plan.json` draft (auto trim, idle speed-ups, zoom keyframes from motion). The printed
event list shows activity bursts (`local` = small region changing → zoom candidate,
`global` = page change/scroll) and idle stretches.

**Read every contact sheet image** (Read tool). Write down the story beat by beat:
what the user does, when, and where on screen. Timestamps on thumbnails are SOURCE seconds.

### 3. Pin down positions
For each moment you want to zoom into or annotate:
```bash
$DEMO frame REC.mov 12.4 -o <workdir>/f12.png   # frame with a 0–1 coordinate grid
```
Read the image and take `x`, `y` (0–1, fraction of width/height) from the grid.

### 4. Write the plan
Edit `<workdir>/plan.json` (full schema: `reference/plan-schema.md`). Rules of thumb:

- **All times are source seconds.** The renderer maps them through trims/cuts/speed-ups.
- **Trim** the start to just before the first meaningful action, and the end right after the
  payoff. Recordings often end with the stop-recording UI — cut it.
- **Waiting (AI thinking, loading, uploads):** `speed` 6–12× (keeps the "it's working" feel)
  or `cuts` if nothing on screen changes. Keep ~0.3 s at 1× on each side of a speed-up.
- **Typing** long text: speed 2–3×. **Mouse wandering:** speed or cut.
- **Zoom** only when the action is in a small area (inputs, menus, buttons, results).
  `scale` 1.3–2.0 (never > 2.5 — text gets soft). Put the keyframe ~0.3 s *before* the action.
  Hold each zoom ≥ 1.5 s; zoom back to `1.0` when the page changes or you need context.
  Consecutive keyframes pan smoothly — use that instead of zoom-out/zoom-in.
- **Captions** = the on-screen instructions. One per step, ≤ 7 words, imperative or benefit
  ("Type */write* and paste notes", "Get a *ready-to-post* draft"). `*word*` = accent colour.
  Use `step` numbers for tutorials, `sub` for a short second line. Each should be on screen
  ≥ 1.5 s of OUTPUT time (check with `timeline`).
- **Callouts** point at a UI element: `box` (w/h around a button/field), `ring`, or `dot`,
  optionally with a `text` label. Use sparingly — 1–3 per video.
- **Intro** (2–3 s): kicker + title + subtitle. **Outro** (3 s): title + `cta` pill (URL/action).
- Target length: 15–45 s for social, ≤ 90 s for walkthroughs.

### 5. Check before the full render
```bash
$DEMO timeline <workdir>/plan.json            # where every caption/zoom lands in OUTPUT time
$DEMO render <workdir>/plan.json --only 16:9 --still 6.5   # one frame, fast
```
Render stills at 3–5 key output times (each caption, each zoom) and **Read them**. Check that
the zoom target is actually in frame (content scrolls — targets move!), captions don't cover
the important UI, text is readable. Fix the plan and repeat. For `9:16`, the landscape
recording is shown in a square window that follows the zoom focus — give that output its
own gentler `zoom` list if wide content gets cropped (see per-output overrides).

### 6. Render
```bash
$DEMO render <workdir>/plan.json               # all outputs; add --quality draft for a quick pass
```
Rendering is roughly 2–4× realtime per output. Report each output path, duration and size, plus
a one-line summary of the edit (e.g. "38 s → 18 s: trimmed, 26 s wait sped 10×, 4 captions").
If the session has an outputs folder for sharing files with the user (e.g. Claude Desktop /
Cowork), copy the finished videos there so the user can open and download them.
Offer tweaks (different theme/background, more/less zoom, vertical cut, GIF).

## Notes
- Text is rendered with bundled Inter (OFL). `style.font` accepts any .ttf/.otf path.
  Colour emoji are not supported in captions — use plain text.
- `$DEMO styles -o dir/` renders preview sheets of all themes and backgrounds; show them if the
  user wants to choose a look.
- Works with any ffmpeg ≥ 5 build; no drawtext/libass needed.
- If the user supplies a voice-over/audio in the recording it is kept (muted during speed-ups
  unless `audio.keep_sped_up`). Background music: `audio.music` path + `audio.music_volume`.
