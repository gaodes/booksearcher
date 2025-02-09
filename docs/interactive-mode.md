# Interactive Mode Guide

The interactive mode in BookSearcher provides a user-friendly way to search for books and audiobooks. This guide will walk you through using the interactive features.

## Starting Interactive Mode

You can start interactive mode in two ways:
1. Simply run the script without arguments:
   ```bash
   ./booksearcher.sh
   ```
2. Explicitly use the interactive flag:
   ```bash
   ./booksearcher.sh -i
   ```

## Navigation Steps

### 1. Select Media Type
First, you'll be prompted to choose what type of media you want to search for:
```
Select Media Type:
1) 🎧 Audiobook
2) 📚 eBook
3) 🎧+📚 Both
q) Quit
```

### 2. Enter Search Term
Next, enter what you're looking for:
```
Enter Search Term (or 'q' to quit):
Examples: author name, book title, series
```

### 3. View Results
Results will be displayed with detailed information:
- Title of the book/audiobook
- File size
- Publication date
- Protocol (📡 Usenet or 🧲 Torrent)
- Indexer name
- Download stats (grabs for Usenet, seeders for torrents)

### 4. Take Action
After viewing results, you can:
- Enter a number to download that specific result
- Type 'q' to quit the search

## Features

- 🔍 Intuitive search interface
- 📚 Search for eBooks, audiobooks, or both
- 📡 Supports both Usenet and Torrent downloads
- 💾 Automatically saves search results for 7 days
- 🔢 Easy selection of items by number

## Tips

- Use specific search terms for better results
- Search results are cached and can be accessed later using the search ID
- Use `./booksearcher.sh --list-cache` to view recent searches
- Browse both eBooks and audiobooks simultaneously using option 3

## Example Session

```
$ ./booksearcher.sh

Select Media Type:
1) 🎧 Audiobook
2) 📚 eBook
3) 🎧+📚 Both
q) Quit
> 1

Enter Search Term (or 'q' to quit):
Examples: author name, book title, series
> Project Hail Mary

[1] Project Hail Mary by Andy Weir
─────────────────────────────────
📦 Size:         325MB
📅 Published:    2021-05-04
🔌 Protocol:     📡 Usenet
🔍 Indexer:      AudiobookBay
📥 Grabs:        1250

Actions:
• Number (1-1) to download
• 'q' to quit

> 1
✨ Successfully sent to download client!
```
