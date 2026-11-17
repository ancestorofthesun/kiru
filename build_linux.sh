#!/bin/sh
# Kiru - build the Linux app.   ./build_linux.sh
# Result:  dist/installer/Kiru-<version>-linux-<arch>.tar.gz   (unpack, run ./install.sh: adds Kiru to the applications menu, no root)
#          dist/installer/Kiru-<version>-<arch>.AppImage        (also, when appimagetool is on PATH: one file you can double-click)
# Needs:   Python 3.10+ with venv, FFmpeg (bundled when found), and Qt for the window (installed by pip below).
set -e
cd "$(dirname "$0")"
PY="${PYTHON:-python3}"
"$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' || { echo "Python 3.10 or newer is needed."; exit 1; }
[ -d .venv-build ] || "$PY" -m venv .venv-build
. .venv-build/bin/activate
pip install --upgrade pip >/dev/null
pip install -r requirements.txt pyinstaller "pywebview[qt]"
python scripts/build_installer.py "$@"
echo "Done: dist/installer/"
