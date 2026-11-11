"""The parse worker's job answers a parser's ParseFailure with a parse_failure reply the parent can map."""

from __future__ import annotations

import json
from unittest import mock

from ontolint import loader
from ontolint.loader import ParseFailure


def test_job_maps_a_parse_failure_to_a_parse_failure_reply() -> None:
    job = loader._ParseJob(b"x", "turtle", "file:///x.ttl", "x.ttl", 10)  # noqa: SLF001

    with mock.patch.object(loader, "_parse_bytes", side_effect=ParseFailure("BadSyntax", "line 1: oops")):
        reply = job.run()

    assert json.loads(reply) == {"parse_failure": ["BadSyntax", "line 1: oops"]}
