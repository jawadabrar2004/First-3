#!/bin/bash
cd "$(dirname "$0")"
if ! command -v node >/dev/null 2>&1; then
  echo "Node.js is not installed. Download the LTS version from https://nodejs.org then run this again."
  read -p "Press Enter to close."
  exit 1
fi
(sleep 1 && open "http://localhost:4000") &
node server.js
