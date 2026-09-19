# 0901 Study：从 BioASQ 到 PubMed 实际检索

本次练习使用仓库中的 [BioASQ-13B-2025-test benchmark](../evals/bioasq_13b_test_benchmark.json)。每道题都保留 BioASQ 专家标注的 `gold_pmids`，用于检查 PubMed 检索结果是否找回标准文献。`2025/12/31` 是本仓库转换脚本补入的文献日期上限，并非 BioASQ 保存的历史 PubMed 检索快照；下列检索网址也是根据题目后加的练习链接。

## 完整问句复核（2026-09-03）

PubMed 网页与 E-utilities 实测一致：`Describe RankMHC` 被翻译为 `describe* AND RankMHC`，返回 0 条；`RankMHC` 返回唯一结果 `39555889`。UCHL1 完整问句被扩展为必须同时含 `disease`、`caused`、`heterozygous`、`UCHL1`、`loss-of-function` 和 `variants`，返回 0 条；去掉问句框架后的 `heterozygous UCHL1 loss-of-function variants` 返回 5 条，包含 gold PMID `35986737`。

这不构成 PubMed 在 benchmark 发布后改变检索系统的证据。NLM 在 [2024 MeSH Highlights](https://www.nlm.nih.gov/oet/ed/mesh/2024/mesh-highlights.html) 中说明 ATM 仍基于翻译表且近期未改变；[2025 PubMed 更新](https://www.nlm.nih.gov/pubs/techbull/mj25/mj25_pubmed_updates.html)主要涉及界面和检索历史，年度 MeSH 维护也不能解释这两例。[BioASQ 数据集说明](https://participants-area.bioasq.org/datasets/)表明数据提供自然语言问题和 gold 文献，参赛系统需要自行完成查询构造，不能假设问题原句就是有效的 PubMed 检索式。

## 统一操作方法

### 1. 先用浏览器理解 PubMed

1. 打开每题的 PubMed 检索网址，观察 PubMed 是否进行了 Automatic Term Mapping，以及返回的结果数量。
2. 再分别搜索问题中的核心实体或短语，比较自然语言检索和关键词检索的差异。
3. 打开前 10 条结果，使用 gold PMID 链接核对标准文献是否出现、出现在哪个位置。
4. 记录：检索词、结果数量、命中的 gold PMID、未命中的 gold PMID，以及 PubMed 对检索词的解释。

### 2. 再用 medlit-cli 对照

在新对话中显式调用 `$medlit-cli`，对同一道题执行：

```text
请用 $medlit-cli 处理下面这道 BioASQ 题目：<问题原文>
请依次展示 PICO、term_plan、query_ladder、每条 query 的 query_translation、命中数和前10个 PMID。
检索截止日期使用 2025/12/31，并说明每个 gold PMID 是否被找回。
```

重点观察流程：

```text
问题 -> PICO -> term_plan -> query_ladder -> PubMed ESearch
     -> retrieval_runs -> RRF -> final_ranked_pmids -> fetch-records
```

比较时先不要启用 MeSH；完成默认检索后，再单独尝试 `validate-mesh` 和 `build-query --use-mesh`，这样才能看出 MeSH 对结果的实际影响。

## 练习题

### 1. Summary：工具/方法型问题

- BioASQ ID：`67d74cde18b1e36f2e00003c`
- 问题：**Describe RankMHC**
- PubMed 检索：[完整问句（复现 0 条）](https://pubmed.ncbi.nlm.nih.gov/?term=Describe+RankMHC)；[推荐关键词 RankMHC](https://pubmed.ncbi.nlm.nih.gov/?term=RankMHC)
- Gold PMID：[39555889](https://pubmed.ncbi.nlm.nih.gov/39555889/)
- Gold 答案要点：RankMHC 是用于识别和排序 peptide-MHC 结合模式的 learning-to-rank 预测器。
- 操作重点：比较完整问题和 `RankMHC`；确认 PubMed 没有自动去掉 `Describe`，并核对唯一 gold 文献是否进入前 10。

### 2. Factoid：基因与疾病型问题

- BioASQ ID：`67d3518718b1e36f2e000008`
- 问题：**Which disease is caused by heterozygous UCHL1 loss-of-function variants?**
- PubMed 检索：[完整问句（复现 0 条）](https://pubmed.ncbi.nlm.nih.gov/?term=Which+disease+is+caused+by+heterozygous+UCHL1+loss-of-function+variants%3F)；[推荐关键词](https://pubmed.ncbi.nlm.nih.gov/?term=heterozygous+UCHL1+loss-of-function+variants)
- 高级检索记录：[`(UCHL1[Title/Abstract]) AND (heterozygous[Title/Abstract])`](https://pubmed.ncbi.nlm.nih.gov/?term=%28UCHL1%5BTitle%2FAbstract%5D%29+AND+%28heterozygous%5BTitle%2FAbstract%5D%29) 返回 17 条结果；第 1 条即 gold PMID `35986737`。该检索式将两个核心实体限定在题名/摘要字段，成功避开完整问句中 `disease`、`caused` 等词造成的过度约束。
- Gold PMID：[35986737](https://pubmed.ncbi.nlm.nih.gov/35986737/)
- Gold 答案：一种伴随痉挛、共济失调、神经病变和视神经萎缩的神经退行性疾病。
- 操作重点：比较完整问题、`heterozygous UCHL1 loss-of-function variants` 和 `UCHL1[Title/Abstract]`；该题只有 1 篇 gold，适合观察问句词造成的过度约束。

### 3. List：药物性质与多答案型问题

- BioASQ ID：`67cc973e81b1027333000011`
- 问题：**Please list the short half life Phosphodiesterase 5 inhibitors.**
- PubMed 检索：[打开问题检索](https://pubmed.ncbi.nlm.nih.gov/?term=Please+list+the+short+half+life+Phosphodiesterase+5+inhibitors.)
- Gold PMID：[29679708](https://pubmed.ncbi.nlm.nih.gov/29679708/)、[17183346](https://pubmed.ncbi.nlm.nih.gov/17183346/)、[16780568](https://pubmed.ncbi.nlm.nih.gov/16780568/)、[15115191](https://pubmed.ncbi.nlm.nih.gov/15115191/)、[27438594](https://pubmed.ncbi.nlm.nih.gov/27438594/)、[16959227](https://pubmed.ncbi.nlm.nih.gov/16959227/)、[17201266](https://pubmed.ncbi.nlm.nih.gov/17201266/)
- Gold 答案要点：`sildenafil`、`vardenafil`、`Mirodenafil`、`Avanafil`、`Udenafil`。
- 操作重点：比较完整句、`PDE5 inhibitor half-life` 和分别搜索药物名；观察结构化 AND 查询是否过窄，以及多个相关 gold PMID 是否能被不同 lane 找回。

### 4. Yes/No：临床相关性型问题

- BioASQ ID：`66301d1d187cba990d000026`
- 问题：**Are respiratory measurements correlated with disease severity in Duchenne Muscular Dystrophy?**
- PubMed 检索：[打开问题检索](https://pubmed.ncbi.nlm.nih.gov/?term=Are+respiratory+measurements+correlated+with+disease+severity+in+Duchenne+Muscular+Dystrophy%3F)
- Gold PMID：[36596294](https://pubmed.ncbi.nlm.nih.gov/36596294/)、[29412787](https://pubmed.ncbi.nlm.nih.gov/29412787/)、[23836708](https://pubmed.ncbi.nlm.nih.gov/23836708/)、[37539841](https://pubmed.ncbi.nlm.nih.gov/37539841/)、[29437939](https://pubmed.ncbi.nlm.nih.gov/29437939/)、[36571207](https://pubmed.ncbi.nlm.nih.gov/36571207/)、[9014949](https://pubmed.ncbi.nlm.nih.gov/9014949/)、[25755201](https://pubmed.ncbi.nlm.nih.gov/25755201/)
- Gold 答案：`yes`；重点指标包括 forced vital capacity、total lung capacity 和 transcutaneous carbon dioxide。
- 操作重点：比较完整问题与 `Duchenne muscular dystrophy respiratory measurements severity`；打开 gold 文献摘要，确认“相关性”结论，而不是只看标题命中。

## 建议记录表

每题实际操作后补记以下结果：

| 题型 | 查询版本 | PubMed命中数 | Top 10命中gold | 未命中gold | query translation | 备注 |
|---|---|---:|---|---|---|---|
| summary |  |  |  |  |  |  |
| factoid |  |  |  |  |  |  |
| list |  |  |  |  |  |  |
| yes/no |  |  |  |  |  |  |

注意：`gold_pmids` 是 BioASQ 专家提供的已知相关文献，不保证穷尽所有相关论文；练习目标是理解检索链路和已知 gold 的召回，不把未标注文献自动判定为错误结果。
