# FDAS PR86 ruleset preflight failure

Date: 2026-08-04

## Result

The first PR86 launch is rejected before gameplay. The checked-in launcher
correctly assigned four process workers to distinct ports 6001–6004 and
attempted all 32 arms without any launcher failure, but its preflight did not
validate the required local `FREECIV_RULESET_ROOT` binding. Every arm stopped
with the same error:

`RuntimeError: engine-live requires FREECIV_RULESET_ROOT`

All 32 manifests identify clean source commit
`4416151a1b39173d1cd1a2411d3452ee6f849efa`; each port received exactly eight
arms. There are 32 terminal status files and zero event ledgers. The ruleset
failure occurred in cognitive-stack assembly before proxy game configuration,
the `run_started` event, map construction, or any action. No seed therefore
produced gameplay, an intention opportunity, an intervention, or an outcome.

The immutable artifact root is
`artifacts/freeciv/fdas-pr86-isolated-launch-paired-v3`. Its tree digest,
computed by hashing the sorted relative-path `sha256sum` rows, is
`f4f8cae73e0d6100bf697627904f6415938ba632378ba4fbe42c161600cefc8b`.
The accompanying JSON record freezes the aggregate counts and timestamps.

## Correction boundary

PR86b may reuse the registered V3 seeds and arm order because this failure
revealed no seed-dependent state and supplied no gameplay or intervention
data. It must write a new output root and never resume or overwrite the failed
root. This is consistent with earlier pre-game missing-ruleset corrections.

Before creating the corrected root, the launcher must now:

- require `FREECIV_RULESET_ROOT/civ2civ3/techs.ruleset`;
- compile the declared ruleset and record the compiler and IR identity;
- confirm that the configured FreeCiv container is running;
- confirm that the proxy endpoint accepts a TCP connection;
- confirm that the Ollama endpoint advertises the exact configured model; and
- retain every existing clean-source, profile, empty-root, pair-order, and
  unique-port check.

The sole ambient correction is the existing pinned ruleset checkout at
`/home/purplezky/Repos/freeciv-llm/freeciv/freeciv/data`. No controller,
semantic manifest, seed, outcome, horizon, or progression criterion changes.
