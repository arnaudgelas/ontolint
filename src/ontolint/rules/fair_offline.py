"""Offline FAIR publishing rules: FAIR004, FAIR006, FAIR007, FAIR011 and FAIR017.

The FAIR catalogue is mostly about what happens over HTTP (does an IRI resolve, does content
negotiation return RDF, is the ontology in a registry).  Those checks need a controlled network
backend and stay ``proposed``.  The rules here are the subset that is *sound from the file alone*:
they inspect the shape of identifiers and metadata values and never claim that anything resolves.

They are publishing checks that do not apply to every ontology, so the ``FAIR`` family is *opt-in*
(see :data:`ontolint.profiles.OPT_IN_FAMILIES`): ``--select FAIR`` or ``--profile fair``.

Each rule is deliberately narrow.  ``FAIR004`` only names hosts that are known to be mutable or
local (it does not demand a persistent-identifier service, because institutional domains are often
fine).  ``FAIR006`` flags only licence values that are not IRIs, or IRIs outside a table of well-known
licence families.  ``FAIR007`` compares a version IRI with its ontology IRI.  ``FAIR011`` validates
ORCID iD and ROR identifier syntax and checksum, not whether they exist.  ``FAIR017`` needs a
``owl:deprecated`` ontology.
"""

from __future__ import annotations

import ipaddress
import re
from typing import TYPE_CHECKING

from rdflib import Graph, Literal, URIRef
from rdflib.namespace import DC, DCTERMS, OWL, XSD
from rdflib.term import Node

from ontolint.models import RuleBackend, RuleScope, RuleSpec, Severity

from .support import META_LICENSE, safe_urlsplit

if TYPE_CHECKING:
    from .runtime import RuleContext

_OBO = "http://purl.obolibrary.org/obo/"
_PAV = "http://purl.org/pav/"
_PROV = "http://www.w3.org/ns/prov#"
_SCHEMA = ("http://schema.org/", "https://schema.org/")

MAX_QUOTE = 80  # Characters of a value quoted in a message.
ORCID_DIGITS = 16  # An ORCID iD has 15 digits and one check character.
ORCID_MODULUS = 11  # ISO 7064 mod 11-2.
ROR_MODULUS = 97  # ISO 7064 mod 97-10.
ROR_BASE = 32  # Crockford base 32.
ROR_CHECK_BASE = 98
ROR_SCALE = 100

# Hosts (and their sub-domains) that serve files from a repository or a drive: the content behind
# the IRI changes with the repository, which is the opposite of a persistent identifier.
MUTABLE_HOSTS = (
    "raw.githubusercontent.com",
    "gist.githubusercontent.com",
    "githubusercontent.com",
    "github.com",
    "github.io",
    "gitlab.com",
    "gitlab.io",
    "bitbucket.org",
    "bitbucket.io",
    "docs.google.com",
    "drive.google.com",
    "dropbox.com",
    "dl.dropboxusercontent.com",
    "localhost",
)
LOCAL_SCHEMES = frozenset({"file"})

# Well-known licence families (host without ``www.`` and path prefix); scheme is ignored.
KNOWN_LICENSE_PREFIXES = (
    "spdx.org/licenses/",
    "creativecommons.org/licenses/",
    "creativecommons.org/publicdomain/",
    "opensource.org/licenses/",
    "opensource.org/license/",
    "gnu.org/licenses/",
    "gnu.org/copyleft/",
    "apache.org/licenses/",
    "mozilla.org/mpl/",
    "mozilla.org/en-us/mpl/",
    "w3.org/consortium/legal/",
    "opendatacommons.org/licenses/",
    "opendefinition.org/licenses/",
    "purl.org/net/rdflicense/",
    "nationalarchives.gov.uk/doc/open-government-licence",
    "eclipse.org/legal/epl",
)
LICENSE_PREDICATES = (
    *META_LICENSE,
    *(URIRef(ns + "license") for ns in _SCHEMA),
    URIRef("http://www.w3.org/1999/xhtml/vocab#license"),
)

MUTABLE_VERSION_TOKENS = frozenset(
    {"latest", "master", "main", "current", "head", "dev", "develop", "trunk", "snapshot", "nightly", "unstable"}
)

SUCCESSOR_PREDICATES = (DCTERMS.isReplacedBy, URIRef(_OBO + "IAO_0100001"), URIRef(_PAV + "hasCurrentVersion"))
PREDECESSOR_PREDICATES = (DCTERMS.replaces, OWL.priorVersion)

PERSON_PREDICATES = (
    DCTERMS.creator,
    DCTERMS.contributor,
    DC.creator,
    DC.contributor,
    URIRef(_PROV + "wasAttributedTo"),
    URIRef(_PAV + "createdBy"),
    URIRef(_PAV + "authoredBy"),
    URIRef(_PAV + "contributedBy"),
    URIRef(_PAV + "curatedBy"),
    *(URIRef(ns + p) for ns in _SCHEMA for p in ("author", "creator", "contributor")),
)

ORCID_URL = re.compile(r"https?://(?:www\.)?orcid\.org/(.*)", re.DOTALL)
ORCID_IN_TEXT = re.compile(r"orcid\.org/([^\s,;<>()\[\]\"']*)", re.IGNORECASE)
ORCID_SHAPE = re.compile(r"[0-9]{4}-[0-9]{4}-[0-9]{4}-[0-9]{3}[0-9X]")
ORCID_BARE = re.compile(r"(?<![0-9-])[0-9]{4}-[0-9]{4}-[0-9]{4}-[0-9]{3}[0-9Xx](?![0-9-])")
ROR_URL = re.compile(r"https?://(?:www\.)?ror\.org/(.*)", re.DOTALL)
ROR_IN_TEXT = re.compile(r"ror\.org/([^\s,;<>()\[\]\"']*)", re.IGNORECASE)
ROR_SHAPE = re.compile(r"0[0-9a-hjkmnp-tv-z]{6}[0-9]{2}")
CROCKFORD = "0123456789abcdefghjkmnpqrstvwxyz"


def _spec(rule_id: str, title: str, severity: Severity, suggestion: str) -> RuleSpec:
    return RuleSpec(
        rule_id,
        "FAIR",
        title,
        severity,
        suggestion,
        "context-dependent",
        RuleBackend.RDFLIB,
        RuleScope.ONTOLOGY,
        "fair_offline",
    )


SPECS: tuple[RuleSpec, ...] = (
    _spec(
        "FAIR004",
        "Ontology or version IRI on a mutable or local host instead of a persistent identifier",
        Severity.WARNING,
        "Mint the IRI under a persistent-identifier service (w3id.org, purl.org, doi.org) or a domain you control.",
    ),
    _spec(
        "FAIR006",
        "Licence given as a text literal or as an IRI outside the well-known licence families",
        Severity.INFO,
        "Point dcterms:license at a licence IRI such as https://spdx.org/licenses/CC-BY-4.0 or a Creative Commons URL.",
    ),
    _spec(
        "FAIR007",
        "Version IRI equal to the ontology IRI, with a floating marker, or without a version token",
        Severity.WARNING,
        "Give each release its own immutable owl:versionIRI containing a version or date, never latest or main.",
    ),
    _spec(
        "FAIR011",
        "Creator or contributor identifier that is not a well-formed ORCID iD or ROR identifier",
        Severity.WARNING,
        "Use the full ORCID iD (https://orcid.org/0000-0002-1825-0097) or ROR id; check the digits and checksum.",
    ),
    _spec(
        "FAIR017",
        "Deprecated ontology or version without a pointer to its successor",
        Severity.WARNING,
        "Add dcterms:isReplacedBy (or obo:IAO_0100001) to the deprecated ontology, naming its replacement.",
    ),
)


def run(ctx: RuleContext) -> None:
    """Run the offline FAIR rules."""
    _persistent_iris(ctx)
    _licenses(ctx)
    _versions(ctx)
    _person_identifiers(ctx)
    _deprecated_ontologies(ctx)


def _quote(text: str) -> str:
    return repr(text if len(text) <= MAX_QUOTE else text[:MAX_QUOTE] + "...")


def _version_iris(ctx: RuleContext, ontology: Node) -> list[URIRef]:
    return sorted((v for v in ctx.g.objects(ontology, OWL.versionIRI) if isinstance(v, URIRef)), key=str)


# --- FAIR004 -----------------------------------------------------------------------------------


def _mutable_reason(iri: str) -> str | None:
    parts = safe_urlsplit(iri)
    if parts.scheme.lower() in LOCAL_SCHEMES:
        return "a local file"
    host = (parts.hostname or "").lower()
    if not host:
        return None
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        return "a bare IP address"
    if any(host == h or host.endswith("." + h) for h in MUTABLE_HOSTS):
        return f"the mutable host {host}"
    return None


def _persistent_iris(ctx: RuleContext) -> None:
    for ontology in sorted(ctx.ontologies, key=str):
        for kind, iri in (
            ("Ontology IRI", ontology),
            *(("Version IRI", v) for v in _version_iris(ctx, ontology)),
        ):
            reason = _mutable_reason(str(iri))
            if reason:
                ctx.add(
                    "FAIR004",
                    ontology,
                    f"{kind} {iri} is on {reason}, not a persistent identifier.",
                    confidence="certain",
                    subject=(iri,),
                )


# --- FAIR006 -----------------------------------------------------------------------------------


def _known_license(iri: str) -> bool:
    parts = safe_urlsplit(iri)
    host = (parts.hostname or "").lower().removeprefix("www.")
    return parts.scheme.lower() in {"http", "https"} and f"{host}{parts.path}".lower().startswith(
        KNOWN_LICENSE_PREFIXES
    )


def _licenses(ctx: RuleContext) -> None:
    for ontology in sorted(ctx.ontologies, key=str):
        for predicate in LICENSE_PREDICATES:
            for value in sorted(ctx.g.objects(ontology, predicate), key=str):
                if isinstance(value, Literal) and str(value).strip():
                    ctx.add(
                        "FAIR006",
                        ontology,
                        f"Licence {_quote(str(value))} is a text literal, not a licence IRI.",
                        confidence="certain",
                        subject=(value,),
                    )
                elif isinstance(value, URIRef) and not _known_license(str(value)):
                    ctx.add(
                        "FAIR006",
                        ontology,
                        f"Licence IRI {value} is outside the well-known licence families.",
                        subject=(value,),
                    )


# --- FAIR007 -----------------------------------------------------------------------------------


def _tokens(iri: str) -> frozenset[str]:
    parts = safe_urlsplit(iri)
    return frozenset(t for t in re.split(r"[^a-z0-9]+", f"{parts.path} {parts.query} {parts.fragment}".lower()) if t)


def _same_iri(a: str, b: str) -> bool:
    return a.rstrip("#/") == b.rstrip("#/")


def _versions(ctx: RuleContext) -> None:
    for ontology in sorted(ctx.ontologies, key=str):
        for version in _version_iris(ctx, ontology):
            new = _tokens(str(version)) - _tokens(str(ontology))
            if _same_iri(str(version), str(ontology)):
                message = f"Version IRI {version} is the same as the ontology IRI, so it does not identify one release."
            elif new & MUTABLE_VERSION_TOKENS:
                marker = sorted(new & MUTABLE_VERSION_TOKENS)[0]
                message = (
                    f"Version IRI {version} contains the floating marker {marker!r}, which is not tied to one release."
                )
            elif not any(any(c.isdigit() for c in t) for t in new):
                message = (
                    f"Version IRI {version} has no version or date token that distinguishes it from the ontology IRI."
                )
            else:
                continue
            ctx.add("FAIR007", ontology, message, confidence="certain", subject=(version,))


# --- FAIR011 -----------------------------------------------------------------------------------


def orcid_checksum(digits: str) -> str:
    """The ISO 7064 mod 11-2 check character for the first 15 digits of an ORCID iD."""
    total = 0
    for char in digits:
        total = (total + int(char)) * 2
    result = (12 - total % ORCID_MODULUS) % ORCID_MODULUS
    return "X" if result == ORCID_MODULUS - 1 else str(result)


def orcid_problem(tail: str) -> str | None:
    """Why ``tail`` (the part after ``orcid.org/``) is not a valid ORCID iD, or ``None`` when it is."""
    if not ORCID_SHAPE.fullmatch(tail):
        return "is not of the form dddd-dddd-dddd-dddX"
    digits = tail.replace("-", "")
    if orcid_checksum(digits[: ORCID_DIGITS - 1]) != digits[-1]:
        return "fails the ISO 7064 mod 11-2 checksum"
    return None


def ror_checksum(body: str) -> str:
    """The two-digit ISO 7064 mod 97-10 checksum of the six base-32 characters after the leading ``0``."""
    value = 0
    for char in body:
        value = value * ROR_BASE + CROCKFORD.index(char)
    return f"{ROR_CHECK_BASE - (value * ROR_SCALE) % ROR_MODULUS:02d}"


def ror_problem(tail: str) -> str | None:
    """Why ``tail`` (the part after ``ror.org/``) is not a valid ROR id, or ``None`` when it is."""
    if not ROR_SHAPE.fullmatch(tail):
        return "is not of the form 0 + six base-32 characters + two digits"
    if ror_checksum(tail[1:7]) != tail[7:]:
        return "fails the ROR checksum"
    return None


_TEXT_PATTERNS = (
    ("ORCID iD", orcid_problem, ORCID_IN_TEXT),
    ("ROR identifier", ror_problem, ROR_IN_TEXT),
)


def _identifier_problems(value: Node) -> list[tuple[str, str, str]]:
    """``(kind, identifier, problem)`` for every malformed ORCID or ROR identifier carried by ``value``."""
    text = str(value).strip()
    if isinstance(value, URIRef):
        orcid, ror = ORCID_URL.fullmatch(text), ROR_URL.fullmatch(text)
        problems = [
            *([("ORCID iD", orcid.group(1), orcid_problem(orcid.group(1)))] if orcid else []),
            *([("ROR identifier", ror.group(1), ror_problem(ror.group(1)))] if ror else []),
        ]
        return [(kind, identifier, problem) for kind, identifier, problem in problems if problem]
    if not isinstance(value, Literal):
        return []
    found: list[tuple[str, str, str]] = []
    tails = [(k, t.rstrip("."), c) for k, c, pattern in _TEXT_PATTERNS for t in pattern.findall(text)]
    for kind, tail, check in tails:
        problem = check(tail)
        if problem:
            found.append((kind, tail, problem))
    for bare in ORCID_BARE.findall(text):
        problem = orcid_problem(bare)
        if problem and not any(tail.startswith(bare) for _, tail, _ in tails):
            found.append(("ORCID iD", bare, problem))
    return found


def _person_identifiers(ctx: RuleContext) -> None:
    seen: set[tuple[Node, Node]] = set()
    for predicate in PERSON_PREDICATES:
        for subject, value in ctx.g.subject_objects(predicate):
            # gremlin: pardon[equivalent] repeats are de-duplicated by add(); blank nodes give no problems
            if not isinstance(value, URIRef | Literal) or (subject, value) in seen:
                continue
            seen.add((subject, value))
            for kind, identifier, problem in _identifier_problems(value):
                ctx.add(
                    "FAIR011",
                    subject,
                    f"{kind} in {_quote(str(value))} {problem}.",
                    confidence="certain",
                    subject=(str(value), kind, identifier),
                )


# --- FAIR017 -----------------------------------------------------------------------------------


def _is_true(value: Node) -> bool:
    lexical = str(value).strip().lower()
    return isinstance(value, Literal) and (lexical == "true" or (value.datatype == XSD.boolean and lexical == "1"))


def _has_pointer(g: Graph, node: Node) -> bool:
    outgoing = any(
        not isinstance(o, Literal) or str(o).strip() for p in SUCCESSOR_PREDICATES for o in g.objects(node, p)
    )
    return outgoing or any(s != node for p in PREDECESSOR_PREDICATES for s in g.subjects(p, node))


def _deprecated_ontologies(ctx: RuleContext) -> None:
    g = ctx.g
    for ontology in sorted(ctx.ontologies, key=str):
        group: list[Node] = [ontology, *_version_iris(ctx, ontology)]
        if any(_has_pointer(g, node) for node in group):
            continue
        for node in group:
            if any(_is_true(o) for o in g.objects(node, OWL.deprecated)):
                ctx.add(
                    "FAIR017",
                    node,
                    "Deprecated ontology has no successor (dcterms:isReplacedBy or obo:IAO_0100001).",
                    confidence="certain",
                )
