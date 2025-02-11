# 📚 BookSearcher

BookSearcher is a Python-based CLI tool that interfaces with Prowlarr to search for books across multiple indexers. It provides a convenient way to search for both eBooks and Audiobooks, with support for caching results and managing downloads.

## ✨ Features

- 🔍 Powerful search across multiple indexers via Prowlarr
- 📚 Support for both eBooks and Audiobooks
- 💾 Smart caching system for quick result retrieval
- 🎯 Interactive and headless mode for easly using it remotely
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

1. Create directories for configuration and cache:
```bash
mkdir -p booksearcher/cache && cd booksearcher
```

2. Create your environment file:
```bash
cat > .env << EOL
PROWLARR_URL=http://your-prowlarr-instance:9696
PROWLARR_API_KEY=your-api-key-here
EOL
```

3. Run the container with persistent cache:
```bash
docker run -d \
  --name booksearcher \
  --env-file .env \
  -v "$(pwd)/cache:/app/src/cache" \
  gaodes/booksearcher:latest
```

Or using Docker Compose:

```yaml
version: '3'
services:
  booksearcher:
    image: gaodes/booksearcher:latest
    container_name: booksearcher
    env_file:
      - .env
    volumes:
      - ./cache:/app/src/cache
    restart: unless-stopped
```

### Development Setup

If you want to contribute or modify the code:

1. Clone the repository:
```bash
git clone https://github.com/gaodes/booksearcher.git
cd booksearcher
```

2. Create `.env` file and modify for your environment:
```bash
cp .env.example .env
```

3. Build and run the development container:
```bash
docker-compose -f docker-compose.dev.yml up -d
```

## 🚀 Usage Guide

### Interactive Mode

1. Enter the container:

```bash
docker exec -it booksearcher /app/src/booksearcher.py
```

2. Follow the interactive menu:
   - Choose media type (Audiobooks/eBooks/Both)
   - Enter your search term
   - Browse through results
   - Select an item to download

### Command Line Mode

Search for books:

```bash
# Basic search
docker exec -it booksearcher /app/src/booksearcher.py "book title or author"

# Search for specific type
docker exec -it booksearcher /app/src/booksearcher.py -k audio "audiobook name"  # audiobooks only
docker exec -it booksearcher /app/src/booksearcher.py -k book "ebook name"       # ebooks only

# Filter by protocol
docker exec -it booksearcher /app/src/booksearcher.py -p tor "book name"   # torrents only
docker exec -it booksearcher /app/src/booksearcher.py -p nzb "book name"   # usenet only
```

### Managing Downloads

When you perform a search, you'll get a search ID. Use this to download items later:

```bash
# List recent searches
docker exec -it booksearcher /app/src/booksearcher.py --list-cache

# Download item #3 from search #42
docker exec -it booksearcher /app/src/booksearcher.py -s 42 -g 3

# Download from most recent search
docker exec -it booksearcher /app/src/booksearcher.py --search-last -g 2
```

### Additional Commands

```bash
# Enable debug output
docker exec -it booksearcher /app/src/booksearcher.py -d "search term"

# Clear search cache
docker exec -it booksearcher /app/src/booksearcher.py --clear-cache

# Show help
docker exec -it booksearcher /app/src/booksearcher.py --help
```

## 💾 Cache System

- 📂 Cache location: 
  - Inside container: `/app/src/cache`
  - Host machine: `./cache` (when using volume mount)
- ⏱️ Default cache duration: 7 days
- 🧹 Auto-cleanup of old cache entries
- 📊 Cache statistics in debug mode
- 💿 Persistent across container restarts when using volume mount

### Cache Directory Structure
```
cache/
├── searches/        # Stores search results
├── downloads/       # Download history
└── statistics.json  # Cache usage statistics
```

> 💡 **Tip**: Mount the cache directory as a volume to preserve your search history and downloads across container restarts

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
