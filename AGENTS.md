# Novel 项目协作规则

## 项目目标

Novel 是纯本地的 AI 长篇小说创作系统。长期调用链为：

```text
作者
→ Codex
→ Codex Plugin / Skill
→ novel CLI
→ Narrative Application
→ Narrative Core
→ 正式文件、Canon Ledger 和 SQLite 投影
```

系统必须形成连续闭环：

```text
多小说选择
→ 新小说 Bootstrap
→ Writing Session
→ 动态历史查询
→ 章节情节确认与必要的 Intent Revision
→ Draft Revision
→ AI Review
→ 作者确认准确 Draft Revision
→ 人物、剧情、地点等线索解析
→ 摘要与可选关键 Canon
→ Publication Diff 和作者批准
→ 事务性发布
→ 下一次创作
```

AI 负责创作、推理、检索决策和审核；应用负责创作环境、数据、版本、引用、批准、发布和
恢复。应用不得用固定算法或检索命中数替代 AI 的语义判断。

每次任务只实现用户明确指定的业务切片，不为未开始的能力预建通用框架、占位服务或
复杂抽象。

## 架构依据

开始产品、架构或领域工作前，阅读与任务相关的现行文档：

- `docs/README.md`
- `docs/01-product-and-business-flow.md`
- `docs/02-system-architecture.md`
- `docs/03-domain-and-storage.md`
- `docs/04-memory-and-query.md`
- `docs/05-local-runtime-and-projects.md`
- `docs/06-creation-and-publishing.md`

这些文档是唯一产品依据，所有实现必须指向其中定义的同一创作闭环。

不要静默改变已经锁定的业务方向。若需求与现行设计冲突，先指出冲突并请求确认；若只有
小范围实现细节未定义，采用最小、直接且可演进的决定，并在交付报告中说明。

## 依赖边界

Python 内部依赖必须单向：

```text
novel_core
    ↑
novel_application
    ↑
novel_adapters
    ↑
novel_cli
```

- `novel_core` 只能依赖 Python 标准库和 Pydantic。
- Core 不得导入 `sqlite3`、CLI、Codex/OpenAI SDK、Git、桌面框架、ORM 或网络服务。
- Application 负责用例、命令、查询和事务编排，只依赖端口和 Core。
- Adapters 实现 Project Catalog、文件、SQLite、锁和恢复存储。
- CLI 只负责协议、参数、服务装配和错误映射。
- Skill/Plugin 只组织 Codex 行为并调用 CLI，不直接写项目业务文件。
- ID、版本、引用、审批和事务不变量必须位于 Core/Application 生产代码。
- 人物、剧情、声音、因果、节奏、情绪和语义充分性属于 AI/作者判断。

不引入远程业务服务、FastAPI、本地 HTTP、ORM、Redis、图数据库、独立向量数据库、
Docker 或微服务。

## 多小说规则

- 每部小说是独立项目，拥有自己的 Manifest、正文、Intent、Ledger、运行产物和 SQLite。
- 全局 Project Catalog 只保存 Project ID、标题、路径和最小状态，不集中保存小说内容。
- Catalog 中移除项目只移除引用，不删除项目目录。
- 写操作必须解析到明确 Project ID 和规范化项目路径。
- 不同项目不得共享领域 UUID、SQLite 表、项目锁或运行产物。
- 不允许用标题或模糊路径决定写入目标。

## 新小说 Bootstrap

- `project create` 只建立空项目身份和存储骨架。
- 作者与 Codex 讨论后生成 Creative Brief、Story Bible、Writing Rules、Current Outline、
  主要实体和初始创作目标。
- 前置内容先进入 Bootstrap Run，不直接覆盖正式 `intent/`。
- Application 生成稳定 ID、Diff 和 approval digest。
- 只有作者批准准确 Digest 后才能应用 Bootstrap。
- Bootstrap apply 使用项目锁并在锁内重验 base revision。
- 初始化不要求一次规划整部长篇，正式 Intent 可以通过后续明确变更继续演进。
- Bootstrap 之后的 Intent Revision 也必须经过 Diff、Digest、批准和项目锁。
- 未批准 Intent 不进入正式 `intent/` 或 Session 起始环境。

## Writing Session、Draft 与 Review

- 每次创作绑定一个 Writing Session。
- Session 保存明确 Project、目标 Chapter ID、Narrative Order 边界、作者目标和 base
  revision。
- 新 Chapter ID 由 Application 预分配，不要求先创建虚假正式 Document。
- Session 起始环境提供 Intent、目标、相邻历史、稀疏 Canon 和查询能力，但不声称完备。
- 所有 Session 查询自动记录实际返回的 `retrieved_sources`。
- 正文创作前，Codex 必须向作者展示章节因果方案并允许反复调整；方案改变正式大纲时先
  完成准确 Intent Revision，再确认最终方案。
- 章节方案确认只授权开始正文，不替代 Intent 或 Publication 的准确 Digest 批准。
- 因果连贯与首遍叙述清晰是最高创作门槛，但仍属于 AI/作者语义判断，不成为 Application
  的固定情节节点、评分或充分性算法。
- Draft Revision 不可变；保存新 revision 不覆盖旧 revision 或正式正文。
- 摘要缺失、查询次数少、Review 未完成或 Canon 提案不完整不能阻止保存草稿。
- Review 必须绑定准确 Draft Revision。
- Reviewer 可以继续查询历史；Application 不判断文学结论真伪。
- Review 达到 `ready` 后，Plugin 必须先向作者展示准确 Draft Revision 和正文并等待确认；
  确认前不得开始 Entity candidate、Chapter Trace、摘要、Canon 或 Publish Plan 工作。
- 作者的草稿确认只绑定当前准确 Draft Revision；保存任何新 Draft Revision 后必须重新
  Review 和确认。草稿确认不是 Publication Digest 批准。

## 导航记忆与查询

- 默认路线是 Volume Summary → Chapter Summary → 稳定 ID → 正式原文 → AI 判断。
- Volume/Chapter Summary 是绑定正文 revision 的导航记忆，不是 Canon，也不声称完整。
- 摘要缺失或 stale 不代表正文不存在相关内容。
- 同一 Session 的 Volume、Chapter、搜索和原文读取使用同一 Narrative Order 边界。
- Writer 不能通过更换查询命令读取目标或之后的正文。
- 一个正式 Chapter 对应一个 UTF-8 Markdown Document。
- Exact Chapter Read 校验 Volume/Chapter 关系、批准状态和磁盘 bytes revision。
- FTS 只返回摘要候选位置，不能承担事实或写作许可判断。
- 每个需要稳定 ID 的查询都必须有对应发现入口。

不建设完整证据链、全量 Narrative Beat、逐句语义链接、自动全局因果图或程序化语义
充分性门槛。

## Canon 与叙事语义

- 正式正文和 Intent Canon 是完整叙事与创作方向的首要来源。
- Canon Ledger 只保存少量批准的长期重要结构化记忆。
- 缺少结构化记录不代表正文中没有发生。
- 所有长期对象使用稳定、不透明 UUID；名称、别名和编号不能作为关联键。
- Proposition 只描述命题；真假、怀疑和声明由 Assertion 表达。
- objective、character、reader 和 narrator scope 必须分离。
- 人物可以相信错误命题；错误信念不能被当作世界事实冲突。
- Story Time 与 Narrative Order 始终分离。
- Event、Assertion 和正式状态变化必须有版本化 SourceRef。
- SourceRef 必须校验 Document/Chapter、revision、excerpt 和 quote hash。
- SourceRef 只回指批准 Canon，不声称记录 AI 使用的全部历史。
- Ledger 是追加式历史；Assertion 修正使用 `retract`、`supersede` 或 `correct`。
- 人物当前状态是历史 Assertion 的计算结果，不能覆盖历史成为唯一事实源。

## 发布规则

Publish Plan 必须绑定：

- Project 和 Writing Session；
- exact Draft Revision；
- base Canon/Document revision；
- 目标 Document、Volume 和 Chapter；
- Chapter/Volume Summary 变化；
- 可选 Intent 变化；
- 可选 Canon 变化；
- Review 引用；
- approval digest。

发布前向作者展示正文、结构、摘要和 Canon Diff。只有作者明确批准准确
`publication_id + approval_digest` 后才能应用。

Publish apply 必须：

1. 获取项目写锁；
2. 在锁内重验 base revision 和批准；
3. 安装准确 manuscript bytes；
4. 更新 Volume/Chapter；
5. 保存导航摘要；
6. 安装可选 Intent；
7. 追加可选 Ledger；
8. 重建并校验 SQLite/FTS；
9. 记录完成或可前滚恢复的事务状态。

文件系统和 SQLite 没有共享事务。失败后不得截断 Ledger、覆盖未经批准内容或猜测用户
意图；恢复只能按已批准的步骤 Digest 前滚。

## 存储规则

- `novel.yaml` 保存 `ProjectManifest`。
- 正文和 Intent 使用可审查的 UTF-8 文件。
- Canon Ledger 位于 `canon/ledger/canon.jsonl`，一行一个完整版本化条目。
- Ledger sequence 连续，`base_revision` 匹配上一 revision。
- `.novel/project.sqlite` 只能由 Application 经 SQLite Adapter 创建或重建。
- SQLite 使用标准库 `sqlite3`、显式 SQL Schema、外键、WAL 和完整性检查。
- SQLite 是投影和必要运行索引，不是唯一事实源。
- 重建先生成并校验临时数据库，再安装到项目。
- `runs/` 子目录按真实 Bootstrap、Writing 或 Publication 操作按需创建。
- Draft、Review 和 Publication 是用户创作资产，不能作为普通缓存删除。

## Narrative Core 编码约定

- 基线为 Python 3.12+、Pydantic v2、pytest 和 src layout。
- 领域模型默认 `extra="forbid"`、严格校验和冻结。
- 优先使用不可变值和 `tuple`。
- 公共模型包含明确 `schema_version`，并稳定 JSON round-trip。
- 关联只保存稳定 ID；显示名称只用于展示。
- 校验器放在拥有该不变量的模型或领域模块中。
- 不为复用创建没有当前业务用例的抽象。
- 新增运行时依赖必须有当前任务依据，同时更新 `pyproject.toml` 和 `uv.lock`。
- 初始开发阶段不保留未采用协议的模型、Schema、迁移、CLI、Skill 或测试入口。

## Schema 规则

- `schemas/*.schema.json` 是生成产物，不手工编辑。
- 修改公共 Pydantic 模型后运行：

```bash
cd backend
uv run --extra dev python scripts/generate_schemas.py
```

- Schema 输出必须确定，包含模型 `schema_version` 和顶层 `x-schema-version`。
- 模型、生成 Schema、SQLite 基线、CLI、Skill 和测试必须描述同一套业务契约。

## 测试规则

- 测试夹具只保存数据，不实现业务规则。
- 新领域约束同时覆盖合法输入、非法输入和 JSON round-trip。
- Canon 测试证明 scope、时间、SourceRef 和追加式修正语义。
- 多项目测试证明 Project ID 和存储不会串写。
- Bootstrap 测试证明未批准前置内容不会进入正式 Intent。
- Session 测试证明所有查询遵守同一历史边界。
- Draft/Review 测试证明 revision 绑定且不覆盖。
- Publish 测试证明 Diff、Digest、锁、安装和恢复使用准确 bytes。
- 保持依赖边界测试，防止 Core/Application 反向依赖。
- 真实闭环测试至少连续发布多个 Chapter，并让后一个 Session 查询到前一个发布结果。

## 开发与验证命令

Codex 沙箱若不能写默认 uv cache，使用：

```bash
export UV_CACHE_DIR=/tmp/novel-uv-cache
```

完成 Python 或 Schema 改动后至少运行：

```bash
cd backend
uv run --extra dev pytest
uv run --extra dev ruff check src scripts tests
uv run --extra dev ruff format --check src scripts tests
uv run --extra dev python scripts/generate_schemas.py --check
uv run --extra dev python -m compileall -q src scripts tests
uv lock --check
```

只修改文档时检查 Markdown 本地链接、冲突术语和 `git diff --check`。

## 工作方式

- 开始前检查 `git status`，保留用户已有改动。
- 搜索优先使用 `rg` / `rg --files`。
- 修改聚焦当前业务切片，不顺手实现其他能力。
- 不用测试通过掩盖业务语义缺失。
- 不修改权威设计或测试基线迁就错误实现。
- 文档只保存能够直接指导正规创作闭环的当前事实、目标和规则。
- 除非用户明确要求，不提交、不暂存、不推送、不创建 PR。

## Definition of Done

一项开发任务只有在以下条件满足时才完成：

- 直接推进正式创作闭环；
- 实现位于正确层并保持依赖方向；
- 机械不变量由生产代码表达；
- 相关测试覆盖成功、失败和恢复；
- 公共 Schema 和 CLI 协议同步；
- 格式、静态检查、Schema 漂移和编译检查通过；
- 没有建立未使用的服务、表、命令或抽象；
- 没有覆盖用户无关改动；
- 交付报告说明实际改动、验证结果和仍未实现的闭环边界。

## Code Review Rules

审查时优先标记：

- Core 导入存储、CLI、Agent、Git、网络或桌面依赖；
- 项目选择可能把内容写入其他小说；
- 名称、别名、章节号或路径被用作长期关联键；
- Story Time 与 Narrative Order 被合并；
- Assertion scope 混合或 Proposition 携带真假；
- 正式 Event、Assertion 或状态缺少准确 SourceRef；
- Canon 修正覆盖或删除历史；
- SQLite、摘要或 Snapshot 被当作唯一事实；
- Session 查询使用不同历史边界；
- Draft、Review 或批准没有绑定准确 revision；
- 未批准内容进入正式正文、Intent 或 Ledger；
- 发布没有准确 Diff、Digest、锁或恢复；
- 业务规则出现在 Skill、CLI、脚本、夹具或 UI，而不是 Core/Application；
- 引入不服务当前创作闭环的框架、存储或复杂抽象。
