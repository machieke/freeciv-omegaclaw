# FreeCiv proxy integration contract

This document freezes the working transport boundary reused by the PLN-FreeCiv agent.
The companion machine fixture is `contracts/freeciv-proxy/v1/contract.json`.

## Pinned reference

The Phase 0 reference was inspected at `freeciv-llm` commit
`26ba7124249f34fd3050ef29bf191bd4d8808018`. Runs must record the actual external
commit or immutable image digest in their manifest. The repository does not assume where
that checkout lives; `FREECIV_LLM_ROOT` is an optional discovery override.

## Connection

The complete WebSocket endpoint is supplied by `FREECIV_WS_URL` or
`FREECIV_PROXY_WS`. It is normally the proxy route `/llmsocket/<proxy-port>` and is used
verbatim.

The handshake is a top-level object:

```json
{"type":"llm_connect","agent_id":"agent","api_token":"token","game_id":"game","port":6001}
```

`type`, `agent_id`, and `api_token` are required. Authentication succeeds only after an
`auth_success` response. A runner must not send actions before this response.

## State

HTTP state is requested at:

```text
GET /api/game/{game_id}/state?player_id={player_id}&format={format}
```

The legacy adapter uses `llm_optimized`. M2 requires a versioned complete authoritative
DTO with research progress, production/rates, resources, map visibility, ruleset identity,
and server buildability data. Missing authoritative data is `unavailable`; it is never
interpreted as permission or zero unless the engine explicitly reports zero.

## Legal actions

Legal actions are requested at:

```text
GET /api/game/{game_id}/legal_actions?player_id={player_id}
```

The action gate compares the full normalized payload. Actor-only matching is invalid.
M2 adds a source snapshot ID and a digest of this exact legal-action collection.

## Action submission

After authentication, actions use:

```json
{"type":"action","action":{"action_type":"unit_move","actor_id":7,"dest_x":2,"dest_y":3}}
```

`unit_id` is normalized to `actor_id`. `end_turn` uses the same envelope with only
`action_type`. A submitted action is successful only when an engine/proxy result is
observed; a successful socket write is not an action result.

## Turn advancement

The loop sends the canonical `end_turn` action and waits for an observed state with a turn
strictly greater than the prior turn. Blind sleep and iteration count are not turn
advancement. Reconnect resumes from observed state.

## Configuration

| Variable | Meaning | Secret |
|---|---|---|
| `FREECIV_PROXY_URL` | Complete HTTP proxy origin | no |
| `FREECIV_WS_URL` / `FREECIV_PROXY_WS` | Complete proxy WebSocket endpoint | no |
| `FREECIV_API_TOKEN` | Proxy authentication token | yes |
| `FREECIV_GAME_ID` | Game identity | no |
| `FREECIV_PLAYER_ID` | Perspective/actor player | no |
| `FREECIV_AGENT_ID` | Proxy agent identity | no |
| `FREECIV_CIVSERVER_PORT` | Backing server port | no |
| `FREECIV_LLM_ROOT` | Optional external source discovery path | no |

Secrets are never written to a manifest or domain event.

## Contract change policy

Changes to endpoint, envelope, required fields, or state meaning require a new fixture
version. DTO additions may remain in v1 only when old consumers safely preserve or ignore
them. State fields that affect legality or ground truth cannot be silently defaulted.

