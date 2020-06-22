#!/usr/bin/env bash

set -e
set -x

TYPE="${1:-openneuro}"

REPO="$(mktemp -d)"
trap 'rm -rf "$REPO"' EXIT # TODO: only clean up on successes?
cd "$REPO"
git init
git annex init
git annex -d initremote on type=external externaltype="$TYPE" exporttree=yes encryption=none 
# I have to say, it *is* really convenient that git-annex comes with built in regression tests
git annex -d testremote "$TYPE"
