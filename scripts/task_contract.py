"""Bind each new lesson to the teacher's choices and current material bytes."""
import hashlib,json
from pathlib import Path

def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for part in iter(lambda:f.read(1048576),b''):h.update(part)
    return h.hexdigest()

def material_records(specs):
    rows=[]
    for spec in specs:
        role,sep,name=spec.partition('=')
        if not sep or role not in ('paper','answers','audio'):raise ValueError('材料应写成 paper=路径、answers=路径或 audio=路径')
        p=Path(name).expanduser().resolve()
        if not p.is_file():raise ValueError('材料文件不存在：'+str(p))
        rows.append({'role':role,'path':str(p),'sha256':sha(p)})
    if not rows:raise ValueError('新建课件必须登记本次材料，不能沿用未知试卷')
    return rows

def validate(plan,ledger):
    from plan import check_data
    issues=check_data(plan)
    if issues:raise ValueError('计划无效：'+'；'.join(issues))
    if not isinstance(plan.get('teacher_response'),str) or not plan['teacher_response'].strip():raise ValueError('缺少老师本次的范围与功能回答；请询问后原样记录 teacher_response')
    if not plan.get('task_id'):raise ValueError('缺少本次 task_id，请重新用 plan.py make 建立计划')
    rows=plan.get('materials',[])
    if not rows:raise ValueError('计划未绑定本次材料，请用 --material 登记文件')
    for row in rows:
        if not Path(row.get('path','')).is_file() or sha(row['path'])!=row.get('sha256'):raise ValueError('材料已变化或无法读取，请确认新材料并更新计划：'+row.get('path','未知文件'))
    if not ledger:raise ValueError('新任务必须提供独立 source-ledger.json')
    data=json.loads(Path(ledger).read_text(encoding='utf-8'))
    def hashes(x):
        if isinstance(x,dict):
            for k,v in x.items():
                if k=='sha256' and isinstance(v,str):yield v
                else:yield from hashes(v)
        elif isinstance(x,list):
            for v in x:yield from hashes(v)
    known=set(hashes(data))
    for row in rows:
        if row['role'] in ('paper','answers') and row['sha256'] not in known:raise ValueError('本次材料与来源台账不一致：'+row['role'])
    return {'task_id':plan['task_id'],'materials':rows,'teacher_response':plan['teacher_response'],'confirmed':True}

def rebuild_plan(directory,src,ledger):
    root=Path(directory)
    for name in ('index.html','exam.json','build-report.json','generation-plan.json'):
        if not (root/name).is_file():raise ValueError('不能重建：旧课件缺少 '+name+'。请先重新确认范围与功能建立计划')
    report=json.loads((root/'build-report.json').read_text(encoding='utf-8'))
    # Verify the old output using its own recorded hash, without requiring today's template.
    recorded=report.get('template_verification',{}).get('html_sha256')
    if not recorded or sha(root/'index.html')!=recorded:raise ValueError('旧 HTML 与构建记录不符，不能把它当已核对的旧课件')
    plan=json.loads((root/'generation-plan.json').read_text(encoding='utf-8'));validate(plan,ledger)
    return plan
