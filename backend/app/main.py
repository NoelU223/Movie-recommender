from fastapi import FastAPI
from .database import engine
from .models import Base

app = FastAPI(title="Movie recommender API")

Base.metadata.create_all(bind=engine)

@app.get("/health")

def health_check():
    return {"status":"ok"}