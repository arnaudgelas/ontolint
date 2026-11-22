"""Count SHQ001-SHQ003 findings on pinned production shapes graphs (issue #208, docs/validation/shq-scope.md).

    uv run python scripts/shq_scope_count.py fetch DIR     # check every repository out at its pinned commit (network)
    uv run python scripts/shq_scope_count.py count DIR     # lint every shapes file, rewrite the results and the page
    uv run python scripts/shq_scope_count.py check DIR     # fail if the counts differ from the recorded results
    uv run python scripts/shq_scope_count.py render        # rewrite the page's generated part from the results

No file is committed: ``docs/validation/shq-scope-corpus.json`` names each repository by URL, commit and licence, and
``fetch`` refuses a checkout whose commit differs (a commit hash covers every byte under it).  A *shapes file* is a
``.ttl`` file of at most 5 MiB that rdflib parses as Turtle and that has a node shape, a property shape or a subject of
``sh:path``; other files are not counted.  Each is linted with the SHQ rules as ``--shapes`` against an empty data
graph, as ``docs/severity-decisions.md`` ("Reproduce") does for the W3C corpus.

What is counted, per file, answers the question of issue #208, whether the widened scope is noisy on real shapes:

* ``judged``: the property shapes SHQ001 and SHQ002 judged before issue #63 (typed ``sh:PropertyShape`` or a value of
  ``sh:property``); ``targeted``: the subjects of ``sh:path`` that are not node shapes, are not ``judged`` and have a
  target of their own, which #63 added.  ``SHQ001`` and ``SHQ002`` are the findings the rules report, ``SHQ001_new``
  and ``SHQ002_new`` the shapes of ``targeted`` that lack the annotation.  The split is counted apart from the rule and
  checked against it: the rule reports one finding per shape without the annotation, except that blank nodes with the
  same content share one, so its count lies between the IRI shapes and all the shapes that lack it.
* ``SHQ003`` is the widened condition's findings; ``SHQ003_narrow`` those the nine parameters 0.12.0 listed would
  report over the same shapes (a deactivated shape is left out of both, so the difference is the parameters alone).
* ``extra_parameters``: for the shapes the widening adds, how many carry each parameter (a shape counts for every
  parameter it carries), so the driver of the added findings shows.
* ``strict_flip``: 1 when the file has no finding of the SHQ family but the extra SHQ003 ones, so the widening alone
  is what makes ``--profile strict`` (which fails on any info finding) fail it on these rules.

The results are a snapshot of one ontolint version: ``docs/releasing.md`` runs ``check`` at every release and
``.github/workflows/corpus.yml`` weekly between releases (advisory, issue #214).
"""

# ruff: noqa: S603, S607 -- runs git on fixed HTTPS URLs and a commit hash of the manifest.

from __future__ import annotations

import argparse
import json
import logging
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "docs" / "validation" / "shq-scope-corpus.json"
RESULTS = ROOT / "docs" / "validation" / "shq-scope-results.json"
PAGE = ROOT / "docs" / "validation" / "shq-scope.md"
BEGIN, END = "<!-- shq_scope_count.py: begin -->", "<!-- shq_scope_count.py: end -->"
COMMIT = re.compile(r"[0-9a-f]{40}")
ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*")
MAX_BYTES = 5 * 1024 * 1024
FIELDS = (
    "node_shapes",
    "judged",
    "targeted",
    "SHQ001",
    "SHQ001_new",
    "SHQ002",
    "SHQ002_new",
    "SHQ003",
    "SHQ003_narrow",
    "strict_flip",
)


def load_manifest(path: Path = MANIFEST) -> list[dict[str, str]]:
    """The repositories of the corpus; refuses one that is not pinned to a commit, licensed or safely named."""
    repositories: list[dict[str, str]] = json.loads(path.read_text(encoding="utf-8"))["repositories"]
    seen: set[str] = set()
    for repo in repositories:
        if not ID.fullmatch(repo["id"]) or repo["id"] in seen:
            raise ValueError(f"{repo['id']!r}: an id is a plain file name, given once")
        seen.add(repo["id"])
        if not repo["url"].startswith("https://") or not COMMIT.fullmatch(repo["commit"]) or not repo["licence"]:
            raise ValueError(f"{repo['id']}: a repository has an https URL, a 40-hex commit and a licence")
    return repositories


def fetch(directory: Path, repositories: list[dict[str, str]]) -> None:
    """Check every repository out at its commit into ``directory/<id>`` unless that commit is already there."""
    for repo in repositories:
        target = directory / repo["id"]
        if not (target / ".git").is_dir():
            target.mkdir(parents=True, exist_ok=True)
            for argv in (
                ["init", "-q"],
                ["fetch", "-q", "--depth", "1", repo["url"], repo["commit"]],
                ["checkout", "-q", "FETCH_HEAD"],
            ):
                subprocess.run(["git", "-C", str(target), *argv], check=True)
        head = subprocess.run(
            ["git", "-C", str(target), "rev-parse", "HEAD"], check=True, capture_output=True, text=True
        ).stdout.strip()
        if head != repo["commit"]:
            raise SystemExit(f"{repo['id']}: checked out {head}, the manifest pins {repo['commit']}")
        print(f"{repo['id']}: {head}", flush=True)


def _named(terms: Any) -> set[Any]:
    from rdflib import BNode, URIRef  # noqa: PLC0415

    return {t for t in terms if isinstance(t, URIRef | BNode)}


def _shapes(graph: Any) -> tuple[set[Any], set[Any], set[Any]]:
    """The node shapes, the property shapes SHQ001 judged before issue #63 and the targeted ones it judges since."""
    from rdflib import RDF  # noqa: PLC0415
    from rdflib.namespace import SH  # noqa: PLC0415

    nodes = set(graph.subjects(RDF.type, SH.NodeShape))
    judged = set(graph.subjects(RDF.type, SH.PropertyShape)) | _named(graph.objects(None, SH.property))
    targets = {
        s
        for target in (SH.targetClass, SH.targetNode, SH.targetSubjectsOf, SH.targetObjectsOf)
        for s in graph.subjects(target, None)
    }
    return nodes, judged, (_named(graph.subjects(SH.path, None)) & targets) - nodes - judged


def _narrow_parameters() -> frozenset[Any]:
    """The nine parameters SHQ003 read in 0.12.0."""
    from rdflib.namespace import SH  # noqa: PLC0415

    return frozenset(
        (SH.minCount, SH.maxCount, SH.datatype, SH["class"], SH.pattern, SH["in"], SH.node, SH["not"], SH.sparql)
    )


def _deactivated(graph: Any, shape: Any) -> bool:
    from rdflib import Literal  # noqa: PLC0415
    from rdflib.namespace import SH, XSD  # noqa: PLC0415

    objects = graph.objects(shape, SH.deactivated)
    return any(isinstance(o, Literal) and o.datatype == XSD.boolean and o.value is True for o in objects)


def _extra_parameters(graph: Any, judged_shapes: set[Any]) -> dict[str, int]:
    """Per parameter, the shapes the widened SHQ003 reports that the nine parameters of 0.12.0 would not.

    A shape counts for every widened parameter it carries (``sh:nodeKind``, ``sh:minInclusive`` and so on), so the
    sum can exceed the number of shapes.
    """
    from rdflib.namespace import SH  # noqa: PLC0415

    from ontolint.rules import shapes  # noqa: PLC0415

    declares, is_boolean = shapes._declares_constraint, shapes._is_boolean  # noqa: SLF001
    wide = (*shapes.CONSTRAINT_PREDICATES, SH.qualifiedValueShape)
    narrow = _narrow_parameters()
    carried: Counter[str] = Counter()
    for shape in judged_shapes:
        predicates = set(graph.predicates(shape, None))
        if (shape, SH.message, None) in graph or predicates & narrow or not declares(graph, shape):
            continue
        named = [p for p in wide if p in predicates]
        named += [p for p in shapes.SWITCH_PREDICATES if any(not is_boolean(o, False) for o in graph.objects(shape, p))]
        carried.update("sh:" + str(p).removeprefix(str(SH)) for p in named)
    return dict(sorted(carried.items()))


def count_graph(graph: Any) -> dict[str, Any] | None:
    """The :data:`FIELDS` of one parsed shapes graph and its ``extra_parameters``, or ``None`` if it has no shape."""
    from rdflib import Graph, URIRef  # noqa: PLC0415
    from rdflib.namespace import SH  # noqa: PLC0415

    from ontolint import Linter  # noqa: PLC0415

    nodes, judged, targeted = _shapes(graph)
    if not (nodes or judged or targeted or set(graph.subjects(SH.path, None))):
        return None
    findings = Linter(Graph(), shapes=graph).execute(["SHQ"]).findings
    by_rule = Counter(f.rule for f in findings)
    counts: dict[str, Any] = {"node_shapes": len(nodes), "judged": len(judged), "targeted": len(targeted)}
    for rule, predicate in (("SHQ001", SH.name), ("SHQ002", SH.description)):
        lacking = {s for s in judged | targeted if (s, predicate, None) not in graph}
        iris = {s for s in lacking if isinstance(s, URIRef)}
        if not len(iris) <= by_rule[rule] <= len(lacking):
            raise ValueError(f"{rule}: {by_rule[rule]} findings for {len(iris)} IRI shapes and {len(lacking)} in all")
        counts[rule] = by_rule[rule]
        counts[f"{rule}_new"] = len(lacking & targeted)
    narrow = _narrow_parameters()
    counts["SHQ003"] = by_rule["SHQ003"]
    counts["SHQ003_narrow"] = sum(
        1
        for s in nodes | judged
        if any(p in narrow for p in graph.predicates(s, None))
        and (s, SH.message, None) not in graph
        and not _deactivated(graph, s)
    )
    extra = counts["SHQ003"] - counts["SHQ003_narrow"]
    counts["strict_flip"] = int(extra > 0 and len(findings) - extra == 0)
    counts["extra_parameters"] = _extra_parameters(graph, nodes | judged)
    return counts


def shapes_files(root: Path) -> list[Path]:
    """The ``.ttl`` files under ``root`` outside ``.git``, sorted, none a link or over the size cap."""
    return sorted(
        p
        for p in root.rglob("*.ttl")
        if ".git" not in p.parts and p.is_file() and not p.is_symlink() and p.stat().st_size <= MAX_BYTES
    )


def count_repository(root: Path) -> dict[str, dict[str, Any]]:
    """The counts of every shapes file of the checkout ``root``, by path relative to it."""
    from rdflib import Graph  # noqa: PLC0415

    logging.disable(logging.CRITICAL)  # rdflib logs a lexical form it cannot convert; the corpus is data, not ours
    found: dict[str, dict[str, Any]] = {}
    for path in shapes_files(root):
        graph = Graph()
        try:
            graph.parse(path, format="turtle")
        except Exception:  # noqa: BLE001, S112 -- not Turtle that rdflib reads: not a shapes file of the corpus
            continue
        if (counted := count_graph(graph)) is not None:
            found[path.relative_to(root).as_posix()] = counted
    return found


def measure(directory: Path, repositories: list[dict[str, str]]) -> dict[str, Any]:
    """The results document: per repository, its pinned commit and the counts of each shapes file."""
    from importlib.metadata import version  # noqa: PLC0415

    return {
        "ontolint": version("ontolint"),
        "repositories": [
            {"id": repo["id"], "commit": repo["commit"], "files": count_repository(directory / repo["id"])}
            for repo in repositories
        ],
    }


def totals(files: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """The sum of each field over ``files``, their number and the widened parameters added up."""
    parameters: Counter[str] = Counter()
    for counted in files.values():
        parameters.update(counted["extra_parameters"])
    return {
        "files": len(files),
        **{name: sum(f[name] for f in files.values()) for name in FIELDS},
        "extra_parameters": dict(sorted(parameters.items())),
    }


def _share(part: int, whole: int) -> str:
    return "n/a" if whole == 0 else f"{100 * part / whole:.1f}%"


def render(results: dict[str, Any]) -> str:
    """The generated part of the page: a table per question, a row per repository and a total."""
    repositories = results["repositories"]
    rows = [(r["id"], totals(r["files"])) for r in repositories]
    every = {f"{r['id']}/{path}": counted for r in repositories for path, counted in r["files"].items()}
    rows.append(("**all**", totals(every)))
    judged = [
        "| Repository | Shapes files | Node shapes | Property shapes judged before | Targeted only (new) | SHQ001 "
        "| of which new | SHQ002 | of which new |",
        "| --- " * 9 + "|",
    ]
    noise = [
        "| Repository | SHQ003 (wide) | SHQ003 (0.12.0 set) | Added by the widening | Per shape | "
        "Files the widening alone fails under `strict` |",
        "| --- " * 6 + "|",
    ]
    for name, t in rows:
        judged.append(
            f"| {name} | {t['files']} | {t['node_shapes']} | {t['judged']} | {t['targeted']} | {t['SHQ001']} | "
            f"{t['SHQ001_new']} | {t['SHQ002']} | {t['SHQ002_new']} |"
        )
        extra = t["SHQ003"] - t["SHQ003_narrow"]
        noise.append(
            f"| {name} | {t['SHQ003']} | {t['SHQ003_narrow']} | +{extra} ({_share(extra, t['SHQ003_narrow'])}) | "
            f"{_share(t['SHQ003'], t['node_shapes'] + t['judged'])} | {t['strict_flip']} of {t['files']} |"
        )
    parameters = rows[-1][1]["extra_parameters"]
    driver = ["| Parameter | Shapes it adds a finding for |", "| --- | --- |"]
    driver += [f"| `{name}` | {count} |" for name, count in sorted(parameters.items(), key=lambda kv: (-kv[1], kv[0]))]
    return "\n".join(
        [
            "### SHQ001 and SHQ002",
            "",
            *judged,
            "",
            "### SHQ003",
            "",
            "*Per shape* is SHQ003's findings over the node and property shapes.",
            "",
            *noise,
            "",
            "### What the widening adds",
            "",
            "A shape counts for each widened parameter it carries.",
            "",
            *driver,
        ]
    )


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
    """The results without the ontolint version: ``check`` compares what was counted, not who counted it."""
    return {k: v for k, v in document.items() if k != "ontolint"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Count SHQ001-SHQ003 findings on pinned production shapes graphs.")
    parser.add_argument("command", choices=("fetch", "count", "check", "render"))
    parser.add_argument("directory", nargs="?", type=Path, help="where the repositories are checked out")
    args = parser.parse_args(argv)
    repositories = load_manifest()
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
        sys.stderr.write("the counts differ from docs/validation/shq-scope-results.json; run `count` and review\n")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
