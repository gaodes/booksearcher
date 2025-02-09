
get_protocol_icon() {
    case "$1" in
        "usenet") echo "📡" ;;
        "torrent") echo "🧲" ;;
        *) echo "📡 & 🧲" ;;
    esac
}

get_kind_icon() {
    case "$1" in
        "Audiobooks") echo "🎧" ;;
        "eBook") echo "📚" ;;
        *) echo "🎧+📚" ;;
    esac
}

show_spinner() {
    local pid=$1
    local delay=0.2
    local spinstr='|/-\'
    while ps a | awk '{print $1}' | grep -q "$pid"; do
        local temp=${spinstr#?}
        printf " %c " "$spinstr"
        local spinstr=$temp${spinstr%"$temp"}
        sleep $delay
        printf "\b\b\b"
    done
    printf "   \b\b\b"
}

show_usage() {
    echo "Usage: $0 [-d|--debug] [-p|--protocol type] [-i|--interactive] [-h|--headless -k kind] [search term]"
    echo "       $0 -s <search_id> -g <result_number>"
    echo
    echo "Options:"
    echo "  -d, --debug        Enable debug mode"
    echo "  -p, --protocol     Specify protocol type: tor, nzb (default: both)"
    echo "  -i, --interactive  Run in interactive mode (default without flags)"
    echo "  -h, --headless    Run in headless mode (requires -k and search term)"
    echo "  -k, --kind        Specify media kind (required with --headless)"
    echo "                    Values: audio, book"
    echo "  -s, --search      Specify search ID for grabbing results"
    echo "  -g, --grab        Grab specific result number (requires -s)"
    echo "  -ls              Use most recent search (alias for --latest)"
    echo
    echo "Media Kind Options:"
    echo "  audio             Search for audiobooks"
    echo "  book              Search for ebooks"
    echo
    echo "Protocol Options:"
    echo "  nzb              Search only Usenet indexers"
    echo "  tor              Search only Torrent indexers"
    echo "  (none)           Search both protocols (default)"
    echo
    echo "Examples:"
    echo "  $0 -i                           # Interactive mode"
    echo "  $0 -h -k audio \"Book Name\"     # Headless mode, search for audiobook"
    echo "  $0 -h -k book -p nzb \"Book\"    # Headless mode, ebook, usenet only"
    echo "  $0 -p tor \"Book Name\"          # Interactive mode with torrent only"
    echo "  $0 -s 1 -g 5               # Grab result #5 from search #1"
    echo "  $0 --latest -g 5          # Grab from most recent search"
    echo
    echo "Cache Management:"
    echo "  --list-cache     List all cached searches"
    echo "  --clear-cache    Clear all cached searches"
}

quit_script() {
    echo "Exiting script..."
    exit 0
}
