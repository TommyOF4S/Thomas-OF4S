#!/bin/sh
# Double-click (Mac) to open the Devon quote builder in your browser.
cd "$(dirname "$0")" && python3 -m devon_quote serve
