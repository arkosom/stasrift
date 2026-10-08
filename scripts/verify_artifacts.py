"""Independent archive membership, source parity, and wheel RECORD validation."""
import base64
import csv
import hashlib
import io
import tarfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
approved = set((ROOT/'scripts/public-files.txt').read_text().splitlines())
assert len(approved) == len((ROOT/'scripts/public-files.txt').read_text().splitlines())
assert not any('maintenance-evidence' in p or 'REPORT_1.0.1' in p for p in approved)
prefix = 'stasrift-1.0.1/'

def check_source(members, generated):
    assert len(members) == len(set(members)), 'duplicate archive members'
    relative = {n.removeprefix(prefix): b for n,b in members.items()}
    assert all(n.startswith(prefix) for n in members), 'invalid archive root'
    assert set(relative) == approved | generated, (set(relative)-approved-generated, approved-set(relative))
    for name in approved:
        assert relative[name] == (ROOT/name).read_bytes(), name

with zipfile.ZipFile(ROOT/'dist/stasrift-1.0.1-source.zip') as z:
    assert len(z.namelist()) == len(set(z.namelist()))
    check_source({n:z.read(n) for n in z.namelist()}, set())
with tarfile.open(ROOT/'dist/stasrift-1.0.1.tar.gz') as t:
    files = [m for m in t.getmembers() if not m.isdir()]
    assert all(m.isfile() for m in files), 'links or special archive entries'
    assert len(files) == len({m.name for m in files})
    generated = {'PKG-INFO','setup.cfg','src/stasrift.egg-info/SOURCES.txt'}
    check_source({m.name:t.extractfile(m).read() for m in files}, generated)
with zipfile.ZipFile(ROOT/'dist/stasrift-1.0.1-py3-none-any.whl') as z:
    info = 'stasrift-1.0.1.dist-info/'
    runtime = {p.removeprefix('src/') for p in approved if p.startswith('src/stasrift/')}
    expected = runtime | {info+n for n in ['METADATA','WHEEL','entry_points.txt','top_level.txt','RECORD','licenses/LICENSE','licenses/NOTICE']}
    assert len(z.namelist()) == len(set(z.namelist())) and set(z.namelist()) == expected
    for name in runtime:
        assert z.read(name) == (ROOT/'src'/name).read_bytes(), name
    for name in ['LICENSE','NOTICE']:
        assert z.read(info+'licenses/'+name) == (ROOT/name).read_bytes()
    rows = list(csv.reader(io.StringIO(z.read(info+'RECORD').decode())))
    assert {r[0] for r in rows} == expected and len(rows) == len(expected)
    for name, digest, size in rows:
        if name.endswith('/RECORD'): continue
        data=z.read(name)
        assert digest == 'sha256='+base64.urlsafe_b64encode(hashlib.sha256(data).digest()).decode().rstrip('=')
        assert int(size)==len(data)
assert hashlib.sha256((ROOT/'schemas/stasrift-contract-v1.schema.json').read_bytes()).hexdigest() == 'de3624d12f46bc8778c94104d65452f3117e7d73a0393a88b6eb54a63bc2c195'
print('PASS exact archive allowlist, source parity, license, wheel RECORD, frozen schema')
