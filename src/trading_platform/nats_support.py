from __future__ import annotations

from nats.js.api import ConsumerConfig, RetentionPolicy, StorageType, StreamConfig
from nats.js.errors import NotFoundError


SIGNAL_STREAM = "SIGNALS"
DEAD_LETTER_STREAM = "SIGNALS_DLQ"
SIGNAL_SUBJECT = "signals.v2.>"
SIGNAL_SUBJECTS = [SIGNAL_SUBJECT]
DLQ_SUBJECTS = ["signals.dlq.>"]


async def ensure_streams(js) -> None:
    configs = (
        StreamConfig(
            name=SIGNAL_STREAM,
            subjects=SIGNAL_SUBJECTS,
            storage=StorageType.FILE,
            retention=RetentionPolicy.LIMITS,
            max_age=30 * 24 * 60 * 60,
            duplicate_window=24 * 60 * 60,
        ),
        StreamConfig(
            name=DEAD_LETTER_STREAM,
            subjects=DLQ_SUBJECTS,
            storage=StorageType.FILE,
            retention=RetentionPolicy.LIMITS,
            max_age=90 * 24 * 60 * 60,
        ),
    )
    for config in configs:
        try:
            await js.stream_info(config.name)
        except NotFoundError:
            await js.add_stream(config=config)


def bridge_consumer_config(durable_name: str, ack_wait_seconds: int, max_deliver: int) -> ConsumerConfig:
    return ConsumerConfig(
        durable_name=durable_name,
        ack_policy="explicit",
        ack_wait=ack_wait_seconds,
        max_deliver=max_deliver,
        filter_subject=SIGNAL_SUBJECT,
    )
