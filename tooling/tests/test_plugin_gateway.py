"""tooling/practice_ci/plugin_gateway.py against fake plugins (#41).

A fake plugin is a real executable the gateway runs as a subprocess, so the stdin request, the stdout
envelope and the exit codes are exercised as a workflow would use them. Its behaviour, per operation and
unit, is a list of exit codes: the nth call takes the nth code, the last one repeating.
"""
import contextlib
import io
import json
import os
import stat
import sys
import tempfile
import unittest
from unittest import mock

from tooling.practice_ci import config, plugin_gateway as gw

PLUGIN_SOURCE = """#!%(python)s
import json, os, sys, time
here = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(here, "behaviour.json"), encoding="utf-8") as f:
    behaviour = json.load(f)
operation = sys.argv[1]
request = json.load(sys.stdin)
unit = request.get("unit", {}).get("id", "")
log = os.path.join(here, "calls.jsonl")
previous = 0
if os.path.exists(log):
    with open(log, encoding="utf-8") as f:
        for line in f:
            entry = json.loads(line)
            if entry["operation"] == operation and entry["unit"] == unit:
                previous += 1
with open(log, "a", encoding="utf-8") as f:
    f.write(json.dumps({"operation": operation, "unit": unit, "request": request}) + "\\n")
codes = behaviour.get("exit", {}).get(operation + ":" + unit, [0])
code = codes[min(previous, len(codes) - 1)]
if "rawBytes" in behaviour:
    sys.stdout.buffer.write(b"x" * behaviour["rawBytes"])
    sys.stdout.buffer.flush()
    time.sleep(behaviour.get("holdSeconds", 0))
    sys.exit(code)
if code != 0:
    sys.stderr.write("fake plugin exits %%d\\n" %% code)
    sys.exit(code)
if behaviour.get("garbage"):
    print("not json")
    sys.exit(0)

def answer(data):
    print(json.dumps({"ok": True, "data": data, "notRead": [], "warnings": ["x" * behaviour.get("padBytes", 0)]}))

if operation == "describe":
    answer(behaviour["describe"])
elif operation == "plan":
    answer(behaviour["plan"])
elif operation == "run-unit":
    answer({"requests": 1, "robots": {"verdict": "allowed"}, "notReached": [],
            "results": [{"fact": f, "outcome": "unchanged"} for f in request["unit"]["facts"]]})
elif operation == "merge":
    seen = set()
    for partial in request["partials"]:
        seen.update(r["fact"] for r in partial["results"])
        seen.update(partial["notReached"])
    planned = [f for u in request["plan"]["units"] for f in u["facts"]]
    answer({"partials": len(request["partials"]),
            "reached": sorted(r["fact"] for p in request["partials"] for r in p["results"]),
            "notReached": sorted(f for p in request["partials"] for f in p["notReached"]),
            "unreadable": sorted(f for f in planned if f not in seen)})
"""

PLAN = {
    "units": [
        {"id": "a", "host": "a.example.com", "facts": ["a1", "a2"]},
        {"id": "b", "host": "b.example.com", "facts": ["b1"]},
    ],
    "maxParallel": 2,
}
DESCRIBE = {"protocol": "0", "operations": ["describe", "plan", "run-unit", "merge"]}
RETRY = config.get("pluginGateway", "retry", "exitCode")


@contextlib.contextmanager
def quiet():
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        yield out, err


class Clock:
    """A clock that only the fake sleep advances, so retry timing is exact and instant."""

    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


class Fake(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = self.tmp.name
        self.plugin = os.path.join(self.dir, "plugin")
        with open(self.plugin, "w", encoding="utf-8") as f:
            f.write(PLUGIN_SOURCE % {"python": sys.executable})
        os.chmod(self.plugin, os.stat(self.plugin).st_mode | stat.S_IXUSR)
        self.behave()
        self.caps = gw.default_caps()
        self.plan_path = os.path.join(self.dir, "plan.json")
        with open(self.plan_path, "w", encoding="utf-8") as f:
            json.dump(PLAN, f)

    def behave(self, **changes):
        behaviour = {"describe": DESCRIBE, "plan": PLAN, "exit": {}}
        behaviour.update(changes)
        with open(os.path.join(self.dir, "behaviour.json"), "w", encoding="utf-8") as f:
            json.dump(behaviour, f)

    def calls(self, operation=None, unit=None):
        path = os.path.join(self.dir, "calls.jsonl")
        if not os.path.exists(path):
            return []
        with open(path, encoding="utf-8") as f:
            entries = [json.loads(line) for line in f]
        return [e for e in entries if (operation is None or e["operation"] == operation) and (unit is None or e["unit"] == unit)]

    def unit(self, unit_id, attempts=3, wait=60, clock=None, caps=None):
        clock = clock or Clock()
        with quiet():
            return gw.run_unit(self.plugin, PLAN, unit_id, caps or self.caps, attempts, wait, clock.sleep, clock), clock

    def run_cli(self, *argv, clock=None):
        clock = clock or Clock()
        with quiet() as (out, _):
            status = gw.main(list(argv), clock.sleep, clock)
        return status, out.getvalue()


class Policy(unittest.TestCase):
    def test_defaults_come_from_policy(self):
        self.assertEqual(gw.default_caps(), config.get("pluginGateway", "caps"))
        self.assertEqual(config.get("pluginGateway", "retry", "exitCode"), 75)
        self.assertEqual(config.get("pluginGateway", "maxParallel"), 3)

    def test_width_is_never_above_the_policy_cap_nor_the_plan(self):
        cap = config.get("pluginGateway", "maxParallel")
        self.assertEqual(gw.effective_max_parallel(cap + 7), cap)
        self.assertEqual(gw.effective_max_parallel(cap + 7, 2), 2)
        self.assertEqual(gw.effective_max_parallel(1, 2), 1)
        self.assertEqual(gw.effective_max_parallel(cap, 1), 1)


class PlanStep(Fake):
    def test_plan_lists_units_and_width(self):
        with quiet():
            data, ids, width = gw.plan(self.plugin, {"anything": 1}, self.caps, 10)
        self.assertEqual(ids, ["a", "b"])
        self.assertEqual(width, 2)
        self.assertEqual(data, PLAN)
        self.assertEqual([c["operation"] for c in self.calls()], ["describe", "plan"])
        self.assertEqual(self.calls("plan")[0]["request"], {"input": {"anything": 1}, "caps": self.caps})

    def test_wrong_protocol_is_refused_before_plan(self):
        self.behave(describe={"protocol": "1", "operations": DESCRIBE["operations"]})
        with quiet(), self.assertRaisesRegex(gw.GatewayError, "protocol"):
            gw.plan(self.plugin, {}, self.caps, 3)
        self.assertEqual(self.calls("plan"), [])

    def test_an_unlisted_operation_is_refused(self):
        self.behave(describe={"protocol": "0", "operations": ["describe", "plan", "run-unit"]})
        with quiet(), self.assertRaisesRegex(gw.GatewayError, "merge"):
            gw.plan(self.plugin, {}, self.caps, 3)

    def test_unsafe_and_repeated_unit_ids_are_refused(self):
        for units in ([{"id": "../x", "host": "h", "facts": []}], [{"id": "a", "host": "h", "facts": []}] * 2):
            self.behave(plan={"units": units})
            with quiet(), self.assertRaises(gw.GatewayError):
                gw.plan(self.plugin, {}, self.caps, 3)

    def test_a_plan_with_no_units_is_a_plan(self):
        self.behave(plan={"units": []})
        with quiet():
            _, ids, _ = gw.plan(self.plugin, {}, self.caps, 3)
        self.assertEqual(ids, [])

    def test_a_missing_plugin_is_a_setup_error(self):
        with quiet(), self.assertRaisesRegex(gw.GatewayError, "cannot run"):
            gw.describe(os.path.join(self.dir, "absent"), self.caps)


class OutputCap(Fake):
    def test_overflow_is_fatal_on_success_retry_and_fatal_exits(self):
        for code in (0, RETRY, 2):
            with self.subTest(code=code):
                self.behave(rawBytes=101, exit={"run-unit:a": [code]})
                outcome, clock = self.unit("a", caps={**self.caps, "outputBytes": 100})
                self.assertEqual(outcome["state"], "fatal")
                self.assertIn("output cap", outcome["reason"])
                self.assertEqual(outcome["attempts"], 1)
                self.assertEqual(clock.sleeps, [])

    def test_overflow_is_detected_before_the_plugin_exits(self):
        self.behave(rawBytes=101, holdSeconds=10)
        with quiet():
            result = gw.call(self.plugin, "run-unit", {}, {"outputBytes": 100, "timeSeconds": 1})
        self.assertIn("output cap", result.problem)

    def test_exact_cap_on_retry_is_allowed(self):
        self.behave(rawBytes=100, exit={"run-unit:": [RETRY]})
        with quiet():
            result = gw.call(self.plugin, "run-unit", {}, {**self.caps, "outputBytes": 100})
        self.assertEqual(result, gw.Call(RETRY, None, None))

    def test_timeout_still_applies_while_reading(self):
        self.behave(rawBytes=1, holdSeconds=10)
        with quiet():
            result = gw.call(self.plugin, "run-unit", {}, {"outputBytes": 100, "timeSeconds": 0.1})
        self.assertIn("time cap", result.problem)


class UnitStep(Fake):
    def test_success_runs_once_with_only_the_units_host(self):
        outcome, clock = self.unit("a")
        self.assertEqual(outcome["state"], "ok")
        self.assertEqual(outcome["attempts"], 1)
        self.assertEqual([r["fact"] for r in outcome["partial"]["results"]], ["a1", "a2"])
        self.assertEqual(clock.sleeps, [])
        request = self.calls("run-unit", "a")[0]["request"]
        self.assertEqual(request["network"], {"hosts": ["a.example.com"]})
        self.assertEqual(request["caps"], self.caps)

    def test_75_then_success_waits_once_and_reports_the_real_partial(self):
        self.behave(exit={"run-unit:a": [RETRY, 0]})
        outcome, clock = self.unit("a", attempts=3, wait=7)
        self.assertEqual(outcome["state"], "ok")
        self.assertEqual(outcome["attempts"], 2)
        self.assertEqual(clock.sleeps, [7])
        self.assertEqual(len(self.calls("run-unit", "a")), 2)
        self.assertEqual(outcome["partial"]["notReached"], [])

    def test_persistent_75_leaves_every_fact_unreached_after_the_attempts(self):
        self.behave(exit={"run-unit:a": [RETRY]})
        outcome, clock = self.unit("a", attempts=3, wait=7)
        self.assertEqual(outcome["state"], "unreached")
        self.assertEqual(outcome["attempts"], 3)
        self.assertEqual(len(self.calls("run-unit", "a")), 3)
        self.assertEqual(clock.sleeps, [7, 7])
        self.assertEqual(outcome["partial"], {"requests": 3, "robots": None, "results": [], "notReached": ["a1", "a2"]})

    def test_one_attempt_means_no_retry(self):
        self.behave(exit={"run-unit:a": [RETRY, 0]})
        outcome, clock = self.unit("a", attempts=1)
        self.assertEqual(outcome["state"], "unreached")
        self.assertEqual(clock.sleeps, [])

    def test_fatal_exit_is_not_retried_and_has_no_partial(self):
        for code in (1, 2, 3):
            with self.subTest(code):
                self.behave(exit={"run-unit:a": [code]})
                before = len(self.calls("run-unit", "a"))
                outcome, clock = self.unit("a")
                self.assertEqual(outcome["state"], "fatal")
                self.assertIsNone(outcome["partial"])
                self.assertIn(str(code), outcome["reason"])
                self.assertEqual(len(self.calls("run-unit", "a")) - before, 1)
                self.assertEqual(clock.sleeps, [])

    def test_a_retry_never_starts_past_the_time_cap(self):
        self.behave(exit={"run-unit:a": [RETRY]})
        caps = {**self.caps, "timeSeconds": 100}
        outcome, clock = self.unit("a", attempts=9, wait=60, caps=caps)
        self.assertEqual(outcome["state"], "unreached")
        self.assertEqual(outcome["attempts"], 2)
        self.assertEqual(clock.sleeps, [60])
        self.assertIn("time cap", outcome["reason"])

    def test_output_over_the_cap_is_fatal(self):
        self.behave(padBytes=500)
        outcome, _ = self.unit("a", caps={**self.caps, "outputBytes": 200})
        self.assertEqual(outcome["state"], "fatal")
        self.assertIn("output cap", outcome["reason"])

    def test_an_answer_that_is_not_an_envelope_is_fatal(self):
        self.behave(garbage=True)
        outcome, _ = self.unit("a")
        self.assertEqual(outcome["state"], "fatal")
        self.assertIsNone(outcome["partial"])

    def test_a_unit_outside_the_plan_is_refused(self):
        with quiet(), self.assertRaises(gw.GatewayError):
            gw.run_unit(self.plugin, PLAN, "zzz", self.caps, 3, 0)


class MergeStep(Fake):
    def write_partial(self, unit_id, partial):
        os.makedirs(os.path.join(self.dir, "partials"), exist_ok=True)
        with open(os.path.join(self.dir, "partials", unit_id + ".json"), "w", encoding="utf-8") as f:
            json.dump(partial, f)

    def merge(self):
        with quiet():
            return gw.merge(self.plugin, PLAN, os.path.join(self.dir, "partials"), self.caps)

    def test_every_partial_present(self):
        for unit_id in ("a", "b"):
            self.write_partial(unit_id, self.unit(unit_id)[0]["partial"])
        report, missing = self.merge()
        self.assertEqual(missing, [])
        self.assertEqual(report["partials"], 2)
        self.assertEqual(report["unreadable"], [])

    def test_a_missing_partial_is_merged_around_and_its_facts_are_unreadable(self):
        self.write_partial("a", self.unit("a")[0]["partial"])
        report, missing = self.merge()
        self.assertEqual(missing, ["b"])
        self.assertEqual(report["partials"], 1)
        self.assertEqual(report["reached"], ["a1", "a2"])
        self.assertEqual(report["unreadable"], ["b1"])

    def test_no_partials_at_all_still_merges(self):
        report, missing = self.merge()
        self.assertEqual(missing, ["a", "b"])
        self.assertEqual(report["unreadable"], ["a1", "a2", "b1"])

    def test_an_unreached_partial_is_not_unreadable(self):
        self.write_partial("a", self.unit("a")[0]["partial"])
        self.write_partial("b", gw.unreached_partial(PLAN["units"][1], 3))
        report, missing = self.merge()
        self.assertEqual(missing, [])
        self.assertEqual(report["notReached"], ["b1"])
        self.assertEqual(report["unreadable"], [])

    def test_a_partial_for_an_unknown_unit_is_refused(self):
        self.write_partial("zzz", {})
        with quiet(), self.assertRaisesRegex(gw.GatewayError, "not in the plan"):
            gw.merge(self.plugin, PLAN, os.path.join(self.dir, "partials"), self.caps)

    def test_a_failing_merge_fails_the_step(self):
        self.behave(exit={"merge:": [2]})
        with quiet(), self.assertRaisesRegex(gw.GatewayError, "exited 2"):
            gw.merge(self.plugin, PLAN, os.path.join(self.dir, "partials"), self.caps)


class Cli(Fake):
    def common(self, step):
        return [step, "--plugin", self.plugin]

    def unit_args(self, unit_id, **extra):
        argv = self.common("unit") + ["--plan", self.plan_path, "--unit", unit_id, "--out-dir", os.path.join(self.dir, "partials")]
        for key, value in extra.items():
            argv += ["--" + key.replace("_", "-"), str(value)]
        return argv

    def merge_args(self):
        return self.common("merge") + [
            "--plan", self.plan_path,
            "--partials-dir", os.path.join(self.dir, "partials"),
            "--out", os.path.join(self.dir, "report.json"),
        ]

    def report(self):
        with open(os.path.join(self.dir, "report.json"), encoding="utf-8") as f:
            return json.load(f)

    def test_plan_writes_the_plan_and_the_matrix_outputs(self):
        outputs = os.path.join(self.dir, "github-output")
        plan_input = os.path.join(self.dir, "plan-input.json")
        with open(plan_input, "w", encoding="utf-8") as f:
            json.dump({"x": 1}, f)
        out = os.path.join(self.dir, "out", "plan.json")
        with mock.patch.dict(os.environ, {gw.OUTPUT_ENV: outputs}):
            status, _ = self.run_cli(*self.common("plan"), "--plan-input", plan_input, "--out", out, "--max-parallel", "9")
        self.assertEqual(status, 0)
        with open(out, encoding="utf-8") as f:
            self.assertEqual(json.load(f), PLAN)
        with open(outputs, encoding="utf-8") as f:
            lines = f.read().splitlines()
        self.assertEqual(lines, ['units=["a","b"]', "has-units=true", "max-parallel=2"])

    def test_merge_runs_after_a_unit_failed(self):
        self.behave(exit={"run-unit:b": [2]})
        self.assertEqual(self.run_cli(*self.unit_args("a"))[0], 0)
        status, out = self.run_cli(*self.unit_args("b"))
        self.assertEqual(status, 1)
        self.assertIn("::warning::unit b", out)
        self.assertFalse(os.path.exists(os.path.join(self.dir, "partials", "b.json")))
        outputs = os.path.join(self.dir, "github-output")
        with mock.patch.dict(os.environ, {gw.OUTPUT_ENV: outputs}):
            status, out = self.run_cli(*self.merge_args())
        self.assertEqual(status, 0)
        self.assertIn("::warning::unit b has no partial", out)
        self.assertEqual(self.report()["unreadable"], ["b1"])
        with open(outputs, encoding="utf-8") as f:
            lines = f.read().splitlines()
        self.assertEqual(lines, ["report-artifact=" + config.get("pluginGateway", "artifacts", "report"), 'missing=["b"]'])

    def test_persistent_75_is_a_partial_not_a_failure(self):
        self.behave(exit={"run-unit:b": [RETRY]})
        self.assertEqual(self.run_cli(*self.unit_args("a"))[0], 0)
        status, out = self.run_cli(*self.unit_args("b", retry_attempts=2, retry_wait_seconds=0))
        self.assertEqual(status, 0)
        self.assertIn("::warning::unit b", out)
        self.assertEqual(len(self.calls("run-unit", "b")), 2)
        self.assertEqual(self.run_cli(*self.merge_args())[0], 0)
        self.assertEqual(self.report()["notReached"], ["b1"])
        self.assertEqual(self.report()["unreadable"], [])

    def test_75_then_success_through_the_cli(self):
        self.behave(exit={"run-unit:a": [RETRY, 0]})
        clock = Clock()
        status, _ = self.run_cli(*self.unit_args("a", retry_wait_seconds=11), clock=clock)
        self.assertEqual(status, 0)
        self.assertEqual(clock.sleeps, [11])
        with open(os.path.join(self.dir, "partials", "a.json"), encoding="utf-8") as f:
            self.assertEqual(len(json.load(f)["results"]), 2)

    def test_a_failing_describe_ends_plan_with_an_error_annotation(self):
        self.behave(describe={"protocol": "9", "operations": []})
        plan_input = os.path.join(self.dir, "plan-input.json")
        with open(plan_input, "w", encoding="utf-8") as f:
            json.dump({}, f)
        status, out = self.run_cli(*self.common("plan"), "--plan-input", plan_input, "--out", os.path.join(self.dir, "plan.json"))
        self.assertEqual(status, 1)
        self.assertIn("::error::describe", out)

    def run_args(self, **extra):
        plan_input = os.path.join(self.dir, "plan-input.json")
        with open(plan_input, "w", encoding="utf-8") as f:
            json.dump({"x": 1}, f)
        argv = self.common("run") + ["--plan-input", plan_input, "--out", os.path.join(self.dir, "report.json")]
        for key, value in extra.items():
            argv += ["--" + key.replace("_", "-"), str(value)]
        return argv

    def run_step(self, *argv, clock=None):
        outputs = os.path.join(self.dir, "github-output")
        with mock.patch.dict(os.environ, {gw.OUTPUT_ENV: outputs}):
            status, out = self.run_cli(*argv, clock=clock)
        lines = []
        if os.path.exists(outputs):
            with open(outputs, encoding="utf-8") as f:
                lines = f.read().splitlines()
        return status, out, lines

    def test_run_plans_runs_every_unit_and_merges(self):
        status, _, lines = self.run_step(*self.run_args())
        self.assertEqual(status, 0)
        self.assertEqual([c["operation"] for c in self.calls()].count("run-unit"), 2)
        self.assertEqual(len(self.calls("run-unit", "a")), 1)
        self.assertEqual(len(self.calls("run-unit", "b")), 1)
        report = self.report()
        self.assertEqual(report["partials"], 2)
        self.assertEqual(report["reached"], ["a1", "a2", "b1"])
        self.assertEqual(report["unreadable"], [])
        # The report output is one compact line, so it works as a step output.
        self.assertEqual(lines, ["report=" + json.dumps(report, separators=(",", ":"))])

    def test_run_width_is_the_least_of_input_plan_and_policy(self):
        for requested, want in (("9", 2), ("1", 1)):
            with self.subTest(requested):
                with mock.patch.object(gw, "ThreadPoolExecutor", wraps=gw.ThreadPoolExecutor) as pool:
                    self.run_step(*self.run_args(max_parallel=requested))
                self.assertEqual(pool.call_args.kwargs["max_workers"], want)

    def test_run_with_no_units_merges_nothing(self):
        self.behave(plan={"units": []})
        status, _, lines = self.run_step(*self.run_args())
        self.assertEqual(status, 0)
        self.assertEqual(self.calls("run-unit"), [])
        self.assertEqual(self.report()["partials"], 0)
        self.assertEqual(len(lines), 1)

    def test_run_a_fatal_unit_is_merged_around_warned_and_fails_the_step(self):
        self.behave(exit={"run-unit:b": [2]})
        status, out, lines = self.run_step(*self.run_args())
        self.assertEqual(status, 1)
        self.assertIn("::warning::unit b", out)
        self.assertNotIn("::warning::unit a", out)
        report = self.report()
        self.assertEqual(report["partials"], 1)
        self.assertEqual(report["reached"], ["a1", "a2"])
        self.assertEqual(report["unreadable"], ["b1"])
        self.assertEqual(len(lines), 1)
        self.assertTrue(lines[0].startswith("report="))

    def test_run_a_persistent_75_is_a_partial_not_a_failure(self):
        self.behave(exit={"run-unit:b": [RETRY]})
        status, out, _ = self.run_step(*self.run_args(retry_attempts=2, retry_wait_seconds=0))
        self.assertEqual(status, 0)
        self.assertEqual(len(self.calls("run-unit", "b")), 2)
        self.assertEqual(self.report()["notReached"], ["b1"])
        self.assertEqual(self.report()["unreadable"], [])

    def test_run_a_failing_merge_fails_the_step_without_a_report(self):
        self.behave(exit={"merge:": [2]})
        status, out, lines = self.run_step(*self.run_args())
        self.assertEqual(status, 1)
        self.assertIn("::error::merge", out)
        self.assertEqual(lines, [])
        self.assertFalse(os.path.exists(os.path.join(self.dir, "report.json")))

    def test_bad_arguments_exit_two(self):
        for argv in (["unit"], self.unit_args("a", retry_attempts=0), self.unit_args("a", time_seconds=0)):
            with self.subTest(argv):
                with quiet(), self.assertRaises(SystemExit) as stop:
                    gw.main(argv)
                self.assertEqual(stop.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
