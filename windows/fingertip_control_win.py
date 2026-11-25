"""Fingertip Control (Windows): map F-keys to media and volume actions."""
import ctypes
import json
import os
import sys
import threading
import tkinter as tk
from ctypes import wintypes
from tkinter import ttk

user32 = ctypes.windll.user32
user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]

APP = "FingertipControl"
CONFIG = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), APP, "config.json")
WM_HOTKEY, WM_APP, WM_QUIT = 0x0312, 0x8000, 0x0012
KEYUP = 0x0002

# Media keys are sent as virtual key presses. Mic actions use the Core Audio API (pycaw).
VK = {
    "Play / Pause": 0xB3, "Next track": 0xB0, "Previous track": 0xB1, "Stop": 0xB2,
    "Mute / unmute speakers": 0xAD, "Volume down": 0xAE, "Volume up": 0xAF,
}
MIC = ["Mute / unmute mic", "Mic volume up", "Mic volume down"]
ACTIONS = ["None (disabled)"] + list(VK) + MIC
KEYS = {f"F{i}": 0x6F + i for i in range(1, 13)}
DEFAULTS = [
    {"key": "F5", "action": "Play / Pause"},
    {"key": "F6", "action": "Mute / unmute mic"},
    {"key": "F7", "action": "Volume down"},
    {"key": "F8", "action": "Volume up"},
]


def load():
    try:
        with open(CONFIG) as f:
            data = json.load(f)
        if len(data) == 4:
            return data
    except (OSError, ValueError):
        pass
    return [dict(d) for d in DEFAULTS]


def save(rows):
    os.makedirs(os.path.dirname(CONFIG), exist_ok=True)
    with open(CONFIG, "w") as f:
        json.dump(rows, f, indent=2)


def press(vk):
    user32.keybd_event(vk, 0, 0, 0)
    user32.keybd_event(vk, 0, KEYUP, 0)


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
        return
    vol = mic_volume()
    if action == "Mute / unmute mic":
        vol.SetMute(not vol.GetMute(), None)
    else:
        step = 0.05 if action == "Mic volume up" else -0.05
        level = min(1.0, max(0.0, vol.GetMasterVolumeLevelScalar() + step))
        vol.SetMasterVolumeLevelScalar(level, None)


class HotkeyThread(threading.Thread):
    """Owns the global hotkeys. Windows delivers WM_HOTKEY to the thread that registered them."""

    def __init__(self):
        super().__init__(daemon=True)
        self.rows = []
        self.result = ""
        self.ready = threading.Event()
        self.tid = None

    def run(self):
        self.tid = ctypes.windll.kernel32.GetCurrentThreadId()
        try:
            import comtypes
            comtypes.CoInitialize()
        except ImportError:
            pass
        msg = wintypes.MSG()
        user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 0)  # create the message queue
        self.ready.set()
        active = {}
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            if msg.message == WM_APP:
                for hid in active:
                    user32.UnregisterHotKey(None, hid)
                active, failed = {}, []
                for i, row in enumerate(self.rows):
                    if row["action"] == ACTIONS[0]:
                        continue
                    if user32.RegisterHotKey(None, i + 1, 0, KEYS[row["key"]]):
                        active[i + 1] = row["action"]
                    else:
                        failed.append(row["key"])
                self.result = ("In use by another program: " + ", ".join(failed)) if failed else "Applied."
            elif msg.message == WM_HOTKEY:
                try:
                    do_action(active[msg.wParam])
                except Exception as e:  # noqa: BLE001
                    self.result = f"Action failed: {e}"

    def set_rows(self, rows):
        self.ready.wait()
        self.rows = rows
        user32.PostThreadMessageW(self.tid, WM_APP, 0, 0)


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


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Fingertip Control")
        self.resizable(False, False)
        base = getattr(sys, "_MEIPASS", os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
        try:
            self._icon = tk.PhotoImage(file=os.path.join(base, "assets", "logo.png"))
            self.iconphoto(True, self._icon)
        except tk.TclError:
            pass
        self.hk = HotkeyThread()
        self.hk.start()
        frm = ttk.Frame(self, padding=14)
        frm.grid()
        ttk.Label(frm, text="Key").grid(row=0, column=0, sticky="w")
        ttk.Label(frm, text="Action").grid(row=0, column=1, sticky="w", padx=12)
        self.rows = []
        for i, row in enumerate(load()):
            key = ttk.Combobox(frm, values=list(KEYS), state="readonly", width=6)
            key.set(row["key"] if row["key"] in KEYS else "F5")
            act = ttk.Combobox(frm, values=ACTIONS, state="readonly", width=26)
            act.set(row["action"] if row["action"] in ACTIONS else ACTIONS[0])
            key.grid(row=i + 1, column=0, pady=5)
            act.grid(row=i + 1, column=1, pady=5, padx=12)
            self.rows.append((key, act))
        bar = ttk.Frame(frm)
        bar.grid(row=5, column=0, columnspan=2, pady=(10, 0), sticky="w")
        ttk.Button(bar, text="Apply", command=self.apply).pack(side="left")
        ttk.Button(bar, text="Reset to defaults", command=self.reset).pack(side="left", padx=8)
        ttk.Button(bar, text="Quit", command=self.quit_app).pack(side="left")
        self.auto = tk.BooleanVar(value=autostart_enabled())
        ttk.Checkbutton(frm, text="Start with Windows", variable=self.auto,
                        command=lambda: set_autostart(self.auto.get())).grid(row=6, column=0, columnspan=2, sticky="w", pady=(8, 0))
        self.status = tk.StringVar()
        ttk.Label(frm, textvariable=self.status).grid(row=7, column=0, columnspan=2, sticky="w", pady=(6, 0))
        self.protocol("WM_DELETE_WINDOW", self.iconify)  # keep running so hotkeys keep working
        self.apply()
        if "--minimized" in sys.argv:
            self.iconify()

    def current(self):
        return [{"key": k.get(), "action": a.get()} for k, a in self.rows]

    def apply(self):
        rows = self.current()
        keys = [r["key"] for r in rows if r["action"] != ACTIONS[0]]
        if len(keys) != len(set(keys)):
            self.status.set("Each key can only be used once.")
            return
        save(rows)
        self.hk.set_rows(rows)
        self.after(300, lambda: self.status.set(self.hk.result))

    def reset(self):
        for (k, a), d in zip(self.rows, DEFAULTS):
            k.set(d["key"])
            a.set(d["action"])

    def quit_app(self):
        if self.hk.tid:
            user32.PostThreadMessageW(self.hk.tid, WM_QUIT, 0, 0)
        self.destroy()


if __name__ == "__main__":
    App().mainloop()
