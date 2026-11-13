#!/bin/sh
# Kiru - install for the current user (no root): program in ~/.local/opt/Kiru, launcher in ~/.local/bin, menu entry.
# Run it from the unpacked folder:   ./install.sh        Remove with:   ./install.sh --uninstall
set -e
APP="$HOME/.local/opt/Kiru"; BIN="$HOME/.local/bin"; DESK="$HOME/.local/share/applications"; ICON="$HOME/.local/share/icons/hicolor/256x256/apps"
if [ "$1" = "--uninstall" ]; then
  rm -rf "$APP" "$BIN/kiru" "$DESK/kiru.desktop" "$ICON/kiru.png"
  echo "Kiru removed. Your templates, fonts and exports in ~/.local/share/Kiru were left alone."; exit 0
fi
HERE="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$APP" "$BIN" "$DESK" "$ICON"
cp -a "$HERE/." "$APP/"
cp "$HERE/kiru.png" "$ICON/kiru.png"
ln -sf "$APP/Kiru" "$BIN/kiru"
cat > "$DESK/kiru.desktop" <<EOT
[Desktop Entry]
Type=Application
Name=Kiru
Comment=Beat-synced edits, a timeline editor and an image editor
X-Copyright=© 2026 Aden. All rights reserved.
Exec=$APP/Kiru
Icon=kiru
Terminal=false
Categories=AudioVideo;Video;Graphics;
EOT
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$DESK" >/dev/null 2>&1 || true
command -v ffmpeg >/dev/null 2>&1 || [ -x "$APP/ffmpeg/ffmpeg" ] || echo "Note: FFmpeg was not found. Install it (for example: sudo apt install ffmpeg) before you export."
echo "Kiru is installed. Start it from the applications menu, or run: kiru"
