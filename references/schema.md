# exam.json 内容格式（整卷版）

UTF-8 JSON。内容字段为纯文本，模板统一转义。所有资源使用本地文件路径，构建器复制为相对路径。题号沿用原卷。

```json
{
  "title":"英语试卷讲评",
  "subtitle":"课堂讲评",
  "expected_question_ids":["21"],
  "sections":[{
    "id":"A", "kind":"reading", "title":"阅读 A", "expected_option_count":4,
    "paragraphs":[{"id":"A-p1","text":"The museum opens at nine.","translation":"博物馆九点开门。","underlines":["opens"]}],
    "questions":[{
      "id":"21","stem":"When does the museum open?",
      "options":{"A":"At eight.","B":"At nine.","C":"At ten.","D":"At eleven."},
      "answer":"B","answer_status":"sample","answer_source":"本文档原创格式示例",
      "question_type":"细节理解 · 时间信息",
      "type_note":"题干问开放时间，答案必须对应原文明确时间。",
      "solve_steps":["从题干提取museum和open。","找到opens at nine。","核对nine与选项B，排除时间提前或推迟的选项。"],
      "pitfall":"不要把到达时间与开放时间混淆。",
      "analysis":"opens at nine直接对应B。",
      "evidence":[{"paragraph_id":"A-p1","quote":"opens at nine"}],
      "distractors":{"A":"比原文提前一小时。","C":"比原文晚一小时。","D":"比原文晚两小时。"},
      "strategy":"先定位时间信息，再核对选项。"
    }],
    "structure":[{"title":"信息引入","paragraph_ids":["A-p1"],"analysis":"开头交代开放时间。"}],
    "vocabulary":[{
      "word":"opens","meaning":"v. 此处指开始营业","paragraph_id":"A-p1",
      "quote":"The museum opens at nine.","context":"这里强调每日营业时间。",
      "collocations":"open at +时间；opening hours","distinguish":"open是动词或形容词；此处是动词。",
      "question_ids":["21"],"teaching_prompt":"Which phrase tells you when it opens?",
      "transfer":"The library opens at eight."
    }],
    "sentences":[{
      "quote":"The museum opens at nine.","paragraph_id":"A-p1","backbone":"The museum opens.",
      "chunks":"主语 + 谓语 + 时间状语。","logic":"提供开放时间。",
      "translation":"博物馆九点开门。","teaching_prompt":"删去时间状语后，句子是否完整？"
    }]
  }]
}
```

## 完整性与题型

- kind: listening / reading / seven / cloze / grammar / writing。
- expected_question_ids在制作前按原卷盘点，构建时检查无漏题。expected_option_count按原卷指定，不能根据已经OCR出的错误选项数反推。常见听力3、阅读4、七选五7、完形4。
- paragraph.id全卷唯一。保留段落、标题、来源图表；paragraph.image、alt支持必要插图。underlines是原文中须保留的下划线词组。
- options为对象；无选项题用{}。answer可字符串或合理变体数组。answer_status为official / inferred / sample / unresolved；写作示例用sample。answer_source记录真实来源，推定不得冒称官方。
- 每题有analysis；客观题给精确evidence和每个错误选项的具体distractors。quote必须是对应段落的真实子串。
- 七选五用shared_options共用A—G；各题仍保留options以支持独立分析。
- 七选五、完形、语法原文用`{{36}}`等题号标记。点击跳题，显示该题答案后回填原文；重置再隐藏。

## 音频与精听

根full_audio为完整原音；每个listening section有独立audio。paragraph.speaker为W/M等。原文轮次按真实音频和答案文件核对。

section.blanks为`[{"paragraph_id":"L1-p1","start":19,"end":23,"question_ids":["1"],"purpose":"本空对应的答案依据或同义转述训练"}]`，用于听力精听。Python Unicode字符下标，右端不含，不重叠、不跨轮次，答案取原文切片。数组顺序决定逐空揭示顺序。切换挖空后，未揭示词不出现在可划选文本中；本段还有隐藏空时暂停显示该段译文。

听力evidence可附start/end，paragraph可附audio_start/audio_end，均是**分段文件局部秒数**。只在实际音频对齐足够可靠时提供；有不一致时保留文本定位及整段播放。不能用均分时间、字数比例、延伸部分匹配来伪造同步。播放速度支持0.5/0.75/1/1.25/1.5，音频互斥。

## 专业精讲、写作及参考

structure采用title / paragraph_ids / analysis，呈现左原文、右功能与逻辑。vocabulary、sentences字段见例；派生词尚未在填空原文中出现时，用source_paragraph指来源，quote保留空位，不能伪造词形出现。

写作section.teacher_model为独立课堂示例，teacher_model_word_count记录词数；questions.answer保留原答案范文，source_model_word_count单独计数；model_versions保存其他原答案示例。避免把超词数的原范文宣称为满足题目篇幅。

题目可有 reference 对象：book / printed_page / topic / note，仅用于保留已核对来源。课堂解析使用 knowledge：`{ "title":"本题用到的知识", "rule":"就地讲清规则", "explanation":"例句拆解与本题联系", "example":"独立教学例句" }`，不显示去教辅页码学习的指令。与本题相关的一般知识和书中直接收录本题是两回事。

## 词典

dictionary是词条键值表，字段meaning、phonetic、english、exchange、source。缺省时构建器注入随Skill分发的10,836条离线释义；公开包词库来自ECDICT（MIT），不是官方考纲或权威频次认证。罕见词先补充审校后释义。

legacy_dictionary为可选的用户自有词库、一词多义与考点笔记，公开包不附带创建者的私人旧词库；使用前核对来源和权限。模板支持显示搭配与辨析，过滤未经核实的“高频”结论和旧tip。上下文精讲优先于一般字典义。查词默认自动调用系统英语发音，可关；离线未收录的词默认尝试Wiktionary REST，Free Dictionary API为可选资源，失败后保留发音与Oxford外部链接。

## 展示规则

数据保持整卷完整，模板一次显示一个章节，题目区可浏览本节全部题目，也可选每次只看一题；解析默认只展开当前题。listening初始只显示题目；原文在“原文与精听”折叠栏，点解析或定位时展开。挖空为原文内的就地开关，启用后隐藏解析/正确答案颜色，题目和音频保留。取消独立课堂环节标签。右上角小型控件连接section.audio，0.5/0.75倍速保留。阅读、七选五、完形等在桌面左原文右题目，在手机原文在前；原文始终共用一份，译文在本段下独立展开。右栏仅有题目讲评、篇章精读、写作迁移；展开原文只改变栏宽，不另设页面。

## 连续阅读、来源与分层词汇

- `paragraph.role` 可为 `heading` / `caption`，分别渲染文章内标题/说明文字，无独立段落编号与中译按钮；缺省为正文。
- `section.source_groups` 为 `[{"title":"信息块", "paragraph_ids":["A-p2","A-p3"]}]`，按原卷顺序覆盖该节全部段落，分组不删除内容。
- `section.quick_words` 为 `[{"word":"called on","lemma":"call on","meaning":"拜访","note":"过去分词形式；与call at区分。","paragraph_id":"L6-p4","occurrences":1}]`。word必须是指定原文的实际词形，次数按本节全文词形统计；重点词汇继续用vocabulary，句子用sentences。
- `section.origin` 为 `{"exam_page":3,"page_image":"/path/page-03.png","publication_status":"未确认原始出版来源","links":[{"title":"出处或研究标题","url":"https://...","relation":"与试卷材料的关系和证据范围"}]}`。页码对应原PDF真实页序，page_image构建后复制至sources/。链接为实际核查的https/http地址，不把相关研究标为确定改编出处。

## 精读迁移与写作支架

- `logic_steps`: `[{"label":"转折后观点","paragraph_id":"A-p1","quote":"原文精确子串","explanation":"它如何组织论证及影响解题"}]`。点击原文高亮真实引文，禁止只标一个模板化转折标签。
- `inquiry`: `[{"question":"教师追问","paragraph_id":"A-p1","answer":"依据原文的讨论提示，区分事实和推断"}]`。
- `transfer_tasks`: `[{"title":"仿写任务","paragraph_id":"A-p1","source_quote":"原文精确子串","prompt":"具体可执行的表达任务","check":"自查标准"}]`。草稿由教师评价，不把开放表达当作唯一标准答案。
- 写作 `writing_steps`: `{ "task":"审题约束", "outline":["段落步骤"], "language":["表达支架"], "model_analysis":[{"quote":"teacher_model中的真实句子","analysis":"主干、成分及写作作用"}] }`。
- 新字段缺省可为空；需要精读功能时按实际材料编写。构建器检查引文、段落对应和写作句式例句。不能自动拼接泛用分析冒充本卷教研。
- `worksheet.html` 从同一份数据生成，章节按本卷实际数量生成。学生版不注入答案、干扰项解析、参考范文、译文或词汇释义；保留原文、选项、追问与练习空间。听力学生版只保留题目及记录位置。
- 课堂记录独立于exam.json，以本卷标题与version=5校验。支持导出后迁移本卷进度，不将输入作答覆盖官方答案。

## 逐题精讲与音频（v6）

- 每题 `question_type` 为具体题型，`type_note` 说明判断依据；`solve_steps` 至少三步，紧扣题干与原文；`pitfall` 是本题易错提醒。已有 `analysis/evidence/distractors/strategy` 保留。缺少字段不可将内容称为完整教研版。
- 听力题 `audio` 为真实导出的本地 MP3，`audio_context` 为 `{ "text_id":"L6", "start":11.43, "end":26.56, "selection_reason":"保留关系推断所需上下文" }`。start/end 相对 Text 片段，独立 q.audio 的播放从 0 开始；构建器复制到 audio/Q6.mp3 等路径并核对时长。首五题若本段只有一题，可保留该Text全部。
- `blanks[].question_ids/purpose` 说明挖空与本题的联系；`listening_focus` 是对老师可见的简短练习目标，不直接写答案。
- `writing_genre` 为 application / continuation。application 不显示阅读或双语标签，continuation 保留英文原文阅读与双语。
- `writing_bank`：`[{"paragraph_id":"cloze-p1","quote":"原文精确子串，可含{{41}}空位","category":"动作与情绪","why":"具体表达效果","frame":"可复用句式","scene":"适用写作情境","example":"明确标注的教学改写","task":"学生迁移练习","check":"学生自查标准"}]`。检查真实原句；补全空位来自官方答案，不伪造原卷文本。写作积累与结构追问在右侧同一层标签切换显示，学生草稿独立保存。
- 当前六个浅色主题：`paper`（青绿）、`amethyst`（紫曜）、`mist`（雾蓝）、`sand`（暖杏）、`rose`（豆沙）、`pearl`（月白）；旧深色或未知值回到青绿。课堂记录仍兼容 version=5。

## 统一阅读工作区（v7）

内容数据格式不变。UI记录的 `layout` 使用 split / deep / writing 对应题目讲评、篇章精读、写作迁移；`readerWide` 为各节布尔值，独立记录是否暂时收起右栏。旧记录 read 迁移为 split + readerWide，parallel 迁移为 split；已展开的段落译文保留。旧 version=5 课堂记录继续可导入。

译文只生成在原段落下，不再生成 translation-pane；删除全局双语入口、重复完整阅读页和二级迁移标签。点击原文空位仍能返回对应题目，自动恢复左右栏；普通右栏切换保留原文滚动位置。原文不因布局切换被重新创建。

## 句间关系可视化（七选五）

每题可提供 `logic_links` 数组，只用已经核实的关系。每组示例：
```json
{"color":"amber","label":"回指愿望","explanation":"this pursuit 概括上文的创作追求。","endpoints":[{"paragraph_id":"S-p1","quote":"long to become social media creators"},{"option":"B","quote":"this pursuit"}]}
```
颜色为amber/violet/teal/blue；每组至少两个端点，并包含原文端点和选项端点。quote必须逐字存在，不能用释义代替可定位的引文。模板统一生成配色和编号。“显示线索”是显性教学提示，默认关闭。选项排除、备选库选择、解析标签及Canvas笔迹属于课堂记录ui字段，不修改exam.json里的标准答案。
