"""The one place a Result becomes workflow output and an exit status.

Exit status: 0 pass, 1 fail, 2 error (the command could not judge). With keep_going a fail exits 0 so
the calling step can branch on the reason it reads from the result file; an error never does.
"""

import sys

from .result import ERROR, FAIL, PASS, Result

EXIT = {PASS: 0, FAIL: 1, ERROR: 2}


def _data(text: str) -> str:
    return text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def _prop(text: str) -> str:
    return _data(text).replace(":", "%3A").replace(",", "%2C")


def annotations(result: Result) -> list[str]:
    """GitHub workflow commands for a result that is not a pass: one per evidence location."""
    if result.status == PASS:
        return []
    text = _data("%s (%s)" % (result.message, result.reason))
    if not result.evidence:
        return ["::error::" + text]
    out = []
    for e in result.evidence:
        where = "file=" + _prop(e.path)
        if e.line is not None:
            where += ",line=%d" % e.line
        out.append("::error %s::%s" % (where, text))
    return out


def emit(result: Result, out=None, result_file: str | None = None, keep_going: bool = False) -> int:
    out = out or sys.stdout
    print(result.message, file=out)
    for line in annotations(result) if not (keep_going and result.status == FAIL) else []:
        print(line, file=out)
    if result_file:
        with open(result_file, "w", encoding="utf-8") as f:
            f.write(result.dumps() + "\n")
    if keep_going and result.status == FAIL:
        return EXIT[PASS]
    return EXIT[result.status]
