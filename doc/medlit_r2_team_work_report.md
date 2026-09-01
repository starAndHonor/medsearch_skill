# MedLit CLI 本轮升级工作报告

## 一、基本内容

### 1. 先解决“大家运行的不是同一套代码”

升级前，仓库根目录、评测脚本和 Codex Skill 可能调用不同位置的代码。这样会出现一种很麻烦的情况：本地测试已经修好，但组员安装后仍在运行旧版本。

现在真正的程序统一放在 `plugins/medlit-cli/`。仓库里的命令、评测脚本和安装后的 Skill 都指向这里。插件也补齐了 manifest、marketplace、Skill 说明和安装文档，可以作为一个完整的 Codex Plugin 分发给组员。

这样做的直接价值不是提高某一个分数，而是保证以后所有人的测试结果可以互相比较。OpenAI 官方也把 plugin 定义为可安装、可共享的能力包，并建议通过本地 marketplace 安装后，在新对话中测试。[OpenAI Plugin 文档](https://learn.chatgpt.com/docs/build-plugins)

### 2. 修复“检索式没有表达我们真正想搜的内容”

真实漏检案例显示，旧程序会把药名和后面的普通动词拼成一个不存在的短语，也会把 `action`、`identified` 之类没有医学区分度的词塞进检索式。这会让真正重要的疾病名、药物名被噪声淹没。

本轮没有重做一套复杂的医学 NLP，而是修复已经确认的问题：

- 保留药名、疾病名等关键实体，不再和相邻动词错误拼接；
- 清除问句中的普通叙述词；
- 同时生成一条接近自然语言的 PubMed 检索和若干条更严格的实体检索；
- 不再默认添加 humans/English 限制，需要时再手动开启；
- MeSH 暂时作为可选实验功能，而不是默认必经步骤。

这里保留自然语言检索不是拍脑袋决定的。PubMed 官方说明：未加字段标签的词会经过 Automatic Term Mapping（ATM），PubMed可能自动补充同义词、词形和 MeSH；显式字段标签则可能绕过 ATM，多词字段检索还可能被当作短语。因此自然语言检索和精确字段检索各有作用，应该互补而不是二选一。[PubMed Help](https://pubmed.ncbi.nlm.nih.gov/help/)

### 3. 让多条检索式真正共同决定排名

旧程序采用“按顺序拼接”的方式合并结果：第一条检索如果已经返回很多文献，后面的检索即使找到了更相关的论文，也很难进入最终前十。

现在改为 RRF（Reciprocal Rank Fusion）：一篇论文如果在多条检索中都排得靠前，最终排名就会提高。RRF 不是 AI 临时发明的方法，而是信息检索领域已有的排名融合方法，来源于 Cormack、Clarke 和 Büttcher 在 SIGIR 2009 的论文。[RRF 论文](https://doi.org/10.1145/1571941.1572114)

同时，每条检索默认取回的候选数由 20 提高到 100，并继续允许调整。原因很直观：如果相关论文在 PubMed 的第 21–100 名，旧程序会在融合前就把它删掉，后面的排序再好也无法找回。

### 4. 实际效果

我们从 BioASQ 13B 中冻结了 32 道题，共 910 篇 gold 文献。四个测试批次各取 8 题，四种问题类型也各取 8 题，避免结果只反映某一类问题。

| 指标 | 升级前 | 升级后 | 怎么理解 |
|---|---:|---:|---|
| 前10名至少找到1篇相关文献的问题比例 | 40.62% | 46.88% | 更多问题能在首页看到相关论文 |
| 前100名平均召回率 | 13.84% | 27.89% | 平均找回的 gold 比例约翻倍 |
| MAP@10 | 0.0216 | 0.0738 | 相关论文不但找得更多，也更靠前，约为原来的3.4倍 |

这些分数不是让 AI 阅读论文后主观打分，计算过程是确定的：

1. 标准答案使用 BioASQ 官方数据中的 gold PMID；
2. 系统输出也是 PMID；
3. 程序直接比较两个 PMID 列表，计算命中数和排名；
4. before/after 使用同一批题、同一批 gold、相同日期限制和候选深度；
5. 每条 PubMed query、PubMed 的实际翻译结果和返回 PMID 都保存在评测记录中，可以追查。

Recall 和 MAP 不是纯 AI 制定的指标。BioASQ Phase A 官方结果本身就报告 Precision、Recall、F-measure、MAP 和 GMAP。[BioASQ 13B Phase A](https://participants-area.bioasq.org/results/13b/phaseA/) 本项目使用 Recall 衡量“相关文献找回多少”，用 MAP 衡量“相关文献是否排在前面”。“前10名至少命中1篇”是为了方便组内理解增加的诊断指标，不是 BioASQ 官方排名指标。

需要注意的只有一点：这 32 题用于判断本轮修改是否有效，不是完整的 BioASQ 官方复赛成绩。要声称复现官方成绩，还需要使用当年的冻结 PubMed 数据库和官方 evaluator。

## 二、安装、冒烟

### 1. 环境要求

- 已安装支持 Plugin 的 Codex CLI；
- Git；
- Python 3.10 或更高版本；
- 可以访问 PubMed。

本插件运行时只使用 Python 标准库，不需要执行 `pip install -r requirements.txt`。

### 2. 下载代码

PR 合并前，使用本次开发分支：

```powershell
git clone -b 0816_feat https://github.com/starAndHonor/medsearch_skill.git
cd medsearch_skill
```

PR 合并后可以直接 clone 默认分支：

```powershell
git clone https://github.com/starAndHonor/medsearch_skill.git
cd medsearch_skill
```

### 3. 安装 Plugin

在仓库根目录运行：

```powershell
codex plugin marketplace add .
codex plugin add medlit-cli@medlit-local
codex plugin list
```

Windows 如果提示无法执行 `codex.ps1`，把上述命令中的 `codex` 换成 `codex.cmd`，不需要修改系统执行策略。

`codex plugin list` 中出现 `medlit-cli@medlit-local` 后，关闭当前 Codex 对话并新建一个对话，让 Codex 重新加载 Skill。

### 4. 运行最简单的黑盒冒烟测试

在新对话中粘贴：

```text
$medlit-cli 检索下面的问题，只运行到 fetch-records，然后报告执行过的 query 数、融合方式、题录数和最终 status：
In adults with hypertension, does home blood pressure monitoring compared with usual care improve blood pressure control?
```

正常情况下应看到类似流程：

```text
init → decompose → plan-terms → build-query
→ 多次 search-pubmed → RRF → fetch-records → status
```

通过标准是：

- 实际入口来自安装后的 `medlit-cli` plugin；
- 执行了多条 query，而不是只搜一次；
- 最终融合方式是 `reciprocal_rank_fusion`；
- 能抓取到 PubMed 题录；
- 默认路径不会停在 `needs_mesh_validation`；
- fetch 完成后，下一步应进入全文定位阶段。

之前同一问题得到过 27 条候选题录，但 PubMed 是在线数据库，数量以后可能变化，所以不要把“必须等于 27”当作通过条件。

### 5. 运行开发检查

如果组员要修改代码，再运行：

```powershell
python scripts/sync_plugin.py --check
python -B -m unittest discover -s plugins/medlit-cli/tests -v
```

第一条确认所有入口都指向插件源码；第二条运行 13 个单元测试。

## 三、本次升级集中在哪里，下一步做什么

### 本次升级的四个重点

1. **可安装、可共享**：把项目整理成真正的 Codex Plugin，组员安装后运行同一套代码。
2. **把检索式写对**：保护关键医学实体，减少普通问句词和错误短语造成的漏检。
3. **提高召回和融合质量**：增加候选深度，用 RRF 让多条检索共同影响最终排名。
4. **让流程状态可信**：默认不使用 MeSH 时不再被状态机错误阻塞；显式使用 MeSH 时仍按正确顺序验证和构建。

### 下一步的优先方向

下一轮最应该做的是分析新版仍然漏掉了哪些文献，以及前十名中哪些文献看似相关、实际不够贴题。先把问题分成两类：

- **根本没搜到**：继续检查实体识别、同义词、检索式和候选深度；
- **已经搜到但排得太后**：再判断是否需要轻量 reranker 或其他排序特征。

只有真实漏检案例表明 MeSH 或 PICO 表达不足时，才投入更复杂的医学概念建模。不要因为“医学检索通常会用 MeSH”就提前重写整个查询系统。

与此同时，应补做基于 2025 frozen PubMed baseline 的严格 BioASQ 复现。这一工作用于建立可对外引用的历史基线，与日常使用在线 PubMed 的产品验证分开。

等检索端稳定后，再进入全文 PDF 获取、解析和证据抽取。当前最重要的目标仍然是：先把相关论文稳定地找出来，并把真正相关的论文排到前面。
