"""
UI routes for Jinja2 templates
"""
from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from pathlib import Path

from core.database import get_db, Miner, Pool, AutomationRule


templates_dir = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(templates_dir))

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, db: AsyncSession = Depends(get_db)):
    """Dashboard page - redirects to default dashboard if set"""
    # NOTE: Default dashboard preference is checked client-side via localStorage
    # The original main dashboard is ALWAYS accessible here at "/"
    # Custom dashboards are accessed via "/dashboards/{id}"
    
    # Get basic stats
    result = await db.execute(select(Miner))
    miners = result.scalars().all()
    
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "page_title": "Dashboard",
        "breadcrumbs": [{"label": "Dashboard", "url": "/"}],
        "miners_count": len(miners)
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


@router.get("/analytics/pools", response_class=HTMLResponse)
async def analytics_pools(request: Request):
    """Pool performance comparison page"""
    return templates.TemplateResponse("pools/performance.html", {
        "request": request,
        "page_title": "Pool Performance Comparison",
        "breadcrumbs": [
            {"label": "Dashboard", "url": "/"},
            {"label": "Analytics", "url": "/analytics"},
            {"label": "Pools", "url": "/analytics/pools"}
        ]
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
            {"label": "Pools", "url": "/pools"},
            {"label": "Strategies", "url": "/pools/strategies"}
        ],
        "strategies": strategies,
        "pools": pools
    })


@router.get("/pools/strategies/add", response_class=HTMLResponse)
async def pools_strategies_add(request: Request, db: AsyncSession = Depends(get_db)):
    """Add pool strategy page"""
    from core.pool_slots import get_common_pools_for_avalon_nanos
    from core.database import MinerPoolSlot
    
    # Check if there are Avalon Nano miners
    nano_result = await db.execute(
        select(Miner.id).where(
            and_(
                Miner.miner_type == "avalon_nano",
                Miner.enabled == True
            )
        )
    )
    nano_miner_ids = [row[0] for row in nano_result.all()]
    has_nano_miners = len(nano_miner_ids) > 0
    
    # Get common pools available on all Avalon Nano miners
    common_pool_ids = await get_common_pools_for_avalon_nanos(db)
    
    # If we have nano miners but no common pools, check if any slots are synced
    slots_need_sync = False
    if has_nano_miners and not common_pool_ids:
        slots_result = await db.execute(
            select(MinerPoolSlot).where(MinerPoolSlot.miner_id.in_(nano_miner_ids)).limit(1)
        )
        if not slots_result.scalar_one_or_none():
            slots_need_sync = True
    
    # Get pool details based on filtering
    if common_pool_ids:
        result = await db.execute(
            select(Pool).where(
                and_(
                    Pool.id.in_(common_pool_ids),
                    Pool.enabled == True
                )
            ).order_by(Pool.name)
        )
    elif has_nano_miners:
        # Have nano miners but no common pools - show empty to prevent misconfiguration
        result = await db.execute(select(Pool).where(Pool.id == -1))  # No results
    else:
        # No nano miners - show all pools
        result = await db.execute(select(Pool).where(Pool.enabled == True).order_by(Pool.name))
    
    pools = result.scalars().all()
    
    return templates.TemplateResponse("pools/strategy_add.html", {
        "request": request,
        "page_title": "Add Pool Strategy",
        "breadcrumbs": [
            {"label": "Dashboard", "url": "/"},
            {"label": "Pools", "url": "/pools"},
            {"label": "Strategies", "url": "/pools/strategies"},
            {"label": "Add", "url": "/pools/strategies/add"}
        ],
        "pools": pools,
        "has_nano_miners": has_nano_miners,
        "slots_need_sync": slots_need_sync
    })


@router.get("/pools/strategies/{strategy_id}/edit", response_class=HTMLResponse)
async def pools_strategies_edit(request: Request, strategy_id: int, db: AsyncSession = Depends(get_db)):
    """Edit pool strategy page"""
    from core.database import PoolStrategy, MinerPoolSlot
    from core.pool_slots import get_common_pools_for_avalon_nanos
    
    result = await db.execute(select(PoolStrategy).where(PoolStrategy.id == strategy_id))
    strategy = result.scalar_one_or_none()
    
    if not strategy:
        return templates.TemplateResponse("error.html", {
            "request": request,
            "error": "Strategy not found"
        }, status_code=404)
    
    # Check if there are Avalon Nano miners
    nano_result = await db.execute(
        select(Miner.id).where(
            and_(
                Miner.miner_type == "avalon_nano",
                Miner.enabled == True
            )
        )
    )
    nano_miner_ids = [row[0] for row in nano_result.all()]
    has_nano_miners = len(nano_miner_ids) > 0
    
    # Get common pools available on all Avalon Nano miners
    common_pool_ids = await get_common_pools_for_avalon_nanos(db)
    
    # If we have nano miners but no common pools, check if any slots are synced
    slots_need_sync = False
    if has_nano_miners and not common_pool_ids:
        slots_result = await db.execute(
            select(MinerPoolSlot).where(MinerPoolSlot.miner_id.in_(nano_miner_ids)).limit(1)
        )
        if not slots_result.scalar_one_or_none():
            slots_need_sync = True
    
    # Get pool details based on filtering
    if common_pool_ids:
        result = await db.execute(
            select(Pool).where(
                and_(
                    Pool.id.in_(common_pool_ids),
                    Pool.enabled == True
                )
            ).order_by(Pool.name)
        )
    elif has_nano_miners:
        # Have nano miners but no common pools - show empty to prevent misconfiguration
        result = await db.execute(select(Pool).where(Pool.id == -1))  # No results
    else:
        # No nano miners - show all pools
        result = await db.execute(select(Pool).where(Pool.enabled == True).order_by(Pool.name))
    
    pools = result.scalars().all()
    has_nano_miners = len(common_pool_ids) > 0 or (has_nano_miners and not common_pool_ids)
    
    return templates.TemplateResponse("pools/strategy_edit.html", {
        "request": request,
        "page_title": f"Edit Strategy: {strategy.name}",
        "breadcrumbs": [
            {"label": "Dashboard", "url": "/"},
            {"label": "Pools", "url": "/pools"},
            {"label": "Strategies", "url": "/pools/strategies"},
            {"label": strategy.name, "url": f"/pools/strategies/{strategy_id}/edit"}
        ],
        "strategy": strategy,
        "pools": pools,
        "has_nano_miners": has_nano_miners,
        "slots_need_sync": slots_need_sync
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
            {"label": "Automation", "url": "/automation"}
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
            {"label": "Automation", "url": "/automation"},
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
            {"label": "Automation", "url": "/automation"},
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
            {"label": "Settings", "url": "/settings"},
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
            {"label": "Settings", "url": "/settings"},
            {"label": "Energy Optimization", "url": "/settings/optimization"}
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


@router.get("/settings/mqtt", response_class=HTMLResponse)
async def mqtt_settings(request: Request):
    """MQTT Configuration page"""
    return templates.TemplateResponse("settings/mqtt.html", {
        "request": request,
        "page_title": "MQTT Configuration",
        "breadcrumbs": [
            {"label": "Dashboard", "url": "/"},
            {"label": "Settings", "url": "/settings"},
            {"label": "MQTT Configuration", "url": "/settings/mqtt"}
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


@router.get("/analytics", response_class=HTMLResponse)
async def analytics(request: Request):
    """Analytics page"""
    return templates.TemplateResponse("analytics.html", {
        "request": request,
        "page_title": "Analytics",
        "breadcrumbs": [
            {"label": "Dashboard", "url": "/"},
            {"label": "Analytics", "url": "/analytics"}
        ]
    })


@router.get("/analytics/overview", response_class=HTMLResponse)
async def analytics_overview(request: Request):
    """Long-term analytics overview page"""
    return templates.TemplateResponse("analytics/overview.html", {
        "request": request,
        "page_title": "Analytics Overview",
        "breadcrumbs": [
            {"label": "Dashboard", "url": "/"},
            {"label": "Analytics", "url": "/analytics"},
            {"label": "Overview", "url": "/analytics/overview"}
        ]
    })


@router.get("/analytics/miners", response_class=HTMLResponse)
async def analytics_miners(request: Request):
    """Miners analytics page"""
    return templates.TemplateResponse("analytics/miners.html", {
        "request": request,
        "page_title": "Miner Analytics",
        "breadcrumbs": [
            {"label": "Dashboard", "url": "/"},
            {"label": "Analytics", "url": "/analytics"},
            {"label": "Miners", "url": "/analytics/miners"}
        ]
    })


@router.get("/analytics/{miner_id}", response_class=HTMLResponse)
async def analytics_detail(request: Request, miner_id: int, db: AsyncSession = Depends(get_db)):
    """Analytics detail page for specific miner"""
    # Get miner name for breadcrumb
    result = await db.execute(select(Miner).where(Miner.id == miner_id))
    miner = result.scalar_one_or_none()
    miner_name = miner.name if miner else f"Miner {miner_id}"
    
    return templates.TemplateResponse("analytics_detail.html", {
        "request": request,
        "page_title": f"Analytics - {miner_name}",
        "breadcrumbs": [
            {"label": "Dashboard", "url": "/"},
            {"label": "Analytics", "url": "/analytics"},
            {"label": miner_name, "url": f"/analytics/{miner_id}"}
        ]
    })


@router.get("/faq", response_class=HTMLResponse)
async def faq(request: Request):
    """FAQ page"""
    return templates.TemplateResponse("faq.html", {
        "request": request,
        "page_title": "FAQ",
        "breadcrumbs": [
            {"label": "Dashboard", "url": "/"},
            {"label": "FAQ", "url": "/faq"}
        ]
    })


@router.get("/dashboards", response_class=HTMLResponse)
async def custom_dashboards_list(request: Request):
    """Custom dashboards management page"""
    return templates.TemplateResponse("dashboards/list.html", {
        "request": request,
        "page_title": "Custom Dashboards",
        "breadcrumbs": [
            {"label": "Dashboard", "url": "/"},
            {"label": "Custom Dashboards", "url": "/dashboards"}
        ]
    })


@router.get("/dashboards/{dashboard_id}", response_class=HTMLResponse)
async def view_custom_dashboard(request: Request, dashboard_id: int):
    """View a specific custom dashboard"""
    return templates.TemplateResponse("dashboards/view.html", {
        "request": request,
        "page_title": "Custom Dashboard",
        "breadcrumbs": [
            {"label": "Dashboard", "url": "/"},
            {"label": "Custom Dashboards", "url": "/dashboards"},
            {"label": "View", "url": f"/dashboards/{dashboard_id}"}
        ],
        "dashboard_id": dashboard_id
    })
