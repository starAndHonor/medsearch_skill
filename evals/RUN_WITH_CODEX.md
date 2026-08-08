# 使用 Codex 启动 BioASQ 评测

本文档记录如何在 Codex 会话中一键启动 medlit-cli 的 BioASQ 13B 全量评测（340 题），
包括运行、评分、产物位置的完整命令序列。所有命令均已在当前仓库验证。

## 前置条件

| 依赖 | 检查命令 | 说明 |
|---|---|---|
| Python 3 | `python3 --version` | 管线与评分脚本 |
| Java | `java -version` | 官方评分 jar（实测 Java 25 可用） |
| Perl 5 | `perl --version` | Perl ROUGE-1.5.5 |
| 官方评分器 | `ls evals/tools/BioASQEvaluation.jar` | 含 commons-cli/gson/SnowBallStemmer 依赖 jar |
| Perl ROUGE | `ls evals/tools/ROUGE-1.5.5/RELEASE-1.5.5/data/WordNet-2.0.exc.db` | WordNet 例外库已构建 |
| 测试集 | `ls data/bioasq_13b_test_merged.json` | 13B 四批合并 golden（340 题） |
| benchmark | `ls evals/bioasq_13b_test_benchmark.json` | convert_bioasq.py 转换产物 |

若 WordNet 例外库缺失，重建命令：

```bash
cd evals/tools/ROUGE-1.5.5/RELEASE-1.5.5/data/WordNet-2.0-Exceptions
perl buildExeptionDB.pl . exc ../WordNet-2.0.exc.db
```

## 方式一：Codex CLI 一键启动（推荐）

```bash
codex exec --full-auto "按 evals/RUN_WITH_CODEX.md 的命令序列执行 BioASQ 13B 全量评测：先 run_bioasq.py 跑 340 题（--resume 断点续跑），完成后依次运行 score_bioasq.py、official_score.py、rouge_score.py，output-dir 均为 evals/results_13b，最后汇报 combined_exact、documents MAP、ROUGE-2/SU4 F1。"
```

## 方式二：交互会话 prompt 模板

在 Codex 交互会话中粘贴：

```text
执行 BioASQ 13B 全量评测（340 题），工作目录 evals/runs_13b，评分输出 evals/results_13b。
步骤（命令见 evals/RUN_WITH_CODEX.md 第三节）：
1. python3 evals/run_bioasq.py（--resume，断点续跑，可随时中断后重跑同命令继续）
2. python3 evals/score_bioasq.py（内置逐题指标）
3. python3 evals/official_score.py（官方 jar，combined_exact）
4. python3 evals/rouge_score.py（Perl ROUGE-2/SU4）
全部完成后汇报：combined_exact、documents_map、yesno macro F1、factoid MRR、list F1、ROUGE-2/SU4 F1。
遇到速率限制不要自行改动参数，说明后继续等待重试。
```

## 命令序列（评测四步）

```bash
# 1. 跑题（340 题，--resume 跳过已完成题，可中断重跑）
python3 evals/run_bioasq.py \
  --benchmark evals/bioasq_13b_test_benchmark.json \
  --work-dir evals/runs_13b \
  --resume

# 2. 内置评分（逐题 P@K/R@K/F1@K + 分题型 token F1，含 bootstrap CI）
python3 evals/score_bioasq.py \
  --benchmark evals/bioasq_13b_test_benchmark.json \
  --work-dir evals/runs_13b \
  --output-dir evals/results_13b

# 3. 官方评分器（Phase A 检索 MAP + Phase B exact 十指标 + combined_exact）
python3 evals/official_score.py \
  --benchmark evals/bioasq_13b_test_benchmark.json \
  --work-dir evals/runs_13b \
  --golden data/bioasq_13b_test_merged.json \
  --phase both \
  --output-dir evals/results_13b

# 4. Perl ROUGE（ideal answer 的 ROUGE-2 / ROUGE-SU4）
python3 evals/rouge_score.py \
  --benchmark evals/bioasq_13b_test_benchmark.json \
  --work-dir evals/runs_13b \
  --golden data/bioasq_13b_test_merged.json \
  --output-dir evals/results_13b
```

### 冒烟（单题验证，全量前必跑）

```bash
python3 evals/run_bioasq.py \
  --benchmark evals/bioasq_13b_test_benchmark.json \
  --work-dir evals/runs_smoke --max-questions 1
# 然后把上面第 2-4 步的 --work-dir 换成 evals/runs_smoke、--output-dir 换成 evals/results_smoke
```

## run_bioasq.py 参数速查

| 参数 | 默认 | 说明 |
|---|---|---|
| `--benchmark` | evals/bioasq_benchmark.json | benchmark JSON |
| `--work-dir` | evals/runs | 每题目录（state.json / report.md / papers/） |
| `--cache-dir` | evals/cache | HTTP 缓存（检索/全文请求落盘，重跑命中） |
| `--max-questions N` | 0 = 全部 | 冒烟用 |
| `--resume` | 关 | 跳过 status ∈ {done, blocked, ready_to_stop} 的题 |
| `--clear-cache` | 关 | 跑前清空 HTTP 缓存 |
| `--pico-dir` | 无 | 预生成 PICO JSON 目录（<question-id>.json） |
| `--retmax` | 20 | search-pubmed 每次检索条数 |

每题执行 13 步管线：init → decompose → plan-terms → validate-mesh → build-query →
search-pubmed → fetch-records → localize-fulltext → parse-fulltext → extract-evidence →
diagnose → report → verify。关键步骤（init/decompose/plan-terms/build-query）失败即中止该题，
其余步骤失败但无 blocker 则继续；每步命令与输出截断（2000 字符）记入 runs.json。

## 产物清单（全程留痕，无需任何 keep 参数）

### 过程层 `evals/runs_13b/`
- `<qid>/state.json` —— PICO、查询阶梯、检索结果、全文、证据、诊断、错误全记录
- `<qid>/report.md` —— 报告（Phase B 答案来源）
- `<qid>/papers/<pmid>/` —— fulltext.xml + parsed_text.md + metadata.json
- `runs.json` —— 每题 status / stop_reason / 13 步命令+退出码+输出

### 评分层 `evals/results_13b/`
- `scores.json` / `scores.csv` —— 内置逐题指标
- `official_submission_phaseA.json` / `official_submission_phaseB.json` —— 提交给官方 jar 的原始 JSON
- `official_output_phaseA.txt` / `official_output_phaseB.txt` —— 官方 jar 原始输出
- `official_scores.json` —— 官方指标 + combined_exact
- `rouge_work/` —— Perl ROUGE 的 SPL 输入 + config.xml
- `rouge_output.txt` —— Perl ROUGE 原始输出
- `rouge_scores.json` —— ROUGE-2 / ROUGE-SU4 的 R/P/F + 95% CI

## 注意事项

- **时长**：冒烟单题约 2 分钟；340 题串行预计数小时，取决于 NCBI 速率与全文获取成功率。
- **中断恢复**：Ctrl+C 后直接重跑第 1 步命令即可（`--resume` 自动跳过完成题）。
- **缓存**：`evals/cache/` 五个分桶持久化全部 HTTP 响应；重跑时检索请求命中缓存，不消耗 NCBI 配额。
- **速率限制**：NCBI E-utilities 无 API key 限 3 req/s。遇限流错误不要调参数，等待后 `--resume` 继续。
- **指标口径**：combined_exact = mean(YN macro F1, factoid MRR, list F1)，与 Task 13B 2025 论文同款；
  ROUGE 对 golden enriched 的多参考（含参赛系统提交）取 average，与官方 Perl 流程一致，
  绝对值低于论文内部评分器（max-over-references）属预期。
