"""Count what a widened SKOS001 would report on pinned SKOS vocabularies (issue #195).

    uv run python scripts/skos_preflabel_count.py fetch DIR   # check every repository out at its commit (network)
    uv run python scripts/skos_preflabel_count.py count DIR   # parse every RDF file, rewrite the results and the page
    uv run python scripts/skos_preflabel_count.py check DIR   # fail if the counts differ from the recorded results
    uv run python scripts/skos_preflabel_count.py render      # rewrite the generated part of the page

The page is docs/validation/skos-preflabel.md.  SKOS001 reports, for an owned resource typed ``skos:Concept``, two or
more preferred labels in one language.  Integrity condition S14 binds *any* resource, so the open question of issue #181
(question 3) is what the rule would report if it read every resource with a ``skos:prefLabel``, and how many files would
start to fail ``--fail-on error``.  Per file with a labelled resource (a subject of at least one literal
``skos:prefLabel``):

* ``labelled_<kind>``: the labelled resources of each kind, by their asserted ``rdf:type``, in this order: ``concept``
  (``skos:Concept``), ``scheme`` (``skos:ConceptScheme``), ``collection`` (``skos:Collection`` or
  ``skos:OrderedCollection``), ``class`` (``owl:Class`` or ``rdfs:Class``), ``other`` (typed, none of those),
  ``untyped``;
* ``multi_<kind>``: the (resource, language) pairs of that kind with more than one preferred label, languages compared
  as SKOS001 does (case-insensitively, an untagged label and ``@und`` one language, ``"a"`` equal to
  ``"a"^^xsd:string``);
* ``SKOS001``: the findings the rule reports today, checked to be at most ``multi_concept`` (the rule reads owned
  concepts only, and a concept in a minority namespace is not owned);
* ``newly_failing``: 1 when the rule reports nothing for the file but a widened rule would.

No file is committed: ``docs/validation/skos-preflabel-corpus.json`` names each repository, its commit and its licence,
and ``fetch`` refuses a checkout whose commit differs.  The reading of RDF files (formats, the 5 MiB cap, the unparsed
and skipped files) is that of ``scripts/pinned_repos.py``, shared with ``scripts/owl_restriction_count.py``.  The
results are a snapshot of one ontolint and one rdflib version.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pinned_repos  # noqa: E402 -- the sibling script; its directory is first on the path when this one is run

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "docs" / "validation" / "skos-preflabel-corpus.json"
RESULTS = ROOT / "docs" / "validation" / "skos-preflabel-results.json"
PAGE = ROOT / "docs" / "validation" / "skos-preflabel.md"
BEGIN, END = "<!-- skos_preflabel_count.py: begin -->", "<!-- skos_preflabel_count.py: end -->"
KINDS = ("concept", "scheme", "collection", "class", "other", "untyped")
NON_CONCEPTS = KINDS[1:]
FIELDS = (
    *(f"labelled_{kind}" for kind in KINDS),
    *(f"multi_{kind}" for kind in KINDS),
    "SKOS001",
    "newly_failing",
)
VERSIONS = ("ontolint", "rdflib")  # recorded with the counts, named when a check fails, not compared

load_manifest = pinned_repos.load_manifest
fetch = pinned_repos.fetch


def _kind(types: set[Any]) -> str:
    from rdflib.namespace import OWL, RDFS, SKOS  # noqa: PLC0415

    if SKOS.Concept in types:
        return "concept"
    if SKOS.ConceptScheme in types:
        return "scheme"
    if types & {SKOS.Collection, SKOS.OrderedCollection}:
        return "collection"
    if types & {OWL.Class, RDFS.Class}:
        return "class"
    return "other" if types else "untyped"


def _labels_by_language(graph: Any, subject: Any) -> dict[str, set[Any]]:
    """The literal preferred labels of ``subject`` by language, as SKOS001 groups them."""
    from rdflib import Literal  # noqa: PLC0415
    from rdflib.namespace import SKOS, XSD  # noqa: PLC0415

    by_language: defaultdict[str, set[Any]] = defaultdict(set)
    for label in graph.objects(subject, SKOS.prefLabel):
        if isinstance(label, Literal):
            plain = Literal(str(label)) if label.datatype == XSD.string else label
            by_language[(label.language or "und").lower()].add(plain)
    return by_language


def count_graph(graph: Any) -> dict[str, int] | None:
    """The :data:`FIELDS` of one parsed graph, or ``None`` if no resource has a literal ``skos:prefLabel``."""
    from rdflib import RDF  # noqa: PLC0415
    from rdflib.namespace import SKOS  # noqa: PLC0415

    from ontolint import Linter  # noqa: PLC0415

    counts = dict.fromkeys(FIELDS, 0)
    for subject in set(graph.subjects(SKOS.prefLabel, None)):
        by_language = _labels_by_language(graph, subject)
        if not by_language:
            continue
        kind = _kind(set(graph.objects(subject, RDF.type)))
        counts[f"labelled_{kind}"] += 1
        counts[f"multi_{kind}"] += sum(1 for labels in by_language.values() if len(labels) > 1)
    if not any(counts[f"labelled_{kind}"] for kind in KINDS):
        return None
    counts["SKOS001"] = len(Linter(graph).execute(["SKOS001"]).findings)
    if counts["SKOS001"] > counts["multi_concept"]:
        raise ValueError(
            f"SKOS001 reports {counts['SKOS001']} findings; counted {counts['multi_concept']} concept pairs"
        )
    counts["newly_failing"] = int(counts["SKOS001"] == 0 and any(counts[f"multi_{k}"] for k in NON_CONCEPTS))
    return counts


def count_repository(root: Path) -> dict[str, Any]:
    """The counts of every RDF file of ``root`` with a labelled resource, how many did not parse, which were skipped."""
    return pinned_repos.read_repository(root, count_graph)


def measure(directory: Path, repositories: list[dict[str, Any]]) -> dict[str, Any]:
    """The results document: per repository, its pinned commit, the file counts and the counts of each file."""
    from importlib.metadata import version  # noqa: PLC0415

    return {
        **{name: version(name) for name in VERSIONS},
        "repositories": [
            {"id": repo["id"], "commit": repo["commit"], **count_repository(directory / repo["id"])}
            for repo in repositories
        ],
    }


def totals(files: dict[str, dict[str, int]]) -> dict[str, int]:
    """The files that have a labelled resource, and the sum of each field over them."""
    return {"files": len(files), **{name: sum(f[name] for f in files.values()) for name in FIELDS}}


def _non_concept(t: dict[str, int], prefix: str) -> int:
    return sum(t[f"{prefix}_{kind}"] for kind in NON_CONCEPTS)


def render(results: dict[str, Any]) -> str:
    """The generated part of the page: a table per repository and in all, then the widening by kind."""
    rows: list[tuple[str, dict[str, int], tuple[int, int, int]]] = []
    every: dict[str, dict[str, int]] = {}
    for repo in results["repositories"]:
        rows.append((repo["id"], totals(repo["files"]), (repo["parsed"], repo["unparsed"], len(repo["skipped"]))))
        every.update({f"{repo['id']}/{p}": f for p, f in repo["files"].items()})
    everything = totals(every)
    columns = list(zip(*(row[2] for row in rows), strict=True))
    rows.append(("**all**", everything, (sum(columns[0]), sum(columns[1]), sum(columns[2]))))
    lines = [
        "### Per repository",
        "",
        "| Repository | RDF files parsed (not parsed, skipped) | Files with a preferred label | Labelled concepts "
        "| Labelled non-concepts | Concept pairs with several labels in one language | SKOS001 findings today "
        "| Non-concept pairs a widened rule adds | Files that would newly fail |",
        "| --- " * 9 + "|",
    ]
    for name, t, (ok, bad, skipped) in rows:
        lines.append(
            f"| {name} | {ok} ({bad}, {skipped}) | {t['files']} | {t['labelled_concept']} "
            f"| {_non_concept(t, 'labelled')} | {t['multi_concept']} | {t['SKOS001']} "
            f"| {_non_concept(t, 'multi')} | {t['newly_failing']} |"
        )
    lines += [
        "",
        "### By kind of resource, all repositories",
        "",
        "| Kind of resource | Labelled resources | (Resource, language) pairs with several preferred labels |",
        "| --- | --- | --- |",
        *(f"| {kind} | {everything[f'labelled_{kind}']} | {everything[f'multi_{kind}']} |" for kind in KINDS),
    ]
    return "\n".join(lines)


def _split(content: str) -> tuple[str, str]:
    if content.count(BEGIN) != 1 or content.count(END) != 1 or content.index(BEGIN) > content.index(END):
        raise ValueError(f"the page must hold one {BEGIN} line followed by one {END} line")
    head, _, rest = content.partition(BEGIN)
    return head, rest.partition(END)[2]


def write_page(results: dict[str, Any], page: Path = PAGE) -> None:
    head, tail = _split(page.read_text(encoding="utf-8"))
    page.write_text(f"{head}{BEGIN}\n\n{render(results)}\n\n{END}{tail}", encoding="utf-8")


def generated_part(page: Path = PAGE) -> str:
    return page.read_text(encoding="utf-8").partition(BEGIN)[2].partition(END)[0].strip("\n")


def dump(document: dict[str, Any]) -> str:
    return json.dumps(document, indent=1, sort_keys=True) + "\n"


def _comparable(document: dict[str, Any]) -> dict[str, Any]:
    """The results without the tool versions: ``check`` compares what was counted, not who counted it."""
    return {k: v for k, v in document.items() if k not in VERSIONS}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Count a widened SKOS001 on pinned SKOS vocabularies.")
    parser.add_argument("command", choices=("fetch", "count", "check", "render"))
    parser.add_argument("directory", nargs="?", type=Path, help="where the repositories are checked out")
    args = parser.parse_args(argv)
    repositories = load_manifest(MANIFEST)
    if args.command == "render":
        write_page(json.loads(RESULTS.read_text(encoding="utf-8")))
        return 0
    if args.directory is None:
        parser.error(f"{args.command} needs a directory")
    if args.command == "fetch":
        fetch(args.directory, repositories)
        return 0
    document = measure(args.directory, repositories)
    if args.command == "count":
        RESULTS.write_text(dump(document), encoding="utf-8")
        write_page(document)
        return 0
    recorded = json.loads(RESULTS.read_text(encoding="utf-8"))
    if _comparable(document) != _comparable(recorded):
        then = ", ".join(f"{name} {recorded.get(name, 'unrecorded')}" for name in VERSIONS)
        now = ", ".join(f"{name} {document[name]}" for name in VERSIONS)
        sys.stderr.write(
            "the counts differ from docs/validation/skos-preflabel-results.json "
            f"(recorded with {then}; now {now}): a change of rule, manifest or parser is evidence to review, "
            "so run `count` and read the diff\n"
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
