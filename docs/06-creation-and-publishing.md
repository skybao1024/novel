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
target_scene_id
target_chapter
before_scene_id
after_scene_id
base_canon_revision
base_document_revision
author_goal
creative_constraints
status
```

Application 为新 Scene 生成稳定 ID。目标位置必须明确：

- 全书第一 Scene；
- 已有 Chapter 末尾；
- 新 Chapter；
- 两个批准 Scene 之间。

边界不能依赖尚不存在的 manuscript Document。

当前实现为新 Scene 预分配 Scene/Document UUID，并以有间隔的整数 Narrative Order
分配新位置。首场、末尾追加和两个相邻 Scene 之间插入都由 Application 校验；如果一个
旧项目的相邻整数位置已经没有可用槽位，Session 会明确失败，而不会静默重排已批准 Scene
或改写 Ledger 历史。

### 3.2 起始环境

`session context` 返回 Creation Context。Codex 获取作者目标、Intent Canon、目标位置、
相邻历史、稀疏人物状态和可用查询能力。

之后 Codex 自主进行摘要搜索、原文读取和 Canon 查询。所有 Session 查询自动记录
`retrieved_sources`。

Plugin 要求 Codex 在当前运行首次起草正文前执行连续性的最低读取：存在前一个批准 Scene
时必须读取其完整原文；新 Chapter 还要检查上一 Chapter Summary，并读取其最后一个批准
Scene 的完整原文；直接动作、对话、情绪或其他衔接跨越更多 Scene 时继续扩展读取。该规则
不下沉为 Application 的查询次数门槛，摘要缺失或 stale 也不能替代或免除所需原文读取。

StoryTime、待保存正文和发布摘要等 Codex 文件输入集中在
`candidates/writing/<writing-session-id>/`；Session ID 分配前使用唯一 pending 子目录。
Application 不读取父工作区寻找输入，也不把 `candidates/` 当作正式 Draft 或正文。

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
- 查询次数少；
- AI 认为仍有不确定性；
- Review 尚未完成；
- 可选 Canon 提案不完整。

非法路径、错误 Session、损坏 UTF-8 或 revision 冲突可以硬阻止。

## 5. Review

Reviewer 是 AI 角色，Review 是绑定准确 Draft Revision 的运行记录。

Reviewer 可以：

- 读取草稿；
- 查看 Creative Brief 和 Writing Rules；
- 查询人物状态和重要 Event；
- 继续搜索摘要和读取历史原文；
- 检查 POV、人物声音、因果、节奏、情绪和主题；
- 报告不确定性；
- 建议修订或准备发布。

Application 校验 Review 绑定和引用存在，不判断文学结论是否正确。

Writer 可以基于 Review 保存新 Draft Revision，然后建立新 Review。旧 Review 保持不变。

Review recommendation 达到 `ready` 后，除非作者明确要求 draft-only 或 review-only，
Plugin 在同一轮生成发布所需摘要，调用 `publish prepare` 和 `publish inspect`，展示准确
Diff、Publication ID 与 approval digest 并请求作者确认。Review 的 `ready` 不构成批准，
Plugin 不得自动调用 approve/apply，但也不得把确认请求拖到作者下一次“继续写”。

## 6. 导航记忆、Intent 与 Canon 提案

准备发布的 Draft 需要生成：

- 当前 Scene Summary；
- 必要的 Chapter Summary 更新；
- 可选 Intent Revision；
- 可选关键 Canon Delta。

Scene Summary 只总结当前 Scene。Chapter Summary 只聚合本章 Scene Summary。

Canon Delta 只记录长期重要内容，不要求覆盖正文中的全部动作、对话、心理或主题变化。
摘要或 Canon 提案的语义完整性由 Codex 和作者审核，不由命中数决定。

## 7. Publish Plan

`publish prepare` 绑定准确 Session 和 Draft Revision，生成不可变 Publish Plan：

```text
publication_id
project_id
writing_session_id
draft_revision
base_canon_revision
target_document
manuscript_digest
scene_change
chapter_change
scene_summary_change
chapter_summary_change
optional_intent_change
optional_canon_change
review_refs
approval_digest
```

Application 必须机械验证：

- 目标位置和 Chapter/Scene 关系；
- 一 Scene 一 Document；
- Draft bytes 和 digest；
- base revision；
- Summary 来源 revision；
- Canon SourceRef 与候选正文；
- 所有稳定 ID 和 Schema；
- 发布步骤能够安全恢复。

`publish prepare` 接收 Scene Summary 与 Chapter Summary 的 UTF-8 文本，以及可选 Entity
ID、key changes 和 open questions。Application 根据 Session、Draft 和当前 Chapter 自动
生成 Summary 的稳定 ID 绑定、source revision、Scene 顺序和 Chapter dependency digest，
调用方不手工计算这些机械字段。可选 Intent Revision 必须已经单独通过其准确 Digest
批准且尚未应用；Publish Digest 会再次绑定该候选 revision。

## 8. 作者批准

`publish inspect` 向作者展示：

- 正文 Diff；
- Scene/Chapter 结构 Diff；
- Scene/Chapter Summary Diff；
- 可选 Intent Diff；
- 可选 Canon Diff；
- Reviewer 结论；
- 未解决问题；
- approval digest。

批准必须显式引用准确 `publication_id` 和 `approval_digest`。Publish Plan 任一受保护内容
变化后，旧批准立即失效。

## 9. 事务性发布

`publish apply` 在项目写锁内执行：

1. 重新读取 Manifest、Ledger 和目标文件；
2. 校验 base revision 和批准 Digest；
3. 把准确 manuscript bytes 写入临时文件；
4. 原子安装正式正文；
5. 创建或更新 Chapter/Scene 正式结构；
6. 保存 Scene Summary；
7. 更新 Chapter Summary；
8. 安装可选 Intent Revision；
9. 追加可选 Canon Ledger；
10. 重建并校验 SQLite/FTS；
11. 保存事务完成状态；
12. 关闭 Writing Session。

未批准内容不得进入正式正文。SQLite 更新失败不能截断已追加 Ledger，也不能静默回滚已经
安装且可恢复的权威文件。

## 10. 恢复

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

## 11. Plugin 工作方式

Plugin 在一次完整创作中：

1. 解析明确 Project；
2. 建立或恢复 Writing Session；
3. 获取 Creation Context；
4. 执行连续性最低读取并按需扩展历史查询；
5. 保存 Draft Revision；
6. 以 Reviewer 角色审核并继续查询；
7. 保存修订稿；
8. Review 达到 `ready` 后在同一轮生成摘要和可选 Canon；
9. 准备可选 Intent 更新；
10. 准备并 inspect Publish Plan；
11. 在当前轮展示 Diff、准确 ID 和 Digest 并等待作者批准；
12. 只在获得准确批准后调用 Publish Apply。

Plugin 不直接修改项目文件，不用提示词代替 Draft、Review、批准或事务记录。

## 12. 闭环验收

使用真实小说连续发布多个 Scene，必须证明：

- 新小说可以从讨论进入可创作状态；
- 新 Scene 不需要预先存在正式正文；
- AI 可以恢复必要历史而不加载整本小说；
- 所有返回来源被准确记录；
- Draft 和 Review revision 不混淆；
- 作者批准内容与最终安装 bytes 一致；
- 发布失败可恢复；
- 上一次发布内容能被下一次 Session 查询；
- 不同小说不会共享或串写数据。
