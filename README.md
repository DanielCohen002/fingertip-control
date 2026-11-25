# Fingertip Control

<p align="center"><img src="assets/logo.png" width="128" alt="Fingertip Control logo"></p>

A small app for Linux Mint (Cinnamon) and Windows that remaps F-keys and mouse buttons to simple actions. No profiles or macros, just pick an action from a dropdown.

- Defaults: F5 Play/Pause, F6 Mute mic, F7 Volume down, F8 Volume up
- Each of the four keys can be changed to any of F1-F12 and any action from a dropdown
- Mouse buttons (middle, back, forward) can be remapped the same way, or disabled
- Closing the window hides it to the system tray and the remaps keep running. Click the tray icon to reopen it, right-click for Quit. Launching the app again just brings the window back
- **Update** button: on Windows it downloads the newest release and restarts itself; on Linux it pulls the latest version from GitHub (git clone installs)
- Actions: play/pause, next, previous, stop, mute speakers, volume up/down, mute mic, mic volume up/down, copy, paste, undo, browser back/forward, middle click, double click, disable button
- Shortcuts are written as Cinnamon custom keybindings; other custom shortcuts are left alone

## Requirements

- Linux Mint Cinnamon
- `python3-gi` (GTK 3), `pactl` (PulseAudio/PipeWire), `playerctl`, and for the mouse buttons `xbindkeys` and `xdotool` (X11)

```
sudo apt install playerctl xbindkeys xdotool
```

Keyboard shortcuts are saved in Cinnamon and keep working with the app closed. Tick **Start at login** to restore your keyboard and mouse remaps automatically after each login.

## Run

```
./key-shortcuts
```

Settings are saved to `~/.config/key-shortcuts/config.json`.

## Windows version

`windows/fingertip_control_win.py` is the Windows port: same four keys and the same action dropdowns, using global hotkeys instead of Cinnamon keybindings.

- To run from source instead: Python 3 with `pip install pycaw comtypes pystray pillow`, then `python windows/fingertip_control_win.py`
- Closing the window minimizes it so the hotkeys keep working; use **Quit** to exit
- Mouse buttons are remapped with a low-level mouse hook; the original button press is blocked
- **Start with Windows** checkbox launches the whole app minimized at login (keyboard and mouse remaps)
- **Download:** get `FingertipControl.exe` from the [latest release](https://github.com/DanielCohen002/fingertip-control/releases/latest). It's a single file with everything built in, so there's nothing to install. Windows may show a SmartScreen warning because the app is unsigned (More info, then Run anyway)
- The exe is built by the **Build Windows exe** GitHub Action
- Untested on real Windows so far
