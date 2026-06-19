#!/bin/bash

# CLI integration tests for gren-format, written in Gren on top of gilramir/gren-ut.
# Builds the gren-format binary, then builds and runs the test app (which shells
# out to that binary). Extra args pass through to the test runner, e.g.:
#
#   ./run_tests.sh -v                    # verbose: per-test status + timing
#   ./run_tests.sh 'AllFlag.*'           # run a glob-selected subset
#   ./run_tests.sh --junit-xml out.xml   # write JUnit XML

set -e

HERE="$(dirname "$0")"

# 1. Build the gren-format binary under test (../app).
cd "$HERE/.."
../gren.sh make Main --output=app

# 2. Build and run the Gren test app.
cd tests
../../gren.sh make Main --output=app
node app "$@"
