# exam.json 内容格式（整卷版）

UTF-8 JSON。内容字段为纯文本，模板统一转义。所有资源使用本地文件路径，构建器复制为相对路径。题号沿用原卷。

## 先看这里：按本次选择决定要写哪些字段

这张表就是"最少要写对的东西"。**老师没勾选的扩展不用写、也不会显示入口**，所以后面用不到的节可以跳过，不必通读。

- **卷级（都要）**：`title`、`sections`、`expected_question_ids`（按原卷独立盘点，含跨页跨栏）、`full_score` / `exam_minutes`（卷首有就写）。
- **每节（都要）**：`id`、`kind`（**试卷自己的题型名**）、`title`、`paragraphs`、`questions`；有原卷页码就写 `origin`；分值取自试卷标题就写 `score_total` / `score_per_question`。
- **每题（都要）**：`id`、`stem`、`options`、`answer`、`answer_status`（`official`/`inferred`/`sample`/`unresolved`）、`answer_source`（出处或推断依据）、`question_type`、`type_note`、`solve_steps`（**≥3 步**）、`pitfall`、`analysis`、`strategy`；客观题还要 `evidence`（真实原文子句）与 `distractors`（每个干扰项都写）。

按"本节实际有的材料 + 老师勾选的功能"追加：

| 触发条件 | 必写字段 | 详解在哪一节 |
| --- | --- | --- |
| 本节有原文（阅读/完形/七选五/短文填空…） | `quick_words`、`vocabulary`（快速档也至少要一项）、`paragraphs[].translation`（证据段必须有译文） | 连续阅读、来源与分层词汇 |
| 老师勾了篇章精读 | `structure`（含真实 `quote` 与 `paragraph_ids`） | 完整性与题型、精读迁移与写作支架 |
| 老师勾了写作迁移 | `writing_bank`（真实原句 + 表达效果/句式/情境/教学改写/自查） | 逐题精讲与音频（v6） |
| 老师勾了文化背景 | `culture_background`（每项 `title`/`paragraph_id`/逐字 `quote`/`explanation`/`reading_connection`/`teaching_note`/`sources` 含 `title`+`url`+`supports`）或 `culture_note` 说明本篇不必写 | 本篇文化背景规范 |
| 这节有听力 | `blanks`（挖空必须落在转写原文里真实完整的词上，带 `question_ids` 与 `purpose`）、`audio` 或 `audio_note`；逐题音频另写 `audio_context.selection_reason` | 音频与精听、逐题精讲与音频（v6） |
| 题目是七选五 | 每题 `logic_links`（`color`/`label`/`explanation` + 至少一对原文与选项端点引文） | 句间关系可视化（七选五） |
| 题目是语法填空 | 每题 `knowledge`（`title`/`rule`/`example`/`explanation` 四栏） | 逐题精讲与音频（v6） |
| 选项是图片（听句子选图、图表选项） | 每题 `option_images`（字母必须与 `options` 一一对应）+ 可选 `option_alts` | 完整性与题型 |
| 要给逐句译文 | `paragraph.sentence_translations`（句数与固定切句结果一致；未译写空串并进待核项） | 完整性与题型 |
| 长引文不想手抄 | 写 `quote_ref` 字符范围，再跑 `scripts/quotes.py fill` 回填逐字引文 | 分节写作与引用（提速用） |

`--profile quick` 只要求"讲课必需"：逐题解析、答案与出处、听力音频或说明与挖空、证据段译文、至少一层词句；`sentences`/`structure`/`writing_bank` 可以后补，报告里记 `missing_enrichment`。用快速档时必须告诉老师"这是快速档、还缺哪些精读内容"。

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
    "structure":[{"title":"信息引入","paragraph_ids":["A-p1"],"quote":"The museum opens at nine.","analysis":"开头交代开放时间。"}],
    "quick_words":[{"word":"opens","meaning":"v. 开放、营业","paragraph_id":"A-p1","occurrences":1,"note":"本文指博物馆开门时间。"}],
    "vocabulary":[{
      "word":"opens","meaning":"v. 此处指开始营业","paragraph_id":"A-p1",
      "quote":"The museum opens at nine.","context":"这里强调每日营业时间。",
      "collocations":"open at +时间；opening hours","distinguish":"open是动词或形容词；此处是动词。",
      "question_ids":["21"],"teaching_prompt":"Which phrase tells you when it opens?",
      "transfer":"The library opens at eight."
    }],
    "writing_bank":[{
      "paragraph_id":"A-p1","quote":"The museum opens at nine.","category":"时间信息表达",
      "why":"用一般现在时陈述固定开放时间，简洁明确。","frame":"... opens at + 时间",
      "scene":"介绍场馆、商店或机构的营业时间","example":"教学改写：The shop opens at ten.",
      "task":"用 opens at 写一句介绍你常去的地方的开放时间。","check":"时态为一般现在时，时间是完整表达。"
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

章节结构由试卷决定：试卷有哪几个板块、什么顺序、叫什么名字、每节讲什么，都按试卷来。

- `section.kind`：**试卷自己的题型名**，自由填写，不再限定六种。例如 `reading`、`听力理解`、`任务型阅读`、`词汇运用`、`读后续写`、`概要写作`。构建只要求它是非空字符串。
- `section.kind_preset`（可选，六选一：`listening` / `reading` / `seven` / `cloze` / `grammar` / `writing`）：只决定"用哪套呈现方式与栏目要求"，不改变题型名。**缺省时**按 kind 是否命中常见题型名（预设名与常见中英文题型名，如 `读后续写`→writing、`任务型阅读`→reading）自动判断，再按本节实际内容推断（有本节音频/逐题音频/挖空→听力，有范文或写作步骤→写作）。写错了只影响呈现与栏目要求，不影响题型名。
- `section.group`（可选）：导航分组键，同一组的章节折叠成一个菜单；缺省等于 `kind`。
- `section.group_title`（可选）：导航里显示的板块名；缺省时**优先用试卷自己的 kind 原文**，只有 kind 是六个预设名时才显示"听力/阅读/七选五/完形/语法填空/写作"。
- `section.score_total` / `section.score_per_question`（可选，正数）：试卷标题里的分值，如「二、语法选择(本大题共10小题，每小题1分，共10分)」→ `score_per_question=1`、`score_total=10`。页面在每节标题显示「本大题 10 分 · 每小题 1 分」。注意「本题15分」这类整题分值只写 `score_total`，不要写成每小题。
- 根级 `full_score` / `exam_minutes`（可选，正数）：卷首说明里的满分与考试用时，页面在标题下显示。
- `section.short`（可选）：导航小标签（如 `Text 1`、`A`、`应用文`）；缺省按预设启发式取。
- **导航顺序 = 试卷里 sections 的顺序**（分组按各组首次出现的位置排列），不再按固定题型顺序重排。题号必须随试卷顺序递增（`quality_gate` 的 `question_order` 会拦下不递增的排列）。
- 每节要求哪些栏目由"这节实际有什么材料 + 老师选了什么功能"决定，不由题型名决定：有音频→精听挖空；有原文→生词速查与重点词汇；两段及以上原文且非听力→句子精讲（开精读再加篇章结构，开写作迁移再加写作积累）；有范文或写作步骤→写作步骤与范文；写作节不要求段落译文。
- expected_question_ids在制作前按原卷盘点，构建时检查无漏题。`scaffold.py` 生成骨架时会写入 `expected_question_ids_source: "machine_draft"`：这份清单来自同一份解析结果，漏掉的题会同时从 expected 里消失，所以**“无漏题”检查此时不成立**。按原卷（含跨页、跨栏）独立盘点题号后，把该字段改成 `checked` 或删除；只要还是 `machine_draft`，构建直接阻断。expected_option_count按原卷指定，不能根据已经OCR出的错误选项数反推；常见值只是参考（听力3、阅读4、七选五7、完形4），以试卷实际为准。**原卷没有的题型不生成**：不要因为模板里常见「听力/阅读/完形/语法填空」就给一份没有听力的卷子补听力。
- `paragraph.sentence_translations`（可选）：**逐句译文**，每句一条、顺序与原文一致。句数以固定切句规则为准（句末 `.` `!` `?` `…` 之后是空白或行尾才算一句；`Mr.`/`3.5` 不会被切开）。页面上有一个「逐句译文」开关：打开后原文逐句显示、每句下面给出中文；点某一句则只显示那一句的译文（再点恢复整段逐句）；未翻译的句子在页面上写「本句未译」，与构建报告里的待核项一致。精听挖空未揭示时，逐句译文与段落译文一样会被隐藏，避免泄漏答案。条数与切出的句数不一致会**阻断**（错位的译文比没有译文更糟）；未翻译的句子写空字符串占位，构建会把它列进待核项；整条译文必须是中文，抄英文原句会被拒绝。
- paragraph.id全卷唯一。保留段落、标题、来源图表；paragraph.image、alt支持必要插图。underlines是原文中须保留的下划线词组。
- options为对象；无选项题用{}。**图片选项**（听句子选图、图表选项）另写 `option_images`：`{"A":"assets/q1-a.png","B":"...","C":"..."}`，字母必须与 options 的字母一一对应，图片选项在 options 里可以留空字符串；`option_alts` 写每张图的文字说明（无障碍朗读与打印用）。文字选项与图片选项可以混用。构建会把图片复制进 `assets/` 并纳入媒体指纹（浏览器验收与打包用的是同一组指纹）。**不要用「图A/图B」这类文字描述代替真实图片**：那就等于没给学生看图。answer可字符串或合理变体数组（页面按 `answer.includes(选项字母)` 判定，所以数组表示"这几个写法都算对"，显示成 `A / B`）。**多字母组合**（如 `"AB"`，答案原件里多选题就这么写）也接受：核对时按字母集合与原件比较（`"AB"` 与 `["A","B"]` 视为同一次多选），但同时记入 `answer_multi_letters` 待核——页面会把 A、B **各自**判为正确，真正的"必须同时选对两个"目前没有学生端判分。answer_status为official / inferred / sample / unresolved；写作示例用sample。answer_source记录真实来源，推定不得冒称官方。
- 每题有analysis；客观题给精确evidence和每个错误选项的具体distractors。quote必须是对应段落的真实子串。
- 七选五用shared_options共用A—G；各题仍保留options以支持独立分析。
- 七选五、完形、语法原文用`{{36}}`等题号标记。点击跳题，显示该题答案后回填原文；重置再隐藏。

## 音频与精听

根full_audio为完整原音；每个listening section有独立audio。paragraph.speaker为W/M等。原文轮次按真实音频和答案文件核对。

音频路径通常不用手写：`build.py --audio-bundle WORK_AUDIO`（或自动识别 audio-work/audio-out）会按 section.id 与题号从切段清单注入 `full_audio`、`section.audio`、`section.audio_duration`、`section.audio_alignment`、`question.audio`、`question.audio_duration`、`question.audio_context`。手写路径仍然支持，用于老师直接交来一段音频的情况。

- `section.audio_scope`：`text`（本 Text 分段音频）或 `full_paper`（整卷原音，未分段）。整卷档页面标签为“整卷原音（未分段）”。
- `section.audio_note`：确实没有音频时写明缺项原因，页面显示该说明；既没有 audio 也没有 audio_note 会被构建阻断。
- `section.audio_alignment`：`{mode, boundary, full_start, full_end, opening_quote, closing_quote, transcript_file, transcript_sha256}`。`boundary` 为 `verified`（切点已逐段试听核对）或 `auto_silence`（静音自动分段；页面标“边界待核对”，qa-report.md 必须逐段记录试听结果，`scripts/qa_report.py init OUTPUT` 会按这些段落生成待填条目，空着会被 `check` 与打包拒绝）；整卷原音未分段时由 `audio_wiring` 写 `not_split`，页面靠 `mode=unsegmented` 标“整卷原音（未分段）”。**`boundary` 缺失或取值不认识会被构建阻断**（`audio_alignment_boundary_missing`）——页面只在 `auto_silence`/未分段时标“边界待核对”，不写这个字段会让页面看起来像已核对；工具也不再替清单补默认值。
- `question.audio` 可选：整卷档或未做逐题裁剪时不填，页面只显示该 Text 的播放器；填了就必须有 `audio_context.selection_reason`。

section.blanks为`[{"paragraph_id":"L1-p1","start":19,"end":23,"question_ids":["1"],"purpose":"本空对应的答案依据或同义转述训练"}]`，用于听力精听。Python Unicode字符下标，右端不含，不重叠、不跨轮次，答案取原文切片。数组顺序决定逐空揭示顺序。切换挖空后，未揭示词不出现在可划选文本中；本段还有隐藏空时暂停显示该段译文。挖空必须落在转写原文里真实、完整的词上：不得遮空白或纯标点，也不得把单词截断；构建会拒绝空切片、半词与越界，避免"遮住关键词"变成随意划范围。

答案侧由 `answers.json` 承担：`scripts/answers.py extract 答案原件 --out answers.json` 生成 `{"answer_source","answer_source_sha256","answers":{"21":"A",...},"unparsed":[...]}`，构建与 quality_gate 会拿它逐题比对 official 答案；解析表缺题或与成品不一致即阻断。解析器同时支持**字母答案与语法填空的单词/短语答案**（`56. which`、`57、has been`、`59. to make`），变体写法 `which/that` 或 `which (that)` 取第一个变体作为主答案；以问号结尾的题干式文本不会被误读成答案。

听力evidence可附start/end，paragraph可附audio_start/audio_end，均是**分段文件局部秒数**。只在实际音频对齐足够可靠时提供；有不一致时保留文本定位及整段播放。不能用均分时间、字数比例、延伸部分匹配来伪造同步。播放速度支持0.5/0.75/1/1.25/1.5，音频互斥。

## 专业精讲、写作及参考

structure采用title / paragraph_ids / analysis / quote，呈现左原文、右功能与逻辑；paragraph_ids不能为空，quote必须是对应段落的真实子串，用来支撑该结构判断，不能只写概括结论。vocabulary必须有context（本篇语境义）与quote（该词在原文中的真实所在句），且quote要包含该词形；派生词尚未在填空原文中出现时，用source_paragraph指来源，quote保留空位，不能伪造词形出现。sentences的quote须为原段真实子串，并填写backbone / chunks / logic / translation。以上由 `scripts/grounding.py` 强制，缺少真实依据会阻断构建。此外，同一节内不同题目的 analysis / pitfall / type_note / strategy 以及整组 solve_steps 不得完全重复，错误选项的辨析不得为空或彼此相同，占位或模板标记（TODO、待补充、此处省略等）也会阻断：这些都属于套话，不是针对本题材料的讲解。

写作section.teacher_model为独立课堂示例，teacher_model_word_count记录词数；questions.answer保留原答案范文，source_model_word_count单独计数；model_versions保存其他原答案示例。避免把超词数的原范文宣称为满足题目篇幅。

题目可有 reference 对象：book / printed_page / topic / note，仅用于保留已核对来源。课堂解析使用 knowledge：`{ "title":"本题用到的知识", "rule":"就地讲清规则", "explanation":"例句拆解与本题联系", "example":"独立教学例句" }`，不显示去教辅页码学习的指令。与本题相关的一般知识和书中直接收录本题是两回事。

## 词典

dictionary是词条键值表，字段meaning、phonetic、english、exchange、source。仅在查词功能开启时（features.dictionary=true）注入，且默认 `--dictionary-scope lesson` **只收录本篇文本中出现的词**：实测同一份示例由整本 10,836 条降到本篇 265 条，HTML 由约 4.2MB 降到约 376KB（1.0.79 实测）。代价是查**不在本篇**的词会走在线词典、离线时不可用；需要任意词都能离线查时用 `--dictionary-scope full`（内置整本，体积回到 4MB 级）。关闭查词时连根字段一起移除（约 255KB）。构建报告会写明实际范围与条数。公开包词库来自ECDICT（MIT），不是官方考纲或权威频次认证。罕见词先补充审校后释义。

legacy_dictionary为可选的用户自有词库、一词多义与考点笔记，公开包不附带创建者的私人旧词库；使用前核对来源和权限。模板支持显示搭配与辨析，过滤未经核实的“高频”结论和旧tip。上下文精讲优先于一般字典义。查词默认自动调用系统英语发音，可关；离线未收录的词默认尝试Wiktionary REST，Free Dictionary API为可选资源，失败后保留发音与Oxford外部链接。

## 展示规则

数据保持整卷完整，模板一次显示一个章节，题目区可浏览本节全部题目，也可选每次只看一题；解析默认只展开当前题。listening初始只显示题目；原文在“原文与精听”折叠栏，点解析或定位时展开。挖空为原文内的就地开关，启用后隐藏解析/正确答案颜色，题目和音频保留。取消独立课堂环节标签。右上角小型控件连接section.audio，0.5/0.75倍速保留。阅读、七选五、完形等在桌面左原文右题目，在手机原文在前；原文始终共用一份，译文在本段下独立展开。右栏仅有题目讲评、篇章精读、写作迁移；展开原文只改变栏宽，不另设页面。

## 分节写作与引用（提速用）

整卷 JSON 太大时不必一口气写完，也不需要手抄长引文：

- `scripts/parts.py split WORK/exam.json --out WORK/parts` 拆出每节一个文件（`_meta.json` 记录全卷字段与节顺序）；`parts.py check WORK/parts` 做**合并前体检**——只拦"合并会出事"的情况（题号跨节重复或缺失、没写 kind、某节还没有小题），**没有原文段落只作提示**（配对阅读、书面表达、纯题目节本来就没有原文，不要为此改数据）；`parts.py merge WORK/parts --out WORK/exam.json` 合回整卷（保留 exam.json 里的全卷级字段如 dictionary、full_audio）。合并前请确认每节文件里的 `id` 与文件名一致。
- 引文可以只写范围：`{"paragraph_id":"A-p2","quote_ref":[120,158]}`，或写作迁移用 `source_quote_ref`；`scripts/quotes.py fill WORK/exam.json` 会把范围替换成逐字引文（原地改写，可 `--out` 另存）。`scripts/quotes.py check WORK/exam.json` 不构建也能一次性列出所有对不上原文的引文。字符下标按 Python 规则，右端不含。
- 构建有 `--profile quick|full`：quick 只要求讲课必需项，精读项（sentences/structure/writing_bank）可缺，报告里记 `missing_enrichment`。

## 连续阅读、来源与分层词汇

- `paragraph.role` 可为 `heading` / `caption`，分别渲染文章内标题/说明文字，无独立段落编号与中译按钮；缺省为正文。
- `section.source_groups` 为 `[{"title":"信息块", "paragraph_ids":["A-p2","A-p3"]}]`，按原卷顺序覆盖该节全部段落，分组不删除内容。
- `section.quick_words` 为 `[{"word":"called on","lemma":"call on","meaning":"拜访","note":"过去分词形式；与call at区分。","paragraph_id":"L6-p4","occurrences":1}]`。word必须是指定原文的实际词形，次数按本节全文词形统计；重点词汇继续用vocabulary，句子用sentences。
- `section.origin` 为 `{"exam_page":3,"page_image":"/path/page-03.png","publication_status":"未确认原始出版来源","links":[{"title":"出处或研究标题","url":"https://...","relation":"与试卷材料的关系和证据范围"}]}`。页码对应原PDF真实页序，page_image构建后复制至sources/。**一节跨多页时**用 `page_images`（按页序的路径数组，与 `page_image` 可并存）：两者都会被复制到 `sources/`、纳入交付指纹，并在课件“出处”弹窗**逐页显示**，多页时页码自 `exam_page` 起递增。链接为实际核查的https/http地址，不把相关研究标为确定改编出处。

## 精读迁移与写作支架

- `logic_steps`: `[{"label":"转折后观点","paragraph_id":"A-p1","quote":"原文精确子串","explanation":"它如何组织论证及影响解题"}]`。点击原文高亮真实引文，禁止只标一个模板化转折标签。
- `inquiry`: `[{"question":"教师追问","paragraph_id":"A-p1","answer":"依据原文的讨论提示，区分事实和推断"}]`。
- `transfer_tasks`: `[{"title":"仿写任务","paragraph_id":"A-p1","source_quote":"原文精确子串","prompt":"具体可执行的表达任务","check":"自查标准"}]`。草稿由教师评价，不把开放表达当作唯一标准答案。
- 写作 `writing_steps`: `{ "task":"审题约束", "outline":["段落步骤"], "language":["表达支架"], "model_analysis":[{"quote":"teacher_model中的真实句子","analysis":"主干、成分及写作作用"}] }`。
- 新字段缺省可为空；需要精读功能时按实际材料编写。构建器检查引文、段落对应和写作句式例句。不能自动拼接泛用分析冒充本卷教研。
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

## 可选功能（1.0.14）

根字段 features 共七项：annotations、dictionary、classroom_tools、quick_answers、writing_transfer、deep_reading、culture_background，值为布尔。新生成使用 --plan 引入教师选择；旧数据不带字段时兼容原功能。annotations 控制画笔与原文文字批注，dictionary 控制输入查词、点击查词及划选查词；关闭扩展不删除原件、答案溯源、基本讲解、播放、备课编辑与记录导出。文化背景的数据结构与计划示例见 [教师选项](teacher-options.md)。关闭写作迁移/篇章精读时不要求对应 writing_bank/structure；逐题 strategy 方法迁移仍为基础解析，不受写作迁移开关影响。
