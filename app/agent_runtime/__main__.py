"""Entry point for: python3 -m app.agent_runtime.runner"""

import asyncio
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)

from app.agent_runtime.runner import run_consumer_loop  # noqa: E402

asyncio.run(run_consumer_loop())
