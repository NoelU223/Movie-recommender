from fastapi import FastAPI, Depends, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
import redis
import json
import asyncio
from prometheus_fastapi_instrumentator import Instrumentator

from .database import engine, get_db
from .models import Base, User, Movie, Rating
from sqlalchemy.orm import Session
from pathlib import Path
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

app = FastAPI(title="Movie recommender API")

Instrumentator().instrument(app).expose(app)

redis_client = redis.from_url("redis://redis:6379/0", encoding="utf-8", decode_responses=True)

app.add_middleware(SessionMiddleware, secret_key="neki_jaki_secret")

Base.metadata.create_all(bind=engine)

BASE_DIR = Path(__file__).resolve().parent

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

def hash_password(password: str) -> str:
    return pwd_context.hash(password[:72])

def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)

def get_current_user(request: Request, db: Session) -> User | None:
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    return db.query(User).filter_by(id=user_id).first()

@app.get("/health")
def health_check():
    return {"status": "ok"}

@app.get("/", response_class=HTMLResponse)
async def list_movies(request: Request, db: Session = Depends(get_db)):
    cache_key = "movies_list"
    
    try:
        cached = redis_client.get(cache_key)
        if cached:
            import ast
            movies_data = json.loads(cached)
            movies = []
            for m_data in movies_data:
                movie = Movie(id=m_data['id'], title=m_data['title'], genre=m_data['genre'], year=m_data['year'])
                movies.append(movie)
        else:
            movies = db.query(Movie).all()
            movies_data = []
            for m in movies:
                m_dict = {'id': m.id, 'title': m.title, 'genre': m.genre, 'year': m.year}
                movies_data.append(m_dict)
            redis_client.setex(cache_key, 300, json.dumps(movies_data))  
    except Exception as e:
        print(f"Redis error: {e}, fallback to DB")
        movies = db.query(Movie).all()
    
    current_user = get_current_user(request, db)
    return templates.TemplateResponse(
        "movies.html",
        {"request": request, "movies": movies, "current_user": current_user},
    )

@app.get("/movies/{movie_id}", response_class=HTMLResponse)
def movie_detail(movie_id: int, request: Request, db: Session = Depends(get_db)):
    movie = db.query(Movie).filter_by(id=movie_id).first()
    if not movie:
        return RedirectResponse("/", status_code=302)

    if movie.ratings:
        count = len(movie.ratings)
        avg_rating = sum(r.rating for r in movie.ratings) / count
    else:
        avg_rating, count = None, 0

    current_user = get_current_user(request, db)

    return templates.TemplateResponse(
        "movie_detail.html",
        {
            "request": request,
            "movie": movie,
            "avg_rating": avg_rating,
            "count": count,
            "current_user": current_user,
        },
    )

@app.get("/users/new", response_class=HTMLResponse)
def new_user_form(request: Request):
    return templates.TemplateResponse("create_user.html", {"request": request})

@app.post("/users/new")
def create_user_html(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    existing = db.query(User).filter_by(email=email).first()
    if existing:
        return RedirectResponse(url="/login", status_code=303)

    user = User(email=email, password_hash=hash_password(password))
    db.add(user)
    db.commit()
    db.refresh(user)

    request.session["user_id"] = user.id
    return RedirectResponse(url="/", status_code=303)

@app.get("/login", response_class=HTMLResponse)
def login_form(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/login")
def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter_by(email=email).first()
    if not user or not verify_password(password, user.password_hash):
        return templates.TemplateResponse(
            "login.html",
            {
                "request": request,
                "error": "Neispravan email ili lozinka.",
            },
            status_code=400,
        )

    request.session["user_id"] = user.id
    return RedirectResponse(url="/", status_code=303)

@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/", status_code=303)

@app.get("/new-movie", response_class=HTMLResponse)
def new_movie_form(request: Request, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    return templates.TemplateResponse(
        "create_movie.html",
        {"request": request, "current_user": current_user},
    )

@app.post("/new-movie")
def create_movie_html(
    request: Request,
    title: str = Form(...),
    genre: str = Form(...),
    year: int = Form(...),
    db: Session = Depends(get_db),
):
    movie = Movie(title=title, genre=genre, year=year)
    db.add(movie)
    db.commit()
    db.refresh(movie)
    
    redis_client.delete("movies_list")
    
    return RedirectResponse(url="/", status_code=303)


@app.post("/ratings/html")
def add_rating_html(
    request: Request,
    movie_id: int = Form(...),
    rating: int = Form(...),
    db: Session = Depends(get_db),
):
    current_user = get_current_user(request, db)
    if not current_user:
        return RedirectResponse(url="/login", status_code=303)

    if rating < 1 or rating > 10:
        return RedirectResponse(url=f"/movies/{movie_id}", status_code=303)

    existing = (
        db.query(Rating)
        .filter_by(user_id=current_user.id, movie_id=movie_id)
        .first()
    )

    if existing:
        existing.rating = rating
    else:
        rating_obj = Rating(user_id=current_user.id, movie_id=movie_id, rating=rating)
        db.add(rating_obj)

    db.commit()
    return RedirectResponse(url=f"/movies/{movie_id}", status_code=303)

@app.post("/users")
def create_user(email: str, password: str, db: Session = Depends(get_db)):
    user = User(email=email, password_hash=hash_password(password))
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"id": user.id, "email": user.email}

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
        return {"error": "rating_must_be_between_1_and_10"}

    existing = db.query(Rating).filter_by(user_id=user_id, movie_id=movie_id).first()
    if existing:
        existing.rating = rating
    else:
        rating_obj = Rating(user_id=user_id, movie_id=movie_id, rating=rating)
        db.add(rating_obj)

    db.commit()
    return {"message": "Rating saved"}
