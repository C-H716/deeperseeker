# 项目记忆（自 Claude Code 移植，2026-11-03）

本文件是 Claude Code 记忆库的镜像索引。每条记忆的完整内容存放在下面的目录中，
按需读取对应文件（文件名即索引里的链接目标）。

记忆目录：`C:/Users/C-H716/.claude/projects/C--Users-C-H716-Desktop-Proxy-deeperseeker/memory`

读取方式：需要某条记忆的细节时，直接读取 `C:/Users/C-H716/.claude/projects/C--Users-C-H716-Desktop-Proxy-deeperseeker/memory/<文件名>`。
每个文件带有 YAML frontmatter（name / description / metadata），正文是实现要点、
**Why** 与 **How to apply**。

---

- [Reply in Chinese](reply-in-chinese.md) — all user-facing replies in Chinese
- [Device id format](device-id-format.md) — real shape of the DeepSeek login device_id and the offset-0/1 validation rule
- [Docker rebuild deploy](docker-rebuild-deploy.md) — verify changes by rebuilding the image; COPY . . bakes code in
- [Web search gateway](web-search-gateway.md) — how web_search becomes web_search_tool_result; non-stream-only and search_sink constraints
- [Token pool dispatch](token-pool-dispatch.md) — least-in-flight token pick, 429 cooldown knob and where it lives
- [Parallel tool calls](parallel-tool-calls.md) — user wants parallel reads; keep parameter blocks well formed
- [Subagent usage preference](subagent-usage-preference.md) — subagents authorised; read-only by default; check results before repeating
- [Avoid blocking waits](avoid-blocking-waits.md) — run long tasks in background; no buffered pipelines
- [Prefer adding missing deps](prefer-add-missing-deps.md) — modpack errors: add the prerequisite library, do not remove the mod
- [AE2LT no markdown edits](ae2lt-no-markdown-edits.md) — never modify .md files in AE2LT
- [Git no branch switch](git-no-branch-switch.md) — do not switch branches or propose cherry-picks when committing fixes
- [Elevation via script](elevation-via-script.md) — DSH cannot elevate; give admin-only changes to the user as a script
- [dsh-docker disallowed](dsh-docker-disallowed.md) — user ruled @hyzyn/dsh-docker out as a reference or upgrade baseline
- [DSH plugin install pitfalls](dsh-plugin-install-pitfalls.md) — bundles registration, pnpm PATH, codegraph and better-sidebar patches, rewind stall
- [Local proxy setup](local-proxy-setup.md) — Hiddify 127.0.0.1:7890; git, installer and Node proxy env vars
- [Java JDK for Gradle](java-jdk-for-gradle.md) — Gradle 8.14.3 needs JDK 21; JDK 25 fails with major version 69
- [Windows file encoding BOM](windows-file-encoding-bom.md) — .ps1 needs BOM; .cmd/.vbs and Java must not have one
- [FastCtx MCP](fastctx-mcp.md) — user-scope fastctx server, four mcp__fastctx__ file tools; pnpm hard links block replace
- [Mod examples maintenance](mod-examples-maintenance.md) — 用户授权我直接改 sources.json 并更新实例库（含多版本共存）
- [Trash-only deletions](trash-only-deletions.md) — 删除必须走 trash 进回收站，rm/del 被钩子 deny
- [context-mode MCP-only install](context-mode-mcp-only-install.md) — 入口必须指 server.bundle.mjs，start.mjs 会偷偷重装插件 hook
