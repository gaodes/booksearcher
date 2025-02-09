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

    try:
        # Get tag IDs
        tags = await prowlarr.get_tag_ids()
        print(f"Found tags: {tags}")
        
        # Convert protocol argument
        protocol = None
        if args.protocol:
            protocol = "usenet" if args.protocol == "nzb" else "torrent"
        
        # Determine tag IDs to use based on kind argument
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
            
            if not results:
                print("No results found")
                return
                
            for i, result in enumerate(results, 1):
                # Format size
                size = result.get('size', 0)
                if size > 0:
                    if size > 1024**3:
                        size_str = f"{size/1024**3:.2f} GB"
                    elif size > 1024**2:
                        size_str = f"{size/1024**2:.2f} MB"
                    else:
                        size_str = f"{size/1024:.2f} KB"
                else:
                    size_str = "N/A"
                
                # Format protocol icon
                protocol_icon = "📡" if result.get('protocol') == "usenet" else "🧲"
                
                # Get status/grabs
                if result.get('protocol') == "usenet":
                    status = f"Grabs: {result.get('grabs', 0)}"
                else:
                    seeders = result.get('seeders', 0)
                    if seeders == 0:
                        status = "Dead torrent"
                    else:
                        status = f"🌱 {seeders} seeders"
                
                # Print formatted result
                print(f"\n[{i}] {result['title']}")
                print(f"{'─' * len(f'[{i}] {result['title']}')}") 
                print(f"📦 Size:      {size_str}")
                print(f"📅 Published: {result.get('publishDate', 'N/A')[:10]}")
                print(f"🔌 Protocol:  {protocol_icon} {result.get('protocol', 'N/A')}")
                print(f"🔍 Indexer:   {result.get('indexer', 'N/A')}")
                print(f"⚡ Status:    {status}")
            
            # Interactive selection
            while True:
                try:
                    choice = input("\nEnter result number to download (or 'q' to quit): ")
                    if choice.lower() == 'q':
                        break
                    
                    idx = int(choice) - 1
                    if 0 <= idx < len(results):
                        selected = results[idx]
                        result = await prowlarr.grab_release(
                            selected['guid'],
                            selected['indexerId']
                        )
                        print("\n✨ Successfully sent to download client!")
                        break
                    else:
                        print("Invalid selection, try again")
                except ValueError:
                    print("Please enter a valid number")
                except Exception as e:
                    print(f"Error grabbing release: {e}")
                    break
                
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
