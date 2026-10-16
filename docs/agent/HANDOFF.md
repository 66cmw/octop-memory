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

### Octop #2060：多 agent 文件描述符与 PostgreSQL 连接容量

- **状态 / 链接**：SQLite 与 PG 实现、本仓和宿主验证完成，待审阅及发布；[Octop#2060](https://github.com/TencentCloud/Octop/issues/2060)、[memory PR#19](https://github.com/TencentCloud/octop-memory/pull/19)。
- **问题与场景**：SQLite 按线程缓存连接，常驻 worker 接触多个 agent 后保留“线程 × agent”条连接；69 个实例可耗尽 1024 fd，旧 close 还会打断在途事务。PG 每 agent 一条业务连接加独立 checkpoint 池，69 个活跃实例达到 138 条会话；真实 PG `max_connections=100` 时第 31 个 checkpoint 超时，空闲回收挡不住活跃峰值。
- **范围与验收**：SQLite 每 backend 一条连接，完整 SQL/事务共用可重入锁，close 等待且不重开。PG 同一进程与连接配置共享业务 8 条、checkpoint/维护 4 条预算，显式事务保留一条连接；checkout 有界等待，关闭一实例不影响其它实例，最后引用关闭池。SQLite checkpoint 仍独立；schema、召回 source/排序和 public API 不变。
- **方案与关键文件**：`storage/backends/sqlite.py` 的操作锁与失败回滚；内部 vacuum/WAL truncate/export 遵守锁。`postgres_pool.py` 管理共享池、引用租约与初始化串行；`postgres.py` 借用连接，`core.py` 失败时释放 checkpoint 租约，导出与 PG 维护进入池预算。取舍见 ADR-039/040。
- **验证**：使用专用 `TEST_POSTGRES_DSN` 执行 `make all RUN='uv run --offline --no-sync'`，format、lint、strict mypy 均通过，pytest 为 1420 passed / 4 skipped；真实 PG 用例均运行。跳过项为 Linux `/proc`、两项 Hermes checkout E2E 和 dashboard extra。新增真实 PG 容量、排队/超时恢复、坏连接探测、空闲回收、初始化失败、跨 agent 事务与幂等关闭断言替代旧连接私有字段 mock。Octop 加载新源码的定向联调 95 passed，包含 6 项真实 PG 维护测试。
- **宿主容量复现**：SQLite 69 个真实 MemoryRuntime 在 soft NOFILE=1024 下，4/8 worker 访问及 30 次重建维持 348 fd，全部关闭回到 3。PG 在服务端 100 连接、进程 1024 fd 限制下，69 个真实 MemoryRuntime 创建/全部 checkpoint 预热分别仅占 1/2 条会话，8 worker 混合访问峰值 12；30 次重建不增长，关闭一个实例后其它实例仍可用，全部关闭会话归零且 fd 回到 3。
- **接续**：CI/release 已配置专用 PG，显式测试 DSN 不可用时失败。无数据迁移；慢 SQL/长事务会占用池，饱和明确报错。预算按进程与连接配置计数，宿主控制面另计。发布后 Octop 需更新 memory 依赖才能消费修复。PROJECT_MAP、DECISIONS、TEST_MATRIX、KNOWN_RISKS 与中英文 README 已同步。

### 系统运行报错的记忆隔离

- **状态**：实现与验证完成。
- **问题与场景**：模型重试耗尽后产生的 `Model call failed after ...` 被当成普通助手消息采集、提炼为 Atom，并再次召回。
- **范围与验收**：按结构化来源及已知旧版运行时消息格式隔离系统报错；用户输入、手工保存、用户批准及明确要求记住的内容保持有效。阻止错误原始证据再次提炼或兜底召回；对可确认来源的存量 Atom 软停用并保留审计。SQLite / PostgreSQL 使用相同规则，不修改 schema 或原始证据。
- **方案与关键文件**：domain retention policy；capture / extractor / episode / promotion / recall 共用判定；operations 提供先预览后应用的存量治理。octop-harness 与 Octop 的重试配置均采用 `on_failure="error"`；不传自定义 `retry_on`，重试范围、次数与退避参数沿用原设置，由上游判断错误类型。checkpoint 保存 task error，WebUI / IM / 团队单独展示失败。团队自动失败通知排除采集；来源标记继续保护自定义宿主及旧版合成回复。
- **验证**：新增用例先复现失败，再通过来源过滤、raw fallback、Candidate/Episode 提炼、晋升及隐私脱敏前判定用例；真实专用 PostgreSQL 与 SQLite 共用 22 条治理断言，验证预览/应用、人工保护、幂等和事务回滚。同步当前 develop 后，`TEST_POSTGRES_DSN='dbname=octop_memory_retention_test' make all RUN='.venv/bin/python -m'` 通过 format/lint/strict mypy，1454 passed / 4 skipped；PG cases 实际执行，skip 属于可选环境。用例与操作均不删除原始证据。
- **宿主后续验证**：真实 LangGraph 失败后 checkpoint 有 task error、没有错误助手消息及 raw/Atom 写入；修复模拟凭据后可恢复执行并正常采集。团队 SDK 异常及主 Agent 汇总异常均结束为 failed 并释放锁，自动通知不采集。octop-harness 提交门禁为 1787 passed / 28 skipped（配套 PR#76）；SDK 401/403 等按原预算重试，实际组装的 `retry_on` 与上游默认对象一致。Octop 在当前 develop 上的重点联调为 200 passed / 1 skipped，覆盖实际重试配置、WebSocket 认证失败与恢复、IM 错误事件、团队错误帧和历史标记；前端强记忆和错误状态测试 7 passed。宿主完整门禁与构建结果记录在配套 Octop PR。本仓文档/架构检查 41 passed。
- **接续**：PROJECT_MAP / DECISIONS / TEST_MATRIX / KNOWN_RISKS / README_AUDIT 和中英文 README 已同步；存量操作默认预览，显式 apply 才软停用。仍发送合成报错的新宿主必须提供来源标记，证据缺失或混合来源记录保守保留，边界见 ADR-041 和 KNOWN_RISKS。

### Octop 命名收尾

- **状态**：命名清理完成；真实 PostgreSQL、Hermes checkout 和 dashboard 可选环境未验。
- **问题与场景**：发行包已更名，宿主示例、评测数据、迁移说明和 portable 扫描路径仍有旧项目名称。
- **范围与验收**：源码、测试、评测及文档统一使用 `octop-memory` / `octop-harness`；全仓检查两者旧名称及分隔符变体无残留。保留现有 README 改动，不改持久化编码、表名或包格式，不搬移用户数据库。
- **方案与关键文件**：更新 `service.py` 的宿主说明、portable `models.py` 的 Agent 扫描路径、CLI help 和迁移指南；测试使用临时目录验证默认发现和显式扫描旧位置。删除旧包目录中未使用的生成版本文件；修正 portable dry-run / recall 测试的默认用户库访问，补全 `_PKG_ERRORS` 的类型标注以通过 strict mypy，异常捕获范围不变。
- **影响**：portable 改为发现 `~/.octop-harness/*/memory.sqlite`；旧位置需显式提供 `extra_paths` 或先迁移目录。主召回 source/排序、事实写入与双 backend 数据契约不变。
- **验证**：相关测试 183 项通过；fixture 修复后的 portable/recall 子集 32 项通过。`PYTEST_ADDOPTS=-rs make all RUN='.venv/bin/python -m'` 通过 format、lint、strict mypy，pytest 为 1268 passed / 132 skipped（129 项 PostgreSQL 不可用、2 项缺少 Hermes checkout、1 项缺少 dashboard extra），不代表这些环境通过验收。`uv build --offline` 构建 wheel/sdist 成功；源码文件名、内容及构建包的旧名称检查无残留。OpenClaw 的 `npm test` 启动器因沙箱 IPC 限制失败，改用 `node --import tsx --test src/*.test.ts` 后 67 项通过，`npm run typecheck` / `npm run build` 通过。`ruff check evals examples` 和 routing 数据集 JSON 解析通过。
- **接续**：PROJECT_MAP / TEST_MATRIX / README_AUDIT 与集成指南已同步，KNOWN_RISKS 移除已修复的测试默认库访问项。需要环境验收时，配置专用 `TEST_POSTGRES_DSN`、Hermes checkout 与 dashboard extra，再运行 TEST_MATRIX 对应命令；本次未更改 backend SQL、事务或持久化协议。
