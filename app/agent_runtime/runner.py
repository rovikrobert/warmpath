"""Agent runtime entry point -- compiles graph and processes events.

This module is the main loop for the agent-runtime Railway service.
It consumes events from Redis Stream and runs them through the LangGraph.
"""

from __futu[RESEND_KEY_REDACTED] import annotations

import asyncio
import contextlib
import json
import logging
from typing import Any

from app.agent_runtime.graph import build_graph
from app.agent_runtime.state import WarmPathState

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


async def process_event(event: dict[str, Any]) -> dict[str, Any]:
    """Run a single event through the CoS supervisor graph.

    Returns the final graph state with findings, actions, and handoff results.
    """
    graph = _get_compiled_graph()

    initial_state: WarmPathState = {
        "event": event,
        "routed_teams": [],
        "priority": "",
        "findings": [],
        "actions": [],
        "needs_human": False,
        "human_decision": "",
        "handoffs": [],
    }

    # 6 nodes per loop iteration × 5 max loops; guards against infinite handoff cycles
    config = {
        "configurable": {"thread_id": event.get("dedup_key", "default")},
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

    from app.config import Settings

    settings = Settings()
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
