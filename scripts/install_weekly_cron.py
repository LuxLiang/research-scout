"""Install one explicitly authorized user cron entry, preserving other jobs."""
from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
import shlex
import subprocess
import sys
from zoneinfo import ZoneInfo


def prepare(workspace: Path, python: str, weekday: int, hour: int, minute: int, timezone: str):
    workspace=workspace.expanduser().resolve()
    if not (workspace/'tracking-profile.json').is_file():
        raise ValueError('Create and validate tracking-profile.json before scheduling')
    if any(c in str(workspace) for c in '\n\r%'):
        raise ValueError('Cron workspace path cannot contain newline or percent characters')
    zone=ZoneInfo(timezone)
    if datetime.now().astimezone().utcoffset()!=datetime.now(zone).utcoffset():
        raise ValueError('Host cron timezone differs; convert the schedule before installing')
    runner=workspace/'run-weekly.sh'
    script='\n'.join([
        '#!/bin/sh','set -eu',f'cd {shlex.quote(str(workspace))}',
        'exec '+shlex.join([str(Path(python).resolve()),'-u','-m','research_scout.cli',
            '--workspace',str(workspace),'weekly','--profile',str(workspace/'tracking-profile.json')]),''])
    marker=f'# research-scout-weekly:{workspace}'
    command=f'{minute} {hour} * * {weekday} {shlex.quote(str(runner))} >> {shlex.quote(str(workspace/"weekly-cron.log"))} 2>&1 {marker}'
    return runner,script,marker,command


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace',required=True,type=Path)
    parser.add_argument('--python',default=sys.executable)
    parser.add_argument('--weekday',type=int,choices=range(7),default=1)
    parser.add_argument('--hour',type=int,choices=range(24),default=9)
    parser.add_argument('--minute',type=int,choices=range(60),default=0)
    parser.add_argument('--timezone',default='Asia/Shanghai')
    parser.add_argument('--print-only',action='store_true')
    args=parser.parse_args()
    runner,script,marker,entry=prepare(args.workspace,args.python,args.weekday,args.hour,args.minute,args.timezone)
    if args.print_only:
        print(entry)
        return
    current=subprocess.run(['crontab','-l'],text=True,capture_output=True)
    if current.returncode and 'no crontab for' not in current.stderr:
        raise RuntimeError('Cannot read existing crontab; no schedule was changed')
    lines=[line for line in current.stdout.splitlines() if not line.rstrip().endswith(marker)]
    runner.write_text(script,encoding='utf-8')
    runner.chmod(0o700)
    proposed='\n'.join(lines+[entry])+'\n'
    subprocess.run(['crontab','-'],input=proposed,text=True,check=True,capture_output=True)
    installed=subprocess.run(['crontab','-l'],text=True,capture_output=True,check=True).stdout
    if entry not in installed.splitlines():
        raise RuntimeError('Cron verification failed')
    print(f'Installed: weekday {args.weekday}, {args.hour:02}:{args.minute:02} {args.timezone}')
    print(f'Workspace: {runner.parent}')
    print(f'Report: {runner.parent/"reports/latest.md"}')


if __name__=='__main__':
    main()
