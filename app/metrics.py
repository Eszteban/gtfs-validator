from prometheus_client import Counter, Histogram

# Total validation jobs categorized by their final status (COMPLETED, FAILED, etc.)
VALIDATION_JOBS_TOTAL = Counter(
    "gtfs_validation_jobs_total",
    "Total number of GTFS validation jobs processed by the microservice.",
    labelnames=["status"],
)

# Execution duration histogram for validation jobs in seconds
VALIDATION_DURATION_SECONDS = Histogram(
    "gtfs_validation_duration_seconds",
    "Execution duration of GTFS validation jobs in seconds.",
    labelnames=["status"],
    buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 2.5, 5.0, 10.0],
)

# Total validation errors encountered, categorized by error code/type
VALIDATION_ERRORS_TOTAL = Counter(
    "gtfs_validation_errors_total",
    "Total number of validation errors encountered during GTFS checks.",
    labelnames=["error_type"],
)

