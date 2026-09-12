#!/usr/bin/env python3
"""Extract a question -> answer table straight from the answer-key file.

This is the authenticity chain: answer key file -> answers.json (parsed here, never typed by the agent)
-> source-ledger.json -> exam.json -> quality_gate cross-check. Anything the agent cannot trace back
to this table must not be labelled official.
"""
import argparse,hashlib,json,re,sys,zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from platform_tools import force_utf8

LETTERS='ABCDEFGH'
CIRCLED={'Ⓐ':'A','Ⓑ':'B','Ⓒ':'C','Ⓓ':'D','Ⓔ':'E','Ⓕ':'F','Ⓖ':'G','Ⓗ':'H'}

def sha256(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for block in iter(lambda:f.read(1<<20),b''):h.update(block)
    return h.hexdigest()

def docx_text(path):
    ns={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
    with zipfile.ZipFile(path) as z:
        root=ET.fromstring(z.read('word/document.xml'));lines=[]
        for node in root.find('w:body',ns):
            kind=node.tag.split('}')[-1]
            if kind=='p':lines.append(''.join(x.text or '' for x in node.findall('.//w:t',ns)))
            elif kind=='tbl':
                for row in node.findall('w:tr',ns):
                    lines.append('\t'.join(''.join(x.text or '' for x in cell.findall('.//w:t',ns)) for cell in row.findall('w:tc',ns)))
        return '\n'.join(lines)

def load_text(path):
    path=Path(path)
    if path.suffix.lower()=='.docx':return docx_text(path)
    if path.suffix.lower()=='.json':
        data=json.loads(path.read_text())
        if isinstance(data,dict) and 'blocks' in data:return '\n'.join(b.get('text','') for b in data['blocks'])
        raise ValueError('JSON 答案文件需要一个 blocks 数组（scripts/extract.py 的输出）')
    return path.read_text(encoding='utf-8',errors='replace')

def normalise_letters(raw):
    """Turn one answer token into its letters: A / AB / 6.A / 答案A / Ⓐ."""
    token=raw.strip()
    token=re.sub(r'^[（(\[【]?\s*(?:答案|answer|key)\s*[:：]?\s*','',token,flags=re.I)
    token=re.sub(r'^[（(\[【]?\s*[0-9]{1,3}\s*[）)\]】]?\s*[.、．:：)）]?\s*','',token)
    token=''.join(CIRCLED.get(ch,ch) for ch in token)
    letters=[ch for ch in token.upper() if ch in LETTERS]
    trailing=re.sub(r'[^A-Za-z]','',token).upper()
    if len(letters)==len(trailing.replace('ANSWER','').replace('KEY','')) and letters:return letters
    if len(letters)==1:return letters
    return []

def expand(line):
    """Extract {number: answer} pairs from one line, including ranges such as 21-25 ABCDA."""
    found={}
    for m in re.finditer(r'(\d{1,3})\s*[-—~－]\s*(\d{1,3})\s*[:：]?\s*([A-Ha-h]{1,8})',line):
        start,end,letters=int(m.group(1)),int(m.group(2)),m.group(3).upper()
        if 1<=end-start+1==len(letters):found.update({str(start+i):letters[i] for i in range(len(letters))})
    cleaned=re.sub(r'\d{1,3}\s*[-—~－]\s*\d{1,3}\s*[:：]?\s*[A-Ha-h]{1,8}',' ',line)
    for m in re.finditer(r'(?:^|[^\dA-Za-z])(\d{1,3})\s*(?:[.、．:：)）]|\s)\s*([A-Ha-h]{1,4}|[Ⓐ-Ⓗ]+)\s*(?=$|[^\dA-Za-z])',cleaned):
        letters=normalise_letters(m.group(2))
        if letters:found[m.group(1)]=letters[0] if len(letters)==1 else ''.join(letters)
    if not found:
        for m in re.finditer(r'(?:^|\s)(\d{1,3})\s+([A-H])(?=\s|$)',line):
            found[m.group(1)]=m.group(2)
    return found

def extract(path,planning=None):
    text=load_text(path);table={};unparsed=[];sources=[]
    for number,line in enumerate(text.splitlines(),1):
        line=line.strip()
        if not line:continue
        if re.fullmatch(r'[\d\s.,、.．:：\-—~－A-Ha-h()（）]+',line) and re.search(r'[A-Ha-h]',line):pass
        pairs=expand(line)
        if pairs:
            for key,value in pairs.items():
                if key in table and table[key]!=value:unparsed.append({'line':number,'text':line,'reason':f'题号 {key} 出现两个不同答案 {table[key]} / {value}'})
                table[key]=value
            sources.append({'line':number,'text':line,'pairs':pairs})
        elif re.search(r'\d',line) and len(line)<80:unparsed.append({'line':number,'text':line,'reason':'含数字但未识别出题号+答案'})
    ordered={k:table[k] for k in sorted(table,key=lambda x:int(x))}
    return {'answer_source':str(Path(path).resolve()),'answer_source_sha256':sha256(path),'count':len(ordered),'answers':ordered,
            'matched_lines':sources,'unparsed':unparsed,
            'planning':planning,'status':'draft_requires_review',
            'note':'机器提取结果必须与答案原件逐页比对；冲突行在 unparsed 中列出，不得自行取舍后仍标 official。'}

def check(table_path,ledger_path):
    table=json.loads(Path(table_path).read_text());rows=table['answers']
    ledger=json.loads(Path(ledger_path).read_text());problems=[]
    for section in ledger.get('sections',[]):
        for q in section.get('questions',[]):
            qid=str(q['id']);key=rows.get(qid)
            answer=q.get('answer');answers=answer if isinstance(answer,list) else [answer]
            normalised=[str(a).strip().upper() for a in answers if a not in (None,'')]
            if key is None:problems.append({'code':'answer_key_missing','question':qid,'message':'答案原件里没有解析到该题，需回原件确认'})
            elif q.get('answer_status')=='official' and key not in normalised:
                problems.append({'code':'answer_key_mismatch','question':qid,'message':f'台账写 {normalised}，答案原件解析为 {key}'})
    return {'status':'blocked' if any(x['code']=='answer_key_mismatch' for x in problems) else 'answer_key_consistent',
            'answer_source':table.get('answer_source'),'answer_source_sha256':table.get('answer_source_sha256'),
            'covered':len(rows),'problems':problems,
            'scope':'比对机器解析的答案表与台账；不证明台账里没有的题目答案，也不证明主观题评分标准。'}

def main():
    p=argparse.ArgumentParser();sub=p.add_subparsers(dest='command',required=True)
    x=sub.add_parser('extract');x.add_argument('source');x.add_argument('--out',required=True);x.add_argument('--planning',help='可选：说明题型与题号区间的 JSON 文件');x.set_defaults(func=lambda a:extract(a.source,json.loads(Path(a.planning).read_text()) if a.planning else None))
    x=sub.add_parser('check');x.add_argument('answers');x.add_argument('--ledger',required=True);x.set_defaults(func=lambda a:check(a.answers,a.ledger))
    a=p.parse_args()
    try:result=a.func(a)
    except (OSError,ValueError,KeyError,json.JSONDecodeError) as e:sys.exit(f'ERROR: {e}')
    if a.command=='extract':
        Path(a.out).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({'count':result['count'],'unparsed':len(result['unparsed']),'out':a.out,'status':result['status']},ensure_ascii=False,indent=2))
    else:print(json.dumps(result,ensure_ascii=False,indent=2))
    return 1 if result.get('status')=='blocked' else 0

if __name__=='__main__':force_utf8();raise SystemExit(main())
