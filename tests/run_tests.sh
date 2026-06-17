#!/bin/bash

set -e

cd "$(dirname "$0")/.."
../gren.sh make Main --output=app

cd tests
python3 -m unittest discover -s . -p "test_*.py" -v
