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
- 在派生线索和发布准备前审阅并确认准确 Draft revision；
- 审阅导航记忆和重要 Canon 变化；
- 对准确的发布 Digest 明确批准。

“继续写”“修改一下”或对草稿的普通反馈都不构成草稿确认或正式发布授权。确认准确
Draft revision 也不构成 Publication Digest 批准。

### 2.2 Codex

Codex 负责：

- 理解小说前置内容、作者目标和当前创作位置；
- 决定需要查询哪些历史线索；
- 阅读 Volume/Chapter Summary、稀疏 Canon 和正式原文；
- 判断信息是否足够；
- 写作、审核和多轮修订；
- 在作者要求重写既有批准 Chapter 时读取准确旧正文，并保留 Chapter、Document 和结构身份；
- Review 达到 `ready` 后先向作者展示准确 Draft revision 和正文并等待确认；
- 只为作者已经确认的准确 Draft revision 生成 Chapter Summary；
- 聚合或更新 Volume Summary；
- 对作者已经确认的准确 Draft 执行人物和地点 Mention 扫描，检查已有 Entity 候选并完成
  身份消歧；
- 生成绑定准确 Draft revision 的 Chapter Trace；
- 在作者要求补建历史线路时，读取准确批准 Chapter，准备可审查的 Trace Backfill；
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
- 已批准 Chapter 的同身份正文 revision、导航记忆和 Trace 受控替换；
- 已知名称和 Alias 的确定性候选召回、稳定 Entity ID 分配和 Chapter Trace 机械校验；
- 历史 Chapter Trace Backfill 的 revision、Diff、Digest、锁和恢复；
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
边界。它可以作为独立规划事务，也可以作为一次 Chapter 发布中的可选变化，不能由 AI
直接覆盖正式 Intent。

## 5. 连续创作闭环

### 5.1 建立 Writing Session

Session 明确绑定：

- 小说项目；
- 作者目标；
- 目标 Chapter；
- 目标在 Narrative Order 中的位置；
- 基础正文和 Canon revision；
- 本次创作约束。

目标可以是尚未发布的新 Chapter，也可以是一个准确指定的已批准 Chapter。新 Chapter 由
Application 预分配稳定 Chapter ID，并使用前后 Chapter 边界表达插入位置，不要求先伪造已
批准正文。修订模式复用既有 Chapter、Document、Volume 和 Narrative Order，绑定准确旧
Document revision，不允许借修订改变 Story Time、POV、地点或结构身份。

### 5.2 恢复创作环境

Application 返回起始环境：

- Creative Brief、Writing Rules 和 Current Outline；
- 本次任务与目标位置；
- 相邻 Chapter 和当前 Volume 的导航信息；
- 重要人物的稀疏 Canon 状态；
- 目标 Chapter 所需的准确 Markdown 章标题；
- 可继续调用的查询能力。

修订 Session 还返回 `revision_source_chapter_id` 和 `base_document_revision`。Codex 必须通过
专用 `session revision-source` 读取准确旧正文；普通历史查询仍然只能读取目标之前的
Chapter。旧正文读取与连续性窗口共同构成保存修订 Draft 前的机械前置条件。

Codex 再按需搜索摘要、读取正式原文或查询关键 Canon。除下面有明确边界的连续性窗口外，
应用不限制查询次数，也不裁决信息是否足够。

Session 起始环境明确返回 `continuity_volume_id` 和有序
`continuity_chapter_ids`：存在 `before_chapter_id` 时，它只包含紧邻目标的那个批准
Chapter。无论该原文是否已经出现在同一 Codex 任务、先前 Session 或模型上下文中，当前
Session 都必须执行 Exact Chapter Read；Application 只根据当前
Session 实际记录且 revision 匹配的 `retrieved_sources` 判定。`draft save` 在该窗口未完成
时拒绝保存。

这项硬约束只保证紧邻章的正式原文确实进入当前 Session，不判断 AI 是否理解充分。更早
历史仍由 Codex 按 Volume Summary → Chapter Summary → 稳定 ID → 正式原文的路径按需读取；
动作、对话、情绪、线索或其他依赖延伸到更早位置时继续扩展。若使用 sub-agent，它只能
辅助定位更早线索，不能替代主写作 Agent 的必读原文、目标正文创作和连续性审核。

每个新建或修订 Chapter 的 Session 都保存显式 Chapter number 和 title。Application 根据
项目语言生成唯一 `required_chapter_heading`，Codex 必须把它原样作为 Draft 第一行。
Draft 保存、Publish prepare 和 apply/recover 都复验该字段，避免结构中的 Chapter title
与正式 manuscript bytes 分离。

### 5.3 章节情节确认与大纲修订

Codex 完成连续性读取和必要历史查询后，先生成作者可见的版本化章节情节方案，不立即写
正文。方案只描述本章功能、进入与退出状态、人物当下目标与知识边界、简洁因果和情绪主脊、
选择与代价、影响视角经验的必要环境条件，以及对 Current Outline 的影响；不预写每次问答、
反应、转场或段落，也不建立穷举人物权限表。它是 `candidates/` 中的讨论输入，不是正式正文、
Intent、Canon、Review 或发布批准。

作者可以反复修改、拒绝、合并或替换方案。如果修改只是细化现有大纲，Codex 更新方案后
继续请求确认；如果修改会改变批准大纲中的章节转折、顺序、关键选择、退出状态或后续依赖，
Codex 必须先通过独立 Intent Revision 展示准确 Diff 和 Digest，并在作者批准后应用。
涉及 Creative Brief 或 Story Bible 的变化也进入同一明确 Intent 边界，不能藏在章节方案
或正文中。

Intent Revision 应用后，Codex 重新获取 Creation Context，确认 Writing Session 使用新的
批准 Intent，并再次向作者展示最终对齐的章节方案。只有作者明确确认该版本后才能开始正文。
创作中若必须改变主要因果、人物选择、代价或退出状态，重新回到这一循环；不改变确认因果链
的局部措辞和动作衔接不需要再次确认。

章节方案确认只是正文创作许可，不构成 Intent 或 Publication 批准。该流程首先由 Plugin
执行，不新增 Application 的语义裁决或固定情节充分性算法。

### 5.4 写作和审核

Codex 保存多个不可变 Draft Revision。Reviewer 必须绑定准确 Draft Revision，并可以
继续查询摘要、Canon 和原文。

在作者明确要求、批准 Intent、事实连续性和结构身份之后，Writer 和 Reviewer 把因果连贯、
首遍叙述清晰、情绪真实和视角人物的在场经验作为并列创作基础。目标读者既应当连续理解
发生了什么、人物依据当时所知为何这样行动，以及行动或结果如何形成下一步条件，也应当
感受到视角人物如何注意、回避、记忆、身体反应和承受余波，以及环境与关系压力如何塑造
当下。人物声音、项目特异性、氛围、意象和语言技巧不能掩盖断裂因果；情节效率也不能弥补
人物无内心、场景可任意替换或选择没有情绪余波。

情绪优先由可观察的选择、身体动作、空间或物质阻力、普通物件和克制反应在场景中累积，
解释随后且只保留必要部分。已经由动作成立的意义，不再用对称议论、时间换算、通用天气、
泛化童年回忆、多重可替换比喻或主题结句重复放大；记忆和比喻只有在批准历史或当下触发使其
具体，并改变人物此刻反应时才进入正文。普通准确措辞和服务动作的重复不因“润色”被自动
替换。这是场景建构偏好，不是对白描、短句或无内心的统一要求。

中文写作路径还应让 Writer 和 Reviewer 在本任务首次处理正文前读取作者标记的正负对照
用例原文及其结构说明，而不是只接收抽象禁令。对照用例用于校准场景证据、解释克制与功能性
重复，不是 AI 检测真值，也不得覆盖项目 Writing Rules、正式正文声音或作者专属锚点。

清晰度包括常用准确词汇、明确的动作与指代关系、段落主次和与叙事重要性匹配的篇幅；不得
用固定生僻字表、统一句长或程序化可读性分数替代 AI 和作者对准确正文的判断。Review
检查方案与连续性、因果、首遍清晰、人物行为、视角内心、情绪与关系变化、环境在场、项目
声音和模板化 AI 表达；这些维度都由 AI 和作者结合准确正文判断，不用固定全通过标签代替
具体发现。

语义问题形成 Review 建议，不成为 Application 硬错误。Writer 可以基于 Review 保存新
revision 并再次审核。

当 Review 结论达到 `ready` 时，Plugin 必须立即向作者展示准确 Draft revision、完整正文
和必要的 Review 结论，并请求作者确认该稿。此时停止，不调用 Entity candidate scan，不
生成 Chapter Trace、Chapter/Volume Summary、Canon 提案或 Publish Plan。

作者可以确认、要求修改或暂时保留。任何修改都保存为新 Draft revision，并重新完成准确
Review 和作者确认；旧确认不适用于新 revision。这个检查点用于避免为作者尚未接受的正文
生成派生线索，不属于 Application 的正式批准状态，也不替代后续 Publication Digest 批准。

### 5.5 准备发布

作者确认准确 Draft revision 后，稳定稿才进入发布派生工作（新增或修订均相同）：

- 正文候选；
- Chapter Summary；
- 必要的 Volume Summary 更新；
- Chapter Trace，包括正文 Mention、候选 Entity、最终身份解析和 Entity 出现记录；
- 可选的新 Entity，由 Application 分配稳定 ID；
- 可选 Intent 更新；
- 可选的少量关键 Canon；
- Reviewer 结论。

Application 生成正文、导航记忆、Chapter Trace、Entity 和 Canon Diff，并计算唯一 approval
digest。修订计划的 Diff 以准确旧正文、旧 Chapter/Volume Summary 和旧 Chapter Trace 为
基线，并把这些 base digest 纳入批准保护。名称精确匹配只作为候选召回；AI 必须把每个
纳入 Trace 的 Mention 明确解析为已有 Entity、新 Entity、匿名或忽略。`ambiguous` 不能
进入 Publish Plan。

准备和检查 Publish Plan 不构成批准。只有作者在看到该计划后明确批准准确
`publication_id + approval_digest`，Plugin 才能 apply。草稿确认不能复用为这项批准。

### 5.6 批准和发布

作者批准准确 Digest 后，Application 在项目锁内校验基础版本、安装正文、更新摘要、追加
可选 Ledger、重建投影并记录事务结果。

修订发布原子替换同一 manuscript 路径，只允许磁盘处于准确旧 revision 或已批准新
revision；Ledger 追加同一 Document/Chapter ID 的新版本记录，不删除旧记录。恢复仍只对同一
不可变 Publication 前滚。

发布完成的新 Chapter 自动进入下一次创作的导航记忆和正式原文查询范围。

### 5.7 受控回填既有 Chapter Trace

升级前已经批准的 Chapter 可以没有 Chapter Trace。缺失不影响正文权威性，也不能由
`doctor`、投影重建或固定抽取算法静默补齐。

作者要求回填时，Codex 按 Narrative Order 逐 Chapter 处理：

1. Application 通过稳定 Volume/Chapter ID 返回准确批准正文、source revision、当前
   Trace 和全库名称候选；
2. Codex 扫描名称、Alias、称谓、代词和描述性 Mention，并明确消歧；
3. Application 生成 Trace Diff、可选新 Entity Diff、Backfill ID 和 approval digest；
4. 作者批准准确 ID 与 Digest；
5. Application 在项目锁内重验正文、Canon 和旧 Trace revision，追加可选 Entity、安装
   Trace 并重建投影；
6. 失败时只对同一不可变计划前滚恢复。

Backfill 不是 Writing Session，不受 Writer 的目标前历史读取边界限制，因为它只索引已经
批准的目标正文，不生成该位置的新叙事。它可以检查完整的当前 Entity Registry 以避免重复
建档，但任何精确、唯一或模糊命中仍只属于候选。回填不得修改 manuscript、Volume/Chapter
结构、Intent、Summary、Event 或 Assertion。

## 6. 完整闭环的判定

系统只有同时满足以下条件才形成创作闭环：

- 可以选择、创建和初始化小说；
- 可以建立尚未发布的新 Chapter 任务；
- 可以对准确已批准 Chapter 建立同身份修订任务；
- AI 可以按需恢复历史并保存查询来源；
- 草稿和 Review 绑定明确 revision；
- 作者看到准确 Diff；
- 未批准内容不会进入正式正文；
- 发布失败可以检测并恢复；
- 发布后的内容可以被下一次 Session 查询。
