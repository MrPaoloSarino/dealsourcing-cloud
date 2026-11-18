#!/usr/bin/env bash
# Publish scrape results to the deal screen and push them to GitHub.
#   save_data.sh "<commit message>" [publish.py args...]
# With no publish args it publishes BusinessesForSale (out/bfs_listings.csv -> docs/data/bfs.json).
set -u
msg="${1:-Update listing data}"; shift || true
python bfs/publish.py "$@" || exit 0
git config user.name "dealsourcing-bot"
git config user.email "dealsourcing-bot@users.noreply.github.com"
git add docs/data/*.json
if git diff --cached --quiet; then echo "No data changes"; exit 0; fi
git commit -q -m "$msg"
for i in 1 2 3 4; do git pull --rebase -q && git push -q && exit 0; sleep $((i * 5)); done
echo "Push failed after 4 tries" >&2
