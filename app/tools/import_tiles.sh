#!/bin/bash

# Configuration
INPUT_FILE="${1:-data/swissalti3d_urls_filtered.txt}"
OUTPUT_DIR="${2:-data/swissALTI3D_tiles}"
MAX_CONCURRENT="${3:-8}"

# Validate input file exists
if [ ! -f "$INPUT_FILE" ]; then
    echo "Error: Input file not found: $INPUT_FILE"
    exit 1
fi

# Create output directory if it doesn't exist
mkdir -p "$OUTPUT_DIR"

# Download tiles with aria2c
aria2c \
    --input-file="$INPUT_FILE" \
    --dir="$OUTPUT_DIR" \
    --max-concurrent-downloads="$MAX_CONCURRENT" \
    --summary-interval=5 \
    --console-log-level=warn \
    --download-result=hide

echo "Download completed successfully!"
exit 0