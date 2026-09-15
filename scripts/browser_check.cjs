#!/usr/bin/env node
/* Actual browser interaction checks; no dependency installation or network services. */
const fs=require('node:fs'),path=require('node:path'),http=require('node:http'),crypto=require('node:crypto'),assert=require('node:assert/strict');
const out=path.resolve(process.argv[2]||'output'),stress=process.argv.includes('--stress');
// 超时可配：Windows 的 CI runner 明显慢于开发机，把上限写死会把"这台机器慢"误报成"课件坏了"。
const limitSeconds=Number(process.env.BROWSER_CHECK_TIMEOUT||180),startedAt=Date.now();
const report={status:'running',started_at:new Date().toISOString(),node_version:process.version,phase:'starting',elapsed_seconds:0,timeout_seconds:limitSeconds,html_sha256:null,engine:process.env.BROWSER_ENGINE||'chromium',checks:[],skipped:[],errors:[],scope:'Actual clicks and media playback via localhost; not a WorkBuddy/Doubao end-to-end certification, file:// test, or teaching/audio-alignment review. Entries under skipped were NOT executed (feature disabled or no data) and must not be read as verified.'};
let server,browser;
const save=()=>{report.elapsed_seconds=Math.round((Date.now()-startedAt)/10)/100;fs.writeFileSync(path.join(out,'browser-check.json'),JSON.stringify(report,null,2))};
// 与 scripts/section_kinds.py 同一套规则：kind 是试卷自己的题型名，呈现方式由 kind_preset 或内容决定。
const SECTION_PRESETS=['listening','reading','seven','cloze','grammar','writing'];
const KIND_ALIASES={'listening':'listening','listen':'listening','听力':'listening','听力理解':'listening','听力测试':'listening','听力部分':'listening','听说应用':'listening','听说':'listening','reading':'reading','阅读理解':'reading','阅读':'reading','任务型阅读':'reading','seven':'seven','七选五':'seven','阅读填空':'seven','阅读七选五':'seven','配对阅读':'seven','信息匹配':'seven','cloze':'cloze','完形':'cloze','完形填空':'cloze','完型填空':'cloze','语法选择':'cloze','grammar':'grammar','语法填空':'grammar','语法':'grammar','单项填空':'grammar','单项选择':'grammar','词汇运用':'grammar','单词拼写':'grammar','短文填空':'grammar','writing':'writing','写作':'writing','书面表达':'writing','读后续写':'writing','概要写作':'writing','应用文写作':'writing','作文':'writing','听句子选图':'listening','听短文':'listening','听对话':'listening','听录音':'listening','回答问题':'reading','阅读回答':'reading','阅读表达':'reading','阅读并回答':'reading','书面表达（':'writing','话题作文':'writing'};
// 小标题也决定呈现方式（如 "B. 书面表达"→writing、"A. 回答问题"→reading），与 scripts/section_kinds.py 同一优先级。
const ALIAS_KEYS=Object.keys(KIND_ALIASES).sort((a,b)=>b.length-a.length);
function aliasIn(text){text=String(text||'');if(!text)return null;for(const key of ALIAS_KEYS){if(text.includes(key))return KIND_ALIASES[key]}return null}
function sectionPreset(s){s=s||{};const declared=String(s.kind_preset||s.preset||'').trim();if(declared)return declared;const kind=String(s.kind||'').trim();if(SECTION_PRESETS.includes(kind))return kind;if(KIND_ALIASES[kind])return KIND_ALIASES[kind];const titlePreset=aliasIn(String(s.title||'')+String(s.subtitle||''));if(titlePreset)return titlePreset;const qs=s.questions||[];if(s.audio||s.audio_note||(s.blanks||[]).length>0||qs.some(q=>q&&q.audio))return 'listening';if(s.writing_steps||s.teacher_model)return 'writing';if(qs.some(q=>q&&q.knowledge))return 'grammar';return 'custom'}
const isListening=s=>sectionPreset(s)==='listening';
const isWriting=s=>sectionPreset(s)==='writing';
const groupKey=s=>String((s&&(s.group||s.kind||s.id))||'');
const groupTitle=s=>{s=s||{};const explicit=String(s.group_title||s.chapter_title||'').trim();if(explicit)return explicit;const kind=String(s.kind||'').trim();if(kind&&!SECTION_PRESETS.includes(kind))return kind;return ({listening:'听力',reading:'阅读',seven:'七选五',cloze:'完形',grammar:'语法填空',writing:'写作'})[sectionPreset(s)]||kind||'章节'};
function chapterGroups(exam){const out=[],index={};for(const s of (exam.sections||[])){const key=groupKey(s);if(!(key in index)){index[key]=out.length;out.push({key,title:groupTitle(s),items:[]})}out[index[key]].items.push(s)}return out}
const ok=(name,details)=>{report.checks.push({name,status:'passed',details});console.log('PASS '+name)};
const skip=(name,reason)=>{report.skipped.push({name,reason});console.log('SKIP '+name+' — '+reason)};
// 未执行却报 PASS 等于让报告撒谎：收尾时把"功能未开启 / 没有可测数据"的项降级为 skipped。
function reconcile(exam){
 const featureChecks={'offline-lookup-serves-lesson-words':'dictionary','deep-reading-structure-renders-and-locates':'deep_reading','writing-transfer-tab-renders':'writing_transfer'};
 const hasData={
  'only-one-analysis-open-per-section':exam.sections.some(s=>!isWriting(s)&&!isListening(s)&&(s.questions||[]).filter(q=>q.options&&Object.keys(q.options).length).length>=2),
  'paragraph-translation-toggles':exam.sections.some(s=>!isListening(s)&&(s.paragraphs||[]).some(p=>p.translation)),
  'listening-dictation-hides-and-reveals-real-words':exam.sections.some(s=>isListening(s)&&(s.blanks||[]).length),
  'quick-answers-whole-and-kind-no-analysis-side-effects':exam.features?.quick_answers!==false,
  'culture-card-and-source-location':Boolean(exam.features?.culture_background)&&exam.sections.some(s=>(s.culture_background||[]).length),
  'multi-page-origin-renders-every-page':exam.sections.some(s=>(s.origin?.page_images||[]).length>1)
 };
 report.checks=report.checks.filter(check=>{
  const feature=featureChecks[check.name];
  const reason=(feature&&exam.features?.[feature]===false)?('功能 '+feature+' 未开启，本项未执行')
   :(check.name in hasData&&!hasData[check.name])?'本课件没有可测数据，本项未执行':null;
  if(reason){report.skipped.push({name:check.name,reason});console.log('SKIP '+check.name+' — '+reason);return false}
  return true;
 });
}
// 超时也要能诊断：写清"跑到第几项、卡在哪个阶段"，而不是只说一句"超过 180 秒"。
const deadline=setTimeout(()=>{report.status='failed';const last=report.checks.at(-1);report.errors.push(`浏览器验收超过 ${limitSeconds} 秒还没跑完（已完成 ${report.checks.length} 项，最后一项是 ${last?last.name:'（一项都没跑完）'}；当前阶段 ${report.phase}）。先用 BROWSER_CHECK_TIMEOUT 放宽上限重跑确认，再判断是不是真的卡死。`);save();process.exit(1)},limitSeconds*1000);
async function main(){
 const html=fs.readFileSync(path.join(out,'index.html'));report.html_sha256=crypto.createHash('sha256').update(html).digest('hex');
 const match=html.toString().match(/<script id="examData" type="application\/json">([\s\S]*?)<\/script>/);assert.ok(match,'Missing canonical examData');const exam=JSON.parse(match[1]);
 const media=new Set([exam.full_audio,...exam.sections.flatMap(s=>[s.audio,s.origin?.page_image,...(s.origin?.page_images||[]),...s.questions.flatMap(q=>[q.audio,...Object.values(q.option_images||{})]),...(s.paragraphs||[]).map(p=>p.image)])].filter(Boolean));report.media_sha256={};for(const name of media){const file=path.resolve(out,name);assert.ok(file.startsWith(out+path.sep),'Media must be inside output');report.media_sha256[name]=crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex')}
 let pw;try{pw=require(process.env.PLAYWRIGHT_MODULE||'playwright')}catch{report.status='not_available';throw Error('Playwright 未安装；没有自动安装。可使用宿主浏览器逐项验收并记录，或经同意准备浏览器测试环境。')}
 server=http.createServer((req,res)=>{try{const url=new URL(req.url,'http://localhost');const isolated=url.pathname==='/isolated.html';let file=isolated?path.join(out,'index.html'):path.resolve(out,'.'+decodeURIComponent(url.pathname==='/'?'/index.html':url.pathname));if(file!==out&&!file.startsWith(out+path.sep)){res.writeHead(403).end();return}const bytes=fs.readFileSync(file),ext=path.extname(file);res.setHeader('Content-Type',({'.html':'text/html; charset=utf-8','.json':'application/json','.wav':'audio/wav','.mp3':'audio/mpeg','.png':'image/png','.jpg':'image/jpeg'})[ext]||'application/octet-stream');res.setHeader('Cache-Control','no-store');const range=req.headers.range?.match(/^bytes=(\d+)-(\d*)$/);if(range){const start=+range[1],end=Math.min(range[2]?+range[2]:bytes.length-1,bytes.length-1);if(start>end){res.writeHead(416).end();return}res.writeHead(206,{'Content-Range':`bytes ${start}-${end}/${bytes.length}`,'Accept-Ranges':'bytes','Content-Length':end-start+1});res.end(bytes.subarray(start,end+1))}else res.end(bytes)}catch{res.writeHead(404).end()}});
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));const base=`http://127.0.0.1:${server.address().port}`;
 report.phase='launching';save();browser=await pw[report.engine].launch({headless:true,...(report.engine==='chromium'&&process.env.CHROME_BIN?{executablePath:process.env.CHROME_BIN}:{})});report.browser_version=browser.version();report.platform=process.platform;report.phase='checks';
 async function newPage(mode='normal',width=1440){const ctx=await browser.newContext({viewport:{width,height:900},javaScriptEnabled:mode!=='no-js'});await ctx.route('**/*',route=>route.request().url().startsWith(base)||route.request().url().startsWith('blob:'+base+'/')||route.request().url().startsWith('data:')?route.continue():route.abort());
 if(mode==='isolated')await ctx.route('**/audio/**',r=>r.abort());
 await ctx.addInitScript(({mode,title})=>{
 if(mode==='no-speech'){Object.defineProperty(window,'speechSynthesis',{value:undefined});Element.prototype.requestFullscreen=undefined}
 if(mode==='no-canvas')HTMLCanvasElement.prototype.getContext=()=>null;
 if(mode==='no-dialog'){HTMLDialogElement.prototype.showModal=undefined;HTMLDialogElement.prototype.close=undefined}
 if(mode==='bad-scores')localStorage.setItem('exam-scores-'+title,'[null,null,null,null]');
 if(mode==='bad-storage')localStorage.setItem('exam-classroom-v5-'+title,JSON.stringify({title,version:5,ui:{openAnswers:null,layout:null}}));
 if(mode==='no-storage'){Storage.prototype.getItem=()=>{throw Error('Storage blocked')};Storage.prototype.setItem=()=>{throw Error('Storage blocked')}}
 },{mode,title:exam.title});const p=await ctx.newPage();p.setDefaultTimeout(7000);p.on('pageerror',e=>report.errors.push(mode+': '+e.message));await p.goto(base+(mode==='isolated'?'/isolated.html':'/'),{waitUntil:'load',timeout:15000});if(mode!=='no-js')await p.waitForFunction(()=>window.__lessonReady===true,{},{timeout:10000});return {p,ctx}}
 async function go(p,s){await p.locator(`[data-group="${groupKey(s)}"] .chapter-group-toggle`).click();await p.locator(`#chapterMenuFloat [data-nav="${s.id}"]`).click();await p.waitForFunction(id=>state.active===id,s.id);}
 async function quick(p){if(exam.features?.quick_answers===false){assert.ok(await p.locator('#quickAnswers').isHidden());return}const scoped=exam.sections.filter(s=>!isWriting(s)&&s.questions.length);const count=scoped.reduce((n,s)=>n+s.questions.length,0);if(!count)return;await p.locator('#quickAnswers').click();assert.equal(await p.locator('.answer-tile').count(),count);await p.locator('#quickToggleAnswers').click();await p.locator('#quickScopeKind').click();const keys=[...new Set(scoped.map(groupKey))];assert.equal(await p.locator('#quickAnswerScope option').count(),keys.length);for(const k of keys){await p.locator('#quickAnswerScope').selectOption(k);assert.equal(await p.locator('.answer-tile').count(),scoped.filter(s=>groupKey(s)===k).reduce((n,s)=>n+s.questions.length,0))}await p.locator('[data-close="quickAnswersDialog"]').click()}
 async function play(p,s){await go(p,s);const a=p.locator('#audio-'+s.id);await a.evaluate(a=>a.muted=true);await p.locator(`[data-action="playListening"][data-sid="${s.id}"]`).click();try{await p.waitForFunction(id=>{const a=document.getElementById('audio-'+id);return a.currentTime>0&&!a.paused},s.id)}catch(e){throw Error('Audio playback failed: '+JSON.stringify(await a.evaluate(a=>({error:a.error?{code:a.error.code,message:a.error.message}:null,readyState:a.readyState,networkState:a.networkState,paused:a.paused,currentTime:a.currentTime,duration:a.duration,playError:window.__lastAudioError,source:a.currentSrc.slice(0,100)}))))}assert.ok(await a.evaluate(a=>Number.isFinite(a.duration)&&a.duration>0));await p.locator(`.speed[data-audio="audio-${s.id}"]`).selectOption('0.75');assert.equal(await a.evaluate(a=>a.playbackRate),.75);await p.locator(`[data-action="playListening"][data-sid="${s.id}"]`).click();for(const q of s.questions.filter(q=>q.audio)){const qa=p.locator(`audio[data-q-audio="${q.id}"]`);await qa.evaluate(async a=>{a.muted=true;await a.play()});await p.waitForFunction(id=>document.querySelector('audio[data-q-audio="'+id+'"]').currentTime>0,q.id);await qa.evaluate(a=>a.pause())}}
 const {p,ctx}=await newPage();assert.ok(await p.locator('#bootNotice').isHidden());assert.equal(await p.locator('.chapter-group-toggle').count(),chapterGroups(exam).length);
 for(const s of exam.sections){await go(p,s);const section=p.locator('#section-'+s.id);assert.ok(await section.isVisible());if(isListening(s))assert.ok(await section.locator('.transcript-tools, [data-action="playListening"], [data-action="listenMode"]').count()>0,`${s.kind} 是听力节，必须渲染听力工具`);else{assert.equal(await section.locator('.transcript-tools').count(),0,`${s.kind} 不是听力节，不能渲染听力工具`);const t=section.locator('[data-action="translate"]').first();if(await t.count()){await t.click();assert.ok(await section.locator('.translation:not([hidden])').count()>0);await t.click()}}
 await section.locator('[data-action="vocabulary"]').click();assert.ok(await p.locator('#studyDialog').isVisible());await p.locator('[data-close="studyDialog"]').click();
 // Each question is independently expandable; no whole-section reveal substitution.
 for(const q of s.questions){const button=section.locator(`[data-action="answer"][data-qid="${q.id}"]`);if(await button.count()){await button.click();assert.ok(await p.evaluate(id=>ui.openAnswers.includes(id),q.id));await button.click()}}
 }
 ok('all-sections-navigation-vocabulary-and-individual-analysis',{sections:exam.sections.length,questions:exam.sections.reduce((n,s)=>n+s.questions.length,0)});
 // 逐句译文：开关显示整段逐句；点某一句只看该句；未译的句子必须如实标出。
 {
  const pick=exam.sections.flatMap(s=>(s.paragraphs||[]).filter(p=>(p.sentence_translations||[]).length).map(p=>({s,p})))[0];
  if(!pick)skip('sentence-translations-display','本课件没有逐句译文，本项未执行');
  else{
   await go(p,pick.s);
   const section=p.locator(`#section-${pick.s.id}`);
   const toggle=section.locator(`[data-action="sentenceMode"][data-pid="${pick.p.id}"]`);
   assert.equal(await toggle.count(),1,'有逐句译文的段落必须有「逐句译文」开关');
   const sentences=(await p.evaluate(({sid,pid})=>splitSentences(sections.get(sid).paragraphs.find(x=>x.id===pid).text),{sid:pick.s.id,pid:pick.p.id}));
   await toggle.click();
   const rows=section.locator(`.sentence-row`);
   assert.equal(await rows.count(),sentences.length,`逐句译文必须与分句一一对应（应为 ${sentences.length} 行）`);
   const translated=pick.p.sentence_translations.filter(text=>String(text||'').trim()).length;
   assert.equal(await section.locator('.sentence-zh').count(),sentences.length,'每句都要有中文行（未译也要写清楚）');
   const body=await section.locator('.sentence-block').innerText();
   assert.ok(translated>0&&body.includes('合成测试译文'),'已翻译的句子必须显示中文');
   if(translated<sentences.length)assert.ok(body.includes('本句未译'),'未翻译的句子必须如实写出「本句未译」');
   // 点某一句 → 只看该句
   const target=Math.min(sentences.length-1,1);
   await section.locator(`.sentence-pick[data-sentence="${target}"]`).click();
   assert.equal(await section.locator('.sentence-row').count(),1,'点某句后只应保留该句');
   assert.equal(await section.locator('.sentence-row').first().getAttribute('data-sentence')===null?String(target):String(target),String(target));
   // 再点同句 → 回到整段逐句
   await section.locator(`.sentence-pick[data-sentence="${target}"]`).click();
   assert.equal(await section.locator('.sentence-row').count(),sentences.length,'再点同句应恢复整段逐句');
   await toggle.click();
   assert.equal(await section.locator('.sentence-row').count(),0,'关闭后不应显示逐句译文');
   ok('sentence-translations-display',{sentences:sentences.length,translated});
  }
 }
 // 分值来自试卷标题：卷首满分/用时、每节的"本大题X分·每小题Y分"都要真的显示出来。
 {
  const scored=exam.sections.filter(s=>Number(s.score_total)>0||Number(s.score_per_question)>0);
  if(!exam.full_score&&!exam.exam_minutes&&!scored.length)skip('scores-and-exam-info-render','本课件没有分值信息，本项未执行');
  else{
   const hero=await p.locator('#hero').evaluate(el=>el.textContent||'');   // 用 textContent：卷首说明在打印样式里可能被隐藏
   if(exam.full_score)assert.ok(hero.includes(`满分 ${exam.full_score} 分`),`卷首必须显示满分：${hero}`);
   if(exam.exam_minutes)assert.ok(hero.includes(`考试用时 ${exam.exam_minutes} 分钟`),`卷首必须显示考试用时：${hero}`);
   for(const s of scored){
    await go(p,s);
    const head=await p.locator(`#section-${s.id} h2`).innerText();
    if(Number(s.score_total)>0)assert.ok(head.includes(`本大题 ${s.score_total} 分`),`第 ${s.id} 节标题必须显示本大题分值：${head}`);
    if(Number(s.score_per_question)>0)assert.ok(head.includes(`每小题 ${s.score_per_question} 分`),`第 ${s.id} 节标题必须显示每小题分值：${head}`);
   }
   ok('scores-and-exam-info-render',{sections:scored.map(s=>s.id)});
  }
 }
 // 图片选项（听句子选图 / 图表选项）：图片必须真的加载出来，并且仍然能点选。
 {
  const withImages=exam.sections.flatMap(s=>(s.questions||[]).filter(q=>Object.keys(q.option_images||{}).length).map(q=>({s,q})));
  if(!withImages.length)skip('option-images-render-and-select','本课件没有图片选项，本项未执行');
  else{
   for(const {s,q} of withImages){
    await go(p,s);
    const section=p.locator('#section-'+s.id);
    const letters=Object.keys(q.option_images);
    for(const letter of letters){
     const img=section.locator(`#q-${q.id} .option[data-choice="${letter}"] .option-image`);
     assert.ok(await img.count()>0,`第 ${q.id} 题选项 ${letter} 的图片没有渲染出来`);
     const loaded=await img.first().evaluate(el=>el.complete&&el.naturalWidth>0);
     assert.ok(loaded,`第 ${q.id} 题选项 ${letter} 的图片没能加载（src 或指纹不对）`);
    }
    const first=section.locator(`#q-${q.id} .option[data-choice="${letters[0]}"]`);
    await first.click();
    assert.equal(await p.evaluate(id=>state.choices[id],q.id),letters[0],`第 ${q.id} 题的图片选项仍然必须能点选`);
    await first.click();
   }
   ok('option-images-render-and-select',{questions:withImages.map(x=>x.q.id)});
  }
 }
 // 课堂反馈 1：答案解析的字号必须跟着字号控件一起变大（原来 .analysis-panel 是固定 px）。
 {
  const target=exam.sections.find(s=>!isListening(s)&&(s.questions||[]).some(q=>q.analysis));
  if(!target)skip('analysis-font-scales-with-font-control','本课件没有解析内容，本项未执行');
  else{
   await go(p,target);
   const qid=target.questions.find(q=>q.analysis).id;
   const button=p.locator(`#section-${target.id} [data-action="answer"][data-qid="${qid}"]`);
   const wasOpen=await p.evaluate(id=>ui.openAnswers.includes(id),qid);
   if(await button.count()&&!wasOpen)await button.click();
   const sizeOf=()=>p.evaluate(id=>{const el=document.querySelector('#q-'+id+' .analysis-panel');return el?parseFloat(getComputedStyle(el).fontSize):0},qid);
   const before=await sizeOf();
   if(!before)skip('analysis-font-scales-with-font-control','打不开解析面板，本项未执行');
   else{
    await p.locator('#fontPlus').click();await p.locator('#fontPlus').click();
    const after=await sizeOf();
    assert.ok(after>before,`解析字号必须跟着字号控件变大：${before} → ${after}`);
    await p.locator('#fontMinus').click();await p.locator('#fontMinus').click();
    assert.ok(Math.abs((await sizeOf())-before)<0.6,'字号调回后解析应回到原大小');
    if(!wasOpen&&await button.count())await button.click();   // 还原解析展开状态，后面的检查不受影响
    ok('analysis-font-scales-with-font-control',{before,after});
   }
  }
 }
 // 课堂反馈 2：解析展开后，点选项里的单词要能查词/带读（原来被"选择选项"吞掉）。
 {
  const target=exam.sections.find(s=>!isListening(s)&&(s.questions||[]).some(q=>Object.keys(q.options||{}).length&&q.analysis));
  if(!target)skip('option-word-opens-dictionary-after-reveal','本课件没有带选项的解析，本项未执行');
  else{
   await go(p,target);
   const q=target.questions.find(q=>Object.keys(q.options||{}).length&&q.analysis);
   const button=p.locator(`#section-${target.id} [data-action="answer"][data-qid="${q.id}"]`);
   const wasOpen=await p.evaluate(id=>ui.openAnswers.includes(id),q.id);
   if(await button.count()&&!wasOpen)await button.click();
   const word=p.locator(`#q-${q.id} .option .word`).first();
   if(!(await word.count()))skip('option-word-opens-dictionary-after-reveal','选项里没有可点单词，本项未执行');
   else{
    await word.click();
    await p.waitForFunction(()=>{const el=document.querySelector('#quickDict');return el&&!el.hidden&&el.querySelector('.quick-meaning')},{},{timeout:4000});
    const term=await p.locator('#quickDict .quick-title strong').innerText();
    assert.ok(term.length>0,'词旁释义必须显示被点的词');
    assert.ok(await p.locator('#quickDict [data-action="speakWord"]').count()>0,'词旁释义必须能带读');
    assert.ok(!(await p.evaluate(id=>ui.openAnswers.includes(id),q.id))===false,'点单词查词不能把解析关掉');
    await p.evaluate(()=>{const el=document.querySelector('#quickDict');if(el)el.hidden=true});
    if(!wasOpen&&await button.count())await button.click();   // 还原
    ok('option-word-opens-dictionary-after-reveal',{term});
   }
  }
 }
 // 课堂反馈 3：划选一个短语（固搭）要能看到义项/固搭，而不是什么都没有。
 {
  const target=exam.sections.find(s=>!isListening(s)&&(s.paragraphs||[]).some(p=>(p.text||'').trim().split(/\s+/).length>=4));
  if(!target)skip('selection-shows-phrase-meaning-or-collocation','本课件没有可划选的原文，本项未执行');
  else{
   await go(p,target);
   const picked=await p.evaluate(sid=>{
    const node=document.getElementById('section-'+sid)?.querySelector('.ptext');
    if(!node)return null;
    const spans=[...node.querySelectorAll('.word')];
    if(spans.length<2)return null;
    const first=spans[0].firstChild,second=spans[1].firstChild;
    if(!first||!second)return null;
    const range=document.createRange();range.setStart(first,0);range.setEnd(second,second.textContent.length);
    const sel=getSelection();sel.removeAllRanges();sel.addRange(range);
    node.dispatchEvent(new MouseEvent('mouseup',{bubbles:true}));
    return sel.toString().trim();
   },target.id);
   if(!picked)skip('selection-shows-phrase-meaning-or-collocation','原文里没有可划选的短语，本项未执行');
   else{
    await p.waitForFunction(()=>{const el=document.querySelector('#v10Selection');return el&&!el.hidden&&el.querySelector('.v10-snippet')},{},{timeout:4000});
    const snippet=await p.locator('#v10Selection .v10-snippet').innerText();
    assert.equal(snippet.trim(),picked,'划选工具必须显示选中的原文');
    const meaning=await p.locator('#v10Selection .v10-selection-meaning').count();
    assert.ok(meaning>0,'划选短语后必须给出义项（或如实说明未收录），不能只显示原文片段');
    const text=await p.locator('#v10Selection .v10-selection-meaning').innerText();
    assert.ok(text.trim().length>0,'义项说明不能为空');
    await p.evaluate(()=>{const sel=getSelection();if(sel)sel.removeAllRanges();const el=document.querySelector('#v10Selection');if(el)el.hidden=true});
    ok('selection-shows-phrase-meaning-or-collocation',{picked,shown:text.slice(0,40)});
   }
  }
 }
 // 结构由试卷决定：导航的分组、顺序、名称必须与试卷数据一致，不能被模板按固定题型重排或改名。
 {
  const expected=chapterGroups(exam);
  assert.equal(await p.locator('.chapter-group-toggle').count(),expected.length,'章节组数量必须等于试卷里的板块数');
  assert.deepEqual(await p.locator('.chapter-group-toggle').allInnerTexts(),expected.map(g=>g.title),'顶层章节组必须按试卷顺序显示试卷自己的板块名');
  assert.deepEqual(await p.locator('.chapter-group').evaluateAll(nodes=>nodes.map(n=>n.dataset.group)),expected.map(g=>g.key),'每个章节组的 data-group 必须是试卷的分组键');
  assert.deepEqual(await p.locator('#nav .navgroup').allInnerTexts(),expected.map(g=>g.title),'侧边栏分组同样按试卷顺序与名称');
  for(const group of expected){
   await p.locator(`[data-group="${group.key}"] .chapter-group-toggle`).click();
   const labels=await p.locator('#chapterMenuFloat [data-nav]').evaluateAll(nodes=>nodes.map(n=>n.dataset.nav));
   assert.deepEqual(labels,group.items.map(s=>s.id),`「${group.title}」菜单里的章节顺序必须与试卷一致`);
   await p.evaluate(()=>window.__chapterMenuHide&&window.__chapterMenuHide());
  }
  ok('chapter-bar-follows-paper-structure',{groups:expected.map(g=>g.title)});
 }
 // 题型名不在预设六种里时，工具必须跟着"这一节实际有什么"走，而不是跟着名字走。
 {
  const custom=exam.sections.filter(s=>!SECTION_PRESETS.includes(String(s.kind||'').trim()));
  if(!custom.length)skip('custom-kinds-get-tools-from-content','本课件没有使用预设之外的题型名，本项未执行');
  else{
   for(const s of custom){
    await go(p,s);const section=p.locator('#section-'+s.id);
    if(isWriting(s))assert.match(await section.locator('h2').innerText(),/项写作/,`${s.kind} 有范文/写作步骤，必须显示写作讲解区`);
    else if(isListening(s))assert.match(await section.locator('h2').innerText(),/^Test /,`${s.kind} 带音频，必须显示听力播放区`);
    else assert.ok(await section.locator('.reader-head, .transcript-tools').count()>0,`${s.kind} 有原文，必须显示原文区`);
   }
   ok('custom-kinds-get-tools-from-content',{kinds:custom.map(s=>s.kind)});
  }
 }
 // 课堂不变式：每节最多展开一道解析（SKILL.md / regression.md）。此前只逐个开关，从未同时开两道。
 for(const sect of exam.sections.filter(s=>!isWriting(s)&&!isListening(s)&&s.questions.length>=2)){
   const objective=sect.questions.filter(q=>q.options&&Object.keys(q.options).length);
   if(objective.length<2)continue;
   await go(p,sect);
   const analysis=id=>p.locator(`#q-${id} .analysis`);
   await p.locator(`[data-action="answer"][data-qid="${objective[0].id}"]`).click();
   assert.ok(await analysis(objective[0].id).isVisible(),'the first analysis must open');
   await p.locator(`[data-action="answer"][data-qid="${objective[1].id}"]`).click();
   assert.ok(await analysis(objective[1].id).isVisible(),'the second analysis must open');
   assert.ok(await analysis(objective[0].id).isHidden(),'opening a second analysis must collapse the first');
   assert.equal(await p.locator(`#section-${sect.id} .analysis:not([hidden])`).count(),1,'at most one analysis may be expanded per section');
 }
 ok('only-one-analysis-open-per-section');
 // 图片版试卷：一节跨多页时，“出处”弹窗必须渲染每一页，而不是只给第一页。
 const multiPage=exam.sections.find(s=>(s.origin?.page_images||[]).length>1);
 // 这是通用检查：普通课件没有多页页图时应当跳过，而不是判定失败（夹具必须带多页由测试保证）。
 if(!multiPage)skip('multi-page-origin-renders-every-page','本课件没有多页页图');
 else{
  await go(p,multiPage);
  const originButton=p.locator(`#section-${multiPage.id} [data-action="origin"]`).first();
  assert.ok(await originButton.count(),'a section with source pages must offer the 出处 entry');
  await originButton.click();
  assert.equal(await p.locator('#originDialog .origin-pages img').count(),multiPage.origin.page_images.length,'every source page must render');
  await p.locator('[data-close="originDialog"]').click();
  ok('multi-page-origin-renders-every-page');
 }
 // 离线查词：本页禁止一切外部请求，所以查本篇的词若还能出释义，只可能来自内置词库。
 if(exam.features?.dictionary!==false){
   const scoped=exam.dictionary||{};
   assert.ok(Object.keys(scoped).length>0,'dictionary feature is on but no entries were embedded — the offline lookup check would be vacuous');
   const dictWord=(exam.sections.flatMap(s=>s.quick_words||[]).map(w=>w.word).find(w=>scoped[String(w).toLowerCase()]))||Object.keys(scoped)[0];
   await p.locator('#lookupInput').fill(dictWord);
   await p.locator('#lookupForm button[type="submit"]').click();
   await p.waitForFunction(()=>{const el=document.querySelector('#dictResult');return el&&el.innerText.trim().length>0});
   assert.match(await p.locator('#dictResult').innerText(),/ECDICT|离线/,'a lesson word must resolve from the bundled dictionary without network');
   const closer=p.locator('[data-close="dictDialog"]');
   if(await closer.count())await closer.click();
 }
 ok('offline-lookup-serves-lesson-words');
 assert.equal(await p.locator('#themeSelect option').count(),6);for(const theme of ['paper','amethyst','mist','sand','rose','pearl']){await p.locator('#themeSelect').selectOption(theme);assert.equal(await p.locator('#themeSelect').inputValue(),theme)}await p.locator('#themeSelect').selectOption('amethyst');await p.locator('#fontSizeSelect').selectOption('28');await p.reload();await p.waitForFunction(()=>window.__lessonReady);assert.equal(await p.locator('#fontSizeSelect').inputValue(),'28');assert.equal(await p.locator('#themeSelect').inputValue(),'amethyst');ok('font-and-theme-persist');
 const before=await p.evaluate(()=>JSON.stringify([ui.openAnswers,[...state.answers]]));await quick(p);assert.equal(await p.evaluate(()=>JSON.stringify([ui.openAnswers,[...state.answers]])),before);ok('quick-answers-whole-and-kind-no-analysis-side-effects');
 const reading=exam.sections.find(s=>sectionPreset(s)==='reading')||exam.sections.find(s=>!isListening(s));if(reading)await go(p,reading);
 if(exam.features?.annotations!==false){await p.locator('#annotate').click();assert.ok(await p.locator('#inkToolbar').isVisible())}else assert.ok(await p.locator('#annotate').isHidden());
 if(reading&&exam.features?.annotations!==false){const box=await p.locator('#section-'+reading.id+' .source-text').first().boundingBox();assert.ok(box);for(const tool of ['pen','arrow','rect','ellipse']){await p.locator('[data-ink-mode="'+tool+'"]').click();await p.mouse.move(box.x+20,box.y+15);await p.mouse.down();await p.mouse.move(box.x+140,box.y+55,{steps:8});await p.mouse.up()}assert.equal(await p.evaluate(()=>ui.ink[state.active].length),4);await p.locator('#inkUndo').click();assert.equal(await p.evaluate(()=>ui.ink[state.active].length),3);await p.locator('#inkClear').click();assert.equal(await p.evaluate(()=>ui.ink[state.active].length),0);ok('pen-arrow-rectangle-ellipse-undo-clear')}
 if(exam.features?.annotations!==false)await p.locator('#inkClose').click();if(exam.features?.classroom_tools!==false){await p.locator('#classroom').click();assert.ok(await p.locator('#classDialog').isVisible());await p.locator('[data-close="classDialog"]').click()}else assert.ok(await p.locator('#classroom').isHidden());ok('annotation-and-classroom-open');

 // Teacher-authored revisions: use real form controls, then persistence and record import.
 const editSection=exam.sections.find(s=>!isWriting(s)&&s.questions.some(q=>Object.keys(q.options||{}).length));
 if(editSection){await go(p,editSection);const q=editSection.questions.find(q=>Object.keys(q.options||{}).length),other=Object.keys(q.options).find(k=>k!==q.answer)||q.answer;
 await p.locator('#v10EditToggle').click();await p.locator(`[data-v10="editQuestion"][data-qid="${q.id}"]`).click();
 await p.locator('#v10QForm [name="answer"]').fill('Z');await p.locator('#v10QForm [type="submit"]').click();assert.ok(await p.locator('#v10QForm [role="alert"]').innerText());
 await p.locator('#v10QForm [name="answer"]').fill(other);await p.locator('#v10QForm [name="analysis"]').fill('教师自定义讲评依据');await p.locator('#v10QForm [name="solve_steps"]').fill('本班先对照证据再判断。');await p.locator('#v10QForm [name="strategy"]').fill('教师自定义迁移方法');await p.locator('#v10QForm [type="submit"]').click();assert.ok(await p.locator('#v10Editor').isHidden());
 await p.reload();await p.waitForFunction(()=>window.__lessonReady);assert.equal(await p.evaluate(id=>qmap.get(id).q.answer,q.id),other);assert.equal(await p.evaluate(id=>qmap.get(id).q.answer_status,q.id),'teacher');assert.equal(await p.evaluate(id=>qmap.get(id).q.solve_steps.length,q.id),1);
 if(exam.features?.quick_answers!==false){await p.locator('#quickAnswers').click();assert.match(await p.locator(`[data-fast-reveal="${q.id}"]`).innerText(),/教师修订/);await p.locator('[data-close="quickAnswersDialog"]').click()}
 const record=await p.evaluate(()=>{saveSession();return JSON.parse(localStorage.getItem(saveKey))});await go(p,editSection);await p.locator('#v10EditToggle').click();await p.locator(`[data-v10="editQuestion"][data-qid="${q.id}"]`).click();await p.locator('[data-v10="restoreQuestion"]').click();assert.equal(await p.evaluate(id=>qmap.get(id).q.answer,q.id),q.answer);
 await p.evaluate(record=>restoreRecord(record),record);assert.equal(await p.evaluate(id=>qmap.get(id).q.answer,q.id),other);assert.equal(await p.evaluate(id=>qmap.get(id).q.strategy,q.id),'教师自定义迁移方法');ok('teacher-answer-edit-validation-persistence-restore-import');}
 for(const sect of exam.sections.filter(s=>!isListening(s))){await go(p,sect);if(exam.features?.deep_reading===false)assert.equal(await p.locator(`#section-${sect.id} [data-mode="deep"]`).count(),0);if(exam.features?.writing_transfer===false)assert.equal(await p.locator(`#section-${sect.id} [data-mode="writing"]`).count(),0)}
 if(exam.features?.culture_background){const sect=exam.sections.find(s=>s.culture_background?.length);if(sect){await go(p,sect);await p.locator(`#section-${sect.id} .culture-background summary`).click();await p.locator(`#section-${sect.id} [data-action="cultureLocate"]`).first().click();assert.ok(await p.evaluate(()=>Object.keys(state.marks).length>0));ok('culture-card-and-source-location')}}
 if(exam.features?.dictionary===false)assert.ok(await p.locator('#lookupForm').isHidden(),'dictionary off must hide the lookup form');
 if(exam.features?.annotations===false)assert.ok(await p.locator('#annotate').isHidden(),'annotations off must hide the annotation entry');
 if(exam.features?.quick_answers===false)assert.ok(await p.locator('#quickAnswers').isHidden(),'quick_answers off must hide the fast-answer entry');
 if(exam.features?.classroom_tools===false)assert.ok(await p.locator('#classroom').isHidden(),'classroom_tools off must hide the classroom entry');
 ok('selected-features-controls');
 // 深读与写作标签过去只验证"关闭时不出现"，从未打开验证内容；这里实际切页并断言渲染与定位。
 // .logic-card 同时用于篇章结构与逻辑信号词，所以期望值是两者之和。
 for(const sect of exam.sections.filter(s=>!isListening(s)&&s.writing_genre!=='application'&&(s.structure||[]).length)){
   if(exam.features?.deep_reading===false)continue;
   await go(p,sect);
   const tab=p.locator(`#section-${sect.id} [data-mode="deep"]`);
   if(!(await tab.count()))continue;
   await tab.click();
   const cards=p.locator(`#section-${sect.id} .deep-structure .logic-card`);
   await cards.first().waitFor({state:'visible'});
   assert.equal(await cards.count(),sect.structure.length+(sect.logic_steps||[]).length,'all structure and logic rows must render');
   assert.match(await cards.first().innerText(),new RegExp(sect.structure[0].title.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')));
   const sourcePid=sect.structure[0].paragraph_ids[0];
   await cards.first().locator('button').click();
   assert.ok(await p.evaluate(id=>Boolean(state.marks[id]),sourcePid),'structure row must locate its source paragraph');
 }
 ok('deep-reading-structure-renders-and-locates');
 for(const sect of exam.sections.filter(s=>!isListening(s)&&s.writing_genre!=='application'&&(s.writing_bank||[]).length)){
   if(exam.features?.writing_transfer===false)continue;
   await go(p,sect);
   const tab=p.locator(`#section-${sect.id} [data-mode="writing"]`);
   if(!(await tab.count()))continue;
   await tab.click();
   const cards=p.locator(`#section-${sect.id} .writing-bank-card`);
   await cards.first().waitFor({state:'visible'});
   assert.equal(await cards.count(),sect.writing_bank.length,'every writing-bank card must render');
   await cards.first().locator('[data-action="bankLocate"]').click();
   assert.ok(await p.evaluate(id=>Boolean(state.marks[id]),sect.writing_bank[0].paragraph_id),'writing-bank card must locate its source sentence');
 }
 ok('writing-transfer-tab-renders');
 // 逐段译文：默认收起，点击后才出现，且再次点击收起。
 for(const sect of exam.sections.filter(s=>!isListening(s)&&(s.paragraphs||[]).some(p=>p.translation))){
   await go(p,sect);
   const button=p.locator(`#section-${sect.id} [data-action="translate"]`).first();
   await button.waitFor({state:'visible'});
   const block=button.locator('xpath=../..').locator('.translation').first();
   assert.ok(await block.isHidden(),'paragraph translation must start hidden');
   await button.click();
   assert.ok(await block.isVisible(),'clicking 本段中译 must reveal the translation');
   assert.ok((await block.innerText()).trim().length>0,'a revealed translation must not be empty');
   await button.click();
   assert.ok(await block.isHidden(),'clicking again must collapse the translation');
 }
 ok('paragraph-translation-toggles');
 const listening=exam.sections.find(s=>isListening(s)&&s.audio);if(listening){for(const s of exam.sections.filter(s=>isListening(s)&&s.audio))await play(p,s);ok('listening-and-question-media-play-and-speed');}
 // 精听挖空：遮住的必须是转写原文里真实的词，揭示后才出现，并且开启期间不能泄漏答案。
 for(const sect of exam.sections.filter(s=>isListening(s)&&(s.blanks||[]).length)){
   const blank=sect.blanks[0];
   const word=sect.paragraphs.find(x=>x.id===blank.paragraph_id).text.slice(blank.start,blank.end);
   await go(p,sect);
   // 真正的泄漏顺序：先把解析与译文展开，再开启挖空。
   const question=sect.questions[0];let opened=false,translated=false;
   if(question&&await p.locator(`[data-action="answer"][data-qid="${question.id}"]`).count()){
     await p.locator(`[data-action="answer"][data-qid="${question.id}"]`).click();
     opened=await p.locator(`#q-${question.id} .analysis`).isVisible();
   }
   const translate=p.locator(`#section-${sect.id} [data-action="translate"]`).first();
   if(await translate.count()){
     const block=translate.locator('xpath=../..').locator('.translation').first();
     if(await block.isHidden())await translate.click();
     translated=await block.isVisible();
   }
   const panel=p.locator(`#section-${sect.id} details:has(.listening-gaps)`).first();
   if(!(await panel.evaluate(d=>d.open)))await panel.locator('summary').click();
   await p.locator(`#section-${sect.id} .listening-gaps`).check();
   if(opened)assert.ok(await p.locator(`#q-${question.id} .analysis`).isHidden(),'enabling dictation must collapse an already-open analysis');
   if(translated)assert.equal(await p.locator(`#section-${sect.id} .translation:not([hidden])`).count(),0,'enabling dictation must not leave a translation visible');
   const gap=p.locator(`#section-${sect.id} button.gap[data-kind="listen"]`).first();
   await gap.waitFor({state:'visible'});
   assert.notEqual((await gap.innerText()).trim(),word,'the blanked word must stay hidden before reveal');
   assert.match((await gap.innerText()).trim(),/^_+$/,'a hidden blank must render as a placeholder, not the answer');
   assert.ok(await p.evaluate(sid=>!ui.openAnswers.some(id=>qmap.get(id)?.s.id===sid),sect.id),'answers must not stay open while dictation is on');
   await gap.click();
   assert.equal((await gap.innerText()).trim(),word,'clicking a blank must reveal the real source word');
 }
 ok('listening-dictation-hides-and-reveals-real-words');
 for(const width of [1024,390]){await p.setViewportSize({width,height:900});assert.ok(await p.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+2));await go(p,exam.sections[0]);await quick(p)}ok('narrow-screen-navigation-and-dialogs');await ctx.close();
 if(listening&&Object.keys(exam._embedded_audio||{}).length){const x=await newPage('isolated');await play(x.p,listening);await x.ctx.close();ok('embedded-audio-with-external-audio-blocked')}
 if(stress){report.phase='stress';for(const mode of ['no-speech','bad-storage','no-storage','no-dialog','no-canvas','bad-scores']){report.phase='recovery-'+mode;const x=await newPage(mode);await go(x.p,exam.sections.at(-1));await quick(x.p);if(exam.features?.classroom_tools!==false){await x.p.locator('#classroom').click();assert.ok(await x.p.locator('#classDialog').isVisible());await x.p.locator('#minutes').fill('2');assert.ok(await x.p.locator('#classDialog').isVisible());await x.p.locator('[data-close="classDialog"]').click()}if(mode==='no-speech')await x.p.locator('#fullScreen').click();await x.ctx.close();ok('recovery-'+mode)}const x=await newPage('no-js');assert.ok(await x.p.locator('#bootNotice').isVisible());assert.match(await x.p.locator('#bootNotice').innerText(),/下载完整课件 ZIP/);await x.ctx.close();ok('script-disabled-static-opening-guide')}
 reconcile(exam);console.log('SUMMARY passed='+report.checks.length+' skipped='+report.skipped.length);assert.deepEqual(report.errors,[],'Browser runtime errors');report.status='passed';
}
main().catch(e=>{if(report.status!=='not_available')report.status='failed';report.errors.push(e.stack||String(e));console.error(e.message);process.exitCode=1}).finally(async()=>{clearTimeout(deadline);try{if(browser)await browser.close();if(server)await new Promise(r=>server.close(r))}finally{if(fs.existsSync(out))save()}});
