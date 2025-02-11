# BookSearcher

BookSearcher is a Python-based tool that interfaces with Prowlarr to search for books across multiple indexers. It provides a convenient way to search and manage book downloads through a Docker container.

## Features

- Integration with Prowlarr for comprehensive book searching
- Caching system to store and quickly retrieve previous search results
- Support for multiple indexers through Prowlarr
- Docker containerization for easy deployment

## Requirements

### Prowlarr Setup
- A running instance of Prowlarr
- Prowlarr API key
- Properly configured download clients in Prowlarr
- Indexers with appropriate tags for book content

### System Requirements
- Docker
- Docker Compose (optional, but recommended)

## Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/booksearcher.git
cd booksearcher
```

2. Build the Docker image:
```bash
docker build -t booksearcher .
```

## Configuration

Create a `.env` file with the following variables:
```
PROWLARR_URL=http://your-prowlarr-instance:9696
PROWLARR_API_KEY=your-api-key-here
```

## Usage

### Running with Docker

```bash
docker run -d \
  --name booksearcher \
  --env-file .env \
  -v ./cache:/app/cache \
  booksearcher
```

### Using Docker Compose

```yaml
version: '3'
services:
  booksearcher:
    build: .
    environment:
      - PROWLARR_URL=http://your-prowlarr-instance:9696
      - PROWLARR_API_KEY=your-api-key-here
    volumes:
      - ./cache:/app/cache
```

Then run:
```bash
docker-compose up -d
```

## Cache System

The application maintains a local cache to store search results:
- Cache is stored in the `/app/cache` directory inside the container
- Results are cached for faster subsequent searches
- Cache can be cleared by removing files from the cache directory

## Prowlarr Setup Requirements

1. Ensure your Prowlarr instance has:
   - At least one configured download client
   - Book-specific indexers with appropriate tags
   - A valid API key with necessary permissions

2. Tag your book indexers appropriately:
   - Use consistent tags for book-related indexers
   - Ensure indexers support book/ebook formats

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

[Add your license information here]
