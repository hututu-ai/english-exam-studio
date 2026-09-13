#!/usr/bin/env python3
"""Maintainer: produce a complete installer and integrity inventory, no user-machine mutation."""
import argparse,hashlib,json,zipfile
from pathlib import Path
from check_install import check

def package(root,out):
    root=Path(root).resolve();out=Path(out).resolve()
    names=[p for p in root.rglob('*') if p.is_file() and not p.is_symlink()
        and not any(x.startswith('.') or x in ('dist','work','__pycache__') for x in p.relative_to(root).parts)
        and p.suffix not in ('.pyc','.zip') and p.name!='install-manifest.json']
    inventory={'version':(root/'VERSION').read_text().strip(),'files':{p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(names)}}
    (root/'install-manifest.json').write_text(json.dumps(inventory,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    report=check(root)
    if report['status']!='complete':raise ValueError(report)
    out.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
        for p in names+[root/'install-manifest.json']:z.write(p,p.relative_to(root).as_posix())
    return {**report,'zip':str(out),'sha256':hashlib.sha256(out.read_bytes()).hexdigest()}
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('out');a=p.parse_args();print(json.dumps(package(Path(__file__).resolve().parents[1],a.out),ensure_ascii=False,indent=2))
