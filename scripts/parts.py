#!/usr/bin/env python3
"""Split exam.json into per-section work files and merge them back.

Why: a full paper is 60-80 questions. Writing it as one huge JSON means every repair rewrites the
whole file, and nothing can be authored in parallel. Per-section files let several workers write
different sections at the same time and make each repair local.

  python3 scripts/parts.py split WORK/exam.json --out WORK/parts
  python3 scripts/parts.py check WORK/parts
  python3 scripts/parts.py merge WORK/parts --out WORK/exam.json
"""
import argparse,json,sys
from pathlib import Path
from platform_tools import force_utf8

def split(exam_path,out,force=False):
    exam=json.loads(Path(exam_path).read_text(encoding='utf-8'))
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    existing=sorted(p.name for p in out.glob('*.json'))
    if existing and not force:raise ValueError(f'{out} 已有 {len(existing)} 个 json（{existing[:3]}）；加 --force 覆盖')
    meta={k:v for k,v in exam.items() if k!='sections'}
    meta['section_order']=[s['id'] for s in exam['sections']]
    meta['_source']=str(Path(exam_path).resolve())
    (out/'_meta.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding='utf-8')
    for section in exam['sections']:
        (out/f"{section['id']}.json").write_text(json.dumps(section,ensure_ascii=False,indent=2),encoding='utf-8')
    return {'sections':len(exam['sections']),'out':str(out),'files':[f"{s['id']}.json" for s in exam['sections']]}

def load_parts(directory):
    directory=Path(directory)
    meta_path=directory/'_meta.json'
    if not meta_path.is_file():raise ValueError(f'{directory} 缺少 _meta.json，先跑 parts.py split')
    meta=json.loads(meta_path.read_text(encoding='utf-8'))
    sections=[];missing=[]
    for sid in meta['section_order']:
        path=directory/f'{sid}.json'
        if not path.is_file():missing.append(path.name);continue
        try:sections.append(json.loads(path.read_text(encoding='utf-8')))
        except json.JSONDecodeError as error:
            raise ValueError(f'{path.name} 不是合法 JSON（第 {error.lineno} 行第 {error.colno} 列：{error.msg}）') from error
    if missing:raise ValueError('缺少分节文件：'+', '.join(missing))
    extra=sorted(p.name for p in directory.glob('*.json') if p.name!='_meta.json' and p.stem not in meta['section_order'])
    return meta,sections,extra

def check(directory):
    meta,sections,extra=load_parts(directory)
    problems=[]
    for section in sections:
        if section.get('id') not in meta['section_order']:problems.append(f"{section.get('id')}: 不在 _meta 的 section_order 里")
        if not section.get('paragraphs'):problems.append(f"{section.get('id')}: 缺少 paragraphs")
        if not section.get('questions'):problems.append(f"{section.get('id')}: 缺少 questions")
    return {'sections':len(sections),'questions':sum(len(s.get('questions',[])) for s in sections),
            'files_to_merge':[f"{s['id']}.json" for s in sections],'unused_files':extra,'problems':problems,
            'status':'ok' if not problems else 'needs_fix'}

def merge(directory,out):
    meta,sections,extra=load_parts(directory)
    target=Path(out)
    if Path(meta['_source']).parent!=target.resolve().parent:
        raise ValueError('合并输出必须与原 exam.json 同目录，保持素材相对路径有效')
    if any(section.get('id')!=sid for section,sid in zip(sections,meta['section_order'])):
        raise ValueError('分节文件 ID 与文件名不符，禁止串节合并')
    merged={k:v for k,v in meta.items() if k not in {'section_order','_source'}}
    merged['sections']=sections
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(merged,ensure_ascii=False,indent=2),encoding='utf-8')
    return {'out':str(target),'sections':len(sections),'questions':sum(len(s.get('questions',[])) for s in sections),
            'section_order':[s['id'] for s in sections],'unused_files':extra,
            'next':'python3 scripts/build.py '+str(target)+' OUTPUT --source-ledger ... --audio-bundle ...'}

def main():
    force_utf8()
    p=argparse.ArgumentParser();sub=p.add_subparsers(dest='command',required=True)
    x=sub.add_parser('split');x.add_argument('exam');x.add_argument('--out',required=True);x.add_argument('--force',action='store_true');x.set_defaults(func=lambda a:split(a.exam,a.out,a.force))
    x=sub.add_parser('check');x.add_argument('parts');x.set_defaults(func=lambda a:check(a.parts))
    x=sub.add_parser('merge');x.add_argument('parts');x.add_argument('--out',required=True);x.set_defaults(func=lambda a:merge(a.parts,a.out))
    a=p.parse_args()
    try:result=a.func(a)
    except (OSError,ValueError,KeyError,json.JSONDecodeError) as e:sys.exit(f'ERROR: {e}')
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 1 if result.get('status')=='needs_fix' else 0

if __name__=='__main__':raise SystemExit(main())
