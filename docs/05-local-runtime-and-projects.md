# 本地运行与多项目管理

## 1. 本地运行原则

Novel 的业务数据和运行过程保存在用户本机。CLI 是 Codex Plugin 调用 Application/Core
的稳定入口。

```text
Codex Skill
→ novel CLI
→ Application
→ Core
→ 项目文件和 SQLite
```

运行时不监听网络端口，不要求用户启动数据库服务或 Web 服务。

## 2. Project Catalog

应用级 Project Catalog 位于用户应用数据目录，只保存小说项目引用，不保存正文、Canon
或草稿内容。

Catalog 支持：

- 注册新项目；
- 添加已有项目；
- 列出项目；
- 通过 Project ID 解析路径；
- 更新标题和最近打开时间；
- 从 Catalog 移除引用。

从 Catalog 移除项目不得删除项目目录。项目目录移动后可以通过新路径重新添加。

Catalog 写入使用原子替换和应用级锁。项目内容使用各自的项目锁，因此不同小说可以并行
读取和写作。

默认应用数据目录使用标准库按平台定位：

- macOS：`~/Library/Application Support/Novel`；
- Windows：`%LOCALAPPDATA%/Novel`；
- Linux 和其他 Unix：`$XDG_DATA_HOME/novel`，未设置时使用
  `~/.local/share/novel`。

Catalog 文件为该目录中的 `projects.json`。`NOVEL_APP_DATA_DIR` 环境变量或 CLI
`--catalog-dir` 可以覆盖整个应用数据目录，测试必须使用隔离目录。Catalog 是带
`schema_version` 和 `catalog_format_version` 的 JSON；条目只保存 Project ID、标题、
规范化绝对路径和最小项目状态。写入在 `projects.lock` 保护下使用同目录临时文件和原子
替换。

## 3. 项目选择

CLI 接受显式 `--project-id` 或 `--project`：

- `--project-id` 通过 Catalog 解析；
- `--project` 直接使用包含 `novel.yaml` 的项目路径；
- 两者同时提供时必须指向同一 Project ID；
- 写操作不使用模糊标题匹配；
- Plugin 在 Session 建立后始终携带明确项目身份。

从当前目录向上发现 `novel.yaml` 只用于交互便利，不替代 Session 中保存的项目身份。

当前正式多项目入口为：

```text
novel project list
novel project create <path> --title <title> [--language <tag>]
novel project add <path>
novel [--project-id <uuid> | --project <path>] project show
novel project remove --project-id <uuid>
```

`project create` 只创建空项目骨架并报告 `not_bootstrapped`；`project add` 只读取项目
Manifest 并维护 Catalog 引用；`project remove` 不读取或删除项目资产。不存在旧的
`novel init` 兼容入口。

## 4. CLI 协议

机器调用使用一个版本化 JSON Envelope：

```json
{
  "protocol_version": "1.0",
  "ok": true,
  "command": "session show",
  "data": {},
  "warnings": []
}
```

失败返回：

```json
{
  "protocol_version": "1.0",
  "ok": false,
  "command": "publish apply",
  "error": {
    "code": "canon_conflict",
    "message": "..."
  }
}
```

规则：

- `--json` stdout 只输出一个 JSON 文档；
- 诊断信息写 stderr；
- error code 和 exit code 是 Plugin 协议；
- 人类输出不改变机器字段语义；
- 写命令返回 Project ID、操作 ID 和结果 revision。

## 5. 命令族

```text
novel project list|create|add|show|remove
novel bootstrap start|save|inspect|approve|apply
novel intent show|prepare|inspect|approve|apply
novel session start|show|context|close
novel memory chapters|scenes|search-summaries|read-scene
novel query entity|character|events|event-chain|source
novel draft save|list|show|diff
novel review save|list|show
novel publish prepare|inspect|approve|apply|recover
novel doctor
novel rebuild
novel schema show
```

具体参数由对应领域契约决定，但同一业务动作只保留一个正式入口。

当前实现中，Bootstrap、Intent Revision、Writing Session、Draft、Review 和 Publication
完整运行记录都保存在对应 `runs/` 目录的版本化 JSON 与 UTF-8 文件中。SQLite migration
`0002_creation_runs` 只保存这些记录的最小查询索引；删除数据库后，`rebuild` 会从运行
文件恢复索引。

Session 模式的 `memory`、`resolve` 和 `query` 调用携带 `--session-id`。Application 使用
Session 中保存的 Narrative Order 边界并自动写入 `retrieved_sources`；不能通过临时换一个
`--before-scene` 绕过 Session 边界。

## 6. 项目锁与并发

- 多个读取可以并行。
- 每个项目同一时间只有一个写事务。
- Bootstrap apply、正式意图修改和 Publish apply 获取项目写锁。
- 锁文件包含 PID 和随机 token。
- 只有确认所属进程不存在的有效锁可以自动清理。
- 锁内重新读取 Manifest、Ledger 和目标文件 revision。
- 不同小说使用不同锁，可以同时创作。

## 7. 投影与恢复

`.novel/project.sqlite` 是可重建投影。

`doctor` 必须区分：

- Manifest/Ledger/导航投影是否一致；
- 正式 manuscript 文件是否存在；
- Document revision 是否匹配磁盘 bytes；
- SourceRef 是否匹配正文；
- stale 或缺失摘要数量；
- 未完成 Bootstrap/Publication 事务；
- 锁是否安全。

已开始但未完成的 Publication 步骤会使 `doctor` 报告不健康，并给出准确 Publication ID
和步骤状态；`doctor --repair` 只修复可重建投影，不会替代 `publish recover` 猜测或批准
业务内容。

`rebuild` 从 Manifest、Intent、Ledger、Chapter、Summary 和运行记录重建新数据库，完成
校验后再安装。重建失败不能修改权威文件。

## 8. 运行产物和清理

每个 Run 使用稳定 ID 独立目录。不可变 Draft、Review、Diff、批准和事务记录不得被同 ID
覆盖。

允许清理的仅是明确可重建的临时文件。未发布草稿和 Review 是用户创作资产，不能作为
普通缓存删除。

## 9. 安装与项目数据分离

程序安装目录只包含运行时、Schema、SQL 和 Plugin 资源。小说项目保存在用户选择的位置。

必须保证：

- 更新程序不移动或覆盖小说项目；
- 卸载程序不默认删除小说项目；
- 项目可以独立备份或使用 Git；
- Catalog 丢失不影响项目内容；
- SQLite 丢失不影响权威记录；
- 中文、空格和非默认磁盘路径可用。

## 10. 健康标准

一个项目只有在以下条件满足时才报告可创作：

- Manifest 有效且 Project ID 唯一；
- Ledger 可完整 replay；
- 正式正文 revision 匹配；
- SQLite 投影与权威文件一致；
- 没有无法恢复的写事务；
- Plugin 与 CLI 协议版本匹配。

摘要缺失或 stale 可以降低导航质量，应作为明确 warning，但不把小说判定为不存在相关
历史，也不阻止保存草稿。
