"""Publish only after required native gates; refuse to replace any release/tag."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]
REPO='arkosom/stasrift'
TAG='v1.0.1'

def gh(*args):
    return subprocess.check_output(['gh',*args],text=True).strip()

def old_release():
    r=json.loads(gh('api',f'repos/{REPO}/releases/tags/v1.0.0'))
    return {'id':r['id'],'tag_name':r['tag_name'],'body':r['body'],'target_commitish':r['target_commitish'],
            'assets':[(a['id'],a['name'],a['size'],a.get('digest')) for a in r['assets']],
            'ref':json.loads(gh('api',f'repos/{REPO}/git/ref/tags/v1.0.0'))['object']}

assert os.environ.get('GITHUB_REPOSITORY')==REPO
assert os.environ.get('GITHUB_REF')=='refs/heads/main'
assert os.environ.get('GITHUB_EVENT_NAME')=='push'
before=old_release()
for endpoint in [f'repos/{REPO}/releases/tags/{TAG}',f'repos/{REPO}/git/ref/tags/{TAG}']:
    result=subprocess.run(['gh','api',endpoint],capture_output=True,text=True)
    if result.returncode==0:
        raise SystemExit('Release/tag exists; refusing to overwrite. Inspect existing state manually.')
    assert '404' in result.stderr, result.stderr
names=['stasrift-1.0.1-py3-none-any.whl','stasrift-1.0.1.tar.gz','stasrift-1.0.1-source.zip','SHA256SUMS-1.0.1.txt']
original={n:hashlib.sha256((ROOT/'dist'/n).read_bytes()).hexdigest() for n in names}
sha=os.environ['GITHUB_SHA']
gh('api','--method','POST',f'repos/{REPO}/git/refs','-f',f'ref=refs/tags/{TAG}','-f',f'sha={sha}')
gh('release','create',TAG,'--repo',REPO,'--verify-tag','--draft','--title','Stasrift v1.0.1 — maintenance release',
   '--notes-file',str(ROOT/'RELEASE_NOTES_1.0.1.md'),*[str(ROOT/'dist'/n) for n in names])
with tempfile.TemporaryDirectory() as folder:
    gh('release','download',TAG,'--repo',REPO,'--dir',folder)
    assert {n:hashlib.sha256((Path(folder)/n).read_bytes()).hexdigest() for n in names}==original
assert old_release()==before, 'Original v1.0.0 changed; stop before publication'
gh('release','edit',TAG,'--repo',REPO,'--draft=false','--latest')
with tempfile.TemporaryDirectory() as folder:
    gh('release','download',TAG,'--repo',REPO,'--dir',folder)
    assert {n:hashlib.sha256((Path(folder)/n).read_bytes()).hexdigest() for n in names}==original
    subprocess.run(['python','-m','pip','install','--force-reinstall','--no-deps',str(Path(folder)/names[0])],check=True)
    subprocess.run(['python',str(ROOT/'tests/helpers/installed_smoke.py'),'stasrift',str(ROOT)],check=True)
assert old_release()==before
print(json.dumps({'release':f'https://github.com/{REPO}/releases/tag/{TAG}','commit':sha,'tag':TAG,'checksums':original,'v1.0.0':'unchanged','published_download_install_cli':'PASS'},indent=2))
