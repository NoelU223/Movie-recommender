"""
Trenira 3 klasifikatora (Naive Bayes, Logistic Regression, Random Forest)
na podacima iz baze i sprema najbolji model kao .pkl u /app/model/.
"""
import os
import json
import logging
from collections import defaultdict

import numpy as np
import pandas as pd
import joblib
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.preprocessing import StandardScaler
from sklearn.naive_bayes import GaussianNB
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, f1_score, roc_auc_score, classification_report

from app.database import SessionLocal
from app.models import Movie, Rating

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

MODEL_DIR = "/app/model"
RATING_THRESHOLD = 7   


def build_dataset() -> tuple[pd.DataFrame, pd.Series, list[str], list[str]]:
    """Iz baze izvlači sve (user, movie, rating) zapise i gradi features."""
    db = SessionLocal()
    try:
        movies = {m.id: m for m in db.query(Movie).all()}
        ratings = db.query(Rating).all()
        logger.info(f"Učitano {len(ratings)} ocjena, {len(movies)} filmova.")
    finally:
        db.close()

    user_ratings = defaultdict(list)        
    user_genre_ratings = defaultdict(list)  
    for r in ratings:
        movie = movies.get(r.movie_id)
        if not movie:
            continue
        user_ratings[r.user_id].append(r.rating)
        user_genre_ratings[(r.user_id, movie.genre)].append(r.rating)

    all_genres = sorted({m.genre for m in movies.values() if m.genre})

    rows = []
    for r in ratings:
        movie = movies.get(r.movie_id)
        if not movie:
            continue

        other_user_ratings = [x for x in user_ratings[r.user_id] if x != r.rating]
        user_avg = np.mean(other_user_ratings) if other_user_ratings else 6.0
        user_count = len(other_user_ratings)

        same_genre = user_genre_ratings[(r.user_id, movie.genre)]
        other_same_genre = [x for x in same_genre if x != r.rating]
        user_genre_avg = np.mean(other_same_genre) if other_same_genre else user_avg
        user_rated_genre_count = len(other_same_genre)

        row = {
            "user_avg_rating": user_avg,
            "user_ratings_count": user_count,
            "user_genre_avg": user_genre_avg,
            "user_rated_genre_count": user_rated_genre_count,
            "movie_year": movie.year or 2000,
            "tmdb_vote_average": movie.vote_average or 0.0,
            "tmdb_popularity": movie.popularity or 0.0,
            "tmdb_vote_count": movie.vote_count or 0,
        }
        for g in all_genres:
            row[f"genre_{g}"] = 1 if movie.genre == g else 0

        row["label"] = 1 if r.rating >= RATING_THRESHOLD else 0
        rows.append(row)

    df = pd.DataFrame(rows)
    y = df["label"]
    X = df.drop(columns=["label"])

    feature_names = X.columns.tolist()
    return X, y, feature_names, all_genres


def evaluate_model(name: str, model, X_train, X_test, y_train, y_test) -> dict:
    """Trenira model i vraća dict s metrikama."""
    model.fit(X_train, y_train)
    y_pred = model.predict(X_test)
    y_proba = model.predict_proba(X_test)[:, 1] if hasattr(model, "predict_proba") else None

    acc = accuracy_score(y_test, y_pred)
    f1 = f1_score(y_test, y_pred)
    auc = roc_auc_score(y_test, y_proba) if y_proba is not None else None

    cv_acc = cross_val_score(model, X_train, y_train, cv=5, scoring="accuracy").mean()

    auc_str = f"{auc:.3f}" if auc else "n/a"
    logger.info(f"  {os.name}: Acc={acc:.3f}  F1={f1:.3f}  AUC={auc_str}  CV-Acc={cv_acc:.3f}")
    logger.info("\n" + classification_report(y_test, y_pred, target_names=["<7", ">=7"]))

    return {
        "name": name,
        "model": model,
        "accuracy": acc,
        "f1": f1,
        "auc": auc if auc else 0.0,
        "cv_accuracy": cv_acc,
    }


def run():
    logger.info("=== ML Training Pipeline ===")
    X, y, feature_names, all_genres = build_dataset()

    logger.info(f"Dataset: {len(X)} primjera, {len(feature_names)} featurea.")
    logger.info(f"Class balance: {sum(y==1)} pozitivnih, {sum(y==0)} negativnih.")

    if len(X) < 50:
        logger.error("Premalo podataka za treniranje. Generiraj više sintetičkih ili dodaj prave ocjene.")
        return

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)

    logger.info("→ Treniram modele...")
    results = []
    results.append(evaluate_model(
        "Naive Bayes", GaussianNB(),
        X_train_scaled, X_test_scaled, y_train, y_test
    ))
    results.append(evaluate_model(
        "Logistic Regression", LogisticRegression(max_iter=1000, C=1.0),
        X_train_scaled, X_test_scaled, y_train, y_test
    ))
    results.append(evaluate_model(
        "Random Forest", RandomForestClassifier(n_estimators=100, random_state=42),
        X_train_scaled, X_test_scaled, y_train, y_test
    ))

    best = max(results, key=lambda r: r["f1"])
    logger.info(f"=== POBJEDNIK: {best['name']} (F1={best['f1']:.3f}) ===")

    os.makedirs(MODEL_DIR, exist_ok=True)
    joblib.dump(best["model"], f"{MODEL_DIR}/classifier.pkl")
    joblib.dump(scaler, f"{MODEL_DIR}/scaler.pkl")

    metadata = {
        "model_name": best["name"],
        "feature_names": feature_names,
        "all_genres": all_genres,
        "rating_threshold": RATING_THRESHOLD,
        "metrics": {
            "accuracy": best["accuracy"],
            "f1": best["f1"],
            "auc": best["auc"],
            "cv_accuracy": best["cv_accuracy"],
        },
        "all_results": [
            {k: v for k, v in r.items() if k != "model"} for r in results
        ],
    }
    with open(f"{MODEL_DIR}/metadata.json", "w") as f:
        json.dump(metadata, f, indent=2)

    logger.info(f"✓ Model spremljen u {MODEL_DIR}/")
    logger.info(f"  classifier.pkl, scaler.pkl, metadata.json")


if __name__ == "__main__":
    run()