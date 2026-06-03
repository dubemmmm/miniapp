#!/usr/bin/env bash
# Build the prebuilt Tailwind CSS via the standalone CLI (no Node/npm).
# Run locally before `manage.py runserver`, and in deploy before collectstatic.
#   bash build_tailwind.sh
set -euo pipefail

VERSION="v3.4.17"
case "$(uname -s)-$(uname -m)" in
  Darwin-arm64)  BIN="tailwindcss-macos-arm64" ;;
  Darwin-*)      BIN="tailwindcss-macos-x64" ;;
  Linux-aarch64) BIN="tailwindcss-linux-arm64" ;;
  *)             BIN="tailwindcss-linux-x64" ;;
esac

mkdir -p bin
if [ ! -x bin/tailwindcss ]; then
  echo "Fetching Tailwind standalone CLI $VERSION ($BIN)…"
  curl -sL -o bin/tailwindcss "https://github.com/tailwindlabs/tailwindcss/releases/download/${VERSION}/${BIN}"
  chmod +x bin/tailwindcss
fi

./bin/tailwindcss \
  -c tailwind.config.js \
  -i static/miniapp/css/tailwind.src.css \
  -o static/miniapp/css/tailwind.css \
  --minify
echo "Built static/miniapp/css/tailwind.css"
