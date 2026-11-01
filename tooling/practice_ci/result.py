"""The shared result every command returns: a status, a reason code from a closed vocabulary, a message
for people, where the evidence is, and an optional machine payload. Decisions read status and reason;
the message is never parsed."""

import json
import re
from dataclasses import dataclass, field

PASS = "pass"
FAIL = "fail"
ERROR = "error"
STATUSES = (PASS, FAIL, ERROR)

# <source>.<code>: lower-case words joined by hyphens, for example "denylist.list-deleted".
_REASON = re.compile(r"[a-z][a-z0-9-]*\.[a-z][a-z0-9-]*")


@dataclass(frozen=True)
class Evidence:
    path: str
    line: int | None = None

    def to_json(self) -> dict:
        out = {"path": self.path}
        if self.line is not None:
            out["line"] = self.line
        return out


@dataclass(frozen=True)
class Result:
    status: str
    reason: str
    message: str
    evidence: tuple[Evidence, ...] = field(default_factory=tuple)
    detail: str = ""

    def __post_init__(self):
        if self.status not in STATUSES:
            raise ValueError("unknown status: %r" % (self.status,))
        if not _REASON.fullmatch(self.reason):
            raise ValueError("reason is not <source>.<code>: %r" % (self.reason,))

    def to_json(self) -> dict:
        return {
            "status": self.status,
            "reason": self.reason,
            "message": self.message,
            "evidence": [e.to_json() for e in self.evidence],
            "detail": self.detail,
        }

    def dumps(self) -> str:
        return json.dumps(self.to_json(), ensure_ascii=False, separators=(",", ":"))

    @classmethod
    def from_json(cls, data: dict) -> "Result":
        return cls(
            status=data["status"],
            reason=data["reason"],
            message=data["message"],
            evidence=tuple(Evidence(e["path"], e.get("line")) for e in data["evidence"]),
            detail=data["detail"],
        )
