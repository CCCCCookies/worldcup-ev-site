from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .service import DataService, build_backtest_report, load_odds_history, snapshot_to_dict


LOCAL_HOSTS = {"127.0.0.1", "::1", "localhost"}
FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"

data_service = DataService()


def create_app(service: DataService | None = None, enable_scheduler: bool = True) -> FastAPI:
    active_service = service or data_service
    app = FastAPI(title="World Cup EV Dashboard", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    scheduler: BackgroundScheduler | None = None
    if enable_scheduler:
        scheduler = BackgroundScheduler(timezone="Asia/Shanghai")

        @app.on_event("startup")
        def start_refresh_job() -> None:
            scheduler.add_job(
                active_service.refresh,
                "interval",
                hours=1,
                id="refresh_worldcup_data",
                replace_existing=True,
                max_instances=1,
                next_run_time=datetime.now(),
            )
            scheduler.start()

        @app.on_event("shutdown")
        def stop_refresh_job() -> None:
            scheduler.shutdown(wait=False)

    @app.get("/api/status")
    def status() -> dict:
        return asdict(active_service.snapshot.status)

    @app.get("/api/polyalpha")
    def polyalpha() -> dict:
        return active_service.snapshot.polyalpha

    @app.get("/api/odds")
    def odds() -> dict:
        return asdict(active_service.snapshot.odds)

    @app.get("/api/ev/singles")
    def single_ev(limit: int = Query(default=10, ge=1, le=50)) -> list[dict]:
        return [asdict(row) for row in active_service.snapshot.single_top[:limit]]

    @app.get("/api/ev/parlays")
    def parlay_ev(
        min_legs: int = Query(default=2, ge=2, le=8),
        max_legs: int = Query(default=8, ge=2, le=8),
        limit: int = Query(default=10, ge=1, le=50),
    ) -> dict[str, list[dict]]:
        if max_legs < min_legs:
            raise HTTPException(status_code=400, detail="max_legs must be >= min_legs")
        rows = active_service.snapshot.parlays_by_legs
        return {
            str(legs): [asdict(row) for row in rows.get(legs, [])[:limit]]
            for legs in range(min_legs, max_legs + 1)
        }

    @app.get("/api/ev/nearest-sale")
    def nearest_sale() -> dict:
        data = asdict(active_service.snapshot.nearest_sale)
        data["parlays_by_legs"] = {
            str(legs): rows for legs, rows in data["parlays_by_legs"].items()
        }
        return data

    @app.get("/api/ev/accuracy-strategy")
    def accuracy_strategy() -> dict:
        data = asdict(active_service.snapshot.accuracy_strategy)
        data["nearest_sale"]["parlays_by_legs"] = {
            str(legs): rows for legs, rows in data["nearest_sale"]["parlays_by_legs"].items()
        }
        return data

    @app.get("/api/snapshot")
    def snapshot() -> dict:
        return snapshot_to_dict(active_service.snapshot)

    @app.get("/api/backtest")
    def backtest() -> dict:
        return build_backtest_report(active_service.snapshot.polyalpha, load_odds_history())

    @app.post("/api/admin/refresh")
    def refresh(request: Request) -> dict:
        host = request.client.host if request.client else ""
        if host not in LOCAL_HOSTS:
            raise HTTPException(status_code=403, detail="manual refresh is only allowed from localhost")
        return asdict(active_service.refresh().status)

    if FRONTEND_DIST.exists():
        assets_dir = FRONTEND_DIST / "assets"
        if assets_dir.exists():
            app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

        @app.get("/{path:path}")
        def frontend(path: str) -> FileResponse:
            target = FRONTEND_DIST / path
            if path and target.exists() and target.is_file():
                return FileResponse(target)
            return FileResponse(FRONTEND_DIST / "index.html")

    return app


app = create_app()
