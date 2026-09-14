#!/usr/bin/env python3
"""Align checked text within real audio windows. Does not invent question cut points."""
import argparse,hashlib,json,os,sys,wave
from pathlib import Path
from exam_document import read_json

def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def whisperx_version():
    """取 WhisperX 版本；没装就给中文说明（importlib.metadata 的英文原文对老师没用）。"""
    import importlib.metadata
    try:return importlib.metadata.version('whisperx')
    except importlib.metadata.PackageNotFoundError:
        raise ValueError('本机没有安装 WhisperX（找不到 whisperx 包元数据）：对齐要装 whisperx==3.8.6 与英语对齐权重；'
                         '如果你已经有同源带时间字幕或转写，改跑 scripts/import_timed_text.py，不必装它') from None

def align(audio,plan,out,cache):
    cache=Path(cache).resolve();cache.mkdir(parents=True,exist_ok=True)
    os.environ['TORCH_HOME']=str(cache/'torch');os.environ['NLTK_DATA']=str(cache/'nltk')
    from audio import probe,sha256,run
    from platform_tools import ffmpeg_bin
    out=Path(out)
    # 先审输入再查环境：计划文件写错却先报"没装 WhisperX"，会让人去装一个用不上的依赖。
    data=read_json(plan)
    duration=probe(audio);items=data.get('segments');previous=0
    if not isinstance(items,list):raise ValueError('计划文件里没有 segments 数组：plan.json 形如 {"segments":[{"id":"L1","start":58.83,"end":74.16,"text":"原件英文原文"}]}，时间窗必须来自你核对过的实际录音，不要照抄示例秒数')
    if not items:raise ValueError('计划文件里的 segments 是空的：请先确认题组所在的实际时间窗，再按 references/whisperx-workflow.md 的格式写进 plan.json 的 segments')
    for index,s in enumerate(items):
        if not isinstance(s,dict):raise ValueError(f'segments 第 {index+1} 项不是对象：{s!r}；每段必须是形如 {{"id":"L1","start":58.83,"end":74.16,"text":"原件英文原文"}} 的对象')
        label=f"片段 {s['id']!r}" if 'id' in s else f'segments 第 {index+1} 项'
        missing=[k for k in ('id','start','end','text') if k not in s]
        if missing:raise ValueError(f"{label} 缺少 {'/'.join(missing)}：每段都必须写 id、start、end、text（对齐需要每段原文）")
        if any(isinstance(s[k],bool) or not isinstance(s[k],(int,float)) for k in ('start','end')):raise ValueError(f"片段 {s.get('id')!r} 的 start/end 必须是秒数（数字），当前是 start={s['start']!r}、end={s['end']!r}；请填实际秒数")
        if not (0<=s['start']<s['end']<=duration+.05 and s['start']>=previous):raise ValueError(f"时间窗无效或与前一段重叠：start={s.get('start')}、end={s.get('end')}，音频共 {duration:.2f} 秒，上一段结束于 {previous}；请按实际音频改正")
        if not isinstance(s['text'],str) or not s['text'].strip():raise ValueError(f"片段 {s.get('id')!r} 缺少 text 或不是文字：对齐需要每段的原文（文字），不能空着")
        if s.get('alignment_text',s['text'])!=s['text'] and not s.get('normalization_note'):raise ValueError(f"片段 {s.get('id')!r} 改了 alignment_text 却没写 normalization_note：原文必须保留，口语形式的改写要说明依据")
        previous=s['end']
    fingerprint={'audio':sha256(audio),'plan':digest(plan),'script':digest(__file__),'whisperx':whisperx_version()}
    if out.exists():
        old=json.loads(out.read_text(encoding='utf-8'))
        if old.get('fingerprint')==fingerprint and old.get('status')=='aligned_review_required':return old
    import torch,numpy as np,whisperx,nltk
    nltk.data.path=[str(cache/'nltk')]
    nltk.data.find('tokenizers/punkt_tab/english/')
    torch.set_num_threads(4)
    model,metadata=whisperx.load_align_model(language_code='en',device='cpu',model_dir=str(cache/'align'))
    wav=cache/(fingerprint['audio']+'.wav')
    if not wav.exists():run([ffmpeg_bin(),'-v','error','-y','-i',audio,'-ar','16000','-ac','1','-c:a','pcm_s16le',wav],timeout=180)
    rows=[];issues=[]
    with wave.open(str(wav),'rb') as w:
        if w.getframerate()!=16000 or w.getsampwidth()!=2 or w.getnchannels()!=1:raise ValueError(f'缓存的 WAV 格式不对（需要 16kHz/16bit/单声道，实际 {w.getframerate()}Hz/{w.getsampwidth()*8}bit/{w.getnchannels()}声道）；删掉缓存后重跑')
        for s in items:
            w.setpos(round(s['start']*16000));raw=w.readframes(round((s['end']-s['start'])*16000))
            samples=np.frombuffer(raw,dtype=np.int16).astype(np.float32)/32768
            text=s.get('alignment_text',s['text'])
            result=whisperx.align([{'start':0,'end':len(samples)/16000,'text':text}],model,metadata,samples,'cpu',return_char_alignments=False)
            words=[]
            for word in result['word_segments']:
                word=dict(word)
                if 'start' not in word or 'end' not in word or not 0<=word['start']<word['end']<=len(samples)/16000+.05:
                    issues.append({'id':s.get('id'),'word':word,'reason':'missing_or_invalid_time'});continue
                word['start']+=s['start'];word['end']+=s['start'];words.append(word)
            if not words:issues.append({'id':s.get('id'),'reason':'no_aligned_words'})
            rows.append({'start':s['start'],'end':s['end'],'text':s['text'],'alignment_text':text,'words':words,'id':s.get('id')})
    report={'fingerprint':fingerprint,'source_audio_sha256':fingerprint['audio'],'duration':duration,'segments':rows,'issues':issues,'status':'alignment_failed' if issues else 'aligned_review_required','alignment_review':'pending','note':'Original text retained. Check numbers, context, boundaries and playback before marking cuts verified.'}
    out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');return report
if __name__=='__main__':
    from platform_tools import force_utf8
    force_utf8();p=argparse.ArgumentParser();p.add_argument('audio');p.add_argument('plan');p.add_argument('--out',required=True);p.add_argument('--cache',required=True);a=p.parse_args()
    try:
        r=align(a.audio,a.plan,a.out,a.cache);print(json.dumps({'status':r['status'],'segments':len(r['segments']),'issues':len(r['issues'])},ensure_ascii=False));sys.exit(2 if r['issues'] else 0)
    except Exception as e:p.exit(1,'ERROR: '+str(e)+'\n')
