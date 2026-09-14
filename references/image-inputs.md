# 只有图片时怎么办（图片版试卷 / 答案 / 听力原文）

老师完全可能**没有 PDF**：手机拍的试卷、截图拼成的答案页、图片版听力原文或范文。这不是异常情况，必须和第 0 步一样先问清楚，并按下面的流程处理。**不要让老师先去转 PDF**；能不能读图由宿主决定，Skill 直接吃图片。

## 0. 先确认材料形态

开始前用一句话确认，不要默认老师有 PDF：

> 这次是只有图片，还是有 PDF/DOCX？答案和听力原文也分别是图片吗？

三种常见组合：① 卷面图片 + 图片答案；② 卷面图片 + 文字答案（如答案抄在聊天里）；③ 卷面 PDF + 图片答案。**分别记录**，不要用一处材料的情况推断另一处。

宿主读不了图时（见 [宿主能力与回退](host-compatibility.md)）：如实说明读不到内容，请老师提供文字或可读文件，**不得按常识补写题目**。

## 1. 把图片登记成可校验的页集合

```bash
python3 scripts/image_pages.py --dir WORK/试卷图片 --role paper   --out WORK/paper-inventory.json

（`--dir` 会**递归子目录**：若老师的文件夹里同时有"原图/""裁剪/"这类子目录，页集合会变成几倍且顺序穿插，
脚本会以 `images_from_multiple_dirs` 拦下并列出目录，请只指向其中一批，或按页序一次列全文件。
系统产生的 `.DS_Store`／`Thumbs.db`／`desktop.ini` 与非图片文件不会被算作页。）
python3 scripts/image_pages.py --dir WORK/答案图片 --role answers --out WORK/answer-inventory.json
```

在**台账所在目录**执行（清单里的路径相对当前目录）。它会按文件名自然排序（`page-2` 在 `page-10` 前），并逐页记录 `sha256`、字节数、宽高，输出集合指纹。同时报出：

| 代码 | 含义 |
| --- | --- |
| `duplicate_page` | 两页内容完全相同：同一页拍了两遍，或漏拍了别的页 |
| `possible_missing_page` | 文件名编号中间缺号，核对是否漏拍 |
| `empty_file` / `unreadable_image` | 空文件、损坏或被改名的图片 |
| `unsupported_file` | 混进了非图片（PDF/DOCX/HEIC 等） |
| `path_outside_base` | 图片不在台账目录之下，路径会解析不到 |

有报错时先处理再继续；`image_pages.py` 有问题就返回 1，不会假装通过。

## 2. 写进 source-ledger.json

一个图片来源 = 台账里的一条 `sources`，`path` 指向图片文件夹，并带上页清单：

```json
{"role":"answers","kind":"image_pages","path":"答案图片",
 "sha256":"<image_pages.py 输出的 source_sha256>",
 "pages":[{"index":1,"path":"答案图片/answer-1.png","sha256":"..."}]}
```

`role` 按实际用途区分：`paper`（卷面）、`answers`（答案）、`listening_text`（听力原文）、`writing_model`（范文）。

构建时会**逐页核对指纹**，并**重算集合指纹**：换页、重拍、漏页、调换顺序，都会以 `source_page_hash` 或 `source_pages_digest` 阻断，而不是照旧交付。

## 3. 逐页转录，题号独立盘点

按图片逐页整理原文、题号、选项、标点、下划线与表格；跨页题干要接上，双栏排版按栏顺序读。题号清单见 [内容数据格式](schema.md)：`scaffold.py` 生成的是机器草稿，必须**独立按图盘点**后把 `expected_question_ids_source` 改成 `checked`，否则构建会阻断——否则漏页/漏题会同时从两边消失。

## 4. 图片版答案：如实标成转录来源

图片答案没法用解析器逐字形核对，只能人读图转录。转录文本仍需过一遍解析器，把指纹绑到**那组图片**：

```bash
python3 scripts/answers.py extract WORK/答案转录.txt \
  --source-images WORK/answer-inventory.json --out WORK/answers.json
```

它会写入 `answer_source_kind=image_transcription`、`answer_source_sha256=<图片集合指纹>`、`answer_source_pages`，并保留转录文本的指纹。构建时：

- 台账必须登记同一组答案图片（`role=answers`），否则 `answer_key_not_registered` 阻断；
- 因为来源是转录，构建会**固定报出一条待核项** `answer_key_image_transcription`：必须逐题与答案原图比对，构建通过**不代表**答案已被机器核对。

绝不把转录结果说成"脚本解析的原件答案"。读不清的行留在 `unparsed` 里，逐行回原图确认；同一题出现两个答案时保留冲突，不自行取舍后仍标 `official`。

## 4.4 跨页照片（拍翻开的书：一张图两页）

老师最常见的手持拍法是**翻开的书**：一张照片里并排两页（横版）。这时"1 张 = 1 页"会让漏页与页序核对失真，必须显式声明：

```bash
# 全部都是跨页照片
python3 scripts/image_pages.py --dir WORK/试卷图片 --role paper --spread --out WORK/paper-inventory.json
# 只有部分是（其余一页一张）
python3 scripts/image_pages.py --dir WORK/试卷图片 --role paper --spread-files 卷面-01.jpg,卷面-02.jpg --out WORK/paper-inventory.json
```

清单会写 `layout=spread`、`pages_per_image`、`logical_pages`（张数 × 每张页数），并逐张标 `spread`/`pages_in_image`；把竖版图片误标成跨页会给一条 `spread_not_landscape` 提示。构建时 `quality_gate` 也会给一条不阻断的提醒，要求**左右页分别核对**题号与漏页。

`page_count` 始终是**图片张数**（交付与指纹以文件为准），`logical_pages` 才是真实页数——两者都要写进核对记录，不要只说其中一个。

## 4.5 图片选项（听句子选图 / 图表选项）

初中卷的「听说应用·第一节 听句子选图」、部分图表题，选项本身就是图片。处理方式：

1. 从卷面照片里把 A/B/C 三张小图**分别裁出来**（一张一张，不要整页塞进去）；
2. 在题目上写 `option_images`（字母 → 路径），`options` 里保留同样的字母（值可为空串），可另写 `option_alts` 作为图片说明；
3. 构建会把它们复制到 `assets/` 并计入媒体指纹，浏览器验收会检查每张图**真的加载出来**、并且仍然能点选；
4. 原卷页图照旧登记在 `section.origin.page_images`，两者互不替代。

课堂上的"带读与翻译"针对的是文字；图片选项没有可点的单词，这是正常的——不要在图片上强行叠文字。

## 5. 页图随课件一起交付

给节登记 `section.origin.exam_page` 与页图，构建会把页图复制到 `sources/` 随课件交付，老师上课可以随时对照原图：

- 一节占一页：`{"exam_page":3,"page_image":"试卷图片/page-3.png"}`
- **一节跨多页**（图片版试卷最常见：原文一页、题目一页）：`{"exam_page":3,"page_images":["试卷图片/page-3.png","试卷图片/page-4.png"]}`

`page_images` 按页序排列，会全部复制进 `sources/`、全部纳入交付验收指纹，并在课件“出处”弹窗**逐页显示**（多页时页码自 `exam_page` 起递增）。只给一页会让老师看不到另一页的原文或题目，所以跨页时不要只填第一页。

## 6. 图片材料必须过的检查

- **漏页 / 重号**：页清单编号连续、无重复指纹；题号连续且与原图一致。
- **裁切与完整**：题干、选项、表格、图注没有被裁掉；页边页码是否可见。
- **方向与清晰**：倒置、倾斜、反光、过暗导致认不清的字符，标注待核，不猜。
- **版本一致**：A 卷/B 卷、AB 卷答案不要混用；听力原文与音频、与题目版本一致。
- **手写批注**：原卷上的手写答案或批注不得当作印刷原文。
- **不可替代**：图片没有文本层，无法像 PDF 文本层那样校验；识别结果永远需要人工逐页核对。

## 7. 不能说的话

- 不把"我看到了图片文件名"说成"已读取内容"。
- 不把图片识别说成"已 OCR 全文并逐字校对"。
- 不因某一页读不清就删题或跳过整节。
- 不把图片版答案说成"机器解析的官方答案"。
- 不保证图片识别零错误；交付说明里要保留"逐页人工核对"这一项。
