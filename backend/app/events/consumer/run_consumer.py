import os
import json
import csv
import logging
import time
from datetime import datetime, timezone
from io import StringIO, BytesIO

from kafka import KafkaConsumer
from kafka.errors import NoBrokersAvailable
from minio import Minio
from minio.error import S3Error

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "kafka:29092")
TOPIC = "movie_events"
BUCKET = "events"

MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "minio:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "minioadmin")

BATCH_SIZE = 50          
BATCH_TIMEOUT_SEC = 60   

CSV_COLUMNS = [
    "timestamp",
    "event_type",
    "user_id",
    "movie_id",
    "path",
    "method",
    "status_code",
]


def get_minio_client() -> Minio:
    """Spaja se na MinIO i osigurava da bucket postoji."""
    client = Minio(
        MINIO_ENDPOINT,
        access_key=MINIO_ACCESS_KEY,
        secret_key=MINIO_SECRET_KEY,
        secure=False,
    )
    if not client.bucket_exists(BUCKET):
        client.make_bucket(BUCKET)
        logger.info(f"MinIO bucket '{BUCKET}' kreiran.")
    return client


def flush_batch(batch: list[dict], minio_client: Minio) -> None:
    """Sprema batch evenata kao jedan CSV file u MinIO."""
    if not batch:
        return

    csv_buffer = StringIO()
    writer = csv.DictWriter(csv_buffer, fieldnames=CSV_COLUMNS, extrasaction="ignore")
    writer.writeheader()
    for event in batch:
        writer.writerow(event)

    data = csv_buffer.getvalue().encode("utf-8")
    data_stream = BytesIO(data)

    now = datetime.now(timezone.utc)
    filename = f"events_{now.strftime('%Y-%m-%dT%H-%M-%S-%f')}.csv"

    minio_client.put_object(
        BUCKET,
        filename,
        data_stream,
        length=len(data),
        content_type="text/csv",
    )
    logger.info(f"✓ Spremljeno {len(batch)} eventa → {filename}")


def connect_consumer() -> KafkaConsumer:
    """Spaja se na Kafku, retry pri startu (Kafka može trebati par sekundi)."""
    for attempt in range(10):
        try:
            consumer = KafkaConsumer(
                TOPIC,
                bootstrap_servers=KAFKA_BOOTSTRAP,
                value_deserializer=lambda v: json.loads(v.decode("utf-8")),
                auto_offset_reset="earliest",   
                enable_auto_commit=True,
                group_id="event-archiver",      
                consumer_timeout_ms=1000,       
            )
            logger.info("Kafka consumer spreman.")
            return consumer
        except NoBrokersAvailable:
            logger.warning(f"Kafka nije dostupna, retry {attempt+1}/10...")
            time.sleep(5)
    raise RuntimeError("Kafka nije dostupna nakon 10 pokušaja.")


def run() -> None:
    minio_client = get_minio_client()
    consumer = connect_consumer()

    batch: list[dict] = []
    last_flush = time.time()

    logger.info(f"Slušam topic '{TOPIC}'... (batch={BATCH_SIZE}, timeout={BATCH_TIMEOUT_SEC}s)")

    while True:
        records = consumer.poll(timeout_ms=1000)

        for tp, messages in records.items():
            for msg in messages:
                batch.append(msg.value)

        elapsed = time.time() - last_flush
        if len(batch) >= BATCH_SIZE or (batch and elapsed >= BATCH_TIMEOUT_SEC):
            try:
                flush_batch(batch, minio_client)
                batch.clear()
                last_flush = time.time()
            except S3Error as e:
                logger.error(f"MinIO greška: {e}, zadržavam batch.")


if __name__ == "__main__":
    run()