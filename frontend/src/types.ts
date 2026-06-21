export interface Status {
  last_refresh_at: string;
  polyalpha_generated_at: string;
  sporttery_last_update: string;
  sporttery_total_count: number;
  valid_had_matches: number;
  skipped_matches: number;
  stale: boolean;
  errors: string[];
}

export interface BestBet {
  match_num: string;
  match_id: string;
  match_label: string;
  pick: "home" | "draw" | "away";
  pick_label: string;
  team_or_draw: string;
  probability: number;
  odds: number;
  ev: number;
  factor: number;
  match_date?: string;
  match_time?: string;
}

export interface Parlay {
  legs: number;
  rank: number;
  ev: number;
  probability: number;
  decimal_odds: number;
  match_nums: string[];
  picks: string[];
  matches: string[];
  leg_details: string[];
}

export interface NearestSale {
  match_date: string;
  match_count: number;
  singles: BestBet[];
  parlays_by_legs: Record<string, Parlay[]>;
}

export interface AccuracyStrategy {
  accuracy: number;
  single_top: BestBet[];
  nearest_sale: NearestSale;
}

export interface BacktestSingle {
  result_date: string;
  sporttery_date: string;
  sporttery_time: string;
  match_num: string;
  match_id: string;
  match_label: string;
  score: string;
  actual_pick: "home" | "draw" | "away";
  actual_label: string;
  selected_pick: "home" | "draw" | "away";
  selected_label: string;
  team_or_draw: string;
  probability: number;
  odds: number;
  ev: number;
  hit: boolean;
  profit: number;
  source: string;
  captured_at: string;
  had_update: string;
}

export interface BacktestUnpricedMatch {
  result_date: string;
  match_label: string;
  score: string;
  reason: string;
}

export interface BacktestParlay {
  legs: number;
  rank: number;
  ev: number;
  probability: number;
  decimal_odds: number;
  hit: boolean;
  profit: number;
  match_nums: string[];
  matches: string[];
  leg_details: string[];
}

export interface BacktestDay {
  date: string;
  summary: {
    single_stake: number;
    single_profit: number;
    single_roi: number;
    parlay_stake: number;
    parlay_profit: number;
    parlay_roi: number;
    priced_matches: number;
    unpriced_matches: number;
  };
  singles: BacktestSingle[];
  unpriced_matches: BacktestUnpricedMatch[];
  parlays_by_legs: Record<string, BacktestParlay[]>;
}

export interface BacktestReport {
  generated_at: string;
  history_record_count: number;
  completed_match_count: number;
  priced_match_count: number;
  unpriced_match_count: number;
  days: BacktestDay[];
  notes: string[];
}

export interface OddsRow {
  match_num: string;
  match_id: string;
  match_date: string;
  match_time: string;
  home_cn: string;
  away_cn: string;
  home_en: string;
  away_en: string;
  probabilities: Record<"home" | "draw" | "away", number>;
  had_odds: Record<"home" | "draw" | "away", number | null>;
  hhad_odds: Record<"home" | "draw" | "away" | "goal_line", number | string | null>;
  participates_ev: boolean;
  skip_reason: string;
  had_update: string;
}

export interface OddsSummary {
  matches: OddsRow[];
  skipped: OddsRow[];
}

export interface PolyalphaData {
  generated_at: string;
  report_date: string;
  title_probability: Record<string, number>;
  reach_knockout_R32: Record<string, number>;
  group_standings: Record<string, Record<string, number>>;
  golden_boot: {
    top_scorer_probability?: Record<string, number>;
    expected_goals?: Record<string, number>;
  };
  schedule: Array<{
    date: string;
    stage: string;
    matchday?: number;
    group?: string;
    home: string;
    away: string;
    probs?: [number, number, number];
    pick?: number;
    status?: string;
  }>;
  predictions: Array<{
    date: string;
    home: string;
    away: string;
    p_home: number;
    p_draw: number;
    p_away: number;
    p_over_2_5?: number;
    p_btts?: number;
  }>;
  bracket?: {
    champion?: string;
    rounds?: Array<{
      round: string;
      matches: Array<{ a: string; b: string; winner: string; p?: number; m?: number }>;
    }>;
  };
  title_comparison?: Record<string, { model?: number; market?: number; edge?: number }>;
  movement?: Record<string, unknown>;
  live_accuracy?: unknown;
}

export interface DashboardData {
  status: Status;
  polyalpha: PolyalphaData;
  odds: OddsSummary;
  singles: BestBet[];
  parlays: Record<string, Parlay[]>;
  nearestSale: NearestSale;
  accuracyStrategy: AccuracyStrategy;
  backtest: BacktestReport;
  staticMode?: boolean;
}
