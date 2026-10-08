"""Run the unchanged 91 regressions against isolated installed distributions."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import venv

ROOT=Path(__file__).resolve().parents[1]

def run(args, cwd=None):
    subprocess.run(list(map(str,args)),cwd=cwd,check=True)

with tempfile.TemporaryDirectory() as folder:
    base=Path(folder)
    for kind,artifact in [('wheel','stasrift-1.0.1-py3-none-any.whl'),('sdist','stasrift-1.0.1.tar.gz')]:
        env=base/kind
        venv.EnvBuilder(with_pip=True).create(env)
        py=env/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
        cli=env/('Scripts/stasrift.exe' if os.name=='nt' else 'bin/stasrift')
        run([py,'-m','pip','install','pytest','PyYAML','setuptools>=77','wheel'])
        run([py,'-m','pip','install','--no-deps','--no-build-isolation','--ignore-installed',ROOT/'dist'/artifact])
        work=base/(kind+'-tests');work.mkdir()
        with tarfile.open(ROOT/'dist/stasrift-1.0.1.tar.gz') as t:
            # Members were verified by verify_artifacts.py before extraction.
            for m in t.getmembers():
                assert m.name.startswith('stasrift-1.0.1/') or m.name=='stasrift-1.0.1'
                assert '..' not in Path(m.name).parts and (m.isfile() or m.isdir())
            t.extractall(work)
        testroot=work/'stasrift-1.0.1'
        shutil.rmtree(testroot/'src')
        # Route existing subprocess tests to the installed package, not source.
        (testroot/'stasrift.py').write_text("import sys\nfrom pathlib import Path\np=Path(__file__).resolve().parent\nsys.path[:]=[x for x in sys.path if Path(x or '.').resolve()!=p]\nfrom stasrift.cli import main\nraise SystemExit(main())\n",encoding='utf-8')
        run([py,'-m','pytest','-q',testroot/'tests'],testroot)
        run([py,ROOT/'tests/helpers/installed_smoke.py',cli,testroot],base)
        print('PASS installed',kind,'91 regressions and all CLI commands',flush=True)
