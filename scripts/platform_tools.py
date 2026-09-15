#!/usr/bin/env python3
"""Cross-platform lookups shared by every helper script (Windows / macOS / Linux).

Windows notes that actually bite:
  * whisper.cpp ships as main.exe, whisper-cli.exe or whisper.exe depending on the build
  * a legacy console is cp936/cp1252, so printing Chinese raises UnicodeEncodeError
  * ffmpeg is usually installed by winget/scoop/choco but not always on PATH
"""
import json,os,re,shutil,sys
from pathlib import Path

IS_WINDOWS=os.name=='nt'
CJK=re.compile(r'[\u4e00-\u9fff]')

def explain_error(error,next_step=''):
    """把异常转成老师能照做的一句中文，别把英文 errno 直接甩给人。

    真发生过：`verify_output.py` 指着不存在的输出目录时报 `[Errno 2] No such file or directory:
    '.../index.html'`，`package_lesson.py` 连 `ERROR:` 前缀都没有——老师与助手都看不出"该先构建"
    还是"路径写错了"。这里统一成"找不到什么 + 最可能的原因 + 下一步"；已经是中文的说明原样保留。
    """
    hint=f'（{next_step}）' if next_step else ''
    path=getattr(error,'filename',None) or getattr(error,'filename2',None)
    if isinstance(error,FileNotFoundError):
        return f'找不到文件或目录：{path if path else error}；请确认路径、文件名大小写与相对位置，并确认上一步是否真的生成过它'+hint
    if isinstance(error,PermissionError):
        return f'没有权限读写：{path if path else error}；请换一个有写权限的目录（Windows 上避开系统盘受保护目录），或先关闭占用该文件的程序'+hint
    if isinstance(error,IsADirectoryError):
        return f'这里需要文件但给的是目录：{path if path else error}；请指到具体文件（例如 …/exam.json，而不是它所在的文件夹）'+hint
    if isinstance(error,NotADirectoryError):
        return f'路径中间有一段不是目录：{path if path else error}；请检查路径拼写'+hint
    text=str(error).strip() or type(error).__name__
    if CJK.search(text):return text+hint          # 已经是中文说明，原样保留
    return f'处理时出错（{type(error).__name__}）：{text}'+hint

def force_utf8():
    """Make stdout/stderr UTF-8 so Chinese output never crashes a Windows console."""
    for stream in ('stdout','stderr'):
        handle=getattr(sys,stream,None)
        if handle is None:continue
        try:handle.reconfigure(encoding='utf-8',errors='replace')
        except (AttributeError,ValueError):pass

def runtime_root():
    if IS_WINDOWS:
        local_app_data=os.environ.get('LOCALAPPDATA')
        return (Path(local_app_data) if local_app_data else Path.home()/'AppData/Local')/'english-exam-studio'
    return Path.home()/'.cache/english-exam-studio'

def find_tool(*names):
    for name in names:
        key={'ffmpeg':'FFMPEG_BIN','ffprobe':'FFPROBE_BIN'}.get(name)
        if name in WHISPER_NAMES:
            configured=os.environ.get('WHISPER_BIN')
            if configured and Path(configured).is_file():return str(Path(configured).resolve())
            try:
                record=json.loads((runtime_root()/'runtime.json').read_text(encoding='utf-8'));candidate=Path(record.get('whisper_bin',''))
                if candidate.is_file():return str(candidate.resolve())
            except (OSError,ValueError,TypeError):pass
        if key and os.environ.get(key):
            configured=Path(os.environ[key]).expanduser()
            if configured.is_file():return str(configured.resolve())
        if key:
            directories=[os.environ.get('ENGLISH_EXAM_TOOLS','')]
            if IS_WINDOWS and os.environ.get('LOCALAPPDATA'):
                directories.append(str(Path(os.environ['LOCALAPPDATA'])/'english-exam-studio/tools/bin'))
            for directory in filter(None,directories):
                candidate=Path(directory)/(name+('.exe' if IS_WINDOWS else ''))
                if candidate.is_file():return str(candidate.resolve())
        found=shutil.which(name)
        if found:return found
    return None

def ffmpeg_bin():
    return find_tool('ffmpeg') or 'ffmpeg'

def ffprobe_bin():
    return find_tool('ffprobe') or 'ffprobe'

WHISPER_NAMES=('whisper-cli','whisper-cli.exe','whisper','whisper.exe','main','main.exe','whisper-cpp','whisper-cpp.exe')

def whisper_bin():
    return find_tool(*WHISPER_NAMES)

def model_dirs():
    home=os.path.expanduser('~')
    extra=os.environ.get('WHISPER_MODEL_DIR')
    dirs=[
        str(runtime_root()/'models'),
        os.environ.get('WHISPER_MODEL_INCLUDE') or '',
        extra or '',
        os.path.join(home,'whisper.cpp','models'),
        os.path.join(home,'models'),
        os.path.join(home,'.cache','whisper.cpp'),
        '/opt/homebrew/share/whisper-cpp/models',
        '/usr/local/share/whisper-cpp/models',
        '/usr/share/whisper.cpp/models',
    ]
    if IS_WINDOWS:
        local=os.environ.get('LOCALAPPDATA','')
        program=os.environ.get('ProgramData','')
        user=os.environ.get('USERPROFILE',home)
        dirs+=[os.path.join(user,'whisper.cpp','models'),
               os.path.join(user,'Downloads','whisper.cpp','models'),
               os.path.join(user,'scoop','apps','whisper-cpp','current','models'),
               os.path.join(local,'whisper.cpp','models') if local else '',
               os.path.join(local,'Programs','whisper.cpp','models') if local else '',
               'C:\\whisper.cpp\\models',
               os.path.join(program,'chocolatey','lib','whisper-cpp','tools','models') if program else '']
    return [d for d in dirs if d]

def install_hints():
    if IS_WINDOWS:
        return {
            'ffmpeg':'winget install Gyan.FFmpeg（或 scoop install ffmpeg / choco install ffmpeg-full），装完重开终端再跑一次',
            'whisper':'下载 whisper.cpp 的 Windows 预编译包（whisper-bin-x64.zip），把解压目录加进 PATH；可执行文件可能叫 main.exe 或 whisper-cli.exe',
            'model':'从 whisper.cpp 仓库的模型页下载 ggml-base.bin 或 ggml-small.bin，放进 %USERPROFILE%\\whisper.cpp\\models，或用 WHISPER_MODEL 指向它',
            'python':'winget install Python.Python.3.12，安装时勾选 Add python.exe to PATH',
            'pdf':'安装 poppler for Windows（含 pdftotext/pdftoppm）或直接用图片/Word 版试卷；扫描卷可用 tesseract 做 OCR',
        }
    return {
        'ffmpeg':'brew install ffmpeg（macOS）/ apt install ffmpeg（Linux）',
        'whisper':'brew install whisper-cpp，或自行编译 whisper.cpp',
        'model':'把 ggml-base.bin / ggml-small.bin 放到 /opt/homebrew/share/whisper-cpp/models，或用 WHISPER_MODEL 指向它',
        'python':'安装 Python 3.9+，系统自带即可',
        'pdf':'pdftotext/pdftoppm（poppler）与 tesseract',
    }

def describe_platform():
    import platform as _platform
    family='windows' if IS_WINDOWS else ('macos' if sys.platform=='darwin' else 'linux')
    return {'family':family,'platform':_platform.platform(),'machine':_platform.machine(),'python':sys.version.split()[0]}
