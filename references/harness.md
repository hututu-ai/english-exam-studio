# 生成主流程：第一步到第十三步（助手按这个顺序做）

1.0.119 起，先读 [新建、重建与内容复核](reliable-generation.md)。下列生成步骤必须携带本次绑定计划与复核记录；听力统一按 [WhisperX 链路](whisperx-workflow.md) 执行。

这一页是**路由**，不是第二份说明书：每一步只写"谁做 → 命令 → 判定标准 → 需要时再打开哪一份文档"。
细节一律留在被指向的文档里，避免两处说法漂移；这里出现的脚本与参数由 `check_docs.py` 每次发布前核对，
写错会直接失败。

**谁决定什么**：标 🧑 的步骤必须等老师回答，**不许替他默认**；标 🤖 的步骤由助手做完并拿出证据。
每一步的"判定标准"没达到，就不算这一步做完，也不要用后面的步骤盖过去。

**读什么、能跳过什么**（省额度就省在这里）：`SKILL.md` 是完整契约、`schema.md` 是本卷字段说明，两份加起来约 73KB，**不需要从头读到尾**。按下面这张表读。

**本次实际要读多少**（本页数字由 `scripts/check_docs.py` 按文件实时核对，写漂了会发布失败）：

| 情形 | 实际阅读量 | 说明 |
| --- | --- | --- |
| 只做听力（范围 A） | 约 26KB | 本页 10KB + [听力](listening.md) 7KB + `SKILL.md` 里两节听力 4KB + `schema.md` 顶部清单 6KB |
| 写教学内容（整卷） | 约 30KB 起 | 上一行换成"命中的那几节 `schema.md`"；没勾的功能节不读 |
| 全部文档（不应发生） | 约 222KB | `SKILL.md`+`schema.md` 73KB，`references/` 20 份共 149KB |


| 你要做的事 | 读这些 | 可以跳过 |
| --- | --- | --- |
| 走完整条流程 | 本页（约 10KB） | 其余先不读 |
| 写 `exam.json` | `schema.md` 顶部「先看这里：按本次选择决定要写哪些字段」+ **只读命中的那几节** | 没勾选功能对应的节（文化背景／写作迁移／篇章精读／听力／七选五／图片选项／逐句译文…） |
| 选范围与功能 | `teacher-options.md`，以及 `generation-planning.md` 里的省时几条 | 其余 |
| 收材料 | 只有图片才读 `image-inputs.md`；有音频才读 `listening.md`（没有转写再看 `listening-alternatives.md`），以及 `SKILL.md` 里两处标了「只在本次有听力时读这一节」的小节（`## 二、自动分段与精听`、`### 听力三档接入`） | 没有该材料就不读（原卷没有听力就别碰这几节） |
| 答案溯源与交付闸门 | `source-verification.md`、`runtime-delivery.md` | 交付前再读，不必开工就读 |
| 宿主受限／装不上 | `host-compatibility.md`，以及 `../docs/UPDATE.md` 的「网络受限」一节 | 本机正常时跳过 |
| 改模板或人工浏览器验收 | `regression.md` | 只写教学内容时不必读 |
| 想弄清界面/课堂行为（老师提问、改模板） | `SKILL.md` 里标了「模板行为说明」的那几节（约 15KB） | **写教学内容时全部可跳过** |

**只做听力（范围 A）**时，写作迁移、篇章精读、七选五、图片选项这些节都可以跳过；有音频才需要读听力与音频两节。

## 第一步到第十三步

### 第 1 步 🤖 安装与更新核对

- 命令：`python3 scripts/check_install.py`
- 判定：`status=complete`。缺模板、缺词典、哈希不符时，**不许说"已安装/已更新/可以生成"**。
- 详见 [更新说明](../docs/UPDATE.md)。

### 第 2 步 🤖 收材料并登记页集合

- 命令：`python3 scripts/image_pages.py --dir WORK/试卷图片 --role paper --out WORK/paper-inventory.json`（图片版答案换成 `--role answers`）
- 判定：顺序、漏页、重号、尺寸与指纹都登记下来，并**按页与原卷核对**；只有图片也能做，不要让老师先转 PDF。
- 详见 [图片版材料处理](image-inputs.md)。

### 第 3 步 🧑 问范围

- 没有命令：整卷讲评 / 指定板块 / **只要听力（就是"只要听力"这一档）**，一次问清。
- 判定：老师明确回答。未回答不得默认整卷，也不得默认全部功能。
- 详见 [范围与提速](generation-planning.md) 与 [教师选项](teacher-options.md)。

### 第 4 步 🧑 问功能（七项多选）

- 命令：`python3 scripts/plan.py menu` → `python3 scripts/plan.py make --confirmed --range A --features 1,3,5 --response "老师本次实际回答" --material paper=WORK/试卷.pdf --material answers=WORK/答案.docx --material audio=WORK/听力.mp3 --out WORK/generation-plan.json` → `python3 scripts/plan.py check WORK/generation-plan.json`
- 无听力时省略 audio 材料，已有材料按实际角色逐项登记。
- 判定：七项全部记录在案、`--confirmed` 已由老师确认、计划与老师回答一致。不能替老师勾选，也不能用单选冒充多选。
- 详见 [教师选项](teacher-options.md)。

### 第 5 步 🤖 环境与宿主自检

- 命令：仅本次有听力时 `python3 scripts/speech_runtime.py probe` 与 `python3 scripts/doctor.py --minutes 20` 与 `python3 scripts/host_probe.py --json`
- 无听力用 `python3 scripts/doctor.py --no-listening`，跳过语音探测与安装。
- 判定：能说清所选后端、宿主能不能跑 Python/浏览器；缺工具先按统一链路准备，仍受限时由老师选择后续方案，不静默降级。
- 详见 [无 Whisper 的听力路径](listening-alternatives.md) 与 [宿主能力与回退](host-compatibility.md)。

### 第 6 步 🤖 答案原件 → 答案表 → 台账

- 命令：`python3 scripts/answers.py extract WORK/答案原件.docx --out WORK/answers.json` → `python3 scripts/answers.py check WORK/answers.json --ledger WORK/source-ledger.json`
- 判定：官方答案都能追到答案原件的题号；对不上的进 `unparsed` 并逐行回原件确认。答案表由脚本解析，**不许手工录入**。
- 详见 [原件核对与交付门槛](source-verification.md)。

### 第 7 步 🤖 原卷 → 台账与骨架

- 命令：`python3 scripts/scaffold.py ledger --paper WORK/extracted.json --answers WORK/answers.json --out WORK/source-ledger.json` → `python3 scripts/scaffold.py exam --ledger WORK/source-ledger.json --out WORK/exam.json`
- 判定：题号**独立**按原卷盘点（含跨页、跨栏），`expected_question_ids_source` 不再是 `machine_draft`。
- 详见 [内容数据格式](schema.md)。

### 第 8 步 🤖 写教学内容（省额度在这一步）

- 命令：先 `python3 scripts/cost.py WORK/exam.json --plan WORK/generation-plan.json` 看清要写多少字；长引文写 `quote_ref`，写完 `python3 scripts/quotes.py fill WORK/exam.json` 回填。
- 判定：每节的栏目由"这节实际有的材料 + 老师选的功能"决定；原卷没有的题型不生成，原卷有的不删。
- 详见 [范围与提速](generation-planning.md) 与 [内容真实性](#三条贯穿全程的纪律)。

本次有听力时，此时执行 [统一 WhisperX 链路](whisperx-workflow.md)：短音频试跑或复用、查找题组、对齐、单题完整语境、试听与裁剪。音频清单通过后构建时传 `--audio-bundle WORK/audio-out`。

在本步写作后、构建前执行 `python3 scripts/teaching_review.py draft WORK/exam.json --plan WORK/generation-plan.json --out WORK/teaching-review.json`，另起一遍实际语义核对；清单不自动标通过。

### 第 9 步 🤖 构建

- 命令：`python3 scripts/build.py WORK/exam.json OUTPUT --source-ledger WORK/source-ledger.json --plan WORK/generation-plan.json --review WORK/teaching-review.json`
- 判定：`status=structural_checks_passed` 且没有阻塞项。报错会**一次列全并带实际值**——把清单一次改完再重跑，**不要改一条重建一次**（这是"生成特别久"最主要的来源）。
- 详见 [内容数据格式](schema.md)。

### 第 10 步 🤖 产物核验

- 命令：`python3 scripts/verify_output.py OUTPUT`
- 判定：`status=passed`（模板与内嵌数据一致）。它只证明"是同一套模板"，不证明答案与教学内容正确。
- 详见 [启动与交付验收](runtime-delivery.md)。

### 第 11 步 🤖 浏览器点击验收

- 命令：`node scripts/browser_check.cjs OUTPUT`
- 判定：`errors` 为空才算过；缺 Node/Playwright 时如实写 `not_available`，只交付"待验收版"，**不许手写通过**。
- 详见 [课堂功能回归清单](regression.md)。

### 第 12 步 🤖 人工复核清单

- 命令：`python3 scripts/qa_report.py init OUTPUT` → 逐条在 `结论：` 后写判断 → `python3 scripts/qa_report.py check OUTPUT`
- 判定：`status=ok`。空结论、`待填`、`TODO` 一类占位文字、缺章节都会被拒；结论必须是**人写下的实际判断**，不由脚本代填。
- 详见 [启动与交付验收](runtime-delivery.md)。

### 第 13 步 🤖 打包交付

- 命令：`python3 scripts/package_lesson.py OUTPUT 输出目录之外的.zip`
- 判定：`browser_checked` 才可交付；缺浏览器验收或人工复核清单时命令会拦（**两道门都要过**），确需先给老师时加 `--allow-unchecked`，并在交付说明里写明"待验收"。
- 详见 [启动与交付验收](runtime-delivery.md)；Windows 老师照 [Windows 验收清单](../docs/WINDOWS.md) 走同一条路。

## 三条贯穿全程的纪律

- **跳过 ≠ 通过**：`skipped`、`not_available`、`not_tested`、缺工具的步骤一律写成"未执行"，不能算完成，也不能在报告里写成通过。
- **一轮改完**：构建与核验的错误一次列全，改完再重跑；每多一轮就多花几分钟和一轮 token。
- **结构通过 ≠ 内容为真**：引文锚定只证明"有依据"；词义、篇章结构、文化背景、逐句译文与答案仍要人工逐条复核，结论写在 `qa-report.md`。

## 只要听力（范围 A）

第 3 步选 A、第 4 步按老师选的功能回答即可，**同一套 Skill，不需要另装"听力版"**：后面的步骤照走，
构建只保留听力节（`mode=intensive`），其他题型不生成、页面上也不出现入口。
