"""Merge A1/A2 without the overlapping A1 tail; preserve original sources."""
from pathlib import Path
import argparse
import csv
import json
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
CASE = ROOT / 'case_data/yasuo_vs_veigar'


def merge(force=False):
    manifest = json.loads((CASE/'media/source_manifest.json').read_text(encoding='utf-8'))
    paths = {s['id']: ROOT/s['repository_path'] for s in manifest['sources']}
    cut = manifest['a_merge']['A1_end_video_s']
    out = CASE/'media/A_merged.mp4'
    if out.exists() and not force:
        print('Merged video already exists:', out.relative_to(ROOT))
        return
    if not shutil.which('ffmpeg'):
        raise SystemExit('Install FFmpeg and put ffmpeg/ffprobe on PATH.')
    filters = (
        f'[0:v:0]trim=end={cut},setpts=PTS-STARTPTS,setsar=1[v0];'
        f'[0:a:0]atrim=end={cut},asetpts=PTS-STARTPTS,aresample=48000[a0];'
        '[1:v:0]setpts=PTS-STARTPTS,setsar=1[v1];'
        '[1:a:0]asetpts=PTS-STARTPTS,aresample=48000[a1];'
        '[v0][a0][v1][a1]concat=n=2:v=1:a=1[v][a]'
    )
    subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'warning', '-y',
        '-i', str(paths['A1']), '-i', str(paths['A2']), '-filter_complex', filters,
        '-map', '[v]', '-map', '[a]', '-c:v', 'libx264', '-preset', 'fast',
        '-crf', '23', '-c:a', 'aac', '-b:a', '128k', '-movflags', '+faststart', str(out)], check=True)
    print('Created', out.relative_to(ROOT))


def combine_tables():
    cut = json.loads((CASE/'media/source_manifest.json').read_text(encoding='utf-8'))['a_merge']['A1_end_video_s']
    sources = [('A1','action_table_0_3s.csv'), ('A2','action_table_v2_0_3s.csv')]
    rows = []
    for segment, name in sources:
        with (CASE/name).open(encoding='utf-8-sig', newline='') as f:
            for n, row in enumerate(csv.DictReader(f), start=2):
                source_t = float(row['video_s'])
                if segment == 'A1' and source_t >= cut:
                    continue
                rows.append(dict(segment=segment, source_csv=name, source_csv_line=n,
                    source_video_s=source_t, merged_video_s=round(source_t+(cut if segment=='A2' else 0),3),
                    game_clock_status='legacy_label_not_verified', **row))
    rows.sort(key=lambda x: x['merged_video_s'])
    with (CASE/'A_combined_action_index.csv').open('w', encoding='utf-8-sig', newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]))
        writer.writeheader();writer.writerows(rows)
    print('Combined action index rows:',len(rows))


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--force',action='store_true',help='Re-encode the derived video')
    args=parser.parse_args()
    merge(args.force)
    combine_tables()
