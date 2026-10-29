import csv
import io
import os
import zipfile
from datetime import datetime, timezone
from typing import Any, Dict, List, Set, Tuple

from app.database import SessionLocal
from app.models import JobStatus, ValidationJob


REQUIRED_GTFS_FILES = {
    "agency.txt",
    "stops.txt",
    "routes.txt",
    "trips.txt",
    "stop_times.txt",
}

REQUIRED_COLUMNS = {
    "agency.txt": ["agency_name", "agency_url", "agency_timezone"],
    "stops.txt": ["stop_id", "stop_name", "stop_lat", "stop_lon"],
    "routes.txt": ["route_id", "route_type"],
    "trips.txt": ["route_id", "service_id", "trip_id"],
    "stop_times.txt": ["trip_id", "stop_id", "stop_sequence"],
}


def _read_csv_from_zip(
    zf: zipfile.ZipFile, filename: str
) -> Tuple[List[Dict[str, str]], List[Dict[str, Any]]]:
    """Reads a CSV file from a zip archive and returns rows and header syntax errors."""
    errors: List[Dict[str, Any]] = []
    rows: List[Dict[str, str]] = []

    try:
        with zf.open(filename, "r") as f:
            # Wrap binary stream in TextIOWrapper with utf-8-sig to strip potential UTF-8 BOM
            text_stream = io.TextIOWrapper(f, encoding="utf-8-sig", errors="replace")
            reader = csv.DictReader(text_stream)

            if reader.fieldnames is None:
                errors.append({
                    "file": filename,
                    "line": 1,
                    "field": None,
                    "code": "EMPTY_OR_INVALID_CSV",
                    "message": f"File '{filename}' is empty or has no header row.",
                })
                return rows, errors

            # Clean header whitespace
            headers = [h.strip() for h in reader.fieldnames if h]

            # Check required columns
            expected_cols = REQUIRED_COLUMNS.get(filename, [])
            for col in expected_cols:
                if col not in headers:
                    errors.append({
                        "file": filename,
                        "line": 1,
                        "field": col,
                        "code": "MISSING_REQUIRED_COLUMN",
                        "message": f"Missing required column '{col}' in '{filename}'.",
                    })

            # Special case for routes.txt: must have route_short_name OR route_long_name
            if filename == "routes.txt":
                if "route_short_name" not in headers and "route_long_name" not in headers:
                    errors.append({
                        "file": filename,
                        "line": 1,
                        "field": "route_short_name/route_long_name",
                        "code": "MISSING_ROUTE_NAME",
                        "message": "routes.txt must include at least one of 'route_short_name' or 'route_long_name'.",
                    })

            for line_no, row in enumerate(reader, start=2):
                # Clean keys and values
                clean_row = {
                    (k.strip() if k else ""): (v.strip() if v else "")
                    for k, v in row.items()
                    if k is not None
                }
                rows.append(clean_row)

    except Exception as exc:
        errors.append({
            "file": filename,
            "line": None,
            "field": None,
            "code": "FILE_READ_ERROR",
            "message": f"Could not read '{filename}': {str(exc)}",
        })

    return rows, errors


def validate_gtfs_archive(zip_path: str) -> Dict[str, Any]:
    """
    Validates a GTFS zip archive using standard zipfile and csv modules:
    - Zip integrity
    - Required file presence
    - CSV syntax & required columns
    - Data types (coordinates, sequences)
    - Relational integrity across files (Foreign Keys)
    """
    errors: List[Dict[str, Any]] = []
    warnings: List[Dict[str, Any]] = []
    stats: Dict[str, Any] = {}
    files_found: List[str] = []

    if not os.path.exists(zip_path):
        return {
            "is_valid": False,
            "error_summary": "Archive file not found on disk.",
            "files_found": [],
            "errors": [{
                "file": None,
                "line": None,
                "field": None,
                "code": "FILE_NOT_FOUND",
                "message": "Uploaded zip file cannot be found.",
            }],
            "warnings": [],
            "stats": {},
        }

    if not zipfile.is_zipfile(zip_path):
        return {
            "is_valid": False,
            "error_summary": "The uploaded file is not a valid zip archive.",
            "files_found": [],
            "errors": [{
                "file": None,
                "line": None,
                "field": None,
                "code": "INVALID_ZIP_ARCHIVE",
                "message": "File is not a valid zip archive.",
            }],
            "warnings": [],
            "stats": {},
        }

    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            all_names = zf.namelist()
            # Map canonical base names (e.g. 'stops.txt') to actual entry names in zip
            name_map: Dict[str, str] = {}
            for name in all_names:
                base = os.path.basename(name)
                if base:
                    name_map[base] = name

            files_found = sorted(list(name_map.keys()))
            stats["total_files_in_zip"] = len(files_found)

            # 1. Check required files
            for req in REQUIRED_GTFS_FILES:
                if req not in name_map:
                    errors.append({
                        "file": req,
                        "line": None,
                        "field": None,
                        "code": "MISSING_REQUIRED_FILE",
                        "message": f"Mandatory GTFS file '{req}' is missing from the archive.",
                    })

            # Check service calendar files
            if "calendar.txt" not in name_map and "calendar_dates.txt" not in name_map:
                warnings.append({
                    "file": "calendar.txt/calendar_dates.txt",
                    "line": None,
                    "field": None,
                    "code": "MISSING_CALENDAR_DATA",
                    "message": "Neither 'calendar.txt' nor 'calendar_dates.txt' was found; feed may lack active service definitions.",
                })

            parsed_data: Dict[str, List[Dict[str, str]]] = {}
            for req_file in REQUIRED_GTFS_FILES.union({"calendar.txt", "calendar_dates.txt"}):
                if req_file in name_map:
                    rows, read_errors = _read_csv_from_zip(zf, name_map[req_file])
                    errors.extend(read_errors)
                    parsed_data[req_file] = rows
                    stats[f"{req_file}_records"] = len(rows)

            # 2. Syntax & Data type checks
            # stops.txt: coordinates check
            valid_stop_ids: Set[str] = set()
            if "stops.txt" in parsed_data:
                for idx, row in enumerate(parsed_data["stops.txt"], start=2):
                    stop_id = row.get("stop_id", "")
                    if stop_id:
                        valid_stop_ids.add(stop_id)
                    else:
                        errors.append({
                            "file": "stops.txt",
                            "line": idx,
                            "field": "stop_id",
                            "code": "EMPTY_PRIMARY_KEY",
                            "message": "stop_id cannot be empty.",
                        })

                    # Check lat/lon
                    lat_str = row.get("stop_lat", "")
                    lon_str = row.get("stop_lon", "")
                    try:
                        lat = float(lat_str)
                        if not (-90.0 <= lat <= 90.0):
                            errors.append({
                                "file": "stops.txt",
                                "line": idx,
                                "field": "stop_lat",
                                "code": "INVALID_COORDINATE",
                                "message": f"stop_lat '{lat_str}' out of range [-90, 90].",
                            })
                    except ValueError:
                        errors.append({
                            "file": "stops.txt",
                            "line": idx,
                            "field": "stop_lat",
                            "code": "INVALID_FLOAT",
                            "message": f"stop_lat '{lat_str}' is not a valid floating point number.",
                        })

                    try:
                        lon = float(lon_str)
                        if not (-180.0 <= lon <= 180.0):
                            errors.append({
                                "file": "stops.txt",
                                "line": idx,
                                "field": "stop_lon",
                                "code": "INVALID_COORDINATE",
                                "message": f"stop_lon '{lon_str}' out of range [-180, 180].",
                            })
                    except ValueError:
                        errors.append({
                            "file": "stops.txt",
                            "line": idx,
                            "field": "stop_lon",
                            "code": "INVALID_FLOAT",
                            "message": f"stop_lon '{lon_str}' is not a valid floating point number.",
                        })

            # routes.txt: route_type check
            valid_route_ids: Set[str] = set()
            if "routes.txt" in parsed_data:
                for idx, row in enumerate(parsed_data["routes.txt"], start=2):
                    route_id = row.get("route_id", "")
                    if route_id:
                        valid_route_ids.add(route_id)
                    else:
                        errors.append({
                            "file": "routes.txt",
                            "line": idx,
                            "field": "route_id",
                            "code": "EMPTY_PRIMARY_KEY",
                            "message": "route_id cannot be empty.",
                        })

                    route_type = row.get("route_type", "")
                    if not route_type.isdigit():
                        errors.append({
                            "file": "routes.txt",
                            "line": idx,
                            "field": "route_type",
                            "code": "INVALID_ROUTE_TYPE",
                            "message": f"route_type '{route_type}' must be an integer.",
                        })

            # trips.txt: collect trip IDs and validate FK route_id
            valid_trip_ids: Set[str] = set()
            if "trips.txt" in parsed_data:
                for idx, row in enumerate(parsed_data["trips.txt"], start=2):
                    trip_id = row.get("trip_id", "")
                    if trip_id:
                        valid_trip_ids.add(trip_id)
                    else:
                        errors.append({
                            "file": "trips.txt",
                            "line": idx,
                            "field": "trip_id",
                            "code": "EMPTY_PRIMARY_KEY",
                            "message": "trip_id cannot be empty.",
                        })

                    # Relational check: route_id in trips -> routes.txt
                    route_id = row.get("route_id", "")
                    if route_id and route_id not in valid_route_ids:
                        errors.append({
                            "file": "trips.txt",
                            "line": idx,
                            "field": "route_id",
                            "code": "FOREIGN_KEY_VIOLATION",
                            "message": f"route_id '{route_id}' does not exist in routes.txt.",
                        })

            # stop_times.txt: FK trip_id and stop_id checks, stop_sequence integer check
            if "stop_times.txt" in parsed_data:
                for idx, row in enumerate(parsed_data["stop_times.txt"], start=2):
                    trip_id = row.get("trip_id", "")
                    stop_id = row.get("stop_id", "")
                    seq_str = row.get("stop_sequence", "")

                    if trip_id and trip_id not in valid_trip_ids:
                        errors.append({
                            "file": "stop_times.txt",
                            "line": idx,
                            "field": "trip_id",
                            "code": "FOREIGN_KEY_VIOLATION",
                            "message": f"trip_id '{trip_id}' does not exist in trips.txt.",
                        })

                    if stop_id and stop_id not in valid_stop_ids:
                        errors.append({
                            "file": "stop_times.txt",
                            "line": idx,
                            "field": "stop_id",
                            "code": "FOREIGN_KEY_VIOLATION",
                            "message": f"stop_id '{stop_id}' does not exist in stops.txt.",
                        })

                    if not seq_str.isdigit():
                        errors.append({
                            "file": "stop_times.txt",
                            "line": idx,
                            "field": "stop_sequence",
                            "code": "INVALID_STOP_SEQUENCE",
                            "message": f"stop_sequence '{seq_str}' must be a non-negative integer.",
                        })

    except zipfile.BadZipFile:
        errors.append({
            "file": None,
            "line": None,
            "field": None,
            "code": "CORRUPTED_ZIP",
            "message": "Zip archive is corrupted or could not be decompressed.",
        })
    except Exception as exc:
        errors.append({
            "file": None,
            "line": None,
            "field": None,
            "code": "UNEXPECTED_ERROR",
            "message": f"Unexpected error during validation: {str(exc)}",
        })

    is_valid = len(errors) == 0
    if is_valid and len(warnings) == 0:
        error_summary = "Validation succeeded without any issues."
    elif is_valid:
        error_summary = f"Validation passed with {len(warnings)} warning(s)."
    else:
        error_summary = f"Validation failed with {len(errors)} error(s) and {len(warnings)} warning(s)."

    return {
        "is_valid": is_valid,
        "error_summary": error_summary,
        "files_found": files_found,
        "errors": errors,
        "warnings": warnings,
        "stats": stats,
    }


def process_validation_job(job_id: str, file_path: str) -> None:
    """Background task worker that performs the validation and updates the database job record."""
    db = SessionLocal()
    try:
        job = db.query(ValidationJob).filter(ValidationJob.id == job_id).first()
        if not job:
            return

        job.status = JobStatus.PROCESSING
        db.commit()

        # Run validation
        report = validate_gtfs_archive(file_path)

        job.status = JobStatus.COMPLETED
        job.finished_at = datetime.now(timezone.utc)
        job.error_summary = report.get("error_summary")
        job.report_details = report
        db.commit()

    except Exception as exc:
        db.rollback()
        job = db.query(ValidationJob).filter(ValidationJob.id == job_id).first()
        if job:
            job.status = JobStatus.FAILED
            job.finished_at = datetime.now(timezone.utc)
            job.error_summary = f"Worker failed: {str(exc)}"
            job.report_details = {
                "is_valid": False,
                "error_summary": f"Worker failed: {str(exc)}",
                "files_found": [],
                "errors": [{
                    "file": None,
                    "line": None,
                    "field": None,
                    "code": "WORKER_EXCEPTION",
                    "message": str(exc),
                }],
                "warnings": [],
                "stats": {},
            }
            db.commit()
    finally:
        db.close()

