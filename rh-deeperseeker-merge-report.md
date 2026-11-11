# rh-deeperseeker 合并差异报告（供逐项取舍）

生成时间：2026-11-07 · 本次未修改任何代码

对比对象：

- 上游：https://github.com/AmanCode22/deeperseeker
- 本仓库：`C:/Users/C-H716/Desktop/Proxy/deeperseeker`（`origin` = C-H716/deeperseeker，本地 `main` = `32fe0c0`）
- 待合并：https://github.com/1515asd/rh-deeperseeker（`main` = `adf576703`，2026-11-07 01:27Z）

数据来源：GitHub API（仓库信息、146 个提交的哈希与提交说明）+ `codeload` 下载的 main 最终源码快照（23 个文件）。`git fetch` 该仓库持续报 `schannel: failed to receive handshake` / `Empty reply from server`，故改用只读 HTTP 通道取源码，**未改动本地任何 remote 或分支**。

---

## 0. 一句话结论

**这两个仓库不能做 git 意义上的合并，只能做「以你本地为主干的功能增量移植」。** rh 相对你的版本，真正缺失且值得考虑的功能只有 4 类：禁言（muted）账号识别、可选的风控请求头、令牌池加密备份、官方 API 直通；其余绝大部分改动你已独立实现过，或该问题在你这边根本不存在。

请直接看 **第 6 节取舍速查表**，在「你的选择」列填「做 / 不做 / 待定」后告诉我编号即可。

---

## 1. 谱系与技术约束

| 事实 | 证据 |
|---|---|
| rh 在 GitHub 上**不是登记在案的 fork** | `is_fork: null`、`parent: null`、`source: null`；仓库创建于 2026-10-11 |
| 两边**没有共同祖先** | rh 的 146 个提交哈希与本地 git 对象库逐一比对，命中 **0** 个 |
| 因此 `git merge` / `cherry-pick` / 基于 merge-base 的三方合并都不成立 | 无共享对象，合并只会变成「无关历史强制合并」，等于用 rh 的树覆盖你的树 |
| 两边代码分化极大 | rh 共 23 个文件：`app.py` 3241 行、`functions.py` 4754 行、`plugin_helper.py` 1255 行、模板在 `templates/zh/`、**无 tests 目录**；本地 `app.py` 4237 行、`functions.py` 3835 行，另有 `usage_stats.py` 624 行、统计面板、亮色 UI 重写、**33 个测试文件**、uv + 分层 lock |
| 文件哈希比对 | rh 的 23 个 blob 中最多只有 5 个能在上游 338 个历史提交里找到，说明 rh 是从一份被大幅改写过的快照重建的，无法反推出干净的分叉点 |
| rh 的 `english` 分支 | 其 README 明确「代码与 main 一致」，仅注释/日志/面板/文档全英文，**不需要单独合并** |

**结论**：可行路径只有一条 —— 保留本地 `main` 的所有实现，把 rh 中本地确实没有的功能作为增量搬进来，逐项补测试并跑通现有 33 个测试文件。

---

## 2. 文件级差异矩阵

| 文件 | rh | 本地 | 差异性质 | 处理建议 |
|---|---|---|---|---|
| `app.py` | 3241 行 | 4237 行 | 主流程双向重写，行号与函数组织完全不同 | **不整体替换**，只允许定点插入函数/路由 |
| `functions.py` | 4754 行 | 3835 行 | 同上；DDL、错误分类、请求构造均不同 | **不整体替换** |
| `plugin_helper.py` | 1255 行 | 1048 行 | 上下文滚动 / 提示词构建各有实现 | 保留本地 |
| `middleware.py` | 244 行（三中间件） | 253 行（Stage 0 rails，含 `TRUSTED_PROXIES` fail-closed XFF） | 本地更完整且有测试 | 保留本地 |
| `templates/*.html` | `templates/zh/` 3 件 | `templates/` 4 件（含 `stats.html`） | **结构不兼容**：本地 block 为 `title/layout/content` + `static_version` + 外链 `style.css`；rh 为 `title/head/content`、内联 CSS、无 `stats.html` | 只可摘取片段，禁止整目录覆盖（否则 `TemplateNotFound`、`static_version` 未定义、导航丢失） |
| `static/style.css` | 34 行 | 574 行 | 本地为完整亮色主题重写 | 保留本地 |
| `official_api.py` | 238 行 | 无 | rh 独有 | 决策项 D6 |
| `ds_backup.py` | 385 行 | 无 | rh 独有 | 决策项 D5 |
| `README.zh-CN.md` / `docs/GUIDE*.md` | 有 | 无（本地是上游英文 README 172 行） | 纯文档 | 决策项 D9 |
| `usage_stats.py` / `templates/stats.html` | 无 | 有 | 本地独有 | 必须保留 |
| `tests/`（33 个 `.py`） | 无 | 有 | 本地独有 | 必须保留，作为移植回归网 |
| `pyproject.toml` / `uv.lock` / `requirements-*.in|txt` | 无（仅 2 个 txt） | 有（uv 分层锁定 + WAF 备份锁） | 本地构建体系更完整 | 保留本地 |
| `Dockerfile` | 53 行（非 root、`/app/data`、`HEALTHCHECK`） | 76 行（含 apt/代理重试加固、Playwright 采集 Chromium、`HEALTHCHECK`、数据卷） | 本地已覆盖且更贴合本机代理环境 | 保留本地 |
| `wasm/deepseek_pow_solver.wasm` | 有 | 有 | 相同用途 | 无需处理 |

---

## 3. 你已独立实现、无需重复移植（对照 rh 版本表）

| rh 版本 / 功能 | 本地对应实现 | 判定 |
|---|---|---|
| v82–v85 `parent_message_id` 原生协议（首条省略、用服务端广播的真实编号） | `functions.py:3555` `if parent_message_id == 0: parent_message_id = None`；`app.py` 首轮 `is_first` 判断与锁内重读 | 已覆盖 |
| v86 Apple 风面板 + 深度健康 | 本地亮色 UI 重写（`07e8199`）+ 统计面板（`3370001`）+ 号池轮询局部刷新（`bb2a105`） | 已覆盖且更贴合 |
| v87 记忆丢失链（陈旧 PoW → 空流误判 → 孤儿续写） | 本地 PoW 预取 / 空流重试 / 上下文滚动抑制窗口系列提交，且有 `test_pow_prefetch.py` 等测试 | 已覆盖 |
| v88 上游 PR #94 加固（HTTP 200 业务错误分类、setup 阶段重试） | `2a7c2ea`、`0fedce1`、`32fe0c0` 均明确为「移植上游」，含 INCOMPLETE、流重试、业务错误统一校验 | 已覆盖 |
| v89.4 / v89.5 裸 JSON 工具调用与畸形 DSML 打捞 | 本地 `d03cf37`、`8aa2ff2`、`325f4ca`、`9ad37e3`、`7121053`、`32fe0c0` + 多个专项测试 | 已覆盖 |
| v89.6 ① `restore`/`upload` 的 NameError 500 | 本地 `/tokens/check`、`/v1/files*` 路由正常且有测试覆盖 | 已覆盖 |
| **v89.10 深健康探针不再创建空会话** | 本地 `/dashboard/status`（`app.py:3996`）注释明确「只读本地状态，不触达上游」；`/health`（`app.py:4206`）只读本地库；`check_token_status`（`functions.py:1458`）走 PoW 挑战端点，注释明确「不创建 chat、无模型副作用」 | **该问题本地不存在，无需移植** |
| v89.12 / v89.13 桥内账号密码登录 + SMSdk 设备指纹 | 本地 `/accounts/add`（`app.py:4129`）+ `login_deepseek_account`（`functions.py:762`）+ `_resolve_login_device_id` 三级优先级（env → 持久化文件 → Playwright 采集）+ `DEEPSEEKER_DEVICE_ID*` | 已覆盖，且本地是**自动采集**，比 rh 的「手工填 `SMSdk.getDeviceId()`」更自动化 |
| v89.9 `x-device-id` / `x-device-model` 请求头 | rh 自己在 `56ca42d3f` **revert** 了 v89.9 | 不应移植 |
| 上下文滚动 / 交接摘要 / 任务锚点 / duplicate-call gate | 本地 `plugin_helper.py`、`app.py` 有等价实现 + `test_context_rollover.py` 等测试 | 已覆盖，深度耦合且强测试绑定，不建议动 |
| 三中间件 / `TRUSTED_PROXIES` | 本地 `middleware.py` Stage 0 rails | 已覆盖 |

> 注：本地 `accounts` 表（`functions.py:177`）**不存密码**，只有 `email / alias / token_id / status / last_login_at / last_error / created_at`。这直接影响 D4 的可行性，见下。

---

## 4. 需要取舍的增量（决策项）

### D1 · 禁言（muted）账号识别与隔离 —— 价值最高，建议优先

- **rh 做了什么**（v89.7）：上游禁言报文藏在嵌套信封里（外层 `code=0`、内层 `biz_code=5 "user is muted"`），旧逻辑只读外层 → 返回 `502 "biz error 0"` 且不进入任何隔离通道，禁言账号被显示成「正常」。rh 按硬证据 `biz_data.chat.is_muted == 1` 抛 `UpstreamMutedError`（`functions.py:455-482` 格式化解禁时间、`3443-3445` 抛点），立即隔离并记录原因（`app.py:712-737`）；另加启动时静默扫描 ACTIVE 令牌。
- **rh 附带**：`probe_token_mute`（`functions.py:3253-3300`）用只读 `GET /api/v0/users/current` 直接问上游真实状态，返回 `ok / muted + mute_until / invalid / error`；`/v1/pool/probe`（`app.py:3008-3051`）面板按钮。
- **本地现状**：全库无 `muted` / `is_muted` / `quarantine_reason`；`check_token_status` 只能判 `ACTIVE / INVALID / RATE_LIMITED / CHECK_ERROR`，**读不出禁言与解禁时间**。这是本地确实存在的能力缺口。
- **移植代价**：新增异常类与格式化（约 30 行）+ SSE 解析循环抛点（1 处）+ 失败处理链分支（1 处）+ `tokens` 表幂等 ALTER 增 1–2 列（`quarantine_reason` / `mute_until`）+ 把只读探测接入 `/tokens/check` + 启动扫描。约 120–180 行，涉及 `functions.py`、`app.py`、`init_db`。
- **风险**：中。只改失败路径，成功路径字节不变；但必须沿用 rh v89.3 的教训 —— 「鉴权措辞」属于软证据，单次命中不得隔离，连续 3 次才动手，避免误杀健康账号。
- **建议**：**优先做**。这是唯一一处明确的生产缺陷修复，且本地无等价物。

### D2 · 隔离原因落库 + 面板五态状态与「检测令牌」按钮 —— 依赖 D1

- **rh 做了什么**（v89.6 / v89.7）：`quarantine_reason` 落库，`get_pool_view` 分出「正常 / 限速冷却 / 确认禁言 / 疑似禁言 / 疑似过期 / 其他隔离」五态五色，每种配大白话自查指引；`templates/zh/dashboard.html` 加入 `refreshPool / refreshDeep / refreshEffort / probe` JS。
- **本地现状**：已有 `/tokens/check` 按钮、`/dashboard/status` 轮询返回 `status / limited_until / last_checked_at / last_check_error / inflight / rotation`，但状态是扁平的，没有「隔离原因」与「确认禁言」档。
- **移植代价**：`functions.py` 状态分类 + `dashboard.html` 片段（约 40 行）+ 模板改动。注意两套模板 block 名不同，只能按本地结构改写，**不能覆盖模板文件**。
- **风险**：低–中，纯展示层。
- **建议**：仅在做 D1 时一并做；否则跳过。

### D3 · `x-hif-leim` 风控令牌 —— 有争议，建议默认关闭或暂缓

- **rh 做了什么**（v89.8）：`get_hif_token`（`functions.py:3102-3167`）从 `hif-leim.deepseek.com` 取 TTL 600s 的短期令牌，按 TTL 缓存、提前 30s 刷新、失败退避 60s 并降级为不带该头；注入点仅 1 行（`3930-3932`）。env：`DEEPSEEKER_HIF_ENABLED`、`DEEPSEEKER_HIF_URL`。
- **重要矛盾**：v89.11（`b5ce1d4b8`）以「安卓 App 从不发 `x-hif-leim`，它是网页前端的头，带着会造成混合身份」为由把默认值**改为关闭**；v89.9 的 `x-device-id` 头也被 revert。而 rh 的中文 README 第 47 行仍写「默认开」，**文档与代码不一致**。同一功能在三天内被自我否定，证据强度存疑。
- **本地现状**：无。
- **移植代价**：约 70 行 + 1 处注入 + 2 个环境变量；默认关闭时零行为变化、零新增网络请求。
- **风险**：中。启用后新增对第三方域名的出站请求，且可能与本地 Android 客户端头体系冲突（本地 `DEEPSEEKER_CLIENT_VERSION=2.4.5` 走的就是安卓路径）。
- **建议**：**可移植但保持默认关闭**，或先不做，等上游/社区结论明确。

### D4 · 令牌池自动重登（native token 自愈）—— 需要你单独拍板的安全取舍

- **rh 做了什么**（v89.12）：`relogin_native`（`functions.py:680-847` 一组）在鉴权形态失效（40003/401）时自动重新登录，`DEEPSEEKER_RELOGIN_MIN_INTERVAL` 默认 6h（约每天最多 4 次）、按 token 并发去重；密码错/封号/风控设备分别处理（封号隔离、risk_device 停止重试）。
- **本地现状**：登录能力齐全（`/accounts/add`），但**不存密码、无自动重登**；`accounts` 表没有 password 列。
- **关键取舍**：要实现自动重登，必须把账号密码（或可逆凭据）持久化到 DB。rh 声称「密码只存本地 DB、不进日志、不返回」，但这仍是新增的凭据落库面；且自动重登本身可能触发风控。
- **移植代价**：DDL 加列 + 凭据存取 + 节流/去重 + 失败链挂钩，约 100–150 行，且要改造本地已有的登录链路。
- **风险**：中高（安全 + 风控双重）。
- **建议**：除非你确实被「跨环境会话吊销」困扰，否则**不建议**。你现有的设备指纹登录已经能手动补号。

### D5 · `ds_backup.py` 令牌池加密备份与空池自动恢复 —— 低风险、实用

- **rh 做了什么**：385 行独立模块，PBKDF2-XOR 加密 tokens 表，支持 Telegram / GitHub Gist / 本地文件三种目标，定时（默认 6h）备份，启动时发现池子空了自动恢复。挂载点仅 `app.py:446-456` lifespan 两行；env 共 9 个 `DEEPSEEKER_BACKUP_*`。
- **本地现状**：无。本地依靠 `DB_PATH` 持久卷（`Dockerfile` 已挂 `/app/data`）保数据。
- **移植代价**：新增 1 文件 + lifespan 2 行 + 环境变量文档。**注意**：rh 的恢复逻辑自带一份精简 `tokens` 建表（只含少量列），与本地 `account_id / limited_until / last_checked_at / last_check_error` 不兼容，必须按本地表结构改写，否则恢复会丢列。
- **风险**：低（模块默认惰性、不启用即零影响）；启用外发时注意凭据加密与 Gist/TG token 管理。
- **建议**：**可选，推荐**。自包含、易验证、不动主流程。

### D6 · `official_api.py` 官方 API 直通模式 —— 取决于是否需要付费回退

- **rh 做了什么**：238 行，`DEEPSEEKER_MODE=official` 时改走 `api.deepseek.com`，含模型映射与流式实现；env：`DEEPSEEKER_MODE / OFFICIAL_BASE / OFFICIAL_API_KEY`。
- **本地现状**：无，只有网页免费层反向代理。
- **移植代价**：新增 1 文件 + 在 chat / responses / messages 三个 handler 各加一处分支。
- **风险**：中（改变请求路径，需持有官方 API Key；三条链路都要回归）。
- **建议**：**可选**。若你只用免费层，这项没有价值。

### D7 · effort 面板总开关 —— 价值有限

- **rh 做了什么**（v89.6）：`settings(key,value)` 表 + `GET|POST /v1/features/effort-enhance` + `_apply_effort`，可随时关掉「`reasoning_effort=max` 追加强化指令」的行为。
- **本地现状**：effort 解析链已完整（`request_effort` / `effort_level` / `_with_effort`，`app.py:2504-2605`、`2667`、`2740-2782`、`plugin_helper.py:871`），有 `test_effort.py`；但**没有运行时总开关**，也没有 `settings` 表。
- **移植代价**：新建 settings 表 + 2 个路由 + 面板开关 + 3 处调用点包裹，约 60–90 行。
- **风险**：低。
- **建议**：**可选**。除非你需要不改代码就关掉强化指令。

### D8 · 文档资产 —— 零代码风险，但需改写

- 内容：`README.zh-CN.md`（164 行：版本表、令牌状态表、env 表、Safari 取令牌书签、升级告警）、`docs/GUIDE.md` / `GUIDE.zh-CN.md`（各 128 行：PoW、消息编号、rollover、旧会话恢复）。
- 本地 README 是上游英文原版（172 行），无中文文档、无 GUIDE。
- **注意**：rh 文档里全是 `1515asd/rh-deeperseeker` 链接、v89.x 版本号、rh 专属功能描述，且第 47 行「hif 默认开」与其代码矛盾；直接复制会误导，须按本仓库改写。
- **建议**：**可选**。可作为新增独立文件，风险为零。

### D9 · `x-hif-leim` 之外的中间版本修补 —— 明确跳过

v89.1 / v89b / v89c / v89.2 / v89.3 都是同一「duplicate-call gate」的反复调整，最终形态已定；v89.9 已被 revert。**不要按提交逐个移植**，只取 main 的最终快照状态。

---

## 5. 移植时必须遵守的技术约束

1. **只取 rh `main` 的最终状态**，不要按提交历史逐个应用（无共同祖先，且中间存在 revert 与自我否定）。
2. **DDL 不能照抄**。本地 `tokens` 列：`alias / token / status / last_checked_at / last_check_error / account_id / limited_until / last_used`；rh 列：`rate_limited_until / consecutive_403 / quarantine_reason / account / password / last_login / device_id`。同名不同义（`limited_until` vs `rate_limited_until`），必须映射到本地列名，并沿用本地已有的 `PRAGMA table_info` 幂等 ALTER 写法（`functions.py:242-273`）。
3. **模板不能覆盖**。本地 `templates/` 4 件、block `title/layout/content`、`static_version`、导航含 `/stats`；rh `templates/zh/` 3 件、block `title/head/content`、内联 CSS。整目录覆盖会直接导致 `TemplateNotFound`、`static_version` 未定义、`login.html` 的 `block layout` 丢失。
4. **本地独有路由不能丢**：`/dashboard/status`、`/stats`、`/accounts/add`、`/accounts/{id}/delete`、`/tokens/check`、`/responses` 别名。rh 缺少这些，且它的 `/v1/admin/stats` 语义与本地 `/dashboard/status` 不同。
5. **本地独有环境变量不能丢**：`DEEPSEEKER_DEVICE_ID*`、`POW_POOL_MAX`、`POW_PREFETCH_TTL`、`TOKEN_CHECK_INTERVAL`、`ROLLOVER_SUPPRESS_SECONDS`、`ALLOW_DEFAULT_ADMIN`、`FACT_MEMORY_TOKENS`、`PROMPT_LANGUAGE`、`TRUSTED_PROXIES`、`DEEPSEEKER_UPSTREAM_FALLBACK`、`DEEPSEEKER_MAX_UPSTREAM_ATTEMPTS`、`DEEPSEEKER_CLIENT_VERSION` 等。
6. **回归网**：现有 33 个测试文件（`tests/`）是最大资产。每个移植项都应新增对应测试，并在每批结束后跑全量套件。
7. **提交纪律**：按项目约定，只提交与当前任务直接相关的文件，不夹带 `.workbuddy-ai/`、`AGENTS.md`、`_fix_strip.py` 等未跟踪文件；提交信息用中文 `<type>(<scope>)：…`，不加任何署名行。

---

## 6. 取舍速查表（请填写「你的选择」）

| 编号 | 功能 | 价值 | 代价 | 风险 | 我的建议 | 你的选择 |
|---|---|---|---|---|---|---|
| D1 | 禁言账号识别与隔离 + 只读探测 | 高 | 中（120–180 行，2 文件 + DDL） | 中 | **优先做** |  |
| D2 | 隔离原因落库 + 面板五态/检测按钮 | 中 | 低–中（依赖 D1） | 低 | 随 D1 一起做 |  |
| D3 | `x-hif-leim` 风控头 | 存疑 | 低（70 行） | 中 | 默认关闭地移植，或暂缓 |  |
| D4 | 令牌池自动重登（需存密码） | 中 | 中高（改登录链路） | 中高 | **不建议** |  |
| D5 | `ds_backup.py` 加密备份 | 中高 | 低（新增文件 + 2 行挂载） | 低 | **推荐** |  |
| D6 | `official_api.py` 官方 API 直通 | 视需求 | 中（3 个 handler 分支） | 中 | 可选 |  |
| D7 | effort 面板总开关 | 低 | 低（60–90 行） | 低 | 可选 |  |
| D8 | 中文 README / GUIDE 文档 | 低 | 极低（纯新增，需改写） | 无 | 可选 |  |
| D9 | 中间版本修补 | 无 | — | — | **跳过** |  |
| — | 模板整套 / 构建体系 / middleware / 主流程 | — | — | — | **保留本地，禁止覆盖** | — |

**建议实施顺序**：若只想拿最稳妥的收益 → `D1 + D2`（一批，含新测试）→ `D5`（一批）→ 其余按你勾选的另行安排。每批结束跑全量测试并核对 `git diff`。

---

## 7. 附：本次调研用到的关键定位

| 内容 | 位置 |
|---|---|
| rh 快照（本地临时目录） | `C:/Users/C-H716/AppData/Local/Temp/rh-deeperseeker-main/rh-deeperseeker-main` |
| rh 探测函数 | `functions.py:3253-3300` `probe_token_mute` |
| rh 深健康探针 | `app.py:3168-3234` |
| rh hif 令牌 | `functions.py:3102-3167`，注入 `3930-3932` |
| rh 原生登录组 | `functions.py:680-847`，路由 `app.py:3121-3150` |
| rh DDL | `functions.py:124-244` |
| 本地令牌检查 | `functions.py:1458` `check_token_status`、`app.py:4171` `/tokens/check` |
| 本地面板轮询 | `app.py:3996` `/dashboard/status` |
| 本地账号登录 | `functions.py:762` `login_deepseek_account`、`app.py:4129` `/accounts/add` |
| 本地 DDL | `functions.py:164-273` |

---

## 8. 后续变更（2026-11-07 晚）

按用户决定，登录请求已改为 rh 的 android 形态，同时处理了第 3 节「本地是自动采集，比 rh 更自动化」这一判断带来的形态不一致问题：

- `login_deepseek_account` 改为安卓客户端头组 + `referer: sign_in` + `x-device-id`（按账号 uuid5）+ 空 `x-device-model`；请求体改为 `os=android` / `area_code=+86` / 支持邮箱或手机号。
- 请求体 `device_id` 仍优先使用真实数美指纹：面板填写 > 按账号持久化（`accounts.device_id`）> `DEEPSEEKER_DEVICE_ID` / 全局缓存 / 浏览器自动采集 > 结构化占位。既保留本地自动采集的优势，也补上 rh v89.13 的按账号复用。
- 后台表单改为「邮箱或手机号 + 可选设备指纹」，并附获取指引；账号列表新增「设备指纹」绑定状态列。
- 登录返回结构化结果（含 `muted` / `mute_until`）；自动重登复用同一指纹，重登后若新会话处于禁言期则立即隔离。
