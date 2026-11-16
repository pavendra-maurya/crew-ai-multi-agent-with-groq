import uuid
from fastapi import FastAPI, Depends, Header, HTTPException, BackgroundTasks, status
from fastapi.responses import StreamingResponse

from .config import settings
from .schemas import TriageRequest, JobSubmissionResponse, JobDetailResponse
from .event_bus import job_manager
from .crew_hierarchy import execute_hierarchical_crew

app = FastAPI(
    title="Hierarchical Multi-Agent Triage Service (CrewAI + Groq + MCP + A2A)",
    description="Root Coordinator Agent orchestrating an Internal MCP Worker and an External A2A Agent.",
    version="2.0.0",
)


def verify_internal_api_key(x_api_key: str = Header(..., description="Internal gateway API key")) -> None:
    if x_api_key != settings.internal_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-API-Key",
        )


@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "groq_model": settings.groq_model,
        "external_a2a_endpoint": settings.external_a2a_endpoint,
    }


@app.post(
    "/api/v1/triage",
    response_model=JobSubmissionResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(verify_internal_api_key)],
)
async def submit_triage_job(payload: TriageRequest, background_tasks: BackgroundTasks):
    job_id = f"inc-{uuid.uuid4().hex[:10]}"
    job_manager.create_job(job_id)

    background_tasks.add_task(
        execute_hierarchical_crew,
        job_id=job_id,
        service_name=payload.service_name,
        alert_description=payload.alert_description,
    )

    return JobSubmissionResponse(
        job_id=job_id,
        status="queued",
        stream_url=f"/api/v1/triage/{job_id}/stream",
        status_url=f"/api/v1/triage/{job_id}",
    )


@app.get(
    "/api/v1/triage/{job_id}",
    response_model=JobDetailResponse,
    dependencies=[Depends(verify_internal_api_key)],
)
async def get_triage_status(job_id: str):
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job ID not found")
    return job


@app.get(
    "/api/v1/triage/{job_id}/stream",
    dependencies=[Depends(verify_internal_api_key)],
)
async def stream_triage_events(job_id: str):
    if not job_manager.get_job(job_id):
        raise HTTPException(status_code=404, detail="Job ID not found")
    return StreamingResponse(
        job_manager.stream_events(job_id),
        media_type="text/event-stream",
    )
