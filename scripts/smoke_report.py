#!/usr/bin/env python3
"""One command to collect a real-machine acceptance report.

Runs 安装完整性 → 宿主能力 → 示例构建 → 模板核验 → 浏览器点击 → 打包 in order,
never installing and never downloading, and writes ONE report to send back:

    smoke-report.json   machine readable
    smoke-report.md     readable summary

It is a diagnostic bundle, not a certificate: a green report means these steps ran
on this machine, not that any real paper's answers, audio cut points or teaching
content were verified.

  py -3 scripts/smoke_report.py                 # Windows
  python3 scripts/smoke_report.py               # macOS / Linux
  python3 scripts/smoke_report.py --no-browser  # skip the click check
"""
import argparse,contextlib,datetime,io,json,os,platform,shutil,subprocess,sys,traceback
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from platform_tools import describe_platform,force_utf8

def tail(text,limit=1500):return (text or '')[-limit:]

def collect(steps,name,fn):
    try:status,detail,output=fn()
    except Exception as error:
        status,detail,output='failed',f'{type(error).__name__}: {error}',tail(traceback.format_exc())
    steps.append({'name':name,'status':status,'detail':detail,'output':output})
    return status

def environment():
    facts=describe_platform()
    return 'passed',f"{platform.platform()} · Python {platform.python_version()}",json.dumps({
        'platform':platform.platform(),'system':platform.system(),'machine':platform.machine(),
        # family 必须落在报告里：判读脚本靠它决定"能不能声明 Windows 已验收"，
        # 只靠 host-probe.json 的话，第 3 步失败时报告就说不清自己在哪个平台上跑的。
        'family':facts['family'],
        'python':platform.python_version(),'executable':sys.executable,
        'stdout_encoding':getattr(sys.stdout,'encoding',''),'cwd':str(Path.cwd())},ensure_ascii=False,indent=2)

def install():
    from check_install import check
    report=check(ROOT)
    status='passed' if report.get('status')=='complete' else 'failed'
    return status,f"{report.get('status')} · files={report.get('checked_files')} · errors={len(report.get('errors',[]))}",json.dumps(report,ensure_ascii=False,indent=2)[:2000]

def host():
    from host_probe import probe
    report=probe(ROOT)
    return report

def build_example(out):
    import build as builder
    source=ROOT/'examples/demo-exam.json';ledger=ROOT/'examples/source-ledger.json'
    buffer=io.StringIO()
    with contextlib.redirect_stdout(buffer):
        builder.build(source,out,ledger,demo=True)
    report=json.loads((out/'build-report.json').read_text(encoding='utf-8'))
    status='passed' if report.get('quality_gate',{}).get('status')=='automated_checks_passed' else 'failed'
    detail=f"structural={report.get('status')} · quality_gate={report.get('quality_gate',{}).get('status')} · answer_audit={report.get('answer_audit',{}).get('status')} · template={report.get('template_verification',{}).get('status')}"
    return status,detail,tail(buffer.getvalue(),600)

def verify(out):
    from verify_output import verify_output
    report=verify_output(out)
    status='passed' if report.get('status')=='passed' else 'failed'
    return status,f"comparison={report.get('comparison')} · html_sha256={str(report.get('html_sha256'))[:16]}…",json.dumps(report,ensure_ascii=False,indent=2)[:1500]

def browser(out,host_report):
    caps=host_report['capabilities'];node=shutil.which('node')
    if not node:return 'skipped','没有找到 node，跳过实际点击验收（交付将标注待验收）',None
    if not caps.get('playwright'):return 'skipped','没有可用的 Playwright 模块，跳过实际点击验收（交付将标注待验收）',None
    if not caps.get('browser'):return 'skipped','没有找到 Chrome/Edge，跳过实际点击验收（交付将标注待验收）',None
    environment=dict(os.environ);environment.setdefault('BROWSER_ENGINE','chromium');environment.setdefault('CHROME_BIN',caps['browser'])
    process=subprocess.run([node,str(ROOT/'scripts/browser_check.cjs'),str(out),'--stress'],
                           capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=300,env=environment)
    evidence=out/'browser-check.json'
    report=json.loads(evidence.read_text(encoding='utf-8')) if evidence.is_file() else {}
    status='passed' if process.returncode==0 and report.get('status')=='passed' else 'failed'
    detail=f"status={report.get('status')} · checks={len(report.get('checks',[]))} · errors={len(report.get('errors',[]))} · engine={report.get('engine')}"
    return status,detail,tail((process.stdout or '')+'\n'+(process.stderr or ''))

def package(out,destination,browser_ok):
    """自检用的打包：**不替人填人工复核清单**，因此按"待验收版"打包并如实标注状态。

    qa-report.md 是必须由人写结论的交付物（1.0.44 起是交付闸门的一部分）；
    自检脚本不能替人写结论，所以这里用 allow_unchecked，并把
    "为什么是待验收版"写进报告——而不是让第 7 步失败或谎报 browser_checked。
    """
    from package_lesson import package as package_lesson
    result=package_lesson(out,destination,allow_unchecked=True)
    status=result.get('status')
    why='示例卷自检不填人工复核清单（qa-report.md 必须由人写），所以状态是待验收版' if status!='browser_checked' else '浏览器验收与人工复核清单都齐备'
    detail=f"status={status} · zip_sha256={str(result.get('zip_sha256'))[:16]}… · {why}"
    if browser_ok:
        detail=f"{detail} · 浏览器验收已通过（步骤 6）"
    return 'passed',detail,json.dumps(result,ensure_ascii=False,indent=2)[:1200]

def marks(steps):return {'passed':sum(1 for s in steps if s['status']=='passed'),'failed':sum(1 for s in steps if s['status']=='failed'),'skipped':sum(1 for s in steps if s['status']=='skipped')}

def render_markdown(report):
    lines=[f"# 实机体检报告 · english-exam-studio {report['version']}",'',
           f"- 时间：{report['generated_at']}",f"- 平台：{report['environment']['platform']}",
           f"- Python：{report['environment']['python']}（{report['environment']['executable']}）",
           f"- 控制台编码：{report['environment']['stdout_encoding']}",
           f"- 结果：通过 {report['summary']['passed']} · 失败 {report['summary']['failed']} · 跳过 {report['summary']['skipped']}",'',
           '## 各步骤','']
    for step in report['steps']:
        lines.append(f"### {step['name']} — {step['status']}")
        lines.append('')
        lines.append(step['detail'] or '')
        if step.get('output'):
            lines+=['','```text',step['output'].strip(),'```']
        lines.append('')
    lines+=['## 说明','','本报告只证明上述步骤在这台机器上实际执行过；不代表真实试卷的答案、听力切点或教学内容已验收。',
            '请把 `smoke-report.json` 与 `smoke-report.md` 一起回传。','']
    return '\n'.join(lines)

def main():
    force_utf8()
    parser=argparse.ArgumentParser(description='一条命令收集实机验收报告')
    parser.add_argument('--workdir',default='smoke-output',help='构建产物目录')
    parser.add_argument('--report-dir',default='.',help='报告写入目录')
    parser.add_argument('--no-browser',action='store_true',help='跳过浏览器点击验收')
    parser.add_argument('--zip',action='store_true',help='把报告打包成 smoke-report-<平台>.zip，便于发回判读')
    args=parser.parse_args()
    work=Path(args.workdir).resolve();reports=Path(args.report_dir).resolve();reports.mkdir(parents=True,exist_ok=True)
    steps=[];host_state={}
    def run(name,fn):return collect(steps,name,fn)=='passed'
    def host_step():
        try:report=host()
        except Exception as error:return 'failed',f'{type(error).__name__}: {error}',tail(traceback.format_exc())
        host_state.update(report);caps=report['capabilities']
        # 落盘宿主探测，随 --zip 一起发回；判读时要能看到安装路径与能力结论
        try:(reports/'host-probe.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        except OSError:pass
        status='passed' if report['installation'].get('status')=='complete' else 'failed'
        paths='、'.join(f"{item['path']}={item['available']}" for item in report.get('install_paths') or [])
        detail=f"delivery={report['delivery_level']} · audio={report['audio_tier']} · python={caps['run_python']} · browser={bool(caps['browser'])}"+(f" · 安装路径 {paths}" if paths else '')
        return status,detail,json.dumps(report,ensure_ascii=False,indent=2)[:3000]
    run('1. 运行环境',environment)
    install_ok=run('2. 安装完整性',install)
    run('3. 宿主能力',host_step)
    if install_ok:build_ok=run('4. 示例构建',lambda:build_example(work))
    else:build_ok=run('4. 示例构建',lambda:('skipped','安装不完整，先补齐安装再构建',None))
    if build_ok:verify_ok=run('5. 模板与产物核验',lambda:verify(work))
    else:verify_ok=run('5. 模板与产物核验',lambda:('skipped','构建未通过，跳过核验',None))
    if args.no_browser:browser_ok=run('6. 浏览器点击验收',lambda:('skipped','按 --no-browser 跳过',None))
    elif verify_ok:browser_ok=run('6. 浏览器点击验收',lambda:browser(work,host_state or {'capabilities':{}}))
    else:browser_ok=run('6. 浏览器点击验收',lambda:('skipped','产物核验未通过，跳过点击验收',None))
    if verify_ok:run('7. 打包交付',lambda:package(work,work.parent/f'{work.name}-delivery.zip',browser_ok))
    else:run('7. 打包交付',lambda:('skipped','产物核验未通过，跳过打包',None))
    version=(ROOT/'VERSION').read_text(encoding='utf-8').strip() if (ROOT/'VERSION').is_file() else '未知'
    environment_block=json.loads(steps[0]['output'] or '{}')
    report={'version':version,'generated_at':datetime.datetime.now().isoformat(timespec='seconds'),
            'family':environment_block.get('family') or str(platform.system()).lower(),
            'environment':environment_block,'summary':marks(steps),'steps':steps}
    (reports/'smoke-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    (reports/'smoke-report.md').write_text(render_markdown(report),encoding='utf-8')
    print(f"报告已写入：{reports/'smoke-report.json'}")
    print(f"           {reports/'smoke-report.md'}")
    if args.zip:
        import zipfile
        family=str(report.get('family') or 'unknown').lower()
        archive=reports/f'smoke-report-{family}.zip'
        with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as bundle:
            bundle.write(reports/'smoke-report.json','smoke-report.json')
            bundle.write(reports/'smoke-report.md','smoke-report.md')
            probe=reports/'host-probe.json'
            if probe.is_file():bundle.write(probe,'host-probe.json')
        print(f"打包完成，把这个文件发回即可判读：{archive}")
        print('（只含报告文本，不含课件媒体与试卷内容）')
    print(json.dumps(report['summary'],ensure_ascii=False))
    print('判读命令：python3 scripts/read_acceptance.py smoke-report.json')
    return 1 if report['summary']['failed'] else 0

if __name__=='__main__':raise SystemExit(main())
