from sqlalchemy import Column, Integer, String, ForeignKey, Float, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime
from .database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)  
    ratings = relationship("Rating", back_populates="user")


class Movie(Base):
    __tablename__ = "movies"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True, nullable=False)
    genre = Column(String, nullable=False)
    year = Column(Integer, nullable=False)

    ratings = relationship("Rating", back_populates="movie")


class Rating(Base):
    __tablename__ = "ratings"

    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True)
    movie_id = Column(Integer, ForeignKey("movies.id"), primary_key=True)
    rating = Column(Integer, nullable=False)

    user = relationship("User", back_populates="ratings")
    movie = relationship("Movie", back_populates="ratings")

class MovieStats(Base):
    __tablename__ = "movie_stats"

    id = Column(Integer, primary_key=True, index=True)
    movie_id = Column(Integer, ForeignKey("movies.id"), unique=True, nullable=False)

    avg_rating = Column(Float, nullable=False)
    rating_count = Column(Integer, nullable=False)
    last_updated = Column(DateTime, default=datetime.utcnow)

    movie = relationship("Movie")