"""Video sampling and health-bar-center annotation workbench."""
from pathlib import Path
from datetime import datetime
import argparse
import json
from workbench.core import (ROOT, VIDEO_SUFFIXES, sample, seconds, calibration,
    read_json, write_json, export_tables, export_assessment, suggest_bars)
from workbench.operations import import_csv, fetch_hero_data, solve_matrix


def create(video, output, start, end, step, scale=None, proposals=False, first_wave_template=False):
    project = sample(Path(video).resolve(),Path(output).resolve(),seconds(start),seconds(end),float(step),first_wave_template)
    project['calibration'] = calibration(scale)
    write_json(Path(output)/'project.json',project)
    if proposals:
        write_json(Path(output)/'proposals.json',{
            f['id']:suggest_bars(Path(output)/f['image']) for f in project['frames']})
    export_tables(output)
    print('Created:',Path(output).resolve(),flush=True)
    return Path(output)


def interactive():
    print('LOL short-window last-hit evaluation workbench')
    print('Video timestamps are source-video times, not the game clock.')
    folder_text = input('Video folder [input_videos] (or type choose for a folder dialog): ').strip()
    if folder_text.lower() == 'choose':
        from tkinter import Tk, filedialog
        root = Tk();root.withdraw()
        folder_text = filedialog.askdirectory(title='Select video folder')
        root.destroy()
        if not folder_text:
            return
    folder = Path(folder_text or ROOT/'input_videos').expanduser().resolve()
    files = sorted(f for f in folder.iterdir() if f.is_file() and f.suffix.lower() in VIDEO_SUFFIXES)
    if not files:
        raise ValueError('No supported videos found. Put videos in input_videos or select another folder.')
    for i,file in enumerate(files,1):
        print(f'{i}: {file.name}')
    indices = [int(x.strip())-1 for x in input('Video number(s), comma separated: ').split(',')]
    if not indices or len(set(indices))!=len(indices) or any(i<0 or i>=len(files) for i in indices):
        raise ValueError('invalid video selection')
    step = float(input('Sampling interval, 0.1 to 0.5 seconds [0.3]: ') or '.3')
    scale = input('Optional pixel calibration, e.g. 189=350 [blank: pixels only]: ').strip()
    template = input('Use first-wave roster template (3 melee + 3 caster per side)? [y/N]: ').strip().lower()=='y'
    session = ROOT/'runs'/datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    workspaces=[]
    for i in indices:
        print(files[i].name)
        start=input('Clip start (seconds or MM:SS): ')
        end=input('Clip end (seconds or MM:SS): ')
        workspaces.append(create(files[i],session/f'clip_{len(workspaces)+1:02d}',start,end,step,scale,first_wave_template=template))
    from workbench.server import review
    for workspace in workspaces:
        review(workspace)


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    sub=p.add_subparsers(dest='command')
    s=sub.add_parser('sample',help='Sample one video; repeat for multiple files')
    s.add_argument('--video',required=True);s.add_argument('--output',required=True)
    s.add_argument('--start',required=True);s.add_argument('--end',required=True)
    s.add_argument('--step',type=float,default=.3);s.add_argument('--scale')
    s.add_argument('--proposals',action='store_true',help='Optional color-fill candidates; require manual full-bar-center confirmation')
    s.add_argument('--review',action='store_true')
    s.add_argument('--first-wave-template',action='store_true',help='Explicit first-wave minion roster; otherwise start with heroes only')
    r=sub.add_parser('review');r.add_argument('project');r.add_argument('--no-browser',action='store_true')
    e=sub.add_parser('export');e.add_argument('project')
    i=sub.add_parser('import-table');i.add_argument('project');i.add_argument('csv');i.add_argument('--encoding',default='utf-8-sig')
    f=sub.add_parser('fetch-data');f.add_argument('--version',required=True);f.add_argument('--blue',required=True)
    f.add_argument('--red',required=True);f.add_argument('--language',default='en_US');f.add_argument('--output',required=True)
    g=sub.add_parser('solve');g.add_argument('--matrix',required=True);g.add_argument('--output',required=True)
    gd=sub.add_parser('game-draft',help='Create an unverified optional planning task from a chosen observation')
    gd.add_argument('project');gd.add_argument('--frame',required=True);gd.add_argument('--output',required=True)
    gr=sub.add_parser('game-run',help='Run an explicitly enabled bounded event task; no solver required for comparison')
    gr.add_argument('project');gr.add_argument('--task',required=True)
    mt=sub.add_parser('mechanics-template');mt.add_argument('--output',required=True)
    me=sub.add_parser('estimate-probabilities');me.add_argument('--csv',required=True);me.add_argument('--output',required=True)
    args=p.parse_args(argv)
    try:
        if not args.command:
            return interactive()
        if args.command=='sample':
            workspace=create(args.video,args.output,args.start,args.end,args.step,args.scale,args.proposals,args.first_wave_template)
            if args.review:
                from workbench.server import review
                review(workspace)
        elif args.command=='review':
            from workbench.server import review
            review(args.project,not args.no_browser)
        elif args.command=='export':
            print(json.dumps(export_assessment(args.project),indent=2))
        elif args.command=='import-table':
            print(json.dumps(import_csv(args.project,args.csv,args.encoding),indent=2))
        elif args.command=='fetch-data':
            write_json(args.output,fetch_hero_data(args.version,args.blue,args.red,args.language))
            print('Base data saved. Verify effective stats, runes, items, ranks and passive state before evaluation.')
        elif args.command=='solve':
            write_json(args.output,solve_matrix(read_json(args.matrix)))
        elif args.command=='game-draft':
            from workbench.game_tools import draft
            directory=Path(args.project)
            write_json(args.output,draft(read_json(directory/'project.json'),read_json(directory/'annotations.json'),args.frame,directory))
        elif args.command=='game-run':
            from workbench.game_tools import save_run
            saved=save_run(args.project,read_json(args.task))
            print(json.dumps({'folder':saved['folder'],'status':saved['result']['status'],'effective_horizon_s':saved['result']['effective_horizon_s'],'samples':saved['result']['samples']} if 'result' in saved else saved,indent=2))
        elif args.command=='mechanics-template':
            from workbench.mechanic_observations import template
            Path(args.output).write_text(template(),encoding='utf-8-sig')
        elif args.command=='estimate-probabilities':
            from workbench.mechanic_observations import estimate
            write_json(args.output,estimate(Path(args.csv).read_text(encoding='utf-8-sig')))
    except (ValueError,OSError,KeyError,ImportError) as error:
        p.exit(2,f'Error: {error}\n')


if __name__=='__main__':
    main()
