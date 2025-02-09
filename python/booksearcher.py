#!/usr/bin/env python3
import asyncio
import argparse
from core.config import settings
from core.prowlarr import ProwlarrAPI

async def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Search for books using Prowlarr')
    parser.add_argument('-k', '--kind', choices=['audio', 'book', 'both'], help='Media type to search for')
    parser.add_argument('-p', '--protocol', choices=['tor', 'nzb'], help='Protocol to use')
    parser.add_argument('search_term', nargs='*', help='Search term')
    
    args = parser.parse_args()
    search_term = ' '.join(args.search_term)

    # Initialize API client
    prowlarr = ProwlarrAPI(settings["PROWLARR_URL"], settings["API_KEY"])

    # Get tag IDs
    try:
        tags = await prowlarr.get_tag_ids()
        print(f"Found tags: {tags}")
        
        # Convert protocol argument
        protocol = None
        if args.protocol:
            protocol = "usenet" if args.protocol == "nzb" else "torrent"
        
        # Determine tag IDs to use
        tag_ids = []
        if args.kind in ('audio', 'both'):
            tag_ids.append(tags['audiobooks'])
        if args.kind in ('book', 'both'):
            tag_ids.append(tags['ebooks'])
            
        # Perform search
        if search_term:
            results = await prowlarr.search(search_term, tag_ids, protocol)
            print("\nSearch Results:")
            print("==============")
            for i, result in enumerate(results, 1):
                print(f"\n[{i}] {result['title']}")
                print(f"Size: {result.get('size', 'N/A')}")
                print(f"Protocol: {result.get('protocol', 'N/A')}")
                print(f"Indexer: {result.get('indexer', 'N/A')}")
                
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
