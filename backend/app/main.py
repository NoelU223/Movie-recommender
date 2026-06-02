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
from .models import Base, User, Movie, Rating, Watchlist, Favorite
from sqlalchemy.orm import Session
from pathlib import Path
from passlib.context import CryptContext
from .events.producer import send_event
from datetime import datetime, timezone


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

app = FastAPI(title="Movie recommender API")



@app.middleware("http")
async def track_event(request: Request, call_next):
    """Bilježi svaki HTTP request kao event u Kafku."""
    response = await call_next(request)

    path = request.url.path
    if path.startswith("/static") or path in ("/metrics", "/health", "/favicon.ico"):
        return response

    event_type = _classify_event(request.method, path)
    if event_type is None:
        return response

    user_id = request.session.get("user_id")

    event = {
        "event_type": event_type,
        "user_id": user_id,
        "path": path,
        "method": request.method,
        "status_code": response.status_code,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    if event_type == "view_movie" and path.startswith("/movies/"):
        try:
            event["movie_id"] = int(path.split("/")[2])
        except (ValueError, IndexError):
            pass
        
    if event_type in ("watchlist_add", "watchlist_remove",
                      "favorite_add", "favorite_remove"):
        try:
            event["movie_id"] = int(path.split("/")[3])
        except (ValueError, IndexError):
            pass
        
    send_event(event)
    return response

def _classify_event(method: str, path: str) -> str | None:
    if method == "GET" and path == "/":
        return "view_list"
    if method == "GET" and path.startswith("/movies/"):
        return "view_movie"
    if method == "POST" and path == "/login":
        return "login"
    if method == "POST" and path == "/users/new":
        return "register"
    if method == "GET" and path == "/logout":
        return "logout"
    if method == "POST" and path == "/ratings/html":
        return "rate_movie"
    if method == "POST" and path == "/new-movie":
        return "create_movie"
    if method == "POST" and path.startswith("/watchlist/add/"):
        return "watchlist_add"
    if method == "POST" and path.startswith("/watchlist/remove/"):
        return "watchlist_remove"
    if method == "POST" and path.startswith("/favorites/add/"):
        return "favorite_add"
    if method == "POST" and path.startswith("/favorites/remove/"):
        return "favorite_remove"
    if method == "GET" and path == "/profile":
        return "view_profile"
    return None

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
            movies_data = json.loads(cached)
            movies = []
            for m_data in movies_data:
                movie = Movie(
                    id=m_data['id'],
                    title=m_data['title'],
                    genre=m_data['genre'],
                    year=m_data['year'],
                    poster_path=m_data.get('poster_path'),
                    vote_average=m_data.get('vote_average'),
                )
                movies.append(movie)
        else:
            movies = db.query(Movie).all()
            movies_data = []
            for m in movies:
                m_dict = {
                    'id': m.id,
                    'title': m.title,
                    'genre': m.genre,
                    'year': m.year,
                    'poster_path': m.poster_path,
                    'vote_average': m.vote_average,
                }
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

    in_watchlist = False
    in_favorites = False
    if current_user:
        in_watchlist = db.query(Watchlist).filter_by(
            user_id=current_user.id, movie_id=movie_id
        ).first() is not None
        in_favorites = db.query(Favorite).filter_by(
            user_id=current_user.id, movie_id=movie_id
        ).first() is not None

    return templates.TemplateResponse(
        "movie_detail.html",
        {
            "request": request,
            "movie": movie,
            "avg_rating": avg_rating,
            "count": count,
            "current_user": current_user,
            "in_watchlist": in_watchlist,
            "in_favorites": in_favorites,
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

@app.post("/watchlist/add/{movie_id}")
def watchlist_add(movie_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=303)

    existing = db.query(Watchlist).filter_by(user_id=user.id, movie_id=movie_id).first()
    if not existing:
        db.add(Watchlist(user_id=user.id, movie_id=movie_id))
        db.commit()

    return RedirectResponse(url=f"/movies/{movie_id}", status_code=303)

@app.post("/watchlist/remove/{movie_id}")
def watchlist_remove(movie_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=303)

    db.query(Watchlist).filter_by(user_id=user.id, movie_id=movie_id).delete()
    db.commit()
    return RedirectResponse(url=f"/movies/{movie_id}", status_code=303)

@app.post("/favorites/add/{movie_id}")
def favorite_add(movie_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=303)

    existing = db.query(Favorite).filter_by(user_id=user.id, movie_id=movie_id).first()
    if not existing:
        db.add(Favorite(user_id=user.id, movie_id=movie_id))
        db.commit()

    return RedirectResponse(url=f"/movies/{movie_id}", status_code=303)


@app.post("/favorites/remove/{movie_id}")
def favorite_remove(movie_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=303)

    db.query(Favorite).filter_by(user_id=user.id, movie_id=movie_id).delete()
    db.commit()
    return RedirectResponse(url=f"/movies/{movie_id}", status_code=303)

@app.get("/profile", response_class=HTMLResponse)
def profile(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=303)

    watchlist_movies = (
        db.query(Movie)
        .join(Watchlist, Watchlist.movie_id == Movie.id)
        .filter(Watchlist.user_id == user.id)
        .order_by(Watchlist.added_at.desc())
        .all()
    )

    favorite_movies = (
        db.query(Movie)
        .join(Favorite, Favorite.movie_id == Movie.id)
        .filter(Favorite.user_id == user.id)
        .order_by(Favorite.added_at.desc())
        .all()
    )

    rated = (
        db.query(Movie, Rating)
        .join(Rating, Rating.movie_id == Movie.id)
        .filter(Rating.user_id == user.id)
        .all()
    )

    total_ratings = len(rated)
    avg_user_rating = (
        sum(r.rating for _, r in rated) / total_ratings
        if total_ratings else None
    )

    return templates.TemplateResponse(
        "profile.html",
        {
            "request": request,
            "current_user": user,
            "watchlist_movies": watchlist_movies,
            "favorite_movies": favorite_movies,
            "rated": rated,
            "total_ratings": total_ratings,
            "avg_user_rating": avg_user_rating,
        },
    )