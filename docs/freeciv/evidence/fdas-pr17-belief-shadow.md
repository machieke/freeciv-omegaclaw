# FDAS PR 17: opponent-belief shadow activation

Date: 2026-08-02
Branch: `experimental/functional-dependent-atomspace`
Status: belief projection declared `shadow-live`; observation pressure remains `component-only`
Machine-readable evidence: `fdas-pr17-belief-shadow-engine.json`

## Acceptance boundary

This increment promotes the read-only uncertain-belief projector into the
engine-live FDAS revision. It does not select an observation, revise truth from
pressure, infer hidden absence, or grant any FDAS action authority.

The existing `BeliefStore` remains the only owner of evidence union, revision,
decay, conflict detection, and context quarantine. FDAS projects its current
output into opponent-local scopes with exact dependencies on belief revision,
evidence, conflict, and quarantine records. Projected belief atoms retain
`UNCERTAIN_BELIEF` authority and `crisp: false`; conflict and quarantine
structure remains diagnostic/control-model knowledge.

## Engine integration repair

The component projector already failed closed when a belief had not been
decayed to the current snapshot turn. Engine-live, however, had never advanced
the belief store before an FDAS turn-boundary projection. Simply enabling the
projector would therefore have failed on turn 2.

The live seam now:

1. calls `BeliefStore.decay_to(current_turn)` immediately before a belief-backed
   FDAS projection;
2. emits every resulting decay as a causal `revision` event using the declared
   linear-window formula;
3. retains the decayed value as the latest terminal calibration prediction;
4. rematerializes the same immutable snapshot after a real visible-roster or
   visible-unit observation changes the belief artifact;
5. records decay-revision and rematerialization counters in final telemetry;
6. requires an exact `belief_domain_projection: shadow-live` manifest and
   `policy_authority: false`; and
7. leaves `observation_pressure_planning` component-only.

Repeated decay at the same turn is idempotent. When confidence reaches zero,
the belief support is removed from the committed FDAS revision. No negative
`absent`, `lacks`, `missing`, or `not-present` proposition is synthesized.

## Fresh paired confirmation

The paired diagnostic used a new predeclared seed, `271828`, and ran from clean
source commit `f25f7445a11d93758e5a803714731d18341a6908`, implementation
SHA-256 `f1a5a8bc564402bb4a3ddb53b31fe4d378f170267b64cb7d1e55cf6dbfccb487`,
FDAS declaration hash
`488afdb508791b6cef0f12796f49cb0fa800ab57cbcd662bc7cd2679fff74eba`,
and configuration hash
`311ddba9e5497c16f64c6a59b315117863296e9db19fdaed781d9e94db85fda0`.

```bash
FREECIV_FDAS_CONFIG_PATH=profile/dependent_atomspace_belief_shadow.yaml \
FREECIV_FDAS_MANIFEST_PATH=profile/fdas_manifest_belief_shadow.json \
PYTHONPATH=src:benchmarks \
python3 scripts/freeciv/run_impact_evaluation.py \
  --config profile/freeciv_harness.yaml \
  --out artifacts/freeciv/fdas-belief-shadow-live-30-v1 \
  --backend engine-live --workers 1 --server-ports 6001 \
  --cohort fdas_belief_shadow_diagnostic_v1 --no-resume

PYTHONPATH=src:benchmarks \
python3 scripts/freeciv/audit_fdas_belief_live.py \
  --cohort-root artifacts/freeciv/fdas-belief-shadow-live-30-v1 \
  --output docs/freeciv/evidence/fdas-pr17-belief-shadow-engine.json
```

Results:

| Measure | Baseline | Treatment |
| --- | ---: | ---: |
| Engine actions / accepted results / rejects | 62 / 62 / 0 | 73 / 73 / 0 |
| Real observation events | 4 | 2 |
| Belief-scope materializations | 24 | 17 |
| Explicit decay revisions | 301 | 16 |
| Same-snapshot belief rematerializations | 4 | 2 |
| Expired/revised atom invalidations | 313 | 24 |
| Conflict / quarantine events | 0 / 0 | 0 / 0 |
| Sampled cold verifications / failures | 1 / 0 | 3 / 0 |
| Belief rematerialization p50 / p95 | 23.11 / 28.24 ms | 1.53 / 2.46 ms |
| FDAS projection p50 / p95 | 2.90 / 37.63 ms | 1.38 / 3.40 ms |
| Full-controller p50 / p95 | 126.73 / 371.71 ms | 138.46 / 401.80 ms |
| FDAS / operation authority actions | 0 / 0 | 0 / 0 |

The different evidence volume is an ordinary behavioral difference between
the existing baseline and treatment planners: the baseline exposed more
previously unseen enemy units and consequently produced more prerequisite
abductions. The cohort does not interpret that difference as a belief-policy
effect because both arms ran the same non-authorizing FDAS projection.

All non-empty committed belief revisions retained one support per projected
atom. Every decay confidence was less than or equal to its prior confidence,
all causal parents existed, all observed/revised atoms were non-crisp, and no
negative absence predicate appeared. No conflict or quarantine was expected
because the real observations had no contradictory independent lineages;
component tests separately cover explicit conflict projection, complete
lineage partitioning, quarantine, and quarantine non-authority.

The audit passed every source-freeze, evidence, uncertainty, decay,
invalidation, cold-parity, latency, and non-authority gate. Both arms also met
the branch-wide 500 ms full-controller p95 target.

The deterministic report structural hash is
`d7597f9db91bf256602252fd1d608221b463ccb66cc9b6319f41d38fc3d43945`.
The tracked report file SHA-256 is
`de5e19d0f0b27f856a7a228428e84c59f82aefb1874816b0ad8ad1fb1bbca2ff`.

## Claim boundary and next gate

This is mechanism, epistemic-separation, decay, support-invalidation,
behavior-preservation, and latency evidence. The paired cohort was deliberately
claim-ineligible and supports no score or win-rate claim.

Observation-pressure selection has since passed its independent shadow-live
gate in
[`fdas-pr18-observation-pressure-shadow.md`](fdas-pr18-observation-pressure-shadow.md).
The remaining gate is execution and authoritative return: bind a selected test
to a current legal observation action, commit-revalidate it, and allow evidence
registration only through the authoritative-return firewall. A selected test
still has no direct path to authoritative or crisp FDAS truth.
