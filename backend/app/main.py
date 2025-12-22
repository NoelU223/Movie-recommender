from fastapi import FastAPI
from .database import engine
from .models import Base
from sqlalchemy.orm import Session
from fastapi import Depends
from .database import get_db
from .models import User
from .models import Movie
from .models import Rating

app = FastAPI(title="Movie recommender API")

Base.metadata.create_all(bind=engine)

@app.get("/health")

def health_check():
    return {"status":"ok"}

#Endpoint for users
@app.post("/users")
def create_user(email: str, db: Session = Depends(get_db)):
    user = User(email=email)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user

#Endpoint for movies
@app.post("/movies")
def create_movie(title: str, genre: str, year: int, db: Session = Depends(get_db)):
    movie = Movie(title=title, genre=genre, year=year)
    db.add(movie)
    db.commit()
    db.refresh(movie)
    return movie


@app.get("/movies")
def get_movies(db: Session = Depends(get_db)):
    return db.query(Movie).all()

#Endpoint for ratings
@app.post("/ratings")
def add_rating(user_id: int, movie_id: int, rating: int, db: Session = Depends(get_db)):
    rating_obj = Rating(
        user_id=user_id,
        movie_id=movie_id,
        rating=rating
    )
    db.add(rating_obj)
    db.commit()
    return {"message": "Rating added"}
