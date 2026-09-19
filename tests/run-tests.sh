#!/bin/bash
# Build the CLI and this suite with the Geng fork beside the checkout
# (geng-lang's vendor/), then run the suite. Arguments go to the runner:
# `-v`, a glob such as 'Diff*', `--junit-xml out.xml`.

set -e
cd "$(dirname "$0")"

geng_lang="$(cd ../../../.. && pwd)"
compiler="$geng_lang/vendor/gren-lang/compiler"
export PATH="$geng_lang/.devbox/nix/profile/default/bin:$PATH"
export GENG_BIN="$compiler/geng"

(cd .. && ./build.sh)
node "$compiler/app" make Main --output=app
node app "$@"
