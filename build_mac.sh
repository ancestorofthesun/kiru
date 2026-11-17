#!/bin/sh
# Kiru - build the macOS app and its disk image.   ./build_mac.sh
# Result:  dist/Kiru.app  (a native bundle, no Terminal window)  and  dist/installer/Kiru-<version>-macOS-<arch>.dmg
# Needs:   Python 3.10+ (python.org or Homebrew). FFmpeg is bundled when found (brew install ffmpeg).
set -e
cd "$(dirname "$0")"
PY="${PYTHON:-python3}"
"$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' || { echo "Python 3.10 or newer is needed."; exit 1; }
[ -d .venv-build ] || "$PY" -m venv .venv-build
. .venv-build/bin/activate
pip install --upgrade pip >/dev/null
pip install -r requirements.txt pyinstaller pywebview
python scripts/build_installer.py "$@"
echo "Done: dist/installer/"
