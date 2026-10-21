import logging

from faststream import FastStream
from faststream.rabbit import RabbitBroker

from app.consumer.worker import (
    dlq_queue,
    dlx_exchange,
    payment_exchange,
    payment_queue,
    process_payment_message,
)
from app.core.config import get_settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)
settings = get_settings()

broker = RabbitBroker(settings.RABBITMQ_URL)
app = FastStream(broker)


@broker.subscriber(
    payment_queue,
    exchange=payment_exchange,
)
async def on_payment_message(body: bytes) -> None:
    """Обработчик: если бросит исключение → сообщение в DLQ."""
    await process_payment_message(body)


@broker.subscriber(dlq_queue, exchange=dlx_exchange)
async def on_dead_letter(body: bytes) -> None:
    """Логируем сообщения, попавшие в DLQ."""
    logger.critical("DEAD LETTER: %s", body.decode())
