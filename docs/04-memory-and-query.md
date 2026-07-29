# 导航记忆与查询

## 1. 目标

Application 的任务是向 Codex 提供当前创作所需的线索和准确数据，而不是替代 AI 回答
开放式语义问题。

信息恢复分为两部分：

1. Session 起始创作环境；
2. AI 主导的动态查询循环。

核心原则是：

> 先提供明确起点，再用摘要定位，用正式原文恢复语义，由 AI 决定是否继续。

## 2. Session 起始创作环境

Writing Session 建立后，Application 返回一个 Creation Context：

- Project ID 和 Session ID；
- 作者目标；
- 目标 Scene ID 和 Narrative Order 边界；
- Creative Brief；
- Writing Rules；
- Current Outline 中与目标直接相关的部分；
- 当前 Chapter 信息；
- 前一个 Scene 的摘要和正式原文入口；
- 前一个 Scene 所在 Chapter 的连续性窗口 Chapter ID 和有序 Scene ID；
- 新 Chapter 首场准确的 `required_chapter_heading`，否则为 `null`；
- 主要人物的稀疏 Canon 状态；
- 当前 base revision；
- 可继续调用的查询能力。

Creation Context 是确定性的起始视图，不声称包含全部相关历史。它列出的
`continuity_scene_ids` 是唯一例外：这些是 `before_scene_id` 所在 Chapter 中、位于目标
Narrative Order 之前的全部批准 Scene，构成保存 Draft 前的有界必读窗口。

当前 Writing Session 必须逐一执行 Exact Scene Read，并用
`session continuity-status` 确认 `satisfied: true`。Application 比对 Scene、Document 和
revision 以及当前 Session 的 `retrieved_sources`；摘要、`previous_scene_text_available`、
已有模型上下文、其他 Session 记录或 sub-agent 报告都不能替代。本窗口为空时通常表示
全书第一 Scene。

Application 只对这个确定的窗口设置 `draft save` 前置条件，不以更广泛的读取次数、摘要
完整度或结构化记录数量判断语义充分性。更早历史仍按 Chapter Summary → Scene Summary →
稳定 ID → 正式原文导航，由 AI 根据动作、对话、情绪、线索等依赖决定是否继续。

## 3. 分层导航

默认导航路线：

```text
Chapter Summary
→ Scene Summary
→ 稳定 Chapter/Scene ID
→ 正式 Scene 原文
→ AI 判断是否继续
```

### 3.1 Scene Summary

Scene Summary 只描述一个批准 Scene revision，包含：

- Scene、Chapter 和 Document ID；
- 章内顺序；
- source revision；
- 简短 summary；
- 主要 Entity ID；
- 少量 key changes；
- 少量 open questions。

摘要不是 Canon，也不声称覆盖全部对话、动作、心理、伏笔或主题。

### 3.2 Scene Trace

Scene Trace 是绑定一个批准 Scene revision 的 Entity 出现线路。它区分：

- 文本 Mention：name、alias、pronoun 或 description；
- 身份解析：existing、new、anonymous 或 ignored；
- Scene occurrence：present、mentioned、recalled 或 offstage；
- prominence：focus、supporting、cameo 或 background。

Application 对准确 Draft 扫描当前 Session 边界内可见的 display name 和 Alias，返回精确
候选及 span。Codex 结合当前人物、地点、Event 和准确历史原文处理同名、称谓、代词和隐含
指代。精确候选必须被 Scene Trace Draft 覆盖，但匹配本身不决定身份。

升级前历史 Scene 的 Trace 通过 `trace-backfill source` 读取目标 Scene 的准确批准正文。
该维护查询不属于 Writing Session，不改变 `retrieved_sources`，并可查看完整当前 Entity
Registry 以减少重复 Entity；它不得被 Writer 用来绕过 Session Narrative Order 边界。
回填后的 occurrence 仍只是定位候选，事实判断继续读取准确 Scene 原文。

### 3.3 Chapter Summary

Chapter Summary 从本章当前 Scene Summary 聚合，保存参与的 Scene ID 和摘要 Digest。

它帮助 AI 选择大致章节，不能覆盖 Scene Summary 或正文含义。

### 3.4 Summary Search

摘要搜索可以使用：

- 关键词；
- Entity ID；
- Chapter ID；
- Narrative Order 边界；
- 摘要 FTS 排序。

搜索只返回候选位置和匹配原因，不返回“事实成立”或“信息已经充分”的结论。

## 4. 统一历史边界

同一 Writing Session 的所有历史导航命令必须使用相同 Narrative Order 边界：

- Chapter 列表可以返回目录元数据，但不能返回依赖目标或之后 Scene 的 Chapter Summary；
- Scene 列表不能返回目标 Scene 或之后的摘要；
- Summary Search 不能返回目标边界之后的候选；
- Exact Scene Read 只能读取目标之前的批准 Scene。

边界由 Session 的 `before_scene_id`、`after_scene_id` 或明确插入位置计算。AI 不能通过换
一个查询命令绕过边界。

Reviewer 默认使用与 Writer 相同的读者历史边界。若作者明确要求全局结构审核，必须建立
具有不同权限语义的 Review 任务，不能静默向 Writer 暴露未来正文。

## 5. 准确原文读取

Exact Scene Read 使用稳定 Chapter ID 和 Scene ID。Application 验证：

- Scene 属于 Chapter；
- Scene 位于 Session 历史边界之前；
- Scene 已批准；
- Scene 对应一个正式 manuscript Document；
- Scene revision、Document revision 和磁盘 bytes 一致；
- 文件是 UTF-8 Markdown。

返回：

- Chapter、Scene 和 Document ID；
- Document revision；
- Story Time 和 Narrative Order；
- POV 和地点；
- 完整 Scene 正文；
- 当前 revision 的 SourceRef；
- 明确的机械 warning。

摘要缺失或 stale 不阻止准确原文读取。

## 6. 稀疏 Canon 查询

Application 提供：

- Entity 名称和 Alias 解析；
- 绑定 Draft revision 的精确 Entity 候选；
- Entity 在目标 Narrative Order 之前的 Scene/Chapter 出现线路；
- 人物在目标 Scene entry/exit 的稀疏状态；
- 人物知识与 objective 世界事实分离的 Assertion；
- Event 列表与查找；
- Event 链；
- SourceRef 展开。

Event 链只表示明确批准的少量关系，不是完整因果图。每个需要 ID 的查询必须有对应的发现
入口，AI 不应被要求预先知道不可见 UUID。

## 7. `retrieved_sources`

Writing Session 自动记录 Application 实际返回的来源：

```text
retrieved_source_id
writing_session_id
retrieval_kind
chapter_id
scene_id
document_id
document_revision
retrieval_reason
retrieved_at
```

摘要查询和准确原文读取使用不同 `retrieval_kind`。记录只说明“Application 返回过什么”，
不说明 AI 一定使用了这些内容，也不说明已经覆盖全部相关历史。

所有 Session 查询通过 Application 记录，Plugin 不在提示词中手工维护来源列表。

## 8. 摘要生成和失效

- Scene Summary 只读取对应 Scene 生成和审核。
- Chapter Summary 只聚合所属 Scene Summary。
- 正文 revision 改变后，旧 Scene Summary 立即 stale。
- 任一依赖 Scene Summary 缺失、stale 或 Digest 改变时，Chapter Summary stale。
- 查询结果明确返回 stale 状态。
- stale 摘要只能帮助定位，不能作为当前事实。

## 9. 检索边界

当前系统使用结构化过滤和摘要 FTS。正式正文不建立全量语义索引，也不建立：

- 全量 Narrative Beat；
- 逐句证据链接；
- 完整人物行为和心理索引；Scene Trace 只索引 Entity Mention 和出现位置；
- 自动全局因果图；
- 完整证据图；
- 语义充分性门槛。

Entity 线路索引是经过批准的有限候选召回增强，不扩展为全量行为或证据图。任何检索增强
仍只能定位候选，最终事实来自正式原文和批准 Canon。

## 10. 查询可用性的验收

- AI 能从 Session 起始环境开始创作；
- AI 能发现 Chapter、Scene、Entity 和 Event 的稳定 ID；
- 所有查询遵守同一目标历史边界；
- 摘要缺失不会阻断原文；
- 正文 revision 漂移会被拒绝；
- retrieved sources 与实际返回内容一致；
- 删除 SQLite 后可以恢复摘要投影和查询；
- AI 不需要一次加载整本小说。
