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
    
    # Add these constants at the top of the BookSearcher class
    SEPARATOR_THIN = "─" * 80
    SEPARATOR_THICK = "═" * 80
    
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

    def _display_header(self, title: str) -> None:
        """Display a consistent header with title"""
        print(f"\n{title}")
        print(self.SEPARATOR_THICK)

    def _display_section(self, title: str) -> None:
        """Display a consistent section header"""
        print(f"\n{title}")
        print(self.SEPARATOR_THIN)

    def _prompt_user(self, prompt: str, choices: List[str] = None, allow_empty: bool = False) -> str:
        """Unified method for user prompts"""
        while True:
            user_input = input(f"\n{prompt} > ").strip()
            
            if user_input.lower() == 'q':
                sys.exit(0)
            
            if not user_input and not allow_empty:
                print("\n❌ Input cannot be empty. Please try again or type 'q' to quit.")
                continue
                
            if choices and user_input not in choices:
                print(f"\n❌ Please choose from: {', '.join(choices)}")
                continue
                
            return user_input

    def _display_instructions(self, command: str, description: str) -> None:
        """Display unified command instructions"""
        print(f"\n📝 {description}:")
        print(f"bs {command}")

    def show_media_type_menu(self) -> tuple[List[int], str, str]:
        """Interactive media type selection with unified formatting"""
        self._display_header("📚 Welcome to BookSearcher! 📚")
        
        print("\nChoose what type of books you're looking for:")
        print("\n1) 🎧 Audiobooks")
        print("   Perfect for listening while commuting or doing other activities")
        print("\n2) 📚 eBooks")
        print("   Digital books for your e-reader or tablet")
        print("\n3) 🎧+📚 Both Formats")
        print("   Search for both audiobooks and ebooks simultaneously")
        print("\n❌ Type 'q' to quit")
        
        choice = self._prompt_user("✨ Your choice", ['1', '2', '3'])
        
        choices = {
            '1': ([self.tags['audiobooks']], "Audiobooks", "🎧"),
            '2': ([self.tags['ebooks']], "eBook", "📚"),
            '3': ([self.tags['audiobooks'], self.tags['ebooks']], "Audiobooks & eBooks", "🎧+📚")
        }
        
        return choices[choice]

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
        """Handle search operation with unified interaction"""
        try:
            # Handle headless mode
            if args.headless and args.search_term:
                await self._handle_headless_search(args)
                return

            # Interactive mode without arguments
            if not args.search_term and not args.search and not args.grab:
                await self._handle_interactive_search()
                return

            # Normal search with arguments
            await self._handle_normal_search(args)

        except Exception as e:
            await self.handle_error(e, "Search operation")

    async def _handle_headless_search(self, args):
        """Handle headless search with unified formatting"""
        # Store current search parameters
        self.current_search = ' '.join(args.search_term)
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
        if self.current_search:
            if self.debug:
                print(f"\n🔍 Executing search with:")
                print(f"  Term: {self.current_search}")
                print(f"  Tags: {tag_ids}")
                print(f"  Protocol: {protocol}")
            
            # Always show spinner during search
            self.spinner.start()
            results = await self.prowlarr.search(self.current_search, tag_ids, protocol)
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
                self.current_search,
                args.kind or 'both',
                protocol,
                'headless'
            )

            await self.display_results(results, search_id, True)

    async def _handle_interactive_search(self):
        """Handle interactive search with unified formatting"""
        # Get media type from menu
        tag_ids, kind, icon = self.show_media_type_menu()
        
        # Get search term
        self._display_section("🔍 Enter Your Search Term")
        print("✨ You can search by:")
        print("  📝 Book title (e.g., 'The Great Gatsby')")
        print("  👤 Author name (e.g., 'Stephen King')")
        print("  📚 Series name (e.g., 'Harry Potter')")
        print("\n❌ Type 'q' to quit")
        
        search_term = self._prompt_user("🔎 Search")

        # Show searching animation
        self._display_section("🔍 Searching through multiple sources...")
        self.spinner.start()
        results = await self.prowlarr.search(search_term, tag_ids, None)
        self.spinner.stop()

        if not results:
            print("\n❌ No results found")
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

    async def _handle_normal_search(self, args):
        """Handle normal search with arguments"""
        try:
            # Store current search parameters
            self.current_search = ' '.join(args.search_term)
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
            if self.current_search:
                if self.debug:
                    print(f"\n🔍 Executing search with:")
                    print(f"  Term: {self.current_search}")
                    print(f"  Tags: {tag_ids}")
                    print(f"  Protocol: {protocol}")
                
                # Always show spinner during search
                self.spinner.start()
                results = await self.prowlarr.search(self.current_search, tag_ids, protocol)
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
                    self.current_search,
                    args.kind or 'both',
                    protocol,
                    'headless' if args.headless else 'interactive'
                )

                await self.display_results(results, search_id, args.headless)

        except Exception as e:
            await self.handle_error(e, "Search operation")

    async def handle_grab(self, search_id: int, result_num: int):
        """Handle grab operation"""
        try:
            if self.debug:
                print(f"\n🔍 Grab Operation:")
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

    def _format_result_size(self, size: int) -> str:
        """Format size in bytes to human readable format"""
        if size == 0:
            return "N/A"
        if size > 1024**3:
            return f"{size/1024**3:.2f}GB"
        elif size > 1024**2:
            return f"{size/1024**2:.2f}MB"
        return f"{size/1024:.2f}KB"

    def _format_result_line(self, index: int, result: Dict) -> List[str]:
        """Format a single result with detailed information and underlined title"""
        # Calculate title with index
        title = f"【{index}】{result['title']}"
        
        # Get status and icons
        protocol_icon = "📡" if result.get('protocol') == "usenet" else "🧲"
        status = f"💫 {result.get('grabs', 0)} grabs" if result.get('protocol') == "usenet" else \
                f"🌱 {result.get('seeders', 0)} seeders" if result.get('seeders', 0) > 0 else "💀 Dead torrent"
        
        # Format size
        size_str = self._format_result_size(result.get('size', 0))
        
        # Create the formatted output
        output = []
        output.append(title)
        
        # Calculate visual width for Unicode characters
        visual_width = len(title)
        # Add extra width for special Unicode characters
        visual_width += title.count('【') + title.count('】')  # Add 1 for each bracket
        visual_width += len([c for c in title if ord(c) > 0x2E80])  # Add 1 for each CJK character
        
        # Create underline with adjusted width
        output.append("─" * visual_width)
        
        # Add details with consistent formatting
        details = [
            f"📦 Size:          {size_str}",
            f"📅 Published:     {result.get('publishDate', 'N/A')[:10]}", 
            f"🔌 Protocol:      {protocol_icon} {result.get('protocol', 'N/A')}", 
            f"🔍 Indexer:       {result.get('indexer', 'N/A')}", 
            f"⚡ Status:        {status}"
        ]
        
        # Add each detail line with proper indentation
        for detail in details:
            output.append(f"  {detail}")
            
        output.append("")  # Add empty line for spacing
        return output

    def _display_search_summary(self, results: List[Dict], search_id: int) -> None:
        """Display detailed search summary with formatting"""
        kind_icon = self._get_kind_icon(self.current_kind)
        proto_icon = self._get_protocol_icon(self.current_protocol)
        
        # Calculate statistics
        protocols = {}
        indexers = set()
        for r in results:
            proto = r.get('protocol', 'unknown')
            protocols[proto] = protocols.get(proto, 0) + 1
            indexers.add(r.get('indexer', 'N/A'))
        
        print("\n" + self.SEPARATOR_THICK)
        print("✨ Search Summary ✨")
        print(self.SEPARATOR_THICK)
        
        # Search details
        if self.current_search:
            print(f"🔍 Search Term:   {self.current_search}")
            print(f"🧩 Media Type:    {kind_icon} {self.current_kind}")
            print(f"🔌 Protocol:      {proto_icon} {self.current_protocol or 'both'}")
        
        # Results statistics
        print(f"\n📊 Statistics")
        print(self.SEPARATOR_THIN)
        print(f"📚 Total Results: {len(results)} items")
        
        # Protocol breakdown
        print("\n🔗 Available Protocols:")
        for proto, count in protocols.items():
            icon = "📡" if proto == "usenet" else "🧲"
            print(f"  {icon} {proto}: {count} results")
        
        # Indexer information
        print("\n🌐 Sources:")
        for indexer in sorted(indexers):
            print(f"  • {indexer}")
        
        print(self.SEPARATOR_THICK)

    async def display_results(self, results: List[Dict], search_id: int, headless: bool = False, interactive: bool = True):
        """Display search results in a detailed, formatted view"""
        self._display_header("📚 Search Results Found 📚")
        
        # Display each result in detailed format
        for i, result in enumerate(results, 1):
            for line in self._format_result_line(i, result):
                print(line)
        
        # Show search summary
        self._display_search_summary(results, search_id)
        
        # Show usage instructions
        print("\n📝 Download Instructions")
        print(self.SEPARATOR_THIN)
        print(f"🔑 Search ID: #{search_id}")
        print(f"📥 Command:   bs -s {search_id} -g <result_number>")
        print("⏰ Note:      Results will be available for 7 days")
        print(self.SEPARATOR_THICK)

        if interactive and not headless:
            await self._handle_interactive_selection(results)

    def _display_headless_results(self, results: List[Dict], search_id: int):
        """Redirect to main display method for consistency"""
        return self.display_results(results, search_id, headless=True, interactive=False)

    async def _handle_interactive_selection(self, results: List[Dict]):
        """Handle interactive result selection with unified prompts"""
        while True:
            try:
                choice = self._prompt_user("Enter result number to download (or 'q' to quit)", 
                                         [str(i) for i in range(1, len(results) + 1)],
                                         allow_empty=True)
                
                if not choice:  # Empty input
                    continue
                    
                idx = int(choice) - 1
                selected = results[idx]
                await self.prowlarr.grab_release(selected['guid'], selected['indexerId'])
                
                # Show success message in a nice box
                success_msg = "✨ Successfully sent to download client! ✨"
                box_width = len(success_msg) + 4
                
                print("\n" + "┌" + "─" * (box_width-2) + "┐")
                print(f"│ {success_msg} │")
                print("└" + "─" * (box_width-2) + "┘")
                
                print(self.SEPARATOR_THIN)
                print(f"📥 Title:    {selected['title']}")
                print(f"📚 Kind:     {self._get_kind_icon(selected.get('kind', 'unknown'))} {selected.get('kind', 'unknown')}")
                print(f"🔌 Protocol: {self._get_protocol_icon(selected.get('protocol'))} {selected.get('protocol', 'N/A')}")
                print(f"🔍 Indexer:  {selected.get('indexer', 'N/A')}")
                print(self.SEPARATOR_THICK)
                
            except ValueError:
                print("\n❌ Please enter a valid number")
            except Exception as e:
                await self.handle_error(e, "Interactive selection")

    async def list_cached_searches(self):
        """List cached searches with unified formatting"""
        if not os.path.exists(self.cache_dir):
            print("\n❌ No cached searches found")
            return

        searches = self._get_cached_searches()
        if not searches:
            print("\n❌ No valid cached searches found")
            return

        self._display_header("📚 Cached Searches")
        
        for search in searches:
            print(f"\n[{search['id']}] {search['term']}")
            print(f"  🧩 Kind: {search['icon']} {search['kind']}")
            print(f"  ⏰ Age:  {search['age']}")

        self._display_instructions("--list-cache <search_id>", "To view details of a specific search, use")

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

    def _get_cached_searches(self) -> List[Dict]:
        """Get cached searches with unified formatting"""
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

        return searches

async def main():
    searcher = BookSearcher()
    await searcher.run()

if __name__ == "__main__":
    if len(sys.argv) > 0 and sys.argv[0].endswith('booksearcher.py'):
        asyncio.run(main())
