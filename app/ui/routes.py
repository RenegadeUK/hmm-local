"""
UI routes for Jinja2 templates
"""
from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pathlib import Path

from core.database import get_db, Miner, Pool, AutomationRule


templates_dir = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(templates_dir))

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, db: AsyncSession = Depends(get_db)):
    """Dashboard page"""
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
    result = await db.execute(select(Miner))
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
    result = await db.execute(select(Pool))
    pools = result.scalars().all()
    
    return templates.TemplateResponse("pools/list.html", {
        "request": request,
        "page_title": "Mining Pools",
        "breadcrumbs": [
            {"label": "Dashboard", "url": "/"},
            {"label": "Pools", "url": "/pools"}
        ],
        "pools": pools
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


@router.get("/energy", response_class=HTMLResponse)
async def energy_pricing(request: Request):
    """Energy pricing page"""
    return templates.TemplateResponse("energy/pricing.html", {
        "request": request,
        "page_title": "Energy Pricing",
        "breadcrumbs": [
            {"label": "Dashboard", "url": "/"},
            {"label": "Energy Pricing", "url": "/energy"}
        ]
    })


@router.get("/logs", response_class=HTMLResponse)
async def logs(request: Request):
    """System logs page"""
    return templates.TemplateResponse("logs.html", {
        "request": request,
        "page_title": "System Logs",
        "breadcrumbs": [
            {"label": "Dashboard", "url": "/"},
            {"label": "Logs", "url": "/logs"}
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


@router.get("/notifications", response_class=HTMLResponse)
async def notifications(request: Request):
    """Notifications page"""
    return templates.TemplateResponse("notifications.html", {
        "request": request,
        "page_title": "Notifications",
        "breadcrumbs": [
            {"label": "Dashboard", "url": "/"},
            {"label": "Notifications", "url": "/notifications"}
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
