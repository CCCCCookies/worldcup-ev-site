from __future__ import annotations

import heapq
import math
from collections.abc import Iterable
from itertools import combinations

from .models import BestBet, Parlay


PICK_LABELS = {
    "home": "胜",
    "draw": "平",
    "away": "负",
}


def single_ev(probability: float, decimal_odds: float) -> float:
    return probability * decimal_odds - 1.0


def combo_ev(probabilities: Iterable[float], decimal_odds: Iterable[float]) -> float:
    factor = 1.0
    for probability, odds in zip(probabilities, decimal_odds):
        factor *= probability * odds
    return factor - 1.0


def best_bet_for_match(
    match_num: str,
    match_id: str,
    match_label: str,
    home_cn: str,
    away_cn: str,
    probabilities: dict[str, float],
    had_odds: dict[str, float | None],
    match_date: str = "",
    match_time: str = "",
) -> BestBet:
    options: list[BestBet] = []
    for pick in ("home", "draw", "away"):
        probability = probabilities[pick]
        odds = had_odds[pick]
        if odds is None:
            continue
        factor = probability * odds
        team_or_draw = home_cn if pick == "home" else away_cn if pick == "away" else "平局"
        options.append(
            BestBet(
                match_num=match_num,
                match_id=match_id,
                match_label=match_label,
                pick=pick,
                pick_label=PICK_LABELS[pick],
                team_or_draw=team_or_draw,
                probability=probability,
                odds=odds,
                ev=factor - 1.0,
                factor=factor,
                match_date=match_date,
                match_time=match_time,
                model_probability=probability,
            )
        )
    if not options:
        raise ValueError(f"Match {match_num} has no HAD odds")
    return max(options, key=lambda item: item.ev)


def max_probability_pick_for_match(
    match_num: str,
    match_id: str,
    match_label: str,
    home_cn: str,
    away_cn: str,
    probabilities: dict[str, float],
    had_odds: dict[str, float | None],
    accuracy: float = 0.5,
    match_date: str = "",
    match_time: str = "",
) -> BestBet:
    pick = max(("home", "draw", "away"), key=lambda key: probabilities[key])
    odds = had_odds[pick]
    if odds is None:
        raise ValueError(f"Match {match_num} has no HAD odds for max-probability pick")
    model_probability = probabilities[pick]
    factor = accuracy * odds
    team_or_draw = home_cn if pick == "home" else away_cn if pick == "away" else "平局"
    return BestBet(
        match_num=match_num,
        match_id=match_id,
        match_label=match_label,
        pick=pick,
        pick_label=PICK_LABELS[pick],
        team_or_draw=team_or_draw,
        probability=accuracy,
        odds=odds,
        ev=factor - 1.0,
        factor=factor,
        match_date=match_date,
        match_time=match_time,
        model_probability=model_probability,
    )


def top_parlays_by_legs(
    bets: list[BestBet],
    min_legs: int = 2,
    max_legs: int = 8,
    limit: int = 10,
) -> dict[int, list[Parlay]]:
    sorted_bets = sorted(bets, key=lambda bet: bet.factor, reverse=True)
    results: dict[int, list[Parlay]] = {}
    max_legs = min(max_legs, len(sorted_bets))
    for legs in range(min_legs, max_legs + 1):
        results[legs] = _top_k_for_leg_count(sorted_bets, legs, limit)
    return results


def all_parlays_by_legs(
    bets: list[BestBet],
    min_legs: int = 2,
    max_legs: int | None = None,
) -> dict[int, list[Parlay]]:
    if not bets:
        return {}
    sorted_bets = sorted(bets, key=lambda bet: bet.factor, reverse=True)
    max_legs = min(max_legs or len(sorted_bets), len(sorted_bets))
    results: dict[int, list[Parlay]] = {}
    for legs in range(min_legs, max_legs + 1):
        scored = [
            (math.prod(bet.factor for bet in selected), list(selected))
            for selected in combinations(sorted_bets, legs)
        ]
        scored.sort(key=lambda item: item[0], reverse=True)
        rows = [_build_parlay(legs, rank, selected) for rank, (_, selected) in enumerate(scored, start=1)]
        if rows:
            results[legs] = rows
    return results


def _top_k_for_leg_count(bets: list[BestBet], legs: int, limit: int) -> list[Parlay]:
    if legs <= 0 or len(bets) < legs or limit <= 0:
        return []

    initial = tuple(range(legs))
    initial_log_score = _log_factor(bets, initial)
    heap: list[tuple[float, tuple[int, ...]]] = [(-initial_log_score, initial)]
    seen = {initial}
    rows: list[Parlay] = []

    while heap and len(rows) < limit:
        negative_score, indices = heapq.heappop(heap)
        selected = [bets[index] for index in indices]
        rows.append(_build_parlay(legs, len(rows) + 1, selected))

        for position in range(legs - 1, -1, -1):
            next_index = indices[position] + 1
            if position < legs - 1 and next_index >= indices[position + 1]:
                continue
            if next_index >= len(bets):
                continue
            candidate = list(indices)
            candidate[position] = next_index
            candidate_tuple = tuple(candidate)
            if candidate_tuple in seen:
                continue
            seen.add(candidate_tuple)
            heapq.heappush(heap, (-_log_factor(bets, candidate_tuple), candidate_tuple))

    return rows


def _log_factor(bets: list[BestBet], indices: tuple[int, ...]) -> float:
    return sum(math.log(max(bets[index].factor, 1e-300)) for index in indices)


def _build_parlay(legs: int, rank: int, selected: list[BestBet]) -> Parlay:
    probability = math.prod(bet.probability for bet in selected)
    decimal_odds = math.prod(bet.odds for bet in selected)
    ev = probability * decimal_odds - 1.0
    return Parlay(
        legs=legs,
        rank=rank,
        ev=ev,
        probability=probability,
        decimal_odds=decimal_odds,
        match_nums=[bet.match_num for bet in selected],
        picks=[bet.pick_label for bet in selected],
        matches=[bet.match_label for bet in selected],
        leg_details=[
            f"{bet.match_num} {bet.match_label} {bet.pick_label}({bet.team_or_draw})@{bet.odds:.2f}"
            for bet in selected
        ],
    )
