# 产品目标与业务流程

## 1. 产品定义

Novel 是一个纯本地的 AI 长篇小说创作环境。它借助 Codex 的创作与推理能力，通过 Codex
Plugin 和 `novel` CLI 完成多部小说的初始化、连续写作、历史导航、草稿管理、审核、批准
和发布。

产品的核心关系是：

> Codex 是创作大脑；Plugin 组织 AI 的工作方式；CLI 提供稳定工具；Application/Core
> 管理创作环境、权威数据和事务；作者决定创作方向并批准正式发布。

创作内环允许 AI 自由查询、写作和修订，正式数据边界必须严格。

## 2. 参与者职责

### 2.1 作者

作者负责：

- 选择或创建小说；
- 与 AI 讨论定位、人物、世界、故事方向和当前任务；
- 决定不可逆的创作方向；
- 审阅正文、导航记忆和重要 Canon 变化；
- 对准确的发布 Digest 明确批准。

“继续写”“修改一下”或对草稿的普通反馈都不构成正式发布授权。

### 2.2 Codex

Codex 负责：

- 理解小说前置内容、作者目标和当前创作位置；
- 决定需要查询哪些历史线索；
- 阅读 Chapter/Scene Summary、稀疏 Canon 和正式原文；
- 判断信息是否足够；
- 写作、审核和多轮修订；
- 为稳定稿生成 Scene Summary；
- 聚合或更新 Chapter Summary；
- 对稳定 Draft 执行人物和地点 Mention 扫描，检查已有 Entity 候选并完成身份消歧；
- 生成绑定准确 Draft revision 的 Scene Trace；
- 在作者要求补建历史线路时，读取准确批准 Scene，准备可审查的 Trace Backfill；
- 提出少量长期重要 Canon；
- 向作者报告不确定性和仍需决定的问题。

Codex 不直接修改 SQLite、Canon Ledger、正式正文或批准状态。

### 2.3 Codex Plugin

Plugin 负责：

- 识别当前小说和当前创作任务；
- 在新项目建立后安装随项目生效的精简 `AGENTS.md`，声明 Codex 工作和批准边界；
- 引导 Codex 调用正确的 CLI 命令；
- 保持 Writer、Reviewer 和发布批准的角色边界；
- 遇到版本、引用、锁或协议错误时停止对应写操作；
- 不把提示策略复制成领域规则。

Plugin 可以从自身模板创建 Codex 专用的项目根 `AGENTS.md`，但不独立保存业务数据，也不
绕过 CLI 写正式 Intent、正文、导航记忆、Ledger 或运行产物。每个 Novel Skill 在解析出
准确 Project 后主动读取该项目根 `AGENTS.md`，因此父目录工作区和当前会话无需切换即可
应用所选小说的契约；契约只作用于绑定同一 Manifest 和 Project ID 的操作。解析完成后，
Plugin 把该 Project 根作为项目工具的工作目录，并把 Codex 生成的 CLI 输入集中到项目内
`candidates/`，不在共同父目录或项目顶层散落 StoryTime、Draft 和 Summary 文件。

### 2.4 Application 与 Core

Application/Core 负责：

- 多小说项目定位；
- 项目 Bootstrap；
- 创作意图、结构、正文、导航记忆和关键 Canon 的可靠存储；
- Writing Session、Draft Revision 和 Review 记录；
- 已知名称和 Alias 的确定性候选召回、稳定 Entity ID 分配和 Scene Trace 机械校验；
- 历史 Scene Trace Backfill 的 revision、Diff、Digest、锁和恢复；
- 为 AI 提供起始创作环境和细粒度查询；
- 自动记录实际返回的来源；
- ID、路径、Schema、revision、Diff、Digest、批准和项目锁；
- 正式发布和可恢复事务；
- 从正式文件重建 SQLite 投影。

Application/Core 不负责：

- 决定人物应当如何行动；
- 判断某个剧情选择是否文学上正确；
- 用命中数判断历史信息是否充分；
- 把摘要或结构化 Canon 的缺失解释为正文中没有发生；
- 用固定规则代替 AI 审核声音、因果、节奏、情绪和主题。
- 根据字符串相似度自动判定两个名称属于同一人物、地点或其他 Entity。

## 3. 多小说业务入口

每部小说是一个独立项目，拥有自己的 Manifest、正文、意图、Ledger、导航记忆、运行产物
和 SQLite 投影。

应用维护轻量 Project Catalog，用于列出和定位本地小说，不集中保存小说内容。

```text
选择已有小说
或
创建空项目 → Bootstrap → 项目进入可创作状态
```

所有写作和发布命令必须显式解析到一个 Project ID 和项目路径，不能依赖模糊的最近目录
把内容写入其他小说。

## 4. 新小说 Bootstrap

空项目只有身份和存储骨架。作者与 Codex 讨论新小说后，AI 生成前置内容草案，包括：

- Creative Brief；
- Story Bible；
- Writing Rules；
- Current Outline；
- 主要实体；
- 第一阶段创作目标。

这些内容先进入 Bootstrap Run。Application 生成准确 Diff 和 Digest，作者批准后才安装
为项目的正式创作意图和初始结构。

Bootstrap 不要求一次规划整部长篇。前置内容可以在后续创作中通过明确的修改和批准继续
演进。

Bootstrap 完成后的 Intent 变化使用同样的“草案 → Diff → Digest → 作者批准 → 应用”
边界。它可以作为独立规划事务，也可以作为一次 Scene 发布中的可选变化，不能由 AI
直接覆盖正式 Intent。

## 5. 连续创作闭环

### 5.1 建立 Writing Session

Session 明确绑定：

- 小说项目；
- 作者目标；
- 目标 Scene；
- 目标在 Narrative Order 中的位置；
- 基础正文和 Canon revision；
- 本次创作约束。

目标 Scene 可以是尚未发布的新 Scene。Application 预分配稳定 Scene ID，并使用前后
Scene 边界表达插入位置，不要求先伪造已批准正文。

### 5.2 恢复创作环境

Application 返回起始环境：

- Creative Brief、Writing Rules 和 Current Outline；
- 本次任务与目标位置；
- 相邻 Scene 和当前 Chapter 的导航信息；
- 重要人物的稀疏 Canon 状态；
- 新 Chapter 首场所需的准确 Markdown 章标题；
- 可继续调用的查询能力。

Codex 再按需搜索摘要、读取正式原文或查询关键 Canon。除下面有明确边界的连续性窗口外，
应用不限制查询次数，也不裁决信息是否足够。

Session 起始环境明确返回 `continuity_chapter_id` 和有序
`continuity_scene_ids`：它们表示 `before_scene_id` 所在 Chapter 中、位于目标 Narrative
Order 之前的全部批准 Scene。无论这些原文是否已经出现在同一 Codex 任务、先前 Session
或模型上下文中，当前 Session 都必须逐一执行 Exact Scene Read；Application 只根据当前
Session 实际记录且 revision 匹配的 `retrieved_sources` 判定。`draft save` 在该窗口未完成
时拒绝保存。

这项硬约束只保证紧邻章的正式原文确实进入当前 Session，不判断 AI 是否理解充分。更早
历史仍由 Codex 按 Chapter Summary → Scene Summary → 稳定 ID → 正式原文的路径按需读取；
动作、对话、情绪、线索或其他依赖延伸到更早位置时继续扩展。若使用 sub-agent，它只能
辅助定位更早线索，不能替代主写作 Agent 的必读原文、目标正文创作和连续性审核。

当 Session 创建新 Chapter 时，Application 根据项目语言、Chapter number 和 title 生成
唯一 `required_chapter_heading`。Codex 必须把它原样作为首场 Draft 第一行；已有 Chapter
的后续 Scene 不重复章标题。Draft 保存、Publish prepare 和 apply/recover 都复验该字段，
避免结构中的 Chapter title 与正式 manuscript bytes 再次分离。

### 5.3 写作和审核

Codex 保存多个不可变 Draft Revision。Reviewer 必须绑定准确 Draft Revision，并可以
继续查询摘要、Canon 和原文。

语义问题形成 Review 建议，不成为 Application 硬错误。Writer 可以基于 Review 保存新
revision 并再次审核。

当 Review 结论达到 `ready` 时，除非作者明确要求只保留 Draft 或只做 Review，Plugin 必须
在同一轮转入发布准备，生成摘要、调用 `publish prepare` 和 `publish inspect`，向作者展示
准确 Diff、Publication ID 和 approval digest 后请求确认。Plugin 不能只报告“ready、尚未
发布”，也不能等作者下一次说“继续写”才补做批准交接。

### 5.4 准备发布

稳定稿产生：

- 正文候选；
- Scene Summary；
- 必要的 Chapter Summary 更新；
- Scene Trace，包括正文 Mention、候选 Entity、最终身份解析和 Entity 出现记录；
- 可选的新 Entity，由 Application 分配稳定 ID；
- 可选 Intent 更新；
- 可选的少量关键 Canon；
- Reviewer 结论。

Application 生成正文、导航记忆、Scene Trace、Entity 和 Canon Diff，并计算唯一 approval
digest。名称精确匹配只作为候选召回；AI 必须把每个纳入 Trace 的 Mention 明确解析为已有
Entity、新 Entity、匿名或忽略。`ambiguous` 不能进入 Publish Plan。

准备和检查 Publish Plan 不构成批准。只有作者在看到该计划后明确批准准确
`publication_id + approval_digest`，Plugin 才能 apply。

### 5.5 批准和发布

作者批准准确 Digest 后，Application 在项目锁内校验基础版本、安装正文、更新摘要、追加
可选 Ledger、重建投影并记录事务结果。

发布完成的新 Scene 自动进入下一次创作的导航记忆和正式原文查询范围。

### 5.6 受控回填既有 Scene Trace

升级前已经批准的 Scene 可以没有 Scene Trace。缺失不影响正文权威性，也不能由
`doctor`、投影重建或固定抽取算法静默补齐。

作者要求回填时，Codex 按 Narrative Order 逐 Scene 处理：

1. Application 通过稳定 Chapter/Scene ID 返回准确批准正文、source revision、当前
   Trace 和全库名称候选；
2. Codex 扫描名称、Alias、称谓、代词和描述性 Mention，并明确消歧；
3. Application 生成 Trace Diff、可选新 Entity Diff、Backfill ID 和 approval digest；
4. 作者批准准确 ID 与 Digest；
5. Application 在项目锁内重验正文、Canon 和旧 Trace revision，追加可选 Entity、安装
   Trace 并重建投影；
6. 失败时只对同一不可变计划前滚恢复。

Backfill 不是 Writing Session，不受 Writer 的目标前历史读取边界限制，因为它只索引已经
批准的目标正文，不生成该位置的新叙事。它可以检查完整的当前 Entity Registry 以避免重复
建档，但任何精确、唯一或模糊命中仍只属于候选。回填不得修改 manuscript、Chapter/Scene
结构、Intent、Summary、Event 或 Assertion。

## 6. 完整闭环的判定

系统只有同时满足以下条件才形成创作闭环：

- 可以选择、创建和初始化小说；
- 可以建立尚未发布的新 Scene 任务；
- AI 可以按需恢复历史并保存查询来源；
- 草稿和 Review 绑定明确 revision；
- 作者看到准确 Diff；
- 未批准内容不会进入正式正文；
- 发布失败可以检测并恢复；
- 发布后的内容可以被下一次 Session 查询。
