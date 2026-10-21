"""Reproduce observed Stasrift 1.0.1 results; writes only demo inputs/evidence."""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
from datetime import datetime, timezone

p = argparse.ArgumentParser()
p.add_argument('--source-root', type=Path, default=Path(__file__).parent / 'stasrift-1.0.1')
p.add_argument('--deps', type=Path)
a = p.parse_args()
root = Path(__file__).resolve().parent
source = a.source_root.resolve()
cli = source / 'stasrift.py'
env = dict(os.environ)
env['PYTHONIOENCODING'] = 'utf-8'
if a.deps:
    env['PYTHONPATH'] = str(a.deps.resolve()) + os.pathsep + env.get('PYTHONPATH', '')
inputs = root / 'inputs'
inputs.mkdir(exist_ok=True)
evidence = []

def run(label, args, code, verdict=None):
    result = subprocess.run([sys.executable, str(cli), *args], env=env,
        cwd=source, text=True, encoding='utf-8', capture_output=True)
    actual = None
    if verdict:
        try:
            actual = json.loads(result.stdout)['verdict']
        except (ValueError, KeyError):
            pass
    ok = result.returncode == code and (not verdict or actual == verdict)
    evidence.append(dict(case=label, arguments=args, expected_exit=code,
        expected_verdict=verdict, exit_code=result.returncode, verdict=actual,
        stdout=result.stdout, stderr=result.stderr, passed=ok))
    print(label, 'PASS' if ok else 'FAIL', result.returncode, actual or '')

def save(name, obj):
    path = inputs / (name + '.json')
    path.write_text(json.dumps(obj, indent=2) + '\n', encoding='utf-8')
    return str(path)

base = {'stasrift_format':'stasrift-contract-v1', 'fields':[
    {'name':'occurred_at','type':'timestamp','sem':{'time_axis':['event_time']}}]}
processing = copy.deepcopy(base)
processing['fields'][0]['sem']['time_axis'] = ['processing_time']
broader = copy.deepcopy(base)
broader['fields'][0]['sem']['time_axis'] = ['event_time','processing_time']
type_only = copy.deepcopy(base)
type_only['fields'][0]['type'] = 'string'
old = save('event-time', base)
new = save('processing-time', processing)
wide = save('two-time-axes', broader)
typ = save('physical-type-change', type_only)
empty = save('empty', {'stasrift_format':'stasrift-contract-v1','fields':[]})
bad = inputs / 'malformed.json'
bad.write_text('{"fields": [}', encoding='utf-8')
run('version', ['--version'], 0)
run('valid contract', ['validate','--contract',old], 0)
run('identical declarations', ['diff','--old',old,'--new',old,'--json'], 0, 'UNCHANGED')
run('same type, changed time meaning', ['diff','--old',old,'--new',new,'--json'], 1, 'INCOMPATIBLE')
run('widened meaning set', ['diff','--old',old,'--new',wide,'--json'], 1, 'WIDENED')
run('narrowed meaning set', ['diff','--old',wide,'--new',old,'--json'], 0, 'NARROWED')
run('physical type is outside semantic diff', ['diff','--old',old,'--new',typ,'--json'], 0, 'UNCHANGED')
run('empty contract accepted', ['validate','--contract',empty], 0)
run('malformed input rejected', ['validate','--contract',str(bad)], 2)

# The release's simple shape-only baseline, not a comparison against every
# existing schema validator or commercial product.
shape = lambda c: {f['name']: f.get('type') for f in c['fields']}
shape_equal = shape(base) == shape(processing)
report = dict(recorded_at=datetime.now(timezone.utc).isoformat(),
    python=sys.version, platform=platform.platform(), mode='unmodified release source',
    release='v1.0.1', tag_commit='ceeadec43a69790e6fa3dc11738892841add69b2',
    release_url='https://github.com/arkosom/stasrift/releases/tag/v1.0.1',
    source_zip_sha256='9cf9877c7b346f36ba0eb26bcadb0b6ad3fc0b90cc095f15ae07f5722110c3f9',
    cli_sha256=hashlib.sha256(cli.read_bytes()).hexdigest(),
    shape_baseline_equal=shape_equal, cases=evidence,
    passed=shape_equal and all(x['passed'] for x in evidence))
(root / 'observed-results.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
raise SystemExit(0 if report['passed'] else 1)
