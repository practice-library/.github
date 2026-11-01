"""Brings a repository of the organisation to the defaults in docs/new-repo-checklist.md.

The work is two phases. build_plan() reads (never writes), renders and validates every file, and
returns a Plan; only when that succeeds does apply() make the API writes. A failure while planning
therefore makes zero writes.

  steps 1, 2 and 5 (security settings, the label, merge settings, the ruleset) are applied through the API;
  step 4 (files) is printed as a diff against the consumer templates, for a pull request;
  step 3 (team access) needs an organisation owner and is only checked.

Usage: PIN=<sha> python3 -m practice_ci.onboarding [--dry-run] <repo>   (scripts/onboard.sh wraps it)
  GH   the command used for API calls (default policy onboarding.ghCommand)
  PIN  required: the full commit of this repository the callers pin
  REF  the label written after the pin; default the release tag (release.tag), and only when that tag
       exists and points at PIN; otherwise no label is written
"""
import base64
import difflib
import json
import os
import re
import shlex
import subprocess
import sys

from . import config

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

MERGE_FIELDS = {"merge": "allow_merge_commit", "squash": "allow_squash_merge", "rebase": "allow_rebase_merge"}
SECURITY_FIELDS = (
    "security_and_analysis[secret_scanning][status]=enabled",
    "security_and_analysis[secret_scanning_push_protection][status]=enabled",
)
RULESET_SHAPE_KEYS = ("name", "target", "enforcement", "conditions", "bypass_actors", "rules")


class OnboardError(Exception):
    """Something that makes the plan unusable; nothing has been written."""


class Gh:
    """Runs `<gh command> api ...`. read() never writes; write() is the only method that can."""

    def __init__(self, command=None, runner=subprocess.run):
        self.command = shlex.split(command or config.get("onboarding", "ghCommand"))
        self._runner = runner

    def read(self, endpoint):
        done = self._runner([*self.command, "api", endpoint], capture_output=True, text=True)
        return done.stdout if done.returncode == 0 else None

    def write(self, method, endpoint, fields=(), body=None):
        args = [*self.command, "api", "-X", method, endpoint]
        for flag, value in fields:
            args += [flag, value]
        if body is not None:
            args += ["--input", "-"]
        done = self._runner(args, input=body, capture_output=True, text=True)
        if done.returncode != 0:
            raise OnboardError(f"api {method} {endpoint} failed: {done.stderr.strip()}")


class Write:
    def __init__(self, method, endpoint, fields=(), body=None):
        self.method, self.endpoint, self.fields, self.body = method, endpoint, tuple(fields), body

    def describe(self):
        return " ".join(["+ api", "-X", self.method, self.endpoint, *[f"{f} {v}" for f, v in self.fields]]
                        + (["--input -"] if self.body is not None else []))


class Plan:
    def __init__(self, repo, ruleset_name, ruleset_text):
        self.repo, self.ruleset_name, self.ruleset_text = repo, ruleset_name, ruleset_text
        self.lines = []
        self.writes = []

    def say(self, text):
        self.lines.append(text)

    def add(self, write):
        self.writes.append(write)
        self.lines.append(write.describe())


def parse_repo(arg):
    org = config.get("org", "name")
    parts = arg.split("/")
    if len(parts) > 2:
        raise OnboardError(f"<repo> must be <name> or <owner>/<name>, got '{arg}'")
    owner, name = (org, parts[0]) if len(parts) == 1 else parts
    if owner != org:
        raise OnboardError(f"<repo> must belong to {org}, got owner '{owner}'")
    if not re.fullmatch(config.get("onboarding", "repoNamePattern"), name) or name in (".", ".."):
        raise OnboardError(f"'{name}' is not a repository name")
    return f"{org}/{name}"


def _json_read(gh, endpoint):
    text = gh.read(endpoint)
    return None if text is None else json.loads(text)


def _commit_sha(gh, repo, ref):
    try:
        data = _json_read(gh, f"repos/{repo}/commits/{ref}")
    except ValueError:
        return ""
    return data.get("sha", "") if isinstance(data, dict) else ""


def _file_text(gh, repo, path, branch):
    try:
        data = _json_read(gh, f"repos/{repo}/contents/{path}?ref={branch}")
        return base64.b64decode(data["content"]).decode("utf-8")
    except (ValueError, KeyError, TypeError):
        return None


def resolve_ref(gh, pin, ref_env, plan):
    """The label written after the pin, or "" for none."""
    if ref_env:
        if not re.fullmatch(config.get("onboarding", "refPattern"), ref_env):
            raise OnboardError(f"REF may hold only letters, digits, '.', '_' and '-', got '{ref_env}'")
        return ref_env
    tag = config.get("release", "tag")
    tag_sha = _commit_sha(gh, f"{config.get('org', 'name')}/{config.get('org', 'repo')}", tag)
    if tag_sha == pin:
        return tag
    why = f"points at {tag_sha}, not PIN" if tag_sha else "does not exist"
    plan.say(f"note: tag {tag} {why}; writing no label after the pin")
    return ""


def render_consumer_file(text, rel, pin, ref):
    """One consumer template with the pin and label filled in and its generated header dropped."""
    cfg = config.get("onboarding")
    out = text.replace(cfg["pinPlaceholder"], pin)
    if ref:
        out = out.replace(cfg["refPlaceholder"], ref)
    else:
        out = out.replace(cfg["refComment"], "")
    out = "".join(line for line in out.splitlines(keepends=True) if not line.startswith(cfg["generatedHeaderPrefix"]))
    if cfg["refPlaceholder"] in out or cfg["pinPlaceholder"] in out:
        raise OnboardError(f"{rel}: a placeholder is left after rendering")
    uses = re.compile(cfg["usesPattern"].format(org=re.escape(config.get("org", "name")),
                                                repo=re.escape(config.get("org", "repo"))))
    for found in uses.finditer(out):
        if found.group(1) != pin:
            raise OnboardError(f"{rel}: a uses: is pinned to '{found.group(1)}', not to PIN")
    return out


def render_files(root, gh, repo, pin, ref):
    """Every file the repository should hold, as {path: text}; raises OnboardError when any cannot be made."""
    cfg = config.get("onboarding")
    branch = config.get("org", "defaultBranch")
    maintainer = config.get("org", "maintainer")
    paths = []
    text = _file_text(gh, repo, config.get("automerge", "pathsFile"), branch)
    if text is not None:
        try:
            paths = json.loads(text)["paths"]
            if not isinstance(paths, list) or not all(isinstance(p, str) for p in paths):
                raise TypeError
        except (ValueError, KeyError, TypeError):
            raise OnboardError(f"{config.get('automerge', 'pathsFile')} on {branch} is not {{\"paths\": [...]}}") from None
    files = {cfg["codeownersPath"]: "\n".join([f"* {maintainer}", *[f"/{p}" for p in paths]]) + "\n"}
    base = os.path.join(root, cfg["consumerDir"])
    for dirpath, _, names in sorted(os.walk(base)):
        for name in sorted(names):
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, base).replace(os.sep, "/")
            try:
                with open(full, encoding="utf-8") as f:
                    source = f.read()
            except (OSError, UnicodeDecodeError) as err:
                raise OnboardError(f"{rel}: cannot read the template: {err}") from None
            files[rel] = render_consumer_file(source, rel, pin, ref)
    return files


def read_ruleset(root):
    path = os.path.join(root, config.get("onboarding", "rulesetFile"))
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
        name = json.loads(text)["name"]
    except (OSError, ValueError, KeyError, TypeError) as err:
        raise OnboardError(f"{path}: not a usable ruleset: {err}") from None
    return name, text


def build_plan(repo, pin, ref_env, gh, root=ROOT):
    """Reads and renders everything; makes no write. Raises OnboardError when anything is wrong."""
    cfg = config.get("onboarding")
    org = config.get("org", "name")
    branch = config.get("org", "defaultBranch")
    if not re.fullmatch(cfg["pinPattern"], pin or ""):
        raise OnboardError(f"PIN must be a full 40-hex commit sha, got '{pin}'")
    self_repo = f"{org}/{config.get('org', 'repo')}"
    if _commit_sha(gh, self_repo, pin) != pin:
        raise OnboardError(f"PIN {pin} is not a commit of {self_repo}")
    ruleset_name, ruleset_text = read_ruleset(root)
    plan = Plan(repo, ruleset_name, ruleset_text)
    ref = resolve_ref(gh, pin, ref_env, plan)
    files = render_files(root, gh, repo, pin, ref)  # every file is rendered and validated before any write

    plan.say(f"== 1. security settings: {repo}")
    plan.add(Write("PUT", f"repos/{repo}/private-vulnerability-reporting"))
    plan.add(Write("PATCH", f"repos/{repo}", [("-f", v) for v in SECURITY_FIELDS]))
    plan.add(Write("PUT", f"repos/{repo}/vulnerability-alerts"))
    label_name = config.get("guards", "loosenLabel")
    if gh.read(f"repos/{repo}/labels/{label_name}") is not None:
        plan.say(f"ok: label {label_name} exists")
    else:
        plan.add(Write("POST", f"repos/{repo}/labels", [
            ("-f", f"name={label_name}"),
            ("-f", f"color={cfg['label']['color']}"),
            ("-f", f"description={cfg['label']['description']}")]))

    plan.say("== 2. merge settings")
    allowed = config.get("ruleset", "allowedMergeMethods")
    fields = [("-F", "allow_auto_merge=true")]
    fields += [("-F", f"{MERGE_FIELDS[m]}={'true' if m in allowed else 'false'}") for m in MERGE_FIELDS]
    plan.add(Write("PATCH", f"repos/{repo}", fields))

    plan.say("== 3. maintainers (an organisation owner grants this by hand)")
    maintainer = config.get("org", "maintainer")
    slug = maintainer.split("/", 1)[-1]
    permission = ""
    try:
        for team in _json_read(gh, f"repos/{repo}/teams") or []:
            if team.get("slug") == slug:
                permission = team.get("permission", "")
    except (ValueError, AttributeError):
        pass
    if permission in cfg["maintainerPermissions"]:
        plan.say(f"ok: {maintainer} has {permission}")
    else:
        plan.say(f"TODO: give {maintainer} Write access to {repo} (currently: {permission or 'none'})")

    plan.say(f"== 4. files (diff of the repository's {branch} against the templates; open a pull request with these)")
    for rel, want in files.items():
        have = _file_text(gh, repo, rel, branch)
        label = (f"{rel} (now)", f"{rel} (template)") if have is not None else (f"{rel} (missing)", f"{rel} (template)")
        diff = difflib.unified_diff((have or "").splitlines(keepends=True), want.splitlines(keepends=True),
                                    fromfile=label[0], tofile=label[1])
        plan.say("".join(diff).rstrip("\n"))

    plan.say("== 5. ruleset")
    rulesets = _json_read(gh, f"repos/{repo}/rulesets") or []
    existing = [r["id"] for r in rulesets if r.get("name") == ruleset_name]
    if existing:
        plan.add(Write("PUT", f"repos/{repo}/rulesets/{existing[0]}", body=ruleset_text))
    else:
        plan.add(Write("POST", f"repos/{repo}/rulesets", body=ruleset_text))
    return plan


def _shape(ruleset):
    shaped = {k: ruleset.get(k) for k in RULESET_SHAPE_KEYS}
    shaped["rules"] = sorted(shaped["rules"] or [], key=lambda r: r.get("type", ""))
    return json.dumps(shaped, sort_keys=True)


def apply(plan, gh):
    """Makes the writes of a finished plan, then checks the ruleset. Returns the exit status."""
    for write in plan.writes:
        gh.write(write.method, write.endpoint, write.fields, write.body)
    found = [r["id"] for r in _json_read(gh, f"repos/{plan.repo}/rulesets") or [] if r.get("name") == plan.ruleset_name]
    if not found:
        print(f"DIFF: no ruleset named {plan.ruleset_name} after the write")
        return 1
    live = _json_read(gh, f"repos/{plan.repo}/rulesets/{found[0]}")
    if _shape(live) == _shape(json.loads(plan.ruleset_text)):
        print(f"ok: ruleset {found[0]} equals {config.get('onboarding', 'rulesetFile')}")
        return 0
    print(f"DIFF: ruleset {found[0]} differs from {config.get('onboarding', 'rulesetFile')}")
    return 1


def main(argv=None, env=None, gh=None, root=ROOT):
    argv = list(sys.argv[1:] if argv is None else argv)
    env = os.environ if env is None else env
    dry = bool(argv) and argv[0] == "--dry-run"
    if dry:
        argv.pop(0)
    if len(argv) != 1:
        print("usage: PIN=<40-hex sha> onboard.sh [--dry-run] <repo>", file=sys.stderr)
        return 2
    gh = gh or Gh(env.get("GH"))
    try:
        plan = build_plan(parse_repo(argv[0]), env.get("PIN", ""), env.get("REF", ""), gh, root)
    except (OnboardError, ValueError) as err:
        print(f"error: {err}", file=sys.stderr)
        return 2
    print("\n".join(plan.lines))
    if dry:
        return 0
    try:
        return apply(plan, gh)
    except (OnboardError, ValueError) as err:
        print(f"error: {err}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
