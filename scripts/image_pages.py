#!/usr/bin/env python3
"""Inventory image-only material (试卷照片 / 图片版答案 / 图片版听力原文) as a verifiable page set.

Teachers sometimes have no PDF at all: only photos or screenshots. Those pages must be
ordered, hashed and checked the same way a PDF is, or "漏页/重号/顺序错" becomes invisible.

  python3 scripts/image_pages.py WORK/paper-images --role paper --out WORK/paper-inventory.json
  python3 scripts/image_pages.py WORK/answer-images --role answers --out WORK/answer-inventory.json
  python3 scripts/image_pages.py page1.jpg page2.jpg --role paper --out inventory.json

The output is meant to be embedded in source-ledger.json as one source:

  {"role":"paper","path":"paper-images","pages":[{"index":1,"path":"...","sha256":"..."}],
   "sha256":"<aggregate digest over the page set>"}

quality_gate.py re-verifies every page hash and recomputes the aggregate, so a page that is
swapped, re-shot or removed after the ledger was written is caught.
"""
import argparse,hashlib,json,re,sys
from pathlib import Path
from platform_tools import explain_error,force_utf8

IMAGE_SUFFIXES={'.png','.jpg','.jpeg','.webp','.bmp','.tif','.tiff','.heic','.heif','.gif'}

def digest_bytes(data):
    return hashlib.sha256(data).hexdigest()

def natural_key(name):
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r'(\d+)',Path(name).name)]

def page_set_digest(pages):
    """Aggregate fingerprint of a page set: order- and identity-sensitive, path-independent."""
    payload='\n'.join(f"{page['index']}\t{page['sha256']}\t{Path(page['path']).name}" for page in pages)
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()

def png_size(data):
    if len(data)>=24 and data[:8]==b'\x89PNG\r\n\x1a\n' and data[12:16]==b'IHDR':
        return int.from_bytes(data[16:20],'big'),int.from_bytes(data[20:24],'big')
    return None

def jpeg_size(data):
    if len(data)<4 or data[:2]!=b'\xff\xd8':return None
    i=2
    while i+9<len(data):
        if data[i]!=0xff:i+=1;continue
        marker=data[i+1]
        if marker in (0xd8,0xd9) or 0xd0<=marker<=0xd7:i+=2;continue
        length=int.from_bytes(data[i+2:i+4],'big')
        if 0xc0<=marker<=0xcf and marker not in (0xc4,0xc8,0xcc):
            return int.from_bytes(data[i+7:i+9],'big'),int.from_bytes(data[i+5:i+7],'big')
        i+=2+max(length,2)
    return None

def image_size(data):
    return png_size(data) or jpeg_size(data)

def collect(files,directory):
    if files:
        paths=[Path(item) for item in files]
    else:
        root=Path(directory)
        if not root.is_dir():raise ValueError(f'{directory} 不是文件夹')
        paths=[p for p in sorted(root.rglob('*'),key=natural_key) if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES]
    return paths

def inventory(files,directory,role,relative_to=None,spread=False,pages_per_image=2,spread_files=None):
    """登记图片页集合。

    spread=True（或 spread_files 命中某个文件）表示这张照片是**翻开的书**：一张图里并排两页。
    这时 page_count 仍是图片张数，另给 logical_pages = 张数 × 每张页数，
    并逐页标 spread/pages_in_image，避免"1 张=1 页"把漏页与页序核对带偏。
    """
    spread_names={Path(name).name for name in (spread_files or [])}
    paths=collect(files,directory)
    if not paths:raise ValueError('没有找到图片文件（支持 '+' '.join(sorted(IMAGE_SUFFIXES))+'）')
    # 路径按 source-ledger.json 所在目录（通常是当前工作目录）输出，quality_gate 才找得到。
    base=Path(relative_to).resolve() if relative_to else Path.cwd().resolve()
    pages=[];problems=[];seen={}
    if not files:
        # 扫文件夹会递归子目录：老师的"原图/裁剪"、多批照片只要同时在，页集合就会悄悄变成几倍，
        # 而且按文件名排序会把不同目录的同号页穿插在一起。如实拦下，让人自己二选一。
        directories=sorted({Path(path).parent for path in paths})
        if len(directories)>1:
            names={}
            for path in paths:names.setdefault(Path(path).name,set()).add(str(Path(path).parent))
            duplicated=sorted(name for name,dirs in names.items() if len(dirs)>1)
            detail='、'.join(str(directory) for directory in directories)
            extra=f'；其中 {duplicated} 在多个目录里同名' if duplicated else ''
            problems.append({'code':'images_from_multiple_dirs','file':'','message':
                f'这些图片来自 {len(directories)} 个目录（{detail}）{extra}：很可能把原图与裁剪图、或多批照片混在一起了；'
                f'请只指向其中一批（例如 --dir 试卷图片/原图），或按页序一次列全文件（page1.jpg page2.jpg …），不要让脚本猜'})
    for index,path in enumerate(sorted(paths,key=natural_key),1):
        if path.suffix.lower() not in IMAGE_SUFFIXES:
            problems.append({'code':'unsupported_file','file':str(path),'message':'不是受支持的图片格式，先转换或确认没有把 PDF/DOCX 混进来'});continue
        data=path.read_bytes()
        if not data:
            problems.append({'code':'empty_file','file':str(path),'message':'文件是空的，可能是下载或截图失败'});continue
        sha=digest_bytes(data)
        try:relative=path.resolve().relative_to(base).as_posix()
        except ValueError:
            relative=str(path.resolve())
            problems.append({'code':'path_outside_base','file':relative,'message':'图片不在台账所在目录之下；请把它放进工作目录，或把 source-ledger.json 放在素材同级再生成清单'})
        size=image_size(data)
        if size is None and path.suffix.lower() in {'.png','.jpg','.jpeg'}:
            problems.append({'code':'unreadable_image','file':relative,'message':'读不出图片尺寸，文件可能损坏或被改名'})
        if sha in seen:
            problems.append({'code':'duplicate_page','file':relative,'message':f'与第 {seen[sha]} 页内容完全相同：同一页拍了两遍，或漏拍了别的页'})
        else:seen[sha]=index
        is_spread=bool(spread or path.name in spread_names or Path(relative).name in spread_names)
        per_image=int(pages_per_image or 2) if is_spread else 1
        page={'index':index,'path':relative,'sha256':sha,'bytes':len(data),
              'width':size[0] if size else None,'height':size[1] if size else None}
        if is_spread:
            page['spread']=True;page['pages_in_image']=per_image
            if size and size[0]<size[1]:
                problems.append({'code':'spread_not_landscape','file':relative,
                                 'message':f'声明为跨页照片，但图片是竖版（{size[0]}×{size[1]}）：跨页通常是横版；请确认页数或取消跨页标记'})
        pages.append(page)
    numbers=[]
    for page in pages:
        found=re.findall(r'\d+',Path(page['path']).stem)
        if found:numbers.append(int(found[-1]))
    if len(numbers)>=3:
        low,high=min(numbers),max(numbers)
        gaps=[n for n in range(low,high+1) if n not in numbers]
        if gaps:problems.append({'code':'possible_missing_page','file':'','message':f'文件名编号 {low}–{high} 之间缺 {gaps}：核对是否漏拍'})
    logical=sum(page.get('pages_in_image',1) for page in pages)
    result={'role':role,'kind':'image_pages','source_sha256':page_set_digest(pages),'page_count':len(pages),
            'pages':pages,'problems':problems,
            'note':'图片版材料同样必须逐页核对题号、漏页、重号与裁切；本清单只解决顺序、重复与缺失的可核对问题。'}
    if logical!=len(pages):
        result['layout']='spread'
        result['pages_per_image']=int(pages_per_image or 2)
        result['logical_pages']=logical
        result['note']=result['note']+f'本组有跨页照片：{len(pages)} 张图共 {logical} 页（翻开的书一张两页），逐页核对时要按左右页分别看。'
    return result

def main():
    force_utf8()
    parser=argparse.ArgumentParser(description='把图片版试卷/答案/听力原文登记成可校验的页集合')
    parser.add_argument('files',nargs='*',help='图片文件；也可以只给一个文件夹')
    parser.add_argument('--dir',help='图片文件夹（与 files 二选一）')
    parser.add_argument('--role',default='paper',choices=['paper','answers','listening_text','writing_model','other'])
    parser.add_argument('--relative-to',help='清单里的路径相对哪个目录（默认当前目录，应等于 source-ledger.json 所在目录）')
    parser.add_argument('--spread',action='store_true',help='所有图片都是翻开的书（一张图并排两页）')
    parser.add_argument('--spread-files',help='只有这些文件是跨页照片（逗号分隔文件名），其余按一页一张')
    parser.add_argument('--pages-per-image',type=int,default=2,help='跨页照片每张几页（默认 2）')
    parser.add_argument('--out',required=True)
    args=parser.parse_args()
    if not args.files and not args.dir:parser.error('请给出图片文件或 --dir 文件夹')
    spread_files=[name.strip() for name in (args.spread_files or '').replace('，',',').split(',') if name.strip()]
    try:result=inventory(args.files,args.dir,args.role,args.relative_to,
                         spread=args.spread,pages_per_image=args.pages_per_image,spread_files=spread_files)
    except (OSError,ValueError) as error:
        print(f'ERROR: {explain_error(error)}',file=sys.stderr);return 1
    Path(args.out).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    summary={'role':result['role'],'pages':result['page_count'],'problems':len(result['problems']),
             'source_sha256':result['source_sha256'],'out':args.out}
    if result.get('layout')=='spread':summary['logical_pages']=result['logical_pages']
    print(json.dumps(summary,ensure_ascii=False,indent=2))
    return 1 if result['problems'] else 0

if __name__=='__main__':raise SystemExit(main())
