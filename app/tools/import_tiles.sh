#!/bin/bash
aria2c \
  --input-file=../data/swissalti3d_urls_filtered.txt \
  --dir=../data/swissALTI3D_tuiles \
  --max-concurrent-downloads=8 \
  --summary-interval=5 \
  --console-log-level=warn \
  --download-result=hide
echo "All downloads completed."