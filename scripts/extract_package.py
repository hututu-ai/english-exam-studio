#!/usr/bin/env python3
r"""Prepare (or apply) a skill update from a downloaded release ZIP.

docs/UPDATE.md tells the agent to verify SHA256SUMS, extract safely (no absolute paths, no
`..`, no symlinks, no hidden files), run check_install, and only then replace files — while
warning about the teacher's own edits. Doing that by hand is where updates go wrong, and on
Windows a half-copied skill is hard to recover. This tool does exactly those steps and reports
before it changes anything.

  python3 scripts/extract_package.py UPDATE.zip --sha256sums SHA256SUMS.txt --out 新版本目录
  python3 scripts/extract_package.py UPDATE.zip --out 新版本目录 --compare-to 现有技能目录
  python3 scripts/extract_package.py UPDATE.zip --out 新版本目录 --apply --backup 备份目录

路径一律用普通目录名或绝对路径（Windows 上写 `"D:\新版本"` 并加双引号即可），脚本不依赖 `/tmp` 或任何 POSIX 目录。

Nothing is replaced unless --apply is given, and --apply refuses to run without --backup.
"""
import argparse,hashlib,json,os,shutil,stat,sys,zipfile
from pathlib import Path,PurePosixPath
from platform_tools import force_utf8

SIZE_CAP=2_000_000_000

def sha256_file(path):
    h=hashlib.sha256()
    with open(path,'rb') as handle:
        for block in iter(lambda:handle.read(1<<20),b''):h.update(block)
    return h.hexdigest()

def parse_sums(path):
    table={}
    for line in Path(path).read_text(encoding='utf-8',errors='replace').splitlines():
        parts=line.replace('*',' ').split()
        if len(parts)>=2 and len(parts[0])==64:table[parts[-1].lstrip('./')]=parts[0].lower()
    return table

def verify_archive(archive,sums_path):
    actual=sha256_file(archive)
    result={'archive':str(archive),'sha256':actual,'expected':None,'status':'not_checked'}
    if not sums_path:return result
    table=parse_sums(sums_path)
    expected=table.get(Path(archive).name.lower()) or table.get(Path(archive).name)
    if expected is None:
        result.update(status='missing_entry',expected=None);return result
    result['expected']=expected
    result['status']='passed' if expected==actual else 'mismatch'
    return result

def safe_parts(name):
    """返回 (是否可用, 拒绝原因)。与 prepare_whisper 的规则一致，但会报出而不是静默跳过。"""
    pure=PurePosixPath(name)
    if pure.is_absolute():return False,'绝对路径'
    if '..' in pure.parts:return False,'试图跳出解压目录（..）'
    if '\\' in name:return False,'含反斜杠的可疑路径'
    if ':' in name:return False,'含盘符或 ADS 冒号'
    if not pure.parts:return False,'空路径'
    if any(part.startswith('.') or part=='__MACOSX' for part in pure.parts):return False,'隐藏文件或 __MACOSX 残留'
    return True,None

def safe_extract(archive,out):
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    rejected=[];written=0;total=0
    with zipfile.ZipFile(archive) as bundle:
        total=sum(info.file_size for info in bundle.infolist())
        if total>SIZE_CAP:raise ValueError('压缩包解压后过大，拒绝解压')
        for info in bundle.infolist():
            ok,reason=safe_parts(info.filename)
            if not ok:
                rejected.append({'entry':info.filename,'reason':reason});continue
            if stat.S_ISLNK(info.external_attr>>16):
                rejected.append({'entry':info.filename,'reason':'符号链接'});continue
            target=out/info.filename
            if info.is_dir():target.mkdir(parents=True,exist_ok=True);continue
            target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes(bundle.read(info));written+=1
    return {'written':written,'uncompressed_bytes':total,'rejected':rejected}

def package_root(directory):
    """ZIP 可能是平铺的，也可能多包一层目录；找到含 SKILL.md 或 VERSION 的那层。"""
    root=Path(directory)
    if (root/'SKILL.md').is_file() or (root/'VERSION').is_file():return root
    candidates=[p for p in root.iterdir() if p.is_dir() and ((p/'SKILL.md').is_file() or (p/'VERSION').is_file())]
    if len(candidates)==1:return candidates[0]
    return root

def install_status(root):
    try:
        from check_install import check
    except ImportError:
        return {'status':'unknown','errors':['缺少 scripts/check_install.py']}
    return check(root)

def compare(current,extracted):
    current=Path(current);extracted=Path(extracted)
    try:
        old=json.loads((current/'install-manifest.json').read_text(encoding='utf-8')).get('files',{})
        new=json.loads((extracted/'install-manifest.json').read_text(encoding='utf-8')).get('files',{})
    except (OSError,ValueError) as error:
        return {'status':'cannot_compare','reason':str(error)}
    added=[];changed=[];same=[];modified=[]
    for name,digest in sorted(new.items()):
        if name not in old:added.append(name);continue
        (same if old[name]==digest else changed).append(name)
        on_disk=current/name
        if on_disk.is_file() and sha256_file(on_disk)!=old[name]:modified.append(name)
    removed=[name for name in sorted(old) if name not in new]
    return {'status':'compared','added':added,'changed':changed,'unchanged':len(same),'removed':removed,
            'locally_modified':modified,
            'note':'locally_modified 是你自己改过、与官方清单不一致的文件：更新前先备份；apply 会用新版覆盖它们。'}

def update_sources(extracted):
    """这次更新会覆盖哪些文件（跳过隐藏文件与目录）。"""
    sources=[]
    for source in sorted(Path(extracted).rglob('*')):
        if not source.is_file() or source.is_symlink():continue
        relative=source.relative_to(extracted)
        if any(part.startswith('.') for part in relative.parts):continue
        sources.append((source,relative))
    return sources

def can_write(path):
    """真的试一下能不能写：只读属性与"被别的程序占用"都会在这里暴露。

    Windows 上 OneDrive/杀毒/Office/WPS 正打开着的文件复制到一半会失败，留下"改了一半"的技能目录；
    先预检就能在**动手前**拒绝，而不是事后收拾。
    """
    path=Path(path)
    if path.exists():
        try:
            with open(path,'r+b'):pass
            return True,None
        except OSError as error:
            return False,str(error)
    parent=path.parent
    while not parent.exists() and parent!=parent.parent:parent=parent.parent
    if not os.access(parent,os.W_OK):return False,f'目录不可写：{parent}'
    return True,None

def apply_update(current,extracted,backup):
    current=Path(current).resolve();extracted=Path(extracted).resolve();backup=Path(backup).resolve()
    if not backup:raise ValueError('--apply 必须同时给出 --backup，先把现有技能目录完整备份')
    if backup==current or current in backup.parents:raise ValueError('备份目录不能与技能目录重叠')
    if backup.exists():raise ValueError(f'备份目录已存在：{backup}（换一个，避免覆盖上一次备份）')
    sources=update_sources(extracted)
    # 预检：有任何一个目标不可写就先拒绝，此时**一个文件都没动**。
    blocked=[]
    for source,relative in sources:
        ok,reason=can_write(current/relative)
        if not ok:blocked.append(f'{relative}（{reason}）')
    if blocked:
        raise ValueError(f'有 {len(blocked)} 个文件现在不能写入：'+'；'.join(blocked[:5])
                         +'。多半是被 OneDrive/网盘同步、杀毒或 Office/WPS 占用，或设成了只读；'
                          '请先关闭占用它的程序（或去掉只读属性）再重跑——现在没有改动任何文件')
    shutil.copytree(current,backup)
    copied=[]
    try:
        for source,relative in sources:
            target=current/relative
            target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(source,target);copied.append(relative)
    except OSError as error:
        # 复制中途失败：用刚做的备份把已经覆盖过的文件逐个恢复，技能目录保持"更新前"的可用状态。
        # 注意先把失败的文件名记下来：下面的回滚循环会重新绑定变量，直接引用会报成另一个文件名。
        failed=str(relative)
        restored=[];not_restored=[]
        for item in copied:
            old=backup/item
            try:
                if old.exists():shutil.copy2(old,current/item);restored.append(str(item))
                else:not_restored.append(str(item))
            except OSError:not_restored.append(str(item))
        detail=(f'；另有 {len(not_restored)} 个文件没能回滚（{"、".join(not_restored[:3])}），'
                f'请从备份 {backup} 手动复制回去') if not_restored else ''
        raise ValueError(f'复制 {failed} 时失败：{error}；已把本次改动过的 {len(restored)} 个文件恢复成更新前的内容'
                         f'（技能目录仍可用），完整备份在 {backup}{detail}。请关闭占用该文件的程序后重跑')
    return {'backup':str(backup),'copied':len(copied),'files':[str(item) for item in copied[:40]]}

def main():
    force_utf8()
    parser=argparse.ArgumentParser(description='校验、安全解压并比较技能更新包（默认不改动现有安装）')
    parser.add_argument('archive')
    parser.add_argument('--sha256sums',help='同版本 SHA256SUMS.txt，用于核对压缩包指纹')
    parser.add_argument('--out',required=True,help='解压到哪个临时目录')
    parser.add_argument('--compare-to',help='现有技能目录：列出新增/变更/删除/被本地改过的文件')
    parser.add_argument('--apply',action='store_true',help='确认后用新版覆盖现有技能目录')
    parser.add_argument('--backup',help='--apply 时必填：现有目录的备份位置')
    args=parser.parse_args()
    report={}
    try:
        report['verification']=verify_archive(args.archive,args.sha256sums)
        if report['verification']['status']=='mismatch':raise ValueError('压缩包指纹与 SHA256SUMS.txt 不一致，不要使用这个文件')
        if report['verification']['status']=='missing_entry':raise ValueError('SHA256SUMS.txt 里没有这个压缩包的条目，无法核对')
        report['extract']=safe_extract(args.archive,args.out)
        if report['extract']['rejected']:raise ValueError(f"压缩包含 {len(report['extract']['rejected'])} 个被拒绝的条目（见 extract.rejected），不要直接使用")
        root=package_root(args.out);report['package_root']=str(root)
        report['installation']=install_status(root)
        if report['installation'].get('status')!='complete':
            raise ValueError('解压后的包不是完整安装（check_install 未通过），先按 docs/UPDATE.md 重新获取完整包')
        if args.compare_to:report['comparison']=compare(args.compare_to,root)
        if args.apply:
            if not args.backup:raise ValueError('--apply 必须同时给出 --backup')
            report['applied']=apply_update(args.compare_to or Path(__file__).resolve().parents[1],root,args.backup)
    except (OSError,ValueError,KeyError,zipfile.BadZipFile,json.JSONDecodeError) as error:
        report['status']='failed';report['error']=str(error)
        print(json.dumps(report,ensure_ascii=False,indent=2));return 1
    report['status']='ok'
    print(json.dumps(report,ensure_ascii=False,indent=2))
    return 0

if __name__=='__main__':raise SystemExit(main())
