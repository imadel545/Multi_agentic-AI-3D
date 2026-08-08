#!/bin/sh
set -eu

index_html="$(wget -qO- http://127.0.0.1:8080/)"
main_bundle="$({
  printf '%s\n' "$index_html" \
    | sed -n 's/.*src="\([^\"]*\.js\)".*/\1/p' \
    | head -n 1
} || true)"

case "$main_bundle" in
  /static/*.js) ;;
  *) exit 1 ;;
esac

wget -q --spider "http://127.0.0.1:8080${main_bundle}"
