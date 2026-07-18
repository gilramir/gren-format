#!/bin/bash

set -e

devbox run build_test

node app "$@"
