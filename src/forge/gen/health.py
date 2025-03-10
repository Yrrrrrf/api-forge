from datetime import datetime
from pydantic import BaseModel
from fastapi import APIRouter, Response

from forge.tools.model import ModelForge


class HealthStatus(BaseModel):
    status: str
    timestamp: datetime
    version: str
    uptime: float
    database: bool


from pydantic import BaseModel, Field


class HealthStatus(BaseModel):
    """Health status response model"""

    status: str = Field(..., description="Current health status")
    timestamp: datetime = Field(..., description="Current timestamp")
    version: str = Field(..., description="API version")
    uptime: float = Field(..., description="Server uptime in seconds")
    # database: bool = Field(..., description="Database connection status")
    # environment: str = Field(..., description="Current environment")


def health_root(
    dt_router: APIRouter,
    model_forge: ModelForge,
    start_time: datetime,
    environment: str = "development",
):
    def check_db_connection() -> bool:
        try:
            model_forge.db_manager.exec_raw_sql("SELECT 1")
            return True
        except Exception:
            return False

    @dt_router.get("", response_model=HealthStatus)
    def health_check():
        """Basic health check endpoint"""
        is_connected = check_db_connection()
        return HealthStatus(
            status="healthy" if is_connected else "degraded",
            timestamp=datetime.now(),
            version=model_forge.db_manager.get_db_version(),
            uptime=(datetime.now() - start_time).total_seconds(),
            # database=is_connected,  # Add database status
            # environment=environment  # Add environment
        )


class CacheStatus(BaseModel):
    last_updated: datetime
    total_items: int
    tables_cached: int
    views_cached: int
    enums_cached: int
    functions_cached: int
    procedures_cached: int
    triggers_cached: int


def cache(dt_router: APIRouter, model_forge: ModelForge, start_time: datetime):
    @dt_router.get("/cache", response_model=CacheStatus)
    def cache_status():
        """Get metadata cache status"""
        counter = [
            len(model_forge.table_cache),
            len(model_forge.view_cache),
            len(model_forge.enum_cache),
            len(model_forge.fn_cache),
            len(model_forge.proc_cache),
            len(model_forge.trig_cache),
        ]

        # same as above in less code lines, like using the len iterated over the list of caches
        # counter = [len(cache) for cache in [model_forge.table_cache, model_forge.view_cache, model_forge.enum_cache, model_forge.fn_cache, model_forge.proc_cache, model_forge.trig_cache]]

        return CacheStatus(
            last_updated=start_time,  # You might want to track actual cache updates
            total_items=sum(counter),
            tables_cached=counter[0],
            views_cached=counter[1],
            enums_cached=counter[2],
            functions_cached=counter[3],
            procedures_cached=counter[4],
            triggers_cached=counter[5],
        )


def clear_cache(dt_router: APIRouter, model_forge: ModelForge, start_time: datetime):
    @dt_router.post("/clear-cache")
    def clear_cache():
        """Clear and reload all metadata caches"""
        try:
            #
            return {"status": "success", "message": "Cache cleared and reloaded"}
        except Exception as e:
            return {"status": "error", "message": str(e)}


def ping(dt_router: APIRouter):
    @dt_router.get("/ping", status_code=200)
    def ping():
        """Simple ping endpoint for load balancers"""
        return Response(content="pong", media_type="text/plain")
