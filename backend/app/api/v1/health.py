import redis
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.db.session import check_database
from app.integrations.storage import get_storage

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live")
def live() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready")
def ready() -> JSONResponse:
    checks = {}
    try:
        check_database()
        checks["database"] = "ok"
    except Exception:  # noqa: BLE001 - any failure means not ready; details stay in the logs
        checks["database"] = "unavailable"
    try:
        get_storage().check()
        checks["storage"] = "ok"
    except Exception:  # noqa: BLE001
        checks["storage"] = "unavailable"
    if get_settings().task_executor == "celery":
        try:
            redis.Redis.from_url(get_settings().redis_url, socket_timeout=2).ping()
            checks["redis"] = "ok"
        except Exception:  # noqa: BLE001
            checks["redis"] = "unavailable"
    healthy = all(v == "ok" for v in checks.values())
    return JSONResponse(
        {"status": "ok" if healthy else "unavailable", "checks": checks},
        status_code=200 if healthy else 503,
    )
