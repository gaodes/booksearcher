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

    async def get_indexer_ids(self, tag_ids: List[int], protocol: Optional[str] = None) -> List[int]:
        """Get indexer IDs that match the given tags and protocol"""
        async with aiohttp.ClientSession(headers=self.headers) as session:
            async with session.get(f"{self.base_url}/api/v1/indexer") as response:
                indexers = await response.json()
                filtered = []
                
                for indexer in indexers:
                    if not indexer.get('enable', False):  # Skip disabled indexers
                        continue
                    
                    # Check if indexer has any of our tags
                    indexer_tags = indexer.get('tags', [])
                    if any(str(tag) in map(str, indexer_tags) for tag in tag_ids):
                        # Check protocol if specified
                        if not protocol or indexer.get('protocol', '').lower() == protocol.lower():
                            filtered.append(indexer['id'])
                
                return filtered

    async def search(self, query: str, tag_ids: List[int], protocol: Optional[str] = None) -> List[Dict]:
        """Search for releases using indexers with matching tags"""
        params = {
            "query": query,
            "type": "search",
            "limit": 100,
            "offset": 0
        }
        
        # Get matching indexer IDs first
        indexer_ids = await self.get_indexer_ids(tag_ids, protocol)
        if not indexer_ids:
            raise ValueError("No matching indexers found for the given tags and protocol")
            
        async with aiohttp.ClientSession(headers=self.headers) as session:
            async with session.get(f"{self.base_url}/api/v1/search", params=params) as response:
                results = await response.json()
                
                if isinstance(results, dict) and ("error" in results or "errors" in results):
                    raise ValueError(results.get("error") or results.get("errors"))
                
                # Filter only by protocol and matching indexers
                filtered = [
                    r for r in results
                    if r.get('indexerId') in indexer_ids
                    and (not protocol or r.get('protocol', '').lower() == protocol.lower())
                ]
                
                # Sort by size and return
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
