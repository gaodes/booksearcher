# 📚 BookSearcher

BookSearcher is a Python-based CLI tool that interfaces with Prowlarr to search for books across multiple indexers. It provides a convenient way to search for both eBooks and Audiobooks, with support for caching results and managing downloads.

## ✨ Features

- 🔍 Powerful search across multiple indexers via Prowlarr
- 📚 Support for both eBooks and Audiobooks
- 💾 Smart caching system for quick result retrieval
- 🎯 Interactive and headless mode for easily using it remotely
- 🐳 Docker containerization for easy deployment
- 📡 Support for both Usenet and Torrent protocols

## 🛠️ Requirements

### Prowlarr Configuration

1. 🏃‍♂️ A running instance of Prowlarr
2. 🔑 Prowlarr API key (Settings > General)
3. 📥 Configured download client (Transmission, qBittorrent, SABnzbd, etc.)
4. 🏷️ Indexers must be tagged properly:

   - Tag `audiobooks` for audiobook indexers
   - Tag `ebooks` for ebook indexers
   - Both tags for indexers supporting both types

> ⚠️ **Important**: Tag names must be exactly `audiobooks` and `ebooks` (lowercase)

### System Requirements

- 🐳 Docker
- 🔧 Docker Compose (recommended)

## 📦 Installation


### Quick Start with Docker

Run the container with persistent cache:

```bash
docker run -d \
  --name booksearcher \
  --network host \
  -v "$(pwd)/cache:/app/src/cache" \
  -e PROWLARR_URL=https://prowlarr.your.domain \
  -e API_KEY='YOUR PROWLARR API KEY' \
  -e CACHE_MAX_AGE=604800 \
  gaodes/booksearcher:latest
```

Or using Docker Compose:

```yaml
services:
  booksearcher:
    image: gaodes/booksearcher:latest
    container_name: booksearcher
    network_mode: host
    restart: unless-stopped
    environment:
      PROWLARR_URL: 'https://prowlarr.your.domain # or ip'
      API_KEY: 'YOUR PROWLARR API KEY'
      CACHE_MAX_AGE: 604800
    volumes:
      - ./cache:/app/src/cache
```

Save the above as `docker-compose.yml` and run:

```bash
# Start the container
docker compose up -d

# View logs
docker compose logs -f

# Stop the container
docker compose down
```

## 🚀 Usage Guide

### Operation Modes

BookSearcher operates in two modes:

1. **Interactive Mode** (Default)

   - Full interactive interface with menus and prompts
   - Rich formatting and detailed result display
   - Step-by-step guidance through the search process
   - Continuous download prompt after results
   - Best for direct usage and exploration
2. **Headless Mode** (`-x, --headless`)

   - Minimal output suitable for scripts and automation
   - Single-line results format
   - No interactive prompts
   - Returns search ID for later use
   - Perfect for scripting and remote usage

### Interactive Mode (Default)

Simply run without any flags:

```bash
docker exec -it booksearcher bs
```

Follow the interactive menu:

- Choose media type (Audiobooks/eBooks/Both)
- Enter your search term
- Browse through results
- Select an item to download

### Headless Mode

Search for books:

```bash
# Headless search (no interactive prompts)
docker exec -it booksearcher bs --headless "book name"
```

When running in headless mode, the output will show a search ID and instructions. You can then grab a specific result:

```bash
# Format: bs -s <search_id> -g <result_number>
docker exec -it booksearcher bs -s 42 -g 1  # Grab first result from search #42

# Quick grab from last search
docker exec -it booksearcher bs --search-last -g 1  # Grab first result from most recent search
```

### Managing Downloads

When you perform a search, you'll get a search ID. Use this to download items later:

```bash
# List recent searches
docker exec -it booksearcher bs --list-cache

# Download item #3 from search #42
docker exec -it booksearcher bs -s 42 -g 3

# Download from most recent search
docker exec -it booksearcher bs -sl -g 2
```

### Additional Commands

```bash
# Enable debug output
docker exec -it booksearcher bs -d "search term"

# Clear search cache
docker exec -it booksearcher bs --clear-cache

# Show help
docker exec -it booksearcher bs --help
```

## 📝 Command Reference

Available commands and flags for `bs` (booksearcher):

### Search Flags

| Flag(s)                        | Description                                 |
| ------------------------------ | ------------------------------------------- |
| `-k, --kind {audio,book,both}` | Specify media type to search for            |
| `-p, --protocol {tor,nzb}`     | Filter results by protocol (torrent/usenet) |
| `-x, --headless`               | Run in non-interactive mode                 |
| `-d, --debug`                  | Enable debug output                         |

### Cache Management

| Flag(s)               | Description                      |
| --------------------- | -------------------------------- |
| `-s, --search <ID>`   | Specify a search ID to work with |
| `-g, --grab <number>` | Download specific result number  |
| `-sl, --search-last`  | Use most recent search           |
| `--list-cache`        | Show all cached searches         |
| `--clear-cache`       | Delete all cached searches       |

## 💾 Cache System

- 📂 Cache location:
    - Inside container: `/app/src/cache`
    - Host machine: `./cache` (when using volume mount)
- ⏱️ Default cache duration: 7 days
- 🧹 Auto-cleanup of old cache entries
- 📊 Cache statistics in debug mode
- 💿 Persistent across container restarts when using volume mount

> 💡 **Tip**: Mount the cache directory as a volume to preserve your search history across container restarts

## 🐛 Troubleshooting

Common issues and solutions:

1. **Can't connect to Prowlarr**

   - Verify PROWLARR_URL is accessible from container
   - Check API key is correct
   - Ensure Prowlarr is running
2. **No results found**

   - Verify indexers are properly tagged
   - Check indexer health in Prowlarr
   - Try different search terms
3. **Download not starting**

   - Check download client configuration in Prowlarr
   - Verify download client is running
   - Check Prowlarr logs for errors

## 🤝 Contributing

Contributions welcome! Please:

1. Fork the repository
2. Create your feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## 📞 Support

- 📝 Open an issue for bugs
- 💡 Feature requests welcome
- 🌟 Star the repo if you find it useful!