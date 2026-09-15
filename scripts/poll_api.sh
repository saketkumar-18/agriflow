#!/usr/bin/env bash
# Poll the deployed AgriFlow API until it answers or budget runs out (cold start
# on Render free tier can take ~60s). Usage: bash scripts/poll_api.sh [url]
URL="${1:-https://agriflow-api-90yf.onrender.com}"
for i in $(seq 1 30); do
  BODY=$(curl -s -m 45 "$URL/api/health" 2>/dev/null)
  if [ -n "$BODY" ]; then
    echo "$BODY"
    exit 0
  fi
  sleep 10
done
echo "TIMEOUT after 30 attempts"
exit 1
