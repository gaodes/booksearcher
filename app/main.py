from fastapi import FastAPI, HTTPException
from core.config import settings
from core.prowlarr import ProwlarrAPI
from models.schemas import SearchRequest, GrabRequest

app = FastAPI(title="BookSearcher API")
prowlarr = ProwlarrAPI(settings.PROWLARR_URL, settings.API_KEY)

@app.get("/health")
async def health_check():
    return {"status": "ok"}

# ...rest of FastAPI endpoints will be added later...
