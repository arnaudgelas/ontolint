"""Cases for SHQ007-SHQ027 (SHACL authoring lints); each shapes graph breaks exactly one thing."""

from __future__ import annotations

from rule_harness import Case, rule_cases, with_shapes

DATA = "ex:A a owl:Class ."
NODE = "ex:S a sh:NodeShape ; sh:targetClass ex:A ; "


def _c(name: str, shapes: str, data: str = DATA, **options: object) -> Case:
    return with_shapes(name, data, shapes, **options)


def _prop(body: str) -> str:
    """A targeted node shape with one property shape ``ex:P`` carrying ``body``."""
    return NODE + f"sh:property ex:P .\nex:P sh:path ex:p ; {body} ."


GOOD = _c("well-formed shapes", _prop("sh:minCount 1 ; sh:maxCount 2 ; sh:datatype xsd:string"))
ANY_CHECK_FREE = _c("empty shapes graph", "")


def _list_case(predicate: str, members: str) -> str:
    return NODE + f"{predicate} {members} ."


CASES = {
    "SHQ007": rule_cases(
        [
            _c("min above max", _prop("sh:minCount 3 ; sh:maxCount 2")),
            _c("max zero", _prop("sh:minCount 1 ; sh:maxCount 0")),
            _c("leading-zero lexical form", _prop('sh:minCount "03"^^xsd:integer ; sh:maxCount 2')),
            _c("derived integer types", _prop('sh:minCount "3"^^xsd:int ; sh:maxCount "2"^^xsd:nonNegativeInteger')),
            _c("on a node shape", NODE + "sh:minCount 3 ; sh:maxCount 2 ."),
        ],
        [
            GOOD,
            _c("min equals max", _prop("sh:minCount 2 ; sh:maxCount 2")),
            _c("only min", _prop("sh:minCount 5")),
            _c("only max", _prop("sh:maxCount 0")),
            _c("several min values are not compared", _prop("sh:minCount 3, 4 ; sh:maxCount 2")),
            _c("decimal bound is left to SHQ008", _prop("sh:minCount 3.0 ; sh:maxCount 2")),
            _c("ill-typed bound is left to SHQ008", _prop('sh:minCount "x3"^^xsd:integer ; sh:maxCount 2')),
        ],
    ),
    "SHQ008": rule_cases(
        [
            _c("negative", _prop("sh:minCount -1")),
            _c("negative max", _prop("sh:maxCount -2")),
            _c("decimal", _prop("sh:minCount 1.0")),
            _c("double", _prop("sh:maxCount 1e0")),
            _c("string", _prop('sh:minCount "1"')),
            _c("boolean", _prop("sh:minCount true")),
            _c("IRI", _prop("sh:maxCount ex:one")),
            _c("ill-typed integer", _prop('sh:minCount "one"^^xsd:integer')),
            _c("ill-typed derived integer", _prop('sh:minCount "-1"^^xsd:nonNegativeInteger')),
            _c("one bad value among good ones", _prop("sh:maxCount 1, -1")),
            # SHACL 4.2.1/4.2.2 and 4.4.1/4.4.2: the value is a literal with datatype xsd:integer.
            _c("derived integer type", _prop('sh:minCount "1"^^xsd:nonNegativeInteger')),
            _c("xsd:int count", _prop('sh:maxCount "1"^^xsd:int')),
            _c("xsd:unsignedByte count", _prop('sh:minCount "0"^^xsd:unsignedByte')),
            _c("negative length", _prop("sh:minLength -1")),
            _c("decimal length", _prop("sh:minLength 1.5")),
            _c("string length", _prop('sh:maxLength "2"')),
            _c("IRI length", _prop("sh:minLength ex:two")),
            _c("derived integer length", _prop('sh:maxLength "2"^^xsd:int')),
        ],
        [
            GOOD,
            _c("zero", _prop("sh:minCount 0")),
            _c("leading zero and plus sign", _prop('sh:minCount "01"^^xsd:integer ; sh:maxCount "+2"^^xsd:integer')),
            _c("lengths", _prop("sh:minLength 0 ; sh:maxLength 10")),
            _c("other numeric parameters are not judged", _prop("sh:minInclusive -1 ; sh:maxExclusive 1.5")),
        ],
    ),
    "SHQ011": rule_cases(
        [
            _c("unbalanced paren", _prop('sh:pattern "(abc"')),
            _c("inverted repetition", _prop('sh:pattern "a{2,1}"')),
            _c("unbalanced with flags", _prop('sh:pattern "[a-z" ; sh:flags "im"')),
            _c("x flag keeps the error", _prop('sh:pattern "a b (" ; sh:flags "x"')),
            _c("one bad pattern among good ones", _prop('sh:pattern "^a$", "(b"')),
            # F&O 5.6.1 over XSD Part 2 Appendix F: patterns Python compiles but XPath rejects.
            _c("word-boundary escape", _prop('sh:pattern "\\\\bword"')),
            _c("lookahead", _prop('sh:pattern "a(?=b)"')),
            _c("escaped slash", _prop('sh:pattern "^https?:\\\\/\\\\/"')),
            _c("x flag keeps a stray brace", _prop('sh:pattern "a b{" ; sh:flags "x"')),
            _c("possessive quantifier", _prop('sh:pattern "a*+"')),
            _c("category escape without braces", _prop('sh:pattern "\\\\pL"')),
            # XSD 1.0 F.1 and 1.1 G.4.1: an unescaped [ or a leading ] is not a class member in either.
            _c("unescaped [ inside a class", _prop('sh:pattern "[[:alpha:]]+"')),
            _c("leading ] in a class", _prop('sh:pattern "[]a]"')),
            _c("unknown category name", _prop('sh:pattern "\\\\p{Letter}+"')),
            _c("unbalanced group beside an XPath-only escape", _prop('sh:pattern "\\\\p{L}("')),
        ],
        [
            GOOD,
            _c("valid pattern", _prop('sh:pattern "^[a-z]+$" ; sh:flags "i"')),
            _c("xpath-only escape", _prop('sh:pattern "^\\\\p{L}+$"')),
            _c("xpath-only escapes for name characters", _prop('sh:pattern "\\\\i\\\\c*"')),
            _c("non-capturing group, reluctant quantifier, back-reference", _prop('sh:pattern "(?:(a)b)*?\\\\1"')),
            _c("q flag accepts what XPath would not", _prop('sh:pattern "\\\\bword" ; sh:flags "q"')),
            # Boundary: an unknown flag letter is SHQ015's, which reports the same shape.
            _c("unknown flag letter is SHQ015's", _prop('sh:pattern "a" ; sh:flags "z"')),
            _c("q flag makes the pattern a plain string", _prop('sh:pattern "(abc" ; sh:flags "q"')),
            _c("x flag: # is a literal, not a comment", _prop('sh:pattern "(a # b)" ; sh:flags "x"')),
            _c("character class subtraction", _prop('sh:pattern "[a-z-[aeiou]]+"')),
            _c("subtraction from a negated group", _prop('sh:pattern "[^a-[b]]"')),
            _c("subtraction after a class escape", _prop('sh:pattern "[\\\\d-[5]]"')),
            _c("quantified anchor", _prop('sh:pattern "^*a"')),
            _c("non-literal pattern", _prop("sh:pattern ex:regex")),
        ],
    ),
    "SHQ013": rule_cases(
        [_c("datatype and class", _prop("sh:datatype xsd:string ; sh:class ex:A"))],
        [GOOD, _c("class only", _prop("sh:class ex:A"))],
    ),
    "SHQ017": rule_cases(
        [
            _c("min length above max", _prop("sh:minLength 5 ; sh:maxLength 2")),
            _c("max length zero", _prop("sh:minLength 1 ; sh:maxLength 0")),
            _c("derived integer types", _prop('sh:minLength "3"^^xsd:int ; sh:maxLength "2"^^xsd:unsignedByte')),
        ],
        [
            GOOD,
            _c("equal lengths", _prop("sh:minLength 2 ; sh:maxLength 2")),
            _c("only max length", _prop("sh:maxLength 0")),
            _c("several min lengths are not compared", _prop("sh:minLength 5, 6 ; sh:maxLength 2")),
            _c("negative lengths are left to SHQ008", _prop("sh:minLength -1 ; sh:maxLength -3")),
            _c("decimal length is left to SHQ008", _prop("sh:minLength 3.0 ; sh:maxLength 2")),
        ],
    ),
    "SHQ018": rule_cases(
        [
            _c("inclusive inverted", _prop("sh:minInclusive 10 ; sh:maxInclusive 1")),
            _c("equal but exclusive", _prop("sh:minExclusive 3 ; sh:maxInclusive 3")),
            _c("equal, both exclusive", _prop("sh:minExclusive 3 ; sh:maxExclusive 3.0")),
            _c("decimal vs integer", _prop("sh:minInclusive 2.5 ; sh:maxExclusive 2")),
            _c("double vs integer", _prop("sh:minInclusive 1e1 ; sh:maxInclusive 2")),
            _c("one lower bound conflicts", _prop("sh:minInclusive 1, 5 ; sh:maxInclusive 3")),
            _c(
                "minus infinity, exclusive",
                _prop('sh:minInclusive "-INF"^^xsd:double ; sh:maxExclusive "-INF"^^xsd:float'),
            ),
            _c("on a node shape", NODE + "sh:minInclusive 10 ; sh:maxInclusive 1 ."),
        ],
        [
            GOOD,
            _c("single point", _prop("sh:minInclusive 3 ; sh:maxInclusive 3")),
            _c("non-numeric bounds are not compared", _prop('sh:minInclusive "b" ; sh:maxInclusive "a"')),
            _c(
                "dates are not compared",
                _prop('sh:minInclusive "2020-02-01"^^xsd:date ; sh:maxInclusive "2020-01-01"^^xsd:date'),
            ),
            _c("booleans are not compared", _prop("sh:minInclusive true ; sh:maxInclusive false")),
            _c("ill-typed bound is ignored", _prop('sh:minInclusive "ten"^^xsd:integer ; sh:maxInclusive 1')),
            _c("NaN bound is ignored", _prop('sh:minInclusive "NaN"^^xsd:double ; sh:maxInclusive 1')),
            _c("decimal promoted to double", _prop('sh:minInclusive "0.1"^^xsd:double ; sh:maxInclusive 0.1')),
            _c(
                "integer promoted to double",
                _prop('sh:minInclusive 9007199254740993 ; sh:maxInclusive "9007199254740992"^^xsd:double'),
            ),
            _c("decimal promoted to float", _prop('sh:minInclusive 0.1000000001 ; sh:maxInclusive "0.1"^^xsd:float')),
            _c("infinite single point", _prop('sh:minInclusive "INF"^^xsd:double ; sh:maxInclusive "INF"^^xsd:double')),
            _c("empty only over the integers", _prop("sh:minExclusive 1 ; sh:maxExclusive 2")),
        ],
    ),
    "SHQ019": rule_cases(
        [_c("undefined sh:node", _prop("sh:node ex:Missing"))],
        [
            GOOD,
            _c("blank node reference", _prop("sh:node [ sh:nodeKind sh:IRI ]")),
            _c("defined reference", _prop("sh:node ex:T") + "\nex:T a sh:NodeShape ; sh:nodeKind sh:IRI ."),
        ],
    ),
    "SHQ020": rule_cases(
        [_c("deactivated", NODE + "sh:deactivated true .")],
        [GOOD, _c("explicitly active", NODE + "sh:deactivated false .")],
    ),
    "SHQ021": rule_cases(
        [
            _c("floating node shape", "ex:S a sh:NodeShape ."),
            _c(
                "untargeted shape beside a targeted one",
                "ex:S a sh:NodeShape .\nex:T a sh:NodeShape ; sh:targetClass ex:A .",
            ),
        ],
        [
            GOOD,
            _c("referenced shape", NODE + "sh:node ex:T .\nex:T a sh:NodeShape ."),
            _c("implicit class target", "ex:S a sh:NodeShape, rdfs:Class ."),
            _c(
                "referenced from a list",
                NODE + "sh:or ( ex:T ex:U ) .\nex:T a sh:NodeShape .\nex:U a sh:NodeShape .",
            ),
            _c("deactivated is reported by SHQ020 instead", "ex:S a sh:NodeShape ; sh:deactivated true ."),
            _c("SHACL-AF custom target", "ex:S a sh:NodeShape ; sh:target [ a sh:SPARQLTarget ] ."),
        ],
    ),
    "SHQ024": rule_cases(
        [
            _c("closed without ignore", NODE + "sh:closed true ."),
            _c(
                "ignore list lacks rdf:type",
                NODE + "sh:closed true ; sh:ignoredProperties ( ex:q ) .",
            ),
        ],
        [
            GOOD,
            _c(
                "closed and ignoring type",
                NODE + "sh:closed true ; sh:ignoredProperties ( rdf:type ) .",
            ),
            _c("open shape", NODE + "sh:closed false ."),
            _c("rdf:type is a property shape's path", NODE + "sh:closed true ; sh:property [ sh:path rdf:type ] ."),
        ],
    ),
    "SHQ025": rule_cases(
        [
            _c("single-member or", _list_case("sh:or", "( ex:T )") + "\nex:T a sh:NodeShape ."),
        ],
        [
            GOOD,
            _c("two members", _list_case("sh:and", "( ex:T ex:U )") + "\nex:T a sh:NodeShape .\nex:U a sh:NodeShape ."),
        ],
    ),
    "SHQ026": rule_cases(
        [
            _c(
                "same path twice",
                NODE + "sh:property ex:P1, ex:P2 .\n"
                "ex:P1 sh:path ex:p ; sh:minCount 1 .\nex:P2 sh:path ex:p ; sh:datatype xsd:string .",
            )
        ],
        [
            GOOD,
            _c(
                "different paths",
                NODE + "sh:property ex:P1, ex:P2 .\n"
                "ex:P1 sh:path ex:p ; sh:minCount 1 .\nex:P2 sh:path ex:q ; sh:minCount 1 .",
            ),
            _c(
                "qualified shapes may repeat a path",
                NODE + "sh:property ex:P1, ex:P2 .\n"
                "ex:P1 sh:path ex:p ; sh:qualifiedValueShape ex:Q ; sh:qualifiedMinCount 1 .\n"
                "ex:P2 sh:path ex:p ; sh:qualifiedValueShape ex:Q ; sh:qualifiedMinCount 1 .\nex:Q a sh:NodeShape .",
            ),
        ],
    ),
    "SHQ027": rule_cases(
        [
            _c(
                "typo in target class",
                "ex:S a sh:NodeShape ; sh:targetClass ex:Typo .",
                base="https://example.test/onto#",
            )
        ],
        [
            _c("declared class", "ex:S a sh:NodeShape ; sh:targetClass ex:A .", base="https://example.test/onto#"),
            _c(
                "external class",
                "ex:S a sh:NodeShape ; sh:targetClass <http://other.test/X> .",
                base="https://example.test/onto#",
            ),
            _c("no base configured", "ex:S a sh:NodeShape ; sh:targetClass ex:Typo ."),
        ],
    ),
}
