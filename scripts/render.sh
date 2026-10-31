#!/usr/bin/env bash
# Renders every file under the templates directory (except fragments) to the same path at the
# repository root, filling placeholders from policy/constants.json (see render.jq).
#   render.sh          write the rendered files
#   render.sh --check  render to a scratch directory and exit 1 if any committed file differs
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
constants="$root/policy/constants.json"
read_const() { jq -er --arg k "$1" 'getpath($k | split("."))' "$constants"; }
templates="$root/$(read_const render.templatesDir)"
fragments="$root/$(read_const render.fragmentsDir)"

mode="${1:-write}"
case "$mode" in
  write) out="$root" ;;
  --check) out="$(mktemp -d)"; trap 'rm -rf "$out"' EXIT ;;
  *) echo "usage: render.sh [--check]" >&2; exit 2 ;;
esac

frags="$(cd "$fragments" && for f in *.yml; do jq -Rs --arg n "$f" '{($n): .}' "$f"; done | jq -s 'add // {}')"

header() {
  local src="$1"
  case "$src" in
    *.yml|*.yaml|*.toml) printf '# Generated from %s and policy/constants.json by %s. Do not edit.\n' "$src" "$(read_const render.script)" ;;
    *.md) printf '<!-- Generated from %s and policy/constants.json by %s. Do not edit. -->\n' "$src" "$(read_const render.script)" ;;
    *) ;;
  esac
}

status=0
while IFS= read -r -d '' tpl; do
  rel="${tpl#"$templates"/}"
  src="${tpl#"$root"/}"
  dest="$out/$rel"
  mkdir -p "$(dirname "$dest")"
  body="$(jq -nr --slurpfile c "$constants" --argjson frags "$frags" --rawfile t "$tpl" -f "$(dirname "${BASH_SOURCE[0]}")/render.jq")"
  case "$rel" in
    *.json) printf '%s\n' "$body" | jq . > "$dest" ;;
    *) { header "$src"; printf '%s\n' "$body"; } > "$dest" ;;
  esac
  if [ "$mode" = "--check" ]; then
    if ! cmp -s "$dest" "$root/$rel"; then
      echo "::error file=$rel::$rel is not what $src renders to; run $(read_const render.script)"
      diff -u "$root/$rel" "$dest" || true
      status=1
    fi
  fi
done < <(find "$templates" -type f ! -path "$fragments/*" -print0 | sort -z)

exit "$status"
