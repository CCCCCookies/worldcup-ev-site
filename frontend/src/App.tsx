import { useEffect, useMemo, useState } from "react";
import { loadDashboard, refreshNow } from "./api";
import type {
  AccuracyStrategy,
  BacktestDay,
  BacktestParlay,
  BacktestReport,
  BacktestSingle,
  BestBet,
  DashboardData,
  NearestSale,
  OddsRow,
  Parlay,
  PolyalphaData
} from "./types";
import "./styles.css";

const TEAM_ZH: Record<string, string> = {
  Mexico: "墨西哥",
  "South Africa": "南非",
  "South Korea": "韩国",
  "Czech Republic": "捷克",
  Canada: "加拿大",
  "Bosnia and Herzegovina": "波黑",
  "United States": "美国",
  Paraguay: "巴拉圭",
  Qatar: "卡塔尔",
  Switzerland: "瑞士",
  Brazil: "巴西",
  Morocco: "摩洛哥",
  Haiti: "海地",
  Scotland: "苏格兰",
  Australia: "澳大利亚",
  Turkey: "土耳其",
  Sweden: "瑞典",
  Tunisia: "突尼斯",
  Netherlands: "荷兰",
  Japan: "日本",
  Germany: "德国",
  "Curaçao": "库拉索",
  "Ivory Coast": "科特迪瓦",
  Ecuador: "厄瓜多尔",
  Spain: "西班牙",
  "Cape Verde": "佛得角",
  Belgium: "比利时",
  Egypt: "埃及",
  "Saudi Arabia": "沙特阿拉伯",
  Uruguay: "乌拉圭",
  Iran: "伊朗",
  "New Zealand": "新西兰",
  France: "法国",
  Senegal: "塞内加尔",
  Iraq: "伊拉克",
  Norway: "挪威",
  Argentina: "阿根廷",
  Algeria: "阿尔及利亚",
  Austria: "奥地利",
  Jordan: "约旦",
  Portugal: "葡萄牙",
  "DR Congo": "刚果(金)",
  England: "英格兰",
  Croatia: "克罗地亚",
  Ghana: "加纳",
  Panama: "巴拿马",
  Uzbekistan: "乌兹别克斯坦",
  Colombia: "哥伦比亚"
};

function pct(value?: number | null, digits = 1): string {
  if (value === undefined || value === null || Number.isNaN(value)) return "—";
  return `${(value * 100).toFixed(digits)}%`;
}

function num(value?: number | null, digits = 2): string {
  if (value === undefined || value === null || Number.isNaN(value)) return "—";
  return value.toFixed(digits);
}

function money(value?: number | null): string {
  if (value === undefined || value === null || Number.isNaN(value)) return "—";
  return (value >= 0 ? "+" : "") + value.toFixed(2);
}

function teamName(name: string): string {
  return TEAM_ZH[name] ?? name;
}

function topEntries(record: Record<string, number> | undefined, limit: number): Array<[string, number]> {
  return Object.entries(record ?? {})
    .sort((a, b) => b[1] - a[1])
    .slice(0, limit);
}

export default function App() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [error, setError] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [activeLeg, setActiveLeg] = useState("2");

  async function reload() {
    setLoading(true);
    try {
      setData(await loadDashboard());
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }

  async function forceRefresh() {
    setRefreshing(true);
    try {
      await refreshNow();
      await reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setRefreshing(false);
    }
  }

  useEffect(() => {
    void reload();
    const timer = window.setInterval(() => void reload(), 60_000);
    return () => window.clearInterval(timer);
  }, []);

  if (loading && !data) {
    return <div className="boot">正在加载世界杯赔率与期望值数据…</div>;
  }

  if (!data) {
    return (
      <main className="page">
        <div className="notice danger">加载失败：{error || "未知错误"}</div>
      </main>
    );
  }

  return (
      <main className="page">
        <Header data={data} error={error} refreshing={refreshing} onRefresh={forceRefresh} />
        <BacktestSection report={data.backtest} />
        <NearestSaleSection nearestSale={data.nearestSale} />
        <EvSection singles={data.singles} parlays={data.parlays} activeLeg={activeLeg} setActiveLeg={setActiveLeg} />
        <AccuracyStrategySection strategy={data.accuracyStrategy} />
        <OddsSection odds={data.odds.matches} />
      <PolyalphaSection polyalpha={data.polyalpha} />
      <footer className="foot">
        数据来源：PolyAlpha World Cup Predictions 与中国竞彩网公开接口。EV为模型概率和当前赔率下的理论期望，不构成投注建议。
      </footer>
    </main>
  );
}

function Header({
  data,
  error,
  refreshing,
  onRefresh
}: {
  data: DashboardData;
  error: string;
  refreshing: boolean;
  onRefresh: () => void;
}) {
  const status = data.status;
  const noticeText = headerNoticeText(status, error);
  return (
    <header className="top">
      <div className="top-title">
        <p className="eyebrow">World Cup 2026 · 体彩胜平负EV</p>
        <h1>世界杯赔率与期望值面板</h1>
        <p className="sub">每小时同步 PolyAlpha 预测和中国体彩胜平负赔率，只计算已开售HAD。</p>
      </div>
      <button className="refresh" onClick={onRefresh} disabled={refreshing || Boolean(data.staticMode)}>
        {data.staticMode ? "云端定时更新" : refreshing ? "刷新中…" : "立即刷新"}
      </button>
      <div className="metrics">
        <Metric label="有效HAD场次" value={String(status.valid_had_matches)} />
        <Metric label="跳过场次" value={String(status.skipped_matches)} />
        <Metric label="体彩返回" value={String(status.sporttery_total_count)} />
        <Metric label="数据状态" value={status.stale ? "使用缓存" : "正常"} tone={status.stale ? "warn" : "ok"} />
        {data.staticMode && <Metric label="部署模式" value="GitHub Pages" tone="ok" />}
      </div>
      <div className="source-line">
        <span>本地刷新：{status.last_refresh_at || "—"}</span>
        <span>PolyAlpha：{status.polyalpha_generated_at || "—"}</span>
        <span>体彩：{status.sporttery_last_update || "—"}</span>
      </div>
      {noticeText && (
        <div className="notice danger">
          {noticeText}
        </div>
      )}
    </header>
  );
}

function headerNoticeText(status: DashboardData["status"], error: string): string {
  if (error) {
    return "页面接口加载失败：" + error;
  }
  if (status.stale) {
    return "自动刷新外网数据失败，当前显示本地缓存；回测和历史赔率数据仍可用。";
  }
  if (status.errors.length > 0) {
    return "最近一次自动刷新有错误，已保留上一版可用数据。";
  }
  return "";
}

function Metric({ label, value, tone }: { label: string; value: string; tone?: "ok" | "warn" }) {
  return (
    <div className={`metric ${tone ?? ""}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function NearestSaleSection({ nearestSale }: { nearestSale: NearestSale }) {
  const parlayEntries = Object.entries(nearestSale.parlays_by_legs)
    .sort(([left], [right]) => Number(left) - Number(right))
    .filter(([, rows]) => rows.length > 0);
  const maxLeg = parlayEntries.length ? Number(parlayEntries[parlayEntries.length - 1][0]) : nearestSale.match_count;

  return (
    <section className="section nearest-section">
      <div className="section-head">
        <h2>最近可买比赛日：{nearestSale.match_date || "暂无"}</h2>
        <p>
          只统计当前体彩已返回且 HAD 正在售的最早比赛日期；当天 {nearestSale.match_count} 场，单场和 2串1 到 {maxLeg}串1
          全部按 EV 从高到低排列。
        </p>
      </div>
      {nearestSale.match_count === 0 ? (
        <div className="empty">当前没有可参与 EV 计算的 HAD 比赛。</div>
      ) : (
        <div className="nearest-grid">
          <div className="panel">
            <h3>当天单场最高期望选择（全部）</h3>
            <SingleBetTable rows={nearestSale.singles} />
          </div>
          <div className="nearest-parlay-groups">
            {parlayEntries.length === 0 ? (
              <div className="panel">
                <h3>当天串关</h3>
                <div className="empty">当天可买场次不足 2 场，不能组成串关。</div>
              </div>
            ) : (
              parlayEntries.map(([legs, rows]) => (
                <div className="panel nearest-group" key={legs}>
                  <h3>{legs}串1 全部组合（{rows.length}组）</h3>
                  <ParlayList rows={rows} />
                </div>
              ))
            )}
          </div>
        </div>
      )}
    </section>
  );
}

function SingleBetTable({ rows }: { rows: BestBet[] }) {
  return (
    <div className="table-wrap">
      <table className="compact-table">
        <thead>
          <tr>
            <th>排名</th>
            <th>比赛</th>
            <th>怎么买</th>
            <th>概率</th>
            <th>赔率</th>
            <th>EV</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={`${row.match_id}-${row.pick}`}>
              <td>{index + 1}</td>
              <td>
                <b>{row.match_num || "—"}</b> {row.match_time ? `${row.match_time} ` : ""}{row.match_label}
              </td>
              <td>买{row.pick_label}（{row.team_or_draw}）</td>
              <td>{pct(row.probability, 2)}</td>
              <td>{num(row.odds)}</td>
              <td className={row.ev >= 0 ? "positive" : "negative"}>{pct(row.ev, 2)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function AccuracyStrategySection({ strategy }: { strategy: AccuracyStrategy }) {
  const nearestSale = strategy.nearest_sale;
  const parlayEntries = Object.entries(nearestSale.parlays_by_legs)
    .sort(([left], [right]) => Number(left) - Number(right))
    .filter(([, rows]) => rows.length > 0);

  return (
    <section className="section accuracy-section">
      <div className="section-head">
        <h2>最大概率选项策略（按{pct(strategy.accuracy, 0)}准确率）</h2>
        <p>
          每场只买 PolyAlpha 胜/平/负里模型概率最大的选项，但理论命中率统一按 {pct(strategy.accuracy, 0)}
          估算；单场EV = {pct(strategy.accuracy, 0)} × 体彩赔率 - 1。
        </p>
      </div>
      <div className="nearest-grid">
        <div className="panel">
          <h3>单场期望前10</h3>
          <SingleBetTable rows={strategy.single_top} />
        </div>
        <div className="nearest-parlay-groups">
          <div className="panel">
            <h3>最近可买日：{nearestSale.match_date || "暂无"}（{nearestSale.match_count}场）</h3>
            {parlayEntries.length === 0 ? (
              <div className="empty">当天可买场次不足 2 场，不能组成串关。</div>
            ) : (
              parlayEntries.map(([legs, rows]) => (
                <div className="accuracy-parlay-group" key={legs}>
                  <h4>{legs}串1 全部组合（{rows.length}组）</h4>
                  <ParlayList rows={rows} />
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </section>
  );
}

function BacktestSection({ report }: { report: BacktestReport }) {
  const totalSingleProfit = report.days.reduce((sum, day) => sum + day.summary.single_profit, 0);
  const totalSingleStake = report.days.reduce((sum, day) => sum + day.summary.single_stake, 0);
  const totalParlayProfit = report.days.reduce((sum, day) => sum + day.summary.parlay_profit, 0);
  const totalParlayStake = report.days.reduce((sum, day) => sum + day.summary.parlay_stake, 0);

  return (
    <section className="section backtest-section">
      <div className="section-head">
        <h2>已完赛回测（按天）</h2>
        <p>
          只用本地保存过的赛前体彩HAD赔率结算；没有历史赔率的已完赛比赛只列出赛果，不计入盈利或亏损。
        </p>
      </div>
      <div className="metrics backtest-metrics">
        <Metric label="已完赛结果" value={String(report.completed_match_count)} />
        <Metric label="可结算场次" value={String(report.priced_match_count)} />
        <Metric label="缺历史赔率" value={String(report.unpriced_match_count)} tone={report.unpriced_match_count ? "warn" : "ok"} />
        <Metric label="历史赔率记录" value={String(report.history_record_count)} />
        <Metric label="单场总盈亏" value={money(totalSingleProfit)} tone={totalSingleProfit >= 0 ? "ok" : "warn"} />
        <Metric label="串关总盈亏" value={money(totalParlayProfit)} tone={totalParlayProfit >= 0 ? "ok" : "warn"} />
      </div>
      <div className="backtest-total">
        <span>单场总投入 {totalSingleStake}，ROI {pct(totalSingleStake ? totalSingleProfit / totalSingleStake : 0, 2)}</span>
        <span>串关总投入 {totalParlayStake}，ROI {pct(totalParlayStake ? totalParlayProfit / totalParlayStake : 0, 2)}</span>
      </div>
      {report.days.length === 0 ? (
        <div className="empty">PolyAlpha 当前没有返回已完赛赛果，暂时无法回测。</div>
      ) : (
        <div className="backtest-days">
          {report.days.map((day) => (
            <BacktestDayPanel day={day} key={day.date} />
          ))}
        </div>
      )}
      {report.notes.length > 0 && (
        <ul className="backtest-notes">
          {report.notes.map((note) => (
            <li key={note}>{note}</li>
          ))}
        </ul>
      )}
    </section>
  );
}

function BacktestDayPanel({ day }: { day: BacktestDay }) {
  const parlayEntries = Object.entries(day.parlays_by_legs)
    .sort(([left], [right]) => Number(left) - Number(right))
    .filter(([, rows]) => rows.length > 0);
  return (
    <div className="panel backtest-day">
      <div className="panel-title-row">
        <h3>{day.date} 回测</h3>
        <div className="day-summary">
          <span>单场 {day.summary.single_stake} 注 / {money(day.summary.single_profit)}</span>
          <span>串关 {day.summary.parlay_stake} 注 / {money(day.summary.parlay_profit)}</span>
          <span>缺赔率 {day.summary.unpriced_matches} 场</span>
        </div>
      </div>
      <h4>单场最佳EV选择</h4>
      <BacktestSingleTable rows={day.singles} />
      {day.unpriced_matches.length > 0 && (
        <div className="unpriced-box">
          <h4>已完赛但缺少历史体彩HAD赔率</h4>
          <div className="table-wrap">
            <table className="compact-table unpriced-table">
              <thead>
                <tr>
                  <th>比赛</th>
                  <th>比分</th>
                  <th>原因</th>
                </tr>
              </thead>
              <tbody>
                {day.unpriced_matches.map((row) => (
                  <tr key={row.match_label}>
                    <td>{row.match_label}</td>
                    <td>{row.score || "—"}</td>
                    <td>{row.reason}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
      <h4>当天串关结算</h4>
      {parlayEntries.length === 0 ? (
        <div className="empty">当天可结算单场少于 2 场，不能组成串关。</div>
      ) : (
        <div className="backtest-parlay-groups">
          {parlayEntries.map(([legs, rows]) => (
            <div className="backtest-parlay-group" key={legs}>
              <h5>{legs}串1（{rows.length} 组）</h5>
              <BacktestParlayList rows={rows} />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function BacktestSingleTable({ rows }: { rows: BacktestSingle[] }) {
  if (rows.length === 0) {
    return <div className="empty">当天没有可结算的历史赔率单场。</div>;
  }
  return (
    <div className="table-wrap">
      <table className="compact-table backtest-single-table">
        <thead>
          <tr>
            <th>EV排序</th>
            <th>体彩时间</th>
            <th>比赛</th>
            <th>比分/赛果</th>
            <th>当时怎么买</th>
            <th>概率</th>
            <th>赔率</th>
            <th>理论EV</th>
            <th>实际盈亏</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={row.match_id + "-" + row.selected_pick}>
              <td>{index + 1}</td>
              <td>{row.sporttery_date} {row.sporttery_time}</td>
              <td><b>{row.match_num || "—"}</b> {row.match_label}</td>
              <td>{row.score || "—"} / {row.actual_label}</td>
              <td>买{row.selected_label}（{row.team_or_draw}）</td>
              <td>{pct(row.probability, 2)}</td>
              <td>{num(row.odds)}</td>
              <td className={row.ev >= 0 ? "positive" : "negative"}>{pct(row.ev, 2)}</td>
              <td className={row.profit >= 0 ? "positive" : "negative"}>
                {row.hit ? "命中 " : "未中 "}{money(row.profit)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function BacktestParlayList({ rows }: { rows: BacktestParlay[] }) {
  return (
    <div className="parlay-list backtest-parlay-list">
      {rows.map((row) => (
        <article className={"parlay " + (row.hit ? "settled-hit" : "settled-miss")} key={String(row.legs) + "-" + String(row.rank)}>
          <div className="parlay-head">
            <strong>{row.legs}串1 第{row.rank}</strong>
            <span className={row.ev >= 0 ? "positive" : "negative"}>EV {pct(row.ev, 2)}</span>
          </div>
          <div className="parlay-meta">
            <span>理论命中 {pct(row.probability, 4)}</span>
            <span>总赔率 {num(row.decimal_odds)}</span>
            <span className={row.profit >= 0 ? "positive" : "negative"}>{row.hit ? "全中 " : "未全中 "}{money(row.profit)}</span>
          </div>
          <ol>
            {row.leg_details.map((detail) => (
              <li key={detail}>{detail}</li>
            ))}
          </ol>
        </article>
      ))}
    </div>
  );
}

function EvSection({
  singles,
  parlays,
  activeLeg,
  setActiveLeg
}: {
  singles: BestBet[];
  parlays: Record<string, Parlay[]>;
  activeLeg: string;
  setActiveLeg: (value: string) => void;
}) {
  const activeRows = parlays[activeLeg] ?? [];
  return (
    <section className="section">
      <div className="section-head">
        <h2>EV排行和买法</h2>
        <p>EV是理论净期望，不是命中概率；串关命中概率会随场次数增加快速下降。</p>
      </div>
      <div className="split">
        <div className="panel">
          <h3>单场期望最高前10</h3>
          <SingleBetTable rows={singles} />
        </div>
        <div className="panel">
          <div className="panel-title-row">
            <h3>串关各档前10</h3>
            <div className="tabs">
              {[2, 3, 4, 5, 6, 7, 8].map((legs) => (
                <button
                  key={legs}
                  className={activeLeg === String(legs) ? "on" : ""}
                  onClick={() => setActiveLeg(String(legs))}
                >
                  {legs}串1
                </button>
              ))}
            </div>
          </div>
          <ParlayList rows={activeRows} />
        </div>
      </div>
    </section>
  );
}

function ParlayList({ rows }: { rows: Parlay[] }) {
  if (rows.length === 0) {
    return <div className="empty">当前有效HAD场次不足，无法组成该档串关。</div>;
  }
  return (
    <div className="parlay-list">
      {rows.map((row) => (
        <article className="parlay" key={`${row.legs}-${row.rank}`}>
          <div className="parlay-head">
            <strong>{row.legs}串1 第{row.rank}</strong>
            <span className={row.ev >= 0 ? "positive" : "negative"}>EV {pct(row.ev, 2)}</span>
          </div>
          <div className="parlay-meta">
            <span>命中概率 {pct(row.probability, 4)}</span>
            <span>总赔率 {num(row.decimal_odds)}</span>
          </div>
          <ol>
            {row.leg_details.map((detail) => (
              <li key={detail}>{detail}</li>
            ))}
          </ol>
        </article>
      ))}
    </div>
  );
}

function OddsSection({ odds }: { odds: OddsRow[] }) {
  const [onlyEv, setOnlyEv] = useState(false);
  const rows = useMemo(() => odds.filter((row) => !onlyEv || row.participates_ev), [odds, onlyEv]);
  return (
    <section className="section">
      <div className="section-head horizontal">
        <div>
          <h2>体彩胜平负赔率与模型概率</h2>
          <p>HAD为空或未开售的比赛只展示，不参与EV排行；HHAD仅作为参考展示。</p>
        </div>
        <label className="toggle">
          <input type="checkbox" checked={onlyEv} onChange={(event) => setOnlyEv(event.target.checked)} />
          只看参与EV的比赛
        </label>
      </div>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>编号</th>
              <th>时间</th>
              <th>比赛</th>
              <th>模型胜/平/负</th>
              <th>体彩HAD胜/平/负</th>
              <th>让球参考</th>
              <th>状态</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row, index) => (
              <tr key={`${row.match_id || row.home_en}-${index}`} className={!row.participates_ev ? "muted-row" : ""}>
                <td>{row.match_num || "未返回"}</td>
                <td>{row.match_date} {row.match_time}</td>
                <td>{row.home_cn} vs {row.away_cn}</td>
                <td>{pct(row.probabilities.home)} / {pct(row.probabilities.draw)} / {pct(row.probabilities.away)}</td>
                <td>{num(row.had_odds.home)} / {num(row.had_odds.draw)} / {num(row.had_odds.away)}</td>
                <td>
                  {row.hhad_odds.goal_line ? `${row.hhad_odds.goal_line}：` : ""}
                  {num(row.hhad_odds.home as number | null)} / {num(row.hhad_odds.draw as number | null)} / {num(row.hhad_odds.away as number | null)}
                </td>
                <td>{row.participates_ev ? "参与EV" : reasonText(row.skip_reason)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function PolyalphaSection({ polyalpha }: { polyalpha: PolyalphaData }) {
  const titleTop = topEntries(polyalpha.title_probability, 16);
  const r32Top = topEntries(polyalpha.reach_knockout_R32, 32);
  const scorerTop = topEntries(polyalpha.golden_boot?.top_scorer_probability, 12);
  const groupNames = Object.keys(polyalpha.group_standings ?? {}).sort();
  const predictions = polyalpha.predictions.slice(0, 72);
  return (
    <section className="section">
      <div className="section-head">
        <h2>PolyAlpha预测同步</h2>
        <p>以下为同步后的核心预测板块，结合本站新增的体彩赔率和EV结果使用。</p>
      </div>
      <div className="grid three">
        <RankingPanel title="夺冠概率" entries={titleTop} />
        <RankingPanel title="进入32强" entries={r32Top} />
        <RankingPanel title="金靴概率" entries={scorerTop} playerMode />
      </div>
      <GroupPanel groupNames={groupNames} groups={polyalpha.group_standings} />
      <PredictionPanel predictions={predictions} />
      <BracketPanel bracket={polyalpha.bracket} />
    </section>
  );
}

function RankingPanel({ title, entries, playerMode = false }: { title: string; entries: Array<[string, number]>; playerMode?: boolean }) {
  return (
    <div className="panel">
      <h3>{title}</h3>
      <div className="rank-list">
        {entries.map(([name, value], index) => (
          <div className="rank-row" key={name}>
            <span>{index + 1}</span>
            <b>{playerMode ? name : teamName(name)}</b>
            <em>{pct(value)}</em>
          </div>
        ))}
      </div>
    </div>
  );
}

function GroupPanel({ groupNames, groups }: { groupNames: string[]; groups: Record<string, Record<string, number>> }) {
  return (
    <div className="panel wide">
      <h3>小组出线概率</h3>
      <div className="group-grid">
        {groupNames.map((group) => (
          <div className="group-box" key={group}>
            <strong>小组 {group}</strong>
            {topEntries(groups[group], 4).map(([team, value]) => (
              <div className="group-row" key={team}>
                <span>{teamName(team)}</span>
                <div className="bar"><i style={{ width: `${Math.min(100, value * 100)}%` }} /></div>
                <em>{pct(value, 0)}</em>
              </div>
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}

function PredictionPanel({ predictions }: { predictions: PolyalphaData["predictions"] }) {
  return (
    <div className="panel wide">
      <h3>小组赛胜平负预测</h3>
      <div className="match-grid">
        {predictions.map((row) => (
          <div className="match-card" key={`${row.date}-${row.home}-${row.away}`}>
            <span className="date">{row.date}</span>
            <b>{teamName(row.home)} vs {teamName(row.away)}</b>
            <div className="prob-line">
              <span>胜 {pct(row.p_home, 0)}</span>
              <span>平 {pct(row.p_draw, 0)}</span>
              <span>负 {pct(row.p_away, 0)}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function BracketPanel({ bracket }: { bracket?: PolyalphaData["bracket"] }) {
  if (!bracket?.rounds?.length) {
    return null;
  }
  return (
    <div className="panel wide">
      <h3>淘汰赛预测路径</h3>
      <p className="champion">预测冠军：{teamName(bracket.champion ?? "")}</p>
      <div className="bracket-grid">
        {bracket.rounds.map((round) => (
          <div className="round-box" key={round.round}>
            <strong>{round.round}</strong>
            {round.matches.slice(0, 16).map((match, index) => (
              <div className="round-row" key={`${round.round}-${index}`}>
                <span>{teamName(match.a)} / {teamName(match.b)}</span>
                <b>{teamName(match.winner)}</b>
              </div>
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}

function reasonText(reason: string): string {
  const map: Record<string, string> = {
    HAD_not_selling_or_missing: "未开HAD",
    HAD_odds_empty: "HAD赔率为空",
    match_already_started: "已开赛/已结束",
    team_name_unmatched: "队名未匹配",
    polyalpha_prediction_unmatched: "预测未匹配",
    not_returned_by_sporttery_current_query: "体彩暂未返回"
  };
  return map[reason] ?? (reason || "未参与");
}
