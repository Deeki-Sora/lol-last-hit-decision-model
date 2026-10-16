"""Verify archived bytes, frozen scores and case video metadata."""
from pathlib import Path
import argparse
import csv
import hashlib
import json
import subprocess
import sys
import re

ROOT=Path(__file__).resolve().parents[1]
CASE=ROOT/'example/yasuo_vs_veigar'


def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):
            h.update(block)
    return h.hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--write-manifest',action='store_true',help='Create a new integrity manifest; never replace an existing one')
    p.add_argument('--replace-manifest',action='store_true',help='Explicitly replace the release integrity manifest, preserving fixed case snapshots')
    p.add_argument('--examples',action='store_true',help='Also replay frozen reference scores and probe reference videos')
    args=p.parse_args()
    manifest=ROOT/'repository_manifest.json'
    if args.write_manifest:
        if manifest.exists() and not args.replace_manifest:
            raise SystemExit('An integrity manifest already exists; use a new repository release')
        files={f.relative_to(ROOT).as_posix():sha(f) for f in sorted(ROOT.rglob('*'))
            if f.is_file() and not any(part in {'.git','.venv','__pycache__','runs'} for part in f.relative_to(ROOT).parts)
            and ('input_videos' not in f.relative_to(ROOT).parts or f.name=='.gitkeep')
            and f!=manifest and f.suffix!='.pyc'}
        manifest.write_text(json.dumps({'sha256':files},ensure_ascii=False,indent=2),encoding='utf-8')
    content=json.loads(manifest.read_text(encoding='utf-8'))
    for name,expected in content['sha256'].items():
        f=ROOT/name
        if not f.is_file() or sha(f)!=expected:
            raise SystemExit('Integrity mismatch: '+name)
    documents=json.loads((ROOT/'framework_documents.json').read_text(encoding='utf-8'))
    english=ROOT/documents['en']
    chinese=ROOT/documents['zh']
    en=english.read_text(encoding='utf-8-sig');zh=chinese.read_text(encoding='utf-8-sig')
    if re.search(r'[\u4e00-\u9fff]',en):
        raise SystemExit('Untranslated Chinese text in the English model')
    def headings(text):
        return re.findall(r'(?m)^#{1,4} (\d+(?:\.\d+)*)\.? ',text)
    if headings(en)!=headings(zh):
        raise SystemExit('Bilingual model section numbers differ')
    def formulas(text):
        blocks=re.findall(r'\\\[.*?\\\]',text,re.S)
        return [re.sub(r'\s+','',re.sub(r'\\text\{[^{}]*\}',lambda m:r'\text{LABEL}',b)) for b in blocks]
    if formulas(en)!=formulas(zh):
        raise SystemExit('Bilingual displayed formulas differ beyond localized text labels')
    if args.examples:
        score=CASE/'reevaluation_v091/score_intervals.py'
        first=subprocess.check_output([sys.executable,str(score)],cwd=ROOT)
        second=subprocess.check_output([sys.executable,str(score)],cwd=ROOT)
        if first!=second:raise SystemExit('Score replay was not deterministic')
        for file in [CASE/'media/A_merged.mp4',CASE/'media/originals/B.mp4']:
            probe=json.loads(subprocess.check_output(['ffprobe','-v','quiet','-show_format','-show_streams','-of','json',str(file)]))
            if not any(s['codec_type']=='video' for s in probe['streams']):raise SystemExit('No video stream: '+str(file))
            print(file.relative_to(ROOT).as_posix(),probe['format']['duration'],'seconds')
        print('PASS: two identical frozen-score replays; reference media streams valid.')
    print('PASS:',len(content['sha256']),'file hashes; bilingual sections/formulas aligned.')


if __name__=='__main__':
    main()
