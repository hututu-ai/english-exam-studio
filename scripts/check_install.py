#!/usr/bin/env python3
"""Check every distributed file; VERSION alone is never an installation receipt."""
import argparse, hashlib, json
from pathlib import Path, PurePosixPath

REQUIRED = ['SKILL.md','VERSION','assets/lesson.html','assets/template-manifest.json',
 'assets/offline-dictionary.json','scripts/build.py','scripts/audio.py',
 'scripts/doctor.py','scripts/verify_output.py','scripts/browser_check.cjs',
 'scripts/check_install.py','scripts/prepare_whisper.py','scripts/import_timed_text.py','scripts/preferences.py','references/schema.md']

def check(root):
    root=Path(root).resolve(); errors=[]
    try:
        manifest=json.loads((root/'install-manifest.json').read_text(encoding='utf-8'))
        files=manifest['files']
        if not isinstance(files,dict):raise ValueError('安装清单格式不对：files 应该是「相对路径 → sha256」的对象')
    except (OSError,ValueError,KeyError) as e:
        return {'status':'incomplete_install','errors':['缺少或无法读取完整安装清单: '+str(e)],'root':str(root)}
    for name in REQUIRED:
        if name not in files:errors.append('安装清单缺少必要项: '+name)
    for name,digest in files.items():
        p=PurePosixPath(name)
        if p.is_absolute() or '..' in p.parts or '\\' in name or ':' in name:
            errors.append('非法清单路径: '+name);continue
        path=root/name
        if path.is_symlink() or not path.is_file() or root not in path.resolve().parents:
            errors.append('缺少文件或路径异常: '+name);continue
        if hashlib.sha256(path.read_bytes()).hexdigest()!=digest:errors.append('文件不完整或已修改: '+name)
    version=(root/'VERSION').read_text(encoding='utf-8').strip() if (root/'VERSION').is_file() else None
    if version!=manifest.get('version'):errors.append('VERSION 与安装清单不一致')
    return {'status':'complete' if not errors else 'incomplete_install','version':version,
      'checked_files':len(files),'root':str(root),'errors':errors,
      'note':'完整性检查，不代表宿主依赖、答案或音频已验收。个性化修改须备份并明确记录差异。'}

if __name__=='__main__':
    from platform_tools import force_utf8
    force_utf8()
    p=argparse.ArgumentParser();p.add_argument('root',nargs='?',default=str(Path(__file__).resolve().parents[1]));a=p.parse_args()
    r=check(a.root);print(json.dumps(r,ensure_ascii=False,indent=2));raise SystemExit(0 if r['status']=='complete' else 1)
