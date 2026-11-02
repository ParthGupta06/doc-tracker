"""Validate against the pinned proposed pod schema, including optional drift fields."""
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[2]
DOCUMENT = yaml.safe_load((ROOT / 'docs/contract/pod-contract.openapi.yml').read_text())


def validate(value: Any, component: str) -> None:
    schema = {'$ref': f'#/components/schemas/{component}', 'components': DOCUMENT['components']}
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(value)
