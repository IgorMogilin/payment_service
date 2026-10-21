import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from app.models.payment import Currency, PaymentStatus


class PaymentCreate(BaseModel):
    """Тело запроса `POST /api/v1/payments`."""

    amount: Decimal = Field(..., gt=0, description="Сумма > 0")
    currency: Currency = Field(..., description="Валюта: RUB / USD / EUR")
    description: str = Field(default="", max_length=1000)
    metadata_: dict[str, Any] = Field(
        default_factory=dict, alias="metadata", description="Произвольные метаданные"
    )
    webhook_url: HttpUrl = Field(..., description="URL для уведомления о результате")

    model_config = ConfigDict(populate_by_name=True)


class PaymentCreatedResponse(BaseModel):
    """Ответ `202 Accepted` на создание платежа."""

    payment_id: uuid.UUID
    status: PaymentStatus
    created_at: datetime


class PaymentResponse(BaseModel):
    """Ответ `200 OK` на получение платежа."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    amount: Decimal
    currency: str
    description: str
    metadata_: dict[str, Any] = Field(alias="metadata")
    status: PaymentStatus
    idempotency_key: str
    webhook_url: str
    created_at: datetime
    processed_at: datetime | None = None


class WebhookPayload(BaseModel):
    """Тело webhook-уведомления, отправляемого клиенту."""

    payment_id: uuid.UUID
    status: PaymentStatus
    amount: Decimal
    currency: str
    processed_at: datetime
