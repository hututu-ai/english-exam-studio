#!/usr/bin/env python3
"""Plan/prepare a user-local whisper.cpp runtime and base model. Never uses sudo or modifies PATH."""
import argparse, hashlib, json, os, platform, re, shutil, stat, subprocess, sys, tarfile, tempfile, time, urllib.request, zipfile
from pathlib import Path, PurePosixPath
from platform_tools import force_utf8, whisper_bin
from bounded_command import run as run_bounded
REPO='https://api.github.com/repos/ggml-org/whisper.cpp'

def cache_root():
    return Path(os.environ.get('LOCALAPPDATA',Path.home()/'AppData/Local'))/'english-exam-studio' if os.name=='nt' else Path.home()/'.cache/english-exam-studio'

def remaining(deadline):
    left=deadline-time.monotonic()
    if left<=0:raise TimeoutError('依赖准备已达到时间预算；可由老师选择继续下载，不会自动改成已完成精听')
    return left

def fetch(url,target=None,deadline=None):
    deadline=deadline or time.monotonic()+120
    req=urllib.request.Request(url,headers={'User-Agent':'english-exam-studio-setup'})
    with urllib.request.urlopen(req,timeout=min(15,remaining(deadline))) as r:
        if target:
            part=Path(str(target)+'.part')
            with part.open('wb') as f:
                while True:
                    remaining(deadline);block=r.read(1<<18)
                    if not block:break
                    f.write(block)
            part.replace(target);return target
        data=r.read(4<<20);remaining(deadline);return json.loads(data)

def safe_name(name):
    p=PurePosixPath(name)
    if p.is_absolute() or '..' in p.parts or '\\' in name or ':' in name:raise ValueError('Unsafe archive path: '+name)
    return bool(p.parts) and all(not x.startswith('.') and x!='__MACOSX' for x in p.parts)

def unpack(archive,dest):
    dest=Path(dest);dest.mkdir(parents=True,exist_ok=True)
    if zipfile.is_zipfile(archive):
        with zipfile.ZipFile(archive) as z:
            if sum(x.file_size for x in z.infolist())>2_000_000_000:raise ValueError('Archive unexpectedly large')
            for info in z.infolist():
                if not safe_name(info.filename) or stat.S_ISLNK(info.external_attr>>16):continue
                p=dest/info.filename
                if info.is_dir():p.mkdir(parents=True,exist_ok=True)
                else:p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(z.read(info))
    else:
        with tarfile.open(archive) as t:
            members=t.getmembers()
            if sum(x.size for x in members)>2_000_000_000:raise ValueError('Archive unexpectedly large')
            for info in members:
                if not safe_name(info.name) or not info.isfile():continue
                p=dest/info.name;p.parent.mkdir(parents=True,exist_ok=True)
                with t.extractfile(info) as f:p.write_bytes(f.read())
                if info.mode&0o111:p.chmod(0o700)

def run(command,deadline):
    command=list(map(str,command));code,out,err=run_bounded(command,remaining(deadline))
    if code:raise RuntimeError(json.dumps({'command':command,'exit_code':code,'stderr':err,'stdout':out},ensure_ascii=False))
    return out+err

def windows_asset(releases,machine):
    names={'amd64':'whisper-bin-x64.zip','x86_64':'whisper-bin-x64.zip','arm64':'whisper-bin-arm64.zip','aarch64':'whisper-bin-arm64.zip'}
    expected=names.get(machine.lower())
    if not expected:raise ValueError('Unsupported Windows architecture: '+machine)
    for release in releases:
        if release.get('prerelease') or release.get('draft'):continue
        for a in release.get('assets',[]):
            if a['name']==expected and a.get('digest','').startswith('sha256:'):return release,a
    raise ValueError('官方发布中没有找到与架构匹配且有 SHA256 的便携包；请查看官方 Release，不猜测链接')

def prepare(root,install=False,seconds=120):
    root=Path(root).expanduser().resolve();exe=whisper_bin();model=root/'models/ggml-base.bin'
    report={'status':'plan','root':str(root),'family':platform.system(),'machine':platform.machine(),'existing_executable':exe,
      'model':'ggml-base.bin（约 142 MiB，多语言）','scope':'仅用户目录，不改系统 PATH、不安装 Python、不使用管理员命令','budget_seconds':seconds}
    if not install:return report
    deadline=time.monotonic()+seconds
    try:
        cached=json.loads((root/'runtime.json').read_text(encoding='utf-8'))
        binary=Path(cached['whisper_bin']);weight=Path(cached['whisper_model'])
        if binary.is_file() and weight.is_file() and hashlib.sha256(weight.read_bytes()).hexdigest()==cached['model_sha256']:
            run([binary,'--help'],deadline);return {**cached,'status':'ready_for_smoke_test','reused':True}
    except (OSError,ValueError,KeyError,RuntimeError):pass
    root.mkdir(parents=True,exist_ok=True)
    # Reuse an executable only if it actually identifies itself as the whisper CLI.
    if exe:
        try:
            helptext=run([exe,'--help'],deadline)
            if '-m ' not in helptext or '-f ' not in helptext:exe=None
        except (RuntimeError,OSError):exe=None
    if not exe:
        with tempfile.TemporaryDirectory(prefix='whisper-setup-',dir=root) as temp:
            temp=Path(temp)
            if os.name=='nt':
                release,asset=windows_asset(fetch(REPO+'/releases?per_page=15',deadline=deadline),platform.machine())
                archive=fetch(asset['browser_download_url'],temp/'runtime.zip',deadline)
                if hashlib.sha256(archive.read_bytes()).hexdigest()!=asset['digest'][7:]:raise ValueError('Whisper archive checksum mismatch')
                tag=release['tag_name']
                if not re.fullmatch(r'[A-Za-z0-9_.-]{1,80}',tag):raise ValueError('Invalid release tag')
                target=root/('whisper-'+tag)
                if target.exists():raise ValueError('目标运行时已存在但未识别为可用；保留旧目录，请诊断而非覆盖')
                unpack(archive,target);found=list(target.rglob('whisper-cli.exe'))
            else:
                cmake=shutil.which('cmake');compiler=shutil.which('c++') or shutil.which('clang++')
                if not cmake or not compiler:raise ValueError('缺少 CMake/C++ 编译工具。请按安装说明在授权后准备；未安装系统工具。')
                release=fetch(REPO+'/releases/latest',deadline=deadline)
                archive=fetch(release['tarball_url'],temp/'source.tar.gz',deadline);unpack(archive,temp/'source')
                source=next((p for p in (temp/'source').iterdir() if (p/'CMakeLists.txt').is_file()),None)
                if source is None:raise ValueError('官方源码不完整')
                tag=release['tag_name']
                if not re.fullmatch(r'[A-Za-z0-9_.-]{1,80}',tag):raise ValueError('Invalid release tag')
                target=root/('whisper-'+tag)
                if target.exists():raise ValueError('运行时目录已存在但未识别为可用，保留以便诊断')
                shutil.copytree(source,target)
                run([cmake,'-S',target,'-B',target/'build','-DCMAKE_BUILD_TYPE=Release','-DGGML_METAL=OFF','-DWHISPER_BUILD_TESTS=OFF'],deadline)
                run([cmake,'--build',target/'build','--config','Release','--target','whisper-cli','-j',str(min(4,os.cpu_count() or 1))],deadline)
                found=[p for p in (target/'build').rglob('whisper-cli') if p.is_file()]
            if len(found)!=1:raise ValueError('未找到唯一的 whisper-cli 程序')
            exe=str(found[0].resolve());run([exe,'--help'],deadline)
    # Resolve immutable model revision and LFS digest from the upstream model repository.
    meta=fetch('https://huggingface.co/api/models/ggerganov/whisper.cpp?blobs=true',deadline=deadline)
    entry=next((x for x in meta.get('siblings',[]) if x['rfilename']==model.name),None)
    digest=(entry or {}).get('lfs',{}).get('sha256')
    if not digest or not re.fullmatch('[0-9a-f]{64}',digest):raise ValueError('官方模型缺少可核对的 SHA256')
    model.parent.mkdir(parents=True,exist_ok=True)
    if not model.is_file() or hashlib.sha256(model.read_bytes()).hexdigest()!=digest:
        staged=model.with_suffix('.download');fetch('https://huggingface.co/ggerganov/whisper.cpp/resolve/'+meta['sha']+'/'+model.name,staged,deadline)
        if hashlib.sha256(staged.read_bytes()).hexdigest()!=digest:raise ValueError('模型校验失败，不能开始转写')
        staged.replace(model)
    result={**report,'status':'ready_for_smoke_test','whisper_bin':exe,'whisper_model':str(model),'model_sha256':digest,
      'next':'先用真实短音频验证转写内容和时间戳，再处理整卷；设置仅当前进程 WHISPER_BIN、WHISPER_MODEL。'}
    (root/'runtime.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');return result
if __name__=='__main__':
    force_utf8();p=argparse.ArgumentParser();p.add_argument('--root',default=str(cache_root()));p.add_argument('--install',action='store_true');p.add_argument('--seconds',type=int,default=120);a=p.parse_args()
    try:
        if not 15<=a.seconds<=3600:raise ValueError('时间预算范围 15–3600 秒；延长前取得老师同意')
        print(json.dumps(prepare(a.root,a.install,a.seconds),ensure_ascii=False,indent=2))
    except (OSError,ValueError,RuntimeError,TimeoutError,subprocess.SubprocessError) as e:
        print(json.dumps({'status':'setup_failed','error':str(e),'root':a.root,'message':'未完成依赖准备；保留已完成内容，说明失败原因后选择继续安装或其他识别方案。'},ensure_ascii=False),file=sys.stderr);raise SystemExit(1)
