"""
Home Miner Manager v1.0.0 - Main Application Entry Point
"""
import os
import sys
import logging
import uuid
import traceback
from pathlib import Path
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from contextlib import asynccontextmanager

# Force unbuffered output
sys.stdout = os.fdopen(sys.stdout.fileno(), 'w', buffering=1)
sys.stderr = os.fdopen(sys.stderr.fileno(), 'w', buffering=1)

# Setup logging FIRST
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

logger.info("=" * 60)
logger.info("MAIN.PY MODULE LOADING")
logger.info("=" * 60)

from core.config import settings
from core.database import init_db, engine
from core.db_pool_metrics import record_pool_timeout
from sqlalchemy.exc import TimeoutError as SATimeoutError
from core.scheduler import scheduler
from api import miners, pools, automation, dashboard, settings as settings_api, notifications, analytics, energy, pool_health, discovery, tuning, bulk, audit, strategy_pools, overview, agile_solo_strategy, leaderboard, cloud, health, ai, database_settings, websocket, operations, pool_templates

logger.info("All imports successful")


app = FastAPI(
    title="Home Miner Manager",
    description="Modern ASIC Miner Management Platform",
    version="1.0.0"
)

# Add CSP middleware for GridStack (requires unsafe-eval)
class CSPMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "img-src 'self' data: https:; "
            "font-src 'self' data:; "
            "connect-src 'self' ws: wss: https://cdn.jsdelivr.net;"
        )
        return response

app.add_middleware(CSPMiddleware)


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-Id") or str(uuid.uuid4())
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-Id"] = request_id
        return response


app.add_middleware(RequestIdMiddleware)


@app.exception_handler(SATimeoutError)
async def database_timeout_handler(request: Request, exc: SATimeoutError):
    timeout_seconds = getattr(engine.pool, "_timeout", 5)
    request_id = getattr(request.state, "request_id", "unknown")
    logger.error(
        "Database pool timeout",
        extra={
            "request_id": request_id,
            "method": request.method,
            "path": str(request.url.path),
            "wait_seconds": timeout_seconds
        }
    )
    record_pool_timeout(float(timeout_seconds))
    return JSONResponse(
        status_code=503,
        content={
            "detail": "Database connection pool exhausted",
            "request_id": request_id
        }
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    request_id = getattr(request.state, "request_id", "unknown")
    status_code = 500
    detail = "Internal server error"
    if isinstance(exc, HTTPException):
        status_code = exc.status_code
        detail = exc.detail

    if status_code >= 500:
        tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        max_len = 20000
        truncated = False
        if len(tb) > max_len:
            tb = tb[:max_len] + "\n... (truncated)"
            truncated = True

        data = {
            "request_id": request_id,
            "method": request.method,
            "path": str(request.url.path),
            "traceback": tb,
            "traceback_truncated": truncated,
            "exception_type": type(exc).__name__,
        }

        try:
            from core.database import AsyncSessionLocal, Event
            async with AsyncSessionLocal() as db:
                db.add(Event(
                    event_type="error",
                    source="exception",
                    message=f"{type(exc).__name__}: {exc}",
                    data=data
                ))
                await db.commit()
        except Exception as log_error:
            logger.error(
                "Failed to persist exception event",
                extra={
                    "request_id": request_id,
                    "error": str(log_error)
                }
            )

        logger.exception(
            "Unhandled exception",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": str(request.url.path)
            }
        )

    return JSONResponse(
        status_code=status_code,
        content={
            "detail": detail,
            "request_id": request_id
        }
    )

@app.on_event("startup")
async def startup_event():
    """Application startup"""
    logger.info(f"🚀 Starting Home Miner Manager on port {settings.WEB_PORT}")
    
    try:
        # Initialize database
        logger.info("🗄️  Initializing database...")
        await init_db()
        logger.info("✅ Database schema deployed")
        
        # Initialize PostgreSQL optimizations (if using PostgreSQL)
        logger.info("⚡ Initializing database optimizations...")
        from core.database import AsyncSessionLocal
        from core.postgres_optimizations import initialize_postgres_optimizations
        async with AsyncSessionLocal() as db:
            await initialize_postgres_optimizations(db)
        logger.info("✅ Database optimizations initialized")
        
        # Ensure default alert types exist
        logger.info("🔔 Syncing default alert types...")
        from core.notifications import ensure_default_alerts
        await ensure_default_alerts()
        logger.info("✅ Alert types synced")
        
        # Load pool plugins
        logger.info("🔌 Loading pool plugins...")
        from core.plugin_loader import load_plugins_from_config
        from core.config import app_config
        loaded_plugins = load_plugins_from_config(app_config._config)
        logger.info(f"✅ Loaded {len(loaded_plugins)} pool plugin(s)")
        
        # Load pool drivers and configs (NEW ARCHITECTURE)
        logger.info("🔌 Loading pool drivers and configs...")
        from core.pool_loader import init_pool_loader
        pool_loader = init_pool_loader("/config")
        logger.info(f"✅ Loaded {len(pool_loader.drivers)} driver(s) and {len(pool_loader.pool_configs)} pool config(s)")
        
        # Start scheduler
        logger.info("⏰ Starting scheduler...")
        scheduler.start()
        logger.info(f"✅ Scheduler started with {len(scheduler.scheduler.get_jobs())} jobs")
    except Exception as e:
        logger.error(f"❌ Startup error: {e}")
        import traceback
        traceback.print_exc()
        raise

@app.on_event("shutdown")
async def shutdown_event():
    """Application shutdown"""
    logger.info("🛑 Shutting down Home Miner Manager")
    scheduler.shutdown()

# Mount static files
static_dir = Path(__file__).parent / "ui" / "static"
static_dir.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# Include API routes
app.include_router(miners.router, prefix="/api/miners", tags=["miners"])
app.include_router(pools.router, prefix="/api/pools", tags=["pools"])
app.include_router(automation.router, prefix="/api/automation", tags=["automation"])
app.include_router(dashboard.router, prefix="/api/dashboard", tags=["dashboard"])
app.include_router(settings_api.router, prefix="/api/settings", tags=["settings"])
app.include_router(database_settings.router, prefix="/api/settings", tags=["database"])
app.include_router(notifications.router, prefix="/api/notifications", tags=["notifications"])
app.include_router(analytics.router, prefix="/api/analytics", tags=["analytics"])
app.include_router(energy.router, prefix="/api/energy", tags=["energy"])

# Import integrations routes
from api.integrations import router as integrations_router
app.include_router(integrations_router, tags=["integrations"])
app.include_router(pool_health.router, prefix="/api", tags=["pool-health"])
app.include_router(discovery.router, prefix="/api", tags=["discovery"])
app.include_router(tuning.router, prefix="/api/tuning", tags=["tuning"])
app.include_router(bulk.router, prefix="/api/bulk", tags=["bulk"])
app.include_router(audit.router)
app.include_router(strategy_pools.router, prefix="/api", tags=["strategy-pools"])
app.include_router(overview.router, tags=["overview"])
app.include_router(agile_solo_strategy.router, prefix="/api/settings", tags=["agile-solo-strategy"])
app.include_router(leaderboard.router, prefix="/api", tags=["leaderboard"])
app.include_router(cloud.router, prefix="/api", tags=["cloud"])
app.include_router(health.router, prefix="/api/health", tags=["health"])
app.include_router(ai.router, prefix="/api/ai", tags=["ai"])
app.include_router(operations.router, prefix="/api", tags=["operations"])
app.include_router(websocket.router, tags=["websocket"])
app.include_router(pool_templates.router, tags=["pool-templates"])

# Serve React app at /app route
from fastapi.responses import FileResponse, RedirectResponse

@app.get("/app")
@app.get("/app/")
async def serve_react_index():
    """Serve React app index.html with no-cache headers"""
    react_index = Path(__file__).parent / "ui" / "static" / "app" / "index.html"
    if react_index.exists():
        return FileResponse(
            react_index,
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0"
            }
        )
    return {"error": "React app not found"}

# Mount React app assets BEFORE catch-all route
react_assets_dir = Path(__file__).parent / "ui" / "static" / "app" / "assets"
if react_assets_dir.exists():
    app.mount("/app/assets", StaticFiles(directory=str(react_assets_dir)), name="react_assets")

# Serve React favicon
def _favicon_response(filename: str):
    path = Path(__file__).parent / "ui" / "static" / "app" / filename
    if path.exists():
        media_type = "image/svg+xml" if filename.endswith(".svg") else "image/x-icon"
        return FileResponse(path, media_type=media_type)
    return {"error": "Favicon not found"}

@app.get("/app/favicon.svg")
async def serve_react_favicon_svg():
    return _favicon_response("favicon.svg")

@app.get("/app/favicon.ico")
async def serve_react_favicon_ico():
    return _favicon_response("favicon.ico")

@app.get("/favicon.svg")
async def serve_root_favicon_svg():
    return _favicon_response("favicon.svg")

@app.get("/favicon.ico")
async def serve_root_favicon_ico():
    return _favicon_response("favicon.ico")

# Catch-all for React SPA client-side routing (must be after assets mount)
@app.get("/app/{path:path}")
async def serve_react_app(path: str):
    """Serve React SPA for all /app/* routes (client-side routing) with no-cache headers"""
    react_index = Path(__file__).parent / "ui" / "static" / "app" / "index.html"
    if react_index.exists():
        return FileResponse(
            react_index,
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0"
            }
        )
    return {"error": "React app not found"}

@app.get("/")
async def serve_default_ui():
    """Redirect the root to the React SPA"""
    react_index = Path(__file__).parent / "ui" / "static" / "app" / "index.html"
    if react_index.exists():
        return RedirectResponse(url="/app")
    return {"error": "React app not found"}

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "version": "0.1.0"
    }



if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=settings.WEB_PORT,
        reload=False
    )
