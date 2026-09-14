#!/usr/bin/env python3
"""合成一份"试卷定结构"的素材：题型名、板块顺序、板块名全部来自试卷，不是我们的预设。

按一份**初中卷**来排（老师明确说过初中会出现短文填空这类题型）：
  一、听说应用
  二、语法选择
  三、完形填空
  四、阅读理解（任务型阅读）
  五、配对阅读
  六、短文填空
  七、读写综合
其中"听说应用/语法选择/配对阅读/短文填空/读写综合"这五个名字**都不在**预设六种里，
而预设顺序 listening→reading→seven→cloze→grammar→writing 与卷面顺序完全对不上。
旧模板会按固定题型重排、把名字换成"听力/阅读/完形/语法填空/写作"，甚至给没有听力的卷子加上听力入口；
本夹具用来验收"顺序、名称、分组、呈现方式都跟着试卷走"。

素材与录音都是合成的界面测试数据，不代表真实试卷内容或答案。
"""
import base64,json,sys
from pathlib import Path

# 1x1 PNG：图片选项的合成占位（界面测试素材，不是真实试卷图片）
SQUARE='iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=='
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tests'));sys.path.insert(0,str(ROOT/'scripts'))
import make_browser_fixture
from platform_tools import force_utf8

# 试卷自己的题型名与板块（顺序即试卷顺序，题号必须随试卷顺序递增）
# (素材节 id, 试卷题型名, 呈现预设, 板块名, 导航小标签, 题号, 本卷节 id)
PLAN=[
    ('L1','听说应用','listening','一、听说应用','1',['1','2'],'L1',(1.0,2.0)),
    ('Cloze','语法选择','cloze','二、语法选择','语法选择',['3','4'],'G1',(1.0,10.0)),
    ('A','完形填空','cloze','三、完形填空','完形填空',['5','6'],'C1',(1.0,10.0)),
    ('W','阅读理解','reading','四、阅读理解','任务型阅读',['7','8'],'R1',(2.0,30.0)),
    ('S','配对阅读','seven','五、配对阅读','配对阅读',['9','10'],'M1',(2.0,5.0)),
    ('G','短文填空','grammar','六、短文填空','短文填空',['11','12'],'F1',(1.5,15.0)),
]

def make(base,output):
    base=Path(base).resolve()
    document=make_browser_fixture.paper_document(base)
    by_id={section['id']:section for section in document['sections']}
    sections=[]
    for sid,kind,preset,group,short,ids,new_id,(per,total) in PLAN:
        section=json.loads(json.dumps(by_id[sid],ensure_ascii=False).replace('A-p',sid+'-p'))
        old_ids=[str(q['id']) for q in section['questions']]
        if len(old_ids)==len(ids):
            raw=json.dumps(section,ensure_ascii=False)
            for old_id,fresh_id in zip(old_ids,ids):raw=raw.replace('"'+old_id+'"','"'+fresh_id+'"')  # 别用 new_id：它是本节的 id
            section=json.loads(raw)
        section.update(id=new_id,kind=kind,kind_preset=preset,group=group,group_title=group,short=short,
                       score_per_question=per,score_total=total,
                       title=f'{group} · {short}')
        sections.append(section)
    # 初中听说应用第一节是「听句子选图」：把 L1 的选项换成图片，真正走一遍 option_images
    listening=[s for s in sections if s['id']=='L1'][0]
    for index in range(4):
        letter='ABCD'[index]
        name=f'选项{letter}.png'
        (base/name).write_bytes(base64.b64decode(SQUARE))
    for question in listening['questions']:
        question['options']={letter:'' for letter in 'ABCD'}
        question['option_images']={letter:f'选项{letter}.png' for letter in 'ABCD'}
        question['option_alts']={letter:f'第{question["id"]}题选项{letter}的合成测试图' for letter in 'ABCD'}
    document['sections']=sections
    document['title']='试卷定结构测试 · 合成素材'
    document['subtitle']='题型名与板块顺序来自试卷'
    document['full_score']=120
    document['exam_minutes']=90
    document['expected_question_ids']=[q['id'] for s in sections for q in s['questions']]
    source,ledger=make_browser_fixture.write_paper(base,document)
    import build,contextlib,io
    with contextlib.redirect_stdout(io.StringIO()):  # 构建报告由测试自己断言，不要刷屏
        build.build(source,Path(output),ledger,profile='quick')
    return document

if __name__=='__main__':
    force_utf8();make(sys.argv[1],sys.argv[2])
    print((Path(sys.argv[2])/'build-report.json').read_text(encoding='utf-8'))
