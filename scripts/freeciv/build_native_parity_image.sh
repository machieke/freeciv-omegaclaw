#!/bin/sh
set -eu

if [ "$#" -ne 2 ]; then
  echo "usage: $0 FREECIV_SOURCE IMAGE_TAG" >&2
  exit 2
fi

SOURCE=$1
IMAGE=$2
REPO=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
CONTEXT="$REPO/build/freeciv/native-parity-image"

if [ ! -f "$SOURCE/meson.build" ]; then
  echo "not a FreeCiv source root: $SOURCE" >&2
  exit 2
fi

if [ ! -d "$CONTEXT/source" ]; then
  mkdir -p "$CONTEXT"
  cp -a "$SOURCE" "$CONTEXT/source"
fi
cp "$REPO/scripts/freeciv/native/research_parity.c" "$CONTEXT/source/tools/research_parity.c"
if ! grep -q "freeciv-research-parity" "$CONTEXT/source/meson.build"; then
  sed -i -e '$r'"$REPO/scripts/freeciv/native/research-parity.meson" \
    "$CONTEXT/source/meson.build"
fi

docker build --tag "$IMAGE" --file "$REPO/scripts/freeciv/native/Dockerfile" "$CONTEXT"
docker image inspect "$IMAGE" --format '{{.Id}}'
