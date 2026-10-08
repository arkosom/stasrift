"""Compare synthetic and repository contracts against preserved 1.0.0 code."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import jsonschema

ROOT=Path(__file__).resolve().parents[2]
BASE=Path(sys.argv[1]).resolve()
def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    return mod
old=module('old_cli',BASE/'src/stasrift/cli.py')
new=module('new_cli',ROOT/'src/stasrift/cli.py')
schema=json.loads((ROOT/'schemas/stasrift-contract-v1.schema.json').read_text())
validator=jsonschema.Draft202012Validator(schema)

def outcome(cli,path):
    try:
        data=cli.load_any(path)
        normalized=cli.normalize_contract(data,str(path))
        return {'accepted':True,'normalized':normalized}
    except Exception as exc:
        return {'accepted':False,'error':str(exc)}

cases={
    'canonical':{'stasrift_format':'stasrift-contract-v1','fields':[{'name':'amount','sem':{'unit':['USD']}}]},
    'legacy_scalar':{'fields':[{'name':'amount','sem':{'unit':'USD'}}]},
    'canonical_scalar_invalid_schema':{'stasrift_format':'stasrift-contract-v1','fields':[{'name':'amount','sem':{'unit':'USD'}}]},
    'identical_duplicate':{'stasrift_format':'stasrift-contract-v1','fields':[{'name':'x'},{'name':'x'}]},
    'conflicting_duplicate':{'stasrift_format':'stasrift-contract-v1','fields':[{'name':'x','sem':{'unit':['USD']}},{'name':'x','sem':{'unit':['EUR']}}]},
    'unknown_sem_key_invalid_schema':{'stasrift_format':'stasrift-contract-v1','fields':[{'name':'x','sem':{'currency':['USD']}}]},
    'unknown_legacy_sem_key':{'fields':[{'name':'x','sem':{'currency':['USD']}}]},
    'empty_contract':{'stasrift_format':'stasrift-contract-v1','fields':[]},
    'empty_semantics':{'stasrift_format':'stasrift-contract-v1','fields':[{'name':'x','sem':{}}]},
    'multiple_modes':{'stasrift_format':'stasrift-contract-v1','fields':[{'name':'x','sem':{'time_axis':['event_time','processing_time']}}]},
    'extra_metadata':{'stasrift_format':'stasrift-contract-v1','extra':42,'fields':[{'name':'x','vendor':'anything'}]},
    'odcs_properties':{'properties':[{'name':'x','customProperties':{'sem':{'unit':'USD'}}}]},
    'nested_odcs':{'schema':{'properties':[{'name':'x','sem':{'unit':'USD'}}]}},
    'null_sem_invalid_schema':{'stasrift_format':'stasrift-contract-v1','fields':[{'name':'x','sem':None}]},
    'repeated_mode_invalid_schema':{'stasrift_format':'stasrift-contract-v1','fields':[{'name':'x','sem':{'unit':['USD','USD']}}]},
}
results=[]
with tempfile.TemporaryDirectory() as d:
    for name,data in cases.items():
        p=Path(d)/(name+'.json');p.write_text(json.dumps(data))
        results.append({'case':name,'corpus':'synthetic','frozen_schema_valid':validator.is_valid(data),
                        'original':outcome(old,p),'candidate':outcome(new,p)})
    p=Path(d)/'merged.yaml';p.write_text('''stasrift_format: stasrift-contract-v1
base: &base {name: amount, sem: {unit: [USD]}}
fields:
  - <<: *base
    sem: {unit: [EUR]}
''')
    results.append({'case':'yaml_merge_override','corpus':'synthetic','frozen_schema_valid':validator.is_valid(old.load_any(p)),
                    'original':outcome(old,p),'candidate':outcome(new,p)})
for p in sorted(ROOT.rglob('*.yaml')):
    if any(part in {'.venv','dist','build'} for part in p.relative_to(ROOT).parts):continue
    try:data=old.load_any(p)
    except Exception:continue
    if not isinstance(data,dict) or not any(k in data for k in ('fields','properties','schema')):continue
    results.append({'case':str(p.relative_to(ROOT)),'corpus':'repository',
                    'frozen_schema_valid':validator.is_valid(data),'original':outcome(old,p),'candidate':outcome(new,p)})
output={'original_commit':'ca6098b40e2f4b48f5ab9c849a9fcb8da4f49edb','results':results}
Path(__file__).with_name('compatibility-results.json').write_text(json.dumps(output,indent=2)+'\n')
repository=[r for r in results if r['corpus']=='repository']
assert all(r['original'].get('normalized')==r['candidate'].get('normalized') and r['original']['accepted']==r['candidate']['accepted'] for r in repository)
assert next(r for r in results if r['case']=='yaml_merge_override')['candidate']['accepted']
print('PASS',len(repository),'repository contracts have matching acceptance and normalized declarations')
print('Synthetic cases:',len(cases)+1)
for r in results:
 if r['original']['accepted']!=r['candidate']['accepted']:
  print('INTENTIONAL ACCEPTANCE CHANGE',r['case'],'schema valid:',r['frozen_schema_valid'])
