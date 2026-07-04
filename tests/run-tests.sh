#!/bin/bash

set -e

pushd ..
devbox run build_test

popd
node app "$@"
