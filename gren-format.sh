#!/bin/bash

THIS_DIR=$(dirname $(realpath $0))

export PATH=/opt/nodejs/25.1.0/bin:$PATH

node "${THIS_DIR}"/app "$@"
