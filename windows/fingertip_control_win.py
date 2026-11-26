"""Fingertip Control (Windows): remap F-keys and mouse buttons to simple actions."""
import ctypes
import json
import os
import queue
import subprocess
import sys
import threading
import urllib.request
import tkinter as tk
from ctypes import wintypes
from tkinter import ttk

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
LRESULT = ctypes.c_ssize_t
HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD]
user32.SetWindowsHookExW.restype = ctypes.c_void_p
user32.CallNextHookEx.argtypes = [ctypes.c_void_p, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
user32.CallNextHookEx.restype = LRESULT
kernel32.GetModuleHandleW.restype = wintypes.HMODULE

APP = "FingertipControl"
VERSION = "1.4.1"
REPO = "DanielCohen002/fingertip-control"
CONFIG = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), APP, "config.json")
WM_HOTKEY, WM_APP, WM_QUIT = 0x0312, 0x8000, 0x0012
WM_RUN = WM_APP + 1  # run an action requested by the mouse hook
WH_MOUSE_LL = 14
WM_MBUTTONDOWN, WM_MBUTTONUP, WM_XBUTTONDOWN, WM_XBUTTONUP = 0x0207, 0x0208, 0x020B, 0x020C
LLMHF_INJECTED = 0x01
KEYUP = 0x0002

NONE = "None (leave as is)"
# Media keys are sent as virtual key presses. Mic actions use the Core Audio API (pycaw).
VK = {
    "Play / Pause": 0xB3, "Next track": 0xB0, "Previous track": 0xB1, "Stop": 0xB2,
    "Mute / unmute speakers": 0xAD, "Volume down": 0xAE, "Volume up": 0xAF,
    "Browser back": 0xA6, "Browser forward": 0xA7,
}
COMBO = {"Copy": (0x11, 0x43), "Paste": (0x11, 0x56), "Undo": (0x11, 0x5A),
         "Clipboard history": (0x5B, 0x56)}  # Ctrl+C / Ctrl+V / Ctrl+Z / Win+V
MIC = ["Mute / unmute mic", "Mic volume up", "Mic volume down"]
CLICKS = ["Middle click", "Double click"]
DISABLE = "Disable this button"
CUSTOM = "Custom key combo"
ACTIONS = [NONE] + list(VK) + MIC + list(COMBO) + CLICKS + [CUSTOM, DISABLE]
MODS = {"ctrl": 0x11, "control": 0x11, "alt": 0x12, "shift": 0x10, "win": 0x5B, "windows": 0x5B, "super": 0x5B}
NAMED = {"enter": 0x0D, "return": 0x0D, "esc": 0x1B, "escape": 0x1B, "tab": 0x09, "space": 0x20, "delete": 0x2E,
         "del": 0x2E, "backspace": 0x08, "home": 0x24, "end": 0x23, "pageup": 0x21, "pagedown": 0x22, "insert": 0x2D,
         "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28}
HELP = ("Custom key combo: type keys joined with +, like ctrl+shift+t or alt+left.\n"
        "Modifiers: ctrl, alt, shift, win.  Keys: a-z, 0-9, f1-f12, enter, esc, tab, space, delete,\n"
        "backspace, home, end, pageup, pagedown, left, right, up, down.")


def parse_combo(text):
    """'ctrl+shift+t' -> list of virtual key codes (modifiers first). Raises ValueError if unclear."""
    parts = [p for p in text.lower().replace(" ", "").split("+") if p]
    if not parts:
        raise ValueError("type a combo like ctrl+shift+t")
    codes = []
    for p in parts:
        if p in MODS:
            codes.append(MODS[p])
        elif p in NAMED:
            codes.append(NAMED[p])
        elif len(p) in (2, 3) and p[0] == "f" and p[1:].isdigit() and 1 <= int(p[1:]) <= 12:
            codes.append(0x6F + int(p[1:]))
        elif len(p) == 1 and p.isalnum() and p.isascii():
            codes.append(ord(p.upper()))
        else:
            raise ValueError(f"unknown key '{p}'")
    if all(c in MODS.values() for c in codes):
        raise ValueError("add a normal key, like ctrl+c")
    return sorted(codes, key=lambda c: c not in MODS.values())

KEYS = {f"F{i}": 0x6F + i for i in range(1, 13)}
KEYS.update({"PageUp": 0x21, "PageDown": 0x22, "LeftAlt": 0xA4, "RightAlt": 0xA5})
MOUSE = {"Middle button": "middle", "Back button": 1, "Forward button": 2}  # X1 = back, X2 = forward
DEFAULTS = {
    "keys": [
        {"key": "F5", "action": "Play / Pause"},
        {"key": "F6", "action": "Mute / unmute mic"},
        {"key": "F7", "action": "Volume down"},
        {"key": "F8", "action": "Volume up"},
    ],
    "mouse": {name: NONE for name in MOUSE},
    "autostart": False,
}


def load():
    cfg = json.loads(json.dumps(DEFAULTS))
    try:
        with open(CONFIG) as f:
            data = json.load(f)
        if isinstance(data, list) and len(data) == 4:  # config from the first version
            cfg["keys"] = data
        elif isinstance(data, dict):
            if len(data.get("keys", [])) == 4:
                cfg["keys"] = data["keys"]
            cfg["mouse"].update({k: v for k, v in data.get("mouse", {}).items() if k in MOUSE})
    except (OSError, ValueError):
        pass
    return cfg


def save(cfg):
    os.makedirs(os.path.dirname(CONFIG), exist_ok=True)
    with open(CONFIG, "w") as f:
        json.dump(cfg, f, indent=2)


def press(*vks):
    for vk in vks:
        user32.keybd_event(vk, 0, 0, 0)
    for vk in reversed(vks):
        user32.keybd_event(vk, 0, KEYUP, 0)


def click(down, up, times=1):
    for _ in range(times):
        user32.mouse_event(down, 0, 0, 0, 0)
        user32.mouse_event(up, 0, 0, 0, 0)


def mic_volume():
    from comtypes import CLSCTX_ALL
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
    dev = AudioUtilities.GetMicrophone()
    if hasattr(dev, "EndpointVolume"):  # newer pycaw
        return dev.EndpointVolume
    iface = dev.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
    return ctypes.cast(iface, ctypes.POINTER(IAudioEndpointVolume))


def do_action(action):
    if action in VK:
        press(VK[action])
    elif action in COMBO:
        press(*COMBO[action])
    elif action.startswith("Custom:"):
        press(*parse_combo(action[7:]))
    elif action == "Middle click":
        click(0x20, 0x40)
    elif action == "Double click":
        click(0x02, 0x04, 2)
    elif action in MIC:
        vol = mic_volume()
        if action == "Mute / unmute mic":
            vol.SetMute(not vol.GetMute(), None)
        else:
            step = 0.05 if action == "Mic volume up" else -0.05
            level = min(1.0, max(0.0, vol.GetMasterVolumeLevelScalar() + step))
            vol.SetMasterVolumeLevelScalar(level, None)


class MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [("pt", wintypes.POINT), ("mouseData", wintypes.DWORD), ("flags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class InputThread(threading.Thread):
    """Owns the global hotkeys and the mouse hook (both need a message loop on one thread)."""

    def __init__(self):
        super().__init__(daemon=True)
        self.cfg = load()
        self.result = ""
        self.ready = threading.Event()
        self.tid = None
        self.pending = []
        self.mouse_map = {}  # "middle" / 1 / 2 -> action
        self._proc = HOOKPROC(self._mouse_proc)  # keep a reference so it isn't garbage collected

    def _mouse_proc(self, code, wparam, lparam):
        if code >= 0 and wparam in (WM_MBUTTONDOWN, WM_MBUTTONUP, WM_XBUTTONDOWN, WM_XBUTTONUP):
            info = ctypes.cast(lparam, ctypes.POINTER(MSLLHOOKSTRUCT)).contents
            if not info.flags & LLMHF_INJECTED:  # ignore clicks we send ourselves
                if wparam in (WM_MBUTTONDOWN, WM_MBUTTONUP):
                    button = "middle"
                else:
                    button = (info.mouseData >> 16) & 0xFFFF
                action = self.mouse_map.get(button)
                if action:
                    if wparam in (WM_MBUTTONDOWN, WM_XBUTTONDOWN) and action != DISABLE:
                        self.pending.append(action)
                        user32.PostThreadMessageW(self.tid, WM_RUN, 0, 0)
                    return 1  # swallow the original button press and release
        return user32.CallNextHookEx(None, code, wparam, lparam)

    def run(self):
        self.tid = kernel32.GetCurrentThreadId()
        try:
            import comtypes
            comtypes.CoInitialize()
        except ImportError:
            pass
        msg = wintypes.MSG()
        user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 0)  # create the message queue
        hook = user32.SetWindowsHookExW(WH_MOUSE_LL, self._proc, kernel32.GetModuleHandleW(None), 0)
        self.ready.set()
        active = {}
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            if msg.message == WM_APP:
                for hid in active:
                    user32.UnregisterHotKey(None, hid)
                active, failed = {}, []
                for i, row in enumerate(self.cfg["keys"]):
                    if row["action"] == NONE:
                        continue
                    if user32.RegisterHotKey(None, i + 1, 0, KEYS[row["key"]]):
                        active[i + 1] = row["action"]
                    else:
                        failed.append(row["key"])
                self.mouse_map = {MOUSE[n]: a for n, a in self.cfg["mouse"].items() if a != NONE}
                self.result = ("In use by another program: " + ", ".join(failed)) if failed else "Applied."
                if not hook and self.mouse_map:
                    self.result = "Could not hook the mouse."
            elif msg.message in (WM_HOTKEY, WM_RUN):
                action = active.get(msg.wParam) if msg.message == WM_HOTKEY else (self.pending.pop(0) if self.pending else None)
                try:
                    if action:
                        do_action(action)
                except Exception as e:  # noqa: BLE001
                    self.result = f"Action failed: {e}"
        if hook:
            user32.UnhookWindowsHookEx(hook)

    def set_cfg(self, cfg):
        self.ready.wait()
        self.cfg = cfg
        user32.PostThreadMessageW(self.tid, WM_APP, 0, 0)


def _version(tag):
    return tuple(int(x) for x in tag.lstrip("v").split(".") if x.isdigit())


def check_update():
    """Return (tag, download_url) if a newer release exists, else None."""
    req = urllib.request.Request(f"https://api.github.com/repos/{REPO}/releases/latest",
                                 headers={"User-Agent": "FingertipControl"})
    with urllib.request.urlopen(req, timeout=10) as r:
        data = json.load(r)
    if _version(data["tag_name"]) <= _version(VERSION):
        return None
    for a in data.get("assets", []):
        if a["name"] == "FingertipControl.exe":
            return data["tag_name"], a["browser_download_url"]
    return None


def install_update(url):
    """Download the new exe, swap it in (a running exe can be renamed but not overwritten) and relaunch."""
    exe = sys.executable
    new, old = exe + ".new", exe + ".old"
    urllib.request.urlretrieve(url, new)
    if os.path.exists(old):
        os.remove(old)
    os.replace(exe, old)
    os.replace(new, exe)
    subprocess.Popen([exe, "--after-update"], env={**os.environ, "PYINSTALLER_RESET_ENVIRONMENT": "1"})


def set_autostart(on):
    import winreg
    exe = f'"{sys.executable}"' if getattr(sys, "frozen", False) else f'"{sys.executable}" "{os.path.abspath(__file__)}"'
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_SET_VALUE) as k:
        if on:
            winreg.SetValueEx(k, APP, 0, winreg.REG_SZ, exe + " --minimized")
        else:
            try:
                winreg.DeleteValue(k, APP)
            except FileNotFoundError:
                pass


def autostart_enabled():
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run") as k:
            winreg.QueryValueEx(k, APP)
            return True
    except OSError:
        return False


def single_instance():
    """Return False if another copy is already running (and bring its window forward)."""
    wait = 5 if "--after-update" in sys.argv else 0  # the old copy is still shutting down
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    for _ in range(wait * 10 + 1):
        k32.CreateMutexW(None, False, "Local\\FingertipControlSingleInstance")
        if ctypes.get_last_error() != 183:  # ERROR_ALREADY_EXISTS
            return True
        if wait:
            import time
            time.sleep(0.1)
    hwnd = user32.FindWindowW(None, "Fingertip Control")
    if hwnd:
        user32.ShowWindow(hwnd, 5)
        user32.SetForegroundWindow(hwnd)
    return False


class ActionPicker(ttk.Frame):
    """Action dropdown plus a text box that is used when 'Custom key combo' is chosen."""

    def __init__(self, parent, value):
        super().__init__(parent)
        self.combo = ttk.Combobox(self, values=ACTIONS, state="readonly", width=22)
        self.entry = ttk.Entry(self, width=18)
        self.combo.pack(side="left")
        self.entry.pack(side="left", padx=(6, 0))
        self.combo.bind("<<ComboboxSelected>>", lambda e: self._sync())
        self.set(value)

    def _sync(self):
        self.entry.configure(state="normal" if self.combo.get() == CUSTOM else "disabled")

    def get(self):
        if self.combo.get() == CUSTOM:
            return "Custom: " + self.entry.get().strip()
        return self.combo.get()

    def set(self, value):
        self.entry.configure(state="normal")
        self.entry.delete(0, "end")
        if value.startswith("Custom:"):
            self.combo.set(CUSTOM)
            self.entry.insert(0, value[7:].strip())
        else:
            self.combo.set(value if value in ACTIONS else NONE)
        self._sync()


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        if getattr(sys, "frozen", False):  # clean up after a previous update
            try:
                os.remove(sys.executable + ".old")
            except OSError:
                pass
        self.title("Fingertip Control")
        self.resizable(False, False)
        base = getattr(sys, "_MEIPASS", os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
        try:
            self._icon = tk.PhotoImage(file=os.path.join(base, "assets", "logo.png"))
            self.iconphoto(True, self._icon)
        except tk.TclError:
            pass
        self.hk = InputThread()
        self.hk.start()
        cfg = load()
        frm = ttk.Frame(self, padding=14)
        frm.grid()
        ttk.Label(frm, text="Keyboard", font=("Segoe UI", 9, "bold")).grid(row=0, column=0, columnspan=2, sticky="w")
        self.key_rows = []
        for i, row in enumerate(cfg["keys"]):
            key = ttk.Combobox(frm, values=list(KEYS), state="readonly", width=16)
            key.set(row["key"] if row["key"] in KEYS else "F5")
            act = ActionPicker(frm, row["action"])
            key.grid(row=i + 1, column=0, pady=4, sticky="w")
            act.grid(row=i + 1, column=1, pady=4, padx=12)
            self.key_rows.append((key, act))
        ttk.Label(frm, text="Mouse buttons", font=("Segoe UI", 9, "bold")).grid(row=6, column=0, columnspan=2, sticky="w", pady=(10, 0))
        self.mouse_rows = {}
        for i, name in enumerate(MOUSE):
            ttk.Label(frm, text=name).grid(row=7 + i, column=0, sticky="w")
            act = ActionPicker(frm, cfg["mouse"][name])
            act.grid(row=7 + i, column=1, pady=4, padx=12)
            self.mouse_rows[name] = act
        ttk.Label(frm, text=HELP, foreground="#555", justify="left").grid(row=10, column=0, columnspan=2, sticky="w", pady=(8, 0))
        self.auto = tk.BooleanVar(value=autostart_enabled())
        ttk.Checkbutton(frm, text="Start with Windows", variable=self.auto,
                        command=lambda: set_autostart(self.auto.get())).grid(row=11, column=0, columnspan=2, sticky="w", pady=(8, 0))
        bar = ttk.Frame(frm)
        bar.grid(row=12, column=0, columnspan=2, pady=(10, 0), sticky="w")
        ttk.Button(bar, text="Apply", command=self.apply).pack(side="left")
        ttk.Button(bar, text="Reset to defaults", command=self.reset).pack(side="left", padx=8)
        ttk.Button(bar, text="Update", command=self.update).pack(side="left", padx=(0, 8))
        ttk.Button(bar, text="Quit", command=self.quit_app).pack(side="left")
        self.status = tk.StringVar()
        ttk.Label(frm, textvariable=self.status).grid(row=13, column=0, columnspan=2, sticky="w", pady=(6, 0))
        self.protocol("WM_DELETE_WINDOW", self.withdraw)  # hide to the tray; remaps keep working
        self.tray_events = queue.Queue()
        self.start_tray(base)
        self.after(150, self.poll_tray)
        self.apply()
        if "--minimized" in sys.argv:
            self.withdraw()

    def start_tray(self, base):
        try:
            import pystray
            from PIL import Image
            menu = pystray.Menu(
                pystray.MenuItem("Show Fingertip Control", lambda: self.tray_events.put("show"), default=True),
                pystray.MenuItem("Quit", lambda: self.tray_events.put("quit")),
            )
            self.tray = pystray.Icon(APP, Image.open(os.path.join(base, "assets", "logo.png")), "Fingertip Control", menu)
            self.tray.run_detached()
        except Exception:  # noqa: BLE001  (no tray available: closing just minimizes)
            self.tray = None
            self.protocol("WM_DELETE_WINDOW", self.iconify)

    def poll_tray(self):
        try:
            while True:
                event = self.tray_events.get_nowait()
                if event == "show":
                    self.deiconify()
                    self.lift()
                    self.focus_force()
                elif event == "quit":
                    self.quit_app()
                    return
        except queue.Empty:
            pass
        self.after(150, self.poll_tray)

    def current(self):
        return {
            "keys": [{"key": k.get(), "action": a.get()} for k, a in self.key_rows],
            "mouse": {n: a.get() for n, a in self.mouse_rows.items()},
            "autostart": self.auto.get(),
        }

    def apply(self):
        cfg = self.current()
        for what, action in [(r["key"], r["action"]) for r in cfg["keys"]] + list(cfg["mouse"].items()):
            if action.startswith("Custom:"):
                try:
                    parse_combo(action[7:])
                except ValueError as e:
                    self.status.set(f"{what}: {e}")
                    return
        keys = [r["key"] for r in cfg["keys"] if r["action"] != NONE]
        if len(keys) != len(set(keys)):
            self.status.set("Each key can only be used once.")
            return
        save(cfg)
        self.hk.set_cfg(cfg)
        self.after(300, lambda: self.status.set(self.hk.result))

    def update(self):
        self.status.set(f"Checking for updates (v{VERSION})...")

        def work():
            try:
                found = check_update()
                if not found:
                    msg = f"You're up to date (v{VERSION})."
                elif not getattr(sys, "frozen", False):
                    msg = f"{found[0]} is available. Download it from the GitHub releases page."
                else:
                    self.after(0, lambda: self.status.set(f"Downloading {found[0]}..."))
                    install_update(found[1])
                    self.after(0, self.quit_app)
                    return
            except Exception as e:  # noqa: BLE001
                msg = f"Update failed: {e}"
            self.after(0, lambda: self.status.set(msg))

        threading.Thread(target=work, daemon=True).start()

    def reset(self):
        for (k, a), d in zip(self.key_rows, DEFAULTS["keys"]):
            k.set(d["key"])
            a.set(d["action"])
        for a in self.mouse_rows.values():
            a.set(NONE)

    def quit_app(self):
        if getattr(self, "tray", None):
            self.tray.stop()
        if self.hk.tid:
            user32.PostThreadMessageW(self.hk.tid, WM_QUIT, 0, 0)
        self.destroy()


if __name__ == "__main__":
    if single_instance():
        App().mainloop()
