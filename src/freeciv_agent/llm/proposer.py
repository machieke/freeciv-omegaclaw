"""Strict JSON proposer with bounded corrective retries and no guessed symbols."""

import copy
import json
import os

import jsonschema

from ..paths import repo_path
from .model import CandidateGoal, FactualClaim, Proposal


PROMPT_VERSION = "freeciv-constrained-proposer/1.0"
SCHEMA_PATH = repo_path("schemas", "freeciv-llm", "v1", "proposal.schema.json")


class ProposalError(ValueError):
    pass


class ProposalParser(object):
    def __init__(self, catalog):
        self.catalog = catalog
        with open(SCHEMA_PATH, encoding="utf-8") as stream:
            self.schema = json.load(stream)
        self.validator = jsonschema.Draft202012Validator(self.schema)

    def parse(self, raw):
        try:
            value = json.loads(raw)
        except (TypeError, ValueError) as exc:
            raise ProposalError("invalid_json: {}".format(exc))
        errors = sorted(self.validator.iter_errors(value), key=lambda item: list(item.path))
        if errors:
            raise ProposalError("schema: {}".format(errors[0].message))
        goals = tuple(CandidateGoal(
            row["goal_id"], row["target_id"], row["predicate"], tuple(row["arguments"]))
                      for row in value["goals"])
        claims = tuple(FactualClaim(
            row["claim_id"], row["text"], row["predicate"], tuple(row["arguments"]),
            row["asserted"]) for row in value["claims"])
        identifiers = [row.goal_id for row in goals]
        if len(identifiers) != len(set(identifiers)):
            raise ProposalError("duplicate_goal_id")
        claim_ids = [row.claim_id for row in claims]
        if len(claim_ids) != len(set(claim_ids)):
            raise ProposalError("duplicate_claim_id")
        for goal in goals:
            valid, reason = self.catalog.validate_goal(goal)
            if not valid:
                raise ProposalError("goal {}: {}".format(goal.goal_id, reason))
        for claim in claims:
            valid, reason = self.catalog.validate_claim(claim)
            if not valid:
                raise ProposalError("claim {}: {}".format(claim.claim_id, reason))
        if value["selection"] is not None and value["selection"] not in identifiers:
            raise ProposalError("selection_not_in_goals")
        return Proposal(value["proposal_id"], goals, claims, value["rationale"],
                        value["selection"])


class ConstrainedProposer(object):
    def __init__(self, client, catalog, model, max_corrections=1):
        self.client = client
        self.catalog = catalog
        self.model = str(model)
        self.max_corrections = int(max_corrections)
        self.parser = ProposalParser(catalog)

    def input_document(self, state_summary, plan_status=None, invalidations=None,
                       budgets=None):
        if not hasattr(state_summary, "to_dict"):
            raise TypeError("LLM state input must be a query summary DTO")
        return {
            "allowed": self.catalog.prompt_catalog(),
            "budgets": copy.deepcopy(budgets or {"max_goals": 5, "max_claims": 20}),
            "invalidations": copy.deepcopy(list(invalidations or [])),
            "output_schema": self.parser.schema,
            "plan_status": copy.deepcopy(plan_status),
            "prompt_version": PROMPT_VERSION,
            "state_query_results": state_summary.to_dict(),
        }

    def propose(self, state_summary, plan_status=None, invalidations=None, budgets=None):
        document = self.input_document(state_summary, plan_status, invalidations, budgets)
        error = None
        for attempt in range(self.max_corrections + 1):
            request = copy.deepcopy(document)
            if error is not None:
                request["correction"] = {
                    "attempt": attempt, "error": str(error),
                    "instruction": "Return one corrected JSON document only."}
            raw = self.client(request)
            try:
                return self.parser.parse(raw), attempt
            except ProposalError as exc:
                error = exc
        raise ProposalError("correction_exhausted: {}".format(error))
