# 原件核对与交付门槛（1.2.0）

先读原件，再写教学解析。source-ledger.json 是识别阶段的源材料台账，不是从已生成的 exam.json 反向复制的“答案证明”。必须在编写解析前建立；修订它时重新打开对应原件核对并记录原因。结构通过、模板通过、功能字段存在均不能代替此项。

## 1. 扫描材料必须真正读到

PDF提取结果只有空白/换页符时，渲染页面并视觉识别/OCR；不能在空answer.txt上继续猜官方答案。答案页的连续字母组按题号逐个登记，复核跨行、跨题型的起止。每题答案记录来源页/行；which/that等允许变体全部保留。答案相冲突时标记待核，不能自行改成推理答案并仍写official。

先建立独立台账，原始材料路径相对台账，SHA256由实际文件计算。下面展示字段结构，内容必须来自实际原件：

```json
{
  "sources":[{"role":"paper","path":"paper.pdf","sha256":"实际SHA256"},{"role":"answers","path":"answers.pdf","sha256":"实际SHA256"}],
  "sections":[{
    "id":"A","kind":"reading",
    "paragraphs":[{"id":"A-p1","text":"原文第一段逐字文本"}],
    "questions":[{"id":"21","stem":"原卷题干","options":{"A":"原选项","B":"原选项"},"answer":"A","answer_status":"official","answer_reference":"answers.pdf 第1页，21题"}]
  }]
}
```

- sections按原卷出现顺序，题号自然排序，不用字典字符串排序产生L1、L10、L2。
- paragraphs保留真实段落、标题和写作题目要求；题目空位规范为{{题号}}。去除页眉水印不改变正文。不得为了满足证据引用而改原文。
- 教学范文不能混入原卷paragraphs；新增范文放teacher_model，原答案范文放对应答案/版本字段。续写所给段首句和词数要求属于原题，必须保留。
- 表格、价签等可为一个有明确role的块；正文不能把所有段落塞进一个含多次换行的paragraph。
- 给“修复引文不存在”的错误时，回原件找引文并修改派生解析。不能改原题以凑校验。

## 2. 音频必须对应内容

静音点只能产生候选。10段音频、31个文件和verified=true不证明正确。必须读完整原音带时间转写，对照题号、场景、首句、末句，去除试音/说明和相邻Text。每段对话按说话轮次分paragraph，标单一speaker。

在section保存：

```json
"audio_alignment":{
  "full_start":58.8,"full_end":74.2,
  "opening_quote":"该Text实际开头原句或连续短语",
  "closing_quote":"该Text实际结束原句或连续短语",
  "transcript_file":"audio-work/transcript.json",
  "transcript_sha256":"实际SHA256"
}
```

时间相对原始完整音频；转写文件必须由原音识别/对齐得到，保留segments的start/end/text，不能人工编造时间来配切点。首尾引句至少三个词，逐字来自本Text正文，并能在切点附近的转写里对应。转写同时记录source_audio_sha256，构建核对它确实来自本卷完整录音。ASR有错时回听局部核对再修订，并保留修订依据。

每题audio_context.start/end是Text内部相对时间。多题组不能给每道题复制同一个完整Text，再让老师快进；需要完整语境时可保留相互重叠区间，但逐题复听仍需题意选择。只有单题Text可合理复用整个短对话。所有多题组音频均等于整段时停止交付，重新对齐切割。

## 3. 逐题解析复核

先锁定参考答案，再独立判断原文依据。答案字母、对应选项文字、数值计算、三步解法、干扰项分析必须一致。发现官方答案与证据冲突时保留冲突，不强行替某选项编理由。不可统一用“与语境不符”充当全部干扰项分析；指出本题词义/搭配/逻辑依据。

篇章结构要说明每个功能段如何推进，不用“全文共N段，按顺序逐段精读”占位。多段文章不能只用一张全文概览替代结构分析。写作迁移必须有真实原句与有效示范。段落翻译不能因所有对话/篇章合并而变成一次全显。

## 4. 执行与交付

```bash
python3 scripts/quality_gate.py WORK/exam.json --source-ledger WORK/source-ledger.json --report WORK/quality-report.json
python3 scripts/build.py WORK/exam.json OUTPUT --source-ledger WORK/source-ledger.json
python3 scripts/verify_output.py OUTPUT
```

构建遇到门槛错误停止输出；按错误回到相应原件或音频修复，禁止删检查、改清单或硬写passed。构建会输出delivery_status=content_and_browser_review_required，表示仍需实际核对内容和浏览器，不是“已可上课”。

最后写qa-report.md，分别说明：原件识别与答案逐题比对、解析自洽复核、每段/每题首尾与题意核对、浏览器实际操作（包括回填/精听/词句/写作原题）。保留未完成项及具体位置。不把“网页打开了”写成所有交互验收。无可靠转写工具时先解决环境；不能降级为复制整段音频并宣布完成。

WorkBuddy可能在浏览器预览时向HTML添加data-page-node-id。新版模板核验仅允许这种页面标记和标签之间的空行变化；JavaScript、CSS、实际文字或功能改动仍不允许。报告要基于最终交付文件重跑，不能沿用预览前的旧文件指纹。

整份课件需带audio目录，HTML本身不是含全部音频的“单文件成品”。最终提供完整ZIP。source-ledger、原件、转写等工作证据可作为独立核对资料保留，不公开分发真实试卷或教辅给无关第三方。
