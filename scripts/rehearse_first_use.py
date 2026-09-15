#!/usr/bin/env python3
"""把"老师第一次使用"整条路径重放一遍，并用实际输出出报告。

发布前跑一次（也可以老师在真机上跑），它按文档顺序执行：安装完整性 → 问范围与功能
→ 图片版材料登记 → 图片版答案绑定 → 构建 → 产物核验 → 浏览器验收（有工具时）
→ 人工复核清单 → 打包。**每一步记录真实状态，缺工具的步骤如实标 skipped，不算通过。**

  python3 scripts/rehearse_first_use.py [--workdir DIR] [--report-dir DIR] [--json]
"""
import argparse,base64,json,os,shutil,struct,subprocess,sys,tempfile,zlib
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from platform_tools import force_utf8

PNG=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==')

def run(args,cwd=None):
    # cwd 可能是老师的工作目录；此时 `scripts/x.py` 这类相对路径要按包根解析，否则找不到脚本。
    resolved=[str(ROOT/argument) if argument.startswith('scripts/') else argument for argument in args]
    result=subprocess.run([sys.executable,*resolved],capture_output=True,text=True,encoding='utf-8',errors='replace',cwd=str(cwd or ROOT),timeout=600)
    return result.returncode,(result.stdout or '').strip(),(result.stderr or '').strip()

def as_json(text):
    """从脚本输出里取出 JSON 对象：容忍 JSON 前后的提示行。

    只吃"第一个完整对象"（raw_decode），因为有的脚本会在 JSON 之后再打印一行给人看的话；
    以前直接 `json.loads(text[start:])` 遇到那种输出会抛异常，把**整条重放**崩掉，
    而不是只让这一步失败。解析不出来时返回空对象，让这一步如实标 failed 并附原始输出。
    """
    start=text.find('{')
    if start<0:return {}
    try:return json.JSONDecoder().raw_decode(text[start:])[0]
    except ValueError:return {}

def picture(path,size=64,color=(60,90,120)):
    """生成一张真实的 PNG（纯标准库），充当"老师拍的一页"与"答案截图"。

    每页颜色不同：image_pages 会把内容相同的两页判为 duplicate_page（重复拍/漏拍），
    所以夹具也必须是两页不同的图，否则测的是夹具的错而不是流程。
    """
    width=height=size
    raw=b''.join(b'\x00'+bytes(color)*width for _ in range(height))
    def chunk(tag,data):return struct.pack('>I',len(data))+tag+data+struct.pack('>I',zlib.crc32(tag+data)&0xffffffff)
    path.write_bytes(b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',width,height,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(raw))+chunk(b'IEND',b''))

# ── 每一步的判定标准 ────────────────────────────────────────────────────────────
# 抽成独立函数（1.0.112）：以前这些判据写成 `rehearse()` 里的内联表达式，只有一路绿灯的
# 端到端重放能覆盖它们——把判据改坏一处不会被任何测试抓到。现在每条都能单独喂"做坏的输入"。
# 所有函数都只用 `.get`，所以脚本输出解析失败（空对象）时一律判为不通过，不会抛异常。
STEP_COUNT=9

def install_ok(report):
    """第 1 步：安装必须 `complete`。只看 VERSION 或"看得到文件"不算装上。"""
    return report.get('status')=='complete'

def plan_ok(plan):
    """第 2 步：七项功能**全记**且老师已确认（`--confirmed`）；缺一项或没确认都不算。"""
    features=plan.get('features') or {}
    return len(features)==7 and bool(plan.get('confirmed'))

def inventory_ok(inventory):
    """第 3 步：图片登记要有真实页数且**没有 problems**（重复页/漏页都算 problems）。"""
    return bool(inventory.get('logical_pages')) and not (inventory.get('problems') or [])

def answers_ok(table):
    """第 4 步：答案表必须来自图片转录且有题数；普通解析（parsed）不走这条。"""
    return table.get('answer_source_kind')=='image_transcription' and bool(table.get('count'))

def build_ok(report):
    """第 5 步：构建必须 `structural_checks_passed`（而不是只看退出码）。"""
    return report.get('status')=='structural_checks_passed'

def verify_ok(report):
    """第 6 步：产物核验必须 `passed`。"""
    return report.get('status')=='passed'

def browser_ok(evidence):
    """第 7 步：浏览器证据必须 `passed`；缺工具时这一步标 skipped，不走这个判据。"""
    return evidence.get('status')=='passed'

def qa_ok(items,code_unfilled,code_filled):
    """第 8 步：清单非空，且**未填写时退出 1、填写后退出 0**——只生成不校验不算过。"""
    return bool(items) and code_unfilled==1 and code_filled==0

def package_ok(report):
    """第 9 步：`browser_checked`（有浏览器验收）或 `preview_only_browser_check_pending`（如实降级）。"""
    return report.get('status') in ('browser_checked','preview_only_browser_check_pending')

def rehearse(work,reports,skip_browser=False):
    work=Path(work);reports=Path(reports)
    work.mkdir(parents=True,exist_ok=True);reports.mkdir(parents=True,exist_ok=True)
    steps=[];state={}
    def step(name,status,detail='',output=''):
        steps.append({'name':name,'status':status,'detail':detail,'output':output[:2000]})
        return status=='passed'
    # 1 安装完整性
    code,out,err=run(['scripts/check_install.py'])
    report=as_json(out)
    step('1. 安装完整性','passed' if install_ok(report) else 'failed',
         f"status={report.get('status')} · version={report.get('version')} · files={report.get('checked_files')}",out or err)
    # 2 问范围与功能（老师回复编号）
    code,out,err=run(['scripts/plan.py','make','--confirmed','--range','B','--features','1,2,3,5','--out',str(work/'plan.json')])
    plan=json.loads((work/'plan.json').read_text(encoding='utf-8')) if (work/'plan.json').is_file() else {}
    features=plan.get('features') or {}
    step('2. 老师选范围与功能',('passed' if plan_ok(plan) else 'failed'),
         f"scope={plan.get('sections')}/{plan.get('mode')} · 七项全记={len(features)==7} · 开启={[k for k,v in features.items() if v]}",out or err)
    # 3 图片版材料登记（老师只有照片）
    paper=work/'试卷图片';paper.mkdir(exist_ok=True)
    picture(paper/'卷面-01.png',color=(60,90,120));picture(paper/'卷面-02.png',size=72,color=(120,60,60))
    code,out,err=run(['scripts/image_pages.py','--dir','试卷图片','--role','paper','--spread','--out','paper-inventory.json'],cwd=work)
    paper_inv=json.loads((work/'paper-inventory.json').read_text(encoding='utf-8')) if (work/'paper-inventory.json').is_file() else {}
    step('3. 图片版试卷登记',('passed' if inventory_ok(paper_inv) else 'failed'),
         f"张数={paper_inv.get('page_count')} · 真实页数={paper_inv.get('logical_pages')} · problems={len(paper_inv.get('problems') or [])}",out or err)
    # 4 图片版答案 → answers.json（指纹绑到那组图片）
    answers_dir=work/'答案图片';answers_dir.mkdir(exist_ok=True)
    picture(answers_dir/'答案-01.png')
    code,out,err=run(['scripts/image_pages.py','--dir','答案图片','--role','answers','--out','answer-inventory.json'],cwd=work)
    (work/'答案转录.txt').write_text('21 B\n22 C\n',encoding='utf-8')
    code,out,err=run(['scripts/answers.py','extract','答案转录.txt','--source-images','answer-inventory.json','--out','answers.json'],cwd=work)
    table=json.loads((work/'answers.json').read_text(encoding='utf-8')) if (work/'answers.json').is_file() else {}
    step('4. 图片版答案绑定',('passed' if answers_ok(table) else 'failed'),
         f"来源={table.get('answer_source_kind')} · 题数={table.get('count')}",out or err)
    # 5 构建（用包内示例卷，按老师的计划）
    code,out,err=run(['scripts/build.py','--demo','examples/demo-exam.json',str(work/'out'),'--source-ledger','examples/source-ledger.json','--plan',str(work/'plan.json')])
    built=as_json(out)
    step('5. 构建',('passed' if build_ok(built) else 'failed'),
         f"status={built.get('status')} · 模板={built.get('template_verification',{}).get('status')} {built.get('template_verification',{}).get('template_version')} · 节={built.get('sections')} 题={built.get('questions')}",out or err)
    # 6 产物核验
    code,out,err=run(['scripts/verify_output.py',str(work/'out')])
    verified=as_json(out)
    step('6. 产物核验',('passed' if verify_ok(verified) else 'failed'),f"status={verified.get('status')} · 模板={verified.get('comparison')}",out or err)
    # 7 浏览器验收（有工具才跑）
    browser='skipped'
    if skip_browser:
        step('7. 浏览器验收','skipped','按 --no-browser 跳过；跳过不算通过')
    else:
        node=shutil.which('node');module=os.environ.get('PLAYWRIGHT_MODULE','playwright')
        probe=subprocess.run([node,'-e',f"try{{require({module!r})}}catch(e){{process.exit(3)}}"],capture_output=True) if node else None
        if not node or probe.returncode!=0:
            step('7. 浏览器验收','skipped','没有 node/Playwright：只交付标注「待浏览器验收」的版本')
        else:
            result=subprocess.run([node,str(ROOT/'scripts/browser_check.cjs'),str(work/'out')],capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=300,env={**os.environ,'BROWSER_ENGINE':'chromium'})
            evidence=json.loads((work/'out'/'browser-check.json').read_text(encoding='utf-8'))
            browser=evidence.get('status')
            step('7. 浏览器验收',('passed' if browser_ok(evidence) else 'failed'),
                 f"status={evidence.get('status')} · 通过={len(evidence.get('checks') or [])} · 跳过={len(evidence.get('skipped') or [])} · errors={len(evidence.get('errors') or [])}",
                 (result.stdout or '')[-1200:])
    # 8 人工复核清单
    code,out,err=run(['scripts/qa_report.py','init',str(work/'out')])
    items=as_json(out).get('items',0)
    code_unfilled,_,_=run(['scripts/qa_report.py','check',str(work/'out')])
    qa=work/'out'/'qa-report.md'
    if qa.is_file():
        import re
        qa.write_text(re.sub(r'—— 结论：$','—— 结论：首次使用重放自检，逐条按实际证据填写。',qa.read_text(encoding='utf-8'),flags=re.M),encoding='utf-8')
    code_filled,out2,_=run(['scripts/qa_report.py','check',str(work/'out')])
    step('8. 人工复核清单',('passed' if qa_ok(items,code_unfilled,code_filled) else 'failed'),
         f"条目={items} · 未填写时退出={code_unfilled} · 填写后退出={code_filled} · {as_json(out2).get('concluded')}/{items}",out2)
    # 9 打包：没有浏览器验收时只能交"待验收版"（这正是文档写明的降级路径）
    command=['scripts/package_lesson.py',str(work/'out'),str(work/'first-use.zip')]
    if browser!='passed':command.append('--allow-unchecked')
    code,out,err=run(command)
    packed=as_json(out)
    step('9. 打包',('passed' if package_ok(packed) else 'failed'),
         f"status={packed.get('status')} · {'（无浏览器验收，按文档交付待验收版）' if browser!='passed' else ''} zip={Path(str(packed.get('zip',''))).name}",out or err)
    assert len(steps)==STEP_COUNT,f'重放步骤数应为 {STEP_COUNT} 步（文档与报告都按九步描述），实际 {len(steps)} 步'
    summary={status:sum(1 for item in steps if item['status']==status) for status in ('passed','failed','skipped')}
    report={'version':(ROOT/'VERSION').read_text(encoding='utf-8').strip(),'summary':summary,'steps':steps,
            'browser_verified':browser=='passed',
            'note':'本报告只证明这台机器上这条路径能走通；不证明真实试卷内容、答案正确性、听力边界或宿主端到端。跳过的步骤不算通过。'}
    (reports/'first-use-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    lines=[f"# 首次使用重放报告 · {report['version']}",'',
           f"通过 {summary['passed']} / 失败 {summary['failed']} / 跳过 {summary['skipped']}",'']
    for item in steps:lines.append(f"- [{item['status']}] {item['name']}：{item['detail']}")
    lines+=['',report['note']]
    (reports/'first-use-report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    return report

def main():
    force_utf8()
    parser=argparse.ArgumentParser(description='把老师第一次使用的整条路径重放一遍并出报告')
    parser.add_argument('--workdir',default='first-use-work')
    parser.add_argument('--report-dir',default='first-use-report')
    parser.add_argument('--no-browser',action='store_true')
    parser.add_argument('--json',action='store_true')
    args=parser.parse_args()
    report=rehearse(args.workdir,args.report_dir,skip_browser=args.no_browser)
    if args.json:print(json.dumps(report,ensure_ascii=False,indent=2))
    else:
        for item in report['steps']:print(f"[{item['status']}] {item['name']}：{item['detail']}")
        print(json.dumps(report['summary'],ensure_ascii=False))
        print(f"报告：{Path(args.report_dir).resolve()}/first-use-report.json")
    return 1 if report['summary']['failed'] else 0

if __name__=='__main__':raise SystemExit(main())
