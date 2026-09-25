"""Delivery contract: playable full recording is not segmented listening."""
from pathlib import Path
from audio_wiring import sha256
from section_kinds import is_listening

def check(document,plan,base):
    groups=[s for s in document.get('sections',[]) if is_listening(s)]
    if not groups:return {'status':'not_applicable'}
    choice=plan.get('listening_delivery') or {}
    mode=choice.get('mode','questions')
    if mode not in ('questions','groups','full_recording'):raise ValueError('听力交付模式无效')
    if mode!='questions':
        if choice.get('confirmed') is not True or not str(choice.get('teacher_response','')).strip():raise ValueError('降低听力分段要求须记录老师本次明确同意，不能由 Agent 默认降级')
        if plan.get('mode')=='intensive':raise ValueError('精听任务不能降级为整卷录音或仅题组，请完成逐题语境分段')
    if mode=='full_recording':return {'status':'teacher_approved_full_recording','mode':mode,'note':'未分段，不是完整精听'}
    errors=[];group_files=[];n=0
    def resolve(name):return (Path(base)/name).resolve() if name else None
    for s in groups:
        align=s.get('audio_alignment') or {};file=resolve(s.get('audio'))
        if s.get('audio_scope')!='text' or align.get('mode')=='unsegmented' or align.get('boundary')!='verified':errors.append(s['id']+'：题组未分段或边界未核对')
        if not file or not file.is_file():errors.append(s['id']+'：缺少实际题组音频')
        else:group_files.append((s['id'],sha256(file)))
        if mode=='questions':
            for q in s.get('questions',[]):
                clip=resolve(q.get('audio'));context=q.get('audio_context') or {}
                if not clip or not clip.is_file() or not context.get('selection_reason'):errors.append('第 '+str(q['id'])+' 题：缺少逐题语境音频或选段依据')
                else:n+=1
    if len(group_files)>1 and len({h for _,h in group_files})<len(group_files):errors.append('多个题组使用了相同录音内容，不能复制整卷原音冒充分段')
    if errors:raise ValueError('听力分段尚未完成，不能交付为精听成品：\n'+'\n'.join(errors)+'\n请完成 listening_pipeline.py run → 核对候选片段 → finalize，并通过 --audio-bundle 接入题组与逐题切片；缺环境先按授权准备 WhisperX。')
    return {'status':'segmented','mode':mode,'groups':len(groups),'question_clips':n}
