# 0915_v3：MedLit 可靠性优化版盲测

状态：未运行。沿用原16题，只包含自然语言问题与题型，不携带参考答案、gold PMID、旧检索式或旧结果。

## 实验边界

新窗口仅打开本目录，选择6 Astra，发送 [NEW_WINDOW_PROMPT.md](NEW_WINDOW_PROMPT.md)。固定已安装 MedLit 版本 `0.2.0+codex.20260915142801`；记录实际可确认的模型标识，无法确认时注明。不可使用 Science 技能或仓库里的迁移副本作为替代。

每题独立 state；仅检索模式；retmax=100、relevance 排序、前10篇标题及完整可用摘要反馈、不设日期截止。按插件自身规则迭代，只接受一个查询，原样保留其 PubMed 排名。禁止合并结果、摘要筛选、重排、全文下载或答案生成。

## 执行与留痕

1. 先检查插件版本、CLI入口及各命令帮助。插件不可用则报告阻塞，不能换实现。
2. 用 `init --question <原题> --mode retrieval` 建立独立状态。具体 state 参数和入口以插件帮助为准。
3. 每次查询JSON保存到 `runs/queries/<test_id>/`，命令输出和错误保存到 `runs/logs/<test_id>/`。执行 `search-pubmed --query-file <文件> --retmax 100 --feedback-records 10`；不要添加日期截止。
4. 检查 attempt 的状态、PubMed翻译及反馈覆盖。缺失记录与已返回但无摘要分开记录；前者可用 `recover-feedback --attempt-id <id>` 恢复一次，仍失败则保留错误，不无休止重试。恢复不是新的查询或语义改写。
5. 接受选定 attempt，向尚不存在的 `runs/exports/<test_id>` 执行 `export-retrieval --output-dir <目录>`。不要预建逐题导出目录。保留 result、state_snapshot、integrity_check 和 SHA-256 清单。
6. 将完整live state保存到 results中约定的路径，逐题填写 `runs/results.json` 和观察记录。attempts完整保留，包括失败和恢复；最终查询、accepted_attempt_id、排名须与插件导出逐项一致。兼容字段 screened/fulltext 保持空列表。

真正零结果无法accept；如已按插件规则确认无可用结果，记录 `no_results`、尝试及原因，不伪造接受或导出。基础设施失败记录 `failed`，与零结果区分。

## 封存与后续评分

全部完成后检查16题齐全、PMID未重排、文件齐全且导出清单校验通过；live state导出后状态与导出前snapshot可能不同，不要求整个文件相同。批次另外生成 `runs/integrity_check.json` 以及 `runs/manifest.sha256.json`，用相对路径和SHA-256封存问题、模板填充结果、观察、查询、日志、live state及导出文件；清单不包含自身。未完成题必须显式列出，不能标记整批成功。

本窗口封存后再由原开发窗口使用未修改的BioASQ官方源码评分，保持旧实验相同输入口径（最终原始排名的前10篇）。这里不放gold或评分器，也不自行计算MAP。新增可靠性观察只是运行诊断，不替代BioASQ指标；本次优化不预设MAP必然提高。

