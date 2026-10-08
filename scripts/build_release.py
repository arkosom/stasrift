"""Build only explicitly approved public inputs; never build from a dirty tree."""
import hashlib
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'dist'
FILES = (ROOT / 'scripts/public-files.txt').read_text().splitlines()

def main():
    OUT.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory() as folder:
        stage = Path(folder) / 'stasrift-1.0.1'
        for name in FILES:
            assert name and not name.startswith('/') and '..' not in Path(name).parts
            dest = stage / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / name, dest)
        subprocess.run([sys.executable, '-m', 'build', '--outdir', str(OUT), str(stage)], check=True)
        with zipfile.ZipFile(OUT / 'stasrift-1.0.1-source.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
            for name in FILES:
                archive.write(stage / name, 'stasrift-1.0.1/' + name)
    subprocess.run([sys.executable, str(ROOT/'scripts/verify_artifacts.py')], check=True)
    names = ['stasrift-1.0.1-py3-none-any.whl','stasrift-1.0.1.tar.gz','stasrift-1.0.1-source.zip']
    (OUT/'SHA256SUMS-1.0.1.txt').write_text(''.join(hashlib.sha256((OUT/n).read_bytes()).hexdigest()+'  '+n+'\n' for n in names), encoding='utf-8')

if __name__ == '__main__':
    main()
