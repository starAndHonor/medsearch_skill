# MedLit PubMed 检索全过程记录

## 范围与限制

本记录对应 `2026-09-04` 的盲测。输入只使用：

- `eval_result/questions.json`
- `eval_result/README.md`
- MedLit 技能文件及其 PubMed 查询规则

没有读取 `evals/`、`data/`、benchmark、golden、答案或评分文件。没有执行全文下载、全文解析、证据抽取、报告生成或答案生成。

## 初始化与入口确认

首先确认 CLI 入口：

```sh
python plugins/medlit-cli/scripts/medlit_cli.py --help
python plugins/medlit-cli/scripts/medlit_cli.py init --help
python plugins/medlit-cli/scripts/medlit_cli.py search-pubmed --help
```

CLI 返回了 `init`、`search-pubmed`、`accept-query` 等命令。每题使用独立 state 文件，避免不同问题的检索状态混合。

每题初始化命令的实际形式为：

```sh
python plugins/medlit-cli/scripts/medlit_cli.py \
  --state eval_result/runs/states/<test_id>.json \
  init --question "<questions.json 中的 question>"
```

初始化阶段全部成功，state 写入 `eval_result/runs/states/`。

## 首轮查询过程

每题先写入一个 query JSON 到 `eval_result/runs/query_files/<test_id>.json`，然后调用：

```sh
python plugins/medlit-cli/scripts/medlit_cli.py \
  --state eval_result/runs/states/<test_id>.json \
  search-pubmed \
  --query-file eval_result/runs/query_files/<test_id>.json \
  --retmax 100 \
  --feedback-records 10
```

查询文件中的 `reasoning` 是当时的过程语言；CLI 返回中检查了 `count`、PMID 排序、`query_translation`、`warninglist`、`errorlist` 和反馈记录。

| test_id | 首轮完整 query | 首轮返回 |
|---|---|---:|
| factoid_01 | `(UCHL1[Title/Abstract]) AND (heterozygous[Title/Abstract]) AND (loss-of-function[Title/Abstract] OR loss of function[Title/Abstract])` | 5 |
| factoid_02 | `(colorectal cancer[Title/Abstract]) AND (consensus molecular subtype[Title/Abstract] OR CMS[Title/Abstract])` | 434 |
| factoid_03 | `(Zika virus[Title/Abstract]) AND (vector[Title/Abstract])` | 1415 |
| factoid_04 | `(colorectal cancer[Title/Abstract]) AND (liver metastasis[Title/Abstract] OR liver metastases[Title/Abstract]) AND (conversion therapy[Title/Abstract])` | 76 |
| list_01 | `(CRELD1[Title/Abstract]) AND (biallelic[Title/Abstract] OR bi-allelic[Title/Abstract]) AND (variant[Title/Abstract] OR variants[Title/Abstract])` | 3 |
| list_02 | `(ivonescimab[Title/Abstract]) AND (target[Title/Abstract] OR targets[Title/Abstract])` | 18 |
| list_03 | `(phosphodiesterase 5[Title/Abstract] OR PDE5[Title/Abstract]) AND (inhibitor[Title/Abstract] OR inhibitors[Title/Abstract]) AND (short half-life[Title/Abstract] OR short half life[Title/Abstract])` | 6 |
| list_04 | `(Clostridium difficile[Title/Abstract] OR Clostridioides difficile[Title/Abstract]) AND (infection[Title/Abstract]) AND (complication[Title/Abstract] OR complications[Title/Abstract])` | 962 |
| summary_01 | `RankMHC[Title/Abstract]` | 1 |
| summary_02 | `(Eiffel-by-Night Sign[Title/Abstract] OR Eiffel by Night Sign[Title/Abstract])` | 1 |
| summary_03 | `(irritable bowel syndrome[Title/Abstract] OR IBS[Title/Abstract]) AND (pathophysiology[Title/Abstract])` | 1686 |
| summary_04 | `(AXL[Title/Abstract] OR receptor tyrosine kinase AXL[Title/Abstract]) AND (malignancy[Title/Abstract])` | 82 |
| yesno_01 | `(WEE1[Title/Abstract]) AND (high expression[Title/Abstract]) AND (PARP inhibition[Title/Abstract] OR PARP inhibitor[Title/Abstract]) AND (resistance[Title/Abstract])` | 0 |
| yesno_02 | `(mucopolysaccharidosis-plus syndrome[Title/Abstract] OR MPSPS[Title/Abstract]) AND (X-linked[Title/Abstract] OR X linked[Title/Abstract])` | 0 |
| yesno_03 | `(Duchenne muscular dystrophy[Title/Abstract] OR DMD[Title/Abstract]) AND (respiratory measurement[Title/Abstract] OR respiratory measurements[Title/Abstract]) AND (disease severity[Title/Abstract])` | 0 |
| yesno_04 | `(colorectal cancer[Title/Abstract]) AND (consensus molecular subtype[Title/Abstract] OR CMS[Title/Abstract]) AND (routine clinical practice[Title/Abstract] OR clinical practice[Title/Abstract])` | 17 |

首轮网络问题：第一次执行时，沙箱返回 `[BLOCKED] network unavailable during PubMed search`。当时只创建了 state，没有伪造搜索结果。随后在获得网络权限后，用同样的 `search-pubmed` 命令重新执行，16 题均成功访问 PubMed。

## 重试判断与重试命令

三题首轮结果为 0，因此依据 CLI 返回的 `No items found.` 反馈进行可解释重试。没有向 query 中加入已知答案或 gold PMID。

### yesno_01

过程判断：`high expression`、`PARP inhibition/PARP inhibitor` 和 `resistance` 的精确共现条件过窄；保留题干中的 WEE1、PARP、resistance 核心概念。

```sh
python plugins/medlit-cli/scripts/medlit_cli.py \
  --state eval_result/runs/states/yesno_01.json \
  search-pubmed \
  --query-file eval_result/runs/query_files/yesno_01.json \
  --retmax 100 --feedback-records 10
```

重试 query：`(WEE1[Title/Abstract]) AND (PARP[Title/Abstract]) AND (resistance[Title/Abstract])`；返回 59 条。

### yesno_02

过程判断：遗传方式未必出现在题名/摘要中；先去掉必须共现的 `X-linked`，检索综合征本身的记录。

```sh
python plugins/medlit-cli/scripts/medlit_cli.py \
  --state eval_result/runs/states/yesno_02.json \
  search-pubmed \
  --query-file eval_result/runs/query_files/yesno_02.json \
  --retmax 100 --feedback-records 10
```

重试 query：`(mucopolysaccharidosis-plus syndrome[Title/Abstract] OR mucopolysaccharidosis plus syndrome[Title/Abstract] OR MPSPS[Title/Abstract])`；返回 32 条。

### yesno_03

过程判断：`respiratory measurement` 和 `disease severity` 的精确短语组合过窄；改为题干直接概念 `respiratory` 与 `severity`，并加入直接临床结果词 `disease progression`。

```sh
python plugins/medlit-cli/scripts/medlit_cli.py \
  --state eval_result/runs/states/yesno_03.json \
  search-pubmed \
  --query-file eval_result/runs/query_files/yesno_03.json \
  --retmax 100 --feedback-records 10
```

重试 query：`(Duchenne muscular dystrophy[Title/Abstract] OR DMD[Title/Abstract]) AND (respiratory[Title/Abstract]) AND (severity[Title/Abstract] OR disease progression[Title/Abstract])`；返回 147 条，返回 PMID 按相关性截取前 100 条。

## 接受最终 query

首轮结果适合继续作为该题检索结果的 13 题接受 `q001`；三题重试后接受 `q002`。实际命令形式为：

```sh
python plugins/medlit-cli/scripts/medlit_cli.py \
  --state eval_result/runs/states/<test_id>.json \
  accept-query --attempt-id q001
```

三题重试题使用：

```sh
python plugins/medlit-cli/scripts/medlit_cli.py \
  --state eval_result/runs/states/<test_id>.json \
  accept-query --attempt-id q002
```

最终接受情况：`factoid_01` 至 `summary_04`（除三题重试题外）及 `yesno_04` 接受 `q001`；`yesno_01`、`yesno_02`、`yesno_03` 接受 `q002`。全部 16 题接受成功。

## 文件与原始日志

- 查询输入：`eval_result/runs/query_files/`
- 每题 state：`eval_result/runs/states/`
- 初始化、搜索、重试和接受命令输出：`eval_result/runs/logs/`
- 汇总观察：`eval_result/runs/observations.md`

本轮最终只汇总检索过程指标，不作答案质量结论。
