from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models import JobStatus


class ValidationIssue(BaseModel):
    file: str | None = None
    line: int | None = None
    field: str | None = None
    code: str
    message: str


class JobCreateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    filename: str
    status: JobStatus
    created_at: datetime
    message: str = "Validation job created and queued"


class JobStatusResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    filename: str
    status: JobStatus
    created_at: datetime
    finished_at: datetime | None = None
    error_summary: str | None = None


class ValidationReportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    job_id: str
    filename: str
    status: JobStatus
    created_at: datetime
    finished_at: datetime | None = None
    is_valid: bool
    error_summary: str | None = None
    files_found: list[str] = Field(default_factory=list)
    errors: list[ValidationIssue] = Field(default_factory=list)
    warnings: list[ValidationIssue] = Field(default_factory=list)
    stats: dict[str, Any] = Field(default_factory=dict)

