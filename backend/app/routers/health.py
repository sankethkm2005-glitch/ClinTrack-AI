"""Health-check router verifying API and SQLite database status."""

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from app.config import settings
from app.database import check_db_connection

router = APIRouter(tags=["Health"])


@router.get("/health")
def health_check():
    """Return backend service and SQLite connectivity status."""
    db_ok = check_db_connection()
    payload = {
        "status": "ok" if db_ok else "degraded",
        "app": settings.APP_NAME,
        "environment": settings.APP_ENV,
        "database": "connected" if db_ok else "unavailable",
        "ai_provider": settings.AI_PROVIDER,
    }
    http_status = status.HTTP_200_OK if db_ok else status.HTTP_503_SERVICE_UNAVAILABLE
    return JSONResponse(status_code=http_status, content=payload)
