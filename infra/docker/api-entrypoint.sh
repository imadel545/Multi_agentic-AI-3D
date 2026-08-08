#!/bin/sh
set -eu

blender_binary="${TELECOM_STUDIO_BLENDER_BINARY:-/opt/blender/blender}"
expected_version="Blender 4.5.12 LTS"

mkdir -p "${HOME:-/tmp/telecom-studio-home}"

if [ ! -x "$blender_binary" ]; then
  echo "Blender preflight failed: executable is unavailable." >&2
  exit 70
fi

blender_version="$($blender_binary --background --factory-startup --version 2>&1)"
first_line="$(printf '%s\n' "$blender_version" | sed -n '1p')"
case "$first_line" in
  "$expected_version" | "$expected_version ("*) ;;
  *)
    echo "Blender preflight failed: expected '$expected_version', got '$first_line'." >&2
    exit 71
    ;;
esac

for writable_dir in /var/lib/telecom/sqlite /var/lib/telecom/outputs; do
  if [ ! -d "$writable_dir" ] || [ ! -w "$writable_dir" ]; then
    echo "Storage preflight failed: $writable_dir is not writable." >&2
    exit 72
  fi
done

echo "Blender preflight passed: $expected_version (background/factory-startup)."
exec "$@"
