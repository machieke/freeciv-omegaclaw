# FDAS PR64a grounded-transition smoke launch correction

Date: 2026-08-03

The first PR64 launch from clean commit `a9ac5d9` stopped during configuration
loading, before a run directory or game was created. The PR64 seed overlay
declared only fixed seed `109007`, but the shared harness schema requires every
profile to contain at least 30 unique seeds even when execution later uses
`--limit-seeds 1`.

This is a pre-collection execution-contract defect. No FreeCiv process began,
no event, action, outcome, or metric was generated, and no model result was
inspected. The correction adds 29 unused seeds after `109007` so the profile is
schema-valid and adds `--limit-seeds 1` to the frozen command. It does not
change the first seed, horizon, model, artifact bindings, union thresholds,
auditor, authority boundary, or acceptance gates.

The corrected implementation must be committed and clean before collection.
The failed command and this correction remain documented; it is not an engine
attempt and cannot be included in readout-yield evidence.
