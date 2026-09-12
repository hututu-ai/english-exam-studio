#!/usr/bin/env python3
"""Wire audio bundle output into exam data so listening always reaches the lesson.

Shared by build.py and quality_gate.py: the standalone gate must see exactly the same audio
state as the build, otherwise it reports a missing-listening error that the build would fix.
"""
import hashlib,json,os
from pathlib import Path

def sha256(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for block in iter(lambda:f.read(1<<20),b''):h.update(block)
    return h.hexdigest()

def rel(target,base):
    target=str(Path(target).resolve());base=str(Path(base).resolve())
    try:return os.path.relpath(target,base).replace(os.sep,'/')
    except ValueError:return target.replace(os.sep,'/')  # different drives on Windows

def bundle_dir(src_dir,explicit=None):
    if explicit:
        path=Path(explicit).resolve();assert path.is_dir(),f'音频目录不存在：{explicit}';return path
    for name in ['audio-work','audio-out','listening-work','audio']:
        for base in [src_dir,src_dir.parent]:
            candidate=base/name
            if (candidate/'segments.json').is_file():return candidate
    return None

def read_segments(path,kind):
    data=json.loads(Path(path).read_text())
    assert data.get('kind',kind)==kind,f'{path} 不是 {kind} 类型的切段清单'
    return data

def question_bundle(directory):
    if directory is None:return None
    for candidate in [directory/'questions'/'segments.json',directory/'segments-questions.json',directory/'questions.json']:
        if candidate.is_file():return candidate
    return None

def find_transcript(directory,src_dir,full):
    """Pick the transcript whose source_audio_sha256 matches this exact recording."""
    candidates=[]
    if directory:
        candidates+=[directory/'transcript.json',directory.parent/'transcript.json']
        candidates+=sorted(directory.parent.glob('*/transcript.json'))+sorted(directory.glob('*/transcript.json'))
    candidates+=sorted(Path(src_dir).glob('*/transcript.json'))
    target=sha256(full) if full and Path(full).is_file() else None
    for candidate in candidates:
        if not candidate.is_file():continue
        try:data=json.loads(candidate.read_text())
        except (OSError,ValueError):continue
        if target is None or data.get('source_audio_sha256')==target:return candidate
    return None

def wire_audio(d,src_dir,directory):
    """Fill every audio path from the bundle so listening always reaches the HTML."""
    report={'bundle':str(directory) if directory else None,'sections':[],'pending':[],'questions_with_clip':0,'mode':None}
    listening=[s for s in d.get('sections',[]) if s.get('kind')=='listening']
    text_bundle=read_segments(directory/'segments.json','text') if directory and (directory/'segments.json').is_file() else None
    qpath=question_bundle(directory)
    question_bundle_data=read_segments(qpath,'question') if qpath else None
    transcript=None
    if text_bundle:
        full=Path(text_bundle['full_audio'])
        full=full if full.is_absolute() else (directory/full).resolve()
        if full.is_file() and not d.get('full_audio'):d['full_audio']=rel(full,src_dir)
        transcript=find_transcript(directory,src_dir,full)
    segments_by_id={str(s['id']):s for s in (text_bundle or {}).get('segments',[])}
    for section in listening:
        if section.get('audio'):continue
        segment=segments_by_id.get(str(section['id']))
        if segment is None:
            wanted={str(q['id']) for q in section.get('questions',[])}
            segment=next((x for x in segments_by_id.values() if wanted & {str(q) for q in x.get('question_ids',[])}),None)
        if segment is None and len(listening)==1 and len(segments_by_id)==1:
            segment=next(iter(segments_by_id.values()))
        if segment:
            section['audio']=rel(directory/segment['audio'],src_dir)
            section['audio_duration']=round(float(segment.get('duration') or 0),3)
            section['audio_scope']='text'
            alignment={'mode':text_bundle.get('verification_mode','verified'),'boundary':'verified' if segment.get('verified') else 'auto_silence',
                       'full_start':segment['start'],'full_end':segment['end'],
                       'opening_quote':segment.get('opening_quote',''),'closing_quote':segment.get('closing_quote',''),
                       'transcript_text':segment.get('transcript_text','')}
            if transcript:
                alignment['transcript_file']=rel(transcript,src_dir)
                alignment['transcript_sha256']=sha256(transcript)
            section['audio_alignment']={k:v for k,v in alignment.items() if v!=''}
            report['sections'].append({'section':section['id'],'mode':'text_clip','file':segment['audio'],'verification':segment.get('verified')})
            if not segment.get('verified'):
                report['pending'].append(f"{section['id']}：音频边界为静音自动分段，需人工试听首尾")
        elif d.get('full_audio'):
            section['audio']=d['full_audio'];section['audio_scope']='full_paper'
            section['audio_alignment']={'mode':'unsegmented','boundary':'not_split'}
            report['sections'].append({'section':section['id'],'mode':'full_paper','file':d['full_audio'],'verification':False})
            report['pending'].append(f"{section['id']}：未分段，HTML 使用整卷原音，标注为「整卷原音（未分段）」")
    if question_bundle_data:
        qmap={str(s['id']):s for s in question_bundle_data['segments']}
        question_dir=qpath.parent
        for section in listening:
            text_segment=segments_by_id.get(str(section['id']))
            for q in section.get('questions',[]):
                segment=qmap.get('Q'+str(q['id'])) or qmap.get(str(q['id'])) or next((x for x in qmap.values() if str(q['id']) in [str(v) for v in x.get('question_ids',[])]),None)
                if not segment:continue
                q['audio']=rel(question_dir/segment['audio'],src_dir)
                duration=round(float(segment.get('duration') or 0),3);q['audio_duration']=duration
                start=round(max(0.0,segment['start']-(text_segment['start'] if text_segment else segment['start'])),3)
                end=round(start+duration,3) if text_segment else duration
                reason=(q.get('audio_context') or {}).get('selection_reason') or segment.get('evidence') or '按题意保留本题所需完整语境'
                q['audio_context']={'text_id':section['id'],'start':start,'end':end,'selection_reason':reason}
                report['questions_with_clip']+=1
    if text_bundle:report['mode']=text_bundle.get('verification_mode')
    if report['mode']=='auto_silence':report['pending'].append('全套听力边界为静音自动分段：qa-report.md 必须逐段记录首尾试听结果')
    if report['mode']=='unsegmented' or any(x['mode']=='full_paper' for x in report['sections']):
        report['pending'].append('听力未分段：成品可用，但逐题复听与精听挖空依赖人工拖动，交付说明要写清')
    return report
