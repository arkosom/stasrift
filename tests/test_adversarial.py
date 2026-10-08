"""Reproducible adversarial cases; CLI assertions exercise real user boundaries."""
import json
import os
import subprocess
import sys
from pathlib import Path
import pytest

ROOT = Path(os.environ.get('STASRIFT_TEST_ROOT', Path(__file__).resolve().parents[1]))

def run(*args, input_text=None):
    return subprocess.run([sys.executable, str(ROOT/'stasrift.py'), *map(str, args)],
                          cwd=ROOT, input=input_text, capture_output=True, text=True, timeout=15)

def contract(tmp_path, data, name='contract.json'):
    p = tmp_path/name
    p.write_text(json.dumps(data))
    return p

@pytest.mark.parametrize('data', [
    {'fields':[{'name':'x','sem':{'time_axis':['event_time']}},{'name':'x','sem':{'time_axis':['processing_time']}}]},
    {'fields':[{'name':'x','sem':[]}]},
    {'fields':[{'name':'x','sem':False}]},
    {'fields':[{'name':'x','sem':{'unt':['USD']}}]},
    {'stasrift_format':'stasrift-contract-v1','fields':[{'name':'x','sem':{'unit':'USD'}}]},
    {'stasrift_format':'stasrift-contract-v1','fields':[{'name':'x','nullable':'false'}]},
    {'stasrift_format':'stasrift-contract-v1','fields':[{'name':'x','sem':{'unit':['USD','USD']}}]},
    None, [], {'fields':[42]}, {'fields':[{'name':''}]},
    {'fields':[{'name':'x','sem':{'time_axis':['made_up']}}]},
])
def test_invalid_contract(tmp_path, data):
    p=run('validate','--contract',contract(tmp_path,data))
    assert p.returncode == 2 and 'Traceback' not in p.stderr

@pytest.mark.parametrize('name,text', [
    ('bad.json','{"fields": []'), ('bad.yaml','fields: ['),
    ('dup.json','{"fields": [], "fields": [{"name":"x"}]}'),
    ('dup.yaml','fields: []\nfields: [{name: x}]'),
    ('nan.json','{"fields": [], "extra": NaN}'),
    ('unsafe.yaml','!!python/object/apply:os.system ["echo UNSAFE"]'),
])
def test_bad_serialization(tmp_path,name,text):
    p=tmp_path/name;p.write_text(text)
    r=run('validate','--contract',p)
    assert r.returncode==2 and 'Traceback' not in r.stderr

def test_invalid_utf8(tmp_path):
    p=tmp_path/'bad.yaml';p.write_bytes(b'\xff')
    r=run('validate','--contract',p)
    assert r.returncode==2 and 'Traceback' not in r.stderr

@pytest.mark.parametrize('old,new,expected,code', [
    ({},{},'UNCHANGED',0),
    ({'time_axis':['event_time']},{'time_axis':['processing_time']},'INCOMPATIBLE',1),
    ({'unit':['USD']},{'unit':['EUR']},'INCOMPATIBLE',1),
    ({'absent':['unknown']},{'absent':['zero_equivalent']},'INCOMPATIBLE',1),
    ({'unit':['USD']},{},'WIDENED',1),
    ({},{'unit':['USD']},'NARROWED',0),
    ({'unit':['USD','EUR']},{'unit':['USD']},'NARROWED',0),
])
def test_comparison(tmp_path,old,new,expected,code):
    a=contract(tmp_path,{'fields':[{'name':'x','sem':old}]},'a.json')
    b=contract(tmp_path,{'fields':[{'name':'x','sem':new}]},'b.json')
    r=run('diff','--old',a,'--new',b,'--json')
    assert r.returncode==code and json.loads(r.stdout)['verdict']==expected

@pytest.mark.parametrize('field',['amount_cents','amount_dollars'])
def test_currency_is_not_invented(tmp_path,field):
    c=contract(tmp_path,{'fields':[{'name':field}]})
    ev=tmp_path/'ev.json';sg=tmp_path/'sg.json'
    assert run('scan','--repo',tmp_path,'--contract',c,'--out',ev).returncode==0
    assert run('suggest','--evidence',ev,'--out',sg).returncode==0
    item=json.loads(sg.read_text())['suggestions'][0]
    assert item['kind']=='question' and item['proposed'] is None

@pytest.mark.parametrize('sql',[
    "select 'current_timestamp' as captured_at from raw",
    "/* select current_timestamp as captured_at from raw */ select other as captured_at from raw",
    "select current_timestamp as captured_at from a union all select event_time as captured_at from b",
    "with c as (select current_timestamp as ts from a) select ts as captured_at from c join b on 1=1",
])
def test_sql_false_positive(tmp_path,sql):
    c=contract(tmp_path,{'fields':[{'name':'captured_at'}]})
    (tmp_path/'model.sql').write_text(sql)
    ev=tmp_path/'ev.json';sg=tmp_path/'sg.json'
    assert run('scan','--repo',tmp_path,'--contract',c,'--out',ev).returncode==0
    assert run('suggest','--evidence',ev,'--out',sg).returncode==0
    assert not any(s['kind']=='suggestion' for s in json.loads(sg.read_text())['suggestions'])

@pytest.mark.parametrize('fields',[None,[None],[{'name':'x','evidence':[None]}],[{'name':'x','evidence':{}}]])
def test_malformed_bundle(tmp_path,fields):
    ev=contract(tmp_path,{'format':'stasrift-evidence-v2','fields':fields})
    r=run('suggest','--evidence',ev,'--out',tmp_path/'s.json')
    assert r.returncode==2 and 'Traceback' not in r.stderr

def review_case(tmp_path):
    c=contract(tmp_path,{'fields':[{'name':'x'}]})
    sg=contract(tmp_path,{'format':'stasrift-suggestions-v2','suggestions':[
        {'field':'x','attribute':'time_axis','kind':'question','choices':['event_time','processing_time'],
         'evidence':[],'evidence_hash':'abc'}]},'sg.json')
    return c,sg,tmp_path/'skip.json'

@pytest.mark.parametrize('args,answer',[(['--dry-run'],'s\n'),([], 's\n2\n')])
def test_review_no_unapproved_state(tmp_path,args,answer):
    c,sg,skip=review_case(tmp_path);before=c.read_bytes()
    r=run('review','--contract',c,'--suggestions',sg,'--skip-file',skip,*args,input_text=answer)
    assert r.returncode==0 and c.read_bytes()==before and not skip.exists()

@pytest.mark.parametrize('answer',['0\n','-1\n','3\n'])
def test_invalid_choice(tmp_path,answer):
    c,sg,skip=review_case(tmp_path)
    r=run('review','--contract',c,'--suggestions',sg,'--skip-file',skip,input_text=answer)
    assert r.returncode==2 and not skip.exists()

def test_stale_review(tmp_path):
    c,sg,skip=review_case(tmp_path)
    data=json.loads(sg.read_text());data['source_contract_sha256']='0'*64;sg.write_text(json.dumps(data))
    r=run('review','--contract',c,'--suggestions',sg,'--skip-file',skip,input_text='1\n1\n')
    assert r.returncode==2 and 'stale' in r.stderr and not skip.exists()

def test_invalid_human_value_not_written(tmp_path):
    c,sg,skip=review_case(tmp_path);data=json.loads(sg.read_text());data['suggestions'][0]['choices']=[];sg.write_text(json.dumps(data))
    before=c.read_bytes()
    r=run('review','--contract',c,'--suggestions',sg,'--skip-file',skip,input_text='made_up\n1\n')
    assert r.returncode==2 and c.read_bytes()==before and not skip.exists()

def test_json_review_keeps_json_and_approved_state(tmp_path):
    c,sg,skip=review_case(tmp_path)
    r=run('review','--contract',c,'--suggestions',sg,'--skip-file',skip,input_text='1\n1\n')
    assert r.returncode==0
    assert json.loads(c.read_text())['fields'][0]['sem']['time_axis']==['event_time']
    assert run('validate','--contract',c).returncode==0

def test_demo_does_not_invent_shape_pass(tmp_path):
    fixture=tmp_path/'incident_fixture';fixture.mkdir()
    contract(fixture,{'fields':[{'name':'x','type':'string'}]},'schema_v1.yaml')
    contract(fixture,{'fields':[{'name':'x','type':'integer'}]},'schema_v2.yaml')
    r=run('demo','--root',tmp_path)
    assert r.returncode==1 and 'FAIL: structural schema changed' in r.stdout

@pytest.mark.parametrize('data',[
    {'stasrift_format':'stasrift-contract-v1','fields':[{'name':'x','sem':None}]},
    {'stasrift_format':'stasrift-contract-v1','properties':[{'name':'x'}]},
])
def test_v1_schema_boundary(tmp_path,data):
    assert run('validate','--contract',contract(tmp_path,data)).returncode==2

@pytest.mark.parametrize('data',[
    [], {'format':[]}, {'format':'stasrift-suggestions-v2','suggestions':[None]},
    {'format':'stasrift-suggestions-v2','source_contract_sha256':[]},
    {'format':'stasrift-suggestions-v2','suggestions':[{'field':'x','attribute':[]}]},
    {'format':'stasrift-suggestions-v2','suggestions':[{'field':'x','attribute':'unit','kind':[]}]},
    {'format':'stasrift-suggestions-v2','suggestions':[{'field':'x','attribute':'unit','kind':'suggestion','proposed':'USD'}]},
])
def test_malformed_review_bundle(tmp_path,data):
    c,sg,skip=review_case(tmp_path);sg.write_text(json.dumps(data))
    r=run('review','--contract',c,'--suggestions',sg,'--skip-file',skip,input_text='')
    assert r.returncode==2 and 'Traceback' not in r.stderr and not skip.exists()
