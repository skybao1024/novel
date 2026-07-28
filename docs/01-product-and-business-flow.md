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
应用所选小说的契约；契约只作用于绑定同一 Manifest 和 Project ID 的操作。

### 2.4 Application 与 Core

Application/Core 负责：

- 多小说项目定位；
- 项目 Bootstrap；
- 创作意图、结构、正文、导航记忆和关键 Canon 的可靠存储；
- Writing Session、Draft Revision 和 Review 记录；
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
- 可继续调用的查询能力。

Codex 再按需搜索摘要、读取正式原文或查询关键 Canon。应用不限制查询次数，也不裁决
信息是否足够。

Plugin 设定连续性的最低读取规则：只要目标之前存在批准 Scene，Codex 在当前运行首次起草
正文前必须读取紧邻 Scene 的完整原文；新 Chapter 还要查看上一 Chapter Summary，并读取
其最后一个批准 Scene 的完整原文。若动作、对话、情绪或其他直接衔接尚未结束，Codex 继续
读取承载该衔接的相关 Scene。该规则约束 Codex 工作方式，不变成 Application 的查询次数
门槛。

### 5.3 写作和审核

Codex 保存多个不可变 Draft Revision。Reviewer 必须绑定准确 Draft Revision，并可以
继续查询摘要、Canon 和原文。

语义问题形成 Review 建议，不成为 Application 硬错误。Writer 可以基于 Review 保存新
revision 并再次审核。

### 5.4 准备发布

稳定稿产生：

- 正文候选；
- Scene Summary；
- 必要的 Chapter Summary 更新；
- 可选 Intent 更新；
- 可选的少量关键 Canon；
- Reviewer 结论。

Application 生成正文、导航记忆和 Canon Diff，并计算唯一 approval digest。

### 5.5 批准和发布

作者批准准确 Digest 后，Application 在项目锁内校验基础版本、安装正文、更新摘要、追加
可选 Ledger、重建投影并记录事务结果。

发布完成的新 Scene 自动进入下一次创作的导航记忆和正式原文查询范围。

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
