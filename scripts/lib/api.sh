
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
