from pydantic import BaseModel
from typing import Optional, List

class SearchRequest(BaseModel):
    query: str
    media_type: str
    protocol: Optional[str] = None

class SearchResponse(BaseModel):
    id: str
    title: str
    size: int
    protocol: str
    indexer: str
    download_url: str

class GrabRequest(BaseModel):
    guid: str
    indexer_id: int
