#!/bin/bash
# Check bundle sizes against budgets.
# Run after `npm run build` in the frontend directory.
#
# Budgets (uncompressed):
#   vendor chunk: 200 kB
#   clerk chunk: 300 kB
#   main index chunk: 500 kB
#   total: 1200 kB

set -euo pipefail

DIST="$(dirname "$0")/../dist/assets"
MAX_TOTAL_KB=1200

if [ ! -d "$DIST" ]; then
  echo "ERROR: dist/assets not found. Run 'npm run build' first."
  exit 1
fi

total=0
exceeded=0

for f in "$DIST"/*.js; do
  size_bytes=$(wc -c < "$f" | tr -d ' ')
  size_kb=$((size_bytes / 1024))
  total=$((total + size_kb))

  name=$(basename "$f")
  # Check per-chunk budgets
  if echo "$name" | grep -q "vendor"; then
    if [ "$size_kb" -gt 200 ]; then
      echo "FAIL: $name is ${size_kb}kB (budget: 200kB)"
      exceeded=1
    fi
  elif echo "$name" | grep -q "clerk"; then
    if [ "$size_kb" -gt 300 ]; then
      echo "FAIL: $name is ${size_kb}kB (budget: 300kB)"
      exceeded=1
    fi
  elif echo "$name" | grep -q "^index-"; then
    if [ "$size_kb" -gt 500 ]; then
      echo "FAIL: $name is ${size_kb}kB (budget: 500kB)"
      exceeded=1
    fi
  fi

  echo "  $name: ${size_kb}kB"
done

echo ""
echo "Total JS: ${total}kB (budget: ${MAX_TOTAL_KB}kB)"

if [ "$total" -gt "$MAX_TOTAL_KB" ]; then
  echo "FAIL: Total JS bundle exceeds ${MAX_TOTAL_KB}kB budget"
  exceeded=1
fi

if [ "$exceeded" -eq 1 ]; then
  exit 1
fi

echo "PASS: All bundle size budgets met"
