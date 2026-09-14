#!/usr/bin/env python3
"""试卷决定章节结构：kind 是试卷自己的题型名，preset 只决定"怎么呈现、要求哪些栏目"。

1.0.45 之前 build.py 用一个封闭的六种题型集合（listening/reading/seven/cloze/grammar/writing）
校验，模板也用这六个名字写死了导航顺序与标签。结果是：试卷上写着"读后续写""任务型阅读"
"词汇运用"的板块只能硬塞进"写作/阅读/语法填空"，导航还会按我们的固定顺序重排、把试卷
自己的板块名换成我们的名字。

现在：
  * `section.kind`  试卷自己的题型名，自由填写（不再限定六种）；
  * `section.kind_preset`  可选，声明用哪套呈现方式与栏目要求；缺省时先看 kind 是否命中
     常见题型名（含中文），再按这份卷子实际有什么内容推断；
  * `section.group` / `group_title` / `short`  决定导航分组、组名与小标签，缺省才回退到预设名。
其它脚本一律从这里取判断，不要直接比较 kind 字符串。
"""
import re

SECTION_PRESETS=('listening','reading','seven','cloze','grammar','writing')
PRESET_LABELS={'listening':'听力','reading':'阅读','seven':'七选五','cloze':'完形','grammar':'语法填空','writing':'写作'}
# 常见题型名 → 呈现预设。只影响"怎么呈现/要求什么"，不改变试卷自己的名称。
KIND_ALIASES={
    'listening':'listening', 'listen':'listening', '听力':'listening', '听力理解':'listening', '听力测试':'listening',
    '听力部分':'listening', '听说应用':'listening', '听说':'listening', 'reading':'reading', '阅读理解':'reading', '阅读':'reading',
    '任务型阅读':'reading', 'seven':'seven', '七选五':'seven', '阅读填空':'seven', '阅读七选五':'seven', '配对阅读':'seven',
    '信息匹配':'seven', 'cloze':'cloze', '完形':'cloze', '完形填空':'cloze', '完型填空':'cloze', '语法选择':'cloze',
    'grammar':'grammar', '语法填空':'grammar', '语法':'grammar', '单项填空':'grammar', '单项选择':'grammar', '词汇运用':'grammar',
    '单词拼写':'grammar', '短文填空':'grammar', 'writing':'writing', '写作':'writing', '书面表达':'writing', '读后续写':'writing',
    '概要写作':'writing', '应用文写作':'writing', '作文':'writing', '听句子选图':'listening', '听短文':'listening', '听对话':'listening',
    '听录音':'listening', '回答问题':'reading', '阅读回答':'reading', '阅读表达':'reading', '阅读并回答':'reading', '书面表达（':'writing',
    '话题作文':'writing'
}

def _kind(section):
    return str((section or {}).get('kind') or '').strip()

def _declared_preset(section):
    value=str((section or {}).get('kind_preset') or (section or {}).get('preset') or '').strip()
    return value or None

def _alias_in(text):
    """在一段文字（小标题/节标题）里找题型别名；长别名优先，避免"阅读"抢走"阅读理解"。"""
    text=str(text or '')
    if not text:return None
    for alias in sorted(KIND_ALIASES,key=len,reverse=True):
        if alias in text:return KIND_ALIASES[alias]
    return None

# "图A/图B/图片1/单个字母"这类选项文字是**图片的引用**，不是选项内容：学生看不到图就等于没选项。
# 只认"图/图片/图N"这类**图片引用**：单个字母是合法选项内容（例如语法选择的 "A. a B. an C. the"，
# A 的选项文本就是 "a"），把它们当占位会误伤真实题目。
IMAGE_PLACEHOLDER=re.compile(r'^(?:图|图片|圖|圖片)\s*[A-Ha-h0-9一二三四五六七八九十]{0,2}$')

def placeholder_options(question):
    """返回"只是图片占位"的选项字母（已经给了 option_images 的字母不算）。"""
    images=(question or {}).get('option_images') or {}
    hits=[]
    for letter,value in ((question or {}).get('options') or {}).items():
        if letter in images:continue
        text=re.sub(r'[\s（）()。.、，,：:]','',str(value or ''))
        if IMAGE_PLACEHOLDER.fullmatch(text):hits.append(letter)
    return hits

def paragraphs(section):
    """真正有原文的段落（图片版没有 text，不算）。"""
    return [p for p in (section or {}).get('paragraphs') or [] if isinstance(p,dict) and str(p.get('text') or '').strip()]

def questions(section):
    return [q for q in (section or {}).get('questions') or [] if isinstance(q,dict)]

def has_audio(section):
    """本节或本题真的带了音频。"""
    section=section or {}
    return bool(section.get('audio')) or any(q.get('audio') for q in questions(section))

def has_audio_note(section):
    return bool(str((section or {}).get('audio_note') or '').strip())

def has_blanks(section):
    """真的带精听挖空。空数组是"没有"，不是"有"（JS 里 !![] 为真，踩过）。"""
    return len((section or {}).get('blanks') or [])>0

def is_writing(section):
    """写作节：只看 preset。宣告了别的题型就是别的题型，残留的写作字段不改变呈现方式。"""
    return preset(section)=='writing'

def is_grammar(section):
    """语法节：只看 preset（未宣告时 preset() 会按"每题带知识卡"推断为 grammar）。"""
    return preset(section)=='grammar'

def is_objective(section):
    return any(isinstance(q.get('options'),dict) and q['options'] for q in questions(section))

def shape(section):
    """这份卷子在这一节实际给了什么——栏目要求由它决定，而不是由题型名字决定。"""
    pars=paragraphs(section)
    return {'paragraphs':len(pars),'passage':bool(pars),'multi_passage':len(pars)>=2,
            'questions':len(questions(section)),'objective':is_objective(section),
            'audio':has_audio(section),'audio_note':has_audio_note(section),'writing':is_writing(section)}

def preset(section):
    """呈现预设，一条规则定死优先级：

    1. 显式 kind_preset（试卷/助手宣告的呈现方式，最高优先级）
    2. kind 命中预设名或常见题型名（含中文，如 短文填空→grammar）
    2.5 本节的 title/小标题命中别名（如 "B. 书面表达"→writing、"A. 回答问题"→reading）
    3. 按这份卷子实际有什么内容推断（有音频/挖空→听力，有范文或写作步骤→写作，题带知识卡→语法）
    4. custom

    第 2.5 步只在 kind 认不出来时用；第 3 步只在没有宣告也没有别名时兜底：
    已经宣告或已经由题型名认出的呈现方式，不会被残留字段推翻。
    """
    section=section or {}
    declared=_declared_preset(section)
    if declared:return declared
    kind=_kind(section)
    if kind in SECTION_PRESETS:return kind
    if kind in KIND_ALIASES:return KIND_ALIASES[kind]
    # 小标题也决定呈现方式：初中卷的"读写综合"底下常常是 "A. 回答问题" + "B. 书面表达"，
    # 只看 kind 会把两节都当成 custom（写作节就丢掉写作工作区与 required 栏目）。
    title_preset=_alias_in(str(section.get('title') or '')+str(section.get('subtitle') or ''))
    if title_preset:return title_preset
    if has_audio(section) or has_audio_note(section) or has_blanks(section):return 'listening'
    if section.get('writing_steps') or section.get('teacher_model'):return 'writing'
    if any(q.get('knowledge') for q in questions(section)):return 'grammar'
    return 'custom'

def is_listening(section):
    """听力节：只看 preset（未宣告时 preset() 会按音频/挖空推断）。"""
    return preset(section)=='listening'

def group_key(section):
    """导航分组键；同一组的章节折叠成一个菜单。缺省按试卷的题型名分组。"""
    section=section or {}
    return str(section.get('group') or _kind(section) or section.get('id') or '').strip()

def group_title(section):
    """导航里显示的组名：试卷自己写的最优先，其次才是预设中文名。"""
    section=section or {}
    explicit=str(section.get('group_title') or section.get('chapter_title') or '').strip()
    if explicit:return explicit
    kind=_kind(section)
    if kind and kind not in SECTION_PRESETS:return kind
    return PRESET_LABELS.get(preset(section)) or kind or '章节'

def short(section):
    """导航里的小标签；没写就交给模板按题型启发式取（如 Test 2 / A / 应用文）。"""
    return str((section or {}).get('short') or '').strip() or None

def groups(sections):
    """按试卷顺序把章节分组：顺序 = 各组首次出现的顺序，不再按固定题型顺序重排。"""
    ordered=[]
    index={}
    for section in sections or []:
        key=group_key(section)
        if key not in index:
            index[key]=len(ordered)
            ordered.append({'key':key,'title':group_title(section),'sections':[]})
        ordered[index[key]]['sections'].append(section)
    return ordered
