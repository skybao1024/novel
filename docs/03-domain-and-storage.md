# 领域与存储

## 1. 权威层级

| 层 | 内容 | 权威性 |
| --- | --- | --- |
| Text Canon | 作者批准的正式正文 | 完整叙事的首要来源 |
| Intent Canon | Creative Brief、Story Bible、Writing Rules、Current Outline | 创作方向的首要来源 |
| Canon Ledger | 少量批准的 Event、Assertion 和长期状态 | 可查询的重要结构化记忆 |
| Navigation Memory | Chapter/Scene Summary | 可修正的定位辅助 |
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
│   └── chapters/
├── manuscript/
├── memory/
│   ├── chapters/
│   └── scenes/
├── canon/
│   └── ledger/
│       └── canon.jsonl
├── runs/
│   ├── bootstrap/
│   ├── intent/
│   ├── writing/
│   └── publish/
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

## 4. 正文、Chapter 与 Scene

- Chapter 和 Scene 使用稳定 UUID。
- Chapter number、标题和章内序号是显示信息。
- Scene 是最小写作、审核和发布单元。
- 一个正式 Scene 对应一个 UTF-8 Markdown Document。
- 一个正式 Markdown Document 不同时承载多个 Scene。
- Chapter 通过有序 Scene ID 组合内容。
- 导出连续章节属于派生操作，不改变 Scene 的正式存储边界。

新 Scene 在 Writing Session 中预分配 ID。发布前它是运行目标，不是批准正文；发布事务
创建正式 Document 并把 Scene 纳入 Chapter。

## 5. Story Time 与 Narrative Order

Story Time 描述故事世界发生时间，Narrative Order 描述读者看到内容的顺序。二者始终
分离。

历史查询边界使用 Narrative Order，避免向 Writer 泄漏目标位置之后的正文。Story Time
用于人物状态、事件排序、倒叙和多时间线语义，不能替代阅读边界。

Story Time 可以是 ordinal、文本表达或事件锚点，不强制转换成系统 `datetime`。

## 6. 稳定身份和实体

- 所有长期对象使用不透明 UUID。
- 名称、别名和称号只用于显示和精确解析。
- Alias 不能作为 Entity、Scene、Event 或 Document 外键。
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

### 7.1 Proposition 与 Assertion

Proposition 只描述命题，不携带真假。真假、怀疑、声明和错误信念由 Assertion 表达。

Assertion scope 必须区分：

- objective；
- character；
- reader；
- narrator。

人物相信错误命题不能被当作世界事实冲突。

### 7.2 追加式修正

批准的 Ledger 是追加式历史。Assertion 修正使用：

- `retract`；
- `supersede`；
- `correct`。

不得覆盖、删除或原地修改已经批准的历史记录。

## 8. SourceRef

正式 Event、Assertion 和状态变化必须指向版本化 SourceRef。SourceRef 至少绑定：

- Document ID；
- Scene ID；
- Document revision；
- fragment ordinal；
- quote hash；
- exact excerpt。

Application 在批准或发布时验证：

- Document 和 Scene 关系正确；
- Document revision 与正式正文 bytes 一致；
- excerpt 存在于该 revision；
- quote hash 与 excerpt 一致。

AI 判断 excerpt 是否在语义上支持 Canon 提案。SourceRef 不记录一次创作依赖的全部历史，
也不构建完整证据链。

## 9. 运行产物

### 9.1 Bootstrap Run

保存前置内容草案、解析后的稳定 ID、Diff、Digest、批准和应用结果。

### 9.2 Writing Session

保存项目、目标 Scene、位置边界、作者目标、base revision、状态和实际返回来源。

### 9.3 Intent Revision

保存 Bootstrap 之后对 Creative Brief、Story Bible、Writing Rules 或 Current Outline 的
候选变化、Diff、Digest、批准和应用结果。未批准 Intent Revision 不进入正式 `intent/`。

### 9.4 Draft Revision

保存不可变 UTF-8 正文、content digest、parent revision 和创建时间。新 revision 不覆盖旧
revision。

### 9.5 Review

绑定准确 Draft Revision，保存 Reviewer 结论、不确定性、建议和查询来源。Review 不是
批准。

### 9.6 Publication

保存正文、摘要、可选 Intent/Canon Diff、approval digest、事务状态和恢复信息。

## 10. SQLite 投影

SQLite 保存正式文件的查询投影和必要的运行索引：

- 项目元数据；
- Ledger 投影；
- Entity、Assertion、Event 和 SourceRef 查询表；
- Chapter/Scene 关系；
- Navigation Summary；
- Summary FTS；
- Session、Draft、Review 和 Publication 的最小索引。

运行产物的完整内容保存在可审查文件中。SQLite 删除后，正式正文、意图、Ledger、摘要和
运行记录仍然存在，并可以恢复必要投影。

## 11. 版本和并发

- 正式变更携带 base revision。
- Draft、Review、Summary 和 Publication 绑定准确来源 revision。
- Application 计算正文和批准 Digest。
- 所有项目写操作使用同一个项目级写锁。
- 锁内再次校验 base revision，不能依赖锁前读取。
- 文件系统和 SQLite 没有共享事务，发布使用幂等步骤和前滚恢复。
