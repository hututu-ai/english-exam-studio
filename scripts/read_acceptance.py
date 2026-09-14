#!/usr/bin/env python3
"""读回真机验收材料：这份报告能证明什么、还不能证明什么。

老师（或维护者）在任意一台机器上跑一次 `scripts/smoke_report.py`，把产物发回来；
这个脚本负责**严格判读**，避免把"跑了几个步骤"当成"已经验收"：

* `skipped` 一律不算通过；`--no-browser` 跑出来的报告**不能**支持"按钮与播放已验证"；
* 平台不是 Windows 时，报告不能支持"Windows 已验收"；
* 报告用的是**示例卷**，因此永远不能支持"真实试卷内容/答案/听力边界已验收"；
* 豆包工作 / WorkBuddy 的端到端链路不在报告范围内，单独列为未验证。

  python3 scripts/read_acceptance.py smoke-report.json [--json]
  python3 scripts/read_acceptance.py 收到的材料目录或.zip
"""
import argparse,json,sys,zipfile
from pathlib import Path
from platform_tools import explain_error,force_utf8

def load(path):
    """支持：smoke-report.json 本身、包含它的目录、或打包回来的 zip。"""
    path=Path(path)
    data={'smoke':None,'host':None,'source':str(path),'files':[]}
    if path.is_file() and path.suffix.lower()=='.json':
        data['smoke']=json.loads(path.read_text(encoding='utf-8'));data['files']=[path.name];return data
    if path.is_file() and path.suffix.lower()=='.zip':
        with zipfile.ZipFile(path) as archive:
            for name in archive.namelist():
                data['files'].append(name)
                if name.endswith('smoke-report.json'):
                    data['smoke']=json.loads(archive.read(name).decode('utf-8'))
                elif name.endswith('host-probe.json'):
                    data['host']=json.loads(archive.read(name).decode('utf-8'))
        return data
    if path.is_dir():
        for candidate in sorted(path.rglob('*')):
            if not candidate.is_file():continue
            data['files'].append(str(candidate.relative_to(path)))
            if candidate.name=='smoke-report.json' and data['smoke'] is None:
                data['smoke']=json.loads(candidate.read_text(encoding='utf-8'))
            elif candidate.name=='host-probe.json' and data['host'] is None:
                data['host']=json.loads(candidate.read_text(encoding='utf-8'))
        return data
    raise ValueError(f'读不到验收材料：{path}（需要 smoke-report.json、包含它的目录，或打包好的 zip）')

def family_of(smoke,host):
    """报告来自哪个平台：顶层 family → host-probe.json → environment.family → environment.system。

    四级都要看：第 3 步（宿主能力）失败时不会落盘 host-probe.json，只看它就会把一台 Windows
    机器的报告读成"不是 Windows"。四级都拿不到时返回 'unknown'，判读要如实说"判断不了"，
    不能把"报告里没写平台"当成"不是 Windows"的证据。
    """
    block=smoke.get('environment') or {}
    for value in [smoke.get('family'),(host or {}).get('family'),block.get('family'),block.get('system')]:
        text=str(value or '').strip().lower()
        if not text:continue
        if text.startswith('win') or text=='nt':return 'windows'
        if text.startswith('mac') or text in ('darwin','osx'):return 'macos'
        if text.startswith('linux'):return 'linux'
        return text
    return 'unknown'

def verdict(data):
    smoke=data.get('smoke')
    if not smoke:raise ValueError('材料里没有 smoke-report.json；请先在该机器上运行 scripts/smoke_report.py')
    steps={step.get('name'):step for step in smoke.get('steps') or []}
    def status(name):return (steps.get(name) or {}).get('status','missing')
    summary=smoke.get('summary') or {}
    family=family_of(smoke,data.get('host'))
    install=status('2. 安装完整性')=='passed'
    built=status('4. 示例构建')=='passed'
    verified=status('5. 模板与产物核验')=='passed'
    browser=status('6. 浏览器点击验收')=='passed'
    packaged=status('7. 打包交付')=='passed'
    claims=[];gaps=[]
    def claim(text,supported,why=''):
        entry={'claim':text,'supported':bool(supported)}
        if why:entry['why']=why
        (claims if supported else gaps).append(entry)
    claim('该机器的安装完整（check_install=complete）',install,
          '' if install else f"第 2 步状态 {status('2. 安装完整性')}")
    claim('该机器能构建并核验成品（模板与产物核验 passed）',built and verified,
          '' if built and verified else f"构建 {status('4. 示例构建')} / 核验 {status('5. 模板与产物核验')}")
    claim('该机器上浏览器实际操作与播放已执行',browser,
          '' if browser else f"第 6 步状态 {status('6. 浏览器点击验收')}——未执行就不能声明按钮/播放已验证")
    pack_detail=str((steps.get('7. 打包交付') or {}).get('detail') or '')
    claim('该机器的打包链路可用（能产出交付 ZIP）',packaged,
          '' if packaged else f"第 7 步状态 {status('7. 打包交付')}")
    if packaged and 'status=browser_checked' not in pack_detail and browser:
        gaps.append({'claim':'该机器可交付 browser_checked 版本','supported':False,
                     'why':'浏览器验收通过了，但自检不填人工复核清单（qa-report.md 必须由人写），所以打包状态是待验收版；真实交付要写好 qa-report.md 再打包'})
    else:
        claim('该机器可交付 browser_checked 版本（打包状态见报告）',packaged and browser and 'status=browser_checked' in pack_detail,
              '' if packaged else f"打包 {status('7. 打包交付')}")
    pipeline=install and built and verified
    if family=='windows':
        # 来自 Windows 还不够：安装/构建/核验没全过，就不算"Windows 验收完成"
        claim('Windows 实机验收已完成（本次报告来自 Windows）',pipeline,
              '' if pipeline else '报告来自 Windows，但安装/构建/核验未全部通过，不能算验收完成')
    elif family=='unknown':
        claim('Windows 实机验收已完成',False,
              '报告里没有平台信息（environment.system 与 host-probe.json 都缺），无法判断是在哪个系统上跑的；请用当前版本的 smoke_report.py 重跑一次')
    else:
        claim('Windows 实机验收已完成',False,f'本次报告来自 {family}，不是 Windows')
    claim('真实试卷内容、答案与听力边界已验收',False,'报告用的是仓库自带示例卷；真实卷必须另做并写进 qa-report')
    claim('豆包工作 / WorkBuddy 端到端链路已验证',False,'报告不覆盖宿主链路，需在该宿主里实机跑一次')
    failed=[step.get('name') for step in smoke.get('steps') or [] if step.get('status')=='failed']
    skipped=[step.get('name') for step in smoke.get('steps') or [] if step.get('status')=='skipped']
    return {'source':data.get('source'),'family':family,'version':smoke.get('version'),
            'summary':summary,'claims':claims,'gaps':gaps,'failed_steps':failed,'skipped_steps':skipped,
            'files':data.get('files') or [],
            'scope':'本判读只根据报告内容推断，不代替报告本身；skipped 与 failed 一律不当作通过。'}

def render(result):
    lines=[f"验收材料：{result['source']}",
           f"平台 {result['family']} · 版本 {result['version']} · 通过 {result['summary'].get('passed',0)} / 失败 {result['summary'].get('failed',0)} / 跳过 {result['summary'].get('skipped',0)}",'']
    lines.append('可以据此声明：')
    lines+= [f"  ✓ {item['claim']}" for item in result['claims']] or ['  （无）']
    lines.append('')
    lines.append('仍不能声明：')
    lines+= [f"  ✗ {item['claim']}（{item.get('why','')}）" for item in result['gaps']] or ['  （无）']
    if result['failed_steps']:lines+=['','失败步骤：']+[f"  ! {name}" for name in result['failed_steps']]
    if result['skipped_steps']:lines+=['','跳过步骤（不算通过）：']+[f"  - {name}" for name in result['skipped_steps']]
    lines+=['',result['scope']]
    return '\n'.join(lines)

def main():
    force_utf8()
    parser=argparse.ArgumentParser(description='判读真机验收材料：能证明什么、还不能证明什么')
    parser.add_argument('path',help='smoke-report.json、包含它的目录，或打包回来的 zip')
    parser.add_argument('--json',action='store_true')
    args=parser.parse_args()
    try:
        result=verdict(load(args.path))
    except (OSError,ValueError,KeyError,json.JSONDecodeError) as error:
        print(f'ERROR: {explain_error(error)}',file=sys.stderr);return 1
    print(json.dumps(result,ensure_ascii=False,indent=2) if args.json else render(result))
    return 0

if __name__=='__main__':raise SystemExit(main())
