import asyncio
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from faststream.rabbit import RabbitBroker

from app.api.routes.payments import router as payments_router
from app.core.config import get_settings
from app.services.outbox_publisher import publish_outbox_messages

settings = get_settings()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Старт/остановка фоновых задач: RabbitMQ + outbox poller."""
    broker = RabbitBroker(settings.RABBITMQ_URL)
    await broker.start()
    logger.info("Connected to RabbitMQ")

    poller = asyncio.create_task(publish_outbox_messages(broker))

    yield

    poller.cancel()
    await broker.stop()
    logger.info("Shutdown complete")


app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    lifespan=lifespan,
)
app.include_router(payments_router)


@app.get("/health", tags=["System"])
async def health_check() -> dict[str, str]:
    return {"status": "ok"}
