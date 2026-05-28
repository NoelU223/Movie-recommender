import os
import json
import logging
from kafka import KafkaProducer
from kafka.errors import NoBrokersAvailable

logger = logging.getLogger(__name__)

KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "kafka:29092")
TOPIC = "movie_events"

_producer = None


def get_producer() -> KafkaProducer | None:
    """Lazy init – producer se kreira tek pri prvom slanju.
    Vraća None ako Kafka nije dostupna (npr. tijekom razvoja)."""
    global _producer
    if _producer is None:
        try:
            _producer = KafkaProducer(
                bootstrap_servers=KAFKA_BOOTSTRAP,
                value_serializer=lambda v: json.dumps(v).encode("utf-8"),
                acks=1,
                retries=3,
                request_timeout_ms=5000,
            )
            logger.info("Kafka producer spreman.")
        except NoBrokersAvailable:
            logger.warning("Kafka nije dostupna, eventi se preskaču.")
            return None
    return _producer


def send_event(event: dict) -> None:
    """Šalje event u Kafka topic. Tihi failover – ako Kafka ne radi,
    aplikacija nastavlja bez prekida."""
    producer = get_producer()
    if producer is None:
        return
    try:
        producer.send(TOPIC, value=event)
    except Exception as e:
        logger.warning(f"Slanje eventa nije uspjelo: {e}")