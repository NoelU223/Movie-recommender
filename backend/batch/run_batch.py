from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime

from app.database import SessionLocal
from app.models import Rating, MovieStats


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


if __name__ == "__main__":
    run_batch()
