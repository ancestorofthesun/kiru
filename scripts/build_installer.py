"""Build Kiru for the system you are on. One command, one installer per system:

    python scripts/build_installer.py              # app + installer
    python scripts/build_installer.py --app-only    # just the app folder / bundle in dist/

  Windows  ->  dist/installer/KiruSetup.exe                (PyInstaller + Inno Setup 6.6+, installs per user, no admin rights)
  macOS    ->  dist/installer/Kiru-<version>-macOS-<arch>.dmg   (PyInstaller .app + hdiutil; drag Kiru to Applications)
  Linux    ->  dist/installer/Kiru-<version>-linux-<arch>.tar.gz  (folder + install.sh: menu entry, no root)
               dist/installer/Kiru-<version>-<arch>.AppImage      (also, when appimagetool is on PATH: one double-clickable file)

The app is built WITHOUT a console (PyInstaller --windowed = --noconsole = console=False): no terminal window ever opens,
and every FFmpeg / helper process Kiru starts is created with CREATE_NO_WINDOW.

The easy way: build_windows.bat, build_mac.sh or build_linux.sh in the project folder (they install what is needed, then run this).

PyInstaller does not cross-compile: build each one on its own system, or let .github/workflows/build.yml do all three.

Needs (once):  pip install pyinstaller pywebview -r requirements.txt          (Linux: pip install "pywebview[qt]")
FFmpeg:        Windows: put ffmpeg.exe + ffprobe.exe in vendor/ffmpeg/ (or have them on PATH) - they are bundled.
               macOS / Linux: bundled too when found in vendor/ffmpeg/ or on PATH; otherwise the app uses the system's FFmpeg.
Offline:       if an ai_model/ folder exists (Kiru downloads the AI models there on first use), it is bundled,
               so the installed app needs no internet at all.

UPX is deliberately NOT used: UPX-packed executables are a common false positive in Windows Defender.

© 2026 Aden. All rights reserved.
"""
import os
import platform
import shutil
import subprocess
import sys
import tarfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VERSION = "1.0.0"
WIN, MAC = os.name == "nt", sys.platform == "darwin"
OUT = os.path.join(ROOT, "dist", "installer")

def run(cmd, **kw):
    print(">", " ".join(cmd))
    subprocess.check_call(cmd, **kw)


def find_ffmpeg(required):
    vend, out = os.path.join(ROOT, "vendor", "ffmpeg"), []
    for name in ("ffmpeg", "ffprobe"):
        exe = name + (".exe" if WIN else "")
        p = os.path.join(vend, exe)
        if not os.path.isfile(p):
            p = shutil.which(exe) or shutil.which(name)
        if not p:
            if required:
                sys.exit(f"[build] {exe} not found. Put it in vendor/ffmpeg/ or on PATH.")
            print(f"[build] note: {name} not found - the app will use the FFmpeg installed on the user's system.")
            return []
        out.append(p)
    return out


def add_payload(folder):
    """Next to the program: the AI models (when present), the built-in templates, licence. (FFmpeg is bundled by kiru.spec.)"""
    models = os.path.join(ROOT, "ai_model")
    if os.path.isdir(models):
        shutil.copytree(models, os.path.join(folder, "ai_model"), dirs_exist_ok=True)
    else:
        print("[build] note: no ai_model/ folder - the installed app downloads the AI models on first use (run Kiru once from source to fetch them, then build again for a fully offline installer).")
    for name in ("templates", "locales"):               # built-in templates, the language files (Settings > Language)
        if os.path.isdir(os.path.join(ROOT, name)):
            shutil.copytree(os.path.join(ROOT, name), os.path.join(folder, name), dirs_exist_ok=True)
    for name in ("LICENSE", "README.md"):
        shutil.copy2(os.path.join(ROOT, name), folder)


FFMPEG_HELP = """
  [X] FFmpeg is missing: {what}

      Kiru cannot make videos without it, so the build stops here instead of making a broken app.

      Fix:  1. download  https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip
            2. open it and copy  bin\\ffmpeg.exe  and  bin\\ffprobe.exe  into  {vend}
            3. run build_windows.bat again
"""


def build_app():
    if WIN:                                               # stop early, with words, when FFmpeg is not there to bundle
        vend = os.path.join(ROOT, "vendor", "ffmpeg")
        gone = [e for e in ("ffmpeg.exe", "ffprobe.exe") if not os.path.isfile(os.path.join(vend, e))]
        if gone:
            sys.exit(FFMPEG_HELP.format(what=", ".join(gone), vend=vend))
    else:
        find_ffmpeg(required=False)
    for d in ("build", "dist"):
        shutil.rmtree(os.path.join(ROOT, d), ignore_errors=True)
    # everything about the app itself (hidden imports, bundled FFmpeg, no console, no UPX, icon, copyright) is in kiru.spec
    run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", os.path.join(ROOT, "kiru.spec")], cwd=ROOT)
    folder = os.path.join(ROOT, "dist", "Kiru.app", "Contents", "Resources") if MAC else os.path.join(ROOT, "dist", "Kiru")
    add_payload(folder)
    exe = os.path.join(ROOT, "dist", "Kiru.app", "Contents", "MacOS", "Kiru") if MAC else os.path.join(ROOT, "dist", "Kiru", "Kiru.exe" if WIN else "Kiru")
    if not os.path.isfile(exe):
        sys.exit(f"[build] PyInstaller finished but {exe} is not there - see the messages above.")
    print(f"[build] app ready in {os.path.join(ROOT, 'dist')}")


def installer_windows():
    iscc = shutil.which("iscc") or next((p for p in (
        os.path.join(os.environ.get("ProgramFiles(x86)", ""), "Inno Setup 6", "ISCC.exe"),
        os.path.join(os.environ.get("ProgramFiles", ""), "Inno Setup 6", "ISCC.exe"),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Inno Setup 6", "ISCC.exe")) if os.path.isfile(p)), None)
    if not iscc:
        sys.exit("\n  [X] Inno Setup was not found, so KiruSetup.exe could not be made.\n"
                 "      The app itself IS built: dist\\Kiru\\Kiru.exe\n"
                 "      Install Inno Setup 6 (https://jrsoftware.org/isdl.php  or:  winget install JRSoftware.InnoSetup) and run build_windows.bat again.\n")
    iss = os.path.join(ROOT, "scripts", "installer.iss")
    try:
        run([iscc, f"/DAppVersion={VERSION}", iss], cwd=ROOT)
    except subprocess.CalledProcessError:                 # never lose the installer over its optional script part
        print("[build] the installer script's [Code] part did not compile here - building the installer without it.")
        run([iscc, f"/DAppVersion={VERSION}", "/DNoCode", iss], cwd=ROOT)


def installer_macos():
    os.makedirs(OUT, exist_ok=True)
    stage = os.path.join(ROOT, "build", "dmg")
    shutil.rmtree(stage, ignore_errors=True)
    os.makedirs(stage)
    shutil.copytree(os.path.join(ROOT, "dist", "Kiru.app"), os.path.join(stage, "Kiru.app"), symlinks=True)
    os.symlink("/Applications", os.path.join(stage, "Applications"))
    dmg = os.path.join(OUT, f"Kiru-{VERSION}-macOS-{platform.machine()}.dmg")
    run(["hdiutil", "create", "-volname", "Kiru", "-srcfolder", stage, "-ov", "-format", "UDZO", dmg])


def installer_linux():
    os.makedirs(OUT, exist_ok=True)
    src = os.path.join(ROOT, "dist", "Kiru")
    shutil.copy2(os.path.join(ROOT, "scripts", "install_linux.sh"), os.path.join(src, "install.sh"))
    shutil.copy2(os.path.join(ROOT, "assets", "kiru.png"), os.path.join(src, "kiru.png"))
    os.chmod(os.path.join(src, "install.sh"), 0o755)
    with tarfile.open(os.path.join(OUT, f"Kiru-{VERSION}-linux-{platform.machine()}.tar.gz"), "w:gz") as tar:
        tar.add(src, arcname="Kiru")
    tool = shutil.which("appimagetool") or shutil.which("appimagetool-x86_64.AppImage")
    if not tool:
        print("[build] appimagetool not found: only the .tar.gz was made (get it from https://github.com/AppImage/appimagetool/releases for an .AppImage).")
        return
    appdir = os.path.join(ROOT, "build", "Kiru.AppDir")
    shutil.rmtree(appdir, ignore_errors=True)
    shutil.copytree(src, os.path.join(appdir, "usr", "lib", "kiru"), symlinks=True)
    shutil.copy2(os.path.join(ROOT, "assets", "kiru.png"), os.path.join(appdir, "kiru.png"))
    with open(os.path.join(appdir, "kiru.desktop"), "w", encoding="utf-8") as fh:
        fh.write("[Desktop Entry]\nType=Application\nName=Kiru\nComment=Beat-synced edits, a timeline editor and an image editor\n"
                 "Exec=Kiru\nIcon=kiru\nTerminal=false\nCategories=AudioVideo;Video;Graphics;\nX-Copyright=\u00a9 2026 Aden. All rights reserved.\n")
    with open(os.path.join(appdir, "AppRun"), "w") as fh:
        fh.write('#!/bin/sh\nHERE="$(dirname "$(readlink -f "$0")")"\nexec "$HERE/usr/lib/kiru/Kiru" "$@"\n')
    os.chmod(os.path.join(appdir, "AppRun"), 0o755)
    env = dict(os.environ, ARCH=platform.machine(), APPIMAGE_EXTRACT_AND_RUN="1")
    run([tool, appdir, os.path.join(OUT, f"Kiru-{VERSION}-{platform.machine()}.AppImage")], env=env)


if __name__ == "__main__":
    build_app()
    if "--app-only" not in sys.argv and "--exe-only" not in sys.argv:
        (installer_windows if WIN else installer_macos if MAC else installer_linux)()
        print(f"[build] installer written to {OUT}")
