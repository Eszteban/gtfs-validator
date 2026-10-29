import io
import os
import zipfile

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.database as database
import app.validator as validator
from app.database import Base
from app.main import app
from app.models import JobStatus


@pytest.fixture(autouse=True)
def setup_test_db(tmp_path, monkeypatch):
    # Set up isolated SQLite database per test run
    db_file = tmp_path / "test_gtfs.db"
    test_db_url = f"sqlite:///{db_file}"
    test_engine = create_engine(
        test_db_url,
        connect_args={"check_same_thread": False},
    )
    TestingSessionLocal = sessionmaker(
        autocommit=False, autoflush=False, bind=test_engine
    )

    Base.metadata.create_all(bind=test_engine)

    # Point upload dir to temp path during tests
    upload_test_dir = str(tmp_path / "uploads")
    os.makedirs(upload_test_dir, exist_ok=True)
    monkeypatch.setattr("app.main.UPLOAD_DIR", upload_test_dir)

    # Monkeypatch session factories
    monkeypatch.setattr(database, "engine", test_engine)
    monkeypatch.setattr(database, "SessionLocal", TestingSessionLocal)
    monkeypatch.setattr(validator, "SessionLocal", TestingSessionLocal)

    yield

    Base.metadata.drop_all(bind=test_engine)
    test_engine.dispose()


@pytest.fixture
def client():
    return TestClient(app)


def create_sample_gtfs_zip(corrupt_fk: bool = False) -> io.BytesIO:
    """Helper to create a minimal in-memory GTFS zip archive."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        # agency.txt
        zf.writestr(
            "agency.txt",
            "agency_id,agency_name,agency_url,agency_timezone\n"
            "AG1,Demo Transit,http://example.com,Europe/Budapest\n",
        )
        # stops.txt
        zf.writestr(
            "stops.txt",
            "stop_id,stop_name,stop_lat,stop_lon\n"
            "STOP1,Central Station,47.4979,19.0402\n"
            "STOP2,North Gate,47.5000,19.0500\n",
        )
        # routes.txt
        zf.writestr(
            "routes.txt",
            "route_id,route_short_name,route_long_name,route_type\n"
            "R1,100,City Express,3\n",
        )
        # trips.txt
        invalid_route = "NON_EXISTENT_ROUTE" if corrupt_fk else "R1"
        zf.writestr(
            "trips.txt",
            "trip_id,route_id,service_id\n"
            f"T1,{invalid_route},WEEKDAY\n",
        )
        # stop_times.txt
        zf.writestr(
            "stop_times.txt",
            "trip_id,stop_id,stop_sequence\n"
            "T1,STOP1,1\n"
            "T1,STOP2,2\n",
        )
        # calendar.txt
        zf.writestr(
            "calendar.txt",
            "service_id,monday,tuesday,wednesday,thursday,friday,saturday,sunday,start_date,end_date\n"
            "WEEKDAY,1,1,1,1,1,0,0,20260101,20261231\n",
        )
    buffer.seek(0)
    return buffer


def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


def test_upload_non_zip_file_rejected(client):
    response = client.post(
        "/api/v1/jobs",
        files={"file": ("test.txt", b"plain text", "text/plain")},
    )
    assert response.status_code == 400
    assert "Invalid file format" in response.json()["detail"]


def test_gtfs_validation_flow_valid(client):
    zip_buf = create_sample_gtfs_zip(corrupt_fk=False)
    response = client.post(
        "/api/v1/jobs",
        files={"file": ("valid_gtfs.zip", zip_buf, "application/zip")},
    )
    assert response.status_code == 201
    job_data = response.json()
    assert "id" in job_data
    assert job_data["filename"] == "valid_gtfs.zip"
    job_id = job_data["id"]

    # In TestClient, BackgroundTasks executes before request completes
    status_resp = client.get(f"/api/v1/jobs/{job_id}")
    assert status_resp.status_code == 200
    status_data = status_resp.json()
    assert status_data["status"] == JobStatus.COMPLETED.value
    assert status_data["finished_at"] is not None

    # Check report
    report_resp = client.get(f"/api/v1/jobs/{job_id}/report")
    assert report_resp.status_code == 200
    report_data = report_resp.json()
    assert report_data["is_valid"] is True
    assert len(report_data["errors"]) == 0
    assert "stops.txt" in report_data["files_found"]
    assert report_data["stats"]["stops.txt_records"] == 2


def test_gtfs_validation_flow_relational_error(client):
    zip_buf = create_sample_gtfs_zip(corrupt_fk=True)
    response = client.post(
        "/api/v1/jobs",
        files={"file": ("invalid_gtfs.zip", zip_buf, "application/zip")},
    )
    assert response.status_code == 201
    job_id = response.json()["id"]

    # Check report
    report_resp = client.get(f"/api/v1/jobs/{job_id}/report")
    assert report_resp.status_code == 200
    report_data = report_resp.json()
    assert report_data["is_valid"] is False
    assert len(report_data["errors"]) > 0

    fk_errors = [e for e in report_data["errors"] if e["code"] == "FOREIGN_KEY_VIOLATION"]
    assert len(fk_errors) > 0
    assert "NON_EXISTENT_ROUTE" in fk_errors[0]["message"]


def test_job_not_found(client):
    response = client.get("/api/v1/jobs/non-existent-id")
    assert response.status_code == 404


def test_metrics_endpoint(client):
    response = client.get("/metrics")
    assert response.status_code == 200
    content = response.text
    assert "gtfs_validation_jobs_total" in content
    assert "gtfs_validation_duration_seconds" in content
    assert "gtfs_validation_errors_total" in content
