#!/usr/bin/env python3
"""Import same-recording SRT/VTT/JSON without a Whisper dependency; no ASR claims."""
import argparse, json, re
from pathlib import Path
from audio import sha256, transcript, probe
from platform_tools import force_utf8

def seconds(value):
    parts=value.replace(',','.').split(':')
    if len(parts) not in (2,3):raise ValueError('无效字幕时间: '+value)
    values=[float(x) for x in parts]
    if values[-1]>=60 or values[-2]>=60 or any(x<0 for x in values):raise ValueError('无效字幕时间: '+value)
    return sum(v*60**i for i,v in enumerate(reversed(values)))

def parse(path):
    path=Path(path);raw=path.read_text(encoding='utf-8-sig')
    if path.suffix.lower()=='.json':return transcript(json.loads(raw))
    if path.suffix.lower() not in ('.srt','.vtt'):raise ValueError('支持 SRT / VTT / 带时间 JSON；纯文本不含真实切点')
    rows=[]
    for block in re.split(r'\n\s*\n',raw.replace('\r\n','\n').strip()):
        lines=block.splitlines();idx=next((i for i,l in enumerate(lines) if '-->' in l),None)
        if idx is None:continue
        match=re.fullmatch(r'\s*([\d:.,]+)\s*-->\s*([\d:.,]+)(?:\s+.*)?',lines[idx])
        if not match:raise ValueError('无法解析字幕时间行: '+lines[idx])
        text=re.sub(r'<[^>]*>','',' '.join(lines[idx+1:])).strip()
        if not text:raise ValueError('字幕片段缺少文字')
        rows.append({'start':seconds(match[1]),'end':seconds(match[2]),'text':text})
    if not rows:raise ValueError('字幕没有有效时间段')
    return transcript({'segments':rows})

def convert(audio,subtitles,out,confirmed=False):
    if not confirmed:raise ValueError('先确认字幕确实来自本次录音，使用 --same-recording-confirmed；不能只把别的字幕绑定到本卷')
    audio=Path(audio);subtitles=Path(subtitles);duration=probe(audio);rows=parse(subtitles)
    if any(r['end']>duration+.05 for r in rows):raise ValueError('字幕超出原音时长，可能不是同一录音或需要核对时间偏移')
    result={'source_audio_sha256':sha256(audio),'duration':duration,'segments':rows,
      'import_source':subtitles.name,'import_sha256':sha256(subtitles),'alignment_review':'pending',
      'note':'只检查格式、时长和绑定信息；切片前仍需核对实际首尾及题意。'}
    Path(out).parent.mkdir(parents=True,exist_ok=True);Path(out).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');return result
if __name__=='__main__':
    force_utf8();p=argparse.ArgumentParser();p.add_argument('audio');p.add_argument('subtitles');p.add_argument('--out',required=True);p.add_argument('--same-recording-confirmed',action='store_true');a=p.parse_args()
    try:r=convert(a.audio,a.subtitles,a.out,a.same_recording_confirmed);print(json.dumps({'status':'imported_review_required','segments':len(r['segments']),'out':a.out},ensure_ascii=False))
    except (OSError,ValueError,AssertionError) as e:p.exit(1,'ERROR: '+str(e)+'\n')
