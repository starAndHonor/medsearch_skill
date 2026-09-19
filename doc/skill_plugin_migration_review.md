# MedLit CLI Plugin 迁移完成复审

> 复审日期：2026-08-09  
> 工作分支：`lhq_0809_fix`  
> 插件：`medlit-cli@medlit-local`  
> 版本：`0.2.0`

## 1. 最终结论

当前仓库已经从“只能在当前项目中发现的 Skill”迁移为“可登记、可安装、可缓存，并能在仓库外新 Codex 会话中调用的 Plugin”。

| 目标 | 结果 | 证据 |
|---|---:|---|
| 下载仓库后能登记为插件来源 | ✅ | `.agents/plugins/marketplace.json` |
| Codex 能识别完整 Plugin | ✅ | `plugins/medlit-cli/.codex-plugin/plugin.json` 通过官方校验器 |
| Skill 位于 Plugin 标准目录 | ✅ | `plugins/medlit-cli/skills/medlit-cli/SKILL.md` |
| 安装后不依赖原仓库上级代码 | ✅ | Plugin 内包含 `scripts/medlit_cli.py` 和精简后的 `medlit/` 运行包 |
| Codex 插件 CLI 可以安装 | ✅ | 已安装 `medlit-cli@medlit-local 0.2.0` |
| 仓库外新会话可以发现 Skill | ✅ | 新会话从 Codex 插件缓存加载了 Skill 和脚本 |
| 发布包不含评测或测试数据 | ✅ | 包内没有 `evals/`、`data/`、`test_*`、`__pycache__` 或 `.pyc` |

依据 OpenAI 官方文档，Skill 可以单独放在仓库中使用；要作为可安装内容分发，则应包装成具有 `plugin.json`、`skills/` 和插件来源清单的 Plugin：

- [Build skills](https://developers.openai.com/codex/skills)
- [Add skills to your plugin](https://developers.openai.com/plugins/build/skills)
- [Package and publish a plugin](https://developers.openai.com/plugins/build/plugins)

## 2. 新手理解：这次迁移解决了什么

迁移前只有：

```text
.agents/skills/medlit-cli/SKILL.md
```

这相当于“项目里放了一份智能体操作说明”。Codex 打开该项目时可以看见它，但它不是一个可安装插件。

迁移后形成：

```text
仓库 marketplace（告诉 Codex 到哪里找插件）
        ↓
plugin.json（插件的身份和版本）
        ↓
skills/medlit-cli/SKILL.md（智能体工作说明）
        ↓
scripts/ + medlit/（安装后真正执行的代码）
```

因此，Codex 现在可以把整个 Plugin 复制进自己的插件缓存。即使新会话的工作目录不在本仓库里，安装后的 Skill 仍能找到随包代码。

## 3. 当前发布结构

```text
.agents/
└── plugins/
    └── marketplace.json

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
        └── 运行所需 Python 模块

README.md
scripts/sync_plugin.py
```

原来的 `.agents/skills/medlit-cli/` 已迁走。这样做可以避免仓库 Skill 和已安装 Plugin 同时提供两个同名 `$medlit-cli`。

## 4. 官方规范逐条核对

状态含义：✅ 符合；⚠️ 不阻塞安装，但公开发布前需要项目负责人决定。

### 4.1 Plugin 外层结构

| 官方要求 | 当前实现 | 状态 | 原因 |
|---|---|---:|---|
| Plugin 根目录包含 `.codex-plugin/plugin.json` | 已提供 | ✅ | 这是 Codex 识别插件的清单文件（插件身份证）。 |
| `plugin.json` 名称与目录名一致 | 都是 `medlit-cli` | ✅ | 避免插件命名冲突。 |
| 版本使用语义版本 | `0.2.0` | ✅ | 格式为“主版本.次版本.修订版本”。 |
| 提供真实描述和作者 | 描述对应实际功能；作者为项目贡献者 | ✅ | 没有写入未实现的 PDF 提取或医学验证能力。 |
| Skill 路径从 Plugin 根目录开始 | `skills: "./skills/"` | ✅ | 与实际目录一致。 |
| 未创建的 MCP、App 不应声明 | 未声明 | ✅ | 当前功能不依赖 MCP 或 App，不为了形式添加空配置。 |
| 许可证字段必须真实吗 | 当前没有填写 | ⚠️ | 仓库尚无许可证，不能猜。Git 下载和本地安装不受阻；若正式以开源项目公开发布，负责人应先选择并提交真实 `LICENSE`。 |

### 4.2 Marketplace（插件目录清单）

| 官方要求 | 当前实现 | 状态 | 原因 |
|---|---|---:|---|
| 仓库 marketplace 位于 `.agents/plugins/marketplace.json` | 已提供 | ✅ | Codex CLI 可以从仓库根目录登记它。 |
| marketplace 名称应能区分来源 | `medlit-local` | ✅ | 不与本机默认的 `personal` 目录重名。 |
| 来源使用仓库内相对路径 | `./plugins/medlit-cli` | ✅ | 下载或移动整个仓库后仍然有效。 |
| 包含安装和认证策略 | `AVAILABLE`、`ON_INSTALL` | ✅ | 字段完整，值属于官方允许范围。 |
| 包含插件分类 | `Productivity` | ✅ | 目录条目完整。 |

### 4.3 Skill 本身

| 官方要求或建议 | 当前实现 | 状态 | 原因 |
|---|---|---:|---|
| 必须有 `SKILL.md` | 已提供 | ✅ | 位于 Plugin 的标准 Skill 目录。 |
| 开头只写 `name` 和 `description` | 已遵守 | ✅ | 没有虚构 `allowed-tools`、许可证或未支持字段。 |
| 名称与目录名一致 | `medlit-cli` | ✅ | 触发名称稳定。 |
| 描述说明功能和触发条件 | 明确要求显式 `$medlit-cli` | ✅ | 普通医学问题不会自动启动网络工作流。 |
| 正文写明输入、步骤、输出和停止条件 | 已写明完整 13 步工作流 | ✅ | 命令可以在真实 `medlit/cli.py` 中找到。 |
| 说明真实限制 | PDF 仅占位；`verify` 不验证医学正确性 | ✅ | 没有把未实现能力写进 Skill。 |
| `agents/openai.yaml` 与 Skill 一致 | 使用 `bundled workflow`，禁止自动触发 | ✅ | 安装后不再依赖“当前仓库工作流”的旧表述。 |

### 4.4 随包运行代码

| 检查项 | 当前实现 | 状态 | 原因 |
|---|---|---:|---|
| 安装包能够独立执行 | 包含启动脚本和运行模块 | ✅ | Skill 从自身位置向上即可找到 `scripts/medlit_cli.py` 与 `medlit/cli.py`。 |
| 不打包无关大型数据 | 不含 `data/` 和 `evals/` | ✅ | BioASQ 数据和评分工具不是 Skill 运行依赖。 |
| 不打包旧智能体外壳 | 排除 `medlit/agent/` | ✅ | 当前 Skill 调用确定性的 `medlit.cli`，不使用旧交互外壳。 |
| 不打包 Python 缓存 | 已检查无缓存 | ✅ | 避免平台和 Python 版本相关的脏文件。 |
| 依赖说明真实 | Python 3.10+ 标准库 | ✅ | 删除了尚未接入代码的未来 PDF 依赖。 |
| 开发源码和发布快照能防止漂移 | `scripts/sync_plugin.py` | ✅ | `--check` 会报告缺失、过期或多余文件。 |

## 5. 实际安装与发现验证

### 5.1 校验器

以下检查均通过：

```text
python scripts/sync_plugin.py --check
  Plugin runtime verified: 18 files

quick_validate.py plugins/medlit-cli/skills/medlit-cli
  Skill is valid!

validate_plugin.py plugins/medlit-cli
  Plugin validation passed
```

### 5.2 运行冒烟

使用项目指定的 Conda Python：

```text
D:\anaconda\conda3\envs\Swarm-Evo\python.exe
```

验证结果：

- 插件启动脚本的 `--help` 正常列出所有真实命令。
- 在临时目录执行 `init` 成功创建状态。
- 随后执行 `status` 返回 `running`、`needs_pico` 和下一步 `decompose`。
- 临时状态目录已经清理。

### 5.3 Codex 安装

实际执行：

```text
codex plugin marketplace add D:\GZIC_study\SRP\medlit-cli-v2\medsearch_skill
codex plugin add medlit-cli@medlit-local
```

Codex 返回：

```text
marketplaceName: medlit-local
pluginId: medlit-cli@medlit-local
version: 0.2.0
status: installed, enabled
```

旧的 `medlit-cli@personal 0.1.0` 已卸载，避免两个同名 Skill 同时启用。

### 5.4 仓库外新会话验证

在系统临时目录创建了一个不属于本仓库的新工作目录，并启动只读、临时 Codex 会话。会话显式调用 `$medlit-cli` 后加载了：

```text
C:\Users\CGOMI\.codex\plugins\cache\medlit-local\medlit-cli\0.2.0\skills\medlit-cli\SKILL.md
```

它解析到的运行脚本为：

```text
C:\Users\CGOMI\.codex\plugins\cache\medlit-local\medlit-cli\0.2.0\scripts\medlit_cli.py
```

并确认同一安装缓存中存在：

```text
C:\Users\CGOMI\.codex\plugins\cache\medlit-local\medlit-cli\0.2.0\medlit\cli.py
```

这项验证排除了“Codex 只是从当前仓库看见 Skill”的情况：新会话实际读取的是 Codex 安装缓存中的完整 Plugin。

## 6. 用户安装方式

仓库合并后，用户可以选择本地克隆：

```text
git clone https://github.com/starAndHonor/medsearch_skill.git
cd medsearch_skill
codex plugin marketplace add .
codex plugin add medlit-cli@medlit-local
```

也可以直接登记 GitHub 仓库：

```text
codex plugin marketplace add starAndHonor/medsearch_skill --ref main
codex plugin add medlit-cli@medlit-local
```

安装后重启 Codex 应用并开启新会话，然后显式调用：

```text
$medlit-cli Research a biomedical literature question.
```

Windows PowerShell 如果阻止 `codex.ps1`，使用 `codex.cmd` 执行相同命令即可，不需要修改整个系统的执行策略。

## 7. 仍然存在但不阻塞安装的问题

以下属于基础功能问题，不是 Plugin 结构问题：

1. PDF 当前只生成占位内容，不提取正文。
2. PDF 占位结果仍被内部状态标成 `fulltext`；Skill 已禁止把它当作证据，但底层标记以后仍应修正。
3. `verify` 只检查报告引用完整性，不验证医学事实、研究质量或临床适用性。
4. 正式以开源许可证发布前，需要项目负责人选择真实许可证并添加 `LICENSE`；本次没有擅自选择。

这些限制均已在 Skill 中如实声明，没有包装成已实现能力。

## 8. 本轮合并建议

从“Codex Plugin 的迁移、安装和发现规范”角度，原报告中的必要缺口已经解决，可以进入提交前人工复核：

- Plugin 清单：通过。
- Marketplace：实际登记成功。
- Skill：通过官方快速校验。
- 发布代码：自包含并通过同步检查。
- 安装：成功。
- 新会话发现：成功。
- 测试/评测代码污染：未发现。

本地 `doc/` 仍按要求被 `.gitignore` 忽略，因此本复审报告不会进入提交。面向安装者的正式说明位于仓库根 `README.md`，会随代码提交。
