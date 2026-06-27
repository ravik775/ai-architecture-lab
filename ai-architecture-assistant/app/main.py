from fastapi import FastAPI, HTTPException

from app.schemas import ArchitectureRequest, ArchitectureRecommendation
from app.architecture_service import generate_architecture_recommendation

app = FastAPI(title="Architecture Recommendation API", version="1.0.0")

@app.get("/")
def health_check():
    return {"status": "ok"}


@app.post("/recommendation", response_model=ArchitectureRecommendation)
def recommendation_endpoint(request: ArchitectureRequest):
    try:
        return generate_architecture_recommendation(request);
    except Exception as e:
        return HTTPException(status_code=500, detail=str(e))
