# 初始化、写作与发布

## 1. Project Bootstrap

### 1.1 建立空项目

`project create` 生成：

- Project ID；
- `novel.yaml`；
- 正式目录骨架；
- 空 Canon Ledger；
- 初始 SQLite 投影；
- Project Catalog 记录。

当创建动作由 Codex Plugin 组织时，Bootstrap Skill 随后从插件固定模板安装项目根
`AGENTS.md`，使后续 Codex 运行持续遵守项目选择、Skill 路由、正式数据和准确批准边界。
该文件不是 Intent Canon，也不由 Application/Core 生成；已有不同内容时 Plugin 必须保留
原文件并报告冲突。Skill 安装后立即读取该契约；以后其他 Novel Skill 也在解析出准确
Project 后主动读取，因此小说位于当前工作区子目录时不要求作者切换工作区或新建会话。
从解析成功开始，Skill 把 Project 根作为项目工具工作目录，并把 Codex 生成的 CLI 输入
集中到项目内按需创建的 `candidates/`，不在父目录或项目顶层散落候选文件。

空项目状态不能被当作已经具备创作环境。

### 1.2 建立 Bootstrap Run

作者与 Codex 讨论小说后，`bootstrap start` 创建隔离运行目录并绑定空项目 revision。

Codex 生成：

- `creative-brief.md`；
- `story-bible.md`；
- `writing-rules.md`；
- `current-outline.md`；
- 主要 Entity 草案；
- 初始创作目标。

Bootstrap 内容允许反复保存 revision，不直接覆盖正式 `intent/`。

当前正式 `bootstrap save` 接收四份候选 Intent 文件和可选 Bootstrap Entity Draft。
Entity Draft 只携带临时名称、类型和显示名；Application 在审批前分配并返回稳定 Entity
UUID，同一个 Bootstrap Run 的后续保存会为同一临时名称保留该 UUID。

这些由 Codex 生成的输入文件位于 `candidates/bootstrap/<bootstrap-id>/`。它们是 Plugin
暂存输入，不是正式 Intent 或 Run 资产；正式候选 revision 仍由 Application 保存。

### 1.3 检查和应用

Application 将 AI 使用的临时名称解析为稳定 ID，校验引用，并生成：

- Intent 文件 Diff；
- 初始实体和结构 Diff；
- 准确 content digest；
- 未解决问题。

作者批准 Digest 后，`bootstrap apply` 在项目锁内再次校验 base revision，安装 Intent，
追加需要的初始 Canon，建立初始结构并重建投影。

Bootstrap 完成后项目进入可创建 Writing Session 的状态。

## 2. Intent Revision

Bootstrap 之后，作者和 Codex 可以继续调整 Creative Brief、Story Bible、Writing Rules
或 Current Outline。

Intent 修改先保存候选 revision。Application 生成文件 Diff 和 approval digest，作者批准
后才在项目锁内安装。Intent Revision 可以独立应用，也可以作为一次 Publish Plan 的可选
组成部分。

未批准 Intent 不进入 Session 起始环境，AI 不能直接覆盖正式 `intent/`。

## 3. Writing Session

### 3.1 目标

Session 是一次明确的创作任务，不是固定上下文包。它保存：

```text
writing_session_id
project_id
mode
target_chapter_id
target_volume
before_chapter_id
after_chapter_id
base_canon_revision
base_document_revision
author_goal
creative_constraints
status
```

Application 为新 Chapter 生成稳定 ID。目标位置必须明确：

- 全书第一 Chapter；
- 已有 Volume 末尾；
- 新 Volume；
- 两个批准 Chapter 之间。

边界不能依赖尚不存在的 manuscript Document。

当前实现为新 Chapter 预分配 Chapter/Document UUID，并以有间隔的整数 Narrative Order
分配新位置。第一章、末尾追加和两个相邻 Chapter 之间插入都由 Application 校验；如果一个
旧项目的相邻整数位置已经没有可用槽位，Session 会明确失败，而不会静默重排已批准 Chapter
或改写 Ledger 历史。

`mode=revise` 时，作者或 Codex 必须给出准确已批准 Chapter ID。Application 复用该 Chapter
及其 Document、Volume、Narrative Order、Story Time、POV 和地点，保存准确
`base_document_revision`，并拒绝同时传入新 Volume、插入边界或元数据覆盖。修订不是新增
一个重复 Chapter，也不是直接编辑正式文件。

### 3.2 起始环境

`session context` 返回 Creation Context。Codex 获取作者目标、Intent Canon、目标位置、
相邻历史、稀疏人物状态和可用查询能力。

新 Chapter 的 Session 必须接收显式 Chapter number 和 title，并返回准确
`required_chapter_heading`。它由 Application 根据项目语言生成并保存于 Session；Codex
必须原样用作 Draft 第一行。修订 Session 沿用原 Chapter number、title 和标题。

之后 Codex 自主进行摘要搜索、原文读取和 Canon 查询。所有 Session 查询自动记录
`retrieved_sources`。

Creation Context 同时返回有界连续性窗口：存在 `before_chapter_id` 时，只返回紧邻目标的
批准 Chapter ID。当前 Session 必须执行 Exact Chapter Read；
`session continuity-status` 按 Chapter、Document、revision 和当前 Session 的
`retrieved_sources` 报告完成状态。`draft save` 在窗口未完成时拒绝保存。即使正文已在同一
Codex 任务的上下文、另一个 Session 或 sub-agent 上下文中出现，也必须为当前 Session
重新读取并记录。

更早历史仍由 Codex 用摘要定位，并在动作、对话、情绪、线索或其他依赖需要时读取准确
原文。Application 不把这部分的查询次数、摘要缺失或 stale、结构化记录完整度变成写作
许可。

修订 Context 另返回 `revision_source_chapter_id`。Codex 必须调用
`session revision-source` 读取目标旧正文；Application 校验 Chapter/Volume/Document、
磁盘 bytes 和 `base_document_revision` 后记录来源。普通 `memory read-chapter` 仍拒绝目标
或之后正文。修订源和连续性窗口都满足后才能保存 Draft。

StoryTime、待保存正文和发布摘要等 Codex 文件输入集中在
`candidates/writing/<writing-session-id>/`；Session ID 分配前使用唯一 pending 子目录。
Application 不读取父工作区寻找输入，也不把 `candidates/` 当作正式 Draft 或正文。

### 3.3 章节情节确认

完成 Creation Context、连续性窗口和必要历史查询后，Plugin 先在
`candidates/writing/<writing-session-id>/planning/` 保存版本化章节情节方案，并向作者展示。
方案保持简洁且明显短于候选正文，只包含本章与批准大纲的对应关系、进入和退出状态、人物
目标与知识边界、简洁因果和情绪主脊、选择与代价、影响视角经验的必要环境条件、下一章
条件和潜在 Intent 影响。它不穷举人物权限，不预写每次问答、反应、转场或段落，给正文的
局部动作、内心、感官、沉默和关系潜台词保留发现空间。它不是正式业务数据，也不建立低于
Chapter 的正式叙事单位。

作者可以反复调整方案。若调整改变 Current Outline 的正式承诺，Plugin 转入
`intent prepare → intent inspect → 准确批准 → intent apply`，应用后重新获取 Creation
Context，再确认最终对齐的方案。只有作者明确确认该方案版本后，Writer 才能产生正文；
正文阶段发现必须改变主要因果、人物选择、代价或退出状态时，返回方案与必要 Intent 修订。

方案确认只允许开始写作，不替代 Intent Digest 或 Publication Digest 批准。Application
继续管理 Intent 和 Publication 的机械边界，不用固定字段、情节节点数或算法判断方案是否
文学上充分。

## 4. Draft Revision

`draft save` 接收非空 UTF-8 正文，由 Application 计算 revision。

每个 Draft Revision 保存：

- Session ID；
- Draft revision；
- Parent revision；
- Content digest；
- Base document revision；
- 正文 bytes；
- 创建时间。

保存新 revision 不覆盖旧 revision，也不写正式 `manuscript/`。

以下情况不能阻止保存草稿：

- 摘要缺失；
- 连续性窗口之外的查询次数少；
- AI 认为仍有不确定性；
- Review 尚未完成；
- 可选 Canon 提案不完整。

当前 Session 尚未完成连续性窗口 Exact Chapter Read、缺少或改动
`required_chapter_heading`、非法路径、错误 Session、损坏 UTF-8 或 revision 冲突可以
硬阻止。

修订 Draft 还必须完成准确 revision source 读取，并绑定 Session 的旧 Document revision。
首个 `draft diff` 默认以旧正式正文为基线，而不是 `/dev/null`。修订后的 bytes 必须与旧
revision 不同。

只有 Review 达到 `ready` 且作者确认准确 Draft revision 后，才可以调用
`draft entity-candidates`。Application 只扫描当前 Session 历史边界内可见 Entity 的
display name 和 Alias，并返回准确文本 span 和全部精确候选。返回结果用于召回和消歧，
不自动决定身份。

## 5. Review

Reviewer 是 AI 角色，Review 是绑定准确 Draft Revision 的运行记录。

Reviewer 可以：

- 读取草稿；
- 查看 Creative Brief 和 Writing Rules；
- 查询人物状态和重要 Event；
- 继续搜索摘要和读取历史原文；
- 检查 POV、人物声音、因果、节奏、情绪、关系、视角内心、环境在场、主题、首遍可读性、
  词汇可达性和段落主次；
- 报告不确定性；
- 建议修订或准备发布。

首遍可读性要求目标读者通常能够连续读懂谁做了什么、发生了什么变化、因果或指代指向
哪里，以及当前段落最重要的内容。情绪与在场经验要求视角人物在需要时具有身体感受、私人
念头、记忆、矛盾和选择余波，环境通过视角影响压力、关系、情绪或意义；非视角人物仍只从
外部可见。Intent 可以批准有意的不确定性或特殊语体，但不能把生僻措辞、句法纠缠、逻辑
压缩、无差别描写或完全排除内心与环境误当成作者性。Application 不使用固定词表、句长、
段落模板、情绪密度或可读性分数裁决这些语义判断。

Writer 让可观察动作、身体用力、空间或物质阻力、普通物件和克制反应先承担情绪，再保留
必要解释。Reviewer 检查对称议论、时间换算、通用天气、泛化童年回忆、可替换比喻或主题
结句是否只在重复已经成立的意义，也保护服务动作的普通措辞与功能性重复不被装饰性润色
抹平。记忆、意象、氛围和长句仍可在项目声音需要且由当下经验触发时使用。

当 Plugin 随中文写作能力提供作者标记的正负校准用例时，Writer 和 Reviewer 在本任务首次
起草或审核正文前读取全部用例原文和结构说明。它们只帮助理解“场景证据先于重复解释”的
差异，不作为检测器真值、不诱导复制示例句面，也不凌驾于批准 Writing Rules 和项目声音。

Reviewer 必须给出与准确 Draft 相关的具体发现，不能用固定的一组 `passed` 标签替代因果、
清晰、视角经验、情绪变化、环境在场和项目声音判断。氛围、感官、内心或留白既不能作为
自动补写项，也不能因为不直接改变下一步情节就被自动删除。

Application 校验 Review 绑定和引用存在，不判断文学结论是否正确。

Writer 可以基于 Review 保存新 Draft Revision，然后建立新 Review。旧 Review 保持不变。

Review recommendation 达到 `ready` 后，Plugin 立即向作者展示准确 Draft revision、完整
正文和必要的 Review 结论，并请求确认该稿，然后停止当前后续工作。确认前不得调用
`draft entity-candidates`，不得生成 Chapter Trace、Chapter/Volume Summary、Canon 提案或
Publish Plan。

作者要求修改时，Writer 保存新 Draft revision 并重新 Review，再展示新准确 revision。
作者确认只适用于被展示的准确 Draft revision，不是 Intent 或 Publication 批准，也不能
复用于任何后续 revision。

## 6. 作者确认稳定 Draft

作者可以明确确认、要求修改或暂时保留 Review `ready` 的 Draft。Plugin 只有在作者明确
确认准确 Draft revision 后才能进入派生线索和发布准备。如果任务跨轮继续，后续轮必须
引用同一 revision；无法确认当前上下文中的准确确认时，重新展示 Draft 并请求确认。

这项检查点由 Plugin 管理，不新增 Application 状态或 Digest。它的目的只是避免在正文仍
可能被作者改动时提前执行人物、剧情、地点等线索解析及其它派生工作。最终正式发布仍必须
经过独立的 `publication_id + approval_digest` 批准。

## 7. 导航记忆、Intent 与 Canon 提案

作者确认的准确 Draft 需要生成：

- 当前 Chapter Summary；
- 必要的 Volume Summary 更新；
- Chapter Trace Draft；
- 可选 Intent Revision；
- 可选关键 Canon Delta。

Chapter Summary 只总结当前 Chapter。Volume Summary 只聚合本章 Chapter Summary。

Canon Delta 只记录长期重要内容，不要求覆盖正文中的全部动作、对话、心理或主题变化。
摘要或 Canon 提案的语义完整性由 Codex 和作者审核，不由命中数决定。

Chapter Trace Draft 必须覆盖 Application 返回的精确 Entity 候选，并补充 AI 识别的称谓、
代词和描述性 Mention。每个 Mention 明确解析为已有 Entity、新 Entity、匿名或忽略；新
Entity 使用临时名称，Application 在准备 Publish Plan 时分配稳定 UUID。未解决的
`ambiguous` Mention、错误文本 span、不可见 Entity ID 或未覆盖精确候选会拒绝准备发布。

## 8. Publish Plan

`publish prepare` 绑定准确 Session 和 Draft Revision，生成不可变 Publish Plan：

```text
publication_id
project_id
writing_session_id
mode
draft_revision
base_canon_revision
base_document_revision
base_chapter_summary_digest
base_volume_summary_digest
base_chapter_trace_digest
target_document
manuscript_digest
chapter_change
volume_change
chapter_summary_change
volume_summary_change
chapter_trace_change
optional_intent_change
optional_canon_change
review_refs
approval_digest
```

Application 必须机械验证：

- 目标位置和 Volume/Chapter 关系；
- Chapter 正文第一行与 Session 的 `required_chapter_heading` 完全一致；
- 一 Chapter 一 Document；
- Draft bytes 和 digest；
- base revision；
- Summary 来源 revision；
- Chapter Trace 文本 span、候选覆盖、身份解析、Chapter/Document revision 和 occurrence；
- Canon SourceRef 与候选正文；
- 所有稳定 ID 和 Schema；
- 发布步骤能够安全恢复。

修订模式还验证当前 Canon 中的 Chapter/Document 仍是 Session 锁定的同一身份和旧
revision，Volume 结构与 Chapter 元数据未变，磁盘 bytes 等于准确旧 revision，旧 Summary
和 Trace digest 未发生未批准变化。候选 Document/Chapter 保持同一 ID，只更新正文
revision。

`publish prepare` 接收 Chapter Summary、Volume Summary 和版本化 Chapter Trace Draft，
以及可选 Entity ID、key changes 和 open questions。Application 根据 Session、Draft 和
当前 Volume 自动分配 Trace、Mention、occurrence 和新 Entity ID，生成 Summary 的稳定
绑定、source revision、Chapter 顺序和 Volume dependency digest。调用方不手工计算这些
机械字段。可选 Intent Revision 必须已经单独通过其准确 Digest 批准且尚未应用；Publish
Digest 会再次绑定该候选 revision。

标题校验在 `draft save` 提前反馈，并在 Publish prepare、apply/recover 重复执行，防止
升级前保存的旧 Draft 或恢复路径绕过格式契约。

## 9. 作者批准

`publish inspect` 向作者展示：

- 正文 Diff；
- Chapter/Volume 结构 Diff；
- Chapter/Volume Summary Diff；
- Chapter Trace、Mention resolution 和新 Entity Diff；
- 可选 Intent Diff；
- 可选 Canon Diff；
- Reviewer 结论；
- 未解决问题；
- approval digest。

修订时正文 Diff 必须是旧正式正文 → 候选正文，结构 Diff 显示同一 Chapter/Document 的
revision 变化，Summary 和 Trace Diff 显示旧当前版本 → 新候选版本，不能用 `/dev/null`
掩盖覆盖范围。

批准必须显式引用准确 `publication_id` 和 `approval_digest`。Publish Plan 任一受保护内容
变化后，旧批准立即失效。

草稿确认只说明作者接受准确正文 revision，不批准随后生成的 Summary、Trace、Entity、
Intent 或 Canon Diff，不能被解释为 Publication 批准。

## 10. 事务性发布

`publish apply` 在项目写锁内执行：

1. 重新读取 Manifest、Ledger 和目标文件；
2. 校验 base revision 和批准 Digest，并在任何正式文件写入前记录 `applying` 状态；
3. 把准确 manuscript bytes 写入临时文件；
4. 新 Chapter 原子安装新文件；修订 Chapter 仅在现有 bytes 等于准确 base revision 时原子
   替换同一路径；
5. 创建或更新 Volume/Chapter 正式结构；
6. 保存 Chapter Summary；
7. 更新 Volume Summary；
8. 保存 Chapter Trace；
9. 安装可选 Intent Revision；
10. 追加包含可选新 Entity 的 Canon Ledger；
11. 重建并校验 SQLite/FTS；
12. 保存事务完成状态；
13. 关闭 Writing Session。

修订 Ledger entry 追加同一 Document ID 和 Chapter ID 的新版本。Core replay 只允许
Document 路径和 kind 不变，并只允许批准 Chapter 的正文 revision 改变；Volume、Narrative
Order、Story Time、POV、地点、状态或 Document 关联变化都会被拒绝。

未批准内容不得进入正式正文。SQLite 更新失败不能截断已追加 Ledger，也不能静默回滚已经
安装且可恢复的权威文件。

## 11. 恢复

每个 Publication 保存足够状态以判断：

- 尚未开始；
- 正文已安装；
- 导航记忆已安装；
- Intent 已安装；
- Ledger 已追加；
- 投影尚未更新；
- 全部完成。

`publish recover` 根据权威文件和步骤 Digest 前滚到一致状态。恢复不能猜测用户意图，也
不能创建未经批准的新内容。

恢复使用同一个不可变 Publish Plan 幂等重试 manuscript、导航记忆、Intent、Ledger 和
投影步骤。不同 bytes 的既有 manuscript 会产生 revision conflict，不会被恢复流程覆盖。
修订恢复接受准确旧 bytes 或已批准新 bytes，第三种 revision 一律冲突。

## 12. Plugin 工作方式

Plugin 在一次完整创作中：

1. 解析明确 Project；
2. 建立或恢复新增或修订 Writing Session；修订时读取准确 revision source；
3. 获取 Creation Context；
4. 逐一读取连续性窗口原文并确认状态，再按需扩展历史查询；
5. 生成并展示章节情节方案，按作者意见反复调整；
6. 若方案改变正式大纲，先完成准确 Intent Revision，再重新获取 Context 并确认最终方案；
7. 作者明确确认方案后保存 Draft Revision；
8. 以因果连贯、首遍叙述清晰、情绪真实和视角在场为并列基础进行 Reviewer 审核并继续查询；
9. 保存必要的修订稿并重新 Review；
10. Review 达到 `ready` 后立即展示准确 Draft revision 和正文，等待作者确认，不执行派生
    线索或发布准备；
11. 作者要求修改时回到第 9 步；作者确认准确 revision 后继续；
12. 对已确认 Draft 调用 Entity candidate scan，完成人物、地点等 Mention 消歧并生成
    Chapter Trace Draft；
13. 生成 Chapter/Volume Summary 和可选 Canon；
14. 准备可选 Intent 更新；
15. 准备并 inspect Publish Plan；
16. 展示正文、Trace、Entity、准确 ID 和 Digest 并等待作者批准；
17. 只在获得准确批准后调用 Publish Apply。

Plugin 不直接修改项目文件，不用提示词代替 Draft、Review、批准或事务记录。

## 13. 历史 Chapter Trace Backfill

历史回填使用独立命令，不建立虚假 Writing Session、Draft、Review 或 Publication。

### 13.1 Source

```text
novel trace-backfill source \
  --volume-id <id> --chapter-id <id>
```

Application 校验稳定 Volume/Chapter 关系、批准状态、Document revision 和磁盘 bytes，
返回完整正文、当前 Trace、旧 Trace digest 以及对完整当前 Entity Registry 的确定性精确
候选。这个入口只服务回填，不能作为普通 Writer 历史读取入口。

同名或身份不清时，使用
`trace-backfill entity-line --entity-id <id>` 查看候选 Entity 已有的 revision-bound
occurrence，并对相关 Chapter 再调用 `trace-backfill source` 阅读准确批准原文。线路和精确
名称仍不能自动决定身份。

### 13.2 Prepare 与批准

Codex 生成版本化 Chapter Trace Draft，覆盖全部精确候选并补充代词、称谓和描述性 Mention。
`trace-backfill prepare` 绑定 source revision；Application 物化稳定 Trace/Mention/
occurrence ID 和可选新 Entity ID，生成新旧 Trace Diff、Canon Diff、Backfill ID 和
approval digest。

`trace-backfill inspect` 向作者展示目标 Chapter、准确 revision、Mention resolutions、
occurrences、新 Entity、Diff、Backfill ID 和 Digest。只有作者明确批准准确
`backfill_id + approval_digest` 后才能 approve/apply。

### 13.3 Apply 与恢复

Application 在项目锁内：

1. 重验 Project、Canon base、Volume/Chapter/Document 和 manuscript bytes；
2. 重验旧 Trace digest；
3. 幂等追加可选新 Entity Ledger entry；
4. 安装准确 Chapter Trace；
5. 重建并校验 SQLite；
6. 记录完成状态。

发生中途失败后，只能对同一不可变计划调用 `trace-backfill recover`。Backfill 不修改
manuscript、Volume/Chapter、Summary、Intent、Event、Assertion 或 Writing Session。

Plugin 默认按 Narrative Order 从早到晚回填，降低同一章节人物被重复建档的风险；处理
顺序不是身份判断依据。每一 Chapter 都单独准备和批准，不提供“一键自动全书抽取并写入”。

## 14. 闭环验收

使用真实小说连续发布多个 Chapter，必须证明：

- 新小说可以从讨论进入可创作状态；
- 新 Chapter 不需要预先存在正式正文；
- AI 可以恢复必要历史而不加载整本小说；
- 所有返回来源被准确记录；
- Draft 和 Review revision 不混淆；
- Review `ready` 后先确认准确 Draft revision，确认前不执行派生线索或发布准备；
- 作者批准内容与最终安装 bytes 一致；
- 发布失败可恢复；
- 上一次发布内容能被下一次 Session 查询；
- 升级前 Chapter 可以通过准确 Digest 回填 Trace，且旧 Trace 修正不改正文；
- 不同小说不会共享或串写数据。
