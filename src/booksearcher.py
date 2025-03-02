#!/usr/bin/env python3
import asyncio
import argparse
import sys
import time
import json
import os
import threading
import aiohttp
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any, TypedDict
from core.config import settings
from core.prowlarr import ProwlarrAPI

class SearchError(Exception):
    """Base exception for search related errors"""
    pass

class CacheError(Exception):
    """Base exception for cache related errors"""
    pass

class PerformanceStats(TypedDict):
    start_time: Optional[datetime]
    total_searches: int
    total_grabs: int
    cache_hits: int
    cache_misses: int

class LastError(TypedDict):
    timestamp: str
    context: str
    type: str
    message: str

class Spinner:
    def __init__(self):
        self.spinner = ['⣾', '⣽', '⣻', '⢿', '⡿', '⣟', '⣯', '⣷']
        self.busy = False
        self.delay = 0.1
        self.thread = None

    def write(self, message):
        sys.stdout.write(message)
        sys.stdout.flush()

    def spin(self):
        while self.busy:
            for char in self.spinner:
                self.write(f'\rSearching {char}')
                time.sleep(self.delay)

    def start(self):
        self.busy = True
        self.thread = threading.Thread(target=self.spin)
        self.thread.start()

    def stop(self):
        self.busy = False
        if self.thread:
            self.thread.join()
        self.write('\r')

class BookSearcher:
    # Maximum cache size in bytes (default: 100MB)
    MAX_CACHE_SIZE = 100 * 1024 * 1024
    # Maximum number of cached searches
    MAX_CACHED_SEARCHES = 100
    
    def __init__(self) -> None:
        """Initialize the BookSearcher with necessary components and settings."""
        self.cache_dir: str = os.path.join(os.path.dirname(__file__), 'cache')
        self.prowlarr: ProwlarrAPI = ProwlarrAPI(settings["PROWLARR_URL"], settings["API_KEY"])
        self.spinner: Spinner = Spinner()
        self.debug: bool = False
        self.last_error: Optional[LastError] = None
        self.debug_log: List[Dict[str, Any]] = []
        self.performance_stats: PerformanceStats = {
            'start_time': None,
            'total_searches': 0,
            'total_grabs': 0,
            'cache_hits': 0,
            'cache_misses': 0
        }
        self.current_search: Optional[str] = None
        self.current_kind: Optional[str] = None
        self.current_protocol: Optional[str] = None
        
        try:
            os.makedirs(self.cache_dir, exist_ok=True)
            # Run initial cache cleanup
            self._cleanup_cache()
        except OSError as e:
            raise CacheError(f"Failed to create cache directory: {str(e)}")

    async def handle_error(self, error: Exception, context: str = "") -> None:
        """
        Centralized error handling with improved error categorization and logging.
        
        Args:
            error: The exception that occurred
            context: Additional context about where the error occurred
        """
        self.spinner.stop()
        
        error_category = "Unknown"
        if isinstance(error, SearchError):
            error_category = "Search"
        elif isinstance(error, CacheError):
            error_category = "Cache"
        elif isinstance(error, aiohttp.ClientError):
            error_category = "Network"
        
        self.last_error = {
            'timestamp': datetime.now().isoformat(),
            'context': context,
            'type': f"{error_category}: {type(error).__name__}",
            'message': str(error)
        }

        print(f"\n❌ {error_category} Error: {str(error)}")
        
        if self.debug:
            import traceback
            print("\n🔧 Debug Information:")
            print(f"  Category: {error_category}")
            print(f"  Context:  {context}")
            print(f"  Type:     {type(error).__name__}")
            print(f"  Location: {error.__traceback__.tb_frame.f_code.co_filename}:{error.__traceback__.tb_lineno}")
            print("\n📜 Traceback:")
            print(traceback.format_exc())
            
            if hasattr(self.prowlarr, 'last_error') and self.prowlarr.last_error:
                print("\n🌐 Last API Error:")
                print(json.dumps(self.prowlarr.last_error, indent=2))

    def show_media_type_menu(self) -> tuple[List[int], str, str]:
        """Interactive media type selection"""
        while True:
            print("\n📚 Welcome to BookSearcher! 📚")
            print("───────────────────────────")
            print("Choose what type of books you're looking for:")
            print("\n1) 🎧 Audiobooks")
            print("   Perfect for listening while commuting or doing other activities")
            print("\n2) 📚 eBooks")
            print("   Digital books for your e-reader or tablet")
            print("\n3) 🎧+📚 Both Formats")
            print("   Search for both audiobooks and ebooks simultaneously")
            print("\nq) ❌ Quit")
            
            choice = input("\n✨ Your choice > ").strip().lower()
            
            if choice == 'q':
                sys.exit(0)
            elif choice == '1':
                return [self.tags['audiobooks']], "Audiobooks", "🎧"
            elif choice == '2':
                return [self.tags['ebooks']], "eBook", "📚"
            elif choice == '3':
                return [self.tags['audiobooks'], self.tags['ebooks']], "Audiobooks & eBooks", "🎧+📚"
            else:
                print("\n❌ Please choose 1, 2, 3, or q to quit")

    async def run(self):
        self.performance_stats['start_time'] = datetime.now()
        parser = self.create_parser()
        args = parser.parse_args()
        self.debug = args.debug

        try:
            # Get tags silently first since we need them for searches
            self.tags = await self.prowlarr.get_tag_ids()
        except Exception as e:
            await self.handle_error(e, "Failed to get tag IDs")
            return

        if self.debug:
            print("\n🔧 Debug Mode Enabled")
            print("──────────────────────")
            print(f"📂 Cache Dir: {self.cache_dir}")
            print(f"🔌 Prowlarr URL: {settings['PROWLARR_URL']}")
            print(f"⚙️  Cache Max Age: {settings['CACHE_MAX_AGE']}s")
            print(f"🏷️  Tags: {self.tags}")
            print("──────────────────────\n")

        # If only search term provided (no flags), set defaults for interactive search
        if args.search_term and not any([
            args.kind, args.protocol, args.headless, args.search, args.grab,
            args.list_cache, args.clear_cache, args.search_last, args.debug
        ]):
            self.current_search = ' '.join(args.search_term)
            self.current_kind = 'Audiobooks & eBooks'
            self.current_protocol = None
            
            # Get tags for both types
            tag_ids = [self.tags['audiobooks'], self.tags['ebooks']]
            
            # Show searching animation
            self.spinner.start()
            results = await self.prowlarr.search(self.current_search, tag_ids, None)
            self.spinner.stop()

            if not results:
                print("No results found")
                return

            # Save and display results
            search_id = self.get_next_search_id()
            self.save_search_results(
                search_id,
                results,
                self.current_search,
                self.current_kind,
                None,
                'interactive'
            )

            await self.display_results(results, search_id, False)
            return

        if self.debug:
            print("\n🔧 Debug Mode Enabled")
            print("──────────────────────")
            print(f"📂 Cache Dir: {self.cache_dir}")
            print(f"🔌 Prowlarr URL: {settings['PROWLARR_URL']}")
            print(f"⚙️  Cache Max Age: {settings['CACHE_MAX_AGE']}s")
            print("──────────────────────\n")

        # Handle search-last functionality
        if args.search_last and args.grab:
            # Find most recent search
            searches = []
            for entry in os.listdir(self.cache_dir):
                if entry.startswith('search_'):
                    try:
                        search_id = int(entry.split('_')[1])
                        meta_file = os.path.join(self.cache_dir, entry, 'meta.json')
                        if os.path.exists(meta_file):
                            searches.append((search_id, os.path.getmtime(meta_file)))
                    except (ValueError, OSError):
                        continue

            if not searches:
                print("No recent searches found")
                return

            latest_id = max(searches, key=lambda x: x[1])[0]
            print(f"Using most recent search #{latest_id}")
            await self.handle_grab(latest_id, args.grab)
            return
        
        if args.list_cache is not None:
            # If no specific ID provided, show all searches
            if isinstance(args.list_cache, bool):
                await self.list_cached_searches()
            # Otherwise show specific search details
            else:
                await self.list_cached_search_by_id(args.list_cache)
            return
        
        if args.clear_cache:
            self.clear_cache()
            return

        if args.search and args.grab:
            await self.handle_grab(args.search, args.grab)
            return

        # Handle search operation
        await self.handle_search(args)
        
        if self.debug:
            await self.show_debug_stats()

    def create_parser(self) -> argparse.ArgumentParser:
        """Create argument parser with all supported flags"""
        parser = argparse.ArgumentParser(description='Search for books using Prowlarr')
        parser.add_argument('-k', '--kind', choices=['audio', 'book', 'both'], help='Media type')
        parser.add_argument('-p', '--protocol', choices=['tor', 'nzb'], help='Protocol')
        parser.add_argument('-x', '--headless', action='store_true', help='Headless mode')
        parser.add_argument('-s', '--search', type=int, help='Search ID')
        parser.add_argument('-g', '--grab', type=int, help='Result number')
        parser.add_argument('--list-cache', nargs='?', const=True, type=int, help='List cached searches or a specific search ID')
        parser.add_argument('--clear-cache', action='store_true', help='Clear cache')
        parser.add_argument('-sl', '--search-last', action='store_true', help='Use most recent search')
        parser.add_argument('-d', '--debug', action='store_true', help='Enable debug output')
        parser.add_argument('search_term', nargs='*', help='Search term')
        return parser

    def get_next_search_id(self) -> int:
        """Get next available search ID"""
        existing_searches = [int(f.split('_')[1]) for f in os.listdir(self.cache_dir) 
                           if f.startswith('search_')]
        return max(existing_searches, default=0) + 1

    def _get_cache_size(self) -> int:
        """
        Calculate the total size of the cache directory in bytes.
        
        Returns:
            int: Total size of cache in bytes
        """
        total_size = 0
        for dirpath, _, filenames in os.walk(self.cache_dir):
            for f in filenames:
                fp = os.path.join(dirpath, f)
                total_size += os.path.getsize(fp)
        return total_size

    def _get_cache_entries(self) -> List[tuple[int, str, float]]:
        """
        Get all cache entries sorted by access time.
        
        Returns:
            List of tuples containing (search_id, path, last_access_time)
        """
        entries = []
        for entry in os.listdir(self.cache_dir):
            if entry.startswith('search_'):
                try:
                    search_id = int(entry.split('_')[1])
                    path = os.path.join(self.cache_dir, entry)
                    # Use the most recent access time of any file in the search directory
                    max_atime = max(
                        os.path.getatime(os.path.join(root, f))
                        for root, _, files in os.walk(path)
                        for f in files
                    )
                    entries.append((search_id, path, max_atime))
                except (ValueError, OSError):
                    continue
        return sorted(entries, key=lambda x: x[2])  # Sort by access time

    def _cleanup_cache(self) -> None:
        """
        Clean up the cache directory based on size and entry limits.
        Removes oldest accessed entries first when limits are exceeded.
        """
        try:
            # Check if we're over the entry limit
            entries = self._get_cache_entries()
            while len(entries) > settings["CACHE_MAX_ENTRIES"]:
                search_id, path, _ = entries.pop(0)  # Remove oldest
                self._remove_cache_entry(path)
                if self.debug:
                    self._log_debug(f"Removed cache entry {search_id} due to entry limit")

            # Check if we're over the size limit
            while self._get_cache_size() > settings["CACHE_MAX_SIZE"] and entries:
                search_id, path, _ = entries.pop(0)  # Remove oldest
                self._remove_cache_entry(path)
                if self.debug:
                    self._log_debug(f"Removed cache entry {search_id} due to size limit")

        except Exception as e:
            if self.debug:
                self._log_debug(f"Cache cleanup error: {str(e)}", "cleanup")

    def _remove_cache_entry(self, path: str) -> None:
        """
        Safely remove a cache entry directory.
        
        Args:
            path: Path to the cache entry directory
        """
        try:
            import shutil
            shutil.rmtree(path)
        except Exception as e:
            if self.debug:
                self._log_debug(f"Failed to remove cache entry {path}: {str(e)}", "cleanup")

    def save_search_results(self, search_id: int, results: List[Dict], 
                          search_term: str, kind: str, protocol: Optional[str], mode: str) -> None:
        """Save search results to cache"""
        search_dir = os.path.join(self.cache_dir, f'search_{search_id}')
        
        try:
            os.makedirs(search_dir, exist_ok=True)

            # Save results
            with open(os.path.join(search_dir, 'results.json'), 'w') as f:
                json.dump(results, f)

            # Save metadata
            meta = {
                'timestamp': datetime.now().isoformat(),
                'search_term': search_term,
                'kind': kind,
                'protocol': protocol,
                'mode': mode
            }
            with open(os.path.join(search_dir, 'meta.json'), 'w') as f:
                json.dump(meta, f)

            # Run cleanup after saving new results
            self._cleanup_cache()
            
        except OSError as e:
            raise CacheError(f"Failed to save search results: {str(e)}")

    async def handle_search(self, args):
        """Handle search operation"""
        try:
            # Store current search parameters for headless mode
            if args.headless and args.search_term:
                self.current_search = ' '.join(args.search_term)
                self.current_kind = 'both'  # Default to both
                self.current_protocol = None  # Default to both protocols
                
                # Get tags for both ebooks and audiobooks
                tag_ids = [
                    self.tags['audiobooks'],
                    self.tags['ebooks']
                ]

                if self.debug:
                    print(f"\n🔍 Executing search with:")
                    print(f"  Term: {self.current_search}")
                    print(f"  Tags: {tag_ids}")
                    print(f"  Protocol: {self.current_protocol}")

                # Show searching animation
                self.spinner.start()
                results = await self.prowlarr.search(self.current_search, tag_ids, None)
                self.spinner.stop()

                if not results:
                    print("No results found")
                    return

                # Save results
                search_id = self.get_next_search_id()
                self.save_search_results(
                    search_id,
                    results,
                    self.current_search,
                    'both',
                    None,
                    'headless'
                )

                await self.display_results(results, search_id, True)
                return

            # If no arguments provided, go into interactive mode
            if not args.search_term and not args.search and not args.grab:
                # Get media type from menu
                tag_ids, kind, icon = self.show_media_type_menu()
                
                # Get search term
                while True:
                    print("\n🔍 Enter Your Search Term:")
                    print("─────────────────────────")
                    print("✨ You can search by:")
                    print("  📝 Book title (e.g., 'The Great Gatsby')")
                    print("  👤 Author name (e.g., 'Stephen King')")
                    print("  📚 Series name (e.g., 'Harry Potter')")
                    print("\n❌ Type 'q' to quit")
                    search_term = input("\n🔎 Search > ").strip()
                    
                    if search_term.lower() == 'q':
                        return
                    if search_term:
                        break
                    print("\n❌ Please enter a search term")

                # Show searching animation
                print("\n🔍 Searching through multiple sources...")
                self.spinner.start()
                results = await self.prowlarr.search(search_term, tag_ids, None)
                self.spinner.stop()

                if self.debug:
                    print(f"\n📊 Results Summary:")
                    print(f"  Total results: {len(results)}")
                    print("  Protocols: " + ", ".join(set(r.get('protocol', 'unknown') for r in results)))
                    print("  Indexers: " + ", ".join(set(r.get('indexer', 'unknown') for r in results)))
                    print("──────────────────────")

                if not results:
                    print("No results found")
                    return

                # Save and display results
                search_id = self.get_next_search_id()
                self.save_search_results(
                    search_id,
                    results,
                    search_term,
                    kind,
                    None,
                    'interactive'
                )

                await self.display_results(results, search_id, False)
                return

            # Handle normal search with arguments
            search_term = ' '.join(args.search_term)

            try:
                # Store current search parameters
                self.current_search = search_term
                self.current_kind = args.kind if args.kind else 'both'
                self.current_protocol = args.protocol

                # Get tag IDs based on kind argument
                tag_ids = []
                if not args.kind or args.kind in ('audio', 'both'):
                    tag_ids.append(self.tags['audiobooks'])
                if not args.kind or args.kind in ('book', 'both'):
                    tag_ids.append(self.tags['ebooks'])

                # Convert protocol
                protocol = None
                if args.protocol:
                    protocol = "usenet" if args.protocol == "nzb" else "torrent"

                # Perform search
                if search_term:
                    if self.debug:
                        print(f"\n🔍 Executing search with:")
                        print(f"  Term: {search_term}")
                        print(f"  Tags: {tag_ids}")
                        print(f"  Protocol: {protocol}")
                    
                    # Always show spinner during search
                    self.spinner.start()
                    results = await self.prowlarr.search(search_term, tag_ids, protocol)
                    self.spinner.stop()
                    
                    if self.debug:
                        print(f"\n📊 Results Summary:")
                        print(f"  Total results: {len(results)}")
                        print("  Protocols: " + ", ".join(set(r.get('protocol', 'unknown') for r in results)))
                        print("  Indexers: " + ", ".join(set(r.get('indexer', 'unknown') for r in results)))
                        print("──────────────────────")

                    if not results:
                        print("No results found")
                        return

                    # Save results
                    search_id = self.get_next_search_id()
                    self.save_search_results(
                        search_id, 
                        results,
                        search_term,
                        args.kind or 'both',
                        protocol,
                        'headless' if args.headless else 'interactive'
                    )

                    await self.display_results(results, search_id, args.headless)

            except Exception as e:
                await self.handle_error(e, "Search operation")

        except Exception as e:
            await self.handle_error(e, "Search operation")

    async def handle_grab(self, search_id: int, result_num: int):
        """Handle grab operation"""
        try:
            if self.debug:
                print(f"\n🔧 Grab Operation:")
                print(f"  Search ID: {search_id}")
                print(f"  Result #: {result_num}")
                
            search_dir = os.path.join(self.cache_dir, f'search_{search_id}')
            
            try:
                # Load results
                with open(os.path.join(search_dir, 'results.json')) as f:
                    results = json.load(f)
                
                if not 0 <= result_num - 1 < len(results):
                    raise ValueError(f"Invalid result number {result_num}")
                
                result = results[result_num - 1]
                await self.prowlarr.grab_release(result['guid'], result['indexerId'])
                
                protocol_icon = "📡" if result.get('protocol') == "usenet" else "🧲"
                kind_icon = "🎧" if "audiobooks" in result.get('categories', []) else "📚"
                
                print("✨ Successfully sent to download client! ✨")
                print("═" * 60)
                print(f"📥 Title:          {result['title']}")
                print(f"📚 Kind:          {kind_icon} {'Audiobook' if kind_icon == '🎧' else 'eBook'}")
                print(f"🔌 Protocol:      {protocol_icon} {result.get('protocol', 'N/A')}")
                print(f"🔍 Indexer:       {result.get('indexer', 'N/A')}")
                
            except FileNotFoundError:
                print(f"Error: Search #{search_id} not found")
            except Exception as e:
                await self.handle_error(e, f"Grab operation (Search #{search_id}, Result #{result_num})")
        except Exception as e:
            await self.handle_error(e, f"Grab operation (Search #{search_id}, Result #{result_num})")

    async def display_results(self, results: List[Dict], search_id: int, headless: bool = False, interactive: bool = True):
        if headless:
            self._display_headless_results(results, search_id)
            return

        print("\n📚 Search Results Found 📚")
        print("═══════════════════════")
        print(f"Found {len(results)} items\n")

        def get_visual_width(s: str) -> int:
            """Get the visual width of a string, counting emojis as width 2"""
            width = 0
            for c in s:
                if ord(c) > 0xFFFF:  # Emoji characters
                    width += 2
                else:
                    width += 1
            return width

        for i, result in enumerate(results, 1):
            # Calculate box width based on title but with space for adjustments
            title = f"【{i}】{result['title']}"
            title_width = get_visual_width(title)
            box_width = title_width + 6  # Adding more padding for adjustments

            # Draw the box only around the title
            print(f"┌{'─' * box_width}┐")
            print(f"│ {title}{' ' * (box_width - title_width - 3)}│")
            print(f"└{'─' * box_width}┘")

            # Format info first
            size_str = "N/A"
            if result.get('size', 0) > 0:
                size = result.get('size', 0)
                if size > 1024**3:
                    size_str = f"{size/1024**3:.2f} GB"
                elif size > 1024**2:
                    size_str = f"{size/1024**2:.2f} MB"
                else:
                    size_str = f"{size/1024:.2f} KB"

            protocol_icon = "📡" if result.get('protocol') == "usenet" else "🧲"
            status = f"💫 {result.get('grabs', 0)} grabs" if result.get('protocol') == "usenet" else \
                     f"🌱 {result.get('seeders', 0)} seeders" if result.get('seeders', 0) > 0 else "💀 Dead torrent"

            # Print details left-aligned
            details = [
                f"📦 Size:          {size_str}",
                f"📅 Published:     {result.get('publishDate', 'N/A')[:10]}", 
                f"🔌 Protocol:      {protocol_icon} {result.get('protocol', 'N/A')}", 
                f"🔍 Indexer:       {result.get('indexer', 'N/A')}", 
                f"⚡ Status:        {status}"
            ]

            # Print each detail line with consistent left alignment
            for line in details:
                print(f"  {line}")

            print()  # Empty line between results

        # Add search summary after results but before search ID
        print("\n" + "═" * 50)
        print("📊 Search Summary")
        print("─" * 50)
        print(f"🔍 Found: {len(results)} items")
        protocols = []
        for p in set(r.get('protocol', 'unknown') for r in results):
            icon = "📡" if p == "usenet" else "🧲"
            protocols.append(f"{icon} {p}")
        print(f"🔌 Protocols: {', '.join(sorted(protocols))}")
        print(f"🌐 Sites: {', '.join(sorted(set(r.get('indexer', 'unknown') for r in results)))}")
        print("═" * 50)

        # Then show search ID and instructions
        print("\n" + "═" * 60)
        print("✨ Search saved! To download later, use this ID: ✨")
        print(f"🔑 Search ID: #{search_id}")
        print("═" * 60)
        print("\nTo download, use:")
        print(f"bs -s {search_id} -g <result_number>")

        if interactive:
            await self._handle_interactive_selection(results)

    async def _handle_interactive_selection(self, results: List[Dict]):
        """Handle interactive result selection"""
        while True:
            try:
                choice = input("\nEnter result number to download (or 'q' to quit): ")
                if choice.lower() == 'q':
                    return

                idx = int(choice) - 1
                if 0 <= idx < len(results):
                    selected = results[idx]
                    await self.prowlarr.grab_release(selected['guid'], selected['indexerId'])
                    print("\n✨ Successfully sent to download client!")
                    print(f"📥 Title:")
                    print(f"    {selected['title']}")
                    # Removed the return statement here to keep the loop going
                else:
                    print("Invalid selection. Please try again.")
            except ValueError:
                print("Please enter a valid number")
            except Exception as e:
                await self.handle_error(e, "Interactive selection")
                # Continue the loop even after an error

    async def list_cached_searches(self):
        """List all cached searches and allow interactive selection"""
        if not os.path.exists(self.cache_dir):
            print("No cached searches found")
            return

        searches = []
        for entry in os.listdir(self.cache_dir):
            if not entry.startswith('search_'):
                continue

            try:
                sid = int(entry.split('_')[1])
                meta_file = os.path.join(self.cache_dir, entry, 'meta.json')
                
                with open(meta_file) as f:
                    meta = json.load(f)
                
                timestamp = datetime.fromisoformat(meta['timestamp'])
                age = datetime.now() - timestamp
                age_str = self._format_age(age)
                kind_icon = self._get_kind_icon(meta['kind'])
                
                searches.append({
                    'id': sid,
                    'term': meta['search_term'],
                    'kind': meta['kind'],
                    'icon': kind_icon,
                    'age': age_str,
                    'timestamp': timestamp
                })
            except (ValueError, FileNotFoundError, json.JSONDecodeError):
                continue

        if not searches:
            print("No valid cached searches found")
            return

        # Sort by ID in ascending order (oldest first)
        searches.sort(key=lambda x: x['id'])

        print("\n📚 Cached Searches")
        print("═══════════════════")
        for search in searches:
            print(f"\n[{search['id']}] {search['term']}")
            print(f"  🧩 Kind: {search['icon']} {search['kind']}")
            print(f"  ⏰ Age:  {search['age']}")

        print("\n✨ To view details of a specific search, use:")
        print("bs --list-cache <search_id>")

    async def list_cached_search_by_id(self, search_id: int):
        """List a specific cached search by ID"""
        search_dir = os.path.join(self.cache_dir, f'search_{search_id}')
        results_file = os.path.join(search_dir, 'results.json')
        meta_file = os.path.join(search_dir, 'meta.json')

        if not os.path.exists(results_file) or not os.path.exists(meta_file):
            print(f"Error: Search ID #{search_id} not found")
            return

        try:
            with open(meta_file) as f:
                meta = json.load(f)
            with open(results_file) as f:
                results = json.load(f)

            print(f"\n📚 Showing cached results for search #{search_id}")
            print(f"🔍 Term: {meta['search_term']}")
            await self.display_results(results, search_id, False, interactive=False)
        except (json.JSONDecodeError, FileNotFoundError) as e:
            print(f"Error: Failed to load search ID #{search_id}. {str(e)}")
        finally:
            sys.exit(0)  # Ensure the script exits after displaying the results

    @staticmethod
    def _format_age(age: timedelta) -> str:
        """Format timedelta into human readable string"""
        if age.days > 0:
            return f"{age.days}d {age.seconds // 3600}h ago"
        if age.seconds >= 3600:
            return f"{age.seconds // 3600}h {(age.seconds % 3600) // 60}m ago"
        return f"{age.seconds // 60}m ago"

    @staticmethod
    def _get_kind_icon(kind: str) -> str:
        """Get icon for media kind"""
        icons = {
            "audiobooks": "🎧",
            "Audiobooks": "🎧",
            "ebook": "📚",
            "eBook": "📚",
            "book": "📚",
            "both": "🎧+📚",
            "Audiobooks & eBooks": "🎧+📚",
            None: "🎧+📚"  # Default to both icons
        }
        return icons.get(kind.lower() if isinstance(kind, str) else None, "🎧+📚")

    @staticmethod
    def _get_protocol_icon(protocol: Optional[str]) -> str:
        """Get icon for protocol"""
        icons = {
            "usenet": "📡",
            "torrent": "🧲",
            None: "📡+🧲"
        }
        return icons.get(protocol, "📡+🧲")

    def clear_cache(self):
        """Clear all cached searches"""
        if not os.path.exists(self.cache_dir):
            print("Cache directory doesn't exist")
            return

        import shutil
        shutil.rmtree(self.cache_dir)
        os.makedirs(self.cache_dir)
        print("Cache cleared successfully")

    def _log_debug(self, message: str, context: str = ""):
        """Add debug message with timestamp"""
        if self.debug:
            timestamp = datetime.now().isoformat()
            self.debug_log.append({
                'timestamp': timestamp,
                'context': context,
                'message': message
            })
            print(f"[{timestamp}] {context}: {message}")

    async def show_debug_stats(self):
        """Display comprehensive debug statistics"""
        if not self.debug:
            return

        print("\n📊 Debug Statistics")
        print("═══════════════════")
        
        # Runtime stats
        runtime = datetime.now() - self.performance_stats['start_time'] if self.performance_stats['start_time'] else 0
        print(f"\n🕒 Runtime Statistics:")
        print(f"  Total runtime:    {runtime.total_seconds():.2f}s")
        print(f"  Total searches:   {self.performance_stats['total_searches']}")
        print(f"  Total grabs:      {self.performance_stats['total_grabs']}")
        
        # Cache stats
        cache_size = self._get_cache_size()
        print(f"\n💾 Cache Statistics:")
        print(f"  Cache hits:       {self.performance_stats['cache_hits']}")
        print(f"  Cache misses:     {self.performance_stats['cache_misses']}")
        print(f"  Hit ratio:        {self._calculate_cache_ratio():.1f}%")
        print(f"  Current size:     {cache_size/1024/1024:.1f}MB / {settings['CACHE_MAX_SIZE']/1024/1024:.1f}MB")
        print(f"  Entry count:      {len(self._get_cache_entries())} / {settings['CACHE_MAX_ENTRIES']}")
        print(f"  Max age:         {settings['CACHE_MAX_AGE']/3600:.1f} hours")
        
        # API stats
        print(f"\n🌐 API Statistics:")
        print(f"  Total requests:   {self.prowlarr.api_stats['requests']}")
        print(f"  Total errors:     {self.prowlarr.api_stats['errors']}")
        print(f"  Avg response:     {self.prowlarr.api_stats['avg_response_time']*1000:.1f}ms")
        
        # Memory usage
        import psutil
        process = psutil.Process()
        print(f"\n💻 Resource Usage:")
        print(f"  Memory usage:     {process.memory_info().rss / 1024 / 1024:.1f} MB")
        print(f"  CPU time:         {process.cpu_times().user:.1f}s")
        
        # Recent debug logs
        print("\n📝 Recent Debug Logs:")
        for log in self.debug_log[-5:]:
            print(f"  [{log['timestamp']}] {log['context']}: {log['message']}")

    def _calculate_cache_ratio(self) -> float:
        total = self.performance_stats['cache_hits'] + self.performance_stats['cache_misses']
        return (self.performance_stats['cache_hits'] / total * 100) if total > 0 else 0

    def _display_headless_results(self, results: List[Dict], search_id: int):
        """Display results summary in headless mode"""
        kind_icon = self._get_kind_icon(self.current_kind)
        proto_icon = self._get_protocol_icon(self.current_protocol)
        
        # Show condensed results listing
        print("\n📚 Results:")
        print("─" * 50)
        for i, result in enumerate(results, 1):
            size_str = "N/A"
            if result.get('size', 0) > 0:
                size = result.get('size', 0)
                if size > 1024**3:
                    size_str = f"{size/1024**3:.2f}GB"
                elif size > 1024**2:
                    size_str = f"{size/1024**2:.2f}MB"
                else:
                    size_str = f"{size/1024:.2f}KB"
                    
            protocol_icon = "📡" if result.get('protocol') == "usenet" else "🧲"
            print(f"{i:2d}. {protocol_icon} [{size_str}] {result['title']}")

        # Show summary
        print("\n" + "═" * 60)
        print("✨ Search Summary ✨")
        print("═" * 60)
        print(f"🔑 Search ID:  #{search_id}")
        print(f"🔍 Term:       {self.current_search}")
        print(f"🧩 Kind:       {kind_icon} {self.current_kind}")
        print(f"🔌 Protocol:   {proto_icon} {self.current_protocol or 'both'}")
        print(f"📊 Results:    {len(results)} items found")
        
        # Show protocol and indexer information
        protocols = []
        for p in set(r.get('protocol', 'unknown') for r in results):
            icon = "📡" if p == "usenet" else "🧲"
            protocols.append(f"{icon} {p}")
        print(f"🔗 Available:  {', '.join(sorted(protocols))}")
        print(f"🌐 Sites:      {', '.join(sorted(set(r.get('indexer', 'unknown') for r in results)))}")
        print("═" * 60)

        print("\n📝 To download a result, use:")
        print(f"bs -s {search_id} -g <result_number>")
        print("\n⏰ Results will be available for 7 days")
        print("═" * 60)

async def main():
    searcher = BookSearcher()
    await searcher.run()

if __name__ == "__main__":
    if len(sys.argv) > 0 and sys.argv[0].endswith('booksearcher.py'):
        asyncio.run(main())
