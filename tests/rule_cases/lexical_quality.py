"""Cases for LEX010-LEX017, LEX019, LEX020 and LEX022-LEX024."""

from __future__ import annotations

from rule_harness import rule_cases, ttl

CASES = {
    "LEX010": rule_cases(
        [
            ttl("camelCase label equals local name", 'ex:hasPart a owl:ObjectProperty ; rdfs:label "hasPart" .'),
            ttl("underscore label equals local name", 'ex:has_part a owl:ObjectProperty ; rdfs:label "has_part" .'),
        ],
        [
            ttl("spaced label", 'ex:hasPart a owl:ObjectProperty ; rdfs:label "has part" .'),
            ttl("single word equal to local name", 'ex:Person a owl:Class ; rdfs:label "Person" .'),
        ],
    ),
    "LEX011": rule_cases(
        [
            ttl("newline", 'ex:A a owl:Class ; rdfs:label "a\\nb" .'),
            ttl("double space", 'ex:A a owl:Class ; rdfs:label "a  b" .'),
            ttl("tab", 'ex:A a owl:Class ; skos:prefLabel "a\\tb" .'),
        ],
        [
            ttl("single spaces", 'ex:A a owl:Class ; rdfs:label "a b" .'),
            ttl("padding is LEX005", 'ex:A a owl:Class ; rdfs:label " a " .'),
        ],
    ),
    "LEX012": rule_cases(
        [
            ttl("period", 'ex:A a owl:Class ; rdfs:label "Thing." .'),
            ttl("colon", 'ex:A a owl:Class ; rdfs:label "Thing:"@en .'),
        ],
        [
            ttl("clean", 'ex:A a owl:Class ; rdfs:label "Thing" .'),
            ttl("inner punctuation", 'ex:A a owl:Class ; rdfs:label "a.b" .'),
        ],
    ),
    "LEX013": rule_cases(
        [
            ttl("IRI label", "ex:A a owl:Class ; rdfs:label ex:B ."),
            ttl("blank-node definition", "ex:A a owl:Class ; skos:definition [] ."),
        ],
        [
            ttl("literals", 'ex:A a owl:Class ; rdfs:label "A" ; rdfs:comment "An A." .'),
            ttl("rdf:value node", 'ex:A a owl:Class ; skos:definition [ rdf:value "An A." ] .'),
            ttl("rdf:value IRI", 'ex:A a owl:Class ; skos:definition ex:d . ex:d rdf:value "An A." .'),
        ],
    ),
    "LEX014": rule_cases(
        [
            ttl("integer label", "ex:A a owl:Class ; rdfs:label 5 ."),
            ttl("custom datatype", 'ex:A a owl:Class ; rdfs:label "x"^^ex:custom .'),
        ],
        [
            ttl("plain", 'ex:A a owl:Class ; rdfs:label "A" .'),
            ttl("tagged", 'ex:A a owl:Class ; rdfs:label "A"@en .'),
            ttl("explicit xsd:string", 'ex:A a owl:Class ; rdfs:label "A"^^xsd:string .'),
        ],
    ),
    "LEX015": rule_cases(
        [ttl("altLabel equals prefLabel", 'ex:A a owl:Class ; skos:prefLabel "Car"@en ; skos:altLabel "car"@en .')],
        [
            ttl("different text", 'ex:A a owl:Class ; skos:prefLabel "Car" ; skos:altLabel "Auto" .'),
            ttl("other language", 'ex:A a owl:Class ; skos:prefLabel "Car"@en ; skos:altLabel "Car"@fr .'),
        ],
    ),
    "LEX016": rule_cases(
        [
            ttl(
                "synonym is another term's label",
                'ex:A a owl:Class ; rdfs:label "Car" . ex:B a owl:Class ; skos:altLabel "Car" .',
            )
        ],
        [
            ttl("distinct", 'ex:A a owl:Class ; rdfs:label "Car" . ex:B a owl:Class ; skos:altLabel "Auto" .'),
            ttl(
                "other language", 'ex:A a owl:Class ; rdfs:label "Car"@en . ex:B a owl:Class ; skos:altLabel "Car"@fr .'
            ),
            ttl("empty alt label", 'ex:A a owl:Class ; rdfs:label "" . ex:B a owl:Class ; skos:altLabel "" .'),
        ],
    ),
    "LEX017": rule_cases(
        [ttl("definition equals label", 'ex:A a owl:Class ; rdfs:label "Car" ; rdfs:comment "car" .')],
        [ttl("real definition", 'ex:A a owl:Class ; rdfs:label "Car" ; rdfs:comment "A wheeled vehicle." .')],
    ),
    "LEX019": rule_cases(
        [
            ttl("empty", 'ex:A a owl:Class ; rdfs:comment "" .'),
            ttl("whitespace", 'ex:A a owl:Class ; skos:definition "  " .'),
        ],
        [ttl("text", 'ex:A a owl:Class ; rdfs:comment "text" .'), ttl("absent", "ex:A a owl:Class .")],
    ),
    "LEX020": rule_cases(
        [
            ttl(
                "same definition twice",
                'ex:A a owl:Class ; rdfs:comment "A thing." . ex:B a owl:Class ; rdfs:comment "a  thing." .',
            )
        ],
        [
            ttl("different", 'ex:A a owl:Class ; rdfs:comment "One." . ex:B a owl:Class ; rdfs:comment "Two." .'),
            ttl("same term repeated", 'ex:A a owl:Class ; rdfs:comment "One." ; skos:definition "One." .'),
            ttl(
                "blank definitions are LEX019",
                'ex:A a owl:Class ; rdfs:comment "" . ex:B a owl:Class ; rdfs:comment "" .',
            ),
        ],
    ),
    "LEX022": rule_cases(
        [ttl("German label with en policy", 'ex:A a owl:Class ; rdfs:label "A"@de .', languages=("en",))],
        [
            ttl("allowed", 'ex:A a owl:Class ; rdfs:label "A"@en .', languages=("en",)),
            ttl("regional variant", 'ex:A a owl:Class ; rdfs:label "A"@en-GB .', languages=("en",)),
            ttl("no policy", 'ex:A a owl:Class ; rdfs:label "A"@de .'),
            ttl("untagged", 'ex:A a owl:Class ; rdfs:label "A" .', languages=("en",)),
        ],
    ),
    "LEX023": rule_cases(
        [ttl("definition only in English", 'ex:A a owl:Class ; rdfs:comment "An A."@en .', languages=("en", "fr"))],
        [
            ttl("both", 'ex:A a owl:Class ; rdfs:comment "An A."@en, "Un A."@fr .', languages=("en", "fr")),
            ttl("no definition at all", "ex:A a owl:Class .", languages=("en", "fr")),
            ttl("no policy", 'ex:A a owl:Class ; rdfs:comment "An A."@en .'),
        ],
    ),
    "LEX024": rule_cases(
        [ttl("two definitions", 'ex:A a owl:Class ; skos:definition "One."@en, "Two."@en .')],
        [
            ttl("one per language", 'ex:A a owl:Class ; skos:definition "One."@en, "Un."@fr .'),
            ttl("multiple rdfs:comment is fine", 'ex:A a owl:Class ; rdfs:comment "One."@en, "Two."@en .'),
        ],
    ),
}
