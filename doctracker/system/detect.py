"""Static, deterministic prose detector from the proposed pod v2.4.0 / v1.1 rules."""
from __future__ import annotations

import ast
import hashlib
import re
from typing import Any, TypeGuard

from doctracker.system.classify import MappingConfig
from doctracker.system.gitops import GitFailure, RawChange, Workspace


def valid_path(value: Any) -> TypeGuard[str]:
    return (isinstance(value, str) and bool(value) and not value.startswith('/')
            and '\\' not in value and not any(ord(c) < 32 for c in value)
            and all(p not in ('', '.', '..') for p in value.split('/'))
            and not any(c in value for c in '*?[]'))


def facts(text: str) -> dict[str, tuple[str, Any]]:
    """Parse module-level facts only; never import or execute untrusted code."""
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError, RecursionError) as exc:
        raise GitFailure('mapped Python source could not be parsed') from exc
    result: dict[str, tuple[str, Any]] = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not node.name.startswith('_'):
            args = node.args.posonlyargs + node.args.args + node.args.kwonlyargs
            result[node.name] = ('function', [a.arg for a in args])
        elif isinstance(node, ast.ClassDef) and not node.name.startswith('_'):
            result[node.name] = ('class', None)
        elif isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
            if re.fullmatch(r'[A-Z][A-Z0-9_]*', name):
                # Single literal values, including signed numeric literals; no expressions/calls.
                value = node.value
                if isinstance(value, ast.Constant) or (isinstance(value, ast.UnaryOp)
                        and isinstance(value.op, (ast.USub, ast.UAdd)) and isinstance(value.operand, ast.Constant)):
                    try:
                        result[name] = ('constant', repr(ast.literal_eval(value)))
                    except (ValueError, TypeError):
                        pass
    return result


def mentions(text: str, token: str) -> bool:
    return re.search(r'(?<![A-Za-z0-9_])' + re.escape(token) + r'(?![A-Za-z0-9_])', text) is not None


def literal_token(value: str) -> str:
    return value[1:-1] if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'" else value


def detect(ws: Workspace, base: str | None, head: str, raw: list[RawChange],
           config: MappingConfig) -> tuple[list[dict[str, Any]], list[str], dict[str, str] | None]:
    issues: list[dict[str, Any]] = []
    unmapped: list[str] = []
    mappings = config.raw.get('mappings')
    if not isinstance(mappings, list):
        raise GitFailure('invalid mapping configuration')
    links: dict[str, str] = {}
    for entry in mappings:
        source = entry.get('source') if isinstance(entry, dict) else None
        doc = entry.get('documentation') if isinstance(entry, dict) else None
        if not valid_path(source) or not valid_path(doc) or source == doc:
            raise GitFailure('invalid mapping configuration')
        if source in links and links[source] != doc:
            raise GitFailure('conflicting mapping configuration')
        links[source] = doc
    changed = {c.path for c in raw}
    error = None

    def finding(kind: str, source: str, doc: str, fact: str | None = None) -> None:
        identity = f"{head}|{kind}|{source}|{doc}|{fact or ''}"
        issues.append({'finding_id': 'fnd-' + hashlib.sha256(identity.encode()).hexdigest()[:16],
                       'issue_type': kind, 'code_file': source, 'documentation_file': doc,
                       'change_category': 'IMPLEMENTATION', 'fact': fact,
                       'explanation': f'{kind}: {source} -> {doc}' + (f' ({fact})' if fact else '')
                                      + '; human review required.',
                       'verification_status': 'PENDING_REVIEW'})

    for change in sorted(raw, key=lambda c: (c.path, c.old_path or '')):
        source = change.path
        if config.classify(source) != 'IMPLEMENTATION':
            continue
        doc = links.get(source)
        if doc is None:
            if change.change_type != 'DELETED':
                unmapped.append(source)
            continue
        if not config.is_supported(doc):
            error = {'code': 'MAPPING_UNSUPPORTED', 'message': f'mapped document {doc} has an unsupported extension'}
            continue
        doc_text = ws.read_text(head, doc)
        if change.change_type == 'DELETED':
            if doc_text is not None:
                finding('ORPHANED_DOCUMENTATION', source, doc)
            continue
        if doc_text is None:
            finding('MISSING_DOCUMENTATION', source, doc)
            continue
        if doc not in changed:
            finding('OUTDATED_DOCUMENTATION', source, doc)
        if not source.endswith('.py'):
            continue
        head_text = ws.read_text(head, source)
        if head_text is None:
            raise GitFailure('changed mapped source is unavailable')
        before = facts(ws.read_text(base, change.old_path or source) or '') if base else {}
        after = facts(head_text)
        for name in sorted(after.keys() - before.keys()):
            if not mentions(doc_text, name):
                finding('UNDOCUMENTED_SYMBOL', source, doc, name)
        for name in sorted(before.keys() - after.keys()):
            if mentions(doc_text, name):
                finding('STALE_REFERENCE', source, doc, name)
        for name in sorted(before.keys() & after.keys()):
            old_kind, old_value = before[name]
            kind, value = after[name]
            if kind == old_kind == 'function':
                for param in sorted(set(value) - set(old_value)):
                    if not mentions(doc_text, param):
                        finding('STALE_SIGNATURE', source, doc, f'{name}.{param}')
                for param in sorted(set(old_value) - set(value)):
                    if mentions(doc_text, param):
                        finding('STALE_SIGNATURE', source, doc, f'{name}.{param}')
            elif kind == old_kind == 'constant' and value != old_value:
                if mentions(doc_text, literal_token(old_value)) or not mentions(doc_text, literal_token(value)):
                    finding('STALE_VALUE', source, doc, name)
    issues.sort(key=lambda f: (f['code_file'], f['issue_type'], f['fact'] or ''))
    return issues, sorted(unmapped), error
