# DeeperSeeker（简体中文说明）

[English README](README.md) · [中文使用指南](docs/GUIDE.zh-CN.md)

把 DeepSeek 网页免费层包装成标准 API 的自托管网关，同时提供 OpenAI Chat Completions / Responses 与 Anthropic Messages 两套接口。本项目基于上游 [AmanCode22/deeperseeker](https://github.com/AmanCode22/deeperseeker)（MIT），在其基础上维护长期自托管部署所需的稳定性与风控适配。

> ⚠️ 自动化使用违反 DeepSeek 的服务条款。请只用专用小号，切勿使用个人主号；账号可能随时被禁言或封禁，风险自负。本项目与 DeepSeek 无任何关联。

---

## 快速开始

### 本地运行（推荐 uv）

```bash
uv sync
uv run patchright install chromium          # 安装浏览器内核（Linux 上如缺少系统依赖可加 --with-deps）
cp .env.example .env      # 修改面板口令与 API Key
uv run deeperseeker
```

不使用 uv 时：

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
patchright install chromium                 # 安装浏览器内核（Linux 上如缺少系统依赖可加 --with-deps）
python3 app.py
```

> **说明：** DeeperSeeker 1:1 模拟桌面端 Chrome 客户端，包括 Sec-CH-UA hints、WebAssembly PoW 挑战求解、数美（Shumei）设备令牌转发与 HIF 认证令牌。绕过 DeepSeek 的 Cloudflare / AWS WAF 护盾以及获取数美设备标识，需要系统安装 Patchright（防检测加固版 Playwright）与 Chromium 内核——执行上面的安装命令即可。缺少时启动会直接失败并报 `CookieGenerationError: playwright is not installed`。

### Docker / Podman

```bash
cp .env.example .env
docker compose up -d      # 或 podman-compose up -d
```

镜像内置代理环境下的 apt 重试与 HTTPS 源加固，并带 `/health` 健康检查。数据库与运行时文件放在 `/app/data` 持久卷。

面板地址：`http://localhost:4000/`

---

## 添加账号：请用「桥内登录」

面板 →「添加 DeepSeek 账号（推荐）」。账号密码在**桥内**按官方安卓 App 形态登录（`os=android`、安卓请求头、`x-device-id` UUID、`referer: sign_in`），会话出生与使用都在本服务内，不会经过浏览器。

**为什么**：2026 年 11 月起，上游会整体吊销「浏览器出生、跨环境使用」的会话——粘贴浏览器令牌往往几分钟内失效，还会让浏览器端同时退出登录，表现为频繁封号与反复重新提取。面板里的「粘贴浏览器 Token」只保留作应急备用。

**设备指纹（强烈建议填写）**：真实安卓登录的请求体携带数美（SMSdk）生成的设备指纹（约 89 字符的 base64 串）。随机或伪造的 UUID 会被风控以 `RISK_DEVICE_DETECTED`（`biz_code=11`）直接拒绝。

获取方式（一次即可，长期有效）：

1. Chrome 打开 `chat.deepseek.com`（**不需要登录**），等页面完全加载
2. F12 → Console，执行 `SMSdk.getDeviceId()`
3. 把输出的 base64 串粘贴进面板的「设备指纹」输入框

留空时的回退顺序：该账号已保存的指纹 → `DEEPSEEKER_DEVICE_ID` → 本机缓存 → 浏览器自动采集 → 结构化占位（此时登录大概率被风控拒绝）。**同一账号请始终使用同一指纹**，桥会按账号持久化并在自动重登时复用。

**凭据如何保存**：密码经本机密钥加密后只存本地 SQLite，不写入日志、不返回页面，仅用于令牌失效时的自动重登（默认至少间隔 6 小时，且封号/密码错/风控设备会停止自动重试）。号池表里「桥内」与「浏览器」徽章可区分令牌来源。

---

## 面板功能

| 区域 | 说明 |
|---|---|
| 账号列表 | 邮箱或手机号、状态、设备指纹绑定情况、最近登录 |
| Token 号池 | 来源徽章、状态、**五态说明列**、在途占用、轮换转移、最近检查；支持逐个或全量「检查」 |
| 人工恢复 | 隔离状态（确认禁言 / 疑似过期 / 疑似禁言 / 其他隔离）可点「恢复」显式放回轮换 |
| 检测链路 | 只读探测「面板 → 上游」链路，不创建会话、不发送消息；`/health?deep=1` 也可供外部监控使用 |
| 功能开关 | 提示词增强总开关：控制 `reasoning_effort=max` 等档位是否附加强化指令，即时生效 |
| 使用统计 | 独立的用量统计页，含逐小时峰谷计价与命中率 |

**五态说明**：按上游硬证据（`is_muted==1`）识别的禁言会立即隔离并记录解禁时间；隔离不会因冷却到期自动回到轮换，必须人工恢复或由下一次只读探测确认已解禁。

**防封禁相关**：禁言识别与隔离、`x-hif-leim` 风控头（默认关闭，见下）、只读令牌探测、桥内登录自动重登、令牌池加密灾备。

**遇到人机验证（40303）**：上游偶尔会对高频请求要求人机验证。此时账号会被置为「需人机验证」并停放 30 分钟——退出轮换，且不会被「全冷却兜底」选中，避免继续硬撞加剧风控。面板说明列会给出指引：在**自己电脑的浏览器**登录该账号、发一条消息解掉验证码，再回面板点「恢复」。免费方案无法在服务端自动解验证码；部署在 Docker / 无图形界面的服务器上时，验证码只能在外部浏览器手动完成。

---

## 号池加密灾备

`ds_backup.py` 按真实列导出 `tokens` 与 `accounts` 两表（含自动重登所需的加密密码和设备指纹），用 PBKDF2 派生流密钥加密后推送到外部目标；启动时**仅在号池为空**时自动恢复，本地数据始终优先。

未设置 `DEEPSEEKER_BACKUP_SECRET` 时模块完全静默，零网络请求、零行为变化。目标支持 `telegram` / `gist` / `file`，默认 `none`，间隔默认 6 小时。完整变量见 `.env.example`。

---

## 主要配置（`.env`）

| 变量 | 说明 | 默认值 |
|---|---|---|
| `DEEPSEEKER_API_KEY` | 访问 API 的 Bearer 密钥 | 未设置时自动生成并持久化 |
| `DEEPSEEKER_ADMIN_USER` / `DEEPSEEKER_ADMIN_PASSWORD` | 面板登录口令 | `admin` / `admin` |
| `HOST` / `PORT` | 监听地址与端口 | `127.0.0.1` / `4000` |
| `DEEPSEEKER_DEVICE_ID` | 数美设备指纹的全局兜底值 | 未设置 |
| `DEEPSEEKER_HIF_ENABLED` | 是否携带 `x-hif-leim` 风控头 | `0`（关闭） |
| `DEEPSEEKER_RELOGIN_MIN_INTERVAL` | 自动重登最小间隔（秒） | `21600` |
| `DEEPSEEKER_TOKEN_CHECK_INTERVAL` | 号池健康检查间隔（秒） | `300` |
| `DEEPSEEKER_BACKUP_SECRET` | 备份加密密码，设置后启用灾备 | 未设置 |
| `DEEPSEEKER_BACKUP_TARGET` | `telegram` / `gist` / `file` / `none` | `none` |

**关于 `x-hif-leim`**：`x-hif-leim` 是网页前端携带的风控令牌，抓包显示安卓 App 从不发送它。本桥使用安卓请求头，携带网页专属头反而构成「安卓 + 网页」的混合身份信号，因此默认关闭；确有需要时设为 `1`，取令牌失败会自动降级为不带该头，绝不阻断请求。

完整变量与上下文优先级见 `.env.example`。

---

## API 端点

- **OpenAI 兼容**：`http://localhost:4000/v1`
  - `POST /v1/chat/completions`（流式 / 非流式）
  - `POST /v1/responses`、`POST /responses`
  - `GET /v1/models`
  - `POST /v1/files`、`POST /v1/files/upload`
  - `GET /v1/files/{id}`、`GET /v1/files/{id}/content`
- **Anthropic 兼容**：`http://localhost:4000`
  - `POST /v1/messages`、`POST /messages`
- **面板 / 运维**：`/dashboard`、`/stats`、`/health`、`/health?deep=1`
- **模型**：默认 `v4.1flash`（视觉原生支持），其他传入值会归一化到它；`/v1/models` 同时列出 `anthropic/claude-v4.1flash` 供客户端自动发现

---

## 安全须知

- 修改默认面板口令与 `DEEPSEEKER_API_KEY`，尤其服务对外暴露时
- 令牌等同于账号本体，不要发给任何人；`account_secret.key` 已加入 `.gitignore`
- 建议只绑定本机（`HOST=127.0.0.1`），远程访问请套 VPN / 反向代理 + HTTPS
- 请勿搭建公共转发站，仅限个人用途

## 许可

MIT — 见 [LICENSE](LICENSE)。版权归上游作者 AmanCode22，本仓库的改进以同一许可发布。
