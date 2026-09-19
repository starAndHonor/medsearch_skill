# 0915_2：MedLit + 6 Astra 同16题独立盲测

## 目的与隔离

使用迁移前已安装的 MedLit 插件，与0915 Science PubMed实验作同模型对照。只测检索式构造、搜索、前10篇摘要反馈、必要修改及接受一个查询；不下载全文、不生成答案、不筛选或重排文章。

在全新窗口中**只打开本目录作为工作区**，选择6 Astra。不要读取父工作区、0915或其他日期结果、评估文件、gold、迁移源码、备份或先前分析。允许读取已安装MedLit插件的技能、必需参考和运行文件。这是工作区与盲测约束，不是操作系统级隔离。

固定插件版本：`0.2.0+codex.20260915113715`。预期缓存根目录：
`C:/Users/CGOMI/.codex/plugins/cache/medlit-local/medlit-cli/0.2.0+codex.20260915113715`。
先核实活动插件版本，完整阅读其 skills/medlit-cli/SKILL.md。不得使用仓库中的正在迁移副本。版本不同或插件不可用时停止并记录阻塞，不改用Science、网页检索或手写API。记录模型实际标识；无法确认精确标识时如实说明。

## 条件

- 按questions.json的原文、test_id及顺序测试，16题不得遗漏。
- 每题独立state；retmax=100、relevance排序、feedback-records=10；不设日期截止。
- 模型按MedLit自身技能规则构造检索式、查看前10篇完整可用摘要，并决定修改或接受。不要移植其他技能的查询建议。
- 一个题目最终仅接受一个查询；保留该次原始PMID排名，最多100个，不合并不同尝试。
- 不为目标论文反向优化，不读取答案或评分；不追加题目未要求的语言、开放全文、人类或文章类型限制。
- 零结果与网络/工具失败必须区分，不能伪造、替代或静默跳题。
- 仅调用init、status、search-pubmed及accept-query等检索命令；不进入全文或摘要筛选流程。

## 调用范式

按活动技能说明解析执行根目录，先检查入口 --help。以下root指已安装缓存根，不是当前工作区：

~~~powershell
python "<root>/scripts/medlit_cli.py" --state "runs/states/factoid_01.json" init --question "<题目原文>"
python "<root>/scripts/medlit_cli.py" --state "runs/states/factoid_01.json" search-pubmed --query-file "runs/factoid_01/q1/query.json" --retmax 100 --feedback-records 10
python "<root>/scripts/medlit_cli.py" --state "runs/states/factoid_01.json" accept-query --attempt-id q1
~~~

调用前创建相应目录。query.json按照MedLit技能要求填写attempt_id、exact_query、reasoning及added_terms；每次尝试使用新ID，不覆盖旧文件。保存命令stdout/stderr到对应尝试目录，state中保留完整响应字段。

## 输出与封存

填写runs/results.json的16行。每次attempt至少记录attempt_id、query、reason、status、returned_count、ranked_pmids、state_file、日志路径及observation；returned_count为实际返回数，不是总命中数。总命中数可单独记total_count，并保留Query Translation、警告和错误。

完成时填写accepted_attempt_id、final_query、original_pubmed_ranked_pmids，确保与state.accepted_query_attempt_id、所接受尝试exact_query以及state.final_ranked_pmids完全一致。未执行筛选和全文选择，两个对应数组必须为空，abstract_screening_method保留pubmed仅作兼容字段。

题目status使用pending/completed/blocked。真实零结果可以记录completed且最终列表为空，同时说明未执行accept-query；工具失败必须blocked并填写error。仅当16题真实完成才能将总体run_status设为completed。记录开始/结束时间、模型、插件版本、搜索次数和环境异常；不记录密钥或邮箱值。

runs/observations.md记录各题修改依据与接受理由。完成后生成runs/integrity_check.json以及runs/manifest.sha256.json，哈希封存results.json、state、query文件和原始命令日志，不能在封存后改变结果。不要在本窗口评分。

回到开发窗口后，使用BioASQ官方Java源码评分前10篇；不复用自写MAP公式。开发窗口会进行三方对照，在线检索日期差异仍需明确报告。此目录不包含gold或历史查询。
