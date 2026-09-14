"""Grounding rules: every teaching claim must be anchored to real source text.

These checks stop fabricated or unanchored content from entering a lesson:
vocabulary 语境义 must quote the sentence that actually contains the word,
structure/function claims must quote the paragraph they describe, sentence
notes must carry their own analysis fields, and listening 精听 blanks must
land on a whole real word in the transcript.

Structural grounding is not semantic review: a quote can be real and still be
misread. Humans still confirm meaning; the build only refuses invented anchors.
"""
import re

from cost import AUTHORED_KEYS,lastkey,walk

ALNUM=re.compile(r'[A-Za-z0-9]')
# "有字"的判据：引用可能是中文，所以只要有任何文字（\w 含中文）就不算纯标点。
WORD=re.compile(r'\w')

# Distinctive markers only: a single character like 略 appears inside real words
# such as 策略, so substring matching must stay conservative to avoid false blocks.
PLACEHOLDERS=('TODO','待补充','待编写','此处省略','Lorem ipsum','占位符','合成控件测试','此卡仅测试')

def paragraphs(section):
    return {p['id']:p.get('text','') for p in section.get('paragraphs',[])}

def validate_vocabulary(section):
    pars=paragraphs(section)
    for i,item in enumerate(section.get('vocabulary',[])):
        where=f'vocabulary[{i}]'
        word=(item.get('word') or '').strip()
        assert word and (item.get('meaning') or '').strip(),f'{where}: 缺少 word 或 meaning'
        assert (item.get('context') or '').strip(),f'{where}: 需要 context 说明该词在本篇语境中的意思，不能只给通用释义'
        quote=(item.get('quote') or '').strip()
        if item.get('paragraph_id'):
            pid=item['paragraph_id']
            assert pid in pars,f'{where}: paragraph_id 不在本节原文段落中'
            assert quote,f'{where}: 需要 quote —— 该词在原文中的真实所在句，用来证明语境义来自本篇'
            assert quote in pars[pid],f'{where}: quote 不是该段落的真实子串'
            assert word.lower() in quote.lower(),f'{where}: quote 中没有出现词形 {word}，无法证明语境义出自本篇'
        else:
            # Documented exception: a derived form that never appears in this passage.
            # It must point at the real source paragraph, and must not invent a quote.
            source=item.get('source_paragraph')
            assert source in pars,f'{where}: 原文没有该词形时，必须用 source_paragraph 指向本节真实来源段'
            assert not quote,f'{where}: 原文没有该词形时不要伪造 quote，用 source_paragraph 指向来源段即可'

def validate_structure(section):
    pars=paragraphs(section)
    for i,item in enumerate(section.get('structure',[])):
        where=f'structure[{i}]'
        ids=item.get('paragraph_ids')
        assert isinstance(ids,list) and ids,f'{where}: 需要至少一个真实 paragraph_ids，不能用空数组充当结构分析'
        assert all(pid in pars for pid in ids),f'{where}: paragraph_ids 含不存在的段落'
        assert (item.get('title') or '').strip(),f'{where}: 缺少 title'
        assert (item.get('analysis') or '').strip(),f'{where}: 缺少 analysis'
        quote=(item.get('quote') or item.get('source_quote') or '').strip()
        assert quote,f'{where}: 需要 quote 引用支撑该结构判断，不能只写概括结论'
        assert any(quote in pars[pid] for pid in ids),f'{where}: quote 不在所引用段落的原文中'

def validate_sentences(section):
    pars=paragraphs(section)
    for i,item in enumerate(section.get('sentences',[])):
        where=f'sentences[{i}]'
        pid=item.get('paragraph_id')
        assert pid in pars,f'{where}: paragraph_id 不在本节原文段落中'
        quote=(item.get('quote') or '').strip()
        assert quote and quote in pars[pid],f'{where}: quote 必须是该段原文的真实子串'
        for key,label in (('backbone','主干'),('chunks','成分'),('logic','逻辑'),('translation','译文')):
            assert (item.get(key) or '').strip(),f'{where}: 缺少 {key}（{label}）'

def validate_teaching_substance(section):
    """Reject placeholder filler and copy-pasted boilerplate across questions.

    A wrong-but-grounded explanation is a teaching judgement a human must fix;
    identical 'analysis' on two different questions, or empty distractor notes,
    is not judgement at all — it is unfilled or duplicated text. Section-scoped,
    so two sections may legitimately share wording.
    """
    sid=section.get('id','?')
    for path,value in walk(section):
        if isinstance(value,str) and lastkey(path) in AUTHORED_KEYS:
            for marker in PLACEHOLDERS:
                assert marker.lower() not in value.lower(),f'{sid}: {path} 含占位或模板标记「{marker}」，不是真实教学内容'
    seen={}
    for question in (section.get('questions') or []):
        if not isinstance(question,dict):continue
        qid=question.get('id','?')
        for field in ('analysis','pitfall','type_note','strategy'):
            value=(question.get(field) or '').strip()
            if not value:continue
            key=(field,value)
            assert key not in seen,f'{sid}/{qid}: {field} 与第 {seen[key]} 题完全相同，像是复制套话；请按本题材料分别编写'
            seen[key]=qid
        steps=tuple(str(step or '').strip() for step in question.get('solve_steps',[]))
        if steps:
            key=('solve_steps',steps)
            assert key not in seen,f'{sid}/{qid}: solve_steps 与第 {seen[key]} 题完全相同，解题步骤必须按本题重写'
            seen[key]=qid
        notes=[]
        for option,explanation in (question.get('distractors') or {}).items():
            text=(explanation or '').strip()
            assert text,f'{sid}/{qid}: 选项 {option} 的辨析为空，等于没有讲解'
            notes.append(text)
        assert len(notes)==len(set(notes)),f'{sid}/{qid}: 不同选项的辨析内容完全相同，必须分别说明各自错在哪'

def span_problem(text,start,end,require_english_word=False):
    """一段下标区间的问题码，没问题返回 None。

    挖空与引用范围（`quote_ref`）共用这一条判据：都不许落在空白、纯标点或单词中间。
    两者的差别只有"里面要不要有英文词"：精听挖空遮的是听力原文里的英文词（`require_english_word=True`），
    引用可能是中文小标题或中文说明，所以只要求"有字"（任何文字都算），否则中文引文会被误判成标点。
    """
    if not (isinstance(start,int) and isinstance(end,int) and 0<=start<end<=len(text)):return 'invalid'
    piece=text[start:end]
    if not piece.strip():return 'blank'
    if not (ALNUM.search(piece) if require_english_word else WORD.search(piece)):return 'punctuation'
    if start!=0 and ALNUM.match(text[start-1]):return 'half_word_start'
    if end!=len(text) and ALNUM.match(text[end]):return 'half_word_end'
    return None

def validate_blank_tokens(section):
    """精听挖空必须落在一个真实、完整的词上，而不是空白、标点或被截断的半词。"""
    pars=paragraphs(section)
    messages={'invalid':'下标无效','blank':'范围是空白，遮住的不是词语',
              'punctuation':'没有遮到真实词语，只遮了标点或空格',
              'half_word_start':'起点不在词首，会把单词截断','half_word_end':'终点不在词尾，会把单词截断'}
    for i,blank in enumerate(section.get('blanks',[])):
        where=f'blanks[{i}]'
        pid=blank.get('paragraph_id')
        assert pid in pars,f'{where}: 未知段落'
        text=pars[pid]
        start,end=blank.get('start'),blank.get('end')
        problem=span_problem(text,start,end,require_english_word=True)
        assert problem is None,f'{where}: 挖空必须遮住一个完整真实的词——{messages[problem]}'
