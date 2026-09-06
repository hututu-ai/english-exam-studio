"""Student-only worksheet: no answer keys, translations or hidden model answers."""
from html import escape
from pathlib import Path
import re

def e(v):return escape(str(v or ''),quote=True)
def source(t):return re.sub(r'\{\{(\d+)\}\}',lambda m:'<span class="blank">'+m[1]+' ________</span>',e(t)).replace('\n','<br>')
def make_worksheet(d,assets,out):
 rows=[]
 for s in d['sections']:
  body='<header><h2>'+e(s['title'])+'</h2><span>姓名：____________ 日期：____________</span></header>'
  if s['kind']!='listening':
   body+='<div class="reading">'
   for p in s['paragraphs']:
    tag='h3' if p.get('role')=='heading' or p.get('heading') else 'p'
    body+='<'+tag+' class="'+('caption' if p.get('role')=='caption' else '')+'">'+source(p['text'])+'</'+tag+'>'
    if p.get('image'):body+='<img src="'+e(p['image'])+'" alt="'+e(p.get('alt','原卷图示'))+'">'
   body+='</div>'
  else:body+='<p class="hint">先审题，再听音。记录关键词、同义表达或干扰信息；与老师核对后补充自己的判断依据。</p>'
  for q in s['questions']:
   body+='<article class="question" data-qid="'+e(q['id'])+'"><p><b>'+e(q['id'])+'.</b> '+e(q['stem'])+'</p>'
   if q.get('options'):body+='<div class="options">'+''.join('<div>'+e(k)+'. '+e(v)+'</div>' for k,v in q['options'].items())+'</div>'
   body+='<p class="answer-space">'+('写作草稿' if s['kind']=='writing' else '我的答案与依据')+'：________________________________________________________</p>'
   if s['kind']=='writing':body+='<div class="writing-space"></div>'
   body+='</article>'
  if s.get('inquiry'):
   body+='<h3>回到原文，再想一步</h3>'+''.join('<p>'+e(x['question'])+'</p><div class="lines"></div>' for x in s['inquiry'])
  if s.get('transfer_tasks'):
   body+='<h3>从阅读到表达</h3>'+''.join('<article><b>'+e(x['title'])+'</b><blockquote>'+source(x.get('source_quote',''))+'</blockquote><p>'+e(x['prompt'])+'</p><div class="lines"></div><p class="hint">自查：'+e(x['check'])+'</p></article>' for x in s['transfer_tasks'])
  words={v['word']:v for v in s.get('quick_words',[])};words.update({v['word']:v for v in s.get('vocabulary',[])})
  if words:body+='<h3>语境词汇积累</h3><table><thead><tr><th>本节词语</th><th>语境义 / 搭配 / 自己的例句</th></tr></thead><tbody>'+''.join('<tr><td>'+e(w)+'</td><td> </td></tr>' for w in words)+'</tbody></table>'
  if s.get('writing_bank'):
   body+='<h3>写作表达迁移</h3>'+''.join('<article><b>'+e(x['category'])+'</b><blockquote>'+source(x['quote'])+'</blockquote><p>'+e(x['task'])+'</p><div class="lines"></div><p class="hint">自查：'+e(x['check'])+'</p></article>' for x in s['writing_bank'])
  if s.get('sentences'):body+='<h3>句子观察</h3>'+''.join('<blockquote>'+source(x['quote'])+'</blockquote><p class="hint">圈出主干，标出修饰或连接成分，再写一句同结构的表达。</p><div class="lines"></div>' for x in s['sentences'])
  rows.append('<section id="'+e(s['id'])+'" data-kind="'+e(s['kind'])+'" class="worksheet">'+body+'</section>')
 template=(assets/'worksheet.html').read_text()
 nav=''.join('<label><input type="checkbox" checked data-section="'+e(s['id'])+'">'+e(s['title'])+'</label>' for s in d['sections'])
 html=template.replace('__TITLE__',e(d['title'])).replace('__SECTION_OPTIONS__',nav).replace('__WORKSHEET_BODY__',''.join(rows))
 (out/'worksheet.html').write_text(html,encoding='utf-8')
 return len(rows)
