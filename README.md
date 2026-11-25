# Fingertip Control

<p align="center"><img src="assets/logo.png" width="128" alt="Fingertip Control logo"></p>

A small GTK app for Linux Mint (Cinnamon) that maps keyboard keys to media and volume actions.

- Defaults: F5 Play/Pause, F6 Mute mic, F7 Volume down, F8 Volume up
- Each of the four keys can be changed to any of F1-F12 and any action from a dropdown
- Actions: play/pause, next, previous, stop, mute speakers, volume up/down, mute mic, mic volume up/down
- Shortcuts are written as Cinnamon custom keybindings; other custom shortcuts are left alone

## Requirements

- Linux Mint Cinnamon
- `python3-gi` (GTK 3), `pactl` (PulseAudio/PipeWire), `playerctl`

```
sudo apt install playerctl
```

## Run

```
./key-shortcuts
```

Settings are saved to `~/.config/key-shortcuts/config.json`.

## Windows version

`windows/fingertip_control_win.py` is the Windows port: same four keys and the same action dropdowns, using global hotkeys instead of Cinnamon keybindings.

- Needs Python 3 with `pip install pycaw comtypes` (pycaw is only used for the mic actions)
- Run: `python windows/fingertip_control_win.py`
- Closing the window minimizes it so the hotkeys keep working; use **Quit** to exit
- Optional **Start with Windows** checkbox
- To build `FingertipControl.exe`, move `windows/build-windows.yml` to `.github/workflows/` (pushing workflow files needs the GitHub `workflow` permission), then run it from the Actions tab and download the artifact
- Untested on real Windows so far
