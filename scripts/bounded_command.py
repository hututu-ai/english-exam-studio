#!/usr/bin/env python3
"""Run an approved dependency command with a deadline; never installs by itself."""
import argparse, os, signal, subprocess, sys
from platform_tools import force_utf8

def run(command, seconds=120):
    if not command:raise ValueError('缺少命令；在 -- 后传入已获准执行的命令及参数')
    options={'start_new_session':True} if os.name!='nt' else {'creationflags':subprocess.CREATE_NEW_PROCESS_GROUP}
    p=subprocess.Popen(command,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                       text=True,encoding='utf-8',errors='replace',**options)
    try:
        out,err=p.communicate(timeout=seconds)
        return p.returncode,out,err
    except subprocess.TimeoutExpired:
        if os.name=='nt':
            # Only the process tree created by this invocation; no administrator prompt.
            subprocess.run(['taskkill','/PID',str(p.pid),'/T','/F'],capture_output=True,timeout=10)
        else:
            try:os.killpg(p.pid,signal.SIGKILL)
            except ProcessLookupError:pass
        try:out,err=p.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            p.kill();out,err=p.communicate(timeout=5)
        return 124,out,err+f'\n依赖命令超过 {seconds:g} 秒，已终止；停止换源重试，继续无需该依赖的板块。'

def main():
    force_utf8();p=argparse.ArgumentParser()
    p.add_argument('--seconds',type=float,default=120);p.add_argument('command',nargs=argparse.REMAINDER)
    a=p.parse_args()
    if not 0<a.seconds<=180:p.error('超时范围为 0–180 秒')
    command=a.command[1:] if a.command[:1]==['--'] else a.command
    try:code,out,err=run(command,a.seconds)
    except (OSError,ValueError,subprocess.SubprocessError) as e:p.exit(1,f'ERROR: {e}\n')
    print(out,end='');print(err,end='',file=sys.stderr);return code
if __name__=='__main__':raise SystemExit(main())
