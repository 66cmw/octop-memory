# HANDOFF.md

代码相关任务的文本澄清与接续入口。使用 Issue / PR 编号或简短标题识别任务，不以日期建流水账。
有 Issue / PR 时链接正文，只在这里保留状态、关键结论和下一步；未开 Issue 时直接使用下方模板。
已完成记录压缩或替换，稳定知识移入对应文档，历史由 Git / Issue / PR 保存。

## 任务模板

- **任务 / 状态 / 链接**：待澄清 → 可实现 → 进行中 → 待验证 → 完成；阻塞时写明原因。
- **问题与场景**：bug 的实际/预期行为及最小复现；新需求的使用者、场景和期望结果。
- **范围与验收**：要做/不做、可验证条件、兼容性及数据影响。
- **待澄清 / 假设**：哪些已确认，哪些影响实现；不能把未回答的问题记成确认。
- **方案与关键文件**：最小实现、受影响调用链；重要取舍链接 DECISIONS。
- **验证**：确切命令、实际结果、失败/skip/未覆盖，必要时附脱敏证据。
- **接续**：当前进度、未解决风险、下一步；受影响文档是否同步。

## 当前任务

### Octop #2060：多 agent 文件描述符耗尽

- **状态 / 链接**：实现与本仓验证完成，待审阅及发布；[Octop#2060](https://github.com/TencentCloud/Octop/issues/2060)。
- **问题与场景**：SQLite 按线程缓存连接，常驻 worker 接触多个 agent 后保留“线程 × agent”条连接；69 个 Memory、软限制 1024 可耗尽 fd。旧实现的 `close()` 还可能关闭其他线程正在使用的事务连接。
- **范围与验收**：每个 SQLite backend 一条连接；完整 SQL 操作与显式事务受同一可重入锁保护，关闭等待操作结束且不重开。69 个实例、8 个工作线程在 1024 限制下仍可读库和创建 socket，关闭后 fd 回到基线。checkpoint 仍单独连接，schema、召回 source/排序和 public API 不变。
- **方案与关键文件**：`storage/backends/sqlite.py` 的操作锁和失败回滚；vacuum、WAL truncate、export 的内部直接 SQL 同样持锁。PostgreSQL 已使用单连接与可重入锁，本次通过同组事务行为断言验证；取舍见 ADR-039。
- **验证**：改动前常驻 12 worker 打开 13 条连接、关闭会打断事务的回归均失败。定向 SQLite/PostgreSQL、公共写入、checkpoint 和维护测试 294 passed / 1 skipped。使用专用 `TEST_POSTGRES_DSN` 执行 `make all RUN='uv run --offline --no-sync'`，format、lint、strict mypy 均通过，pytest 为 1432 passed / 4 skipped；真实 PG 用例均运行，跳过项为 Linux `/proc`、两项 Hermes checkout E2E 和 dashboard extra。文档/架构检查 41 passed，Hermes 两项仍因缺 checkout 跳过。Octop 最新 develop 加载本次 memory 源码联调 191 passed / 1 skipped。69 个真实 MemoryRuntime 在 soft NOFILE=1024 下，4/8 个 worker 反复访问及重建 30 次均维持 348 fd，全部关闭回到基线 3。
- **接续**：无数据迁移。慢查询或长显式事务会阻塞同 backend 的其他 SQL；不同 agent 与独立 checkpoint 连接仍可并行。发布后宿主需更新 memory 依赖才能获得连接修复。

### Octop 命名收尾

- **状态**：命名清理完成；真实 PostgreSQL、Hermes checkout 和 dashboard 可选环境未验。
- **问题与场景**：发行包已更名，宿主示例、评测数据、迁移说明和 portable 扫描路径仍有旧项目名称。
- **范围与验收**：源码、测试、评测及文档统一使用 `octop-memory` / `octop-harness`；全仓检查两者旧名称及分隔符变体无残留。保留现有 README 改动，不改持久化编码、表名或包格式，不搬移用户数据库。
- **方案与关键文件**：更新 `service.py` 的宿主说明、portable `models.py` 的 Agent 扫描路径、CLI help 和迁移指南；测试使用临时目录验证默认发现和显式扫描旧位置。删除旧包目录中未使用的生成版本文件；修正 portable dry-run / recall 测试的默认用户库访问，补全 `_PKG_ERRORS` 的类型标注以通过 strict mypy，异常捕获范围不变。
- **影响**：portable 改为发现 `~/.octop-harness/*/memory.sqlite`；旧位置需显式提供 `extra_paths` 或先迁移目录。主召回 source/排序、事实写入与双 backend 数据契约不变。
- **验证**：相关测试 183 项通过；fixture 修复后的 portable/recall 子集 32 项通过。`PYTEST_ADDOPTS=-rs make all RUN='.venv/bin/python -m'` 通过 format、lint、strict mypy，pytest 为 1268 passed / 132 skipped（129 项 PostgreSQL 不可用、2 项缺少 Hermes checkout、1 项缺少 dashboard extra），不代表这些环境通过验收。`uv build --offline` 构建 wheel/sdist 成功；源码文件名、内容及构建包的旧名称检查无残留。OpenClaw 的 `npm test` 启动器因沙箱 IPC 限制失败，改用 `node --import tsx --test src/*.test.ts` 后 67 项通过，`npm run typecheck` / `npm run build` 通过。`ruff check evals examples` 和 routing 数据集 JSON 解析通过。
- **接续**：PROJECT_MAP / TEST_MATRIX / README_AUDIT 与集成指南已同步，KNOWN_RISKS 移除已修复的测试默认库访问项。需要环境验收时，配置专用 `TEST_POSTGRES_DSN`、Hermes checkout 与 dashboard extra，再运行 TEST_MATRIX 对应命令；本次未更改 backend SQL、事务或持久化协议。
