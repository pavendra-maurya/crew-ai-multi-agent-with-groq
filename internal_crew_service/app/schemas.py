from datetime import datetime
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class TriageRequest(BaseModel):
    service_name: str = Field(..., example="auth-service")
    alert_description: str = Field(
        ...,
        example="Anomalous outbound traffic from auth-service to 185.220.101.42 after Deploy #418. Run full internal telemetry and external complex diagnostics.",
    )


class StructuredRCAReport(BaseModel):
    severity: str = Field(..., description="CRITICAL, HIGH, MEDIUM, or LOW")
    affected_service: str
    root_cause_summary: str
    internal_mcp_evidence: List[str] = Field(
        ..., description="Evidence collected by the Internal Telemetry Specialist via local MCP"
    )
    external_a2a_findings: str = Field(
        ..., description="Analysis returned by the External A2A Agent backed by the remote MCP complex server"
    )
    immediate_remediation_steps: List[str]


class JobSubmissionResponse(BaseModel):
    job_id: str
    status: JobStatus
    stream_url: str
    status_url: str


class JobDetailResponse(BaseModel):
    job_id: str
    status: JobStatus
    created_at: datetime
    completed_at: Optional[datetime] = None
    report: Optional[StructuredRCAReport] = None
    error: Optional[str] = None
