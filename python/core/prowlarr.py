from typing import Optional, List, Dict
import aiohttp
import asyncio
from core.config import settings

class ProwlarrAPI:
    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.headers = {
            "X-Api-Key": api_key,
            "Accept": "application/json"
        }

    async def get_tag_ids(self) -> Dict[str, int]:
        """Get audiobooks and ebooks tag IDs"""
        async with aiohttp.ClientSession(headers=self.headers) as session:
            async with session.get(f"{self.base_url}/api/v1/tag") as response:
                tags = await response.json()
                
                audiobooks_tag = next(
                    (tag for tag in tags if tag["label"].lower() == "audiobooks"),
                    None
                )
                ebooks_tag = next(
                    (tag for tag in tags if tag["label"].lower() == "ebooks"),
                    None
                )
                
                if not audiobooks_tag or not ebooks_tag:
                    raise ValueError("Required tags 'audiobooks' and/or 'ebooks' not found")
                
                return {
                    "audiobooks": audiobooks_tag["id"],
                    "ebooks": ebooks_tag["id"]
                }

    async def search(self, query: str, tag_ids: List[int], protocol: Optional[str] = None) -> List[Dict]:
        """Search for releases"""
        params = {
            "query": query,
            "type": "search",
            "limit": 100,
            "offset": 0
        }
        
        print(f"Searching with params: {params}")
        print(f"Using tag IDs: {tag_ids}")
        print(f"Protocol filter: {protocol}")
        
        async with aiohttp.ClientSession(headers=self.headers) as session:
            async with session.get(f"{self.base_url}/api/v1/search", params=params) as response:
                results = await response.json()
                
                if isinstance(results, dict) and ("error" in results or "errors" in results):
                    raise ValueError(results.get("error") or results.get("errors"))
                
                print(f"Total results before filtering: {len(results)}")
                
                # Filter results
                filtered = []
                for r in results:
                    result_tags = r.get("indexerTags", [])  # Changed from tags to indexerTags
                    if any(str(tag) in map(str, result_tags) for tag in tag_ids):
                        if not protocol or r.get("protocol", "").lower() == protocol.lower():
                            filtered.append(r)
                
                print(f"Results after filtering: {len(filtered)}")
                return sorted(filtered, key=lambda x: x.get("size", 0), reverse=True)

    async def grab_release(self, guid: str, indexer_id: int) -> Dict:
        """Grab a release for download"""
        payload = {
            "guid": guid,
            "indexerId": indexer_id
        }
        
        async with aiohttp.ClientSession(headers=self.headers) as session:
            async with session.post(f"{self.base_url}/api/v1/search", json=payload) as response:
                result = await response.json()
                
                if "rejected" in result:
                    raise ValueError(f"Download rejected: {result['rejected']}")
                
                return result
