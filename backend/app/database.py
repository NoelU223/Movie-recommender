import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from sqlalchemy.orm import Session
from fastapi import Depends

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://movie_user:movie_pass@localhost:5432/movie_db"
)

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
