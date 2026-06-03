"""
Generira sintetičke korisnike, ocjene, watchlist i favorite zapise.
Modelira realno ponašanje:
- Svaki korisnik ima 1-3 omiljena žanra (daje im više ocjene)
- Neki korisnici su strogi (prosjek 5), neki popustljivi (prosjek 8)
- TMDB ocjena utječe – popularniji filmovi dobivaju malo bolje ocjene
- Korisnici dodaju u Watchlist filmove koje još nisu ocijenili
- Favoriti su filmovi koje su ocijenili 8+
"""
import os
import random
from datetime import datetime, timedelta
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import User, Movie, Rating, Watchlist, Favorite
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

NUM_USERS = 50
RATINGS_PER_USER_RANGE = (15, 40)
WATCHLIST_PER_USER_RANGE = (3, 10)


def hash_password(p: str) -> str:
    return pwd_context.hash(p[:72])


def generate_users(db: Session, all_genres: list[str]) -> list[dict]:
    """Stvara sintetičke korisnike s 'profilom' (omiljeni žanrovi + strogost)."""
    profiles = []
    for i in range(1, NUM_USERS + 1):
        email = f"synth_user{i}@test.com"

        existing = db.query(User).filter_by(email=email).first()
        if existing:
            user_id = existing.id
        else:
            user = User(email=email, password_hash=hash_password("password123"))
            db.add(user)
            db.flush()
            user_id = user.id

        fav_genres = random.sample(all_genres, k=random.randint(1, min(3, len(all_genres))))
        bias = random.gauss(0, 1.2)
        bias = max(-2.0, min(2.0, bias))

        profiles.append({"user_id": user_id, "fav_genres": fav_genres, "bias": bias})

    db.commit()
    return profiles


def simulate_rating(movie: Movie, profile: dict) -> int:
    """Pokušava simulirati realnu ocjenu na temelju profila i filma."""
    base = 6.0  # baza

    if movie.genre in profile["fav_genres"]:
        base += random.uniform(1.0, 2.0)
    else:
        base += random.uniform(-1.0, 0.5)

    if movie.vote_average:
        tmdb_factor = (movie.vote_average - 6.5) * 0.4
        base += tmdb_factor

    base += profile["bias"]

    base += random.gauss(0, 0.8)

    return max(1, min(10, round(base)))


def generate_ratings_and_lists(db: Session, profiles: list[dict], movies: list[Movie]) -> None:
    total_ratings = 0
    total_watchlist = 0
    total_favorites = 0

    for profile in profiles:
        user_id = profile["user_id"]

        num_ratings = random.randint(*RATINGS_PER_USER_RANGE)
        rated_movies = random.sample(movies, k=min(num_ratings, len(movies)))

        rated_movie_ids = set()
        for movie in rated_movies:
            existing = db.query(Rating).filter_by(user_id=user_id, movie_id=movie.id).first()
            if existing:
                continue
            rating_val = simulate_rating(movie, profile)
            db.add(Rating(user_id=user_id, movie_id=movie.id, rating=rating_val))
            rated_movie_ids.add(movie.id)
            total_ratings += 1

            if rating_val >= 8 and random.random() < 0.6:
                fav_exists = db.query(Favorite).filter_by(user_id=user_id, movie_id=movie.id).first()
                if not fav_exists:
                    db.add(Favorite(
                        user_id=user_id, movie_id=movie.id,
                        added_at=datetime.utcnow() - timedelta(days=random.randint(0, 30))
                    ))
                    total_favorites += 1

        unrated = [m for m in movies if m.id not in rated_movie_ids]
        num_watchlist = random.randint(*WATCHLIST_PER_USER_RANGE)
        for movie in random.sample(unrated, k=min(num_watchlist, len(unrated))):
            wl_exists = db.query(Watchlist).filter_by(user_id=user_id, movie_id=movie.id).first()
            if not wl_exists:
                db.add(Watchlist(
                    user_id=user_id, movie_id=movie.id,
                    added_at=datetime.utcnow() - timedelta(days=random.randint(0, 30))
                ))
                total_watchlist += 1

        db.commit()

    print(f"✓ Generirano: {total_ratings} ocjena, {total_watchlist} watchlist, {total_favorites} favoriti.")


def run():
    db = SessionLocal()
    try:
        movies = db.query(Movie).all()
        if len(movies) < 50:
            print(f"⚠ Premalo filmova u bazi ({len(movies)}). Pokreni TMDB importer prvo.")
            return

        all_genres = list(set(m.genre for m in movies if m.genre))
        print(f"→ {len(movies)} filmova, {len(all_genres)} žanrova.")

        print(f"→ Generiram {NUM_USERS} sintetičkih korisnika...")
        profiles = generate_users(db, all_genres)

        print("→ Generiram ocjene, watchlist i favorite...")
        generate_ratings_and_lists(db, profiles, movies)

        print("✓ Gotovo.")
    finally:
        db.close()


if __name__ == "__main__":
    run()