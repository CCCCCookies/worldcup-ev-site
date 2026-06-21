# 世界杯赔率与期望值网站

这是一个世界杯胜平负赔率与期望值面板。它有两种运行方式：

- 本地动态版：FastAPI 后端每小时抓取 PolyAlpha 和中国体彩数据，前端通过 `/api/*` 读取。
- 公网静态版：GitHub Actions 每小时生成 `dashboard.json`，GitHub Pages 直接托管静态网页，不依赖你的电脑。

## 本地启动

```powershell
cd F:\华设\华设项目汇总\华设项目报告\worldcup_ev_site\backend
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8035
```

浏览器打开：

```text
http://127.0.0.1:8035
```

## 前端构建

```powershell
cd F:\华设\华设项目汇总\华设项目报告\worldcup_ev_site\frontend
npm install
npm run build
```

## 生成静态数据

```powershell
cd F:\华设\华设项目汇总\华设项目报告\worldcup_ev_site
python .\backend\scripts\build_static_dashboard.py
```

生成位置：

```text
worldcup_ev_site/frontend/public/data/dashboard.json
```

Vite 构建时会把它复制到：

```text
worldcup_ev_site/frontend/dist/data/dashboard.json
```

## GitHub Pages 部署

建议只把 `worldcup_ev_site` 作为 GitHub 仓库根目录发布，不要把上一级报告目录里的 Word 文档一起传到公开仓库。

本目录已经包含工作流：

```text
.github/workflows/worldcup-ev-pages.yml
```

推送到 GitHub 后：

1. 进入仓库 `Settings -> Pages`。
2. Source 选择 `GitHub Actions`。
3. 到 `Actions` 手动运行 `World Cup EV Pages`，或等待每小时自动运行。
4. 部署完成后，GitHub 会给出公网 Pages 地址。

工作流会做这些事：

- 安装 Python 和 Node。
- 抓取 PolyAlpha / 中国体彩数据。
- 更新 `worldcup_ev_site/backend/data/odds_history.json`，用于持续回测。
- 生成 `dashboard.json`。
- 构建 React 前端。
- 发布到 GitHub Pages。

## 数据和计算口径

- PolyAlpha：`https://worldcup.polyalpha.cn/data.json`
- 体彩：`https://webapi.sporttery.cn/gateway/uniform/football/getMatchCalculatorV1.qry?channel=c&poolCode=hhad,had`
- 单场 EV：`模型概率 × 体彩HAD赔率 - 1`
- 串关 EV：`Π(模型概率 × 体彩HAD赔率) - 1`
- 只用非让球胜平负 `HAD` 计算 EV；`HHAD` 只展示，不参与 EV。
- 回测只结算本地或仓库中已经保存过历史 HAD 赔率的比赛；缺历史赔率的已完赛比赛会列出赛果，但不计入盈亏。

## 注意

GitHub Pages 静态版没有实时后端，所以网页上的“立即刷新”会被禁用，数据由 GitHub Actions 每小时更新。需要立即更新时，在 GitHub 仓库的 Actions 页面手动运行 `World Cup EV Pages`。
