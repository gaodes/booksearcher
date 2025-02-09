#!/bin/bash

# Get script and base directories
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_DIR="$(dirname "$SCRIPT_DIR")"
CACHE_DIR="$BASE_DIR/cache"
LIB_DIR="$SCRIPT_DIR/lib"
CONFIG_DIR="$BASE_DIR/config"

# Source configuration and library files
source "$CONFIG_DIR/settings.conf"
source "$LIB_DIR/api.sh"
source "$LIB_DIR/cache.sh"
source "$LIB_DIR/ui.sh"
source "$LIB_DIR/validation.sh"

# Check if jq is installed
if ! command -v jq &> /dev/null; then
    echo "Error: jq is required but not installed."
    exit 1
fi

# Validate Prowlarr URL
if [[ ! "$PROWLARR_URL" =~ ^https?:// ]]; then
    echo "Error: Invalid Prowlarr URL. Must start with http:// or https://"
    exit 1
fi

# Parse command line arguments
DEBUG=false
PROTOCOL_PROMPT=false
MEDIA_TYPE_FLAG=""
DIRECT_SEARCH=""
PROTOCOL=""
INTERACTIVE=false
HEADLESS=false
KIND=""

# Add new variables to argument parsing section
SEARCH_ID=""
GRAB_NUMBER=""

# Get all arguments after flags as search term
while [[ $# -gt 0 ]]; do
    case $1 in
        -d|--debug)
            DEBUG=true
            shift
            ;;
        -p|--protocol)
            if [[ -n "$2" && "$2" =~ ^(tor|nzb)$ ]]; then
                PROTOCOL=$([ "$2" = "tor" ] && echo "torrent" || echo "usenet")
                shift 2
            else
                echo "Error: -p|--protocol requires 'tor' or 'nzb' as argument"
                show_usage
            fi
            ;;
        -i|--interactive)
            INTERACTIVE=true
            shift
            ;;
        -h|--headless)
            HEADLESS=true
            shift
            ;;
        -k|--kind)
            if [[ -n "$2" && "$2" =~ ^(audio|book)$ ]]; then
                KIND="$2"
                shift 2
            else
                echo "Error: -k|--kind requires 'audio' or 'book' as argument"
                show_usage
            fi
            ;;
        --usenet)
            echo "Warning: --usenet is deprecated, use -p nzb instead"
            PROTOCOL="usenet"
            shift
            ;;
        --torrent)
            echo "Warning: --torrent is deprecated, use -p tor instead"
            PROTOCOL="torrent"
            shift
            ;;
        -a|--audio)
            MEDIA_TYPE_FLAG="audio"
            shift
            ;;
        -b|--book)
            MEDIA_TYPE_FLAG="book"
            shift
            ;;
        -s|--search)
            if [[ -n "$2" && "$2" =~ ^[0-9]+$ ]]; then
                SEARCH_ID="$2"
                shift 2
            else
                echo "Error: -s|--search requires a numeric search ID"
                show_usage
            fi
            ;;
        -g|--grab)
            if [[ -n "$2" && "$2" =~ ^[0-9]+$ ]]; then
                GRAB_NUMBER="$2"
                shift 2
            else
                echo "Error: -g|--grab requires a numeric result number"
                show_usage
            fi
            ;;
        --list-cache)
            list_cached_searches
            exit 0
            ;;
        --clear-cache)
            clear_cache
            exit 0
            ;;
        -ls|--latest)
            latest_dir=$(ls -td "$CACHE_DIR"/search_* 2>/dev/null | head -n1)
            if [ -n "$latest_dir" ]; then
                SEARCH_ID=$(basename "$latest_dir" | sed 's/search_//')
                echo "Using most recent search #$SEARCH_ID"
            else
                echo "No recent searches found"
                exit 1
            fi
            shift
            ;;
        --latest)
            latest_meta=$(ls -t "$CACHE_DIR"/search_*.meta 2>/dev/null | head -n1)
            if [ -n "$latest_meta" ]; then
                SEARCH_ID=$(basename "$latest_meta" | sed 's/search_\([0-9]*\).meta/\1/')
                echo "Using most recent search #$SEARCH_ID"
            else
                echo "No recent searches found"
                exit 1
            fi
            shift
            ;;
        -*)
            echo "Unknown option: $1"
            show_usage
            ;;
        *)
            # If there's no DIRECT_SEARCH yet, start collecting it
            if [ -z "$DIRECT_SEARCH" ]; then
                DIRECT_SEARCH="$1"
            else
                DIRECT_SEARCH="$DIRECT_SEARCH $1"
            fi
            shift
            ;;
    esac
done

# Validate headless mode requirements
if [ "$HEADLESS" = true ]; then
    if [ -z "$KIND" ]; then
        echo "Error: Headless mode requires -k|--kind flag"
        show_usage
    fi
    if [ -z "$DIRECT_SEARCH" ]; then
        echo "Error: Headless mode requires a search term"
        show_usage
    fi
    # Set media type flag based on kind
    MEDIA_TYPE_FLAG="$KIND"
fi

# Debug information if enabled
if [ "$DEBUG" = "true" ]; then
    echo "DEBUG: Direct search term: '$DIRECT_SEARCH'"
    echo "DEBUG: Media type flag: $MEDIA_TYPE_FLAG"
    echo "DEBUG: Protocol prompt: $PROTOCOL_PROMPT"
    echo "DEBUG: Protocol: ${PROTOCOL:-both}"
    echo "DEBUG: Mode: $([ "$HEADLESS" = true ] && echo "headless" || echo "interactive")"
    echo "DEBUG: Kind: $KIND"
fi

# Get tag IDs
TAG_IDS=$(get_tag_ids)
if [ $? -ne 0 ]; then
    exit 1
fi
AUDIOBOOKS_TAG_ID=$(echo "$TAG_IDS" | awk '{print $1}')
EBOOKS_TAG_ID=$(echo "$TAG_IDS" | awk '{print $2}')

# Validate tag IDs
validate_tag_id "$AUDIOBOOKS_TAG_ID" || exit 1
validate_tag_id "$EBOOKS_TAG_ID" || exit 1

# Add validation after argument parsing
if [ -n "$GRAB_NUMBER" ]; then
    if [ -z "$SEARCH_ID" ]; then
        echo "Error: -g|--grab requires -s|--search to specify which search to use"
        exit 1
    fi
    
    # Load cache files and metadata
    search_dir="$CACHE_DIR/search_${SEARCH_ID}"
    meta_file="$search_dir/meta"
    if [ ! -f "$meta_file" ]; then
        echo "Error: Search #${SEARCH_ID} metadata not found"
        exit 1
    fi
    
    # Load metadata
    source "$meta_file"
    cached_results=$(cat "$search_dir/results.json")
    
    # Get icons for display
    kind_icon=$(get_kind_icon "$MEDIA_KIND")
    proto_icon=$(get_protocol_icon "$PROTOCOL")
    
    # Show detailed search context
    echo "────────────────────────────────────"
    echo "🔢 Search #$SEARCH_ID"
    echo "🔍 Term: ${SEARCH_TERM}"
    echo "🧩 Kind: $kind_icon ${MEDIA_KIND}"
    echo "🔌 Protocol: $proto_icon ${PROTOCOL:-both}"
    echo "⏰ When: ${TIMESTAMP}"
    echo "🎮 Mode: ${MODE}"
    echo "────────────────────────────────────"
    echo
    
    release_data=$(echo "$cached_results" | jq -r --arg num "$GRAB_NUMBER" '.[$num|tonumber - 1]')
    if [ "$release_data" = "null" ]; then
        echo "Error: Result #$GRAB_NUMBER not found in search #$SEARCH_ID"
        exit 1
    fi
    
    # Grab the release
    grab_release "$release_data"
    exit 0
fi

# Ensure cache directory exists
if [ ! -d "$CACHE_DIR" ]; then
    mkdir -p "$CACHE_DIR"
fi

# Cleanup old cache entries
cleanup_cache

# Modified media type selection logic
if [ -n "$DIRECT_SEARCH" ]; then
    # If we have a direct search but no media flag, ask for media type
    if [ -z "$MEDIA_TYPE_FLAG" ]; then
        while true; do
            echo
            echo "Select Media Type for '$DIRECT_SEARCH':"
            echo "1) 🎧 Audiobook"
            echo "2) 📚 eBook"
            echo "3) 🎧+📚 Both"
            echo "q) Quit"
            read -r -p "> " media_choice
            case $media_choice in
                1)
                    MEDIA_TAG="$AUDIOBOOKS_TAG_ID"
                    MEDIA_KIND="Audiobooks"    # Changed from MEDIA_TYPE
                    MEDIA_ICON="🎧"
                    break
                    ;;
                2)
                    MEDIA_TAG="$EBOOKS_TAG_ID"
                    MEDIA_KIND="eBook"         # Changed from MEDIA_TYPE
                    MEDIA_ICON="📚"
                    break
                    ;;
                3)
                    MEDIA_TAG=("$AUDIOBOOKS_TAG_ID" "$EBOOKS_TAG_ID")
                    MEDIA_KIND="Audiobooks & eBooks"
                    MEDIA_ICON="🎧+📚"
                    break
                    ;;
                q|Q)
                    quit_script
                    ;;
                *)
                    echo "Invalid selection. Please choose 1, 2, 3, or q to quit."
                    ;;
            esac
        done
    else
        # Use the media type flag that was provided
        if [ "$MEDIA_TYPE_FLAG" = "audio" ]; then
            MEDIA_TAG="$AUDIOBOOKS_TAG_ID"
            MEDIA_KIND="Audiobooks"    # Changed from MEDIA_TYPE
            MEDIA_ICON="🎧"
        elif [ "$MEDIA_TYPE_FLAG" = "book" ]; then
            MEDIA_TAG="$EBOOKS_TAG_ID"
            MEDIA_KIND="eBook"         # Changed from MEDIA_TYPE
            MEDIA_ICON="📚"
        fi
    fi
    SEARCH_INPUT="$DIRECT_SEARCH"
else
    # Interactive mode - no direct search or media flag
    while true; do
        echo
        echo "Select Media Type:"
        echo "1) 🎧 Audiobook"
        echo "2) 📚 eBook"
        echo "3) 🎧+📚 Both"
        echo "q) Quit"
        read -r -p "> " media_choice
        case $media_choice in
            1)
                MEDIA_TAG="$AUDIOBOOKS_TAG_ID"
                MEDIA_KIND="Audiobooks"    # Changed from MEDIA_TYPE
                MEDIA_ICON="🎧"
                break
                ;;
            2)
                MEDIA_TAG="$EBOOKS_TAG_ID"
                MEDIA_KIND="eBook"         # Changed from MEDIA_TYPE
                MEDIA_ICON="📚"
                break
                ;;
            3)
                MEDIA_TAG=("$AUDIOBOOKS_TAG_ID" "$EBOOKS_TAG_ID")
                MEDIA_KIND="Audiobooks & eBooks"
                MEDIA_ICON="🎧+📚"
                break
                ;;
            q|Q)
                quit_script
                ;;
            *)
                echo "Invalid selection. Please choose 1, 2, 3, or q to quit."
                ;;
        esac
    done
fi

# Protocol selection - only show if -p flag was used
PROTOCOL_TYPE="📡 Usenet & 🧲 Torrent"  # Default text changed

if [ "$PROTOCOL_PROMPT" = "true" ]; then
    protocol_result=$(select_protocol "$PROTOCOL_PROMPT")
    PROTOCOL=$(echo "$protocol_result" | cut -d: -f1)
    PROTOCOL_TYPE=$(echo "$protocol_result" | cut -d: -f2)
fi

# Display the number of indexers being queried
if [ -n "$PROTOCOL" ]; then
    PROTOCOL_TYPE="📡 Usenet"
    if [ "$PROTOCOL" == "torrent" ]; then
        PROTOCOL_TYPE="🧲 Torrent"
    fi
fi

# Get search term - either from argument or user input
if [ -n "$DIRECT_SEARCH" ]; then
    SEARCH_INPUT="$DIRECT_SEARCH"
else
    while true; do
        echo
        echo "Enter Search Term (or 'q' to quit):"
        echo "Examples: author name, book title, series"
        read -r -p "> " SEARCH_INPUT
        case $SEARCH_INPUT in
            q|Q)
                quit_script
                ;;
            "")
                echo "⚠️  Search term required"
                ;;
            *)
                break
                ;;
        esac
    done
fi

# Get search term display
echo
echo "🔍 '$SEARCH_INPUT'"
if [[ "$MEDIA_KIND" == "Audiobooks & eBooks" ]]; then
    echo "Searching both: 🎧 Audiobooks & 📚 eBooks ┃ $PROTOCOL_TYPE"
else
    echo "$MEDIA_ICON $MEDIA_KIND ┃ $PROTOCOL_TYPE"
fi

# URL encode the search term
SEARCH_TERM=$(echo "$SEARCH_INPUT" | sed 's/ /%20/g')

# Get indexers tagged with selected media type and protocol
indexers=$(curl -s -H "X-Api-Key: $API_KEY" "$PROWLARR_URL/api/v1/indexer")
if [ $? -ne 0 ]; then
    echo "Error: Failed to get indexers list"
    exit 1
fi

if [ "$DEBUG" = "true" ]; then
    echo "DEBUG: All indexers and their tags:"
    echo "$indexers" | jq -r '.[] | "Name: \(.name), Protocol: \(.protocol), Tags: \(.tags), Enabled: \(.enable), ID: \(.id)"'
fi

# Extract IDs of indexers tagged with selected media type and matching protocol
indexer_ids=$(echo "$indexers" | jq -r --arg tags "${MEDIA_TAG[*]}" --arg proto "$PROTOCOL" '
    .[] | 
    select(.enable == true) |
    select(any(.tags[]; . as $tag | ($tags | split(" ") | map(tonumber) | contains([$tag|tonumber])))) |
    select($proto == "" or (.protocol|ascii_downcase) == ($proto|ascii_downcase)) |
    .id
')

# Count the number of indexers
num_indexers=$(echo "$indexer_ids" | wc -l)

if [ "$DEBUG" = "true" ]; then
    echo "DEBUG: Looking for indexers with:"
    echo "- Tag ID: $MEDIA_TAG"
    echo "- Protocol: ${PROTOCOL:-both}"
    echo "Selected indexers:"
    echo "$indexers" | jq -r --arg tag "$MEDIA_TAG" --arg proto "$PROTOCOL" '
        .[] | 
        select(.enable == true) |
        select(.tags[] | contains($tag|tonumber)) |
        select($proto == "" or (.protocol|ascii_downcase) == ($proto|ascii_downcase)) |
        "- \(.name) (Protocol: \(.protocol), Tags: \(.tags), ID: \(.id))"
    '
fi

if [ -z "$indexer_ids" ]; then
    echo "Error: No enabled indexers found with ${MEDIA_KIND,,} tag (ID: $MEDIA_TAG) and protocol ${PROTOCOL:-any}"
    exit 1
fi

# Display the number of indexers being queried
echo "Querying $num_indexers indexers..."
echo "────────────────────────────────────"

# Build the search URL
SEARCH_URL="$PROWLARR_URL/api/v1/search"
QUERY_PARAMS="query=$SEARCH_TERM&type=search&limit=100&offset=0"

# Construct final URL
SEARCH_URL="${SEARCH_URL}?${QUERY_PARAMS}"
if [ "$DEBUG" = "true" ]; then
    echo "DEBUG: Search parameters:"
    echo "- Query: $SEARCH_TERM"
    echo "- Tag being used: $MEDIA_TAG (${MEDIA_KIND}s)"
    echo "- Selected indexer IDs: $indexer_ids"
    echo "- Protocol: ${PROTOCOL:-both}"
    echo "DEBUG: Full URL: $SEARCH_URL"
fi

# Make the API request with better error handling
if ! response=$(curl -s -m 30 -H "X-Api-Key: $API_KEY" -H "Accept: application/json" "$SEARCH_URL"); then
    echo "Error: Failed to connect to Prowlarr"
    exit 1
fi

if [ -z "$response" ]; then
    echo "Error: Empty response from Prowlarr"
    exit 1
fi

# Make API request with spinner
response=$(make_api_call "$SEARCH_URL") &
show_spinner $!

if [ -z "$response" ]; then
    echo "Error: No response from Prowlarr"
    exit 1
fi

# Check if the API request was successful and look for error messages
if [ "$DEBUG" = "true" ]; then
    echo "DEBUG: Raw response:"
    echo "$response" | jq '.'
    echo "DEBUG: Search URL:"
    echo "$SEARCH_URL"
fi

# Check if response is an error message
if echo "$response" | jq -e 'type == "object" and (has("error") or has("errors"))' >/dev/null; then
    echo "Error from Prowlarr:"
    echo "$response" | jq -r '.errors // .error // "Unknown error"'
    exit 1
fi

# Parse and display results
PROWLARR_URL_ESC=$(printf '%s\n' "$PROWLARR_URL" | sed 's/[&/\]/\\&/g')
echo "Search Results:"
echo "=============="
echo

# Store results in JSON format
echo "$response" | jq -r --arg url "$PROWLARR_URL_ESC" --arg key "$API_KEY" --arg proto "$PROTOCOL" '
  def formatSize(bytes):
    def _format(value):
      if value < 10 then (value * 100 | floor) / 100
      elif value < 100 then (value * 10 | floor) / 10
      else value | floor
      end;
    
    if bytes == 0 or bytes == null then "N/A"
    elif bytes < 1024 then "\(_format(bytes))B"
    elif bytes < 1024*1024 then "\(_format(bytes/1024))KB"
    elif bytes < 1024*1024*1024 then "\(_format(bytes/1024/1024))MB"
    elif bytes < 1024*1024*1024*1024 then "\(_format(bytes/1024/1024/1024))GB"
    else "\(_format(bytes/1024/1024/1024/1024))TB"
    end;
  
  def formatGrabs(entry):
    if entry.protocol == "usenet" then
      if entry.grabs == null then "0" else "\(entry.grabs)" end
    else
      if entry.seeders == null then "No seeders"
      elif entry.seeders == 0 then "Dead torrent"
      else "🌱 \(entry.seeders) seeders"
      end
    end;
  
  def protocolIcon(protocol):
    if protocol == "usenet" then "📡"
    else "🧲"
    end;
  
  def makeSeparator(str):
    reduce range(0; str|length) as $i (""; . + "─");
  
  if type == "array" then
    . | 
    map(select($proto == "" or (.protocol|ascii_downcase) == ($proto|ascii_downcase))) |
    sort_by(.size) | reverse | to_entries[] | 
    "[\(.key + 1)] \(.value.title)\n" +
    "\(makeSeparator("[\(.key + 1)] \(.value.title)"))\n" +
    "📦 Size:         \(formatSize(.value.size))\n" +
    "📅 Published:    \(.value.publishDate[:10] // "N/A")\n" +
    "🔌 Protocol:     \(protocolIcon(.value.protocol)) \(.value.protocol // "N/A")\n" +
    "🔍 Indexer:      \(.value.indexer)\n" +
    if .value.protocol == "usenet" then
    "📥 Grabs:        \(formatGrabs(.value))"
    else
    "⚡ Status:       \(formatGrabs(.value))"
    end +
    "\n\n"
  else
    "No valid results in response"
  end
'

# Store results parsing
titles=()
data=()
counter=1

# Process and store the results
while IFS= read -r line; do
    if [[ "$line" =~ ^[0-9]+\) ]]; then
        title="${line#*) }"
        titles[$counter]="$title"
    elif [[ "$line" == *"STORE:"* ]]; then
        data[$counter]="${line#*STORE: }"
        ((counter++))
    fi
done < <(echo "$response" | jq -r --arg url "$PROWLARR_URL_ESC" '
  if type == "array" then
    . | sort_by(.size) | reverse | to_entries[] |
    "\(.key + 1)) \(.value.title)\nSTORE: \(.value)"
  else
    empty
  end
')

# Store download clients globally
DOWNLOAD_CLIENTS=""

# Function to get download clients
get_download_clients() {
    DOWNLOAD_CLIENTS=$(curl -s \
         -H "X-Api-Key: $API_KEY" \
         "${PROWLARR_URL}/api/v1/downloadclient" | jq -r '[.[] | select(.enable==true)]')
}

# If no results found (modify to handle headless mode)
if [ "$response" == "[]" ]; then
    echo "────────────────────────────────────"
    echo "No results found for: $SEARCH_INPUT"
    echo "Possible reasons:"
    echo "• No matching indexers enabled"
    echo "• Incorrect search term"
    echo "────────────────────────────────────"
    if [ "$HEADLESS" = true ]; then
        exit 1
    fi
    while true; do
        read -r -p "Retry search? (y/n): " retry_choice
        case $retry_choice in
            [yY])
                $0 "$@"
                # Restart the script
                exit 0
                ;;
            [nN])
                exit 0
                ;;
            *)
                echo "Invalid choice. Please enter 'y' or 'n'."
                ;;
        esac
    done
fi

if [ ${#data[@]} -gt 0 ]; then
    get_download_clients
    search_id=$(get_next_search_id)
    # Store results for both interactive and headless modes
    mode=$([ "$HEADLESS" = true ] && echo "headless" || echo "interactive")
    save_search_results "$search_id" \
                      "$(echo "$response" | jq -c '.')" \
                      "$SEARCH_INPUT" \
                      "$MEDIA_KIND" \
                      "$PROTOCOL" \
                      "$mode"
    
    if [ "$HEADLESS" = true ]; then
        kind_icon=$(get_kind_icon "$MEDIA_KIND")
        proto_icon=$(get_protocol_icon "$PROTOCOL")
        echo
        echo "════════════════════════════════════"
        echo "     ✨ Search completed! ✨"
        echo "────────────────────────────────────"
        echo "🔢 Search ID: #$search_id"
        echo "🔍 Term: $SEARCH_INPUT"
        echo "🧩 Kind: $kind_icon $MEDIA_KIND"  # Changed from 📋 to 🧩
        echo "🔌 Protocol: $proto_icon ${PROTOCOL:-both}"
        echo
        echo "To download a result, use:"
        echo "./booksearcher.sh -s $search_id -g <result_number>"
        echo
        echo "Results will be available for 7 days"
        echo "════════════════════════════════════"
        exit 0
    else
        echo "────────────────────────────────────"
        echo "Search saved as #$search_id"
        echo "Actions:"
        echo "• Number (1-$((counter-1))) to download"
        echo "• 'q' to quit"
        echo
    fi
    while true; do
        printf "> "
        read -r choice
        case $choice in
            [0-9]*)
                if [ -n "${data[$choice]}" ]; then
                    release_data="${data[$choice]}"
                    grab_release "$release_data"
                else
                    echo "Invalid selection. Please try again."
                fi
                ;;
            q|Q)
                quit_script
                ;;
            *)
                echo "Invalid selection. Please try again."
                ;;
        esac
    done
fi
