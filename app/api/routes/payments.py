import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import verify_api_key
from app.core.database import get_db
from app.schemas.payment import (
    PaymentCreate,
    PaymentCreatedResponse,
    PaymentResponse,
)
from app.services import payment_service

router = APIRouter(prefix="/api/v1/payments", tags=["Payments"])


@router.post(
    "",
    response_model=PaymentCreatedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Создать платёж",
)
async def create_payment(
    data: PaymentCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    idempotency_key: Annotated[
        str,
        Header(alias="Idempotency-Key", min_length=1, max_length=255),
    ],
    _api_key: Annotated[str, Depends(verify_api_key)] = "",
) -> PaymentCreatedResponse:
    """
    Принимает платёж в обработку (202 Accepted).
    """
    payment, _ = await payment_service.create_payment(
        db=db, data=data, idempotency_key=idempotency_key
    )
    return PaymentCreatedResponse(
        payment_id=payment.id,
        status=payment.status,
        created_at=payment.created_at,
    )


@router.get(
    "/{payment_id}",
    response_model=PaymentResponse,
    summary="Получить информацию о платеже",
)
async def get_payment(
    payment_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    _api_key: Annotated[str, Depends(verify_api_key)] = "",
) -> PaymentResponse:
    """Возвращает детальную информацию о платеже."""
    payment = await payment_service.get_payment_by_id(db, payment_id)
    if payment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Payment {payment_id} not found",
        )
    return PaymentResponse.model_validate(payment)
