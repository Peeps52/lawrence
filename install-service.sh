#!/bin/bash
# Run Lawrence at login, in the background, with no terminal window.
#   ./install-service.sh          install and start
#   ./install-service.sh remove   stop and uninstall
set -e
LABEL="com.francesconagel.lawrence"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ "$1" = "remove" ]; then
  launchctl bootout "gui/$UID/$LABEL" 2>/dev/null || true
  rm -f "$PLIST"
  echo "Lawrence removed."
  exit 0
fi

mkdir -p "$HOME/Library/LaunchAgents" "$HOME/.lawrence"
cat > "$PLIST" <<PL
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>/usr/bin/python3</string>
    <string>$DIR/lawrence.py</string>
  </array>
  <key>WorkingDirectory</key><string>$DIR</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>$HOME/.lawrence/out.log</string>
  <key>StandardErrorPath</key><string>$HOME/.lawrence/err.log</string>
</dict></plist>
PL

launchctl bootout "gui/$UID/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$UID" "$PLIST"
echo "Lawrence installed and running in the background."
echo "  logs:    ~/.lawrence/out.log"
echo "  stop:    ./install-service.sh remove"
echo
echo "macOS will ask for microphone access the first time. If you miss the"
echo "prompt, grant it under System Settings > Privacy & Security > Microphone."
