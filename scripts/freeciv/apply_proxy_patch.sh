#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
upstream_root="${1:-${FREECIV_LLM_ROOT:-}}"
patch_file="$repo_root/scripts/freeciv/upstream/0001-pln-authoritative-state.patch"
pinned_commit="26ba7124249f34fd3050ef29bf191bd4d8808018"
pinned_patch_sha256="647596e2d2bc613da30bbdb3b5e7bb39213ed21d8268babebb23198663ec2aa9"

if [[ -z "$upstream_root" ]]; then
  echo "usage: $0 /path/to/freeciv-llm (or set FREECIV_LLM_ROOT)" >&2
  exit 2
fi
if ! git -C "$upstream_root" rev-parse --git-dir >/dev/null 2>&1; then
  echo "not a freeciv-llm git checkout: $upstream_root" >&2
  exit 2
fi
actual_patch_sha256="$(sha256sum "$patch_file" | cut -d' ' -f1)"
if [[ "$actual_patch_sha256" != "$pinned_patch_sha256" ]]; then
  echo "proxy patch digest mismatch: expected $pinned_patch_sha256, got $actual_patch_sha256" >&2
  exit 1
fi

if git -C "$upstream_root" apply --reverse --check "$patch_file" >/dev/null 2>&1; then
  echo "PLN authoritative-state patch is already applied"
  exit 0
fi
actual_commit="$(git -C "$upstream_root" rev-parse HEAD)"
if [[ "$actual_commit" != "$pinned_commit" ]]; then
  echo "freeciv-llm commit mismatch: expected $pinned_commit, got $actual_commit" >&2
  exit 1
fi
git -C "$upstream_root" apply --check "$patch_file"
git -C "$upstream_root" apply "$patch_file"
echo "Applied PLN authoritative-state patch to $actual_commit"
