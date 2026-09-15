#!/usr/bin/env python3
"""发布验收一条命令：文档一致 → 安装完整 → 整链重放 → 材料包判读 → 闸门用例。

维护者平时是手工按顺序跑这几步；手工顺序最容易漏掉某一步（这一路就漏过：改了文档没跑
check_docs、打了包没在包上跑重放）。这里把它们串成一条命令并写出报告：

  python3 scripts/release_check.py [--json] [--no-browser]

任何一项失败即以非零码退出；跳过（缺工具）如实记录，不计为通过。
"""
import argparse,contextlib,io,json,subprocess,sys,tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from platform_tools import force_utf8

GATE_MODULES=['tests.test_gates_fire','tests.test_delivery_gates_fire','tests.test_check_docs',
              'tests.test_sentence_split_sync','tests.test_first_use_rehearsal',
              'tests.test_task_contract_new','tests.test_teaching_review_new',
              'tests.test_listening_pipeline_new','tests.test_new_workflow_failures']

def item(name,status,detail=''):
    return {'name':name,'status':status,'detail':detail}

def clear_bytecode_caches(root):
    """删除 `__pycache__`，强制按当前源码重新编译。

    起因是 1.0.112 的一次真实踩坑：改一处常量再改回来，**同一秒内、文件大小又没变**，
    CPython 的 pyc 失效判据是 (mtime 秒, 大小) 这一对，于是它认为缓存有效，
    接着跑验收用的还是**改坏那一版**的代码（表现是断言说"应为 8 步、实际 9 步"）。
    验收工具必须验证当前源码，所以跑之前先清掉这些派生文件（它们不随包发布）。
    """
    removed=0
    for cache in sorted(Path(root).rglob('__pycache__')):
        try:
            for stale in cache.glob('*.pyc'):stale.unlink();removed+=1
            cache.rmdir()
        except OSError:continue
    return removed

def run_unittest(modules,timeout=900):
    result=subprocess.run([sys.executable,'-m','unittest',*modules],cwd=str(ROOT),
                          capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=timeout)
    tail=(result.stderr or result.stdout or '').strip().splitlines()[-3:]
    return result.returncode==0,' / '.join(tail)

def check(with_browser=True):
    items=[]
    clear_bytecode_caches(ROOT)   # 先清派生缓存，保证下面验的是当前源码（见该函数说明）
    # 1 文档一致
    import check_docs
    report=check_docs.check()
    items.append(item('文档一致性（命令/参数/版本/链接/测试数量）','passed' if not report['problems'] else 'failed',
                      '；'.join(report['problems'][:3]) or '一致'))
    # 2 安装完整
    from check_install import check as install_check
    install=install_check(ROOT)
    items.append(item('安装完整性','passed' if install['status']=='complete' else 'failed',
                      f"status={install['status']} · files={install.get('checked_files')} · version={install.get('version')}"))
    # 3 整链重放（老师第一次使用路径）
    import rehearse_first_use
    with tempfile.TemporaryDirectory(prefix='英语 skill 发布验收 ') as temp:
        base=Path(temp)
        replay=rehearse_first_use.rehearse(base/'work',base/'reports',skip_browser=not with_browser)
        skipped=[row['name'] for row in replay['steps'] if row['status']=='skipped']
        items.append(item('整链重放（九步，老师第一次使用路径）','passed' if replay['summary']['failed']==0 else 'failed',
                          f"passed={replay['summary']['passed']} failed={replay['summary']['failed']} skipped={replay['summary']['skipped']}"
                          + (f"（跳过：{'、'.join(skipped)}）" if skipped else '')))
    # 4 材料包判读（无浏览器时如实标未执行）
    with tempfile.TemporaryDirectory(prefix='英语 skill 发布验收体检 ') as temp:
        base=Path(temp)
        code,out,err=rehearse_first_use.run(['scripts/smoke_report.py','--no-browser','--zip',
                                             '--workdir',str(base/'work'),'--report-dir',str(base/'reports')])
        archives=sorted((base/'reports').glob('smoke-report-*.zip'))
        if not archives:
            items.append(item('材料包判读','failed',(err or out)[-200:]))
        else:
            import read_acceptance
            verdict=read_acceptance.verdict(read_acceptance.load(archives[0]))
            claims=[entry['claim'] for entry in verdict['claims']]
            items.append(item('材料包判读（能声明什么/不能声明什么）','passed',
                              f"可声明 {len(claims)} 项：{'；'.join(claims[:3])}…；不能声明 {len(verdict['gaps'])} 项"))
    # 5 闸门用例（结构、交付、文档、切句同步、重放）
    ok,detail=run_unittest(GATE_MODULES)
    items.append(item('闸门与一致性用例',('passed' if ok else 'failed'),detail))
    summary={status:sum(1 for row in items if row['status']==status) for status in ('passed','failed','skipped')}
    version=(ROOT/'VERSION').read_text(encoding='utf-8').strip()
    report={'version':version,'summary':summary,'items':items,
            'note':'只证明这台机器上这些检查跑得过；不证明真实试卷内容、答案正确性、听力边界或宿主端到端。缺工具的跳过项不算通过。'}
    # 报告写到 dist/ 下：dist 不进发布包，避免包里留一份过期报告
    out_dir=ROOT/'dist'/'release-check';out_dir.mkdir(parents=True,exist_ok=True)
    (out_dir/'release-check.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    lines=[f"# 发布验收报告 · {version}",'',f"通过 {summary['passed']} / 失败 {summary['failed']} / 跳过 {summary['skipped']}",'']
    lines+= [f"- [{row['status']}] {row['name']}：{row['detail']}" for row in items]
    lines+= ['',report['note']]
    (out_dir/'release-check.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    return report

def main():
    force_utf8()
    parser=argparse.ArgumentParser(description='发布验收：文档/安装/整链重放/材料包判读/闸门用例')
    parser.add_argument('--json',action='store_true')
    parser.add_argument('--no-browser',action='store_true')
    args=parser.parse_args()
    report=check(with_browser=not args.no_browser)
    if args.json:print(json.dumps(report,ensure_ascii=False,indent=2))
    else:
        for row in report['items']:print(f"[{row['status']}] {row['name']}：{row['detail']}")
        print(json.dumps(report['summary'],ensure_ascii=False))
        print('报告：dist/release-check/release-check.json / .md')
    return 1 if report['summary']['failed'] else 0

if __name__=='__main__':raise SystemExit(main())
