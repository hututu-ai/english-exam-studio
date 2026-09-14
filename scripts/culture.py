"""Structural safeguards for passage-linked background; semantic review remains required."""
import re

def validate_culture(section):
    paragraphs={p['id']:p['text'] for p in section.get('paragraphs',[])}
    for item in section.get('culture_background',[]):
        quote=item.get('quote','')
        assert quote.strip() and quote in paragraphs.get(item.get('paragraph_id'),''),f"文化背景 {item.get('title')!r} 的 quote 必须是段落 {item.get('paragraph_id')!r} 的真实子串：{quote!r}；背景要挂在本篇原文上，不能只讲常识"
        for key in ('title','explanation','reading_connection','teaching_note'):
            assert isinstance(item.get(key),str) and item[key].strip(),f"文化背景 {item.get('title')!r} 缺少 {key}；title/explanation/reading_connection/teaching_note 四栏都要写（explanation=背景事实，reading_connection=与本篇的关系，teaching_note=课堂怎么用）"
        assert item['reading_connection'].strip()!=item['explanation'].strip(),f"文化背景 {item['title']!r} 的 reading_connection 与 explanation 完全相同；前者要说清这段背景怎样解释本篇，不能重复背景本身"
        text=' '.join(item[k] for k in ('title','explanation','reading_connection','teaching_note'))
        assert not any(x in text for x in ('合成控件测试','此卡仅测试','TODO','待补充文化背景','Lorem ipsum')),f"文化背景 {item.get('title')!r} 里仍是占位文字，不是真实背景；请查证后重写"
        sources=item.get('sources',[])
        assert sources and all(isinstance(x,dict) and re.match(r'^https?://',x.get('url','')) and x.get('title') and x.get('supports') for x in sources),f"文化背景 {item.get('title')!r} 缺少可用来源：每条 sources 要有 http(s) 链接、标题与 supports（这条来源支撑哪一句背景），不能凭印象写背景"
