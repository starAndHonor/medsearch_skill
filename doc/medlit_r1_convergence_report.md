# MedLit Retrieval Upgrade：R0/R1 二审收敛报告

> 日期：2026-08-16  
> 范围：仓库事实、provenance 与 retrieval-only smoke；不构成方案 v3  
> 结论：已有证据支持批准少量 R2 改动，但不支持全面重写检索架构

## 1. 已确认的仓库事实

1. **340 题来源可靠，但“平均 25.69 篇 gold”口径不严谨。** 官方数据页将 BioASQ13（2025）的测试数据列为 `13b golden enriched`。本地四个 `13B1–4_golden.json` 各 85 题，合并文件与四批按序拼接完全一致，仅新增 `batch` 字段；无重复 question ID。合并文件 SHA-256 为 `232597966C41628A92DE05D6FFCEFFD5FF923F9A40DF40ADC7B0C1FED673FCD5`。[BioASQ datasets](https://participants-area.bioasq.org/datasets/)
2. 25.6912 是每题原始 document URL 数，含 169 个重复引用；规范化为唯一 PMID 后平均 **25.1941**，范围 1–123。后续评分必须先去重。该数据是赛后 enriched gold，不等于 Phase A 当日初始 gold，也不应与官方 leaderboard 分数直接无条件对比。
3. **现有代码不是历史 BioASQ 复现。** 原始 golden JSON 没有 `question_date`；`convert_bioasq.py` 根据任务号自行注入 `2025/12/31`。评测实际调用 2026 年当前在线 E-utilities，再加 publication-date 条件。BioASQ13 使用的是 PubMed Annual Baseline；NLM 的 2025 baseline 是 2025-01-14 发布的完整快照 `pubmed25n0001–1274`，之后另有 daily new/revised/deleted updates。当前在线索引加日期条件不能还原该快照。[NLM 2025 Baseline](https://www.nlm.nih.gov/pubs/techbull/jf25/jf25_pubmed_2025_baseline.html)
4. 仓库没有 2025 baseline corpus，也没有 `runs_13b/results_13b`；故此前不存在可审核的历史全量基线。当前机器也没有 Java，官方 BioASQ jar 暂不能执行。
5. **“当前 legacy”有两个版本。** `run_bioasq.py` 强制从根目录 `medlit/` 运行；已安装插件运行 `plugins/medlit-cli/medlit/`。`sync_plugin.py --check` 显示 `cli.py`、`pubmed/client.py`、`pubmed/query.py` 不同步，因此评测结果不能自动代表插件。
6. 当前 BioASQ heuristic 把整题放入单一 `population`；所以本路径的主查询并不是多个 PICO 字段机械 AND，而是一个包含大量词项的 OR block。PICO 多字段 AND 不是本次 smoke 所观察到的主因。

## 2. 实际运行的 smoke experiments

### 2.1 对照设计

从四个 batch 各取 factoid/list/yesno/summary 的第一题，共 16 题、241 个唯一 gold PMID。该样本用于区分解释，不用于估计全量成绩。每条查询取当前 PubMed Best Match 前 500，并缓存完整 query translation：

- `raw_current`：原始问题直接交给当前 PubMed ATM；
- `raw_cutoff`：同上，加现有 `2025/12/31` 条件；
- `eval_legacy_concat`：当前根目录评测 query ladder，按现有运行顺序拼接；
- `plugin_legacy_concat`：当前插件代码；
- `eval_legacy_rrf_diagnostic`：不改候选，只把现有各 query 排名做 RRF；
- `eval_legacy_no_mesh_concat`：相同 term plan，但不给 MeSH validation。

下表为内部诊断 AP/MAP，不冒充官方 jar 成绩：

| 系统 | Hit@10 | MAP@10 | Macro R@10 | R@50 | R@500 |
|---|---:|---:|---:|---:|---:|
| raw current | 0.375 | 0.151 | 0.155 | 0.201 | 0.249 |
| raw + derived cutoff | 0.438 | 0.125 | 0.156 | 0.198 | 0.250 |
| eval legacy concat | 0.500 | 0.210 | 0.239 | 0.401 | 0.518 |
| plugin legacy concat | 0.500 | 0.218 | 0.253 | 0.371 | 0.576 |
| eval legacy + RRF | **0.563** | **0.248** | **0.301** | **0.422** | **0.620** |
| eval legacy, no MeSH | 0.500 | 0.210 | 0.239 | 0.400 | 0.619 |

结论：legacy 整体强于未经清理的 raw baseline；raw 是必要对照，但不能取代 legacy。日期 cutoff 没有排除本样本中 raw top-500 已找到的 gold，却改变排名并降低 MAP，说明它既不是历史快照，也不是当前主要漏检解释。RRF 在不新增 query 的前提下改善前十；缓存重跑结果一致。

### 2.2 判别性案例

- **RankMHC：raw 清理问题。** `Describe RankMHC` 被 ATM 翻译为 `describe AND RankMHC`，返回 0；去掉指令词后 `RankMHC` 唯一结果即 gold。说明“raw ATM 必然强”被推翻，轻量问句清理有证据。
- **Plozasiran：实体在 term construction 中丢失。** legacy 生成短语 `"Plozasiran reduce"[tiab]`，PubMed translation 最终只剩 `pancreatitis[tiab]`，4 篇 gold 均未进 legacy top-500；`Plozasiran` 单实体查询找回 4/4（top-10 为 3/4）。这是确定的 representation/query bug。
- **MR-PheWAS：宽 OR 导致排名稀释。** raw 完整问题只返回 gold，rank 1；legacy 把 `identified` 等泛词与实体 OR，命中 2,908,182 篇，gold 降到 rank 216。仅 rare anchor 又只有 rank 29，说明不能机械改成“anchor-only”；需要保留互补 query lane并控制泛词。
- **Nipocalimab：两种基线都有缺陷。** raw ATM 把 `what is` 误解析出 author 条件而返回 0；legacy 把泛词 `action` OR 进去，候选 874,741。`nipocalimab[tiab]` 找回 6/6，前 50 为 5/6。问题是问句解析与泛词，而非缺少复杂 PICO。
- **Zotiraciclib：确认是 fusion/order bug。** 宽 OR 中两篇 gold 排 24/56，AND 变体排 1/3；现有 concat 前十为 0/2，RRF 为 2/2。当前所谓 multi-query 在第一条查询返回超过十篇时，后续 query 对 top-10 实际没有贡献。
- **PDE5：query formulation 与 ranking 同时存在。** legacy 宽 OR 命中 281,294 篇且 top-10 为 0；`class AND (half-life OR pharmacokinetic*)` 降至 258 篇，找回 6/7，但前 50 只有 2 篇。更好的 query 能扩大有效候选，仍需后续排名。

### 2.3 Filters 与 MeSH 的直接对照

用 `PMID[uid]` 对 241 个 gold 做成员测试：全部存在于**当前** PubMed；加 `humans[MeSH]` 后排除 53 篇（22.0%），加 `english[Language]` 后排除 13 篇（5.4%），二者合计排除 65 篇（27.0%，8/16 题受影响）。所以默认 filters 的召回风险被实验支持。但 current concat 的第一条 broad query没有 filters，故 filters 不是本样本当前 top-10 的首要直接原因，而是一个无必要的高风险后续 lane。

36 个 MeSH candidate 中只有 6 个 valid、1 个 entry term。MeSH/no-MeSH 的 top-10 完全相同，深层结果混合：MeSH 对个别题略有帮助，却把 PDE5 的 top-500 gold 从 4 降为 0、MR-PheWAS 从 1 降为 0；总体 R@500 为 0.518 vs 0.619。该 smoke **不支持优先进行 MeSH 大改**，也不能推出“MeSH 无用”；它只说明现有 mapping/组合尚未显示稳定净收益。

## 3. 当前主要 failure modes

以 241 个 gold 为单位（大 gold 题会占更多权重）：

| 观察结果 | 数量 | 当前解释 |
|---|---:|---|
| legacy top-10 | 10 | 已命中 |
| legacy 某 query rank 11–500 | 86 | candidate depth / ranking |
| legacy 未达、raw 可达 | 36 | query formulation/translation 损失 |
| 后续 variant 很高但 concat 丢失 | 5 | fusion/order 损失 |
| raw 与 legacy 均未进 top-500，但 PMID 当前存在 | 104 | query coverage、语义间接性或 enriched-gold 相关性；不是当前 corpus 不存在 |

因此当前最有证据的瓶颈顺序是：

1. **query construction 产生错误短语或泛化 OR，导致实体消失或百万级候选稀释；**
2. **候选深度与排序不足；**实际 runner 默认 retmax 20，会比本次 top-500 诊断更早截断；
3. **顺序拼接使 multi-query 对前十失效；**
4. default filters 能真实排除 gold，但在当前 concat 顺序下不是第一主因；
5. 当前 PubMed corpus 不可达在本样本中为 0；Annual Baseline 是否可达仍未测，因为本地没有该快照。

## 4. 对上一轮 reviewer 关键意见的判断

| 争议点 | 判断 | 证据修正 |
|---|---|---|
| 先做 retrieval，暂缓 PDF/调度平台 | **支持** | 本轮已用纯检索实验定位瓶颈，无需产品扩建 |
| raw PubMed 应保留为基线 | **支持，但不能替代 legacy** | legacy 指标更高；raw 会被 `Describe`、`what is` 错误解析 |
| `question_date` 是危险假设 | **支持** | 字段为仓库派生；live EUtils + 日期不等于 Annual Baseline |
| PICO/多概念 AND 是当前主因 | **部分推翻** | BioASQ heuristic 只有一个 population；主查询实际是过宽 OR |
| 应改为 anchor/refiner | **部分成立** | 稀有实体保留很重要，但 MR-PheWAS 显示 anchor-only 也可能降 rank；应做互补 lanes，不设单一规则 |
| field tag/MeSH 导致主要漏检 | **尚不能整体判断** | 已确认一个 tagged phrase 丢实体；MeSH top-10 无净收益且深层混合，不能泛化 |
| humans/English 默认过滤危险 | **支持并量化** | 直接排除 27.0% 样本 gold；但不是当前 concat top-10 首因 |
| RRF 值得先做 | **支持** | 同候选 MAP 0.210→0.248，Zotiraciclib 0/2→2/2 |
| 低召回来自 corpus 不可达 | **当前 live corpus 上推翻** | 241/241 PMID 可达；历史 baseline 条件仍未知 |

## 5. R2 最小开发建议

只建议批准以下四项，并保持独立 feature flag 与消融：

1. **先统一运行源码和评分入口。** 评测必须调用 `plugins/medlit-cli`，消除根目录/插件双版本；否则任何 R2 分数不可归因。
2. **候选池加深并用 RRF 取代顺序拼接。** 每个 lane 拉取可配置深度（先测 100/500），融合后只输出前十；这是收益最直接、改动最小的一项。
3. **修复现有 term construction，而不是先重写通用 AST。** 保留稀有实体单词，禁止把实体与动词粘成未命中 phrase；从 broad OR 删除 `action/identified` 等泛词；保存 PubMed translation，并保留“清理后的自然问题”和结构化实体 query 两条互补 lane。
4. **关闭默认 humans/English filters。** 仅在用户明确要求时作为可选 lane，不进入 recall-first 默认查询。

暂不批准：全面 biomedical representation/PICO 重写、MeSH 年度系统、embedding/reranker、Europe PMC、引用扩展、复杂 orchestrator、SQLite scheduler、PDF/OCR。MeSH 保留现状或实验开关，待更大 validation 集消融后再决定。

## 6. 产物与剩余不确定性

- 可复现 runner：`evals/r1_retrieval_smoke.py`，SHA-256 `8903EC5C835D478A2E91D775AAA53E676873992B95EFD81EFD4F3160F6FE635C`。
- 完整查询、translation、PMID 排名和 counterfactual：`evals/r1_smoke/results.json`，SHA-256 `4AD3CE59E58B013A0AB8CB02A510351C5265366670AB414C51C010D31F0FB2E9`。
- 本报告不声称 16 题代表全量；下一轮应在冻结 validation 集验证四项最小改动。
- 如需声称“BioASQ13 历史成绩”，仍必须获得/构建 2025 Annual Baseline 本地索引、明确 enriched gold 口径，并恢复官方 evaluator 运行环境。

