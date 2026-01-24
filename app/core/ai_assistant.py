"""
Sam - AI Mining Assistant
OpenAI-powered assistant for mining operation optimization
"""
import logging
from typing import List, Dict, Optional, AsyncGenerator
from datetime import datetime, timedelta
from openai import AsyncOpenAI
import json
import os
from pathlib import Path

from core.config import app_config
from core.database import AsyncSessionLocal, Miner, Telemetry, BlockFound, EnergyPrice, HighDiffShare
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# Documentation directory (mounted in /config volume)
DOCS_DIR = Path("/config/docs")
STARTER_DOCS_DIR = Path(__file__).parent.parent / "docs" / "starter"

def _initialize_docs():
    """
    Copy starter documentation to /config/docs/ if it doesn't exist.
    This runs once on first startup to provide default docs.
    Users can then customize them without losing changes on updates.
    """
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    
    # Only copy if /config/docs/ is empty
    if not any(DOCS_DIR.rglob("*.md")):
        if STARTER_DOCS_DIR.exists():
            logger.info("Initializing Sam documentation from starter templates...")
            import shutil
            shutil.copytree(STARTER_DOCS_DIR, DOCS_DIR, dirs_exist_ok=True)
            logger.info(f"Documentation initialized: {len(list(DOCS_DIR.rglob('*.md')))} files")
        else:
            logger.warning("Starter docs not found - Sam will work but with limited context")

# Initialize docs on module load (runs once per container start)
_initialize_docs()

# =============================================================================
# FUNCTION CALLING TOOLS FOR SAM
# =============================================================================

SAM_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_telemetry_stats",
            "description": "Get statistical summary of telemetry data for a miner over a time period. Use this to analyze hashrate trends, detect degradation, or calculate averages.",
            "parameters": {
                "type": "object",
                "properties": {
                    "miner_id": {
                        "type": "integer",
                        "description": "The miner ID to get stats for"
                    },
                    "days": {
                        "type": "integer",
                        "description": "Number of days to look back (default: 7, max: 90)"
                    }
                },
                "required": ["miner_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_all_miners_power_usage",
            "description": "Calculate total power consumption and cost across ALL miners over a time period. Use this for questions like 'how much power/money did I spend?' or 'what's my total electricity cost?'",
            "parameters": {
                "type": "object",
                "properties": {
                    "days": {
                        "type": "integer",
                        "description": "Number of days to look back (default: 7, max: 90)"
                    },
                    "daily_breakdown": {
                        "type": "boolean",
                        "description": "Return per-day breakdown (default: false). Use true for questions like 'which day was most expensive?'"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_hashrate_trend",
            "description": "Analyze hashrate trend over time to detect degradation. Returns daily averages and calculates percentage change.",
            "parameters": {
                "type": "object",
                "properties": {
                    "miner_id": {
                        "type": "integer",
                        "description": "The miner ID to analyze"
                    },
                    "days": {
                        "type": "integer",
                        "description": "Number of days to analyze (default: 30, max: 90)"
                    }
                },
                "required": ["miner_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_oldest_telemetry",
            "description": "Get the timestamp of the oldest telemetry record in the database.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_block_history",
            "description": "Get blocks found by a miner (or all miners) over a time period.",
            "parameters": {
                "type": "object",
                "properties": {
                    "miner_id": {
                        "type": "integer",
                        "description": "The miner ID to get blocks for (optional - omit for all miners)"
                    },
                    "days": {
                        "type": "integer",
                        "description": "Number of days to look back (default: 30, max: 365)"
                    },
                    "coin": {
                        "type": "string",
                        "description": "Filter by coin (BTC, BCH, DGB, BC2, XMR) - optional"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_price_history",
            "description": "Get electricity price history (Octopus Agile) for trend analysis.",
            "parameters": {
                "type": "object",
                "properties": {
                    "days": {
                        "type": "integer",
                        "description": "Number of days to look back (default: 7, max: 30)"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "query_telemetry_range",
            "description": "Get raw telemetry records for detailed analysis. Returns timestamp, hashrate, temperature, power, shares for each record.",
            "parameters": {
                "type": "object",
                "properties": {
                    "miner_id": {
                        "type": "integer",
                        "description": "The miner ID to query"
                    },
                    "start_date": {
                        "type": "string",
                        "description": "Start date in YYYY-MM-DD format"
                    },
                    "end_date": {
                        "type": "string",
                        "description": "End date in YYYY-MM-DD format"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum records to return (default: 1000, max: 10000)"
                    }
                },
                "required": ["miner_id", "start_date", "end_date"]
            }
        }
    }
]

# =============================================================================
# FUNCTION HANDLERS - Execute database queries for Sam
# =============================================================================

async def _execute_tool(tool_name: str, arguments: Dict, db: AsyncSession) -> str:
    """
    Execute a tool function and return JSON string result.
    All functions are read-only and safe to execute.
    """
    try:
        args = arguments
        
        if tool_name == "get_telemetry_stats":
            miner_id = args["miner_id"]
            days = min(args.get("days", 7), 90)
            since = datetime.utcnow() - timedelta(days=days)
            
            result = await db.execute(
                select(
                    func.count(Telemetry.id).label("count"),
                    func.avg(Telemetry.hashrate).label("avg_hashrate"),
                    func.min(Telemetry.hashrate).label("min_hashrate"),
                    func.max(Telemetry.hashrate).label("max_hashrate"),
                    func.avg(Telemetry.temperature).label("avg_temperature"),
                    func.max(Telemetry.temperature).label("max_temperature"),
                    func.avg(Telemetry.power_watts).label("avg_power_watts"),
                    func.sum(Telemetry.shares_accepted).label("total_accepted"),
                    func.sum(Telemetry.shares_rejected).label("total_rejected"),
                    Telemetry.hashrate_unit
                )
                .where(Telemetry.miner_id == miner_id, Telemetry.timestamp >= since)
                .group_by(Telemetry.hashrate_unit)
            )
            row = result.first()
            
            if not row or row.count == 0:
                return json.dumps({"error": f"No telemetry found for miner {miner_id} in last {days} days"})
            
            reject_rate = (row.total_rejected / (row.total_accepted + row.total_rejected) * 100) if (row.total_accepted + row.total_rejected) > 0 else 0
            
            return json.dumps({
                "miner_id": miner_id,
                "days": days,
                "record_count": row.count,
                "avg_hashrate": f"{row.avg_hashrate:.2f} {row.hashrate_unit}",
                "min_hashrate": f"{row.min_hashrate:.2f} {row.hashrate_unit}",
                "max_hashrate": f"{row.max_hashrate:.2f} {row.hashrate_unit}",
                "avg_temperature": f"{row.avg_temperature:.1f}°C" if row.avg_temperature else "N/A",
                "max_temperature": f"{row.max_temperature:.1f}°C" if row.max_temperature else "N/A",
                "avg_power": f"{row.avg_power_watts:.1f}W" if row.avg_power_watts else "N/A",
                "shares_accepted": row.total_accepted,
                "shares_rejected": row.total_rejected,
                "reject_rate": f"{reject_rate:.2f}%"
            })
        
        elif tool_name == "get_all_miners_power_usage":
            days = min(args.get("days", 7), 90)
            daily_breakdown = args.get("daily_breakdown", False)
            since = datetime.utcnow() - timedelta(days=days)
            
            # Load region from config
            from core.config import app_config
            region = app_config.get("octopus_agile.region", "H")
            
            # Get all telemetry with power data
            result = await db.execute(
                select(Telemetry)
                .where(
                    Telemetry.timestamp >= since,
                    Telemetry.power_watts.isnot(None)
                )
                .order_by(Telemetry.timestamp)
            )
            telemetry_records = result.scalars().all()
            
            if not telemetry_records:
                return json.dumps({"error": "No power data found"})
            
            # Calculate cost
            if daily_breakdown:
                # Group by day
                from collections import defaultdict
                daily_data = defaultdict(lambda: {"cost_pence": 0, "kwh": 0, "records": 0})
                
                for telem in telemetry_records:
                    if not telem.power_watts or telem.power_watts <= 0:
                        continue
                    
                    day_key = telem.timestamp.date().isoformat()
                    
                    # Find energy price
                    price_result = await db.execute(
                        select(EnergyPrice)
                        .where(EnergyPrice.region == region)
                        .where(EnergyPrice.valid_from <= telem.timestamp)
                        .where(EnergyPrice.valid_to > telem.timestamp)
                        .limit(1)
                    )
                    price = price_result.scalar_one_or_none()
                    
                    if price:
                        interval_hours = 30 / 3600
                        energy_kwh = (telem.power_watts / 1000) * interval_hours
                        daily_data[day_key]["cost_pence"] += energy_kwh * price.price_pence
                        daily_data[day_key]["kwh"] += energy_kwh
                        daily_data[day_key]["records"] += 1
                
                # Format daily results
                daily_costs = []
                for day, data in sorted(daily_data.items()):
                    daily_costs.append({
                        "date": day,
                        "cost": f"£{data['cost_pence'] / 100:.2f}",
                        "kwh": round(data["kwh"], 2)
                    })
                
                return json.dumps({"days": days, "daily_breakdown": daily_costs})
            
            else:
                # Total only (existing logic)
                total_cost_pence = 0
                
                for telem in telemetry_records:
                    if not telem.power_watts or telem.power_watts <= 0:
                        continue
                    
                    price_result = await db.execute(
                        select(EnergyPrice)
                        .where(EnergyPrice.region == region)
                        .where(EnergyPrice.valid_from <= telem.timestamp)
                        .where(EnergyPrice.valid_to > telem.timestamp)
                        .limit(1)
                    )
                    price = price_result.scalar_one_or_none()
                    
                    if price:
                        interval_hours = 30 / 3600
                        energy_kwh = (telem.power_watts / 1000) * interval_hours
                        total_cost_pence += energy_kwh * price.price_pence
                
                total_cost_gbp = total_cost_pence / 100
                total_kwh = sum((t.power_watts / 1000) * (30 / 3600) for t in telemetry_records if t.power_watts)
                avg_power = sum(t.power_watts for t in telemetry_records if t.power_watts) / len([t for t in telemetry_records if t.power_watts])
                
                result_data = {
                    "days": days,
                    "total_kwh": round(total_kwh, 2),
                    "total_cost": f"£{round(total_cost_gbp, 2):.2f}",
                    "avg_power_watts": round(avg_power, 2),
                    "daily_cost": f"£{round(total_cost_gbp / days, 2):.2f}"
                }
                
                logger.info(f"Power usage calculation: {result_data}")
                return json.dumps(result_data)
        
        elif tool_name == "get_hashrate_trend":
            miner_id = args["miner_id"]
            days = min(args.get("days", 30), 90)
            since = datetime.utcnow() - timedelta(days=days)
            
            # Get daily averages
            result = await db.execute(
                select(
                    func.date(Telemetry.timestamp).label("date"),
                    func.avg(Telemetry.hashrate).label("avg_hashrate"),
                    Telemetry.hashrate_unit
                )
                .where(Telemetry.miner_id == miner_id, Telemetry.timestamp >= since)
                .group_by(func.date(Telemetry.timestamp), Telemetry.hashrate_unit)
                .order_by(func.date(Telemetry.timestamp))
            )
            rows = result.all()
            
            if not rows:
                return json.dumps({"error": f"No telemetry found for miner {miner_id} in last {days} days"})
            
            daily_data = [{"date": str(row.date), "avg_hashrate": float(row.avg_hashrate)} for row in rows]
            first_week_avg = sum(d["avg_hashrate"] for d in daily_data[:7]) / min(7, len(daily_data))
            last_week_avg = sum(d["avg_hashrate"] for d in daily_data[-7:]) / min(7, len(daily_data))
            percent_change = ((last_week_avg - first_week_avg) / first_week_avg * 100) if first_week_avg > 0 else 0
            
            unit = rows[0].hashrate_unit if rows else "GH/s"
            
            return json.dumps({
                "miner_id": miner_id,
                "days_analyzed": len(daily_data),
                "first_week_avg": f"{first_week_avg:.2f} {unit}",
                "last_week_avg": f"{last_week_avg:.2f} {unit}",
                "percent_change": f"{percent_change:+.2f}%",
                "trend": "declining" if percent_change < -5 else "stable" if abs(percent_change) <= 5 else "improving",
                "daily_averages": daily_data
            })
        
        elif tool_name == "get_oldest_telemetry":
            result = await db.execute(
                select(func.min(Telemetry.timestamp))
            )
            oldest = result.scalar()
            
            if not oldest:
                return json.dumps({"error": "No telemetry records found"})
            
            age_days = (datetime.utcnow() - oldest).days
            return json.dumps({
                "oldest_timestamp": oldest.isoformat(),
                "age_days": age_days,
                "human_readable": f"{age_days} days ago ({oldest.strftime('%Y-%m-%d %H:%M:%S')})"
            })
        
        elif tool_name == "get_block_history":
            days = min(args.get("days", 30), 365)
            since = datetime.utcnow() - timedelta(days=days)
            
            query = select(BlockFound).where(BlockFound.timestamp >= since)
            
            if "miner_id" in args:
                query = query.where(BlockFound.miner_id == args["miner_id"])
            if "coin" in args:
                query = query.where(BlockFound.coin == args["coin"].upper())
            
            query = query.order_by(desc(BlockFound.timestamp)).limit(100)
            
            result = await db.execute(query)
            blocks = result.scalars().all()
            
            if not blocks:
                return json.dumps({"blocks": [], "total": 0})
            
            blocks_data = [{
                "miner_name": b.miner_name,
                "coin": b.coin,
                "difficulty": float(b.difficulty),
                "network_difficulty": float(b.network_difficulty) if b.network_difficulty else None,
                "block_height": b.block_height,
                "block_reward": float(b.block_reward) if b.block_reward else None,
                "timestamp": b.timestamp.isoformat()
            } for b in blocks]
            
            return json.dumps({
                "blocks": blocks_data,
                "total": len(blocks),
                "days": days,
                "by_coin": {coin: sum(1 for b in blocks if b.coin == coin) for coin in set(b.coin for b in blocks)}
            })
        
        elif tool_name == "get_price_history":
            days = min(args.get("days", 7), 30)
            since = datetime.utcnow() - timedelta(days=days)
            
            result = await db.execute(
                select(EnergyPrice)
                .where(EnergyPrice.valid_from >= since)
                .order_by(EnergyPrice.valid_from)
            )
            prices = result.scalars().all()
            
            if not prices:
                return json.dumps({"error": "No price data found"})
            
            price_data = [{
                "timestamp": p.valid_from.isoformat(),
                "price_pence": float(p.price_pence),
                "region": p.region
            } for p in prices]
            
            avg_price = sum(p.price_pence for p in prices) / len(prices)
            min_price = min(p.price_pence for p in prices)
            max_price = max(p.price_pence for p in prices)
            
            return json.dumps({
                "records": price_data[:100],  # Limit to 100 for context
                "stats": {
                    "avg_price": f"{avg_price:.2f}p/kWh",
                    "min_price": f"{min_price:.2f}p/kWh",
                    "max_price": f"{max_price:.2f}p/kWh",
                    "total_slots": len(prices)
                }
            })
        
        elif tool_name == "query_telemetry_range":
            miner_id = args["miner_id"]
            start_date = datetime.fromisoformat(args["start_date"])
            end_date = datetime.fromisoformat(args["end_date"])
            limit = min(args.get("limit", 1000), 10000)
            
            result = await db.execute(
                select(Telemetry)
                .where(
                    Telemetry.miner_id == miner_id,
                    Telemetry.timestamp >= start_date,
                    Telemetry.timestamp <= end_date
                )
                .order_by(Telemetry.timestamp)
                .limit(limit)
            )
            records = result.scalars().all()
            
            if not records:
                return json.dumps({"error": "No telemetry found in date range"})
            
            telemetry_data = [{
                "timestamp": t.timestamp.isoformat(),
                "hashrate": f"{t.hashrate:.2f} {t.hashrate_unit}" if t.hashrate else "N/A",
                "temperature": f"{t.temperature:.1f}°C" if t.temperature else "N/A",
                "power_watts": f"{t.power_watts:.1f}W" if t.power_watts else "N/A",
                "shares_accepted": t.shares_accepted,
                "shares_rejected": t.shares_rejected,
                "pool": t.pool_in_use
            } for t in records]
            
            return json.dumps({
                "miner_id": miner_id,
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "record_count": len(records),
                "records": telemetry_data
            })
        
        else:
            return json.dumps({"error": f"Unknown tool: {tool_name}"})
    
    except Exception as e:
        logger.error(f"Error executing tool {tool_name}: {e}")
        return json.dumps({"error": str(e)})


def get_openai_api_key() -> Optional[str]:
    """Get OpenAI API key from config (encrypted storage)"""
    config = app_config.get("openai", {})
    if not config.get("enabled", False):
        return None
    
    api_key = config.get("api_key")
    if not api_key:
        return None
    
    # TODO: Decrypt if encrypted
    # For now, store plaintext (will encrypt in production)
    return api_key


class SamAssistant:
    """Sam - AI Mining Assistant using OpenAI GPT-4 or Ollama"""
    
    def __init__(self):
        self.api_key = get_openai_api_key()
        config = app_config.get("openai", {})
        
        # Get provider (default to openai)
        provider = config.get("provider", "openai")
        self.model = config.get("model", "gpt-4o")
        self.max_tokens = config.get("max_tokens", 1000)
        
        # Configure client based on provider
        if provider == "ollama":
            # Ollama: Use base_url, doesn't need real API key
            base_url = config.get("base_url", "http://localhost:11434/v1")
            self.client = AsyncOpenAI(
                api_key="ollama",  # Ollama doesn't use API keys
                base_url=base_url
            )
        elif self.api_key:
            # OpenAI: Use API key
            base_url = config.get("base_url", "https://api.openai.com/v1")
            self.client = AsyncOpenAI(
                api_key=self.api_key,
                base_url=base_url
            )
        else:
            self.client = None
    
    def is_enabled(self) -> bool:
        """Check if Sam is enabled and configured"""
        return self.client is not None
    
    def _load_documentation(self) -> Dict[str, str]:
        """
        Load markdown documentation files from /config/docs/
        
        This allows features to be documented externally and Sam stays current.
        Files are organized by category:
        - /config/docs/features/*.md - Feature documentation
        - /config/docs/coins/*.md - Coin-specific info
        - /config/docs/strategies/*.md - Strategy explanations
        - /config/docs/README.md - Overview
        
        Returns:
            Dict mapping filename to content
        """
        docs = {}
        
        if not DOCS_DIR.exists():
            return docs
        
        # Recursively find all .md files
        for md_file in DOCS_DIR.rglob("*.md"):
            try:
                relative_path = md_file.relative_to(DOCS_DIR)
                content = md_file.read_text(encoding='utf-8')
                docs[str(relative_path)] = content
                logger.debug(f"Loaded documentation: {relative_path}")
            except Exception as e:
                logger.warning(f"Failed to load {md_file}: {e}")
        
        return docs
    
    async def test_connection(self) -> Dict:
        """Test OpenAI API connection"""
        if not self.client:
            return {"success": False, "error": "API key not configured"}
        
        try:
            # Simple test call
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": "Hello"}],
                max_tokens=10
            )
            return {
                "success": True,
                "model": self.model,
                "response": response.choices[0].message.content
            }
        except Exception as e:
            logger.error(f"OpenAI connection test failed: {e}")
            return {"success": False, "error": str(e)}
    
    async def chat(
        self,
        user_message: str,
        conversation_history: List[Dict] = None
    ) -> AsyncGenerator[str, None]:
        """
        Chat with Sam (streaming response with function calling)
        
        Args:
            user_message: User's question
            conversation_history: Previous messages in conversation
        
        Yields:
            Chunks of Sam's response
        """
        if not self.client:
            yield "Sam is not configured. Please add an OpenAI API key in Settings > Integrations."
            return
        
        try:
            # Immediate feedback
            yield "⏳ Analyzing...\n\n"
            
            # Build context from current system state
            # MINIMAL VERSION for Ollama with limited context (4k tokens)
            context = await self._build_minimal_context()
            
            # Build message history
            messages = [
                {"role": "system", "content": self._get_system_prompt()},
                {"role": "system", "content": f"System State: {json.dumps(context)}"}
            ]
            
            # Add conversation history (limit to last 3 messages for context-limited models)
            if conversation_history:
                messages.extend(conversation_history[-3:])  # Reduced from 10 to 3
            
            # Add user message
            messages.append({"role": "user", "content": user_message})
            
            # Function calling loop - Sam can request data multiple times
            max_iterations = 5  # Prevent infinite loops
            iteration = 0
            
            while iteration < max_iterations:
                iteration += 1
                
                # Call OpenAI with tools
                response = await self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    max_tokens=self.max_tokens,
                    tools=SAM_TOOLS,
                    tool_choice="auto",
                    temperature=0.7
                )
                
                message = response.choices[0].message
                
                # DEBUG: Log the exact response format
                logger.info(f"🔍 DEBUG: message.tool_calls = {message.tool_calls}")
                logger.info(f"🔍 DEBUG: message.content = {repr(message.content)}")
                logger.info(f"🔍 DEBUG: message.finish_reason = {response.choices[0].finish_reason}")
                
                # Check if model returned tool calls properly (OpenAI format)
                if message.tool_calls:
                    # Standard OpenAI tool calling - works as expected
                    pass
                
                # Fallback: Check if Ollama returned tool call as text content
                elif message.content and message.content.strip().startswith("{"):
                    try:
                        content_str = message.content.strip()
                        
                        # Fix unquoted function names (Ollama bug)
                        # {"name": get_all_miners_power_usage, ...} -> {"name": "get_all_miners_power_usage", ...}
                        import re
                        content_str = re.sub(r'("name":\s*)([a-zA-Z_][a-zA-Z0-9_]*)', r'\1"\2"', content_str)
                        
                        # Try to parse as JSON tool call
                        content_json = json.loads(content_str)
                        if "name" in content_json and "arguments" in content_json:
                            logger.info(f"Ollama returned tool call as text, converting to tool_calls format")
                            
                            # Create a mock tool_call structure
                            from types import SimpleNamespace
                            mock_tool_call = SimpleNamespace(
                                id=f"call_{iteration}",
                                type="function",
                                function=SimpleNamespace(
                                    name=content_json["name"],
                                    arguments=json.dumps(content_json["arguments"])
                                )
                            )
                            message.tool_calls = [mock_tool_call]
                            message.content = None  # Clear content since we converted it
                    except json.JSONDecodeError:
                        # Not a JSON tool call, treat as regular response
                        pass
                
                # If Sam wants to call functions, execute them
                if message.tool_calls:
                    # Add assistant message with tool calls to history
                    messages.append({
                        "role": "assistant",
                        "content": message.content,
                        "tool_calls": [
                            {
                                "id": tc.id,
                                "type": "function",
                                "function": {
                                    "name": tc.function.name,
                                    "arguments": tc.function.arguments
                                }
                            } for tc in message.tool_calls
                        ]
                    })
                    
                    # Execute each tool call
                    async with AsyncSessionLocal() as db:
                        for tool_call in message.tool_calls:
                            function_name = tool_call.function.name
                            function_args = json.loads(tool_call.function.arguments)
                            
                            logger.info(f"Sam executing tool: {function_name} with args: {function_args}")
                            
                            # Inform user what Sam is doing
                            yield f"[Analyzing {function_name}...]\n\n"
                            
                            # Execute the function
                            result = await _execute_tool(function_name, function_args, db)
                            
                            logger.info(f"Tool {function_name} result length: {len(result)} chars")
                            
                            # Add tool result to messages
                            messages.append({
                                "role": "tool",
                                "tool_call_id": tool_call.id,
                                "content": result
                            })
                    
                    # Continue loop to let Sam process the results
                    continue
                
                # Sam has finished (no more tool calls), yield the response
                if message.content:
                    logger.info(f"Sam response content: {message.content[:100]}...")
                    yield message.content
                else:
                    logger.warning("Sam returned no content after tool calls")
                    yield "I analyzed the data but have no response content."
                
                break  # Done
        
        except Exception as e:
            logger.error(f"Sam chat error: {e}", exc_info=True)
            yield f"Sorry, I encountered an error: {str(e)}"
    
    def _get_system_prompt(self) -> str:
        """Get Sam's system prompt - optimized for models with limited context"""
        return """You are Sam, an AI mining assistant for Home Miner Manager.

## YOUR ROLE
Analyze mining data and provide insights. You are READ-ONLY - you cannot control miners.

## FUNCTION CALLING TOOLS
Use these when users ask historical questions:
- get_all_miners_power_usage(days) - Total power cost across ALL miners
- get_telemetry_stats(miner_id, days) - Stats for ONE miner
- get_hashrate_trend(miner_id, days) - Detect hashrate degradation
- get_block_history(miner_id, days, coin) - Blocks found
- get_price_history(days) - Electricity price trends

## KEY FACTS
- You get "Current System State" JSON with all current data
- For historical data beyond current state, USE FUNCTION CALLING
- Home mining is a hobby/lottery, not profitable at small scale
- UK Octopus Agile pricing changes every 30min

Be concise and data-driven."""
    
    async def _build_minimal_context(self) -> Dict:
        """
        Build MINIMAL system context for models with limited context window (e.g., Ollama 4k tokens)
        Only includes essential current state - historical data available via function calling
        """
        async with AsyncSessionLocal() as db:
            context = {}
            now = datetime.utcnow()
            
            # Current electricity price only
            result = await db.execute(
                select(EnergyPrice)
                .where(EnergyPrice.valid_from <= now)
                .where(EnergyPrice.valid_to > now)
                .limit(1)
            )
            current_price = result.scalar_one_or_none()
            if current_price:
                context["current_price_pence"] = float(current_price.price_pence)
            
            # Miners: name, type, enabled, current stats only
            result = await db.execute(select(Miner).where(Miner.enabled == True))
            enabled_miners = result.scalars().all()
            
            miners_data = []
            for miner in enabled_miners:
                # Latest telemetry only
                telem_result = await db.execute(
                    select(Telemetry)
                    .where(Telemetry.miner_id == miner.id)
                    .order_by(desc(Telemetry.timestamp))
                    .limit(1)
                )
                latest = telem_result.scalar_one_or_none()
                
                if latest:
                    miners_data.append({
                        "name": miner.name,
                        "type": miner.miner_type,
                        "hashrate": f"{latest.hashrate:.1f} {latest.hashrate_unit}",
                        "temp": f"{latest.temperature:.0f}°C" if latest.temperature else "N/A",
                        "power": f"{latest.power_watts:.0f}W" if latest.power_watts else "N/A"
                    })
            
            context["miners"] = miners_data
            context["total_miners"] = len(miners_data)
            
            return context
    
    async def _build_context(self) -> Dict:
        """
        Build comprehensive system context for Sam
        
        SECURITY: Explicitly filters out sensitive data (passwords, API keys, tokens)
        ACCESS: Provides operational data needed for insights and recommendations
        DYNAMIC: Reads actual database state + documentation files for current features
        """
        async with AsyncSessionLocal() as db:
            from core.database import Pool, AutomationRule, PoolHealth, HealthScore, AuditLog, CryptoPrice
            
            context = {}
            now = datetime.utcnow()
            cutoff_24h = now - timedelta(hours=24)
            
            # === DYNAMIC DOCUMENTATION ===
            # Load any markdown docs from /config/docs/ to stay current with features
            context['documentation'] = self._load_documentation()
            
            # === SUPPORTED COINS (Dynamic Discovery) ===
            # Instead of hardcoding, discover what coins actually have price data
            result = await db.execute(select(CryptoPrice))
            crypto_prices = result.scalars().all()
            context['supported_coins'] = {
                cp.coin_id: {
                    'price_gbp': cp.price_gbp,
                    'source': cp.source,
                    'updated_at': cp.updated_at.isoformat() if cp.updated_at else None
                }
                for cp in crypto_prices
            }
            
            # === ENERGY DATA ===
            # Current price
            result = await db.execute(
                select(EnergyPrice)
                .where(EnergyPrice.valid_from <= now)
                .where(EnergyPrice.valid_to > now)
                .limit(1)
            )
            current_price = result.scalar_one_or_none()
            if current_price:
                context["current_electricity_price_pence"] = float(current_price.price_pence)
            
            # Next 6 hours pricing
            result = await db.execute(
                select(EnergyPrice)
                .where(EnergyPrice.valid_from >= now)
                .order_by(EnergyPrice.valid_from)
                .limit(12)  # 6 hours at 30min intervals
            )
            future_prices = result.scalars().all()
            context["next_6h_prices"] = [
                {
                    "time": p.valid_from.isoformat(),
                    "price_pence": float(p.price_pence)
                }
                for p in future_prices
            ]
            
            # === MINER DATA ===
            result = await db.execute(select(Miner))
            all_miners = result.scalars().all()
            
            miners_data = []
            for miner in all_miners:
                # Latest telemetry
                telem_result = await db.execute(
                    select(Telemetry)
                    .where(Telemetry.miner_id == miner.id)
                    .order_by(desc(Telemetry.timestamp))
                    .limit(1)
                )
                latest = telem_result.scalar_one_or_none()
                
                # Last 24h average telemetry
                cutoff_24h = now - timedelta(hours=24)
                avg_result = await db.execute(
                    select(
                        func.avg(Telemetry.hashrate).label('avg_hashrate'),
                        func.avg(Telemetry.temperature).label('avg_temp'),
                        func.avg(Telemetry.power_watts).label('avg_power'),
                        func.sum(Telemetry.shares_accepted).label('total_accepted'),
                        func.sum(Telemetry.shares_rejected).label('total_rejected')
                    )
                    .where(Telemetry.miner_id == miner.id)
                    .where(Telemetry.timestamp >= cutoff_24h)
                )
                avg_data = avg_result.first()
                
                miner_info = {
                    "name": miner.name,
                    "type": miner.miner_type,
                    "enabled": miner.enabled,
                    "current_mode": miner.current_mode,
                    "pool": latest.pool_in_use if latest else None  # Pool from telemetry, not miner
                }
                
                if latest:
                    miner_info["current_state"] = {
                        "hashrate": float(latest.hashrate) if latest.hashrate else 0,
                        "hashrate_unit": latest.hashrate_unit,
                        "temperature": float(latest.temperature) if latest.temperature else 0,
                        "power_watts": float(latest.power_watts) if latest.power_watts else 0,
                        "shares_accepted": latest.shares_accepted or 0,
                        "shares_rejected": latest.shares_rejected or 0,
                        "last_seen": latest.timestamp.isoformat()
                    }
                
                if avg_data and avg_data.avg_hashrate:
                    miner_info["24h_averages"] = {
                        "hashrate": float(avg_data.avg_hashrate),
                        "temperature": float(avg_data.avg_temp) if avg_data.avg_temp else 0,
                        "power_watts": float(avg_data.avg_power) if avg_data.avg_power else 0,
                        "total_shares_accepted": int(avg_data.total_accepted or 0),
                        "total_shares_rejected": int(avg_data.total_rejected or 0),
                        "reject_rate_percent": (float(avg_data.total_rejected) / float(avg_data.total_accepted + avg_data.total_rejected) * 100) if (avg_data.total_accepted or avg_data.total_rejected) else 0
                    }
                
                miners_data.append(miner_info)
            
            context["miners"] = miners_data
            
            # === POOL DATA (NO CREDENTIALS) ===
            result = await db.execute(select(Pool))
            pools = result.scalars().all()
            context["pools"] = [
                {
                    "name": p.name,
                    "enabled": p.enabled,
                    "priority": p.priority,
                    "url": p.url  # URL is OK, just no passwords
                }
                for p in pools
            ]
            
            # Pool health
            result = await db.execute(
                select(PoolHealth, Pool.name)
                .join(Pool, PoolHealth.pool_id == Pool.id)
                .where(PoolHealth.timestamp >= cutoff_24h)
                .order_by(desc(PoolHealth.timestamp))
            )
            pool_health_records = result.all()
            pool_health_summary = {}
            for ph, pool_name in pool_health_records:
                if pool_name not in pool_health_summary:
                    pool_health_summary[pool_name] = {
                        "latest_health_score": ph.health_score,
                        "reachable": ph.is_reachable,
                        "response_time_ms": ph.response_time_ms,
                        "reject_rate": ph.reject_rate
                    }
            context["pool_health"] = pool_health_summary
            
            # === BLOCKS & HIGH DIFF SHARES ===
            # All blocks (not just 24h)
            result = await db.execute(
                select(BlockFound).order_by(desc(BlockFound.timestamp))
            )
            all_blocks = result.scalars().all()
            context["all_blocks_found"] = [
                {
                    "miner": b.miner_name,
                    "coin": b.coin,
                    "difficulty": float(b.difficulty),
                    "network_difficulty": float(b.network_difficulty) if b.network_difficulty else None,
                    "block_height": b.block_height,
                    "timestamp": b.timestamp.isoformat()
                }
                for b in all_blocks
            ]
            
            # Top high diff shares (last 7 days)
            cutoff_7d = now - timedelta(days=7)
            result = await db.execute(
                select(HighDiffShare)
                .where(HighDiffShare.timestamp >= cutoff_7d)
                .order_by(desc(HighDiffShare.difficulty))
                .limit(20)
            )
            high_shares = result.scalars().all()
            context["top_high_diff_shares"] = [
                {
                    "miner": s.miner_name,
                    "coin": s.coin,
                    "difficulty": float(s.difficulty),
                    "network_difficulty": float(s.network_difficulty) if s.network_difficulty else None,
                    "percentage": (float(s.difficulty) / float(s.network_difficulty) * 100) if s.network_difficulty else None,
                    "timestamp": s.timestamp.isoformat()
                }
                for s in high_shares
            ]
            
            # === AUTOMATION & OPTIMIZATION ===
            # Active automation rules
            result = await db.execute(
                select(AutomationRule).where(AutomationRule.enabled == True)
            )
            active_rules = result.scalars().all()
            context["active_automation_rules"] = [
                {
                    "name": r.name,
                    "trigger_type": r.trigger_type,
                    "action_type": r.action_type,
                    "last_triggered": r.last_triggered.isoformat() if r.last_triggered else None
                }
                for r in active_rules
            ]
            
            # Energy optimization state (from app_config instead of database)
            energy_config = app_config.get("energy_optimization", {})
            if energy_config:
                context["energy_optimization"] = {
                    "auto_optimization_enabled": energy_config.get("auto_optimization_enabled", False),
                    "price_threshold": energy_config.get("price_threshold_pence")
                }
            
            # Agile Solo Strategy
            from core.agile_solo_strategy import AgileSoloStrategy
            enrolled_miners = await AgileSoloStrategy.get_enrolled_miners(db)
            if enrolled_miners:
                context["agile_solo_strategy"] = {
                    "enrolled_miners": [m.name for m in enrolled_miners],
                    "description": "Automatically switches between Solo/Braiins based on electricity prices"
                }
            
            # === DEVICE HEALTH ===
            result = await db.execute(
                select(HealthScore, Miner.name)
                .join(Miner, HealthScore.miner_id == Miner.id)
                .where(HealthScore.timestamp >= cutoff_24h)
                .order_by(desc(HealthScore.timestamp))
            )
            health_records = result.all()
            health_summary = {}
            for h, miner_name in health_records:
                if miner_name not in health_summary:
                    health_summary[miner_name] = {
                        "overall_score": h.overall_score,
                        "uptime_score": h.uptime_score,
                        "temperature_score": h.temperature_score,
                        "hashrate_score": h.hashrate_score,
                        "reject_rate_score": h.reject_rate_score,
                        "timestamp": h.timestamp.isoformat()
                    }
            context["miner_health_scores"] = health_summary
            
            # === RECENT SYSTEM EVENTS (NO SENSITIVE AUDIT LOGS) ===
            result = await db.execute(
                select(AuditLog)
                .where(AuditLog.timestamp >= cutoff_24h)
                .where(AuditLog.action.not_in(['api_key_saved', 'password_changed']))  # Exclude sensitive actions
                .order_by(desc(AuditLog.timestamp))
                .limit(50)
            )
            recent_events = result.scalars().all()
            context["recent_system_events"] = [
                {
                    "action": e.action,
                    "user": e.user,
                    "resource_type": e.resource_type,
                    "resource_name": e.resource_name,
                    "status": e.status,
                    "timestamp": e.timestamp.isoformat()
                }
                for e in recent_events
            ]
            
            return context
