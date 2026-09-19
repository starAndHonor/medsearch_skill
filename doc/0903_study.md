# 0903 Study：PubMed 检索式构造与多文献证据

本次继续使用 [BioASQ-13B-2025-test benchmark](../evals/bioasq_13b_test_benchmark.json)，另选四种题型。推荐式不是唯一正确答案，重点是观察字段限定、概念宽窄、别名和同义表达如何影响 gold PMID 的召回与排名。检索结果可能随 PubMed 数据更新变化。

## 操作方法

1. 先直接打开推荐检索式，保持 `Best match` 排序，记录结果总数以及 gold PMID 的排名。
2. 在 `Advanced` 页面查看 Query details，确认字段标签、布尔关系和短语是否按预期解析。
3. 按每题给出的对照方向只改一个因素，再比较结果，不要同时改动多个概念。
4. 对 summary 或多篇 gold 的题目，打开至少三篇摘要，记录每篇分别支持答案的哪一部分。

## 1. Summary：GBM 缺氧与细胞状态

- BioASQ ID：`67d74b0418b1e36f2e00003b`
- 问题：**How does hypoxia influence the cell states of glioblastoma multiforme (GBM)?**
- 推荐精确式：`(glioblastoma[Title/Abstract] OR GBM[Title/Abstract]) AND hypoxia[Title/Abstract] AND cell state*[Title/Abstract]`
- 直接打开：[精确检索](https://pubmed.ncbi.nlm.nih.gov/?term=%28glioblastoma%5BTitle%2FAbstract%5D+OR+GBM%5BTitle%2FAbstract%5D%29+AND+hypoxia%5BTitle%2FAbstract%5D+AND+cell+state%2A%5BTitle%2FAbstract%5D)
- 召回对照式：`(glioblastoma[Title/Abstract] OR GBM[Title/Abstract]) AND hypoxia[Title/Abstract]`
- 直接打开：[宽检索](https://pubmed.ncbi.nlm.nih.gov/?term=%28glioblastoma%5BTitle%2FAbstract%5D+OR+GBM%5BTitle%2FAbstract%5D%29+AND+hypoxia%5BTitle%2FAbstract%5D)
- Gold PMID：[38538643](https://pubmed.ncbi.nlm.nih.gov/38538643/)、[38653236](https://pubmed.ncbi.nlm.nih.gov/38653236/)、[34956900](https://pubmed.ncbi.nlm.nih.gov/34956900/)、[26724617](https://pubmed.ncbi.nlm.nih.gov/26724617/)、[25592037](https://pubmed.ncbi.nlm.nih.gov/25592037/)
- 观察重点：精确式只使用问题原文中的概念；不能根据 gold answer 反向加入 `mesenchymal` 等答案词。宽式候选更多，gold 可能被推到较深位置。比较两式的 gold 并集，并整理不同论文分别描述的细胞状态变化。

## 2. Factoid：Axatilimab 的靶点

- BioASQ ID：`67e6bed318b1e36f2e0000c4`
- 问题：**What is the target of axatilimab?**
- 推荐式：`axatilimab[Title/Abstract] AND (CSF1R[Title/Abstract] OR "colony stimulating factor 1 receptor"[Title/Abstract] OR target*[Title/Abstract])`
- 直接打开：[推荐检索](https://pubmed.ncbi.nlm.nih.gov/?term=axatilimab%5BTitle%2FAbstract%5D+AND+%28CSF1R%5BTitle%2FAbstract%5D+OR+%22colony+stimulating+factor+1+receptor%22%5BTitle%2FAbstract%5D+OR+target%2A%5BTitle%2FAbstract%5D%29)
- Gold PMID：[39292927](https://pubmed.ncbi.nlm.nih.gov/39292927/)、[39551906](https://pubmed.ncbi.nlm.nih.gov/39551906/)、[39704205](https://pubmed.ncbi.nlm.nih.gov/39704205/)、[36459673](https://pubmed.ncbi.nlm.nih.gov/36459673/)
- Gold 答案：colony-stimulating factor 1 receptor（CSF-1R）。
- 观察重点：先搜索 `axatilimab[Title/Abstract]`，再加入靶点缩写、全称和 `target*`，比较增加概念后结果是更集中还是反而漏检。

## 3. List：Ivonescimab 的多个靶点

- BioASQ ID：`67e6ba8e18b1e36f2e0000bf`
- 问题：**What are the targets of Ivonescimab?**
- 推荐式：`(ivonescimab[Title/Abstract] OR AK112[Title/Abstract]) AND (PD-1[Title/Abstract] OR VEGF[Title/Abstract] OR bispecific[Title/Abstract] OR target*[Title/Abstract])`
- 直接打开：[推荐检索](https://pubmed.ncbi.nlm.nih.gov/?term=%28ivonescimab%5BTitle%2FAbstract%5D+OR+AK112%5BTitle%2FAbstract%5D%29+AND+%28PD-1%5BTitle%2FAbstract%5D+OR+VEGF%5BTitle%2FAbstract%5D+OR+bispecific%5BTitle%2FAbstract%5D+OR+target%2A%5BTitle%2FAbstract%5D%29)
- Gold PMID：[39073550](https://pubmed.ncbi.nlm.nih.gov/39073550/)、[38642937](https://pubmed.ncbi.nlm.nih.gov/38642937/)、[37879536](https://pubmed.ncbi.nlm.nih.gov/37879536/)、[39490738](https://pubmed.ncbi.nlm.nih.gov/39490738/)、[39276767](https://pubmed.ncbi.nlm.nih.gov/39276767/)
- Gold 答案：programmed cell death protein 1（PD-1）和 vascular endothelial growth factor A（VEGF-A）。
- 观察重点：删去旧名 `AK112` 后重新搜索，检查哪些 gold 消失或排名下降；这用于观察实体别名对召回的贡献，而不只是布尔式宽窄。

## 4. Yes/No：Perampanel 与 homicidal ideation

- BioASQ ID：`67e4571218b1e36f2e0000a7`
- 问题：**Is perampanel associated with homicidal ideation?**
- 推荐精确式：`perampanel[Title/Abstract] AND "homicidal ideation"[Title/Abstract]`
- 直接打开：[精确短语检索](https://pubmed.ncbi.nlm.nih.gov/?term=perampanel%5BTitle%2FAbstract%5D+AND+%22homicidal+ideation%22%5BTitle%2FAbstract%5D)
- 扩展对照式：`perampanel[Title/Abstract] AND (homicid*[Title/Abstract] OR aggression[Title/Abstract] OR violen*[Title/Abstract])`
- 直接打开：[扩展概念检索](https://pubmed.ncbi.nlm.nih.gov/?term=perampanel%5BTitle%2FAbstract%5D+AND+%28homicid%2A%5BTitle%2FAbstract%5D+OR+aggression%5BTitle%2FAbstract%5D+OR+violen%2A%5BTitle%2FAbstract%5D%29)
- Gold PMID：[37315406](https://pubmed.ncbi.nlm.nih.gov/37315406/)、[28830031](https://pubmed.ncbi.nlm.nih.gov/28830031/)
- Gold 答案：`yes`。
- 观察重点：比较精确短语与扩展不良行为概念。前者适合直接回答题目，后者可能找到更多安全性背景，但要判断新增论文是否真正支持 homicidal ideation，而不只是一般攻击行为。

## 实际记录表

| 题目 | 检索式版本 | 结果数 | Gold 命中及排名 | 新增相关论文 | 支持的答案要点 | 备注 |
|---|---|---:|---|---|---|---|
| GBM hypoxia | 精确式 |  |  |  |  |  |
| GBM hypoxia | 宽式 |  |  |  |  |  |
| Axatilimab | 推荐式 |  |  |  |  |  |
| Ivonescimab | 含 AK112 |  |  |  |  |  |
| Ivonescimab | 不含 AK112 |  |  |  |  |  |
| Perampanel | 精确短语 |  |  |  |  |  |
| Perampanel | 扩展概念 |  |  |  |  |  |

本练习中 gold PMID 是已知相关文献集合，不保证穷尽所有相关论文。判断检索式时应同时看 gold 召回、排名和新增结果的真实相关性；判断答案时则要进一步检查多篇证据能否共同覆盖结论。
