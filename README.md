# mashboard

Cross-interface soundboard — CLI, TUI, desktop GUI — over a shared audio core. Audio playback via `sounddevice` (PortAudio) with optional dual-output, library stored as TOML, cross-platform.

## Install

```bash
# from a locally built wheel:
uv tool install --from dist/mashboard-0.1.0-py3-none-any.whl mashboard
```

`pipx install mashboard` will work once the package is published to PyPI. `mashboard fetch` (YouTube clip grabber) needs `ffmpeg` on PATH.

## Quickstart

```bash
mashboard add path/to/clip.wav --name horn
mashboard list
mashboard play horn
mashboard-tui                       # Textual TUI
mashboard-gui                       # PySide6 desktop GUI
```

## Develop from source

```bash
uv sync
uv run mashboard --help
uv run mashboard-tui
uv run mashboard-gui
uv run pytest
uv run ruff check
```

> **Migrating from `soundboard` (the previous name):** copy `%APPDATA%\soundboard\library.toml` and `settings.toml` to `%APPDATA%\mashboard\` (Windows) or the equivalent `~/.config/soundboard/` → `~/.config/mashboard/` (Linux) so your existing library carries over.

## CLI cheatsheet

```bash
mashboard add path/to/clip.wav --name horn --hotkey ctrl+h --tag funny --color red
mashboard edit horn --volume 0.5 --add-tag loud --clear-hotkey --color "#22aa55"
mashboard edit horn --clear-color
mashboard list
mashboard play horn
mashboard stop
mashboard remove horn
mashboard where          # config/data paths
mashboard devices        # audio output devices (P = primary, M = monitor)
mashboard config show
mashboard config set-device "VoiceMeeter Input (VB-Audio Voicemeeter VAIO)"
mashboard config set-device --clear     # back to system default
mashboard config set-monitor "Headphones (X)"   # mirror to a 2nd device
mashboard config set-monitor --clear     # disable monitor output
```

## Grabbing clips from YouTube

Requires `ffmpeg` on PATH (yt-dlp uses it for the time-range extraction and mp3 conversion).

```bash
mashboard fetch "https://youtu.be/XYZ" --start 1:23 --end 1:30 --name horn --tag funny
```

Timecodes accept `SS`, `MM:SS`, or `H:MM:SS` (fractional seconds OK). Omit `--start`/`--end` to pull the full audio. Personal use only — respect the source's licensing.

## Routing into a virtual meeting (Teams, Zoom, Meet…)

Meeting apps accept a single "microphone" input, so to have them hear both your voice and the soundboard you need an external routing tool that mixes them and exposes the result as a virtual mic. Once that tool is running, point mashboard at its **virtual input** with `mashboard config set-device "<name>"` so non-mashboard audio (music, system sounds) does not leak into the call.

### Windows — plain VoiceMeeter (free) or Banana

1. Install [VoiceMeeter](https://vb-audio.com/Voicemeeter/) (plain or Banana). Reboot if prompted.
2. Windows sound settings: keep your regular speakers/headset as **default playback**; set your real mic as **default recording**.
3. Point mashboard at VoiceMeeter's virtual input. Run `mashboard devices`, find the entry for the main VAIO virtual input, and feed it back:
   ```
   mashboard config set-device "<paste the entry from the list>"
   ```
   Depending on your VB-Audio driver version that entry is one of:
   `Voicemeeter Input (VB-Audio Voicemeeter VAIO)` · `Voicemeeter In B1 (…)` · `Voicemeeter In 1 (…)`. They all land on the main VAIO strip. Ignore `In 2/3/4/5` (ASIO multichannel taps) and `AUX VAIO` (that's the second virtual input, only present in Banana).
4. Open VoiceMeeter. Route **Hardware Input 1** (your mic) and the **Voicemeeter VAIO** strip (mashboard) to both **A1** (your speakers/headphones, so you hear yourself + sounds) and **B1** (the virtual output Teams will read).
5. In Teams/Zoom/Meet, set the **Microphone** to the B1 virtual output. Depending on driver version this shows as one of: `Voicemeeter Output (VB-Audio Voicemeeter VAIO)` · `Voicemeeter Out B1 (…)` · `Voicemeeter Out 1 (…)`. Pick whichever you see. Avoid `Out 2` (that's B2, for a preview/monitor bus in Banana), and `Out 3/4/5` (multichannel taps).
6. Test: `mashboard play <name>` — the Teams mic meter should react. To confirm it's B1: Teams → Settings → Devices → **Make a test call**; the bot will echo back whatever reaches your virtual mic.

Upgrade to Banana if you want per-strip gate/compressor/EQ on your mic, or use its B2 bus (Voicemeeter Aux Output / Out B2 / Out 2) for a headphone-only preview channel.

### Linux — PipeWire + Helvum

1. Install Helvum (`sudo apt install helvum`, `dnf install helvum`, etc.) — it's a visual PipeWire patch-bay. Alternative: `qpwgraph`.
2. Create a null sink that will act as the "virtual mic":
   ```bash
   pactl load-module module-null-sink sink_name=mashboard sink_properties=device.description=Mashboard
   ```
3. `mashboard config set-device "Mashboard"` (the description string from step 2).
4. In Helvum, drag a cable from your real mic's capture node to **mashboard**'s playback node, so your mic also feeds the null sink.
5. In Teams (the web client or the `teams-for-linux` wrapper), select **Monitor of Mashboard** as the microphone.

To make the null sink persistent, put the `pactl load-module` line in `~/.config/pipewire/pipewire.conf.d/mashboard.conf` using the `context.modules` syntax.

### macOS — BlackHole + LadioCast

1. Install [BlackHole 2ch](https://existential.audio/blackhole/) (free virtual audio driver) and [LadioCast](https://apps.apple.com/app/ladiocast/id411213048) from the App Store (free mixer).
2. `mashboard config set-device "BlackHole 2ch"`.
3. In LadioCast: route **Input 1** = your real mic, **Input 2** = BlackHole 2ch; send both to **Main**; set **Main Output** = BlackHole 2ch.
4. In Teams, set the microphone to **BlackHole 2ch**.
5. Optional: set **Aux 1 Output** in LadioCast = your headphones so you can monitor what's being sent.

For a more polished paid option, [Loopback](https://rogueamoeba.com/loopback/) from Rogue Amoeba is the macOS equivalent of VoiceMeeter.

### Dual output (hear it locally + send to meeting)

mashboard can drive two output devices in parallel — a **primary** (`output_device`) and a **monitor** (`monitor_device`) — so a single `play` reaches both endpoints. Useful when:

- You want a simple "headphones + USB speakers" setup with no virtual-mic stack.
- You're using the routing tools above but don't want to wire mashboard back into your monitor bus there (e.g. skip routing the VAIO strip to A1 on VoiceMeeter).
- Driving two physical outputs simultaneously for a livestream/demo.

```bash
mashboard config set-device "VoiceMeeter Input (VB-Audio Voicemeeter VAIO)"
mashboard config set-monitor "Headphones (X)"
mashboard config show
mashboard config set-monitor --clear   # back to single-output
```

`mashboard devices` marks the primary with **P** and the monitor with **M**. Note: the two streams are not sample-synchronous (independent PortAudio streams), so don't expect studio-grade routing — fine for soundboard clips, not a substitute for a real audio router.

## Look and feel

Each sound carries an optional colour (named — `red`, `blue`, `green`, `yellow`, `orange`, `purple`, `pink`, `cyan`, `white`, `black` — or hex `#rrggbb`). When unset, the colour is derived deterministically from the sound's id so the soundboard isn't a wall of identical buttons. Colours apply across the CLI (swatch column in `list`), the TUI (tinted button background), and the desktop GUI, where they render as round arcade-style caps with a domed gradient and press feedback. Set or change a colour with `--color` on `add` / `edit` / `fetch`; remove it with `edit --clear-color`.

## Project layout

```
src/mashboard/
├── core/              ← Sound model + in-memory library
├── audio/             ← Player Protocol + sounddevice implementation + device enumeration
├── storage/           ← Library TOML repository
├── settings.py        ← Settings (output device) TOML repository
├── config.py          ← platformdirs paths
├── cli/               ← Typer entry point (mashboard)
├── tui/               ← Textual entry point (mashboard-tui)
└── gui/               ← PySide6 entry point (mashboard-gui)
tests/                 ← pytest, pytest-qt, Textual Pilot
```

## License

Apache-2.0 — see [LICENSE](LICENSE).
