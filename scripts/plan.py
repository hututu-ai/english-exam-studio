#!/usr/bin/env python3
"""Turn a teacher's answers into a valid generation-plan.json.

Weak hosts (豆包工作 / WorkBuddy, plain chat) often have no real multi-select widget, so the
teacher replies with numbers — "1、3、5". Hand-converting that into the plan is where it goes
wrong: apply_plan refuses a plan that omits any of the seven features, and a silent miss turns
into a confusing build failure. This tool prints the canonical menu and does the conversion.

  python3 scripts/plan.py menu
  python3 scripts/plan.py make --confirmed --range B --features 1,3,5 --out generation-plan.json
  python3 scripts/plan.py make --confirmed --range C --sections reading,A --features all
  python3 scripts/plan.py check generation-plan.json
"""
import argparse,json,sys
from pathlib import Path
from platform_tools import explain_error,force_utf8

# 顺序与 references/teacher-options.md 一致，编号就是老师回复的编号。
FEATURES=[('annotations','批注','原文划线、记号与文字批注'),
          ('dictionary','查词','点词/划词查询；默认只内置本篇出现的词的离线释义'),
          ('quick_answers','速对答案','全部/按板块快速揭晓客观题与填空答案'),
          ('classroom_tools','课堂工具','计时、计分、待复讲、随机抽号、打印'),
          ('deep_reading','篇章精读','篇章结构、逻辑与信号词、课堂追问'),
          ('writing_transfer','写作迁移','原句表达效果、可复用句式、示范改写'),
          ('culture_background','文化背景','有来源的背景解读，默认关闭')]
RANGES={'A':('独立听力精听','listening','intensive'),'B':('整卷讲评','all','lesson'),'C':('指定板块',None,'lesson')}

def menu():
    lines=['本次生成先选范围，再选功能。范围单选，功能可多选（回复编号即可）。','',
           '第一问 · 这次做哪些内容？','  A. 独立听力精听（只做听力 Text，保留原题号与录音）',
           '  B. 整卷讲评（已提供的全部题型）','  C. 指定板块（请写出章节，如 reading,A,L6）','',
           '第二问 · 本次需要哪些功能？可多选，回复编号（例如 1、3、5），也可以说“全部”“基础讲评即可”“沿用上次”。']
    for index,(_,label,note) in enumerate(FEATURES,1):
        lines.append(f'  {index}. {label} —— {note}')
    lines+=['','说明：原文、题目、答案与解析、定位、必要译文、音频/倍速/精听挖空、备课编辑与课堂记录导出是基础功能，始终保留，不必勾选。',
            '未选择的扩展不会生成，也不显示入口。']
    return '\n'.join(lines)

def parse_features(raw,previous=None):
    text=(raw or '').strip()
    if text in {'沿用上次','同上次','same'}:
        if not previous:raise ValueError('选择“沿用上次”时必须提供 --previous 指向上次的 generation-plan.json')
        return {key:bool(previous['features'][key]) for key,_,_ in FEATURES}
    if text in {'全部','all','都要'}:return {key:True for key,_,_ in FEATURES}
    if text in {'基础讲评即可','都不要','none','无'}:return {key:False for key,_,_ in FEATURES}
    tokens=[token for token in text.replace('，',',').replace('、',',').replace(' ',',').split(',') if token]
    if not tokens:raise ValueError('请给出功能编号（如 1,3,5），或“全部/基础讲评即可/沿用上次”')
    chosen=set()
    for token in tokens:
        if not token.isdigit():raise ValueError(f'无法识别的功能选择：{token}（只接受编号或“全部/基础讲评即可/沿用上次”）')
        number=int(token)
        if not 1<=number<=len(FEATURES):raise ValueError(f'功能编号 {number} 超出范围 1–{len(FEATURES)}')
        chosen.add(number)
    return {key:(index in chosen) for index,(key,_,_) in enumerate(FEATURES,1)}

def make(args):
    previous=None
    if args.previous:
        path=Path(args.previous)
        if not path.is_file():raise ValueError(f'找不到上一份计划文件：{args.previous}（“沿用上次”需要它）')
        previous=json.loads(path.read_text(encoding='utf-8'))
    if not args.confirmed:raise ValueError('请确认已收到老师的范围与功能回答；不能未经回答就把 confirmed 置真')
    code=(args.range or '').strip().upper()
    if code not in RANGES:raise ValueError('请选择范围：A 独立听力精听 / B 整卷讲评 / C 指定板块')
    label,sections,mode=RANGES[code]
    if code=='C':
        if not args.sections:raise ValueError('选择“指定板块”时必须用 --sections 写出板块，如 reading,A,L6')
        sections=args.sections.strip()
    features=parse_features(args.features,previous)
    plan={'confirmed':True,'sections':sections,'mode':mode,'features':features}
    if getattr(args,'material',None):
        from task_contract import material_records
        import uuid
        plan.update(materials=material_records(args.material),task_id=str(uuid.uuid4()),teacher_response=getattr(args,'response','') or '')
    if args.profile:plan['profile']=args.profile
    return plan,f'范围：{label}（sections={sections}, mode={mode}）· 开启的功能：'+('、'.join(short for (key,short,_) in FEATURES if features[key]) or '无（仅基础功能）')

def check_data(plan):
    return _check_data(plan)['problems']

def check(path):
    return _check_data(json.loads(Path(path).read_text(encoding='utf-8')))

def _check_data(plan):
    keys={key for key,_,_ in FEATURES}
    given=set(plan.get('features',{}))
    problems=[]
    if given!=keys:
        missing=sorted(keys-given);unknown=sorted(given-keys)
        problems.append(f'功能必须七项全记：缺 {missing or "无"}，多 {unknown or "无"}')
    if plan.get('mode') not in ('lesson','intensive'):problems.append('mode 必须是 lesson 或 intensive')
    if not isinstance(plan.get('sections'),str) or not plan['sections'].strip():problems.append('sections 不能为空')
    if plan.get('profile') not in (None,'quick','full'):problems.append('profile 只能是 quick 或 full')
    if plan.get('confirmed') is not True:problems.append('confirmed 未置 true：还没有拿到老师的范围与功能回答')
    on=[short for (key,short,_) in FEATURES if plan.get('features',{}).get(key)]
    off=[short for (key,short,_) in FEATURES if key in plan.get('features',{}) and not plan['features'][key]]
    return {'status':'ok' if not problems else 'needs_fix','problems':problems,
            'range':plan.get('sections'),'mode':plan.get('mode'),'profile':plan.get('profile') or 'full',
            'enabled':on,'disabled':off}

def main():
    force_utf8()
    parser=argparse.ArgumentParser(description='把老师的回答变成合法的 generation-plan.json')
    sub=parser.add_subparsers(dest='command',required=True)
    sub.add_parser('menu',help='打印可照抄的范围与功能菜单')
    make_parser=sub.add_parser('make',help='按老师的回答生成计划')
    make_parser.add_argument('--range',required=True,help='A=独立听力精听 B=整卷讲评 C=指定板块')
    make_parser.add_argument('--sections',help='C 时必填，如 reading,A,L6')
    make_parser.add_argument('--features',required=True,help='编号如 1,3,5，或 全部/基础讲评即可/沿用上次')
    make_parser.add_argument('--previous',help='“沿用上次”时的上一份 generation-plan.json')
    make_parser.add_argument('--profile',choices=['quick','full'],help='不填则由构建按计划默认 full')
    make_parser.add_argument('--confirmed',action='store_true',help='确认已收到老师的范围与功能回答')
    make_parser.add_argument('--material',action='append',help='本次原件，重复填写 paper=路径 / answers=路径 / audio=路径')
    make_parser.add_argument('--response',help='老师实际的范围与功能回答，原样记录')
    make_parser.add_argument('--out',default='generation-plan.json')
    check_parser=sub.add_parser('check',help='检查已有计划是否可用')
    check_parser.add_argument('plan')
    args=parser.parse_args()
    try:
        if args.command=='menu':print(menu());return 0
        if args.command=='make':
            plan,summary=make(args)
            Path(args.out).write_text(json.dumps(plan,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
            print(json.dumps({'out':args.out,'summary':summary,'plan':plan},ensure_ascii=False,indent=2))
            return 0
        result=check(args.plan)
        print(json.dumps(result,ensure_ascii=False,indent=2))
        return 0 if result['status']=='ok' else 1
    except (OSError,ValueError,KeyError,json.JSONDecodeError) as error:
        print(f'ERROR: {explain_error(error)}',file=sys.stderr);return 1

if __name__=='__main__':raise SystemExit(main())
