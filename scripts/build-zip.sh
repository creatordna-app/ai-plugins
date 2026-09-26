#!/bin/sh
# Build product-demo-video.zip (for the Claude Desktop upload) from skills/product-demo-video.
# Attach the result to a GitHub Release; it is not committed to the repo.
set -e
cd "$(dirname "$0")/../skills"
rm -f ../product-demo-video.zip
zip -qrX ../product-demo-video.zip product-demo-video -x '*/__pycache__/*' '*.pyc' '*.DS_Store'
echo "Built product-demo-video.zip"
