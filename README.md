# Fingertip Control

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
