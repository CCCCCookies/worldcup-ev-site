from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class BestBet:
    match_num: str
    match_id: str
    match_label: str
    pick: str
    pick_label: str
    team_or_draw: str
    probability: float
    odds: float
    ev: float
    factor: float
    match_date: str = ""
    match_time: str = ""
    model_probability: float = 0.0


@dataclass(frozen=True)
class Parlay:
    legs: int
    rank: int
    ev: float
    probability: float
    decimal_odds: float
    match_nums: list[str]
    picks: list[str]
    matches: list[str]
    leg_details: list[str]


@dataclass(frozen=True)
class NearestSale:
    match_date: str
    match_count: int
    singles: list[BestBet]
    parlays_by_legs: dict[int, list[Parlay]]


@dataclass(frozen=True)
class AccuracyStrategy:
    accuracy: float
    single_top: list[BestBet]
    nearest_sale: NearestSale


@dataclass(frozen=True)
class OddsRow:
    match_num: str
    match_id: str
    match_date: str
    match_time: str
    home_cn: str
    away_cn: str
    home_en: str
    away_en: str
    probabilities: dict[str, float]
    had_odds: dict[str, float | None]
    hhad_odds: dict[str, float | str | None]
    participates_ev: bool
    skip_reason: str
    had_update: str


@dataclass(frozen=True)
class OddsSummary:
    matches: list[OddsRow]
    skipped: list[OddsRow]


@dataclass(frozen=True)
class SourceStatus:
    last_refresh_at: str
    polyalpha_generated_at: str
    sporttery_last_update: str
    sporttery_total_count: int
    valid_had_matches: int
    skipped_matches: int
    stale: bool = False
    errors: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Snapshot:
    status: SourceStatus
    polyalpha: dict[str, Any]
    odds: OddsSummary
    single_top: list[BestBet]
    parlays_by_legs: dict[int, list[Parlay]]
    nearest_sale: NearestSale
    accuracy_strategy: AccuracyStrategy
