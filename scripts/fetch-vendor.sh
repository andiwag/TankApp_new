#!/bin/sh
# Download self-hosted frontend vendor assets into app/static/vendor/
set -e
VENDOR_DIR="app/static/vendor"
mkdir -p "$VENDOR_DIR"

ALPINE_VERSION="3.14.9"
CHARTJS_VERSION="4.4.9"

curl -fsSL "https://cdn.jsdelivr.net/npm/alpinejs@${ALPINE_VERSION}/dist/cdn.min.js" \
  -o "$VENDOR_DIR/alpine.min.js"

curl -fsSL "https://cdn.jsdelivr.net/npm/chart.js@${CHARTJS_VERSION}/dist/chart.umd.min.js" \
  -o "$VENDOR_DIR/chart.umd.min.js"

curl -fsSL "https://cdn.tailwindcss.com" \
  -o "$VENDOR_DIR/tailwindcss.js"

echo "Vendor assets written to $VENDOR_DIR"
