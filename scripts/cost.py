#!/usr/bin/env python3
"""Estimate the authoring (token) cost of a lesson and point at real savings.

No network, no model calls, no money estimates. It counts the characters the
agent must actually write, versus characters that are source text or that can be
referenced by range and filled in by scripts/quotes.py. Long quotes pasted
inline are paid for twice — once when read, once when written — so the biggest
honest saving is replacing them with {{"quote_ref":[start,end]}}.

Usage:
  python3 scripts/cost.py WORK/exam.json [--plan WORK/generation-plan.json] [--json]
"""
import argparse,json,re,sys
from pathlib import Path
from exam_document import load as load_exam

# Prose the agent has to author (teaching judgement, not copyable from the paper).
AUTHORED_KEYS={
    'question_type','type_note','pitfall','analysis','strategy','explanation','meaning','context',
    'collocations','distinguish','teaching_prompt','transfer','note','backbone','chunks','logic',
    'translation','sentence_translations','title','why','frame','scene','example','task','check','reading_connection',
    'teaching_note','label','question','answer','prompt','outline','language','rule',
}
# Fields that must be an exact substring of the source, and can therefore be a range reference.
QUOTE_KEYS={'quote','source_quote'}
# Representative size of a range reference such as {"quote_ref":[120,158]}.
REF_OVERHEAD=28
# 引文重复的长度下限：太短的重复（如 's'、'略'）不值得报
QUOTE_FLOOR=20

def walk(node,path=''):
    if isinstance(node,dict):
        for key,value in node.items():
            yield from walk(value,f'{path}.{key}' if path else key)
    elif isinstance(node,list):
        for index,value in enumerate(node):
            yield from walk(value,f'{path}[{index}]')
    else:
        yield path,node

def lastkey(path):
    return re.sub(r'\[\d+\]$','',path).rsplit('.',1)[-1]

def duplicates(exam,threshold=0.9,min_chars=30,max_items=400):
    """找出"白写两遍"的内容：重复引文、重复/近重复的解析、重复条目。

    只做可核对的字面比较（完全相同 + difflib 相似度），不判断教学价值；
    省下的是抄写与重复编写，不是教学判断。
    """
    import difflib
    exam={k:v for k,v in exam.items() if k not in ('dictionary','legacy_dictionary')}
    quotes=[];prose=[];entries=[]
    for path,value in walk(exam):
        if not isinstance(value,str) or not value.strip():continue
        key=lastkey(path)
        if key in QUOTE_KEYS:quotes.append((path,value.strip()))
        elif key in AUTHORED_KEYS:prose.append((path,value.strip()))
        if key in ('word',):entries.append((path,value.strip().lower()))
    # 1) 逐字重复的引文
    same={}
    for path,value in quotes:same.setdefault(value,[]).append(path)
    repeated_quotes=[{'text':value[:60],'chars':len(value),'count':len(paths),'paths':paths[:6],
                      'saving':len(value)*(len(paths)-1)} for value,paths in same.items()
                     if len(paths)>1 and len(value)>=QUOTE_FLOOR]
    # 2) 重复/近重复的解析文字（跨节也算，构建只拦同一节内的完全重复）
    groups={}
    for path,value in prose:groups.setdefault(value,[]).append(path)
    exact=[{'text':value[:60],'chars':len(value),'count':len(paths),'paths':paths[:6],
            'saving':len(value)*(len(paths)-1)} for value,paths in groups.items()
           if len(paths)>1 and len(value)>=min_chars]
    near=[];seen=set()
    sample=[(p,v) for p,v in prose if len(v)>=min_chars][:max_items]
    # 两两比对是 O(n²)，而 ratio() 很贵：真实整卷（几十节、几百条解析）光这一项就要几秒到十几秒，
    # 而它只是"编写量报告"，不该拖慢构建。这里用 difflib 自己保证的两个**上界**先筛：
    #   * 长度上界：ratio() <= 2*min(len_a,len_b)/(len_a+len_b)（排序后长度只增，不达标就 break）；
    #   * 字符多重集上界：quick_ratio() 是 ratio() 的上界（文档明示），比 ratio() 便宜得多。
    # 两个上界都不改结果：只有可能 >=threshold 的组合才真的去算 ratio()。
    order=sorted(range(len(sample)),key=lambda index:len(sample[index][1]))
    for position,index in enumerate(order):
        pa,va=sample[index];la=len(va)
        for other in order[position+1:]:
            pb,vb=sample[other];lb=len(vb)
            if 2*la<threshold*(la+lb):break          # la<=lb，再往后长度更大，更不可能达标
            if va==vb:continue
            if (va,vb) in seen:continue
            matcher=difflib.SequenceMatcher(None,va,vb)
            if matcher.real_quick_ratio()<threshold or matcher.quick_ratio()<threshold:continue
            ratio=matcher.ratio()
            if ratio>=threshold:
                seen.add((va,vb))
                near.append({'ratio':round(ratio,2),'chars':min(len(va),len(vb)),'saving':min(len(va),len(vb)),
                             'a':pa,'b':pb,'sample':va[:50],'_i':index,'_j':other})
    near.sort(key=lambda item:(-item['saving'],item['_i'],item['_j']))   # 与逐对扫描的顺序一致，去掉临时下标
    for item in near:item.pop('_i');item.pop('_j')
    # 3) 同一节的同名词条重复（quick_words / vocabulary 里同一个词写两遍）
    duplicate_entries=[]
    for index,(path,value) in enumerate(entries):
        for other_path,other in entries[index+1:]:
            if value==other and path.split('.')[0]==other_path.split('.')[0]:
                duplicate_entries.append({'word':value,'a':path,'b':other_path,'saving':len(value)})
    saving=sum(item['saving'] for item in repeated_quotes)+sum(item['saving'] for item in exact)+ \
           sum(item['saving'] for item in near)+sum(item['saving'] for item in duplicate_entries)
    return {'repeated_quotes':repeated_quotes,'exact_prose':exact,'near_prose':near[:20],
            'duplicate_entries':duplicate_entries[:20],
            'estimated_saving':saving,'threshold':threshold,'min_chars':min_chars,
            'scope':'重复内容检测只做字面比较；相似不代表可删，删改前要确认教学上确实重复。'}

def candidate_pairs(texts,min_common):
    """返回"可能含 >=min_common 字连续相同片段"的下标对，按 (i,j) 升序。

    做法是倒排索引：把每个文本切成 min_common 长的片段，只有共享过至少一个片段的两个文本
    才可能命中。这是**必要**条件，所以不会漏报；片段太短（min_common<4）时倒排表会爆炸，
    直接退回全量两两组合（结果相同，只是慢）。
    """
    if min_common<4:
        return [(i,j) for i in range(len(texts)) for j in range(i+1,len(texts))]
    from collections import defaultdict
    buckets=defaultdict(list)
    for index,text in enumerate(texts):
        if len(text)<min_common:continue
        for gram in {text[start:start+min_common] for start in range(len(text)-min_common+1)}:
            buckets[gram].append(index)
    pairs=set()
    for members in buckets.values():
        if len(members)<2:continue
        for position,left in enumerate(members):
            for right in members[position+1:]:
                pairs.add((left,right))
    return sorted(pairs)

def review_pairs(exam,fields=('analysis','type_note','pitfall','strategy','context','note','why','explanation'),min_common=10):
    """去重复核清单：把同类解析文字按题号列出来，并给出"连续相同片段"这一弱信号。

    为什么不做"相似度>=X 就算重复"：实测中文改写（"先看首段…" vs "先读第一段…"）字符相似度只有 0.54，
    任何合理阈值都会漏；而调低阈值又会把无关内容全抓进来。所以这里**不声称能检测改写**，
    只把同类内容并排交给人工扫一遍，并用"有 ≥min_common 字连续相同"提示可能同源。
    """
    import difflib
    from collections import defaultdict
    index=defaultdict(list)
    for path,value in walk(exam):
        if not isinstance(value,str) or not value.strip():continue
        key=lastkey(path)
        if key in fields:index[key].append({'path':path,'chars':len(value.strip()),'text':value.strip()[:60]})
    hints=[]
    for key,rows in index.items():
        # 逐对比 find_longest_match 是 O(n²) 次昂贵比较（32 节 0.6s、64 节 2.4s）。
        # 先用一条**必要**条件把候选对缩到"至少共有一个 min_common 字片段"（倒排索引），
        # 再做原来的比较：最长公共片段若 >=min_common，两者必然共享一个该长度的片段。
        # 判定与输出顺序都不变（候选对按 (i,j) 升序遍历，等价于原来的双循环顺序）。
        for i,j in candidate_pairs([row['text'] for row in rows],min_common):
            a,b=rows[i]['text'],rows[j]['text']
            match=difflib.SequenceMatcher(None,a,b).find_longest_match(0,len(a),0,len(b))
            if match.size>=min_common:
                hints.append({'field':key,'common_chars':match.size,'shared':a[match.a:match.a+match.size],
                              'a':rows[i]['path'],'b':rows[j]['path']})
    hints.sort(key=lambda item:item['common_chars'],reverse=True)
    return {'index':{key:rows for key,rows in sorted(index.items())},'counts':{key:len(rows) for key,rows in index.items()},
            'same_phrase_hints':hints[:20],'hint_total':len(hints),'min_common':min_common,
            'scope':'脚本不判断"换一种说法讲同一件事"；本清单只把同类内容并排列出，供人工扫读。'}

def analyze(exam,min_quote=40):
    # The bundled dictionary is injected into lessons but is not authored prose.
    exam={k:v for k,v in exam.items() if k not in ('dictionary','legacy_dictionary')}
    authored=[(p,v) for p,v in walk(exam) if lastkey(p) in AUTHORED_KEYS and isinstance(v,str) and v.strip()]
    quotes=[(p,v) for p,v in walk(exam) if lastkey(p) in QUOTE_KEYS and isinstance(v,str) and v.strip()]
    source_chars=sum(len(p.get('text','')) for s in exam.get('sections',[]) for p in s.get('paragraphs',[]))
    candidates=[{'path':p,'chars':len(v),'saving':len(v)-REF_OVERHEAD} for p,v in quotes if len(v)>min_quote and len(v)>REF_OVERHEAD]
    saving=sum(c['saving'] for c in candidates)
    sections=exam.get('sections',[])
    questions=[q for s in sections for q in s.get('questions',[]) or []]
    notes=[]
    if candidates:
        notes.append(f"{len(candidates)} 处长引文可改为 quote_ref，用 scripts/quotes.py fill 自动回填，约省 {saving} 字符（每处省去逐字抄写与核对）")
    else:
        notes.append('没有超过阈值的逐字引文；引文已经较短或已使用 quote_ref')
    if len(sections)>1:
        notes.append('多节可用 scripts/parts.py split 拆成单节文件后并行写作，再 merge 合并，返工只改一节')
    notes.append('先用 scope.py 或 --sections 只处理本次要讲的板块，未选章节不编写；需要先出可上课版时用 --profile quick')
    notes.append('有同源带时间转写时复用，不重复 ASR；重复构建只改文字不重切音频')
    dup=duplicates(exam);review=review_pairs(exam)
    if review['hint_total']:
        notes.append(f"{review['hint_total']} 组解析文字含有 ≥{review['min_common']} 字连续相同片段，可能同源；"
                     f"换一种说法讲同一件事脚本判断不了，请跑 cost.py --duplicates 看清单后人工扫一遍")
    if dup['estimated_saving']:
        notes.append(f"检测到重复内容：逐字重复引文 {len(dup['repeated_quotes'])} 组、完全相同解析 {len(dup['exact_prose'])} 组、"
                     f"高度相似解析 {len(dup['near_prose'])} 组、重复词条 {len(dup['duplicate_entries'])} 处，"
                     f"合计约 {dup['estimated_saving']} 字符可省（用 cost.py --duplicates 看清单；删改前确认教学上确实重复）")
    else:
        notes.append('没有发现重复引文或重复解析：这部分没有可省的抄写量')
    return {
        'sections':len(sections),'questions':len(questions),
        'paragraphs':sum(len(s.get('paragraphs',[])) for s in sections),
        'source_chars':source_chars,
        'authored_chars':sum(len(v) for _,v in authored),
        'authored_fields':len(authored),
        'quote_chars':sum(len(v) for _,v in quotes),
        'inline_quotes':len(quotes),
        'long_quote_candidates':sorted(candidates,key=lambda c:c['saving'],reverse=True),
        'estimated_quote_ref_saving':saving,
        'min_quote':min_quote,
        'duplicates':{'estimated_saving':dup['estimated_saving'],'repeated_quotes':len(dup['repeated_quotes']),
                      'exact_prose':len(dup['exact_prose']),'near_prose':len(dup['near_prose']),
                      'duplicate_entries':len(dup['duplicate_entries'])},
        'review_index':review['counts'],'same_phrase_hints':review['same_phrase_hints'],
        'same_phrase_total':review['hint_total'],
        'notes':notes,
        'scope':'作者负担估算，不是 token 计费、不是模型速度承诺；引文回填只省抄写，不省教学判断。',
    }

def main():
    parser=argparse.ArgumentParser(description='估算编写负担并指出可省的部分')
    parser.add_argument('input');parser.add_argument('--plan');parser.add_argument('--json',action='store_true')
    parser.add_argument('--min-quote',type=int,default=40,help='超过多少字符的引文建议改为 quote_ref')
    parser.add_argument('--duplicates',action='store_true',help='列出重复引文、重复/近重复解析与重复词条')
    args=parser.parse_args()
    sys.path.insert(0,str(Path(__file__).resolve().parent))
    from platform_tools import force_utf8
    force_utf8()
    exam=load_exam(args.input)
    if args.plan:
        plan=json.loads(Path(args.plan).read_text(encoding='utf-8'))
        # Report only the sections the teacher actually chose, mirroring build.py's scope.
        try:
            sys.path.insert(0,str(Path(__file__).resolve().parent))
            from scope import select
            exam=select(exam,plan.get('sections','all'),plan.get('mode'))
        except Exception as error:
            print(f'警告：无法按计划筛选范围（{error}），改为统计整卷',file=sys.stderr)
    report=analyze(exam,args.min_quote)
    if args.json:print(json.dumps(report,ensure_ascii=False,indent=2))
    else:
        print(f"章节 {report['sections']} · 题目 {report['questions']} · 原文 {report['source_chars']} 字符")
        print(f"需要编写 {report['authored_chars']} 字符（{report['authored_fields']} 处）；逐字引文 {report['quote_chars']} 字符（{report['inline_quotes']} 处）")
        for note in report['notes']:print('· '+note)
        if args.duplicates:
            detail=duplicates(load_exam(args.input))
            if not detail['estimated_saving']:
                print('\n重复内容：无')
            else:
                print(f"\n重复内容清单（约可省 {detail['estimated_saving']} 字符）：")
                for item in detail['repeated_quotes']:
                    print(f"  · 引文出现 {item['count']} 次（{item['chars']} 字符，省 {item['saving']}）：{item['text']}…")
                    print(f"      {item['paths'][:4]}")
                for item in detail['exact_prose']:
                    print(f"  · 完全相同解析 {item['count']} 处（{item['chars']} 字符，省 {item['saving']}）：{item['text']}…")
                    print(f"      {item['paths'][:4]}")
                for item in detail['near_prose']:
                    print(f"  · 高度相似 {item['ratio']}（省 {item['saving']}）：{item['sample']}…")
                    print(f"      {item['a']} ↔ {item['b']}")
                for item in detail['duplicate_entries']:
                    print(f"  · 同一节重复词条 {item['word']}：{item['a']} ↔ {item['b']}")
                print('  注意：字面相似不等于教学上重复，删改前请自己判断。')
            print('\n去重复核清单（脚本不判断改写，请并排扫读）：')
            review=review_pairs(load_exam(args.input))
            for field,rows in review['index'].items():
                print(f"  · {field}（{len(rows)} 处）")
                for row in rows[:12]:print(f"      {row['chars']} 字 {row['path']}：{row['text']}…")
            for hint in review['same_phrase_hints']:
                print(f"  ! 可能同源（连续 {hint['common_chars']} 字相同「{hint['shared']}」）：{hint['a']} ↔ {hint['b']}")
    return 0

if __name__=='__main__':
    try:raise SystemExit(main())
    except SystemExit:raise
    # 给错文件（把 generation-plan.json 当成 exam.json）以前会漏出英文 AttributeError 堆栈；
    # 这里统一成与其它脚本一致的「ERROR: 中文说明」。
    except (OSError,ValueError,KeyError,IndexError,AttributeError,TypeError,json.JSONDecodeError) as error:
        from platform_tools import explain_error
        raise SystemExit('ERROR: '+explain_error(error))
