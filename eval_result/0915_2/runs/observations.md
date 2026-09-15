# MedLit 检索实验观察

仅检索实验；未生成问题答案、筛选、重排、下载全文或评分。

全部题目首次检索按 questions.json 原顺序执行。list_03 的 HTTP 500 在其余题目按序完成后恢复重试一次；保留独立失败尝试。

模型精确标识无法从本次运行上下文独立核实；插件版本已核实为 0.2.0+codex.20260915113715。

工作区初始普通写入失败，显式限定本目录的提升执行成功。list_04 的前10个PMID中1条未返回反馈记录；其余全部可用摘要均已阅读。

## factoid_01

Which disease is caused by heterozygous UCHL1 loss-of-function variants?

### q1

```text
UCHL1[Title/Abstract] AND heterozygous[Title/Abstract] AND "loss-of-function"[Title/Abstract]
```

接受：字段和基因、杂合、功能缺失关系保持完整，无警告错误。已读全部5条反馈（4条有摘要，1条勘误无摘要）；首条直接研究指定变异状态，后续同主题家系研究支持检索相关性。末条涉及复合杂合，原排名保留。

总命中：5；实际返回：5；耗时：3.84 秒。

最终状态：completed；接受：q1。

## factoid_02

What proportion of colorectal cancer cases are not assignable to any of the consensus molecular subtype (CMS) groups?

### q1

```text
"colorectal cancer"[Title/Abstract] AND "consensus molecular subtype*"[Title/Abstract]
```

接受：已读前10条完整可用摘要，首条为分类建立研究，第6条分类综述明确涉及未分类组；其他分类异质性研究与题目相关。441总命中不构成单独收窄理由，字段翻译正确，无警告错误。

总命中：441；实际返回：100；耗时：8.11 秒。

最终状态：completed；接受：q1。

## factoid_03

Vector of zika virus.

### q1

```text
"zika virus"[Title/Abstract] AND vector*[Title/Abstract]
```

接受：已读前10条完整摘要。首条及第2、4条提供病毒媒介背景，第5、10条直接研究媒介能力或媒介传播范围。存在病毒机制、诊断等邻近主题，但媒介问题在前列已覆盖；不加入待求媒介名，不因1709总命中单独收窄。翻译准确，无警告错误。

总命中：1709；实际返回：100；耗时：6.84 秒。

最终状态：completed；接受：q1。

## factoid_04

What is the most appropriate systemic treatment for conversion therapy in colorectal cancer with potentially resectable liver metastasis?

### q1

```text
"colorectal cancer"[Title/Abstract] AND "conversion therapy"[Title/Abstract] AND ("liver metastasis"[Title/Abstract] OR "liver metastases"[Title/Abstract])
```

最终接受：已读前10条反馈的全部9条可用摘要，第6条无摘要。初次排序偏向影像、预后和外科，但第3条涉及方案选择，第9条为全身转化方案研究。尝试q2后，systemic限制仍保留大量预后/影像记录，且丢失q1中的直接方案研究，故保留覆盖更充分的q1及其76条原排名，不合并。

总命中：76；实际返回：76；耗时：5.75 秒。

### q2

```text
"colorectal cancer"[Title/Abstract] AND "conversion therapy"[Title/Abstract] AND ("liver metastasis"[Title/Abstract] OR "liver metastases"[Title/Abstract]) AND systemic[Title/Abstract]
```

不接受：已读前10条全部摘要。增加题目已有systemic后27条命中，翻译准确无警告错误；第8、9条为治疗概述，第10条为转化策略研究，但前列仍偏外科、预测和影像，未表现出优于q1的方案覆盖，且第7条主要为肺转移。停止无依据追加限定，选择q1。

总命中：27；实际返回：27；耗时：4.92 秒。

最终状态：completed；接受：q1。

## list_01

What is caused by biallelic CRELD1 variants?

### q1

```text
CRELD1[Title/Abstract] AND biallelic[Title/Abstract]
```

接受：3条全部摘要均涉及双等位CRELD1变异及临床表型，实体和字段正确，无警告错误；罕见实体小结果集无需机械拓宽。

总命中：3；实际返回：3；耗时：4.00 秒。

最终状态：completed；接受：q1。

## list_02

What are the targets of ivonescimab?

### q1

```text
ivonescimab[Title/Abstract]
```

接受：已读前10条全部9条可用摘要，第4条无摘要。第2、5、6、9条明确涉及药物靶点或作用机制；虽有广泛抗体综述，独特药物单实体查询已覆盖问题，无须把答案靶点加入查询。翻译正确无警告错误。

总命中：82；实际返回：82；耗时：4.83 秒。

最终状态：completed；接受：q1。

## list_03

Please list the short half life phosphodiesterase 5 inhibitors.

### q1

```text
("phosphodiesterase 5 inhibitors"[Title/Abstract] OR "PDE5 inhibitors"[Title/Abstract]) AND "half life"[Title/Abstract]
```

阻塞（历史失败，后续恢复）：CLI返回PubMed API error，state.errors记录HTTP 500；没有成功ESearch响应、PMID或摘要，不是零命中，不执行accept-query。先保留错误并顺序处理其他题；后续请求持续成功后，以q2对同一查询进行一次基础设施恢复重试。

总命中：None；实际返回：0；耗时：22.13 秒。

### q2

```text
("phosphodiesterase 5 inhibitors"[Title/Abstract] OR "PDE5 inhibitors"[Title/Abstract]) AND "half life"[Title/Abstract]
```

接受：恢复成功，总命中33，实际返回33。已读前10条全部摘要，第1、7、8条为药理或药物比较，第3条直接区分长短半衰期，足以定位题目关系。其余有长效药或其他适应证记录，但不据此加入待求药名；字段翻译准确，无警告错误。该次为基础设施重试，不是语义修订。

总命中：33；实际返回：33；耗时：4.12 秒。

最终状态：completed；接受：q2。

## list_04

Please list major complications of Clostridium difficile infection.

### q1

```text
("Clostridium difficile"[Title/Abstract] OR "Clostridioides difficile"[Title/Abstract]) AND infection[Title/Abstract] AND complication*[Title/Abstract]
```

接受并披露反馈缺失：ESearch原始前10个PMID中29262007未出现在插件返回的feedback_records内，实际9条，feedback_error为空。已完整阅读其余9条摘要；菌种与并发症关系准确，多条描述感染后严重后果或不良结局，部分为感染本身作为并发症及特殊人群背景。无检索翻译警告错误。原始100条排名全部保留，不补位、不筛选、不重排；缺失不是无摘要记录，两者分别记录。

总命中：964；实际返回：100；耗时：5.41 秒。

最终状态：completed；接受：q1。

## summary_01

Describe RankMHC.

### q1

```text
RankMHC[Title/Abstract]
```

接受：唯一结果直接匹配RankMHC方法名，完整摘要描述方法、输入与评估。字段正确，无警告错误，不因仅1条而拓宽。

总命中：1；实际返回：1；耗时：4.05 秒。

最终状态：completed；接受：q1。

## summary_02

What is the clinical significance of the Eiffel-by-Night Sign?

### q1

```text
"Eiffel-by-Night"[Title/Abstract]
```

接受：6条反馈中4条有摘要，首条及第3条无摘要；全部可用摘要已完整阅读。独特征象名称正确保留，临床相关性、影像意义与随访研究均有覆盖；无警告错误，无需增加待求病名。

总命中：6；实际返回：6；耗时：3.84 秒。

最终状态：completed；接受：q1。

## summary_03

Pathophysiology of irritable bowel syndrome (IBS).

### q1

```text
"irritable bowel syndrome"[Title/Abstract] AND pathophysiology[Title/Abstract]
```

接受：前10条摘要全部完整阅读。第1至6条多数为病理生理总体综述，其他涉及具体病理生理分支，适合题目的概述范围；翻译正确无警告错误，不因1637总命中收窄到猜测机制。

总命中：1637；实际返回：100；耗时：6.52 秒。

最终状态：completed；接受：q1。

## summary_04

What is the role of the receptor tyrosine kinase AXL in malignancy?

### q1

```text
AXL[Title/Abstract] AND (malignan*[Title/Abstract] OR cancer[Title/Abstract])
```

接受：前10条摘要全部完整阅读。前2条为AXL肿瘤作用综述，其他为受体介导肿瘤行为与治疗相关研究，AXL实体未出现不当映射。无警告错误；不追加具体癌种或机制。

总命中：1474；实际返回：100；耗时：4.79 秒。

最终状态：completed；接受：q1。

## yesno_01

Is high WEE1 expression linked to PARP inhibition resistance?

### q1

```text
WEE1[Title/Abstract] AND PARP[Title/Abstract] AND resistan*[Title/Abstract]
```

修订：已读前10条全部9条可用摘要，第6条无摘要。检索翻译正确，无警告错误，但多数为检查点抑制组合、逆转耐药及广泛机制综述，表达水平与耐药关联覆盖不直接。增加题目已有expression形成q2，不加入任何新癌种、分子或药物。

总命中：68；实际返回：68；耗时：4.16 秒。

### q2

```text
WEE1[Title/Abstract] AND PARP[Title/Abstract] AND resistan*[Title/Abstract] AND expression[Title/Abstract]
```

接受：全部7条摘要已完整阅读，第3条直接研究表达水平与PARP抑制耐药的关系，第2条涉及WEE1表达调节和药物抵抗。仍有PARP作为凋亡标记等邻近记录，原排名保留；相比q1更贴近所问关系。翻译准确，无警告错误。

总命中：7；实际返回：7；耗时：4.47 秒。

最终状态：completed；接受：q2。

## yesno_02

Is mucopolysaccharidosis-plus syndrome (MPSPS) an X-linked disease?

### q1

```text
"mucopolysaccharidosis-plus syndrome"[Title/Abstract] OR MPSPS[Title/Abstract]
```

修订：前10条摘要全部完整阅读，前列有病种研究，但第5、7、8、9、10条为其他含MPSPs同形缩写的主题，非所问疾病；无语法或翻译警告仍存在语义歧义。删除缩写分支形成q2。

总命中：32；实际返回：32；耗时：5.18 秒。

### q2

```text
"mucopolysaccharidosis-plus syndrome"[Title/Abstract]
```

接受：10条全部摘要已完整阅读，前列直接讨论该病及其遗传特征，缩写假阳性已排除；第10条为相似综合征的鉴别性研究，保留原排序。字段正确，无警告错误，不将待验证遗传方式或已发现的基因写入查询。

总命中：10；实际返回：10；耗时：4.19 秒。

最终状态：completed；接受：q2。

## yesno_03

Are respiratory measurements correlated with disease severity in Duchenne muscular dystrophy?

### q1

```text
"Duchenne muscular dystrophy"[Title/Abstract] AND (respiratory[Title/Abstract] OR pulmonary[Title/Abstract]) AND severity[Title/Abstract]
```

接受：前10条完整摘要全部阅读，包括第2条较长系统综述。首条直接评估呼吸测试与疾病严重程度，第3、4、6、7、9条涉及指标与临床状态或进展关系；少量心脏、动物及训练背景研究保留，不构造文章筛选结果。翻译正确无警告错误。

总命中：72；实际返回：72；耗时：5.54 秒。

最终状态：completed；接受：q1。

## yesno_04

Does the consensus molecular subtype (CMS) classification for colorectal cancer have any use in routine clinical practice?

### q1

```text
"colorectal cancer"[Title/Abstract] AND "consensus molecular subtype*"[Title/Abstract] AND clinical[Title/Abstract]
```

接受：前10条完整摘要全部阅读。第7条聚焦临床意义，第8条为预测与预后应用研究，第10条讨论临床标志物用途，第5条涉及实际应用限制，覆盖用途及限制；无须把routine作为额外硬性词。翻译正确无警告错误。

总命中：221；实际返回：100；耗时：8.25 秒。

最终状态：completed；接受：q1。

