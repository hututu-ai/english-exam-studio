#!/usr/bin/env python3
"""Create independent teacher-confirmed jobs; inspect actual per-paper delivery, not promises."""
import argparse,json,re,uuid
from pathlib import Path
from task_contract import material_records,sha
from plan import check_data
from platform_tools import force_utf8

def initialize(manifest,out):
    path=Path(manifest).resolve();d=json.loads(path.read_text(encoding='utf-8'));out=Path(out).resolve()
    if d.get('confirmed') is not True or not str(d.get('teacher_response','')).strip():raise ValueError('批量任务须先确认每套材料配对、生成范围与功能，并记录老师回答')
    papers=d.get('papers');jobs=[];ids=set();used={}
    if not isinstance(papers,list) or not papers:raise ValueError('批量清单没有试卷')
    for paper in papers:
        name=str(paper.get('id',''))
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',name) or name in ids:raise ValueError('每套试卷 ID 必须唯一且不包含路径：'+name)
        ids.add(name);settings={**d.get('settings',{}),**paper.get('settings',{}),'confirmed':True}
        problems=check_data(settings)
        if problems:raise ValueError(name+' 的范围与功能未完整确认：'+'；'.join(problems))
        specs=[]
        for role,files in (paper.get('materials') or {}).items():
            for file in files if isinstance(files,list) else [files]:specs.append(role+'='+str((path.parent/file).resolve()))
        rows=material_records(specs)
        if not any(r['role']=='paper' for r in rows):raise ValueError(name+' 缺少试卷材料')
        for row in rows:
            key=(row['role'],row['sha256'])
            if key in used and not paper.get('shared_materials_confirmed'):raise ValueError(name+' 与 '+used[key]+' 共用了同一材料，请核对是否配错；合卷材料需明确确认 shared_materials_confirmed')
            used[key]=name
        plan={**settings,'task_id':str(uuid.uuid4()),'teacher_response':d['teacher_response'],'materials':rows}
        jobs.append({'id':name,'directory':name,'plan':plan})
    # Validate every job before writing; never overwrite an earlier batch.
    if out.exists():raise ValueError('批量输出目录已存在，请用 status 检查原进度或另选新目录')
    out.mkdir(parents=True)
    for job in jobs:
        folder=out/job['directory'];folder.mkdir();(folder/'generation-plan.json').write_text(json.dumps(job.pop('plan'),ensure_ascii=False,indent=2),encoding='utf-8')
    (out/'batch.json').write_text(json.dumps({'jobs':jobs,'teacher_response':d['teacher_response']},ensure_ascii=False,indent=2),encoding='utf-8')
    return {'status':'planned','papers':len(jobs),'directory':str(out),'note':'尚未生成；逐套完成原件台账、内容、听力、正式构建与验收。'}

def status(directory):
    from verify_output import verify_output
    from task_contract import validate
    root=Path(directory).resolve();d=json.loads((root/'batch.json').read_text(encoding='utf-8'));rows=[]
    for job in d['jobs']:
        folder=(root/job['directory']).resolve()
        if folder.parent!=root:raise ValueError('批量任务目录越界')
        item={'id':job['id'],'status':'pending','missing':[]};output=folder/'output'
        needed=['index.html','exam.json','build-report.json','generation-plan.json','teaching-review.json','browser-check.json']
        item['missing']=[n for n in needed if not (output/n).is_file()]
        if not item['missing']:
            try:
                plan=json.loads((folder/'generation-plan.json').read_text(encoding='utf-8'))
                delivered=json.loads((output/'generation-plan.json').read_text(encoding='utf-8'))
                if plan!=delivered:raise ValueError('产物使用了另一套生成计划')
                validate(plan,folder/'source-ledger.json');verified=verify_output(output)
                report=json.loads((output/'build-report.json').read_text(encoding='utf-8'))
                browser=json.loads((output/'browser-check.json').read_text(encoding='utf-8'))
                if browser.get('status')!='passed' or browser.get('html_sha256')!=verified['html_sha256']:raise ValueError('浏览器验收未通过或不对应当前 HTML')
                if not report.get('task_contract') or report['task_contract'].get('task_id')!=plan['task_id']:raise ValueError('构建报告未绑定本套试卷')
                from teaching_review import validate as teaching_check
                data=json.loads((folder/'exam.json').read_text(encoding='utf-8'))
                from preferences import apply_plan
                review=json.loads((output/'teaching-review.json').read_text(encoding='utf-8'))
                from build import prune_features
                judgment=teaching_check(prune_features(apply_plan(data,plan)),review,folder)
                if judgment['errors']:raise ValueError('教学复核记录尚未完成或已过期')
                from qa_report import check as check_qa
                if check_qa(output)['status']!='ok':raise ValueError('逐题内容与试听复核记录未通过')
                item['status']='verified'
            except (OSError,ValueError,KeyError,ImportError) as error:item.update(status='needs_review',reason=str(error))
        rows.append(item)
    return {'status':'verified' if rows and all(x['status']=='verified' for x in rows) else 'incomplete','papers':rows,'note':'逐套状态；不可把部分通过宣称整批完成。'}

def main():
    force_utf8();p=argparse.ArgumentParser();sub=p.add_subparsers(dest='cmd',required=True)
    a=sub.add_parser('init');a.add_argument('manifest');a.add_argument('--out',required=True)
    a=sub.add_parser('status');a.add_argument('directory');args=p.parse_args()
    try:r=initialize(args.manifest,args.out) if args.cmd=='init' else status(args.directory);print(json.dumps(r,ensure_ascii=False,indent=2))
    except (OSError,ValueError,KeyError) as e:p.exit(1,str(e)+'\n')
if __name__=='__main__':main()
