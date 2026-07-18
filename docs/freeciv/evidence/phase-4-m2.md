# Phase 4 / M2 evidence

Date: 2026-07-17 UTC  
External base: `26ba7124249f34fd3050ef29bf191bd4d8808018`  
Proxy patch SHA-256: `2c0fae26da7936470fe00eb4d4eb9096e0b8c2620defa2eff27e6b4b104f23f0`

## Contract and fail-closed behavior

- V2 fixture SHA-256: `e4563d55b85254ec306df0427045e866b6cecc2fda84e9a8d72fd24e3c2acf81`.
- State schema SHA-256: `c5541999f3bad7694fb8c843b94e3acdb0f1991ed15d5b2dc6000f6de63830b9`.
- The byte-real old `llm_optimized` capture remains readable but reports ruleset, research rate,
  and economy as unavailable; it cannot pass the execution gate.
- Missing city buildability and missing ruleset-ready state are covered by local no-transport
  assertions.
- Static target-LLM scan found no `ProxyStateDTO` or `AuthoritativeSnapshot` import.
- Crisp atom projection has a hard quantitative-predicate denylist and the test suite finds no
  stored numeric derived atom.

## Tests

- OmegaClaw M2: 9 passed.
- Combined V0/M0/M1/M2 regression: 38 passed.
- Patched upstream targeted proxy suite in `fciv-net`: 133 passed. Two cache-write warnings are
  caused by the bind mount permissions and do not affect test results.
- The broader upstream `test_state_extractor.py` currently fails during collection because its
  Tornado `AsyncHTTPTestCase` base is collected as a test under the container's pytest/Tornado
  combination; targeted state extractor behavior is exercised directly by the new contract
  test.

## 100-turn comparators

Deterministic packet-contract comparator, seed 4202:

- 100 turns verified;
- 100 current legal actions submitted;
- 99 prior-snapshot actions rejected locally;
- zero field/atom/grounded mismatches;
- zero engine rejections.

Live patched-proxy/FreeCiv run (`m2-live-6002`), seed 4202:

- 100 authoritative turns verified;
- 100 randomized server-listed actions accepted;
- 100 end-turn actions accepted;
- 99 deliberately stale actions rejected locally with no submission;
- zero own-state field, atom, or grounded-value mismatches;
- zero proxy/engine-path action rejections.

The live state included `format=pln_authoritative`, `ruleset_ready=true`, a monotonic packet
sequence, packet-backed gold and beaker rates, seven starting owned units, and a city created
through the legal-action path.

This satisfies P4.A1-P4.A7 and closes M2.

## Post-gate authoritative technology-index regression

The tracked proxy patch also verifies that invention-array index `i` maps to ruleset
technology ID `i`, not `i + 1`, renews active sessions before their inactivity window
expires, and preserves exact release-game configuration across retries. The focused proxy
suite passes 12/12 tests. A deterministic
two-turn live run (`m7-cognitive_index_fix-e_full_loop-104729-10`) then emitted a validated
61-event trace in which the scheduler-selected `Industrialization` research action was sent,
accepted by Freeciv, and marked completed with zero engine rejections. This closes the
specific live discrepancy that exposed the former shifted name projection.
