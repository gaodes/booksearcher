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

class CacheFullError(CacheError):
    """Raised when cache is full and cleanup failed"""
    pass

class CacheIOError(CacheError):
    """Raised when cache IO operations fail"""
    pass

class NetworkError(Exception):
    """Base exception for network related errors"""
    pass

class APIError(NetworkError):
    """Raised when API calls fail"""
    pass

class RetryExceededError(NetworkError):
    """Raised when maximum retries are exceeded"""
    pass

class PerformanceStats(TypedDict):
    start_time: Optional[datetime]
    total_searches: int
    total_grabs: int
    cache_hits: int
    cache_misses: int
    cache_cleanups: int
    cache_size: int
    cache_entries: int
    network_requests: int
    network_errors: int
    total_response_time: float

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
    
    # Add retry configuration
    MAX_RETRIES = 3
    RETRY_DELAY = 1  # Base delay in seconds
    
    # Add connection pool configuration
    POOL_SIZE = 10
    POOL_TIMEOUT = 30
    
    def __init__(self) -> None:
        """Initialize the BookSearcher with necessary components and settings."""
        self.cache_dir: str = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'cache')
        self.session: Optional[aiohttp.ClientSession] = None
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
            'cache_misses': 0,
            'cache_cleanups': 0,
            'cache_size': 0,
            'cache_entries': 0,
            'network_requests': 0,
            'network_errors': 0,
            'total_response_time': 0
        }
        self.current_search: Optional[str] = None
        self.current_kind: Optional[str] = None
        self.current_protocol: Optional[str] = None
        
        try:
            os.makedirs(self.cache_dir, exist_ok=True)
            # Run initial cache cleanup and stats update
            self._cleanup_cache()
            self._update_cache_stats()
        except OSError as e:
            raise CacheIOError(f"Failed to create cache directory: {str(e)}")

    async def _init_session(self) -> None:
        """Initialize connection pool"""
        if not self.session:
            connector = aiohttp.TCPConnector(
                limit=self.POOL_SIZE,
                ttl_dns_cache=300,  # Cache DNS results for 5 minutes
                enable_cleanup_closed=True
            )
            timeout = aiohttp.ClientTimeout(total=self.POOL_TIMEOUT)
            self.session = aiohttp.ClientSession(
                connector=connector,
                timeout=timeout,
                raise_for_status=True
            )

    async def _close_session(self) -> None:
        """Close connection pool"""
        if self.session:
            await self.session.close()
            self.session = None

    async def handle_error(self, error: Exception, context: str = "") -> None:
        """Enhanced error handling with specific error types and better context"""
        error_type = type(error).__name__
        error_msg = str(error)
        
        # Update last error state
        self.last_error = {
            'timestamp': datetime.now().isoformat(),
            'type': error_type,
            'message': error_msg,
            'context': context
        }
        
        # Log the error with context
        self._log_debug(f"Error in {context}: {error_type} - {error_msg}", "error")
        
        # Format user-facing error message based on error type
        if isinstance(error, CacheError):
            print(f"\n❌ Cache Error: {error_msg}")
            if isinstance(error, CacheFullError):
                print("💡 Tip: Try clearing the cache with --clear-cache")
        elif isinstance(error, NetworkError):
            print(f"\n❌ Network Error: {error_msg}")
            if isinstance(error, RetryExceededError):
                print("💡 Tip: Check your internet connection and try again")
            elif isinstance(error, APIError):
                print("💡 Tip: Verify your Prowlarr configuration and API key")
        else:
            print(f"\n❌ Error: {error_msg}")
        
        if self.debug:
            import traceback
            print("\n🔍 Debug Information:")
            print("─" * 40)
            print(f"Error Type: {error_type}")
            print(f"Context: {context}")
            print(f"Timestamp: {self.last_error['timestamp']}")
            print("\nTraceback:")
            print(traceback.format_exc())
            print("─" * 40)

    async def _retry_operation(self, operation, *args, **kwargs):
        """
        Retry an async operation with exponential backoff.
        
        Args:
            operation: Async function to retry
            *args: Positional arguments for the operation
            **kwargs: Keyword arguments for the operation
            
        Returns:
            The result of the successful operation
            
        Raises:
            RetryExceededError: If maximum retries are exceeded
        """
        last_error = None
        for attempt in range(self.MAX_RETRIES):
            try:
                return await operation(*args, **kwargs)
            except Exception as e:
                last_error = e
                if attempt < self.MAX_RETRIES - 1:
                    delay = self.RETRY_DELAY * (2 ** attempt)  # Exponential backoff
                    if self.debug:
                        self._log_debug(
                            f"Attempt {attempt + 1} failed: {str(e)}. "
                            f"Retrying in {delay}s...",
                            "retry"
                        )
                    await asyncio.sleep(delay)
                else:
                    break
        
        raise RetryExceededError(
            f"Operation failed after {self.MAX_RETRIES} attempts. "
            f"Last error: {str(last_error)}"
        )

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
        """Run the BookSearcher with connection pool management"""
        try:
            await self._init_session()
            self.performance_stats['start_time'] = datetime.now()
            
            parser = self.create_parser()
            args = parser.parse_args()
            
            self.debug = args.debug
            
            if self.debug:
                print("\n🔧 Debug Mode Enabled")
                print("──────────────────────")
                print(f"📂 Cache Dir: {self.cache_dir}")
                print(f"🔌 Prowlarr URL: {settings['PROWLARR_URL']}")
                print(f"⚙️  Cache Max Age: {settings['CACHE_MAX_AGE']}h")
                print(f"🌐 Pool Size: {self.POOL_SIZE}")
                print("──────────────────────\n")
            
            # Get tags silently first since we need them for searches
            self.tags = await self.prowlarr.get_tag_ids()

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

        finally:
            await self._close_session()

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
        Uses a more efficient algorithm with os.scandir().
        
        Returns:
            int: Total size of cache in bytes
        """
        total_size = 0
        try:
            for entry in os.scandir(self.cache_dir):
                if entry.is_file():
                    total_size += entry.stat().st_size
                elif entry.is_dir():
                    for root, _, files in os.walk(entry.path):
                        total_size += sum(os.path.getsize(os.path.join(root, name)) for name in files)
        except OSError as e:
            self._log_debug(f"Error calculating cache size: {e}", "cache")
            return 0
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

    def _update_cache_stats(self) -> None:
        """Update cache statistics"""
        try:
            self.performance_stats['cache_size'] = self._get_cache_size()
            self.performance_stats['cache_entries'] = len([
                d for d in os.listdir(self.cache_dir)
                if d.startswith('search_') and os.path.isdir(os.path.join(self.cache_dir, d))
            ])
        except OSError as e:
            self._log_debug(f"Error updating cache stats: {e}", "cache")

    def _cleanup_cache(self) -> None:
        """
        Clean up the cache directory based on size, entry limits, and age.
        Removes entries that exceed the maximum age first, then oldest accessed entries
        if still over limits.
        """
        try:
            entries = self._get_cache_entries()
            cleaned = False
            
            # First pass: Remove entries exceeding max age
            max_age = timedelta(hours=settings["CACHE_MAX_AGE"])
            now = datetime.now()
            
            entries = [
                entry for entry in entries
                if now - datetime.fromtimestamp(entry[2]) <= max_age
            ]
            
            # Second pass: Check entry count limit
            while len(entries) > settings["CACHE_MAX_ENTRIES"]:
                search_id, path, _ = entries.pop(0)  # Remove oldest
                self._remove_cache_entry(path)
                cleaned = True
                if self.debug:
                    self._log_debug(f"Removed cache entry {search_id} due to entry limit")

            # Third pass: Check size limit
            current_size = self._get_cache_size()
            while current_size > settings["CACHE_MAX_SIZE"] and entries:
                search_id, path, _ = entries.pop(0)  # Remove oldest
                current_size -= self._get_entry_size(path)
                self._remove_cache_entry(path)
                cleaned = True
                if self.debug:
                    self._log_debug(f"Removed cache entry {search_id} due to size limit")
            
            if cleaned:
                self.performance_stats['cache_cleanups'] += 1
                self._update_cache_stats()

        except Exception as e:
            self._log_debug(f"Cache cleanup error: {str(e)}", "cleanup")
            raise CacheError(f"Cache cleanup failed: {str(e)}")

    def _get_entry_size(self, path: str) -> int:
        """
        Get the size of a cache entry directory.
        
        Args:
            path: Path to the cache entry directory
            
        Returns:
            int: Size of the entry in bytes
        """
        try:
            total = 0
            for root, _, files in os.walk(path):
                total += sum(os.path.getsize(os.path.join(root, name)) for name in files)
            return total
        except OSError:
            return 0

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
        """Handle search operation with enhanced error handling"""
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

        except aiohttp.ClientError as e:
            await self.handle_error(APIError(f"Failed to connect to Prowlarr: {str(e)}"), "API Connection")
        except asyncio.TimeoutError:
            await self.handle_error(NetworkError("Request timed out"), "Network Timeout")
        except Exception as e:
            await self.handle_error(e, "Search operation")

    async def _handle_headless_search(self, args):
        """Handle headless search with retry mechanism"""
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

        if self.current_search:
            if self.debug:
                print(f"\n🔍 Executing search with:")
                print(f"  Term: {self.current_search}")
                print(f"  Tags: {tag_ids}")
                print(f"  Protocol: {protocol}")
            
            self.spinner.start()
            try:
                # Use retry mechanism for search
                results = await self._retry_operation(
                    self.prowlarr.search,
                    self.current_search,
                    tag_ids,
                    protocol
                )
            finally:
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

            # Save results with error handling
            try:
                search_id = self.get_next_search_id()
                self.save_search_results(
                    search_id,
                    results,
                    self.current_search,
                    args.kind or 'both',
                    protocol,
                    'headless'
                )
            except CacheError as e:
                await self.handle_error(e, "Cache Operation")
                return

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
        """
        Format a single result with detailed information and underlined title.
        Optimized for performance with string concatenation.
        """
        # Pre-calculate common values
        title = f"【{index}】{result['title']}"
        protocol = result.get('protocol', 'unknown')
        is_usenet = protocol == "usenet"
        
        # Calculate visual width efficiently
        visual_width = len(title)
        visual_width += title.count('【') + title.count('】')  # Add 1 for each bracket
        visual_width += sum(1 for c in title if ord(c) > 0x2E80)  # Add 1 for each CJK character
        
        # Build status string based on protocol
        if is_usenet:
            status = f"💫 {result.get('grabs', 0)} grabs"
        else:
            seeders = result.get('seeders', 0)
            status = f"🌱 {seeders} seeders" if seeders > 0 else "💀 Dead torrent"
        
        # Format size once
        size_str = self._format_result_size(result.get('size', 0))
        
        # Build output list with minimal string operations
        output = [
            title,
            "─" * visual_width,
            f"  📦 Size:          {size_str}",
            f"  📅 Published:     {result.get('publishDate', 'N/A')[:10]}", 
            f"  🔌 Protocol:      {'📡' if is_usenet else '🧲'} {protocol}", 
            f"  🔍 Indexer:       {result.get('indexer', 'N/A')}", 
            f"  ⚡ Status:        {status}",
            ""  # Empty line for spacing
        ]
        
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
        """Display search results with optimized formatting"""
        # Pre-format all results
        formatted_results = []
        for i, result in enumerate(results, 1):
            formatted_results.extend(self._format_result_line(i, result))
        
        # Display results in batches for better performance
        self._display_header("📚 Search Results Found 📚")
        
        BATCH_SIZE = 10
        for i in range(0, len(formatted_results), BATCH_SIZE):
            batch = formatted_results[i:i + BATCH_SIZE]
            print("\n".join(batch))
        
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
