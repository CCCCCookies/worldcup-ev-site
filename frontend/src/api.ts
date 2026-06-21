import type { AccuracyStrategy, BacktestReport, BestBet, DashboardData, NearestSale, OddsSummary, Parlay, PolyalphaData, Status } from "./types";

async function getJson<T>(url: string): Promise<T> {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`);
  }
  return response.json() as Promise<T>;
}

function staticDashboardUrl(): string {
  const base = import.meta.env.BASE_URL || "./";
  return `${base.replace(/\/?$/, "/")}data/dashboard.json`;
}

export async function loadDashboard(): Promise<DashboardData> {
  const host = window.location.hostname;
  if (host === "127.0.0.1" || host === "localhost") {
    try {
      return await loadApiDashboard();
    } catch {
      return await getJson<DashboardData>(staticDashboardUrl());
    }
  }
  return await getJson<DashboardData>(staticDashboardUrl());
}

async function loadApiDashboard(): Promise<DashboardData> {
  const [status, polyalpha, odds, singles, parlays, nearestSale, accuracyStrategy, backtest] = await Promise.all([
    getJson<Status>("/api/status"),
    getJson<PolyalphaData>("/api/polyalpha"),
    getJson<OddsSummary>("/api/odds"),
    getJson<BestBet[]>("/api/ev/singles?limit=10"),
    getJson<Record<string, Parlay[]>>("/api/ev/parlays?min_legs=2&max_legs=8&limit=10"),
    getJson<NearestSale>("/api/ev/nearest-sale"),
    getJson<AccuracyStrategy>("/api/ev/accuracy-strategy"),
    getJson<BacktestReport>("/api/backtest")
  ]);
  return { status, polyalpha, odds, singles, parlays, nearestSale, accuracyStrategy, backtest };
}

export async function refreshNow(): Promise<Status> {
  const host = window.location.hostname;
  if (host !== "127.0.0.1" && host !== "localhost") {
    throw new Error("公网静态版由 GitHub Actions 每小时自动更新；需要立即刷新时请手动运行 GitHub Actions。");
  }
  const response = await fetch("/api/admin/refresh", { method: "POST" });
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`);
  }
  return response.json() as Promise<Status>;
}
