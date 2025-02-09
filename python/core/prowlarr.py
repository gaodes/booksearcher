from typing import Optional, List, Dict
import aiohttp
import asyncio
import json
from datetime import datetime
from core.config import settings

class ProwlarrAPI:
    def __init__(self, base_url: str, api_key: str, debug: bool = False):
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.headers = {
            "X-Api-Key": api_key,
            "Accept": "application/json"
        }
        self.debug = debug
        self.request_count = 0
        self.last_error = None
        self.api_stats = {
            'requests': 0,
            'errors': 0,
            'avg_response_time': 0,
            'total_time': 0,
            'last_request': None,
            'requests_by_endpoint': {}
        }

    async def _make_request(self, method: str, endpoint: str, params: Dict = None, json_data: Dict = None) -> Dict:
        """Enhanced request handling with detailed stats"""
        self.api_stats['requests'] += 1
        endpoint_key = f"{method} {endpoint}"
        self.api_stats['requests_by_endpoint'][endpoint_key] = self.api_stats['requests_by_endpoint'].get(endpoint_key, 0) + 1
        
        start_time = datetime.now()
        
        if self.debug:
            print(f"\n🔌 API Request #{self.api_stats['requests']}")
            print(f"  Method:     {method}")
            print(f"  Endpoint:   {endpoint}")
            print(f"  User-Agent: {self.headers.get('User-Agent', 'Not set')}")
            print(f"  Rate Limit: {self.headers.get('X-Rate-Limit', 'Not set')}")
            print(f"  Params:   {params}")
            if json_data:
                print(f"  Payload:  {json.dumps(json_data, indent=2)}")

        try:
            async with aiohttp.ClientSession(headers=self.headers) as session:
                async with session.request(method, f"{self.base_url}{endpoint}", 
                                         params=params, json=json_data) as response:
                    duration = (datetime.now() - start_time).total_seconds()
                    self.api_stats['total_time'] += duration
                    self.api_stats['avg_response_time'] = self.api_stats['total_time'] / self.api_stats['requests']
                    self.api_stats['last_request'] = {
                        'timestamp': datetime.now().isoformat(),
                        'duration': duration,
                        'endpoint': endpoint,
                        'status': response.status
                    }
                    
                    if self.debug:
                        print(f"\n📡 Response Info:")
                        print(f"  Status:     {response.status} {response.reason}")
                        print(f"  Duration:   {duration:.2f}s")
                        print(f"  Headers:    {dict(response.headers)}")

                    data = await response.json()
                    
                    if self.debug and isinstance(data, (dict, list)):
                        print("\n📊 Response Summary:")
                        if isinstance(data, list):
                            print(f"  Items:      {len(data)}")
                            if data:
                                print("  First item: ")
                                print(json.dumps(data[0], indent=2)[:200] + "...")
                        else:
                            print("  Keys:       " + ", ".join(data.keys()))

                    if response.status >= 400:
                        error_msg = f"API Error: {response.status} - {data.get('error', 'Unknown error')}"
                        self.last_error = {
                            'timestamp': datetime.now().isoformat(),
                            'status': response.status,
                            'message': error_msg,
                            'response': data
                        }
                        raise aiohttp.ClientError(error_msg)

                    return data

        except aiohttp.ClientError as e:
            self.api_stats['errors'] += 1
            self.last_error = {
                'timestamp': datetime.now().isoformat(),
                'error_type': type(e).__name__,
                'message': str(e)
            }
            raise
        except Exception as e:
            self.api_stats['errors'] += 1
            self.last_error = {
                'timestamp': datetime.now().isoformat(),
                'error_type': type(e).__name__,
                'message': str(e)
            }
            raise

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
        
        try:
            # Get matching indexer IDs first
            indexer_ids = await self.get_indexer_ids(tag_ids, protocol)
            if not indexer_ids:
                raise ValueError(f"No matching indexers found for tags {tag_ids} and protocol {protocol}")

            results = await self._make_request("GET", "/api/v1/search", params=params)
            
            # Filter and sort results
            filtered = [
                r for r in results
                if r.get('indexerId') in indexer_ids
                and (not protocol or r.get('protocol', '').lower() == protocol.lower())
            ]

            if self.debug:
                print("\n🔍 Search Stats:")
                print(f"  Total results:    {len(results)}")
                print(f"  Filtered results: {len(filtered)}")
                print("  Protocols:        " + ", ".join(set(r.get('protocol', 'unknown') for r in filtered)))
                print("  Indexers:         " + ", ".join(set(r.get('indexer', 'unknown') for r in filtered)))
                if filtered:
                    sizes = [r.get('size', 0) for r in filtered]
                    print(f"  Size range:       {self._format_size(min(sizes))} - {self._format_size(max(sizes))}")

            return sorted(filtered, key=lambda x: x.get("size", 0), reverse=True)

        except Exception as e:
            if self.debug:
                print("\n❌ Error Details:")
                print(f"  Type:    {type(e).__name__}")
                print(f"  Message: {str(e)}")
                if self.last_error:
                    print("  Last API Error:")
                    print(json.dumps(self.last_error, indent=2))
            raise

    @staticmethod
    def _format_size(size: int) -> str:
        """Format size in bytes to human readable string"""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size < 1024:
                return f"{size:.2f}{unit}"
            size /= 1024
        return f"{size:.2f}PB"

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
