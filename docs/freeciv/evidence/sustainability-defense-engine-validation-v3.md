# Sustainability and defense engine validation

Date: 2026-07-27

Pinned seed: `4543804-00`

Ruleset/opponent: `civ2civ3` / built-in experimental AI

Horizon: 480 turns

This is a same-seed diagnostic sequence, not a statistically reliable score or
win-rate claim. Each row contains one engine game. Its purpose is to reject
unsafe policy changes and confirm that the release candidate preserves the
best established behavior.

| Cohort | Policy under test | Score | Cities / population | Known tech / BPT | Gold / net | Final units | Disorder city-turns | Result |
|---|---|---:|---:|---:|---:|---:|---:|---|
| sustainability-confirmation-v12 | adapter 1.20 reference | 319 | 5 / 42 | 59 / 41 | 144 / -19 | 6 | 319 | reference |
| defense-confirmation-v3 | weakened garrison | 280 | 5 / 40 | 54 / 21 | 1562 / -31 | 2 | 695 | rejected |
| defense-confirmation-v4 | persistent global luxury | 205 | 5 / 43 | 49 / 0 | 659 / -18 | 1 | 1 | rejected: research starvation |
| defense-confirmation-v5 | anticipatory garrison plus global luxury | 214 | 5 / 45 | 50 / 11 | 263 / -17 | 6 | 72 | rejected |
| defense-confirmation-v6 | local `require_happy` CMA enabled | 319 | 5 / 42 | 59 / 41 | 144 / -19 | 6 | 319 | no behavioral gain; CMA infeasible |
| defense-confirmation-v8 | unrestricted replacement reserve | 196 | 2 / 15 | 53 / 5 | 1509 / -8 | 3 | 354 | rejected: blocked expansion |
| defense-confirmation-v9 | reserve gated after fifth city | 274 | 5 / 35 | 54 / 13 | 107 / -22 | 6 | 252 | rejected: attrition/research harm |
| defense-confirmation-v10 | adapter 1.24 release candidate; experiments disabled | 319 | 5 / 42 | 59 / 41 | 144 / -19 | 6 | 319 | accepted |

The accepted run completed 480/480 turns with zero rejected engine actions and
8,890 canonical events. It acquired four additional cities, completed 17
units, lost 10 defenders in combat, and ended with two of five cities
garrisoned. It also recorded 37 negative-food city-turns and four famine
city-turns. These remaining weaknesses are measured limitations; the rejected
experiments did not solve them without larger harm.

The `require_happy` result is specifically a feasibility finding. The proxy
accepted 13 packet-valid CMA requests in the enabled cohort, but subsequent
authoritative city state never showed the requested enabled template. The
release profile therefore sets both `city_happiness_governor_enabled` and
`disorder_luxury_recovery_enabled` to false.
