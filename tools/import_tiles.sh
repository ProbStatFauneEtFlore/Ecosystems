#!/bin/bash
aria2c \
  --input-file=data/swissalti3d_urls.txt \
  --dir=./data/swissALTI3D_tuiles \
  --continue=true \
  --auto-file-renaming=false \
  --max-concurrent-downloads=8 \
  --max-connection-per-server=16 \
  --split=16 \
  --min-split-size=5M \
  --conditional-get=true \
  --retry-wait=5 \
  --max-tries=0 \
  --summary-interval=10
echo "All downloads completed."