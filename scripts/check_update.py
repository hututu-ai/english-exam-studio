#!/usr/bin/env python3
"""Report the installed version and how to move to the latest release.

Prints the local VERSION, asks GitHub for the newest release tag, and explains the update steps.
Works offline: without network it still prints the local version and the manual update path.

  python3 scripts/check_update.py            # 联网核对
  python3 scripts/check_update.py --offline  # 只报本机版本
"""
import argparse,json,re,sys,urllib.error,urllib.request
from pathlib import Path

REPO='hututu-ai/english-exam-studio'
API=f'https://api.github.com/repos/{REPO}/releases/latest'
RELEASE_PAGE=f'https://github.com/{REPO}/releases/latest'

def local_version():
    root=Path(__file__).resolve().parents[1]
    version=root/'VERSION'
    return version.read_text(encoding='utf-8').strip() if version.is_file() else '未知（找不到 VERSION，可能不是完整安装包）'

def normalise(tag):
    return re.sub(r'^v','',str(tag or '').strip())

def version_key(version):
    """Comparable key so 1.0.22 is newer than 1.0.13.

    A pre-release suffix (-dev/-rc/-beta) sorts below the plain release with the same
    numbers, matching how the project numbers development builds.
    """
    text=normalise(version)
    match=re.match(r'^(\d+(?:\.\d+)*)(?:[-+._]?(dev|alpha|beta|rc|pre)\D*?(\d*))?$',text,re.I)
    if not match:return None
    numbers=tuple(([int(x) for x in match.group(1).split('.')]+[0,0,0,0])[:4])
    prerelease=(match.group(2) or '').lower()
    return (numbers,0 if prerelease else 1,int(match.group(3) or 0))

def compare(current,latest):
    """Return 'up_to_date' | 'update_available' | 'newer_than_release' | 'unknown'."""
    if not latest:return 'unknown'
    current_key,latest_key=version_key(current),version_key(latest)
    if current_key is None or latest_key is None:
        return 'up_to_date' if normalise(current)==normalise(latest) else 'update_available'
    if current_key==latest_key:return 'up_to_date'
    return 'update_available' if current_key<latest_key else 'newer_than_release'

def latest_release(timeout=10):
    request=urllib.request.Request(API,headers={'User-Agent':'english-exam-studio-check'})
    with urllib.request.urlopen(request,timeout=timeout) as response:
        data=json.loads(response.read().decode('utf-8'))
    return normalise(data.get('tag_name')),data.get('name') or ''

def update_steps():
    return [
        f'下载最新包：{RELEASE_PAGE}/download/english-exam-studio.zip',
        '让助手更新（最省事）：把下面这段发给它 ——',
        '',
        '  请把 english-exam-studio Skill 更新到最新版：先备份我当前的技能目录，'
        f'再从 {RELEASE_PAGE} 下载最新 ZIP，替换旧文件（保留我自己的笔记文件），'
        '更新后运行 scripts/check_install.py 确认完整安装，再运行 scripts/doctor.py 检查环境，最后告诉我版本变化。',
        '',
        '手动更新：备份旧技能目录 → 下载并解压最新 ZIP → 用其中的 SKILL.md、scripts、assets、references、agents、VERSION 替换旧文件。',
        '完整说明见 docs/UPDATE.md（仓库内）。',
    ]

def main():
    parser=argparse.ArgumentParser(description='检查 english-exam-studio 的版本与更新方式')
    parser.add_argument('--offline',action='store_true',help='不联网，只报本机版本')
    parser.add_argument('--json',action='store_true',help='输出 JSON，便于助手读取')
    args=parser.parse_args()
    try:sys.stdout.reconfigure(encoding='utf-8',errors='replace')
    except (AttributeError,ValueError):pass
    current=local_version()
    try:
        from check_install import check
        installation=check(Path(__file__).resolve().parents[1])
    except ImportError:
        installation={'status':'incomplete_install','errors':['缺少完整性检查脚本']}
    if installation['status']!='complete':
        print(json.dumps({'status':'incomplete_install','installed_version':current,'installation':installation,'message':'未完整安装，不能依据 VERSION 宣称更新成功；按 docs/UPDATE.md 获取完整包。'},ensure_ascii=False,indent=2));return 1
    latest=None;error=None
    if not args.offline:
        try:latest,_=latest_release()
        except (urllib.error.URLError,urllib.error.HTTPError,TimeoutError,ValueError,json.JSONDecodeError) as issue:
            error=f'{type(issue).__name__}: {issue}'
    status=compare(current,latest) if latest else 'unknown_remote'
    if status=='update_available':
        steps=update_steps()
    elif status=='newer_than_release':
        steps=[f'本机 {current} 比公开最新版 {latest} 更新（通常是开发版或抢先版），无需降级；继续使用本机版本即可。',
               '如果确实要回到公开版，请先备份，再按 docs/UPDATE.md 下载并替换；不要在未备份时覆盖。']
    elif status=='up_to_date':
        steps=['已经是最新版，无需更新。']
    else:
        steps=update_steps()
    payload={'installed_version':current,'latest_version':latest,'status':status,
             'release_page':RELEASE_PAGE,'note':error or '',
             'update_steps':steps}
    if args.json:
        print(json.dumps(payload,ensure_ascii=False,indent=2));return 0
    print(f'当前安装版本：{current}')
    if status=='up_to_date':print(f'最新版本：{latest}（已是最新，无需更新）');return 0
    if status=='newer_than_release':
        print(f'最新版本：{latest}（本机版本更新，无需降级）')
    elif status=='update_available':
        print(f'最新版本：{latest}（可以更新）')
    else:
        print('暂时无法联网核对最新版本（离线或网络受限）')
    if error:print(f'（联网失败：{error}）')
    print('\n更新方法：')
    for line in steps:print(('  ' if line and not line.startswith('   ') else '')+line)
    return 0

if __name__=='__main__':raise SystemExit(main())
