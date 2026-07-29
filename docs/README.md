# Novel 设计文档

本目录只保存当前产品的事实、目标、业务流程和工程约束。每份文档都必须能够直接指导
正规创作闭环的产品和工程实现。

## 文档索引

| 文档 | 内容 |
| --- | --- |
| [产品目标与业务流程](./01-product-and-business-flow.md) | 产品定义、参与者职责、多小说创作闭环和完成标准 |
| [系统架构](./02-system-architecture.md) | Plugin、CLI、Application、Core、Adapter 和依赖边界 |
| [领域与存储](./03-domain-and-storage.md) | 权威数据、稳定身份、Canon、运行产物、项目目录和 SQLite |
| [导航记忆与查询](./04-memory-and-query.md) | 创作起始信息、摘要导航、准确原文、查询边界和来源记录 |
| [本地运行与多项目管理](./05-local-runtime-and-projects.md) | Project Catalog、CLI 协议、锁、恢复和本地运行规则 |
| [初始化、写作与发布](./06-creation-and-publishing.md) | Bootstrap、Writing Session、Draft、Review、批准和发布事务 |

## 统一目标

Novel 必须支持以下连续业务：

1. 管理多部相互独立的本地小说。
2. 由作者和 Codex 讨论新小说，并把批准后的前置内容初始化为正式创作环境。
3. 为每次创作建立明确的目标、位置、规则和基础版本。
4. 让 Codex 通过摘要、稀疏 Canon 和准确原文按需恢复历史。
5. 保存多个不可变草稿 revision，并让 Reviewer 绑定准确草稿继续审核和查询。
6. 在 Scene 达到稳定 Review 的同一轮向作者展示正文、导航记忆和可选 Canon 的准确
   Diff，并请求准确 Digest 批准。
7. 只在作者批准准确 Digest 后事务性发布。
8. 让发布结果自动成为下一次创作的正文和导航记忆。

## 长期边界

- AI 负责创作和开放式语义判断。
- 应用负责多项目定位、数据、查询、版本、批准、发布和恢复。
- 正文与作者意图是完整叙事和创作方向的首要来源。
- Chapter/Scene Summary 只用于导航，不是 Canon，也不声称完整。
- Event、Assertion 和人物状态只保存少量长期重要 Canon。
- SourceRef 只为批准的结构化 Canon 提供准确回指，不构成完整证据链。
- 每个新发布 Scene 必须携带绑定准确 Draft revision 的 Scene Trace。名称和 Alias 的精确
  命中只生成候选，AI 负责结合历史消歧；未解决的歧义不能进入发布计划。
- Scene Trace 是可修正、可失效的导航索引，只记录已解析 Entity 的出现线路，不把字符串
  匹配或 AI 抽取结果升级为世界事实。
- 升级前已经批准但缺少 Scene Trace 的历史 Scene 只能通过独立 Trace Backfill
  事务补建。回填绑定准确正文 revision，展示 Trace 和可选新 Entity Diff，并经过准确
  Digest 批准；项目打开、`doctor` 或 SQLite 重建不得自动生成语义记录。
- 应用不使用任意检索命中数、固定上下文包或结构化记录完整度判断语义是否充分；唯一的
  写作前读取门槛是当前 Session 对紧邻前场景所在 Chapter 的有界 Exact Scene Read 窗口。
- 新 Chapter 首场的 Markdown 章标题由 Session 给出准确值，并由 Draft 和 Publish 链路
  机械校验，不能只依赖 AI 自行保持格式。
- SQLite 和检索索引可以从正式文件重建，不能成为唯一事实源。
- 每项新增结构和命令必须服务于已经定义的创作闭环。
