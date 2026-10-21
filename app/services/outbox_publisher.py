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
                        OutboxMessage.published.is_(False),
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
                        if msg.retry_count >= settings.MAX_PROCESSING_RETRIES:
                            msg.published = True
                            logger.error(
                                "Outbox message %s gave up after %d retries (payment %s)",
                                msg.id,
                                msg.retry_count,
                                msg.aggregate_id,
                            )
                        else:
                            logger.exception(
                                "Outbox publish failed: %s (retry #%d/%d)",
                                msg.id,
                                msg.retry_count,
                                settings.MAX_PROCESSING_RETRIES,
                            )

                await session.commit()

        except Exception:
            logger.exception("Outbox poller error")

        await asyncio.sleep(settings.OUTBOX_POLL_INTERVAL)
