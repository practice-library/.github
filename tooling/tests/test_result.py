"""The shared result and the one adapter that turns it into workflow output and an exit status."""

import io
import json
import os
import tempfile
import unittest

from practice_ci import adapter
from practice_ci.result import ERROR, FAIL, PASS, Evidence, Result


class Results(unittest.TestCase):
    def test_status_is_a_closed_set(self):
        with self.assertRaises(ValueError):
            Result("ok", "x.y", "m")

    def test_reason_is_source_dot_code(self):
        for bad in ("ok", "x.", ".y", "X.y", "x.y z", "x.y.z", "x.y\n"):
            with self.assertRaises(ValueError, msg=bad):
                Result(PASS, bad, "m")
        Result(PASS, "denylist.list-deleted", "m")

    def test_round_trip(self):
        r = Result(FAIL, "a.b", "msg", (Evidence("p", 3), Evidence("q")), "detail")
        self.assertEqual(Result.from_json(json.loads(r.dumps())), r)


class Adapter(unittest.TestCase):
    def emit(self, result, **kw):
        out = io.StringIO()
        return adapter.emit(result, out=out, **kw), out.getvalue()

    def test_exit_status_per_status(self):
        self.assertEqual(self.emit(Result(PASS, "a.b", "m"))[0], 0)
        self.assertEqual(self.emit(Result(FAIL, "a.b", "m"))[0], 1)
        self.assertEqual(self.emit(Result(ERROR, "a.b", "m"))[0], 2)

    def test_keep_going_passes_a_fail_on_but_never_an_error(self):
        self.assertEqual(self.emit(Result(FAIL, "a.b", "m"), keep_going=True)[0], 0)
        self.assertEqual(self.emit(Result(ERROR, "a.b", "m"), keep_going=True)[0], 2)

    def test_a_fail_is_annotated_at_each_evidence(self):
        code, out = self.emit(Result(FAIL, "a.b", "50% bad\nline", (Evidence("x,y:z", 4),)))
        self.assertIn("::error file=x%2Cy%3Az,line=4::50%25 bad%0Aline (a.b)", out)

    def test_a_pass_is_not_annotated(self):
        self.assertNotIn("::error", self.emit(Result(PASS, "a.b", "m"))[1])

    def test_result_file(self):
        fd, path = tempfile.mkstemp()
        os.close(fd)
        try:
            self.emit(Result(FAIL, "a.b", "m", detail="[1]"), result_file=path, keep_going=True)
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            self.assertEqual((data["status"], data["reason"], data["detail"]), (FAIL, "a.b", "[1]"))
        finally:
            os.unlink(path)


if __name__ == "__main__":
    unittest.main()
