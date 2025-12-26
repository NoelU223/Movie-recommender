from fastapi import FastAPI, Depends, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .database import engine, get_db
from .models import Base, User, Movie, Rating
from sqlalchemy.orm import Session
from pathlib import Path


app = FastAPI(title="Movie recommender API")

Base.metadata.create_all(bind=engine)

BASE_DIR = Path(__file__).resolve().parent

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
def list_movies(request: Request, db: Session = Depends(get_db)):
    movies = db.query(Movie).all()
    return templates.TemplateResponse(
        "movies.html",
        {"request": request, "movies": movies},
    )


@app.get("/movies/{movie_id}", response_class=HTMLResponse)
def movie_detail(movie_id: int, request: Request, db: Session = Depends(get_db)):
    movie = db.query(Movie).filter_by(id=movie_id).first()
    if not movie:
        return RedirectResponse("/", status_code=302)

    users = db.query(User).all()

    if movie.ratings:
        count = len(movie.ratings)
        avg_rating = sum(r.rating for r in movie.ratings) / count
    else:
        avg_rating, count = None, 0

    return templates.TemplateResponse(
        "movie_detail.html",
        {
            "request": request,
            "movie": movie,
            "avg_rating": avg_rating,
            "count": count,
            "users": users,
        },
    )

@app.get("/users/new", response_class=HTMLResponse)
def new_user_form(request: Request):
    return templates.TemplateResponse("create_user.html", {"request": request})


@app.post("/users/new")
def create_user_html(
    email: str = Form(...),
    db: Session = Depends(get_db),
):
    user = User(email=email)
    db.add(user)
    db.commit()
    db.refresh(user)
    return RedirectResponse(url="/", status_code=303)


@app.get("/new-movie", response_class=HTMLResponse)
def new_movie_form(request: Request):
    return templates.TemplateResponse("create_movie.html", {"request": request})


@app.post("/new-movie")
def create_movie_html(
    title: str = Form(...),
    genre: str = Form(...),
    year: int = Form(...),
    db: Session = Depends(get_db),
):
    movie = Movie(title=title, genre=genre, year=year)
    db.add(movie)
    db.commit()
    db.refresh(movie)
    return RedirectResponse(url="/", status_code=303)


@app.post("/ratings/html")
def add_rating_html(
    user_id: int = Form(...),
    movie_id: int = Form(...),
    rating: int = Form(...),
    db: Session = Depends(get_db),
):
    if rating < 1 or rating > 10:
        return RedirectResponse(url=f"/movies/{movie_id}", status_code=303)

    existing = db.query(Rating).filter_by(user_id=user_id, movie_id=movie_id).first()

    if existing:
        existing.rating = rating 
    else:
        rating_obj = Rating(user_id=user_id, movie_id=movie_id, rating=rating)
        db.add(rating_obj)

    db.commit()
    return RedirectResponse(url=f"/movies/{movie_id}", status_code=303)


@app.post("/users")
def create_user(email: str, db: Session = Depends(get_db)):
    user = User(email=email)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


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


@app.post("/ratings")
def add_rating(user_id: int, movie_id: int, rating: int, db: Session = Depends(get_db)):

    if rating < 1 or rating > 10:
        return RedirectResponse(url=f"/movies/{movie_id}", status_code=303)
    
    rating_obj = Rating(
        user_id=user_id,
        movie_id=movie_id,
        rating=rating,
    )
    db.add(rating_obj)
    db.commit()
    return {"message": "Rating added"}
