#!/usr/bin/env bash
# Publish the current scrape results to the deal screen and push them to GitHub.
# Used after every checkpoint during a crawl, and once more at the end.
set -u
python bfs/publish.py out/bfs_listings.csv || exit 0
git config user.name "dealsourcing-bot"
git config user.email "dealsourcing-bot@users.noreply.github.com"
git add docs/data/bfs.json
if git diff --cached --quiet; then echo "No data changes"; exit 0; fi
git commit -q -m "${1:-Update BusinessesForSale data}"
for i in 1 2 3; do git pull --rebase -q && git push -q && exit 0; sleep 5; done
echo "Push failed after 3 tries" >&2
