# FDAS PR70 PR68 pair-scope sensitivity

## Result

The post-hoc sensitivity reconstructs all six aggregate PR68 scope rows and
correctly binds the original failed PR68 report hash. Its report,
`fdas-pr70-pr68-pair-scope-sensitivity.json`, has hash
`9b90b1de8a10ece1fab72d8cb28cb5087f17313aed9cda94984811ad102437f9`
and a false `passed` value.

All six pairs are:

- distinct canonical actions;
- the same ordinary unit actor within each pair;
- the same reinforcement operation type; and
- the same inferred actor resource within each pair.

However, all six pairs have *different* bounded target-support atoms. The
required same-target-support gate fails for every row, not merely for a subset.

## Corrected interpretation

This falsifies the initial interpretation based on one inspected action pair.
Two first-step moves by the same unit are not necessarily alternate routes to
the same city. In all six stored PR68 cases they serve different grounded city
deficits. The scalar readout was therefore correct to reject them under its
same-target contract. Relaxing only the shared-resource rule would neither make
these pairs eligible nor preserve decision semantics.

The bottleneck is upstream candidate recall. The protected union spends its
single calibrated-per-action slot across the broad operation category, without
protecting an alternative in the scalar baseline's target scope. It can thus
recall a high-estimate move for another city while providing no alternative for
the actual scalar decision being evaluated.

## Next correction

Keep the readout's target identity and fail-closed resource rules unchanged.
Version the protected union so calibrated recall is conditioned on the scalar
baseline's operation target. Its bounded slot may recall only a distinct
candidate with the same operation type and exact target reference as scalar
top-1. Emit exact target-scoped opportunity and abstention counters. A fresh
shadow-only smoke must first prove target-scoped addition and grounded-
alternative yield; interval separation or preference should remain optional.

## Claim boundary

PR70 is post-hoc and cannot change PR68 or PR69. It diagnoses why their recalled
candidates were decision-incomparable but does not establish alternative value,
ranking quality, counterfactual benefit, gameplay, score, or win rate. It
changes no runtime behavior or authority.
