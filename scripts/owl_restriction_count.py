"""Count OWL035 on pinned OWL 1 era RDF files (issue #196, docs/validation/owl-restrictions.md).

    uv run python scripts/owl_restriction_count.py fetch DIR   # check every repository out at its commit (network)
    uv run python scripts/owl_restriction_count.py count DIR   # parse every file, rewrite the results and the page
    uv run python scripts/owl_restriction_count.py check DIR   # fail if the counts differ from the recorded results
    uv run python scripts/owl_restriction_count.py render      # rewrite the generated part of the page

No file is committed: ``docs/validation/owl-restrictions-corpus.json`` names each repository, its directories, its
commit and its licence, and ``fetch`` refuses a checkout whose commit differs.  A *file* is a ``.owl``, ``.rdf``,
``.xml`` (RDF/XML), ``.ttl``, ``.n3`` or ``.nt`` file of at most 5 MiB that rdflib parses.  ``unparsed`` counts the
others (most are OWL/XML or functional syntax, which rdflib does not read, or RDF/XML with a malformed literal), and
``skipped`` names the files over the cap or links that are not read, so no file named like RDF is dropped silently.

The question of issue #196 is how often the OWL 1 and Protege 3 idiom "one restriction with both a minimum and a maximum
cardinality" occurs, because OWL035 reports it as an error.  Per file with at least one restriction:

* ``restrictions``: the nodes typed ``owl:Restriction``, which are the nodes OWL035 visits;
* ``several``: those with more than one constraint triple (``owl:someValuesFrom``, ``owl:allValuesFrom``,
  ``owl:hasValue``, ``owl:hasSelf`` or a cardinality), which is what OWL035 reports as "more than one constraint";
* ``min_max``: those with a minimum (``owl:minCardinality`` or ``owl:minQualifiedCardinality``) and a maximum
  (``owl:maxCardinality`` or ``owl:maxQualifiedCardinality``) together: the idiom;
* ``split_pairs``: ``owl:intersectionOf`` lists that hold a minimum restriction and a maximum restriction on the same
  property, as two restrictions: the form OWL035 accepts, counted to show what the idiom becomes in practice;
* ``owl2``: 1 when the file uses OWL 2 vocabulary (qualified cardinalities, ``owl:hasSelf``, ``owl:NamedIndividual``,
  property chains and so on), so the OWL 1 only files can be read apart;
* ``OWL035``: the findings the rule reports, checked against ``several`` and the restrictions without a constraint.

The results are a snapshot of one ontolint version.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import Counter
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pinned_repos  # noqa: E402 -- the sibling script; its directory is first on the path when this one is run

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "docs" / "validation" / "owl-restrictions-corpus.json"
RESULTS = ROOT / "docs" / "validation" / "owl-restrictions-results.json"
PAGE = ROOT / "docs" / "validation" / "owl-restrictions.md"
BEGIN, END = "<!-- owl_restriction_count.py: begin -->", "<!-- owl_restriction_count.py: end -->"
MAX_BYTES = 5 * 1024 * 1024
FORMATS = {".owl": "xml", ".rdf": "xml", ".xml": "xml", ".ttl": "turtle", ".n3": "n3", ".nt": "nt"}
VERSIONS = ("ontolint", "rdflib")  # recorded with the counts, named when a check fails, not compared
FIELDS = ("restrictions", "several", "min_max", "split_pairs", "OWL035")
NO_CONSTRAINT = "Restriction has no value, cardinality or self constraint."
SEVERAL = "Restriction has more than one constraint ("  # a message starts with its focus: match the text, not the start

load_manifest = pinned_repos.load_manifest
fetch = pinned_repos.fetch


def _vocabulary() -> dict[str, Any]:
    from rdflib.namespace import OWL  # noqa: PLC0415

    cardinality = (OWL.cardinality, OWL.minCardinality, OWL.maxCardinality)
    qualified = (OWL.qualifiedCardinality, OWL.minQualifiedCardinality, OWL.maxQualifiedCardinality)
    return {
        "constraints": (OWL.allValuesFrom, OWL.someValuesFrom, OWL.hasValue, OWL.hasSelf, *cardinality, *qualified),
        "minimum": (OWL.minCardinality, OWL.minQualifiedCardinality),
        "maximum": (OWL.maxCardinality, OWL.maxQualifiedCardinality),
        "owl2_predicates": frozenset(
            {
                *qualified,
                OWL.onClass,
                OWL.onDataRange,
                OWL.hasSelf,
                OWL.propertyChainAxiom,
                OWL.propertyDisjointWith,
                OWL.disjointUnionOf,
                OWL.hasKey,
                OWL.members,
                OWL.onDatatype,
                OWL.withRestrictions,
                OWL.datatypeComplementOf,
                OWL.annotatedSource,
                OWL.sourceIndividual,
            }
        ),
        "owl2_types": frozenset(
            {
                OWL.NamedIndividual,
                OWL.AllDisjointClasses,
                OWL.AllDisjointProperties,
                OWL.ReflexiveProperty,
                OWL.IrreflexiveProperty,
                OWL.AsymmetricProperty,
                OWL.Axiom,
                OWL.NegativePropertyAssertion,
            }
        ),
    }


def _uses_owl2(graph: Any, vocabulary: dict[str, Any]) -> bool:
    from rdflib import RDF  # noqa: PLC0415

    predicates = set(graph.predicates())
    return bool(
        predicates & vocabulary["owl2_predicates"]
        or {o for _s, o in graph.subject_objects(RDF.type)} & vocabulary["owl2_types"]
    )


def _split_pairs(graph: Any, vocabulary: dict[str, Any]) -> int:
    """The ``owl:intersectionOf`` lists with a minimum and a maximum restriction on one property."""
    from rdflib.namespace import OWL  # noqa: PLC0415

    pairs = 0
    for _owner, head in graph.subject_objects(OWL.intersectionOf):
        try:
            members = list(graph.items(head))
        except ValueError:  # a list that loops: not a list of the corpus's concern
            continue
        kinds: dict[Any, set[str]] = {}
        for member in members:
            for prop in graph.objects(member, OWL.onProperty):
                kinds.setdefault(prop, set()).update(
                    name for name in ("minimum", "maximum") if any((member, p, None) in graph for p in vocabulary[name])
                )
        pairs += sum(1 for found in kinds.values() if found == {"minimum", "maximum"})
    return pairs


def count_graph(graph: Any) -> dict[str, Any] | None:
    """The :data:`FIELDS` and ``owl2`` of one parsed graph, or ``None`` if it has no restriction."""
    from rdflib import RDF  # noqa: PLC0415
    from rdflib.namespace import OWL  # noqa: PLC0415

    from ontolint import Linter  # noqa: PLC0415

    vocabulary = _vocabulary()
    restrictions = set(graph.subjects(RDF.type, OWL.Restriction))
    if not restrictions:
        return None
    several = unconstrained = min_max = 0
    for restriction in restrictions:
        triples = sum(1 for p in vocabulary["constraints"] for _o in graph.objects(restriction, p))
        several += triples > 1
        unconstrained += triples == 0
        min_max += any((restriction, p, None) in graph for p in vocabulary["minimum"]) and any(
            (restriction, p, None) in graph for p in vocabulary["maximum"]
        )
    findings = Linter(graph).execute(["OWL035"]).findings
    reported = Counter(
        "several" if SEVERAL in f.message else "none" if f.message.endswith(NO_CONSTRAINT) else "other"
        for f in findings
    )
    # The rule gives one finding per restriction that lacks or doubles a constraint, but a blank node whose content
    # equals another's shares a finding (RuleContext.add), so the rule's count is at most the count and is zero only
    # when the count is.
    if (reported["several"] == 0) != (several == 0) or reported["several"] > several:
        raise ValueError(
            f"OWL035 reports {reported['several']} restrictions with several constraints; counted {several}"
        )
    if (reported["none"] == 0) != (unconstrained == 0) or reported["none"] > unconstrained:
        raise ValueError(f"OWL035 reports {reported['none']} restrictions without one; counted {unconstrained}")
    return {
        "restrictions": len(restrictions),
        "several": several,
        "min_max": min_max,
        "split_pairs": _split_pairs(graph, vocabulary),
        "owl2": int(_uses_owl2(graph, vocabulary)),
        "OWL035": len(findings),
    }


def rdf_files(root: Path) -> list[Path]:
    """The RDF files under ``root`` outside ``.git``, sorted, none a link or over the size cap."""
    return sorted(
        p
        for p in root.rglob("*")
        if p.suffix.lower() in FORMATS
        and ".git" not in p.parts
        and p.is_file()
        and not p.is_symlink()
        and p.stat().st_size <= MAX_BYTES
    )


def skipped_files(root: Path) -> list[str]:
    """The files named like RDF that :func:`rdf_files` leaves out (over the size cap or links), relative to ``root``."""
    read = set(rdf_files(root))
    return sorted(
        p.relative_to(root).as_posix()
        for p in root.rglob("*")
        if p.suffix.lower() in FORMATS and ".git" not in p.parts and p not in read
    )


def count_repository(root: Path) -> dict[str, Any]:
    """The counts of every RDF file of ``root`` with a restriction, how many did not parse, and which were skipped."""
    from rdflib import Graph  # noqa: PLC0415

    logging.disable(logging.CRITICAL)  # rdflib logs a lexical form it cannot convert; the corpus is data, not ours
    files: dict[str, dict[str, Any]] = {}
    parsed = unparsed = 0
    for path in rdf_files(root):
        graph = Graph()
        try:
            graph.parse(path, format=FORMATS[path.suffix.lower()])
        except Exception:  # noqa: BLE001 -- not RDF that rdflib reads in the format its name says: counted as unparsed
            unparsed += 1
            continue
        parsed += 1
        if (counted := count_graph(graph)) is not None:
            files[path.relative_to(root).as_posix()] = counted
    return {"parsed": parsed, "unparsed": unparsed, "skipped": skipped_files(root), "files": files}


def measure(directory: Path, repositories: list[dict[str, Any]]) -> dict[str, Any]:
    """The results document: per repository, its pinned commit, the file counts and the counts of each file."""
    from importlib.metadata import version  # noqa: PLC0415

    return {
        "ontolint": version("ontolint"),
        "rdflib": version("rdflib"),
        "repositories": [
            {"id": repo["id"], "commit": repo["commit"], **count_repository(directory / repo["id"])}
            for repo in repositories
        ],
    }


def totals(files: dict[str, dict[str, Any]]) -> dict[str, int]:
    """The files that have a restriction, and the sum of each field over them."""
    return {"files": len(files), **{name: sum(f[name] for f in files.values()) for name in FIELDS}}


def _table(rows: list[tuple[str, dict[str, int]]], parsed: dict[str, tuple[int, int, int]]) -> list[str]:
    lines = [
        "| Repository | RDF files parsed (not parsed, skipped) | Files with a restriction | Restrictions "
        "| Several constraints "
        "| Minimum and maximum together | Min and max as two restrictions of one intersection | OWL035 findings |",
        "| --- " * 8 + "|",
    ]
    for name, t in rows:
        ok, bad, skipped = parsed[name]
        lines.append(
            f"| {name} | {ok} ({bad}, {skipped}) | {t['files']} | {t['restrictions']} | {t['several']} "
            f"| {t['min_max']} | {t['split_pairs']} | {t['OWL035']} |"
        )
    return lines


def render(results: dict[str, Any]) -> str:
    """The generated part of the page: the counts per repository and in all, then those of OWL 1 vocabulary only."""
    sections: list[str] = []
    for title, keep in (("All files", None), ("Files that use no OWL 2 vocabulary", 0)):
        rows: list[tuple[str, dict[str, int]]] = []
        parsed: dict[str, tuple[int, int, int]] = {}
        every: dict[str, dict[str, Any]] = {}
        for repo in results["repositories"]:
            files = {p: f for p, f in repo["files"].items() if keep is None or f["owl2"] == keep}
            rows.append((repo["id"], totals(files)))
            parsed[repo["id"]] = (repo["parsed"], repo["unparsed"], len(repo["skipped"]))
            every.update({f"{repo['id']}/{p}": f for p, f in files.items()})
        rows.append(("**all**", totals(every)))
        columns = list(zip(*parsed.values(), strict=True))
        parsed["**all**"] = (sum(columns[0]), sum(columns[1]), sum(columns[2]))
        sections += [f"### {title}", "", *_table(rows, parsed), ""]
    return "\n".join(sections).rstrip("\n")


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
    parser = argparse.ArgumentParser(description="Count OWL035 findings on pinned OWL 1 era RDF files.")
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
            "the counts differ from docs/validation/owl-restrictions-results.json "
            f"(recorded with {then}; now {now}): a change of rule, manifest or parser is evidence to review, "
            "so run `count` and read the diff\n"
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
