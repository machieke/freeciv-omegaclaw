#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
upstream_root="${1:-${FREECIV_LLM_ROOT:-}}"
authoritative_patch="$repo_root/scripts/freeciv/upstream/0001-pln-authoritative-state.patch"
spatial_patch="$repo_root/scripts/freeciv/upstream/0002-pln-spatial-projection.patch"
lifecycle_patch="$repo_root/scripts/freeciv/upstream/0003-pln-unit-lifecycle.patch"
pinned_commit="26ba7124249f34fd3050ef29bf191bd4d8808018"
pinned_authoritative_sha256="48e416000bf36c3c7ce13c8c59bb51bc682a1f17ee8568e432a82f673a10df55"
pinned_spatial_sha256="a4eb88c827c7a2ea68db602aa2463c2aa53bb0c6156a71e1a5a5e7fc09908856"
pinned_lifecycle_sha256="1df99426c617e72beb0ca2bcbc879793cffce03e79a28a91e6e1955346228c31"

if [[ -z "$upstream_root" ]]; then
  echo "usage: $0 /path/to/freeciv-llm (or set FREECIV_LLM_ROOT)" >&2
  exit 2
fi
if ! git -C "$upstream_root" rev-parse --git-dir >/dev/null 2>&1; then
  echo "not a freeciv-llm git checkout: $upstream_root" >&2
  exit 2
fi
for patch_spec in \
  "$authoritative_patch:$pinned_authoritative_sha256" \
  "$spatial_patch:$pinned_spatial_sha256" \
  "$lifecycle_patch:$pinned_lifecycle_sha256"; do
  patch_file="${patch_spec%:*}"
  pinned_patch_sha256="${patch_spec##*:}"
  actual_patch_sha256="$(sha256sum "$patch_file" | cut -d' ' -f1)"
  if [[ "$actual_patch_sha256" != "$pinned_patch_sha256" ]]; then
    echo "proxy patch digest mismatch for $(basename "$patch_file"): expected $pinned_patch_sha256, got $actual_patch_sha256" >&2
    exit 1
  fi
done

# Each later patch depends on its predecessors. If the final reverse check
# succeeds, the complete patch series is already present.
if git -C "$upstream_root" apply --reverse --check "$lifecycle_patch" >/dev/null 2>&1; then
  echo "PLN authoritative-state, spatial-projection, and unit-lifecycle patches are already applied"
  exit 0
fi
actual_commit="$(git -C "$upstream_root" rev-parse HEAD)"
if [[ "$actual_commit" != "$pinned_commit" ]]; then
  echo "freeciv-llm commit mismatch: expected $pinned_commit, got $actual_commit" >&2
  exit 1
fi
for patch_file in "$authoritative_patch" "$spatial_patch" "$lifecycle_patch"; do
  if git -C "$upstream_root" apply --reverse --check "$patch_file" >/dev/null 2>&1; then
    echo "$(basename "$patch_file") is already applied"
    continue
  fi
  git -C "$upstream_root" apply --check "$patch_file"
  git -C "$upstream_root" apply "$patch_file"
  echo "Applied $(basename "$patch_file") to $actual_commit"
done
