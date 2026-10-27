from fastapi import FastAPI
from src.compass_backend.database import engine, Base
from compass_backend import models
from src.compass_backend.routers import auth, students, matching

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Compass API Engine",
    description="Backend API for the Compass Student & Job Matching Platform",
    version="1.0.0"
)

app.include_router(auth.router)
app.include_router(students.router)
app.include_router(matching.router)

@app.get("/", tags=["Health Check"])
def read_root():
    return {
        "status": "online",
        "message": "Welcome to Compass API backend is running successfully!"
    }

# Base.metadata.create_all(bind=engine)
