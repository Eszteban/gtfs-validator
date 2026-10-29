import enum
import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, Text, JSON, Enum as SQLEnum
from app.database import Base


class JobStatus(str, enum.Enum):
    QUEUED = "QUEUED"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class ValidationJob(Base):
    __tablename__ = "validation_jobs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()), index=True)
    filename = Column(String(255), nullable=False)
    status = Column(
        SQLEnum(JobStatus, native_enum=False),
        default=JobStatus.QUEUED,
        nullable=False,
        index=True,
    )
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    finished_at = Column(DateTime(timezone=True), nullable=True)
    error_summary = Column(Text, nullable=True)
    report_details = Column(JSON, nullable=True)

    def __repr__(self) -> str:
        return f"<ValidationJob(id={self.id}, filename={self.filename}, status={self.status})>"

