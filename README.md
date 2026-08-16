# MedLit CLI for Codex

MedLit CLI is an installable Codex plugin for a stateful biomedical literature
workflow. It can plan and run PubMed searches, fetch records, try open-access
full-text sources, extract first-pass evidence, and write and integrity-check a
report.

The current implementation does not extract text from PDF files and does not
validate medical correctness. See the in-plugin `medlit-cli` skill for the
complete workflow and safety boundaries.

## Requirements

- Codex with plugin support
- Python 3.10 or later
- Network access for PubMed, Europe PMC, and optional Unpaywall requests

The runtime uses the Python standard library and has no required `pip`
packages.

## Install from the repository

Clone the repository, then register it as a Codex marketplace (plugin
directory) and install the plugin:

```text
git clone https://github.com/starAndHonor/medsearch_skill.git
cd medsearch_skill
codex plugin marketplace add .
codex plugin add medlit-cli@medlit-local
```

On Windows, if PowerShell blocks the `codex.ps1` launcher, run the same
commands with `codex.cmd` instead of changing the system execution policy.

You can also add the GitHub repository directly after the plugin changes have
been merged into the selected branch:

```text
codex plugin marketplace add starAndHonor/medsearch_skill --ref main
codex plugin add medlit-cli@medlit-local
```

Restart the Codex app after first installation, open a new thread, and invoke
the skill explicitly:

```text
$medlit-cli Research a biomedical literature question.
```

The skill intentionally disables automatic invocation so an ordinary medical
question does not start a networked research workflow unexpectedly.

## Repository layout

```text
.agents/plugins/marketplace.json       Codex marketplace entry
plugins/medlit-cli/
  .codex-plugin/plugin.json            Plugin identity and UI metadata
  skills/medlit-cli/SKILL.md           Codex workflow instructions
  scripts/medlit_cli.py                Bundled command entrypoint
  medlit/                               Bundled runtime package
scripts/sync_plugin.py                 Single-runtime verification helper
```

`plugins/medlit-cli/medlit/` is the only maintained runtime source. The
repository launcher and compatibility `medlit` import delegate to it, so evals
and installed use cannot silently execute different retrieval code. Verify the
resolution before committing a release:

```text
python scripts/sync_plugin.py --check
```

The helper is deliberately read-only; it fails if repository imports resolve
outside the plugin runtime.

## Verify an installation

```text
codex plugin list
python plugins/medlit-cli/scripts/medlit_cli.py --help
```

`codex plugin list` should show `medlit-cli@medlit-local` as installed and
enabled. Use a new Codex thread after installing or updating so the new Skill
metadata is loaded.
