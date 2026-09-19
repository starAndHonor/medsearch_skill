# 0915_v3 运行观察

## 批次条件

使用已安装 MedLit CLI 0.2.0+codex.20260915142801；入口、版本清单及所用各命令帮助保存在 runs/logs/_preflight 和 runs/plugin_manifest.json。Python 3.12.1。
用户选择模型为 6 Astra；当前会话说明为 Codex / GPT-6，但未暴露可独立核实的精确运行时模型 ID，因此不将用户选择视作已验证的 gpt-6-astra 身份。
每题独立 retrieval state；retmax=100，relevance，feedback-records=10，无日期截止。只接受一个查询，完整保留其原始 PubMed 排名；未执行筛选、重排、全文下载、答案生成或 MAP 评分。
查询 JSON、命令参数、stdout、stderr、完整 state、原始插件导出均在 runs 下。全量 attempts 从插件 live state 复制进 results.json；恢复历史在 feedback_recoveries 中。
初始本地写入遇到 PermissionError，之后在自动审核允许的提升执行环境中完成；未修改插件实现。控制台首次读取中文使用了错误默认编码，之后改为 UTF-8；反馈展示脚本也修正了控制台编码。查询及插件原始日志保留 UTF-8。
runner 的 status 日志使用固定名称，重复查询前的 status 会覆盖该题先前 status 展示；每次 search/init/recovery/accept/export 日志独立完整保存，所有搜索与恢复历史仍完整存在 state 中。
本批次基础设施检索均成功；反馈恢复命令返回成功不等于找回记录，实际恢复均未返回缺失 PMID。按规则停止进一步恢复。

## 逐题记录

### factoid_01

- 模型：同批次，精确运行时 ID 未核实。
- 接受：q1；返回排名条数：17。
- 接受理由：首位记录直接研究题目中的基因、杂合及功能丧失关系；其他反馈包括相关遗传病例，也有背景噪声。字段翻译保留原意，已有合适结果，不再缩窄。

- **q1**：success；总命中 17；耗时 3.781 秒。
  - 查询：`UCHL1[Title/Abstract] AND heterozygous[Title/Abstract]`
  - 查询理由：Use the question's distinctive entities and relationship; omit question scaffolding and avoid guessing the answer. Wildcards cover lexical endings.
  - PubMed 翻译：`"UCHL1"[Title/Abstract] AND "heterozygous"[Title/Abstract]`；warnings={}；errors={}。
  - 反馈：请求 10 条，返回 10 条；缺失 []；已返回无摘要 ["37650884"]。
  - 恢复次数 0；恢复详情 []；最终反馈错误：无。

### factoid_02

- 模型：同批次，精确运行时 ID 未核实。
- 接受：q1；返回排名条数：100。
- 接受理由：首位分类原始研究和分类综述直接讨论分组及未分类样本；后续记录涉及同一分类，查询适合比例问题的检索。

- **q1**：success；总命中 474；耗时 6.719 秒。
  - 查询：`colorectal[Title/Abstract] AND "consensus molecular"[Title/Abstract] AND subtype*[Title/Abstract]`
  - 查询理由：Use the question's distinctive entities and relationship; omit question scaffolding and avoid guessing the answer. Wildcards cover lexical endings.
  - PubMed 翻译：`"colorectal"[Title/Abstract] AND "consensus molecular"[Title/Abstract] AND "subtype*"[Title/Abstract]`；warnings={}；errors={}。
  - 反馈：请求 10 条，返回 10 条；缺失 []；已返回无摘要 []。
  - 恢复次数 0；恢复详情 []；最终反馈错误：无。

### factoid_03

- 模型：同批次，精确运行时 ID 未核实。
- 接受：q1；返回排名条数：100。
- 接受理由：前列综述和媒介能力研究覆盖病毒与传播媒介关系。命中数大但前列相关，无需按数量缩窄。

- **q1**：success；总命中 3376；耗时 4.766 秒。
  - 查询：`zika[Title/Abstract] AND vector*[Title/Abstract]`
  - 查询理由：Use the question's distinctive entities and relationship; omit question scaffolding and avoid guessing the answer. Wildcards cover lexical endings.
  - PubMed 翻译：`"zika"[Title/Abstract] AND "vector*"[Title/Abstract]`；warnings={}；errors={}。
  - 反馈：请求 10 条，返回 10 条；缺失 []；已返回无摘要 []。
  - 恢复次数 0；恢复详情 []；最终反馈错误：无。

### factoid_04

- 模型：同批次，精确运行时 ID 未核实。
- 接受：q4；返回排名条数：98。
- 接受理由：q1偏预后及影像，q2引入conversion的代谢歧义，q3仍偏预测因素；q4聚焦原题的潜在可切除人群，包含治疗综述、方案比较及转化治疗研究。仍有局部治疗与预后记录，保留全部原始排序，不继续添加具体方案。

- **q1**：success；总命中 119；耗时 3.688 秒。
  - 查询：`colorectal[Title/Abstract] AND liver[Title/Abstract] AND "conversion therapy"[Title/Abstract]`
  - 查询理由：Use the question's distinctive entities and relationship; omit question scaffolding and avoid guessing the answer. Wildcards cover lexical endings.
  - PubMed 翻译：`"colorectal"[Title/Abstract] AND "liver"[Title/Abstract] AND "conversion therapy"[Title/Abstract]`；warnings={}；errors={}。
  - 反馈：请求 10 条，返回 10 条；缺失 []；已返回无摘要 ["34629317"]。
  - 恢复次数 0；恢复详情 []；最终反馈错误：无。
- **q2**：success；总命中 142；耗时 5.844 秒。
  - 查询：`colorectal[Title/Abstract] AND liver[Title/Abstract] AND conversion[Title/Abstract] AND systemic[Title/Abstract]`
  - 查询理由：q1 feedback emphasized prognosis and imaging; use the explicit systemic concept and relax the fixed conversion therapy phrase to find systemic treatment discussions.
  - PubMed 翻译：`"colorectal"[Title/Abstract] AND "liver"[Title/Abstract] AND "conversion"[Title/Abstract] AND "systemic"[Title/Abstract]`；warnings={}；errors={}。
  - 反馈：请求 10 条，返回 10 条；缺失 []；已返回无摘要 []。
  - 恢复次数 0；恢复详情 []；最终反馈错误：无。
- **q3**：success；总命中 38；耗时 3.922 秒。
  - 查询：`colorectal[Title/Abstract] AND liver[Title/Abstract] AND "conversion therapy"[Title/Abstract] AND systemic[Title/Abstract]`
  - 查询理由：q2's unphrased conversion retrieved metabolic prodrug conversion as its top hit. Restore the original conversion therapy phrase while retaining systemic to focus the requested therapeutic setting.
  - PubMed 翻译：`"colorectal"[Title/Abstract] AND "liver"[Title/Abstract] AND "conversion therapy"[Title/Abstract] AND "systemic"[Title/Abstract]`；warnings={}；errors={}。
  - 反馈：请求 10 条，返回 10 条；缺失 []；已返回无摘要 []。
  - 恢复次数 0；恢复详情 []；最终反馈错误：无。
- **q4**：success；总命中 98；耗时 3.938 秒。
  - 查询：`colorectal[Title/Abstract] AND liver[Title/Abstract] AND "potentially resectable"[Title/Abstract] AND (treatment[Title/Abstract] OR therapy[Title/Abstract])`
  - 查询理由：q3 still emphasizes conversion prediction rather than treatment choice. Replace the conversion/systemic requirements with the question's explicit potentially resectable patient setting, retaining treatment or therapy; no regimen or answer term is added.
  - PubMed 翻译：`"colorectal"[Title/Abstract] AND "liver"[Title/Abstract] AND "potentially resectable"[Title/Abstract] AND ("treatment"[Title/Abstract] OR "therapy"[Title/Abstract])`；warnings={}；errors={}。
  - 反馈：请求 10 条，返回 10 条；缺失 []；已返回无摘要 []。
  - 恢复次数 0；恢复详情 []；最终反馈错误：无。

### list_01

- 模型：同批次，精确运行时 ID 未核实。
- 接受：q1；返回排名条数：3。
- 接受理由：全部3条反馈均针对该基因的双等位变异及其表型关系；稀有实体的少量命中适合本题。

- **q1**：success；总命中 3；耗时 4.5 秒。
  - 查询：`CRELD1[Title/Abstract] AND biallelic[Title/Abstract]`
  - 查询理由：Use the question's distinctive entities and relationship; omit question scaffolding and avoid guessing the answer. Wildcards cover lexical endings.
  - PubMed 翻译：`"CRELD1"[Title/Abstract] AND "biallelic"[Title/Abstract]`；warnings={}；errors={}。
  - 反馈：请求 3 条，返回 3 条；缺失 []；已返回无摘要 []。
  - 恢复次数 0；恢复详情 []；最终反馈错误：无。

### list_02

- 模型：同批次，精确运行时 ID 未核实。
- 接受：q1；返回排名条数：82。
- 接受理由：药物开发概述、机制研究及试验反馈中直接描述靶点；独特药名已足够，未添加猜测靶点。

- **q1**：success；总命中 82；耗时 4.813 秒。
  - 查询：`ivonescimab[Title/Abstract]`
  - 查询理由：Use the question's distinctive entities and relationship; omit question scaffolding and avoid guessing the answer. Wildcards cover lexical endings.
  - PubMed 翻译：`"ivonescimab"[Title/Abstract]`；warnings={}；errors={}。
  - 反馈：请求 10 条，返回 10 条；缺失 []；已返回无摘要 []。
  - 恢复次数 0；恢复详情 []；最终反馈错误：无。

### list_03

- 模型：同批次，精确运行时 ID 未核实。
- 接受：q2；返回排名条数：13。
- 接受理由：q1混入其他物质半衰期及长效制剂，q2的前列记录直接涉及短半衰期药物与长短效比较。q2恢复一次后仍缺PMID 20641200，基于其余9条完整可用反馈接受查询；不删除缺失PMID、不补位或重复恢复。

- **q1**：success；总命中 40；耗时 4.0 秒。
  - 查询：`"phosphodiesterase 5"[Title/Abstract] AND inhibitor*[Title/Abstract] AND "half life"[Title/Abstract]`
  - 查询理由：Use the question's distinctive entities and relationship; omit question scaffolding and avoid guessing the answer. Wildcards cover lexical endings.
  - PubMed 翻译：`"phosphodiesterase 5"[Title/Abstract] AND "inhibitor*"[Title/Abstract] AND "half life"[Title/Abstract]`；warnings={}；errors={}。
  - 反馈：请求 10 条，返回 9 条；缺失 ["20641200"]；已返回无摘要 []。
  - 恢复次数 1；恢复详情 [{"requested_pmids": ["20641200"], "started_at": "2026-09-15T14:34:58+00:00", "status": "success", "finished_at": "2026-09-15T14:35:00+00:00", "returned_pmids": []}]；最终反馈错误：Feedback records still missing。
- **q2**：success；总命中 13；耗时 3.359 秒。
  - 查询：`("phosphodiesterase 5"[Title/Abstract] OR PDE5[Title/Abstract]) AND inhibitor*[Title/Abstract] AND "half life"[Title/Abstract] AND short[Title/Abstract]`
  - 查询理由：q1 returned many studies of other drugs or long half-life; require the requested short property and include the direct class abbreviation visible in feedback.
  - PubMed 翻译：`("phosphodiesterase 5"[Title/Abstract] OR "PDE5"[Title/Abstract]) AND "inhibitor*"[Title/Abstract] AND "half life"[Title/Abstract] AND "short"[Title/Abstract]`；warnings={}；errors={}。
  - 反馈：请求 10 条，返回 9 条；缺失 ["20641200"]；已返回无摘要 []。
  - 恢复次数 1；恢复详情 [{"requested_pmids": ["20641200"], "started_at": "2026-09-15T14:37:23+00:00", "status": "success", "finished_at": "2026-09-15T14:37:25+00:00", "returned_pmids": []}]；最终反馈错误：Feedback records still missing。

### list_04

- 模型：同批次，精确运行时 ID 未核实。
- 接受：q2；返回排名条数：100。
- 接受理由：q1混入其他疾病并发CDI的记录；q2以标题限定疾病并加入同一菌种新名称，前列以CDI临床综述及并发症研究为主。q1恢复后仍缺一条；q2反馈完整。

- **q1**：success；总命中 1008；耗时 3.609 秒。
  - 查询：`"Clostridium difficile"[Title/Abstract] AND complication*[Title/Abstract]`
  - 查询理由：Use the question's distinctive entities and relationship; omit question scaffolding and avoid guessing the answer. Wildcards cover lexical endings.
  - PubMed 翻译：`"Clostridium difficile"[Title/Abstract] AND "complication*"[Title/Abstract]`；warnings={}；errors={}。
  - 反馈：请求 10 条，返回 9 条；缺失 ["29262007"]；已返回无摘要 []。
  - 恢复次数 1；恢复详情 [{"requested_pmids": ["29262007"], "started_at": "2026-09-15T14:35:00+00:00", "status": "success", "finished_at": "2026-09-15T14:35:03+00:00", "returned_pmids": []}]；最终反馈错误：Feedback records still missing。
- **q2**：success；总命中 679；耗时 4.64 秒。
  - 查询：`("Clostridium difficile"[Title] OR "Clostridioides difficile"[Title]) AND complication*[Title/Abstract]`
  - 查询理由：q1 frequently describes CDI as a complication of another condition; restrict the infection entity to title to focus the disease under study, including its direct renamed form.
  - PubMed 翻译：`("Clostridium difficile"[Title] OR "Clostridioides difficile"[Title]) AND "complication*"[Title/Abstract]`；warnings={}；errors={}。
  - 反馈：请求 10 条，返回 10 条；缺失 []；已返回无摘要 []。
  - 恢复次数 0；恢复详情 []；最终反馈错误：无。

### summary_01

- 模型：同批次，精确运行时 ID 未核实。
- 接受：q1；返回排名条数：1。
- 接受理由：唯一命中标题和摘要明确描述指定方法的建模和评价，翻译正确，不因结果少而扩大。

- **q1**：success；总命中 1；耗时 3.562 秒。
  - 查询：`RankMHC[Title/Abstract]`
  - 查询理由：Use the question's distinctive entities and relationship; omit question scaffolding and avoid guessing the answer. Wildcards cover lexical endings.
  - PubMed 翻译：`"RankMHC"[Title/Abstract]`；warnings={}；errors={}。
  - 反馈：请求 1 条，返回 1 条；缺失 []；已返回无摘要 []。
  - 恢复次数 0；恢复详情 []；最终反馈错误：无。

### summary_02

- 模型：同批次，精确运行时 ID 未核实。
- 接受：q1；返回排名条数：6。
- 接受理由：六条记录均围绕指定征象，包含临床与影像关联研究；两条已返回但无摘要，其余摘要可用，不应恢复或下载全文补足。

- **q1**：success；总命中 6；耗时 3.125 秒。
  - 查询：`"Eiffel-by-Night"[Title/Abstract]`
  - 查询理由：Use the question's distinctive entities and relationship; omit question scaffolding and avoid guessing the answer. Wildcards cover lexical endings.
  - PubMed 翻译：`"Eiffel-by-Night"[Title/Abstract]`；warnings={}；errors={}。
  - 反馈：请求 6 条，返回 6 条；缺失 []；已返回无摘要 ["39555834", "38519435"]。
  - 恢复次数 0；恢复详情 []；最终反馈错误：无。

### summary_03

- 模型：同批次，精确运行时 ID 未核实。
- 接受：q1；返回排名条数：100。
- 接受理由：前列多篇综述直接讨论所要求疾病的病理生理，另有相关机制研究；无需以命中量为由缩窄。

- **q1**：success；总命中 1637；耗时 4.578 秒。
  - 查询：`"irritable bowel syndrome"[Title/Abstract] AND pathophysiology[Title/Abstract]`
  - 查询理由：Use the question's distinctive entities and relationship; omit question scaffolding and avoid guessing the answer. Wildcards cover lexical endings.
  - PubMed 翻译：`"irritable bowel syndrome"[Title/Abstract] AND "pathophysiology"[Title/Abstract]`；warnings={}；errors={}。
  - 反馈：请求 10 条，返回 10 条；缺失 []；已返回无摘要 []。
  - 恢复次数 0；恢复详情 []；最终反馈错误：无。

### summary_04

- 模型：同批次，精确运行时 ID 未核实。
- 接受：q1；返回排名条数：100。
- 接受理由：前列综合综述和机制研究覆盖AXL与恶性肿瘤关系；直接同义词cancer已审计。

- **q1**：success；总命中 1530；耗时 5.219 秒。
  - 查询：`AXL[Title/Abstract] AND (malignan*[Title/Abstract] OR cancer*[Title/Abstract])`
  - 查询理由：Use the question's distinctive entities and relationship; omit question scaffolding and avoid guessing the answer. Wildcards cover lexical endings.
  - PubMed 翻译：`"AXL"[Title/Abstract] AND ("malignan*"[Title/Abstract] OR "cancer*"[Title/Abstract])`；warnings={}；errors={}。
  - 反馈：请求 10 条，返回 10 条；缺失 []；已返回无摘要 []。
  - 恢复次数 0；恢复详情 []；最终反馈错误：无。

### yesno_01

- 模型：同批次，精确运行时 ID 未核实。
- 接受：q2；返回排名条数：7。
- 接受理由：q1偏抑制剂联用和一般耐药，q2加入原题expression后前列出现明确研究表达与PARP抑制耐药关系的记录，保留全部7条排名。

- **q1**：success；总命中 68；耗时 4.672 秒。
  - 查询：`WEE1[Title/Abstract] AND PARP[Title/Abstract] AND resistan*[Title/Abstract]`
  - 查询理由：Use the question's distinctive entities and relationship; omit question scaffolding and avoid guessing the answer. Wildcards cover lexical endings.
  - PubMed 翻译：`"WEE1"[Title/Abstract] AND "PARP"[Title/Abstract] AND "resistan*"[Title/Abstract]`；warnings={}；errors={}。
  - 反馈：请求 10 条，返回 10 条；缺失 []；已返回无摘要 ["38318945"]。
  - 恢复次数 0；恢复详情 []；最终反馈错误：无。
- **q2**：success；总命中 7；耗时 4.172 秒。
  - 查询：`WEE1[Title/Abstract] AND PARP[Title/Abstract] AND resistan*[Title/Abstract] AND expression[Title/Abstract]`
  - 查询理由：q1 emphasizes combination inhibition and general replication stress, while the question asks about expression. Require the visible expression term without imposing direction of association.
  - PubMed 翻译：`"WEE1"[Title/Abstract] AND "PARP"[Title/Abstract] AND "resistan*"[Title/Abstract] AND "expression"[Title/Abstract]`；warnings={}；errors={}。
  - 反馈：请求 7 条，返回 7 条；缺失 []；已返回无摘要 []。
  - 恢复次数 0；恢复详情 []；最终反馈错误：无。

### yesno_02

- 模型：同批次，精确运行时 ID 未核实。
- 接受：q2；返回排名条数：11。
- 接受理由：q1缩写映射到多种无关主题；q2删除歧义缩写后前10条均研究指定综合征，多篇说明遗传方式。未以待判断的遗传方式限定查询。

- **q1**：success；总命中 33；耗时 5.391 秒。
  - 查询：`("mucopolysaccharidosis-plus"[Title/Abstract] OR MPSPS[Title/Abstract])`
  - 查询理由：Use the question's distinctive entities and relationship; omit question scaffolding and avoid guessing the answer. Wildcards cover lexical endings.
  - PubMed 翻译：`"mucopolysaccharidosis-plus"[Title/Abstract] OR "MPSPS"[Title/Abstract]`；warnings={}；errors={}。
  - 反馈：请求 10 条，返回 10 条；缺失 []；已返回无摘要 []。
  - 恢复次数 0；恢复详情 []；最终反馈错误：无。
- **q2**：success；总命中 11；耗时 4.75 秒。
  - 查询：`"mucopolysaccharidosis-plus"[Title/Abstract]`
  - 查询理由：q1's MPSPS abbreviation retrieves unrelated scaffold particles, polystyrene and sports studies. Remove the ambiguous acronym and retain the full named syndrome without assuming inheritance.
  - PubMed 翻译：`"mucopolysaccharidosis-plus"[Title/Abstract]`；warnings={}；errors={}。
  - 反馈：请求 10 条，返回 10 条；缺失 []；已返回无摘要 []。
  - 恢复次数 0；恢复详情 []；最终反馈错误：无。

### yesno_03

- 模型：同批次，精确运行时 ID 未核实。
- 接受：q1；返回排名条数：60。
- 接受理由：前列肺功能研究直接评估呼吸测量与疾病严重程度或进展的关联，反馈满足实际关系，无需修改。

- **q1**：success；总命中 60；耗时 4.39 秒。
  - 查询：`"Duchenne muscular dystrophy"[Title/Abstract] AND respiratory[Title/Abstract] AND severity[Title/Abstract]`
  - 查询理由：Use the question's distinctive entities and relationship; omit question scaffolding and avoid guessing the answer. Wildcards cover lexical endings.
  - PubMed 翻译：`"Duchenne muscular dystrophy"[Title/Abstract] AND "respiratory"[Title/Abstract] AND "severity"[Title/Abstract]`；warnings={}；errors={}。
  - 反馈：请求 10 条，返回 10 条；缺失 []；已返回无摘要 []。
  - 恢复次数 0；恢复详情 []；最终反馈错误：无。

### yesno_04

- 模型：同批次，精确运行时 ID 未核实。
- 接受：q1；返回排名条数：100。
- 接受理由：分类研究、临床意义综述及应用限制/临床关联研究覆盖常规应用问题的证据范围，未加入预设结论。

- **q1**：success；总命中 234；耗时 6.328 秒。
  - 查询：`colorectal[Title/Abstract] AND "consensus molecular"[Title/Abstract] AND subtype*[Title/Abstract] AND clinical[Title/Abstract]`
  - 查询理由：Use the question's distinctive entities and relationship; omit question scaffolding and avoid guessing the answer. Wildcards cover lexical endings.
  - PubMed 翻译：`"colorectal"[Title/Abstract] AND "consensus molecular"[Title/Abstract] AND "subtype*"[Title/Abstract] AND "clinical"[Title/Abstract]`；warnings={}；errors={}。
  - 反馈：请求 10 条，返回 10 条；缺失 []；已返回无摘要 []。
  - 恢复次数 0；恢复详情 []；最终反馈错误：无。

## 封存结果

16/16 题已接受并导出；23 次查询，3 次反馈恢复。
最终接受的 list_03/q2 仍缺 PMID 20641200；其余最终查询反馈记录齐全。无摘要记录单独标记。
导出与排名完整性：通过。未完成题：无。
批次状态为 completed_with_warnings；这是检索与审计封存状态，不表示反馈全部可用或检索效果优于旧实验。未计算 MAP。
