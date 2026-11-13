"""Kiru - desktop launcher. The simple way:

  1. started twice? -> a message box "Kiru is already open." and nothing else;
  2. the engine (the Flask app in app.py) starts on a background thread;
  3. the Kiru window opens straight onto http://127.0.0.1:5000.

That is all this file does. There is no splash screen, no second process, no hand-off and no waiting loop, and after
the window exists nothing in here touches it from another thread. The loading screen is part of the page itself
(app.py): it is the first thing the page draws, and it goes away when the engine answers /api/status. The engine's heavy
background work (sound-analysis library, AI self-test) starts only after that, on background threads.

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

PORT = 5000
URL = f"http://127.0.0.1:{PORT}"


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

    def win_min(self):
        self._win.minimize()

    def win_max(self):
        if self._maxed:
            self._win.restore()
        else:
            self._win.maximize()
        self._maxed = not self._maxed
        return self._maxed

    def win_close(self):
        self._win.destroy()

    def win_resize(self, width, height):
        if not self._maxed:
            self._win.resize(max(900, int(width)), max(600, int(height)))


def http_json(url, timeout=1.0, post=False):
    """A tiny HTTP call to the engine. -> the JSON it answered, or None."""
    try:
        req = urllib.request.Request(url, data=b"{}" if post else None, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8", "replace") or "{}")
    except Exception:
        return None


def port_busy(port):
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sk:
        sk.settimeout(0.4)
        return sk.connect_ex(("127.0.0.1", port)) == 0


def start_engine(kiru):
    """Flask on a background thread. The port is bound before this returns, so the window can be pointed at it at once.
    Nothing heavy starts here: the page asks for the background work when the editor is on screen (app.start_warmups),
    and a timer does it anyway after 20 seconds."""
    kiru.wipe_temp()
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

    # 1. started twice? Say so and stop. (Everything here happens before any window exists.)
    if port_busy(PORT) and already_open():
        message_box("Kiru is already open.")
        os._exit(0)

    # 2. the engine, on a background thread
    try:
        import app as kiru
        start_engine(kiru)
    except Exception as e:
        fatal(f"Kiru could not start.\n\n{e}\n\nIf this keeps happening, restart the PC or reinstall Kiru.")

    # 3. the window, straight onto the editor
    api = WindowApi()
    for key, val in (("ALLOW_DOWNLOADS", True), ("DRAG_REGION_DIRECT_TARGET_ONLY", True), ("OPEN_EXTERNAL_LINKS_IN_BROWSER", True)):
        if key in getattr(webview, "settings", {}):
            webview.settings[key] = val
    w, h = window_size(webview)
    win = webview.create_window(APP_NAME, URL, width=w, height=h, min_size=(min(1100, w), min(700, h)), frameless=True, easy_drag=False,
                                js_api=api, background_color="#0b0b14", text_select=True)
    api._win = win

    def closed():
        try:
            kiru.wipe_temp()                                               # nothing of yours stays behind
        finally:
            os._exit(0)
    win.events.closed += closed
    try:
        webview.start(private_mode=False, storage_path=os.path.join(DATA, "_webview"))
    except Exception as e:
        fatal(f"The Kiru window could not be opened.\n\n{e}\n\n" + ("Kiru needs the Microsoft Edge WebView2 Runtime (it is part of Windows 11, and a free download for Windows 10)." if os.name == "nt"
                   else "On Linux Kiru needs GTK WebKit or Qt WebEngine: pip install 'pywebview[qt]' (or your distribution's python3-gi + gir1.2-webkit2-4.1)." if sys.platform.startswith("linux") else ""))
    closed()


if __name__ == "__main__":
    main()
