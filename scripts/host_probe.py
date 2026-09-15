#!/usr/bin/env python3
"""Probe what THIS host can actually do, so the agent reports limits instead of guessing.

Never installs, never downloads, never mutates the package. It answers the eight
capability questions in references/host-compatibility.md that can be checked
locally, and states the honest delivery level that follows from them.

Usage:
  python3 scripts/host_probe.py [--json]
"""
import argparse,json,os,shutil,subprocess,sys,tempfile
from pathlib import Path
from platform_tools import describe_platform,find_tool,force_utf8

WHISPER_NAMES=('whisper-cli','whisper','main','whisper-cpp')

def node_info():
    node=shutil.which('node')
    if not node:return None,None
    try:
        result=subprocess.run([node,'--version'],capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=10)
        return node,(result.stdout or '').strip() or None
    except (OSError,subprocess.SubprocessError):return node,None

def playwright_available(node):
    if not node:return False
    script="try{require(process.env.PLAYWRIGHT_MODULE||'playwright');}catch(e){process.exit(3)}"
    try:
        result=subprocess.run([node,'-e',script],capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=20)
        return result.returncode==0
    except (OSError,subprocess.SubprocessError):return False

def browser_binary():
    candidates=[]
    if os.environ.get('CHROME_BIN'):candidates.append(os.environ['CHROME_BIN'])
    if sys.platform=='darwin':
        candidates+=['/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
                     '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge']
    elif os.name=='nt':
        for base in (os.environ.get('PROGRAMFILES'),os.environ.get('PROGRAMFILES(X86)'),os.environ.get('LOCALAPPDATA')):
            if base:
                candidates+=[str(Path(base)/'Google/Chrome/Application/chrome.exe'),
                              str(Path(base)/'Microsoft/Edge/Application/msedge.exe')]
    else:
        candidates+=[shutil.which(name) for name in ('google-chrome','chromium','chromium-browser','microsoft-edge')]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():return candidate
    return None

def reachable(url,timeout=4):
    """只看能不能连上（HEAD，仍有界超时）；不下载、不写盘。"""
    import urllib.error,urllib.request
    request=urllib.request.Request(url,method='HEAD',headers={'User-Agent':'english-exam-studio-probe'})
    try:
        with urllib.request.urlopen(request,timeout=timeout):return True
    except urllib.error.HTTPError:return True          # 403/404 也说明网络通
    except Exception:return False

def install_paths(root,network=False):
    """按可靠性排好的四条安装路径，并把"能不能用"如实标出来。

    老师电脑/沙箱常见情形：git clone github.com 被 TLS 拦，但网页抓取可用
    （真实反馈截图里 WorkBuddy 就是这样），所以顺序是
    "老师上传 ZIP → 抓 raw 文件 → 走 jsDelivr CDN → 克隆仓库"。

    jsDelivr 是主流 CDN，在部分网络（含大陆）比 raw 更容易打开；但它是第三方通道：
    逐文件抓取时 `install-manifest.json` 也来自同一通道，哈希一致只能证明传输没损坏，
    不能证明来源未被篡改——要证明来源仍需官方 `SHA256SUMS.txt`（它核对的是官方 ZIP）。
    """
    state='yes' if can_write(root) else 'no'
    github=raw=cdn='not_probed'
    if network:
        github='yes' if reachable('https://github.com') else 'no'
        raw='yes' if reachable('https://raw.githubusercontent.com') else 'no'
        cdn='yes' if reachable('https://cdn.jsdelivr.net/gh/hututu-ai/english-exam-studio@main/SKILL.md') else 'no'
    return [{'path':'teacher_uploaded_zip','available':'unknown',
             'how':'请老师把发布 ZIP（english-exam-studio.zip）作为附件上传，再解压到技能目录；这是最稳的一条，不受宿主网络限制（ZIP 约 2MB，微信/邮件都能转发）。'},
            {'path':'raw_files_fetch','available':raw,
             'how':'用一条命令抓：python3 scripts/fetch_package.py --base https://raw.githubusercontent.com/hututu-ai/english-exam-studio/main --out 临时目录（它按 install-manifest.json 逐个下载并核对 SHA256，比手工抓可靠）。抓完必须跑 scripts/check_install.py 到 complete。'},
            {'path':'cdn_jsdelivr','available':cdn,
             'how':'raw 打不开时改走 CDN：python3 scripts/fetch_package.py --base https://cdn.jsdelivr.net/gh/hututu-ai/english-exam-studio@main --out 临时目录（第三方 CDN，通常更好打开）。第三方通道的哈希一致只证明传输没损坏；来源可信仍需官方 SHA256SUMS.txt 核对官方 ZIP。'},
            {'path':'git_clone','available':github,
             'how':'git clone https://github.com/hututu-ai/english-exam-studio。沙箱里经常被 TLS 握手拦下；失败不要反复重试，改走前三条。'}]

def can_write(root):
    try:
        with tempfile.NamedTemporaryFile('w',encoding='utf-8',dir=root,delete=True) as handle:
            handle.write('probe');handle.flush()
        return True
    except OSError:return False

def probe(root,network=False):
    root=Path(root)
    report=describe_platform()
    try:
        from check_install import check
        installation=check(root)
    except ImportError:
        installation={'status':'incomplete_install','errors':['缺少 scripts/check_install.py，未完整安装']}
    capabilities={}
    capabilities['read_package']=all((root/name).is_file() for name in ('SKILL.md','assets/lesson.html','scripts/build.py'))
    capabilities['write_files']=can_write(root)
    capabilities['run_python']=sys.version_info>=(3,9)
    node,node_version=node_info()
    capabilities['node']=bool(node);capabilities['node_version']=node_version
    capabilities['playwright']=playwright_available(node)
    capabilities['browser']=browser_binary()
    capabilities['ffmpeg']=find_tool('ffmpeg');capabilities['ffprobe']=find_tool('ffprobe')
    capabilities['whisper']=find_tool(*WHISPER_NAMES)
    capabilities['skill_root_writable']=can_write(root.parent if root.parent.is_dir() else root)
    report['capabilities']=capabilities
    report['install_paths']=install_paths(root,network=network)
    report['network_probed']=bool(network)
    report['installation']=installation
    report['browser_check_possible']=bool(capabilities['node'] and capabilities['playwright'] and capabilities['browser'])
    if not capabilities['ffmpeg'] or not capabilities['ffprobe']:audio_tier='no_ffmpeg'
    elif capabilities['whisper']:audio_tier='full_auto'
    else:audio_tier='silence_only'
    from speech_runtime import choose
    speech=choose();report['speech_backend']=speech
    report['legacy_audio_tier']=audio_tier
    if audio_tier!='no_ffmpeg':audio_tier='whisperx_package_ready' if speech['status']=='package_ready' else 'whisperx_needs_setup'
    report['audio_tier']=audio_tier
    report['delivery_level']='browser_check_possible' if report['browser_check_possible'] else 'preview_only_browser_check_pending'
    guidance=[]
    if installation.get('status')!='complete':
        not_probed=not network
        guidance.append('安装不完整：先请老师把发布 ZIP 作为附件上传再解压（最稳）；其次抓 raw.githubusercontent.com 上的文件；'
                        '不要反复尝试 git clone——沙箱常拦 TLS。'+(f'（本机未做网络探测；要预先判断可加 --network，探测只发 HEAD 请求、不下载）' if not_probed else ''))
        guidance.append('无论走哪条路，必须 scripts/check_install.py 到 complete 才能说"已安装"；只能说"完整包下载受限，尚未完整安装"。')
    if not capabilities['read_package']:
        guidance.append('读不到完整技能包：只能处理文字，不生成"同款"课件。')
    if not capabilities['write_files']:
        guidance.append('无法在技能目录写文件：说明构建产物不能落盘，不把 HTML 源码当交付。')
    if not capabilities['run_python']:
        guidance.append('缺少 Python 3.9+：构建、审计、打包都不可用，指明被挡阶段。')
    if report['browser_check_possible']:
        guidance.append('可用浏览器验收：node scripts/browser_check.cjs OUTPUT --stress，报告绑定 HTML 指纹。')
    else:
        guidance.append('无法自动浏览器验收：只交付标注「待浏览器验收」的版本（package_lesson.py --allow-unchecked），不得手写 browser-check.json。')
    if audio_tier=='no_ffmpeg':
        guidance.append('无 ffmpeg/ffprobe：不切割或转码，可接入整卷原音并标注「未分段」；阅读等板块不受影响。')
    elif audio_tier=='whisperx_needs_setup':
        guidance.append('WhisperX 尚未准备：有同源时间字幕则复用；否则使用 speech_runtime.py prepare，经授权准备后短音频试跑。')
    guidance.append('功能多选：宿主无真正多选控件时用编号清单，请老师回复多个编号，禁止单选冒充。')
    report['guidance']=guidance
    report['scope']='本机能力探测；不代表真实试卷识别、听力边界或教学质量已验证。'
    return report

def main():
    force_utf8()
    parser=argparse.ArgumentParser(description='探测当前宿主能力并给出诚实的交付级别')
    parser.add_argument('--json',action='store_true')
    parser.add_argument('--root',default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument('--network',action='store_true',help='额外探测 github.com / raw.githubusercontent.com 是否可达（只发 HEAD，不下载）')
    args=parser.parse_args()
    report=probe(args.root,network=args.network)
    if args.json:print(json.dumps(report,ensure_ascii=False,indent=2))
    else:
        print(f"平台 {report['family']} · 交付级别 {report['delivery_level']} · 听力档位 {report['audio_tier']}")
        for note in report['guidance']:print('· '+note)
        print('安装路径（按可靠性排序）：')
        for item in report['install_paths']:print(f"  [{item['available']}] {item['path']} —— {item['how']}")
    return 0

if __name__=='__main__':raise SystemExit(main())
