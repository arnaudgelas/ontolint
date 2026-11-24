"""Why a run exited 2 (issue #175).

Exit status 2 means the tool could not deliver a verdict.  Its causes fall in two groups, and both say why:

* **After the report is built**: a rule failed, timed out or is unsupported, a budget could not be checked, a
  measurement could not be computed.  The reasons are derived from the report (:func:`report_reasons`), so they
  are in every format that carries it: the ``exit`` key of the JSON report, a notification and ``ontolintExit`` in
  SARIF, and the lines under the text.  The exit code and the reasons are decided by the same two sources
  (:attr:`~ontolint.reporting.RunReport.broken` and ``failed_measurements``), so they cannot disagree.
* **Before there is a report**: an input that does not parse, a policy rejected as ``GOV020``, an unknown rule, a
  usage error, an internal error, an output that cannot be written.  There is nothing to put the reason in, so it is
  printed on stderr, through :func:`refuse`, the only way :mod:`ontolint.cli` leaves with 2
  (``tests/test_exit_reasons.py`` reads the source to prove it).

The kinds are an open enumeration (``docs/report-compatibility.md``): a release may add one, so a consumer
treats a kind it does not know as "some other tool failure".  Messages are one line each and carry no IRI userinfo.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, NoReturn

from .escaping import one_line
from .models import ExecutionStatus, RuleExecution
from .redaction import redact_userinfo

if TYPE_CHECKING:
    from .reporting import RunReport

TOOL_FAILURE_EXIT = 2

#: Reasons found in a report (the run completed, its verdict is missing).
RULE_FAILED = "rule_failed"
RULE_TIMEOUT = "rule_timeout"
RULE_UNSUPPORTED = "rule_unsupported"
BUDGET_UNMEASURED = "budget_unmeasured"
MEASUREMENT_FAILED = "measurement_failed"
REPORT_KINDS = frozenset({RULE_FAILED, RULE_TIMEOUT, RULE_UNSUPPORTED, BUDGET_UNMEASURED, MEASUREMENT_FAILED})

#: Reasons of a run that stopped before it had a report: stderr only.
REFUSAL_KINDS = frozenset(
    {
        "input_unparseable",
        "input_rejected",
        "config_invalid",
        "policy_rejected",
        "snapshot_unreadable",
        "output_failed",
        "unknown_rule",
        "usage",
        "execution_failed",
        "internal_error",
    }
)
KINDS = REPORT_KINDS | REFUSAL_KINDS

BUDGET_RULE = "METRIC014"
_TIMEOUT_MARKERS = (
    "ValidationTimeout",
    "WorkerTimeout",
    "TimeoutError",
    "did not finish",
    "did not answer within",
    "TimeoutExpired",
    "timed out",
)


@dataclass(frozen=True)
class ExitReason:
    """One cause of exit status 2.

    ``message`` is the diagnostic, without userinfo; a reason found in a report has it on one line (a refusal prints its
    message as it is, which may take several lines).  ``rule``, ``path`` and ``measurement`` say where
    it happened, when it did so somewhere.
    """

    kind: str
    message: str
    rule: str | None = None
    path: str | None = None
    measurement: str | None = None

    def __post_init__(self) -> None:
        if self.kind not in KINDS:
            raise ValueError(f"unknown exit reason kind {self.kind!r}")
        object.__setattr__(self, "message", redact_userinfo(self.message))
        if self.path is not None:
            object.__setattr__(self, "path", redact_userinfo(self.path))

    def to_dict(self) -> dict[str, str]:
        """The JSON form: ``kind`` and ``message``, then the place when there is one."""
        document = {"kind": self.kind, "message": self.message}
        for key in ("rule", "path", "measurement"):
            if (value := getattr(self, key)) is not None:
                document[key] = value
        return document

    def line(self) -> str:
        """The text form: ``kind: message``, with the place after the kind."""
        place = " ".join(
            part
            for part in (
                self.rule,
                f"for {self.path}" if self.path is not None else None,
                self.measurement,
            )
            if part
        )
        if self.rule is not None:  # the execution line above says why; saying it twice would print the results twice
            return f"{self.kind}: {place}"
        return f"{self.kind}: {place + ': ' if place else ''}{self.message}"


def refuse(reason: ExitReason, *, announce: bool = True) -> int:
    """Leave with exit status 2 for ``reason``: print its message on stderr (unless the caller did) and return 2.

    The message goes to the stream :func:`ontolint.cli.main` has put behind the redaction.  A closed stderr is the
    caller's to handle (``main`` turns it into the pipe status), as it was before.
    """
    if announce:
        print(reason.message, file=sys.stderr)
    return TOOL_FAILURE_EXIT


def execution_reason(path: str, execution: RuleExecution) -> ExitReason:
    """The reason a rule execution that delivered no verdict gives (status ``failed`` or ``unsupported``)."""
    if execution.status is ExecutionStatus.UNSUPPORTED:
        kind = RULE_UNSUPPORTED
    elif execution.rule_id == BUDGET_RULE:
        kind = BUDGET_UNMEASURED
    elif any(marker in execution.detail for marker in _TIMEOUT_MARKERS):
        kind = RULE_TIMEOUT
    else:
        kind = RULE_FAILED
    return ExitReason(kind, one_line(execution.detail), rule=execution.rule_id, path=one_line(path))


def report_reasons(report: RunReport) -> tuple[ExitReason, ...]:
    """The reasons a run report exits 2: its broken rule executions, then its failed measurements.

    Both are in report order (file by file, rules in the order they ran, measurements in the order they were computed),
    so the list is the same for the same run.  ``()`` for a run that exits 0 or 1.
    """
    return (
        *(execution_reason(path, x) for path, x in report.broken),
        *(
            ExitReason(MEASUREMENT_FAILED, one_line(reason), path=one_line(path), measurement=one_line(measurement_id))
            for path, measurement_id, reason in report.failed_measurements
        ),
    )


def exit_object(report: RunReport) -> dict[str, Any] | None:
    """The ``exit`` object of the JSON report and the ``ontolintExit`` property of SARIF; ``None`` unless exit 2."""
    reasons = report_reasons(report)
    if not reasons:
        return None
    return {"code": TOOL_FAILURE_EXIT, "reasons": [r.to_dict() for r in reasons]}


def text_lines(report: RunReport) -> list[str]:
    """The lines under the text report: ``Exit status 2: N reason(s)`` and one line each; none unless exit 2."""
    reasons = report_reasons(report)
    if not reasons:
        return []
    return [f"Exit status {TOOL_FAILURE_EXIT}: {len(reasons)} reason(s)", *(f"  - {r.line()}" for r in reasons)]


class UsageParser(argparse.ArgumentParser):
    """The command-line parser: a usage error is a reason like any other.

    ``argparse`` prints the usage and the message and exits with 2 on its own.  This prints the same two things, through
    :func:`refuse`, and raises the same ``SystemExit(2)``.
    """

    def error(self, message: str) -> NoReturn:
        self.print_usage(sys.stderr)
        raise SystemExit(refuse(ExitReason("usage", f"{self.prog}: error: {message}")))
