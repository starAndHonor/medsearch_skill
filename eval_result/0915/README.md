# 0915：Science Skills PubMed 独立冒烟测试

## 实验完成后的官方评分

本轮及0904结果已用未修改的 BioASQ 官方 Java 源码重新评分，见 [官方源码评分报告](../../evals/results_0915_official/benchmark.md)。复现入口为 `python evals/run_official_bioasq.py`，仅负责输入转换、编译和调用，不自行实现指标。旧 `evaluation/` 为历史项目口径；MAP结论以官方源码报告为准。评分答案未加入本盲测目录。

## 测试边界

使用已安装的 `pubmed-database`，测试同一组16题的“模型构造检索式 → PubMed 搜索 → 查看摘要 → 必要时修改 → 接受一个检索式”。不调用 MedLit，不做全文下载、答案生成、摘要筛选或重排。本目录不包含参考答案或相关性标签。

在另一个全新窗口打开**本目录本身**作为工作区，不要打开仓库根目录。关闭原测试对话；只阅读本目录及已安装 PubMed 技能和其必要依赖技能。不要阅读其他日期目录、仓库评估文件、历史检索结果或备份。这里是工作区隔离与盲测约束，不是操作系统级访问隔离。

## 固定条件

- 按 questions.json 顺序逐题运行；保持原文和 test_id 不变。
- 搜索 `max_results=100`、`sort_by=relevance`。
- 不设日期截止：原0904记录的 max_date 为空。不同日期的在线数据库结果仍可能变化。
- 可读取每次搜索前10篇的标题和完整摘要，判断是否修改检索式；不改变返回排名。
- 检索式构造与修改遵循该技能自身说明，不额外套用 MedLit 的查询策略。
- 必要修改须有观察依据；接受一个检索式，不合并多个检索结果。
- 不自行追加开放全文、语言、人类、文章类型等问题未要求的过滤条件。
- 不读取或推测参考 PMID，不计算 MAP；评分在结果封存后由原窗口完成。

## 安装与调用

技能已安装在 `C:/Users/CGOMI/.codex/skills/pubmed_database`。先完整阅读其 SKILL.md，并按要求处理 uv、许可证提示和安全凭据检查；不要把密钥写入日志或结果。

调用搜索前阅读 references/search-and-discovery.md；获取摘要前阅读 references/fetch-and-resolve.md。脚本路径必须是已安装目录的绝对路径，不能依赖当前工作区存在脚本。

~~~powershell
uv run "C:/Users/CGOMI/.codex/skills/pubmed_database/scripts/pubmed_api.py" "runs/factoid_01/q1/search.json" search_pubmed "<模型自行构造的检索式>" --max_results 100 --sort_by relevance
uv run "C:/Users/CGOMI/.codex/skills/pubmed_database/scripts/pubmed_api.py" "runs/factoid_01/q1/feedback.json" fetch_article_abstracts "<搜索前10个PMID，用逗号连接>"
~~~

调用前创建相应题目/尝试目录。搜索输出是 PMID 数组，不包含总命中数或 Query Translation；不要编造这些字段。合法空数组表示零返回；错误对象不等于零命中。基础设施失败需如实记录，不能改用 MedLit、网页搜索或自行手写 API 调用代替。

## 输出

填写 runs/results.json，保持16行。每次尝试保存原始 search.json、feedback.json，并在 attempts 中记录：

~~~json
{
  "attempt_id": "q1",
  "query": "实际完整检索式",
  "reason": "首次构造或修改依据",
  "status": "completed",
  "returned_count": 0,
  "ranked_pmids": [],
  "search_file": "runs/factoid_01/q1/search.json",
  "feedback_file": "runs/factoid_01/q1/feedback.json",
  "observation": "基于工具输出的观察"
}
~~~

示例空值不是实际检索结果。完成时将题目 status 设为 completed，填写 accepted_attempt_id、final_query，并将该次搜索的全部 PMID 按原顺序写入 original_pubmed_ranked_pmids。最多100个；不得筛掉“不相关”文章。保留 abstract_screening_method=pubmed，两个筛选/全文字段保持空数组，仅为兼容旧评分器，并不代表执行了筛选或全文选择。

真实零结果可完成并保留空列表；基础设施失败设 blocked，填写 error，不得冒充完成或静默遗漏。总体 run_status 只能在16题全部真实完成后设 completed。填写模型名称、时间、环境问题；不要写凭据值。

在 runs/observations.md 记录过程。封存后回到原窗口检查文件完整性，使用原评分口径计算 MAP@10、Recall@10/20/100、Precision@10、Hit@10，并逐题对照旧结果。在线时点和模型变化须作为限制报告，不能直接归因于技能优劣。
