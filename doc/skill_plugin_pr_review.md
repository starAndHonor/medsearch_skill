# 【已归档】MedLit Skill / Plugin 迁移前规范性 PR Review

> 本文件记录的是插件迁移前的基线问题，结论已经过时。  
> 迁移完成后的逐项复审见 [skill_plugin_migration_review.md](skill_plugin_migration_review.md)。

> 审查日期：2026-08-09  
> 审查分支：`lhq_0809_fix`  
> 审查基准：`origin/main`  
> 当前提交：`929b8ef`（`规范化 MedLit Codex 技能结构`）

## 1. 先给结论

这次需要把两个容易混淆的概念分开看：

| 审查对象 | 当前结论 | 含义 |
|---|---|---|
| 仓库级 Skill：`.agents/skills/medlit-cli/` | **基本符合，可以被 Codex 在本仓库中发现和调用** | 打开这个仓库后，Codex 可以根据 `SKILL.md` 使用工作流 |
| 当前 PR 是否已经构成可安装 Plugin | **不符合，缺少 Plugin 包装和安装入口** | 仅有 Skill 文件，还不能让其他人从 Codex 的“插件”页面安装 |
| 本机个人 Plugin | **结构基本符合，也曾通过本地校验，但不在本 PR 中** | 它位于用户目录，其他人拉取本 PR 后不会得到它 |
| Skill 描述与真实代码是否一致 | **大部分一致，存在少数需要修正或说明的问题** | 命令顺序和退出条件有代码依据，但 PDF 状态标记等细节有风险 |

因此，如果这个 PR 的目标只是“让 Skill 在当前仓库内可用”，目前已经接近完成；如果目标是“让 Skill 出现在 Codex 插件目录中，并可被安装”，当前 PR 还不能合并为完成状态。

## 2. 新手先理解这几个词

- **Skill（技能）**：一份给智能体看的操作说明。它告诉 Codex 何时使用某个工作流、按照什么顺序执行、遇到什么情况停止。
- **Plugin（插件）**：一个可以安装的完整包。它可以装入一个或多个 Skill，也可以带上程序代码、MCP 服务等内容。
- **Manifest（清单文件）**：插件的“身份证”，文件名是 `.codex-plugin/plugin.json`，记录插件名称、版本、说明以及 Skill 在哪里。
- **Marketplace（插件目录清单）**：告诉 Codex“有哪些插件可以安装、插件位于哪里”的 JSON 文件。个人目录和仓库都可以有自己的清单。
- **MCP（模型上下文协议）**：让 Codex 调用外部服务或工具的一种连接方式。当前 MedLit 工作流直接运行随包附带的 Python 代码，因此并不因为没有 MCP 就不合格。
- **仓库级 Skill**：Skill 放在项目的 `.agents/skills/` 中，仅在 Codex 处理这个仓库时被发现。
- **个人 Plugin**：安装在当前用户环境中的插件，可在其他对话或仓库中使用，但不会自动随 Git PR 分享给队友。

完整的“插件安装”关系可以简化为：

```text
SKILL.md（工作说明）
        ↓ 放进插件目录
.codex-plugin/plugin.json（插件身份证）
        ↓ 登记插件来源
.agents/plugins/marketplace.json（插件目录清单）
        ↓ 在 Codex 中安装并重新打开会话
插件中的 Skill 才能从插件入口使用
```

## 3. 本次采用的官方文档

本报告只把 OpenAI 官方页面作为规范依据：

1. [Build skills（构建 Skill）](https://developers.openai.com/codex/skills)
2. [Add skills to your plugin（把 Skill 加入 Plugin）](https://developers.openai.com/plugins/build/skills)
3. [Package and publish a plugin（打包和发布 Plugin）](https://developers.openai.com/plugins/build/plugins)

官方文档明确区分了两条路径：在仓库中编写和使用 Skill，以及为了分发而把 Skill 包装成 Plugin。Skill 可以独立工作；需要安装、分享和出现在插件目录中时，才需要 Plugin 包装。[官方说明：Build skills](https://developers.openai.com/codex/skills)

## 4. 当前 PR 实际包含什么

相对 `origin/main`，当前提交只包含以下 Skill 相关变化：

```text
.agents/
└── skills/
    └── medlit-cli/
        ├── SKILL.md
        └── agents/
            └── openai.yaml

删除：仓库根目录旧的 SKILL.md
```

当前 PR **没有**以下插件文件：

```text
.codex-plugin/plugin.json
.agents/plugins/marketplace.json
plugins/medlit-cli/...
```

本机上虽然另有一个个人插件，但它位于：

```text
C:\Users\CGOMI\plugins\medlit-cli
C:\Users\CGOMI\.agents\plugins\marketplace.json
```

这些文件不在 Git 仓库和 PR 中。因此，不能把“本机已经安装成功”等同于“这个 PR 已经提供了可安装插件”。

## 5. Skill 规范逐条核对

状态说明：

- ✅ 符合：与官方要求和当前代码一致。
- ⚠️ 部分符合：可以工作，但可移植性、表述或测试仍有不足。
- ❌ 不符合：若要达到所声明的目标，当前缺少必要内容。
- ℹ️ 可选：官方允许提供，但不是硬性要求。

### 5.1 文件位置与基本结构

| 官方要求 | 当前实现 | 状态 | 分析 |
|---|---|---:|---|
| 仓库级 Skill 放在 `.agents/skills/<skill-name>/` | `.agents/skills/medlit-cli/` | ✅ | 路径正确。Codex 会从当前目录向仓库根目录寻找 `.agents/skills`。[官方说明](https://developers.openai.com/codex/skills) |
| Skill 目录必须有 `SKILL.md` | 已存在 | ✅ | 这是 Skill 的必需入口文件。 |
| 文件夹名称应与 Skill 名称一致 | 文件夹和 `name` 都是 `medlit-cli` | ✅ | 名称一致，便于发现和避免混淆。 |
| 可以有 `scripts/`、`references/`、`assets/`、`agents/openai.yaml` | 当前有 `agents/openai.yaml`；功能代码位于仓库上级的 `scripts/` 和 `medlit/` | ⚠️ | 对“仓库级 Skill”是可行的；但只复制 Skill 文件夹时，代码不会随它一起走，因此不是独立可搬运的包。[官方说明](https://developers.openai.com/codex/skills) |

### 5.2 `SKILL.md` 开头的声明

当前开头为：

```yaml
---
name: medlit-cli
description: "..."
---
```

| 官方要求 | 当前实现 | 状态 | 分析 |
|---|---|---:|---|
| 手工编写 Skill 时必须声明 `name` | 已声明 `medlit-cli` | ✅ | 符合。 |
| 必须声明 `description` | 已声明，并写明使用场景和不支持的能力 | ✅ | 描述决定 Codex 何时选择该 Skill。当前描述没有把未实现的 PDF 提取和医学正确性验证写成已实现能力。 |
| `description` 应清楚说明何时使用 | 仅在用户明确调用 `$medlit-cli` 或要求仓库工作流时使用 | ✅ | 触发边界清楚。 |
| `compatibility`、`license`、`metadata`、`allowed-tools` 是否必填 | 当前没有 | ✅ | OpenAI 当前的手工 Skill 文档只要求 `name` 和 `description`。这些字段不是当前官方文档中的必填项，不应为了“看起来完整”而虚构。[官方说明](https://developers.openai.com/codex/skills) |

补充说明：Plugin 的 `plugin.json` 可以填写作者、主页、仓库和许可证等信息，但这些属于 **Plugin 清单**，不等于必须塞进 `SKILL.md`。没有真实许可证时，不应猜测或编造。

### 5.3 Skill 正文是否像一个真实工作流

官方建议正文写清楚预期输入、执行步骤、输出、不能自行推断的事实，以及何时询问、停止或拒绝；较长材料可以拆到引用文件中。[官方说明：Add skills to your plugin](https://developers.openai.com/plugins/build/skills)

| 官方建议 | 当前实现 | 状态 | 分析 |
|---|---|---:|---|
| 写明预期输入 | 写明问题、PICO 文件、状态 JSON、运行根目录等 | ✅ | 用户和 Codex 能知道开始前需要什么。 |
| 按顺序写步骤 | 从 `init`、`decompose` 到 `report`、`verify`、`status` 共 13 步 | ✅ | 顺序与 `medlit/cli.py` 中的命令一致。 |
| 写明输出 | 写明状态文件、报告文件和命令输出 | ✅ | 不会把临时输出误当成最终研究结论。 |
| 写明停止条件 | 写明输入阻塞、搜索/抓取失败、预算耗尽和诊断终止 | ✅ | 退出码和终止条件可以在真实代码中找到。 |
| 不把未知事实当成已完成能力 | 明确 PDF 当前只是占位记录；`verify` 只检查证据完整性 | ✅ | 这是重要的真实性边界。 |
| 提供输入/输出示例 | 已有命令示例和预期结果 | ✅ | 对新用户友好。 |
| 提供常见边缘情况 | 已覆盖无结果、网络失败、缺少邮箱、PDF 占位等 | ✅ | 与实际代码情况大体一致。 |
| 保持正文精简，长材料拆分 | 约 190 行，未超过常见建议长度 | ✅ | 长度可以接受；PDF 限制在多处重复，仍可精简。 |
| 提供“不应该触发”的测试例子 | 描述中有不支持边界，但正文没有专门的负面触发示例 | ⚠️ | 官方建议同时测试直接触发、间接触发、不完整请求和不应触发的请求。建议补一小组测试用例，但不要把测试产物放进发布包。[官方测试建议](https://developers.openai.com/plugins/build/skills) |

### 5.4 `agents/openai.yaml`

该文件控制 Skill 在界面中的展示和是否允许自动触发。它是可选文件，不是 Skill 能否工作的必要条件。[官方说明](https://developers.openai.com/codex/skills)

| 检查项 | 当前实现 | 状态 | 分析 |
|---|---|---:|---|
| `display_name` | `MedLit CLI` | ✅ | 简短清楚。 |
| `short_description` | `Run stateful biomedical literature workflows` | ✅ | 与实际功能一致。 |
| `default_prompt` | 要求使用 `$medlit-cli` 执行 `repository workflow` | ⚠️ | 放在仓库级 Skill 中合理；复制到个人 Plugin 后，“repository”会显得过时。建议改成 `bundled MedLit workflow`（随包附带的工作流）。 |
| `allow_implicit_invocation` | `false` | ✅ | 与 `SKILL.md` 中“明确调用”规则一致，避免它因为普通医学问题被误触发。 |
| MCP 依赖 | 未声明 | ✅ | Skill 可以不依赖 MCP。当前工作流调用随包 Python 程序，不需要为了形式而添加不存在的 MCP 服务。[官方说明](https://developers.openai.com/plugins/build/skills) |

## 6. Skill 是否忠实描述了真实代码

本节不只看文档格式，也检查 Skill 写的命令能否在代码中找到依据。

### 6.1 执行入口

| Skill 中的说法 | 代码依据 | 结论 |
|---|---|---|
| 从 `scripts/medlit_cli.py` 启动 | `scripts/medlit_cli.py` 导入并调用 `medlit.cli.main` | ✅ 真实入口 |
| 向上查找同时含有 `scripts/medlit_cli.py` 和 `medlit/cli.py` 的目录 | 两个文件目前确实位于仓库根目录对应位置 | ✅ 不依赖写死的绝对路径 |
| 使用 `--state` 指定 JSON 状态文件 | `medlit/cli.py` 定义全局 `--state` 参数 | ✅ 与代码一致 |

### 6.2 命令阶段

Skill 中列出的以下命令均在 `medlit/cli.py` 中注册：

```text
init
decompose
search
fetch
localize
parse
index
retrieve
diagnose
repair
report
verify
status
```

因此，Research workflow（研究工作流）的主干不是猜测，而是按真实命令接口编写的。

### 6.3 退出条件与预算

| Skill 中的规则 | 代码依据 | 状态 |
|---|---|---:|
| `decompose` 缺少必要输入时停止 | `medlit/cli.py` 会设置阻塞并以退出码 8 结束 | ✅ |
| 搜索和抓取存在不同失败退出码 | `search`、`fetch` 处理网络、上游和输入错误 | ✅ |
| `diagnose` 可以决定终止 | `medlit/evolution/diagnostics.py` 有查询数、全文尝试数和终止判断 | ✅ |
| 默认预算有限 | `medlit/state/store.py` 设置查询、记录和尝试次数默认值 | ✅ |

### 6.4 PDF 与验证能力

这里有一个需要特别注意的代码问题：

- `medlit/fulltext/parser.py` 对 PDF 目前只生成 `pdf_placeholder`（PDF 占位记录），并没有提取 PDF 正文。
- Skill 已经如实提醒这一点，所以 **Skill 文案没有夸大能力**。
- 但是，同一段解析代码把这个占位结果的 `source_granularity` 标成了 `fulltext`（全文）。这可能让后续流程误以为已经取得全文证据。

结论：**文档表述合格，但底层状态标记存在中高风险问题。** 建议在功能修复前，把 PDF 占位结果标成明确的 `placeholder`、`metadata_only` 或其他不会被当作全文的值，并让后续检索拒绝把占位内容当成全文证据。

`verify` 的真实实现位于 `medlit/report.py`，它检查报告和证据引用的完整性，不负责判断医学结论是否正确。Skill 已明确说明这一限制，符合“有什么写什么”的原则。

### 6.5 网络与全文来源

`medlit/fulltext/localizer.py` 中可以看到 Europe PMC、Unpaywall、全文 XML 和 PDF 定位逻辑；Unpaywall 还需要邮箱。Skill 对开放获取、网络失败和缺少邮箱的说明有代码依据。

## 7. Plugin 规范逐条核对

这是当前 PR 最主要的缺口。官方规定，一个 Plugin 至少需要插件目录和 `.codex-plugin/plugin.json`；Skill 应位于插件的 `skills/<name>/SKILL.md` 下。[官方说明：Package and publish a plugin](https://developers.openai.com/plugins/build/plugins)

### 7.1 插件目录结构

| 官方要求 | 当前 PR | 状态 | 原因 |
|---|---|---:|---|
| 插件根目录包含 `.codex-plugin/plugin.json` | 没有 | ❌ | 缺少插件“身份证”，Codex 不能把 PR 内容识别为一个可安装插件。 |
| 插件中的 Skill 位于 `skills/medlit-cli/SKILL.md` | 只有仓库级 `.agents/skills/medlit-cli/SKILL.md` | ❌ | `.agents/skills` 是仓库发现路径，不是 Plugin 包内部的 Skill 路径。 |
| 插件应带上 Skill 运行所需的代码，或明确声明外部依赖 | PR 的 Python 代码在仓库根目录，Skill 通过向上查找调用 | ⚠️ | 在本仓库中能运行，但单独安装 Skill/Plugin 时不保证能找到代码。 |
| `.codex-plugin/` 内只放 `plugin.json` | PR 尚无该目录 | ❌ | 创建插件时需要遵守；目前无法核对实际文件。 |

### 7.2 插件目录清单与安装入口

官方文档说明，仓库级插件目录清单可放在 `$REPO_ROOT/.agents/plugins/marketplace.json`；个人目录清单可放在 `~/.agents/plugins/marketplace.json`。登记后，插件才会出现在本地插件目录中，安装或更新后通常需要重启 Codex 桌面应用并开启新会话。[官方说明](https://developers.openai.com/plugins/build/plugins)

| 官方步骤 | 当前 PR | 状态 | 原因 |
|---|---|---:|---|
| 提供仓库内 `marketplace.json`，或有其他真实发布来源 | PR 中没有 | ❌ | 队友拉取 PR 后没有插件安装入口。 |
| 目录条目指向仓库内真实插件路径 | 没有仓库插件目录可指向 | ❌ | 必须先构造完整插件包。 |
| 安装后在新会话测试 | 本机个人插件做过校验和调用测试 | ⚠️ | 测试证明本机副本可用，但不能证明 PR 可复现。 |

### 7.3 本机个人 Plugin 的现状

当前本机个人插件包含 `plugin.json`、`skills/medlit-cli/`、`scripts/medlit_cli.py` 和 `medlit/`，结构上比 PR 更接近完整 Plugin，也曾通过本地验证。

但仍有这些问题：

1. 它位于用户目录，不在 Git 中，队友无法通过 PR 获得。
2. 它与仓库级 Skill 使用相同名称 `medlit-cli`。官方说明同名 Skill 不会自动合并，可能同时出现，容易让人不清楚究竟调用了哪一份。[官方说明](https://developers.openai.com/codex/skills)
3. 本地插件目录出现了 `__pycache__` 和 `.pyc`（Python 运行缓存）文件。这些是运行产生的临时文件，不应进入可分享的插件包。
4. `plugin.json` 没有许可证、主页、仓库链接等发布信息。对本地个人插件不是硬性错误；如果以后公开发布，应在信息真实、许可证已经确定后再填写，不能编造。

## 8. 按严重程度列出审查发现

### 必须修改：如果 PR 声称“提供可安装 Plugin”

1. **缺少 `.codex-plugin/plugin.json`。** 当前 PR 只能算仓库级 Skill，不能算 Plugin。
2. **Skill 没有放进 Plugin 的 `skills/` 目录。** `.agents/skills/` 和插件内部 `skills/` 用途不同。
3. **没有可复现的插件来源或目录清单。** 本机个人目录不能替代 PR 中的插件包和安装说明。
4. **运行代码没有随 PR 中的插件结构一起封装。** 如果只复制 Skill，`scripts/medlit_cli.py` 和 `medlit/` 不会跟随。

### 中高风险：真实代码问题

5. **PDF 占位记录被标为 `fulltext`。** 文档说得诚实，但代码状态可能误导后续证据处理。

### 中等问题：建议本轮或下一轮处理

6. **同名 Skill 冲突。** 本机 Plugin 和仓库 Skill 都叫 `medlit-cli`，在仓库内可能出现两个候选。
7. **`default_prompt` 的 `repository workflow` 不适合安装版。** 若同一份文件放入 Plugin，建议改为 `bundled MedLit workflow`。
8. **个人 Plugin 含 Python 缓存文件。** 打包前清理 `__pycache__/` 和 `*.pyc`。
9. **缺少“不应触发”的代表性测试。** 应验证普通医学问答不会自动触发此 Skill。
10. **`requirements.txt` 写了“未来可选”的 PDF 包，但当前代码未使用。** 这与“只写已实现能力”的原则不完全一致，也会让安装者误判依赖；应删除未来说明，或在真正接入后再加入。

### 低风险：可以后续优化

11. PDF 占位限制在正文多处重复，可以合并，减少 Codex 每次加载 Skill 时读取的文字量。
12. Skill 名称 `medlit-cli` 不是动词形式，但它准确对应工具名。官方更偏好简短、动作明确的名称，这属于写作建议，不是格式错误。

## 9. 两种合规目标，不要混在一起

### 方案 A：只做仓库级 Skill

如果当前目标只是让参与这个仓库开发的 Codex 使用 MedLit：

```text
.agents/skills/medlit-cli/SKILL.md
.agents/skills/medlit-cli/agents/openai.yaml
scripts/medlit_cli.py
medlit/
```

当前结构基本正确。应把 PR 描述写成“增加仓库级 Skill”，不要称为“已发布/可安装 Plugin”。

### 方案 B：做真正可安装的仓库 Plugin

建议形成一个自包含（安装后不依赖原仓库其他位置）的目录：

```text
plugins/
└── medlit-cli/
    ├── .codex-plugin/
    │   └── plugin.json
    ├── skills/
    │   └── medlit-cli/
    │       ├── SKILL.md
    │       └── agents/
    │           └── openai.yaml
    ├── scripts/
    │   └── medlit_cli.py
    └── medlit/
        └── ...真实运行代码...

.agents/
└── plugins/
    └── marketplace.json
```

`marketplace.json` 中的插件来源可指向 `./plugins/medlit-cli`。这符合官方给出的仓库本地插件模式。[官方目录示例](https://developers.openai.com/plugins/build/plugins)

注意：不要手工长期维护两份相同 Python 源码，否则两份代码容易逐渐不同。可以选择以下一种方式：

- 把仓库本身整理成 Plugin 的规范目录，让这里成为唯一源代码；或
- 保留开发源码，在发布时用明确的构建脚本生成干净的 Plugin 包，并校验生成物。

第二种方式中的生成目录和测试缓存不应混入日常源码提交，除非团队明确决定把可安装包本身纳入版本控制。

## 10. 推荐的修改顺序

1. 先由团队确认本 PR 的目标是“仓库级 Skill”还是“可安装 Plugin”。
2. 如果目标是 Plugin，在仓库内创建完整、可复现的插件目录和 `plugin.json`。
3. 添加仓库级 `.agents/plugins/marketplace.json`，让其他人拉取仓库后能在插件目录中安装。
4. 确保 Plugin 内包含真实运行所需的 `scripts/` 和 `medlit/`，不要只带说明文件。
5. 修复 PDF 占位记录被标成 `fulltext` 的问题。
6. 清理发布包中的 `__pycache__`、`.pyc` 和测试状态文件。
7. 调整安装版 `default_prompt` 的措辞，避免依赖“当前仓库”这一前提。
8. 添加最小触发测试：应触发、不应触发、缺少输入、网络失败、PDF 占位。
9. 用一个全新的 Codex 会话验证：发现插件、安装、显式调用、运行命令、生成报告。

## 11. 本次 Review 的合并建议

**建议：Request changes（请求修改），但原因只针对“可安装 Plugin”这一目标。**

- 作为仓库级 Skill：结构和内容已经基本合格，可以继续小幅修正。
- 作为可安装 Plugin：当前 PR 缺少必要的插件清单、插件目录和安装入口，不应宣称已经完成。
- 本机个人插件只能作为开发验证证据，不能替代 PR 中可被队友复现的插件包。

## 12. 审查范围说明

- 本报告检查了当前 PR、Skill 文件、主要 Python 入口、状态管理、全文定位、PDF 解析、诊断、报告和验证代码。
- 没有把未实现的能力写成“计划功能”，只记录当前实际存在的行为和缺口。
- `doc/` 按要求加入 `.gitignore`，因此本报告默认只保留在本地，不会进入后续 Git 提交；若需要把审查报告提交到 PR，必须先改变这一忽略策略。
