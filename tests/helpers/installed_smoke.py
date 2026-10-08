import subprocess, json, tempfile, sys
from pathlib import Path
CLI=sys.argv[1]
root=Path(sys.argv[2]).resolve()
with tempfile.TemporaryDirectory() as folder:
    work=Path(folder)
    c=work/'c.json';c.write_text(json.dumps({'stasrift_format':'stasrift-contract-v1','fields':[{'name':'captured_at'}]}))
    (work/'model.sql').write_text('select current_timestamp as captured_at from raw')
    ev=work/'ev.json';sg=work/'sg.json';skip=work/'skip.json'
    checks=[(['--version'],0,None),(['contract-schema','--json'],0,None),
      (['validate','--contract',str(c)],0,None),(['doctor','--repo',str(work)],0,None),
      (['scan','--repo',str(work),'--contract',str(c),'--out',str(ev)],0,None),
      (['suggest','--evidence',str(ev),'--out',str(sg)],0,None),
      (['review','--suggestions',str(sg),'--contract',str(c),'--skip-file',str(skip),'--dry-run'],0,'1\n'),
      (['diff','--old',str(root/'incident_fixture/schema_v1.yaml'),'--new',str(root/'incident_fixture/schema_v2.yaml')],1,None),
      (['demo','--root',str(root)],1,None)]
    for args,expected,answer in checks:
      p=subprocess.run([CLI,*args],cwd=folder,input=answer,text=True,capture_output=True,timeout=15)
      assert p.returncode==expected,(args,p.stdout,p.stderr)
      print('PASS installed offline',args[0])
    assert not skip.exists()
