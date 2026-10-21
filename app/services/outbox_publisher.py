import asyncio
import json
import logging
from datetime import UTC, datetime

from faststream.rabbit import RabbitBroker
from sqlalchemy import select

from app.core.config import get_settings
from app.core.database import async_session_factory
from app.models.outbox import OutboxMessage

logger = logging.getLogger(__name__)
settings = get_settings()

PAYMENT_QUEUE = "payments.new"


async def publish_outbox_messages(broker: RabbitBroker) -> None:
    """Бесконечный цикл поллинга outbox и публикации в брокер."""
    logger.info("Outbox publisher started")

    while True:
        try:
            async with async_session_factory() as session:
                stmt = (
                    select(OutboxMessage)
                    .where(
                        OutboxMessage.published == False,  # noqa: E712
                        OutboxMessage.scheduled_at <= datetime.now(UTC),
                    )
                    .order_by(OutboxMessage.created_at)
                    .limit(10)
                )
                result = await session.execute(stmt)
                messages = result.scalars().all()

                for msg in messages:
                    try:
                        await broker.publish(
                            message=json.dumps(msg.payload),
                            queue=PAYMENT_QUEUE,
                        )
                        msg.published = True
                        msg.published_at = datetime.now(UTC)
                        logger.info(
                            "Published outbox %s → payment %s",
                            msg.id,
                            msg.aggregate_id,
                        )
                    except Exception:
                        msg.retry_count += 1
                        logger.exception(
                            "Outbox publish failed: %s (retry #%d)",
                            msg.id,
                            msg.retry_count,
                        )

                await session.commit()

        except Exception:
            logger.exception("Outbox poller error")

        await asyncio.sleep(settings.OUTBOX_POLL_INTERVAL)
