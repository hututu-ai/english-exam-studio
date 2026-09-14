#!/usr/bin/env python3
"""Generate and verify qa-report.md — the human-review record that no machine can replace.

Several rules require the agent to write conclusions into qa-report.md (per-question answer
review, audio-boundary listening, culture semantics, browser interactions), but nothing created
or checked that file: its completeness depended entirely on the agent's diligence. This tool
pre-fills every item that machine evidence already knows about, and refuses to accept an item
whose conclusion is still empty or a placeholder.

  python3 scripts/qa_report.py init OUTPUT          # 生成待填的复核清单
  python3 scripts/qa_report.py check OUTPUT         # 校验每条结论都已填写
"""
import argparse,json,re,sys
from pathlib import Path
from platform_tools import explain_error,force_utf8

PLACEHOLDERS=('待填','待补充','待核','TODO','XXX','略')
MIN_CONCLUSION=6
SECTIONS=['## 1. 原件识别与答案比对','## 2. 解析自洽复核','## 3. 听力边界',
          '## 4. 浏览器实际操作','## 5. 未完成项与交付状态']
ITEM=re.compile(r'^- \[[ x]\] (.*)$')
CONCLUSION='结论：'

def _has_sentence_translations(output):
    """构建产物里是否含逐句译文：只有这时才要求人工核对这一条。"""
    try:exam=json.loads((Path(output)/'exam.json').read_text(encoding='utf-8'))
    except (OSError,ValueError):return False
    return any(p.get('sentence_translations') for s in exam.get('sections',[]) for p in s.get('paragraphs',[]))

# 明细每类最多列几条：清单要能一眼扫完；完整清单仍由 cost.py --duplicates 打印（已写在条目里）。
DETAIL_CAPS={'repeated_quotes':5,'exact_prose':3,'near_prose':3,'duplicate_entries':5}
DETAIL_MAX=12

def duplicate_rows(output,cap=DETAIL_MAX):
    """逐字重复项的**逐条**明细，供复核清单直接看，不必再跑一次命令。

    与构建报告里的计数同源：都来自 `cost.duplicates(exam)`，只是这里重新算一遍取明细
    （实测 320 题的卷子 0.26 秒，读文件的成本可以忽略；明细本来就没进 build-report）。
    """
    try:
        exam=json.loads((Path(output)/'exam.json').read_text(encoding='utf-8'))
    except (OSError,ValueError):
        return []
    try:
        from cost import duplicates
        found=duplicates(exam)
    except Exception:
        return []
    rows=[]
    for item in (found.get('repeated_quotes') or [])[:DETAIL_CAPS['repeated_quotes']]:
        rows.append(f"· 引文出现 {item.get('count')} 次（{item.get('chars')} 字符，可省 {item.get('saving')}）：{item.get('text')}…")
    for item in (found.get('exact_prose') or [])[:DETAIL_CAPS['exact_prose']]:
        rows.append(f"· 完全相同解析 {item.get('count')} 处（{item.get('chars')} 字符，可省 {item.get('saving')}）：{item.get('text')}…")
    for item in (found.get('near_prose') or [])[:DETAIL_CAPS['near_prose']]:
        rows.append(f"· 高度相似 {item.get('ratio')}（可省 {item.get('saving')}）：{item.get('sample')}…（{item.get('a')} ↔ {item.get('b')}）")
    for item in (found.get('duplicate_entries') or [])[:DETAIL_CAPS['duplicate_entries']]:
        rows.append(f"· 同节重复词条 {item.get('word')}：{item.get('a')} ↔ {item.get('b')}")
    if not rows:return []
    rows=rows[:cap]
    total=sum(int(found.get(key) or 0) if isinstance(found.get(key),int) else len(found.get(key) or []) for key in DETAIL_CAPS)
    if total>len(rows):rows.append(f'· 另有 {total-len(rows)} 条未列出：跑 python3 scripts/cost.py {Path(output).name}/exam.json --duplicates 看完整清单')
    return rows

def read_json(path,default=None):
    try:return json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError,ValueError):return default if default is not None else {}

def collect(output):
    output=Path(output)
    report=read_json(output/'build-report.json')
    audit=read_json(output/'answer-audit.json')
    browser=read_json(output/'browser-check.json')
    quality=report.get('quality_gate') or {}
    counts=(audit.get('counts') or {})
    items={key:[] for key in SECTIONS}
    items[SECTIONS[0]].append('原件识别：逐页核对题号、选项、标点、下划线、表格与页序')
    items[SECTIONS[0]].append(f"答案原件比对：official {counts.get('official',0)} 题 / inferred {counts.get('inferred',0)} / sample {counts.get('sample',0)} / unresolved {counts.get('unresolved',0)}")
    for row in (audit.get('review') or []):
        items[SECTIONS[0]].append(f"第{row.get('question')}题语义复核：{row.get('message','')}")
    for row in (audit.get('blocking') or []):
        items[SECTIONS[0]].append(f"第{row.get('question')}题阻断项复核：{row.get('message','')}")
    items[SECTIONS[1]].append('引文锚定：词句语境义、篇章结构、句子精讲均为本篇真实子串（由 scripts/grounding.py 校验）')
    if _has_sentence_translations(output):items[SECTIONS[1]].append('逐句译文：每句译文与原文分句一一对应，未译句子已在待核项列出（由构建校验对齐，语义仍须人工核对）')
    items[SECTIONS[1]].append('教学内容非套话、非占位：不同题目不得重复同一段分析（由构建校验）')
    cost=(report.get('authoring_cost') or {})
    index_total=sum((cost.get('review_index') or {}).values())
    if index_total>=8 or cost.get('same_phrase_total'):
        items[SECTIONS[1]].append(f"去重复核：本卷 {index_total} 处解析/题型说明/易错/方法无法用脚本判断是否在讲同一件事"
                                  f"（连续相同片段提示 {cost.get('same_phrase_total') or 0} 组）；请并排扫读，清单见 build-report.json 的 authoring_cost.review_index")
    # 可核对的重复项（逐字重复引文 / 重复解析 / 同节重复词条）也要落到复核清单里：
    # 只给"约省 N 字符"的总数不够——重复引文该改成 quote_ref、同节重复词条该删，处置方式不同。
    duplicate_labels=(('repeated_quotes','重复引文','组'),('exact_prose','完全相同解析','组'),
                      ('near_prose','高度相似解析','组'),('duplicate_entries','同节重复词条','处'))
    duplicates={key:int(cost.get(key) or 0) for key,_,_ in duplicate_labels}
    saving=int(cost.get('estimated_saving') or 0)
    if any(duplicates.values()):
        detail='、'.join(f'{label} {duplicates[key]} {unit}' for key,label,unit in duplicate_labels if duplicates[key])
        head=(f"逐字重复项（可核对，不必凭感觉；约可省 {saving} 字符）：{detail}。"
              f"重复引文优先改成 quote_ref 由脚本回填，同节重复词条可直接删；"
              f"清单：python3 scripts/cost.py {output.name}/exam.json --duplicates（或看 build-report.json 的 authoring_cost）")
        rows=duplicate_rows(output)
        items[SECTIONS[1]].append(head+(''.join('\n'+row for row in rows) if rows else ''))
    else:
        items[SECTIONS[1]].append('逐字重复项：无（重复引文 / 完全相同解析 / 高度相似解析 / 同节重复词条均为 0）')
    auto=[w for w in (quality.get('warnings') or []) if w.get('code')=='audio_alignment_auto_silence']
    if auto:
        for row in auto:items[SECTIONS[2]].append(f"{row.get('location')}：静音自动分段，逐段试听首尾并记录结论")
    else:
        items[SECTIONS[2]].append('听力边界：本卷按已验证切点或无听力处理，若有听力请回听确认首尾')
    ran=[c.get('name') for c in (browser.get('checks') or [])]
    named=[name for name in ran if isinstance(name,str) and name.strip()]
    items[SECTIONS[3]].append(f"已执行的浏览器操作 {len(ran)} 项：{'、'.join(named) if named else '（报告未逐项记录名称）'}")
    for row in (browser.get('skipped') or []):
        name=row.get('name') if isinstance(row.get('name'),str) and row.get('name').strip() else '未命名检查'
        items[SECTIONS[3]].append(f"未执行（跳过）：{name}（{row.get('reason') or '未说明原因'}）—— 该功能未经验证")
    for pending in (report.get('pending_items') or []):
        items[SECTIONS[4]].append(f"待核项：{pending}")
    if not items[SECTIONS[4]]:items[SECTIONS[4]].append('待核项：无')
    return items,report,browser

def render(items,report):
    lines=['# 交付前人工复核（qa-report）','',
           '本文件记录机器无法代替的判断。**构建与浏览器检查通过不等于内容正确。**',
           '每条把结论写在 `结论：` 之后；`python3 scripts/qa_report.py check OUTPUT` 会拒绝空结论与占位文字。','',
           f"版本：{report.get('profile','-')} 档 · 交付状态：{report.get('delivery_status','-')} · 生成时间见文件系统",'']
    for section in SECTIONS:
        lines.append(section);lines.append('')
        for item in items[section]:
            head,*detail=item.split('\n')
            lines.append(f'- [ ] {head} —— {CONCLUSION}')
            lines.extend('  '+row for row in detail)   # 明细行不是 "- [ ]"，不进条目计数
        lines.append('')
    lines+=['## 结论边界','',
            '- 结构校验、模板核验、浏览器点击分别只证明各自那一层，不能互相代替。',
            '- 未执行（跳过）的检查项必须在第 4 节写明，不得当作已通过。',
            '- 本文件由 Agent 填写；老师上课前抽查关键答案与音频切点。','']
    return '\n'.join(lines)

def check(output,path=None):
    output=Path(output);target=Path(path) if path else output/'qa-report.md'
    problems=[]
    if not target.is_file():
        return {'status':'missing','file':str(target),'problems':['缺少 qa-report.md：交付前必须写人工复核结论（可用 scripts/qa_report.py init 生成）']}
    text=target.read_text(encoding='utf-8')
    for section in SECTIONS:
        if section not in text:problems.append(f'缺少章节：{section}')
    total=0;filled=0
    for line in text.splitlines():
        match=ITEM.match(line.strip())
        if not match:continue
        total+=1
        item=match.group(1)
        if CONCLUSION not in item:
            problems.append(f'条目缺少“{CONCLUSION}”：{item[:40]}');continue
        conclusion=item.split(CONCLUSION,1)[1].strip()
        # 占位文字只有在"去掉占位词后几乎不剩内容"时才判为占位：老师/助手写"已核对，无待核项"
        # 是诚实结论，不能因为句子里出现"待核"就被拒；而单独一个"待填"必须被拒。
        residual=conclusion
        for marker in PLACEHOLDERS:residual=residual.replace(marker,'')
        residual=residual.strip('。.，,；;：:！!？?、　 ')
        if residual!=conclusion and len(residual)<MIN_CONCLUSION:
            problems.append(f'结论仍是占位文字（{conclusion[:20]}）：{item[:40]}')
        elif len(conclusion)<MIN_CONCLUSION:
            problems.append(f'结论过短（{conclusion or "空"}）：{item[:40]}')
        else:filled+=1
    if total==0:problems.append('没有任何“- [ ]”复核条目，文件可能被清空或改写')
    return {'status':'ok' if not problems else 'needs_fix','file':str(target),'items':total,'concluded':filled,'problems':problems}

def main():
    force_utf8()
    parser=argparse.ArgumentParser(description='生成/校验交付前的人工复核清单 qa-report.md')
    sub=parser.add_subparsers(dest='command',required=True)
    for name,help_text in (('init','按已有报告生成待填清单'),('check','校验每条结论都已填写')):
        node=sub.add_parser(name,help=help_text);node.add_argument('output')
        node.add_argument('--file',help='qa-report.md 路径（默认在输出目录下）')
        if name=='init':node.add_argument('--force',action='store_true',help='覆盖已存在的 qa-report.md')
        node.add_argument('--json',action='store_true')
    args=parser.parse_args()
    output=Path(args.output)
    target=Path(args.file) if args.file else output/'qa-report.md'
    try:
        if args.command=='init':
            if target.exists() and not args.force:
                print(json.dumps({'status':'exists','file':str(target),'message':'已存在 qa-report.md；确认要重写时加 --force（会丢失已填写的结论）'},ensure_ascii=False,indent=2));return 1
            items,report,_=collect(output)
            target.write_text(render(items,report),encoding='utf-8')
            result={'status':'ok','file':str(target),'items':sum(len(value) for value in items.values())}
        else:
            result=check(output,args.file)
        print(json.dumps(result,ensure_ascii=False,indent=2));return 0 if result['status']=='ok' else 1
    except (OSError,ValueError,KeyError) as error:
        print(f'ERROR: {explain_error(error)}',file=sys.stderr);return 1

if __name__=='__main__':raise SystemExit(main())
