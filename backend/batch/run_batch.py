from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime

from app.database import SessionLocal
from app.models import Rating, MovieStats

import csv
import json
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
    recommendations = generate_recommendations(db)
    export_recommendations(recommendations)

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

def generate_recommendations(db: Session, top_n: int = 5):
    movies = (
        db.query(MovieStats)
        .order_by(MovieStats.avg_rating.desc(), MovieStats.rating_count.desc())
        .limit(top_n)
        .all()
    )

    recommendations = []

    for m in movies:
        recommendations.append({
            "movie_id": m.movie_id,
            "avg_rating": m.avg_rating,
            "rating_count": m.rating_count
        })

    return recommendations

def export_recommendations(recommendations: list):
    data = json.dumps(recommendations, indent=2).encode("utf-8")

    client = Minio(
        "minio:9000",
        access_key="minioadmin",
        secret_key="minioadmin",
        secure=False
    )

    bucket_name = "recommendations"

    if not client.bucket_exists(bucket_name):
        client.make_bucket(bucket_name)

    client.put_object(
        bucket_name,
        "top_movies.json",
        BytesIO(data),
        length=len(data),
        content_type="application/json"
    )


if __name__ == "__main__":
    run_batch()
