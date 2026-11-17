# -*- mode: python ; coding: utf-8 -*-
# Kiru - PyInstaller build description. Used by build_windows.bat, build_mac.sh and build_linux.sh:
#
#     pyinstaller --noconfirm --clean kiru.spec
#
# What it guarantees:
#   * no console window, ever (console=False) and no UPX (UPX-packed programs are a common antivirus false alarm)
#   * every module Kiru loads by name is listed under hiddenimports, so the built app cannot start "missing" one
#   * FFmpeg is INSIDE the app: vendor/ffmpeg/ffmpeg(.exe) + ffprobe(.exe) -> <app>/ffmpeg/
#     On Windows the build stops with a clear message if they are not there (build_windows.bat fetches them first).
#   * the program's properties show:  (c) 2026 Aden. All rights reserved.
import os
import shutil
import sys

from PyInstaller.utils.hooks import collect_all

ROOT = os.path.abspath(SPECPATH)
VERSION = "1.0.0"
COPYRIGHT = "© 2026 Aden. All rights reserved."
WIN, MAC = os.name == "nt", sys.platform == "darwin"

# ---------------------------------------------------------------- FFmpeg (bundled)
datas, binaries = [], []
missing = []
for name in ("ffmpeg", "ffprobe"):
    exe = name + (".exe" if WIN else "")
    path = os.path.join(ROOT, "vendor", "ffmpeg", exe)
    if not os.path.isfile(path):          # Windows: only vendor/ffmpeg counts (what is on PATH may be a package manager's shim, not the program)
        path = "" if WIN else (shutil.which(exe) or shutil.which(name) or "")
    if path:
        datas.append((path, "ffmpeg"))
    else:
        missing.append(exe)
if missing and WIN:
    raise SystemExit(
        "\n\n  [Kiru build] FFmpeg is missing: " + ", ".join(missing) + "\n"
        "  Kiru cannot make videos without it, so the build stops here instead of making a broken app.\n\n"
        "  Fix:  1. download  https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip\n"
        "        2. open it and copy  bin\\ffmpeg.exe  and  bin\\ffprobe.exe  into  " + os.path.join(ROOT, "vendor", "ffmpeg") + "\n"
        "        3. run build_windows.bat again   (it normally downloads them for you: check your internet connection)\n")
if missing:
    print("[Kiru build] note: " + ", ".join(missing) + " not found - the app will use the FFmpeg installed on the user's system.")

# (templates, AI models, LICENSE and README are placed next to the program by scripts/build_installer.py, where Kiru looks for them)

# ---------------------------------------------------------------- modules
hiddenimports = [
    # Kiru itself: the launcher imports the server by name
    "app",
    # the window
    "webview", "webview.http", "webview.util", "webview.window", "webview.event", "webview.menu", "webview.screen", "webview.localization",
    "bottle", "proxy_tools", "typing_extensions",
    # the local server
    "flask", "flask.json", "flask.json.provider", "werkzeug", "werkzeug.serving", "werkzeug.routing", "werkzeug.middleware.shared_data",
    "jinja2", "jinja2.ext", "markupsafe", "itsdangerous", "click", "blinker",
    # sound analysis
    "librosa", "librosa.core", "librosa.beat", "librosa.onset", "librosa.feature", "librosa.util", "audioread", "soundfile", "soxr", "pooch", "lazy_loader",
    "numba", "llvmlite", "scipy", "scipy.signal", "scipy.fft", "scipy.ndimage", "scipy.interpolate", "scipy.special", "scipy.sparse",
    "scipy._lib.messagestream", "sklearn", "sklearn.utils._typedefs", "sklearn.utils._heap", "sklearn.utils._sorting", "sklearn.utils._vector_sentinel",
    "sklearn.neighbors._partition_nodes", "joblib", "threadpoolctl", "decorator", "msgpack",
    # pictures and video analysis
    "numpy", "cv2", "PIL", "PIL.Image", "PIL.ImageDraw", "PIL.ImageFont", "PIL.ImageFilter", "PIL.ImageOps", "PIL.ImageChops", "PIL.ImageEnhance",
    "scenedetect", "scenedetect.detectors", "pytesseract",
    # AI (background removal, text reading)
    "onnxruntime", "onnxruntime.capi", "onnxruntime.capi.onnxruntime_pybind11_state", "rembg", "rembg.sessions", "pymatting", "skimage", "skimage.transform",
    "rapidocr_onnxruntime", "pyclipper", "shapely", "yaml", "six",
    # Voice (Kokoro text to speech)
    "kokoro_onnx", "phonemizer", "phonemizer.backend", "phonemizer.backend.espeak", "espeakng_loader", "joblib", "attr", "dlinfo",
]
if WIN:
    hiddenimports += ["webview.platforms.edgechromium", "webview.platforms.winforms", "clr", "clr_loader", "pythonnet", "ctypes.wintypes", "win32timezone"]
elif MAC:
    hiddenimports += ["webview.platforms.cocoa", "objc", "Foundation", "AppKit", "WebKit", "Quartz", "Security", "UniformTypeIdentifiers"]
else:
    hiddenimports += ["webview.platforms.qt", "webview.platforms.gtk", "qtpy", "PyQt6", "PyQt6.QtCore", "PyQt6.QtGui", "PyQt6.QtWidgets",
                      "PyQt6.QtWebEngineWidgets", "PyQt6.QtWebEngineCore", "PyQt6.QtWebChannel", "PyQt6.QtNetwork"]

# packages that keep data files / native libraries next to their code: take everything, when they are installed
for pkg in ("webview", "librosa", "rembg", "rapidocr_onnxruntime", "onnxruntime", "scenedetect", "numba", "llvmlite", "soundfile", "pymatting",
            "soxr", "audioread", "lazy_loader", "sklearn", "skimage", "pythonnet", "clr_loader",
            "kokoro_onnx", "phonemizer", "espeakng_loader", "joblib"):
    try:
        d, b, h = collect_all(pkg)
    except Exception:
        continue
    datas += d
    binaries += b
    hiddenimports += h


def installed(mod):
    """Leave out names that are not installed on this machine (optional packages), so the build never stops on one."""
    import importlib.util
    try:
        return importlib.util.find_spec(mod.split(".")[0]) is not None
    except Exception:
        return False


hiddenimports = sorted({m for m in hiddenimports if installed(m)})
excludes = ["tkinter", "matplotlib", "IPython", "jupyter", "notebook", "pytest", "torch", "tensorflow", "pandas", "PyQt5"]

a = Analysis(
    [os.path.join(ROOT, "kiru.py")],
    pathex=[ROOT],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
)
pyz = PYZ(a.pure)

icon = os.path.join(ROOT, "assets", "kiru.icns" if MAC else "kiru.ico" if WIN else "kiru.png")
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Kiru",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,                       # never: antivirus false alarms
    console=False,                   # never a terminal / command prompt window
    disable_windowed_traceback=False,
    icon=icon if os.path.isfile(icon) and (WIN or MAC) else None,
    version=os.path.join(ROOT, "scripts", "version_info.txt") if WIN else None,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="Kiru")

if MAC:
    app = BUNDLE(
        coll,
        name="Kiru.app",
        icon=icon if os.path.isfile(icon) else None,
        bundle_identifier="app.kiru.desktop",
        version=VERSION,
        info_plist={
            "CFBundleName": "Kiru",
            "CFBundleDisplayName": "Kiru",
            "CFBundleShortVersionString": VERSION,
            "CFBundleVersion": VERSION,
            "NSHumanReadableCopyright": COPYRIGHT,
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "11.0",
            "LSApplicationCategoryType": "public.app-category.video",
        },
    )
