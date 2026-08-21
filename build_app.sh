#!/bin/zsh
set -euo pipefail
ROOT="${0:A:h}"
APP="$ROOT/build/Vivo Lightroom Archive Converter.app"
CONTENTS="$APP/Contents"
rm -rf "$APP"
mkdir -p "$CONTENTS/MacOS" "$CONTENTS/Resources/Engine"
clang -fobjc-arc -framework Cocoa "$ROOT/AppKit/main.m" \
  -o "$CONTENTS/MacOS/VivoLightroomArchiveConverter"
cp "$ROOT/Resources/Info.plist" "$CONTENTS/Info.plist"
cp "$ROOT/Resources/AppIcon.icns" "$CONTENTS/Resources/AppIcon.icns"
cp "$ROOT/Engine"/*.py "$CONTENTS/Resources/Engine/"
codesign --force --deep --sign - "$APP"
echo "$APP"
