import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.outbox import OutboxMessage
from app.models.payment import Payment, PaymentStatus
from app.schemas.payment import PaymentCreate


async def create_payment(
    db: AsyncSession,
    data: PaymentCreate,
    idempotency_key: str,
) -> tuple[Payment, bool]:
    """
    Создаёт платёж и outbox-запись в транзакции.
    """
    stmt = select(Payment).where(Payment.idempotency_key == idempotency_key)
    result = await db.execute(stmt)
    existing = result.scalar_one_or_none()

    if existing is not None:
        return existing, False
    payment = Payment(
        id=uuid.uuid4(),
        amount=data.amount,
        currency=data.currency.value,
        description=data.description,
        metadata_=data.metadata_,
        status=PaymentStatus.PENDING,
        idempotency_key=idempotency_key,
        webhook_url=str(data.webhook_url),
    )
    db.add(payment)
    outbox = OutboxMessage(
        id=uuid.uuid4(),
        event_type="payment.created",
        aggregate_id=payment.id,
        payload={
            "payment_id": str(payment.id),
            "amount": str(payment.amount),
            "currency": payment.currency,
            "webhook_url": payment.webhook_url,
            "idempotency_key": payment.idempotency_key,
            "metadata": payment.metadata_,
        },
    )
    db.add(outbox)
    await db.commit()
    await db.refresh(payment)

    return payment, True


async def get_payment_by_id(
    db: AsyncSession,
    payment_id: uuid.UUID,
) -> Payment | None:
    """Возвращает платёж по ID или None."""
    stmt = select(Payment).where(Payment.id == payment_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()
