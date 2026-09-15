#!/usr/bin/env python3
"""One WhisperX environment probe/preparation path for Windows and macOS; CPU by default."""
import argparse,json,os,shutil,sys,time
from pathlib import Path
from bounded_command import run
from platform_tools import runtime_root
VERSION='3.8.6'

def python_in(root):return Path(root)/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
def candidates(explicit=None):
    values=[explicit,os.environ.get('EXAM_WHISPERX_PYTHON'),str(python_in(runtime_root()/'whisperx-env')),sys.executable]
    return list(dict.fromkeys(str(Path(x).absolute()) for x in values if x and Path(x).is_file()))

def probe(python=None):
    attempts=[]
    for exe in candidates(python):
        code,out,err=run([exe,'-c',"import json,importlib.metadata,whisperx,torch,nltk;print(json.dumps({'version':importlib.metadata.version('whisperx'),'torch':torch.__version__}))"],40)
        if code==0:
            try:
                data=json.loads(out.strip().splitlines()[-1]);return {'status':'package_ready','python':exe,**data,'models':'not_probed','next_step':'short_audio_smoke_test','attempts':attempts}
            except (ValueError,IndexError):pass
        attempts.append({'python':exe,'exit_code':code,'error':'环境检查未通过：'+(err.strip().splitlines()[-1] if err.strip() else '未返回有效版本信息')})
    return {'status':'needs_setup','python':None,'attempts':attempts,'next_step':'speech_runtime.py prepare（安装前需说明并授权）'}

def prepare(root,base_python=None,approved=False,seconds=120,cache=None):
    root=Path(root).resolve();python=python_in(root);existing=probe(str(python) if python.exists() else base_python)
    if existing['status']=='package_ready' and not approved:return existing
    if not approved:return {'status':'awaiting_install_approval','directory':str(root),'changes':'创建独立虚拟环境并安装 WhisperX CPU 依赖；不修改系统 Python；模型在短音频验证时按需下载','space':'依赖和模型需要数GB，取决于已有缓存','next_step':'获得安装授权后加 --install-approved'}
    base=base_python or sys.executable
    if existing['status']=='package_ready':python=Path(existing['python'])
    deadline=time.monotonic()+seconds;root.parent.mkdir(parents=True,exist_ok=True)
    commands=[]
    if existing['status']!='package_ready' and not python.exists():commands.append([base,'-m','venv',str(root)])
    if existing['status']!='package_ready' and os.name=='nt':commands.append([str(python),'-m','pip','install','--disable-pip-version-check','torch==2.8.0','torchaudio==2.8.0','--index-url','https://download.pytorch.org/whl/cpu'])
    if existing['status']!='package_ready':commands.append([str(python),'-m','pip','install','--disable-pip-version-check','whisperx=='+VERSION])
    commands.append([str(python),str(Path(__file__).with_name('speech_worker.py')),'--prepare-resources','--cache',str(cache or root.parent/'speech-cache')])
    for cmd in commands:
        remaining=deadline-time.monotonic()
        if remaining<=0:return {'status':'setup_timeout','directory':str(root),'next_step':'保存当前环境，向老师报告；获准延长后继续，不自动换源'}
        code,out,err=run(cmd,remaining)
        if code: return {'status':'setup_failed' if code!=124 else 'setup_timeout','directory':str(root),'command':cmd,'stderr':err,'stdout':out,'next_step':'停止安装并报告实际错误，不使用管理员命令'}
    return probe(str(python))

def choose(python=None,timed_transcript=False):
    if timed_transcript:return {'backend':'timed_transcript','status':'verify_source_fingerprint','next_step':'复用同源时间字幕，跳过安装'}
    result=probe(python)
    return {'backend':'whisperx','status':result['status'],'runtime':result,'next_step':result['next_step']}

def main():
    from platform_tools import force_utf8
    force_utf8();p=argparse.ArgumentParser();p.add_argument('command',choices=['probe','prepare']);p.add_argument('--python');p.add_argument('--root',default=str(runtime_root()/'whisperx-env'));p.add_argument('--cache');p.add_argument('--seconds',type=float,default=120);p.add_argument('--install-approved',action='store_true');a=p.parse_args()
    if not 0<a.seconds<=1800:p.error('时间预算须为1–1800秒')
    result=probe(a.python) if a.command=='probe' else prepare(a.root,a.python,a.install_approved,a.seconds,a.cache)
    print(json.dumps(result,ensure_ascii=False,indent=2));return 0 if result['status']=='package_ready' else 2
if __name__=='__main__':raise SystemExit(main())
