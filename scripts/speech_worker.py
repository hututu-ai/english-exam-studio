#!/usr/bin/env python3
"""Run in the isolated WhisperX interpreter. No diarization or API key required."""
import argparse,json,os
from pathlib import Path

def main():
    from platform_tools import force_utf8
    force_utf8()
    p=argparse.ArgumentParser();p.add_argument('audio',nargs='?');p.add_argument('--out');p.add_argument('--prepare-resources',action='store_true');p.add_argument('--cache',required=True);p.add_argument('--model',default='base.en');a=p.parse_args()
    cache=Path(a.cache).resolve();cache.mkdir(parents=True,exist_ok=True)
    os.environ['HF_HOME']=str(cache/'hf');os.environ['TORCH_HOME']=str(cache/'torch');os.environ['NLTK_DATA']=str(cache/'nltk')
    os.environ['HF_HUB_DOWNLOAD_TIMEOUT']='30';os.environ['HF_HUB_ETAG_TIMEOUT']='15'
    import torch,whisperx
    torch.set_num_threads(4)
    if a.prepare_resources:
        import nltk
        target=cache/'nltk';target.mkdir(parents=True,exist_ok=True)
        if not (target/'tokenizers/punkt_tab/english').is_dir():
            if not nltk.download('punkt_tab',download_dir=str(target),quiet=True,raise_on_error=True):raise ValueError('分句资源下载失败')
        whisperx.load_align_model(language_code='en',device='cpu',model_dir=str(cache/'align'))
        print(json.dumps({'status':'alignment_resources_ready'}));return
    if not a.audio or not a.out:p.error('转写需要 audio 和 --out')
    model=whisperx.load_model(a.model,'cpu',compute_type='int8',language='en',vad_method='silero',download_root=str(cache/'asr'))
    audio=whisperx.load_audio(a.audio);result=model.transcribe(audio,batch_size=4,language='en')
    from audio import sha256
    result.update(source_audio_sha256=sha256(a.audio),backend='whisperx',model=a.model,alignment_review='pending')
    Path(a.out).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
if __name__=='__main__':main()
