import os
import shutil
import uuid
from contextlib import asynccontextmanager

from fastapi import (
    BackgroundTasks,
    Depends,
    FastAPI,
    File,
    HTTPException,
    UploadFile,
    status,
)
from sqlalchemy.orm import Session

from app.database import get_db, init_db
from app.models import JobStatus, ValidationJob
from app.schemas import (
    JobCreateResponse,
    JobStatusResponse,
    ValidationReportResponse,
)
from app.validator import process_validation_job

UPLOAD_DIR = os.getenv("UPLOAD_DIR", "./uploads")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ensure database tables and upload directory exist on application startup
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    init_db()
    yield


app = FastAPI(
    title="GTFS Validator Microservice",
    version="1.0.0",
    description=(
        "Asynchronous GTFS relational integrity and syntax validation service "
        "built with FastAPI, SQLAlchemy, and standard Python libraries."
    ),
    lifespan=lifespan,
)


@app.get("/health", tags=["Health"])
def health_check() -> dict[str, str]:
    """Health check endpoint for container orchestrators and readiness probes."""
    return {"status": "healthy"}


@app.post(
    "/api/v1/jobs",
    response_model=JobCreateResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Validation Jobs"],
)
async def create_validation_job(
    file: UploadFile = File(..., description="GTFS zip archive file"),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: Session = Depends(get_db),
) -> JobCreateResponse:
    """
    Upload a GTFS zip archive to queue an asynchronous validation job.
    Relational and syntax checks are run in the background.
    """
    original_filename = file.filename or "unknown.zip"
    if not (original_filename.lower().endswith(".zip") or original_filename.lower().endswith(".gtfs")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file format. Uploaded file must be a .zip or .gtfs archive.",
        )

    job_id = str(uuid.uuid4())
    safe_stored_filename = f"{job_id}_{os.path.basename(original_filename)}"
    destination_path = os.path.join(UPLOAD_DIR, safe_stored_filename)

    # Save uploaded file safely in chunks to avoid high memory consumption
    try:
        with open(destination_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to persist uploaded file: {str(exc)}",
        )
    finally:
        await file.close()

    # Create record in database
    job = ValidationJob(
        id=job_id,
        filename=original_filename,
        status=JobStatus.QUEUED,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    # Schedule validation as a background task
    background_tasks.add_task(process_validation_job, job_id, destination_path)

    return JobCreateResponse.model_validate(job)


@app.get(
    "/api/v1/jobs/{job_id}",
    response_model=JobStatusResponse,
    tags=["Validation Jobs"],
)
def get_job_status(
    job_id: str,
    db: Session = Depends(get_db),
) -> JobStatusResponse:
    """Get the current processing status of a validation job."""
    job = db.query(ValidationJob).filter(ValidationJob.id == job_id).first()
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Validation job with id '{job_id}' not found.",
        )
    return JobStatusResponse.model_validate(job)


@app.get(
    "/api/v1/jobs/{job_id}/report",
    response_model=ValidationReportResponse,
    tags=["Validation Jobs"],
)
def get_validation_report(
    job_id: str,
    db: Session = Depends(get_db),
) -> ValidationReportResponse:
    """
    Retrieve the detailed validation report for a job.
    Returns HTTP 409 Conflict if the validation job is still queued or in progress.
    """
    job = db.query(ValidationJob).filter(ValidationJob.id == job_id).first()
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Validation job with id '{job_id}' not found.",
        )

    if job.status in (JobStatus.QUEUED, JobStatus.PROCESSING):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Validation job '{job_id}' is still in status '{job.status.value}'. Please retry shortly.",
        )

    details = job.report_details or {}
    return ValidationReportResponse(
        job_id=job.id,
        filename=job.filename,
        status=job.status,
        created_at=job.created_at,
        finished_at=job.finished_at,
        is_valid=details.get("is_valid", False),
        error_summary=job.error_summary or details.get("error_summary"),
        files_found=details.get("files_found", []),
        errors=details.get("errors", []),
        warnings=details.get("warnings", []),
        stats=details.get("stats", {}),
    )
