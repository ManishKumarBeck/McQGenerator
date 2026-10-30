"""Health check and analytics endpoints."""

from fastapi import APIRouter
from sqlalchemy import text

from .. import schemas
from ..dependencies import AppSettings, DbSession
from ..services import analytics

router = APIRouter(prefix="/api", tags=["meta"])


@router.get("/health", response_model=schemas.HealthStatus)
def health(db: DbSession, settings: AppSettings):
    try:
        db.execute(text("SELECT 1"))
        database_ok = True
    except Exception:  # pragma: no cover - reported, not raised
        database_ok = False
    return schemas.HealthStatus(
        status="ok",
        database=database_ok,
        ai_configured=settings.has_openai_key,
        model=settings.openai_model,
    )


@router.get("/analytics", response_model=schemas.AnalyticsOverview)
def get_analytics(db: DbSession, settings: AppSettings):
    return analytics.overview(db, settings)
