"""One JSON result per check, and the exit code it maps to."""
import json
from dataclasses import dataclass, field

from practice_ci import config


@dataclass
class Result:
    ok: bool
    check: str
    reasons: list = field(default_factory=list)
    evidence: list = field(default_factory=list)
    # Not part of the JSON: a result that is an error of use (or of the tool), not a verdict on the input.
    errored: bool = field(default=False, compare=False)

    def to_dict(self):
        return {"ok": self.ok, "check": self.check, "reasons": list(self.reasons), "evidence": list(self.evidence)}

    def to_json(self):
        return json.dumps(self.to_dict(), sort_keys=False)

    def exit_code(self, path=None):
        codes = config.get("tooling", "exitCodes", path=path)
        if self.errored:
            return codes["error"]
        return codes["pass"] if self.ok else codes["fail"]


def passed(check, evidence=()):
    return Result(True, check, [], list(evidence))


def failed(check, reasons, evidence=()):
    return Result(False, check, list(reasons), list(evidence))


def error(check, reason):
    return Result(False, check, [reason], [], errored=True)
