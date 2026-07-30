#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
upstream_root="${1:-${FREECIV_LLM_ROOT:-}}"
authoritative_patch="$repo_root/scripts/freeciv/upstream/0001-pln-authoritative-state.patch"
spatial_patch="$repo_root/scripts/freeciv/upstream/0002-pln-spatial-projection.patch"
lifecycle_patch="$repo_root/scripts/freeciv/upstream/0003-pln-unit-lifecycle.patch"
sustainability_patch="$repo_root/scripts/freeciv/upstream/0004-pln-government-and-sustainability.patch"
sustainability_control_patch="$repo_root/scripts/freeciv/upstream/0005-pln-sustainability-control.patch"
city_food_governor_patch="$repo_root/scripts/freeciv/upstream/0006-pln-city-food-governor.patch"
government_transition_patch="$repo_root/scripts/freeciv/upstream/0007-pln-government-transition.patch"
disorder_luxury_recovery_patch="$repo_root/scripts/freeciv/upstream/0008-pln-disorder-luxury-recovery.patch"
strategic_observability_patch="$repo_root/scripts/freeciv/upstream/0009-pln-strategic-observability.patch"
ruleset_name_sanitization_patch="$repo_root/scripts/freeciv/upstream/0010-pln-ruleset-name-sanitization.patch"
government_state_correction_patch="$repo_root/scripts/freeciv/upstream/0011-pln-government-state-correction.patch"
city_ownership_reconciliation_patch="$repo_root/scripts/freeciv/upstream/0012-pln-city-ownership-reconciliation.patch"
native_movement_routes_patch="$repo_root/scripts/freeciv/upstream/0013-pln-native-movement-routes.patch"
pinned_commit="26ba7124249f34fd3050ef29bf191bd4d8808018"
pinned_authoritative_sha256="48e416000bf36c3c7ce13c8c59bb51bc682a1f17ee8568e432a82f673a10df55"
pinned_spatial_sha256="a4eb88c827c7a2ea68db602aa2463c2aa53bb0c6156a71e1a5a5e7fc09908856"
pinned_lifecycle_sha256="1df99426c617e72beb0ca2bcbc879793cffce03e79a28a91e6e1955346228c31"
pinned_sustainability_sha256="d7fa7b77ff7040af0da25ea8ed86156d754b5b6007eee5d98a95b87fe9b3cafa"
pinned_sustainability_control_sha256="412f4b462afab900233793f192732317b7e00b42b165dee1c09056ca9d5a1827"
pinned_city_food_governor_sha256="33a10ec287297629d2383d494f4ac01ad60ad1d25167dec39753e9d8a131113f"
pinned_government_transition_sha256="1b3ecb9458559b0552f232e41804e545a94ccd4d2d774a0f0e6c90dac8dd013c"
pinned_disorder_luxury_recovery_sha256="e800adbe5a4f3a8e68e30a4e21019ef92dabbb272b28ecd50d90c64e7dcb417b"
pinned_strategic_observability_sha256="9a768dda13455760f5d02a3e66ebc3eae564c3b37c8965c77c9e9565c3656e44"
pinned_ruleset_name_sanitization_sha256="09480dc463d3347d26db27e387a5a528c6b525fb65089aa1f6f5cd1fb999ce67"
pinned_government_state_correction_sha256="dee93c53c8f0dcc06c0a0ea98ee278e19cc360fbf36ef554f096cebe11f5d4b3"
pinned_city_ownership_reconciliation_sha256="db29d472e49bd8b24bb227142c3635a77d44932a697b1fe9eafc49517198cf0d"
pinned_native_movement_routes_sha256="e2d2681acdeb53a2b3ace5fb519273d83e5acb20dcadfb2cc590fa16da4c023e"

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
  "$lifecycle_patch:$pinned_lifecycle_sha256" \
  "$sustainability_patch:$pinned_sustainability_sha256" \
  "$sustainability_control_patch:$pinned_sustainability_control_sha256" \
  "$city_food_governor_patch:$pinned_city_food_governor_sha256" \
  "$government_transition_patch:$pinned_government_transition_sha256" \
  "$disorder_luxury_recovery_patch:$pinned_disorder_luxury_recovery_sha256" \
  "$strategic_observability_patch:$pinned_strategic_observability_sha256" \
  "$ruleset_name_sanitization_patch:$pinned_ruleset_name_sanitization_sha256" \
  "$government_state_correction_patch:$pinned_government_state_correction_sha256" \
  "$city_ownership_reconciliation_patch:$pinned_city_ownership_reconciliation_sha256" \
  "$native_movement_routes_patch:$pinned_native_movement_routes_sha256"; do
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
if git -C "$upstream_root" apply --reverse --check "$native_movement_routes_patch" >/dev/null 2>&1; then
  echo "PLN authoritative-state through native-movement-route patches are already applied"
  exit 0
fi
actual_commit="$(git -C "$upstream_root" rev-parse HEAD)"
if [[ "$actual_commit" != "$pinned_commit" ]]; then
  echo "freeciv-llm commit mismatch: expected $pinned_commit, got $actual_commit" >&2
  exit 1
fi
for patch_file in \
  "$authoritative_patch" \
  "$spatial_patch" \
  "$lifecycle_patch" \
  "$sustainability_patch" \
  "$sustainability_control_patch" \
  "$city_food_governor_patch" \
  "$government_transition_patch" \
  "$disorder_luxury_recovery_patch" \
  "$strategic_observability_patch" \
  "$ruleset_name_sanitization_patch" \
  "$government_state_correction_patch" \
  "$city_ownership_reconciliation_patch" \
  "$native_movement_routes_patch"; do
  if git -C "$upstream_root" apply --reverse --check "$patch_file" >/dev/null 2>&1; then
    echo "$(basename "$patch_file") is already applied"
    continue
  fi
  git -C "$upstream_root" apply --check "$patch_file"
  git -C "$upstream_root" apply "$patch_file"
  echo "Applied $(basename "$patch_file") to $actual_commit"
done
