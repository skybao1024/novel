# 领域与存储

## 1. 权威层级

| 层 | 内容 | 权威性 |
| --- | --- | --- |
| Text Canon | 作者批准的正式正文 | 完整叙事的首要来源 |
| Intent Canon | Creative Brief、Story Bible、Writing Rules、Current Outline | 创作方向的首要来源 |
| Canon Ledger | 少量批准的 Event、Assertion 和长期状态 | 可查询的重要结构化记忆 |
| Navigation Memory | Volume/Chapter Summary | 可修正的定位辅助 |
| Run Artifacts | Bootstrap、Session、Draft、Review、Publication | 非 Canon 工作记录 |
| SQLite / FTS | 查询投影和必要运行索引 | 可重建 |

模型临时解释、摘要、FTS 命中、Draft 和 Review 不会自动升级为正式事实。

## 2. 多项目身份

全局 Project Catalog 只保存项目引用：

```text
project_id
title
project_path
status
```

每部小说的 `novel.yaml` 保存项目自身身份。Catalog 丢失时可以重新添加项目路径，不影响
小说内容。

所有项目命令最终解析出 Project ID 和规范化绝对路径。项目内容不得跨项目引用 UUID 或
共享 SQLite 表。

## 3. 项目目录

```text
my-novel/
├── novel.yaml
├── candidates/                 # Plugin 按需创建的非正式 CLI 输入暂存区
├── intent/
│   ├── creative-brief.md
│   ├── story-bible.md
│   ├── writing-rules.md
│   └── current-outline.md
├── structure/
│   └── volumes/
├── manuscript/
├── memory/
│   ├── volumes/
│   ├── chapters/
│   └── traces/
├── canon/
│   └── ledger/
│       └── canon.jsonl
├── runs/
│   ├── bootstrap/
│   ├── intent/
│   ├── writing/
│   ├── publish/
│   └── trace-backfill/
└── .novel/
    ├── project.sqlite
    ├── locks/
    └── tmp/
```

`candidates/` 不由 `project create` 预建，只由 Plugin 在真实 Bootstrap、Intent、Writing
或 Publication 工作需要文件输入时按需创建。它按稳定操作 ID（ID 尚未分配时按唯一 pending
目录）组织，是非权威暂存区，不属于 Application 业务数据，不参与 Project 健康、SQLite
重建、批准或恢复，也不能替代 `runs/` 中的不可变资产。Codex 不得把候选输入放到项目父
目录、项目顶层或正式业务目录。

`runs/` 子目录按真实操作按需创建，空项目不预建通用任务、缓存或候选目录。

## 4. 正文、Volume 与 Chapter

- Volume 和 Chapter 使用稳定 UUID。
- Volume number、Volume title、Chapter number、Chapter title 和章在卷内的位置是显示信息。
- Chapter 是最小写作、审核和发布单元。
- 一个正式 Chapter 对应一个 UTF-8 Markdown Document。
- 一个正式 Markdown Document 不同时承载多个 Chapter。
- Volume 通过有序 Chapter ID 组合内容。
- 既有批准 Chapter 的修订保持 Chapter、Document、Volume 和 Narrative Order 身份不变，只
  产生新的正文 revision、Summary 和 Chapter Trace。
- 每个 Chapter Document 第一行保存由 Session 锁定的准确 Markdown
  `required_chapter_heading`；Chapter 结构保存 number 和 title，发布链路验证两者一致。
- 导出连续章节属于派生操作，不改变 Chapter 的正式存储边界。

新 Chapter 在 Writing Session 中预分配 ID。发布前它是运行目标，不是批准正文；发布事务
创建正式 Document 并把 Chapter 纳入 Volume。

修订 Chapter 在 Session 开始时绑定当前批准 Document revision。应用只允许同一 Document
路径的准确旧 bytes 被批准新 bytes 原子替换；Canon Ledger 追加同一 Document ID 和 Chapter
ID 的新版本记录，replay 选择最新版本作为当前投影。旧 Ledger entry、Draft、Review、
Publication 和 approval 不被覆盖或删除。

## 5. Story Time 与 Narrative Order

Story Time 描述故事世界发生时间，Narrative Order 描述读者看到内容的顺序。二者始终
分离。

历史查询边界使用 Narrative Order，避免向 Writer 泄漏目标位置之后的正文。Story Time
用于人物状态、事件排序、倒叙和多时间线语义，不能替代阅读边界。

Story Time 可以是 ordinal、文本表达或事件锚点，不强制转换成系统 `datetime`。

## 6. 稳定身份和实体

- 所有长期对象使用不透明 UUID。
- 名称、别名和称号只用于显示和精确解析。
- Alias 不能作为 Entity、Chapter、Event 或 Document 外键。
- Bootstrap 中的临时名称由 Application 映射到最终稳定 ID。
- ID 分配结果必须在作者批准前展示，并随 Bootstrap 结果保存。

## 7. 稀疏 Canon

结构化 Canon 只保存对后续创作长期有价值的内容：

- 人物和地点等主要 Entity；
- 世界事实；
- 人物知识和错误信念；
- 重要位置、目标、持有物、身份和承诺；
- 重大 Event；
- 少量明确的 Event 关系。

缺少结构化记录不代表正文中没有发生。

### 7.1 Entity 身份解析

名称、Alias、称谓、代词和描述性短语不是长期关联键。Draft 中的 Entity Mention 先保存
文本 span 和候选，再由 AI 明确解析为：

- `resolved_existing`：绑定目标 Narrative Order 之前可见的既有 Entity ID；
- `resolved_new`：由 Application 在同一 Publish Plan 中分配新 Entity ID；
- `anonymous`：无需长期身份的匿名章节人物或群体；
- `ignored`：不是本次线路索引需要记录的叙事实体；
- `ambiguous`：尚不能安全决定，不能进入 Publish Plan。

Application 可以机械扫描已知 display name 和 Alias，但精确命中只产生候选。模糊匹配、
唯一命中、出现频率或固定评分不能自动建立身份。

### 7.2 Proposition 与 Assertion

Proposition 只描述命题，不携带真假。真假、怀疑、声明和错误信念由 Assertion 表达。

Assertion scope 必须区分：

- objective；
- character；
- reader；
- narrator。

人物相信错误命题不能被当作世界事实冲突。

### 7.3 追加式修正

批准的 Ledger 是追加式历史。Assertion 修正使用：

- `retract`；
- `supersede`；
- `correct`。

不得覆盖、删除或原地修改已经批准的历史记录。

## 8. SourceRef

正式 Event、Assertion 和状态变化必须指向版本化 SourceRef。SourceRef 至少绑定：

- Document ID；
- Chapter ID；
- Document revision；
- fragment ordinal；
- quote hash；
- exact excerpt。

Application 在批准或发布时验证：

- Document 和 Chapter 关系正确；
- Document revision 与正式正文 bytes 一致；
- excerpt 存在于该 revision；
- quote hash 与 excerpt 一致。

AI 判断 excerpt 是否在语义上支持 Canon 提案。SourceRef 不记录一次创作依赖的全部历史，
也不构建完整证据链。

## 9. 运行产物

### 9.1 Bootstrap Run

保存前置内容草案、解析后的稳定 ID、Diff、Digest、批准和应用结果。

### 9.2 Writing Session

保存项目、模式、目标 Chapter、位置边界、作者目标、base revision、修订源要求、状态和实际
返回来源。

### 9.3 Intent Revision

保存 Bootstrap 之后对 Creative Brief、Story Bible、Writing Rules 或 Current Outline 的
候选变化、Diff、Digest、批准和应用结果。未批准 Intent Revision 不进入正式 `intent/`。

### 9.4 Draft Revision

保存不可变 UTF-8 正文、content digest、parent revision 和创建时间。新 revision 不覆盖旧
revision。

### 9.5 Review

绑定准确 Draft Revision，保存 Reviewer 结论、不确定性、建议和查询来源。Review 不是
批准。Review 达到 `ready` 后，Plugin 先把准确 Draft revision 和正文交给作者确认；这是
非权威的创作检查点，不新增正式运行产物，也不替代 Publication Digest 批准。任何新 Draft
revision 都使先前确认失效。

### 9.6 Publication

只在作者确认准确 Draft revision 后准备，保存正文、摘要、Chapter Trace、可选新 Entity、
可选 Intent/Canon Diff、approval digest、事务状态和恢复信息。修订计划还保存旧正文、旧
Chapter/Volume Summary 和旧 Trace 的准确 base digest。

### 9.7 Chapter Trace Backfill

保存目标批准 Chapter、准确正文 revision、base Canon revision、旧 Trace digest、候选
Chapter Trace、可选新 Entity、Diff、approval digest、批准和恢复状态。它不保存或替代
manuscript bytes。

## 10. Chapter Trace

每个新发布 Chapter revision 对应一个 Chapter Trace。它包含：

- Chapter、Volume、Document 和准确 source revision；
- Mention 的文本 span、surface text、形式、机械精确候选和 AI 实际考虑的候选；
- 最终 resolution status、稳定 Entity ID 和简短解析理由；
- 每个已解析 Entity 在该 Chapter 的 presence kind、prominence 和关联 Mention；
- 扫描备注。

Chapter Trace 是 Navigation Memory，不是 Canon。正文 revision 变化后立即 stale。Volume
出现记录由 `Entity → Chapter Trace → Chapter → Volume` 查询推导，不在 Entity 中重复保存。
匿名和忽略 Mention 不创建 Entity；已解析 Mention 必须准确归入一个 Chapter occurrence。

既有 Chapter 的 Trace 缺失或错误时使用 Chapter Trace Backfill。每个计划同时绑定：

- Project、Volume、Chapter 和 Document ID；
- 当前批准正文 revision；
- 准备时的 Canon revision；
- 准备时旧 Trace 的 digest，缺失时为 `null`；
- 新 Trace、可选新 Entity、Diff 和 approval digest。

应用时先在锁内重验这些绑定。新 Entity 先追加到 Ledger，再安装引用它的 Trace；SQLite
最后重建。回填完成文件进入 `runs/trace-backfill/<backfill-id>/`。回填按 Narrative Order
执行是 Plugin 的工作规则，Application 不用名称或处理顺序猜测实体身份。

## 11. SQLite 投影

SQLite 保存正式文件的查询投影和必要的运行索引：

- 项目元数据；
- Ledger 投影；
- Entity、Assertion、Event 和 SourceRef 查询表；
- Volume/Chapter 关系；
- Navigation Summary；
- Chapter Trace 和 Entity/Chapter occurrence；
- Summary FTS；
- Session、Draft、Review 和 Publication 的最小索引。

Trace Backfill 的完整计划保存在运行文件中；当前查询只需要其最终 Chapter Trace 和可选
Entity 投影，不为 Backfill Run 建立额外业务表。

运行产物的完整内容保存在可审查文件中。SQLite 删除后，正式正文、意图、Ledger、摘要和
运行记录仍然存在，并可以恢复必要投影。

## 12. 版本和并发

- 正式变更携带 base revision。
- Draft、Review、Summary 和 Publication 绑定准确来源 revision。
- Application 计算正文和批准 Digest。
- 所有项目写操作使用同一个项目级写锁。
- 锁内再次校验 base revision，不能依赖锁前读取。
- 文件系统和 SQLite 没有共享事务，发布使用幂等步骤和前滚恢复。
