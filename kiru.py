"""Kiru - desktop launcher.

  1. the Kiru window opens AT ONCE on a small loading page of its own (the turning ring); nothing is waited for;
  2. behind it the engine (the Flask app in app.py) is loaded and started on a background thread, on the first free
     port from 5000 (every window is its own Kiru with its own engine, temp folder and auto-save);
  3. the moment the engine listens, the window goes to it. The page it shows has the tab bar; every tab is a project.

Started while Kiru is already open? Then no window is made yet: the launcher asks the Kiru that is open to put the
question on its own screen ("Kiru is already open. Open a new window, a new tab, or switch to existing window?"),
waits for the click, and does that. The native system box is only the fallback when no Kiru window can answer.

Run it with:  python kiru.py      (Start_Tool.bat does this for you)
Without PyWebView installed it falls back to the browser, exactly like `python app.py`.

© 2026 Aden. All rights reserved.
"""
import json
import os
import subprocess
import sys
import threading
import time
import urllib.request

APP_NAME = "Kiru"

if sys.stdout is None or sys.stderr is None:           # started without a console (pythonw / the windowed .exe): give print() somewhere harmless to go
    _null = open(os.devnull, "w")
    sys.stdout = sys.stdout or _null
    sys.stderr = sys.stderr or _null

FROZEN = bool(getattr(sys, "frozen", False))
HERE = os.path.dirname(os.path.abspath(sys.executable if FROZEN else __file__))
# where the user's own things live (the same rule as app.py): next to the program on Windows and from source,
# the per-user data folder for a Mac .app or a Linux install
DATA = HERE
if FROZEN and os.name != "nt":
    DATA = os.path.join(os.path.expanduser("~/Library/Application Support") if sys.platform == "darwin"
                        else os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share"), APP_NAME)
    os.makedirs(DATA, exist_ok=True)

PORT = 5000                                            # the first window; a second one takes the next free port up to PORT_LAST
PORT_LAST = 5019
URL = f"http://127.0.0.1:{PORT}"
SECOND_ASK = "Kiru is already open. Open a new window, a new tab, or switch to existing window?"


def fatal(message):
    """A native error box (never a blank window), then stop."""
    try:
        if os.name == "nt":
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, str(message), APP_NAME, 0x10)       # MB_ICONERROR
        elif sys.platform == "darwin":
            import subprocess
            subprocess.run(["osascript", "-e", f'display alert "{APP_NAME}" message "{str(message).replace(chr(34), chr(39))}" as critical'], check=False)
        else:
            import shutil
            import subprocess
            tool = shutil.which("zenity") or shutil.which("kdialog")
            if tool:
                subprocess.run([tool, "--error", "--title", APP_NAME, "--text", str(message)] if "zenity" in tool else [tool, "--error", str(message), "--title", APP_NAME], check=False)
            print(f"[{APP_NAME}] {message}", file=sys.stderr)
    finally:
        os._exit(1)


def add_bundled_ffmpeg():
    """The installer ships ffmpeg.exe / ffprobe.exe in an 'ffmpeg' folder: put it first on PATH."""
    for d in (os.path.join(HERE, "ffmpeg"), os.path.join(HERE, "_internal", "ffmpeg"), os.path.join(getattr(sys, "_MEIPASS", HERE), "ffmpeg"),
              os.path.join(HERE, "..", "Resources", "ffmpeg"), "/opt/homebrew/bin", "/usr/local/bin"):      # (Mac: inside the .app, or Homebrew)
        if os.path.isdir(d):
            os.environ["PATH"] = d + os.pathsep + os.environ.get("PATH", "")
            return d
    return None


class WindowApi:
    """What the page's own title bar can ask of the window (Minimize / Maximize / Close, and resizing by the corner grip).
    The window is kept in a name starting with "_": the window library publishes every public attribute of this object to
    the page, and must never be handed the window itself to walk through."""

    def __init__(self):
        self._win = None
        self._maxed = False
        self._dirty = False                                                # the page tells us whenever there are unsaved changes
        self._closing = False

    def win_min(self):
        self._win.minimize()

    def win_max(self):
        if self._maxed:
            self._win.restore()
        else:
            self._win.maximize()
        self._maxed = not self._maxed
        return self._maxed

    def set_dirty(self, dirty):
        self._dirty = bool(dirty)

    def may_close(self):
        """Unsaved changes? Then a native box asks first. True = go ahead and close."""
        if self._closing or not self._dirty:
            return True
        if confirm_box("You have unsaved changes. Are you sure you want to close?"):
            self._closing = True
            return True
        return False

    def win_close(self):
        if self.may_close():
            self._closing = True
            self._win.destroy()
            return True
        return False

    def win_front(self):
        """Come to the front (Kiru was started again and this window has to ask what to do)."""
        try:
            if getattr(self, "_maxed", False):
                self._win.show()
            else:
                self._win.restore()
            self._win.on_top = True
            self._win.on_top = False
        except Exception:
            pass
        return True

    def win_resize(self, width, height):
        if not self._maxed:
            self._win.resize(max(900, int(width)), max(600, int(height)))


def http_json(url, timeout=1.0, post=False):
    """A tiny HTTP call to the engine (post: True, or the object to send). -> the JSON it answered, or None."""
    try:
        req = urllib.request.Request(url, data=(json.dumps(post).encode("utf-8") if isinstance(post, dict) else b"{}") if post else None, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8", "replace") or "{}")
    except Exception:
        return None


def port_busy(port):
    """Is something listening on this port? Asked by trying to take the port, which answers at once. (Knocking on a
    closed local port makes Windows wait; with twenty ports to look at, that alone was a start of ten seconds.)"""
    import socket
    sk = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sk.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE if os.name == "nt" else socket.SO_REUSEADDR, 1)
        sk.bind(("127.0.0.1", port))
        return False
    except OSError:
        pass
    finally:
        sk.close()
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as ck:      # the port could not be taken: is somebody really listening (or is it only just closed)?
        ck.settimeout(0.3)
        return ck.connect_ex(("127.0.0.1", port)) == 0


LOADING_HTML = """<!doctype html><html><head><meta charset="utf-8"><title>Kiru</title><style>
html,body{height:100%;margin:0}
body{display:flex;flex-direction:column;align-items:center;justify-content:center;gap:22px;color:#eef0f6;font:15px "Segoe UI",system-ui,sans-serif;user-select:none;cursor:default;
background:radial-gradient(90% 70% at 8% 0%,rgba(59,29,110,.45),transparent 62%),radial-gradient(90% 70% at 100% 100%,rgba(15,92,79,.42),transparent 62%),#0b0b14}
.w{position:relative;width:148px;height:148px;display:grid;place-items:center}
.r{position:absolute;inset:0;border-radius:50%;border:3px solid rgba(110,240,208,.14);border-top-color:#6ef0d0;border-right-color:rgba(110,240,208,.55);box-shadow:0 0 22px rgba(110,240,208,.28);animation:s 1s linear infinite}
@keyframes s{to{transform:rotate(360deg)}}
svg{width:84px;height:84px;filter:drop-shadow(0 10px 26px rgba(110,240,208,.4))}
h1{margin:0;font-size:30px;font-weight:650;letter-spacing:-.02em}p{margin:-10px 0 0;color:#aab0c2;font-size:14.5px;min-height:20px;max-width:560px;text-align:center;white-space:pre-wrap}
.d{position:fixed;left:0;right:0;top:0;height:40px}
</style></head><body><div class="d pywebview-drag-region"></div>
<div class="w"><div class="r"></div><svg viewBox="0 0 28 28"><defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#6ef0d0"/><stop offset="1" stop-color="#8f7bff"/></linearGradient></defs>
<rect x="1" y="1" width="26" height="26" rx="8" fill="url(#g)"/><path d="M9 7v14M19.5 7.5 11 14l8.5 6.5" stroke="#06140f" stroke-width="2.6" fill="none" stroke-linecap="round" stroke-linejoin="round"/></svg></div>
<h1>Kiru</h1><p id="m">Starting&hellip;</p></body></html>"""


def start_engine(kiru):
    """Flask on a background thread. The port is bound before this returns, so the window can be pointed at it at once.
    Nothing heavy starts here: the page asks for the background work when the editor is on screen (app.start_warmups),
    and a timer does it anyway after 20 seconds."""
    kiru.wipe_temp()
    kiru.wipe_stale_instances()
    kiru.make_temp()
    kiru.install_close_handlers()
    import logging
    logging.getLogger("werkzeug").setLevel(logging.WARNING)
    from werkzeug.serving import make_server
    server = make_server(kiru.HOST, kiru.PORT, kiru.app, threaded=True)          # (binds and listens right here)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    tm = threading.Timer(20.0, kiru.start_warmups)
    tm.daemon = True
    tm.start()
    return server


def window_size(webview):
    """1560 x 940, or smaller when the screen is (125% / 150% display scaling). The window library centres it by itself."""
    w, h = 1560, 940
    try:
        if os.name == "nt":
            import ctypes
            u32 = ctypes.windll.user32
            sw, sh = u32.GetSystemMetrics(0), u32.GetSystemMetrics(1)       # the main screen, in pixels...
            if u32.IsProcessDPIAware():                                    # ...which are real pixels only for a DPI-aware process
                scale = max(1.0, u32.GetDpiForSystem() / 96.0)
                sw, sh = int(sw / scale), int(sh / scale)
        else:
            sc = webview.screens[0]
            sw, sh = int(sc.width), int(sc.height)
        if sw >= 800 and sh >= 600:
            w, h = min(w, sw - 60), min(h, sh - 90)
    except Exception:
        pass
    return w, h


def kill_tree(pid):
    if not pid or int(pid) == os.getpid():
        return
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/f", "/t", "/pid", str(int(pid))], capture_output=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), timeout=10)
        else:
            import signal
            os.kill(int(pid), signal.SIGKILL)
    except Exception:
        pass


def process_name(pid):
    """Windows: the program file of a process, lower case ('kiru.exe'). '' when it cannot be told."""
    if os.name != "nt":
        return ""
    try:
        import ctypes
        from ctypes import wintypes
        k32 = ctypes.windll.kernel32
        k32.OpenProcess.restype = ctypes.c_void_p
        k32.CloseHandle.argtypes = [ctypes.c_void_p]
        k32.QueryFullProcessImageNameW.argtypes = [ctypes.c_void_p, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
        h = k32.OpenProcess(0x1000, False, int(pid))                        # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return ""
        buf, n = ctypes.create_unicode_buffer(1024), wintypes.DWORD(1024)
        ok = k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(n))
        k32.CloseHandle(h)
        return os.path.basename(buf.value).lower() if ok else ""
    except Exception:
        return ""


def visible_kiru_window():
    """Windows: the handle of a Kiru main window that is really on screen (another Kiru is open), or 0."""
    if os.name != "nt":
        return 0
    try:
        import ctypes
        from ctypes import wintypes
        u32 = ctypes.windll.user32
        found = []
        me = os.getpid()
        PROC = ctypes.WINFUNCTYPE(wintypes.BOOL, ctypes.c_void_p, ctypes.c_void_p)
        u32.GetWindowThreadProcessId.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.DWORD)]
        u32.IsWindowVisible.argtypes = [ctypes.c_void_p]
        u32.GetWindowTextW.argtypes = [ctypes.c_void_p, wintypes.LPWSTR, ctypes.c_int]

        def each(hwnd, _):
            if u32.IsWindowVisible(hwnd):
                buf = ctypes.create_unicode_buffer(64)
                u32.GetWindowTextW(hwnd, buf, 64)
                if buf.value == APP_NAME:
                    pid = wintypes.DWORD(0)
                    u32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                    if pid.value != me and process_name(pid.value) in ("kiru.exe", "python.exe", "pythonw.exe"):
                        found.append(hwnd)
            return True
        cb = PROC(each)
        u32.EnumWindows.argtypes = [PROC, ctypes.c_void_p]
        u32.EnumWindows(cb, None)
        return found[0] if found else 0
    except Exception:
        return 0


def kill_stray_kiru():
    """Windows, installed app: any other Kiru.exe while no Kiru window is on screen is a left-over of an earlier run -
    an invisible window process, or an engine that lost its window. End them so they hold neither the port nor the program files."""
    if os.name != "nt" or not FROZEN or visible_kiru_window():
        return 0
    n = 0
    try:
        out = subprocess.run(["tasklist", "/fi", "imagename eq " + os.path.basename(sys.executable), "/fo", "csv", "/nh"], capture_output=True, text=True,
                             timeout=10, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
        for ln in out.splitlines():
            f = [x.strip('"') for x in ln.split('","')]
            if len(f) >= 2 and f[1].strip().isdigit() and int(f[1]) != os.getpid():
                kill_tree(int(f[1]))
                n += 1
    except Exception:
        pass
    return n


def port_owner(port):
    """Windows: the process id listening on this port (from netstat), or 0."""
    if os.name != "nt":
        return 0
    try:
        out = subprocess.run(["netstat", "-ano", "-p", "TCP"], capture_output=True, text=True, timeout=8,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
        for ln in out.splitlines():
            f = ln.split()
            if len(f) >= 5 and f[0].upper() == "TCP" and f[1].endswith(":" + str(port)) and f[3].upper() == "LISTENING":
                return int(f[4])
    except Exception:
        pass
    return 0


def wait_port_free(port, seconds):
    t = time.time()
    while time.time() - t < seconds:
        if not port_busy(port):
            return True
        time.sleep(0.2)
    return not port_busy(port)


def already_open():
    """Port 5000 is taken when Kiru starts. -> True when another Kiru really is open (its window is brought to the front);
    False when it was only a left-over of an earlier run, which has been removed, and the port is free again."""
    hwnd = visible_kiru_window()
    if hwnd:
        try:
            import ctypes
            ctypes.windll.user32.ShowWindow(ctypes.c_void_p(hwnd), 9)                  # SW_RESTORE
            ctypes.windll.user32.SetForegroundWindow(ctypes.c_void_p(hwnd))
        except Exception:
            pass
        return True
    if os.name != "nt":
        return True
    # Windows, no Kiru window on screen: something invisible holds the port. If it is a Kiru left behind by an earlier
    # run (ended badly, or one of the old builds' background engines), end it and carry on.
    http_json(f"http://127.0.0.1:{PORT}/api/quit", timeout=1.5, post=True)             # (older builds' engines understand this)
    owner = port_owner(PORT)
    if owner and process_name(owner) in ("kiru.exe",):
        kill_tree(owner)
    kill_stray_kiru()
    return not wait_port_free(PORT, 3.0)


def kiru_ports():
    """The ports on which a Kiru engine answers right now (= the Kiru windows that are open), lowest first.
    Only ports that are really taken are asked, so with no Kiru open this costs nothing."""
    out = []
    for port in range(PORT, PORT_LAST + 1):
        if port_busy(port):
            j = http_json(f"http://127.0.0.1:{port}/api/status", timeout=1.5)
            if isinstance(j, dict) and (j.get("app") == "kiru" or ("ffmpeg" in j and "librosa" in j)):       # (builds before this one did not say "app")
                out.append(port)
    return out


def free_port():
    for port in range(PORT, PORT_LAST + 1):
        if not port_busy(port):
            return port
    return 0


def focus_existing():
    """Bring the Kiru window that is already open to the front (Windows; elsewhere the system does not let one program do that)."""
    hwnd = visible_kiru_window()
    if not hwnd:
        return False
    try:
        import ctypes
        u32 = ctypes.windll.user32
        u32.ShowWindow(ctypes.c_void_p(hwnd), 9)                                       # SW_RESTORE
        u32.SetForegroundWindow(ctypes.c_void_p(hwnd))
        return True
    except Exception:
        return False


def ask_in_app(port):
    """Kiru is open on this port: have ITS window ask the question, in Kiru's own style, and wait for the click.
    -> "window" | "tab" | "switch", or None when no Kiru window is there to ask (then the system box is used)."""
    pre = (os.environ.get("KIRU_ON_SECOND") or "").strip().lower()
    base = f"http://127.0.0.1:{port}"
    if pre in ("tab", "switch"):                                          # (answered beforehand: just tell the open Kiru)
        st = http_json(base + "/api/status", timeout=2.0) or {}
        if st.get("shell"):
            http_json(base + "/api/shell/cmd", timeout=2.0, post={"cmd": "tab" if pre == "tab" else "focus"})
            return pre
        return None
    if pre == "window":
        return "window"
    st = http_json(base + "/api/status", timeout=2.0) or {}
    if not st.get("shell"):
        return None
    allow_foreground(st.get("pid"))
    r = http_json(base + "/api/shell/cmd", timeout=2.0, post={"cmd": "ask"})
    if not r or not r.get("id"):
        return None
    t0 = time.time()
    while time.time() - t0 < 600:                                         # the question stays up until it is answered
        a = http_json(f"{base}/api/shell/answer?id={r['id']}", timeout=30.0)
        if a is None:
            return None                                                   # that Kiru went away
        if a.get("answer") in ("window", "tab", "switch"):
            _ASKED_IN_APP["v"] = True
            return a["answer"]
        if a.get("shell") is False:
            return None
    return "switch"


_ASKED_IN_APP = {"v": False}


def ask_was_in_app():
    """True when the answer came from the question inside the open Kiru (which has then already opened the tab itself)."""
    return _ASKED_IN_APP["v"]


def allow_foreground(pid):
    """Windows only lets the program the user just started bring a window to the front. That is this launcher: hand the right on to the open Kiru."""
    if os.name != "nt" or not pid:
        return
    try:
        import ctypes
        ctypes.windll.user32.AllowSetForegroundWindow(int(pid))
    except Exception:
        pass


def task_dialog3(text, labels):
    """Windows: one box with three named buttons. -> 0 / 1 / 2, or None when this kind of box is not there (then the plain one is used)."""
    import ctypes
    from ctypes import wintypes

    class BUTTON(ctypes.Structure):
        _pack_ = 1
        _fields_ = [("id", ctypes.c_int), ("text", wintypes.LPCWSTR)]

    class CONFIG(ctypes.Structure):
        _pack_ = 1
        _fields_ = [("cbSize", wintypes.UINT), ("hwndParent", ctypes.c_void_p), ("hInstance", ctypes.c_void_p), ("dwFlags", ctypes.c_uint),
                    ("dwCommonButtons", ctypes.c_uint), ("pszWindowTitle", wintypes.LPCWSTR), ("mainIcon", ctypes.c_void_p),
                    ("pszMainInstruction", wintypes.LPCWSTR), ("pszContent", wintypes.LPCWSTR), ("cButtons", wintypes.UINT),
                    ("pButtons", ctypes.POINTER(BUTTON)), ("nDefaultButton", ctypes.c_int), ("cRadioButtons", wintypes.UINT),
                    ("pRadioButtons", ctypes.c_void_p), ("nDefaultRadioButton", ctypes.c_int), ("pszVerificationText", wintypes.LPCWSTR),
                    ("pszExpandedInformation", wintypes.LPCWSTR), ("pszExpandedControlText", wintypes.LPCWSTR),
                    ("pszCollapsedControlText", wintypes.LPCWSTR), ("footerIcon", ctypes.c_void_p), ("pszFooter", wintypes.LPCWSTR),
                    ("pfCallback", ctypes.c_void_p), ("lpCallbackData", ctypes.c_void_p), ("cxWidth", wintypes.UINT)]
    try:
        fn = ctypes.windll.comctl32.TaskDialogIndirect
    except (AttributeError, OSError):
        return None
    btns = (BUTTON * len(labels))(*[BUTTON(100 + i, lb) for i, lb in enumerate(labels)])
    cfg = CONFIG()
    cfg.cbSize = ctypes.sizeof(CONFIG)
    cfg.dwFlags = 0x0008 | 0x1000000                                                   # allow closing with Esc / X, size to the text
    cfg.pszWindowTitle = APP_NAME
    cfg.pszMainInstruction = "Kiru is already open."
    cfg.pszContent = text
    cfg.cButtons = len(labels)
    cfg.pButtons = btns
    cfg.nDefaultButton = 100
    got = ctypes.c_int(0)
    fn.argtypes = [ctypes.POINTER(CONFIG), ctypes.POINTER(ctypes.c_int), ctypes.c_void_p, ctypes.c_void_p]
    fn.restype = ctypes.c_long
    if fn(ctypes.byref(cfg), ctypes.byref(got), None, None) != 0:
        return None
    return got.value - 100 if 100 <= got.value < 100 + len(labels) else 2             # (closed with X / Esc: the window that is there)


def ask_second():
    """Kiru is started while it is already open. -> "window" (a new Kiru window), "tab" (the open Kiru in a browser tab)
    or "switch" (show the window that is there). KIRU_ON_SECOND=window|tab|switch answers without asking."""
    pre = (os.environ.get("KIRU_ON_SECOND") or "").strip().lower()
    if pre in ("window", "tab", "switch"):
        return pre
    names = ["window", "tab", "switch"]
    labels = ["New Window", "New Tab", "Switch to Existing"]
    try:
        if os.name == "nt":
            import ctypes
            try:
                r = task_dialog3("Open a new window, a new tab, or switch to existing window?", labels)
            except Exception:
                r = None
            if r is not None:
                return names[r]
            r = ctypes.windll.user32.MessageBoxW(0, SECOND_ASK + "\n\nYes = New Window\nNo = New Tab\nCancel = Switch to Existing", APP_NAME, 0x3 | 0x20 | 0x10000)
            return {6: "window", 7: "tab"}.get(r, "switch")
        if sys.platform == "darwin":
            r = subprocess.run(["osascript", "-e", f'button returned of (display dialog "{SECOND_ASK}" with title "{APP_NAME}" buttons {{"Switch to Existing", "New Tab", "New Window"}} default button "New Window")'],
                               capture_output=True, text=True, check=False)
            return {"New Window": "window", "New Tab": "tab"}.get((r.stdout or "").strip(), "switch")
        import shutil
        tool = shutil.which("zenity")
        if tool:
            r = subprocess.run([tool, "--question", "--title", APP_NAME, "--text", SECOND_ASK, "--ok-label", "New Window", "--cancel-label", "Switch to Existing", "--extra-button", "New Tab"],
                               capture_output=True, text=True, check=False)
            return "tab" if "New Tab" in (r.stdout or "") else "window" if r.returncode == 0 else "switch"
        tool = shutil.which("kdialog")
        if tool:
            r = subprocess.run([tool, "--title", APP_NAME, "--yesnocancel", SECOND_ASK, "--yes-label", "New Window", "--no-label", "New Tab", "--cancel-label", "Switch to Existing"], check=False)
            return {0: "window", 1: "tab"}.get(r.returncode, "switch")
    except Exception:
        pass
    print(f"[{APP_NAME}] {SECOND_ASK}  (no dialog could be shown: opening a new window)", file=sys.stderr)
    return "window"


def message_box(text, error=False):
    """A native message box."""
    try:
        if os.name == "nt":
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, str(text), APP_NAME, 0x10 if error else 0x40)      # error / information icon
        elif sys.platform == "darwin":
            subprocess.run(["osascript", "-e", f'display alert "{APP_NAME}" message "{str(text).replace(chr(34), chr(39))}"'], check=False)
        else:
            import shutil
            tool = shutil.which("zenity") or shutil.which("kdialog")
            if tool:
                subprocess.run([tool, "--info", "--title", APP_NAME, "--text", str(text)] if "zenity" in tool else [tool, "--msgbox", str(text), "--title", APP_NAME], check=False)
            print(f"[{APP_NAME}] {text}", file=sys.stderr)
    except Exception:
        pass


def confirm_box(text):
    """A native Yes / No question. True = Yes. (If no dialog can be shown, the answer is Yes: never trap the user.)"""
    try:
        if os.name == "nt":
            import ctypes
            return ctypes.windll.user32.MessageBoxW(0, str(text), APP_NAME, 0x4 | 0x30 | 0x100 | 0x10000) == 6      # Yes/No, warning icon, No is the default, on top
        if sys.platform == "darwin":
            r = subprocess.run(["osascript", "-e", f'display dialog "{str(text).replace(chr(34), chr(39))}" with title "{APP_NAME}" buttons {{"Cancel", "Close"}} default button "Cancel" with icon caution'],
                               capture_output=True, check=False)
            return r.returncode == 0
        import shutil
        tool = shutil.which("zenity") or shutil.which("kdialog")
        if tool:
            r = subprocess.run([tool, "--question", "--title", APP_NAME, "--text", str(text)] if "zenity" in tool else [tool, "--warningyesno", str(text), "--title", APP_NAME], check=False)
            return r.returncode == 0
    except Exception:
        pass
    return True


def main():
    add_bundled_ffmpeg()
    if DATA != HERE:                                                       # Mac / Linux install: hand the bundled templates and AI models to the user's data folder once
        import shutil
        for name in ("templates", "ai_model"):
            for src in (os.path.join(HERE, name), os.path.join(HERE, "..", "Resources", name)):
                if os.path.isdir(src) and not os.path.isdir(os.path.join(DATA, name)):
                    shutil.copytree(src, os.path.join(DATA, name))
    os.chdir(DATA)
    if "--gpu-check" in sys.argv or "--ai-selftest" in sys.argv:           # Kiru.exe re-runs itself for these two checks
        import app as kiru
        sys.exit(kiru.gpu_check_main() if "--gpu-check" in sys.argv else kiru.ai_selftest_main())
    try:
        import webview
    except ImportError:                                                    # no PyWebView: the browser, as before
        import app as kiru
        return kiru.main()

    # 1. started while Kiru is open? The open Kiru asks, in its own window. (Nothing here waits when Kiru is not open.)
    global PORT, URL
    running = kiru_ports()
    if os.name == "nt" and (running or port_busy(PORT)) and not visible_kiru_window() \
            and not any((http_json(f"http://127.0.0.1:{p}/api/status", timeout=1.5) or {}).get("shell") for p in running):
        already_open()                                                     # no Kiru window on screen and no Kiru page alive: a left-over of an earlier run. End it.
        running = kiru_ports()
    if running:
        choice = ask_in_app(running[0]) or ask_second()
        if choice == "switch":
            if not http_json(f"http://127.0.0.1:{running[0]}/api/shell/cmd", timeout=2.0, post={"cmd": "focus"}):
                focus_existing()
            os._exit(0)
        if choice == "tab":
            st = http_json(f"http://127.0.0.1:{running[0]}/api/status", timeout=2.0) or {}
            if not st.get("shell"):                                        # (no Kiru window with a tab bar there: the browser, as before)
                import webbrowser
                webbrowser.open(f"http://127.0.0.1:{running[0]}/?tab=t{int(time.time() * 1000) % 100000000:x}")
            elif (os.environ.get("KIRU_ON_SECOND") or "").strip().lower() != "tab" and choice == "tab" and not ask_was_in_app():
                http_json(f"http://127.0.0.1:{running[0]}/api/shell/cmd", timeout=2.0, post={"cmd": "tab"})
            os._exit(0)
    port = free_port()
    if not port:
        message_box(f"Kiru could not find a free port ({PORT} to {PORT_LAST} are all in use). Close a Kiru window and try again.", error=True)
        os._exit(1)
    PORT, URL = port, f"http://127.0.0.1:{port}"
    os.environ["KIRU_PORT"] = str(port)                                    # (the engine reads it: its port, its own temp folder and auto-save)

    # 2. the window, at once, on its own loading page
    api = WindowApi()
    for key, val in (("ALLOW_DOWNLOADS", True), ("DRAG_REGION_DIRECT_TARGET_ONLY", True), ("OPEN_EXTERNAL_LINKS_IN_BROWSER", True)):
        if key in getattr(webview, "settings", {}):
            webview.settings[key] = val
    w, h = window_size(webview)
    win = webview.create_window(APP_NAME, html=LOADING_HTML, width=w, height=h, min_size=(min(1100, w), min(700, h)), frameless=True, easy_drag=False,
                                js_api=api, background_color="#0b0b14", text_select=True)
    api._win = win
    box = {"kiru": None}

    def boot():
        """3. Runs beside the window once it is on screen: load the engine, start it, send the window to it."""
        try:
            import app as kiru
            box["kiru"] = kiru
            start_engine(kiru)
            win.load_url(URL + ("/?solo=1" if os.environ.get("KIRU_TABS") == "0" else "/"))
        except Exception as e:
            msg = f"Kiru could not start.\n\n{e}\n\nIf this keeps happening, restart the PC or reinstall Kiru."
            try:
                win.evaluate_js("document.querySelector('.r').style.display='none';document.getElementById('m').textContent=" + json.dumps(msg))
            except Exception:
                pass
            print(f"[{APP_NAME}] {msg}", file=sys.stderr)
            box["failed"] = True

    def closing():                                                         # Alt+F4, the taskbar, the system menu: the same question
        return api.may_close()

    def closed():
        try:
            kiru = box["kiru"]
            if kiru is not None:
                kiru.wipe_temp()                                           # nothing of yours stays behind
                kiru.autosave_clear()                                      # closed on purpose: nothing to recover next time
        finally:
            os._exit(1 if box.get("failed") else 0)
    try:
        win.events.closing += closing
    except Exception:
        pass
    win.events.closed += closed
    try:
        webview.start(boot, private_mode=False, storage_path=os.path.join(DATA, "_webview"))
    except Exception as e:
        fatal(f"The Kiru window could not be opened.\n\n{e}\n\n" + ("Kiru needs the Microsoft Edge WebView2 Runtime (it is part of Windows 11, and a free download for Windows 10)." if os.name == "nt"
                   else "On Linux Kiru needs GTK WebKit or Qt WebEngine: pip install 'pywebview[qt]' (or your distribution's python3-gi + gir1.2-webkit2-4.1)." if sys.platform.startswith("linux") else ""))
    closed()


if __name__ == "__main__":
    main()
