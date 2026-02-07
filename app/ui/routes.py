"""
UI routes for Jinja2 templates
"""
from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from pathlib import Path
import os

from core.database import get_db, Miner, Pool, AutomationRule


templates_dir = Path(__file__).parent / "templates"

# Add git_commit to all template contexts
class CustomTemplates(Jinja2Templates):
    def TemplateResponse(self, *args, **kwargs):
        # Add git_commit to context if it's a dict
        if len(args) >= 2 and isinstance(args[1], dict):
            args[1]["git_commit"] = GIT_COMMIT
        return super().TemplateResponse(*args, **kwargs)

templates = CustomTemplates(directory=str(templates_dir))

router = APIRouter()

# Read git commit from file (set during Docker build)
def get_git_commit():
    try:
        commit_file = Path("/app/.git_commit")
        if commit_file.exists():
            return commit_file.read_text().strip()
    except Exception:
        pass
    return "dev"

GIT_COMMIT = get_git_commit()


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, db: AsyncSession = Depends(get_db)):
    """Dashboard page (default)"""
    
    # Get basic stats
    result = await db.execute(select(Miner))
    miners = result.scalars().all()
    
    return templates.TemplateResponse("dashboard_asic.html", {
        "request": request,
        "page_title": "Dashboard",
        "breadcrumbs": [{"label": "Dashboard", "url": "/"}],
        "miners_count": len(miners),
        "dashboard_type": "asic"
    })


@router.get("/miners", response_class=HTMLResponse)
async def miners_list(request: Request, db: AsyncSession = Depends(get_db)):
    """Miners list page"""
    from sqlalchemy import func
    result = await db.execute(select(Miner).order_by(func.lower(Miner.name)))
    miners = result.scalars().all()
    
    return templates.TemplateResponse("miners/list.html", {
        "request": request,
        "page_title": "Miners",
        "breadcrumbs": [
            {"label": "Dashboard", "url": "/"},
            {"label": "Miners", "url": "/miners"}
        ],
        "miners": miners
    })


@router.get("/miners/add", response_class=HTMLResponse)
async def add_miner(request: Request):
    """Add miner wizard"""
    return templates.TemplateResponse("miners/add.html", {
        "request": request,
        "page_title": "Add Miner",
        "breadcrumbs": [
            {"label": "Dashboard", "url": "/"},
            {"label": "Miners", "url": "/miners"},
            {"label": "Add Miner", "url": "/miners/add"}
        ]
    })


@router.get("/miners/discover", response_class=HTMLResponse)
async def discover_miners(request: Request):
    """Network discovery page"""
    return templates.TemplateResponse("miners/discover.html", {
        "request": request,
        "page_title": "Discover Miners",
        "breadcrumbs": [
            {"label": "Dashboard", "url": "/"},
            {"label": "Miners", "url": "/miners"},
            {"label": "Discover", "url": "/miners/discover"}
        ]
    })


@router.get("/miners/{miner_id}", response_class=HTMLResponse)
async def miner_detail(request: Request, miner_id: int, db: AsyncSession = Depends(get_db)):
    """Miner detail page"""
    result = await db.execute(select(Miner).where(Miner.id == miner_id))
    miner = result.scalar_one_or_none()
    
    if not miner:
        return templates.TemplateResponse("404.html", {
            "request": request,
            "page_title": "Miner Not Found"
        }, status_code=404)
    
    return templates.TemplateResponse("miners/detail.html", {
        "request": request,
        "page_title": f"Miner: {miner.name}",
        "breadcrumbs": [
            {"label": "Dashboard", "url": "/"},
            {"label": "Miners", "url": "/miners"},
            {"label": miner.name, "url": f"/miners/{miner_id}"}
        ],
        "miner": miner
    })


@router.get("/miners/{miner_id}/edit", response_class=HTMLResponse)
async def miner_edit(request: Request, miner_id: int, db: AsyncSession = Depends(get_db)):
    """Miner edit page"""
    from adapters import get_adapter
    
    result = await db.execute(select(Miner).where(Miner.id == miner_id))
    miner = result.scalar_one_or_none()
    
    if not miner:
        return templates.TemplateResponse("404.html", {
            "request": request,
            "page_title": "Miner Not Found"
        }, status_code=404)
    
    # Calculate effective_port using the adapter
    adapter = get_adapter(miner)
    effective_port = adapter.port if adapter else miner.port
    
    # Create a miner dict with effective_port for the template
    miner_data = {
        "id": miner.id,
        "name": miner.name,
        "miner_type": miner.miner_type,
        "ip_address": miner.ip_address,
        "port": miner.port,
        "effective_port": effective_port,
        "current_mode": miner.current_mode,
        "enabled": miner.enabled,
        "manual_power_watts": miner.manual_power_watts,
        "config": miner.config
    }
    
    return templates.TemplateResponse("miners/edit.html", {
        "request": request,
        "page_title": f"Edit Miner: {miner.name}",
        "breadcrumbs": [
            {"label": "Dashboard", "url": "/"},
            {"label": "Miners", "url": "/miners"},
            {"label": miner.name, "url": f"/miners/{miner_id}"},
            {"label": "Edit", "url": f"/miners/{miner_id}/edit"}
        ],
        "miner": miner_data
    })


@router.get("/pools", response_class=HTMLResponse)
async def pools_list(request: Request, db: AsyncSession = Depends(get_db)):
    """Pools list page"""
    from core.pool_health import PoolHealthService
    from core.database import PoolHealth
    from sqlalchemy import desc, func
    
    result = await db.execute(select(Pool).order_by(func.lower(Pool.name)))
    pools = result.scalars().all()
    
    # Get latest health data for each pool
    pool_health_map = {}
    for pool in pools:
        health_result = await db.execute(
            select(PoolHealth)
            .where(PoolHealth.pool_id == pool.id)
            .order_by(desc(PoolHealth.timestamp))
            .limit(1)
        )
        latest_health = health_result.scalar_one_or_none()
        pool_health_map[pool.id] = latest_health
    
    return templates.TemplateResponse("pools/list.html", {
        "request": request,
        "page_title": "Mining Pools",
        "breadcrumbs": [
            {"label": "Dashboard", "url": "/"},
            {"label": "Pools", "url": "/pools"}
        ],
        "pools": pools,
        "pool_health_map": pool_health_map
    })


@router.get("/pools/add", response_class=HTMLResponse)
async def add_pool(request: Request):
    """Add pool page"""
    return templates.TemplateResponse("pools/add.html", {
        "request": request,
        "page_title": "Add Pool",
        "breadcrumbs": [
            {"label": "Dashboard", "url": "/"},
            {"label": "Pools", "url": "/pools"},
            {"label": "Add Pool", "url": "/pools/add"}
        ]
    })


@router.get("/pools/{pool_id}/edit", response_class=HTMLResponse)
async def edit_pool(request: Request, pool_id: int, db: AsyncSession = Depends(get_db)):
    """Edit pool page"""
    result = await db.execute(select(Pool).where(Pool.id == pool_id))
    pool = result.scalar_one_or_none()
    
    if not pool:
        return templates.TemplateResponse("404.html", {
            "request": request,
            "page_title": "Pool Not Found"
        }, status_code=404)
    
    return templates.TemplateResponse("pools/edit.html", {
        "request": request,
        "page_title": f"Edit Pool: {pool.name}",
        "breadcrumbs": [
            {"label": "Dashboard", "url": "/"},
            {"label": "Pools", "url": "/pools"},
            {"label": f"Edit {pool.name}", "url": f"/pools/{pool_id}/edit"}
        ],
        "pool": pool
    })


@router.get("/pools/strategies", response_class=HTMLResponse)
async def pools_strategies(request: Request, db: AsyncSession = Depends(get_db)):
    """Pool strategies list page"""
    from core.database import PoolStrategy
    
    result = await db.execute(select(PoolStrategy).order_by(PoolStrategy.id))
    strategies = result.scalars().all()
    
    result = await db.execute(select(Pool).order_by(Pool.id))
    pools = result.scalars().all()
    
    return templates.TemplateResponse("pools/strategies.html", {
        "request": request,
        "page_title": "Pool Strategies",
        "breadcrumbs": [
            {"label": "Dashboard", "url": "/"},
            {"label": "Miner Management", "url": "/miner-management"},
            {"label": "Pool Strategies", "url": "/pools/strategies"}
        ],
        "strategies": strategies,
        "pools": pools
    })


@router.get("/pools/strategies/add", response_class=HTMLResponse)
async def pools_strategies_add(request: Request, db: AsyncSession = Depends(get_db)):
    """Add pool strategy page"""
    
    # Get all enabled pools - Avalon Nano now supports dynamic pool switching
    result = await db.execute(
        select(Pool).where(Pool.enabled == True).order_by(Pool.name)
    )
    
    pools = result.scalars().all()
    
    return templates.TemplateResponse("pools/strategy_add.html", {
        "request": request,
        "page_title": "Add Pool Strategy",
        "breadcrumbs": [
            {"label": "Dashboard", "url": "/"},
            {"label": "Miner Management", "url": "/miner-management"},
            {"label": "Pool Strategies", "url": "/pools/strategies"},
            {"label": "Add", "url": "/pools/strategies/add"}
        ],
        "pools": pools
    })


@router.get("/pools/strategies/{strategy_id}/edit", response_class=HTMLResponse)
async def pools_strategies_edit(request: Request, strategy_id: int, db: AsyncSession = Depends(get_db)):
    """Edit pool strategy page"""
    from core.database import PoolStrategy
    
    result = await db.execute(select(PoolStrategy).where(PoolStrategy.id == strategy_id))
    strategy = result.scalar_one_or_none()
    
    if not strategy:
        return templates.TemplateResponse("error.html", {
            "request": request,
            "error": "Strategy not found"
        }, status_code=404)
    
    # Get all enabled pools - Avalon Nano now supports dynamic pool switching
    result = await db.execute(
        select(Pool).where(Pool.enabled == True).order_by(Pool.name)
    )
    
    pools = result.scalars().all()
    
    return templates.TemplateResponse("pools/strategy_edit.html", {
        "request": request,
        "page_title": f"Edit Strategy: {strategy.name}",
        "breadcrumbs": [
            {"label": "Dashboard", "url": "/"},
            {"label": "Miner Management", "url": "/miner-management"},
            {"label": "Pool Strategies", "url": "/pools/strategies"},
            {"label": strategy.name, "url": f"/pools/strategies/{strategy_id}/edit"}
        ],
        "strategy": strategy,
        "pools": pools
    })


@router.get("/automation", response_class=HTMLResponse)
async def automation_list(request: Request, db: AsyncSession = Depends(get_db)):
    """Automation rules list page"""
    result = await db.execute(select(AutomationRule))
    rules = result.scalars().all()
    
    return templates.TemplateResponse("automation/list.html", {
        "request": request,
        "page_title": "Automation Rules",
        "breadcrumbs": [
            {"label": "Dashboard", "url": "/"},
            {"label": "Miner Management", "url": "/miner-management"},
            {"label": "Automation Rules", "url": "/automation"}
        ],
        "rules": rules
    })


@router.get("/automation/add", response_class=HTMLResponse)
async def add_rule(request: Request):
    """Add automation rule wizard"""
    return templates.TemplateResponse("automation/add.html", {
        "request": request,
        "page_title": "Add Automation Rule",
        "breadcrumbs": [
            {"label": "Dashboard", "url": "/"},
            {"label": "Miner Management", "url": "/miner-management"},
            {"label": "Automation Rules", "url": "/automation"},
            {"label": "Add Rule", "url": "/automation/add"}
        ]
    })


@router.get("/automation/edit/{rule_id}", response_class=HTMLResponse)
async def edit_rule(request: Request, rule_id: int):
    """Edit automation rule"""
    return templates.TemplateResponse("automation/edit.html", {
        "request": request,
        "page_title": "Edit Automation Rule",
        "breadcrumbs": [
            {"label": "Dashboard", "url": "/"},
            {"label": "Miner Management", "url": "/miner-management"},
            {"label": "Automation Rules", "url": "/automation"},
            {"label": "Edit Rule", "url": f"/automation/edit/{rule_id}"}
        ],
        "rule_id": rule_id
    })


@router.get("/settings/energy", response_class=HTMLResponse)
async def energy_settings(request: Request):
    """Energy pricing page"""
    return templates.TemplateResponse("energy/pricing.html", {
        "request": request,
        "page_title": "Energy Pricing",
        "breadcrumbs": [
            {"label": "Dashboard", "url": "/"},
            {"label": "Miner Management", "url": "/miner-management"},
            {"label": "Energy Pricing", "url": "/settings/energy"}
        ]
    })


@router.get("/settings/optimization", response_class=HTMLResponse)
async def energy_optimization_settings(request: Request):
    """Energy optimization page"""
    return templates.TemplateResponse("energy/optimization.html", {
        "request": request,
        "page_title": "Energy Optimization",
        "breadcrumbs": [
            {"label": "Dashboard", "url": "/"},
            {"label": "Miner Management", "url": "/miner-management"},
            {"label": "Energy Optimization", "url": "/settings/optimization"}
        ]
    })


@router.get("/miner-management", response_class=HTMLResponse)
async def miner_management(request: Request):
    """Miner Management page"""
    return templates.TemplateResponse("miner_management.html", {
        "request": request,
        "page_title": "Miner Management",
        "breadcrumbs": [
            {"label": "Dashboard", "url": "/"},
            {"label": "Miner Management", "url": "/miner-management"}
        ]
    })


@router.get("/settings", response_class=HTMLResponse)
async def settings(request: Request):
    """Settings page"""
    return templates.TemplateResponse("settings.html", {
        "request": request,
        "page_title": "Settings",
        "breadcrumbs": [
            {"label": "Dashboard", "url": "/"},
            {"label": "Settings", "url": "/settings"}
        ]
    })


@router.get("/settings/audit", response_class=HTMLResponse)
async def audit_logs_page(request: Request):
    """Audit Logs page"""
    return templates.TemplateResponse("audit_logs.html", {
        "request": request,
        "page_title": "Audit Logs",
        "breadcrumbs": [
            {"label": "Dashboard", "url": "/"},
            {"label": "Settings", "url": "/settings"},
            {"label": "Audit Logs", "url": "/settings/audit"}
        ]
    })


@router.get("/settings/discovery", response_class=HTMLResponse)
async def discovery_settings(request: Request):
    """Network Discovery Settings page"""
    return templates.TemplateResponse("settings/discovery.html", {
        "request": request,
        "page_title": "Network Discovery",
        "breadcrumbs": [
            {"label": "Dashboard", "url": "/"},
            {"label": "Settings", "url": "/settings"},
            {"label": "Network Discovery", "url": "/settings/discovery"}
        ]
    })


@router.get("/settings/pools", response_class=HTMLResponse)
async def pool_integrations_settings(request: Request):
    """Pool Integrations page"""
    return templates.TemplateResponse("settings/pools.html", {
        "request": request,
        "page_title": "Pool Integrations",
        "breadcrumbs": [
            {"label": "Dashboard", "url": "/"},
            {"label": "Settings", "url": "/settings"},
            {"label": "Pool Integrations", "url": "/settings/pools"}
        ]
    })


@router.get("/settings/agile-solo-strategy", response_class=HTMLResponse)
async def agile_solo_strategy_settings(request: Request):
    """Agile Strategy settings page"""
    return templates.TemplateResponse("settings/agile_solo_strategy.html", {
        "request": request,
        "page_title": "Agile Strategy",
        "breadcrumbs": [
            {"label": "Dashboard", "url": "/"},
            {"label": "Miner Management", "url": "/miner-management"},
            {"label": "Agile Strategy", "url": "/settings/agile-solo-strategy"}
        ]
    })


@router.get("/settings/logs", response_class=HTMLResponse)
async def logs_settings(request: Request):
    """System logs page"""
    return templates.TemplateResponse("logs.html", {
        "request": request,
        "page_title": "System Logs",
        "breadcrumbs": [
            {"label": "Dashboard", "url": "/"},
            {"label": "Settings", "url": "/settings"},
            {"label": "System Logs", "url": "/settings/logs"}
        ]
    })


@router.get("/settings/notifications", response_class=HTMLResponse)
async def notifications_settings(request: Request):
    """Notifications page"""
    return templates.TemplateResponse("notifications.html", {
        "request": request,
        "page_title": "Notifications",
        "breadcrumbs": [
            {"label": "Dashboard", "url": "/"},
            {"label": "Settings", "url": "/settings"},
            {"label": "Notifications", "url": "/settings/notifications"}
        ]
    })


@router.get("/settings/tuning", response_class=HTMLResponse)
async def tuning_profiles(request: Request):
    """Tuning Profiles page"""
    return templates.TemplateResponse("settings/tuning.html", {
        "request": request,
        "page_title": "Tuning Profiles",
        "breadcrumbs": [
            {"label": "Dashboard", "url": "/"},
            {"label": "Settings", "url": "/settings"},
            {"label": "Tuning Profiles", "url": "/settings/tuning"}
        ]
    })


@router.get("/settings/defaults", response_class=HTMLResponse)
async def defaults_settings(request: Request):
    """Defaults Settings page"""
    return templates.TemplateResponse("settings/defaults.html", {
        "request": request,
        "page_title": "Defaults",
        "breadcrumbs": [
            {"label": "Dashboard", "url": "/"},
            {"label": "Settings", "url": "/settings"},
            {"label": "Defaults", "url": "/settings/defaults"}
        ]
    })


@router.get("/settings/cloud", response_class=HTMLResponse)
async def cloud_settings(request: Request):
    """Cloud Settings page"""
    return templates.TemplateResponse("cloud.html", {
        "request": request,
        "page_title": "Cloud Settings",
        "breadcrumbs": [
            {"label": "Dashboard", "url": "/"},
            {"label": "Settings", "url": "/settings"},
            {"label": "Cloud", "url": "/settings/cloud"}
        ]
    })


@router.get("/settings/integrations", response_class=HTMLResponse)
async def integrations_settings(request: Request):
    """Integrations Settings page (Home Assistant, etc.)"""
    return templates.TemplateResponse("settings/integrations.html", {
        "request": request,
        "page_title": "External Integrations",
        "breadcrumbs": [
            {"label": "Dashboard", "url": "/"},
            {"label": "Settings", "url": "/settings"},
            {"label": "Integrations", "url": "/settings/integrations"}
        ]
    })


@router.get("/settings/integrations/homeassistant", response_class=HTMLResponse)
async def homeassistant_integration(request: Request):
    """Home Assistant integration page"""
    return templates.TemplateResponse("settings/homeassistant.html", {
        "request": request,
        "page_title": "Home Assistant Integration",
        "breadcrumbs": [
            {"label": "Dashboard", "url": "/"},
            {"label": "Miner Management", "url": "/miner-management"},
            {"label": "Home Assistant", "url": "/settings/integrations/homeassistant"}
        ]
    })


@router.get("/settings/openai", response_class=HTMLResponse)
async def openai_settings(request: Request):
    """OpenAI AI Settings page"""
    return templates.TemplateResponse("settings/openai.html", {
        "request": request,
        "page_title": "AI Settings",
        "breadcrumbs": [
            {"label": "Dashboard", "url": "/"},
            {"label": "Settings", "url": "/settings"},
            {"label": "AI Settings", "url": "/settings/openai"}
        ]
    })


@router.get("/leaderboard", response_class=HTMLResponse)
async def leaderboard(request: Request):
    """High difficulty share leaderboard page"""
    return templates.TemplateResponse("leaderboard.html", {
        "request": request,
        "page_title": "Leaderboard",
        "breadcrumbs": [
            {"label": "Dashboard", "url": "/"},
            {"label": "Leaderboard", "url": "/leaderboard"}
        ]
    })


@router.get("/health", response_class=HTMLResponse)
async def health_page(request: Request, db: AsyncSession = Depends(get_db)):
    """System Health page"""
    return templates.TemplateResponse("health.html", {
        "request": request,
        "page_title": "System Health",
        "breadcrumbs": [
            {"label": "Dashboard", "url": "/"},
            {"label": "Health", "url": "/health"}
        ]
    })



