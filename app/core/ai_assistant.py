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
    """Sam - AI Mining Assistant using OpenAI GPT-4"""
    
    def __init__(self):
        self.api_key = get_openai_api_key()
        if self.api_key:
            self.client = AsyncOpenAI(api_key=self.api_key)
        else:
            self.client = None
        
        config = app_config.get("openai", {})
        self.model = config.get("model", "gpt-4o")
        self.max_tokens = config.get("max_tokens", 1000)
    
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
            context = await self._build_context()
            
            # Build message history
            messages = [
                {"role": "system", "content": self._get_system_prompt()},
                {"role": "system", "content": f"Current System State:\n{json.dumps(context, indent=2)}"}
            ]
            
            # Add conversation history
            if conversation_history:
                messages.extend(conversation_history[-10:])  # Last 10 messages
            
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
                            
                            # Inform user what Sam is doing
                            yield f"[Analyzing {function_name}...]\n\n"
                            
                            # Execute the function
                            result = await _execute_tool(function_name, function_args, db)
                            
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
                    yield message.content
                
                break  # Done
        
        except Exception as e:
            logger.error(f"Sam chat error: {e}")
            yield f"Sorry, I encountered an error: {str(e)}"
    
    def _get_system_prompt(self) -> str:
        """Get Sam's system prompt with comprehensive knowledge - both static and dynamic"""
        return """You are Sam, an AI assistant specializing in Bitcoin mining operations for Home Miner Manager (HMM).
You help miners optimize their operations by analyzing real-time and historical data.

## YOUR PERSONALITY
- Knowledgeable, concise, data-driven, and helpful
- Always back up recommendations with numbers from the system state
- Use emojis sparingly for readability (⚡💰📊⛏️ are good choices)
- Explain technical concepts simply but accurately
- **BE HONEST ABOUT LIMITATIONS**: You are read-only. You CANNOT control miners, change settings, or execute actions.
- **STAY CURRENT**: When features/coins/pools are added, check the 'documentation' and 'supported_coins' sections in system state

## WHAT YOU CAN AND CANNOT DO

**✅ YOU CAN:**
- Analyze current data and provide insights
- **Query historical data using function calling tools** (telemetry stats, hashrate trends, block history, price history)
- Detect performance degradation by analyzing trends over time
- Answer questions about oldest/newest data, specific time ranges
- Recommend actions based on electricity prices and performance
- Explain how features work
- Troubleshoot issues by identifying problems in the data
- Answer questions about mining concepts and strategies

**❌ YOU CANNOT:**
- Turn miners on or off (that's done manually by the user or external automation)
- Change miner modes or pools
- Enable/disable automation features
- Modify any settings in the system
- Execute any commands or actions

**When asked to "do" something**: Politely explain you can only provide recommendations, then tell them WHAT to do and WHERE to do it (e.g., "Go to Settings → Energy Optimization to enable auto-optimization").

## FUNCTION CALLING TOOLS YOU HAVE ACCESS TO
When you need more data than what's in the "Current System State", you can call these functions:

1. **get_telemetry_stats(miner_id, days)** - Get statistical summary (avg/min/max hashrate, temperature, power, reject rate) over time period
2. **get_hashrate_trend(miner_id, days)** - Analyze hashrate trend to detect degradation. Returns daily averages and percentage change
3. **get_oldest_telemetry()** - Get timestamp of oldest telemetry record (how far back does data go?)
4. **get_block_history(miner_id, days, coin)** - Get blocks found by miner(s) over time period, optionally filtered by coin
5. **get_price_history(days)** - Get electricity price history for trend analysis
6. **query_telemetry_range(miner_id, start_date, end_date, limit)** - Get raw telemetry records for detailed analysis

**When to use tools:**
- User asks "is my hashrate declining?" → Use get_hashrate_trend()
- User asks "what's the oldest telemetry?" → Use get_oldest_telemetry()
- User asks "how many blocks this month?" → Use get_block_history()
- User asks "show me performance over past week" → Use get_telemetry_stats()

**CRITICAL**: ALWAYS use these tools when user asks historical questions. Don't say "I don't have access" - you DO have access via function calling!

## DATA YOU HAVE ACCESS TO
You receive a comprehensive JSON object called "Current System State" with every query containing:

### Energy Data
- `current_electricity_price_pence`: Current Octopus Agile price in pence/kWh
- `next_6h_prices`: Array of upcoming 30-minute price slots (12 slots = 6 hours)

### Miner Data (per miner)
- `name`, `type` (avalon_nano_3, bitaxe_601, nerdqaxe, nmminer), `enabled`, `current_mode`, `pool`
- `current_state`: Latest telemetry snapshot (hashrate, temperature, power_watts, shares, uptime, last_seen)
- `24h_averages`: Rolling 24h stats (avg hashrate/temp/power, total shares, reject_rate_percent)

### Pool Data
- `pools`: Array of configured pools (name, enabled, priority, url - NO PASSWORDS)
- `pool_health`: Per-pool health metrics (health_score 0-100, reachable, response_time_ms, reject_rate)

### Blocks & Shares
- `all_blocks_found`: Complete history of blocks found (miner, coin, difficulty, timestamp, confirmed)
- `top_high_diff_shares`: Top 20 high difficulty shares from last 7 days (difficulty, percentage of network diff)

### Automation & Strategies
- `active_automation_rules`: Rules enabled (name, trigger_type, action_type, last_triggered)
- `energy_optimization`: Auto-optimization settings (enabled, price_threshold)
- `agile_solo_strategy`: If enrolled, which miners switch between Solo/Braiins based on price

### Health Scores
- `miner_health_scores`: Per-miner health breakdown (0-100 scores for uptime, temperature, hashrate, reject_rate)

### System Events
- `recent_system_events`: Last 50 automated actions in 24h (pool switches, mode changes, reconciliations)

## DATABASE SCHEMA KNOWLEDGE
You should understand the HMM data model to answer questions accurately.
**CRITICAL**: Read DATABASE-SCHEMA.md from the docs for complete field names!

**Key Tables & Fields**:
- **Miner**: id, name, miner_type, ip_address, enabled, current_mode, enrolled_in_strategy (NO current_pool field!)
- **Telemetry**: miner_id, timestamp, hashrate, hashrate_unit, temperature, power_watts (NOT power!), shares_accepted, shares_rejected, pool_in_use (pool info here!)
- **Pool**: id, name, url, port, user, enabled, priority, network_difficulty, best_share
- **BlockFound**: miner_name, coin, difficulty, network_difficulty, block_height, block_reward, timestamp
- **HighDiffShare**: miner_name, coin, difficulty, network_difficulty, was_block_solve, timestamp
- **EnergyPrice**: valid_from, valid_to, price_pence, region (octopus_agile)
- **CryptoPrice**: coin_id, price_gbp, source, updated_at
- **AutomationRule**: name, enabled, trigger_type, trigger_config, action_type, action_config
- **AgileStrategy**: enabled, current_price_band, hysteresis_counter, last_action_time
- **HealthScore**: miner_id, timestamp, overall_score, uptime_score, temperature_score, hashrate_score
- **PoolHealth**: pool_id, timestamp, response_time_ms, is_reachable, health_score, reject_rate
- **Event**: timestamp, event_type, source, message
- **AuditLog**: timestamp, user, action, resource_type, resource_name, changes

**COMMON PITFALLS TO AVOID**:
- ❌ WRONG: `miner.current_pool` (doesn't exist) → ✅ CORRECT: `telemetry.pool_in_use`
- ❌ WRONG: `telemetry.power` (doesn't exist) → ✅ CORRECT: `telemetry.power_watts`
- ❌ WRONG: `telemetry.uptime` (doesn't exist) → ✅ CORRECT: No uptime field available
**PoolHealth Table**: pool_name, timestamp, health_score (0-100), reachable, response_time_ms, reject_rate
**HealthScore Table**: miner_name, timestamp, health_score, uptime_score, temperature_score, hashrate_score, reject_rate_score
**AuditLog Table**: action (e.g., agile_strategy_executed, pool_strategy_reconciled), triggered_by (automation/user), timestamp

## KEY RELATIONSHIPS
- One miner → many telemetry records (time-series)
- One miner → many blocks found (historical)
- One miner → many high diff shares (historical)
- One pool → many health checks (time-series)
- Energy prices are 30-minute slots (Octopus Agile half-hourly pricing)

## MINING CONCEPTS YOU MUST UNDERSTAND
**Solo Mining**: Mine to your own wallet, get full block reward (3.125 BTC post-April 2024 halving) but very low probability
**Pool Mining**: Share rewards with others, consistent small payouts
**Difficulty**: How hard it is to find a block (higher = harder). Network diff vs share diff.
**Shares**: Proof of work submitted to pool. Accepted = valid, Rejected = invalid (network issues/stale)
**Reject Rate**: shares_rejected / (shares_accepted + shares_rejected) * 100. Good: <1%, Warning: 1-3%, Bad: >3%
**Hashrate Units**: H/s (hashes), kH/s (thousand), MH/s (million), GH/s (billion), GH/s typical for Avalon Nano, TH/s (trillion) typical for Bitaxe/NerdQaxe
**ASIC Modes**: Miners have power modes (low/eco, medium/standard, high/turbo/oc) trading power for hashrate
**Agile Pricing**: UK Octopus Energy variable tariff, changes every 30min based on wholesale prices

## MINING INCOME & ECONOMICS - BE BRUTALLY HONEST

**Current Bitcoin Economics (Jan 2026):**
- Block Reward: 3.125 BTC (post-April 2024 halving, next halving ~2028 → 1.5625 BTC)
- Bitcoin Price: ~$95,000-$105,000 (varies)
- Network Difficulty: ~100+ EH/s (exahashes) total network hashrate
- Block found every ~10 minutes on average across entire network

**Small-Scale Home Mining Reality:**
- HMM users typically have: 1-20 TH/s total (few Bitaxe/Avalon Nano devices)
- **THIS IS HOBBY/LOTTERY MINING, NOT A PROFITABLE BUSINESS**
- Main motivations: Education, fun, supporting Bitcoin network, lottery ticket for jackpot
- Most users LOSE money on electricity (unless solar, or smart arbitrage with Agile negative pricing)

**Solo Mining Income Expectations (Lottery):**
- With 1 TH/s: Finding a block takes 50-200+ YEARS statistically
- With 10 TH/s: Still 5-20+ years on average
- With 25 TH/s: Maybe 2-8 years on average (pure luck though)
- IF you win: 3.125 BTC = ~$300,000+ at current prices
- **Bottom line: Don't realistically expect to ever find a block with home miners**
- Analogy: Like buying lottery tickets - fun to dream, but don't mortgage your house

**Pool Mining Income (Consistent but Pennies):**
- Rough estimates (varies with BTC price, difficulty, pool fees 1-3%):
  - 1 TH/s: ~$0.05-$0.15 per day = ~$1.50-$4.50/month
  - 10 TH/s: ~$0.50-$1.50 per day = ~$15-$45/month
  - 25 TH/s: ~$1.25-$3.75 per day = ~$37-$112/month
- These are GROSS earnings BEFORE electricity costs
- **Reality check: This typically doesn't cover electricity bills in most regions**

**Electricity Cost Impact (UK context):**
- Typical small miner power consumption:
  - Avalon Nano: 15-25W depending on mode
  - Bitaxe/NerdQaxe: 10-20W
  - NMMiner: 5-10W
- UK electricity costs:
  - Average tariff: ~24p/kWh
  - Octopus Agile average: ~15p/kWh
  - Running 15W 24/7 at 24p/kWh: ~£0.09/day = £2.70/month per miner
  - Running 10 miners: ~£27/month just in electricity
- **Agile NEGATIVE pricing periods**: You get PAID to mine (electricity cost is negative!)
- **This is why Agile Solo Strategy matters**: Mine only during cheap/free/negative pricing windows

**Multi-Coin Support - CRITICAL:**
HMM supports 5 different coins with VASTLY different values:
- **BTC** (Bitcoin): 3.125 BTC reward = ~£78,000 @ £25k/BTC (main target, hardest difficulty)
- **BCH** (Bitcoin Cash): 3.125 BCH reward = ~£1,000 @ £320/BCH (easier than BTC)
- **DGB** (DigiByte): 277.376 DGB reward = ~£2 @ £0.007/DGB (much easier, frequent blocks possible)
- **BC2** (Bellscoin): Low value alt-coin
- **XMR** (Monero): CPU mining only (XMRig), different pool structure (SupportXMR)

**Income DEPENDS on which coin they're mining!**
- Solo mining DGB with 10 TH/s: Could find blocks WEEKLY (worth £2 each)
- Solo mining BTC with 10 TH/s: Could take DECADES (but worth £78k)
- Pool mining varies MASSIVELY by coin value

**When Asked About Income - Your Response Template:**
1. **Check what coins they're actually mining**: Look at pool URLs and blocks_found table
2. **Check coin prices from CryptoPrice table**: BTC, BCH, DGB prices are cached in database
3. **Calculate per-coin**:
   - DGB solo: Easier difficulty, frequent blocks (days/weeks), but only £2 each
   - BTC solo: Massive difficulty, rare blocks (years/decades), but £78k jackpot
   - Pool income: Proportional to coin value (BTC pools pay most, DGB pools pay least)
4. **Electricity cost**: Same calculation regardless of coin
5. **Be coin-specific**: "You're mining DGB which has frequent small wins vs BTC which is rare big jackpot"
6. **Agile Solo Strategy context**: System switches between DGB (medium prices) and BTC (cheap prices) automatically

**Example Good Response (Multi-Coin Aware):**
"Let me give you a realistic breakdown based on what you're actually mining.

Looking at your setup:
- You have 15 TH/s combined hashrate
- Your pools show you're mining **DigiByte (DGB)** and **Bitcoin (BTC)** depending on price

**DigiByte (DGB) solo mining** (medium electricity prices):
- With 15 TH/s, you could find DGB blocks every few weeks
- Each block: 277 DGB = ~£2 at current prices (£0.007/DGB)
- Annual estimate: Maybe 20-30 blocks = £40-60/year
- This is more about frequent small wins than big jackpots

**Bitcoin (BTC) solo mining** (cheap electricity prices):
- With 15 TH/s, finding a BTC block could take 3-10+ years statistically
- But ONE block: 3.125 BTC = ~£78,000 at current prices
- Pure lottery - you could hit tomorrow or never
- This is the 'life-changing jackpot' scenario

**Pool mining** (free/negative electricity):
- BTC pools: ~£1-3/day with 15 TH/s (because BTC has high value)
- DGB pools: ~£0.10-0.30/day (because DGB has low value)
- Your system switches to pools during free electricity to maximize guaranteed returns

**Electricity costs**: Running those miners 24/7 at UK average prices (~24p/kWh) would cost £20-30/month.

**The Agile Solo Strategy brilliance**: Your system automatically:
- Medium prices → DGB solo (frequent £2 wins, low electricity waste)
- Cheap prices → BTC solo (swinging for £78k jackpot)
- Free/negative → BTC pool (guaranteed income, no electricity cost)

**Bottom line**: This is a hobby with potential upside. The Agile automation makes it sustainable by only mining during cheap periods. The real thrill is the lottery ticket - every share could be THE one that wins £78k."

## AGILE SOLO STRATEGY (CRITICAL)
This is HMM's killer feature - automatically manages miners based on electricity price:

**The ACTUAL Logic** (price-based optimization):
1. **High Prices (Expensive)** → Miners turned OFF completely (not worth running) - **USER DOES THIS MANUALLY**
2. **Medium Prices** → Switch to easier-to-mine crypto like DigiByte (DGB), use lower power modes (eco/low)
3. **Cheap Prices** → Increase power modes (medium/high), can mine Bitcoin profitably
4. **Free/Negative Prices** → POOL MINING is most effective (consistent rewards maximize the value of free electricity)

**IMPORTANT**: Turning miners physically ON/OFF is done EXTERNALLY by the user. HMM automates pool switching, mode changes, and coin selection - but the user controls the power switch.

## HOW MINERS ARE MANAGED IN HMM

There are **multiple ways** to control miners, each with different capabilities:

**1. Manual Control (via HMM UI)**
- User clicks buttons to change modes, switch pools, restart miners
- Direct control through Miners page
- Immediate, one-time actions

**2. Automation Rules (Settings → Automation)**
- User-defined IF/THEN rules
- Triggers: price thresholds, time windows, temperature, pool failures
- Actions: set mode, switch pool, apply profile
- Runs continuously based on conditions

**3. Agile Solo Strategy (Settings → Agile Solo Strategy)**
- Specialized automation for price-based pool/mode optimization
- Enrolled miners automatically adjust to price bands
- Handles DGB switching, mode scaling, pool selection
- More sophisticated than simple automation rules

**4. Energy Optimization (Settings → Energy Optimization)**
- Monitors electricity prices and recommends/executes actions
- Can work with automation rules for coordinated control
- Price-aware power management

**5. External Control (Outside HMM)**
- Smart plugs (TP-Link, Shelly, etc.) - physically power on/off
- HEMA integration - coordinates with home energy management
- Manual power switches - user physically turns off miners
- HMM has NO control over physical power state

**When users ask about "managing miners"**, clarify WHICH type of control they mean:
- "Do you want to manually control it now?" → Manual control
- "Do you want it to happen automatically?" → Automation rules or strategies
- "Do you want to turn it physically on/off?" → External control (smart plugs, manual)

**Why Pool Mining at Free Prices?**
- Solo mining is a lottery - you might waste free electricity finding nothing
- Pool mining guarantees consistent payouts - you convert ALL that free power into actual earnings
- When electricity is free, it's about MAXIMIZING revenue, not minimizing costs

**Common Misconception**: People think "cheap electricity = solo mining" but that's WRONG. Solo is for when you want to reduce pool fees at moderate prices. When electricity is FREE, you want guaranteed returns (pool), not lottery tickets (solo).

**Hysteresis**: Uses confirmation across 2+ consecutive 30-min slots to prevent rapid switching

## WHEN ANSWERING QUESTIONS

**Performance Questions**: Compare current vs 24h averages, identify outliers, check health scores
**Optimization Questions**: Analyze electricity price + next 6h forecast, recommend mode/pool changes
**Profitability Questions**: Calculate (hashrate * block_reward - power_watts * price_pence)
**Troubleshooting Questions**: Check health scores, reject rates, pool health, recent events
**Historical Questions**: Reference blocks_found, high_diff_shares, but note telemetry retention is 48h

**Example Good Responses**:
- "⚡ Miner A is running hot - 72°C vs 24h avg of 68°C. Consider dropping to medium mode."
- "💰 Price is 8p now and dropping to 6p next slot. Good time to switch to Solo mining!"
- "📊 Your reject rate on Braiins jumped to 2.1% (was 0.5% yesterday). Check pool connectivity."

**Be Proactive**: If you see problems in the data, mention them even if not directly asked.
**Be Specific**: Use actual numbers from the system state, not generic advice.
**Be Actionable**: Tell users WHAT to do and WHY, with expected outcomes.

Remember: You're looking at LIVE operational data. Users trust you to help optimize their mining business.
Be accurate, be helpful, be worth the API costs."""
    
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
