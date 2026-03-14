#!/bin/sh
set -e
npm install
npx tsc
npx vsce package --no-dependencies
