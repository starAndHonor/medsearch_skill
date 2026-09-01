# MedLit 高召回与高命中升级：详细开发审核稿

> **文档状态：第一轮审核未通过，已被 v2 取代，不得据此实施。**  
> 当前待审稿：`medlit_retrieval_upgrade_review_v2.md`  
> 实施对象：`plugins/medlit-cli` 及其直接测试、评测与发布链路  
> 约束版本：2026-08-16  
> 关系说明：本稿取代 `medlit_retrieval_upgrade_plan.md` 中关于 MCP 的设计；旧稿不再作为实施依据。

## 1. 审核结论与硬约束

本轮建议把 `plugins/medlit-cli` 建成**纯 Skill + 本地 Python CLI** 插件。Codex 负责理解用户问题、审核 PICO/检索式和综合证据；插件内的确定性 Python 代码负责状态、检索、并发、下载、解析、排序、验证和恢复。

系统**不得采用 MCP**，具体落实为：

- 插件中不得存在 `.mcp.json`、`mcpServers`、MCP 服务进程、MCP SDK、MCP 工具调用或间接运行依赖。
- CI/发布预检对上述文件名、manifest 字段、依赖名和关键字做阻断式扫描。
- PubMed、NCBI MeSH、PMC、Europe PMC、Unpaywall 等均由插件内 HTTPS 客户端直接访问。
- 插件安装后不启动常驻服务，不要求远端后端，不生成嵌套 Codex 会话。
- 仅获取开放获取全文或用户明确提供的本地文件，不绕过付费墙、鉴权或访问控制。
- 输出是文献检索和证据整理结果，不宣称完成临床验证，不生成患者个体诊疗建议。

OpenAI 的插件规范允许插件只提供 Skills；MCP 是可选组件。因此上述限制不妨碍第三方通过 Codex 插件机制安装和调用本系统。

## 2. 当前系统审计与主要缺口

当前实际入口为：

```text
SKILL.md
  -> scripts/medlit_cli.py
  -> medlit.cli.main()
  -> init / decompose / plan-terms / validate-mesh / build-query
     / search-pubmed / fetch-records / localize-fulltext
     / parse-fulltext / extract-evidence / report / verify / diagnose
```

已有 manifest 和 Skill 能通过基础校验，但仍有以下结构性问题：

1. 根目录 `medlit/` 与插件内 `plugins/medlit-cli/medlit/` 是两套运行副本，`sync_plugin.py --check` 已能发现差异；评测可能跑根目录新版，而用户实际安装的是插件旧版。
2. manifest 为 `0.2.0`，Python 包仍报告 `0.1.0`，版本、缓存和结果溯源可能失真。
3. `evals/score_bioasq.py` 仅按多次 `retrieval_runs` 的出现顺序去重，未使用统一融合后的最终排名；现有 Precision@K 以实际返回数为分母，也未正式定义 Hit Rate。
4. 当前 PICO 结构较窄，默认加入 human/English 过滤，可能误杀动物、机制、罕见病或非英语问题；MeSH、缩写、药物名、基因名和检索变体覆盖不足。
5. 多查询不是统一调度的并行任务，缺少租约、幂等、优先级、取消、断点恢复和每主机限速。
6. 已下载 PDF 只产生 `pdf_placeholder`，却被标成 fulltext；该占位文本不能支持证据抽取。
7. 抽取器只看前 20,000 字符，报告器主要序列化状态；`verify` 只查引用关系和路径存在性，不能证明引文真的出现在来源中。
8. 个人 marketplace 路径、仓库 marketplace、插件缓存副本三者容易混淆，尚未形成可复现的第三方安装—升级—新会话加载测试。

## 3. 总目标、指标定义与评测口径

### 3.1 目标优先级

1. 第一目标：提高相关论文召回率，尤其是困难问题的 Recall@20/50/100。
2. 第二目标：提高前列结果至少命中一篇相关论文的概率，即 Hit@5/10/20。
3. 保护目标：MAP@10、nDCG、Precision@10 不因盲目扩词显著下降。
4. 工程目标：在请求预算、限速、可恢复、可追溯和合法全文获取约束内完成上述提升。

### 3.2 统一定义

对问题 `q`，金标准 PMID 集为 `Gq`，最终去重排序结果前 `K` 项为 `Rq@K`：

- `Recall@K = |Rq@K ∩ Gq| / |Gq|`。
- `Hit@K = 1` 当 `Rq@K ∩ Gq` 非空，否则为 `0`；数据集 Hit Rate@K 为所有问题 `Hit@K` 的宏平均。
- `Precision@K = |Rq@K ∩ Gq| / K`，固定使用 K 作分母；另报 `ReturnedPrecision@K` 以区分返回不足 K 篇的情况。
- 同时计算 F1@10/20、MRR、MAP@10、nDCG@20/50，以及问题级 Recall-AUC。
- 金标准为空时不静默计零：评测器报数据错误并单列；PMID 统一规范化后再比较。

`final_ranked_pmids` 将成为评分唯一入口；旧的“按 retrieval run 拼接”仅用于复刻基线。每项指标按题型、PICO 完整度、缩写密度、罕见病、药物/基因、时间敏感性、金标准规模等子集报告，并用配对 bootstrap 给出差值和 95% 置信区间。

### 3.3 防泄漏与双轨评测

- 所有 BioASQ 检索严格应用 `question_date`，防止使用题目之后的文献。
- “检索核心轨”使用冻结且带版本的 PICO/术语输入，衡量检索引擎本身。
- “端到端轨”从原始问题开始，由当前 Skill 产生结构化 PICO，衡量真实用户路径。
- 两条轨道必须执行同一份插件代码和同一 CLI 入口，禁止评测导入根目录的另一份实现。
- 保存运行配置、代码版本、MeSH 版本、查询文本、请求时间、缓存命中和最终排名，确保复现。

### 3.4 建议验收阈值

冻结当前全量基线后再锁死阈值。初始目标为 Hit@10、Recall@20/50 相对提升不少于 20%；MAP@10 和 Precision@10 不出现超出统计误差的回退。另设工程护栏：单题请求数、墙钟时间和下载量不超过审定预算；网络失败可恢复；同输入、同缓存和同版本产生确定性排名。若召回提升依赖明显增加成本，必须提交消融结果，由审核者选择默认档位。

## 4. 目标架构

```text
用户 / Codex
    │  调用 Skill、生成或审核结构化输入
    ▼
Skill-only 插件入口（无 MCP）
    ▼
CLI：run / resume / status / cancel / explain-plan + 兼容阶段命令
    ▼
确定性 Orchestrator（DAG、预算、阶段门、终止条件、审计）
    ▼
本地 Scheduler（SQLite WAL 任务日志、租约、重试、优先级）
    ├─ I/O 线程 Worker：检索、批量抓取、全文定位与下载
    └─ CPU 进程 Worker：PDF 解析、可选 OCR、重型文本处理
    ▼
结果队列 → Orchestrator 单写者提交 → 状态快照与本地产物
    ▼
融合排序 → 证据抽取 → 报告 → 引文与来源完整性验证
```

关键边界：worker 不直接修改公共 `state.json`；SQLite 保存内部任务与租约，orchestrator 是状态唯一写者，并原子生成可读 JSON 快照。Codex 不逐条手工编排网络任务，Python 也不擅自作临床语义判断。

## 5. 详细设计

### 5.1 插件规范与第三方安装

- 以 `plugins/medlit-cli` 为唯一可执行源码；根目录脚本先降级为明确的开发兼容入口，待迁移测试通过后再决定删除，避免一次性破坏现有调用。
- `.codex-plugin/plugin.json` 采用严格 semver，并补齐可公开的 license、作者联系方式、仓库、文档、隐私与服务条款；Python 包版本从同一位置读取。
- manifest 只声明 `skills: "./skills/"` 和真实存在的界面资产，不写未实现字段；增加预检确保没有 MCP 配置。
- `SKILL.md` 继续向上查找 `scripts/medlit_cli.py` 与 `medlit/cli.py`，不依赖固定工作目录；补充 `run/resume/cancel/doctor`、全文来源等级、预算和失败降级说明。
- 增加 `doctor`：检查 Python 版本、写权限、TLS、可选依赖、环境变量、磁盘空间和网络端点；不得未经用户同意自动安装依赖。
- 核心尽量保持标准库可运行；PDF 能力的 `PyMuPDF` 版本和许可证经审核后锁定。OCR 作为可选 extra，缺失时明确降级，不影响摘要检索。
- 仓库 marketplace 作为团队/第三方来源，安装流程按当前官方 CLI 验证：先配置非默认 marketplace，再执行 `codex plugin add medlit-cli@<marketplace>`；升级时替换单一 cachebuster、重新安装并在新会话验证。正式发布前在全新用户目录、无源码工作目录和无开发环境变量条件下做黑盒安装测试。
- 每次发布运行 plugin validator、Skill validator、manifest 路径/资产检查、版本一致性检查、MCP 禁用扫描和压缩包内容清单检查。

### 5.2 本地 Orchestrator：有必要，但不是自由推理 Agent

新增 `run` 作为完整工作流入口，`resume` 恢复未完成 DAG，`status` 展示阶段、任务和预算，`cancel` 协作式取消，`explain-plan` 输出将在执行的查询与成本。原有阶段命令保留，便于审核和调试。

Orchestrator 负责：

- 构建 `decompose → terms → mesh → query variants → search → fetch → fulltext → parse → extract → report → verify` DAG。
- 检查前置产物、配置预算、任务优先级、重试策略、阶段门槛、早停和召回饱和度。
- 根据新增唯一 PMID 比例、排名稳定度和预算决定是否继续扩展查询/引用网络。
- 对错误分类：可重试网络错误、限速、永久 4xx、解析质量不足、依赖缺失、数据约束失败；不同错误不共享同一重试策略。
- 记录为什么生成某条查询、为什么下载/跳过某篇、为什么降级到摘要以及终止原因。
- 所有排序和合并显式指定稳定 tie-breaker，保证可复现。

Codex 仅参与需要语义判断的点：问题框架和 PICO 审核、歧义消解、用户约束解释、可选查询审阅、最终证据综合。默认工作流不调用嵌套 Codex CLI，也不把“逐命令循环”当 orchestrator。

### 5.3 真正的并行 Worker 调度器

调度器是进程内、可持久化的执行设施，不是多个提示词 Agent。SQLite WAL 表至少包含：`task_id`、`run_id`、`kind`、`payload_json`、`payload_hash`、`dependency_ids`、`priority`、`status`、`attempts/max_attempts`、`lease_owner/lease_until`、`not_before`、时间戳、错误分类和产物路径。

实现要求：

- 用幂等键防止恢复时重复检索、重复下载或重复提交；任务提交和状态转换使用事务。
- I/O 任务采用有界 `ThreadPoolExecutor`；PDF/OCR 等 CPU 任务可用有界 `ProcessPoolExecutor`，兼容 Windows `spawn`，禁止在子进程隐式重建整个运行状态。
- 对 NCBI、Europe PMC、Unpaywall 分别设置 semaphore、令牌桶和连接池；无 NCBI API key 时默认不超过其公共速率，配置 key 后仍受用户预算限制。
- 429 读取 `Retry-After`；5xx/超时使用指数退避和抖动；永久错误快速失败；每个主机有熔断和半开恢复。
- 支持依赖就绪、优先级、公平性、批量 EFetch、分页、协作取消、超时、失败隔离、过期租约回收和崩溃恢复。
- worker 只返回类型化结果/临时产物，orchestrator 校验哈希、schema 和路径后一次性提交公共状态。
- 记录队列等待、执行时长、重试、吞吐、限速等待、缓存命中、峰值并发和失败率，以证明确实发生并发且没有突破速率。

默认并发值在压力测试后确定，CLI 允许用户降低但不允许绕过主机上限。SQLite 不用于分布式多机调度，本轮也不建设常驻 daemon。

### 5.4 PICO、MeSH 与 PubMed 检索式

首先识别问题类型，再选择 PICO、PECO、PCC 或 SPIDER。统一输入 schema 包含：`framework`、population、intervention/exposure、comparator、outcome、context、study design、time、明确排除项、假设、置信度，以及每个实体的原词、规范词、同义词、缩写、拼写变体和来源。Python 负责 schema 校验；Codex 生成项必须保留 provenance 和版本。

MeSH 处理不再把整段问题当一个 heading。对实体解析 preferred term、entry term、tree number、是否 explode、subheading 和映射置信度；缓存 MeSH 年度版本与响应。映射失败保留 Title/Abstract 自由词并明确标记 fallback。不得默认强加 humans、English、review 或 trial 过滤；过滤项由问题语义决定，并尽量后置为可审计查询变体。

Query planner 生成有预算的 recall-first 梯形组合：

1. 核心概念自由词宽检索；
2. MeSH + Title/Abstract 双通道；
3. 规范短语、缩写、全称、药物通用名/商品名、基因/蛋白别名；
4. comparator、outcome 或研究设计条件的可选收窄变体；
5. 题型相关的系统综述、试验或观察性研究变体；
6. 已有高相关种子文献的 Related Articles、参考文献和被引扩展。

同一概念内部 OR，核心概念之间 AND；否定词和排除式谨慎使用。构建器对 PubMed 字段标签、引号、括号、特殊字符、日期和最大长度做结构化转义，不拼接未经验证的原始片段。查询执行保存 PubMed translation、总命中数、分页游标、执行时间和来源。

### 5.5 多源召回、去重、融合与重排

- PubMed 为主检索源；Europe PMC 作为第二召回源和全文源，通过独立 HTTPS adapter 接入。适配器输出统一 `RetrievedRecord`，单源失败不污染其他源。
- 先以 PMID、PMCID、DOI 去重，再用规范化标题、年份、第一作者进行保守近重复合并；所有合并保留原始标识和判定原因。
- 多查询排名用带参数记录的 Reciprocal Rank Fusion；不能再依赖运行先后顺序。每条记录保存其命中的查询、源排名、融合分和词项覆盖。
- 第一阶段重排采用可解释的 BM25/词项覆盖、PICO 概念覆盖、publication type 和必要的日期匹配；不相关的“新近程度”不应普遍加分。
- 可选 embedding/reranker 必须位于可替换接口后，默认离线路径无需外部模型或密钥；引入前必须做独立消融、成本、隐私和许可证审核。
- 引用扩展只从高置信种子开始，限定深度、每种子数量和总预算；每轮计算新增金标准不可见的代理信号，如新 PMID 比例与语义覆盖，防止无界膨胀。

### 5.6 开放全文与 PDF

定位顺序建议为 PMC/NCBI ID Converter、Europe PMC XML、Europe PMC PDF、Unpaywall 开放链接、用户本地文件。下载前后记录来源 URL、重定向链、访问时间、license、MIME、Content-Length、SHA-256 和最终文件名；限制协议、允许域、文件大小、超时和路径，验证 PDF magic bytes，防止 HTML 错误页伪装成 PDF。

- XML：按章节和段落解析，避免嵌套节点重复文本，并保留 section/paragraph locator。
- PDF：用 PyMuPDF 提取 page、block、bbox、阅读顺序和文本；保留原 PDF，不把占位消息视为正文。
- OCR：仅当页面文本密度低且可选 OCR 依赖通过 `doctor` 时运行；记录引擎、语言、页码和置信度。
- HTML：仅处理用户文件或确认开放的来源，清理导航/脚本并保留章节锚点。
- 质量评分至少考虑可读字符数、乱码率、页覆盖、章节覆盖、重复率和标题/作者一致性。质量不足时降级到摘要，且 `source_granularity` 必须准确为 `abstract`、`fulltext` 或 `failed`。
- 彻底删除 `pdf_placeholder` 进入证据和报告的路径；迁移旧状态时把其 granularity 修正为 `failed/placeholder`。

### 5.7 证据、报告与强验证

证据 schema 增加：论文标识、来源文件哈希、来源粒度、解析方法、页码/章节/字符区间或 bbox、研究设计、样本、干预/对照、结局、效应值及 CI/p 值、局限、匹配的 PICO 概念和抽取置信度。正文按章节切块，优先 Methods/Results/Table，不再只截取开头 20,000 字符。

抽取仍是可审核草稿，不冒充系统综述级风险偏倚评价。报告至少列出：问题与结构化框架、完整检索策略、日期和来源、类似 PRISMA 的数量流、最终证据表、全文/摘要标记、缺失全文、局限和未解决冲突。

新版 `verify` 必须检查：record 与文件/哈希存在；locator 落在真实文本范围；引用片段确实包含于来源；占位文本未进入证据；报告内引用能回到 evidence 和 paper；重复记录、孤儿文件、错误 granularity、无来源结论和迁移异常均被识别。通过只表示可追溯完整性，不表示医疗结论正确。

### 5.8 状态、迁移与可恢复性

状态升级为显式 schema 版本，至少包含 run config、question、PICO、terms、MeSH、queries、tasks、retrieval runs、final ranking、records、fulltexts、parsed sources、evidence、diagnostics、reports、verification、budgets、counters 和 audit events。

- 内部 SQLite 是任务事实源，JSON 是面向用户的原子快照；两者均存于用户指定运行目录。
- JSON 保存采用临时文件、flush/fsync、schema 校验和原子替换；崩溃后优先从 SQLite 与已验证产物重建快照。
- 提供 v0.1 → 新版本迁移器：先备份、后迁移、再校验；不覆盖原状态，支持 dry-run 和迁移报告。
- 旧命令保持一个兼容周期；所有预算在动作前检查，不允许执行后才发现超额。
- 错误可标记 resolved，但历史不可静默删除；运行 ID、插件版本和配置哈希贯穿全部产物。

### 5.9 HTTP、缓存、安全与隐私

- 统一 HTTP 客户端负责 User-Agent、联系邮箱、API key、TLS、超时、重试、限速、缓存和审计；禁止默认关闭证书验证。
- 缓存键包含规范化 URL/方法/参数/来源版本，缓存有 TTL、响应校验和 schema 版本；不得缓存密钥或可识别患者信息。
- API key 只从环境/安全配置读取，日志脱敏；命令执行使用 argv 数组，文件路径做根目录约束，防止 shell 注入和目录穿越。
- 对疑似患者级敏感输入发出本地处理提示，不把原问题发送到检索所必需端点之外。
- 下载遵守 robots、来源条款和开放许可；无法确认开放状态时只保存元数据和摘要。

## 6. CLI 与配置契约

计划新增或调整：

```text
medlit run --question ... --workspace ... [--profile balanced]
medlit resume --state ...
medlit status --state ... [--json]
medlit cancel --state ...
medlit explain-plan --state ...
medlit doctor [--json]
medlit migrate-state --state ... --dry-run
medlit eval-retrieve --benchmark ... --output ...
```

配置档位建议为 `conservative / balanced / recall-first`，分别控制查询变体、retmax、引用扩展、worker 数和全文预算；所有最终值写入状态。环境变量仅承载密钥/联系邮箱，不承载不可追溯的排序逻辑。命令返回码按成功、输入错误、网络暂态、服务端错误、预算耗尽、依赖缺失、状态损坏和验证失败区分。

## 7. 预计文件改造清单

```text
plugins/medlit-cli/
  .codex-plugin/plugin.json
  skills/medlit-cli/SKILL.md
  skills/medlit-cli/agents/openai.yaml
  skills/medlit-cli/references/{workflow,metrics,fulltext}.md
  scripts/{medlit_cli,doctor}.py
  medlit/cli.py
  medlit/orchestrator.py
  medlit/config.py
  medlit/scheduler/{models,db,executor,rate_limit}.py
  medlit/state/{schema,store,migrate}.py
  medlit/retrieval/{planner,fusion,rerank,expand,dedupe}.py
  medlit/pubmed/{client,mesh,query}.py
  medlit/sources/{base,pubmed,europe_pmc,unpaywall}.py
  medlit/fulltext/{localizer,download,xml,pdf,html,quality}.py
  medlit/extraction/{evidence,locators}.py
  medlit/{http,report,verify}.py
  tests/{unit,fixtures,contract,integration,concurrency}/
  pyproject.toml / requirements lock（依赖方案审核后确定）

evals/
  metrics.py
  score_bioasq.py
  run_bioasq.py
  ablations.py
  fixtures/frozen_pico/
  baselines/<version>/

scripts/
  sync_plugin.py（迁移期只检查或改为兼容入口）
```

不会新增 `.mcp.json`，manifest 不会新增 `mcpServers`。

## 8. 测试与评测矩阵

### 8.1 自动化测试

- 单元：指标边界、PMID 规范化、PICO schema、MeSH fallback、PubMed 转义、查询梯形、RRF、去重、排序稳定性、预算、迁移和 locator。
- 固定夹具：PubMed XML、MeSH 响应、Europe PMC XML/PDF、重定向、HTML 错误页、损坏 PDF、扫描 PDF、重复段落和超大文件。
- 契约：录制并脱敏的 HTTP 响应作为默认离线测试；真实网络测试显式 opt-in，不能成为普通 CI 的不稳定依赖。
- 并发：任务只执行一次、依赖顺序、限速、429、超时、租约过期、进程崩溃、取消、恢复、SQLite 锁争用和单写状态无竞态。
- 集成：从 question 到 verified report 的离线 smoke；按来源模拟部分失败；无 PDF 依赖时正确降级。
- 安全：路径穿越、恶意文件名、超大响应、错误 MIME、日志密钥泄漏、TLS 禁用、非开放 URL 和 MCP 禁用扫描。
- 插件：validator、Skill validator、全新目录安装、cachebuster 重装、新会话识别、插件外工作目录调用和卸载后无残留运行依赖。

### 8.2 召回评测与消融

先保存未改代码的完整基线，再逐项开启：扩词、MeSH 双通道、查询梯形、批量/分页、多源、RRF、重排、引用扩展。每次只改变一个组件，报告总体与子集指标、请求数、延迟、缓存、错误和排名变化。最终候选版本再跑 340 题全量评测；开发中可用冻结小集，但不得用测试金标准手工调查询。

全文另报：OA 定位率、PDF 下载成功率、可解析全文率、OCR 使用率、质量通过率、摘要降级率、证据 locator 有效率和 report 引文可追溯率。这些指标不能与文献 PMID 召回率混为一谈。

## 9. 分阶段实施、审查门和回滚点

| 阶段 | 主要交付 | 必须通过的审查门 | 可回滚边界 |
|---|---|---|---|
| P0 基线与约束 | 当前插件基线、指标重算、MCP 禁用检查 | 同一插件入口可复现；现状指标和成本归档 | 不改运行行为 |
| P1 插件单一源码 | 版本统一、doctor、安装/重装、根目录兼容入口 | 全新环境黑盒安装和 validators 通过 | 恢复旧插件包 |
| P2 评测重构 | `final_ranked_pmids`、Hit/Recall/MAP/nDCG、双轨评测 | 指标金测试、日期防泄漏、基线一致 | 保留旧 scorer 只读对照 |
| P3 检索核心 | 新 schema、MeSH、查询梯形、分页、RRF/去重 | 小集和困难子集召回改善，无明显精度崩溃 | 每类查询独立 feature flag |
| P4 编排与并发 | orchestrator、SQLite 调度、限速、恢复/取消 | 并发与故障注入测试；状态无竞态 | `--workers 1` 顺序模式 |
| P5 全文与证据 | OA 定位、真实 PDF/XML 解析、locator、强 verify | 无 placeholder 证据；坏文件安全降级 | 关闭 PDF/OCR，退回摘要 |
| P6 多源与扩展 | Europe PMC、引用扩展、可选重排 | 独立消融证明收益/成本 | 逐适配器、逐重排器关闭 |
| P7 全量验收发布 | 340 题结果、文档、依赖锁、发布包 | 指标门槛、安装、许可证、安全全通过 | 保留上一语义版本可重装 |

任何阶段都先提交测试和迁移策略，再提交行为变更。未通过门槛的组件保留为实验开关，不进入默认 `balanced` 配置。

## 10. 主要风险与控制

| 风险 | 控制措施 |
|---|---|
| 扩词提高召回但污染前十 | 查询分层、RRF、可解释重排、MAP/P@10 保护门 |
| 查询数量爆炸或触发 API 限制 | 全局预算、每源令牌桶、批量抓取、缓存、饱和早停 |
| 并发破坏状态或重复下载 | SQLite 事务、幂等键、租约、单写者、原子快照 |
| MeSH 映射错误导致漏检 | 自由词双通道、映射置信度、fallback、映射审计 |
| PDF 依赖和 OCR 跨平台不稳定 | 可选 extra、doctor、固定夹具、摘要降级、进程池隔离 |
| 评测结果与生产插件脱节 | 所有评测只调用已打包插件入口，记录版本和配置哈希 |
| 日期泄漏夸大成绩 | 强制 question_date，测试查询必须出现正确日期约束 |
| 非开放全文或条款风险 | 白名单来源、license 记录、不确认则不下载、不绕过访问控制 |
| 第三方安装依赖开发机 | 清洁用户目录和插件外 CWD 黑盒测试，不引用仓库外文件 |
| 模型输出不稳定 | 冻结检索核心输入轨、schema 校验、保存 provenance、确定性后处理 |

## 11. 审核人需要确认的决策

以下项目不阻碍本稿评审，但在对应阶段开始前必须定案：

1. 公开发布使用的许可证、作者邮箱、隐私政策和服务条款 URL。
2. PyMuPDF 是必装依赖还是 `fulltext` extra；是否允许可选 Tesseract/OCR。
3. 默认配置档位、单题最大查询数、最大返回数、下载体积和 worker 上限。
4. 是否允许 Europe PMC、Unpaywall 和引用扩展作为默认网络来源。
5. 是否允许可选本地 embedding 模型；若允许，模型许可证、体积和下载方式。
6. 根目录旧 CLI 的兼容期，以及何时完全以插件目录为唯一源码。
7. BioASQ 基线版本、冻结 PICO 的审核方式，以及最终统计门槛。

在审核未确认前，默认采用最保守方案：标准库核心、PyMuPDF 可选、OCR 关闭、多源可配置、无 embedding、`balanced` 受限预算、保留旧 CLI 兼容入口。

## 12. 完成定义（Definition of Done）

只有同时满足以下条件，本轮升级才算完成：

- 插件为可独立安装的 Skill-only 包，所有 MCP 禁用检查和官方 validators 通过。
- 生产、测试和 BioASQ 评测运行同一插件代码，版本、配置和查询可复现。
- Hit Rate 与 Recall 的定义、实现、金测试、子集统计和置信区间全部落地。
- orchestrator 能一键运行、解释、取消和恢复；worker 有可观测的真实并发、严格限速和故障隔离。
- PDF 不再是占位文本，所有证据都有真实来源粒度与可验证 locator。
- 召回目标达到审核后的门槛，前十质量和成本护栏未被突破；各组件有消融和回滚开关。
- 全新用户环境完成安装、运行、重装、新会话加载和卸载验证，文档足以让第三方复现。
- 未访问非开放全文，未泄漏密钥或敏感输入，报告明确标注能力边界和失败降级。
