# 先选范围，再生成

新任务先按 [教师选项](teacher-options.md) 完成课型和扩展功能两项选择，构建传入 `--plan generation-plan.json`。

安装 Skill 是准备文件，不能保证宿主自动弹出窗口。安装成功后的回复应发起一次范围询问；若宿主安装流程不能对话，则在首次调用时询问。已有明确范围时直接使用，不重复问。

推荐问题：**这次准备讲哪些内容？**

- 整卷讲评：生成已提供的全部题型。
- 指定板块：按**试卷自己的板块名**说，例如听说应用、语法选择、完形填空、阅读理解 A、配对阅读、短文填空、读写综合、读后续写；可多选。
- 精听：只处理指定听力 Text，默认展开原文与答案线索挖空，保留题目、整段和逐题录音。

使用宿主的交互式问题控件；没有控件就用一条普通消息让老师回复。没有回答时保留待选状态，不自动开始整卷。材料已齐时，可等待期间检查文件格式、题型目录和环境，不提前全文 OCR、ASR 或编写未选板块。选择“指定板块”但未说具体内容时，再按材料目录询问一次；保留原卷题号和整个 Text 的语境。

将选择写入 `generation-plan.json`，记录 `sections`（原卷章节 ID）、`mode`（lesson/intensive）、`profile`（默认 full）、材料路径和各阶段状态。快速档只有老师明确接受少做精读扩展时才选 quick；选少量板块保留完整基础讲评；可选扩展按老师明确选择生成。

## 执行与提速

1. 先用 PDF 文本层、DOCX 提取；只对缺字或扫描页 OCR。只深入读取选中板块和其答案。
2. 骨架按章保存，保留已核对的原文、答案和未完成清单。不要在对话里输出一份大 JSON 后再复制到文件。
3. 本次不含听力时不检查或安装 ASR、不读取完整录音、不生成切片。含听力时复用同一原音指纹对应的时间转写；纸质听力原文不等于带时间转写，仍需试听确认边界。
4. 每节按实际教学价值精选词句与迁移，避免所有单词都编成长词条。需要完整精读时再扩展。保持原文、题目、答案依据与干扰项辨析完整。
5. 已完成章节用 `parts.py` 局部更新，改文字不重切音频。同长度的新切点不能复用旧音频；缓存必须同时匹配原音指纹和起止时间。
6. `build-report.json` 记录 `timing`（prepare_audio / validate / quality_gate / answer_audit / render_and_write 各阶段秒数）与 `authoring_cost`（需编写字符数、逐字引文字符数、可改用 quote_ref 的预估节省）。Agent 另记识别、转写、编写解析和浏览器验收用时；没有这些分项数据，不把整卷慢归因于某个模型或承诺固定完成分钟数。

## 省 token 与积分

编写教学解析是唯一无法省掉的部分；能省的是重复读取、逐字抄写和返工。开始写之前先量一次：

```text
python3 scripts/cost.py WORK/exam.json --plan WORK/generation-plan.json
```

它给出本次要编写的字符数、逐字引文字符数，以及哪些长引文可以改成 `quote_ref`（按范围引用，由脚本回填）。按下面顺序做：

1. **只写选中的板块**：`--plan`、`scope.py` 或 `--sections` 先筛范围，未选章节不编写、不逐字读取。
2. **长引文一律用 quote_ref**：写完跑 `python3 scripts/quotes.py fill WORK/exam.json` 回填逐字引文。省下的正是逐字抄写与对不齐后的重试。
3. **先出可上课版**：材料大、时间紧时在教师确认计划中使用 `profile="quick"` 先交付能上课的完整讲评，再补 sentences/structure/writing_bank，最后更新计划为 `profile="full"` 并重新复核后重建。
4. **复用转写与切片**：同一原音指纹的带时间转写直接复用；重复构建只改文字，不重跑 OCR/ASR、不重切音频。
5. **分节写、局部改**：`parts.py split` 后每节一个文件，返工只重写一节，再 `merge` 合并；不要把整卷 JSON 贴回对话里改。
6. **一轮改完校验错误**：构建一次列出本节全部问题，每条中文并带实际值（真实词频、要求/实际选项数、引文与段落 ID），末尾给出下一步。按清单一次改完再重跑——每多一轮返工就多几分钟和一轮 token。
7. **别把同一段内容写两遍**：`python3 scripts/cost.py WORK/exam.json --duplicates` 会列出逐字重复的引文、跨节完全/近似的解析与重复词条，并给出可省字符；重复引文优先改成 `quote_ref` 由脚本回填。字面相似不等于教学上重复，删改前自己判断。
8. **控制课件体积**：默认 `--dictionary-scope lesson` 只为本篇出现的词内置离线释义（示例由 4.4MB 降到约 375KB）；课件要带到没有网络的教室、又希望任意生词都能离线查时，才用 `--dictionary-scope full`。录音很大时用 `--audio-mode folder` 并把音频文件夹一起交付。

`cost.py` 只估算编写负担，不是 token 计费，也不承诺模型速度；引文回填省抄写，不省教学判断。

已经有全卷数据时可直接筛选再构建：

```text
python3 scripts/scope.py WORK/exam.json --sections reading,cloze --out WORK/selected.json
python3 scripts/build.py WORK/selected.json OUTPUT --source-ledger WORK/source-ledger.json
python3 scripts/build.py WORK/exam.json OUTPUT --sections L6,L7 --mode intensive --source-ledger WORK/source-ledger.json
```

Windows 使用实际可执行的 `py -3` 或 `python`；macOS/Linux 可用 `python3`。未选章节不用先生成内容再删掉；上述筛选是已有数据的复用路径。台账保留原卷来源，质量门槛仅核对本次明确选择的章节，未知章节 ID 会报错。

## 音频交付

默认 `--audio-mode embedded`：原卷录音和切片真正嵌入 HTML，页面按当前章节加载。`audio/` 同时保留为可编辑备份。单独复制 HTML 时听力可用；原卷页图仍需要 sources/ 等目录，所以完整分享仍交付 ZIP。

录音很大或平台限制单个附件体积时，老师可选择 `--audio-mode folder`，HTML 更小，但必须带上音频文件夹。不能为了加速悄悄省略音频或把外部路径描述成内嵌。

验收时将生成的 index.html 复制到一个不含 audio/ 的临时文件夹，通过浏览器检查内嵌音频的加载、实际播放和定位。依次抽查整段、逐题、0.5/0.75 倍速和切换章节；另检查全部媒体文件能解码。把“字节校验”“浏览器加载”“实际播放”“语义切点”分别记录，结构通过不能写成全部播放通过。
