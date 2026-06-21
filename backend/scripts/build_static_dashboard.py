from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_DIR = BACKEND_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.service import DataService, dashboard_data_from_snapshot, load_odds_history  # noqa: E402


DEFAULT_OUTPUT = PROJECT_DIR / "frontend" / "public" / "data" / "dashboard.json"


def build_static_dashboard(output_path: Path = DEFAULT_OUTPUT) -> dict:
    service = DataService()
    snapshot = service.refresh()
    history = load_odds_history()
    payload = dashboard_data_from_snapshot(snapshot, history=history, static_mode=True)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Build static dashboard JSON for GitHub Pages.")
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Path to write dashboard.json.",
    )
    args = parser.parse_args()
    payload = build_static_dashboard(args.output)
    status = payload["status"]
    print(
        "generated dashboard.json "
        f"polyalpha={status.get('polyalpha_generated_at', '')} "
        f"sporttery={status.get('sporttery_last_update', '')} "
        f"valid_had={status.get('valid_had_matches', 0)} "
        f"stale={status.get('stale', False)}"
    )


if __name__ == "__main__":
    main()
