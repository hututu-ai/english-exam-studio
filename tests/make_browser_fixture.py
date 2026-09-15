"""Original text + synthetic tones for UI checks; not an exam/alignment example."""
import base64, copy, hashlib, json, math, struct, sys, wave
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import build
from platform_tools import force_utf8
from sentence_split import split_sentences

def paper_document(base):
    """生成合成素材与 exam.json 数据（不构建），供界面测试与"试卷定结构"测试复用。"""
    base=Path(base).resolve();base.mkdir(parents=True,exist_ok=True)
    d=json.loads((ROOT/'examples/demo-reading.json').read_text(encoding='utf-8'))
    original=d['sections'][0]
    d['features']={'culture_background':True}
    # A real, validated culture entry (quote must be in the passage, sources must state
    # what they support) so the browser check actually opens the card and locates it.
    # 逐句译文 fixture：与原文分句一一对应（含一句未译，用来验证"未译"如实显示）
    first=original['paragraphs'][0]
    sentences=split_sentences(first['text'])
    if len(sentences)>=2:
        # 最后一句故意留空：验证"未译"如实显示、并进入待核项
        first['sentence_translations']=[f'第 {index+1} 句的合成测试译文。' for index in range(len(sentences)-1)]+['']
    original['culture_background']=[{'title':'校园维修角·界面测试条','paragraph_id':'A-p1',
        'quote':'opened a repair corner in the library',
        'explanation':'这一条用于验证文化背景卡片的折叠与定位交互，不主张真实文化事实。',
        'reading_connection':'它交代活动发生在图书馆，与下文的维修记录形成同一场景。',
        'teaching_note':'课堂可借此提醒学生先确认地点信息再看细节。',
        'sources':[{'title':'项目界面测试说明','url':'https://github.com/hututu-ai/english-exam-studio','supports':'本条仅为界面测试，不代表真实背景结论'}]}]
    def section(sid,kind,ids):
        raw=json.dumps(original,ensure_ascii=False).replace('A-p',sid+'-p')
        for old,new in zip(['21','22'],ids):raw=raw.replace('"'+old+'"','"'+new+'"')
        s=json.loads(raw);s.update(id=sid,kind=kind,title=sid+' 控件测试');return s
    for name,duration,freq in [('full.wav',8,.2),('q1.wav',3,.4),('q2.wav',3,.5)]:
        with wave.open(str(base/name),'wb') as f:
            f.setparams((1,2,8000,0,'NONE','not compressed'))
            f.writeframes(b''.join(struct.pack('<h',int(1000*math.sin(i*freq))) for i in range(8000*duration)))
    listening=section('L1','listening',['1','2'])
    listening.update(audio='full.wav',audio_scope='full_paper',audio_alignment={'mode':'unsegmented'},blanks=[{'paragraph_id':'L1-p1','start':0,'end':2,'purpose':'控件测试，非真实听力','question_ids':['1']}])
    for i,q in enumerate(listening['questions']):q.update(audio=f'q{i+1}.wav',audio_context={'start':i,'end':i+3,'selection_reason':'合成音频控件测试'})
    seven=section('S','seven',['36','37'])
    for q in seven['questions']:
        opt=next(iter(q['options']));q['logic_links']=[{'color':'amber','label':'控件测试','explanation':'仅检验高亮交互，不代表真实七选五教学关系','endpoints':[{'paragraph_id':seven['paragraphs'][0]['id'],'quote':seven['paragraphs'][0]['text'][:10]},{'option':opt,'quote':q['options'][opt][:10]}]}]
    grammar=section('G','grammar',['56','57']);grammar.pop('expected_option_count',None)
    for q in grammar['questions']:q.update(options={},answer='named',answer_status='sample',knowledge={'title':'测试','rule':'测试规则','example':'Test.','explanation':'测试说明'})
    writing=section('W','writing',['66','67']);writing.pop('expected_option_count',None)
    writing.update(teacher_model='Test model.',writing_genre='application',writing_steps={'task':'测试任务','outline':['构思'],'language':['Test model.'],'model_analysis':[{'quote':'Test model.','analysis':'示范分析'}]})
    for q in writing['questions']:q.update(options={},answer='Sample writing.')
    # 图片版试卷：本节跨两页，用于验收“出处”弹窗把每一页都渲染出来。
    for name in ('page-a.png','page-b.png'):
        (base/name).write_bytes(base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=='))
    original['origin']={'exam_page':2,'page_images':['page-a.png','page-b.png'],'publication_status':'未确认原始出版来源'}
    d.update(title='六题型界面测试 · 合成录音',sections=[listening,original,seven,section('Cloze','cloze',['41','42']),grammar,writing],full_audio='full.wav')
    d['expected_question_ids']=[q['id'] for s in d['sections'] for q in s['questions']]
    return d

def write_paper(base,d):
    source=Path(base)/'exam.json';source.write_text(json.dumps(d,ensure_ascii=False),encoding='utf-8')
    ledger=Path(base)/'source-ledger.json'
    ledger.write_text(json.dumps({'sources':[{'role':'original_demo','path':'exam.json','sha256':hashlib.sha256(source.read_bytes()).hexdigest()}],'sections':d['sections']},ensure_ascii=False),encoding='utf-8')
    return source,ledger

def make(base, output):
    d=paper_document(base)
    source,ledger=write_paper(base,d)
    build._render(source,Path(output),ledger)
if __name__=='__main__':
    force_utf8();make(sys.argv[1],sys.argv[2])
