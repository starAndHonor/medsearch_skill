使用 $medlit-cli，先完整阅读当前目录README.md，再独立执行questions.json的16题检索盲测。我选择6 Astra，请记录可确认的实际模型标识。

仅允许访问当前实验目录及已安装活动MedLit必要文件；固定插件版本0.2.0+codex.20260915142801。不要访问仓库、旧实验、gold、评分文件、Science技能或迁移副本。插件版本或入口不符则停止并报告，不替换检索实现。

每题独立state，init使用--mode retrieval；retmax100、relevance排序、前10篇标题与完整可用摘要反馈，不设日期截止。遵守插件自身查询迭代规则，只accept一个查询；不合并、不筛选、不重排、不下载全文、不生成答案。反馈缺失可recover-feedback一次并保留日志，不能把无摘要当作未返回记录。

逐题保存查询JSON、stdout/stderr、完整live state及export-retrieval的原始导出。填充runs/results.json和runs/observations.md，排名与导出逐项一致，兼容筛选/全文字段保持空。零结果和基础设施失败如实区分。完成后校验所有导出哈希并按README要求生成批次完整性记录与SHA-256清单；不计算MAP，不接触gold。
