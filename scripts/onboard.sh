#!/usr/bin/env bash
# Brings a repository of the organisation to the defaults in docs/new-repo-checklist.md:
#   steps 1, 2 and 5 (security settings, merge settings, ruleset) are applied through the API;
#   step 4 (files) is printed as a diff against the consumer templates, for a pull request;
#   step 3 (team access) needs an organisation owner and is only checked.
# Usage: PIN=<sha> scripts/onboard.sh [--dry-run] <repo>
#   <repo> a repository of the organisation, as <name> or <owner>/<name>; no other path segments
#   GH   the command used for API calls, default "gh"; set it to run as the automation account,
#        for example GH="et app exec --item <key item> --account <account> --app-id <id> --installation <id> -- gh"
#   PIN  required: the full 40-hex commit of this repository the callers pin
#   REF  the label written after the pin; default the release tag (release.tag), and only when
#        that tag exists and points at PIN; otherwise no label is written
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
constants="$root/policy/constants.json"
c() { jq -er --arg k "$1" 'getpath($k | split("."))' "$constants"; }

dry=false
if [ "${1:-}" = --dry-run ]; then dry=true; shift; fi
usage() { echo "usage: PIN=<40-hex sha> onboard.sh [--dry-run] <repo>" >&2; exit 2; }
[ $# -eq 1 ] || usage
org="$(c org.name)"
name_re='^[A-Za-z0-9._-]+$'
case "$1" in
  */*/*) echo "error: <repo> must be <name> or <owner>/<name>, got '$1'" >&2; exit 2 ;;
  */*) owner="${1%%/*}"; name="${1#*/}" ;;
  *) owner="$org"; name="$1" ;;
esac
[ "$owner" = "$org" ] || { echo "error: <repo> must belong to $org, got owner '$owner'" >&2; exit 2; }
if ! [[ "$name" =~ $name_re ]] || [ "$name" = . ] || [ "$name" = .. ]; then
  echo "error: '$name' is not a repository name" >&2; exit 2
fi
repo="$org/$name"
read -r -a gh <<<"${GH:-gh}"
default_branch="$(c org.defaultBranch)"
api() { "${gh[@]}" api "$@"; }

pin="${PIN:-}"
[[ "$pin" =~ ^[0-9a-f]{40}$ ]] || { echo "error: PIN must be a full 40-hex commit sha, got '${pin}'" >&2; usage; }
self="$org/$(c org.repo)"
[ "$(api "repos/$self/commits/$pin" --jq '.sha' 2>/dev/null || true)" = "$pin" ] \
  || { echo "error: PIN $pin is not a commit of $self" >&2; exit 2; }
if [ -n "${REF:-}" ]; then
  ref="$REF"
  [[ "$ref" =~ ^[A-Za-z0-9._-]+$ ]] || { echo "error: REF may hold only letters, digits, '.', '_' and '-', got '$ref'" >&2; exit 2; }
else
  tag="$(c release.tag)"
  tag_sha="$(api "repos/$self/commits/$tag" --jq '.sha' 2>/dev/null || true)"
  if [ "$tag_sha" = "$pin" ]; then
    ref="$tag"
  else
    ref=""
    if [ -n "$tag_sha" ]; then why="points at $tag_sha, not PIN"; else why="does not exist"; fi
    echo "note: tag $tag $why; writing no label after the pin"
  fi
fi
if [ -n "$ref" ]; then label=(-e "s/__REF__/$ref/g"); else label=(-e 's/ # __REF__//g'); fi

write() {
  echo "+ api $*"
  if [ "$dry" = false ]; then api "$@" > /dev/null; fi
}

echo "== 1. security settings: $repo"
write -X PUT "repos/$repo/private-vulnerability-reporting"
write -X PATCH "repos/$repo" -f 'security_and_analysis[secret_scanning][status]=enabled' \
  -f 'security_and_analysis[secret_scanning_push_protection][status]=enabled'
write -X PUT "repos/$repo/vulnerability-alerts"

echo "== 2. merge settings"
merge_args=(-F allow_auto_merge=true)
for method in merge squash rebase; do
  allowed="$(jq -r --arg m "$method" '.ruleset.allowedMergeMethods | index([$m]) != null' "$constants")"
  field="allow_${method}_merge"; [ "$method" = merge ] && field=allow_merge_commit
  merge_args+=(-F "$field=$allowed")
done
write -X PATCH "repos/$repo" "${merge_args[@]}"

echo "== 3. maintainers (an organisation owner grants this by hand)"
team="$(c org.maintainer)"; team="${team#@*/}"
permission="$(api "repos/$repo/teams" --jq ".[] | select(.slug == \"$team\") | .permission" 2>/dev/null || true)"
if [ "$permission" = push ] || [ "$permission" = maintain ] || [ "$permission" = admin ]; then
  echo "ok: $(c org.maintainer) has $permission"
else
  echo "TODO: give $(c org.maintainer) Write access to $repo (currently: ${permission:-none})"
fi

echo "== 4. files (diff of the repository's $default_branch against the templates; open a pull request with these)"
paths="$(api "repos/$repo/contents/$(c automerge.pathsFile)?ref=$default_branch" --jq '.content' 2>/dev/null | base64 -d 2>/dev/null | jq -c '.paths' 2>/dev/null || echo '[]')"
scratch="$(mktemp -d)"
trap 'rm -rf "$scratch"' EXIT
{
  echo "* $(c org.maintainer)"
  jq -r '.[] | "/" + .' <<<"$paths"
} > "$scratch/CODEOWNERS"
expected=(".github/CODEOWNERS:$scratch/CODEOWNERS")
while IFS= read -r -d '' f; do
  rel="${f#"$root/consumer/"}"
  sed -e "s/__PIN__/$pin/g" "${label[@]}" "$f" | grep -v '^# Generated from ' > "$scratch/$(echo "$rel" | tr / _)"
  expected+=("$rel:$scratch/$(echo "$rel" | tr / _)")
done < <(find "$root/consumer" -type f -print0 | sort -z)
for pair in "${expected[@]}"; do
  rel="${pair%%:*}"; want="${pair#*:}"
  if have="$(api "repos/$repo/contents/$rel?ref=$default_branch" --jq '.content' 2>/dev/null | base64 -d 2>/dev/null)"; then
    diff -u --label "$rel (now)" --label "$rel (template)" <(printf '%s\n' "$have") "$want" || true
  else
    diff -u --label "$rel (missing)" --label "$rel (template)" /dev/null "$want" || true
  fi
done

echo "== 5. ruleset"
name="$(jq -r '.name' "$root/rulesets/main.json")"
id="$(api "repos/$repo/rulesets" --jq ".[] | select(.name == \"$name\") | .id" 2>/dev/null || true)"
if [ -n "$id" ]; then
  write -X PUT "repos/$repo/rulesets/$id" --input "$root/rulesets/main.json"
else
  write -X POST "repos/$repo/rulesets" --input "$root/rulesets/main.json"
  id="$(api "repos/$repo/rulesets" --jq ".[] | select(.name == \"$name\") | .id" 2>/dev/null || true)"
fi
if [ -n "$id" ] && [ "$dry" = false ]; then
  shape='{name,target,enforcement,conditions,bypass_actors,rules:(.rules|sort_by(.type))}'
  if diff <(jq -S "$shape" "$root/rulesets/main.json") <(api "repos/$repo/rulesets/$id" | jq -S "$shape") > /dev/null; then
    echo "ok: ruleset $id equals rulesets/main.json"
  else
    echo "DIFF: ruleset $id differs from rulesets/main.json"; exit 1
  fi
fi
