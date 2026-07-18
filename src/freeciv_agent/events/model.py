"""Canonical atom, proof, and plan fixture helpers shared by tests/emitters."""

import copy

from .schema import structural_hash


CRISP_TV = {"strength": 1.0, "confidence": 0.99}


def truth_value(strength=1.0, confidence=0.99):
    return {"strength": float(strength), "confidence": float(confidence)}


def atom(atom_id, predicate, args, tv=None, crisp=True, provenance_ids=None):
    return {
        "atom_id": str(atom_id),
        "predicate": str(predicate),
        "args": list(args),
        "tv": copy.deepcopy(tv or CRISP_TV),
        "crisp": bool(crisp),
        "provenance_ids": list(provenance_ids or []),
    }


def proof_node(node_id, kind, value, satisfied, rule_applied=None,
               premise_node_refs=None, tv=None, crisp=True,
               grounded_result=None, formula=None, dampening_lambda=None,
               scope=None, rule_source=None):
    row = {
        "node_id": str(node_id),
        "kind": kind,
        "atom": copy.deepcopy(value),
        "tv": copy.deepcopy(tv or value["tv"]),
        "crisp": bool(crisp),
        "satisfied": bool(satisfied),
        "rule_applied": rule_applied,
        "premise_node_refs": list(premise_node_refs or []),
        "subtree_hash": "",
    }
    if grounded_result is not None:
        row["grounded_result"] = grounded_result
    if scope is not None:
        row["scope"] = scope
    if rule_source is not None:
        row["rule_source"] = rule_source
    if formula is not None:
        row["formula"] = formula
    if dampening_lambda is not None:
        row["dampening_lambda"] = dampening_lambda
    return row


def proof_tree(root_node_id, nodes):
    """Populate canonical subtree hashes and return a lossless proof tree."""
    rows = {node["node_id"]: copy.deepcopy(node) for node in nodes}
    if len(rows) != len(nodes):
        raise ValueError("proof node IDs must be unique")
    visiting = set()

    def visit(node_id):
        if node_id not in rows:
            raise ValueError("unknown proof node reference: {}".format(node_id))
        if rows[node_id].get("subtree_hash"):
            return rows[node_id]["subtree_hash"]
        if node_id in visiting:
            # A cycle node is a typed leaf. Reference cycles in the serialized graph
            # are invalid because they cannot have a finite structural hash.
            raise ValueError("cyclic serialized proof reference: {}".format(node_id))
        visiting.add(node_id)
        premise_hashes = [visit(ref) for ref in rows[node_id]["premise_node_refs"]]
        material = copy.deepcopy(rows[node_id])
        material.pop("subtree_hash", None)
        material.pop("node_id", None)
        material.pop("premise_node_refs", None)
        material["premise_subtree_hashes"] = premise_hashes
        rows[node_id]["subtree_hash"] = structural_hash(material)
        visiting.remove(node_id)
        return rows[node_id]["subtree_hash"]

    root_hash = visit(root_node_id)
    for node_id in sorted(rows):
        visit(node_id)
    return {
        "root_node_id": root_node_id,
        "nodes": [rows[node_id] for node_id in sorted(rows)],
        "structural_hash": root_hash,
    }


def deduplicate_proof_tree(proof):
    """Store structurally identical subtrees once and remap premise references."""
    rows = {node["node_id"]: copy.deepcopy(node) for node in proof["nodes"]}
    by_hash = {}
    representative = {}
    for node_id in sorted(rows):
        subtree = rows[node_id]["subtree_hash"]
        by_hash.setdefault(subtree, node_id)
        representative[node_id] = by_hash[subtree]
    kept = {}
    for node_id in sorted(rows):
        canonical = representative[node_id]
        if canonical != node_id:
            continue
        node = rows[node_id]
        node["premise_node_refs"] = [representative[ref] for ref in node["premise_node_refs"]]
        kept[node_id] = node
    root = representative[proof["root_node_id"]]
    return {"root_node_id": root, "nodes": [kept[key] for key in sorted(kept)],
            "structural_hash": proof["structural_hash"]}


def plan_step(step_id, kind, target, predicted_turn, actual_turn=None,
              status="PENDING", cost=0, spatial=None):
    return {
        "step_id": str(step_id), "kind": str(kind), "target": target,
        "predicted_turn": int(predicted_turn), "actual_turn": actual_turn,
        "status": status, "cost": float(cost), "spatial": spatial,
    }


def plan(plan_id, goal_atom_id, proof_hash, snapshot_id, steps,
         status="ACTIVE", feasibility_grade=1.0, scheduler_cost=0,
         cost_profile="turns-to-goal", ledger=None, assumptions=None,
         reused=None, rederived=None):
    return {
        "plan_id": str(plan_id), "status": status,
        "goal_atom_id": str(goal_atom_id), "source_proof_hash": proof_hash,
        "snapshot_id": str(snapshot_id),
        "feasibility_grade": float(feasibility_grade),
        "scheduler_cost": float(scheduler_cost), "cost_profile": cost_profile,
        "steps": list(steps), "ledger": list(ledger or []),
        "assumptions": list(assumptions or []),
        "reused_subtree_hashes": list(reused or []),
        "rederived_subtree_hashes": list(rederived or []),
    }
