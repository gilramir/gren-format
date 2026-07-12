#!/usr/bin/env bash
# Regenerate the PNG diagrams from their .dot sources in this directory.
# Requires graphviz's `dot` on PATH.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

for dot_file in *.dot; do
    png_file="${dot_file%.dot}.png"
    echo "Rendering $dot_file -> $png_file"
    dot -Tpng "$dot_file" -o "$png_file"
done
