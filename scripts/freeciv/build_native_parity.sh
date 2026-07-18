#!/bin/sh
set -eu

if [ "$#" -ne 2 ]; then
  echo "usage: $0 FREECIV_SOURCE OUTPUT_ROOT" >&2
  exit 2
fi

SOURCE=$1
OUTPUT=$2
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
CLONE="$OUTPUT/source"
BUILD="$OUTPUT/build"

if [ ! -f "$SOURCE/meson.build" ]; then
  echo "not a FreeCiv source root: $SOURCE" >&2
  exit 2
fi

if [ ! -d "$CLONE" ]; then
  mkdir -p "$OUTPUT"
  cp -a "$SOURCE" "$CLONE"
  cp "$SCRIPT_DIR/native/research_parity.c" "$CLONE/tools/research_parity.c"
  sed -i -e '$r'"$SCRIPT_DIR/native/research-parity.meson" "$CLONE/meson.build"
fi

if [ ! -f "$BUILD/build.ninja" ]; then
  meson setup "$BUILD" "$CLONE" \
    -Dclients=[] -Dfcmp=[] -Druledit=false -Daudio=false -Dmwand=false \
    -Dnls=false -Dreadline=false -Dserver=enabled -Dbuildtype=release
fi

meson compile -C "$BUILD" freeciv-research-parity
printf '%s\n' "$BUILD/freeciv-research-parity"
