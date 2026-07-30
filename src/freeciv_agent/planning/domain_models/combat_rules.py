"""Independent finite-duel mathematics for a declared combat-rule subset."""

import math
from dataclasses import dataclass


def _positive(value, name):
    if isinstance(value, bool):
        raise TypeError(
            "{} must be numeric".format(name))
    value = float(value)
    if not math.isfinite(value) or value <= 0.0:
        raise ValueError(
            "{} must be positive".format(name))
    return value


@dataclass(frozen=True)
class DuelTerminalOutcome:
    winner: str
    probability: float
    attacker_hits_taken: int
    defender_hits_taken: int
    attacker_hp_remaining: float
    defender_hp_remaining: float

    def to_dict(self):
        return {
            "attacker_hits_taken":
                self.attacker_hits_taken,
            "attacker_hp_remaining":
                float(self.attacker_hp_remaining),
            "defender_hits_taken":
                self.defender_hits_taken,
            "defender_hp_remaining":
                float(self.defender_hp_remaining),
            "probability":
                float(self.probability),
            "winner": self.winner,
        }


@dataclass(frozen=True)
class DuelDistribution:
    attacker_round_probability: float
    attacker_hits_to_destroy: int
    defender_hits_to_destroy: int
    terminal_outcomes: tuple
    attacker_max_hp: float
    defender_max_hp: float
    attacker_firepower: float
    defender_firepower: float

    @property
    def attacker_win_probability(self):
        return sum(
            row.probability
            for row in self.terminal_outcomes
            if row.winner == "attacker")

    @property
    def defender_win_probability(self):
        return sum(
            row.probability
            for row in self.terminal_outcomes
            if row.winner == "defender")

    def expected_friendly_shield_loss(
            self, attacker_shield_cost):
        cost = _positive(
            attacker_shield_cost,
            "attacker shield cost")
        value = sum(
            row.probability * cost * (
                1.0
                - row.attacker_hp_remaining
                / self.attacker_max_hp)
            for row in self.terminal_outcomes)
        return min(cost, max(0.0, value))

    def expected_enemy_shield_loss(
            self, defender_shield_cost):
        cost = _positive(
            defender_shield_cost,
            "defender shield cost")
        value = sum(
            row.probability * cost * (
                1.0
                - row.defender_hp_remaining
                / self.defender_max_hp)
            for row in self.terminal_outcomes)
        return min(cost, max(0.0, value))

    def to_dict(self):
        return {
            "attacker_hits_to_destroy":
                self.attacker_hits_to_destroy,
            "attacker_round_probability":
                float(
                    self.attacker_round_probability),
            "attacker_win_probability":
                float(
                    self.attacker_win_probability),
            "defender_hits_to_destroy":
                self.defender_hits_to_destroy,
            "defender_win_probability":
                float(
                    self.defender_win_probability),
            "terminal_outcomes": [
                row.to_dict()
                for row in self.terminal_outcomes],
        }


def finite_duel_distribution(
        attacker_power, defender_power,
        attacker_hp, defender_hp,
        attacker_firepower, defender_firepower,
        maximum_terminal_outcomes=10000):
    """Return the exact terminal distribution of this finite round process.

    This function is an independently written mathematical kernel.  Whether a
    Freeciv context maps to these six inputs is a separate, parity-gated domain
    question handled by the caller.
    """
    attacker_power = _positive(
        attacker_power, "attacker power")
    defender_power = _positive(
        defender_power, "defender power")
    attacker_hp = _positive(
        attacker_hp, "attacker HP")
    defender_hp = _positive(
        defender_hp, "defender HP")
    attacker_firepower = _positive(
        attacker_firepower,
        "attacker firepower")
    defender_firepower = _positive(
        defender_firepower,
        "defender firepower")
    if (isinstance(maximum_terminal_outcomes, bool)
            or not isinstance(maximum_terminal_outcomes, int)
            or maximum_terminal_outcomes < 2):
        raise ValueError(
            "maximum terminal outcomes must be an integer of at least two")
    probability = (
        attacker_power
        / (attacker_power + defender_power))
    attacker_hits = int(math.ceil(
        defender_hp / attacker_firepower))
    defender_hits = int(math.ceil(
        attacker_hp / defender_firepower))
    if attacker_hits + defender_hits > maximum_terminal_outcomes:
        raise ValueError(
            "finite duel exceeds the terminal-outcome budget")
    outcomes = []
    # Attacker reaches the required successful rounds after exactly `losses`
    # defender-success rounds.
    for losses in range(defender_hits):
        row_probability = (
            math.comb(
                attacker_hits + losses - 1,
                losses)
            * probability ** attacker_hits
            * (1.0 - probability) ** losses)
        outcomes.append(DuelTerminalOutcome(
            winner="attacker",
            probability=row_probability,
            attacker_hits_taken=losses,
            defender_hits_taken=attacker_hits,
            attacker_hp_remaining=max(
                0.0,
                attacker_hp
                - losses
                * defender_firepower),
            defender_hp_remaining=0.0))
    # Defender reaches its required successful rounds after exactly `wins`
    # attacker-success rounds.
    for wins in range(attacker_hits):
        row_probability = (
            math.comb(
                defender_hits + wins - 1,
                wins)
            * (1.0 - probability)
            ** defender_hits
            * probability ** wins)
        outcomes.append(DuelTerminalOutcome(
            winner="defender",
            probability=row_probability,
            attacker_hits_taken=(
                defender_hits),
            defender_hits_taken=wins,
            attacker_hp_remaining=0.0,
            defender_hp_remaining=max(
                0.0,
                defender_hp
                - wins
                * attacker_firepower)))
    outcomes = tuple(sorted(
        outcomes,
        key=lambda row: (
            row.winner,
            row.attacker_hits_taken,
            row.defender_hits_taken)))
    total = sum(
        row.probability for row in outcomes)
    if abs(total - 1.0) > 1e-9:
        raise ArithmeticError(
            "finite duel probability mass is not conserved")
    return DuelDistribution(
        attacker_round_probability=probability,
        attacker_hits_to_destroy=(
            attacker_hits),
        defender_hits_to_destroy=(
            defender_hits),
        terminal_outcomes=outcomes,
        attacker_max_hp=attacker_hp,
        defender_max_hp=defender_hp,
        attacker_firepower=(
            attacker_firepower),
        defender_firepower=(
            defender_firepower))
