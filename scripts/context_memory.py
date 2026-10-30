"""Compatibility facade: the same stdlib Composer is packaged with Runtime."""
import importlib.util
from pathlib import Path
import sys

_name = '_pcp_context_memory'
_spec = importlib.util.spec_from_file_location(_name,
    Path(__file__).resolve().parents[1] / 'services/runtime/app/context_memory.py')
_core = importlib.util.module_from_spec(_spec)
sys.modules[_name] = _core
_spec.loader.exec_module(_core)
globals().update({name: value for name, value in vars(_core).items() if not name.startswith('__')})
