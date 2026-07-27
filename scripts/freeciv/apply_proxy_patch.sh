#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
upstream_root="${1:-${FREECIV_LLM_ROOT:-}}"
authoritative_patch="$repo_root/scripts/freeciv/upstream/0001-pln-authoritative-state.patch"
spatial_patch="$repo_root/scripts/freeciv/upstream/0002-pln-spatial-projection.patch"
pinned_commit="26ba7124249f34fd3050ef29bf191bd4d8808018"
pinned_authoritative_sha256="48e416000bf36c3c7ce13c8c59bb51bc682a1f17ee8568e432a82f673a10df55"
pinned_spatial_sha256="a4eb88c827c7a2ea68db602aa2463c2aa53bb0c6156a71e1a5a5e7fc09908856"

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
  "$spatial_patch:$pinned_spatial_sha256"; do
  patch_file="${patch_spec%:*}"
  pinned_patch_sha256="${patch_spec##*:}"
  actual_patch_sha256="$(sha256sum "$patch_file" | cut -d' ' -f1)"
  if [[ "$actual_patch_sha256" != "$pinned_patch_sha256" ]]; then
    echo "proxy patch digest mismatch for $(basename "$patch_file"): expected $pinned_patch_sha256, got $actual_patch_sha256" >&2
    exit 1
  fi
done

# The spatial patch depends on the authoritative patch. If its reverse check
# succeeds, the complete patch series is already present.
if git -C "$upstream_root" apply --reverse --check "$spatial_patch" >/dev/null 2>&1; then
  echo "PLN authoritative-state and spatial-projection patches are already applied"
  exit 0
fi
actual_commit="$(git -C "$upstream_root" rev-parse HEAD)"
if [[ "$actual_commit" != "$pinned_commit" ]]; then
  echo "freeciv-llm commit mismatch: expected $pinned_commit, got $actual_commit" >&2
  exit 1
fi
if ! git -C "$upstream_root" apply --reverse --check "$authoritative_patch" >/dev/null 2>&1; then
  git -C "$upstream_root" apply --check "$authoritative_patch"
  git -C "$upstream_root" apply "$authoritative_patch"
  echo "Applied PLN authoritative-state patch to $actual_commit"
fi
git -C "$upstream_root" apply --check "$spatial_patch"
git -C "$upstream_root" apply "$spatial_patch"
echo "Applied PLN spatial-projection patch to $actual_commit"
