#!/usr/bin/env python3
"""Maintainer: produce a complete installer and integrity inventory, no user-machine mutation."""
import argparse,hashlib,json,zipfile
from pathlib import Path
from check_install import check
from check_docs import ROOT_REPORT_RESIDUE

def write_sums(out,digest):
    """把这次产物的 SHA256 写进同目录的 SHA256SUMS.txt（`sha256sum -c` 格式，按文件名合并）。

    为什么必须有：`docs/UPDATE.md` 要求老师"下载同版 SHA256SUMS.txt 并用 scripts/extract_package.py
    核对"，但发布流程此前只产出 ZIP——那个文件得靠人手工补，漏一次老师就无法核对指纹。这里由打包
    脚本自己产出，格式与 `sha256sum` 一致；同目录已有旧版本条目时合并保留，便于多版本并存。
    """
    sums=out.parent/'SHA256SUMS.txt'
    rows={}
    if sums.is_file():
        for line in sums.read_text(encoding='utf-8').splitlines():
            parts=line.split()
            if len(parts)>=2 and len(parts[0])==64:rows[parts[-1].lstrip('*')]=parts[0].lower()
    rows[out.name]=digest
    sums.write_text(''.join(f'{rows[name]}  {name}\n' for name in sorted(rows)),encoding='utf-8')
    return sums

def package(root,out):
    root=Path(root).resolve();out=Path(out).resolve()
    # dist/ 不进包；根目录的验收报告同样不进包——它是旧版残留，发出去会让老师误读（check_docs.py 也会报）。
    names=[p for p in root.rglob('*') if p.is_file() and not p.is_symlink()
        and not any(x.startswith('.') or x in ('dist','work','__pycache__') for x in p.relative_to(root).parts)
        and p.relative_to(root).as_posix() not in ROOT_REPORT_RESIDUE
        and p.suffix not in ('.pyc','.zip') and p.name!='install-manifest.json' and p.name!='SHA256SUMS.txt']
    inventory={'version':(root/'VERSION').read_text(encoding='utf-8').strip(),'files':{p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(names)}}
    (root/'install-manifest.json').write_text(json.dumps(inventory,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    report=check(root)
    if report['status']!='complete':raise ValueError(report)
    out.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
        for p in names+[root/'install-manifest.json']:z.write(p,p.relative_to(root).as_posix())
    digest=hashlib.sha256(out.read_bytes()).hexdigest()
    sums=write_sums(out,digest)
    return {**report,'zip':str(out),'sha256':digest,'sha256sums':str(sums)}
if __name__=='__main__':
    from platform_tools import force_utf8
    force_utf8()
    p=argparse.ArgumentParser();p.add_argument('out');a=p.parse_args();print(json.dumps(package(Path(__file__).resolve().parents[1],a.out),ensure_ascii=False,indent=2))
