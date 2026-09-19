使用 $medlit-cli，按照当前工作区README.md完成questions.json的16题独立检索盲测。我将使用6 Astra，请记录可确认的模型标识。

先核实并使用已安装的MedLit版本0.2.0+codex.20260915113715。只读取当前目录与该活动插件必要文件，不读取仓库、迁移副本、Science技能、历史实验、参考答案或评分。

每题独立state；retmax100、relevance排序、前10篇摘要反馈，不设日期截止。遵循MedLit自身查询构造与修改规则，接受一个查询，不合并、不筛选、不重排、不下载全文、不生成答案。

保存完整state、每次query和原始命令日志，填写runs/results.json及runs/observations.md。结束后检查排名与state一致，并生成完整性记录与SHA-256封存清单。不计算MAP。插件不可用时如实报告阻塞，不使用替代检索实现。
