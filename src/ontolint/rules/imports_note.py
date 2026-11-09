"""Run note about ``owl:imports`` that ontolint did not follow: SEC007.

ontolint never fetches ``owl:imports`` from the network (deterministic output).  By default every rule
judges the asserted graph of the one file it was given; with ``--follow-imports`` or ``--catalog`` the
imports that resolve to local files are loaded too (:mod:`ontolint.imports`), and only the others are
listed here.  An unfollowed import is a limit of the result, not a defect of the ontology, hence the INFO
severity: the finding is one summary line per file (focus ``(imports)``) naming the imports that were
skipped, so a reader knows what the other rules could not see.  It never fails a run by default and can be
silenced with ``--ignore SEC007``.  Pinning of the imports is GOV002's concern, not this rule's.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from rdflib import BNode
from rdflib.namespace import OWL

from ontolint.models import RuleBackend, RuleScope, RuleSpec, Severity

from .support import display_iri, stable_blank_id

if TYPE_CHECKING:
    from .runtime import RuleContext

MAX_LISTED = 10
"""How many import IRIs the message names before it summarises the rest as ``and N more``."""

SPECS: tuple[RuleSpec, ...] = (
    RuleSpec(
        "SEC007",
        "SEC",
        "owl:imports not followed",
        Severity.INFO,
        "Map the imports to local files with --follow-imports and a catalog-v001.xml (or --catalog), or lint "
        "them separately; ontolint never fetches imports from the network. Use --ignore SEC007 to silence this note.",
        "deterministic",
        RuleBackend.RDFLIB,
        RuleScope.ONTOLOGY,
        "imports_note",
    ),
)


def run(ctx: RuleContext) -> None:
    """Emit one note listing the distinct ``owl:imports`` objects (sorted) when the graph has any.

    A blank-node target is named by its content-stable identity, so neither the sort order nor the message
    depends on how the parser labelled it.
    """
    resolved = ctx.policy.resolved_imports  # loaded from local files by --follow-imports / --catalog
    imports = sorted(
        {
            stable_blank_id(ctx.g, t) if isinstance(t, BNode) else display_iri(str(t), ctx.policy.document_bases)
            for t in ctx.g.objects(None, OWL.imports)
            if str(t) not in resolved
        }
    )
    if not imports:
        return
    count = len(imports)
    listed = ", ".join(imports[:MAX_LISTED])
    if count > MAX_LISTED:
        listed += f" and {count - MAX_LISTED} more"
    noun = "owl:import was" if count == 1 else "owl:imports were"
    ctx.add("SEC007", "(imports)", f"{count} {noun} not followed: {listed}.", confidence="certain")
