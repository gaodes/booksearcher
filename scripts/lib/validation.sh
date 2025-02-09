
validate_tag_id() {
    local tag_id="$1"
    if ! [[ "$tag_id" =~ ^[0-9]+$ ]]; then
        echo "Error: Invalid tag ID: $tag_id. Must be a number." >&2
        return 1
    fi
    return 0
}
