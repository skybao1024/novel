# Novel 项目设计文档

> 最后更新：2026-07-24

## 文档导航

| 文档 | 状态 | 说明 |
| --- | --- | --- |
| [系统设计方案](./01-system-design.md) | 讨论稿 v0.2 | 产品愿景、总体架构、叙事记忆和工作流 |
| [计算架构与技术栈](./02-computing-architecture.md) | 本地架构候选方案 | Python、SQLite、CLI、桌面端和存储选型 |
| [MVP Narrative Core](./03-mvp-core-architecture.md) | 核心架构讨论稿 | 时间化 Canon、Assertion、事件、状态与检索 |
| [历史情节的检索](./04-historical-plot-retrieval.md) | 业务设计考虑项 | Source Ref、结构化检索、FTS5和可选语义检索 |
| [运行环境与本地分发](./05-runtime-and-local-distribution.md) | 技术设计候选方案 | 开发环境、CLI、Sidecar、安装程序和版本兼容 |

## 当前已确定方向

1. 产品是纯本地客户端，不建设远程业务服务或网页生成端。
2. MVP 聚焦 Codex Plugin / Skill、CLI 和 Narrative Core。
3. Narrative Core 使用 Python + Pydantic。
4. 本地数据库使用 SQLite；MVP 使用 Python `sqlite3` 和显式 SQL migrations。
5. 正文、人工设定和已批准 Canon Change Set 是权威记录；SQLite 是运行投影。
6. 世界事实、人物知识、错误信念和叙述声明使用 Proposition + Assertion 表达。
7. 故事时间和叙述顺序从第一版分离。
8. MVP 使用 Source Ref、结构化检索和 FTS5；不引入独立向量数据库。
9. 桌面端延后实现，但 Core 和 CLI 从第一版保持可封装为本地 Sidecar。

## 尚需细化

- 第一版 Pydantic Schema
- SQLite 表结构和索引
- State Delta 与 Canon Change Set 格式
- 人物历史状态重建算法
- 连续性测试小说夹具
- Codex Plugin / Skill 与 CLI 协议
- macOS、Windows 的安装和签名流水线
