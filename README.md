# 热度观察站 · OzBargain 超值 Deal 监控

少刷一会儿，好价不错过。在手机上快速看热门、突然爆发的帖子和关注词命中。中文界面支持浅色 / 深色、收藏、隐藏和自定义关键词。

**预定站点**：[OzBargain](https://jc-ailab.github.io/ozbargain-monitor/) · [Hacker News](https://jc-ailab.github.io/ozbargain-monitor/hn.html)。部署需要仓库 Owner 在 Settings → Pages 选择 GitHub Actions；本地实现不代表站点已上线。

## 本地使用

需要 Python 3.12+，无需安装依赖。在仓库根目录运行：

```sh
python3 -m unittest discover -s tests
python3 scripts/run.py --monitor ozbargain --fixtures
python3 scripts/run.py --monitor hackernews --fixtures
python3 -m http.server 8000 --directory site
```

打开 `http://localhost:8000`。另开终端运行 `python3 scripts/check_site.py`，可检查两页资源、JSON 与所有 JS element id；可选 `node tests/frontend_smoke.js site` 执行无浏览器交互冒烟检查。首次只有一个采样点，爆发趋势显示「采样中」。Fixture 与 live 的默认历史分别在 `.state/fixtures/<monitor>/` 与 `.state/live/<monitor>/`，避免混入演示数据。`site/data/` 为生成文件，不提交。

可选真实浏览器布局检查（开发工具，不进入 unittest / CI）：

```sh
python3 scripts/check_layout.py
```

需要本机 Google Chrome，默认路径为 macOS 的 `/Applications/Google Chrome.app/Contents/MacOS/Google Chrome`，可用 `--chrome` 覆盖。脚本独立构建并服务离线 fixtures，将两页放入同源 iframe，检查 360 / 375 / 390 / 1300px 下的溢出、分数、统计、按钮和图片失败占位；同时断言 iframe 的实际 `innerWidth` 和截图宽度等于目标值，避免 macOS Chrome 最小窗口宽度影响手机测试。不请求外部图片或 feed。截图保存在仓库内 `.state/layoutcheck/screenshots/ozb-layout-*.png`，可用 `--screenshots` 改目录。Chrome 或本地服务若被沙箱阻止，需要在获准的沙箱外环境运行；启动失败会明确报错。

真实采样（不要频繁运行）：

```sh
python3 scripts/run.py --monitor ozbargain --state-dir .state/live/ozbargain --out site
python3 scripts/run.py --monitor hackernews --state-dir .state/live/hackernews --out site
```

显式 `--state-dir` 应每个 monitor 使用独立目录。OzBargain 每轮最多两次 RSS 请求，包含重试；超时 20 秒。不会访问原帖正文、商家网页或跳转链接。请至少间隔 30 分钟。

## 热度分怎么来

每项先按 `min(1, log1p(max(raw, 0)) / log1p(cap))` 归一化，再乘权重，相加四舍五入至 0–100。

| 项目 | 权重 | 原始值 | 上限 |
| --- | ---: | --- | ---: |
| 票数 | 30 | 赞成 − 反对 | 300 |
| 评论 | 25 | 评论总数 | 150 |
| 增速 | 发表以来净票数 / 小时，时间至少 0.5 小时 | 60 / 小时 |
| 点击 | 10 | 点击数 | 5000 |
| 爆发 | 10 | 近期新增赞成票 + 0.7 × 新增评论 | 40 |

爆火：分数 ≥70 或净票数 ≥200；热门：≥55 或净票数 ≥80；升温：≥40 或符合爆发条件。已过期帖子保留在列表末尾，不进入 Top 3。热度反映关注度，不保证商品质量。

爆发比较最接近 30 分钟前、且距最新点 20–90 分钟的快照。新增票数 + 0.7 × 新增评论至少为 5，且每小时增速至少为自身整个观测期平均增速的 2 倍，才显示「正在爆发」。没有合适旧点时显示「采样中」。平均增速包含当前窗口，所以只有两个采样点时通常不会判为爆发。

## 设置与运行

页面「设置」可覆盖关注词、屏蔽词、首页限定与过期显示，只保存在本浏览器。收藏 / 隐藏独立按 monitor 保存。存储被禁用时页面仍可使用。筛选和搜索影响列表，Top 3 按基础可见条件中的热度选出。统计栏展示服务端整体采样概况，不随个人筛选变化。

修改 `monitors/<name>/config.json` 可改权重、阈值、默认关键词、展示时限（`display_hours`，默认 36 小时）、保留天数及 AI 模型；[新增监控指南](docs/NEW_MONITOR.md) 使用 HN 展示完整复用过程。HN 的 points 映射为赞成票，点击为 0，不显示商家按钮。

GitHub Actions 在每小时第 7、37 分钟运行；修改代码 / 页面并推到 main 或手动 dispatch 也会运行。`state` 分支使用单个 amended commit 保存历史及上次发布结果；不要用该分支保存手工内容。仓库变量 `STOP_DATE` 默认 `2027-01-01`，到该悉尼日期后定时运行跳过；手动运行仍可用。第一次运行会创建 state 分支。Pages 必须允许 Actions 部署，仓库策略也必须允许 state 分支写入。

AI 默认关闭：两个 monitor 的 `summary.provider` 都是 `"none"`。如需启用，改为 `"gemini"`，并在 Actions secrets 设置 `GEMINI_API_KEY`；本地运行从同名环境变量读取。`summary.model` 默认 `gemini-3.8-flash`，可自行配置。使用官方 [Gemini REST generateContent](https://ai.google.dev/api/generate-content) 的 JSON 模式，不使用 GitHub Models，也不需要 Models 权限。provider 为 none 或缺少 key 时只记录一行，零 AI 网络请求；fixture 模式始终关闭 AI。

每个 monitor 每轮最多摘要 8 条候选帖子，缓存成功结果；Top 3 集合变化时最多请求一次 120 字速览。任意一次 AI 调用失败（HTTP、超时、非 JSON、结构或长度不合格），立即停止该轮剩余的摘要及速览调用，无模型回退或重试，下一轮再试。已有成功缓存和原始 RSS 数据保留。内容仅为 RSS 提供的有限信息。

OzBargain 卡片无需 AI 也会按 RSS 标题、描述及 flags 显示条件：`Prime 免运` / `需 Prime`、`自提 C&C`、`满 $N 免运`、`会员/定向`、`即将开始`、`需激活`、`返现`。满额免运只在有明确配送语境时识别，不把任意 Spend 金额当成免运门槛。chips 是有限文本提示，资格与具体条款仍以原帖为准；如有 AI 注意事项，会同时显示。

单个 feed 失败保留之前数据，状态写在 JSON 的 `stats.feeds`。全部失败时保留上次成功时间，页面超过 90 分钟会警告。页面仅发布最近 36 小时见过的帖子，统计也只计算这些帖子；本轮未见的卡片标注「已离开 feed」及最后采样时间。历史仍保留 7 天，每条最多 96 个快照，输出趋势最多 24 点；JSON 控制在 1.5 MB 内。页面每 10 分钟重新读取 JSON，无需整页刷新。

## 免责声明

数据来自 OzBargain 公开 RSS / hnrss.org，与 OzBargain、Hacker News 无关联。商品标题保持原文；「免费」按标题及分类自动判断，可能指有条件赠品。AI 摘要可能有误；价格、库存、资格、截止时间以原帖和商家为准。本项目不提供通知、账户或购买服务。

## English

A standard-library Python RSS → snapshots → configurable scores → static-page monitor. Vanilla JS/CSS, no build step or external scripts/styles. OzBargain is the main product; Hacker News demonstrates the reusable core. Run the offline tests and fixture commands above, then serve `site/`. The implementation report is in [docs/reports/IMPL_REPORT.md](docs/reports/IMPL_REPORT.md). Deployment and independent acceptance are separate from local verification.
