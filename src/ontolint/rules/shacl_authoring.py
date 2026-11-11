"""SHACL authoring checks over the supplied shapes graph: a documented subset of SHQ007-SHQ027.

Implemented: SHQ007, 008, 011, 013, 017-021 and 024-027.

Every check is a structural lint of the asserted shapes graph (no SHACL engine, no entailment, no
network).  Rules are skipped by the engine when no shapes graph is supplied; ``run`` is also a no-op
then.  Each check is deliberately conservative: it flags constructs that are invalid or unsatisfiable
according to the SHACL specification, or well-known authoring pitfalls, and stays silent when a value
cannot be interpreted with certainty.

A *shape* below is any subject in the shapes graph (``--shapes``) typed ``sh:NodeShape`` or
``sh:PropertyShape``, any object of ``sh:property``, or any subject of a shape parameter (``sh:path``,
``sh:minCount``, ``sh:pattern``, ``sh:minInclusive`` ...), so node and property shapes alike; the data
graph is never read.  A *natural* is a literal whose RDFLib value is a Python ``int`` other than a
boolean and is ``>= 0``: ``xsd:integer`` and its derived types (``xsd:int``, ``xsd:nonNegativeInteger``
...) in any valid XSD lexical form (``"01"``, ``"+1"``, ``" 2 "``); an ill-typed literal
(``"abc"^^xsd:integer``, ``"1.0"^^xsd:integer``), an ``xsd:decimal`` or ``xsd:double`` (``1.0``,
``1e0``), a string, a boolean and an IRI are not naturals.  Specifications of the error rules:

* **SHQ007.** A shape with exactly one ``sh:minCount`` and exactly one ``sh:maxCount``, both naturals,
  where the minimum is greater than the maximum (``3`` and ``2``; ``1`` and ``0``), derived integer
  types included (SHQ008 reports their datatype).  Excluded: equal bounds, a missing bound, several
  values for either parameter, and a bound that is not a natural (SHQ008 reports it).  Error,
  certain: no set of value nodes satisfies both, so every focus node violates the shape.
* **SHQ008.** Every value of ``sh:minCount``, ``sh:maxCount``, ``sh:minLength`` or ``sh:maxLength`` on
  a shape that is not a natural, each reported on its own: negative, decimal or double, ill-typed,
  string, boolean or IRI; and every natural whose datatype is not ``xsd:integer`` (a derived type
  such as ``xsd:int``, ``xsd:nonNegativeInteger`` or ``xsd:unsignedByte``).  A count keeps the
  message "sh:minCount value 1.0 is not a non-negative integer." (the predicate as the shapes graph's
  prefixes write it, the value's lexical form); a length, and a derived type, print the value in
  N-Triples and the predicate as ``sh:``.  Error: SHACL (sections 4.2.1, 4.2.2, 4.4.1 and 4.4.2, and
  the syntax rules of Appendix B) requires each to be a literal with datatype ``xsd:integer``, so the
  shape is ill-formed (a SHACL processor may reject the shapes graph or ignore the constraint); the
  check is deterministic, though its findings are recorded with the default confidence
  ``heuristic``.
* **SHQ011.** A literal value of ``sh:pattern`` that is not an XPath regular expression under the
  shape's ``sh:flags`` (all values concatenated).  SHACL regexes are XPath regexes (F&O 5.6.1, over
  XSD Part 2 Appendix F), so the flags are translated: ``i``, ``s`` and ``m`` map to the Python
  flags, ``x`` removes whitespace outside character classes before anything else (Python's VERBOSE
  would also read ``#`` as a comment), and ``q`` (XPath 3.0: the pattern is a plain string; SPARQL
  1.1 cites XPath 2.0, which lacks it) means every pattern is valid.  Two judgements, at most one
  finding per pattern: first, a pattern without an XPath-only escape (``\\p``, ``\\P``, ``\\i``,
  ``\\I``, ``\\c``, ``\\C``) that Python's ``re`` cannot compile, quoting Python's error ("sh:pattern
  does not compile: ..."); then, for every other pattern, the first construct a left-to-right scan
  finds that XPath does not allow ("sh:pattern is not an XPath regular expression: ..."): an escape
  outside XSD's SingleCharEsc (with XPath's ``\\$``), MultiCharEsc and ``\\p{..}``/``\\P{..}`` (``\\b``,
  ``\\A``, ``\\x41``, ``\\0``, ``\\/``), a back-reference inside a class; ``(?`` other than XPath 3.0's
  ``(?:`` (lookaround, inline flags, named groups); a ``+`` after a quantifier (possessive), any
  other quantifier after one except a single reluctant ``?``, or a quantifier with nothing to repeat;
  an unescaped ``{`` that starts no ``{n}``, ``{n,}`` or ``{n,m}``; and an unescaped ``}`` or ``]``
  outside a class.  Excluded: a non-literal value; inside a character class everything but its
  escapes (an unescaped ``[`` not after ``-``, a leading ``]``, and the placement of ``-``, on which XSD
  1.0 and 1.1 disagree; Python decides those); a ``\\p{..}`` category or block name, which is not
  checked; the XPath 2.0 / 3.0 differences beyond ``(?:`` and ``q``; and an unknown flag letter, which
  is dropped when compiling and is SHQ015's.  It can also flag a valid pattern Python rejects (a
  repetition count above 4294967295).  Error, heuristic: an invalid pattern makes the shape
  ill-formed, but a SHACL engine built on Python's or Java's regex may accept it (``\\/`` in
  particular, which JavaScript habit writes).
* **SHQ017.** As SHQ007 for ``sh:minLength`` and ``sh:maxLength``, derived integer types included.
  Excluded as for SHQ007; a length that is not a natural is SHQ008's.  Error, certain: no value node has a
  string length in the range, so every value node (and every blank node) violates the shape.
* **SHQ018.** A shape where some lower bound (``sh:minInclusive`` or ``sh:minExclusive``) and some
  upper bound (``sh:maxInclusive`` or ``sh:maxExclusive``), both numbers, admit no value: the lower
  is greater than the upper, or they are equal and either is exclusive.  A number is a non-NaN literal
  of ``xsd:decimal``, ``xsd:float``, ``xsd:double`` or an integer type; every lower bound is paired with
  every upper bound.  The pair is compared after XPath numeric promotion: two integers or decimals
  exactly, and when either is ``xsd:float`` (``xsd:double``) both are cast to float (double), so
  ``"0.1"^^xsd:double`` and ``0.1`` are equal; an ``xsd:float`` is read at single precision, and a
  number beyond a type's range becomes ``INF`` or ``-INF``, which compare as infinities.  Excluded: NaN,
  ill-typed literals, booleans, and non-numeric bounds such as dates or strings; an interval empty
  only over the integers (``sh:minExclusive 1 ; sh:maxExclusive 2``), as the value nodes' datatype is
  not considered.  Error: no value node can satisfy both bounds; deterministic, though the findings
  are recorded with the default confidence ``heuristic``.
"""

from __future__ import annotations

import math
import re
import struct
import warnings
from collections import defaultdict
from collections.abc import Callable
from decimal import Decimal
from typing import TYPE_CHECKING

from rdflib import BNode, Graph, Literal, URIRef
from rdflib.namespace import OWL, RDF, RDFS, SH, XSD
from rdflib.term import Node

from ontolint.models import Requirement, RuleBackend, RuleScope, RuleSpec, Severity

from .support import list_items, shape_term, term_text

if TYPE_CHECKING:
    from .runtime import RuleContext

type Check = Callable[["RuleContext", Graph, Node], None]

LOGICAL_PARAMETERS = (SH["and"], SH["or"], SH.xone)
TARGET_PREDICATES = (SH.targetClass, SH.targetNode, SH.targetSubjectsOf, SH.targetObjectsOf)
REFERENCE_PREDICATES = (
    SH.node,
    SH["not"],
    SH["and"],
    SH["or"],
    SH.xone,
    SH.property,
    SH.qualifiedValueShape,
)
SHAPE_PREDICATES = (
    SH.path,
    SH.property,
    SH.node,
    SH.minCount,
    SH.maxCount,
    SH.datatype,
    SH["class"],
    SH.nodeKind,
    SH.pattern,
    SH["in"],
    SH.closed,
    SH.deactivated,
    SH.severity,
    SH.minLength,
    SH.maxLength,
    SH.minInclusive,
    SH.maxInclusive,
    SH.minExclusive,
    SH.maxExclusive,
    SH.uniqueLang,
    SH.languageIn,
    SH["and"],
    SH["or"],
    SH.xone,
    SH["not"],
    SH.qualifiedValueShape,
    *TARGET_PREDICATES,
)
# XPath ``x`` is not Python's VERBOSE (which also reads ``#`` as a comment): see ``_strip_whitespace``.
REGEX_FLAGS = {"i": re.IGNORECASE, "s": re.DOTALL, "m": re.MULTILINE}
XPATH_WHITESPACE = frozenset("\t\n\r ")
# SHQ018 compares bounds after XPath numeric promotion: integer/decimal < xsd:float < xsd:double.
EXACT, FLOAT, DOUBLE = 0, 1, 2
NUMERIC_RANK: dict[URIRef | None, int] = {XSD.float: FLOAT, XSD.double: DOUBLE}
MIN_LOGICAL_MEMBERS = 2
# XPath-only regex escapes that Python cannot compile although they are valid SHACL patterns.
XPATH_ONLY_ESCAPES = re.compile(r"\\[pPiIcC]")
# XSD Part 2 Appendix F SingleCharEsc, with the ``\$`` that XPath adds, and MultiCharEsc.
XPATH_SINGLE_ESCAPES = frozenset("nrt\\|.?*+(){}-[]^$")
XPATH_MULTI_ESCAPES = frozenset("sSiIcCdDwW")
XPATH_QUANTITY = re.compile(r"\{[0-9]+(?:,[0-9]*)?\}")
_ATOM, _START, _QUANTIFIED, _RELUCTANT = range(4)  # what the scanner read last


def _spec(rule_id: str, title: str, severity: Severity, suggestion: str, category: str = "deterministic") -> RuleSpec:
    return RuleSpec(
        rule_id,
        "SHQ",
        title,
        severity,
        suggestion,
        category,
        RuleBackend.RDFLIB,
        RuleScope.SHAPES,
        "shacl_authoring",
        Requirement.SHAPES,
    )


SPECS: tuple[RuleSpec, ...] = (
    _spec(
        "SHQ007", "Shape with sh:minCount greater than sh:maxCount", Severity.ERROR, "Make sh:minCount <= sh:maxCount."
    ),
    _spec(
        "SHQ008",
        "Cardinality or length value is not a non-negative xsd:integer",
        Severity.ERROR,
        "Use a non-negative xsd:integer.",
    ),
    _spec(
        "SHQ011",
        "Invalid sh:pattern regular expression",
        Severity.ERROR,
        "Fix the sh:pattern expression (and sh:flags) so it compiles.",
        "heuristic",
    ),
    _spec(
        "SHQ013",
        "Shape combining sh:datatype and sh:class",
        Severity.WARNING,
        "Remove one: a literal cannot be an instance of a class, so the shape cannot be satisfied.",
    ),
    _spec(
        "SHQ017",
        "Shape with sh:minLength greater than sh:maxLength",
        Severity.ERROR,
        "Make sh:minLength <= sh:maxLength.",
    ),
    _spec(
        "SHQ018",
        "Shape with an empty numeric range",
        Severity.ERROR,
        "Make the lower bound smaller than the upper bound (min/max Inclusive/Exclusive).",
    ),
    _spec(
        "SHQ019",
        "sh:node or sh:property refers to an undefined shape",
        Severity.WARNING,
        "Define the referenced shape in the shapes graph or correct the IRI.",
        "heuristic",
    ),
    _spec(
        "SHQ020",
        "Deactivated shape left in the shapes graph",
        Severity.INFO,
        "Remove the shape or re-enable it; sh:deactivated true silently disables validation.",
        "heuristic",
    ),
    _spec(
        "SHQ021",
        "Node shape that is neither targeted nor referenced",
        Severity.WARNING,
        "Add a target (for example sh:targetClass) or reference the shape from another shape.",
        "heuristic",
    ),
    _spec(
        "SHQ024",
        "Closed shape that does not ignore rdf:type",
        Severity.INFO,
        "Add rdf:type to sh:ignoredProperties, otherwise every typed focus node violates the closed shape.",
        "heuristic",
    ),
    _spec(
        "SHQ025",
        "sh:and, sh:or or sh:xone with fewer than two members",
        Severity.INFO,
        "Inline the single member or add the missing alternatives; an empty sh:or can never hold.",
        "heuristic",
    ),
    _spec(
        "SHQ026",
        "Node shape with several property shapes for the same path",
        Severity.INFO,
        "Merge the property shapes that constrain the same sh:path.",
        "heuristic",
    ),
    _spec(
        "SHQ027",
        "Shape targets a local class the ontology does not declare",
        Severity.WARNING,
        "Fix the sh:targetClass IRI or declare the class in the ontology.",
        "heuristic",
    ),
)


# --- helpers ---------------------------------------------------------------------------------


def _natural(term: Node | None) -> int | None:
    """Return ``term`` as a non-negative integer, or ``None`` when it is not one."""
    if isinstance(term, Literal) and isinstance(term.value, int) and not isinstance(term.value, bool):
        return term.value if term.value >= 0 else None
    return None


def _number(term: Node) -> Decimal | float | int | None:
    """Return the numeric value of a literal (booleans excluded), or ``None``."""
    if isinstance(term, Literal) and isinstance(term.value, int | float | Decimal) and not isinstance(term.value, bool):
        return term.value
    return None


def _is_nan(number: Decimal | float) -> bool:
    if isinstance(number, int):
        return False  # math.isnan overflows on an integer beyond the double range
    return number.is_nan() if isinstance(number, Decimal) else math.isnan(number)


def _single(sg: Graph, shape: Node, predicate: URIRef) -> Node | None:
    values = list(sg.objects(shape, predicate))
    return values[0] if len(values) == 1 else None


def _shapes(sg: Graph) -> list[Node]:
    found: set[Node] = set(sg.subjects(RDF.type, SH.NodeShape)) | set(sg.subjects(RDF.type, SH.PropertyShape))
    found |= {o for o in sg.objects(None, SH.property) if isinstance(o, URIRef | BNode)}
    for predicate in SHAPE_PREDICATES:
        found |= set(sg.subjects(predicate, None))
    return sorted(found, key=str)


def _is_property_shape(sg: Graph, shape: Node) -> bool:
    return (shape, RDF.type, SH.PropertyShape) in sg or (None, SH.property, shape) in sg or (shape, SH.path, None) in sg


def _is_node_shape(sg: Graph, shape: Node) -> bool:
    return (shape, RDF.type, SH.NodeShape) in sg and not _is_property_shape(sg, shape)


def _is_true(term: Node) -> bool:
    return isinstance(term, Literal) and term.datatype == XSD.boolean and term.value is True


# --- per-shape checks ------------------------------------------------------------------------


def _ordered_pair(
    ctx: RuleContext, sg: Graph, shape: Node, bounds: tuple[URIRef, URIRef], report: tuple[str, str]
) -> None:
    lo, hi = _single(sg, shape, bounds[0]), _single(sg, shape, bounds[1])
    lo_n, hi_n = _natural(lo), _natural(hi)
    if lo_n is not None and hi_n is not None and lo_n > hi_n:
        ctx.add(report[0], shape, report[1].format(lo=lo_n, hi=hi_n), confidence="certain", subject=())


def _cardinality_order(ctx: RuleContext, sg: Graph, shape: Node) -> None:
    message = "sh:minCount {lo} exceeds sh:maxCount {hi}."
    _ordered_pair(ctx, sg, shape, (SH.minCount, SH.maxCount), ("SHQ007", message))


def _length_order(ctx: RuleContext, sg: Graph, shape: Node) -> None:
    message = "sh:minLength {lo} exceeds sh:maxLength {hi}."
    _ordered_pair(ctx, sg, shape, (SH.minLength, SH.maxLength), ("SHQ017", message))


def _integer_values(ctx: RuleContext, sg: Graph, shape: Node) -> None:
    """SHQ008: every count and length is a literal of datatype ``xsd:integer`` with a value of at least 0."""
    for predicate in (SH.minCount, SH.maxCount, SH.minLength, SH.maxLength):
        name = "sh:" + str(predicate).removeprefix(str(SH))
        for value in sg.objects(shape, predicate):
            if _natural(value) is None and predicate in (SH.minCount, SH.maxCount):
                ctx.add(
                    "SHQ008",
                    shape,
                    f"{predicate.n3(sg.namespace_manager)} value {value!s} is not a non-negative integer.",
                    subject=(predicate, shape_term(value)),
                )
            elif _natural(value) is None:
                message = f"{name} value {term_text(value)} is not a non-negative integer."
                ctx.add("SHQ008", shape, message, subject=(predicate, shape_term(value)))
            elif isinstance(value, Literal) and value.datatype != XSD.integer:
                message = f"{name} value {term_text(value)} is not of datatype xsd:integer."
                ctx.add("SHQ008", shape, message, subject=(predicate, value))


def _strip_whitespace(text: str) -> str:
    """Drop whitespace outside character classes, as the XPath ``x`` flag does (``#`` stays a literal)."""
    out: list[str] = []
    depth, escaped = 0, False
    for ch in text:
        if escaped:
            escaped = False
        elif ch == "\\":
            escaped = True
        elif ch == "[":
            depth += 1
        elif ch == "]" and depth:
            depth -= 1
        elif not depth and ch in XPATH_WHITESPACE:
            continue
        out.append(ch)
    return "".join(out)


def _escape_end(text: str, i: int, *, in_class: bool) -> tuple[str | None, int]:
    """The problem with the escape at ``text[i]`` (a backslash), and where it ends."""
    letter = text[i + 1 : i + 2]
    if letter and (letter in XPATH_SINGLE_ESCAPES or letter in XPATH_MULTI_ESCAPES):
        return None, i + 2
    if letter in ("p", "P"):
        close = text.find("}", i + 3)
        if text[i + 2 : i + 3] != "{" or close < 0:
            return f"\\{letter} is not followed by a {{name}}", i + 2
        return None, close + 1
    if letter.isdigit() and letter != "0" and not in_class:
        end = i + 2
        while end < len(text) and text[end].isdigit():
            end += 1
        return None, end  # a back-reference
    hint = "" if letter.isalnum() or not letter else f" (write {letter} without the backslash)"
    return f"the escape \\{letter} is not XPath{hint}", i + 2


def _class_end(text: str, i: int) -> tuple[str | None, int]:
    """The problem with the escapes of the character class opening at ``text[i]``, and where it ends.

    Only escapes are judged inside a class, and ``-[`` opens a subtracted class; the placement of ``-``
    and an unescaped ``[`` elsewhere are left to Python, as XSD 1.0 and 1.1 disagree on them.
    """
    end = i + 1 + (text[i + 1 : i + 2] == "^")
    end += text[end : end + 1] == "]"  # Python reads a leading ] as a member
    depth, dash = 1, False
    while end < len(text):
        char = text[end]
        if char == "\\":
            problem, end = _escape_end(text, end, in_class=True)
            if problem is not None:
                return problem, end
            dash = False
            continue
        if char == "]":
            depth -= 1
            if not depth:
                return None, end + 1
        depth += char == "[" and dash
        dash = char == "-"
        end += 1
    return None, end


def _quantifier_end(text: str, i: int, last: int, previous: int) -> tuple[str | None, int]:
    """The problem with the quantifier at ``text[i]``, after a piece of kind ``last``, and where it ends.

    ``previous`` is where the quantifier before it started, when ``last`` is one.
    """
    quantity = XPATH_QUANTITY.match(text, i) if text[i] == "{" else None
    if text[i] == "{" and quantity is None:
        return "an unescaped { starts no quantifier", i + 1
    end = quantity.end() if quantity is not None else i + 1
    if last in (_QUANTIFIED, _RELUCTANT) and text[i] == "+":
        return f"the possessive quantifier {text[previous:end]} is not XPath", end
    if last in (_QUANTIFIED, _RELUCTANT):
        return f"the quantifier {text[i:end]} follows another quantifier", end
    if last == _START:
        return f"the quantifier {text[i:end]} has nothing to repeat", end
    return None, end


def xpath_regex_problem(text: str) -> str | None:
    """The first construct of ``text`` that an XPath regular expression does not allow, or ``None``.

    The language is XSD Part 2 Appendix F's with the XPath additions of F&O 5.6.1 (``^`` and ``$``,
    reluctant quantifiers, back-references, ``\\$``) and XPath 3.0's ``(?:``.  Decided by one scan: an
    escape outside SingleCharEsc, MultiCharEsc and ``\\p{..}``/``\\P{..}`` (a back-reference only outside a
    class); ``(?`` not followed by ``:``; a quantifier after a quantifier (a ``+`` there is possessive)
    other than one reluctant ``?``, or with nothing to repeat; an unescaped ``{`` that starts no ``{n}``,
    ``{n,}`` or ``{n,m}``; and an unescaped ``}`` or ``]`` outside a class.
    """
    i, last, quantifier = 0, _START, 0
    while i < len(text):
        char = text[i]
        problem: str | None = None
        if char == "\\":
            problem, i = _escape_end(text, i, in_class=False)
            last = _ATOM
        elif char == "[":
            problem, i = _class_end(text, i)
            last = _ATOM
        elif char == "?" and last == _QUANTIFIED:
            i, last = i + 1, _RELUCTANT
        elif char in "*+?{":
            problem, end = _quantifier_end(text, i, last, quantifier)
            i, last, quantifier = end, _QUANTIFIED, i
        elif text.startswith("(?:", i):
            i, last = i + 3, _START
        elif text.startswith("(?", i):
            problem = f"the group construct {text[i : i + 3]} is not XPath"
        elif char in "}]":
            problem = f"an unescaped {char} outside a character class"
        else:
            i, last = i + 1, _START if char in "(|" else _ATOM
            continue
        if problem is not None:
            return problem
    return None


def _regex(ctx: RuleContext, sg: Graph, shape: Node) -> None:
    letters = "".join(str(flag) for flag in sg.objects(shape, SH.flags))
    if "q" in letters:
        return  # XPath 3 ``q``: the pattern is a plain string, so any pattern is valid
    flags = sum(REGEX_FLAGS[ch] for ch in set(letters) if ch in REGEX_FLAGS)
    for pattern in sg.objects(shape, SH.pattern):
        if not isinstance(pattern, Literal):
            continue
        text = _strip_whitespace(str(pattern)) if "x" in letters else str(pattern)
        if not XPATH_ONLY_ESCAPES.search(text):  # Python cannot compile those: only the scan judges them
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    re.compile(text, flags)
            except (re.error, RecursionError, OverflowError) as exc:
                message = f"sh:pattern does not compile: {exc}"
                ctx.add("SHQ011", shape, message, confidence="heuristic", subject=(pattern,))
                continue
        if (problem := xpath_regex_problem(text)) is not None:
            message = f"sh:pattern is not an XPath regular expression: {problem}."
            ctx.add("SHQ011", shape, message, confidence="heuristic", subject=(pattern,))


def _logical_members(ctx: RuleContext, sg: Graph, shape: Node) -> None:
    for predicate in LOGICAL_PARAMETERS:
        for head in sg.objects(shape, predicate):
            items = None if isinstance(head, Literal) else list_items(sg, head)
            if items is not None and len(items) < MIN_LOGICAL_MEMBERS:
                ctx.add(
                    "SHQ025",
                    shape,
                    f"{predicate.n3(sg.namespace_manager)} has {len(items)} member(s).",
                    subject=(predicate,),
                )


def _datatype_and_class(ctx: RuleContext, sg: Graph, shape: Node) -> None:
    if (shape, SH.datatype, None) in sg and (shape, SH["class"], None) in sg:
        ctx.add("SHQ013", shape, "Shape has both sh:datatype and sh:class; no value can satisfy both.")


type Bound = tuple[Decimal | float | int, int, bool]  # value, XPath promotion rank, exclusive


def _range_bounds(sg: Graph, shape: Node, inclusive: URIRef, exclusive: URIRef) -> list[Bound]:
    out: list[Bound] = []
    for predicate, strict in ((inclusive, False), (exclusive, True)):
        for value in sg.objects(shape, predicate):
            number = _number(value)
            if number is not None and not _is_nan(number):
                rank = NUMERIC_RANK.get(value.datatype, EXACT) if isinstance(value, Literal) else EXACT
                out.append((number, rank, strict))
    return out


def _promote(number: Decimal | float | int, rank: int) -> Decimal | float | int:
    """Cast ``number`` to xsd:float or xsd:double as XPath numeric promotion does; exact otherwise."""
    if rank == EXACT:
        return number
    try:
        double = float(number)
    except OverflowError:  # an integer beyond the double range
        double = math.inf if number > 0 else -math.inf
    if rank == DOUBLE or math.isinf(double):
        return double
    try:
        return struct.unpack("f", struct.pack("f", double))[0]
    except OverflowError:  # beyond the float range
        return math.copysign(math.inf, double)


def _numeric_range(ctx: RuleContext, sg: Graph, shape: Node) -> None:
    lows = _range_bounds(sg, shape, SH.minInclusive, SH.minExclusive)
    highs = _range_bounds(sg, shape, SH.maxInclusive, SH.maxExclusive)
    for low, low_rank, low_strict in lows:
        for high, high_rank, high_strict in highs:
            rank = max(low_rank, high_rank)
            # An xsd:float is first read at float precision, then promoted with its partner.
            lo = _promote(_promote(low, low_rank), rank)
            hi = _promote(_promote(high, high_rank), rank)
            if lo > hi or (lo == hi and (low_strict or high_strict)):
                ctx.add(
                    "SHQ018", shape, f"Numeric bounds {low} and {high} admit no value.", subject=(str(low), str(high))
                )


def _deactivated(ctx: RuleContext, sg: Graph, shape: Node) -> None:
    if any(_is_true(v) for v in sg.objects(shape, SH.deactivated)):
        ctx.add("SHQ020", shape, "Shape is deactivated with sh:deactivated true.")


def _closed_without_type(ctx: RuleContext, sg: Graph, shape: Node) -> None:
    if not any(_is_true(v) for v in sg.objects(shape, SH.closed)):
        return
    ignored = [list_items(sg, head) for head in sg.objects(shape, SH.ignoredProperties)]
    if not any(items is not None and RDF.type in items for items in ignored):
        ctx.add("SHQ024", shape, "Closed shape does not list rdf:type in sh:ignoredProperties.")


def _duplicate_paths(ctx: RuleContext, sg: Graph, shape: Node) -> None:
    by_path: dict[Node, list[Node]] = defaultdict(list)
    for prop in sg.objects(shape, SH.property):
        paths = list(sg.objects(prop, SH.path))
        if len(paths) == 1 and isinstance(paths[0], URIRef) and (prop, SH.qualifiedValueShape, None) not in sg:
            by_path[paths[0]].append(prop)
    for path, props in sorted(by_path.items(), key=lambda kv: str(kv[0])):
        if len(props) > 1:
            ctx.add("SHQ026", shape, f"{len(props)} property shapes constrain the same path {path!s}.", subject=(path,))


def _undefined_references(ctx: RuleContext, sg: Graph, shape: Node) -> None:
    for predicate in (SH.node, SH.property):
        for target in sg.objects(shape, predicate):
            if isinstance(target, URIRef) and (target, None, None) not in sg:
                ctx.add(
                    "SHQ019",
                    shape,
                    f"{predicate.n3(sg.namespace_manager)} refers to undefined shape {target!s}.",
                    subject=(predicate, target),
                )


def _unused_node_shape(ctx: RuleContext, sg: Graph, shape: Node, referenced: set[Node]) -> None:
    if not _is_node_shape(sg, shape) or shape in referenced:
        return
    targeted = any((shape, p, None) in sg for p in TARGET_PREDICATES)
    implicit = any((shape, RDF.type, c) in sg for c in (RDFS.Class, OWL.Class))
    if not targeted and not implicit and not any(_is_true(v) for v in sg.objects(shape, SH.deactivated)):
        ctx.add("SHQ021", shape, "Node shape has no target and no other shape refers to it.")


def _referenced_shapes(sg: Graph) -> set[Node]:
    referenced: set[Node] = set()
    for predicate in REFERENCE_PREDICATES:
        for value in sg.objects(None, predicate):
            items = list_items(sg, value) if predicate in LOGICAL_PARAMETERS else None
            referenced |= set(items) if items is not None else {value}
    return referenced


def _undeclared_targets(ctx: RuleContext, sg: Graph, shape: Node) -> None:
    if not ctx.policy.base:
        return
    for target in sg.objects(shape, SH.targetClass):
        if ctx.local(target) and target not in ctx.classes and target not in ctx.terms:
            ctx.add(
                "SHQ027",
                shape,
                f"sh:targetClass {target!s} is not declared as a class in the ontology.",
                subject=(shape_term(target),),
            )


SHAPE_CHECKS: tuple[Check, ...] = (
    _cardinality_order,
    _length_order,
    _integer_values,
    _regex,
    _logical_members,
    _datatype_and_class,
    _numeric_range,
    _deactivated,
    _closed_without_type,
    _duplicate_paths,
    _undefined_references,
    _undeclared_targets,
)


def run(ctx: RuleContext) -> None:
    """Run the SHACL authoring checks; a no-op when no shapes graph was supplied."""
    sg = ctx.shapes
    if sg is None:
        return
    referenced = _referenced_shapes(sg)
    for shape in _shapes(sg):
        for check in SHAPE_CHECKS:
            check(ctx, sg, shape)
        _unused_node_shape(ctx, sg, shape, referenced)
