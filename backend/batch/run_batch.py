from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime

from app.database import SessionLocal
from app.models import Rating, MovieStats

import csv
from minio import Minio
from io import StringIO, BytesIO


def run_batch():
    db: Session = SessionLocal()

    results = (
        db.query(
            Rating.movie_id,
            func.avg(Rating.rating).label("avg_rating"),
            func.count(Rating.movie_id).label("rating_count")
        )
        .group_by(Rating.movie_id)
        .all()
    )

    for row in results:
        stats = (
            db.query(MovieStats)
            .filter(MovieStats.movie_id == row.movie_id)
            .first()
        )

        if stats:
            stats.avg_rating = float(row.avg_rating)
            stats.rating_count = row.rating_count
            stats.last_updated = datetime.utcnow()
        else:
            stats = MovieStats(
                movie_id=row.movie_id,
                avg_rating=float(row.avg_rating),
                rating_count=row.rating_count,
                last_updated=datetime.utcnow()
            )
            db.add(stats)

    db.commit()
    db.close()

    print("Batch obrada završena.")
    export_ratings_dataset(db)

def export_ratings_dataset(db: Session):
    ratings = db.query(Rating).all()

    csv_buffer = StringIO()
    writer = csv.writer(csv_buffer)
    writer.writerow(["user_id", "movie_id", "rating"])

    for r in ratings:
        writer.writerow([r.user_id, r.movie_id, r.rating])

    data = csv_buffer.getvalue().encode("utf-8")
    data_stream = BytesIO(data)

    client = Minio(
        "minio:9000",
        access_key="minioadmin",
        secret_key="minioadmin",
        secure=False
    )

    bucket_name = "datasets"

    if not client.bucket_exists(bucket_name):
        client.make_bucket(bucket_name)

    client.put_object(
        bucket_name,
        "ratings_dataset.csv",
        data_stream,
        length=len(data),
        content_type="text/csv"
    )


if __name__ == "__main__":
    run_batch()
