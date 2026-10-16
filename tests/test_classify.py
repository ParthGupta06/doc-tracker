import pytest

from doctracker.system.classify import glob_to_regex, load_config


@pytest.mark.parametrize(
    ("path", "category"),
    [
        ("src/model.py", "IMPLEMENTATION"),
        ("deep/nested/thing.ts", "IMPLEMENTATION"),
        ("requirements/REQUIREMENTS.md", "REQUIREMENT"),
        ("pkg/REQUIREMENTS-v2.md", "REQUIREMENT"),
        ("specs/api.yaml", "SPECIFICATION"),
        ("service/openapi.json", "SPECIFICATION"),
        ("docs/architecture/overview.md", "ARCHITECTURE"),
        ("models/model_config.json", "ARCHITECTURE"),
        ("docs/design/decisions.md", "DESIGN"),
        ("docs/adr/0001.md", "DESIGN"),
        ("README.md", "OTHER"),
        ("requirements.txt", "OTHER"),
        ("assets/logo.png", "OTHER"),
    ],
)
def test_classification(path: str, category: str) -> None:
    assert load_config().classify(path) == category


def test_precedence_requirement_beats_implementation() -> None:
    assert load_config().classify("requirements/check.py") == "REQUIREMENT"


@pytest.mark.parametrize(
    ("path", "supported"),
    [("a.py", True), ("docs/x.MD", True), ("LICENSE", True), ("a.png", False), ("w.bin", False)],
)
def test_supported_files(path: str, supported: bool) -> None:
    assert load_config().is_supported(path) is supported


def test_glob_double_star_root() -> None:
    rx = glob_to_regex("**/*.py")
    assert rx.match("a.py") and rx.match("x/y/a.py") and not rx.match("a.pyc")


def test_single_star_stays_in_segment() -> None:
    rx = glob_to_regex("docs/*.md")
    assert rx.match("docs/a.md") and not rx.match("docs/sub/a.md")


def test_config_version() -> None:
    assert load_config().config_version == "mapping-v1"
