from pathlib import Path
import json, subprocess, sys
ROOT=Path(__file__).resolve().parent
def run(*args):
    return subprocess.run([sys.executable,str(ROOT/'stasrift.py'),*args],cwd=ROOT,capture_output=True,text=True)
checks=[]
p=run('--version'); checks.append(('version',p.returncode==0 and '1.0.0' in p.stdout))
p=run('validate','--contract','examples/orders.stasrift.yaml','--json'); checks.append(('validate',p.returncode==0 and json.loads(p.stdout)['valid'] is True))
p=run('diff','--old','incident_fixture/schema_v1.yaml','--new','incident_fixture/schema_v2.yaml','--json'); checks.append(('semantic break',p.returncode==1 and json.loads(p.stdout)['verdict']=='INCOMPATIBLE'))
p=run('doctor','--repo','dbt_fixture','--json'); checks.append(('doctor',p.returncode==0 and json.loads(p.stdout)['ready'] is True))
for name,ok in checks: print(('PASS' if ok else 'FAIL'),name)
raise SystemExit(0 if all(ok for _,ok in checks) else 1)
