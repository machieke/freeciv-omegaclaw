# Native Gameplay Parity Corpus

This directory is reserved for generated movement/combat parity corpora and
reports. No corpus is committed yet because no separately installed native
gameplay comparator has been identified and reviewed.

`scripts/run_gdo_gameplay_parity.py` accepts a JSON object with:

```json
{
  "schema_version": "1.0",
  "corpus_id": "generated-visible-subset-v1",
  "generator_identity": "generator binary or image digest",
  "ruleset_digest": "ruleset content digest",
  "cases": [
    {
      "case_id": "stable unique ID",
      "kind": "movement",
      "payload": {},
      "derived_result": {}
    }
  ]
}
```

The separately installed comparator receives one canonical JSON request per
process invocation on standard input and returns:

```json
{
  "protocol_version": "freeciv-native-gameplay-parity/1.0",
  "oracle_identity": "the configured binary or image identity",
  "request_id": "the unchanged request ID",
  "result": {}
}
```

The runner compares native and independently derived results byte-canonically,
sorts cases by ID, records every mismatch, and exits non-zero on any mismatch.
An empty corpus is rejected. Generated fixtures must contain factual inputs and
outputs only and require the licensing review recorded in
`docs/licensing/freeciv_algorithm_boundary.md` before being committed.
