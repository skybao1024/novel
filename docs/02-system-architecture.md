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
切换工作区或新建会话。

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

Plugin 要求 Codex 在当前运行首次起草前至少读取紧邻的批准 Scene 完整原文；新 Chapter
还要检查上一 Chapter Summary 和最后一个批准 Scene 完整原文，并在直接衔接未结束时扩展
读取。除此之外，AI 决定查询顺序、查询次数和停止时机。Application 不把这项 Plugin 行为
规则实现为查询次数或摘要完整度门槛。

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
