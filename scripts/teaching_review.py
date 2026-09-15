#!/usr/bin/env python3
"""Evidence-bound teaching review. Records judgments; never certifies truth from fields alone."""
import argparse,hashlib,json,re,urllib.request,datetime
from html.parser import HTMLParser
from pathlib import Path
from task_contract import sha

def fingerprint(value):return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def targets(exam):
    for s in exam['sections']:
        for kind in ('culture_background','vocabulary','quick_words','structure','blanks'):
            for i,item in enumerate(s.get(kind,[])):
                yield f"{s['id']}/{kind}/{i}",kind,item,s

def draft(exam):
    rows=[]
    for key,kind,item,s in targets(exam):
        rows.append({'id':key,'item_sha256':fingerprint(item),'status':'pending','reviewer':'','judgment':'','evidence':[]})
    return {'exam_sha256':fingerprint(exam),'review_method':'separate_content_review','items':rows,'note':'先阅读原文与证据，再写实际复核判断；脚本不填通过。'}

def validate(exam,review,base):
    errors=[];records=review.get('items',[]);by={x.get('id'):x for x in records}
    if review.get('exam_sha256')!=fingerprint(exam):errors.append('教学内容已变化，复核记录过期：请重新逐项复核')
    if len(by)!=len(records):errors.append('复核条目 ID 重复')
    expected=set()
    for key,kind,item,s in targets(exam):
        expected.add(key);r=by.get(key,{})
        if r.get('status')!='accepted' or r.get('item_sha256')!=fingerprint(item):errors.append(key+' 缺少针对当前内容的通过判断')
        if not r.get('reviewer') or len(r.get('judgment','').strip())<12:errors.append(key+' 缺少复核者与具体判断；不能只写已核对')
        pars={p['id']:p['text'] for p in s.get('paragraphs',[])}
        ev=r.get('evidence',[])
        if not ev:errors.append(key+' 缺少复核依据')
        for e in ev:
            if e.get('paragraph_id') not in pars or not e.get('quote') or e['quote'] not in pars.get(e.get('paragraph_id'),''):errors.append(key+' 复核依据必须逐字来自本篇')
            if len(e.get('reason','').strip())<8:errors.append(key+' 请说明这段依据怎样支持判断')
        if kind=='culture_background':
            for source in item.get('sources',[]):
                ref=source.get('snapshot')
                if not ref:errors.append(key+' 文化来源缺少已抓取 snapshot，不能只填链接');continue
                try:
                    path=(Path(base)/ref).resolve();snap=json.loads(path.read_text(encoding='utf-8'))
                    if snap.get('url')!=source.get('url') or not snap.get('retrieved_at'):raise ValueError('来源地址或检索日期不符')
                    if fingerprint(snap.get('text',''))!=snap.get('text_sha256'):raise ValueError('来源正文指纹不符')
                    excerpt=source.get('excerpt','')
                    if len(excerpt.strip())<12 or excerpt not in snap['text']:raise ValueError('excerpt 未逐字来自已抓取正文')
                    if not source.get('supports'):raise ValueError('未说明来源支持哪条事实')
                    if snap.get('status')!='retrieved':raise ValueError('来源未成功抓取')
                except (OSError,ValueError,KeyError,TypeError) as exc:errors.append(key+' 来源证据无效：'+str(exc))
        if kind=='blanks':
            qids={str(q['id']):q for q in s.get('questions',[])}
            links=item.get('question_ids',[]);focus=item.get('focus_type')
            if focus not in ('answer_evidence','phonetic_difficulty'):errors.append(key+' focus_type 必须为 answer_evidence 或 phonetic_difficulty')
            if len(item.get('purpose','').strip())<8:errors.append(key+' 请说明为何遮这个表达')
            if focus=='answer_evidence':
                if not links or any(str(q) not in qids for q in links):errors.append(key+' 答案线索挖空必须关联本组真实题号')
                quote=pars.get(item.get('paragraph_id'),'')[item.get('start',0):item.get('end',0)]
                for q in links:
                    evidence=qids.get(str(q),{}).get('evidence',[])
                    if isinstance(evidence,dict):evidence=[evidence]
                    # Teacher/Agent must identify a full evidence context, not just tag an arbitrary question.
                    if not any(e.get('paragraph_id')==item.get('paragraph_id') and quote and quote in e.get('quote','') for e in evidence):errors.append(key+' 挖空不在关联题目的真实答案引句中')
            elif focus=='phonetic_difficulty' and len(item.get('phonetic_note','').strip())<8:errors.append(key+' 语音难点需注明连读、弱读、辨音等具体原因')
    if set(by)!=expected:errors.append('复核清单与本次所选内容不一致')
    return {'status':'review_recorded' if not errors else 'review_required','errors':errors,'items':len(expected),'note':'已记录有依据的独立复核；不代表程序自动判定所有事实或词义正确。'}

class TextExtractor(HTMLParser):
    def __init__(self):super().__init__();self.parts=[];self.hidden=0
    def handle_starttag(self,tag,attrs):
        if tag in ('script','style'):self.hidden+=1
    def handle_endtag(self,tag):
        if tag in ('script','style'):self.hidden=max(0,self.hidden-1)
        if tag in ('p','div','li','h1','h2','h3'):self.parts.append('\n')
    def handle_data(self,data):
        if not self.hidden:self.parts.append(data)

def capture(url,out):
    if not re.match(r'^https?://',url):raise ValueError('来源必须是 http(s) 网页')
    req=urllib.request.Request(url,headers={'User-Agent':'english-exam-studio-source-review/1.0'})
    with urllib.request.urlopen(req,timeout=25) as response:
        raw=response.read(3000001)
        if len(raw)>3000000:raise ValueError('来源超过3MB，请改用具体资料页')
        encoding=response.headers.get_content_charset() or 'utf-8'
        parser=TextExtractor();parser.feed(raw.decode(encoding,errors='replace'))
        text='\n'.join(' '.join(line.split()) for line in ''.join(parser.parts).splitlines() if line.strip())
        if len(text)<40:raise ValueError('来源正文不足，请核对是否被登录或访问限制拦截')
        data={'url':url,'resolved_url':response.url,'retrieved_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'text':text,'text_sha256':fingerprint(text),'status':'retrieved'}
    Path(out).parent.mkdir(parents=True,exist_ok=True);Path(out).write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8');return data

def selected(path,plan=None):
    data=json.loads(Path(path).read_text(encoding='utf-8'))
    if plan:
        from preferences import apply_plan
        data=apply_plan(data,json.loads(Path(plan).read_text(encoding='utf-8')))
    from build import prune_features
    return prune_features(data)

def main():
    from platform_tools import force_utf8
    force_utf8();p=argparse.ArgumentParser();sub=p.add_subparsers(dest='command',required=True)
    c=sub.add_parser('capture');c.add_argument('url');c.add_argument('--out',required=True)
    for name in ('draft','check'):
        c=sub.add_parser(name);c.add_argument('exam');c.add_argument('--plan');c.add_argument('--review');c.add_argument('--out')
    a=p.parse_args()
    try:
        if a.command=='capture':capture(a.url,a.out);print(json.dumps({'status':'retrieved','out':a.out}));return
        exam=selected(a.exam,a.plan)
        if a.command=='draft':
            if not a.out:raise ValueError('请用 --out 指定待复核清单路径')
            Path(a.out).write_text(json.dumps(draft(exam),ensure_ascii=False,indent=2),encoding='utf-8');print('已生成待复核清单，没有自动标通过');return
        if not a.review:raise ValueError('请用 --review 指定复核记录')
        r=validate(exam,json.loads(Path(a.review).read_text(encoding='utf-8')),Path(a.exam).parent);print(json.dumps(r,ensure_ascii=False,indent=2));return 0 if not r['errors'] else 2
    except (OSError,ValueError,KeyError) as e:p.exit(1,'ERROR: '+str(e)+'\n')
if __name__=='__main__':raise SystemExit(main())
