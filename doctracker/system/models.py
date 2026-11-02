"""Shared request/response schemas (Phase 2, Section 5.2)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictStr

REPOSITORY_PATTERN = r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})/[A-Za-z0-9._-]{1,100}$"
COMMIT_PATTERN = r"^[0-9a-fA-F]{7,40}$"

ChangeCategory = Literal["IMPLEMENTATION", "DESIGN", "ARCHITECTURE", "SPECIFICATION", "REQUIREMENT", "DOCUMENTATION", "OTHER"]
ChangeType = Literal["ADDED", "MODIFIED", "DELETED", "RENAMED", "COPIED", "TYPE_CHANGED"]


class AnalysisRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    repository: StrictStr = Field(pattern=REPOSITORY_PATTERN, description="GitHub repository as owner/name")
    commit_id: StrictStr = Field(pattern=COMMIT_PATTERN, description="Head commit SHA (7-40 hex)")
    base_commit: StrictStr | None = Field(default=None, pattern=COMMIT_PATTERN,
                                          description="Base commit SHA; defaults to the first parent of commit_id")


class Change(BaseModel):
    path: str
    old_path: str | None = None
    change_type: ChangeType
    category: ChangeCategory


class Skipped(BaseModel):
    path: str
    reason: Literal["UNSUPPORTED_FILE_TYPE"]


class Finding(BaseModel):
    finding_id: str
    issue_type: Literal["MISSING_DOCUMENTATION", "OUTDATED_DOCUMENTATION", "ORPHANED_DOCUMENTATION",
                        "UNDOCUMENTED_SYMBOL", "STALE_SIGNATURE", "STALE_VALUE", "STALE_REFERENCE"]
    code_file: str
    documentation_file: str
    change_category: ChangeCategory
    fact: str | None
    explanation: str
    verification_status: Literal["PENDING_REVIEW"]


class ErrorBody(BaseModel):
    code: str
    message: str


class AnalysisResult(BaseModel):
    analysis_id: str
    repository: str
    head_commit: str
    base_commit: str | None
    config_version: str
    tool_version: str
    status: Literal["SUCCESS", "ERROR"]
    error: ErrorBody | None
    issues: list[Finding]
    changes: list[Change]
    skipped: list[Skipped]
    unmapped: list[str]
    created_at: str


class TestSetupRequest(BaseModel):
    session_id: StrictStr = Field(min_length=1, max_length=200)
    setup: dict[str, Any] = Field(default_factory=dict)
