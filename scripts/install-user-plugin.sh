#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HERMES_HOME_DIR="${HERMES_HOME:-$HOME/.hermes}"
DEST="$HERMES_HOME_DIR/plugins/mnemosyne"

mkdir -p "$(dirname "$DEST")"
rm -rf "$DEST"
cp -R "$ROOT/plugins/memory/mnemosyne" "$DEST"

echo "Installed Mnemosyne memory provider to $DEST"
echo "Enable it in config.yaml with: memory.provider: mnemosyne"
