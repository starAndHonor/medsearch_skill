# MedLit 检索升级审核稿 v2：Retrieval First

> 状态：根据第一轮 reviewer 意见修订，待二审；不授权全面实施  
> 日期：2026-08-16  
> 取代范围：取代 `medlit_retrieval_upgrade_detailed_review.md` 的实施优先级与检索方法设计；原稿仅保留为工程候选清单  
> 硬约束：Skill-only 插件；不得采用 MCP

## 1. 对第一轮审核的处置结论

接受 **Conditional Reject — revise before implementation**。原稿把“检索召回不足”和“完整科研工作流能力不足”放在同一条关键路径上，工程范围过宽，且没有先回答两个核心问题：

1. gold 文献为什么没有进入候选集；
2. 已进入候选集的 gold 为什么没有排进前十。

因此本稿拆成两条轨道：

- **轨道 A：Retrieval Engine（本轮唯一 P0/P1）**。只处理问题表示、PubMed 查询、候选召回、融合、排序、评分和 miss attribution；BioASQ 是该层的回归测试。
- **轨道 B：Research Workflow（冻结）**。开放全文、PDF/OCR、证据 locator、报告、复杂恢复和大规模调度仍是产品目标，但必须等轨道 A 通过召回门后再单独立项。

短期不建设 SQLite lease 平台、ProcessPool/OCR、引用网络、Europe PMC 检索、多级全文质量评分或复杂 orchestrator。需要批量跑实验时，只允许使用可替换的简单 runner 和 NCBI 限速器，不把吞吐设施包装成召回改进。

## 2. 已核实事实，而非方案假设

### 2.1 当前数据与跑分状态

- `data/bioasq_13b_test_merged.json` 含 340 题：factoid 95、list 83、summary 80、yes/no 82；每题 gold 文献 1–124 篇，平均 25.69 篇。
- 原始 BioASQ JSON **没有** `question_date`。仓库的 `evals/convert_bioasq.py` 根据任务编号推断年份，并给所有 13B 题注入 `2025/12/31`。
- 该日期不是题目 schema、batch release date 或 Annual Baseline 快照标识，目前没有来源证明，故从“硬约束”降级为**待验证实验变量**。
- 仓库不存在 `evals/runs_13b` 和 `evals/results_13b`，因此当前没有可审核的 340 题运行结果、基线分数或真实 miss case。`RUN_WITH_CODEX.md` 只是运行说明，不能视作已完成评测的证据。

### 2.2 当前检索链中的直接风险

- `heuristic_pico()` 把整道问题写入 `population`，其余 PICO 留空，却统一附加 RCT、systematic review、meta-analysis；这不适配多数 BioASQ 问题。
- `TermPlanner` 默认 `humans=True`、`language=english`；索引滞后或非临床问题可能被过滤。
- QueryBuilder 主要输出带 `[MeSH Terms]`、`[Title/Abstract]` 的显式 tagged query，并把多个提取概念机械组合；PubMed 官方说明 field tag 会关闭 ATM。
- 评测执行器只运行四个硬编码 query ID，再按运行顺序拼接 PMID；没有 raw ATM baseline，也没有真正的融合排名。
- 评测默认继续跑全文、抽取、报告共 13 步，既拖慢 document retrieval 实验，也混淆 BioASQ title/abstract 任务和最终产品能力。

BioASQ 官方规定 Phase A 每题最多返回 10 篇、按 MAP@10 评估，且只使用 title/abstract，不要求 PMC 全文；官方也承认 gold 很可能不穷尽全部相关文献。因此 BioASQ 的深层指标只能称为 **known-gold recovery**，不能声称现实世界 exhaustive recall。参见 [BioASQ Task 14b 规则](https://participants-area.bioasq.org/general_information/Task14b/)。

## 3. 修订后的成功标准

### 3.1 官方轨与内部诊断轨分开

**BioASQ 官方轨：**最终只提交 `final_ranked_pmids[:10]`，主要报告 MAP@10，并同时报告官方 documents precision、recall、F1。排名必须按置信度递减且 PMID 唯一。

**内部诊断轨：**报告 Hit@5/10、known-gold Recall@10/20/50/100、MRR、nDCG@10/20/50、候选集 gold coverage，以及 gold 的中位/最差排名。R@20/50/100 只衡量“已知 gold 找回程度”，不得写成真实世界总召回率。

所有指标必须：

- 从唯一 `final_ranked_pmids` 读取；
- 宏平均并按题型、intent、gold 数量、索引状态和 failure bucket 分层；
- 用 paired bootstrap 输出候选系统相对基线的差值与 95% CI；
- 同时报请求数、延迟和 PubMed 返回候选数，防止用无界成本换分。

### 3.2 分阶段门槛

不在无基线情况下预先承诺固定“提升 20%”。先运行并冻结 B0 与 legacy 基线，再由二审锁定数值门槛。最低合并条件为：

- held-out 集 MAP@10 不下降；
- known-gold Recall@50 有稳定正向提升，paired CI 不跨越预设的无效区间；
- 至少两个主要 failure bucket 明显减少，且能由消融归因到具体策略；
- 不依赖 gold PMID、gold title 或 gold snippets 生成生产查询。

## 4. P0：先建立 Miss Attribution Lab

这是本轮第一个交付物，不先改“大架构”。对每个问题—gold PMID 对生成 `miss_record.jsonl`：

```json
{
  "question_id": "...",
  "gold_pmid": "...",
  "question_type": "factoid",
  "intent": "entity_identification",
  "variant_ranks": {"B0_raw_atm": null, "B1_anchors": 87},
  "candidate_seen": true,
  "final_rank": 142,
  "pubmed_translation": "...",
  "mesh_index_status": "indexed|not_indexed|unknown",
  "failure_bucket": "ranking_beyond_cutoff",
  "counterfactuals": ["remove_refiner", "restore_atm"],
  "evidence": {"query_id": "...", "retmax": 500}
}
```

### 4.1 Failure buckets

每个 miss 必须落入一个主类，必要时附次类：

1. `dataset_or_id_error`：PMID 重复、格式错误、记录不存在或 gold 数据异常；
2. `temporal_corpus_mismatch`：gold 不在所声明的 PubMed 快照/日期范围；
3. `entity_not_detected`：关键疾病、基因、蛋白、药物或缩写未识别；
4. `alias_or_normalization_gap`：旧名、商品名、基因/蛋白别名、拼写或缩写缺失；
5. `relation_or_intent_loss`：实体识别正确，但问题谓词/关系被丢失；
6. `over_constrained`：过多 anchor 被 AND，删除某个项后 gold 出现；
7. `optional_refiner_promoted`：outcome、comparator、design、mechanism 被错误设为必需；
8. `filter_exclusion`：humans、language、publication type 或日期过滤导致 miss；
9. `atm_suppressed`：field tag、引号或 wildcard 关闭 ATM 后 gold 消失；
10. `mesh_mapping_or_version`：MeSH 映射、explode、历史词表或未完成索引造成 miss；
11. `retrieved_beyond_depth`：查询能找出 gold，但排名超过 retmax；
12. `fusion_or_rerank_loss`：某个 variant 排名较高，融合/重排后跌出前十；
13. `pubmed_unretrievable_by_tested_queries`：所有审定反事实仍未找到；
14. `gold_incomplete_or_relevance_dispute`：只允许人工复核后使用，不能由程序因“未命中”自动判定。

### 4.2 自动追尸流程

对每个未命中的 gold，离线诊断依次检查：各 query variant 的深层 rank；PubMed Search Details/translation；去掉过滤器；逐个删除 AND 条件；恢复 untagged ATM；仅用标题关键实体；MeSH-only 与 free-text-only；当前/历史 MeSH；增大 retmax。诊断可以读取 gold 来解释失败，但产出的 counterfactual query 不得回流为该题生产结果，也不得用于 held-out 调参。

输出三类审核材料：

- `miss_summary.json/csv`：bucket 数量、占比和指标损失；
- `miss_cases.md`：至少 20 个分层代表案例，逐条展示 query、rank 和反事实；
- `query_trace/<qid>.json`：完整变体、translation、候选排名和融合分。

## 5. 分层基线：每一层都必须可独立消融

按以下顺序构建，禁止直接跳到“大一统 pipeline”：

| ID | 系统 | 目的 |
|---|---|---|
| B0 | 原始问题原样提交 PubMed，untagged ATM + `sort=relevance` | 最简单、不可删除的强基线 |
| B1 | 仅 1–2 个高置信 anchor，untagged ATM | 测试去除问句噪声是否有益 |
| B2 | anchor + 自由词别名扩展，不使用 MeSH tag | 测试实体/缩写覆盖收益 |
| B3 | 独立的 MeSH lane 与 Title/Abstract lane | 测试受控词表和未索引记录互补性 |
| B4 | optional refiner 生成独立查询变体 | 测试 relation/outcome/design 的增量价值 |
| B5 | B0–B4 结果做 RRF | 测试多路召回和确定性融合 |
| B6 | 仅在 B5 候选上做可解释重排 | 测试前十排序，而非扩大候选集 |

PubMed 默认 Best Match 是 relevance sort；官方帮助也建议结果太少时删除多余/过度具体的词，并说明 field tag 会关闭 ATM。因此 B0 和 ATM lane 必须长期保留，不能被“更专业”的显式检索式取代。[PubMed User Guide](https://pubmed.ncbi.nlm.nih.gov/help/)

每层记录新增找回的 gold、丢失的 gold、平均 rank 变化、每题请求数和 failure bucket 迁移。只有通过前一层消融，后一层才可成为默认配置。

## 6. 通用 Biomedical Query Representation

PICO 不再是顶层 AST。统一结构改为：

```json
{
  "question_type": "factoid|list|yesno|summary",
  "question_intent": "definition|entity_identification|relation|mechanism|causal|association|treatment|diagnosis|prognosis|epidemiology|measurement|other",
  "entities": [
    {"surface": "...", "canonical": "...", "type": "disease|gene|protein|drug|process|organism|other", "aliases": [], "confidence": 0.0}
  ],
  "predicate": "...",
  "qualifiers": [{"text": "...", "role": "population|outcome|time|setting|study_design|other", "required": false}],
  "anchors": ["entity-id"],
  "optional_refiners": ["qualifier-id"],
  "clinical_framework": {"kind": "PICO", "value": {}}
}
```

`question_type` 是答案形式，不等于检索 intent。PICO 仅在干预效果类问题中作为可选 specialization；机制、定义、基因/蛋白关系、数量和实体识别问题直接使用通用结构。

Anchor 规则：默认 1 个，最多 2 个；只有删除后问题主题会改变、且置信度达到阈值的概念才能强制 AND。Outcome、comparator、study design、mechanism 和多数 qualifiers 默认是 optional refiner，分别生成变体，不进入主查询硬约束。所有 anchor 决策必须保存理由和置信度。

## 7. Query Planner 修订

每道题至少生成四条相互独立的 lane：

1. **Raw ATM lane**：原始问题，去除纯指令前缀的版本可作为独立变体；不加 field tag。
2. **Anchor ATM lane**：1–2 个 anchor 的自然语言形式，保留 PubMed ATM。
3. **Free-text lane**：规范实体、缩写、别名和拼写变体，谨慎使用 `[tiab]`；用于覆盖新收录、未完成 MEDLINE indexing 的记录。
4. **MeSH lane**：验证过的 descriptor/entry term，显式记录 explode/noexp、mapping confidence 和词表年度。

Optional refiners 只生成附加 lane；不得修改 raw lane。所有 filters 默认关闭，只有问题明确要求时才作为独立变体。Query audit 保存 entered query、最终 term、Search Details/translation、sort、retmax、日期模式、MeSH 版本、结果数和 PMID 排名。

RRF 作为第一版融合，参数固定并留痕；同时保留单 lane 最佳 rank、出现 lane 数和源内 rank。B6 重排只能使用题目、标题、摘要和可审计元数据，不能用 gold。先从 lexical/entity/predicate coverage 开始，embedding 或学习排序另行审核。

## 8. 时间切片与 MeSH 年度实验

取消“所有 BioASQ 统一 `question_date=任务年/12/31`”的默认行为，改为三个明确模式：

- `official_snapshot`：使用该届 BioASQ 指定的 PubMed Annual Baseline Repository；这是历史复现实验的首选，但必须先核验 13B 对应快照、获取方式和 PMID 覆盖。
- `live_current`：当前 PubMed + 当前 MeSH，用于产品和日常回归；结果会随数据库更新变化。
- `derived_cutoff`：在线 PubMed + 人为 publication-date cutoff，仅作为敏感性实验；必须记录日期来源，不能冒充官方快照。

MeSH 同时运行 `historical_vocab` 与 `current_vocab` 两组实验。前者匹配 benchmark 年度词表，后者衡量现代产品能力。记录 descriptor 变更、entry term 变化和索引状态；不得用 2026 词表的收益宣称历史无未来信息成绩。NLM 说明 MeSH 层级搜索默认可 explode 到更窄概念，历史年度词表也需单独版本化。[NLM MeSH Explosion](https://www.nlm.nih.gov/oet/ed/pubmed/mesh/mod01/04-200.html)

## 9. 数据划分与防止 Gold 泄漏

- 从 `training13b.json` 建立分层 development 集，用于 failure taxonomy、规则调试和消融。
- 再冻结独立 validation 集，只用于选择 B0–B6 参数与 merge gate。
- 340 题 enriched test 在方案与参数冻结后只运行一次最终验收；如果已经查看其 gold 做 miss analysis，则必须明确降级为 analysis set，并另找 held-out 数据。
- 冻结每题输入、原始 gold 版本、MeSH 版本、PubMed snapshot、代码 commit、插件版本和配置哈希。
- gold 可用于评分与离线 miss explanation，不得进入 query representation、候选生成或重排特征。

BioASQ 明确表示专家 gold 可能遗漏其他相关文献，且会根据系统提交扩充。因此对非 gold 高排文献只计“unjudged”，抽样人工审核后报告 judged precision，不自动定为 false positive。

## 10. 最小实现范围与文件清单

P0/P1 只允许修改或新增以下范围，直接以插件为运行源码：

```text
plugins/medlit-cli/medlit/retrieval/
  representation.py      # 通用 biomedical query schema
  intent.py              # 问题 intent 与 entity/qualifier 结构化
  planner.py             # raw/anchor/free-text/MeSH lanes
  fusion.py              # RRF 与稳定 tie-break
  rerank.py              # 后置、可解释、可消融
plugins/medlit-cli/medlit/pubmed/
  client.py              # relevance、深层 rank、translation/audit
  mesh.py                # mapping、explode、年度词表接口
plugins/medlit-cli/medlit/cli.py
evals/
  retrieval_runner.py    # 只跑检索，不跑全文/报告
  metrics.py
  miss_analysis.py
  ablations.py
  splits/
  baselines/
  results/
```

根目录 `medlit/` 不再作为独立评测实现；迁移期可以是插件代码的薄兼容入口。插件继续只有 Skill + Python CLI，不增加 `.mcp.json`、`mcpServers`、服务进程或 MCP 依赖。

## 11. 修订后的阶段门

| 阶段 | 交付物 | 通过条件 | 暂缓内容 |
|---|---|---|---|
| R0 事实冻结 | 数据 provenance、无跑分声明、时间模式设计、数据 split | reviewer 确认 benchmark 与快照口径 | 所有产品扩建 |
| R1 Baseline Lab | B0/legacy 分数、统一 metrics、20+ real miss cases | 能逐篇回答 gold 在哪一层丢失 | 新 query 大改 |
| R2 表示与查询 | 通用 BQR、anchor/refiner、B1–B4 | 消融显示具体 bucket 减少 | 融合以外的复杂排序 |
| R3 融合与前十 | B5 RRF、B6 简单重排 | MAP@10 与 known-gold recovery 达门 | embedding/学习排序 |
| R4 检索发布 | 插件唯一源码、第三方安装、回归套件 | clean install + held-out 通过 | PDF/OCR/证据系统 |
| P2 产品工作流 | 另立 PDF、证据、并发恢复方案 | 仅在 R4 通过后重新审核 | 不提前占用召回研发 |

如批量实验确有吞吐瓶颈，R1 可加入简单有界线程池，但只负责独立题目/查询并行、3 req/s 无 key 或 10 req/s 有 key 的全局 NCBI 限速和失败重试；不引入 durable scheduler。NCBI 官方速率与批量请求建议见 [E-utilities 使用说明](https://www.ncbi.nlm.nih.gov/books/NBK25497/)。

## 12. 二审前必须提交的证据包

1. `question_date_provenance.md`：说明当前字段是如何派生的，并给出 official snapshot/live/derived 三种模式选择。
2. B0 raw ATM、legacy 系统的 development/validation 分数和完整配置。
3. 至少 20 个真实漏检案例，覆盖不少于 6 个 failure buckets；每例包含 gold PMID、查询、translation、variant rank 和反事实。
4. B0→B6 的逐层消融表，而不是只有最终总分。
5. `final_ranked_pmids` 唯一评分入口及 metric 金测试。
6. 插件源码一致性证明：评测调用 `plugins/medlit-cli`，不再调用根目录另一副本。
7. 明确列出本轮未做事项：PDF/OCR、全文证据、引用网络、复杂 orchestrator、SQLite scheduler 和非 PubMed 官方轨多源检索。

在以上证据包完成前，只批准 R0/R1；R2 之后仍需 reviewer 再次签字。

