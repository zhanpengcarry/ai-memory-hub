# AI 多端记忆共享中心 — 设计与规划

## 1. 目标

将以下工作流中产生的**可移植知识**（偏好、约定、项目事实、决策摘要）汇聚到一处，再**按需下发**到各工具可安全读取的位置，实现「写一次、多端可读」，而不是替换各厂商私有状态库。

| 来源 | 典型载体 | 设计要点 |
|------|----------|----------|
| Claude（桌面 / Code） | `%APPDATA%\Claude\` 下会话与说明类 Markdown、`CLAUDE.md` 等 | 多路径；以 Markdown 与人类可读片段为主 |
| Codex | `~/.codex/memories/`（官方以生成状态为主，不宜原样互拷） | **只读拉取摘要**；写回时生成独立文件供引用，避免破坏内部结构 |
| OpenCode | `~/.config/opencode/memory/*.md`、项目 `.opencode/memory/*.md` | Frontmatter + Markdown；可与 Hub 块对齐 |
| OpenClaw | 工作区内 `memory/YYYY-MM-DD.md`、`MEMORY.md` | 按日追加与长期记忆分离；Hub 可产出「注入块」 |
| Harness | REST API（pipeline 执行记录） | API 源；通过 API key 认证，拉取部署历史转为 MemoryEntry |

## 2. 架构概览

```
各工具原始路径  →  Adapter（解析/规范化）  →  Canonical MemoryEntry
                                              ↓
                         Merge（去重、排序、可选冲突策略）
                                              ↓
                    Hub 数据目录（真相源 + 审计快照）  →  Adapter.export（生成各端可读文件）
```

- **Canonical**：统一结构（ID、来源、时间、标签、正文），便于 diff 与合并。
- **Hub 目录**：默认建议使用本仓库旁或 `%USERPROFILE%\.ai-memory-hub`，包含合并结果与按源的导入快照（便于排错与回滚）。

## 3. 统一数据模型（MemoryEntry）

- `id`：稳定哈希（来源 + 规范化正文）或显式 UUID。
- `source`：`claude` | `codex` | `opencode` | `openclaw` | `harness` | `manual`。
- `title`：可选短标题。
- `body`：Markdown 正文。
- `tags`：字符串列表。
- `created_at` / `updated_at`：ISO8601，缺失则填拉取时间。
- `provenance`：原始文件路径等，便于追溯。

## 4. 兼容性策略（最佳实践）

核心原则：**只约定「可移植层」**（Markdown + 自描述 JSON），不假设各产品内部目录长期稳定；用配置与探测降低升级带来的断裂。

| 手段 | 说明 |
|------|------|
| **路径占位符** | 同时支持 `${VAR}`、`%VAR%`（Windows 文档常见）、`~/`，避免写死盘符。 |
| **多种纳入方式** | `glob_paths` + `files`（显式文件）+ `scan_dirs`（整树按扩展名扫），glob 失效时仍有退路。 |
| **排除规则** | `defaults.exclude_globs` / 各源 `exclude_globs`，跳过 `.git`、`node_modules` 等。 |
| **编码** | 读取时 UTF-8 → UTF-8-SIG → 系统首选编码回退，减少 BOM/历史编码问题。 |
| **JSON** | 支持单对象、数组、**NDJSON 多行**、以及根级 `memories` / `items` / `entries` 包裹；正文键名多别名（`body` / `content` / `summary` / `messages` 等）。 |
| **Markdown** | Frontmatter 保留 `title` / `tags`；可选 `split_level2_headings` 把 OpenClaw 类「单日多 `##`」拆成多条入库。 |
| **去重** | 正文规范化含 **Unicode NFC**，减少跨编辑器保存导致的假重复。 |
| **导出安全** | 默认只写 Hub 与各端 `export/` 注入文件；`sync --dry-run` 跳过 export；**不**强行覆盖 Codex 私有 memories 目录。 |
| **可观测** | `discover` 列出解析到的文件；`hub_data/meta.json` 带 `schema_version` 与每源条数。 |

持久化合并结果仍以 **`merged.json` 顶层数组** 为主，便于 jq/脚本消费；版本信息放在 **`meta.json`**，避免破坏已有读取方。

## 5. 合并策略（当前实现）

1. **规范化**：正文 strip、统一换行、NFC；参与哈希去重。
2. **去重**：同一规范化正文只保留一条，合并 `sources` 列表与最新 `updated_at`。
3. **排序**：按 `updated_at` 降序写出 `MERGED.md`。
4. **冲突**：同 ID 不同正文时，在 `MERGED.md` 中分节保留并在 JSON 中带 `conflict` 标记（后续可扩展三向合并）。

## 6. 与各工具的协作方式（推荐）

- **OpenClaw / OpenCode**：可将 Hub 生成的 `for_openclaw/MEMORY.injection.md` 或 `for_opencode/*.md` 通过配置、include 或手动合并进现有 `MEMORY.md` / 全局 memory。
- **Claude**：将 `for_claude/SHARED_CONTEXT.md` 加入项目 `CLAUDE.md` 引用，或通过用户习惯的说明文件链路引入。
- **Codex**：优先阅读 Hub 汇总；若需回写 Codex，仅建议把 Hub 摘要复制到官方支持的配置/说明通道，**不要**直接批量覆盖 `~/.codex/memories/` 下文件。

## 7. 里程碑

| 阶段 | 内容 |
|------|------|
| M1 | 适配器骨架 + 配置 + `pull` / `merge` / `export` CLI（当前） |
| M2 | 文件监视：已实现 `watch`（轮询 + 指纹）；后续可改为 inotify 扩展 |
| M3 | 可选向量索引与语义检索（与本仓库解耦的插件） |

## 8. 风险与约束

- 各产品存储路径会随版本变化；**所有路径必须在 `config.yaml` 可配**。
- 涉密与隐私：Hub 目录可能含敏感信息，勿提交到 Git；建议 `hub_data/` 在 `.gitignore` 中排除或使用用户主目录。

## 9. 运行方式

1. `cd ai-memory-hub`
2. `pip install -e .`（或 `pip install -r requirements.txt`；开发测试加 `pip install -e ".[dev]"`）
3. `memory-hub init` 生成 `config.yaml`，或手动复制 `config.example.yaml`；按本机修改路径与选项。
4. `memory-hub doctor -c config.yaml` — 健康检查；任一启用源 0 文件时退出码 1（适合 CI）。
5. `memory-hub discover -c config.yaml` — 列出匹配到的源文件。
6. `memory-hub sync -c config.yaml` — 拉取、合并、写 `hub_data` 与各端 `export`。
7. `memory-hub sync -c config.yaml -v` — 打印每源条数与解析失败详情。
8. `memory-hub sync -c config.yaml --dry-run` — 只更新 `hub_data`，不写 export。
9. `memory-hub watch -c config.yaml` — 轮询源文件变更并自动 sync；`-i`/`--interval` 调整秒数。

等价调用：`python -m memory_hub <子命令> ...`

产出：`hub_data/merged.json`、`hub_data/MERGED.md`、`hub_data/meta.json`、各 `export/` 下的注入 Markdown。
