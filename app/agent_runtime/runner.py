"""Agent runtime entry point -- compiles graph and processes events.

This module is the main loop for the agent-runtime Railway service.
It consumes events from Redis Stream and runs them through the LangGraph.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from typing import Any

from app.agent_runtime.cost_guard import BudgetStatus, check_budget
from app.agent_runtime.graph import build_graph
from app.agent_runtime.redis_store import AgentRuntimeRedis
from app.agent_runtime.state import WarmPathState
from app.agent_runtime.trust import TrustLevel

logger = logging.getLogger(__name__)

_compiled_graph = None


def _get_compiled_graph():
    """Lazy-compile the graph (Phase 1: in-memory, no checkpointer).

    Redis checkpointing will be added in Phase 2 when long-running
    workflows with human-in-the-loop require durable state.
    """
    global _compiled_graph
    if _compiled_graph is not None:
        return _compiled_graph

    graph_builder = build_graph()
    _compiled_graph = graph_builder.compile()
    return _compiled_graph


async def _get_budget_status() -> BudgetStatus:
    """Check daily budget against configured limit."""
    from app.config import settings

    try:
        store = AgentRuntimeRedis(redis_url=settings.REDIS_URL)
        daily_spend = await store.get_daily_spend()
        return check_budget(daily_spend, settings.AGENT_RUNTIME_BUDGET_DAILY_USD)
    except Exception:
        logger.debug("Budget check failed, assuming OK", exc_info=True)
        return BudgetStatus.OK


async def process_event(event: dict[str, Any]) -> dict[str, Any]:
    """Run a single event through the CoS supervisor graph.

    Returns the final graph state with findings, actions, and handoff results.
    Skips processing if the daily budget is exceeded.
    """
    budget_status = await _get_budget_status()

    if budget_status == BudgetStatus.EXCEEDED:
        logger.warning("Daily budget exceeded, skipping event %s", event.get("type"))
        return {"findings": [], "actions": [], "budget_exceeded": True}

    graph = _get_compiled_graph()

    initial_state: WarmPathState = {
        "event": event,
        "routed_teams": [],
        "priority": "",
        "trust_level": TrustLevel.RECOMMENDER,
        "findings": [],
        "actions": [],
        "needs_human": False,
        "human_decision": "",
        "handoffs": [],
    }

    # 6 nodes per loop iteration × 5 max loops; guards against infinite handoff cycles
    config = {
        "configurable": {
            "thread_id": event.get("dedup_key", "default"),
            "budget_status": budget_status.value,
            "trust_level": TrustLevel.RECOMMENDER,
        },
        "recursion_limit": 30,
    }
    result = await graph.ainvoke(initial_state, config=config)
    return result


async def run_consumer_loop() -> None:
    """Main event consumer loop (entry point for agent-runtime service).

    Reads events from Redis Stream 'warmpath:agent_events' and processes
    them through the LangGraph. Runs indefinitely.
    """
    import redis.asyncio as aioredis

    from app.config import settings

    if not settings.AGENT_RUNTIME_ENABLED:
        logger.info("Agent runtime disabled, exiting")
        return
    r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    stream_key = "warmpath:agent_events"

    # Create stream + consumer group if they don't exist
    with contextlib.suppress(Exception):
        await r.xgroup_create(stream_key, "agent-runtime", id="0", mkstream=True)

    logger.info("Agent runtime consumer started, listening on %s", stream_key)

    while True:
        try:
            messages = await r.xreadgroup(
                groupname="agent-runtime",
                consumername="worker-1",
                streams={stream_key: ">"},
                count=1,
                block=5000,
            )

            for _stream, entries in messages:
                for msg_id, data in entries:
                    event = json.loads(data.get("event", "{}"))
                    logger.info("Processing event: %s", event.get("type"))

                    dedup_key = event.get("dedup_key", "")
                    if dedup_key:
                        store = AgentRuntimeRedis(redis_url=settings.REDIS_URL)
                        if await store.is_duplicate(
                            dedup_key,
                            settings.AGENT_RUNTIME_EVENT_COOLDOWN_SECONDS,
                        ):
                            logger.info("Duplicate event %s, skipping", dedup_key)
                            await r.xack(stream_key, "agent-runtime", msg_id)
                            continue

                    try:
                        result = await process_event(event)
                        logger.info(
                            "Event processed: %d findings, %d actions",
                            len(result.get("findings", [])),
                            len(result.get("actions", [])),
                        )
                    except Exception:
                        logger.exception("Failed to process event %s", msg_id)

                    await r.xack(stream_key, "agent-runtime", msg_id)

        except asyncio.CancelledError:
            logger.info("Agent runtime shutting down")
            break
        except Exception:
            logger.exception("Consumer loop error, retrying in 5s")
            await asyncio.sleep(5)

    await r.aclose()
