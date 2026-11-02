"""Semantic checker for an incident-detection drill report (spec/drill-report/).

The schema holds the shape. This module holds what JSON Schema cannot say: arithmetic on timestamps and
comparisons across fields. It assumes nothing about the schema having run first; a field of the wrong
type or an unreadable timestamp is a finding, not a crash.

    python3 -m tooling.practice_ci.drill_check report.json [report.json ...]

Exit status: 0 when every report is consistent, 1 when any has a finding, 2 on a usage or read error.
"""
import datetime
import json
import re
import sys

NS_PER_MS = 1_000_000
NS_PER_SECOND = 1_000_000_000
EXIT_OK, EXIT_FINDINGS, EXIT_USAGE = 0, 1, 2

_EPOCH = datetime.datetime(1970, 1, 1, tzinfo=datetime.timezone.utc)
_TIME = re.compile(r"^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d{1,9}))?Z$")
_INTEGER_FIELDS = ("mttdMs", "probeIntervalMs", "threshold", "productionIntervalMs", "scaledMttdMs", "objectiveMs")


def parse_time(text):
    """Nanoseconds since the Unix epoch for a UTC RFC 3339 'Z' timestamp; ValueError when it is not a real instant."""
    match = _TIME.match(text) if isinstance(text, str) else None
    if not match:
        raise ValueError("not a UTC date-time ending in Z")
    year, month, day, hour, minute, second = (int(g) for g in match.groups()[:6])
    moment = datetime.datetime(year, month, day, hour, minute, second, tzinfo=datetime.timezone.utc)
    whole = int((moment - _EPOCH).total_seconds())
    fraction = (match.group(7) or "").ljust(9, "0")
    return whole * NS_PER_SECOND + int(fraction)


def _is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def check(report):
    """Every way the report contradicts itself, as a list of messages; empty when it is consistent."""
    findings = []
    if not isinstance(report, dict):
        return ["report is not an object"]

    times = {}
    for key in ("injectedAt", "detectedAt", "notifiedAt"):
        if key not in report:
            continue
        try:
            times[key] = parse_time(report[key])
        except (ValueError, OverflowError) as error:
            findings.append(f"{key}: {error}")
    numbers = {}
    for key in _INTEGER_FIELDS:
        if _is_int(report.get(key)):
            numbers[key] = report[key]
        else:
            findings.append(f"{key}: missing or not an integer")

    if "injectedAt" not in report:
        findings.append("injectedAt: missing")
    if "detectedAt" not in report:
        findings.append("detectedAt: missing")

    injected, detected = times.get("injectedAt"), times.get("detectedAt")
    if injected is not None and detected is not None:
        findings += _check_detection(numbers, injected, detected)
    findings += _check_projection(numbers)
    findings += _check_verdict(report, numbers)
    findings += _check_notification(report, times, detected)
    return findings


def _check_detection(numbers, injected, detected):
    if detected < injected:
        return ["detectedAt: precedes injectedAt"]
    if "mttdMs" not in numbers:
        return []
    elapsed = detected - injected
    if numbers["mttdMs"] * NS_PER_MS != elapsed:
        return [f"mttdMs: is {numbers['mttdMs']} but detectedAt - injectedAt is {elapsed} ns"]
    return []


def _check_projection(numbers):
    needed = ("mttdMs", "probeIntervalMs", "productionIntervalMs", "scaledMttdMs")
    if any(key not in numbers for key in needed) or numbers["probeIntervalMs"] < 1:
        return []
    expected = numbers["mttdMs"] * numbers["productionIntervalMs"] // numbers["probeIntervalMs"]
    if numbers["scaledMttdMs"] != expected:
        return [
            "scaledMttdMs: is %d but mttdMs * productionIntervalMs / probeIntervalMs, rounded down, is %d"
            % (numbers["scaledMttdMs"], expected)
        ]
    return []


def _check_verdict(report, numbers):
    if "scaledMttdMs" not in numbers or "objectiveMs" not in numbers:
        return []
    if not isinstance(report.get("withinObjective"), bool):
        return ["withinObjective: missing or not a boolean"]
    expected = numbers["scaledMttdMs"] <= numbers["objectiveMs"]
    if report["withinObjective"] != expected:
        return [
            "withinObjective: is %s but scaledMttdMs %d against objectiveMs %d makes it %s"
            % (str(report["withinObjective"]).lower(), numbers["scaledMttdMs"], numbers["objectiveMs"], str(expected).lower())
        ]
    return []


def _check_notification(report, times, detected):
    findings = []
    if not isinstance(report.get("notified"), bool):
        return ["notified: missing or not a boolean"]
    by = report.get("notifiedBy")
    if "notifiedBy" in report and not (isinstance(by, str) and by):
        findings.append("notifiedBy: not a non-empty string")
    present = "notifiedAt" in report and "notifiedAt" in times and isinstance(by, str) and bool(by)
    if report["notified"] != present:
        findings.append(
            "notified: is %s but notifiedAt and notifiedBy are %s"
            % (str(report["notified"]).lower(), "both present" if present else "not both present")
        )
    notified_at = times.get("notifiedAt")
    if notified_at is not None and detected is not None and notified_at < detected:
        findings.append("notifiedAt: precedes detectedAt")
    return findings


def main(argv):
    if not argv:
        print("usage: drill_check.py report.json [report.json ...]", file=sys.stderr)
        return EXIT_USAGE
    status = EXIT_OK
    for path in argv:
        try:
            with open(path, encoding="utf-8") as f:
                report = json.load(f)
        except (OSError, ValueError) as error:
            print(f"{path}: cannot read: {error}", file=sys.stderr)
            return EXIT_USAGE
        findings = check(report)
        for finding in findings:
            print(f"{path}: {finding}")
        if findings:
            status = EXIT_FINDINGS
        else:
            print(f"ok {path}")
    return status


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
