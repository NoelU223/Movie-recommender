# backend/app/tmdb/importer.py
import os
import time 
import requests
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import Movie

TMDB_TOKEN = os.getenv("TMDB_TOKEN")
BASE_URL = "https://api.themoviedb.org/3"

HEADERS = {
    "Authorization": f"Bearer {TMDB_TOKEN}",
    "accept": "application/json",
}


def fetch_genres() -> dict[int, str]:
    r = requests.get(f"{BASE_URL}/genre/movie/list", headers=HEADERS)
    r.raise_for_status()
    return {g["id"]: g["name"] for g in r.json()["genres"]}


def fetch_popular_page(page: int) -> list[dict]:
    r = requests.get(
        f"{BASE_URL}/movie/popular",
        headers=HEADERS,
        params={"page": page, "language": "en-US"},
    )
    r.raise_for_status()
    return r.json()["results"]


def upsert_movie(db: Session, m: dict, genre_map: dict[int, str]) -> bool:
    existing = db.query(Movie).filter_by(tmdb_id=m["id"]).first()

    genre_name = "Unknown"
    if m.get("genre_ids"):
        genre_name = genre_map.get(m["genre_ids"][0], "Unknown")

    year = 2000
    if m.get("release_date"):
        try:
            year = int(m["release_date"][:4])
        except ValueError:
            pass

    if existing:
        existing.popularity = m.get("popularity", 0.0)
        existing.vote_average = m.get("vote_average", 0.0)
        existing.vote_count = m.get("vote_count", 0)
        return False

    movie = Movie(
        tmdb_id=m["id"],
        title=m["title"],
        genre=genre_name,
        year=year,
        overview=m.get("overview"),
        poster_path=m.get("poster_path"),
        popularity=m.get("popularity", 0.0),
        vote_average=m.get("vote_average", 0.0),
        vote_count=m.get("vote_count", 0),
        original_language=m.get("original_language"),
    )
    db.add(movie)
    return True


def run_import(pages: int = 5) -> None:
    if not TMDB_TOKEN:
        print("⚠ TMDB_TOKEN nije postavljen, preskačem uvoz.")
        return

    db: Session = SessionLocal()
    try:
        print("→ Dohvaćam mapu žanrova...")
        genre_map = fetch_genres()

        new_count = 0
        for page in range(1, pages + 1):
            print(f"→ Stranica {page}/{pages}")
            movies = fetch_popular_page(page)
            for m in movies:
                if upsert_movie(db, m, genre_map):
                    new_count += 1
            db.commit()
            time.sleep(0.3)

        print(f"✓ Uvoz završen. Novih filmova: {new_count}")

        try:
            import redis
            redis_client = redis.from_url(
                os.getenv("REDIS_URL", "redis://redis:6379/0")
            )
            redis_client.delete("movies_list")
            print("→ Redis cache 'movies_list' obrisan.")
        except Exception as e:
            print(f"⚠ Cache invalidacija nije uspjela: {e}")
    finally:
        db.close()


def run_loop(pages: int = 10, interval_hours: int = 24) -> None:
    while True:
        try:
            print(f"=== Pokrećem TMDB sinkronizaciju ===")
            run_import(pages=pages)
        except Exception as e:
            print(f"⚠ Greška tijekom sinkronizacije: {e}")

        print(f"→ Sljedeća sinkronizacija za {interval_hours}h. Spavam...")
        time.sleep(interval_hours * 3600)


if __name__ == "__main__":
    run_loop(pages=10, interval_hours=24)