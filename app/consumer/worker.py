import asyncio
import json
import logging
import random
from datetime import UTC, datetime
from uuid import UUID

import httpx
from faststream.rabbit import RabbitExchange, RabbitQueue
from sqlalchemy import select

from app.core.config import get_settings
from app.core.database import async_session_factory
from app.models.payment import Payment, PaymentStatus
from app.schemas.payment import WebhookPayload

logger = logging.getLogger(__name__)
settings = get_settings()
payment_exchange = RabbitExchange("payments", auto_delete=False)
payment_queue = RabbitQueue(
    "payments.new",
    durable=True,
    arguments={
        "x-dead-letter-exchange": "payments.dlx",
        "x-dead-letter-routing-key": "payments.dead",
    },
)

dlx_exchange = RabbitExchange("payments.dlx", auto_delete=False)
dlq_queue = RabbitQueue("payments.dead", durable=True)


async def process_payment_message(body: bytes) -> None:
    """Основная логика: эмуляция → обновление БД → webhook."""
    data = json.loads(body)
    payment_id = UUID(data["payment_id"])
    logger.info("Processing payment %s", payment_id)
    delay = random.uniform(settings.PAYMENT_MIN_DELAY, settings.PAYMENT_MAX_DELAY)
    await asyncio.sleep(delay)
    success = random.random() < settings.PAYMENT_SUCCESS_RATE
    new_status = PaymentStatus.SUCCEEDED if success else PaymentStatus.FAILED
    async with async_session_factory() as session:
        stmt = select(Payment).where(Payment.id == payment_id)
        result = await session.execute(stmt)
        payment = result.scalar_one_or_none()
        if payment is None:
            logger.error("Payment %s not found, skipping", payment_id)
            return
        processed_at = datetime.now(UTC)
        payment.status = new_status
        payment.processed_at = processed_at
        await session.commit()
        logger.info("Payment %s → %s", payment_id, new_status.value)
        await _send_webhook_with_retry(payment, processed_at)


async def _send_webhook_with_retry(payment: Payment, processed_at: datetime) -> None:
    """
    Webhook с повторами.
    """
    payload = WebhookPayload(
        payment_id=payment.id,
        status=payment.status,
        amount=payment.amount,
        currency=payment.currency,
        processed_at=processed_at,
    )

    for attempt in range(1, settings.WEBHOOK_MAX_RETRIES + 1):
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    payment.webhook_url,
                    json=payload.model_dump(mode="json"),
                )
                resp.raise_for_status()

            logger.info("Webhook sent: payment %s (attempt %d)", payment.id, attempt)
            return

        except httpx.HTTPError:
            logger.warning(
                "Webhook attempt %d/%d failed for %s",
                attempt,
                settings.WEBHOOK_MAX_RETRIES,
                payment.id,
                exc_info=True,
            )
            if attempt < settings.WEBHOOK_MAX_RETRIES:
                wait = settings.WEBHOOK_RETRY_BASE_DELAY * 2 ** (attempt - 1)
                await asyncio.sleep(wait)

    logger.error(
        "Webhook permanently failed for payment %s (%d retries exhausted)",
        payment.id,
        settings.WEBHOOK_MAX_RETRIES,
    )
