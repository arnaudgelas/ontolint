"""The package's layering, checked on its direct imports (pytest-archon).

The layers, lowest first: foundations (``models``, ``paths``, ``syntax``, ``ownership``, ``worker``,
``profiles``, ``graph``), then ``policy`` and ``context``, the rule modules, the adapters, the engine and
the output modules, and last the command line. A module may import downwards; these rules fail when
one imports upwards, which is how a rule family would come to depend on the CLI or on a report format.
"""

from __future__ import annotations

from pytest_archon import archrule

PACKAGE = "ontolint"

# What no module below the command line may import.
ENTRY_POINTS = ("ontolint.cli", "ontolint.__main__")
PIPELINE = (
    "ontolint.cli",
    "ontolint.engine",
    "ontolint.linter",
    "ontolint.reporting",
    "ontolint.baseline",
    "ontolint.loader",
    "ontolint.imports",
    "ontolint.library",
    "ontolint.datasets",
    "ontolint.source_locations",
    "ontolint.selection",
    "ontolint.rule_info",
    "ontolint.adapters",
    "ontolint.adapters.*",
)


def test_foundations_import_no_other_module_of_the_package() -> None:
    (
        archrule("foundations import nothing of the package", comment="models, paths, syntax and friends are leaves")
        .match(
            "ontolint.models",
            "ontolint.paths",
            "ontolint.syntax",
            "ontolint.ownership",
            "ontolint.worker",
            "ontolint.profiles",
            "ontolint._version",
            "ontolint.graph.*",
        )
        .exclude("ontolint.graph")
        .should_not_import("ontolint.*")
        .check(PACKAGE, only_direct_imports=True, skip_type_checking=True)
    )


def test_policy_and_context_import_only_foundations() -> None:
    (
        archrule("policy and context sit just above the foundations")
        .match("ontolint.policy", "ontolint.context")
        .should_not_import(*PIPELINE, "ontolint.rules", "ontolint.rules.*")
        .check(PACKAGE, only_direct_imports=True, skip_type_checking=True)
    )


def test_rule_modules_do_not_depend_on_the_pipeline() -> None:
    (
        archrule("rules judge a graph", comment="a rule family never reaches the CLI, the engine or a report format")
        .match("ontolint.rules", "ontolint.rules.*")
        .should_not_import(*PIPELINE)
        .check(PACKAGE, only_direct_imports=True, skip_type_checking=True)
    )


def test_adapters_do_not_depend_on_the_engine_or_the_cli() -> None:
    (
        archrule("adapters wrap one backend each")
        .match("ontolint.adapters.*")
        .should_not_import(
            "ontolint.cli", "ontolint.engine", "ontolint.linter", "ontolint.reporting", "ontolint.baseline"
        )
        .check(PACKAGE, only_direct_imports=True, skip_type_checking=True)
    )


def test_the_engine_does_not_depend_on_the_cli_or_the_linter_facade() -> None:
    (
        archrule("the engine runs rules")
        .match("ontolint.engine")
        .should_not_import("ontolint.cli", "ontolint.linter", "ontolint.baseline", "ontolint.reporting.*")
        .check(PACKAGE, only_direct_imports=True, skip_type_checking=True)
    )


def test_only_the_entry_points_import_the_command_line() -> None:
    (
        archrule("the CLI is the top layer", comment="``ontolint.ontolint`` is the historical entry point")
        .match("ontolint.*")
        .exclude(*ENTRY_POINTS, "ontolint.ontolint")
        .should_not_import("ontolint.cli")
        .check(PACKAGE, only_direct_imports=True, skip_type_checking=True)
    )


def test_the_package_does_not_import_its_test_or_development_tools() -> None:
    (
        archrule("runtime code carries no development dependency")
        .match("ontolint", "ontolint.*")
        .should_not_import("pytest", "pytest.*", "hypothesis", "hypothesis.*", "pytest_archon", "tests", "tests.*")
        .check(PACKAGE, only_direct_imports=True)
    )
