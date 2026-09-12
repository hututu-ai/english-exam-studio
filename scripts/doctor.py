#!/usr/bin/env python3
"""Preflight the local toolchain in seconds so the agent picks a real path before working.

Runs the same way on Windows, macOS and Linux. Never installs anything, never writes files."""
import argparse,json,os,shutil,subprocess,sys
from pathlib import Path
from platform_tools import describe_platform,find_tool,force_utf8,install_hints,model_dirs

MODEL_FACTORS=[('tiny',0.04),('base',0.08),('small',0.18),('medium',0.5),('large',1.1)]
WHISPER_NAMES=('whisper-cli','whisper','main','whisper-cpp')

def tool(*names):
    return find_tool(*names)

def first_line(cmd):
    try:
        r=subprocess.run(cmd,capture_output=True,text=True,timeout=20)
        return (r.stdout or r.stderr).strip().splitlines()[0] if (r.stdout or r.stderr).strip() else ''
    except (OSError,subprocess.SubprocessError,IndexError):return ''

def full_output(cmd):
    try:
        r=subprocess.run(cmd,capture_output=True,text=True,timeout=20)
        return (r.stdout or '')+(r.stderr or '')
    except (OSError,subprocess.SubprocessError):return ''

def find_models():
    found=[];seen=set()
    candidates=[Path(os.environ['WHISPER_MODEL'])] if os.environ.get('WHISPER_MODEL') else []
    for directory in model_dirs():
        try:
            if Path(directory).is_dir():candidates+=sorted(Path(directory).glob('*.bin'))
        except OSError:continue
    for path in candidates:
        try:
            if not path.is_file() or str(path.resolve()) in seen:continue
            seen.add(str(path.resolve()));found.append({'path':str(path.resolve()),'size_gb':round(path.stat().st_size/1e9,2)})
        except OSError:continue
    return sorted(found,key=lambda x:x['size_gb'])

def factor_for(path):
    name=Path(path).name.lower()
    for tag,factor in MODEL_FACTORS:
        if tag in name:return tag,factor
    return 'unknown',0.35

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--minutes',type=float,default=0,help='已知听力总时长（分钟），用于粗估转写耗时')
    ap.add_argument('--json',action='store_true');a=ap.parse_args()
    force_utf8()
    hints=install_hints()
    report=describe_platform()
    report['console_encoding']=(getattr(sys.stdout,'encoding','') or '')
    report['cpu_count']=os.cpu_count() or 1
    report['python_ok']=sys.version_info>=(3,8)
    ffmpeg=tool('ffmpeg');ffprobe=tool('ffprobe');whisper=tool(*WHISPER_NAMES)
    report['ffmpeg']=ffmpeg;report['ffprobe']=ffprobe;report['whisper_cli']=whisper
    report['ffmpeg_version']=first_line([ffmpeg,'-version'])[:80] if ffmpeg else ''
    encoders=full_output([ffmpeg,'-hide_banner','-encoders']) if ffmpeg else ''
    report['mp3_encoder']=('libmp3lame' in encoders) or (' aac ' in encoders)
    report['mp3_encoder_name']='libmp3lame' if 'libmp3lame' in encoders else ('aac' if ' aac ' in encoders else None)
    pdf_names=['pdftotext','pdftoppm','mutool','tesseract','soffice','magick']+(['qlmanage','sips','textutil'] if report['family']=='macos' else [])
    report['pdf_tools']={name:tool(name) for name in pdf_names}
    models=find_models();report['asr_models']=models
    report['recommended_model']=next((m['path'] for m in models if 'small' in Path(m['path']).name.lower()),None) or (models[-1]['path'] if models else None)
    if whisper and models:
        tag,factor=factor_for(report['recommended_model'])
        report['model_guess']=tag;report['asr_factor_vs_realtime']=factor
        if a.minutes:report['asr_estimate_seconds']=round(a.minutes*60*factor,0)
    levels=[]
    if not ffmpeg or not ffprobe:levels.append('no_ffmpeg')
    elif whisper and report['recommended_model']:levels.append('full_auto')
    elif whisper:levels.append('asr_no_model')
    else:levels.append('no_asr')
    if not report['mp3_encoder'] and ffmpeg:levels.append('mp3_encoder_missing')
    report['capability']=('full_auto' if 'full_auto' in levels else 'no_ffmpeg' if 'no_ffmpeg' in levels else 'silence_only')
    notes=[]
    if report['capability']=='full_auto':
        notes.append(f"可走完整自动分段：ffmpeg/ffprobe 与 {Path(whisper).name} 均在，建议模型 {Path(report['recommended_model']).name}。")
        if a.minutes:notes.append(f"按 {a.minutes:g} 分钟原音粗估转写约 {report['asr_estimate_seconds']/60:.1f} 分钟（同机实测可能相差两倍）。")
        notes.append(f"转写并发建议：--jobs {max(1,min(4,(os.cpu_count() or 2)//2))}，每进程 --threads {max(1,(os.cpu_count() or 2)//2)}。")
    elif report['capability']=='silence_only':
        if whisper and not report['recommended_model']:notes.append('有 whisper 可执行文件但没找到本地模型：'+hints['model'])
        else:notes.append('没找到 whisper.cpp 可执行文件：'+hints['whisper'])
        notes.append('仍可用静音分段（analyze --no-asr + cut --allow-unverified）：听力音频照常嵌入，边界标为待人工核对。禁止因此删掉听力。')
    else:
        notes.append('缺少 ffmpeg/ffprobe：'+hints['ffmpeg'])
        notes.append('在装好之前不要切割或转码：把老师给的原始音频直接写进 exam.json 的 full_audio 与听力 section.audio，构建会原样复制并嵌入，听力仍然能播放，只是没有分段。')
    if 'mp3_encoder_missing' in levels:notes.append('当前 ffmpeg 没有 mp3 编码器：分段用 -c:a copy 或 aac/m4a，不要卡在重新安装 ffmpeg 上。')
    if not any(report['pdf_tools'].get(k) for k in ['pdftotext','pdftoppm','mutool','soffice']):
        notes.append('未检出 PDF/Office 命令行工具（'+hints['pdf']+'）：PDF 走逐页渲染加视觉识别，DOCX 仍可用 scripts/extract.py。')
    if report['family']=='windows':
        notes.append('Windows 提示：装完 ffmpeg/whisper 后重开终端让 PATH 生效；PowerShell 里用 where.exe ffmpeg 确认能定位到。')
    report['notes']=notes
    report['install_hints']=hints
    report['next_step']={'full_auto':'python3 scripts/audio.py analyze AUDIO --out WORK_AUDIO','silence_only':'python3 scripts/audio.py analyze AUDIO --out WORK_AUDIO --no-asr','no_ffmpeg':'在 exam.json 里直接指向原始音频文件，再跑 build.py'}[report['capability']]
    text=json.dumps(report,ensure_ascii=False,indent=2)
    if a.json:print(text)
    else:
        print('\n'.join('· '+n for n in notes));print('---');print(text)
    return 0

if __name__=='__main__':raise SystemExit(main())
