
cleanup_cache() {
    find "$CACHE_DIR" -type d -name "search_*" -mtime +7 -exec rm -rf {} \;
}

clear_cache() {
    echo "Clearing cache directory..."
    rm -rf "$CACHE_DIR"/search_*
    rm -f "$CACHE_DIR"/last_id
    echo "Cache cleared."
}

get_next_search_id() {
    local current_id=0
    local id_file="$CACHE_DIR/last_id"
    
    if [ -f "$id_file" ]; then
        current_id=$(cat "$id_file")
    fi
    
    current_id=$(( (current_id + 1) % 1000 ))
    echo "$current_id" > "$id_file"
    echo "$current_id"
}

save_search_results() {
    local search_id="$1"
    local results="$2"
    local search_term="$3"
    local media_kind="$4"
    local protocol="$5"
    local mode="$6"
    local timestamp=$(date "+%Y-%m-%d %H:%M:%S")
    
    local search_dir="$CACHE_DIR/search_${search_id}"
    mkdir -p "$search_dir"
    
    cat > "$search_dir/meta" <<EOF
SEARCH_TERM="$search_term"
MEDIA_KIND="$media_kind"
PROTOCOL="${protocol:-both}"
TIMESTAMP="$timestamp"
MODE="$mode"
EOF
    
    echo "$results" > "$search_dir/results.json"
}

load_search_results() {
    local search_id="$1"
    local search_dir="$CACHE_DIR/search_${search_id}"
    local results_file="$search_dir/results.json"
    local meta_file="$search_dir/meta"
    
    if [ ! -f "$results_file" ] || [ ! -f "$meta_file" ]; then
        echo "Error: Search #${search_id} not found or expired" >&2
        return 1
    fi
    
    if [ -z "$LOADED_META" ]; then
        source "$meta_file"
        LOADED_META=1
    fi
    
    cat "$results_file"
}

list_cached_searches() {
    echo "Recent searches:"
    echo "────────────────────────────────────"
    
    shopt -s nullglob
    folders=("$CACHE_DIR"/search_*)
    shopt -u nullglob
    
    if [ ${#folders[@]} -eq 0 ]; then
        echo "No cached searches found."
        echo "────────────────────────────────────"
        return 0
    fi
    
    for search_dir in "${folders[@]}"; do
        search_id=$(basename "$search_dir" | sed 's/search_//')
        meta_file="$search_dir/meta"
        (
            unset SEARCH_TERM MEDIA_KIND PROTOCOL TIMESTAMP MODE
            source "$meta_file"
            local kind_icon=$(get_kind_icon "$MEDIA_KIND")
            local proto_icon=$(get_protocol_icon "$PROTOCOL")
            echo "🔢 Search #$search_id"
            echo "🔍 Term: ${SEARCH_TERM:-N/A}"
            echo "🧩 Kind: $kind_icon ${MEDIA_KIND:-N/A}"
            echo "🔌 Protocol: $proto_icon ${PROTOCOL:-both}"
            echo "⏰ When: ${TIMESTAMP:-N/A}"
            echo "🎮 Mode: ${MODE:-N/A}"
            echo "────────────────────────────────────"
        )
    done
}
