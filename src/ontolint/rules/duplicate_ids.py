"""Set-level rules: one ontology or version IRI declared by several documents of a run (ONT007, ONT008).

Every other rule judges one file.  These two judge the set of documents a run reads, which no single file
can show: two inputs that claim to be the same release, two modules of an import closure with one header,
the ``--import-dir`` options holding an ontology twice (``owl:imports`` then takes the first file in
argument and path order, so which copy is linted depends on file names), or two named graphs of a dataset
that each declare it.  The command line finds them before linting (:mod:`ontolint.declarations`) and hands
each file the ones reported on it as ``Policy.shared_identities``; ``run`` only turns those into findings,
so the engine applies selection, ignores, severity overrides, baselines and ``--fail-on`` to them like to
any rule.  A run of one file without imports or named graphs, and the library API on a bare graph, have
none: one document shares nothing, so the rules run and find nothing (status ``executed``).  When neither
rule is selected, the CLI compares nothing.

A document *declares* an ontology IRI when it states ``<IRI> rdf:type owl:Ontology``, and a version IRI
when it states ``<O> owl:versionIRI <IRI>`` for such an ontology ``<O>``.  Blank-node ontologies declare
nothing.  The documents are compared in four places, each separately:

* ``inputs``: the files given on the command line, each without its imports (with two or more inputs);
* ``closure``: the files of one input's ``owl:imports`` closure, the input first, then in load order, and
  the file an import resolves to but did not load because a loaded file already declares the imported IRI
  (the OWL API does not read an ontology again under an IRI it has; which module wins then depends on the
  order of the imports, and the module that loses vanishes from the closure);
* ``import-dir``: for each ``owl:imports`` resolved through ``--import-dir``, every file of those
  directories that declares the imported IRI, by directory in argument order then by path (the first is
  the one used); a duplicate no import uses changes no result and is not reported;
* ``graphs``: the named graphs (and default graph) of one dataset file: TriG, N-Quads, JSON-LD.

Two versions of one ontology series share the ontology IRI under different version IRIs, and OWL 2 lets
them coexist (Structural Specification, section 3.3): an ODK ``x-edit.owl`` without a version IRI and its
release ``x.owl`` with a dated one, or two releases.  So for the inputs and the graphs of a dataset, which
are independent documents, a version IRI is reported whenever two documents declare it, and an ontology
IRI only among the documents that give it no version IRI.  An import closure must not hold two versions
of one series (section 3.5), so there an ontology IRI is reported whenever two files declare it, and a
version IRI only when its files do not all declare one ontology IRI.  For ``import-dir`` the focus is the
imported IRI, ontology or version IRI alike: the import had to choose.

*Content* is the document's RDF graph, not its bytes (:func:`ontolint.datasets.same_content`): two
documents have the same content when their graphs are isomorphic, IRIs absolute as parsed, so syntax,
prefixes, triple order and blank-node labels change nothing.

* **ONT007.** A shared identity whose documents differ in content.  The focus is the shared IRI; the
  message names how many documents declare it and lists them, for ``import-dir`` the imported IRI, the
  directories and the file it resolved to, and for ``closure`` each file an import did not load.  Why
  warning: two different documents under one identity make a result depend on which one a tool reads (file
  names, for ``--import-dir``; the order of the imports, in a closure), and a version IRI names exactly
  one release.  Confidence ``certain``.
* **ONT008.** The same, when every document has the same content.  Why info: a mirrored or vendored copy
  is harmless today, but the copies drift apart unless one is generated from the other.  Confidence
  ``certain``.

One fact is reported once: a finding whose documents are all documents of another finding on the same
IRI is dropped (the closure of an input that is also an input; two inputs importing one IRI from one
``--import-dir``).  A finding is reported on the first input in report-path order (so the argument order
changes nothing), or on the input whose closure, import or dataset holds the documents.  It belongs to the
first document's file in that order (JSON ``path``), which is deterministic but says nothing about which
document is the original.  SARIF gives that file as the location and every other file as a related
location (SARIF 2.1.0, section 3.27.12: removing any one copy fixes the finding).  Its baseline identity
is the rule, the IRI, the place and the kind, never the documents: paths depend on the machine and the
working directory, and another copy is the same problem, not a new one; a copy that starts or stops
differing changes the rule, so it is a new finding.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from rdflib import URIRef

from ontolint.models import RuleBackend, RuleScope, RuleSpec, Severity, SharedIdentity

if TYPE_CHECKING:
    from .runtime import RuleContext

SPECS: tuple[RuleSpec, ...] = (
    RuleSpec(
        "ONT007",
        "ONT",
        "Ontology or version IRI declared by several documents with different content",
        Severity.WARNING,
        "Keep one document per release: remove the stale copy, give every release its own version IRI, and "
        "give a fork its own ontology IRI.",
        "deterministic",
        RuleBackend.RDFLIB,
        RuleScope.SET,
        "duplicate_ids",
    ),
    RuleSpec(
        "ONT008",
        "ONT",
        "Identical copies of one ontology in several documents",
        Severity.INFO,
        "Keep one copy, or generate the others from it (robot mirror, a release step) so they cannot drift apart.",
        "deterministic",
        RuleBackend.RDFLIB,
        RuleScope.SET,
        "duplicate_ids",
    ),
)

SET_RULES = frozenset(spec.rule_id for spec in SPECS)
"""The rules that need :func:`ontolint.declarations.shared_identities`: the CLI skips it when neither runs."""

EMPTY_FOCUS = "<>"
"""The empty IRI as a focus, as ``runtime.EMPTY_FOCUS`` renders it (rule modules import runtime only to type)."""

_PLACES = {"inputs": "input files", "closure": "files of the import closure"}


def rule_of(shared: SharedIdentity) -> str:
    """The rule reporting ``shared``: ONT008 for identical copies, ONT007 otherwise."""
    return "ONT008" if shared.identical else "ONT007"


def subject_of(shared: SharedIdentity) -> tuple[str, ...]:
    """The baseline subject of the finding for ``shared``: its place and kind, never its documents.

    The documents are paths (which depend on the working directory and the machine) and a count of copies
    is a measurement: a finding stays the same finding when a copy is added, removed or renamed, and the
    message (so the version 1 hash) still names them all.  A copy that starts or stops differing changes the
    rule, so it is a new finding.
    """
    return (shared.scope, shared.kind)


def finding_key(shared: SharedIdentity) -> tuple[str, str, tuple[str, ...], str]:
    """``(rule, focus, subject, message)`` of the finding reported for ``shared``: how the CLI finds it again."""
    return rule_of(shared), shared.iri or EMPTY_FOCUS, subject_of(shared), message(shared)


def message(shared: SharedIdentity) -> str:
    """The finding's message: what is shared, by how many documents of which place, and which they are."""
    count = len(shared.members)
    content = "with identical content" if shared.identical else "whose content differs"
    listed = ", ".join(shared.members)
    if shared.scope == "import-dir":
        several = ", " in shared.where
        order = "the first in argument and path order" if several else "the first in path order"
        return (
            f"owl:imports <{shared.iri}> matches {count} files in --import-dir {shared.where} {content}: {listed}; "
            f"it resolved to {shared.members[0]}, {order}."
        )
    place = f"graphs of {shared.where}" if shared.scope == "graphs" else _PLACES[shared.scope]
    kind = "Ontology IRI" if shared.kind == "ontology" else "Version IRI"
    unloaded = "".join(
        f"; owl:imports <{iri}> resolves to {member} but did not load it, since a loaded file already declares that IRI"
        for iri, member in shared.unloaded
    )
    return f"{kind} declared by {count} {place} {content}: {listed}{unloaded}."


def run(ctx: RuleContext) -> None:
    """Emit one finding per shared identity the run reports on this file (none outside the CLI)."""
    for shared in ctx.policy.shared_identities:
        ctx.add(rule_of(shared), URIRef(shared.iri), message(shared), confidence="certain", subject=subject_of(shared))
