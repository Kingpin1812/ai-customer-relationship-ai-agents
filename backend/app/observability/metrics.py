from prometheus_client import Counter, Histogram

WORKFLOWS_CREATED = Counter("workflows_created_total", "Workflows submitted")
WORKFLOW_FINISHED = Counter("workflows_finished_total", "Workflows finished", ["status"])
WORKFLOW_DURATION = Histogram(
    "workflow_duration_seconds",
    "Submission to finish, excluding nothing",
    buckets=(1, 5, 15, 60, 300, 1800, 3600, 86400),
)
STEP_DURATION = Histogram("workflow_step_duration_seconds", "Graph step duration", ["step"])
TOOL_LATENCY = Histogram(
    "integration_tool_latency_seconds", "Provider call latency", ["provider", "operation"]
)
TOOL_FAILURES = Counter(
    "integration_tool_failures_total",
    "Provider call failures",
    ["provider", "operation", "category"],
)
RETRIES = Counter("integration_retries_total", "Scheduled retries", ["provider", "operation"])
RECONCILIATIONS = Counter(
    "integration_reconciliations_total", "Reconciliation checks", ["provider", "happened"]
)
APPROVAL_WAIT = Histogram(
    "approval_wait_seconds",
    "Time from approval request to decision",
    ["decision"],
    buckets=(10, 60, 300, 1800, 3600, 14400, 86400, 259200),
)
HTTP_REQUESTS = Counter("http_requests_total", "HTTP requests", ["method", "status"])
