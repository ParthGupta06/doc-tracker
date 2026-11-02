"""Independent golden oracles from the pinned proposed contract, never regenerated."""
from dataclasses import replace
from pathlib import Path

import pytest

from doctracker.system import analysis
from doctracker.system.classify import load_config
from doctracker.system.gitops import FileUnreadable, GitFailure
from doctracker.system.models import AnalysisRequest
from doctracker.system.storage import LocalStore
from doctracker.tester.suite import GOLDEN, check_schema, compare_golden
from tests.test_api import COMMITS, REPO


def run(tag: str, tmp_path: Path) -> dict:
    return analysis.run_analysis(AnalysisRequest(repository=REPO, commit_id=COMMITS[tag]), LocalStore(str(tmp_path)))


@pytest.mark.parametrize('case', list(GOLDEN))
def test_exact_golden(case: str, tmp_path: Path) -> None:
    request = AnalysisRequest(repository=REPO, **GOLDEN[case]['request'])
    result = analysis.run_analysis(request, LocalStore(str(tmp_path)))
    check_schema(result)
    compare_golden(result, case, findings=True)
    assert LocalStore(str(tmp_path)).load(result['analysis_id']) == result


def test_repeatable_finding_ids(tmp_path: Path) -> None:
    runs = [run('c1-impl-only', tmp_path) for _ in range(5)]
    assert len({r['analysis_id'] for r in runs}) == 5
    assert runs[0]['issues']
    assert all(r['issues'] == runs[0]['issues'] for r in runs)


def test_incorrect_coupdate_detects_stale_literal(tmp_path: Path) -> None:
    result = run('c9-incorrect-doc', tmp_path)
    assert [(f['issue_type'], f['fact']) for f in result['issues']] == [('STALE_VALUE', 'THRESHOLD')]


def test_binary_document_never_claims_success(tmp_path: Path) -> None:
    with pytest.raises(FileUnreadable):
        run('c10-unreadable-doc', tmp_path)
    assert not list(tmp_path.glob('*.json'))


@pytest.mark.parametrize('mapping', [
    {'source': 'src/model.py', 'documentation': '../escape.md'},
    {'source': 'src/model.py'},
])
def test_invalid_mapping_never_claims_success(mapping: dict, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    config = load_config()
    monkeypatch.setattr(analysis, 'load_config', lambda: replace(config, raw={**config.raw, 'mappings': [mapping]}))
    with pytest.raises(GitFailure):
        run('c1-impl-only', tmp_path)
    assert not list(tmp_path.glob('*.json'))


def test_unsupported_mapping_is_saved_error(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    config = load_config()
    monkeypatch.setattr(analysis, 'load_config', lambda: replace(config, raw={**config.raw, 'mappings': [
        {'source': 'src/model.py', 'documentation': 'assets/logo.png'}]}))
    result = run('c1-impl-only', tmp_path)
    assert result['status'] == 'ERROR' and result['error']['code'] == 'MAPPING_UNSUPPORTED'
    check_schema(result)
    assert LocalStore(str(tmp_path)).load(result['analysis_id']) == result
