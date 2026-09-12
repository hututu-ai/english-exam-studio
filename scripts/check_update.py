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
        '更新后确认 VERSION 已变化并运行 scripts/doctor.py 检查环境，最后告诉我版本变化。',
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
    latest=None;error=None
    if not args.offline:
        try:latest,_=latest_release()
        except (urllib.error.URLError,urllib.error.HTTPError,TimeoutError,ValueError,json.JSONDecodeError) as issue:
            error=f'{type(issue).__name__}: {issue}'
    if latest and current and normalise(current)==latest:
        status='up_to_date'
    elif latest:
        status='update_available'
    else:
        status='unknown_remote'
    payload={'installed_version':current,'latest_version':latest,'status':status,
             'release_page':RELEASE_PAGE,'note':error or '',
             'update_steps':update_steps() if status!='up_to_date' else ['已经是最新版，无需更新。']}
    if args.json:
        print(json.dumps(payload,ensure_ascii=False,indent=2));return 0
    print(f'当前安装版本：{current}')
    if status=='up_to_date':print(f'最新版本：{latest}（已是最新，无需更新）');return 0
    if status=='update_available':print(f'最新版本：{latest}（可以更新）')
    else:print('暂时无法联网核对最新版本（离线或网络受限）')
    if error:print(f'（联网失败：{error}）')
    print('\n更新方法：')
    for line in payload['update_steps']:print(('  ' if line and not line.startswith('   ') else '')+line)
    return 0

if __name__=='__main__':raise SystemExit(main())
