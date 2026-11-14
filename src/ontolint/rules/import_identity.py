"""Run-level rule about the files an import closure loads: ONT009.

With ``--follow-imports`` or ``--catalog``, an ``owl:imports`` resolves to the file an OASIS XML catalog names
for the imported IRI, and that file is loaded as the import (:mod:`ontolint.imports`).  Nothing makes the
catalog right: a stale entry, a mistyped name or a copied line leaves the closure holding another ontology
than the one imported, whose terms join the linted graph and whose findings are reported as the import's.
Protege and the OWL API report an ontology IRI mismatch in this case.  The closure is unchanged by this rule
(the file is still loaded, so no other finding moves); the CLI hands the root file the mismatches of its
closure as ``Policy.import_mismatches``, and ``run`` turns them into findings.

A file *declares* the imported IRI when one of its ``owl:Ontology`` subjects is that IRI or has it as an
``owl:versionIRI``; a file that declares several ontologies needs only one of them to match.  Blank-node
ontologies declare nothing.  An ontology that gives no version IRI (an ODK edit file) matches its ontology IRI,
and its release matches both, so those pairs are clean.  A ``file:`` IRI import is not checked: it names a
document, not an ontology, and so does an import resolved through ``--import-dir``, whose files are matched by
the IRIs they declare.

* **ONT009.** An ``owl:imports`` IRI that a catalog maps to a file declaring neither it nor a version IRI of
  it.  The focus is the imported IRI; the message names the file and the ontology IRIs it does declare (with
  their version IRIs), or says that it declares no ontology.  The finding is reported once per imported IRI,
  on the file of the closure that states the ``owl:imports``.  Its baseline identity is the rule and the
  imported IRI, never the file or what it declares: repointing the entry at another wrong file is the same
  problem.  Why warning: the closure
  lints a different ontology than the one imported, which changes what every other rule sees; it is not an
  error because the file is still read and the result is deterministic.  A file with no ontology header is
  reported the same way, since nothing says which ontology it is.  Confidence ``certain``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from rdflib import URIRef

from ontolint.models import ImportMismatch, RuleBackend, RuleScope, RuleSpec, Severity

if TYPE_CHECKING:
    from .runtime import RuleContext

MAX_LISTED = 10
"""How many ontology IRIs (and version IRIs of one ontology) the message names before ``and N more``."""

SPECS: tuple[RuleSpec, ...] = (
    RuleSpec(
        "ONT009",
        "ONT",
        "Imported file does not declare the imported IRI",
        Severity.WARNING,
        "Correct the catalog entry (or the owl:imports IRI) so the file declares the imported IRI, or give the "
        "file that ontology or version IRI.",
        "deterministic",
        RuleBackend.RDFLIB,
        RuleScope.ONTOLOGY,
        "import_identity",
    ),
)


def _listed(items: list[str]) -> str:
    shown = ", ".join(items[:MAX_LISTED])
    return shown + f" and {len(items) - MAX_LISTED} more" if len(items) > MAX_LISTED else shown


def message(mismatch: ImportMismatch) -> str:
    """The finding's message: the import, the file the catalog names, and what that file declares instead."""
    found = mismatch.ontologies
    if not found:
        declares = "declares no ontology"
    else:
        shown = []
        for ontology, versions in found[:MAX_LISTED]:
            noun = "version" if len(versions) == 1 else "versions"
            tail = f" ({noun} {_listed([f'<{v}>' for v in versions])})" if versions else ""
            shown.append(f"<{ontology}>{tail}")
        if len(found) > MAX_LISTED:
            shown.append(f"and {len(found) - MAX_LISTED} more")
        declares = f"declares {'ontology' if len(found) == 1 else 'ontologies'} " + ", ".join(shown)
    return f"owl:imports <{mismatch.iri}> is loaded from {mismatch.document}, which {declares}, not <{mismatch.iri}>."


def run(ctx: RuleContext) -> None:
    """Emit one finding per import of the closure whose catalog file does not declare it (none outside the CLI)."""
    for mismatch in ctx.policy.import_mismatches:
        ctx.add("ONT009", URIRef(mismatch.iri), message(mismatch), confidence="certain", subject=())
