"""
Home Miner Manager v1.0.0 - Main Application Entry Point
"""
import os
import sys
import logging
from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
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
from core.database import init_db
from core.mqtt import mqtt_client
from core.scheduler import scheduler
from api import miners, pools, automation, dashboard, settings as settings_api, notifications, analytics, energy, pool_health, discovery, tuning, bulk, audit, dashboards, widgets, strategy_pools, overview
from ui import routes as ui_routes

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
            "connect-src 'self' https://cdn.jsdelivr.net;"
        )
        return response

app.add_middleware(CSPMiddleware)

@app.on_event("startup")
async def startup_event():
    """Application startup"""
    logger.info(f"🚀 Starting Home Miner Manager on port {settings.WEB_PORT}")
    
    try:
        # Initialize database
        logger.info("🗄️  Initializing database...")
        await init_db()
        logger.info("✅ Database initialized")
        
        # Run migrations
        logger.info("🔄 Running database migrations...")
        from core.migrations import run_migrations
        await run_migrations()
        logger.info("✅ Migrations completed")
        
        # Ensure default alert types exist
        logger.info("🔔 Syncing default alert types...")
        from core.notifications import ensure_default_alerts
        await ensure_default_alerts()
        logger.info("✅ Alert types synced")
        
        # Start MQTT client
        logger.info("📡 Starting MQTT client...")
        await mqtt_client.start()
        logger.info("✅ MQTT client started")
        
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
    await mqtt_client.stop()
    scheduler.shutdown()

# Mount static files
static_dir = Path(__file__).parent / "ui" / "static"
static_dir.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# Setup templates
templates_dir = Path(__file__).parent / "ui" / "templates"
templates_dir.mkdir(parents=True, exist_ok=True)
templates = Jinja2Templates(directory=str(templates_dir))

# Include API routes
app.include_router(miners.router, prefix="/api/miners", tags=["miners"])
app.include_router(pools.router, prefix="/api/pools", tags=["pools"])
app.include_router(automation.router, prefix="/api/automation", tags=["automation"])
app.include_router(dashboard.router, prefix="/api/dashboard", tags=["dashboard"])
app.include_router(settings_api.router, prefix="/api/settings", tags=["settings"])
app.include_router(notifications.router, prefix="/api/notifications", tags=["notifications"])
app.include_router(analytics.router, prefix="/api/analytics", tags=["analytics"])
app.include_router(energy.router, prefix="/api/energy", tags=["energy"])
app.include_router(pool_health.router, prefix="/api", tags=["pool-health"])
app.include_router(discovery.router, prefix="/api", tags=["discovery"])
app.include_router(tuning.router, prefix="/api/tuning", tags=["tuning"])
app.include_router(bulk.router, prefix="/api/bulk", tags=["bulk"])
app.include_router(audit.router)
app.include_router(dashboards.router, prefix="/api/dashboards", tags=["dashboards"])
app.include_router(widgets.router, prefix="/api/widgets", tags=["widgets"])
app.include_router(strategy_pools.router, prefix="/api", tags=["strategy-pools"])
app.include_router(overview.router, tags=["overview"])

# Include UI routes
app.include_router(ui_routes.router)


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
