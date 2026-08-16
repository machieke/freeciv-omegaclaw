# Reply on the scale of the pressure/fluid PLN experiments

Ben, thanks — the short and honest answer is that I have explored meaningful
**closed-loop duration and mechanism scale**, but not yet what I would call
large-AtomSpace scalability. The strongest evidence so far is stable,
incremental operation over thousands of FreeCiv turns with a low-thousands
concurrent working set. It is not yet evidence for hundreds of thousands or
millions of simultaneously live atoms, nor for very deep, high-branching PLN
search.

One implementation caveat up front: the scale measurements below come from
the project's Python Functional Dependent AtomSpace and typed control-view
implementation. They are not yet a benchmark of a production OpenCog or
Hyperon knowledge-store deployment.

There are three relevant layers of experiments:

| Layer | Scale reached | What it establishes |
|---|---:|---|
| Ruleset proof oracle | 435 cache-miss proofs; longest chain depth 12 with 132 proof nodes | The compiled FreeCiv prerequisite DAG can be traversed and explained efficiently. Across those proofs, p50 latency was 8.93 ms, p95 32.53 ms, and the maximum 90.18 ms. This is deterministic ruleset reasoning, though, not unrestricted PLN theorem search. |
| Live Functional Dependent AtomSpace (FDAS) | A 2,000-turn engine-backed run with 2,019 committed revisions; median 1,068, p95 1,246, and peak 2,325 concurrent atoms | The scoped materialization/invalidation design remains bounded over a long-running changing world instead of accumulating atoms monotonically. The run also reached a peak of 1,161 active supports and 24 materialized scopes. |
| Pressure/bridge/fluid control graphs | A captured live bridge view with 354 nodes, 855 edges, 34 grounded candidates, and 2 active goals; 576 held-out bridge cases and 1,024 held-out flow cases | The mechanisms have been exercised on nontrivial but still modest control graphs, including cycles, DAGs, distractors, bottlenecks, asymmetric legality, stale topology, dynamic failures, and resource fragmentation. |

The 2,000-turn FDAS trace is useful for understanding temporal scale. It
contains 31,556 deterministic derivation firings, 57,260 atom re-derivations,
26,065 invalidations, and 30,907 support retractions. In other words, the test
did exercise dependency maintenance and churn, rather than merely loading a
static graph. It produced 320,830 fully recorded telemetry events, about 716
MiB, over 72.9 minutes. Equivalent 500- and 1,000-turn runs reached the same
2,325-atom peak, which is encouraging evidence that the active working set is
bounded. However, these three horizons used the same game seed, so they are
not an independent scaling cohort. The profile's 25,000-atom hard cap was also
never approached; it is a safety bound, not a demonstrated operating scale.

The actual live proof chains in that long run were much shallower than the
standalone ruleset benchmark: there were 14 explicit PLN query results and all
had chain depth 1 and tree size 4. Most of the ongoing work in the FDAS run was
incremental deterministic projection, support maintenance, local goal
construction, and grounded candidate generation. I therefore would **not**
use the 2,000-turn result to claim that deep inference has been tested at the
2,325-atom scale. The depth-12/132-node result and the 2,325-atom result come
from different experiments.

There is another important qualification: pressure and fluid are not diffused
over every atom in the FDAS. The controller builds a bounded, typed control
view containing the relevant goals, requirements, rules, packets, and grounded
operations. This is intentional — it is a working-memory/scoped-attention
architecture — but it means the largest measured AtomSpace working set and the
largest measured pressure graph should not be conflated.

For the isolated mechanisms, the bridge experiment's full live path had a p95
latency of about 245 ms on the 354-node/855-edge view, versus about 22 ms for
the scalar comparator. The fluid sandbox included corridor lengths from 4 to
128. At the longest setting, the isolated transport kernel averaged about 2.13
ms per run and roughly 0.13 microseconds per edge update. Those results show
predictable local numerical behavior, but they do not establish end-to-end
large-graph complexity.

I also tested whether the strong synthetic effects transferred to actual game
control. A fresh 100-pair confirmation comprised 200 engine arms and 12,258
healthy flow projections. The player-score delta was only +0.05, with a 95%
interval of [-0.33, +0.43], so there was no confirmed score improvement. The
dominant failure was semantic rather than numerical: the flow controller
routed compute consistently, but an overlap heuristic and uncalibrated
transition values sometimes preferred the wrong grounded action. That result
is why I currently treat bridge/fluid as experimental advisory machinery, not
as established live authority.

So my present claim would be:

> The architecture has been exercised on a real, changing, long-duration
> cognitive-control problem with approximately 10^3 concurrent atoms, tens of
> thousands of dependency updates, proof chains up to depth 12 in a separate
> ruleset benchmark, and pressure subgraphs of a few hundred nodes. It shows
> boundedness, deterministic replay, and measurable mechanism effects at that
> scale. It has not yet demonstrated scalability on a genuinely large
> AtomSpace or on deep, broad, open-ended PLN inference.

The next scalability experiment I would run is a two-dimensional sweep rather
than another longer FreeCiv game: independently scale the concurrently live
AtomSpace (2.5k, 10k, 25k, 100k+ atoms) and the active control subgraph
(10^2–10^5 nodes), while separately varying proof depth and branching factor.
I would measure revision latency, invalidation fan-out, peak memory, proof
latency, candidate recall, decision stability, and controller overhead for
scalar PF-v2, protected bridge readout, path persistence, and source-sink
flow. Grounded scenarios with more cities, units, players, and simultaneous
goals would then test whether the synthetic scaling behavior transfers. That
would be the point at which I would feel comfortable making a stronger claim
about sizeable AtomSpaces.
