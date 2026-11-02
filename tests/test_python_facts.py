"""Fact rules beyond the shared fixtures: signatures, references, classes, literals."""
from dataclasses import replace

import pytest

from doctracker.system.classify import load_config
from doctracker.system.detect import detect, facts, mentions
from doctracker.system.gitops import GitFailure, RawChange


class Files:
    def __init__(self, before, after, doc):
        self.before, self.after, self.doc = before, after, doc
    def read_text(self, commit, path):
        if path == 'docs/model.md':
            return self.doc
        return self.before if commit == 'base' else self.after


@pytest.mark.parametrize('before,after,doc,expected', [
    ('def predict(x): pass', 'def predict(x, *, weights=None): pass', 'predict x', [('STALE_SIGNATURE','predict.weights')]),
    ('def predict(x, y): pass', 'def predict(x): pass', 'predict x y', [('STALE_SIGNATURE','predict.y')]),
    ('class Old: pass', '', 'Old', [('STALE_REFERENCE','Old')]),
    ('', 'class New: pass', 'Newer', [('UNDOCUMENTED_SYMBOL','New')]),
    ('LIMIT=1', 'LIMIT=2', 'LIMIT 2 and 1', [('STALE_VALUE','LIMIT')]),
    ('LABEL="old"', 'LABEL="new"', 'LABEL new', []),
    ('def f(x): pass', 'def f(x): return 1', 'f', []),
])
def test_fact_delta(before,after,doc,expected):
    issues, unmapped, error = detect(Files(before,after,doc),'base','a'*40,
        [RawChange('src/model.py','MODIFIED',None),RawChange('docs/model.md','MODIFIED',None)],load_config())
    assert [(f['issue_type'],f['fact']) for f in issues] == expected
    assert unmapped == [] and error is None


def test_ast_facts_ignore_private_nested_and_never_execute():
    text = 'import os\nos.remove("do-not-execute")\n_PRIVATE=1\nPUBLIC=-2\nasync def api(x, /, y, *, flag): pass\n'
    assert facts(text) == {'PUBLIC':('constant','-2'),'api':('function',['x','y','flag'])}
    with pytest.raises(GitFailure):
        facts('def invalid(')


def test_literal_word_boundaries():
    assert mentions('`THRESHOLD`', 'THRESHOLD')
    assert not mentions('xTHRESHOLD_', 'THRESHOLD')


def test_rename_reads_old_source_and_new_mapping():
    config = load_config()
    config = replace(config,raw={**config.raw,'mappings':[{'source':'src/new.py','documentation':'docs/model.md'}]})
    files = Files('def f(x): pass','def f(x,y): pass','f x')
    issues,_,_ = detect(files,'base','a'*40,[RawChange('src/new.py','RENAMED','src/old.py')],config)
    assert [(f['issue_type'],f['fact']) for f in issues] == [('OUTDATED_DOCUMENTATION',None),('STALE_SIGNATURE','f.y')]
