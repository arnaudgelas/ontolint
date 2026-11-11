"""Cases for ONT007 and ONT008: the identities a run's documents share (``Policy.shared_identities``).

The command line finds them across files (:mod:`ontolint.declarations`); here they are given directly, the
way the CLI hands them to the file they are reported on.  :mod:`tests.test_duplicate_ids` reads the four
places from files.
"""

from __future__ import annotations

from rule_harness import Case, rule_cases, ttl

from ontolint.models import SharedIdentity
from ontolint.policy import Policy

ONTOLOGY = "https://example.test/onto"
HEADER = f"<{ONTOLOGY}> a owl:Ontology ; owl:versionIRI <{ONTOLOGY}/1.0> .\n"


def _shared(*shared: SharedIdentity) -> Policy:
    return Policy(shared_identities=shared)


def case(name: str, policy: Policy) -> Case:
    return ttl(name, HEADER, policy=policy)


TWO_INPUTS = ("release.ttl", "working.ttl")

CASES = {
    "ONT007": rule_cases(
        [
            case(
                "two inputs, one version IRI, different content",
                _shared(SharedIdentity(f"{ONTOLOGY}/1.0", "version", "inputs", TWO_INPUTS, identical=False)),
            ),
            case(
                "two unversioned inputs, one ontology IRI, different content",
                _shared(SharedIdentity(ONTOLOGY, "ontology", "inputs", TWO_INPUTS, identical=False)),
            ),
            case(
                "two modules of one closure",
                _shared(SharedIdentity(ONTOLOGY, "ontology", "closure", ("root.ttl", "copy.ttl"), identical=False)),
            ),
            case(
                "a closure module an import did not load",
                _shared(
                    SharedIdentity(
                        ONTOLOGY,
                        "ontology",
                        "closure",
                        ("copy.ttl", "module.ttl"),
                        identical=False,
                        unloaded=((ONTOLOGY, "module.ttl"),),
                    )
                ),
            ),
            case(
                "an --import-dir with two candidates",
                _shared(
                    SharedIdentity(
                        ONTOLOGY, "ontology", "import-dir", ("mirror/a.ttl", "mirror/b.ttl"), False, "mirror"
                    )
                ),
            ),
            case(
                "two graphs of a dataset",
                _shared(
                    SharedIdentity(
                        ONTOLOGY, "ontology", "graphs", ("(default graph)", "https://example.test/g"), False, "d.trig"
                    )
                ),
            ),
        ],
        [
            case("one file, nothing shared", Policy()),
            case(
                "identical copies are ONT008",
                _shared(SharedIdentity(ONTOLOGY, "ontology", "inputs", TWO_INPUTS, identical=True)),
            ),
        ],
    ),
    "ONT008": rule_cases(
        [
            case(
                "two inputs with identical content",
                _shared(
                    SharedIdentity(f"{ONTOLOGY}/1.0", "version", "inputs", ("copy.ttl", "release.ttl"), identical=True)
                ),
            ),
            case(
                "an --import-dir holding an identical copy",
                _shared(
                    SharedIdentity(ONTOLOGY, "ontology", "import-dir", ("mirror/a.ttl", "mirror/b.ttl"), True, "mirror")
                ),
            ),
        ],
        [
            case("one file, nothing shared", Policy()),
            case(
                "different content is ONT007",
                _shared(SharedIdentity(ONTOLOGY, "ontology", "inputs", TWO_INPUTS, identical=False)),
            ),
        ],
    ),
}
