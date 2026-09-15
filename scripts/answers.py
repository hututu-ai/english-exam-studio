#!/usr/bin/env python3
"""Extract a question -> answer table straight from the answer-key file.

Supported answer-key layouts (all of them are parsed, never typed by hand):
  * one line per question: `11 B`, `26. B`, `27 Ⓒ`, `31 A`
  * ranges: `21-25 ABCDA`
  * 题号行 + 紧邻答案行的表格（答题卡/参考答案表最常见的排法，可分几段）
  * 每行「题号 答案」的两列表格
  * 语法填空那类单词/短语答案：`1 which`
Anything that does not fit lands in `unparsed` with a Chinese reason for page-by-page review —
a column-count mismatch is reported, never force-aligned in order.

This is the authenticity chain: answer key file -> answers.json (parsed here, never typed by the agent)
-> source-ledger.json -> exam.json -> quality_gate cross-check. Anything the agent cannot trace back
to this table must not be labelled official.
"""
import argparse,hashlib,json,re,sys,zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from platform_tools import explain_error,force_utf8

LETTERS='ABCDEFGH'
CIRCLED={'Ⓐ':'A','Ⓑ':'B','Ⓒ':'C','Ⓓ':'D','Ⓔ':'E','Ⓕ':'F','Ⓖ':'G','Ⓗ':'H'}
# 语法填空等题型的答案是单词或短语，不是 A–H 字母；答案原件必须能表达它们。
TEXT_ANSWER=re.compile(r'^\s*(\d{1,3})\s*(?:[.、．:：)）]|\s)\s*(\S.{0,38})$')

def text_answer(value):
    """Return the primary variant of a word/phrase answer, or '' when the text is not answer-like.

    Conservative on purpose: short, no question mark, ASCII letters present. Answer keys are the
    intended input, and anything uncertain still lands in `unparsed` for page-by-page review.
    """
    text=value.strip().strip('。.;；,，')
    text=re.sub(r'\s*[（(][^）)]*[）)]\s*$','',text).strip()   # 变体提示：to make (to do) -> to make
    if not text or '?' in text or '？' in text:return ''
    if len(text)>30 or len(text.split())>4:return ''
    if not re.search(r'[A-Za-z]',text):return ''
    if re.search(r'[。！？!?；;]',text):return ''
    return re.split(r'\s*(?:/|／|或|或者)\s*',text)[0].strip().strip('()（）"\'')

LETTER_ONLY=re.compile(r'[A-H\s,，、/;；]+')

def answer_letters(value):
    """把答案里的选项字母取出来：'AB'、'A B'、['A','B'] 都得到 ['A','B']（按出现顺序去重）。"""
    text=' '.join(str(x) for x in (value if isinstance(value,list) else [value]))
    seen=[]
    for letter in re.findall(r'[A-H]',text.upper()):
        if letter not in seen:seen.append(letter)
    return seen

def answer_match(expected,given):
    """答案原件里的 expected 与成品答案 given 是否算同一个答案。

    两种情况都算相同，避免把正常写法判成不一致：
      * expected 整体出现在 given 里（`answer` 允许写"合理变体数组"，如 ['A','B'] 里含原答案）；
      * 两边都是纯选项字母时按字母集合比较（原件写 'AB'、成品写 ['A','B'] 是同一次多选）。
    文字答案（如 which）走逐字比较；只有两边都是字母串才会走集合比较，避免把单词答案当成字母。
    """
    exp=str(expected).strip().upper()
    values=[str(x).strip().upper() for x in (given if isinstance(given,list) else [given]) if str(x).strip()]
    if not exp or not values:return False
    if exp in values:return True
    joined=' '.join(values)
    if LETTER_ONLY.fullmatch(exp) and LETTER_ONLY.fullmatch(joined):
        return sorted(set(re.findall(r'[A-H]',exp)))==sorted(set(re.findall(r'[A-H]',joined)))
    return False

def sha256(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for block in iter(lambda:f.read(1<<20),b''):h.update(block)
    return h.hexdigest()

def docx_text(path):
    ns={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
    with zipfile.ZipFile(path) as z:
        try:root=ET.fromstring(z.read('word/document.xml'))
        except KeyError:raise ValueError('答案文件里没有 word/document.xml，可能不是 DOCX；老式 .doc、PDF 或改名文件请先转换，或改用文本/JSON 答案')
        body=root.find('w:body',ns)
        if body is None:raise ValueError('答案 DOCX 缺少正文 w:body，文件可能损坏或被截断')
        lines=[]
        for node in body:
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
        data=json.loads(path.read_text(encoding='utf-8'))
        if isinstance(data,dict) and 'blocks' in data:return '\n'.join(b.get('text','') for b in data['blocks'])
        raise ValueError('JSON 答案文件需要一个 blocks 数组（scripts/extract.py 的输出）')
    return path.read_text(encoding='utf-8',errors='replace')

def split_cells(line):
    """把表格行切成单元格：DOCX 表格按制表符、Markdown/文本表格按竖线，都没有时按连续空白。"""
    if '\t' in line:return [cell.strip() for cell in line.split('\t')]
    if '|' in line:return [cell.strip() for cell in line.split('|')]
    return [cell.strip() for cell in re.split(r'\s{2,}',line.strip())]

def head_kind(cell):
    """单元格是不是"题号/答案"这类表头（去掉空格与冒号后比较）。"""
    text=re.sub(r'[\s.。:：]+','',str(cell or '')).lower()
    if not text:return None
    for head in ('题号','序号','编号','小题号','questions','question','no'):
        if text.startswith(head):return 'number'
    for head in ('答案','参考答案','标准答案','answer','answers','key'):
        if text.startswith(head):return 'answer'
    return None

def answer_value(cell):
    """单元格里的答案是字母还是单词/短语；都不是就返回空串（交给 unparsed 人工核对）。"""
    letters=normalise_letters(cell)
    if letters:return letters[0] if len(letters)==1 else ''.join(letters)
    return text_answer(cell)

def paired_rows(rows):
    """识别"题号行 + 紧邻答案行"的表格（答题卡、答案表最常见的排法）。

    以前这种表会解析出 0 条答案、只留一句"含数字但未识别出题号+答案"——而答案表正是老师最常交的原件。
    这里只认**列数一致、题号全是整数、答案格都不空**的严格配对；列数不一致时给中文原因进 unparsed，
    不猜、不按顺序硬对齐。
    """
    pairs={};problems=[];sources=[]
    index=0
    while index<len(rows)-1:
        upper,lower=rows[index],rows[index+1]
        upper_cells,lower_cells=split_cells(upper),split_cells(lower)
        head=head_kind(upper_cells[0]) if upper_cells else None
        looks_numeric=head=='number' or (len(upper_cells)>1 and not str(upper_cells[0]).strip()
                                        and all(re.fullmatch(r'\d{1,3}',cell) for cell in upper_cells[1:] if cell))
        if looks_numeric and len(upper_cells)>=2:
            numbers=upper_cells[1:];answers=lower_cells[1:] if len(lower_cells)>1 else []
            lower_head=head_kind(lower_cells[0]) if lower_cells else None
            numeric=all(re.fullmatch(r'\d{1,3}',cell) for cell in numbers if cell!='')
            if numeric and lower_head=='answer':
                if len(numbers)!=len(answers):
                    problems.append((index+1,upper,f'看起来是"题号行+答案行"的答案表，但列数不一致：题号 {len(numbers)} 列、答案 {len(answers)} 列；'
                                                    f'请把这张表补齐或改成每行"题号 答案"，不要按顺序硬对齐'))
                else:
                    found={}
                    for number,cell in zip(numbers,answers):
                        value=answer_value(cell)
                        if not value:
                            problems.append((index+2,lower,f'第 {number} 题的答案格是 {cell!r}，既不是 A–H 字母也不是可识别的单词/短语；请核对原件'))
                            continue
                        found[str(int(number))]=value
                    if found:
                        pairs.update(found)
                        sources.append({'line':index+1,'text':upper,'rows':[upper,lower],'pattern':'number_row_then_answer_row','pairs':found})
                        index+=2
                        continue
        index+=1
    return pairs,problems,sources

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
    # Word answer sheets may place several numbered answers in a single paragraph,
    # without spaces between the preceding answer and the next question number.
    markers=list(re.finditer(r'(?<!\d)(\d{1,3})[.、．]\s*',line))
    if len(markers)>1 and not line[:markers[0].start()].strip():
        numbers=[int(m[1]) for m in markers]
        values=[text_answer(line[m.end():markers[i+1].start() if i+1<len(markers) else len(line)]) for i,m in enumerate(markers)]
        if numbers==list(range(numbers[0],numbers[0]+len(numbers))) and all(values) and all(not re.search(r'\d',v) for v in values):
            return {str(n):v for n,v in zip(numbers,values)}
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
    if not found:
        match=TEXT_ANSWER.match(line)
        if match:
            value=text_answer(match.group(2))
            if value:found[match.group(1)]=value
    return found

def extract(path,planning=None,source_images=None):
    text=load_text(path);table={};unparsed=[];sources=[]
    lines=text.splitlines()
    # 先处理"题号行 + 答案行"的表格：这种原件以前会解析出 0 条答案（老师最常见的答案表排法）。
    table_pairs,table_problems,table_sources=paired_rows([line for line in lines if line.strip()])
    for entry in table_sources:
        number,line,pairs=entry['line'],entry['text'],entry['pairs']
        for key,value in pairs.items():
            if key in table and table[key]!=value:unparsed.append({'line':number,'text':line,'reason':f'题号 {key} 出现两个不同答案 {table[key]} / {value}'})
            table[key]=value
    sources.extend(table_sources)
    for number,line,reason in table_problems:unparsed.append({'line':number,'text':line,'reason':reason})
    paired_lines={entry['line'] for entry in table_sources}|{entry['line']+1 for entry in table_sources}|{number for number,_,_ in table_problems}
    for number,line in enumerate(lines,1):
        if number in paired_lines:continue          # 表格行已按配对处理，不再按行重复解析
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
    result={'answer_source':str(Path(path).resolve()),'answer_source_sha256':sha256(path),'answer_source_kind':'parsed',
            'count':len(ordered),'answers':ordered,'matched_lines':sources,'unparsed':unparsed,
            'planning':planning,'status':'draft_requires_review',
            'note':'机器提取结果必须与答案原件逐页比对；冲突行在 unparsed 中列出，不得自行取舍后仍标 official。'}
    if source_images:
        # 图片版答案：字形由助手读图得到，机器无法核对，所以把指纹绑定到"那一组图片"，
        # 并显式标成转录来源，让构建把这个不确定性报给老师，而不是冒充脚本解析。
        inventory=json.loads(Path(source_images).read_text(encoding='utf-8'))
        if inventory.get('kind')!='image_pages':raise ValueError('--source-images 需要 scripts/image_pages.py 生成的清单')
        result['answer_source_kind']='image_transcription'
        result['answer_source']=str(Path(source_images).resolve())
        result['answer_source_sha256']=inventory.get('source_sha256')
        result['answer_source_pages']=[{'index':p['index'],'path':p['path'],'sha256':p['sha256']} for p in inventory.get('pages',[])]
        result['transcribed_from']=str(Path(path).resolve())
        result['transcription_text_sha256']=sha256(path)
        result['note']=('答案由助手逐页读取图片转录而来（answer_source_kind=image_transcription），机器无法核对字形：'
                        '必须逐题与答案原图比对后才能标 official；'+result['note'])
    return result

def check(table_path,ledger_path):
    table=json.loads(Path(table_path).read_text(encoding='utf-8'));rows=table['answers']
    ledger=json.loads(Path(ledger_path).read_text(encoding='utf-8'));problems=[]
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
    x=sub.add_parser('extract');x.add_argument('source');x.add_argument('--out',required=True);x.add_argument('--planning',help='可选：说明题型与题号区间的 JSON 文件')
    x.add_argument('--source-images',help='图片版答案原件：用 scripts/image_pages.py 生成的页清单，指纹绑定到那组图片')
    x.set_defaults(func=lambda a:extract(a.source,json.loads(Path(a.planning).read_text(encoding='utf-8')) if a.planning else None,a.source_images))
    x=sub.add_parser('check');x.add_argument('answers');x.add_argument('--ledger',required=True);x.set_defaults(func=lambda a:check(a.answers,a.ledger))
    a=p.parse_args()
    try:result=a.func(a)
    except zipfile.BadZipFile as e:sys.exit(f'ERROR: 不是有效的 DOCX（zip）文件：{e}；老式 .doc、PDF 或改名文件请先转换，或改用文本/JSON 答案')
    except (OSError,ValueError,KeyError,json.JSONDecodeError) as e:sys.exit(f'ERROR: {explain_error(e)}')
    if a.command=='extract':
        Path(a.out).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({'count':result['count'],'unparsed':len(result['unparsed']),'out':a.out,'status':result['status']},ensure_ascii=False,indent=2))
    else:print(json.dumps(result,ensure_ascii=False,indent=2))
    return 1 if result.get('status')=='blocked' else 0

if __name__=='__main__':force_utf8();raise SystemExit(main())
