# 桌面端与 Agent Runtime 开发计划

## 1. 文档状态

- 制定日期：2026-08-05；
- 状态：已确定的后续产品方向，尚未实现；
- 首个目标 Runtime：Codex；
- 现有 Codex Plugin：继续作为独立、完整的工作方式保留；
- 适用范围：Novel 桌面客户端、Agent Runtime 安装与授权、Agent 会话、工具网关和运行时切换；
- 不改变范围：Project、Intent、正文、Canon、Writing Session、Draft、Review、批准、发布和恢复
  的现有业务语义。

本文定义从当前“Codex Plugin 调用 `novel` CLI”扩展到普通作者可安装桌面客户端的开发
顺序。它是实施计划，不表示仓库已经具备所列桌面或 Runtime 能力。当前已经实现的契约仍以
[产品目标与业务流程](./01-product-and-business-flow.md)、[系统架构](./02-system-architecture.md)
和其他现行设计文档为准。

## 2. 产品目标

普通作者安装 Novel 后，不需要自己在终端配置 Agent，即可在首次引导中：

1. 查看 Novel 支持的 Agent Runtime；
2. 选择并确认安装一个 Runtime，默认推荐首个完整验证的 Runtime；
3. 使用该 Runtime 官方支持的账号或 API Key 完成授权；
4. 在 Novel 桌面端创建、选择和连续创作本地小说；
5. 安装其他 Runtime，并在安全边界内切换；
6. 始终由 Novel 管理小说数据、版本、查询、批准、发布和恢复；
7. 在需要完整 Codex 工作区体验时，继续单独使用现有 Codex Plugin。

目标关系从单一入口扩展为两个并存入口：

```text
Codex 原生工作方式
作者 → Codex → Novel Plugin / Skill → novel CLI → Application / Core

Novel 桌面工作方式
作者 → Novel Desktop → Agent Runtime → Novel Tool Gateway
     → novel CLI → Application / Core
```

桌面端不是新的小说业务系统。两个入口必须调用同一套 Application 用例，产生相同的稳定
ID、revision、Diff、Digest、批准、锁和恢复结果。

## 3. 已锁定的产品决定

### 3.1 Agent 是可替换的创作大脑

Novel 不自行复制 Codex 的通用 Agent Loop。创作、推理、检索决策和文学审核继续由受支持
的 Agent Runtime 完成；Novel 提供小说专用环境、工具和机械边界。

每个 Runtime 可以有自己的模型、会话格式和上下文优化，但不得成为小说事实或批准状态的
权威来源。

### 3.2 Novel 项目是跨 Runtime 的长期记忆

Runtime Thread 只是执行状态。切换 Runtime 时，不迁移或伪造供应商内部对话历史，而是从
以下 Novel 权威资产恢复工作：

- 当前批准 Intent；
- Writing Session 目标和 Narrative Order 边界；
- Volume/Chapter Summary；
- 稀疏 Canon；
- 按需读取的准确正式原文；
- 准确 Draft、Review 和 Publication 状态。

因此，上下文控制继续遵守现有的“确定性起始环境 → 摘要定位 → 正式原文 → AI 判断是否
继续”路径，不把整部小说重复塞入每次模型请求。

### 3.3 凭据归 Runtime 所有

Novel 可以发起登录并展示账户状态，但不读取、复制或自行刷新 Runtime 的账号令牌。

对于 Codex：

- Codex App Server 管理 ChatGPT OAuth、令牌持久化和自动刷新；
- Codex 保存 API Key；
- Novel 只把用户一次性输入传给 Codex 登录接口；
- Novel 不读取 `auth.json`，也不把 API Key 写入项目、配置、日志或遥测；
- 凭据存储优先配置为操作系统 Keyring。

Codex App Server 当前公开提供 `account/read`、`account/login/start`、登录通知、
`account/logout`、限额和用量查询，适合作为自定义客户端的账户边界。具体协议以固定 Runtime
版本生成的 Schema 为准：

- [Codex App Server](https://learn.chatgpt.com/docs/app-server)
- [Codex 身份验证](https://learn.chatgpt.com/docs/auth)
- [Codex SDK](https://learn.chatgpt.com/docs/codex-sdk)

### 3.4 安装必须经过用户确认

首次引导可以默认选中推荐 Runtime，但不能在用户不知情时下载安装第三方程序或接受服务
条款。确认页至少展示：

- Runtime 名称和供应商；
- 版本、下载大小和安装来源；
- 支持的登录方式；
- 账号/API 计费归属；
- 许可证和服务条款入口；
- Novel 将授予的本地项目权限。

### 3.5 正式批准不能委托给 Agent

Agent 可以查询、起草、Review 和准备 Diff，但以下动作只能由桌面 Host 响应作者的明确 UI
操作调用：

- 批准 Intent Digest；
- 确认准确 Draft revision；
- 批准准确 `publication_id + approval_digest`；
- 执行 Publish apply/recover；
- 退出账号、删除 Runtime 或改变全局权限。

Agent 工具列表不得暴露可以绕过这些 UI 检查点的宽泛命令执行入口。

## 4. 目标架构

```text
Novel Desktop
├── Project UI
├── Writing / Review / Publication UI
├── Runtime Center
│   ├── Runtime Registry
│   ├── Installer / Updater / Rollback
│   ├── Auth Broker
│   ├── Process Supervisor
│   ├── Capability Negotiation
│   └── Runtime Session Registry
├── Runtime Adapters
│   ├── Codex App Server Adapter
│   ├── Future Protocol Adapter
│   └── Future Agent-specific Adapter
├── Novel Tool Gateway
│   ├── AI-visible typed tools
│   └── Host-only approval tools
└── novel CLI --json
    └── Application → Core → Filesystem / SQLite Adapters
```

### 4.1 依赖边界

现有 Python 依赖方向保持不变：

```text
novel_core
    ↑
novel_application
    ↑
novel_adapters
    ↑
novel_cli
```

Desktop、Runtime Host 和供应商 SDK 位于这条业务链之外。它们可以依赖 `novel` CLI 的
版本化 JSON 协议，但以下依赖一律禁止：

- Core/Application 导入 Codex、其他 Agent、桌面框架或网络 SDK；
- Runtime Adapter 直接写项目正式文件、Ledger 或 SQLite；
- Desktop 根据 UI 状态重新实现 revision、Digest、批准或发布规则；
- Agent 凭据进入小说项目目录；
- Runtime Thread ID 进入 Canon 或正式创作身份。

### 4.2 Runtime Center

Runtime Center 只保存应用级运行信息：

```text
runtime_id
adapter_protocol
installed_version
installation_path
credential_profile_id
capabilities
update_channel
health
```

它位于 Novel 应用数据目录，不属于任何小说项目。不同 Runtime 和凭据 Profile 使用隔离的
配置、缓存、日志和进程目录。

### 4.3 Runtime Manifest

每个可安装 Runtime 必须有由 Novel 维护并签名或随应用发布的 Manifest，至少包含：

```text
manifest_version
runtime_id
display_name
vendor
runtime_version
adapter_protocol
supported_platforms
artifact_source
artifact_digest
signature_metadata
license_url
terms_url
auth_modes
tool_modes
minimum_novel_version
install_size
```

安装器不得执行远程返回的任意 Shell 脚本，不使用管理员权限进行全局安装，也不静默调用
`npm install -g`。Runtime 安装到 Novel 应用数据目录，新版本并行安装并在健康检查通过后
原子切换；至少保留一个可回滚版本。

### 4.4 Runtime Adapter 最小契约

所有 Tier 1 Runtime Adapter 必须支持：

- 安装、发现、版本和健康检查；
- 读取登录状态、开始登录、取消登录和退出登录；
- 创建、恢复、中断和关闭 Agent Thread；
- 流式输出文本、工具调用、状态和错误；
- 接收用户输入和 Host 审批结果；
- 声明模型、上下文、用量和工具能力；
- 把供应商错误映射为 Novel Runtime 稳定错误类别；
- 在进程异常后判断可恢复或需要新建 Thread。

只支持一次性命令输出、无法提供授权状态或无法可靠处理工具审批的 CLI，最多作为实验性
兼容 Runtime，不能标记为完整支持。

### 4.5 Novel Tool Gateway

桌面 Agent 不直接获得任意 `novel` Shell 权限。Tool Gateway 把现有 CLI 用例映射为有类型
的最小工具集，并分为：

| 工具级别 | 调用者 | 示例 |
| --- | --- | --- |
| AI 可读 | Agent | Session Context、摘要搜索、原文读取、Canon 查询 |
| AI 可准备 | Agent | 保存 Draft、保存 Review、准备 Intent/Publication Diff |
| 作者确认 | Desktop Host | Draft revision 确认、Digest 批准 |
| Host 执行 | Desktop Host | apply、recover、账号和 Runtime 管理 |

首个纵向验证可以在 Codex App Server 中注册动态工具，并在 Host 内调用 `novel --json`。
当第二个 Runtime 需要复用工具时，再把同一契约提供为本地 stdio MCP Server。MCP 只是协议
适配，不新增业务服务或第二套领域语义。

## 5. Codex Runtime 设计

### 5.1 进程与协议

首个 Adapter 使用固定版本的 Codex App Server，以本地 stdio JSON-RPC 通信。初期不监听
TCP/WebSocket 端口，也不把 App Server 暴露给局域网。

每个受支持版本必须：

1. 固定 Codex Runtime 版本；
2. 从该版本生成 TypeScript 或 JSON Schema；
3. 在 CI 中检查客户端绑定与 Schema 漂移；
4. 通过初始化、认证、Thread、Turn、工具、审批和退出的契约测试；
5. 升级失败时继续使用上一个已验证版本。

Python SDK 当前可以控制本地 App Server，并随发布版本携带固定 Codex CLI Runtime，适合
技术验证。由于 SDK/部分 App Server 能力仍可能演进，产品 Adapter 应依赖版本化协议契约，
不把 beta SDK 的便利封装当作 Novel 长期领域接口。

### 5.2 隔离目录

Novel 管理的 Codex 使用独立目录，例如：

```text
<Novel App Data>/agent-runtimes/codex/
├── versions/
├── current/
├── profiles/<credential-profile-id>/home/
└── diagnostics/
```

启动前创建准确 `CODEX_HOME`，并在该 Profile 配置：

```toml
cli_auth_credentials_store = "keyring"
```

Novel 不复用或修改用户默认的 `~/.codex`。高级用户可以选择“使用已有 Codex”，但该模式
必须明确说明共享安装、配置和退出登录可能影响已有 CLI/IDE 会话。

### 5.3 ChatGPT 登录流程

```text
account/read
→ 未登录
→ account/login/start(type=chatgpt)
→ Novel 用系统浏览器打开 App Server 返回的 authUrl
→ 等待 account/login/completed
→ 接收 account/updated
→ account/read 复验账户和 planType
```

失败、超时和用户取消必须返回登录页，不得猜测已经成功。浏览器回调不可用时提供 Codex
官方支持的 Device Code 流程。

Novel 不能承诺或绕过：

- 用户所在地区的服务可用性；
- ChatGPT Workspace 的成员、角色或管理员政策；
- 订阅额度、速率限制和功能差异；
- 账号共享、订阅池化或代登录。

### 5.4 API Key 登录流程

```text
用户在安全输入框粘贴 API Key
→ Novel 直接调用 account/login/start(type=apiKey)
→ 清除 UI 字段和临时内存
→ 等待 login/completed / account/updated
→ account/read 复验
```

禁止把 Key 放入命令行参数、环境级长期变量、剪贴板历史、Novel 配置、诊断日志或崩溃
报告。API Key 模式在 UI 中明确显示为按 OpenAI API 用量计费，不显示为“使用 ChatGPT
订阅”。

### 5.5 账户和用量 UI

Runtime Center 只从 Codex 账户接口读取并展示：

- 当前是否登录；
- `authMode`；
- 可用时的账号和 `planType`；
- Rate Limit 状态；
- 可用时的用量摘要；
- 重新登录和退出登录入口。

Novel 不在自己的数据库复制令牌。非敏感展示信息默认也从 Runtime 重新读取，只有确有离线
展示需要时才建立带过期时间的最小缓存。

## 6. Runtime 切换与上下文成本

### 6.1 切换条件

只允许在以下边界切换 Runtime：

- 当前 Agent Turn 已结束或已安全中断；
- 没有等待处理的 Agent 工具调用；
- 没有正在执行的 apply/recover；
- 当前 Writing Session 和准确 Draft revision 已持久化。

切换不改变 Project ID、Writing Session ID、Narrative Order 或任何业务 revision。

### 6.2 Session 映射

应用级注册表可以保存：

```text
project_id
writing_session_id
runtime_id
runtime_thread_id
last_turn_status
last_used_at
```

这只是恢复索引，不是项目权威数据。注册表丢失时可以从 Novel Session 重新建立 Agent Thread。

### 6.3 新 Runtime 的恢复包

切换后创建新 Thread，只发送当前任务需要的起始信息：

1. 项目级 Agent 工作边界；
2. Writing Session Context；
3. 当前确认的章节方案；
4. 当前准确 Draft/Review 状态；
5. 可继续动态调用的 Novel 工具。

更早历史仍由 Agent 使用摘要和准确原文查询。不得为“保持会话感”默认注入整部小说、全部
旧聊天或全部 Canon Ledger。

### 6.4 成本可见性

Runtime 能返回用量时，Desktop 按 Runtime、Project、Session 和 Turn 展示非权威成本统计。
这类统计只帮助用户控制预算，不参与 Draft 保存、Review 结论或发布许可。

首个版本至少提供：

- 本次 Turn 用量；
- 当前 Session 累计用量；
- 订阅模式与 API 计费模式的清晰区别；
- 可配置的提示阈值；
- 达到阈值后由作者决定继续，而不是 Application 代替作者判断语义已经充分。

## 7. 安全与隐私基线

- Agent 默认只以准确 Project 根作为工作目录；
- 默认使用 Runtime 可提供的最小文件系统权限；
- 业务工具全部经过 Tool Gateway allowlist；
- 网络权限由 Runtime 自身能力和用户设置管理，Novel 不静默扩大；
- 账号、API Key、正文、Prompt 和 Review 不进入通用诊断日志；
- 供应商原始事件只在本地按明确保留策略保存，默认不作为 Novel 业务资产；
- Runtime 崩溃不能损坏已持久化的 Draft、Review 或 Publication；
- 卸载 Runtime 只删除明确的 Runtime 安装和 Profile，不删除任何小说项目；
- 卸载 Novel 默认也不删除小说项目；
- Runtime 下载、更新和条款变更需要可追踪版本；
- 每个新 Runtime 在进入稳定通道前完成凭据、沙箱、工具越权和审批绕过测试。

## 8. 分阶段实施计划

开发按纵向闭环推进，不先建设万能 Runtime 框架。

### 阶段 0：冻结桌面 Runtime 契约

目标：把产品决定变成可以编码和验收的最小接口。

工作：

- 定义 Desktop、Runtime Host、Tool Gateway 与现有 CLI 的依赖边界；
- 定义 Runtime Manifest、能力矩阵、稳定错误类别和 Session 映射；
- 定义 AI 可见工具与 Host-only 工具清单；
- 选择桌面壳技术，验证进程管理、系统浏览器、Keyring、中文输入、签名和自动更新；
- 确认 Codex Runtime 的取得、分发、许可证、商标和服务条款边界；
- 建立威胁模型和脱敏日志规则。

退出标准：

- 有一个不依赖具体桌面框架的 Runtime Adapter 契约；
- 已明确 Codex 固定版本和可分发路径；
- 没有任何 Agent/桌面依赖进入 Core/Application；
- 桌面技术选型有可运行的进程、浏览器回调和 Keyring 小样。

预计投入：1 至 2 人周。

### 阶段 1：Codex 端到端技术验证

目标：不追求完整 UI，先证明 Codex 可以成为 Novel 托管的创作大脑。

工作：

- 安装并启动固定版本 Codex App Server；
- 使用隔离 `CODEX_HOME`；
- 完成 ChatGPT、Device Code、API Key、状态读取和退出登录；
- 创建、恢复和中断 Thread/Turn；
- 接收流式文本、工具请求、审批和错误；
- 暴露最小 Novel 动态工具，完成项目选择、Session Context、Exact Chapter Read、Draft save
  和 Review save；
- 验证 Host-only Publication 批准不能被 Agent 直接调用；
- 记录一次完整创作的上下文和用量数据。

退出标准：

- 不打开终端即可完成 Codex 登录；
- 使用 ChatGPT 订阅和 API Key 两条路径分别跑通；
- Agent 能通过工具完成一个准确 Draft/Review 纵向切片；
- 进程崩溃和重启后 Novel 业务资产不丢失；
- 能明确回答 Codex 集成是否满足产品化要求。

预计投入：2 至 3 人周。

### 阶段 2：单 Runtime 桌面 Alpha

目标：让非开发者在桌面端完成一部小说的基础连续创作。

工作：

- Project Catalog、创建、添加和选择 UI；
- Runtime Center 的安装、登录、健康和账户页；
- Writing Session、动态查询、流式创作、Draft 历史和 Review UI；
- 章节方案确认、准确 Draft 确认和 Publication Digest 批准 UI；
- 事务失败和 recover UI；
- 中英文路径、中文输入、长正文渲染和可访问性验证；
- 保持现有 Codex Plugin 全部可用。

退出标准：

- 新用户从安装到第一次创作不需要终端；
- 连续发布至少三个 Chapter，后一个 Session 能查询前一个发布结果；
- 所有批准都展示准确 ID、revision、Diff 和 Digest；
- Desktop 与 Plugin 对同一项目产生一致业务结果。

预计投入：4 至 6 人周。

### 阶段 3：安装、更新和安全加固

目标：把本地样机变成可长期安装和升级的产品。

工作：

- Runtime Manifest Registry；
- 固定来源下载、Digest/签名验证、原子安装、升级和回滚；
- Novel 和 Runtime 版本兼容矩阵；
- Keyring、Profile 隔离、退出和卸载；
- 签名安装包、自动更新和崩溃恢复；
- 凭据泄漏、恶意项目指令、工具越权和审批绕过测试；
- 脱敏诊断导出。

退出标准：

- 更新失败可回到上一可用 Runtime；
- 卸载 Runtime 不影响小说项目；
- 凭据不会出现在项目、日志、命令行或崩溃报告；
- 受支持平台安装和升级验收通过。

预计投入：3 至 5 人周。

### 阶段 4：可移植 Novel Tool Gateway

目标：让第二个 Runtime 可以复用同一套小说工具，而不复制业务规则。

工作：

- 将已验证动态工具整理为版本化 Tool Schema；
- 需要时提供本地 stdio MCP 入口；
- 保持 `novel --json` 为最终业务协议边界；
- 为权限级别、错误映射、超时、取消和幂等建立契约测试；
- 验证 MCP/Tool Gateway 不产生额外批准或状态来源。

退出标准：

- Codex 通过新 Gateway 完成阶段 2 的同一闭环；
- Tool Schema 与 CLI/Application 契约一致；
- Host-only 操作无法从 AI 工具面发现或调用。

预计投入：2 至 3 人周。

### 阶段 5：第二 Runtime 与切换

目标：用真实的第二个 Agent 验证 Runtime 抽象，而不是继续为假设能力扩展接口。

选择条件：

- 有稳定、可嵌入的机器协议；
- 有明确的本地授权与凭据所有权；
- 能流式返回内容和工具调用；
- 能处理中断、错误和审批；
- 许可证和商业分发允许产品集成；
- 在目标用户网络和平台环境中实际可用。

工作：

- 只实现第二 Runtime 当前需要的 Adapter；
- 完成安装、授权、Thread 和工具闭环；
- 在 Turn 安全边界切换 Runtime；
- 从 Novel 权威状态重建上下文；
- 对比正文质量、上下文使用、失败率、延迟和成本。

退出标准：

- 同一个 Writing Session 可以在两个 Runtime 间安全接续；
- 不迁移供应商私有会话也能恢复准确工作状态；
- 两个 Runtime 都无法绕过 Novel 的审批与发布边界；
- 抽象中没有只为未实现第三 Runtime 创建的字段或服务。

预计投入：3 至 5 人周。

### 阶段 6：封闭 Beta 与发布

目标：验证真实作者的易用性和持续创作能力。

工作：

- 首次引导、失败恢复和账户帮助；
- 长篇项目性能和多项目隔离；
- 真实作者连续创作测试；
- Runtime/模型不可用、限额耗尽和网络中断体验；
- 隐私说明、服务条款、开源声明和第三方许可证；
- 支持矩阵、诊断流程和回滚手册。

退出标准：

- 目标作者无需开发者帮助完成安装、登录、创作、Review 和发布；
- 连续创作不会因 Agent Thread 丢失而丢失小说状态；
- 已知失败均能给出安全、可执行的恢复路径；
- 发布包、Runtime 和文档版本可以准确追踪。

预计投入：3 至 5 人周。

## 9. 总体投入与发布策略

单人全职、先支持一个桌面平台时，从阶段 0 到可用封闭 Beta 预计约 5 至 7 个月。该估算不
包含不可控的第三方许可证谈判、应用商店审核、账号地区限制或供应商协议重大变化。

建议发布通道：

1. `development`：开发者本机和协议实验；
2. `alpha`：固定 Codex Runtime、小范围真实项目；
3. `beta`：签名安装包、更新回滚、真实作者；
4. `stable`：至少一个完整支持 Runtime，并有第二 Runtime 验证抽象。

不要以“一次支持尽可能多的 Agent”为首发目标。首发价值是普通作者能够稳定使用一个成熟
Agent 完成 Novel 的正规创作闭环。

## 10. 测试矩阵

### 10.1 Runtime 契约

- 固定版本启动、初始化和干净退出；
- 协议版本或 Schema 不兼容时明确拒绝；
- stdout 协议与 stderr 诊断分离；
- 流式事件有序，重复事件幂等；
- Turn 取消、进程崩溃和重启可判断状态；
- Thread 丢失可以从 Novel Session 新建恢复。

### 10.2 授权

- ChatGPT 登录成功、取消、超时、浏览器失败和重新登录；
- Device Code 成功、过期和取消；
- API Key 成功、无效、撤销和清除；
- Keyring 不可用时安全失败或经过明确确认的降级；
- Workspace 强制登录方式和账号不匹配；
- 退出登录不会删除 Runtime 或小说项目；
- 日志和崩溃产物中不存在令牌或 API Key。

### 10.3 小说闭环

- 多项目选择不会串写；
- Session 查询保持同一 Narrative Order 边界；
- 紧邻 Chapter Exact Read 仍是 Draft 保存前置条件；
- Draft/Review 绑定准确 revision；
- 新 Draft 使旧确认失效；
- Agent 不能自行批准或 apply；
- 作者批准的 bytes 与最终 manuscript 一致；
- 发布失败只按已批准计划前滚恢复；
- Plugin 和 Desktop 可以先后处理同一项目。

### 10.4 安装与切换

- 下载 Digest/签名错误拒绝安装；
- 断电或进程终止不留下被选中的半安装版本；
- 更新失败回滚；
- 多 Runtime Profile 和凭据不混用；
- 活跃 Turn、等待工具或 apply 中禁止切换；
- 切换后从 Novel 状态恢复，不注入未来正文或其他项目上下文。

## 11. 全局完成标准

新的桌面 Runtime 能力只有同时满足以下条件才算完成：

- 普通用户无需终端即可安装、授权并使用一个完整支持的 Agent；
- ChatGPT 订阅登录和 API Key 计费在 UI 与状态中明确区分；
- Novel 不拥有或解析 Agent 凭据；
- Agent Thread 丢失不影响小说权威资产；
- 上下文继续通过 Session 和动态查询控制，不默认重复上传整本小说；
- Runtime 安装、更新、切换和卸载不修改小说项目；
- Desktop、Plugin 和未来 Runtime 共用同一 Application/Core 业务语义；
- Agent 无法绕过准确 Draft 确认和 Publication Digest 批准；
- 至少一个真实长篇项目连续发布多个 Chapter；
- 第二 Runtime 证明适配层真实可替换；
- 所有受支持平台具有签名、回滚、诊断和恢复路径。

## 12. 明确不在首期范围

- Novel 自建远程 Agent 或模型代理服务；
- Novel 代用户注册、购买、共享或托管第三方订阅；
- Novel 云端保存 API Key 或 ChatGPT Token；
- 无确认静默安装任意 Agent CLI；
- 一次适配所有开源 CLI；
- 在 Agent 之间迁移供应商私有对话记录；
- 让 Runtime Thread、模型摘要或 Token 统计成为 Canon；
- 新建 ORM、Redis、远程数据库、Docker 或微服务；
- 为桌面端重新实现一套 Draft、Review、批准或发布服务；
- 因桌面开发而削弱现有 Codex Plugin 工作方式。
