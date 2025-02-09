# Headless Mode

Headless mode allows you to run the book searcher without a graphical user interface, making it suitable for automated scripts and server environments.

## Enabling Headless Mode

To enable headless mode, use the `--headless` flag when running the application:

```bash
booksearcher --headless
```

## Configuration

Headless mode accepts the following command-line arguments:

- `--input-file <path>`: Path to a text file containing search queries (one per line)
- `--output-dir <path>`: Directory where search results will be saved
- `--format <json|csv>`: Output format for search results (default: json)
- `--timeout <seconds>`: Maximum time to wait for each search (default: 30)

## Example Usage

```bash
booksearcher --headless --input-file queries.txt --output-dir results --format csv
```

## Output Format

### JSON Format
Results are saved as individual JSON files with the following structure:
```json
{
  "query": "search term",
  "timestamp": "2023-01-01T00:00:00Z",
  "results": [
    {
      "title": "Book Title",
      "author": "Author Name",
      "url": "https://example.com/book"
    }
  ]
}
```

### CSV Format
Results are combined into a single CSV file with columns: query, timestamp, title, author, url
