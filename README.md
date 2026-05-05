# Soundboard

Cross-interface soundboard with a shared core: CLI, TUI (Textual), and desktop GUI (PySide6). Audio playback via `sounddevice` (PortAudio) with optional dual-output, library stored as TOML, cross-platform.

## Install & run

```bash
uv sync
uv run soundboard --help        # CLI
uv run soundboard-tui           # TUI
uv run soundboard-gui           # desktop GUI
```

## CLI cheatsheet

```bash
uv run soundboard add path/to/clip.wav --name horn --hotkey ctrl+h --tag funny --color red
uv run soundboard edit horn --volume 0.5 --add-tag loud --clear-hotkey --color "#22aa55"
uv run soundboard edit horn --clear-color
uv run soundboard list
uv run soundboard play horn
uv run soundboard stop
uv run soundboard remove horn
uv run soundboard where          # config/data paths
uv run soundboard devices        # audio output devices (P = primary, M = monitor)
uv run soundboard config show
uv run soundboard config set-device "VoiceMeeter Input (VB-Audio Voicemeeter VAIO)"
uv run soundboard config set-device --clear     # back to system default
uv run soundboard config set-monitor "Headphones (X)"   # mirror to a 2nd device
uv run soundboard config set-monitor --clear     # disable monitor output
```

## Grabbing clips from YouTube

Requires `ffmpeg` on PATH (yt-dlp uses it for the time-range extraction and mp3 conversion).

```bash
uv run soundboard fetch "https://youtu.be/XYZ" --start 1:23 --end 1:30 --name horn --tag funny
```

Timecodes accept `SS`, `MM:SS`, or `H:MM:SS` (fractional seconds OK). Omit `--start`/`--end` to pull the full audio. Personal use only — respect the source's licensing.

## Routing into a virtual meeting (Teams, Zoom, Meet…)

Meeting apps accept a single "microphone" input, so to have them hear both your voice and the soundboard you need an external routing tool that mixes them and exposes the result as a virtual mic. Once that tool is running, point the soundboard at its **virtual input** with `soundboard config set-device "<name>"` so non-soundboard audio (music, system sounds) does not leak into the call.

### Windows — plain VoiceMeeter (free) or Banana

1. Install [VoiceMeeter](https://vb-audio.com/Voicemeeter/) (plain or Banana). Reboot if prompted.
2. Windows sound settings: keep your regular speakers/headset as **default playback**; set your real mic as **default recording**.
3. Point soundboard at VoiceMeeter's virtual input. Run `uv run soundboard devices`, find the entry for the main VAIO virtual input, and feed it back:
   ```
   uv run soundboard config set-device "<paste the entry from the list>"
   ```
   Depending on your VB-Audio driver version that entry is one of:
   `Voicemeeter Input (VB-Audio Voicemeeter VAIO)` · `Voicemeeter In B1 (…)` · `Voicemeeter In 1 (…)`. They all land on the main VAIO strip. Ignore `In 2/3/4/5` (ASIO multichannel taps) and `AUX VAIO` (that's the second virtual input, only present in Banana).
4. Open VoiceMeeter. Route **Hardware Input 1** (your mic) and the **Voicemeeter VAIO** strip (soundboard) to both **A1** (your speakers/headphones, so you hear yourself + sounds) and **B1** (the virtual output Teams will read).
5. In Teams/Zoom/Meet, set the **Microphone** to the B1 virtual output. Depending on driver version this shows as one of: `Voicemeeter Output (VB-Audio Voicemeeter VAIO)` · `Voicemeeter Out B1 (…)` · `Voicemeeter Out 1 (…)`. Pick whichever you see. Avoid `Out 2` (that's B2, for a preview/monitor bus in Banana), and `Out 3/4/5` (multichannel taps).
6. Test: `uv run soundboard play <name>` — the Teams mic meter should react. To confirm it's B1: Teams → Settings → Devices → **Make a test call**; the bot will echo back whatever reaches your virtual mic.

Upgrade to Banana if you want per-strip gate/compressor/EQ on your mic, or use its B2 bus (Voicemeeter Aux Output / Out B2 / Out 2) for a headphone-only preview channel.

### Linux — PipeWire + Helvum

1. Install Helvum (`sudo apt install helvum`, `dnf install helvum`, etc.) — it's a visual PipeWire patch-bay. Alternative: `qpwgraph`.
2. Create a null sink that will act as the "virtual mic":
   ```bash
   pactl load-module module-null-sink sink_name=soundboard sink_properties=device.description=Soundboard
   ```
3. `uv run soundboard config set-device "Soundboard"` (the description string from step 2).
4. In Helvum, drag a cable from your real mic's capture node to **soundboard**'s playback node, so your mic also feeds the null sink.
5. In Teams (the web client or the `teams-for-linux` wrapper), select **Monitor of Soundboard** as the microphone.

To make the null sink persistent, put the `pactl load-module` line in `~/.config/pipewire/pipewire.conf.d/soundboard.conf` using the `context.modules` syntax.

### macOS — BlackHole + LadioCast

1. Install [BlackHole 2ch](https://existential.audio/blackhole/) (free virtual audio driver) and [LadioCast](https://apps.apple.com/app/ladiocast/id411213048) from the App Store (free mixer).
2. `uv run soundboard config set-device "BlackHole 2ch"`.
3. In LadioCast: route **Input 1** = your real mic, **Input 2** = BlackHole 2ch; send both to **Main**; set **Main Output** = BlackHole 2ch.
4. In Teams, set the microphone to **BlackHole 2ch**.
5. Optional: set **Aux 1 Output** in LadioCast = your headphones so you can monitor what's being sent.

For a more polished paid option, [Loopback](https://rogueamoeba.com/loopback/) from Rogue Amoeba is the macOS equivalent of VoiceMeeter.

### Dual output (hear it locally + send to meeting)

The soundboard can drive two output devices in parallel — a **primary** (`output_device`) and a **monitor** (`monitor_device`) — so a single `play` reaches both endpoints. Useful when:

- You want a simple "headphones + USB speakers" setup with no virtual-mic stack.
- You're using the routing tools above but don't want to wire the soundboard back into your monitor bus there (e.g. skip routing the VAIO strip to A1 on VoiceMeeter).
- Driving two physical outputs simultaneously for a livestream/demo.

```bash
uv run soundboard config set-device "VoiceMeeter Input (VB-Audio Voicemeeter VAIO)"
uv run soundboard config set-monitor "Headphones (X)"
uv run soundboard config show
uv run soundboard config set-monitor --clear   # back to single-output
```

`soundboard devices` marks the primary with **P** and the monitor with **M**. Note: the two streams are not sample-synchronous (independent PortAudio streams), so don't expect studio-grade routing — fine for soundboard clips, not a substitute for a real audio router.

## Look and feel

Each sound carries an optional colour (named — `red`, `blue`, `green`, `yellow`, `orange`, `purple`, `pink`, `cyan`, `white`, `black` — or hex `#rrggbb`). When unset, the colour is derived deterministically from the sound's id so the soundboard isn't a wall of identical buttons. Colours apply across the CLI (swatch column in `list`), the TUI (tinted button background), and the desktop GUI, where they render as round arcade-style caps with a domed gradient and press feedback. Set or change a colour with `--color` on `add` / `edit` / `fetch`; remove it with `edit --clear-color`.

## Project layout

```
src/soundboard/
├── core/              ← Sound model + in-memory library
├── audio/             ← Player Protocol + sounddevice implementation + device enumeration
├── storage/           ← Library TOML repository
├── settings.py        ← Settings (output device) TOML repository
├── config.py          ← platformdirs paths
├── cli/               ← Typer entry point (soundboard)
├── tui/               ← Textual entry point (soundboard-tui)
└── gui/               ← PySide6 entry point (soundboard-gui)
tests/                 ← pytest, pytest-qt, Textual Pilot
```

## Development

```bash
uv run pytest
uv run ruff check
```
