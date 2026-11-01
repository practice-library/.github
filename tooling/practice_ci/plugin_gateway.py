"""Helpers of the plugin-matrix reusable workflow: run a contract v0 plugin as plan, units, merge.

A plugin is an executable. It is called as `plugin <operation>` with one JSON request on stdin and answers
with one envelope `{"ok", "data", "notRead", "warnings"}` on stdout. Exit 0 is success, 75 (policy:
pluginGateway.retry.exitCode) is a temporary failure the caller may retry, anything else is fatal.
Every limit, name and default is in policy/constants.json under pluginGateway.

    python3 -m tooling.practice_ci.plugin_gateway plan  --plugin P --plan-input F --out plan.json
    python3 -m tooling.practice_ci.plugin_gateway unit  --plugin P --plan plan.json --unit ID --out-dir DIR
    python3 -m tooling.practice_ci.plugin_gateway merge --plugin P --plan plan.json --partials-dir DIR --out report.json

Exit status: 0 on success, 1 when the step failed (a warning or error annotation says why), 2 on bad arguments.
"""
import argparse
import collections
import json
import io
import os
import re
import selectors
import select
import subprocess
import sys
import time

from tooling.practice_ci import config

EXIT_OK, EXIT_FAILED = 0, 1
OUTPUT_ENV = "GITHUB_OUTPUT"

Call = collections.namedtuple("Call", "code envelope problem")


class GatewayError(Exception):
    """A step that cannot go on: the plugin does not meet the contract, or the plan is not usable."""


def _policy(*keys):
    return config.get("pluginGateway", *keys)


def default_caps():
    return {"timeSeconds": _policy("caps", "timeSeconds"), "outputBytes": _policy("caps", "outputBytes")}


def effective_max_parallel(requested, plan_value=None):
    """The matrix width: the input, the plan's own request and the policy cap, whichever is least, and at least 1."""
    limits = [requested, _policy("maxParallel")]
    if plan_value is not None:
        limits.append(plan_value)
    return max(1, min(limits))


def _envelope_problem(envelope):
    if not isinstance(envelope, dict):
        return "the answer is not a JSON object"
    for key in ("ok", "data", "notRead", "warnings"):
        if key not in envelope:
            return f"the envelope has no {key}"
    if not isinstance(envelope["ok"], bool):
        return "the envelope's ok is not a boolean"
    if not isinstance(envelope["notRead"], list) or not isinstance(envelope["warnings"], list):
        return "the envelope's notRead and warnings are not lists"
    if not envelope["ok"]:
        return "the envelope says ok is false"
    return None


def call(plugin, operation, request, caps):
    """Run one operation. A problem is set when the call itself broke the contract (time, size, envelope)."""
    payload = memoryview(json.dumps(request).encode("utf-8"))
    output = bytearray()
    deadline = time.monotonic() + caps["timeSeconds"]
    try:
        with subprocess.Popen(
            [plugin, operation], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        ) as process, selectors.DefaultSelector() as selector:
            try:
                for stream in (process.stdin, process.stdout, process.stderr):
                    os.set_blocking(stream.fileno(), False)
                    selector.register(stream, selectors.EVENT_WRITE if stream is process.stdin else selectors.EVENT_READ)
                while selector.get_map():
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise subprocess.TimeoutExpired(process.args, caps["timeSeconds"])
                    for key, _ in selector.select(remaining):
                        stream = key.fileobj
                        if stream is process.stdin:
                            try:
                                written = os.write(stream.fileno(), payload[:select.PIPE_BUF])
                                payload = payload[written:]
                            except BrokenPipeError:
                                payload = payload[:0]
                            if not payload:
                                selector.unregister(stream)
                                stream.close()
                            continue
                        size = io.DEFAULT_BUFFER_SIZE
                        if stream is process.stdout:
                            # Read only through the first byte beyond the cap.
                            size = min(size, caps["outputBytes"] - len(output) + 1)
                        chunk = os.read(stream.fileno(), size)
                        if not chunk:
                            selector.unregister(stream)
                            stream.close()
                        elif stream is process.stderr:
                            sys.stderr.write(chunk.decode("utf-8", "replace"))
                        else:
                            output.extend(chunk)
                            if len(output) > caps["outputBytes"]:
                                return Call(None, None, f"{operation} wrote more than the output cap of {caps['outputBytes']} bytes")
                process.wait(timeout=max(0, deadline - time.monotonic()))
            finally:
                # Reap on every path, including overflow and timeout; never drain
                # an unbounded producer with communicate().
                if process.poll() is None:
                    process.kill()
                process.wait()
    except subprocess.TimeoutExpired:
        return Call(None, None, f"{operation} ran past the time cap of {caps['timeSeconds']} s")
    except OSError as error:
        raise GatewayError(f"cannot run {plugin}: {error}") from error
    if process.returncode != 0:
        return Call(process.returncode, None, None)
    try:
        envelope = json.loads(output.decode("utf-8"))
    except ValueError:
        return Call(process.returncode, None, f"{operation} did not write one JSON envelope")
    problem = _envelope_problem(envelope)
    return Call(process.returncode, None if problem else envelope, problem)


def _must_succeed(plugin, operation, request, caps):
    result = call(plugin, operation, request, caps)
    if result.problem:
        raise GatewayError(f"{operation}: {result.problem}")
    if result.code != 0:
        raise GatewayError(f"{operation}: the plugin exited {result.code}")
    return result.envelope["data"]


def describe(plugin, caps):
    data = _must_succeed(plugin, _policy("operations", "describe"), {}, caps)
    if not isinstance(data, dict) or data.get("protocol") != _policy("protocol"):
        raise GatewayError(f"describe: the plugin must answer protocol {_policy('protocol')!r}")
    listed = data.get("operations")
    wanted = [_policy("operations", name) for name in ("plan", "runUnit", "merge")]
    missing = [name for name in wanted if not isinstance(listed, list) or name not in listed]
    if missing:
        raise GatewayError(f"describe: the plugin does not list {', '.join(missing)}")
    return data


def _check_plan(plan):
    if not isinstance(plan, dict) or not isinstance(plan.get("units"), list):
        raise GatewayError("plan: the answer has no list of units")
    pattern = re.compile(_policy("unitIdPattern"))
    seen = set()
    for unit in plan["units"]:
        ident = unit.get("id") if isinstance(unit, dict) else None
        if not isinstance(ident, str) or not pattern.match(ident):
            raise GatewayError(f"plan: a unit id must match {_policy('unitIdPattern')}, got {ident!r}")
        if ident in seen:
            raise GatewayError(f"plan: unit {ident} is listed twice")
        seen.add(ident)
        if not isinstance(unit.get("host"), str) or not unit["host"]:
            raise GatewayError(f"plan: unit {ident} has no host")
        if not isinstance(unit.get("facts"), list):
            raise GatewayError(f"plan: unit {ident} has no list of facts")
    plan_width = plan.get("maxParallel")
    if plan_width is not None and (not isinstance(plan_width, int) or isinstance(plan_width, bool) or plan_width < 1):
        raise GatewayError("plan: maxParallel is not a positive integer")


def plan(plugin, plan_input, caps, max_parallel):
    """describe, then plan. Returns (the plan, the unit ids, the matrix width)."""
    describe(plugin, caps)
    data = _must_succeed(plugin, _policy("operations", "plan"), {"input": plan_input, "caps": caps}, caps)
    _check_plan(data)
    return data, [unit["id"] for unit in data["units"]], effective_max_parallel(max_parallel, data.get("maxParallel"))


def _unit(plan_data, unit_id):
    for unit in plan_data["units"]:
        if unit["id"] == unit_id:
            return unit
    raise GatewayError(f"unit {unit_id} is not in the plan")


def unreached_partial(unit, attempts):
    """The partial of a unit that kept answering temporary failure: no robots record, no results, every fact left for the next run."""
    return {"requests": attempts, "robots": None, "results": [], "notReached": list(unit["facts"])}


def run_unit(plugin, plan_data, unit_id, caps, attempts, wait_seconds, sleep=time.sleep, clock=time.monotonic):
    """One unit, with its retries. Returns {"state": ok | unreached | fatal, "partial", "attempts", "reason"}.

    attempts is the calls of the unit in all, the first included. The time cap bounds the unit across its
    calls and waits: a retry that would start past it is not made, and the unit is left unreached.
    """
    unit = _unit(plan_data, unit_id)
    request = {"unit": unit, "network": {"hosts": [unit["host"]]}, "caps": caps}
    retry_code = _policy("retry", "exitCode")
    started = clock()
    made = 0
    while True:
        remaining = caps["timeSeconds"] - (clock() - started)
        made += 1
        result = call(plugin, _policy("operations", "runUnit"), request, {**caps, "timeSeconds": remaining})
        if result.problem:
            return {"state": "fatal", "partial": None, "attempts": made, "reason": result.problem}
        if result.code == 0:
            return {"state": "ok", "partial": result.envelope["data"], "attempts": made, "reason": ""}
        if result.code != retry_code:
            return {"state": "fatal", "partial": None, "attempts": made, "reason": f"the plugin exited {result.code}"}
        if made >= attempts:
            reason = f"still temporary ({retry_code}) after {made} attempts"
            break
        if (clock() - started) + wait_seconds >= caps["timeSeconds"]:
            reason = f"temporary ({retry_code}) and waiting {wait_seconds} s would pass the time cap"
            break
        sleep(wait_seconds)
    return {"state": "unreached", "partial": unreached_partial(unit, made), "attempts": made, "reason": reason}


def _read_partials(plan_data, partials_dir):
    known = {unit["id"] for unit in plan_data["units"]}
    found = {}
    if os.path.isdir(partials_dir):
        for name in sorted(os.listdir(partials_dir)):
            stem, extension = os.path.splitext(name)
            if extension != ".json":
                continue
            if stem not in known:
                raise GatewayError(f"partial {name} is for a unit that is not in the plan")
            with open(os.path.join(partials_dir, name), encoding="utf-8") as f:
                found[stem] = json.load(f)
    return found


def merge(plugin, plan_data, partials_dir, caps):
    """merge with the plan and every partial that exists. Returns (the report, the unit ids with no partial)."""
    found = _read_partials(plan_data, partials_dir)
    missing = [unit["id"] for unit in plan_data["units"] if unit["id"] not in found]
    request = {"plan": plan_data, "partials": [found[unit["id"]] for unit in plan_data["units"] if unit["id"] in found]}
    return _must_succeed(plugin, _policy("operations", "merge"), request, caps), missing


def _write_json(path, value):
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(value, f, indent=2)
        f.write("\n")


def _read_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _output(name, value):
    line = f"{name}={json.dumps(value, separators=(',', ':')) if not isinstance(value, str) else value}"
    target = os.environ.get(OUTPUT_ENV)
    if target:
        with open(target, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    else:
        print(line)


def _at_least(minimum):
    def parse(text):
        value = int(text)
        if value < minimum:
            raise argparse.ArgumentTypeError(f"must be at least {minimum}")
        return value

    return parse


def _parser():
    parser = argparse.ArgumentParser(prog="plugin_gateway", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="step", required=True)
    for name in ("plan", "unit", "merge"):
        step = sub.add_parser(name)
        step.add_argument("--plugin", required=True)
        step.add_argument("--time-seconds", type=_at_least(1), default=_policy("caps", "timeSeconds"))
        step.add_argument("--output-bytes", type=_at_least(1), default=_policy("caps", "outputBytes"))
        if name == "plan":
            step.add_argument("--plan-input", required=True)
            step.add_argument("--out", required=True)
            step.add_argument("--max-parallel", type=_at_least(1), default=_policy("maxParallel"))
        else:
            step.add_argument("--plan", required=True)
        if name == "unit":
            step.add_argument("--unit", required=True)
            step.add_argument("--out-dir", required=True)
            step.add_argument("--retry-attempts", type=_at_least(1), default=_policy("retry", "attempts"))
            step.add_argument("--retry-wait-seconds", type=_at_least(0), default=_policy("retry", "waitSeconds"))
        if name == "merge":
            step.add_argument("--partials-dir", required=True)
            step.add_argument("--out", required=True)
    return parser


def _step_plan(args, caps):
    data, ids, width = plan(args.plugin, _read_json(args.plan_input), caps, args.max_parallel)
    _write_json(args.out, data)
    _output("units", ids)
    _output("has-units", "true" if ids else "false")
    _output("max-parallel", str(width))
    print(f"planned {len(ids)} units, at most {width} at once")
    return EXIT_OK


def _step_unit(args, caps, sleep, clock):
    outcome = run_unit(args.plugin, _read_json(args.plan), args.unit, caps, args.retry_attempts, args.retry_wait_seconds, sleep, clock)
    if outcome["state"] == "fatal":
        print(f"::warning::unit {args.unit}: {outcome['reason']}; no partial, so merge reports its facts unreadable")
        return EXIT_FAILED
    _write_json(os.path.join(args.out_dir, args.unit + ".json"), outcome["partial"])
    if outcome["state"] == "unreached":
        print(f"::warning::unit {args.unit}: {outcome['reason']}; its facts wait for the next run")
    print(f"unit {args.unit}: {outcome['state']} after {outcome['attempts']} attempts")
    return EXIT_OK


def _step_merge(args, caps):
    plan_data = _read_json(args.plan)
    report, missing = merge(args.plugin, plan_data, args.partials_dir, caps)
    for unit_id in missing:
        print(f"::warning::unit {unit_id} has no partial; merge reports its facts unreadable")
    _write_json(args.out, report)
    _output("report-artifact", _policy("artifacts", "report"))
    _output("missing", missing)
    print(f"merged {len(plan_data['units']) - len(missing)} partials, {len(missing)} missing")
    return EXIT_OK


def main(argv=None, sleep=time.sleep, clock=time.monotonic):
    args = _parser().parse_args(argv)
    caps = {"timeSeconds": args.time_seconds, "outputBytes": args.output_bytes}
    try:
        if args.step == "plan":
            return _step_plan(args, caps)
        if args.step == "unit":
            return _step_unit(args, caps, sleep, clock)
        return _step_merge(args, caps)
    except GatewayError as error:
        print(f"::error::{error}")
        return EXIT_FAILED


if __name__ == "__main__":
    sys.exit(main())
