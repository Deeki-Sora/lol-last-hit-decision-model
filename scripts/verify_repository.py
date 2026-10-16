"""Verify archived bytes, frozen scores and case video metadata."""
from pathlib import Path
import argparse
import csv
import hashlib
import json
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
CASE=ROOT/'case_data/yasuo_vs_veigar'


def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):
            h.update(block)
    return h.hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--write-manifest',action='store_true',help='Create a new integrity manifest; never replace an existing one')
    args=p.parse_args()
    manifest=ROOT/'repository_manifest.json'
    if args.write_manifest:
        if manifest.exists():
            raise SystemExit('An integrity manifest already exists; use a new repository release')
        files={f.relative_to(ROOT).as_posix():sha(f) for f in sorted(ROOT.rglob('*'))
            if f.is_file() and not any(part in {'.git','.venv','__pycache__'} for part in f.relative_to(ROOT).parts)
            and f!=manifest and f.suffix!='.pyc'}
        manifest.write_text(json.dumps({'sha256':files},ensure_ascii=False,indent=2),encoding='utf-8')
    content=json.loads(manifest.read_text(encoding='utf-8'))
    for name,expected in content['sha256'].items():
        f=ROOT/name
        if not f.is_file() or sha(f)!=expected:
            raise SystemExit('Integrity mismatch: '+name)
    score=CASE/'reevaluation_v091/score_intervals.py'
    first=subprocess.check_output([sys.executable,str(score)],cwd=ROOT)
    second=subprocess.check_output([sys.executable,str(score)],cwd=ROOT)
    if first!=second:
        raise SystemExit('Score replay was not deterministic')
    models=list(ROOT.glob('*Analyst_PreRelease_v0.91.md'))
    if len(models)!=2 or sha(models[0])!=sha(models[1]):
        raise SystemExit('Model aliases differ')
    for file in [CASE/'media/A_merged.mp4',CASE/'media/originals/B.mp4']:
        probe=json.loads(subprocess.check_output(['ffprobe','-v','quiet','-show_format','-show_streams','-of','json',str(file)]))
        if not any(s['codec_type']=='video' for s in probe['streams']):
            raise SystemExit('No video stream: '+str(file))
        print(file.relative_to(ROOT).as_posix(),probe['format']['duration'],'seconds')
    print('PASS:',len(content['sha256']),'file hashes; identical model aliases; two identical frozen-score replays.')


if __name__=='__main__':
    main()
