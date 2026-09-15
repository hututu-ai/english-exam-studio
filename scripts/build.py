#!/usr/bin/env python3
"""Validate canonical exam data and build a relocatable, offline lesson.

Audio is wired automatically from an audio bundle (audio.py output) so no one has to keep the
file names in sync by hand: --audio-bundle DIR, or auto-detected audio-work / audio-out.
"""
import argparse,base64,copy,json,re,shutil,subprocess,time,mimetypes,wave
from pathlib import Path
from audio_wiring import bundle_dir, wire_audio
from verify_output import verify_output, verify_template
from quality_gate import audit_exam
from answer_audit import audit as answer_audit
from platform_tools import explain_error, force_utf8, find_tool
from scope import select
from preferences import features, apply_plan
import section_kinds
from culture import validate_culture
from grounding import validate_vocabulary,validate_structure,validate_sentences,validate_blank_tokens,validate_teaching_substance
from sentence_split import split_sentences
import re as _re
SECTION_PRESETS=section_kinds.SECTION_PRESETS
# 校验报错里把字段名翻成老师看得懂的栏目名，避免只说 key 不说"这是什么"。
CONTENT_LABELS={'blanks':'精听挖空','writing_steps':'写作讲解步骤','teacher_model':'范文','quick_words':'生词速查',
    'vocabulary':'重点词汇','sentences':'句子精讲','structure':'篇章结构','writing_bank':'写作积累'}
WRITING_LABELS={'task':'写作任务','outline':'提纲','language':'语言支架','model_analysis':'范文分析'}

def validate_section(s,ids,warnings,problems,qids):
    """One section, all checks.

    每一组检查单独兜住异常，一次构建就把本节所有问题列全。只报第一个错的话，每改一处都要
    重建一次整卷——那正是"生成特别久、特别费 token"的主要来源之一。
    """
    sid=s.get('id','?')
    def guard(scope,check):
        """跑一组检查；出问题时记下来并返回 False，让后面的检查继续（或按需跳过重复报告）。"""
        before=len(problems)
        try:check()
        except AssertionError as error:problems.append(str(error) or f'{scope}: 校验未通过')
        except (KeyError,TypeError,IndexError,AttributeError,ValueError) as error:
            problems.append(f'{scope}: 数据缺字段或类型不对（{type(error).__name__}: {error}）；请对照 references/schema.md 检查这一段数据')
        return len(problems)==before
    def header():
        assert re.fullmatch(r'[A-Za-z0-9_-]+',s['id']) and s['id'] not in ids,f"章节 ID 只能用字母、数字、下划线或连字符，且不能重复：{s.get('id')!r}（已用 {sorted(ids)}）"
        ids.add(s['id'])
        assert str(s.get('kind') or '').strip() and s.get('title'),f"章节 {sid} 的 kind 必须是试卷上这个题型的名称（自由填写，如 reading、读后续写、任务型阅读），并要有 title；当前 kind={s.get('kind')!r}、title={s.get('title')!r}"
        for field in ('score_per_question','score_total'):
            value=s.get(field)
            assert value is None or (isinstance(value,(int,float)) and not isinstance(value,bool) and value>0),f"章节 {sid} 的 {field} 必须是大于 0 的数字（来自试卷标题，如「每小题1分，共10分」）；当前 {value!r}"
        if s.get('score_per_question') and s.get('score_total'):
            assert s['score_per_question']<=s['score_total'],f"章节 {sid} 的每小题分值 {s['score_per_question']} 大于本大题总分 {s['score_total']}，请核对试卷标题"
        declared=str(s.get('kind_preset') or '').strip()
        assert not declared or declared in SECTION_PRESETS,f"章节 {sid} 的 kind_preset 只能是 {list(SECTION_PRESETS)} 之一（它只决定呈现方式，不改变题型名）；当前 {declared!r}"
        for field in ('group','group_title','short'):
            value=s.get(field)
            assert value is None or (isinstance(value,str) and value.strip()),f"章节 {sid} 的 {field} 若填写必须是非空字符串（导航分组/组名/小标签；不填写就按试卷的题型名）"
    guard(sid,header)
    pars={}
    def paragraph_table():
        for p in s.get('paragraphs',[]):
            assert re.fullmatch(r'[A-Za-z0-9_-]+',p['id']) and p['id'] not in pars,f"章节 {sid} 的段落 ID 只能用字母、数字、下划线或连字符，且本节内不能重复：{p.get('id')!r}"
            assert isinstance(p.get('text'),str),f"章节 {sid} 的段落 {p.get('id')!r} 缺少 text；原文必须逐字给出，不能只留题目"
            pars[p['id']]=p
        assert pars,f"章节 {sid} 没有任何原文段落；整卷讲评必须带真实原文（图片版用 image 字段，正文用 text）"
    guard(sid,paragraph_table)
    def sentence_translations():
        """逐句译文必须与原文分句一一对应：宁可标"第 N 句未译"，也不许错位或抄英文充数。"""
        for paragraph in s.get('paragraphs',[]):
            rows=paragraph.get('sentence_translations')
            if rows is None:continue
            pid=paragraph.get('id')
            assert isinstance(rows,list) and rows,f"章节 {sid} 段落 {pid} 的 sentence_translations 必须是非空数组（每句一条，顺序与原文一致）；不要用空数组占位"
            parts=split_sentences(paragraph.get('text',''))
            assert len(rows)==len(parts),f"章节 {sid} 段落 {pid} 的逐句译文有 {len(rows)} 条，按句切分原文是 {len(parts)} 句；请按句子顺序补齐，未翻译的句子用空字符串占位，不要让译文与句子错位"
            missing=[]
            for index,(source,translation) in enumerate(zip(parts,rows),1):
                text=str(translation or '').strip()
                if not text:missing.append(index);continue
                assert _re.search(r'[\u4e00-\u9fff]',text),f"章节 {sid} 段落 {pid} 第 {index} 句的译文里没有中文：{text[:30]!r}；逐句译文必须是中文翻译，不能把英文原句抄一遍"
                assert text.lower()!=source.strip().lower(),f"章节 {sid} 段落 {pid} 第 {index} 句的译文与原文完全相同（{source[:30]!r}）；这不是翻译"
            if missing:warnings.append(f"章节 {sid} 段落 {pid} 有 {len(missing)} 句未翻译（第 {missing} 句，共 {len(parts)} 句）——交付前补齐或在 qa-report 说明")
    guard(sid,sentence_translations)
    if not pars:return  # 没有原文，后面的引用检查只会产生噪音
    def source_groups():
        if not s.get('source_groups'):return
        grouped=[pid for group in s['source_groups'] for pid in group['paragraph_ids']]
        assert grouped==list(pars),f"章节 {sid} 的 source_groups 必须按原顺序覆盖全部段落；分组结果是 {grouped}，实际段落是 {list(pars)}"
    guard(sid,source_groups)
    def quick_words():
        for w in s.get('quick_words',[]):
            assert w.get('meaning') and w.get('word'),f"章节 {sid} 的生词条缺少 word 或 meaning：{w!r}；释义可以来自内置词库，但不能空着"
            assert w.get('paragraph_id') in pars and w['word'].lower() in pars[w['paragraph_id']]['text'].lower(),f"章节 {sid} 的生词 {w.get('word')!r} 没有出现在段落 {w.get('paragraph_id')!r} 的原文里；请改成本篇真实出现的词形，或放进 vocabulary 并用 source_paragraph 说明来源（原文没有该词形时不要伪造）"
            actual=len(re.findall(r'\b'+re.escape(w['word'])+r'\b',' '.join(p['text'] for p in pars.values()),re.I))
            assert w.get('occurrences')==actual,f"章节 {sid} 的生词 {w.get('word')!r} 在本节原文实际出现 {actual} 次，条目写的是 {w.get('occurrences')}；请按原文改成实际次数"
    guard(sid,quick_words)
    def origin():
        if not s.get('origin'):return
        origin=s['origin']
        pages=origin.get('page_images')
        assert pages is None or (isinstance(pages,list) and pages and all(isinstance(x,str) and x.strip() for x in pages)),f"章节 {sid} 的 origin.page_images 必须是非空路径数组（一节跨多页时按页序排列）：{pages!r}"
        assert isinstance(origin.get('exam_page'),int) and origin['exam_page']>0 and (origin.get('page_image') or pages),f"章节 {sid} 的 origin 需要 page_image 或 page_images，并写明原卷页码 exam_page（大于 0 的整数）；当前 {origin!r}"
        for link in origin.get('links',[]):
            assert re.match(r'^https?://',link.get('url','')) and link.get('relation'),f"章节 {sid} 的来源链接要以 http(s):// 开头，并写明 relation（这条链接与原卷的关系）：{link!r}"
    guard(sid,origin)
    def writing_bank():
        for item in s.get('writing_bank',[]):
            assert item.get('paragraph_id') in pars and item.get('quote') in pars[item['paragraph_id']]['text'],f"章节 {sid} 的 writing_bank 引文不是段落 {item.get('paragraph_id')!r} 的真实子串：{item.get('quote')!r}；用 quote_ref 配 scripts/quotes.py fill 回填，避免逐字抄错"
            missing=[k for k in ['category','why','frame','scene','example','check'] if not item.get(k)]
            assert not missing,f"章节 {sid} 的 writing_bank 缺少 {'、'.join(missing)}；写作迁移要写清分类、选用理由、句式框架、使用场景、示例句与自查点"
    guard(sid,writing_bank)
    def logic_steps():
        for item in s.get('logic_steps',[]):
            assert item.get('paragraph_id') in pars and item.get('quote') in pars[item['paragraph_id']]['text'],f"章节 {sid} 的 logic_steps 引文不在段落 {item.get('paragraph_id')!r} 原文中：{item.get('quote')!r}；逻辑关系必须引用真实句子"
    guard(sid,logic_steps)
    def inquiry():
        for item in s.get('inquiry',[]):
            assert item.get('question') and item.get('answer') and item.get('paragraph_id') in pars,f"章节 {sid} 的 inquiry 需要 question、answer 与真实的 paragraph_id；当前 {item!r}"
    guard(sid,inquiry)
    def transfer_tasks():
        for item in s.get('transfer_tasks',[]):
            assert item.get('paragraph_id') in pars and item.get('source_quote') in pars[item['paragraph_id']]['text'] and item.get('prompt') and item.get('check'),f"章节 {sid} 的 transfer_tasks 需要位于段落 {item.get('paragraph_id')!r} 的真实 source_quote，以及 prompt 与 check；当前 {item!r}"
    guard(sid,transfer_tasks)
    def model_analysis():
        for item in s.get('writing_steps',{}).get('model_analysis',[]):
            assert item.get('quote') and item['quote'] in s.get('teacher_model','') and item.get('analysis'),f"章节 {sid} 的写作分析引文必须逐字出自 teacher_model 范文，并写出 analysis：{item.get('quote')!r}"
    guard(sid,model_analysis)
    guard(sid,lambda:validate_culture(s))
    def blanks():
        ranges={}
        for index,blank in enumerate(s.get('blanks',[]),1):
            assert isinstance(blank,dict),f"章节 {sid} 的第 {index} 个挖空不是对象：{blank!r}；每个挖空要写 paragraph_id/start/end/question_ids/purpose（见 references/schema.md）"
            b=blank
            assert isinstance(b.get('paragraph_id'),str) and b.get('paragraph_id') in pars,f"章节 {sid} 的第 {index} 个挖空指向了不存在的段落 {b.get('paragraph_id')!r}（也可能是漏写了 paragraph_id）；挖空必须落在本节真实段落上，本节段落为 {list(pars)}"
            assert b.get('purpose') and b.get('question_ids') and all(str(qid) in [str(q['id']) for q in s['questions']] for qid in b['question_ids']),f"章节 {sid} 的挖空需要 purpose（这个空练什么）与有效的 question_ids；当前 purpose={b.get('purpose')!r}、question_ids={b.get('question_ids')!r}、本节题号 {[str(q['id']) for q in s['questions']]}"
            assert isinstance(b.get('start'),int) and isinstance(b.get('end'),int) and 0<=b['start']<b['end']<=len(pars[b['paragraph_id']]['text']),f"章节 {sid} 的段落 {b['paragraph_id']} 挖空下标缺失或无效：start={b.get('start')!r}、end={b.get('end')!r}，必须是 0..{len(pars[b['paragraph_id']]['text'])} 之间的整数且 start<end（按段落字符下标，不是词序；改字段名不等于改下标）"
            seen=ranges.setdefault(b['paragraph_id'],[])
            assert not any(b['start']<end and b['end']>start for start,end in seen),f"章节 {sid} 的挖空 {b.get('start')}-{b.get('end')} 与同段已有挖空重叠；同一段里挖空不能重叠，请合并或错开"
            seen.append((b['start'],b['end']))
    blanks_ok=guard(sid,blanks)
    def listening():
        if not section_kinds.is_listening(s):return
        if not (s.get('audio') or s.get('audio_note')):problems.append(f'{sid}: 听力章节必须有音频或明确的缺音频说明（见 SKILL.md 三档降级）')
        if s.get('audio_note') and not s.get('audio'):warnings.append(f"{s['id']} 未提供音频：{s['audio_note']}")
    guard(sid,listening)
    def questions_present():
        assert s.get('questions'),f'{sid}: 章节至少要有一道题，只有原文不构成讲评'
    guard(sid,questions_present)
    for q in (s.get('questions') or []):
        def question(q=q):
            assert q.get('question_type') and q.get('type_note') and len(q.get('solve_steps',[]))>=3 and q.get('pitfall'),f"第 {q.get('id','?')} 题缺少题型讲评四件套：question_type、type_note、至少 3 步 solve_steps、pitfall；当前 solve_steps 有 {len(q.get('solve_steps') or [])} 步"
            if q.get('audio'):
                assert section_kinds.is_listening(s) and q.get('audio_context',{}).get('selection_reason'),f"第 {q.get('id','?')} 题带音频，但本节不像是听力（kind={s.get('kind')!r}，也没有本节音频/挖空），或没写 audio_context.selection_reason（为什么剪这一段）；逐题音频只能出现在听力章节"
            if q.get('knowledge'):assert all(q['knowledge'].get(k) for k in ['title','rule','example','explanation']),f"第 {q.get('id','?')} 题的语法知识卡缺 {'、'.join(k for k in ['title','rule','example','explanation'] if not q['knowledge'].get(k))}；四栏要齐全"
            q['id']=str(q['id']);assert re.fullmatch(r'[A-Za-z0-9_-]+',q['id']),f"题号只能用字母、数字、下划线或连字符：{q['id']!r}";assert q['id'] not in qids,f"题号重复：{q['id']}（同一个题号只能出现一次）";qids.add(q['id'])
            assert q.get('stem') and isinstance(q.get('options',{}),dict),f"第 {q.get('id','?')} 题缺少 stem，或 options 不是对象（选项必须是 {{\"A\":\"...\"}} 这样的键值对）"
            images=q.get('option_images')
            if images is not None:
                assert isinstance(images,dict) and images,f"第 {q.get('id','?')} 题的 option_images 必须是非空对象（{{\"A\":\"图片路径\"}}）；不要用空对象占位"
                unknown=[k for k in images if k not in q['options']]
                assert not unknown,f"第 {q.get('id','?')} 题的 option_images 含没有对应选项的字母 {unknown}；选项图片必须与 options 的字母一一对应"
                blank=[k for k,v in q['options'].items() if not str(v or '').strip() and k not in images]
                assert not blank,f"第 {q.get('id','?')} 题的选项 {blank} 既没有文字也没有图片；图片选项请写 option_images，文字选项请写 options"
                missing_image=[k for k,v in images.items() if not str(v or '').strip()]
                assert not missing_image,f"第 {q.get('id','?')} 题的 option_images 里 {missing_image} 没有图片路径"
            # 「图A/图B/图片1/单个字母」是图片的引用，不是选项内容：整题都这样又没有 option_images 时必须拦下，
            # 否则页面上学生看到的只是"图A/图B"这几个字，等于这道题没给图（SKILL.md 明令禁止这种凑法）。
            placeholders=section_kinds.placeholder_options(q)
            if placeholders and len(placeholders)==len(q.get('options') or {}):
                assert q.get('option_images'),(
                    f"第 {q.get('id','?')} 题的选项 {placeholders} 看起来只是图片占位（如「图A」「图B」「图片1」），"
                    f"既没有真实选项文字，也没有 option_images；听句子选图/图表题请把真实图片写成 "
                    f"option_images（{{\"A\":\"assets/…png\"}}）；确实拿不到图片时，把这道题标成待核并在 qa-report 里写明，"
                    f"不要用「图A」这类文字冒充选项")
            if s.get('expected_option_count'):
                assert len(q['options'])==s['expected_option_count'],f"第 {q['id']} 题选项数不符：本节要求 {s['expected_option_count']} 项，实际 {len(q['options'])} 项（{list(q['options'])}）"
                assert list(q['options'])==[chr(65+i) for i in range(s['expected_option_count'])],f"第 {q['id']} 题选项标号必须是 {[chr(65+i) for i in range(s['expected_option_count'])]}，实际是 {list(q['options'])}"
            status=q.get('answer_status');assert status in {'official','inferred','sample','unresolved'},f"第 {q.get('id','?')} 题缺少有效的 answer_status：必须是 official/inferred/sample/unresolved 之一，当前 {status!r}（official=原件答案、inferred=按原文推断、sample=示例、unresolved=待核）"
            assert q.get('answer_source'),f"第 {q.get('id','?')} 题缺少 answer_source：写明答案出处（原件页码、官方答案行或“按原文推断”的依据），空着无法追溯"
            ans=q.get('answer');answers=ans if isinstance(ans,list) else [ans]
            if status!='unresolved':assert ans is not None and ans!='' and ans!=[],f"第 {q.get('id','?')} 题 answer_status={status} 却没有答案；确实无法确定时改成 unresolved，并在 answer_source 写明原因"
            if q.get('options') and ans is not None:assert all(x in q['options'] for x in answers),f"第 {q.get('id','?')} 题的答案 {answers} 不在选项 {list(q['options'])} 里；请核对答案与选项标号"
            if status=='unresolved':warnings.append(f"第 {q['id']} 题答案未确定（unresolved），已记入待核项")
            assert q.get('analysis'),f"第 {q.get('id','?')} 题缺少 analysis：讲评正文不能空着"
            if q.get('options') and status!='unresolved':
                assert q.get('evidence'),f"第 {q.get('id','?')} 题是客观题，必须给 evidence（原文证据句），否则无法在课上定位依据"
                lack=[k for k in q['options'] if k not in answers and k not in (q.get('distractors') or {})]
                assert not lack,f"第 {q.get('id','?')} 题的干扰项 {lack} 没有辨析说明；每个错误项都要写清错在哪"
            for link in q.get('logic_links',[]):
                assert link.get('color') in ['amber','violet','teal','blue'] and link.get('label') and link.get('explanation'),f"第 {q.get('id','?')} 题的线索需要 color（amber/violet/teal/blue 之一）、label 与 explanation；当前 {link!r}"
                ends=link.get('endpoints',[])
                assert len(ends)>=2 and any('option' in e for e in ends) and any('paragraph_id' in e for e in ends),f"第 {q.get('id','?')} 题的每条线索至少 2 个端点，并且必须同时连接原文与选项；当前端点 {ends!r}"
                for endpoint in ends:
                    assert ('option' in endpoint)!=('paragraph_id' in endpoint),f"第 {q.get('id','?')} 题的端点必须二选一：要么 option，要么 paragraph_id，不能同时有或都缺；当前 {endpoint!r}"
                    text=q.get('options',{}).get(endpoint.get('option'),'') if 'option' in endpoint else pars.get(endpoint.get('paragraph_id'),{}).get('text','')
                    assert endpoint.get('quote') and endpoint['quote'] in text,f"第 {q.get('id','?')} 题的线索引文不是所引原文/选项的真实子串：{endpoint.get('quote')!r}"
            for ev in q.get('evidence',[]):
                assert ev['paragraph_id'] in pars,f"第 {q.get('id','?')} 题的 evidence 指向不存在的段落 {ev.get('paragraph_id')!r}；本节段落为 {list(pars)}"
                assert ev.get('quote') and ev['quote'] in pars[ev['paragraph_id']]['text'],f"第 {q.get('id','?')} 题在段落 {ev.get('paragraph_id')} 的证据引文不是真实子串：{ev.get('quote')!r}；用 quote_ref 配 scripts/quotes.py fill 回填，可避免抄错标点与大小写"
                if 'start' in ev or 'end' in ev:assert s.get('audio') and 0<=ev['start']<ev['end'],f"第 {q.get('id','?')} 题的音频证据区间无效：本节要有 audio 且 0<=start<end；当前 start={ev.get('start')!r}、end={ev.get('end')!r}"
        guard(f"{sid}/{q.get('id','?') if isinstance(q,dict) else '?'}",question)
    def underlines_and_gaps():
        for p in pars.values():
            for u in p.get('underlines',[]):assert u in p['text'],f"章节 {sid} 段落 {p['id']} 的下划线文本不是原文子串：{u!r}"
            for gap in re.findall(r'\{\{(\d+)\}\}',p['text']):
                assert gap in [q['id'] for q in s['questions']],f"章节 {sid} 段落 {p['id']} 里的空位题号 {gap} 在本节题目中不存在；本节题号是 {[q['id'] for q in s['questions']]}"
    guard(sid,underlines_and_gaps)
    # 下面这些校验器各自检查一整类内容，也要分别兜住：一个词条出错不该掩盖结构和挖空的问题。
    validators=[('重点词汇',validate_vocabulary),('篇章结构',validate_structure),('句子精讲',validate_sentences),('教学内容',validate_teaching_substance)]
    if blanks_ok:validators.append(('精听挖空',validate_blank_tokens))  # 挖空已在上面报过时不再重复报同一处
    for label,validator in validators:
        guard(f'{sid}（{label}）',lambda validator=validator:validator(s))

def section_report(d):
    """结构校验：返回 (report, problems)，**不在内部抛错**，便于和功能覆盖合并成一次报全。"""
    if not (d.get('title') and d.get('sections')):raise ValueError('缺少 title 或 sections')
    for field in ('full_score','exam_minutes'):
        value=d.get(field)
        if value is not None and not (isinstance(value,(int,float)) and not isinstance(value,bool) and value>0):
            raise ValueError(f'{field} 必须是大于 0 的数字（来自试卷卷首说明，如「本卷满分120分，考试用时90分钟」）；当前 {value!r}')
    problems=[];warnings=[];ids=set();declared=set()
    for s in d['sections']:
        for q in s.get('questions',[]) or []:
            if isinstance(q,dict) and q.get('id') is not None:declared.add(str(q['id']))
    qids=set();paragraph_ids=set()
    for s in d['sections']:
        for par in s.get('paragraphs',[]):
            pid=par.get('id')
            if pid in paragraph_ids:problems.append(f'段落 ID 跨章节重复：{pid!r} 已在别的章节用过；同一章节内和跨章节都不能重名')
            paragraph_ids.add(pid)
        try:validate_section(s,ids,warnings,problems,qids)
        except (AssertionError,KeyError,TypeError,IndexError,ValueError) as error:
            # validate_section 内部已按组兜住；走到这里说明是没预料到的数据结构问题。
            problems.append(f"{s.get('id','?')}: 校验时出现未预期的数据问题（{type(error).__name__}: {error}）；请对照 references/schema.md 检查这一节")
    if d.get('expected_question_ids'):
        expected={str(x) for x in d['expected_question_ids']}
        if expected!=declared:
            missing=sorted(expected-declared);extra=sorted(declared-expected)
            problems.append(f"sections: 题号覆盖不一致（缺 {missing or '无'}，多 {extra or '无'}）")
    if d.get('expected_question_ids_source')=='machine_draft':
        # 机器草稿的题号清单与解析同源：漏掉的题会同时从 expected 里消失，因此“无漏题”检查不成立。
        problems.append('sections: 题号清单来自机器草稿（expected_question_ids_source=machine_draft），构建的“无漏题”检查不成立——漏掉的题不会被发现。请按原卷（含跨页、跨栏）独立盘点题号，改正 expected_question_ids 后把该字段改为 checked 或删除')
    for s in d['sections']:
        per,total,count=s.get('score_per_question'),s.get('score_total'),len(s.get('questions') or [])
        if per and total and count and abs(per*count-total)>1e-6:
            implied=round(total/per,2)
            warnings.append(f"章节 {s.get('id')}：标题是每小题 {per} 分、共 {total} 分（按此应有 {implied} 题），本节只放了 {count} 题；若这次只做部分小题（如阅读理解只做 A 篇）属正常，否则请核对题号或分值")
    report={'sections':len(ids),'questions':len(declared),'warnings':warnings,'status':'structural_checks_passed','note':'Does not certify source fidelity, answer correctness, alignment or browser behavior.'}
    return report,problems

def validate(d):
    report,problems=section_report(d)
    if problems:
        raise ValueError(format_problems(problems,'（上面每条都已给出实际值；改完直接重跑同一条命令。字段含义见 references/schema.md，引文回填用 scripts/quotes.py fill）'))
    return report

def format_problems(problems,footer=''):
    """统一"一次改完再重跑"的报错格式：结构问题与功能覆盖问题会共用这一份清单。"""
    return (f'共 {len(problems)} 处问题，一次改完再重跑：\n- '+'\n- '.join(str(x) for x in problems)
            +(f'\n{footer}' if footer else ''))

def feature_report(d,profile='full',selection='all',mode='lesson',audio_mode='embedded'):
    """功能覆盖校验：返回 (report, problems)，不在内部抛错，便于与结构校验合并成一次报全。

    profile=full  : 现有要求，精读项（句子精讲、篇章结构、写作积累）齐全
    profile=quick : 先保讲课必需项（逐题解析、答案证据、听力挖空、证据段译文），精读项可后补

    这里**一次列全所有缺项**再抛错：以前用 assert 逐条抛，一节里少了三项就要重建三次
    （实测一个两题的小样连撞三轮）。"一次改完再重跑"是省时间与省额度的关键，不能只落实在结构校验上。
    """
    quick=profile=='quick';checks=[];enrichment=[];chosen=features(d);problems=[]
    def need(condition,message):
        if not condition:problems.append(message)
    for s in d['sections']:
        sid=s['id'];form=section_kinds.shape(s);kind_preset=section_kinds.preset(s)
        # 要求哪些栏目由"这份卷子实际给了什么"和"老师选了什么功能"决定，
        # 不再由我们预设的题型名决定：听力没转写就不要求生词表，写作不要求段落译文。
        required=[]
        if form['audio']:required+=['blanks']
        if kind_preset=='writing':required+=['writing_steps','teacher_model']
        if form['passage']:required+=['quick_words','vocabulary']
        if not quick:
            if form['multi_passage'] and not form['audio']:required+=['sentences']
            if form['multi_passage'] and not form['audio'] and chosen['deep_reading']:required+=['structure']
            if form['passage'] and not form['audio'] and chosen['writing_transfer']:required+=['writing_bank']
        if quick:
            need(form['passage'] or s.get('quick_words') or s.get('vocabulary'),
                 f'{sid}: 快速档也要求生词速查或重点词汇至少一项（本节有原文时按原文挑词）')
            evidence_paragraphs={e.get('paragraph_id') for q in s['questions'] for e in q.get('evidence',[]) if e.get('paragraph_id')}
            missing_translation=[pid for pid in sorted(evidence_paragraphs) if not next((p.get('translation') for p in s['paragraphs'] if p['id']==pid),'')]
            need(not missing_translation,f'{sid}: 快速档也要求证据段落有译文：{missing_translation}')
            enrichment+=[{'section':sid,'missing':key} for key in ['sentences','structure','writing_bank'] if not s.get(key)]
        need(not (chosen['culture_background'] and (form['passage'] or form['audio'])) or s.get('culture_background') or s.get('culture_note'),
             f'{sid}: 请补充文化背景或说明本篇无必要背景')
        for key in required:
            need(s.get(key),f'{sid}: 缺少「{CONTENT_LABELS.get(key,key)}」内容（{key}），补齐后再交付；先出可上课版可用 --profile quick，未选的功能不必生成')
        if form['passage'] and not form['writing'] and not quick:
            need(any(p.get('translation') for p in s['paragraphs']),
                 f'{sid}: 段落缺少译文（translation）；逐题讲评要靠证据段译文，快速档也要求证据段有译文')
        for q in s['questions']:
            need(q.get('strategy'),f'{sid}/{q["id"]}: 第 {q["id"]} 题缺少 strategy（本题的解题方法/迁移），每道题都要写')
            if kind_preset=='seven':need(q.get('logic_links'),f'{sid}/{q["id"]}: 第 {q["id"]} 题声明为七选五（preset=seven），却缺少 logic_links（课堂上要显示的线索），不能只写答案')
            if kind_preset=='grammar':need(q.get('knowledge'),f'{sid}/{q["id"]}: 第 {q["id"]} 题声明为语法填空（preset=grammar），却缺少 knowledge 知识卡（title/rule/example/explanation）')
        if kind_preset=='writing':
            steps=s.get('writing_steps') or {}
            for key in ['task','outline','language','model_analysis']:
                need(steps.get(key),f'{sid}: 写作章节缺少「{WRITING_LABELS.get(key,key)}」（writing_steps.{key}）')
        checks.append({'section':sid,'kind':s['kind'],'kind_preset':kind_preset,'required_content':required,'status':'passed'})
    report={'status':'passed','profile':profile,'sections':checks,'missing_enrichment':enrichment,
            'scope':'Required feature data present; human review still needed for teaching quality and source fidelity.'}
    return report,problems

def validate_features(d,profile='full',selection='all',mode='lesson',audio_mode='embedded'):
    """兼容入口：只要缺项就抛错（与结构校验共用同一套"一次改完再重跑"格式）。"""
    report,problems=feature_report(d,profile,selection,mode,audio_mode)
    if problems:
        raise ValueError(format_problems(problems,'（以上是本次要求的全部缺项，已按节列全；--profile quick 可先出可上课版，未选的功能不必生成）'))
    return report

def prune_features(d):
    d['features']=features(d)
    for section in d['sections']:
        if not d['features']['deep_reading']:
            for key in ['structure','logic_steps','inquiry']:section.pop(key,None)
        if not d['features']['writing_transfer']:
            for key in ['writing_bank','transfer_tasks']:section.pop(key,None)
        if not d['features']['culture_background']:
            for key in ['culture_background','culture_note']:section.pop(key,None)
    if not d['features']['dictionary']:
        # 关闭查词时不把词库塞进课件：4MB 词库会让 HTML 变大、打开变慢，也违背"未选扩展不生成"。
        for key in ('dictionary','legacy_dictionary'):d.pop(key,None)
    return d

def build(src,out,source_ledger=None,audio_bundle=None,answer_key=None,profile=None,selection='all',mode=None,audio_mode='embedded',plan=None,dictionary_scope='lesson',review=None,rebuild_from=None,demo=False):
    """Public entry: a new lesson needs current choices; rebuild explicitly reuses its old plan."""
    from task_contract import validate as check_task,rebuild_plan
    from teaching_review import validate as check_teaching
    src=Path(src).resolve();ledger=source_ledger or src.parent/'source-ledger.json'
    if demo:
        root=Path(__file__).resolve().parents[1]
        from check_install import check
        if src not in [(root/'examples/demo-exam.json').resolve(),(root/'examples/demo-reading.json').resolve()] or Path(ledger).resolve()!=(root/'examples/source-ledger.json').resolve() or check(root)['status']!='complete':
            raise ValueError('演示模式仅允许完整安装包自带的合成示例，不能用于教师试卷')
        return _render(src,out,source_ledger=ledger,plan=plan,profile=profile,selection=selection,mode=mode,audio_mode=audio_mode,dictionary_scope=dictionary_scope)
    if plan and rebuild_from:raise ValueError('新计划与 --rebuild-from 只能选一个；修改范围时请用新计划')
    if not plan and not rebuild_from:raise ValueError('新建课件请先询问老师范围与功能，并用 --plan 提供本次确认；重建旧课件用 --rebuild-from 旧课件目录')
    if rebuild_from:
        plan_data=rebuild_plan(rebuild_from,src,ledger)
        plan=Path(rebuild_from)/'generation-plan.json'
    else:plan_data=json.loads(Path(plan).read_text(encoding='utf-8'))
    contract=check_task(plan_data,ledger)
    if selection!='all' or mode or profile and profile!=plan_data.get('profile','full'):raise ValueError('不要用额外参数覆盖教师已确认的范围、模式或档位，请更新计划')
    document=prune_features(apply_plan(json.loads(src.read_text(encoding='utf-8')),plan_data))
    if not review:raise ValueError('缺少独立内容复核记录：先用 teaching_review.py draft 生成清单，实际复核后用 --review 传入')
    review_data=json.loads(Path(review).read_text(encoding='utf-8'));judgment=check_teaching(document,review_data,src.parent)
    if judgment['errors']:raise ValueError('内容复核未完成：\n'+'\n'.join(judgment['errors']))
    result=_render(src,out,source_ledger=ledger,audio_bundle=audio_bundle,answer_key=answer_key,plan=plan,audio_mode=audio_mode,dictionary_scope=dictionary_scope)
    out=Path(out)
    (out/'generation-plan.json').write_text(json.dumps(plan_data,ensure_ascii=False,indent=2),encoding='utf-8')
    (out/'teaching-review.json').write_text(json.dumps(review_data,ensure_ascii=False,indent=2),encoding='utf-8')
    report=json.loads((out/'build-report.json').read_text(encoding='utf-8'));report['task_contract']=contract;report['teaching_review']=judgment
    (out/'build-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return result

def _render(src,out,source_ledger=None,audio_bundle=None,answer_key=None,profile=None,selection='all',mode=None,audio_mode='embedded',plan=None,dictionary_scope='lesson'):
    src=Path(src).resolve();out=Path(out).resolve();original=json.loads(src.read_text(encoding='utf-8'));plan_data=json.loads(Path(plan).read_text(encoding='utf-8')) if plan else None;d=apply_plan(original,plan_data) if plan_data else select(original,selection,mode)
    # --profile wins; otherwise honour the teacher's plan; quick==先出可上课版（省 token 的默认手段）
    profile=profile or (plan_data or {}).get('profile') or 'full'
    if profile not in ('quick','full'):raise ValueError('profile 只能是 quick 或 full')
    d=prune_features(d)
    started=time.perf_counter();timing={};_last=[started]
    def stage(name):
        now=time.perf_counter();timing[name]=round(now-_last[0],3);_last[0]=now
    for section in d.get('sections',[]):
        if section.get('kind')=='writing':section['teacher_model_word_count']=len(re.findall(r"[A-Za-z]+(?:['’-][A-Za-z]+)*",section.get('teacher_model','')))
    directory=bundle_dir(src.parent,audio_bundle) if any(section_kinds.is_listening(s) for s in d['sections']) else None
    audio_report=wire_audio(d,src.parent,directory);stage('prepare_audio')
    # **一次报全**：结构、功能覆盖、证据链、答案审计四关的问题合成一份清单。
    # 逐关抛错的话，一份新卷子最多要跑四轮（改结构→改栏目→改台账→改答案），每轮都是老师等待与助手额度。
    ledger_path=source_ledger or (str(src.parent/'source-ledger.json') if (src.parent/'source-ledger.json').is_file() else None)
    key_path=answer_key
    if key_path is None:
        for candidate in [src.parent/'answers.json',(src.parent/'answers')/'answers.json']:
            if candidate.is_file():key_path=str(candidate);break
    section_data,section_problems=section_report(d)
    notes=[]
    feature_data,feature_problems={},[]
    quality_report=answer_report=None
    quality_problems=[];answer_problems=[]
    if section_problems:
        # 结构畸形时后面的检查可能算不出来：能算的照算（多报一条就少一轮），算不出的如实注明。
        try:feature_data,feature_problems=feature_report(d,profile)
        except (AssertionError,KeyError,TypeError,IndexError,ValueError):
            notes.append('结构问题导致功能覆盖检查无法进行，本次未包含"缺哪些栏目"的清单；先修上面的结构问题')
        try:quality_report=audit_exam(d,src.parent,ledger_path,key_path)
        except Exception:
            notes.append('结构问题导致证据链检查无法进行，本次未包含证据链明细')
        try:answer_report=answer_audit(d,ledger_path,key_path)
        except Exception:
            notes.append('结构问题导致答案审计无法进行，本次未包含答案审计明细')
    else:
        feature_data,feature_problems=feature_report(d,profile)
        quality_report=audit_exam(d,src.parent,ledger_path,key_path)
        answer_report=answer_audit(d,ledger_path,key_path)
    if quality_report is not None and quality_report.get('status')=='blocked':
        details='; '.join(x['location']+': '+x['code'] for x in quality_report['errors'])
        quality_problems=['交付被拦下（证据链不一致）：'+details+'；先跑 scripts/quality_gate.py <exam.json> --source-ledger <source-ledger.json> --report quality-report.json 看逐条明细，改原件或数据后重跑构建']
    if answer_report is not None and answer_report.get('status')=='blocked':
        details='; '.join(x['question']+': '+x['code'] for x in answer_report['blocking'])
        answer_problems=['答案审计未通过: '+details+'；回原件核对后再构建']
    problems=section_problems+feature_problems+quality_problems+answer_problems
    if section_problems and (quality_problems or answer_problems):
        # 结构没修好时，证据链/答案审计可能跟着报连带条目；说清先后，免得助手去改不该改的东西。
        notes.append('结构问题可能连带影响下面的证据链/答案审计条目：先修结构，再按剩余条目核对')
    if problems:
        footer=('（上面每条都已给出实际值；改完直接重跑同一条命令。字段含义见 references/schema.md，引文回填用 scripts/quotes.py fill）'
                +(''.join(f'\n（{note}）' for note in notes)))
        raise ValueError(format_problems(problems,footer))
    report=section_data;report['generation_scope']=d['generation_scope'];report['feature_coverage']=feature_data;report['profile']=profile;stage('validate')
    report['quality_gate']=quality_report;stage('quality_gate')
    report['answer_audit']=answer_report;stage('answer_audit')
    report['audio']=audio_report
    report['pending_items']=sorted(set(audio_report['pending']+list(report.get('warnings') or [])+[x['location']+'：'+x['message'] for x in report['quality_gate'].get('warnings',[])]+[f"第{x['question']}题：{x['message']}" for x in report['answer_audit']['review']]))
    report['delivery_status']='quick_profile_content_and_browser_review_required' if profile=='quick' else 'content_and_browser_review_required'
    if profile=='quick' and report['feature_coverage']['missing_enrichment']:
        report['pending_items']=sorted(set(report.get('pending_items',[])+['快速档：部分精读项未生成，详见 missing_enrichment，补齐后跑 --profile full 重新构建']))
    verify_template(Path(__file__).resolve().parents[1]);resources=[]
    assets=Path(__file__).resolve().parents[1]/'assets'
    # 查词默认只内置"本篇出现的词"的离线释义：整本 10,836 条会把 HTML 撑到 4MB 以上，
    # 而课堂上要查的绝大多数是本篇的词。需要任意词离线可查时用 --dictionary-scope full。
    if d['features'].get('dictionary'):
        tokens,blob=lesson_vocabulary(d) if dictionary_scope=='lesson' else (None,None)
        summary={}
        for key,filename in [('dictionary','offline-dictionary.json'),('legacy_dictionary','legacy-dictionary.json')]:
            if key in d or not (assets/filename).exists():continue
            table=json.loads((assets/filename).read_text(encoding='utf-8'))
            if tokens is not None:table=scope_dictionary(table,tokens,blob)
            d[key]=table;summary[key]=len(table)
        report['dictionary']={'scope':dictionary_scope,'entries':summary,
            'note':'lesson 范围只收录本篇文本中出现的词；查不在本篇的词会走在线词典，离线时不可用。需要任意词离线可查请用 --dictionary-scope full。' if dictionary_scope=='lesson' else 'full 范围内置整本离线词库，HTML 体积明显更大。'}
    def source_path(value):
        assert not re.match(r'^[a-zA-Z]+://',value),f'资源只能引用本地文件，不能写网址：{value!r}；需要联网素材请先下载到本地再引用'
        path=(src.parent/value).resolve();assert path.is_file(),f'找不到资源文件：{value!r}（按 {src.parent} 相对路径查找）；请核对文件名大小写与相对位置';return path
    planned=[]
    audio_sources={}
    def media(obj,key,folder,stem):
        if not obj.get(key):return
        source=source_path(obj[key]);name=f'{folder}/{stem}{source.suffix.lower()}'
        if folder=='audio':
            if source in audio_sources:obj[key]=audio_sources[source];return
            audio_sources[source]=name
        planned.append((source,name));obj[key]=name;resources.append(name)
    def media_map(obj,key,folder,stem):
        """复制"选项字母 → 图片"这类字典（听句子选图 / 图表选项），保留字母顺序。"""
        values=obj.get(key) or {}
        if not values:return
        names={}
        for letter,value in values.items():
            source=source_path(value);name=f'{folder}/{stem}-{letter}{source.suffix.lower()}'
            planned.append((source,name));names[letter]=name;resources.append(name)
        obj[key]=names
    def media_list(obj,key,folder,stem):
        """Copy a list of source pages (图片版试卷一节可能跨多页)，并保留顺序。"""
        values=obj.get(key) or []
        if not values:return
        names=[]
        for index,value in enumerate(values,1):
            source=source_path(value);name=f'{folder}/{stem}-{index}{source.suffix.lower()}'
            planned.append((source,name));names.append(name);resources.append(name)
        obj[key]=names
    probe_cache={}
    def duration_of(source,required=True):
        key=str(source.resolve())
        if key in probe_cache:return probe_cache[key]
        # PCM WAV has a standard-library decoder; inspect actual frames, not a guessed duration.
        if source.suffix.lower()=='.wav':
            try:
                with wave.open(key,'rb') as wav:
                    rate=wav.getframerate();frames=wav.getnframes();frame_size=wav.getnchannels()*wav.getsampwidth();remaining=frames
                    while remaining:
                        block=wav.readframes(min(remaining,65536))
                        if not block or len(block)%frame_size:raise ValueError('WAV 数据被截断：'+key)
                        remaining-=len(block)//frame_size
                    if rate<=0 or frames<=0:raise ValueError('WAV 音频为空：'+key)
                    probe_cache[key]=frames/rate;return probe_cache[key]
            except (wave.Error,EOFError):
                pass  # Other WAV codecs still require ffprobe.
        exe=find_tool('ffprobe')
        if not exe:
            if required:raise ValueError('验证分段时长需要 ffprobe；未分段原音可不依赖 ffprobe')
            return 0
        result=subprocess.run([exe,'-v','error','-show_entries','format=duration','-of','default=nw=1:nk=1',key],capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=30,check=True)
        probe_cache[key]=float(result.stdout);return probe_cache[key]
    media(d,'full_audio','audio','full')
    for s in d['sections']:
        media(s,'audio','audio',s['id'])
        if s.get('audio'):
            source=next(x for x,n in planned if n==s['audio'])
            dur=duration_of(source,s.get('audio_scope')!='full_paper');s['audio_duration']=dur
            for q in s['questions']:
                for ev in q.get('evidence',[]):
                    if 'end' in ev:assert ev['end']<=dur+0.05,f"第 {q.get('id','?')} 题的音频证据结束时间 {ev.get('end')} 秒超出本节音频时长 {round(dur,2)} 秒；请按实际音频改小 end"
        for q in s['questions']:
            if q.get('audio'):
                media(q,'audio','audio','Q'+q['id'])
                qsource=next(x for x,n in planned if n==q['audio'])
                q['audio_duration']=duration_of(qsource)
                context=q.get('audio_context',{})
                assert section_kinds.is_listening(s) and 0<=context.get('start',-1)<context.get('end',-1)<=s['audio_duration']+0.1,f"第 {q['id']} 题的 audio_context 无效：逐题音频只能出现在听力章节（本节 kind={s.get('kind')!r}，也没有本节音频），且要满足 0<=start<end<=本节音频时长 {round(s['audio_duration'],2)} 秒；当前 {context!r}"
                assert abs(q['audio_duration']-(context['end']-context['start']))<0.25,f"第 {q['id']} 题音频实际 {round(q['audio_duration'],2)} 秒，与 audio_context 区间 {round(context['end']-context['start'],2)} 秒相差超过 0.25 秒；请重新裁剪这个片段或改正区间"
        if s.get('origin'):
            media(s['origin'],'page_image','sources',s['id']+'-paper')
            media_list(s['origin'],'page_images','sources',s['id']+'-paper')
        for par in s['paragraphs']:media(par,'image','assets',s['id']+'-'+par['id'])
        for q in s.get('questions',[]):media_map(q,'option_images','assets','Q'+str(q['id'])+'-opt')
    for section in d['sections']:
        alignment=section.get('audio_alignment',{})
        if alignment.get('transcript_file'):
            media(alignment,'transcript_file','verification',section['id']+'-transcript')
    # Complete validation before creating output.
    out.mkdir(parents=True,exist_ok=True)
    if (assets/'ECDICT-LICENSE.txt').exists():shutil.copy2(assets/'ECDICT-LICENSE.txt',out/'ECDICT-LICENSE.txt')
    for source,name in planned:
        target=out/name;target.parent.mkdir(parents=True,exist_ok=True)
        if source!=target:shutil.copy2(source,target)
    embedded={}
    for source,name in planned:
        if name.startswith('audio/') and audio_mode=='embedded':
            mime=mimetypes.guess_type(name)[0] or 'audio/mpeg'
            embedded[name]='data:'+mime+';base64,'+base64.b64encode(source.read_bytes()).decode('ascii')
    d['audio_delivery']={'mode':audio_mode,'embedded_count':len(embedded),'external_audio_count':sum(n.startswith('audio/') for _,n in planned)}
    html_data={**d,'_embedded_audio':embedded}
    payload=json.dumps(html_data,ensure_ascii=False).replace('<','\\u003c').replace('\u2028','\\u2028').replace('\u2029','\\u2029')
    template=(Path(__file__).resolve().parents[1]/'assets'/'lesson.html').read_text(encoding='utf-8')
    # 占位符数量与模板指纹已由上面的 verify_template() 校验（1.0.115 移除了这里重复的断言：
    # 它永远走不到，只会成为一条"从未被执行"的死判据；行为由 verify_output.verify_template 覆盖）。
    (out/'index.html').write_text(template.replace('__EXAM_DATA__',payload),encoding='utf-8')
    shutil.copy2(assets/'open-guide.html',out/'打开课件.html')
    (out/'exam.json').write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding='utf-8')
    report['template_verification']=verify_output(out,Path(__file__).resolve().parents[1])
    report['resources']=resources
    report['audio_embedded']=bool(embedded)
    report['audio_delivery']=d['audio_delivery']
    stage('render_and_write')
    report['timing']=timing
    report['elapsed_seconds']=round(time.perf_counter()-started,3)
    try:
        from cost import analyze as analyze_cost
        cost=analyze_cost(d)
        report['authoring_cost']={k:cost[k] for k in ('authored_chars','authored_fields','quote_chars','inline_quotes','estimated_quote_ref_saving')}
        report['authoring_cost']['long_quote_candidates']=len(cost['long_quote_candidates'])
        report['authoring_cost'].update(cost.get('duplicates') or {})
        report['authoring_cost']['review_index']=cost.get('review_index') or {}
        report['authoring_cost']['same_phrase_total']=int(cost.get('same_phrase_total') or 0)
        report['authoring_cost']['same_phrase_hints']=(cost.get('same_phrase_hints') or [])[:5]
        # 脚本判断不了"换一种说法讲同一件事"（实测中文改写字符相似度只有 0.54），
        # 所以只把同类内容并排列出来，请人扫一遍——这条进待核项，不阻断。
        index_total=sum((cost.get('review_index') or {}).values())
        if index_total>=8 or report['authoring_cost']['same_phrase_total']:
            note=(f"去重复核：本卷 {index_total} 处解析/题型说明/易错/方法，脚本判断不了「换一种说法讲同一件事」"
                  f"（连续相同片段提示 {report['authoring_cost']['same_phrase_total']} 组）；"
                  f"请并排扫一遍，清单见 build-report.json 的 authoring_cost.review_index")
            report.setdefault('warnings',[]).append(note)
            report['pending_items']=sorted(set(report.get('pending_items') or [])|{note})
        # 重复内容多到一定程度就给一条不阻断的提示：省 token 是老师明确提过的诉求，
        # 但"字面相似"不等于教学上重复，所以只提醒、不阻断，也不许自动删。
        duplicate_saving=int((cost.get('duplicates') or {}).get('estimated_saving') or 0)
        authored=int(cost.get('authored_chars') or 0)
        if duplicate_saving>=200 and authored and duplicate_saving>=authored*0.1:
            note=f"重复内容约 {duplicate_saving} 字符（占需编写量 {round(duplicate_saving/authored*100)}%）：跑 scripts/cost.py <exam.json> --duplicates 看清单；字面相似不等于教学上重复，删改前自己判断"
            report.setdefault('warnings',[]).append(note)
            report['pending_items']=sorted(set(report.get('pending_items') or [])|{note})
    except Exception:
        report['authoring_cost']=None
    report['browser_playback']='not_tested_by_builder'
    (out/'answer-audit.json').write_text(json.dumps(report['answer_audit'],ensure_ascii=False,indent=2),encoding='utf-8')
    (out/'build-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    remove_stale_outputs(out,assets,resources)
    print(json.dumps(report,ensure_ascii=False))

def scope_dictionary(library,tokens,blob):
    """把整本离线词库裁剪成本篇范围。

    语义就是这一行：`k.lower() in tokens or (len(k)>1 and k.lower() in blob)`。
    但逐条对 10,836 条词库做子串搜索很贵（实测 32 节 0.80s、64 节 1.60s，占构建近三成），
    所以先用一条**必要**条件筛：词条若真是 blob 的子串，它开头 2/3 个字也必然是 blob 的子串。
    只放行可能命中的条目，最终判断仍是原来的 `in blob`——结果与朴素写法逐条一致（有等价性测试守着）。
    """
    grams={size:{blob[index:index+size] for index in range(max(0,len(blob)-size+1))} for size in (2,3)}
    def in_scope(key):
        lowered=key.lower()
        if lowered in tokens:return True
        if len(key)<=1:return False
        size=2 if len(lowered)==2 else 3
        if lowered[:size] not in grams[size]:return False
        return lowered in blob
    return {key:value for key,value in library.items() if in_scope(key)}

def lesson_vocabulary(exam):
    """Every English token visible in the lesson, used to scope the offline dictionary."""
    texts=[]
    def walk(node):
        if isinstance(node,dict):
            for value in node.values():walk(value)
        elif isinstance(node,list):
            for value in node:walk(value)
        elif isinstance(node,str):texts.append(node)
    walk(exam)
    blob=' '.join(texts).lower()
    return {token.lower() for token in re.findall(r"[A-Za-z]+(?:['’-][A-Za-z]+)*",blob)},blob

def remove_stale_outputs(out,assets,resources):
    """Drop media this skill produced on an earlier, wider build but no longer needs.

    Rebuilding a smaller scope into the same folder used to leave the previous
    scope's audio and page images behind, and package_lesson.py zips the whole
    folder — so teachers received clips for sections that were not in the lesson.
    Only files listed by our own previous manifest are removed, so anything the
    teacher placed in the output folder by hand is left untouched.
    """
    produced={'index.html','exam.json','build-report.json','answer-audit.json','打开课件.html',*resources}
    if (assets/'ECDICT-LICENSE.txt').exists():produced.add('ECDICT-LICENSE.txt')
    manifest=out/'.build-manifest.json'
    previous=[]
    if manifest.is_file():
        try:previous=json.loads(manifest.read_text(encoding='utf-8')).get('files',[])
        except (OSError,ValueError,TypeError):previous=[]
    root=out.resolve()
    for name in sorted(set(previous)-produced):
        target=out/str(name)
        try:
            if target.is_file() and root in target.resolve().parents:target.unlink()
        except OSError:continue
    manifest.write_text(json.dumps({'files':sorted(produced)},ensure_ascii=False,indent=2),encoding='utf-8')

if __name__=='__main__':
    force_utf8()
    p=argparse.ArgumentParser();p.add_argument('input');p.add_argument('out')
    p.add_argument('--source-ledger');p.add_argument('--audio-bundle');p.add_argument('--answer-key')
    p.add_argument('--demo',action='store_true',help='仅允许完整安装包中的合成示例，不适用于教师试卷')
    p.add_argument('--review',help='针对本次教学内容的实际复核记录')
    p.add_argument('--rebuild-from',help='明确沿用旧课件目录中的教师选择；仍需复核本次内容')
    p.add_argument('--plan',help='老师确认的 generation-plan.json')
    p.add_argument('--profile',choices=['full','quick'],default=None,help='quick=先出可上课版，精读项后补；不给则用计划里的 profile，计划也没有时用 full')
    p.add_argument('--sections',default='all',help='all 或逗号分隔的题型/章节ID，如 reading,A,L6')
    p.add_argument('--mode',choices=['lesson','intensive'])
    p.add_argument('--audio-mode',choices=['embedded','folder'],default='embedded')
    p.add_argument('--dictionary-scope',choices=['lesson','full'],default='lesson',help='lesson=只内置本篇出现的词的离线释义（HTML 小得多）；full=内置整本离线词库')
    a=p.parse_args()
    try:build(a.input,a.out,a.source_ledger,a.audio_bundle,a.answer_key,a.profile,a.sections,a.mode,a.audio_mode,a.plan,a.dictionary_scope,review=a.review,rebuild_from=a.rebuild_from,demo=a.demo)
    except (AssertionError,ValueError,KeyError,FileNotFoundError,subprocess.CalledProcessError,subprocess.TimeoutExpired) as e:p.exit(1,f'ERROR: {explain_error(e)}\n')
