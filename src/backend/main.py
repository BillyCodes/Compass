from fastapi import FastAPI

app = FastAPI(
    title="QliGenesis API Engine",
    description="Backend API for QliGenesis Platform",
    version="1.0.0"
)

@app.get("/", tags=["Health Check"])
def read_root():
    return {
        "status": "online",
        "message": "Welcome to QliGenesis API backend is running successfully!"
    }

@app.get("/health")
def health_check():
    return {"status": "ok"}
