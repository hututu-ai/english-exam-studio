"""Compare actual local forced aligners; no inferred timestamps or ASR accuracy claims."""
import argparse,os,json,time,platform,traceback,wave,hashlib,re
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('backend',choices=['qwen','whisperx','stable']);p.add_argument('manifest');p.add_argument('--out',required=True);p.add_argument('--cache',required=True);a=p.parse_args()
cache=Path(a.cache).resolve();cache.mkdir(parents=True,exist_ok=True)
os.environ['HF_HOME']=str(cache/'hf');os.environ['TORCH_HOME']=str(cache/'torch');os.environ['HF_HUB_DOWNLOAD_TIMEOUT']='60';os.environ['HF_HUB_ETAG_TIMEOUT']='30';os.environ['TOKENIZERS_PARALLELISM']='false'
manifest=Path(a.manifest).resolve();out=Path(a.out);out.parent.mkdir(parents=True,exist_ok=True)
report={'backend':a.backend,'platform':platform.platform(),'machine':platform.machine(),'python':platform.python_version(),'device':'cpu','cases':[],'status':'running'}
def save():out.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
save();began=time.monotonic()
try:
 import torch,numpy as np
 torch.set_num_threads(4)
 import importlib.metadata as md
 report['versions']={n:md.version(n) for n in ['torch',{'qwen':'qwen-asr','whisperx':'whisperx','stable':'stable-ts'}[a.backend]]}
 if a.backend=='qwen':
  from qwen_asr import Qwen3ForcedAligner
  model=Qwen3ForcedAligner.from_pretrained('Qwen/Qwen3-ForcedAligner-0.6B',dtype=torch.float32,device_map='cpu')
 elif a.backend=='whisperx':
  import whisperx
  model,metadata=whisperx.load_align_model(language_code='en',device='cpu',model_dir=str(cache/'align'))
 else:
  import stable_whisper
  model=stable_whisper.load_model('base',device='cpu',download_root=str(cache/'whisper'))
 report['load_seconds']=round(time.monotonic()-began,3);save()
 for c in json.loads(manifest.read_text(encoding='utf-8')):
  started=time.monotonic();path=manifest.parent/c['audio'];entry={'id':c['id'],'audio_sha256':hashlib.sha256(path.read_bytes()).hexdigest()};report['cases'].append(entry);save()
  try:
   with wave.open(str(path),'rb') as w:
    sr=w.getframerate();assert w.getsampwidth()==2 and w.getnchannels()==1
    audio=np.frombuffer(w.readframes(w.getnframes()),dtype=np.int16).astype(np.float32)/32768.;duration=len(audio)/sr
   assert sr==16000
   if a.backend=='qwen':
    result=model.align(audio=(audio,sr),text=c['text'],language='English')
    words=[{'word':x.text,'start':float(x.start_time),'end':float(x.end_time)} for x in result[0]]
   elif a.backend=='whisperx':
    result=whisperx.align([{'start':0.,'end':duration,'text':c['text']}],model,metadata,audio,'cpu',return_char_alignments=False)
    words=[{k:v for k,v in x.items() if k in ['word','start','end','score']} for x in result['word_segments']]
   else:
    result=model.align(audio,c['text'],language='en',verbose=False)
    words=[{'word':x.word,'start':float(x.start),'end':float(x.end)} for x in result.all_words()]
   missing=[x['word'] for x in words if 'start' not in x or 'end' not in x];bad=[x for x in words if 'start' in x and (x['start']<0 or x['end']>duration+.1 or x['end']<=x['start'])]
   reversals=sum(1 for x,y in zip(words,words[1:]) if 'start' in x and 'start' in y and y['start']<x['start'])
   entry.update(status='produced',seconds=round(time.monotonic()-started,3),duration=duration,words=words,missing_times=missing,invalid_times=bad,reversed_starts=reversals)
  except Exception as e:entry.update(status='error',error=str(e),traceback=traceback.format_exc())
  save();print(c['id'],entry['status'],entry.get('seconds'),flush=True)
 report['status']='finished'
except Exception as e:report.update(status='error',error=str(e),traceback=traceback.format_exc())
report['elapsed_seconds']=round(time.monotonic()-began,2);save()
print(report['status'],flush=True)
if report['status']=='error' or any(c['status']=='error' for c in report['cases']):raise SystemExit(1)
