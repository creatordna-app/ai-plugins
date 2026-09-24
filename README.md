# Product Demo: turn screen recordings into polished demo videos

A free Claude skill by [CreatorDNA](https://creatordna.app). Give it a rough screen recording and Claude edits it into a clean,
share-ready product video. You don't need any video skills.

- Cuts the boring bits and speeds up loading and waiting
- Zooms in smoothly on what you click and type
- Adds step-by-step captions, highlight boxes, and intro and ending title screens
- Puts your video on a nice background with rounded corners
- Makes versions for YouTube (16:9), Reels, TikTok and Shorts (9:16), Instagram (1:1) and GIF
- Keeps your voice-over, and can add background music

Everything runs on your own computer. Nothing is uploaded anywhere, and all the code is in this
repository for you to read.

## Install

First, download **[product-demo-video.zip](product-demo-video.zip)**. Click it on this page, then
click the download button. It goes to your **Downloads** folder.

### Claude Desktop

1. Open the **Claude Desktop** app and click **Customize**.
2. Go to **Skills** and click **Upload**.
3. Choose `product-demo-video.zip`. Don't unzip it first.

The skill is now ready to use in any chat.

### Claude Code

Open a terminal and paste one command. It unzips the skill into Claude Code's skills folder.

**Mac or Linux:**
```bash
mkdir -p ~/.claude/skills && unzip -o ~/Downloads/product-demo-video.zip -d ~/.claude/skills
```

**Windows (PowerShell):**
```powershell
Expand-Archive -Force "$HOME\Downloads\product-demo-video.zip" "$HOME\.claude\skills"
```

Then restart Claude Code. To check it worked, type `/skills` and look for **product-demo-video**.

**To update later,** download the new zip and run the same command again.
**To remove it,** delete the `product-demo-video` folder inside `~/.claude/skills`.

## How to use it

**1. Record your screen**

- **Mac:** press `Cmd + Shift + 5`, choose what to record, then click **Record**. Click the stop button in the menu bar when you're done.
- **Windows:** open the **Snipping Tool** and choose the video option.

Do the task once at a normal speed. Pauses, loading screens and fumbling at the start are fine.
Claude cleans those up.

**2. Ask Claude**

In **Claude Desktop**, drag your recording into a chat. In **Claude Code**, give the file's
location instead, for example "the recording at ~/Desktop/recording.mov". Then say what it
shows. Some examples:

**A quick social clip**
> Make a product demo from this recording. It shows how to create a project in Acme.
> Add step captions, an intro saying "Ship faster with Acme", and an ending that says "Try it at acme.com".

**A vertical video for Reels, TikTok or Shorts**
> Turn this into a 20-second vertical video for Instagram Reels. It shows our new AI search.
> Zoom in on the search box and the results, and use our brand colour #6366F1.

**A step-by-step tutorial**
> Make a tutorial from this recording showing how to invite a teammate.
> Number each step, add a highlight box on the Invite button, and keep it under a minute.

**A launch video with music**
> Make a launch video from this recording for our new dashboard. Use the attached music,
> a dark style, and an ending with "Get early access at acme.com". Also make a 1:1 version for LinkedIn.

**A GIF for your website or docs**
> Make a short looping GIF from this recording showing how the export button works. No title screens.

You don't need to use these exact words. Describe what you want as you would to a video editor.

The first time, Claude spends about a minute setting up its video tools. Then it plans the edit,
checks how it looks, and gives you the finished video.

**3. Ask for changes**

- "Make a vertical version for Instagram Reels"
- "Use a light style and my brand colour #FF5A1F"
- "Zoom in less on the second step"
- "Add this music" *(attach an mp3)*
- "Show me the style options"
- "Make it a GIF too"

**Tips:** record in high resolution, turn off notifications first, and keep it short (15–45
seconds for social media). Tell Claude what your product is and what viewers should take away.

## License

MIT: free to use, share and change, including for commercial work. See [LICENSE](LICENSE).

Includes the Inter typeface © The Inter Project Authors, SIL Open Font License 1.1.
