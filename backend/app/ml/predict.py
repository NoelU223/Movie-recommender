"""
Učitava trenirani model i daje predikcije za (user, movie) parove.
"""
import os
import json
import logging
from collections import defaultdict

import numpy as np
import joblib
from sqlalchemy.orm import Session

from app.models import Movie, Rating

logger = logging.getLogger(__name__)

MODEL_DIR = "/app/model"

_model = None
_scaler = None
_metadata = None


def _load_artifacts() -> bool:
    """Učita model, scaler i metadata. Vrati True ako su dostupni."""
    global _model, _scaler, _metadata
    if _model is not None:
        return True

    try:
        _model = joblib.load(f"{MODEL_DIR}/classifier.pkl")
        _scaler = joblib.load(f"{MODEL_DIR}/scaler.pkl")
        with open(f"{MODEL_DIR}/metadata.json") as f:
            _metadata = json.load(f)
        logger.info(f"ML model učitan: {_metadata['model_name']}")
        return True
    except FileNotFoundError:
        logger.warning("Model nije pronađen. Pokreni 'docker compose run --rm ml_trainer'.")
        return False


def is_model_available() -> bool:
    return _load_artifacts()


def build_features(user_id: int, movie: Movie, db: Session) -> np.ndarray | None:
    """Gradi feature vektor točno istim redom kao u treningu."""
    if not _load_artifacts():
        return None

    user_ratings = db.query(Rating).filter_by(user_id=user_id).all()
    user_rating_values = [r.rating for r in user_ratings]

    movie_lookup = {m.id: m for m in db.query(Movie).filter(
        Movie.id.in_([r.movie_id for r in user_ratings])
    ).all()}
    same_genre_ratings = [
        r.rating for r in user_ratings
        if movie_lookup.get(r.movie_id) and movie_lookup[r.movie_id].genre == movie.genre
    ]

    user_avg = float(np.mean(user_rating_values)) if user_rating_values else 6.0
    user_count = len(user_rating_values)
    user_genre_avg = float(np.mean(same_genre_ratings)) if same_genre_ratings else user_avg
    user_rated_genre_count = len(same_genre_ratings)

    feature_dict = {
        "user_avg_rating": user_avg,
        "user_ratings_count": user_count,
        "user_genre_avg": user_genre_avg,
        "user_rated_genre_count": user_rated_genre_count,
        "movie_year": movie.year or 2000,
        "tmdb_vote_average": movie.vote_average or 0.0,
        "tmdb_popularity": movie.popularity or 0.0,
        "tmdb_vote_count": movie.vote_count or 0,
    }
    for g in _metadata["all_genres"]:
        feature_dict[f"genre_{g}"] = 1 if movie.genre == g else 0

    feature_vector = np.array([
        feature_dict.get(name, 0) for name in _metadata["feature_names"]
    ]).reshape(1, -1)

    return feature_vector


def predict(user_id: int, movie: Movie, db: Session) -> dict | None:
    """
    Vraća predikciju za (user, movie). Format:
    {
      "prediction": 0 | 1,
      "probability": 0.0-1.0,
      "confidence": "high" | "medium" | "low",
      "message": str
    }
    Vraća None ako model nije dostupan.
    """
    if not _load_artifacts():
        return None

    features = build_features(user_id, movie, db)
    if features is None:
        return None

    features_scaled = _scaler.transform(features)
    prediction = int(_model.predict(features_scaled)[0])
    probability = float(_model.predict_proba(features_scaled)[0][1])

    if probability >= 0.75 or probability <= 0.25:
        confidence = "high"
    elif probability >= 0.6 or probability <= 0.4:
        confidence = "medium"
    else:
        confidence = "low"

    if prediction == 1:
        message = "👍 Svidjet će ti se!"
    else:
        message = "👎 Možda nije za tebe"

    return {
        "prediction": prediction,
        "probability": round(probability, 3),
        "confidence": confidence,
        "message": message,
    }