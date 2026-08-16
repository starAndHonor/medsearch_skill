"""Compatibility import that delegates to the installable plugin runtime.

The plugin bundle is the only maintained implementation. Keeping this small
package redirect preserves ``import medlit`` for repository scripts without
creating a second executable code path.
"""

from pathlib import Path

_PLUGIN_PACKAGE = Path(__file__).resolve().parents[1] / "plugins" / "medlit-cli" / "medlit"
if not _PLUGIN_PACKAGE.is_dir():
    raise ImportError(f"MedLit plugin runtime not found: {_PLUGIN_PACKAGE}")

__path__ = [str(_PLUGIN_PACKAGE)]
__version__ = "0.2.0"

