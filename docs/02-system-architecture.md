# 系统架构

## 1. 总体结构

Novel 是纯本地模块化单体。长期调用链固定为：

```text
作者
→ Codex
→ Codex Plugin / Skill
→ novel CLI
→ Narrative Application
→ Narrative Core
→ Filesystem / SQLite Adapters
```

项目不依赖远程业务服务。Codex 提供 AI 能力，Novel 管理本地小说数据和创作事务。

## 2. Python 依赖方向

```text
novel_core
    ↑
novel_application
    ↑
novel_adapters
    ↑
novel_cli
```

### 2.1 `novel_core`

Core 定义稳定领域语义和机械不变量：

- Project、Entity、Document、Chapter、Scene；
- Story Time 与 Narrative Order；
- Proposition、Assertion、Event 和 SourceRef；
- Bootstrap、Writing Session、Draft、Review 和 Publish 的公共契约；
- revision、Digest、状态转换和批准约束；
- Canon Ledger replay。

Core 只能依赖 Python 标准库和 Pydantic，不导入数据库、CLI、Agent、Git、桌面或网络
实现。

### 2.2 `novel_application`

Application 编排用例：

- Project Catalog 和项目选择；
- Project Bootstrap；
- Session 建立和起始创作环境；
- 导航与 Canon 查询；
- retrieved sources 记录；
- Draft 和 Review；
- Publish prepare、approve、apply 和 recover；
- Ledger 追加与 Projection 重建。

Application 依赖端口，不导入具体文件或 SQLite 实现。

### 2.3 `novel_adapters`

Adapters 实现：

- 全局 Project Catalog；
- 项目文件和运行产物；
- Canon Ledger；
- SQLite projection 与摘要 FTS；
- 项目锁；
- 应用数据目录中的脱敏 CLI 诊断日志；
- 正式正文的原子安装和事务恢复记录。

SQLite 是投影和必要运行索引，不拥有小说的唯一事实。

### 2.4 `novel_cli`

CLI 是 Codex Plugin、开发者和本地应用共同使用的稳定协议边界。它负责：

- 参数解析；
- 项目选择；
- Application 服务装配；
- JSON Envelope；
- CLI 调用关联 ID、阶段和错误分类；
- 错误到稳定 code/exit code 的映射。

CLI 不承载领域规则，也不直接写业务表或正式项目文件。
诊断日志不是业务事实、审批证据或恢复依据。

### 2.5 Codex Plugin

Plugin 由围绕正规创作流程的 Skills 组成：

- 项目选择与 Bootstrap；
- 新项目的 Codex 项目级工作边界；
- Writing Session 与历史导航；
- Draft 与 Review；
- Publish 准备和批准边界。

Skill 只能通过 CLI 执行业务动作，不能直接修改 SQLite、Ledger、正式正文、摘要或运行
记录。Bootstrap Skill 可以从插件内的固定模板创建项目根 `AGENTS.md`；该文件只约束
Codex 行为，不属于小说业务数据，且不得覆盖作者已有的不同项目指令。Novel Skills 在
选择准确项目后显式读取该文件，不依赖工作区启动时的递归发现，也不要求作者为子目录小说
切换工作区或新建会话。选择后，Skill 把准确 Project 根作为项目工具工作目录，并仅在
项目内按需创建非正式 `candidates/` 暂存 CLI 输入，不向父工作区或项目顶层散落候选文件。

当准确 Draft 的 Review 达到 `ready` 时，Skill 在同一轮进入 Publish prepare/inspect 并
展示批准 Digest；作者确认仍是独立的下一步，Application 不从 Review 自动推导批准。

## 3. 服务边界

Application 按真实业务能力组织服务，不建立通用工作流框架：

| 服务 | 职责 |
| --- | --- |
| `ProjectCatalogService` | 注册、列出、解析和移除本地项目引用 |
| `ProjectService` | 初始化项目、检查权威记录、重建投影 |
| `BootstrapService` | 保存前置内容草案、生成 Diff、批准并应用 |
| `IntentService` | 准备、批准并应用持续演进的创作意图 |
| `CreationContextService` | 返回 Session 起始环境 |
| `NavigationMemoryService` | Chapter/Scene 导航、搜索和准确原文读取 |
| `EntityResolutionService` | 在 Session 边界内召回名称候选并把已消歧 Draft 输入物化为 Scene Trace |
| `SceneTraceBackfillService` | 为准确批准历史 Scene 准备、批准、应用和恢复 Trace 回填 |
| `CanonQueryService` | 实体、人物状态、Event 和 SourceRef 查询 |
| `WritingSessionService` | 建立目标、边界和基础 revision |
| `DraftService` | 保存和读取不可变 Draft Revision |
| `ReviewService` | 保存绑定准确草稿的 Review |
| `PublicationService` | 准备、批准、应用和恢复发布事务 |

只有当前业务需要的方法进入端口，不为假设场景建立抽象层。

## 4. CLI 业务分组

CLI 必须按用户和 AI 能理解的业务动作组织：

```text
novel project ...
novel bootstrap ...
novel intent ...
novel session ...
novel memory ...
novel draft entity-candidates ...
novel trace-backfill ...
novel query ...
novel draft ...
novel review ...
novel publish ...
novel doctor
novel rebuild
novel schema ...
```

每个命令通过同一套 Application Service 实现。桌面或其他入口只能复用这些用例，不能
建立第二套业务语义。

## 5. AI 创作环境

Application 不向 AI 输出一个声称完备的固定上下文包。它提供：

1. 确定性的 Session 起始环境；
2. 可反复调用的细粒度查询；
3. 准确且带 revision 的正文；
4. 实际返回来源的自动记录。

Creation Context 返回 `before_scene_id` 所在 Chapter 中、位于目标 Narrative Order
之前的全部批准 Scene ID。当前 Writing Session 必须对这些 ID 逐一完成 revision 匹配的
Exact Scene Read；`DraftService` 在保存前通过 `WritingSessionService` 验证当前 Session
的实际 `retrieved_sources`，未完成时拒绝保存。已有 Codex 对话上下文、其他 Session 的
读取记录或 sub-agent 转述都不能替代它。

该机制只表达一个有界、机械的紧邻章连续性前置条件，不以任意命中数判断语义充分性。
更早历史仍由 AI 通过摘要定位并按需读取正式原文；AI 决定其查询顺序、扩展范围和停止
时机。

新 Chapter 的章标题也是机械契约。Application 在 Writing Session 中保存准确
`required_chapter_heading`，Creation Context 将其交给 Codex，`DraftService` 和
`PublicationService` 分别在草稿保存、发布准备、应用及恢复时验证正文第一行。标题文字、
编号、标点和空格不由 Skill 临时推导。

稳定 Draft 的实体解析使用另一条机械边界。Application 在当前 Session 的 Narrative
Order 边界内，用已有 Entity display name 和 Alias 扫描准确 Draft，返回全部精确命中
候选；它不根据命中唯一、模糊分数或最近出现自动决定身份。Codex 将精确命中与代词、称谓
和描述性 Mention 合并，明确解析为已有 Entity、新 Entity、匿名或忽略，再提交
Scene Trace Draft。Application 校验文本 span、候选覆盖、稳定 ID 和 Draft revision；
任何 `ambiguous` Mention 都拒绝进入 Publish Plan。

已发布 Scene Trace 进入 Navigation Memory 和 SQLite 可重建投影。它帮助 Entity →
Scene → Chapter 定位，不是 Canon，也不能代替准确 Scene 原文。

历史 Scene 不通过伪造 Draft 或 Publication 补建 Trace。`SceneTraceBackfillService`
读取准确批准正文，使用完整当前 Entity Registry 召回候选，生成绑定正文、当前 Canon
revision 和旧 Trace digest 的不可变计划。Application 仍只校验 span、候选覆盖、ID、
revision、批准和事务状态；AI 负责身份解析。Backfill 可以在同一批准计划中追加必要的新
Entity，但不能修改正文、结构、摘要、Intent 或其他 Canon。

## 6. 本地技术基线

- Python 3.12+；
- Pydantic v2；
- 标准库文件与 `sqlite3`；
- 显式 SQL Schema；
- SQLite WAL；
- FTS5 只索引导航摘要；
- UTF-8 Markdown 正文和意图文档；
- JSON、JSONL 和版本化公共 Schema；
- pytest 和 Ruff。

不引入远程业务服务、ORM、Redis、图数据库、独立向量数据库、Docker 或微服务。

## 7. 工程规则

- 每个长期对象使用稳定、不透明 UUID。
- 名称、别名、章节号和文件名不作为关联键。
- 正式文件变更必须绑定 base revision。
- 写操作必须通过 Application 并获取项目锁。
- 公共 JSON 契约包含 `schema_version`。
- 运行产物按 Session/Publication ID 隔离并保持可审查。
- 未批准草稿和 Review 不进入正式正文或 Canon。
- 删除 SQLite 后能够从项目正式文件重建查询投影。
- 新能力必须证明它属于初始化、创作、审核或发布闭环。
