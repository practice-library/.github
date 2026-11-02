# main: judges one changed JSON file by running the compatibility classifier
# (@@tooling.dir@@/@@tooling.package@@/compatibility.py, which holds every rule). OLD_FILE is the file on the
# base commit; NEW_FILE the file on the head, or empty when the change deleted it; FILE_PATH its path in the
# repository (a check profile, @@compatibility.checkFile@@, is judged by its own rule); TIGHTEN, when set, the
# reviewed list of pattern pairs that only tighten (unset means no list). Prints one line:
#   "ok nothing loosened"              proven safe
#   "ok nothing loosened; listed tightenings [<path>, ...]"
#   "loose [<path>, ...]"              requires review ("(deleted)" when a schema was deleted)
#   "invalid ..."                      an input cannot be read
#   "skip ..."                         the file is not a JSON schema (its top-level $schema does not name a
#                                      json-schema.org meta-schema, as an instance pointing at its schema does not)
# PRACTICE_CI_DIR names the directory that holds the package (default: @@tooling.dir@@, relative to the
# working directory).
main() {
  local args=(--old "${OLD_FILE:-}" --new "${NEW_FILE:-}" --name "${FILE_PATH:-}")
  [ -z "${TIGHTEN+x}" ] || args+=(--tighten "$TIGHTEN")
  PYTHONPATH="${PRACTICE_CI_DIR:-@@tooling.dir@@}" python3 -P -m @@tooling.package@@.compatibility "${args[@]}"
}
