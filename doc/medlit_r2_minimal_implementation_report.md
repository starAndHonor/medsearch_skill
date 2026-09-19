# MedLit R2-Minimal 实施与验证报告

## 实施范围

本轮仅落地三审批准的 retrieval 修复，没有建设 representation 重构、MeSH 扩展、PDF/OCR、调度器或 reranker。

1. **唯一运行源**：`plugins/medlit-cli/medlit/` 成为唯一维护实现。根目录 CLI 与 `import medlit` 均委托插件；旧同步脚本改为只读解析校验。BioASQ runner 直接调用插件入口，评分器优先读取插件生成的 `final_ranked_pmids`。
2. **term construction**：保留罕见实体及大小写/数字/连字符 token；`reduce`、`identified`、`action` 等泛词不再进入结构化 OR；新增未加 field tag 的 cleaned-natural lane，并保留结构化 entity lane 与实体共现 AND lane。
3. **融合与审计**：多 lane 使用 RRF（k=60）生成最终排名；重复执行同一 lane 会替换旧结果，避免重复加权。状态同时保存输入 query、实际日期约束、PubMed `querytranslation`、`translationset`、retmax 与 fusion provenance。
4. **过滤和深度**：humans/English 改为显式 opt-in；MeSH 仅通过 `build-query --use-mesh` 实验启用。候选深度可配置，balanced 默认值由 validation 曲线从 20 调整为 100。

## 冻结 validation

从 13B1–13B4 中，每个 batch×题型固定取源顺序第 2、3 题，共 32 题；与 R1 的 16 题 smoke 无重叠。共含 910 个 gold PMID，因此同时报告 question-level macro 与 gold-level micro 指标。所有查询使用同一 live PubMed、同一 `2025/12/31` publication cutoff；这不是 2025 frozen baseline，也不作为 BioASQ 官方成绩。

### 核心 before/after（产品默认条件）

| 系统 | depth | Hit@10 | MAP@10 | Macro R@10 | Macro R@50 | Macro R@100 |
|---|---:|---:|---:|---:|---:|---:|
| legacy concat | 20 | 0.406 | 0.0216 | 0.0535 | 0.0844 | 0.0844 |
| fixed terms + RRF | 100 | 0.469 | 0.0738 | 0.1036 | 0.2110 | 0.2789 |

新默认相对旧默认：MAP@10 +0.0521，macro R@10 +0.0500，macro R@50 +0.1266。按题计，R@100 为 28 胜、0 负、4 平；AP@10 为 13 胜、6 负、13 平，说明总体提升明确但不是逐题单调改善。

## 单项消融结论

- **term construction（depth=100，均 concat）**：MAP@10 0.0216→0.0643，macro R@10 0.0535→0.0948，macro R@100 0.1384→0.2783，是本轮主要增益来源。
- **fusion（fixed terms，depth=100）**：concat→RRF 后 Hit@10 0.438→0.469，MAP@10 0.0643→0.0738，macro R@10 0.0948→0.1036。RRF 不改变候选并集，但改善 top ranking，故保留。
- **默认过滤器**：加入强制 humans/English lane 后 MAP@10 0.0738→0.0603，macro R@10 0.1036→0.0958；但 deep micro recall 有小幅互补收益。因此不作默认约束，仍允许协议显式启用。
- **候选深度**：fixed RRF 的 macro R@50 在 50/100/200/500 深度分别为 0.2022/0.2110/0.2138/0.2131。100 是收益—请求成本拐点；500 仅用于 recall-oriented 诊断，不作为 balanced 默认。

## 验证与边界

定向单元测试覆盖实体—动词拆分、泛词排除、自然/结构化 lane、AND anchor、过滤器 opt-in、RRF、lane 内去重、深度截断和 PubMed translation 保存。端到端 CLI smoke 以 Plozasiran 执行两条真实 PubMed lane，确认融合结果写入、translation 可审计且重复 lane 会被替换。

当前证据支持保留全部 R2-Minimal 改动。仍未证明需要 MeSH、完整 PICO/BQR 重写或 reranking；这些继续冻结。历史 BioASQ13 复现仍需 2025 baseline snapshot 与官方 evaluator 环境。
