#!/usr/bin/env python3
"""One command to fetch a skill package file-by-file from raw / CDN, with hash checks.

Why this exists: when the host cannot download the release ZIP (sandbox blocks git, or
raw.githubusercontent.com is unreachable), the documented fallback is "fetch the files one
by one". Doing that by hand means ~120 network calls, and any single truncated file turns
into a confusing build failure later. This script does the boring part: read
`install-manifest.json` first, fetch every file it lists, and compare each file's SHA256.

Honesty boundaries (printed at the end, not buried):
  * the manifest and the files come from the SAME channel, so matching hashes prove the
    transfer was intact — NOT that the source was genuine;
  * to prove provenance you need the official `SHA256SUMS.txt` and the official ZIP;
  * this script never says "installed". Only `scripts/check_install.py` reaching
    `complete` on a real skills directory means installed, and it says so in its report.

  python3 scripts/fetch_package.py --base https://cdn.jsdelivr.net/gh/hututu-ai/english-exam-studio@main --out 临时目录
  python3 scripts/fetch_package.py --base https://raw.githubusercontent.com/hututu-ai/english-exam-studio/main --out 临时目录
"""
import argparse,hashlib,json,sys,urllib.error,urllib.parse,urllib.request
from pathlib import Path
from platform_tools import explain_error,force_utf8

TIMEOUT=20
ATTEMPTS=2
MANIFEST='install-manifest.json'

def safe_relative(name):
    """Return a safe relative Path or None: no absolute paths, no '..', no drive letters."""
    text=str(name).replace('\\','/')
    if not text or text.startswith('/') or ':' in text.split('/')[0]:return None
    parts=[part for part in text.split('/') if part not in ('','.')]
    if not parts or any(part=='..' for part in parts):return None
    return Path(*parts)

def fetch(url,timeout=TIMEOUT):
    """Bounded GET: at most ATTEMPTS tries, one clear Chinese error when it gives up."""
    last=None
    for _ in range(ATTEMPTS):
        try:
            with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'english-exam-studio-fetch'}),timeout=timeout) as response:
                return response.read()
        except (urllib.error.URLError,urllib.error.HTTPError,OSError,ValueError) as error:
            last=error
    raise ValueError(f'下载失败（已重试 {ATTEMPTS} 次，不做无限重试）：{url}；{explain_error(last) if last else "原因未知"}')

def join(base,name):
    return base.rstrip('/')+'/'+urllib.parse.quote(str(name).replace('\\','/'))

def fetch_package(base,out,manifest=MANIFEST,expected_version=None,timeout=TIMEOUT):
    out=Path(out).resolve();out.mkdir(parents=True,exist_ok=True)
    raw=fetch(join(base,manifest),timeout)
    try:document=json.loads(raw.decode('utf-8'))
    except (UnicodeDecodeError,json.JSONDecodeError) as error:
        raise ValueError(f'{manifest} 不是有效 JSON：{explain_error(error)}；请确认 --base 指向技能包根目录（该目录下应有 {manifest}）')
    files=document.get('files') or {}
    version=document.get('version')
    if not isinstance(files,dict) or not files:raise ValueError(f'{manifest} 里没有 files 清单，无法核对；这不是完整的发布包')
    if expected_version and str(version)!=str(expected_version):
        raise ValueError(f'这个包的版本是 {version}，与要求的 {expected_version} 不一致；请换正确的地址或版本')
    # 清单本身不在它自己的 files 列表里（这正是"清单不能自证"的原因），
    # 但目标目录必须有它，check_install 才能逐文件核对——所以按原样写一份。
    (out/manifest).write_bytes(raw)
    written=[];mismatched=[];missing=[];refused=[]
    for name,digest in sorted(files.items()):
        relative=safe_relative(name)
        if relative is None:
            refused.append({'file':str(name),'reason':'清单里有越界或绝对路径，已拒绝（不写入磁盘）'})
            continue
        target=out/relative
        if not str(target.resolve()).startswith(str(out)+str(Path('/'))):
            refused.append({'file':str(name),'reason':'目标路径逃出输出目录，已拒绝'})
            continue
        try:payload=fetch(join(base,name),timeout)
        except ValueError as error:
            missing.append({'file':str(name),'reason':str(error)});continue
        actual=hashlib.sha256(payload).hexdigest()
        if actual!=str(digest).lower():
            mismatched.append({'file':str(name),'expected':digest,'actual':actual,
                               'reason':'文件内容与清单不一致（传输损坏或来源被改动），已保留但不计入成功'})
            continue
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes(payload)
        written.append(str(relative))
    problems=[]
    if refused:problems.append(f'{len(refused)} 个条目的路径不合法，已拒绝')
    if missing:problems.append(f'{len(missing)} 个文件下载失败')
    if mismatched:problems.append(f'{len(mismatched)} 个文件哈希不符')
    status='fetched_all_files' if not problems else 'incomplete_fetch'
    return {'status':status,'base':base,'out':str(out),'version':version,'expected_files':len(files),
            'written':len(written),'manifest_written':str(manifest),
            'refused':refused,'missing':missing,'mismatched':mismatched,
            'files':written,
            'trust':{'source_verified':False,
                     'why':f'{manifest} 与文件来自同一通道（{base}）：哈希一致只证明传输没损坏，不证明来源未被篡改。'
                            '要证明来源，请用官方 Release 的 SHA256SUMS.txt 核对官方 ZIP；'
                            '要证明"装上了"，请在该技能目录跑 scripts/check_install.py 到 complete。'},
            'next_step':'把上面的目录放到技能目录后运行 scripts/check_install.py，必须到 complete 才算装上；'
                        '若清单里出现 refused/mismatched，先如实报告"这次抓取不可用"，不要拿它当已安装。'}

def main():
    force_utf8()
    parser=argparse.ArgumentParser(description='按 install-manifest.json 逐文件抓取技能包（raw 或 jsDelivr CDN），并逐个核对 SHA256')
    parser.add_argument('--base',required=True,help='技能包根目录的 base URL，例如 https://cdn.jsdelivr.net/gh/hututu-ai/english-exam-studio@main')
    parser.add_argument('--out',required=True,help='下载到哪个目录（会新建；不会删除里面已有的其他文件）')
    parser.add_argument('--manifest',default=MANIFEST,help=f'清单文件名，默认 {MANIFEST}')
    parser.add_argument('--version',help='要求包版本与它一致，例如 1.0.83')
    parser.add_argument('--timeout',type=int,default=TIMEOUT,help='单次请求超时秒数（默认 20）')
    parser.add_argument('--json',action='store_true')
    args=parser.parse_args()
    try:report=fetch_package(args.base,args.out,args.manifest,args.version,args.timeout)
    except (ValueError,OSError) as error:
        print(json.dumps({'status':'failed','error':explain_error(error)},ensure_ascii=False,indent=2))
        return 1
    if args.json:print(json.dumps(report,ensure_ascii=False,indent=2))
    else:
        print(f"[{report['status']}] 版本 {report['version']}：写入 {report['written']}/{report['expected_files']} 个文件 → {report['out']}")
        for group in ('refused','missing','mismatched'):
            for item in report[group]:print(f"  ! {group}: {item['file']} —— {item['reason']}")
        print(f"  来源可信度：未证明（{report['trust']['why']}）")
        print(f"  下一步：{report['next_step']}")
    return 0 if report['status']=='fetched_all_files' else 1

if __name__=='__main__':raise SystemExit(main())
