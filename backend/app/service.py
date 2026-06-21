from __future__ import annotations

import csv
import json
import math
import re
import subprocess
import threading
from dataclasses import asdict, replace
from datetime import datetime, time
from itertools import combinations
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from .calculations import all_parlays_by_legs, best_bet_for_match, max_probability_pick_for_match, top_parlays_by_legs
from .models import AccuracyStrategy, BestBet, NearestSale, OddsRow, OddsSummary, Parlay, Snapshot, SourceStatus


POLYALPHA_INDEX_URL = "https://worldcup.polyalpha.cn/"
POLYALPHA_DATA_URL = "https://worldcup.polyalpha.cn/data.json"
SPORTTERY_URLS = (
    (
        "https://webapi.sporttery.cn/gateway/jc/football/"
        "getMatchCalculatorV1.qry?poolCode=hhad,had&channel=c"
    ),
    (
        "https://webapi.sporttery.cn/gateway/uniform/football/"
        "getMatchCalculatorV1.qry?channel=c&poolCode=hhad,had"
    ),
)
CACHE_DIR = Path(__file__).resolve().parents[1] / "data"
CACHE_FILE = CACHE_DIR / "latest_snapshot.json"
ODDS_HISTORY_FILE = CACHE_DIR / "odds_history.json"
PROJECT_ROOT = Path(__file__).resolve().parents[3]
LEGACY_SINGLES_CSV = PROJECT_ROOT / "output" / "spreadsheet" / "worldcup_ev_20260611_215335" / "single_match_ev.csv"
ASIA_SHANGHAI = ZoneInfo("Asia/Shanghai")
PICK_ORDER = ("home", "draw", "away")
PICK_LABELS_ZH = {"home": "胜", "draw": "平", "away": "负"}


class DataService:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._snapshot: Snapshot | None = None

    @property
    def snapshot(self) -> Snapshot:
        with self._lock:
            if self._snapshot is None:
                cached = _load_cached_snapshot()
                if cached is not None:
                    self._snapshot = cached
                    save_odds_history_from_snapshot(cached)
                else:
                    self._snapshot = empty_snapshot("尚未完成首次数据刷新")
            return self._snapshot

    def refresh(self) -> Snapshot:
        try:
            polyalpha_data = fetch_json(POLYALPHA_DATA_URL)
            polyalpha_index = fetch_text(POLYALPHA_INDEX_URL)
            sporttery_data = fetch_sporttery_json()
            snapshot = build_snapshot_from_payloads(polyalpha_data, polyalpha_index, sporttery_data)
            with self._lock:
                self._snapshot = snapshot
            _save_cached_snapshot(snapshot)
            save_odds_history_from_snapshot(snapshot)
            return snapshot
        except Exception as exc:  # noqa: BLE001 - keep stale data instead of taking down the app
            message = f"{type(exc).__name__}: {exc}"
            with self._lock:
                current = self._snapshot or _load_cached_snapshot()
                if current is None:
                    current = empty_snapshot(message)
                stale_status = replace(
                    current.status,
                    stale=True,
                    errors=[*current.status.errors, message][-5:],
                )
                self._snapshot = replace(current, status=stale_status)
                return self._snapshot


def fetch_text(url: str, referer: str | None = None) -> str:
    headers = {"User-Agent": "Mozilla/5.0"}
    if referer:
        headers["Referer"] = referer
    try:
        with urlopen(Request(url, headers=headers), timeout=45) as response:
            return response.read().decode("utf-8")
    except Exception:
        return fetch_text_with_node(url, referer=referer)


def fetch_text_with_node(url: str, referer: str | None = None) -> str:
    script = r"""
const url = process.argv[1];
const referer = process.argv[2] || "";
const headers = {
  "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0 Safari/537.36",
  "Accept": "application/json,text/plain,*/*",
  "Cache-Control": "no-cache",
  "Pragma": "no-cache"
};
if (referer) {
  headers.Referer = referer;
  headers.Origin = new URL(referer).origin;
}
fetch(url, { headers }).then(async (response) => {
  const text = await response.text();
  if (!response.ok) {
    console.error(text.slice(0, 1000));
    process.exit(response.status || 1);
  }
  process.stdout.write(text);
}).catch((error) => {
  console.error(error && error.stack ? error.stack : String(error));
  process.exit(1);
});
"""
    completed = subprocess.run(
        ["node", "-e", script, url, referer or ""],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=45,
    )
    return completed.stdout


def fetch_json(url: str, referer: str | None = None) -> dict[str, Any]:
    return json.loads(fetch_text(url, referer=referer))


def fetch_sporttery_json() -> dict[str, Any]:
    errors: list[str] = []
    for url in SPORTTERY_URLS:
        try:
            return fetch_json(url, referer="https://www.sporttery.cn/jc/jsq/zqspf/")
        except Exception as exc:  # noqa: BLE001 - try the second official gateway
            errors.append(f"{url}: {type(exc).__name__}: {exc}")
    raise RuntimeError("All official Sporttery gateways failed: " + " | ".join(errors))


def build_snapshot_from_payloads(
    polyalpha_data: dict[str, Any],
    polyalpha_index_html: str,
    sporttery_data: dict[str, Any],
    now: datetime | None = None,
) -> Snapshot:
    now = now or datetime.now(ASIA_SHANGHAI)
    zh_to_en = parse_team_map(polyalpha_index_html)
    en_to_zh = {english: chinese for chinese, english in zh_to_en.items()}
    predictions = build_prediction_map(polyalpha_data)
    odds_rows, best_bets = build_odds_rows(sporttery_data, predictions, zh_to_en)
    odds_rows = mark_expired_rows(odds_rows, now)
    odds_rows = filter_display_rows(odds_rows, now)
    best_bets = filter_future_bets(best_bets, now)
    append_not_returned_rows(odds_rows, predictions, en_to_zh, min_date=now.date().isoformat())

    single_top = sorted(best_bets, key=lambda bet: bet.ev, reverse=True)[:10]
    parlays_by_legs = top_parlays_by_legs(best_bets, min_legs=2, max_legs=8, limit=10)
    nearest_sale = build_nearest_sale(best_bets)
    accuracy_strategy = build_accuracy_strategy(odds_rows, now=now)
    skipped = [row for row in odds_rows if not row.participates_ev]

    status = SourceStatus(
        last_refresh_at=datetime.now().isoformat(timespec="seconds"),
        polyalpha_generated_at=str(polyalpha_data.get("generated_at", "")),
        sporttery_last_update=str(sporttery_data.get("value", {}).get("lastUpdateTime", "")),
        sporttery_total_count=int(sporttery_data.get("value", {}).get("totalCount") or 0),
        valid_had_matches=len(best_bets),
        skipped_matches=len(skipped),
        stale=False,
        errors=[],
    )
    return Snapshot(
        status=status,
        polyalpha=standardize_polyalpha(polyalpha_data),
        odds=OddsSummary(matches=odds_rows, skipped=skipped),
        single_top=single_top,
        parlays_by_legs=parlays_by_legs,
        nearest_sale=nearest_sale,
        accuracy_strategy=accuracy_strategy,
    )


def parse_team_map(index_html: str) -> dict[str, str]:
    match = re.search(r"const\s+TEAM\s*=\s*(\{.*?\});", index_html, flags=re.S)
    if not match:
        return {}
    raw_map = json.loads(match.group(1))
    return {values[1]: team for team, values in raw_map.items() if len(values) >= 2}


def build_prediction_map(polyalpha_data: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    predictions: dict[tuple[str, str], dict[str, Any]] = {}
    for row in polyalpha_data.get("predictions", []):
        home = str(row["home"])
        away = str(row["away"])
        predictions[(home, away)] = row
    return predictions


def build_odds_rows(
    sporttery_data: dict[str, Any],
    predictions: dict[tuple[str, str], dict[str, Any]],
    zh_to_en: dict[str, str],
) -> tuple[list[OddsRow], list[Any]]:
    rows: list[OddsRow] = []
    best_bets = []
    for day in sporttery_data.get("value", {}).get("matchInfoList", []):
        for match in day.get("subMatchList", []):
            row, best = build_odds_row(match, predictions, zh_to_en)
            rows.append(row)
            if best is not None:
                best_bets.append(best)
    return rows, best_bets


def build_odds_row(
    match: dict[str, Any],
    predictions: dict[tuple[str, str], dict[str, Any]],
    zh_to_en: dict[str, str],
) -> tuple[OddsRow, Any | None]:
    home_cn = str(match.get("homeTeamAllName", ""))
    away_cn = str(match.get("awayTeamAllName", ""))
    home_en = zh_to_en.get(home_cn, "")
    away_en = zh_to_en.get(away_cn, "")
    prediction = find_prediction(predictions, home_en, away_en)
    probabilities = prediction_to_probabilities(prediction)
    had = match.get("had") or {}
    hhad = match.get("hhad") or {}
    had_odds = {"home": to_float(had.get("h")), "draw": to_float(had.get("d")), "away": to_float(had.get("a"))}
    hhad_odds = {
        "home": to_float(hhad.get("h")),
        "draw": to_float(hhad.get("d")),
        "away": to_float(hhad.get("a")),
        "goal_line": hhad.get("goalLine") or None,
    }
    skip_reason = skip_reason_for_match(match, home_en, away_en, prediction, had_odds)
    participates = skip_reason == ""
    match_num = str(match.get("matchNumStr", ""))
    match_id = str(match.get("matchId", ""))
    match_label = f"{home_cn} vs {away_cn}"
    row = OddsRow(
        match_num=match_num,
        match_id=match_id,
        match_date=str(match.get("matchDate", "")),
        match_time=str(match.get("matchTime", ""))[:5],
        home_cn=home_cn,
        away_cn=away_cn,
        home_en=home_en,
        away_en=away_en,
        probabilities=probabilities,
        had_odds=had_odds,
        hhad_odds=hhad_odds,
        participates_ev=participates,
        skip_reason=skip_reason,
        had_update=f"{had.get('updateDate', '')} {had.get('updateTime', '')}".strip(),
    )
    if not participates:
        return row, None
    return (
        row,
        best_bet_for_match(
            match_num,
            match_id,
            match_label,
            home_cn,
            away_cn,
            probabilities,
            had_odds,
            match_date=row.match_date,
            match_time=row.match_time,
        ),
    )


def build_nearest_sale(best_bets: list[BestBet]) -> NearestSale:
    dated_bets = [bet for bet in best_bets if bet.match_date]
    if not dated_bets:
        return NearestSale(match_date="", match_count=0, singles=[], parlays_by_legs={})
    nearest_date = min(bet.match_date for bet in dated_bets)
    singles = sorted(
        [bet for bet in dated_bets if bet.match_date == nearest_date],
        key=lambda bet: bet.ev,
        reverse=True,
    )
    return NearestSale(
        match_date=nearest_date,
        match_count=len(singles),
        singles=singles,
        parlays_by_legs=all_parlays_by_legs(singles, min_legs=2, max_legs=len(singles)),
    )


def build_accuracy_strategy(rows: list[OddsRow], now: datetime | None = None, accuracy: float = 0.5) -> AccuracyStrategy:
    now = now or datetime.now(ASIA_SHANGHAI)
    bets: list[BestBet] = []
    for row in mark_expired_rows(rows, now):
        if not row.participates_ev:
            continue
        try:
            bets.append(
                max_probability_pick_for_match(
                    row.match_num,
                    row.match_id,
                    f"{row.home_cn} vs {row.away_cn}",
                    row.home_cn,
                    row.away_cn,
                    row.probabilities,
                    row.had_odds,
                    accuracy=accuracy,
                    match_date=row.match_date,
                    match_time=row.match_time,
                )
            )
        except ValueError:
            continue
    bets = filter_future_bets(bets, now)
    return AccuracyStrategy(
        accuracy=accuracy,
        single_top=sorted(bets, key=lambda bet: bet.ev, reverse=True)[:10],
        nearest_sale=build_nearest_sale(bets),
    )


def build_backtest_report(polyalpha: dict[str, Any], history: dict[str, Any] | None = None) -> dict[str, Any]:
    history = history if history is not None else load_odds_history()
    live_accuracy = polyalpha.get("live_accuracy") or {}
    results = live_accuracy.get("results") or []
    by_match = live_accuracy.get("by_match") or {}
    days: dict[str, dict[str, Any]] = {}
    priced_count = 0
    unpriced_count = 0

    for result in sorted(results, key=lambda row: (str(row.get("date", "")), str(row.get("home", "")), str(row.get("away", "")))):
        result_date = str(result.get("date", ""))
        home_en = str(result.get("home", ""))
        away_en = str(result.get("away", ""))
        key = match_history_key(result_date, home_en, away_en)
        result_info = by_match.get(key, {})
        score = str(result_info.get("score") or result.get("score") or "")
        actual_pick = actual_pick_from_result(result, result_info)
        day = days.setdefault(result_date, empty_backtest_day(result_date))

        if actual_pick is None:
            day["unpriced_matches"].append(
                unpriced_backtest_match(result_date, home_en, away_en, score, "缺少赛果方向")
            )
            unpriced_count += 1
            continue

        record = history.get(key)
        if record is None:
            day["unpriced_matches"].append(
                unpriced_backtest_match(result_date, home_en, away_en, score, "缺少历史体彩HAD赔率")
            )
            unpriced_count += 1
            continue

        try:
            single = settled_backtest_single(record, actual_pick, score)
        except (KeyError, TypeError, ValueError):
            day["unpriced_matches"].append(
                unpriced_backtest_match(result_date, home_en, away_en, score, "历史赔率或概率不完整")
            )
            unpriced_count += 1
            continue

        day["singles"].append(single)
        priced_count += 1

    finalized_days = [finalize_backtest_day(day) for day in days.values()]
    finalized_days.sort(key=lambda row: row["date"])
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "history_record_count": len(history),
        "completed_match_count": len(results),
        "priced_match_count": priced_count,
        "unpriced_match_count": unpriced_count,
        "days": finalized_days,
        "notes": [
            "回测只结算本地已保存赛前体彩HAD赔率的比赛。",
            "缺少历史赔率的已赛比赛会列出赛果，但不计入盈亏。",
            "所有单场和每个串关组合默认按1元投入计算。",
        ],
    }


def empty_backtest_day(result_date: str) -> dict[str, Any]:
    return {
        "date": result_date,
        "summary": {
            "single_stake": 0,
            "single_profit": 0.0,
            "single_roi": 0.0,
            "parlay_stake": 0,
            "parlay_profit": 0.0,
            "parlay_roi": 0.0,
            "priced_matches": 0,
            "unpriced_matches": 0,
        },
        "singles": [],
        "unpriced_matches": [],
        "parlays_by_legs": {},
    }


def finalize_backtest_day(day: dict[str, Any]) -> dict[str, Any]:
    singles = sorted(day["singles"], key=lambda row: row["ev"], reverse=True)
    parlays_by_legs = build_backtest_parlays(singles)
    parlay_rows = [row for rows in parlays_by_legs.values() for row in rows]
    single_profit = sum(row["profit"] for row in singles)
    parlay_profit = sum(row["profit"] for row in parlay_rows)
    single_stake = len(singles)
    parlay_stake = len(parlay_rows)
    day["singles"] = singles
    day["parlays_by_legs"] = parlays_by_legs
    day["summary"] = {
        "single_stake": single_stake,
        "single_profit": single_profit,
        "single_roi": single_profit / single_stake if single_stake else 0.0,
        "parlay_stake": parlay_stake,
        "parlay_profit": parlay_profit,
        "parlay_roi": parlay_profit / parlay_stake if parlay_stake else 0.0,
        "priced_matches": single_stake,
        "unpriced_matches": len(day["unpriced_matches"]),
    }
    return day


def build_backtest_parlays(singles: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    results: dict[str, list[dict[str, Any]]] = {}
    max_legs = min(8, len(singles))
    for legs in range(2, max_legs + 1):
        rows = []
        for selected in combinations(singles, legs):
            probability = math.prod(float(row["probability"]) for row in selected)
            decimal_odds = math.prod(float(row["odds"]) for row in selected)
            hit = all(bool(row["hit"]) for row in selected)
            rows.append(
                {
                    "legs": legs,
                    "rank": 0,
                    "ev": probability * decimal_odds - 1.0,
                    "probability": probability,
                    "decimal_odds": decimal_odds,
                    "hit": hit,
                    "profit": decimal_odds - 1.0 if hit else -1.0,
                    "match_nums": [row["match_num"] for row in selected],
                    "matches": [row["match_label"] for row in selected],
                    "leg_details": [
                        (
                            f'{row["match_num"]} {row["match_label"]} '
                            f'买{row["selected_label"]}({row["team_or_draw"]})@{float(row["odds"]):.2f} '
                            f'{"命中" if row["hit"] else "未中"}'
                        )
                        for row in selected
                    ],
                }
            )
        rows.sort(key=lambda row: row["ev"], reverse=True)
        for rank, row in enumerate(rows, start=1):
            row["rank"] = rank
        if rows:
            results[str(legs)] = rows
    return results


def settled_backtest_single(record: dict[str, Any], actual_pick: str, score: str) -> dict[str, Any]:
    probabilities = {
        "home": float(record["probabilities"]["home"]),
        "draw": float(record["probabilities"]["draw"]),
        "away": float(record["probabilities"]["away"]),
    }
    had_odds = {
        "home": float(record["had_odds"]["home"]),
        "draw": float(record["had_odds"]["draw"]),
        "away": float(record["had_odds"]["away"]),
    }
    home_cn = str(record.get("home_cn") or record.get("home_en") or "")
    away_cn = str(record.get("away_cn") or record.get("away_en") or "")
    match_label = f"{home_cn} vs {away_cn}"
    bet = best_bet_for_match(
        str(record.get("match_num", "")),
        str(record.get("match_id", "")),
        match_label,
        home_cn,
        away_cn,
        probabilities,
        had_odds,
        match_date=str(record.get("sporttery_date", "")),
        match_time=str(record.get("sporttery_time", "")),
    )
    hit = bet.pick == actual_pick
    return {
        "result_date": str(record.get("result_date", "")),
        "sporttery_date": str(record.get("sporttery_date", "")),
        "sporttery_time": str(record.get("sporttery_time", "")),
        "match_num": bet.match_num,
        "match_id": bet.match_id,
        "match_label": bet.match_label,
        "score": score,
        "actual_pick": actual_pick,
        "actual_label": actual_pick_label(actual_pick, home_cn, away_cn),
        "selected_pick": bet.pick,
        "selected_label": bet.pick_label,
        "team_or_draw": bet.team_or_draw,
        "probability": bet.probability,
        "odds": bet.odds,
        "ev": bet.ev,
        "hit": hit,
        "profit": bet.odds - 1.0 if hit else -1.0,
        "source": str(record.get("source", "")),
        "captured_at": str(record.get("captured_at", "")),
        "had_update": str(record.get("had_update", "")),
    }


def unpriced_backtest_match(result_date: str, home_en: str, away_en: str, score: str, reason: str) -> dict[str, str]:
    return {
        "result_date": result_date,
        "match_label": f"{home_en} vs {away_en}",
        "score": score,
        "reason": reason,
    }


def actual_pick_from_result(result: dict[str, Any], result_info: dict[str, Any]) -> str | None:
    pick = actual_pick_from_idx(result_info.get("actual_idx"))
    if pick is not None:
        return pick
    actual = str(result.get("actual", ""))
    home = str(result.get("home", ""))
    away = str(result.get("away", ""))
    if actual.lower() == "draw":
        return "draw"
    if actual.startswith(home):
        return "home"
    if actual.startswith(away):
        return "away"
    return None


def actual_pick_from_idx(value: Any) -> str | None:
    try:
        return PICK_ORDER[int(value)]
    except (TypeError, ValueError, IndexError):
        return None


def actual_pick_label(pick: str, home: str, away: str) -> str:
    if pick == "home":
        return f"{home}胜"
    if pick == "away":
        return f"{away}胜"
    return "平"


def match_history_key(result_date: str, home_en: str, away_en: str) -> str:
    return f"{str(result_date).strip()}|{str(home_en).strip()}|{str(away_en).strip()}"


def odds_history_records_from_snapshot(snapshot: Snapshot) -> dict[str, dict[str, Any]]:
    prediction_dates = prediction_dates_by_match(snapshot.polyalpha)
    records: dict[str, dict[str, Any]] = {}
    captured_at = snapshot.status.last_refresh_at or datetime.now().isoformat(timespec="seconds")
    for row in snapshot.odds.matches:
        if not row.participates_ev or not row.home_en or not row.away_en:
            continue
        if any(value is None for value in row.had_odds.values()):
            continue
        result_date = prediction_dates.get((row.home_en, row.away_en)) or row.match_date
        key = match_history_key(result_date, row.home_en, row.away_en)
        records[key] = {
            "result_date": result_date,
            "sporttery_date": row.match_date,
            "sporttery_time": row.match_time,
            "match_num": row.match_num,
            "match_id": row.match_id,
            "home_cn": row.home_cn,
            "away_cn": row.away_cn,
            "home_en": row.home_en,
            "away_en": row.away_en,
            "probabilities": row.probabilities,
            "had_odds": row.had_odds,
            "had_update": row.had_update,
            "captured_at": captured_at,
            "source": "site_snapshot",
        }
    return records


def prediction_dates_by_match(polyalpha: dict[str, Any]) -> dict[tuple[str, str], str]:
    dates: dict[tuple[str, str], str] = {}
    for row in polyalpha.get("predictions", []):
        home = str(row.get("home", ""))
        away = str(row.get("away", ""))
        result_date = str(row.get("date", ""))
        if home and away and result_date:
            dates[(home, away)] = result_date
    return dates


def save_odds_history_from_snapshot(snapshot: Snapshot) -> None:
    new_records = odds_history_records_from_snapshot(snapshot)
    if not new_records:
        return
    history = load_odds_history()
    history.update(new_records)
    write_odds_history(history)


def load_odds_history() -> dict[str, dict[str, Any]]:
    history: dict[str, dict[str, Any]] = {}
    if ODDS_HISTORY_FILE.exists():
        try:
            raw = json.loads(ODDS_HISTORY_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            raw = {}
        records = raw.get("records", raw) if isinstance(raw, dict) else {}
        if isinstance(records, dict):
            history.update(records)
    history.update(load_legacy_odds_history())
    return history


def write_odds_history(history: dict[str, dict[str, Any]]) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "records": history,
    }
    ODDS_HISTORY_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def load_legacy_odds_history() -> dict[str, dict[str, Any]]:
    if not LEGACY_SINGLES_CSV.exists():
        return {}
    records: dict[str, dict[str, Any]] = {}
    with LEGACY_SINGLES_CSV.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            result_date = str(row.get("polyalpha_date", ""))
            home_en = str(row.get("home_en", ""))
            away_en = str(row.get("away_en", ""))
            if not result_date or not home_en or not away_en:
                continue
            key = match_history_key(result_date, home_en, away_en)
            records[key] = {
                "result_date": result_date,
                "sporttery_date": str(row.get("sporttery_date", "")),
                "sporttery_time": str(row.get("sporttery_time", "")),
                "match_num": str(row.get("match_num", "")),
                "match_id": str(row.get("match_id", "")),
                "home_cn": str(row.get("home_cn", "")),
                "away_cn": str(row.get("away_cn", "")),
                "home_en": home_en,
                "away_en": away_en,
                "probabilities": {
                    "home": to_float(row.get("p_home")),
                    "draw": to_float(row.get("p_draw")),
                    "away": to_float(row.get("p_away")),
                },
                "had_odds": {
                    "home": to_float(row.get("odds_home")),
                    "draw": to_float(row.get("odds_draw")),
                    "away": to_float(row.get("odds_away")),
                },
                "had_update": str(row.get("had_update", "")),
                "captured_at": "2026-06-11T21:53:47",
                "source": "legacy_csv_20260611",
            }
    return records


def rebuild_best_bets_from_odds_rows(rows: list[OddsRow], now: datetime | None = None) -> list[BestBet]:
    bets: list[BestBet] = []
    now = now or datetime.now(ASIA_SHANGHAI)
    for row in mark_expired_rows(rows, now):
        if not row.participates_ev:
            continue
        try:
            bets.append(
                best_bet_for_match(
                    row.match_num,
                    row.match_id,
                    f"{row.home_cn} vs {row.away_cn}",
                    row.home_cn,
                    row.away_cn,
                    row.probabilities,
                    row.had_odds,
                    match_date=row.match_date,
                    match_time=row.match_time,
                )
            )
        except ValueError:
            continue
    return filter_future_bets(bets, now)


def mark_expired_rows(rows: list[OddsRow], now: datetime) -> list[OddsRow]:
    marked: list[OddsRow] = []
    for row in rows:
        if row.participates_ev and match_has_started(row.match_date, row.match_time, now):
            marked.append(replace(row, participates_ev=False, skip_reason="match_already_started"))
        else:
            marked.append(row)
    return marked


def filter_display_rows(rows: list[OddsRow], now: datetime) -> list[OddsRow]:
    today = now.date().isoformat()
    return [
        row
        for row in rows
        if row.skip_reason != "team_name_unmatched"
        and (
            not row.match_date
            or (row.match_date >= today and not match_has_started(row.match_date, row.match_time, now))
        )
    ]


def filter_future_bets(best_bets: list[BestBet], now: datetime) -> list[BestBet]:
    return [bet for bet in best_bets if not match_has_started(bet.match_date, bet.match_time, now)]


def match_has_started(match_date: str, match_time: str, now: datetime) -> bool:
    if not match_date:
        return False
    try:
        parsed_date = datetime.strptime(match_date, "%Y-%m-%d").date()
    except ValueError:
        return False
    parsed_time = time.min
    if match_time:
        for pattern in ("%H:%M", "%H:%M:%S"):
            try:
                parsed_time = datetime.strptime(match_time, pattern).time()
                break
            except ValueError:
                continue
    kickoff = datetime.combine(parsed_date, parsed_time, tzinfo=ASIA_SHANGHAI)
    return kickoff <= now


def find_prediction(
    predictions: dict[tuple[str, str], dict[str, Any]],
    home_en: str,
    away_en: str,
) -> dict[str, Any] | None:
    direct = predictions.get((home_en, away_en))
    if direct is not None:
        return direct
    reverse = predictions.get((away_en, home_en))
    if reverse is None:
        return None
    return {
        **reverse,
        "home": home_en,
        "away": away_en,
        "p_home": reverse["p_away"],
        "p_draw": reverse["p_draw"],
        "p_away": reverse["p_home"],
    }


def prediction_to_probabilities(prediction: dict[str, Any] | None) -> dict[str, float]:
    if prediction is None:
        return {"home": 0.0, "draw": 0.0, "away": 0.0}
    return {
        "home": float(prediction["p_home"]),
        "draw": float(prediction["p_draw"]),
        "away": float(prediction["p_away"]),
    }


def skip_reason_for_match(
    match: dict[str, Any],
    home_en: str,
    away_en: str,
    prediction: dict[str, Any] | None,
    had_odds: dict[str, float | None],
) -> str:
    if not home_en or not away_en:
        return "team_name_unmatched"
    if prediction is None:
        return "polyalpha_prediction_unmatched"
    if not had_is_selling(match):
        return "HAD_not_selling_or_missing"
    if any(value is None for value in had_odds.values()):
        return "HAD_odds_empty"
    return ""


def had_is_selling(match: dict[str, Any]) -> bool:
    for pool in match.get("poolList", []):
        if str(pool.get("poolCode", "")).upper() == "HAD":
            return str(pool.get("poolStatus", "")).lower() == "selling"
    return False


def to_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def append_not_returned_rows(
    rows: list[OddsRow],
    predictions: dict[tuple[str, str], dict[str, Any]],
    en_to_zh: dict[str, str],
    min_date: str = "",
) -> None:
    seen = {(row.home_en, row.away_en) for row in rows if row.home_en and row.away_en}
    seen |= {(away, home) for home, away in seen}
    for (home_en, away_en), prediction in predictions.items():
        prediction_date = str(prediction.get("date", ""))
        if min_date and prediction_date and prediction_date < min_date:
            continue
        if (home_en, away_en) in seen:
            continue
        rows.append(
            OddsRow(
                match_num="",
                match_id="",
                match_date=prediction_date,
                match_time="",
                home_cn=en_to_zh.get(home_en, home_en),
                away_cn=en_to_zh.get(away_en, away_en),
                home_en=home_en,
                away_en=away_en,
                probabilities=prediction_to_probabilities(prediction),
                had_odds={"home": None, "draw": None, "away": None},
                hhad_odds={"home": None, "draw": None, "away": None, "goal_line": None},
                participates_ev=False,
                skip_reason="not_returned_by_sporttery_current_query",
                had_update="",
            )
        )


def standardize_polyalpha(polyalpha_data: dict[str, Any]) -> dict[str, Any]:
    simulation = polyalpha_data.get("simulation", {})
    return {
        "generated_at": polyalpha_data.get("generated_at", ""),
        "report_date": polyalpha_data.get("report_date", ""),
        "title_probability": polyalpha_data.get("title_final") or simulation.get("title_probability", {}),
        "reach_knockout_R32": simulation.get("reach_knockout_R32", {}),
        "group_standings": simulation.get("group_standings", {}),
        "golden_boot": simulation.get("golden_boot", {}),
        "schedule": polyalpha_data.get("schedule", []),
        "predictions": polyalpha_data.get("predictions", []),
        "bracket": polyalpha_data.get("bracket", {}),
        "title_comparison": polyalpha_data.get("title_comparison", {}),
        "movement": polyalpha_data.get("movement", {}),
        "live_accuracy": polyalpha_data.get("live_accuracy", {}),
    }


def snapshot_to_dict(snapshot: Snapshot) -> dict[str, Any]:
    data = asdict(snapshot)
    data["parlays_by_legs"] = {str(key): value for key, value in data["parlays_by_legs"].items()}
    data["nearest_sale"]["parlays_by_legs"] = {
        str(key): value for key, value in data["nearest_sale"]["parlays_by_legs"].items()
    }
    data["accuracy_strategy"]["nearest_sale"]["parlays_by_legs"] = {
        str(key): value
        for key, value in data["accuracy_strategy"]["nearest_sale"]["parlays_by_legs"].items()
    }
    return data


def dashboard_data_from_snapshot(
    snapshot: Snapshot,
    history: dict[str, Any] | None = None,
    static_mode: bool = False,
) -> dict[str, Any]:
    nearest_sale = asdict(snapshot.nearest_sale)
    nearest_sale["parlays_by_legs"] = {
        str(legs): rows for legs, rows in nearest_sale["parlays_by_legs"].items()
    }

    accuracy_strategy = asdict(snapshot.accuracy_strategy)
    accuracy_strategy["nearest_sale"]["parlays_by_legs"] = {
        str(legs): rows
        for legs, rows in accuracy_strategy["nearest_sale"]["parlays_by_legs"].items()
    }

    return {
        "status": asdict(snapshot.status),
        "polyalpha": snapshot.polyalpha,
        "odds": asdict(snapshot.odds),
        "singles": [asdict(row) for row in snapshot.single_top],
        "parlays": {
            str(legs): [asdict(row) for row in snapshot.parlays_by_legs.get(legs, [])]
            for legs in range(2, 9)
        },
        "nearestSale": nearest_sale,
        "accuracyStrategy": accuracy_strategy,
        "backtest": build_backtest_report(snapshot.polyalpha, history),
        "staticMode": static_mode,
    }


def empty_snapshot(error: str) -> Snapshot:
    return Snapshot(
        status=SourceStatus(
            last_refresh_at=datetime.now().isoformat(timespec="seconds"),
            polyalpha_generated_at="",
            sporttery_last_update="",
            sporttery_total_count=0,
            valid_had_matches=0,
            skipped_matches=0,
            stale=True,
            errors=[error],
        ),
        polyalpha=standardize_polyalpha({}),
        odds=OddsSummary(matches=[], skipped=[]),
        single_top=[],
        parlays_by_legs={legs: [] for legs in range(2, 9)},
        nearest_sale=NearestSale(match_date="", match_count=0, singles=[], parlays_by_legs={}),
        accuracy_strategy=AccuracyStrategy(
            accuracy=0.5,
            single_top=[],
            nearest_sale=NearestSale(match_date="", match_count=0, singles=[], parlays_by_legs={}),
        ),
    )


def _save_cached_snapshot(snapshot: Snapshot) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(json.dumps(snapshot_to_dict(snapshot), ensure_ascii=False, indent=2), encoding="utf-8")


def _load_cached_snapshot() -> Snapshot | None:
    if not CACHE_FILE.exists():
        return None
    return snapshot_from_dict(json.loads(CACHE_FILE.read_text(encoding="utf-8")))


def snapshot_from_dict(data: dict[str, Any], now: datetime | None = None) -> Snapshot:
    now = now or datetime.now(ASIA_SHANGHAI)
    status = SourceStatus(**data["status"])
    odds_rows = filter_display_rows(mark_expired_rows([OddsRow(**row) for row in data["odds"]["matches"]], now), now)
    skipped = [row for row in odds_rows if not row.participates_ev]
    current_bets = rebuild_best_bets_from_odds_rows(odds_rows, now)
    accuracy_strategy = build_accuracy_strategy(odds_rows, now=now)
    single_top = sorted(current_bets, key=lambda bet: bet.ev, reverse=True)[:10]
    parlays_by_legs = top_parlays_by_legs(current_bets, min_legs=2, max_legs=8, limit=10)
    status = replace(
        status,
        valid_had_matches=len(current_bets),
        skipped_matches=len(skipped),
    )
    if snapshot_is_older_than_today(status, now):
        status = replace(
            status,
            stale=True,
            errors=[*status.errors, "cached_snapshot_older_than_today"][-5:],
        )
    nearest_data = data.get("nearest_sale")
    if nearest_data is None:
        nearest_sale = build_nearest_sale(current_bets)
    else:
        nearest_sale = build_nearest_sale(current_bets)
    return Snapshot(
        status=status,
        polyalpha=data["polyalpha"],
        odds=OddsSummary(matches=odds_rows, skipped=skipped),
        single_top=single_top,
        parlays_by_legs=parlays_by_legs,
        nearest_sale=nearest_sale,
        accuracy_strategy=accuracy_strategy,
    )


def snapshot_is_older_than_today(status: SourceStatus, now: datetime) -> bool:
    today = now.date().isoformat()
    source_dates = [
        status.last_refresh_at[:10],
        status.polyalpha_generated_at[:10],
    ]
    return any(source_date and source_date < today for source_date in source_dates)
