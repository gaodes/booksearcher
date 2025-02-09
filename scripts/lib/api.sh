# Core API functions
make_api_call() {
    local url="$1"
    local method="${2:-GET}"
    local data="$3"
    
    if [ "$method" = "POST" ]; then
        curl -s -H "X-Api-Key: $API_KEY" \
             -H "Content-Type: application/json" \
             -X POST \
             -d "$data" \
             "$url"
    else
        curl -s -H "X-Api-Key: $API_KEY" \
             -H "Accept: application/json" \
             "$url"
    fi
}

get_tag_ids() {
    local response
    
    response=$(make_api_call "$PROWLARR_URL/api/v1/tag")
    
    if [ -z "$response" ]; then
        echo "Error: No tags found in Prowlarr" >&2
        return 1
    fi
    
    AUDIOBOOKS_TAG_ID=$(echo "$response" | jq -r '.[] | select(.label | ascii_downcase == "audiobooks") | .id')
    EBOOKS_TAG_ID=$(echo "$response" | jq -r '.[] | select(.label | ascii_downcase == "ebooks") | .id')
    if [ -z "$AUDIOBOOKS_TAG_ID" ] || [ -z "$EBOOKS_TAG_ID" ]; then
        echo "Error: Could not find 'audiobooks' or 'ebooks' tag in Prowlarr. Please create them." >&2
        return 1
    fi
    
    echo "$AUDIOBOOKS_TAG_ID $EBOOKS_TAG_ID"
}

get_download_clients() {
    DOWNLOAD_CLIENTS=$(curl -s \
         -H "X-Api-Key: $API_KEY" \
         "${PROWLARR_URL}/api/v1/downloadclient" | jq -r '[.[] | select(.enable==true)]')
}

grab_release() {
    local release_data=$1

    echo "Sending to download client..."
    title=$(echo "$release_data" | jq -r '.title')
    guid=$(echo "$release_data" | jq -r '.guid')
    indexer_id=$(echo "$release_data" | jq -r '.indexerId|tostring')
    
    json_payload="{\"guid\": \"$guid\", \"indexerId\": $indexer_id}"
    response=$(make_api_call "${PROWLARR_URL}/api/v1/search" "POST" "$json_payload")

    if [ "$DEBUG" = "true" ]; then
        echo "DEBUG: API Response:"
        echo "$response" | jq '.'
    fi

    if echo "$response" | jq -e 'has("rejected")' >/dev/null; then
        echo "Error: Download rejected"
        echo "$response" | jq -r '.rejected'
    else
        echo "────────────────────────────────────"
        echo "✨ Successfully sent to download client!"
        echo "📥 Title:"
        echo "$title" | fold -s -w 60 | sed 's/^/    /'
        echo "────────────────────────────────────"
    fi
    exit 0
}

format_search_results() {
    local response="$1"
    local prowlarr_url="$2"
    local protocol="$3"
    
    local prowlarr_url_esc=$(printf '%s\n' "$prowlarr_url" | sed 's/[&/\]/\\&/g')
    echo "$response" | jq -r --arg url "$prowlarr_url_esc" --arg proto "$protocol" '
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
    
    # ...existing jq formatting functions...
    
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
    end'
}

process_search_results() {
    local response="$1"
    local prowlarr_url="$2"
    declare -n titles_ref="$3"
    declare -n data_ref="$4"
    local counter=1
    
    while IFS= read -r line; do
        if [[ "$line" =~ ^[0-9]+\) ]]; then
            titles_ref[$counter]="${line#*) }"
        elif [[ "$line" == *"STORE:"* ]]; then
            data_ref[$counter]="${line#*STORE: }"
            ((counter++))
        fi
    done < <(echo "$response" | jq -r --arg url "$prowlarr_url" '
        if type == "array" then
            . | sort_by(.size) | reverse | to_entries[] |
            "\(.key + 1)) \(.value.title)\nSTORE: \(.value)"
        else
            empty
        end')
    
    echo "$counter"
}
