#!/usr/bin/env bash
# thuon.sh — dispatch script for Thuon Platform capabilities
# Usage: ./thuon.sh <capability_module> <method> [json_args]
# Example: ./thuon.sh research_assistant perform_research '{"research_query": "AI trends"}'

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

CAPABILITY="${1:-}"
METHOD="${2:-}"
ARGS="${3:-{}}"

if [[ -z "$CAPABILITY" || -z "$METHOD" ]]; then
    echo "Usage: $0 <capability_module> <method> [json_args]"
    echo ""
    echo "Available capabilities:"
    python3 -c "
import glob, os
caps = sorted(os.path.basename(f).replace('.py','') for f in glob.glob('capabilities/*.py') if not f.endswith('__init__.py'))
for c in caps: print('  -', c)
"
    exit 1
fi

python3 - <<PYEOF
import sys, json
sys.path.insert(0, '.')

# Dynamic import
import importlib
try:
    mod = importlib.import_module(f'capabilities.${CAPABILITY}')
except ModuleNotFoundError:
    # Try CamelCase variants
    name = '${CAPABILITY}'.replace('_', ' ').title().replace(' ', '')
    mod = importlib.import_module(f'capabilities.{name}')

# Find the class (first non-private class in module)
import inspect
cls = None
for attr_name in dir(mod):
    obj = getattr(mod, attr_name)
    if inspect.isclass(obj) and not attr_name.startswith('_') and obj.__module__ == mod.__name__:
        cls = obj
        break

if cls is None:
    print(json.dumps({'error': 'No class found in module ${CAPABILITY}'}))
    sys.exit(1)

# Bootstrap minimal deps
from core.ai_engine import OllamaModel
from core.search_engine import DuckDuckGoSearch

ai = OllamaModel()
search = DuckDuckGoSearch()

# Try constructor signatures
import inspect as _i
sig = _i.signature(cls.__init__)
params = list(sig.parameters.keys())[1:]  # skip self

kwargs = {}
if 'ai_engine' in params: kwargs['ai_engine'] = ai
if 'search_engine' in params: kwargs['search_engine'] = search

instance = cls(**kwargs)

method = getattr(instance, '${METHOD}')
args = json.loads('${ARGS}')
result = method(**args) if isinstance(args, dict) else method(*args)
print(json.dumps(result, indent=2, default=str))
PYEOF
