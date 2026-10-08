import json
import os
from pathlib import Path
import subprocess
import sys
import pytest
from test_adversarial import run, contract, review_case, ROOT

@pytest.mark.parametrize('merge',[
    '''base: &base
  name: amount
  sem: {unit: [USD]}
fields:
  - <<: *base
    sem: {unit: [EUR]}
''',
    '''first: &first {name: amount, sem: {unit: [EUR]}}
second: &second {name: ignored, sem: {unit: [USD]}}
fields:
  - <<: [*first, *second]
''',
])
def test_yaml_merge_precedence(tmp_path,merge):
    path=tmp_path/'c.yaml';path.write_text('stasrift_format: stasrift-contract-v1\n'+merge)
    expected=contract(tmp_path,{'stasrift_format':'stasrift-contract-v1','fields':[{'name':'amount','sem':{'unit':['EUR']}}]})
    r=run('diff','--old',path,'--new',expected,'--json')
    assert r.returncode==0 and json.loads(r.stdout)['verdict']=='UNCHANGED'

@pytest.mark.parametrize('shape',[
    {'fields':[{'name':'x','sem':{'unit':'USD'}}]},
    {'properties':[{'name':'x','customProperties':{'sem':{'time_axis':'event_time'}}}]},
    {'schema':{'properties':[{'name':'x','sem':{'absent':'unknown'}}]}},
    {'stasrift_format':'stasrift-contract-v1','fields':[]},
    {'stasrift_format':'stasrift-contract-v1','extra':{'any':'data'},'fields':[{'name':'x','extra':42,'type':{'vendor':'opaque'},'sem':{}}]},
])
def test_supported_existing_contracts(tmp_path,shape):
    assert run('validate','--contract',contract(tmp_path,shape)).returncode==0

@pytest.mark.parametrize('encoding',['cp1252','ascii','utf-8'])
def test_review_output_encoding(tmp_path,encoding):
    c,sg,skip=review_case(tmp_path)
    env=dict(os.environ,PYTHONIOENCODING=encoding)
    r=subprocess.run([sys.executable,str(ROOT/'stasrift.py'),'review','--suggestions',str(sg),'--contract',str(c),'--skip-file',str(skip),'--dry-run','--no-color'],
                     cwd=ROOT,input=b's\n',capture_output=True,env=env,timeout=15)
    assert r.returncode==0, r.stderr
    assert b'Dry run: nothing written.' in r.stdout and not skip.exists()

def test_identical_duplicate_fields_remain_accepted(tmp_path):
    field={'name':'x','sem':{'unit':['USD']}}
    c=contract(tmp_path,{'stasrift_format':'stasrift-contract-v1','fields':[field,field]})
    r=run('validate','--contract',c,'--json')
    assert r.returncode==0 and json.loads(r.stdout)['fields']==1

def test_review_identical_duplicates_consistently(tmp_path):
    c,sg,skip=review_case(tmp_path)
    c.write_text(json.dumps({'fields':[{'name':'x'},{'name':'x'}]}))
    r=run('review','--contract',c,'--suggestions',sg,'--skip-file',skip,input_text='1\n1\n')
    assert r.returncode==0
    data=json.loads(c.read_text())
    assert all(field['sem']=={'time_axis':['event_time']} for field in data['fields'])
    assert run('validate','--contract',c).returncode==0

def test_wrapper_when_src_already_on_pythonpath():
    env=dict(os.environ,PYTHONPATH=str(ROOT/'src'))
    r=subprocess.run([sys.executable,str(ROOT/'stasrift.py'),'--version'],cwd=ROOT,env=env,capture_output=True,text=True,timeout=15)
    assert r.returncode==0 and r.stdout.strip()=='stasrift 1.0.1'
