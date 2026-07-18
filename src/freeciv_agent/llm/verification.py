"""Exactly-one-sink factual verification and non-queryable quarantine."""

import datetime
import threading

from ..events.schema import structural_hash
from .model import QuarantineEntry, VerifiedClaim


def _utc_now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")


class QuarantineStore(object):
    """Audit-only append store. It intentionally exposes no belief lookup API."""
    def __init__(self):
        self._lock = threading.RLock()
        self._entries = []

    def append(self, entry):
        if not isinstance(entry, QuarantineEntry):
            raise TypeError("quarantine accepts QuarantineEntry")
        with self._lock:
            self._entries.append(entry)
        return entry

    def audit_entries(self):
        with self._lock:
            return tuple(self._entries)


class VerifiedBeliefSink(object):
    def __init__(self):
        self._claims = []

    def write(self, verified):
        if not isinstance(verified, VerifiedClaim) or not verified.usable:
            raise PermissionError("only verified believe claims may enter belief sink")
        self._claims.append(verified)
        return verified

    def claims(self):
        return tuple(self._claims)


class ClaimRouter(object):
    CLOSED_WORLD = frozenset({
        "has-tech", "owns-city", "owns-unit", "unit-type", "unit-at",
        "city-at", "tile-visible", "buildable",
    })

    def __init__(self, catalog, crisp_facts, uncertain_beliefs=None,
                 quarantine=None, belief_sink=None, model="unknown", model_config=None,
                 clock=None):
        self.catalog = catalog
        self.crisp_facts = frozenset((str(predicate), tuple(arguments))
                                     for predicate, arguments in crisp_facts)
        self.uncertain_beliefs = uncertain_beliefs
        self.quarantine = quarantine or QuarantineStore()
        self.belief_sink = belief_sink or VerifiedBeliefSink()
        self.model = str(model)
        self.model_config = tuple(sorted((model_config or {}).items()))
        self.clock = clock or _utc_now

    @staticmethod
    def _atom(predicate, arguments, exists, provenance_ids=()):
        strength = 1.0 if exists else 0.0
        return {
            "args": list(arguments),
            "atom_id": "evidence-" + structural_hash([predicate, list(arguments), exists])[:20],
            "crisp": True, "predicate": str(predicate),
            "provenance_ids": list(provenance_ids),
            "tv": {"confidence": 0.99, "strength": strength},
        }

    def route(self, proposal_id, claim):
        valid, reason = self.catalog.validate_claim(claim)
        key = (claim.predicate, tuple(claim.arguments))
        evidence = []
        if not valid:
            verdict, check = "quarantine", reason
        elif key in self.crisp_facts:
            evidence.append(self._atom(claim.predicate, claim.arguments, True))
            verdict = "believe" if claim.asserted else "quarantine"
            check = ("authoritative_exact_match" if claim.asserted
                     else "authoritative_contradiction")
        elif claim.predicate in self.CLOSED_WORLD:
            evidence.append(self._atom(claim.predicate, claim.arguments, False))
            verdict = "quarantine" if claim.asserted else "believe"
            check = ("authoritative_closed_world_false" if claim.asserted
                     else "authoritative_closed_world_negation")
        elif self.uncertain_beliefs is not None:
            from ..beliefs import BeliefKey
            belief = self.uncertain_beliefs.get(BeliefKey(claim.predicate, tuple(claim.arguments)))
            if belief is not None and belief.confidence >= 0.5:
                evidence.append(belief.atom())
                agrees = (belief.strength >= 0.5) == claim.asserted
                verdict, check = ("believe", "uncertain_supported") if agrees else (
                    "disbelieve", "uncertain_contradiction")
            else:
                verdict, check = "quarantine", "insufficient_evidence"
        else:
            verdict, check = "quarantine", "unverifiable_claim"
        verified = VerifiedClaim(claim, proposal_id, verdict, check, tuple(evidence))
        if verdict == "believe":
            self.belief_sink.write(verified)
        elif verdict == "quarantine":
            entry = QuarantineEntry(
                "quarantine-" + structural_hash([
                    proposal_id, claim.claim_id, claim.text, check])[:20],
                proposal_id, claim, check, tuple(evidence), self.model,
                self.model_config, self.clock())
            self.quarantine.append(entry)
        return verified

    def route_proposal(self, proposal):
        return tuple(self.route(proposal.proposal_id, claim) for claim in proposal.claims)

    def emit_route_proposal(self, proposal, writer, turn, prompt_version,
                            caused_by=None):
        proposal_event = writer.emit("llm_proposal", turn, {
            "claims": [{
                "atom": None, "claim_id": claim.claim_id, "text": claim.text,
            } for claim in proposal.claims],
            "goals": [goal.to_dict() for goal in proposal.goals],
            "model": self.model, "prompt_version": prompt_version,
            "proposal_id": proposal.proposal_id,
        }, caused_by=caused_by)
        results = []
        for verified in self.route_proposal(proposal):
            verification = writer.emit("verification", turn, {
                "check": verified.check, "claim_id": verified.claim.claim_id,
                "evidence_atom_ids": [row["atom_id"] for row in verified.evidence_atoms],
                "proposal_id": proposal.proposal_id,
                "verdict": verified.verdict,
                "verification_id": "verification-" + structural_hash([
                    proposal.proposal_id, verified.claim.claim_id, verified.verdict])[:20],
            }, caused_by=[proposal_event["event_id"]])
            quarantine_event = None
            if verified.verdict == "quarantine":
                # route_proposal appended this entry; refresh the index for the claim.
                entry = next(item for item in reversed(self.quarantine.audit_entries())
                             if item.claim.claim_id == verified.claim.claim_id
                             and item.proposal_id == proposal.proposal_id)
                quarantine_event = writer.emit(
                    "quarantine", turn, entry.to_dict(),
                    caused_by=[verification["event_id"]])
            results.append((verified, verification, quarantine_event))
        return proposal_event, tuple(results)
