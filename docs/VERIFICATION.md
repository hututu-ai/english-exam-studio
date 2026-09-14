# 1.0.116 产出核验的交付判据补反向验证（并修掉两处"漏英文报错"）

## 本次实际执行

用 `trace` 把**整套测试**跑了一遍，统计每条 `raise` 是否真的被触发过（并排除 `__main__` 的入口行）。结果里最值得补的一块是**产出核验**：`verify_output.py` 的 7 条判据此前只有 1 条被测试提到过，其余 6 条都是"老师拿到的课件和你构建的那一份不一致"时才拦人的**交付阻断级**检查。

- **新增 14 项测试**（`tests/test_verify_output_gates.py`）：干净基线必须 `passed`；逐条注入——手工编辑 HTML、内嵌数据与 `exam.json` 不一致、缺媒体文件、媒体文件为空、内嵌音频与登记集合不一致、内嵌音频值不是 base64、内嵌音频内容与磁盘文件不同、页面里出现两份数据块、数据块被弄坏、交付夹里有软链接（打包闸门）。
- **补测试时发现两处真缺陷（都修了）**：
  1. **内嵌音频文件缺失时抛英文 `FileNotFoundError`**：原来直接 `(out/name).read_bytes()`，文件不在就漏出 `[Errno 2] No such file…`。现在先判存在，缺失交给资源清单报「缺少或无效的媒体文件：<名字>」——测试断言也随之从"英文 errno"变成中文说明。
  2. **数据块被粘成两份时漏英文 `JSONDecodeError`**：实测报错是 `JSONDecodeError: Extra data: line 1 column 456981`（既看不懂、也没说该做什么）。现在包成中文并给出下一步：「index.html 里的 examData 不是合法 JSON（可能被手工编辑，或嵌入了两份数据）：…；请用官方模板重新构建」。
- **顺手修掉一处"指错方向"的报错**：内嵌音频的值不是 `data:…;base64` 形式时，原来和"找不到对应文件"共用一句话，会被说成"audio/ 目录里找不到这个文件"；现拆成两条（一条说没有对应文件、一条说形式不对、页面里播不出声）。
- **反向验证 12 条**：逐条改名或放宽（含"删掉缺失文件的 `is_file` 保护"这种**行为**改动）→ 对应测试全部失败。
- **守卫扩到三个交付文件**：`verify_output` / `package_lesson` / `qa_report` 里每条 `raise` 的说明，都必须在测试里找到至少 5 字片段；无法用真实文件自然触发的一条（ZIP 完整性：要文件系统或压缩层出错）在守卫里**显式豁免并写明理由**。
- **顺带留档**：全量 trace 还列出其它文件里"未被触发"的 raise——`build` 5、`extract` 4、`cost` 3、`image_pages` 3、`read_acceptance` 3、`bounded_command` 2、`exam_document` 2、`fetch_package` 2、`quotes` 2、`scaffold` 2，以及若干单条；其中相当一部分是入口行或依赖 ffmpeg 的音频路径 → 已记入 ROADMAP。
- **又抓到两个"我自己的问题"（都修了，如实记）**：
  1. **1.0.115 的覆盖守卫会让整套测试 SIGSEGV（退出码 139）**：那个守卫在本进程内用 `trace` 跟踪其它测试模块；单独跑没事，但放进整套测试时，跑完后留下的对象（实测是 `test_preview_server` 一个未关闭的 socket）会在 `trace` 生效期间被 GC，触发 CPython 在"跟踪 + 终结器"交互下的崩溃。现把测量丢进**独立解释器**（子进程），父进程只读它的 JSON 结论：子进程即使崩了也只是这条测试失败并附 stderr，不会把整套测试带走。**这条正是"守卫本身也要被验证"的例子**——它先是挡住了我漏写的反向用例，接着把自己崩了出来。
  2. **两处 docstring 里的无效转义（将来会变成语法错误）**：`check_docs.status_label_problems` 的说明里有 `\s`、`extract_package` 模块说明里有 `\新`，都是非 raw 字符串 → 编译期 `DeprecationWarning: invalid escape sequence`（在 `-W error` 下直接失败）。两处都改成 raw docstring，已用 `-W error::DeprecationWarning` 导入验证。
- **实测**：`release_check.py` 五项全过（安装 `complete` · 133 文件 · 1.0.116；整链重放 9/9；材料包判读可声明 3 项 / 不能声明 5 项）；全套 **543 项测试通过**（1 项如实跳过）。本记录计数均为打包前命令回读。

## 复核（本记录写完后重打包）

- 本记录写在上面的运行之后，故重新打包 1.0.116 并重跑 `release_check.py`：五项仍全过、`check_install=complete`；`SHA256SUMS.txt` 条目与新 ZIP 指纹一致。

## 未覆盖边界

- 守卫的"说明被断言过"只覆盖 `verify_output`/`package_lesson`/`qa_report` 三个**交付阻断级**文件；其它文件的 `raise` 仍靠各自的用例（全量 trace 清单已留档并记入待办）。
- `audio.py` 的路径依赖 ffmpeg，未纳入"每次发布都跑"的守卫。
- Windows 真机、宿主真机与真实试卷仍未验证（同前几版声明）。

---

# 1.0.115 结构闸门 21 条"从未被执行"的断言补上反向用例（并删掉 1 条死判据）

## 本次实际执行

做 1.0.114 换上的待办：给普通 `assert` 式判据补同类机械守卫。做法是**先量后补**——用 `trace` 记录反向用例实际执行到的行号。

- **量出的缺口**：`build.py` 的 66 条 `assert` 里，`test_gates_fire` 只执行到 45 条 → **21 条判据从未被任何用例触发**，把它们改松不会有测试报警。（`grounding` 的 24 条与 `culture` 的 5 条在这套用例里已全部执行到，不是缺口。）
- **补齐 20 项反向用例**：句子译文与原文完全相同、`source_groups` 没按原序覆盖全部段落、`origin` 的页码/图片/链接、`transfer_tasks` 引文不是真子串、写作分析引文不在范文里、阅读节的题目带音频、选项既没文字也没图片、`option_images` 缺路径、`logic_links` 的颜色/端点/引文、空位题号不存在、资源不能写网址、资源文件必须存在。需要真实构建才走到的三条（音频证据超出时长、逐题 `audio_context` 越界、切片时长与区间不符）用**桩 `ffprobe`**（`FFPROBE_BIN`）跑通，不必装 ffmpeg。
- **删掉 1 条死判据（如实记）**：写"模板占位符"用例时发现 `build.py:498` 那条 assert **永远走不到**——`build()` 在第 390 行已经调用 `verify_template()`（`verify_output.py` 里那条显式 `raise`），它先拦下并给出同样结论。重复的 assert 成了"从未被执行"的死判据，已删除并在原位写明由 `verify_template` 覆盖；同时保留一条用例验证那条**真实生效**的检查（模板被改坏时必须拦）。
- **新增守卫 `tests/test_gate_coverage.py`（2 项）**：用 `trace` 量 `build`/`grounding`/`culture` 三个文件里每条 `assert` 是否被反向用例执行到，**零未执行**才算过；并写明范围——`verify_output`/`package_lesson`/`qa_report` 的判据是显式 `raise`（没有 assert），`audio.py` 的 15 条由音频用例覆盖。守卫放在独立模块以避免"自己 trace 自己"的递归；测量结果缓存，两个用例只量一次（约 2.7 秒）。
- **反向验证**：停用"空位题号"或"迁移任务引文"用例 → 守卫立刻失败；停用"模板占位符"用例 → 守卫仍通过（那条覆盖的是 `verify_output.py` 的 `raise`，不在 assert 范围内）——**这正说明守卫的边界是诚实的**，不是"看起来通过"。
- **覆盖复查（打包后包内）**：`build.py` 65 条 / `grounding.py` 24 条 / `culture.py` 5 条，**未执行 0 条**。
- **实测**：`release_check.py` 五项全过（安装 `complete` · 132 文件 · 1.0.115；整链重放 9/9；材料包判读可声明 3 项 / 不能声明 5 项）；全套 **529 项测试通过**（1 项如实跳过）。本记录的计数均为打包前命令回读。

## 复核（本记录写完后重打包）

- 本记录写在上面的运行之后，故重新打包 1.0.115 并重跑 `release_check.py`：五项仍全过、`check_install=complete`；`SHA256SUMS.txt` 条目与新 ZIP 指纹一致。

## 未覆盖边界

- 守卫只覆盖 **assert 式**判据；`verify_output`/`package_lesson`/`qa_report` 的显式 `raise` 判据还没有"每条都必须被触发"的机械保证（分别由交付闸门用例覆盖，但不是逐条）。
- `audio.py` 的 15 条 assert 由音频用例覆盖，未纳入"每次发布都跑"的守卫（那批用例依赖 ffmpeg）。
- Windows 真机、宿主真机与真实试卷仍未验证（同前几版声明）。

---

# 1.0.114 交付闸门 28 个从未被测试提到的判据补上反向验证

## 本次实际执行

先做 1.0.113 换上的那条待办：把"每条闸门都有反向验证"做成机械检查。一量就发现**交付闸门是最大的空洞**。

- **量出的缺口**：`quality_gate.py` 共 **44 个判据码**（39 个阻断级 `add(...)` + 5 个提示级 `warn(...)`），其中 **28 个从未在任何测试里出现过**。也就是说，把"台账缺失""章节顺序与原件不一致""原文被改过""题号与台账不符""范文混进原卷区域""听力根本没接音频""让老师自己拖动"这些**会阻断构建**的判据改松，不会有任何测试报警。（`answer_audit` 的 15 个码在 1.0.113 已补齐，这次量出来是 0 缺口。）
- **新增 `tests/test_quality_gate_gates.py` 30 项**：
  - **基线必须完全干净**（无错误、无提示、`status=automated_checks_passed`）——台账、原件文件、exam.json 三者一致；
  - **28 个码逐个注入缺陷**：阻断级断言 `status=blocked`，提示级断言"只出现在 warnings、不阻断"；
  - 听力里有几条必须走到真实 `ffprobe`（时长不符、转写指纹、转写来源），用 `FFPROBE_BIN` 指向一个**桩脚本**（`platform_tools.find_tool` 会优先用它），因此不需要装 ffmpeg；另外专门测了"ffprobe 跑不起来时必须阻断"（本机正是这种情况）；
  - **一条守卫**：从源码提取 `add(`/`warn(`/`block(`/`flag(` 的全部判据码，要求每个码都在测试里出现——以后新增判据却没有测试会直接失败。
- **反向验证 29 条**：28 个码逐条改名并**只跑对应的那一个测试**（避免被守卫"顺带拦住"而看不出真伪），**全部失败**；再故意新增一条 `brand_new_gate` 判据，守卫立刻失败。
- **过程中修掉三个我自己写错的夹具/补丁（如实记）**：① 守卫里的正则被写成双反斜杠，永远匹配不到；② 听力夹具的默认段落文本 `M: Hello. W: Hi.` 自己就命中 `dialogue_collapsed`，干扰了"提示级不阻断"的断言；③ `audio=None` 时把键设成了 `None`，闸门会去拼 `base/None` 抛 `TypeError`——真实数据里不会这样，但夹具必须与真实形状一致：**不给音频就不要留这个键**。
- **实测**：`release_check.py` 五项全过（安装 `complete` · 131 文件 · 1.0.114；整链重放 9/9；材料包判读可声明 3 项 / 不能声明 5 项）；全套 **506 项测试通过**（1 项如实跳过）。本记录的计数均为打包前命令回读。

## 复核（本记录写完后重打包）

- 本记录写在上面的运行之后，故重新打包 1.0.114 并重跑 `release_check.py`：五项仍全过、`check_install=complete`；`SHA256SUMS.txt` 条目与新 ZIP 指纹一致。

## 未覆盖边界

- 机械守卫只覆盖**码式判据**（`add`/`warn`/`block`/`flag`）；`grounding`/`culture`/`build` 里用 `assert` 表达的判据还没有同类守卫（已记入 ROADMAP 待办）。
- 这些用例锁的是"判据会触发"，**不锁判据的措辞**（措辞由 `tests/test_messages.py` 的静态检查覆盖）。
- Windows 真机、宿主真机与真实试卷仍未验证（同前几版声明）。

---

# 1.0.113 答案审计的逐题判据补上"注入缺陷必须被拦"

## 本次实际执行

做 1.0.112 换上的待办。答案审计（`answer_audit`）是"答案不许乱编"的最后一处没被反向验证覆盖的闸门。

- **先量了覆盖缺口**：源码里共 15 条判据（7 条阻断级 `block(...)` + 8 条待核级 `flag(...)`），而测试里只提到过 3 条（都是答案表对照相关）。也就是说——**把"缺答案""缺客观题证据""证据段不存在""证据引句不在原段""与台账答案不一致"这些阻断判据改松，不会有任何测试报警**。
- **新增 16 项测试**（`tests/test_provenance.py` 的 `AnswerAuditGates`）：
  - **基线必须完全干净**（无阻断、无待核、`status=answer_checks_passed`），否则注入用例分不清"是注入导致的"还是本来就报；
  - 7 条阻断级各注入一次：`answer_missing`、`answer_not_in_options`、`evidence_missing`、`evidence_paragraph_unknown`、`evidence_quote_absent`、`answer_key_mismatch`、`ledger_answer_mismatch`（前两条还断言 `status=blocked`）；
  - 8 条待核级各注入一次：`answer_key_missing`、`answer_source_vague`、`ledger_stem_drift`、`evidence_option_low_overlap`、`cloze_answer_too_long`、`grammar_answer_suspicious`、`answer_distribution_skew`、`answer_multi_letters`（并断言待核**不阻断**）；
  - **一条守卫**：从源码里提取所有 `block(...)`/`flag(...)` 的判据码，要求每个码都在测试里出现——以后新增判据却没测试会直接失败。
- **完形答案分布那条阈值两侧各测一次**：5/11 = 45.5% 要报、5/12 = 41.7% 不报，把"超过 45% 提示"这个阈值钉住。**我第一版只测了 100% 集中**，结果反向验证把阈值从 0.45 改成 0.999 时测试照样通过——是反向验证先没咬住、我才发现用例太松，改成两侧夹逼后才真正有约束力。
- **反向验证 16 条**：逐条把判据改松（含把阈值 0.45 改成 0.5、以及**故意新增一条没有测试的判据**验证守卫），**全部失败**。反向验证过程中每轮都清 `scripts/__pycache__`——上一轮刚踩过"同一秒改坏又改回、文件大小不变，pyc 被判有效，于是跑的是旧代码"。
- **实测**：`release_check.py` 五项全过（安装 `complete` · 130 文件 · 1.0.113；整链重放 9/9）；全套 **476 项测试通过**（1 项如实跳过）。本记录的计数均为打包前命令回读。

## 复核（本记录写完后重打包）

- 本记录写在上面的运行之后，故重新打包 1.0.113 并重跑 `release_check.py`：五项仍全过、`check_install=complete`；`SHA256SUMS.txt` 条目与新 ZIP 指纹一致。

## 未覆盖边界

- 这些用例锁的是"判据存在且会触发"，**不锁判据的措辞**（报错文字质量由 `tests/test_messages.py` 的静态检查覆盖）。
- 语义层面的正确性（引句是否真的支持答案）本来就无法由脚本判断；本轮只是把"可核对的判据不会被悄悄改松"补上。
- Windows 真机、宿主真机与真实试卷仍未验证（同前几版声明）。

---

# 1.0.112 重放脚本每一步的判定抽成可测函数（并给每一步补"做坏就失败"的用例）

## 本次实际执行

做 1.0.110/1.0.111 留下的那条：`rehearse_first_use.rehearse()` 里九步的判定原来是**内联表达式**，只有"一路绿灯"的端到端重放能覆盖——把某一步改坏（例如把"要有真实页数且没有 problems"放宽成"有页数就行"）不会被任何测试抓到。

- **抽成九个纯函数**：`install_ok` / `plan_ok` / `inventory_ok` / `answers_ok` / `build_ok` / `verify_ok` / `browser_ok` / `qa_ok` / `package_ok`，每条都带中文 docstring 写明判据，例如：
  - 第 3 步"要有真实页数且**没有 problems**（重复页/漏页都算）"；
  - 第 8 步"清单非空，且**未填写时退出 1、填写后退出 0**——只生成不校验不算过"；
  - 第 9 步"`browser_checked`（有浏览器验收）或 `preview_only_browser_check_pending`（如实降级）"。
  全部只用 `.get`，因此脚本输出解析失败（空对象）时一律判不通过，不会抛异常。`rehearse()` 里九处改为调用它们，并加 `STEP_COUNT=9` 与运行时断言"步骤数必须是九步"。
- **行为不变**：重构后用真实重放复跑，九步状态与之前完全一致（第 1 步因"改了文件、清单过期"失败，其余照旧；打包后自然恢复）。
- **这次重构踩到一个真坑，并顺手补了防护（如实记）**：我加完 `STEP_COUNT=9` 与运行时断言后，跑反向验证把常量改成 8 再改回 9——结果随后的 `release_check` 一直报"应为 8 步、实际 9 步"，而文件里明明是 9。原因是**改坏又改回发生在同一秒内、文件大小还没变**，而 CPython 判 pyc 是否失效只看 (mtime 秒, 大小) 这一对，于是导入到的是**改坏那一版**的缓存。这暴露的是验收工具的一个真实风险：它可能"验的是旧代码"。现在 `release_check.check()` 一开始就调用 `clear_bytecode_caches(ROOT)` 清掉 `__pycache__`（这些派生文件不随包发布），并有 3 项测试（清得掉、目录不存在不报错、`check()` 真的调用了它）。顺便说，正是本轮新加的那条运行时断言把这个问题**当场叫了出来**——不是它，我会在"重放通过"的假象里继续走。
- **新增 14 项测试**（11 项判据 + 3 项 pyc 防护）：九个判据各自"好输入通过 + 若干做坏输入不通过"；再加两条守卫——`rehearse()` 必须**真的调用**这九个函数（否则测的是死代码），以及**判据不得再写回内联表达式**（按 `step('N. ` 的步骤编号核对九步都在）。第 7 步有"跳过/执行"两条分支，所以守卫按步骤编号、而不是数 `step(` 行数——我第一版就是数行数，`11 != 9` 当场失败，改成按编号后通过。
- **反向验证 6 条**：第 3 步放宽成"有页数就行"、第 2 步不要求七项全记、第 8 步不要求"未填写被拒"、第 9 步接受任何状态、第 6 步判据改回内联、步骤数常量改成 8——逐条回退后测试**全部失败**。
- **实测**：`release_check.py` 五项全过（安装 `complete` · 130 文件 · 1.0.112；整链重放 9/9；材料包判读可声明 3 项 / 不能声明 5 项）；全套 **459 项测试通过**（1 项如实跳过）。本记录里的每个计数都是打包前用命令回读确认的（测试数、文件数、闸门用例数），不再凭印象填写。

## 复核（本记录写完后重打包）

- 本记录写在上面的运行之后，故重新打包 1.0.112 并重跑 `release_check.py`：五项仍全过、`check_install=complete`；`SHA256SUMS.txt` 条目与新 ZIP 指纹一致。

## 未覆盖边界

- 判据函数是纯函数，测的是"给定脚本输出该判通过还是失败"；**脚本本身是否产生正确输出**仍由端到端重放与各自的测试覆盖。
- 第 7 步的真实浏览器分支（本机有 node+Playwright 时才会走）在本机不执行，`browser_ok` 只覆盖判据、不覆盖真实点击。
- Windows 真机、宿主真机与真实试卷仍未验证（同前几版声明）。

---

# 1.0.111 发布验收脚本自己的判据补上断言（顺手修掉一个会让整条重放崩掉的容错）

## 本次实际执行

做 1.0.110 换上的那条待办：给 `release_check.py`（95 行、测试引用 0 处）与 `rehearse_first_use.py`（145 行、1 处）补断言。两者每轮发布都**真跑**，所以不是"没验证"，但它们的**判据**没有任何测试锁住——改动判据只能靠人工比对发现。

- **新增 `tests/test_release_check.py` 14 项**：把协作者换成桩，只测**聚合与判定**这一层（整条重放已由 `test_first_use_rehearsal.py` 用真实子进程覆盖，不重复跑）。
  - 五项名称与顺序、版本取自 `VERSION`；
  - 全通过 = 5 passed；**任一失败 → 该项 failed 且 failed 计数 +1**（文档/安装/重放/材料包/闸门各一条）；
  - **跳过的步骤如实写进 detail，但不计为通过**；
  - **报告写到 `dist/release-check/` 而不是包根**（历史问题：包根的报告会被打进 ZIP，版本号还停在旧版）；
  - `note` 必须写明"缺工具的跳过项不算通过""不证明真实试卷内容"；
  - 退出码只由 failed 决定：`{passed:3,failed:0,skipped:2}` → 0（跳过不算通过、也不算失败），`failed:1` → 1；
  - 第 5 项判据是子进程退出码（非零必须读成失败），且模块列表与 `cwd=包根` 要原样传下去；
  - 重放侧：`scripts/…` 在老师的工作目录下仍按**包根**解析；`as_json` 容忍噪行；夹具两页必须是**不同**的真实 PNG（相同会被登记成 `duplicate_page`，那是夹具的错不是流程的错）；九个步骤名与脚本里的字面一致。
- **写测试时发现并修掉一个真缺陷**：`rehearse_first_use.as_json()` 原来把 `{` 之后的**全部**文本交给 `json.loads`。只要某个脚本在 JSON 之后再打印一行给人看的话，就会抛 `JSONDecodeError`，把**整条重放**崩掉（而不是只让那一步失败）。现改用 `json.JSONDecoder().raw_decode()` 只吃第一个完整对象；解析不出来时返回空对象——那一步会如实标 `failed` 并附原始输出。已用真实重放复跑确认九步照旧（第 8 步 `条目=9 · 未填写时退出=1 · 填写后退出=0`）。
- **反向验证 7 条**：退出码忽略 failed、报告写回包根、重放失败也算通过、子进程非零也算通过、`note` 去掉诚实注解、`as_json` 退回直接 `loads`、`scripts/` 不再按包根解析——逐条回退后测试**全部失败**。
- **实测**：`release_check.py` 五项全过（安装 `complete` · 130 文件 · 1.0.111；整链重放 9/9；材料包判读可声明 3 项 / 不能声明 5 项）；全套 **445 项测试通过**（1 项如实跳过）。

## 复核（本记录写完后重打包）

- 本记录写在上面的运行之后，故重新打包 1.0.111 并重跑 `release_check.py`：五项仍全过、`check_install=complete`；`SHA256SUMS.txt` 条目与新 ZIP 指纹一致。

## 未覆盖边界

- **重放脚本每一步的失败判据仍未逐条测**（例如"第 3 步要求 `problems` 为空""第 8 步要求未填写退出 1、填写后退出 0"）：这些判定目前写在 `rehearse()` 里面，只能靠一路绿灯的端到端重放覆盖；要逐条测需先把每步判定抽成可调用函数（已记入 ROADMAP 待办）。
- `release_check.check()` 的测试把协作者全部换成桩，因此它证明的是**聚合与判定**，不证明五项检查本身跑得动——后者由每轮真实发布覆盖。
- Windows 真机、宿主真机与真实试卷仍未验证（同前几版声明）。

---

# 1.0.110 逐字重复项的"逐条"明细直接进复核清单

## 本次实际执行

做的是 1.0.109 换上的那条待办：让复核清单不必再跑一条命令就能看到**具体哪条重复**。先按计划量了体量，再决定"全附还是截断"。

- **先量体量**（合成卷实测）：`cost.duplicates()` 在 8 节 80 题上耗时 0.02 秒、完整清单 JSON 2117 字符；16 节 320 题 0.26 秒、3024 字符（`near_prose`/`duplicate_entries` 本来就有 20 条上限）。结论：**明细完全可以附进清单**，不需要额外的体积保护。
- **改动**：`qa_report` 新增 `duplicate_rows()`，从输出目录里的 `exam.json` 现算明细（与构建报告里的计数**同源**，都来自 `cost.duplicates()`；明细本来没进 `build-report.json`）。条目结构变成"一行统计 + 明细行"：
  ```
  - [ ] 逐字重复项（可核对，不必凭感觉；约可省 288 字符）：重复引文 3 组。… —— 结论：
    · 引文出现 3 次（95 字符，可省 190）：The club keeps a small notebook of repairs so that new membe…
    · 同节重复词条 repair：sections[3].vocabulary[0].word ↔ sections[3].vocabulary[1].word
  ```
- **三重保护，避免清单变成负担**：
  1. 每类明细有上限（重复引文 5、完全相同解析 3、高度相似 3、重复词条 5），总行数上限 12；
  2. 被截掉时补一行 `· 另有 N 条未列出：跑 python3 scripts/cost.py <输出目录>/exam.json --duplicates 看完整清单`；
  3. **明细行不是 `- [ ]` 条目**，`qa_report.py check` 不把它们算成待填项——否则老师要为每条明细各写一遍结论。渲染时把它们缩进在条目下面。
- **降级路径**：输出目录里没有 `exam.json`（更早的产物）或解析失败时，只给分类计数与命令，不报错、不留半截。
- **端到端实测**：示例构建 → `init` → 条目带 3 行明细；8 节合成卷 → 明细 7 行 + `另有 3 条未列出`；把结论按 `—— 结论：` 占位填完后 `check` 返回 `ok`，`items == concluded`，且条目数等于 `collect()` 的真实条目数（明细没被计数）。
- **新增 4 项测试 + 3 项反向验证**：明细来自同一份 `exam.json`、没有 `exam.json` 时降级、超上限时给"另有 N 条"与完整清单命令、**渲染出的明细行不被 `check()` 计数**（这一条第一版写得不够狠——只断言 `items==concluded`，而"明细被当成条目"时两者同样相等；改成与 `collect()` 的真实条目数比较后才抓得住，反向验证通过）。
- **实测**：`release_check.py` 五项全过（安装 `complete` · 129 文件 · 1.0.110；整链重放 9/9；材料包判读可声明 3 项 / 不能声明 5 项）；全套 **431 项测试通过**（1 项如实跳过）。

## 复核（本记录写完后重打包）

- 本记录写在上面的运行之后，故重新打包 1.0.110 并重跑 `release_check.py`：五项仍全过、`check_install=complete`；`SHA256SUMS.txt` 条目与新 ZIP 指纹一致。

## 未覆盖边界

- 明细里的**位置路径**（如 `sections[3].vocabulary[0].word`）是脚本口径的定位串，便于核对，但不是"页面上第几处"；真实修改仍要在 `exam.json` 里按路径找。
- 上限（每类 5/3/3/5、总 12 行）是按实测体量定的经验值，不是硬约束；特别大的卷子会走"另有 N 条"的分支。
- Windows 真机、宿主真机与真实试卷仍未验证（同前几版声明）。

---

# 1.0.109 逐字重复项的分类明细进复核清单（并更正我上一轮写错的一句话）

## 本次实际执行

做的是上一轮从"后续可做"里换出来的那条：把 `cost.py --duplicates` 的结果落到老师手上。做的时候发现**我上一轮对现状的描述是错的**，一并更正。

- **先纠正我自己的错误结论**：上一轮我写"这些可核对的重复项只在 `build-report.json` 的 `authoring_cost.duplicates` 里，老师不一定翻：`qa_report.py:51–55` 只用 `review_index`/`same_phrase_total`"。实际读代码后：
  - `build.py:512–517` 把 `cost['duplicates']` 的**计数扁平**合并进 `authoring_cost`——**根本没有嵌套的 `duplicates` 键**（我按 `cost.analyze()` 的返回形状想当然了）；
  - `build.py:529–534` 在重复量超过阈值（省 ≥200 字符且 ≥需编写量 10%）时会写一条进 `pending_items`，而 `qa_report.collect()` 第 67–68 行会把 `pending_items` **全部**列进第 5 节——**总额本来就会出现在清单里**。
  - 所以真实缺口不是"没进清单"，而是"进了也只是个总数"。我上一轮那句"核对过 `qa_report.py` 第 51–55 行"只看了那一处，没顺着 `pending_items` 走完整条链。已在 README 的 1.0.108 小节与本文件 1.0.108 记录里就地更正（保留原文并标注更正，不删痕迹）。
- **本轮实际改动**：`qa_report.collect()` 在"解析自洽复核"一节新增一条**逐字重复项**：
  - 有重复时写清**分类计数**与处置建议，例如 `逐字重复项（可核对，不必凭感觉；约可省 288 字符）：重复引文 3 组、完全相同解析 1 组、同节重复词条 2 处。重复引文优先改成 quote_ref 由脚本回填，同节重复词条可直接删；清单：python3 scripts/cost.py <输出目录>/exam.json --duplicates`；为 0 的分类不列，避免噪音。
  - 没有重复（或输出目录里没有 `authoring_cost`，例如更早的构建产物）时明确写"逐字重复项：无（…均为 0）"，而不是静默省略——与第 5 节"待核项：无"的写法一致。
  - 这样老师/助手在**同一份待填清单**里就能看到"该改 `quote_ref` 还是该删词条"，不必先去翻构建报告。
- **实测端到端**：用仓库示例构建 → `qa_report.py init`，第 2 节确实出现 `逐字重复项（…约可省 288 字符）：重复引文 3 组…`；把全部 10 条结论填完后 `qa_report.py check` 返回 `problems: []`（新条目没有破坏闸门）。
- **新增 3 项测试 + 2 项反向验证**：`test_duplicate_breakdown_reaches_the_review_checklist`（分类计数、省字符数、`quote_ref` 建议都在，且为 0 的分类不出现）、`test_no_duplicates_is_stated_explicitly`；反向验证把"只留总数"与"空值时不写"两种回退改回去，测试都失败。
- **顺手收窄了 1.0.108 那条状态标签闸门**：它上线后先撞出一个**误报**——本文件里 `# 1.0.108 顶部"当前状态"表挂着 37 个版本之前的版本号` 这种**逐版本记录标题**被当成"现役状态声明"。现按 `^#+\s*1\.0\.\d+` 认出来放行（那种标题里的版本号就是"那一版"，必须在），只对现役状态小节要求等于 `VERSION`；并补了 `test_version_log_titles_are_not_status_claims` 锁住两个方向（历史标题放行、现役小节旧标签仍被抓）。
- **实测**：`release_check.py` 五项全过（安装 `complete` · 129 文件 · 1.0.109；整链重放 9/9；材料包判读可声明 3 项 / 不能声明 5 项；闸门用例 **64** 项通过（比上一版多 1 项：状态标签的历史记录豁免））；全套 **427 项测试通过**（1 项如实跳过）。

## 复核（本记录写完后重打包）

- 本记录写在上面的运行之后，故重新打包 1.0.109 并重跑 `release_check.py`：五项仍全过、`check_install=complete`；`SHA256SUMS.txt` 条目与新 ZIP 指纹一致。

## 未覆盖边界

- 清单里给的是**分类计数 + 命令**，不是逐条内容；具体哪条引文重复仍需跑 `cost.py --duplicates`（已换成 ROADMAP 的新待办）。
- 阈值（省 ≥200 字符且 ≥需编写量 10%）以下时不写"重复内容约 N 字符"的待核项，但第 2 节的分类计数仍会出现——这是有意的：复核清单要给出事实，是否值得改由人判断。
- Windows 真机、宿主真机与真实试卷仍未验证（同前几版声明）。

---

# 1.0.108 顶部"当前状态"表挂着 37 个版本之前的版本号

## 本次实际执行

上两轮把"文档自称的数字/参数/命令"纳入了自动核对；这轮查的是**最上面那张状态表**——`docs/ROADMAP.md` 的「当前状态（按目标逐条对照，1.0.70）」：它把六个问题逐条对照"状态→证据"，是我和你判断"哪些闭环了"的入口，可它自己的版本标签停在 **1.0.70**，而当时已经是 **1.0.107**（差 37 个版本）。

- **缺陷①：状态小节版本号漂了。** 读者会以为那一堆结论是七十多版之前下的（其中"文档一致性"一行的内容确实已经过时）。
- **缺陷②："文档与版本一致性"那一行写漏了。** 它列的是 `check_docs.py` 早先的检查项；而 1.0.105–1.0.107 这三轮新增了三项（省额度表的读数与标记、散文里的参数、命令前缀），表里一个都没提——状态表自己落后于状态。
- **缺陷③："后续可做"里有一条已经做完了。** 第 3 条写"`cost.py` 可增加重复引文与冗余条目检测"——这在 1.0.9x 就已经实现（版本记录里有两处写明 `cost.py --duplicates` 找逐字重复引文/重复解析/重复词条），把已完成项列成待办会让"还剩什么"判断失真。
- **修法**：
  1. 状态小节标题改成当前版本，并写明这个版本号的**含义**："发这一版时，这张表逐条复核过、结论仍然成立"——所以发版时要么确认没变（只改版本号），要么把变了的结论一并改掉；确认不了就别写版本号。
  2. 补上三项新检查，并把表里那句话扩展成"含散文里提到的参数"。
  3. 第 3 条换成**真实剩余项**：把 `cost.py --duplicates` 的逐字重复清单接进 `qa_report.md`。~~理由是「它只落在 `build-report.json` 的 `authoring_cost.duplicates`，而 `qa_report.py init` 只用 `review_index`/`same_phrase_total`」~~ —— **更正（1.0.109）**：这句当时不准确。`build.py:512–517` 把 `cost['duplicates']` 的计数**扁平**合并进 `authoring_cost`（没有嵌套 `duplicates` 键）；`build.py:529–534` 在重复量超过阈值（≥200 字符且 ≥需编写量 10%）时写进 `pending_items`，而 `qa_report.collect()` 第 67–68 行会把 `pending_items` 全部列进第 5 节——**总额本来是到得了清单的**。真实缺口只是**分类明细**（重复引文该改 `quote_ref`、同节重复词条该直接删），已在 1.0.109 补上。这也说明我上一轮「核对过 `qa_report.py` 第 51–55 行」只看了那一处，没顺着 `pending_items` 走完整条链。
- **新增闸门 `check_docs.status_label_problems()`**：任何标题里带「当前状态」的小节，其版本号（若写了）必须等于 `VERSION`；不写版本号则放行。**这条闸门在本轮就立刻拦了我自己一次**：我把 `VERSION` 提到 1.0.108、还没改那张表的标签，`check_docs` 就先失败并点名"标题写的是 1.0.107，当前版本是 1.0.108"。
- **新增 4 项测试 + 3 项反向验证**（退回旧标签会被抓；去掉版本号按设计放行；匹配的标签放行、无版本号标题放行）。
- **实测**：`release_check.py` 五项全过（安装 `complete` · 129 文件 · 1.0.108；整链重放 9/9；材料包判读可声明 3 项 / 不能声明 5 项；闸门用例 **63** 项通过）；全套 **424 项测试通过**（1 项如实跳过）。

## 复核（本记录写完后重打包）

- 本记录写在上面的运行之后，故重新打包 1.0.108 并重跑 `release_check.py`：五项仍全过、`check_install=complete`；`SHA256SUMS.txt` 条目与新 ZIP 指纹一致。

## 未覆盖边界

- 闸门只核对**标题里的版本号**；状态表**正文**里的结论（例如"构建 0.68 秒""浏览器验收 45.7 秒"）不会因为版本前进而自动失效，仍需人工在发版时复核——这些数字目前由各自的验证记录与实测支撑，不是自动算术。
- 本轮只改了 ROADMAP 的三处漂移；**没有**逐行重审那张状态表的每一条结论（上一轮已核过 ①②④⑤⑥⑦ 的实现与证据位置）。
- Windows 真机、宿主真机与真实试卷仍未验证（同前几版声明）。

---

# 1.0.107 文档里给老师照抄的命令写成 `python`，macOS 上直接 command not found

## 本次实际执行

这轮按计划审问题④（豆包工作 / WorkBuddy）与⑤（无多选控件时的功能选择）这两条链。

- **先把这两条链测了（都成立，如实记）**：
  - `references/host-compatibility.md`（12.4KB）引用的字符串与状态值**全部与代码对得上**：`请记录全部可选功能的选择`（`preferences.py`）、`preview_only_browser_check_pending`（`package_lesson.py` 在 `--allow-unchecked` 下的实际状态）、`audio_delivery`（`build.py`/`verify_output.py`）、`not_probed`（`host_probe.py`）；四条安装路径顺序与 `host_probe.install_paths()` 一致（这条本来就有检查）；`host_probe --json` 报告的能力项（读包/写文件/执行 Python/Node/Playwright/浏览器/ffmpeg/whisper）与代码一致。
  - **⑤ 那条链实测走得通**：`plan.py menu` 打印编号清单 → `plan.py make --confirmed --range A --features 1,3,5` 生成七项全记的计划（三项 true、四项 false）→ `plan.py check` 通过。负路径也都给中文：缺 `--confirmed` → "请确认已收到老师的范围与功能回答；不能未经回答就把 confirmed 置真"；编号越界 → "功能编号 9 超出范围 1–7"；把缺一项功能的计划拿去构建 → `ERROR: 请记录全部可选功能的选择`（正是文档引用的那一句）。
- **缺陷：文档里 10 处给老师照抄的命令写成裸 `python` 加脚本路径。** 本机（macOS）实测 `command -v python` **为空**，只有 `python3`；而仓库自己的约定在三处写着"Windows 用可用的 `py -3` 或 `python`，macOS/Linux 用 `python3`"。照抄这些命令会直接 command not found——白跑一轮（问题②）。命中位置：`docs/UPDATE.md` 2 处、`references/generation-planning.md` 3 处（正是"已有全卷数据时可直接筛选再构建"那段可复制代码块）、`references/host-compatibility.md` 1 处、`references/runtime-delivery.md` 2 处、`references/whisper-setup.md` 2 处。现全部改成 `python3 scripts/…`。
- **新增闸门 `check_docs.command_prefix_problems()`**：可照抄的命令一律用 `python3`。豁免两份并写明理由——`docs/VERIFICATION.md`（记录的是当时 GitHub Actions 上真跑过的命令，`.github/workflows/compatibility.yml` 里确实用的是 `python`）与 `docs/WINDOWS.md`（面向 Windows 老师，也转录了 CI 命令）。豁免名单写进代码常量与测试，避免以后被当成漏网。
- **新增 4 项测试 + 4 项反向验证**：`CommandPrefixChecks`（仓库命令全部合规、引用文档里的裸 `python` 被抓、`python3` 放行、历史记录与 Windows 文档按设计豁免且名单被测试锁定）。反向验证把裸 `python` 写回 README/whisper-setup/runtime-delivery 都被抓住，写进 VERIFICATION.md 则按设计放行。
- **实测**：`release_check.py` 五项全过（安装 `complete` · 129 文件 · 1.0.107；整链重放 9/9；材料包判读可声明 3 项 / 不能声明 5 项；闸门用例 **59** 项通过）；全套 **420 项测试通过**（1 项如实跳过）。

## 复核（本记录写完后重打包）

- 本记录写在上面的运行之后，故重新打包 1.0.107 并重跑 `release_check.py`：五项仍全过、`check_install=complete`；`SHA256SUMS.txt` 条目与新 ZIP 指纹一致。

## 未覆盖边界

- 前缀检查只看 裸 `python` 加脚本路径 这一种写法；`python -m unittest`、`python -c "…"` 在 macOS 上同样可能失败，但它们在文档里都是 CI/记录语境，本次没有一并规范。
- **④ 的两个宿主（豆包工作、WorkBuddy）仍未实机验收**：本轮核对的是"文档与代码是否一致"，不等于宿主链路已验证；`docs/VERIFICATION.md` 里的声明照旧。
- Windows 真机与真实试卷仍未验证（同前几版声明）。

---

# 1.0.106 文档"散文里提到的参数"没人核对：打错也发布得出去

## 本次实际执行

上一轮把 harness.md 的读数与标记纳入自动核对；这轮顺着"提速/省额度"那几页往下查：**文档自称的机制是否真的有脚本支持**。

- **先测了能测的（都成立，如实记）**：`SKILL.md` 的《生成速度：五个立刻见效的做法》与 `references/generation-planning.md` 的《省 token 与积分》没有互相矛盾；其中可核对的两条也对：
  - 快速档的字段名确实存在——`build.py:307` 的 `missing_enrichment`、`build.py:387` 的 `quick_profile_content_and_browser_review_required`；
  - 词典范围那条"示例由 4.4MB 降到约 375KB"，实测 **4338.9KB → 376.4KB**（默认 `--dictionary-scope lesson` vs `full`），数字属实。
- **缺陷：散文里提到的命令行参数没有任何核对。** `check_docs.py` 原来只查"同一行里同时出现 脚本名 与 `不存在的参数`"的参数；可这些提速/省额度文档经常在**散文里直接写用法**（例如"用 `--profile quick` 先交付"）。实测三种漂移全部漏过：
  1. `--profile quick` 打成 `「`--profile` 多写一个 s」 quick`；
  2. 凭空加一个 「凭空多写一个参数」；
  3. 把 `--dictionary-scope` 写成 「`--dictionary-scope` 写成另一个名字」。

  助手照抄散文里的参数就会撞 argparse 报错——白跑一轮，正是"生成特别久"的来源之一。
- **修法：新增 `check_docs.orphan_flag_problems()`**。"认得"的口径是**所有脚本**的 argparse 选项，外加 Node 的 `scripts/browser_check.cjs`（它的 `--stress` 原来也不在口径里）；并且按**定义来源**排除 CSS 自定义属性——`assets/lesson.html` 里定义过的 `--size`、`--accent` 等不算命令行参数。用"模板里定义过"判定比写白名单耐用：以后新增 CSS 变量不必回来改白名单。
  - 顺带修掉一个我自己写出来的不一致：`doc_files()` 原来固定用仓库根，而新函数接收 `root` 参数，两处对不上（真调仓库根时看不出问题，写测试就会串到真实文档）。现改为 `doc_files(root=None)`，默认仍是仓库根。
- **新增 6 项测试 + 4 项反向验证**：`ProseFlagChecks`（仓库散文参数全部有主、Node 参数算数、模板里定义的 CSS 变量不算参数、不存在的散文参数被抓、存在的散文参数放行、只提 CSS 变量不失败）；反向验证把三种漂移写回去都被抓住，CSS 变量不被误报。
- **实测**：`release_check.py` 五项全过（安装 `complete` · 129 文件 · 1.0.106；整链重放 9/9；材料包判读可声明 3 项 / 不能声明 5 项；闸门用例 **55** 项通过）；全套 **416 项测试通过**（1 项如实跳过）。

## 复核（本记录写完后重打包）

- 本记录写在上面的运行之后，故重新打包 1.0.106 并重跑 `release_check.py`：五项仍全过、`check_install=complete`；`SHA256SUMS.txt` 条目与新 ZIP 指纹一致。

## 未覆盖边界

- 参数检查只保证"这个名字有脚本认得"，**不保证用在了对的那个脚本上**（散文里没写脚本名就无法归属；同行写法的归属检查是原有那条）。
- 只查 Python argparse 与 `browser_check.cjs` 的字面量参数；外部工具自己的选项（如 ffmpeg 的 `-v`）是单横线，不在范围内。
- Windows 真机、宿主真机与真实试卷仍未验证（同前几版声明）。

---

# 1.0.105 "省额度"那张表的读数漂了，而且没有任何检查守着

## 本次实际执行

这轮审 `references/harness.md` 的「读什么、能跳过什么」表——它是省额度的核心指引（问题③），可表里的数字与它引用的标记**从来没有被任何检查核对过**（`check_docs.py` 只核对命令、参数、链接与测试数量）。

- **缺陷①：读数漂了。** 表里写"`SKILL.md` + `schema.md` 两份加起来约 60KB"，实际 **72.9KB**（差 21%）；写"本页（约 5KB）"，实际 **8.1KB**（差 62%）。这两个数字正是助手用来判断"要不要读完整契约"的依据：少报 12KB 会让它低估全读的代价，而本页少报 3KB 会让它低估眼前这一页。
- **缺陷②：引用的标记不是实际字面。** 表里说 SKILL.md 有两节标了「只在本次有听力时读」，但 SKILL.md 的原文是 `只在**本次有听力**时读这一节`（`**` 把词拆开了）。照字面找不到——助手要么多读，要么漏读那两节，而这两节正是精听、挖空与听力三档接入的入口（问题⑥）。
- **修法**：
  1. 数字改成实测值（73KB / 8KB）；"模板行为说明各节约 15KB"这条本来是对的，现在也纳入自动核对。
  2. 标记写成「只在本次有听力时读这一节」，并点名是 `## 二、自动分段与精听` 与 `### 听力三档接入`。
  3. **新增"本次实际要读多少"三行表**：只做听力约 26KB / 写教学内容约 30KB 起 / 全部文档约 222KB。把"省额度"从形容词变成可核对的数字。26KB 的构成写明：本页 8KB + `listening.md` 7KB + `SKILL.md` 两节听力 4KB + `schema.md` 顶部清单 6KB。
  4. **新增闸门 `check_docs.reading_cost_problems()`**：按文件真实字节数核对 harness.md 里的读数（差超过 10% 即失败），并核对 harness.md 「」里点名的 SKILL.md 标记确实存在（比对时忽略 `**` 这类行内标记）。
- **过程中被仓库自己的检查拦了两次（如实记）**：
  1. `tests/test_check_docs.py::test_skippable_sections_stay_marked_with_their_condition` 断言 harness.md 必须含字面 `只在本次有听力时读`；我把标记改成带 `**` 的原文后它立刻失败——说明这处措辞是与 SKILL.md 标记之间的既定约定。最终写成「只在本次有听力时读这一节」（去掉 `**`：既满足那条字面断言，也能在 SKILL.md 去标记后找到）。
  2. **我第一版测试本身是错的**：自己合成一份小 harness 去测"读数对不对"，可合成文件自身的体积就先对不上（"本页约 8KB" 对着 0.1KB），测不到真东西。改成**对真实 harness.md 做一次改写**、并用真实 `SKILL.md`/`schema.md` 建树后才有效。
- **新增 5 项测试 + 3 项反向验证**：`ReadingCostClaims`（仓库读数一致；过时读数被抓；读数缺失被抓；标记改名被抓；文档数字本身不被误报）；反向验证把旧的 60KB、旧的 5KB、标记改名逐一写回去，都能被抓住。
- **实测**：`release_check.py` 五项全过（安装 `complete` · 129 文件 · 1.0.105；整链重放 9/9；材料包判读可声明 3 项 / 不能声明 5 项；闸门用例 49 项通过——比上一版多 5 项，正是本轮新增的读数与标记检查）；全套 **410 项测试通过**（1 项如实跳过）。

## 复核（本记录写完后重打包）

- 本记录写在上面的运行之后，故重新打包 1.0.105 并重跑 `release_check.py`：五项仍全过、`check_install=complete`；`SHA256SUMS.txt` 条目与新 ZIP 指纹一致。

## 未覆盖边界

- 读数检查只覆盖 harness.md 里这四处数字与标记；README、SKILL.md、FAQ 没有同类体量声明，因此没有纳入。
- **26KB 是"最小阅读集"的算术和，不是模型实际读入的 token 数**：真实消耗还包含工具输出、构建报错与重试轮次。要给出真实数字，仍需要一次真实试卷的端到端记录。
- Windows 真机、宿主真机与真实试卷仍未验证（同前几版声明）。

---

# 1.0.104 听力路径的报错：三处英文原文 + 一处报错顺序反了

## 本次实际执行

这轮按"复用同源字幕就不用重跑 ASR"（省额度的一大块）往下查，用一组畸形输入扫了整条听力链（`import_timed_text` / `align_whisperx` / `audio cut`）。

- **缺陷①：字幕时间坏掉时漏 `float()` 的英文原文。** `seconds()` 用 `float(x)` 解析时间，畸形时间（如 `.:.`、`1:2:3.4.5`）会抛出 `could not convert string to float: '.'` 给老师看。现在改成中文说明并给出正确写法：`字幕时间 '.:.' 含无法识别的字符；毫秒请写成 00:00:01,000 或 00:00:01.000`；分钟/秒 ≥60 也单独说明。
- **缺陷②：字幕 JSON 坏掉时漏 `Expecting value: line 1 column 1`。** 现在走共享的 `exam_document.read_json()`，给 `第 N 行第 M 列读不通；请检查引号是否成对、逗号是否多余、括号是否闭合`。同一个读取器也用在 `exam.json` 与切段清单上，中文口径统一。
- **缺陷③：把 `generation-plan.json` 当成切片清单传给 `audio.py cut` 时只说 `KeyError: 'segments'`。** 现在明确说"不像切片清单"并给出清单形状，指向 `references/listening.md`。
- **缺陷④（这轮最值得记的一处）：`align_whisperx.py` 的报错顺序反了。** 它原来**先**取 `importlib.metadata.version('whisperx')`、**后**读计划文件，于是：
  - 计划文件写错时，老师看到的是 `ERROR: No package metadata was found for whisperx`（**英文**，而且指向一个不相关的问题）；
  - 照着去装 WhisperX，装完才发现真正的问题是计划文件。
  现在改成**先审输入、再查环境**，并把缺依赖的消息改成中文且给出替代路径：`本机没有安装 WhisperX（找不到 whisperx 包元数据）：对齐要装 whisperx==3.8.6 与英语对齐权重；如果你已经有同源带时间字幕或转写，改跑 scripts/import_timed_text.py，不必装它`。原计划的 12 项对齐测试全部照旧通过（顺序变了对它们没有影响）。
- **新增 5 项测试 + 5 项反向测试**：`import_timed_text` 2 项（4 种畸形时间都必须是中文且不含 `could not convert`；坏 JSON 必须是中文且不含 `Expecting value`）、`align_whisperx` 3 项（**计划写错必须先报计划错**、缺 WhisperX 给中文并提 `import_timed_text` 替代、坏 JSON 中文）、`test_portability` 的"给错文件"用例扩到 `audio.py cut --manifest`（中文、无英文堆栈，仍跑 cp936/utf-8 两种控制台）。
- **实测**：`release_check.py` 五项全过（安装 `complete` · 129 文件 · 1.0.104；整链重放 9/9；材料包判读可声明 3 项 / 不能声明 5 项；闸门用例 44 项通过）；全套 **405 项测试通过**（1 项如实跳过）。

## 复核（本记录写完后重打包）

- 本记录写在上面的运行之后，故重新打包 1.0.104 并重跑 `release_check.py`：五项仍全过、`check_install=complete`；`SHA256SUMS.txt` 条目与新 ZIP 指纹一致。

## 未覆盖边界

- **我只审了"报错是否说得清"，没有验证字幕识别本身的质量**：真实 SRT/VTT 的时间轴、说话人标注、以及"这份字幕确实来自这段录音"，仍要靠老师/助手核对（工具只做格式、时长与绑定指纹的检查，并已把 `alignment_review` 标为 `pending`）。
- **`align_whisperx` 仍无法在本机实跑**：没有 whisperx/torch/ffmpeg，本轮只覆盖"缺依赖与输入错误的报错"，对齐质量仍未验收。
- 老式 Mac 的 CR-only 字幕（`
` 分行）不会被识别成多段——会退化成一段，仍属已知限制，本轮未改。
- Windows 真机、宿主真机与真实试卷仍未验证（同前几版声明）。

---

# 1.0.103 引用范围与"给错文件"：一个静默产出半截词，一个漏英文堆栈

## 本次实际执行

这轮从"省额度"的关键路径（`quote_ref` 由脚本回填，省掉逐字抄写）往里查，查出两处。

- **缺陷①：`quote_ref` 切在单词中间会静默产出半截词，而且没有任何闸门能拦。** `quotes.py fill` 原来只校验"下标在范围内"，于是 `[10,13]` 这种把 `museum` 切开的范围会照样填成 `' op'`；`quotes.py check` 只看"是不是逐字子串"——**半截词仍然是子串**，所以它也报 `ok`；`answer_audit`/`quality_gate` 同样只比对子串，全部放行。最终"证据引句"会以半截词的形式出现在页面上。实测（`'The museum opens at nine.'`，填 `[10,13]`）：填出 `' op'`，`check` 状态 `ok`，`answer_audit` 不拦。
  - 项目里**本来就有**这条规则：`grounding.validate_blank_tokens` 对精听挖空要求"落在真实、完整的词上，不许截断半词"。问题是它只用在挖空上，引用范围没用它。
  - 修法：把判据提取成 `grounding.span_problem(text,start,end)`（返回问题码），挖空与引用共用一份规则；`quotes.py fill` 遇到问题码就拒绝并列出**全部**问题（不写回文件，一个字节都不动），`quotes.py check` 对已经填好的引文也会定位并点名"把单词截断了"，另外空白/空串引文现在也报问题（以前被 `value.strip()` 直接跳过，等于没有证据却不报）。
  - **我自己的测试又抓到一个假失败**：共用判据第一版要求"范围内必须含 ASCII 词"（挖空的契约），于是中文引文（如"请阅读下列短文"）被判成"纯标点"。现已参数化：挖空要求英文词（`require_english_word=True`），引用只要求"有字"（`\w` 含中文）。中文范围贴着英文单词外侧取整段也不会被误判成截断。
- **缺陷②：把 `generation-plan.json` 当成 `exam.json` 传进来会漏英文堆栈。** 这两份 JSON 常常同目录，而计划里 `sections` 是 `"listening,reading"` 这样的字符串。实测四个脚本都漏堆栈：`quotes.py`/`cost.py`/`scope.py` 抛 `AttributeError: 'str' object has no attribute 'get'`，`answer_audit.py` 抛 `TypeError: string indices must be integers`。看起来像程序坏了，实际只是给错了文件——助手会因此白白重试。
  - 修法：新增内部模块 `scripts/exam_document.py` 的 `load()`，顶层形状不像 exam.json 就抛**中文** `ValueError`，并点名"这看起来像 generation-plan.json"；`quotes`/`cost`/`scope`/`answer_audit` 四个入口统一改用它。`cost.py` 另外补上了与其它脚本一致的 `ERROR: …` 处理（它原来连 try/except 都没有，任何错误都漏堆栈）。
  - 已登记进 `check_docs.py` 的 `INTERNAL`（内部模块，不是老师要敲的命令）。
- **我自己被仓库里的门拦了一次（如实记）**：把挖空判据改成共享函数后，assert 的中文说明变成了从字典里取（`f'{where}: {messages[problem]}'`），字面里没有中文，`tests/test_messages.py` 的静态门立刻判失败（"报错文字必须是中文"）。改成 `assert problem is None,f'{where}: 挖空必须遮住一个完整真实的词——{messages[problem]}'` 后通过。**这说明那条静态门确实在起作用，不是摆设。**
- **新增 9 项测试**：`grounding` 4 项（共享判据的各问题码、范围内含标点不算纯标点、中文不误判成截断、纯标点被拒）、`quotes` 4 项（fill 拒绝半截词且**不写回文件**、拒绝空白与纯标点、check 点名半截词、check 点名空白/空串）、`test_portability` 1 项（把计划文件喂给四个入口：退出码 1、无 Traceback、无 AttributeError/TypeError、中文说明并点名 `exam.json` 与 `generation-plan.json`，并在 cp936/utf-8 两种控制台编码下各跑一遍）。反向测试逐条回退规则，7 次全部失败。
- **实测**：`release_check.py` 五项全过（安装 `complete` · 129 文件 · 1.0.103；整链重放 9/9；材料包判读可声明 3 项 / 不能声明 5 项；闸门用例 44 项通过）；全套 **400 项测试通过**（1 项如实跳过）。

## 复核（本记录写完后重打包）

- 本记录写在上面的运行之后，故重新打包 1.0.103 并重跑 `release_check.py`：五项仍全过、`check_install=complete`；`SHA256SUMS.txt` 条目与新 ZIP 指纹一致。

## 未覆盖边界

- **`quote_ref` 只保证"是整词"，不保证"就是你想引的那一句"**：范围选对了词边界但选错了句子，仍会通过所有闸门（子串检查本来就证明不了语义）。语义判断仍要人看。
- 空白引文现在会被 `quotes.py check` 点名，但**没有**把 `evidence` 缺少引文（条目在、`quote` 字段缺失）也算问题——那属于 schema 必填项，本轮没有扩大范围。
- "给错文件"只覆盖支持 `exam.json` 的四个入口；`build.py`、`parts.py` 的报错口径未在本次逐条复核（`parts.py` 实测已是中文）。
- 宿主真机、Windows 真机与真实试卷仍未验证（同前几版声明）。

---

# 1.0.102 真机验收报告的平台判定：Windows 报告可能被判成"不是 Windows"

## 本次实际执行

审的是**闭环问题①时我自己要用的那条链**：老师在 Windows 上跑 `scripts/smoke_report.py --zip`，把报告发回，我跑 `scripts/read_acceptance.py` 判读。这轮发现判读脚本认不出平台，会让"Windows 验收"永远无法被确认。

- **缺陷**：`read_acceptance.verdict()` 原来的取法是 `smoke['family'] → host-probe.json['family'] → 'unknown'`，可真实产物里
  1. `smoke_report.py` **从来不写顶层 `family`**（只写 `environment`，而 `environment` 里只有 `system`，没有 `family`）；
  2. `host-probe.json` 在第 3 步（宿主能力）失败时**根本不会落盘**（写文件发生在 `host = probe()` 之后，前面就 `return` 了）。

  两条合起来：一台**真的在 Windows 上跑出来**的报告会被读成"本次报告来自 unknown，不是 Windows"。实测把 `environment.system='Windows'`、无 `host-probe.json` 的报告喂进去 → Windows 声明不支持。
- **为什么测试没发现**：`tests/test_read_acceptance.py` 的夹具一直造**顶层 family** 的报告（`report(family='windows')`），而真实产物从来没有这个键；唯一的端到端测试走的是本机（macOS）且第 3 步成功，`host-probe.json` 一直在。**夹具与生产者的形状不一致**，正好把缺陷挡在测试之外。
- **修法（生产者与判读者一起改）**：
  1. `smoke_report.environment()` 写出 `family`（来自 `platform_tools.describe_platform()`），报告顶层也写 `family`；`--zip` 的文件名不再依赖"读一个不存在的键（只靠 `platform.system()` 兜底）"。
  2. `read_acceptance.family_of()` 分四级取：顶层 `family` → `host-probe.json.family` → `environment.family` → `environment.system`，并把 Windows/NT、Darwin/macOS 归一。
  3. 四级都拿不到时返回 `unknown`，判读理由是"报告里没有平台信息，无法判断"——**不再**说成"不是 Windows"："没写平台"不是"不是 Windows"的证据。
- **新增 6 项测试**（`PlatformResolution`）：真实形状的 Windows 报告（无 host-probe）必须支持 Windows 声明；`environment.family` 优先于 `system`；**老报告**（environment 无平台）仍能靠 `host-probe.json` 判出 Windows；`Darwin` 读成 `macos` 且理由含"不是 Windows"（保持原有口径）；完全没有平台信息时理由含"无法判断"且**不含**"不是 Windows"；**生产者契约测试**——直接调 `smoke_report.environment()`，断言它写进了 `family` 且判读结果不是 `unknown`。端到端测试也补上"报告本身要写明平台"。
- **实测**：`release_check.py` 五项全过（安装 `complete` · 128 文件 · 1.0.102；整链重放 9/9；材料包判读可声明 3 项 / 不能声明 5 项；闸门用例 44 项通过）；全套 **391 项测试通过**（1 项如实跳过）。

## 复核（本记录写完后重打包）

- 本记录写在上面的运行之后，故重新打包 1.0.102 并重跑 `release_check.py`：五项仍全过、`check_install=complete`；`SHA256SUMS.txt` 条目与新 ZIP 指纹一致。

## 未覆盖边界

- **这只修"报告能否被判读"，不能替代 Windows 实机执行**：本机仍是 macOS，问题①**尚未闭环**，仍需在 Windows 或豆包工作上真跑一次并回传。
- 四级都取不到平台时判读会拒绝支持 Windows 声明，这是刻意的保守；代价是老版本 `smoke_report.py` 产出的报告（environment 里没有平台）如果同时缺 `host-probe.json`，仍需用新版本重跑。
- `family_of` 对未知平台名（如 `freebsd`）原样返回，判读按"不是 Windows"处理——非 Windows 就不是 Windows。
- 宿主真机与真实试卷仍未验证（同前几版声明）。

---

# 1.0.101 答案对照：两道闸门不一致，各自误拦一种合法写法

## 本次实际执行

这轮审答案对照链（问题里"答案不许乱编"那一半）：`answer_audit.py` 与 `quality_gate.audit_exam()` 都在拿答案原件的解析表逐题对照，但**两处各写了一套比较逻辑**，于是同一条数据出现两种判决。实测（答案原件第 21 题解析为 `AB`）：

| 成品 `answer` | `quality_gate` | `answer_audit` |
| --- | --- | --- |
| `["A","B"]` | 阻断 `answer_key_mismatch`（**误拦**） | 通过 |
| `"AB"` | 通过 | 阻断 `answer_not_in_options`（**误拦**） |
| `["A"]` | 阻断 | 阻断 ✓ |
| `["A","B","C"]` | 阻断 | 阻断 ✓ |

- **误拦①（quality_gate）**：`references/schema.md` 写着 `answer` 可以写"合理变体数组"，页面也按 `answer.includes(key)` 判定并显示成 `A / B`；可 `quality_gate` 用的是 `str(expected).upper() not in given`，于是原件写多选 `AB`、成品写 `["A","B"]` 时**假失败**。假失败的危害 1.0.95 已经吃过一次：正常卷子先撞假失败，还可能诱使助手改数据或编内容去"通过检查"。
- **误拦②（answer_audit）**：它要求答案必须是选项键本身，于是成品照原件写成 `"AB"` 时被拦成"答案 `['AB']` 不在选项里"——尽管与原件逐字一致。它原来的比较还先 `str(answer)` 再取字母，对列表会拼出 `"['A', 'B']"`，属于同一处逻辑不顺。
- **修法**：比较逻辑收进 `answers.py` 的 `answer_match()` / `answer_letters()`，两道闸门都改用它。语义：① `expected` 整体出现在 `given` 里（变体数组语义）→ 相同；② 两边都是纯选项字母时按字母集合比较（`AB` 与 `["A","B"]` 是同一次多选）→ 相同；③ 其余逐字比较（文字答案 `which`）。**只放宽了"原件本身就是多字母"和原有变体语义这两种情形**：`["A"]` vs `AB`、`["A","B","C"]` vs `AB`、`["B"]` vs `A` 仍然阻断。
- **多字母答案进待核项**：`"AB"` 会被接受，但同时记 `answer_multi_letters` 待核——因为页面把 A、B **各自**判为正确（`answer.includes(key)`），真正的多选题目前只能这样表达。宁可让老师看到这条限制，也不假装页面支持多选。
- **没有放宽的**：答案里混进非选项字母仍然阻断。特意确认了"单词答案 + 有选项"这类真错误不会被当成多选放过——`CAT`/`cat` 含 `T`（不在 A–H），仍然 `answer_not_in_options`。
- **新增 6 项测试 + 6 项反向测试**（`tests/test_provenance.py` 的 `AnswerFormTests`）：13 条 `answer_match` 用例；两道闸门对 5 种合法写法一致放行（含 `AB` vs `["A","B"]`、`AB` vs `A B`、`A、B` vs `["B","A"]`）；4 种真不一致一致阻断；单词答案仍自拦；多字母答案进待核且提示含"多选/单选"；单字母变体数组**不**被误报成多选。反向测试逐条回退比较逻辑，全部失败。
- **文档**：`references/schema.md` 写明 `answer` 多字母组合的含义与页面限制（每个字母各自判对）。
- **实测**：`release_check.py` 五项全过（安装 `complete` · 128 文件 · 1.0.101；整链重放 9/9；材料包判读可声明 3 项 / 不能声明 5 项；闸门用例 44 项通过）；全套 **385 项测试通过**（1 项如实跳过）。

## 复核（本记录写完后重打包）

- 本记录写在上面的运行之后，故重新打包 1.0.101 并重跑 `release_check.py`：五项仍全过、`check_install=complete`；`SHA256SUMS.txt` 条目与新 ZIP 指纹一致。

## 未覆盖边界

- **页面仍没有"多选题"判分**：`answer.includes(key)` 只表示"这个选项算对"，所以"必须同时选对两个"的题，学生端单独点 A 也会被标对。本轮只做到"不假失败 + 明确进待核"，**没有**新增多选控件。
- **残余风险（如实记）**：若某题答案写成 `add` 这类**全部由 A–H 组成**的单词，且该题有选项，会被当成字母组合并列入待核（不会静默通过，但会多一条待核）。这是把放宽限制在最窄范围后的代价。
- Windows 真机、宿主真机与真实试卷仍未验证（同前几版声明）。

---

# 1.0.100 听力接线复查：两个"替老师宣布已核对"的默认值

## 本次实际执行

按测试覆盖率排序找下一个零覆盖模块，命中 **`scripts/audio_wiring.py`**（130 行）：全仓 `tests/` 没有任何一处引用它，也没有任何测试创建过切段清单（`segments.json`）——**听力接进 HTML 的这条主路从未被自动测试执行过**，而问题⑥"只要听力"直接依赖它。

- **缺陷①：`mode` 被凭空补成 `verified`**。清单没写 `verification_mode` 时，`wire_audio` 原来写 `text_bundle.get('verification_mode','verified')`。页面（`assets/lesson.html`）正是靠 `boundary==='auto_silence' || mode==='unsegmented'` 决定要不要标"边界待核对"——凭空补 `verified` 等于把没声明的东西显示成已核对。现在不补：字段缺就整个不写，并在 `pending` 里说明"切段清单没有声明 verification_mode，边界核对责任不清"。
- **缺陷②：算不出指纹时会挂上别的录音的转写**。`find_transcript()` 的 docstring 写着"Pick the transcript whose source_audio_sha256 matches this exact recording"，但整卷原音不在磁盘上时 `target` 为 `None`，函数会**返回找到的第一个 `transcript.json`**，`wire_audio` 随即把它的 sha256 记成本节的转写证据。更隐蔽的是：那份转写若连 `source_audio_sha256` 字段都没有，`data.get(...)==None==target` 会直接命中。现在算不出指纹就返回 `None`，并区分两种原因（原音不在磁盘 / 附近转写都不同源）；没有 source 字段的转写不再可能被当成同源。
- **缺陷③：`quality_gate` 把缺失的 `boundary` 当成 `verified`**。`references/schema.md` 要求这个字段，闸门却在缺失时按 `verified` 继续，而页面不写它就不标"待核对"。现在缺失或取值不认识 → 阻断（`audio_alignment_boundary_missing`），并按 `auto_silence` 继续后面的检查——反正已经阻断，不会放过。**实测边界**：`auto_silence` 的两项后果（引句不符降级为警告、qa-report 要求逐段记录）发生在时长探测之后，本机没有 ffprobe 时前面的 `audio_probe` 会先报错并 `continue`，所以那两项后果要等 ffprobe 可用才出现；无论哪种情况该节都是被阻断的，不会因此放过。整卷未分段档（`mode=unsegmented`）不受影响（`tests/make_browser_fixture.py` 用的就是这一档，仍放行）。
- **文档同步**：`references/schema.md` 补上 `boundary` 的第三种取值 `not_split`（整卷未分段时工具实际写的就是它，旧文档只写两种）以及"缺失会被阻断、工具不再补默认值"。
- **新增 `tests/test_audio_wiring.py` 17 项**：整段接线（相对路径、`audio_scope`、时长、首尾原句、转写指纹、`full_audio` 注入）；未核对段标 `auto_silence` 并进 `pending`；缺 `verification_mode` 不补默认值；异源转写拒绝；原音缺失不猜转写；**没有 source 字段的转写拒绝**；已接线的节不改写（`quality_gate` 因此不会重复注入）；整卷原音兜底并说明原因；单节单段 1:1 兜底；逐题切片相对时间（有/无整段清单两种）；非听力节不动；跨盘 `rel()`；`bundle_dir` 显式与自动识别；`kind` 不符拒绝；`quality_gate` 的 boundary 阻断与未分段豁免。
- **反向测试**：本轮 7 道新闸门逐条去掉后跑测试，全部失败。**第一次有两个没咬住——是我的测试写弱了**：一个用显式 `null` 去测默认值，而默认值只在**键整个缺失**时才生效；另一个把"没有 source 字段的转写"命名成 `no-hash.json`，而候选只匹配名为 `transcript.json` 的文件，那个文件根本没进候选。改成真实场景后两条都能咬住。
- **实测**：`release_check.py` 五项全过（安装 `complete` · 128 文件 · 1.0.100；整链重放 9/9；材料包判读可声明 3 项 / 不能声明 5 项；闸门用例 44 项通过）；全套 **379 项测试通过**（1 项如实跳过）。

## 复核（本记录写完后重打包）

- 本记录写在上面的运行之后，故重新打包 1.0.100 并重跑 `release_check.py`：五项仍全过、`check_install=complete`；`SHA256SUMS.txt` 条目与新 ZIP 指纹一致。

## 未覆盖边界

- **仍然没有真实听力音频**：`wire_audio` 只做路径、指纹与时间换算，**不验证切出来的音频听起来对不对**；本机仍没有 ffmpeg/ffprobe，播放与切点仍未实机验收。
- **1:1 兜底是刻意保留的便利**：只有一个听力节、清单里也只有一个切段时（id 不同名也算）会接线。测试锁住了这个行为，但它是"按数量推断"，不是按题号证明。
- **页面标签没有自动化点击验证**：浏览器验收用的夹具没有音频，"边界待核对"标签靠代码断言（模板里 `boundary==='auto_silence'||mode==='unsegmented'`）而非实机截图。
- Windows 真机、宿主真机与真实试卷仍未验证（同前几版声明）。

---

# 1.0.99 WhisperX 对齐与 whisper 运行时准备的校验复查

## 本次实际执行

按上轮清单，这轮审 **`prepare_whisper.py`**（老师第一次准备听力环境要走的路）与 **`align_whisperx.py`**（有原文时的默认对齐后端）。

- **`prepare_whisper.py`：行为未发现缺陷，补齐 4 项测试**。已确认并锁住的行为：Windows 运行时按官方 asset 的 `sha256:` digest 校验（不符即丢弃）；模型按 HuggingFace 的 LFS sha256 校验到暂存的 `.download` 文件，只有哈希一致才替换；缓存只在模型哈希一致时复用；非预期 release tag 被拒；zip 的越界路径与符号链接条目被拒。新增测试：tar 分支保留执行位（`0o700`）且跳过符号链接、越界成员报中文拒绝且不落到目标目录外；macOS 全流程（取源码→得到构建产物→校验模型→写 `runtime.json`，且不留下半成品）；模型摘要不符时拒绝且**不写运行时凭据**；`prepare_whisper.safe_name` 与 `extract_package.safe_parts` 的规则一致性表（11 条危险路径 + 3 条正常路径）。
- **`align_whisperx.py`：修了 4 处报错，并补上此前的空白覆盖**。真实发现：
  1. **报错指向根本不存在的字段**：`segments` 为空时报"请先完成切点核对（verified=true）再对齐"，可是 `plan.json` 的文档格式（`references/whisperx-workflow.md`）里**没有 `verified` 字段**——它属于 `audio.py cut` 的切片清单，不是对齐用的 plan.json。照这条提示改不出任何结果。现在改成指向真实要求（先确认题组所在时间窗，再按工作流文档写 segments）。
  2. **缺字段漏出英文 Python 报错**：少写 `start` 时抛 `KeyError: 'start'`，CLI 只打印 `ERROR: 'start'`。现在逐项点名"缺少 id/start/end/text"，并说明每段都要写。
  3. **`start`/`end` 写成字符串时抛 `TypeError`**：现在先判类型，报"必须是秒数（数字）"并给出实际值。
  4. **`segments` 不是数组时** `data['segments']` 抛 `KeyError`：现在给出 `{"segments":[…]}` 的格式示例，并提醒时间窗必须来自实际录音、不要照抄示例秒数。
- **`align_whisperx.py` 此前没有任何自动测试**：而本文件 1.0.14 的记录里写着"`align_whisperx.py` 的校验与拒绝逻辑由自动测试覆盖"——**当时这句话不成立**（全仓 `tests/` 无一处引用该模块）。本轮新增 `tests/test_align_whisperx.py` 12 项，并**在同一处把旧记录改正为如实说法**，不再让它继续误导读者。
- **测试用假的 `torch`/`whisperx`/`nltk`**（本机没有可用的 torch）：覆盖空数组、缺字段、类型错、时间窗重叠与越界、缺 text、改了 `alignment_text` 却没写 `normalization_note` 的拒绝；词时间被换算到音频绝对时间且 `alignment_review` 保持 `pending`；异常词时间与零词记入 `issues`、状态转 `alignment_failed` 而不是静默成功；缓存 WAV 格式不符（8kHz）的拒绝；同源同计划指纹命中时复用且**不重新加载模型**；CLI 在有问题时退出码为 2 **且仍然留下报告文件**。
- **反向测试**：本轮新增的 11 道闸门逐条去掉规则后跑测试，**每次都失败**（3 道 whisper 准备 + 8 道对齐），确认测试对代码有真实约束力，而不是"写了个永远通过的断言"。
- **实测**：`release_check.py` 五项全过（安装 `complete` · 127 文件 · 1.0.99；整链重放 9/9；材料包判读可声明 3 项 / 不能声明 5 项；闸门用例 44 项通过）；全套 **362 项测试通过**（1 项如实跳过）。

## 复核（本记录写完后重打包）

- 本记录写在上面的运行之后，故重新打包 1.0.99 并重跑 `release_check.py`：五项仍全过、`check_install=complete`；`SHA256SUMS.txt` 条目与新 ZIP 指纹一致。

## 未覆盖边界

- **WhisperX 对齐的准确性仍未实机验收**：本轮覆盖的是校验与记录逻辑；词时间对不对、模型间分歧怎么处理，仍要真实听力材料复核（与上一版声明一致，未因本轮加测试而升级为"已验证"）。
- **`prepare_whisper.py` 的 Windows 分支仍无法在本机执行**：把进程内 `os.name` 改成 `'nt'` 会让 `pathlib` 返回 `WindowsPath` 并在构造时抛 `NotImplementedError`（我试过，这条模拟不成立）；因此 Windows 运行时的资产选择与 digest 存在性由测试覆盖，**下载后解压的实际执行仍待 Windows 实机**。
- **假 torch 不等于真模型**：测试替换了 `whisperx.align`，只验证我们的记录/拒绝逻辑，不验证对齐质量。
- Windows 真机、宿主真机与真实试卷仍未验证（同前几版声明）。

---

# 1.0.98 更新路径的半途失败复查

## 本次实际执行

按上轮列的清单，这轮审 **`extract_package.py --apply`**（老师的更新路径，问题①直接相关）。

- **现状问题**：`apply_update()` 先 `copytree` 备份，然后逐个 `shutil.copy2` 覆盖，**没有任何中途失败防护**。Windows 上 OneDrive／网盘同步、杀毒、Office/WPS 正打开着文件时复制会抛 `PermissionError`，于是技能目录变成"一半新版、一半旧版"——而这个模块自己的 docstring 就写着 "on Windows a half-copied skill is hard to recover"。
- **修法（三层）**：
  1. **动手前预检** `can_write()`：对每个将被覆盖的目标文件真的 `open(path,'r+b')` 试一次——只读属性与"被占用"都会在这里暴露；目标还不存在时检查最近的已存在父目录是否可写。有任何一个写不进去就**直接拒绝**并点名文件，**此时一个文件都没有改动**。
  2. **复制中途失败自动回滚**：用刚做的备份把已覆盖的文件逐个恢复（每个文件单独兜 `OSError`），并报出失败的文件名与备份位置。
  3. **回滚也可能失败**：如实列出未恢复的文件清单，提示从备份手动复制——不声称"已恢复"。
- **过程中修掉我自己写的一个报错错名 bug**：回滚循环里复用了 `relative` 变量，导致"复制 VERSION 时失败"被报成"复制 SKILL.md 时失败"。是我自己的新回归测试（断言报错要点名 VERSION）抓出来的；现先把失败文件名存进 `failed` 再回滚。**这正是"报错必须点对名"的意义**。
- **实测三个场景**：① 只读目标 → 拒绝、文件未变、备份未创建；② 第 2 个文件失败 → 报"复制 VERSION 时失败 … 已把 1 个文件恢复成更新前的内容 … 备份在 …"，两个文件都回到 1.0.0；③ 连回滚也被拒 → 报"已把本次改动过的 0 个文件恢复 … 另有 1 个文件没能回滚（SKILL.md），请从备份手动复制回去"，目录确实是混合态（与报错一致，没有撒谎）。
- **Windows 下载标记**：ZIP 条目含 `C:\Windows\x.txt`、`..\escaped.txt`、`fine.txt:Zone.Identifier`（ADS）→ 三条都被拒并给出原因（盘符/反斜杠/冒号）。
- **测试**：`tests/test_update_flow.py` 新增 4 项；该文件 10 项全绿。`docs/UPDATE.md` 第 3 步写明"预检拒绝"与"中途回滚/回滚失败如实披露"。
- **实测**：`release_check.py` 五项全过（安装 `complete` · 126 文件 · 1.0.98；整链重放 9/9；材料包判读可声明 3 项 / 不能声明 5 项；闸门用例 44 项通过）；全套 **346 项测试通过**（1 项如实跳过）。

## 复核（本记录写完后重打包）

- 本记录写在上面的运行之后，故重新打包 1.0.98 并重跑 `release_check.py`：五项仍全过、`check_install=complete`；`SHA256SUMS.txt` 条目与新 ZIP 指纹一致。

## 未覆盖边界

- 预检用的是 `open(path,'r+b')`：能抓住只读与"已占用"，但**抓不住"预检之后才被占用"**（那正是第二层回滚要处理的情况），也不能保证整棵目录树都可写（只检查将覆盖的文件与最近父目录）。
- 回滚只恢复**本次已覆盖**的文件；若失败发生在 `copytree` 备份阶段，则不会走到回滚（此时目标目录尚未改动，安全）。
- 没有真实 Windows 的 OneDrive/杀毒占用场景：夹具用只读属性与"回滚也拒绝"的模拟覆盖了逻辑分支。
- Windows 真机、宿主真机与真实试卷仍未验证（同前几版声明）。

---

# 1.0.97 图片材料多目录混装复查

## 本次实际执行

按"只有照片"这条最真实的路径审 `image_pages.py`（老师的卷子常常就是手机拍的）。

- **复现**：按老师的典型存放方式造夹具——
  ```
  试卷图片/原图/01.png  原图/02.png
  试卷图片/裁剪/01.png
  试卷图片/.DS_Store  试卷图片/Thumbs.db  试卷图片/说明.txt
  ```
  跑 `--dir 试卷图片`：`page_count=3`、`problems=[]`，页序被文件名排序穿插成 `原图/01 → 裁剪/01 → 原图/02`。**一份两页的卷子变成三页，页序也错了，而检查全绿**——后面的逐页转录、页集合指纹、交付都跟着错。
- **修法**：扫文件夹时若图片来自 **≥2 个目录**，以 `images_from_multiple_dirs` 记入 `problems`（CLI 退出码 1、报告照写），消息里列出目录与**同名页**（`01.png` 同时在两处），并给出两条可照做的路：只指向其中一批（`--dir 试卷图片/原图`）或按页序一次列全文件。**显式给出的文件列表不检查目录数**（人自己列的跨目录文件是刻意选择）。
- **顺带锁定既有正确行为**：`.DS_Store`/`Thumbs.db`/`desktop.ini`/`说明.txt`/`page.docx` 在单层目录里都**不算页**（`page_count=2`、无 problem）；文件名自然排序（`1,2,10`）不变。
- **测试**：`tests/test_image_inputs.py` 新增 3 项（多目录拦下 + 退出码 1 + 报告仍写出、垃圾文件不算页、显式文件列表可跨目录）；顺手修了测试里 `png()` 辅助函数不建父目录的问题（新用例需要子目录）。该文件 26 项全绿。
- **文档**：`references/image-inputs.md` 在 `--dir` 示例下写明"会递归子目录；混装会被 `images_from_multiple_dirs` 拦下"以及哪些文件不算页。
- **实测**：`release_check.py` 五项全过（安装 `complete` · 126 文件 · 1.0.97；整链重放 9/9；材料包判读可声明 3 项 / 不能声明 5 项；闸门用例 44 项通过）；全套 **342 项测试通过**（1 项如实跳过）。

## 复核（本记录写完后重打包）

- 本记录写在上面的运行之后，故重新打包 1.0.97 并重跑 `release_check.py`：五项仍全过、`check_install=complete`；`SHA256SUMS.txt` 条目与新 ZIP 指纹一致。

## 未覆盖边界

- 规则是"≥2 个目录就拦"：若老师**确实**要把两批照片合成一套页集合（例如上卷/下卷分文件夹），需要显式列文件——这是有意的（不让脚本猜），但也确实多一步手工。
- 只在"目录里同时存在两批"时拦；**同一目录内的重复页**（同名不同内容、或两页一模一样）仍由既有的 `duplicate_page`/编号缺页检查负责。
- 没有真实手机照片验证：夹具是标准 PNG，真实照片的 EXIF 方向、HEIC 变体、压缩伪影不在此列（HEIC 在支持后缀里，但解码不做）。
- Windows 真机、宿主真机与真实试卷仍未验证（同前几版声明）。

---

# 1.0.96 本地预览服务的 Range 复查

## 本次实际执行

按"文档承诺但没验证"的清单往下走，这轮找到的是 **`scripts/preview.py`：84 行、零测试**。它是老师"点证据重听、跳到某一秒"时真正提供音频的本地服务，而 `SKILL.md` 明确承诺"支持音频 Range 请求；普通不支持 Range 的服务器可能导致证据重听从头播放"。

- **先补覆盖（12 项）**：整段请求 200 + `Accept-Ranges: bytes` + `audio/*` 类型；`bytes=10-19` → 206 且切片逐字节相等；后缀 `bytes=-10` → 最后 10 字节；开区间 `bytes=100-` → 到文件尾；末端越界 `bytes=0-<size+999>` → 收敛到 `size-1`；**起点越界 → 416 + `Content-Range: bytes */size`**（这条最要紧：不能悄悄返回整段，否则"跳秒"会从头播）；区间反向 → 416；HTML 的 `Content-Type`；目录请求不 500；路径穿越（`/../../../../etc/passwd`、`/..%2f..%2fetc%2fpasswd`、`/audio/../../../etc/passwd`）一律读不出来；缺文件 404。
- **结果**：这 11 项在现有实现上**全部通过**——Range 的算术本身是对的（没有发现缺陷，这一轮补的是覆盖）。
- **但顺带查出一处真问题**：认不出的 `Range` 头走的是 `send_error(400)`。而 **多段请求 `bytes=0-99,200-299` 是合法 HTTP**（正则 `fullmatch` 不匹配逗号形式），未知单位、乱写的值同理。这类客户端会收到 400 → **音频完全放不出声**，老师会以为文件坏了。按 RFC 7233 "An origin server MAY ignore the Range header field" 改为：**解析不出的 Range 一律忽略、照常 200 返回整段**（最多多传一点数据，播放不受影响）；合法但不可满足的区间仍按 RFC 返回 416。新增 4 条断言（多段/未知单位/乱写/`bytes=--`）锁住"忽略而不是拒绝"。
- **实测**：改后 12 项全过；`release_check.py` 五项全过（安装 `complete` · 126 文件 · 1.0.96；整链重放 9/9；材料包判读可声明 3 项 / 不能声明 5 项；闸门用例 44 项通过）；全套 **339 项测试通过**（1 项如实跳过）。

## 复核（本记录写完后重打包）

- 本记录写在上面的运行之后，故重新打包 1.0.96 并重跑 `release_check.py`：五项仍全过、`check_install=complete`；`SHA256SUMS.txt` 条目与新 ZIP 指纹一致。

## 未覆盖边界

- 测试用 `http.client` 直连本机服务，**没有在真实浏览器里验证音频 seek**（那需要 Playwright + 真实媒体文件；`browser_check.cjs` 覆盖的是另一套交互）。
- 只验证了单段 Range 的语义；多段 Range 被有意忽略（返回整段是 RFC 允许的，但不是"分段返回 multipart"）——若将来需要 multipart，这里是明确的行为边界。
- 预览服务只监听 `127.0.0.1`；局域网/宿主预览的差异不在本次范围。
- Windows 真机、宿主真机与真实试卷仍未验证（同前几版声明）。

---

# 1.0.95 parts.check 判据复查

## 本次实际执行

继续按真实材料形态审，这轮看的是"省额度"的一条主路：**分节写作**（`parts.py split → 逐节写 → check → merge`）。

- **复现（假失败）**：把一份正常初中卷的骨架（听说应用／配对阅读／读写综合 B 书面表达）`split` 后跑 `check`：
  ```
  S2: 缺少 paragraphs    S3: 缺少 paragraphs    …
  ```
  原因是体检把"每节都要有 `paragraphs` 与 `questions`"当成错误。可**配对阅读、书面表达、纯题目节本来就没有原文段落**——于是正常卷子先撞一次假失败。更糟的是：助手为了让检查通过，可能**编一段原文**填进去，正好违背"内容不许编"这条底线。
- **同时漏掉的危险**：题号跨节重复。`merge` 不检查，一路合并成功，直到构建才报"题号重复"——而分节写作的初衷正是"返工只改一节"，越晚发现越贵。
- **修法**：重新划定 `check` 的职责——**只管"合并会不会出事"**：
  - 问题（拦）：题号跨节重复（新增，报"题号 X 同时出现在 S1 与 S2"）、某节没有题号（说明构建也会拒绝）、没写 `kind`、小题没有 `id`、节不在 `section_order` 里、缺分节文件；
  - 提示（不拦）：**没有原文段落**（写明"配对阅读/书面表达/纯题目节属正常；原卷有原文的节才要补"）。
- **实测**：正常初中卷骨架 → `status=ok` + 3 条"没有原文段落"提示；把 S2 题号改成与 S1 重复 → 立刻报重复；再清空小题 → 报"还没有小题"。
- **测试**：新增 `tests/test_workflow.py::test_parts_check_flags_real_hazards_not_missing_passages`；`references/schema.md` 里 `parts.py check` 的说明同步改写（写明只拦什么、什么只是提示）。
- **实测**：`release_check.py` 五项全过（安装 `complete` · 125 文件 · 1.0.95；整链重放 9/9；材料包判读可声明 3 项 / 不能声明 5 项；闸门用例 44 项通过）；全套 **327 项测试通过**（1 项如实跳过）。

## 复核（本记录写完后重打包）

- 本记录写在上面的运行之后，故重新打包 1.0.95 并重跑 `release_check.py`：五项仍全过、`check_install=complete`；`SHA256SUMS.txt` 条目与新 ZIP 指纹一致。

## 未覆盖边界

- `check` 仍不是构建校验：题型/分值/选项/引文等要求由 `build.py` 负责，这里不重复（避免又出现"两处口径不一致"）。
- "没有原文段落"只作提示，因此**漏写原文**不会被这道体检拦住——构建的 `validate_features` 会按"本节实际有什么"决定要不要栏目，最终仍以构建与人工复核为准。
- 没有真实卷验证：夹具按真实卷形态构造（配对阅读无原文、书面表达有题号）。
- Windows 真机、宿主真机与真实试卷仍未验证（同前几版声明）。

---

# 1.0.94 范围字母 A/B/C 消歧复查

## 本次实际执行

继续按真实场景审，这轮盯的是**问题⑥（只要听力）**这条路的入口。

- **复现**：老师回答"`A` 只做听力"。`plan.py make --range A` 会翻译成 `sections=listening`（这条路一直是通的），但助手完全可能把 `A` 直接传给 `--sections`。在初中卷（节 ID 是 `S1/S2/…`）上实测：
  ```
  ValueError: 材料中没有这个板块：A
  ```
  `scope.py` 只按"章节 ID / 题型名 / 板块名/别名"匹配，不认范围字母。对刚接触这套 Skill 的助手来说，这是一条会把"只要听力"直接卡死的报错。
- **为什么不能简单把 A 当听力**：示例卷的**阅读节 ID 就是 `A`**，`--sections A` 历来指那一节；无条件翻译会改掉既有行为（文档与测试都依赖它）。
- **修法（消歧）**：新增 `scope.normalize_tokens()`——字母是某个章节的真实 ID 就按 ID 走；对不上才按范围字母解释：`A`→听力（`preset=listening`，含 kind 写成"听说应用"的初中节）、`B`→整卷（与其他板块混用即报错并说明）、`C`→提示"请把具体板块名写在 `--sections` 里"。另外给"传 A 但这份卷没有听力节"补了一条可照做的中文提示（整卷用 all / 直接写板块名）。
- **实测五个方向**：初中卷 `A`+intensive → 选中听说应用（S1）；`B` → 全部三节；`C` → 中文提示含"指定板块"；`B,S1` → 报"B 表示整卷讲评，不能与其他板块混用"；无听力卷 `A` → 报"没有听力节…"；示例卷 `A` / `reading,A` → 仍按章节 ID 选中阅读节（既有行为不变）。
- **测试**：新增 `tests/test_workflow.py::test_range_letters_work_when_section_ids_are_not_letters`；既有 scope 用例（含 `select(d,'C')`、`select(d,'A','intensive')` 的期望报错）全部保持通过——那两处字母恰好是真实 ID，走的是 ID 分支。
- **实测**：`release_check.py` 五项全过（安装 `complete` · 125 文件 · 1.0.94；整链重放 9/9；材料包判读可声明 3 项 / 不能声明 5 项；闸门用例 44 项通过）；全套 **326 项测试通过**（1 项如实跳过）。

## 复核（本记录写完后重打包）

- 本记录写在上面的运行之后，故重新打包 1.0.94 并重跑 `release_check.py`：五项仍全过、`check_install=complete`；`SHA256SUMS.txt` 条目与新 ZIP 指纹一致。

## 未覆盖边界

- 只处理**单个字母** A/B/C（大小写均可）；`A,B` 这种"字母 + 板块名"的组合仍按各自 token 解释，若 `A` 恰好是章节 ID 会按 ID 走——存在歧义时以 ID 优先，已在测试里写明。
- `plan.py --range` 路径本来就是对的（`.upper()` + RANGES 表），本版未改；这里修的是"字母被直接传进 scope/build"这条旁路。
- 没有真实初中卷验证：夹具的节 ID 与 kind 是按真实卷形态构造的。
- Windows 真机、宿主真机与真实试卷仍未验证（同前几版声明）。

---

# 1.0.93 图片占位选项闸门复查

## 本次实际执行

继续按"真实材料形态"审：这次盯的是**图片选项**。`SKILL.md` 早就写明"原卷里选项是图片的题必须用 `option_images` 真的放图片，不能用「图A/图B」这类文字描述代替；那就等于没给学生看图"，但**全仓没有任何检查在拦**（`grep 图A` 在 `build.py`/`quality_gate.py` 里零命中）。

- **为什么必现**：卷面「听句子选图」只印 `A. 图A B. 图B C. 图C`。`scaffold` 解析成文字选项 `{A:'图A',B:'图B',C:'图C'}`，构建的"选项既无文字也无图片"检查只拦**空**选项，于是"图A/图B"一路绿灯交付——学生看到的是几个字，不是图。
- **修法**：`section_kinds.placeholder_options()`（共享给 build 与 scaffold）+ `build.validate_section` 新增阻断：**整题选项全部是图片占位且没有 `option_images`** 时拦下，报错给出两条照做路径（配 `option_images`；确实拿不到图就标待核并写进 `qa-report`，不要用文字冒充）。`scaffold` 同时把提示写进该节待办，助手在第一轮构建前就能配图。
- **判据收紧（重要）**：第一版把"单个字母"也算占位，**被我自己的回归测试当场抓出假阳性**——语法选择的 `6. A. a B. an C. the D. /` 解析后 A 的选项文本就是 `a`，会被误拦。现只认"图/图片/图N"这类图片引用；`a/an/the`、`x/y/z/w` 等正常选项一律不报。
- **实测**：`{A:'图A',B:'图B',C:'图C'}` → 拦下并给出中文说明；给了 `option_images` 的四选项题 → 通过；A 是真实文字、其余是占位（混合）→ **不拦**（只拦整题皆占位）；`a/an/the`、`x/y/z/w` → 不报。
- **测试**：负向用例进 `tests/test_gates_fire.py` 的注入数据表（`build.validate_section#图片占位选项没有 option_images`，要求报错含"待核"）；`tests/test_scaffold_real_paper.py` 新增一项，断言骨架待办含"占位/option_images"，并断言正常文字选项**不被**误报。相关 68 项（闸门/交付链/工作流/图片选项/图片材料）全绿。
- **实测**：`release_check.py` 五项全过（安装 `complete` · 125 文件 · 1.0.93；整链重放 9/9；材料包判读可声明 3 项 / 不能声明 5 项；闸门用例 44 项通过）；全套 **325 项测试通过**（1 项如实跳过）。

## 复核（本记录写完后重打包）

- 本记录写在上面的运行之后，故重新打包 1.0.93 并重跑 `release_check.py`：五项仍全过、`check_install=complete`；`SHA256SUMS.txt` 条目与新 ZIP 指纹一致。

## 未覆盖边界

- 只有"整题都是占位"才拦：**部分**选项是占位（如 A 真实文字、B 是"图B"）不拦——那可能是排版混合，需要人工判断，本版不擅自阻断。
- 占位识别是**词形**判断（图/图片/图N），不认"见下图""如图""figure 1"这类英文或长句引用；这类仍靠人工复核。
- 没有真实老师提供的"听句子选图"试卷；夹具是按卷面常见写法构造的。
- Windows 真机、宿主真机与真实试卷仍未验证（同前几版声明）。

---

# 1.0.92 小标题决定呈现方式复查

## 本次实际执行

1.0.91 把初中卷骨架修好之后继续往下看，发现一个更隐蔽的问题：**呈现方式只按 `kind` 判断**。

- **复现**：初中卷「七、读写综合（本大题分为A、B两部分，共35分）」底下是 `A. 回答问题（…）` 与 `B. 书面表达（本题15分）`。`kind` = "读写综合" 认不出来 → 两节都落成 `custom`。后果：`B. 书面表达` **丢掉写作工作区**——`validate_features` 不会要求 `writing_steps`/`teacher_model`（只有 `preset=='writing'` 才要求），模板也不按写作渲染，页面不会出现审题/提纲/语言支架/范文示范。
- **修法（三处实现必须同步，否则构建与页面会各说一套）**：
  1. `section_kinds.preset()` 增加第 2.5 步：`kind` 认不出来时，用本节 `title`/小标题匹配别名，长别名优先（避免"阅读"抢走"阅读理解"）；新增 `_alias_in()`；
  2. 别名表补口语化写法：`回答问题/阅读回答/阅读表达/阅读并回答`→reading、`听句子选图/听短文/听对话/听录音`→listening、`书面表达（/话题作文`→writing；三份表（Python、`assets/lesson.html`、`scripts/browser_check.cjs`）同步（既有测试锁一致性）；
  3. `assets/lesson.html` 与 `browser_check.cjs` 的 `sectionPreset()` 加同一步 `aliasIn()`，位置与 Python 完全一致；
  4. `scaffold.py` 生成骨架时把认得出的预设写进 `kind_preset`（认不出则**不写**，否则会冻结成 custom），`exam_from_ledger` 透传 `kind_preset`；待办第一条要求核对；
  5. 改动模板后同步更新 `template-manifest.json` 的 `template_sha256`（实测 `verify_output` → `passed`/`exact`）。
- **实测（同一份初中卷骨架）**：`S1 听说应用`→listening（带 `blanks`）、`S4 阅读理解 A`→reading、`S6 读写综合 A`→reading、`S7 配对阅读`→seven、`S8 短文填空`→grammar、**`S10 读写综合 B`→writing（带 `writing_steps`+`teacher_model`）**、`S11 综合运用`→`kind_preset` 留空。
- **测试**：新增 3 项（骨架按题型名+小标题宣告 `kind_preset`、认不出时留空、三份实现的优先级顺序静态一致：`declared → SECTION_PRESETS → KIND_ALIASES[kind] → aliasIn → audio → writing_steps → knowledge`）；修正 1 项旧期望（`test_skeleton_keeps_paper_kinds_and_infers_presets` 原断言读写综合一律 `custom`，现改为 A→reading、B→writing，并在注释里写明这是"卷面小标题给出的证据，比一律留人工确认更准"）。
- **实测**：`release_check.py` 五项全过（安装 `complete` · 125 文件 · 1.0.92；整链重放 9/9；材料包判读可声明 3 项 / 不能声明 5 项；闸门用例 44 项通过）；全套 **324 项测试通过**（1 项如实跳过）。

## 复核（本记录写完后重打包）

- 本记录写在上面的运行之后，故重新打包 1.0.92 并重跑 `release_check.py`：五项仍全过、`check_install=complete`；`SHA256SUMS.txt` 条目与新 ZIP 指纹一致。

## 未覆盖边界

- 小标题匹配是**子串匹配 + 长别名优先**：极端情况下（小标题里同时出现两个题型词，如"阅读与写作"）会取更长的那个；这类模糊标题应人工核对，骨架的待办第一条已提示。
- 只在本机验证了 Python 侧的判断与三份实现的**静态**顺序一致；没有在浏览器里新增"小节标题推出的写作节真的渲染出写作工作区"的断言（现有夹具的读写综合节未覆盖该形态）。
- `kind_preset` 由机器宣告后，若卷面其实是混合体（一节里既有阅读又有写作），仍需助手改回 custom 或拆分。
- Windows 真机、宿主真机与真实试卷仍未验证（同前几版声明）。

---

# 1.0.91 真实形态初中卷的 scaffold 结构复查

## 本次实际执行

前两轮审的是答案侧（1.0.89）与文本框（1.0.90）；这轮按"真实材料的形态"构造一份**结构完整的初中卷文字**（听说应用／语法选择／完形填空／阅读理解 A–C／配对阅读／短文填空／读写综合 A–B，含卷头满分用时、页码、小标题、分值、图片选项续行），跑 `scaffold.py ledger` 看骨架对不对。

- **实测结果（修前）**：同一份卷子被切成 **15 个节**，其中 6 个是"听说应用"、3 个是"阅读理解"、1 个 0 题的节；听说应用与阅读理解的分值全是 `None`。三个根因：
  1. **选项续行被当成小标题**：`SUBHEADING` 正则把 `A. 图A B. 图B C. 图C` 认成"小标题 A"，于是每道题后面都开一节 —— 这是"图片选项"这种初中常见排法直接踩中的；
  2. **续行只取第一个字母**：`OPTION` 分支把整行当作 A 的选项值，B/C 丢失（甚至把 "B. 图B" 写进 A 的值里）；
  3. **大题分值在小标题出现时丢失**：小标题分支用的是 `**scores_of(text)`，把父级标题里的"每小题 1 分／共 5 分"整段覆盖没了。
- **修法**：
  1. 新增 `is_subheading()`：一行里出现 **≥2 个选项标记**（`A.`/`B.`…）或正文只是"图A"时不算小标题；
  2. 续行改用 `split_options()`：一行多个选项按 A/B/C/D 拆开并入上一题，字母重复且内容不同时进 `unparsed`；
  3. 小标题无分值时继承大题标题的 `per_question`；大题 `total` 只在该大题**只有一节**时沿用（如听说应用 5 题×1 分=5 分），多节时置空；
  4. 在 `build_ledger()` 里对"有每小题分值但无本节总分"的节按 `每小题 × 本节题数` **推算** `score_total`，并在 `todo` 里写明"这是推算值，请对照原卷核对或删掉"——不冒充原卷印过的数字。
- **实测结果（修后）**：**10 个节**，`kind`/`group` = 听说应用、语法选择、完形填空、阅读理解×3、配对阅读、短文填空、读写综合×2；题数 5/10/10/5/5/5/5/10/5/0；分值 1/5、1/10、1.5/15、2/10×3（带推算说明）、2/10、1.5/15、2/10、–/15；选项 `{'A':'图A','B':'图B','C':'图C'}`；`unparsed` 为空；卷头标题与满分/用时正确。
- **回归测试 4 项**（新增 `tests/test_scaffold_real_paper.py`）：节数与题型名/板块、题数与分值（含"推算值必须有待办说明"）、选项续行拆分且不切节、卷头信息与页码忽略。
- **实测**：`release_check.py` 五项全过（安装 `complete` · 125 文件 · 1.0.91；整链重放 9/9；材料包判读可声明 3 项 / 不能声明 5 项；闸门用例 44 项通过）；全套 **321 项测试通过**（1 项如实跳过）。

## 复核（本记录写完后重打包）

- 本记录写在上面的运行之后，故重新打包 1.0.91 并重跑 `release_check.py`：五项仍全过、`check_install=complete`；`SHA256SUMS.txt` 条目与新 ZIP 指纹一致。

## 未覆盖边界

- 这份卷子是**我按真实形态构造**的（结构与初中卷一致），不是老师提供的原件；真实卷还有"图片选项无文字""跨栏排版""表格题""读后续写"等形态未覆盖。
- 分值推算只在"小标题没写分值"时发生；若原卷小标题自己写了分值，一律以原卷为准（不推算）。
- 阅读 A/B/C 是否应各自成一节，仍取决于原卷排版：本测试锁的是"按小标题分节"这一种；原卷若不写小标题，会把整道大题作为一节（行为未变）。
- Windows 真机、宿主真机与真实试卷仍未验证（同前几版声明）。

---

# 1.0.90 文本框内容重复修复复查

## 本次实际执行

1.0.89 修的是答案侧；这轮把**试卷侧**读入链路也审了一遍，抓到一个会在真实中文卷上必现的缺陷。

- **复现**：构造一个含文本框的 DOCX（Word/WPS 的标准写法：`mc:AlternateContent` 里 `mc:Choice` 放现代图形、`mc:Fallback` 放 VML 副本，两者文字完全相同）。`extract.py` 输出：
  ```
  3 paragraph '11. When does the museum open?11. When does the museum open?'
  ```
  **题干出现两遍**。原因是 `.//w:t` 会把两份副本都收进来。文本框在中文试卷里很常见（题号、表头、图文混排），所以这不是边角情况。
- **影响**：`scaffold.py` 解析出的题面重复、题号识别对不上，助手会以为原卷多出内容；老师拿到重复题干更无从判断。而 `docs/ROADMAP.md` 的「已知限制」里这条只写着"要人工核对"，等于把 bug 当成限制。
- **修法**（机械且可测）：
  1. `drop_fallbacks()` —— 解析正文后先丢掉所有 `mc:Fallback` 子树（OOXML 里它就是"给老版本的等价副本"），文本框内容只保留一份；
  2. `paragraph_text()` —— 按文档顺序取文字，遇到文本框内嵌的 `w:p` 插入换行，避免多段粘成一句；带 `w:txbxContent` 的段落标 `textbox=true`；
  3. 表格单元格改用同一函数，单元格里的文本框同样不再重复。
- **实测**：同一个夹具修好后——文本框内容只出现一次、多段文本框输出 `'First line in box\nSecond line in box'`、含文本框的单元格输出 `['题号\n11','B']`。
- **回归测试 3 项**（`tests/test_ingest.py`）：文本框内容不重复且带 `textbox` 标记、文本框多段分行、单元格内文本框不重复。该文件 23 项全绿；`test_workflow`/`test_provenance` 无回归。
- **文档同步（含把"限制"改回"事实"）**：ROADMAP「已知限制」把原来一行拆成两行——**文本框**：去重已做、段内多段换行、标 `textbox=true`，但**顺序**仍需对照原件；**照片识别**：仍需人工逐页核对。`SKILL.md` 的 DOCX 说明与老师侧限制表同步改写。
- **实测**：`release_check.py` 五项全过（安装 `complete` · 124 文件 · 1.0.90；整链重放 9/9；材料包判读可声明 3 项 / 不能声明 5 项；闸门用例 44 项通过）；全套 **317 项测试通过**（1 项如实跳过）。

## 复核（本记录写完后重打包）

- 本记录写在上面的运行之后，故重新打包 1.0.90 并重跑 `release_check.py`：五项仍全过、`check_install=complete`；`SHA256SUMS.txt` 条目与新 ZIP 指纹一致。

## 未覆盖边界

- **没有真实老师提供的含文本框试卷**做验证：夹具按 OOXML 标准写法构造（Choice+Fallback、多段文本框、单元格内文本框），但真实卷的嵌套层次更复杂（文本框套表格、图片锚定、WPS 特有命名空间），未逐一覆盖。
- 文本框内容的**位置顺序**仍可能与其视觉位置不一致（并入所在段落），文档已写明要对照原件核对，没有解决。
- 文本框里的图片仍走 `word/media/` 一并导出，与文字的对应关系不做自动判定。
- Windows 真机、宿主真机与真实试卷仍未验证（同前几版声明）。

---

# 1.0.89 表格版答案原件解析复查

## 本次实际执行

复查答案溯源主链路时发现一个**真实缺口**：老师最常见的答案原件形态——**答题卡式答案表**（上一行题号、下一行答案）——`answers.py` 解析出 **0 条答案**，只在 `unparsed` 里留一句"含数字但未识别出题号+答案"。而 `official` 答案只允许来自脚本解析表，所以这等于让助手手工录入或卡住，与"答案必须可溯源、不许人肉录入"的纪律相冲突。

- **复现**：DOCX 表格 `题号|1|2|3|4|5` / `答案|B|C|A|D|B` → `answers: {}`、`matched_lines: []`、一条模糊 `unparsed`。
- **修法**：新增 `split_cells()`（按制表符/竖线/连续空白切格）、`head_kind()`（识别"题号/答案"类表头）、`answer_value()`（字母走 `normalise_letters`，单词/短语走 `text_answer`）、`paired_rows()`（识别"题号行 + 紧邻答案行"）。`extract()` 先按配对处理这些行，普通行仍走原逻辑，配对行不再重复解析。
- **严格配对、不硬对齐**：要求列数一致、题号列全为整数、下一行表头是"答案"类；列数不一致 → 中文原因进 `unparsed`（实测 "题号 3 列、答案 2 列……不要按顺序硬对齐"）；答案格为空 → 其余照常解析、该题点名报出；每条配对记录带 `pattern=number_row_then_answer_row`。
- **实测七种排法**：标准双行表 5 题全对；分两段的表 4 题全对；单词/短语答案（`which`、`has been`）正确；列数不一致 → 0 条答案 + 中文原因；空格子 → 只报该题；表头空角 → 正常；旧的逐行排法不受影响。
- **端到端**：表格答案 DOCX → `answers.py extract` → `scaffold.py ledger` → 台账里 `(id, answer, answer_status) = ('11','B','official')`（新增测试）。
- **测试**：`tests/test_ingest.py` 新增 5 项（表格解析、分段+单词答案、列数不一致不猜、空格子点名、表格答案到 official 台账）；该文件 20 项全绿。
- **文档同步（含修掉旧的限制说法）**：ROADMAP「已知限制」把"表格版答案"从"全靠人工"改为如实描述（已支持两种排法，列数不一致/空格子会点名）；`docs/RELEASE-NOTES.md` 的老师侧限制表相应改写；`answers.py` 模块说明列出全部支持的排法。
- **实测**：`release_check.py` 五项全过（安装 `complete` · 124 文件 · 1.0.89；整链重放 9/9；材料包判读可声明 3 项 / 不能声明 5 项；闸门用例 44 项通过）；全套 **314 项测试通过**（1 项如实跳过）。

## 复核（本记录写完后重打包）

- 本记录写在上面的运行之后，故重新打包 1.0.89 并重跑 `release_check.py`：五项仍全过、`check_install=complete`；`SHA256SUMS.txt` 条目与新 ZIP 指纹一致。

## 未覆盖边界

- 只覆盖**有序号可对齐**的表格。真实卷里还存在"一格一题、跨页续表、合并单元格、图文混排"的答案表；这些仍会落进 `unparsed`，需要人工核对（没有假装支持）。
- 没有对真实老师提供的答案 DOCX 做过批量验证：本次是构造夹具（结构与真实表格一致，但版式复杂度低于真实卷）。
- 单词/短语答案走 `text_answer()` 的保守判定（长度、词数、不含问句标点）；判定不了就进 `unparsed`，不会硬猜。
- Windows 真机、宿主真机与真实试卷仍未验证（同前几版声明）。

---

# 1.0.88 Windows 双击体检脚本复查

## 本次实际执行

问题①的结论只能来自真机，但**收集真机报告这一步**不该要求老师会开终端。本版给发布包加了一个 Windows 原生的双击入口。

- **新增 `一键体检.bat`**（与 `SKILL.md` 同层，随发布包分发，857 字节）：`@echo off` → `chcp 65001` → `cd /d "%~dp0"` → 不在技能包根目录则中文提示并 `exit /b 1` → 自动选 `py -3`（`where py` 失败则退回 `python`）→ 跑 `scripts\smoke_report.py --zip` → 打印路径说明 → `pause`。不安装、不下载、不改设置；产物仍是只含报告文本的 `smoke-report-*.zip`。
- **批处理的两个真实坑由测试钉住**（`tests/test_windows_batch.py`，7 项）：① **必须 CRLF**——逐行检查行尾，并断言无裸 LF、无 BOM（BOM 会让 cmd 把第一行当命令名报错）；② **中文前必须 `chcp 65001`**——断言它出现在前 5 行内。另外断言：跑的就是文档里那条命令、有 `where py` 回退、有 `pause`、用 `%~dp0` 切目录、明显不在根目录时提示 `SKILL.md`、无 `#!/`/`chmod`/`sudo`/`/tmp/` 这类 POSIX 专属写法、**必须进发布包**（按打包过滤规则实际枚举）、引用的 `scripts/smoke_report.py` 存在。
- **文档同步**：`docs/WINDOWS.md` 顶部"一条命令"之后加双击入口；`docs/TEACHER-QUICKSTART.md` 的"发什么回来"一节加双击说明；`docs/FAQ.md` 的沙盒条目末尾加一句；`SKILL.md` 让助手在遇到 Windows 老师时主动提供这个入口。
- **诚实边界（写进文档）**：语法、行尾、编码、引用命令都由测试守住，但**没有在真实 cmd.exe 里执行过**（本机 macOS 无 Windows 环境）。真机结论仍以老师跑出来的报告为准。
- **实测**：`release_check.py` 五项全过（安装 `complete` · 124 文件 · 1.0.88；整链重放 9/9；材料包判读可声明 3 项 / 不能声明 5 项；闸门用例 44 项通过）；全套 **309 项测试通过**（1 项如实跳过）。

## 复核（本记录写完后重打包）

- 本记录写在上面的运行之后，故重新打包 1.0.88 并重跑 `release_check.py`：五项仍全过、`check_install=complete`；并确认 `一键体检.bat` 在 ZIP 内、`SHA256SUMS.txt` 条目与新 ZIP 指纹一致。

## 未覆盖边界

- **未在真实 Windows/cmd.exe 运行**：只做了语法、行尾、编码与引用命令层面的检查；`chcp 65001` 在极老终端（Windows 7 时代 cmd）下仍可能显示乱码（功能不受影响）。
- 双击后若杀毒软件拦截 `.bat`（有些学校电脑会拦批处理），老师可能看不到任何窗口；文档未提供该情形的排查步骤——真机遇到再补。
- 脚本只在技能包根目录双击可用；放在别处会中文提示退出（不会静默做错事）。
- Windows 真机、宿主真机与真实试卷仍未验证（同前几版声明）。

---

# 1.0.87 SKILL.md 条件跳过标记复查

## 本次实际执行

延续 1.0.85 的"固定阅读量"工作：把 `SKILL.md` 里**只在特定条件下才需要读**的节标出来。

- **实测**（`stat` + 按节切分）：`SKILL.md` 全文 **46.2KB**，本次新增 3 处条件标记，加上 1.0.85 的 8 处模板行为标记，共 **11 处、覆盖 21.2KB ≈ 全文 46%**：
  - 模板行为类（写教学内容时可跳过）**15.5KB**：课堂布局、课堂功能基线、界面入口合并、批注与线索、备课修订与文字标注、顶部导航与字号控件、速对答案、模板一致性规则；
  - 听力两类 **4.4KB**：「二、自动分段与精听」「听力三档接入」——**只在本次有听力时读**；
  - 交付/答疑类 **1.3KB**：「跨平台与手机打开」。
- **做法**：只加一行条件说明（`> 只在…时读这一节`），**内容一字未删**；`references/harness.md` 的"读什么/能跳过什么"表同步指向（收材料那行补上"以及 SKILL.md 里标了听力条件的两节"）。
- **守门测试扩写**：`test_skippable_sections_stay_marked_with_their_condition` 要求每个标记①以 `>` 开头且含"跳过"、②贴在节标题下、③写明条件（模板行为/听力/交付答疑三选一），且 `harness.md` 必须指向"模板行为说明"与"只在本次有听力时读"。原来只认一种标记的写法已泛化，避免以后新增条件类型时静默漏检。
- **量化后的诚实说法**：按 `harness.md` 的读法表走一趟，固定阅读量约 **70KB（≈2.5 万 token）**，随卷型（有无听力）与勾选功能变化；这是**估算**（把各文档字节数按场景相加），不是实测的模型上下文占用。
- **本轮未做**：原计划还想压 `schema.md` 各节里与顶部清单重复的字段罗列（预计 4–6KB），复查后判定**风险大于收益**——那些节的文字承载构建真正强制的细则（引文必须逐字、挖空必须落在真实完整的词上、逐句译文句数必须一致），删减容易在无人察觉的情况下丢掉要求，而 `check_docs` 不会发现内容缺失。故只做"加条件"，不做"删内容"。
- **实测**：`release_check.py` 五项全过（安装 `complete` · 122 文件 · 1.0.87；整链重放 9/9；材料包判读可声明 3 项 / 不能声明 5 项；闸门用例 44 项通过）；全套 **302 项测试通过**（1 项如实跳过）。

## 复核（本记录写完后重打包）

- 本记录写在上面的运行之后，故重新打包 1.0.87 并重跑 `release_check.py`：五项仍全过、`check_install=complete`；`SHA256SUMS.txt` 条目与新 ZIP 指纹一致。

## 未覆盖边界

- **"少读多少 token"仍是估算**：无法在本机测量助手的真实上下文占用；字节数与"≈2.5 万 token"是相加估算。
- 标记能否被遵守取决于宿主与模型；文档只能说明"可以跳过"，不能强制。
- `schema.md` 的内容压缩本轮**主动放弃**（理由见上），所以省额度的空间到这一版基本见底；再往下只能靠"少返工轮次"与"缩小本次范围"。
- Windows 真机、宿主真机与真实试卷仍未验证（同前几版声明）。

---

# 1.0.86 四关问题一次报全复查

## 本次实际执行

1.0.84 把"结构 + 功能覆盖"合成一次报全；复查 `build()` 后发现**后面还有两道单独抛错的关**：证据链（`quality_gate`）与答案审计（`answer_audit`）。也就是一份新卷子最坏要跑 **4 轮**：

```
结构问题 → 缺栏目 → 证据链（台账/页码/来源哈希）→ 答案审计（能否追到原件）
```

- **修法**：把台账/答案表路径解析提前，四关在一次构建里跑完并合成一条 `format_problems()` 清单。某关因结构畸形算不出来时 `try/except` 兜住并**如实注明**"本次未包含该关明细"（不假装它通过）；同时若结构问题与证据链/答案条目同时出现，补一句"**结构问题可能连带影响下面的证据链/答案审计条目：先修结构，再按剩余条目核对**"，避免助手去改连带报出来的东西。
- **实测**：同一份示例注入"生词次数写错（结构）+ 缺 3 个栏目（功能覆盖）+ 台账指纹不符（证据链）"后，**一条报错列出 5 处**（原来要 3 轮）。
- **测试**：`tests/test_messages.py` 新增 `test_evidence_chain_failure_shares_the_same_report_as_structure`（结构问题与"证据链不一致"必须出现在同一条清单里、且计数为 2）；原有 `test_structural_and_feature_gaps_are_reported_in_the_same_build` 继续守住前两关的合并。定向回归 83 项（含交付链、闸门、重放）全绿。
- **代价与边界**：结构坏掉的构建现在会**多跑一次证据链/答案审计**（失败路径上略慢，换来少一轮返工）；四关判定标准一条未放宽。
- **实测**：`release_check.py` 五项全过（安装 `complete` · 122 文件 · 1.0.86；整链重放 9/9；材料包判读可声明 3 项 / 不能声明 5 项；闸门用例 44 项通过）；全套 **302 项测试通过**（1 项如实跳过）。

## 复核（本记录写完后重打包）

- 本记录写在上面的运行之后，故重新打包 1.0.86 并重跑 `release_check.py`：五项仍全过、`check_install=complete`；`SHA256SUMS.txt` 条目与新 ZIP 指纹一致。

## 未覆盖边界

- 四关合并只在"结构 + 功能覆盖 + 证据链"三类上实测过；答案审计同时拦下的组合未单独构造夹具（其 `blocking` 分支由既有交付链测试覆盖）。
- 连带条目的提示只是文字说明，脚本无法判断哪些证据链条目是"结构性连带的"——最终仍要人判断先后。
- 失败路径略微变慢（多跑一关），未量化；正常路径（无问题）耗时不变。
- Windows 真机、宿主真机与真实试卷仍未验证（同前几版声明）。

---

# 1.0.85 固定阅读量与"照抄清单"复查

## 本次实际执行

问题③（省 token）里最大的一块不是脚本，而是**每次生成必须读的文档**：`SKILL.md` 45KB + `references/schema.md` 25KB ≈ 2.5 万 token 的固定开销。本版把这块切成"必读"与"按需读"，并给"照抄清单"加了自更新守门。

- **实测文档尺寸**（`stat` 字节数）：`SKILL.md` 45.8KB（加标记后；此前 44.7KB）、`references/schema.md` 25.2KB、`references/harness.md` 8.0KB；其余 references 3–25KB（`regression.md` 25KB 只在改模板/人工验收时读）。
- **`SKILL.md` 标记可跳过**：给 8 节纯模板行为（默认视觉与课堂布局、课堂功能基线、界面入口合并规则、批注与线索、备课修订与文字标注、顶部导航与字号控件、速对答案、模板一致性规则）各加一行「模板行为说明：**写教学内容时可以跳过这一节**」，合计 **15.5KB ≈ 全文 34%**（按中文≈1 字/token 粗估约 4–5 千 token）。**内容一字未删**——只是标明"改模板或回答界面问题时才读"。
- **`schema.md` 顶部新增字段清单**（3.2KB）：卷级/每节/每题必写字段 + "触发条件 → 必写字段 → 详解在哪一节"对照表。听力卷可跳过（词典、连续阅读、精读迁移、统一阅读工作区、七选五、专业精讲与写作、展示规则）合计 **7.4KB**。
- **`harness.md` 增加"读什么、能跳过什么"表**：按步骤给该读的文档与可跳过项，并与 `SKILL.md` 的标记互相指向。
- **两张自更新守门（防清单腐烂）**：① 顶部清单必须覆盖 `build.feature_report` 在演示卷上**自己算出的** `required_content`（`quick_words`/`vocabulary`/`sentences`/`structure`/`writing_bank`）；② 逐一删掉题目的必填字段（`question_type`/`type_note`/`solve_steps`/`pitfall`/`analysis`/`evidence`/`answer_status`/`answer_source`/`strategy`），先断言构建确实报错（证明"必填"成立），再断言顶部清单提到了该字段。校验器将来新增必填字段而文档没跟上 → 测试直接失败。另加一条测试要求 `SKILL.md` 的标记存在、贴在节标题下、且 harness 的读法表指向它。
- **诚实边界（写进文档，不只写在这里）**：`schema.md` 因新增清单**变长约 6.4KB**，通读反而更贵；省额度成立的前提是"按清单 + 读法表按需读"。真正的 token 大头仍是**返工轮次**（1.0.84 已经少一轮）。
- **实测**：`release_check.py` 五项全过（安装 `complete` · 122 文件 · 1.0.85；整链重放 9/9；材料包判读可声明 3 项 / 不能声明 5 项；闸门用例 44 项通过）；全套 **301 项测试通过**（1 项如实跳过）。

## 复核（本记录写完后重打包）

- 本记录写在上面的运行之后，故重新打包 1.0.85 并重跑 `release_check.py`：五项仍全过、`check_install=complete`；`SHA256SUMS.txt` 条目与新 ZIP 指纹一致。

## 未覆盖边界

- **"少读多少 token"没有实测**：本机无法测量助手的真实上下文占用；给出的字节数与"≈4–5 千 token"是按字符数粗估，且只有在助手遵守读法表时才成立。
- 标记是否被真正遵守，取决于宿主/模型；文档只能"说清可以跳过"，不能强制。
- 自更新守门只覆盖"构建强制的必填字段"；风格类要求（教学措辞、结构判断是否正确）仍靠人工复核。
- Windows 真机、宿主真机与真实试卷仍未验证（同前几版声明）。

---

# 1.0.84 两段校验合并与浏览器验收耗时拆解

## 本次实际执行

**一、两段校验合并成一次报全（问题②③）**

- 现状问题：`build.py` 先跑结构校验（`validate`，一次列全）→ 修完重跑 → 才跑功能覆盖校验（`validate_features`，又一次列全）。也就是**第一次动手的卷子最少两轮**，每多一轮就是"老师多等 + 助手多花一轮额度"。
- 修法：把两段拆成 `section_report(d)` 与 `feature_report(d,profile)`，两者都返回 `(report, problems)`、**不再在内部抛错**；`build()` 起手把两段问题合并成一条 `format_problems()` 清单再抛（`validate()`/`validate_features()` 保留为兼容入口，报错格式不变）。结构本身畸形（缺 `sections`/`questions` 等）导致功能覆盖算不出来时，只报结构问题并**如实注明**"本次未包含缺栏目清单，先修上面的结构问题"——不假装功能检查跑过。
- 实测：同一份示例注入 1 个结构问题（生词次数写成 9）与 3 个功能缺项（`sentences`/`structure`/`writing_bank`）后，**一次构建报出 4 处**（原来要两轮）。新增反向用例 `test_structural_and_feature_gaps_are_reported_in_the_same_build` 要求两类问题同时出现在同一条清单里；`tests/test_messages.py` 16 项、`test_gates_fire`/`test_workflow`/`test_delivery_chain`/`test_paper_structure` 全绿。

**二、浏览器点击验收的耗时拆解（问题②）**

在 16 节/32 题的合成整卷上逐条计时（总 26.7s）：

| 环节 | 耗时 |
| --- | --- |
| `all-sections-navigation-vocabulary-and-individual-analysis` | **11.2s**（≈0.6s/节：逐节 `go()` 两次真实点击 + 逐题展开/收起） |
| `only-one-analysis-open-per-section` | 2.9s |
| `deep-reading-structure-renders-and-locates` / `writing-transfer-tab-renders` / `paragraph-translation-toggles` | 各 2.4s（与节数基本无关的固定开销） |
| `pen-arrow-rectangle-ellipse-undo-clear`（真实鼠标轨迹） | 1.3s |
| 其余 10 项 | 各 <1s |
| 分档实测 | 1 节 10.0s → 8 节 17.6s → 16 节 26.7s → 32 节 45.7s |

结论：**约 9–10 秒固定开销 + 约 0.6 秒/节；真实卷（8–10 节）约 15–20 秒**。

**决定：本轮不改浏览器脚本。** 可省的只有"把每节 4–6 次 DOM 查询合并成一次 `evaluate`"这类约 2–4 秒（≈总量的 10%），但改的是 `browser_check.cjs`——"构建通过 ≠ 按钮可用"的**唯一依据**。用页面内 `el.click()` 或抽样题目能省更多，但那是把"真点真播"降级；收益小、回归风险大，故只交付测量与结论，并在 ROADMAP 里写明分档预期。

**三、顺带修掉一个假失败**：`test_doctor_requires_runnable_probe_and_mp3` 依赖工作树的安装完整性——`doctor` 在安装不完整时只报 `installation` 并提前返回（这是设计），于是"刚改过、还没重新打包"时该用例会假失败（此前已两次干扰判断）。现用 `patch.object(check_install,'check',return_value={'status':'complete',…})` 固定安装状态，让它只测能力档位。

- **实测**：`release_check.py` 五项全过（安装 `complete` · 122 文件 · 1.0.84；整链重放 9/9；材料包判读可声明 3 项 / 不能声明 5 项；闸门用例 42 项通过）；全套 **297 项测试通过**（1 项如实跳过）。

## 复核（本记录写完后重打包）

- 本记录写在上面的运行之后，故重新打包 1.0.84 并重跑 `release_check.py`：五项仍全过、`check_install=complete`；`SHA256SUMS.txt` 条目与新 ZIP 指纹一致。

## 未覆盖边界

- 合并报全只在"结构问题 + 功能缺项"两类上验证；结构畸形到功能覆盖无法进行时只报结构问题（已注明），这种情况仍可能要多一轮。
- 浏览器验收耗时是本机（Mac Studio、Chrome）实测；低配 Windows 笔记本、投影环境或 Edge 下可能更慢，未实测。
- 浏览器脚本未做任何加速，"真实卷 15–20 秒"是按合成卷斜率外推的估计，不是真实卷实测。
- Windows 真机、宿主真机与真实试卷仍未验证（同前几版声明）。

---

# 1.0.83 无网抓包命令与真包端到端复查

## 本次实际执行

作者转达的提问是"老师没有梯子是不是就装不了"。1.0.81/1.0.82 把答案与第四条路径写进了文档，但**"逐个抓文件"这条路此前只是个说法**：约 120 次手工请求，截断或漏一个要等构建才暴露。本版把它做成一条命令并真跑了一遍。

- **新增 `scripts/fetch_package.py`**：取 `install-manifest.json` → 按清单逐个下载 → 逐个核对 SHA256。`--base` 支持 raw 与 jsDelivr（也可指任意同结构地址），`--version` 可要求版本一致，`--timeout` 有界。缺文件、哈希不符、越界/盘符路径（`../`、`C:/…`）都进报告并**拒绝写入**；哈希不符的文件不落盘、不计入成功；两类问题都会让退出码非零、状态为 `incomplete_fetch`。
- **诚实边界进返回值**：`trust.source_verified=false`，理由写明"清单与文件来自同一通道，哈希一致只证明传输没损坏，不证明来源未被篡改；要证明来源请用官方 `SHA256SUMS.txt` 核对官方 ZIP"；`next_step` 只指向 `check_install.py` 到 `complete`。脚本本身**不说"已安装"**。
- **真包端到端实测（本机 HTTP 挂真实技能包）**：122/122 个文件、**0.1 秒**；抓完在目标目录跑 `check_install.py` → `complete`。
- **过程中抓出一个真缺陷**：`install-manifest.json` **不在它自己的 `files` 清单里**，所以"只抓清单列出的文件"会缺清单本身 → `check_install` 报 `incomplete_install`。修法：把清单按原字节一并写入目标目录。现已加**真包端到端测试**（复制真实包 → 重建清单 → 本机 HTTP 服务 → 抓取 → 断言 `check_install=complete`）锁住；这条测试第一次跑就复现了缺清单的问题。
- **单测 7 项**：抓全并核对哈希（含中文文件名与子目录）、版本不符报出实际版本、哈希不符不落盘、越界/盘符路径拒绝且不写到目录外、不可达 base 有界失败且报中文原因、缺文件列出而不是静默跳过、真包端到端。
- **文档同步**：`SETUP`/`FAQ`/`SKILL.md`/`references/host-compatibility.md`/`TEACHER-QUICKSTART` 与 `host_probe` 的 `how` 文案都改成"用这条命令抓，不要手工逐个抓"。
- **实测**：`release_check.py` 五项全过（安装 `complete` · 122 文件 · 1.0.83；整链重放 9/9；材料包判读可声明 3 项 / 不能声明 5 项；闸门用例 42 项通过）；全套 **296 项测试通过**（1 项如实跳过）。

## 复核（本记录写完后重打包）

- 本记录写在上面的运行之后，故重新打包 1.0.83 并重跑 `release_check.py`：五项仍全过、`check_install=complete`；`SHA256SUMS.txt` 条目与新 ZIP 指纹一致。

## 未覆盖边界

- 只在本机 HTTP 上验证过抓取链路；**真实 raw / jsDelivr 的可达性与限流未在大陆网络实测**（探测逻辑已就绪，结论要由老师那台机器的 `host_probe.py --network` 给出）。
- 脚本只做"传输一致性"核对，**不能自证来源**；没有官方 `SHA256SUMS.txt` 时来源可信度低于附件上传官方 ZIP。
- 抓取是串行的（122 个文件 0.1 秒是 localhost；真实网络下会更慢），未做并发——避免被 CDN 限流，也避免把这种环境写坏。
- Windows 真机、宿主真机与真实试卷仍未验证（同前几版声明）。

---

# 1.0.82 第四条安装路径与顺序守门

## 本次实际执行

承接上一版的老师提问（"没有梯子是不是装不了"）：FAQ 已解释清楚，但**代码侧只有三条路**，其中第二条（raw）在大陆网络下经常打不开，第三条（git clone）又常被沙箱拦——等于"能走的路"实际只剩"老师上传 ZIP"。本版补一条真实可用的通道，并把它锁进文档顺序。

- **`host_probe.install_paths()` 增加 `cdn_jsdelivr`**：`https://cdn.jsdelivr.net/gh/hututu-ai/english-exam-studio@<版本或 main>/<文件路径>`，作为 `raw_files_fetch` 打不开时的备选；`--network` 分别 HEAD 探测 `github.com`、`raw.githubusercontent.com`、`cdn.jsdelivr.net` 三条通道（只发 HEAD、不下载、不改动）。四条顺序即推荐顺序。
- **边界写进代码与文档**：jsDelivr 是第三方通道——逐文件抓取时 `install-manifest.json` 也来自同一通道，**哈希一致只证明传输没损坏，不证明来源未被篡改**；来源可信仍需官方 `SHA256SUMS.txt` 核对官方 ZIP。没有把它说成"与 GitHub 等同"。
- **分发事实**：实测发布 ZIP **1,966,603 字节 ≈ 1.9MB**（最大单文件是 3.9MB 的离线词库，压缩后占比最大）；该数字写入 FAQ 与探测输出的建议，支撑"换一台能上网的设备下载再转发"这条无梯子方案。
- **新增顺序守门** `check_docs.install_path_doc_problems()`：讲安装的五份文档（`TEACHER-QUICKSTART`/`SETUP`/`FAQ`/`host-compatibility`/`SKILL.md`）必须写全四条路径，且顺序与 `host_probe.install_paths()` 一致。顺序只从"最稳那条"（`附件`/`teacher_uploaded_zip`）出现的位置往后比——因为正文里"沙箱常拦 `git clone`"这类前置说明是背景，不是推荐顺序（第一版取"首次出现"就因此误报了 `SETUP.md`，已修正并写成容忍用例）。
- **测试**：`tests/test_host_probe.py` 更新为四条路径顺序、`not_probed` 诚实标注，并新增"raw 通而 jsDelivr 不通"与"jsDelivr 通而 raw 不通"两种探测结果；`tests/test_check_docs.py` 新增正/反/容忍三类用例（写全且有序不报、少一条要报、顺序写反要报、前言提到 `git clone` 不报）。
- **实测**：`release_check.py` 五项全过（安装 `complete` · 120 文件 · 1.0.82；整链重放 9/9；材料包判读可声明 3 项 / 不能声明 5 项；闸门用例 42 项通过）；全套 **289 项测试通过**（1 项如实跳过）。

## 复核（本记录写完后重打包）

- 本记录写在上面的运行之后，故重新打包 1.0.82 并重跑 `release_check.py`：五项仍全过、`check_install=complete`；`SHA256SUMS.txt` 条目与新 ZIP 指纹一致。

## 未覆盖边界

- **仍然没有在真实的大陆网络下测过 jsDelivr 与 raw 的可用性**：本机（境外网络）只能验证探测逻辑、顺序与文档一致性；哪个通道在老师那里真能通，必须由老师那台机器上的 `host_probe.py --network` 报告说话。
- 逐文件抓取（raw 或 jsDelivr）都**无法自证来源**，只能靠"传输未损坏 + 官方 ZIP 的 SHA256SUMS 对照"；若老师只有逐文件通道，来源可信度低于附件上传官方 ZIP，这一点已写明，但不能靠脚本强制。
- 顺序守门只查"四条路径是否写全且有序"，不校验各文档措辞是否与实际平台菜单相符（平台菜单不能臆造，只能实机确认）。

---

# 1.0.81 "没有梯子/沙盒限制"FAQ 与防断链检查

## 本次实际执行

起因是作者转达的真实提问：**"GitHub 链接发过去，老师没有梯子是不是就装不了？GitHub 需要梯子吗？为什么有的老师的 Agent 显示沙盒限制？"** 这两个问题此前只散落在 `docs/SETUP.md` 的"网络受限时（实测过的一种）"与 `references/host-compatibility.md` 的能力表里，老师在 FAQ 里找不到直接答案。

- **新增两条老师向 FAQ**（`docs/FAQ.md`）：
  - 「GitHub 打不开、又没有梯子，还能装吗？」——关键区分：**安装只要求那台能跑脚本的机器拿到完整 ZIP，下载可以发生在别处**（手机流量、别的网络、同事电脑 → 附件上传）；并说明仓库页面、`raw.githubusercontent.com`、Release ZIP 下载是**三条不同通道**，所以"网页能开 ≠ 包能下"；给出实测手段（`scripts/host_probe.py --network` 打印三条路径可用性）、最稳/次稳/最不稳的排序，以及两条禁止项（不明镜像替换官方包、零散文件拼装）。
  - 「助手说"沙盒限制/网络受限"，这是什么意思？」——说明这是宿主平台的执行隔离而非本 Skill 的限制，列出五类常见表现（网络白名单、只许写工作目录、不给执行 shell/Python、预览限制脚本媒体弹窗、云端容器≠本机）与对应继续方式，并解释"别人能装、我这台不行"通常是通道不同。
- **`docs/TEACHER-QUICKSTART.md`** 安装表下方加一行指引，指向这两条 FAQ。
- **新增防断链检查**：`check_docs.py` 的 `broken_link_problems()` 校验文档里的相对链接指向真实文件（含 `../references/x.md`；http(s)、`mailto:`、纯锚点跳过），接进 `check()` 与发布验收；`tests/test_check_docs.py` 加反向用例（正常/外部/锚点链接不误报，断链必须报出，用临时 ROOT 隔离）。
- **实测**：`release_check.py` 五项全过（安装 `complete` · 120 文件 · 1.0.81；整链重放 9/9；材料包判读可声明 3 项 / 不能声明 5 项；闸门用例 41 项通过）；全套 **288 项测试通过**（1 项如实跳过）。

## 复核（本记录写完后重打包）

- 本记录写在上面的运行之后，故重新打包 1.0.81 并重跑 `release_check.py`：五项仍全过、`check_install=complete`；`SHA256SUMS.txt` 条目与新 ZIP 指纹一致。

## 未覆盖边界

- FAQ 里关于**中国大陆网络对 github.com / raw.githubusercontent.com / Release 下载**的描述，依据是社区反馈与"能开网页不能下载"的常见现象，**不同运营商、地区、时段差异很大**，因此文档写的是"三条通道可能不同、以实测为准"，没有断言"必须/不需要梯子"。本机（macOS，境外网络）无法验证大陆网络实况。
- 沙盒五类表现来自本项目实测（TLS 拦 `git clone`、写盘被拒）与宿主文档整理，仍未在真实豆包工作/WorkBuddy 上做整套实机验收。
- 防断链检查只覆盖相对路径链接；锚点是否正确、外部链接是否可访问都不查（避免网络依赖）。

---

# 1.0.80 更新流程的校验清单与文档数字复查

## 本次实际执行

复查方法：把文档要求的**更新步骤**当成"必须真能执行"的流程跑一遍，而不是只看命令拼写。

- **发现：更新说明要的 `SHA256SUMS.txt` 根本没人产出**。`docs/UPDATE.md` 第 2 步要求"通过官方 Release 下载完整 ZIP 与同版 `SHA256SUMS.txt`，用脚本核对指纹"，但 `scripts/package_skill.py` 只写 ZIP，`dist/` 里也没有任何 `*.txt`；`tests/test_update_flow.py` 的夹具只好**手写**一份校验清单来喂给 `extract_package.py`——说明这条核对步骤在真实发布物上无法执行（漏一次老师就无法核对来源）。
- **修法**：`package_skill.py` 新增 `write_sums()`，在 ZIP 同目录产出 `sha256sum -c` 格式的 `SHA256SUMS.txt`（读取已有条目合并、按文件名排序，便于多版本并存）；打包结果新增 `sha256sums` 字段；打包文件清单同时排除根目录的 `SHA256SUMS.txt`（它是发布产物，不该被打进包）。
- **整链路实测**：`package_skill.py` → `SHA256SUMS.txt` 条目与 ZIP 指纹一致 → `scripts/extract_package.py <zip> --sha256sums <清单> --out …` → `verification.status=passed`、`status=ok`。
- **测试夹具改为用真产物**：`test_update_flow.py` 的 `setUpClass` 不再手写清单，改为断言打包脚本确实产出了它、且条目等于 ZIP 的 SHA256；于是每次回归都在验证"发布 → 下载 → 核对"。
- **UPDATE.md 补上缺文件时怎么说**：若官方 Release 确实没有校验清单，**如实报告"本次无法核对压缩包指纹"**，不许跳过后声称已核对，也不许自编一份。
- **顺带修正漂移数字**：`references/schema.md` 的词典说明实测为——整本 10,836 条 → 本篇 **265** 条（原写 264）；HTML 约 **4.2MB** → 约 **376KB**（原写 4.4MB/375KB）；关闭查词约 **255KB**（原写 245KB）。
- **宿主提示词守门**：新增测试要求 `agents/openai.yaml` 的 `default_prompt` 含全部七项功能且顺序与 `plan.py` 菜单一致（这是宿主给老师看的第一句话，最易与 Skill 内菜单脱节却无人检查）。
- **实测**：`release_check.py` 五项全过（安装 `complete` · 120 文件 · 1.0.80；整链重放 9/9；材料包判读可声明 3 项 / 不能声明 5 项；闸门用例 40 项通过）；全套 **287 项测试通过**（1 项如实跳过）。过程中 `check_docs` 还当场抓出我在 ROADMAP 里把 `--sha256sums` 记到了打包脚本名下（应为 `extract_package.py`），已改正——这条检查确实在拦人。

## 复核（本记录写完后重打包）

- 本记录写在上面的运行之后，故重新打包 1.0.80 并重跑 `release_check.py`：五项仍全过、`check_install=complete`、`SHA256SUMS.txt` 条目与新 ZIP 指纹一致。

## 未覆盖边界

- `SHA256SUMS.txt` 只在**本地发布目录**产出；它是否随 GitHub Release 一起上传仍取决于发布者，文档已要求"没有就如实说无法核对"。
- 数字修正只覆盖 `references/schema.md` 的词典一节；README/ROADMAP 里历史版本小节保留当时的实测值（历史记录不追改）。
- `agents/openai.yaml` 的守门只查"七项功能名与顺序"，不校验该提示词的措辞与宿主实际展示效果。
- 没有真实 Windows / 宿主 / 真实试卷的实机证据（同前几版声明）。

---

# 1.0.79 中文 Windows 控制台与缺路径报错复查

## 本次实际执行

问题①的真机还等不到，但**中文 Windows 的控制台编码（cp936）**可以在本机模拟——而它恰恰是当年真正崩过的那一档（1.0.16 修的就是 cp1252/cp936 下的 `UnicodeEncodeError`）。顺着这条线又查出一批"报错不可照做"的问题。

- **补上 cp936/gbk 实跑回归**：`test_portability.py` 新增 `WindowsConsoleAndFailureMessages`，在 `cp936`、`gbk`、`cp1252` 三种 `PYTHONIOENCODING` 下实跑 `check_install.py`、`doctor.py --minutes 1`、`plan.py menu`、`cost.py examples/demo-reading.json`、`host_probe.py --json`：必须不崩、无 `Traceback`/`UnicodeEncodeError`，并且**中文输出仍能按 UTF-8 解出汉字**（`force_utf8()` 生效的直接证据）。三档全部通过。
- **查出并修掉"英文 errno 甩给老师"**：把 10 条"路径写错"的命令跑了一遍，`verify_output.py` 报 `ERROR: [Errno 2] No such file or directory: '…/index.html'`、`package_lesson.py` 直接打 `[Errno 2] …`（连 `ERROR:` 都没有），`quotes.py`、`answers.py`、`plan.py`、`build.py` 同类。根因是这些入口用 `except OSError: print(f'ERROR: {e}')` 直传异常；`test_messages.py` 的静态锁只覆盖 assert/raise 的字面量，所以一直没被抓住。
- **修法**：新增 `platform_tools.explain_error(error,next_step='')`，把 `FileNotFoundError`/`PermissionError`/`IsADirectoryError`/`NotADirectoryError` 转成"**找不到什么 + 最可能的原因 + 下一步**"，其余异常若原文已是中文则原样保留、否则加中文前缀。共 17 个脚本的入口处理器改用它（`verify_output`、`package_lesson`、`quotes`、`answers`、`plan`、`build`、`scaffold`、`parts`、`answer_audit`、`image_pages`、`extract`、`qa_report`、`read_acceptance`、`scope`、`bounded_command`、`audio`、`import_timed_text`）。
- **新增守门测试**：`test_missing_path_failures_explain_in_chinese` —— 10 条命令 × 3 种编码，逐条断言输出中**不得出现 `[Errno`、`No such file`、`Traceback`**，必须含中文、退出码正常；`test_explain_error_keeps_existing_chinese_messages` 锁住"中文说明不被重复包装"。实测修复前该测试会失败（英文 errno），修复后 11 项全过。
- **实测**：`release_check.py` 五项全过（安装 `complete` · 120 文件 · 1.0.79；整链重放 9/9；材料包判读可声明 3 项 / 不能声明 5 项；闸门用例 39 项通过）；全套 **286 项测试通过**（1 项如实跳过）。

## 复核（本记录写完后重打包）

- 本记录写在上面的运行之后，故重新打包 1.0.79 并重跑 `release_check.py`：五项仍全过、`check_install=complete`。

## 未覆盖边界

- 模拟 cp936 **不等于**真实中文 Windows：控制台代码页、`py -3` 启动器、路径分隔符、盘符与长路径、杀毒软件占用文件等都只能在真机验证。本版证明的是"脚本在这些编码下不会崩、中文可读、报错是中文明文"。
- 缺路径报错测试覆盖 10 条常用命令；其余脚本（如 `prepare_whisper.py`、`align_whisperx.py`）走的是各自的错误处理，未逐条纳入。
- 没有真实 Windows / 宿主 / 真实试卷的实机证据（同前几版声明）。

---

# 1.0.78 去重复核预筛与"发回报告"链路复查

## 本次实际执行

**一、`cost.review_pairs` 的平方级比较**

- 1.0.77 之后它是最后一个逐对比较的热点：对同类解析两两 `find_longest_match`（64 节/128 题 0.64s）。
- 修法：新增 `candidate_pairs()`，用倒排索引把候选缩到"至少共有一个 `min_common`（默认 10）字片段"的对——这是**必要**条件（最长公共片段 ≥10 就必然共享某个 10 字片段），不会漏报；`min_common<4` 时退回全量组合以保证结果不变。候选对按 `(i,j)` 升序返回，与原来双循环的插入顺序一致，排序后前 20 条与顺序都不变。
- 等价性实测（每节内容雷同的最坏夹具）：16 节 1800 条提示、32 节 7440 条、64 节 30240 条，**`hint_total` 与朴素扫描完全一致**；耗时 0.04→0.02s、0.16→0.09s、0.64→0.35s。
- 新增两条测试：`test_review_candidates_never_miss_a_real_shared_phrase`（用 difflib 逐对验证"真共享的对必须在候选里"）+ `test_review_pairs_hint_total_matches_the_plain_pairwise_scan`（整函数与朴素实现逐条比对，含前 20 条顺序）。
- **构建总体**：同一合成卷 16 节 0.25s / 32 节 0.61s / 64 节 128 题 **1.17s**（1.0.75 时 32 节 64 题为 4.26s）。

**二、"老师要发回的材料包"这条链路（问题①④）**

在干净目录跑 `scripts/smoke_report.py --no-browser --zip --workdir … --report-dir …`：

- 产物 `smoke-report-darwin.zip` 内**只有 3 个文本文件**：`smoke-report.json`、`smoke-report.md`、`host-probe.json`，合计 **12.8 KB**，**不含课件媒体与试卷内容**——与 `docs/WINDOWS.md` 里"只含报告文本，不含试卷与音频"的说法一致（这关系到老师的材料会不会跟着报告外流）。
- 本次运行如实记录：第 1 步 passed；第 2 步 `failed`（工作树在打包后又改过文件，`incomplete_install · errors=2`）；第 3 步 `failed`（`delivery=preview_only_browser_check_pending · audio=no_ffmpeg`，安装不完整导致）；第 4/5/7 步因上游失败而 `skipped`；第 6 步按 `--no-browser` `skipped`。**失败级联与跳过语义符合文档**。
- 用 `scripts/read_acceptance.py smoke-report-darwin.zip` 判读，输出"可以据此声明：（无）"，并逐条列出不能声明的 8 项，其中包括 **"Windows 实机验收已完成（本次报告来自 macos，不是 Windows）"** 与"真实试卷内容/答案/听力边界已验收（报告用的是仓库自带示例卷）"。判读口径与设计一致，没有把 skipped 当通过。
- 顺带确认：`smoke_report.py` 的模块级 `host()` 返回探测 dict、由内层 `host_step()` 负责格式化与定级，不是"解包出错"（一度怀疑，实测排除）。

- **实测**：`release_check.py` 五项全过（安装 `complete` · 120 文件 · 1.0.78；整链重放 9/9；材料包判读可声明 3 项 / 不能声明 5 项；闸门用例 39 项通过）；全套 **283 项测试通过**（1 项如实跳过）。

## 复核（本记录写完后重打包）

- 本记录写在上面的运行之后，故重新打包 1.0.78 并重跑 `release_check.py`：五项仍全过、`check_install=complete`。

## 未覆盖边界

- `review_pairs` 的收益取决于"有多少对真的共享 ≥10 字片段"：内容高度雷同（同一节被复制）时几乎全是候选，收益最小（64 节 1.8×）；真实卷若解析各不相同，收益更大。
- 材料包链路是在 **macOS** 上验的：Windows 上的路径分隔符、`py -3` 启动器与控制台编码仍属真机待验；ZIP 文件名会按平台变成 `smoke-report-windows.zip`。
- 没有真实 Windows / 宿主 / 真实试卷的实机证据（同前几版声明）。

---

# 1.0.77 词库裁剪热点与脚本侧时间构成

## 本次实际执行

1.0.76 之后重新做剖面（32 节：总计 2.73s），热点变成三处：`cost.duplicates` 1.00s、`cost.review_pairs` 0.60s、以及 **`build.py` 里词库裁剪的字典推导 0.81s（64 节 1.60s）**。

- **词库裁剪热点**：默认 `--dictionary-scope lesson` 要对整本 `offline-dictionary.json`（10,836 条）逐条判断 `k.lower() in tokens or (len(k)>1 and k.lower() in blob)`；`blob` 在 32 节时约 10 万字符，于是变成上万次长串子串搜索。
- **修法（结果不变）**：抽出 `build.scope_dictionary()`，先建 blob 的 2/3 字子串集合做**必要**条件预筛（词条若真是 blob 的子串，开头 2/3 个字也必然是），再做原来的 `in blob` 判断。等价性实测：1/8/32 节上 `identical=True`（262 条词条完全一致）；该项 32 节 **0.80s → 0.235s**。新增测试 `test_lesson_dictionary_scope_equals_the_straightforward_filter`：与朴素写法逐条比对，并覆盖单字键、两字键、多词短语与"本篇没有的词不得进入"。
- **顺带说明**：进一步压缩这一项的空间有限——剩余耗时来自"上万次子串搜索本身"，而短词条在 10 万字符 blob 里几乎必然出现（这正是原策略会保留它们的原因）；要再快就得改变词库裁剪**语义**，那属于产品决策，不在本版偷偷做。
- **脚本侧时间构成（32 节 / 64 题整卷，真实浏览器）**：`build` **0.68s** + `verify_output` **0.01s** + `scripts/browser_check.cjs` **45.7s**（`status=passed`、17 项检查、6 项如实跳过）。浏览器验收的缩放实测：1 节 10.0s、4 节 12.6s、8 节 17.6s、16 节 26.8s、32 节 45.7s ≈ **约 9 秒固定开销 + 约 0.27 秒/题**。
- **为什么不去优化浏览器验收**：那 17 项检查是"逐节真实切换 + 逐题真实点开/播放"的证据链；改用页面内 `el.click()` 或抽样题目都能显著提速，但会削弱"构建通过 ≠ 按钮可用"的那道保证。本版选择如实量化它，并把它写进 ROADMAP 状态表，而不是悄悄走捷径。
- **实测**：`release_check.py` 五项全过（安装 `complete` · 120 文件 · 1.0.77；整链重放 9/9；材料包判读可声明 3 项 / 不能声明 5 项；闸门用例 39 项通过）；全套 **281 项测试通过**（1 项如实跳过）。

## 复核（本记录写完后重打包）

- 本记录写在上面的运行之后，故重新打包 1.0.77 并重跑 `release_check.py`：五项仍全过、`check_install=complete`。

## 未覆盖边界

- 合成卷是复制同一节的合法内容；真实卷的词条分布不同，词库裁剪收益可能不同（`tokens` 越多，第一分支命中越多，越快）。
- `cost.review_pairs`（32 节 0.60s / 64 节 2.42s）仍是同类内容逐对比较，未做预筛；它的 `hint_total` 需要精确计数，不能抽样。
- 浏览器验收耗时随题目数线性增长，未做任何加速；投影/低配机器上可能更慢。
- 没有真实 Windows / 宿主 / 真实试卷的实机证据（同前几版声明）。

---

# 1.0.76 构建耗时剖面与重复检测优化

## 本次实际执行

问题②是"老师都说生成时间特别久"。这一版不靠感觉，直接测：把 `examples/demo-reading.json` 的节按 1/4/8/16/32 倍复制成合成整卷（节 id、段落 id、题号都改成唯一，内容合法），逐档计时并做剖面。

- **放大后的实测（1.0.75 代码）**：1 节/2 题 0.06s；4 节/8 题 0.18s；8 节/16 题 0.42s；16 节/32 题 1.31s；**32 节/64 题 4.26s**。增长明显超线性（16→32 节耗时 ×3.25）。
- **`cProfile` 定位**：13.9s（含剖面开销）里 `cost.analyze → duplicates` 占 12.8s，其中 `difflib.SequenceMatcher.ratio` 被调用 **67,584 次**、`find_longest_match` 占 9.2s——**唯一热点就是近似重复扫描的 O(n²) 两两比较**，而它只服务于"编写量报告"，不参与任何闸门。
- **修法（保持结果不变）**：用 difflib 文档明示的两个上界预筛——
  1. **长度上界** `ratio() <= 2·min(la,lb)/(la+lb)`：先按长度排序，内层一旦 `2·la < threshold·(la+lb)` 就 break（`la<=lb`，再往后更长）；
  2. **字符多重集上界** `quick_ratio()`（文档明确是 `ratio()` 的上界），比 `ratio()` 便宜得多。
  只有可能达标的组合才真的调用 `ratio()`；`near` 列表最终按 `(-saving, i, j)` 排序，与原来"i 主序 + 稳定排序"的顺序一致。
- **等价性（关键）**：把"朴素两两扫描"作为参考实现写进测试，在含 4 组近似解析（只差一个标点、长度不同）的夹具上逐条比对 `near_prose` 与顺序 → **完全一致**；32 节合成卷上同样 `identical=True`。
- **效果**：`duplicates()` 在 32 节上 3.28s → **0.23s**（14×）；整体构建 32 节/64 题 4.26s → **1.25s**，16 节/32 题 1.31s → **0.56s**。新增一条调用计数测试：长度差异大的夹具上 `ratio()` 调用 **0 次 / 22,791 对**（断言 <25%，留足余量）。
- **顺带修正旧说法**：ROADMAP 状态表原来写"脚本本身 <1 秒（合成大卷实测）"，该说法没有覆盖 64 题档，实测是 4.26 秒；现改为分档实测数字并注明主要时间仍在助手返工与轮次。
- **实测**：`release_check.py` 五项全过（安装 `complete` · 120 文件 · 1.0.76；整链重放 9/9；材料包判读可声明 3 项 / 不能声明 5 项；闸门用例 39 项通过）；全套 **280 项测试通过**（1 项如实跳过）。

## 复核（本记录写完后重打包）

- 本记录写在上面的运行之后，故重新打包 1.0.76 并重跑 `release_check.py`：五项仍全过、`check_install=complete`。

## 未覆盖边界

- 合成卷是**复制同一节的合法内容**，不等于真实整卷：真实卷的解析文字长度分布更分散，优化收益可能更大也可能略小；没有真实卷的耗时数据。
- 优化只针对近似重复扫描；`review_pairs`（去重复核清单）仍是同类内容的逐对比较（32 节约 0.6s），未做上界预筛。
- 脚本耗时从 4.26s 降到 1.25s **不等于"生成变快 3.4 倍"**：老师感觉的"特别久"主要来自助手编写与返工轮次（前几版已处理报错一次列全、示例陷阱、一页主流程）。
- 没有真实 Windows / 宿主 / 真实试卷的实机证据（同前几版声明）。

---

# 1.0.75 文档字段表与挖空报错复查

## 本次实际执行

沿用 1.0.74 的方法：把文档里"助手真会照抄"的字段表与示例拿出来，交给真正的校验器跑一遍。

- **发现 ①：文化背景字段表不全**。`references/teacher-options.md` 只列了 title/paragraph_id/quote/explanation/teaching_note/sources(title,url)，而 `culture.validate_culture` 还强制 `reading_connection`（且必须与 explanation 不同）与 `sources[].supports`。实测：按文档字段拼出的条目被拦"缺少 reading_connection"，补上后会被拦"缺少可用来源"（缺 supports）——**两轮白改，且落在"文化背景不许乱编"这条上**。
- **修法 ①**：字段表补全并注明"少任何一栏构建都会拦下并说明缺哪一栏"。
- **发现 ②：守门测试不能靠人抄字段名**。原来只打算用正则从 `culture.py` 抽 `item.get('x')`，这会漏掉用循环访问的 `teaching_note` 与 `sources[].supports`（实测只抽到 4 个键）。
- **修法 ②**：改成**行为推导**——从一份完整条目出发逐个删字段，看校验器拦不拦，得到真实必填集（实测得到 `title/paragraph_id/quote/explanation/reading_connection/teaching_note/sources/supports`），再断言 `teacher-options.md` 那段必须提到每一项。反向验证：把文档里的 `reading_connection`/`supports` 去掉，规则立刻报 `missing: ['reading_connection','supports']`。校验器将来加必填项而文档没跟上，测试会直接红。
- **顺带修掉一类"看不懂的报错"**：`build.py` 挖空校验原本用 `b['paragraph_id']`/`b['start']`/`b['end']` 直接取值，字段名漏写时抛裸 `KeyError`，CLI 只打 `ERROR: 'paragraph_id'`。现改为 `.get()` + 中文报错（第几个挖空、缺哪个字段、下标范围、字段名与下标的区别），并保留原有"指向了不存在的段落"措辞以免丢掉既有信息。新增三条反向用例（分别删 paragraph_id/start/end）。
- **文档示例守门扩展**：`teacher-options.md` 里的 `generation-plan.json` 示例（原来未被任何测试覆盖）已实测能被 `plan.py check` 接受，并接入测试。
- **实测**：`release_check.py` 五项全过（安装 `complete` · 120 文件 · 1.0.75；整链重放 9/9；材料包判读可声明 3 项 / 不能声明 5 项；闸门用例 39 项通过）；全套 **278 项测试通过**（1 项如实跳过）。

## 复核（本记录写完后重打包）

- 本记录写在上面的运行之后，故重新打包 1.0.75 并重跑 `release_check.py`：五项仍全过、`check_install=complete`。

## 未覆盖边界

- 字段表守门只覆盖 **culture_background** 与 **generation-plan** 两处（这两处是本轮实验命中、且校验器有明确必填集的）。`blanks`、`option_images`、`sentence_translations` 等字段的"文档字段表 vs 校验器"尚未逐个建立同类守门。
- 挖空报错的改进只覆盖缺字段名这一类；值类型写错（如 start 写字符串）本来就由原有断言给出中文说明。
- 没有真实 Windows / 宿主 / 真实试卷的实机证据（同前几版声明）。

---

# 1.0.74 文档示例与"一次列全"复查

## 本次实际执行

复查方法：把 `references/schema.md` 里那份**权威示例**当成助手会照抄的东西，抽出来真的跑一遍构建。

- **发现 ①：示例本身是陷阱**。示例出 `expected_question_ids: ["21"]`、A 节一题，看起来完整，但构建连撞三轮：
  1. `structure[0]: 需要 quote 引用支撑该结构判断` —— 示例的 `structure` 只有 `title/paragraph_ids/analysis`，没有 `quote`；
  2. 补上后又报 `A: 缺少「生词速查」内容（quick_words）`；
  3. 再补后又报 `A: 缺少「写作积累」内容（writing_bank）`。
  对一份只用两题、全篇一句话的示例，助手照抄要三轮才可能过；真实整卷只会更贵。**这正是问题②③要消除的系统性返工。**
- **修法 ①**：示例补上 `structure[].quote`、`quick_words`、`writing_bank`（用的是实测通过的原文与引文），并新增 `tests/test_schema_example.py`：每次发布都把示例原文抽出来真构建一次，断言 `status=structural_checks_passed`、`feature_coverage.status=passed`、`index.html` 存在。文档样例从此不可能再腐烂成陷阱。
- **发现 ②：功能覆盖的报错不是"一次列全"**。`validate_features` 用 `assert` 逐条抛，一节里少三项时每次只报第一个——与 `SKILL.md` 的承诺"构建会把本节全部问题一次性列出来、一次改完再重跑"不符。上面三轮就是这个缺陷的直接后果。
- **修法 ②**：改为收集本节/本卷全部缺项后一次抛出，格式与结构校验一致（`共 N 处问题，一次改完再重跑`，逐条列出并附 `--profile quick` 的替代路径）。同时把写作步骤的 `s['writing_steps']` 改成安全的 `s.get('writing_steps') or {}`，避免一次列全时因缺整块而抛 `KeyError`。
- **连带更新**：4 个原先断言 `AssertionError` 的用例改为断言 `ValueError`（`test_gates_fire`、`test_messages`、`test_preferences_install`、`test_paper_structure`）；新增反向用例 `test_feature_gaps_are_also_listed_in_one_pass`，要求三个缺项**必须出现在同一条报错里**且行数为 3。`SKILL.md` 第 5 条改为"结构校验与功能覆盖都会一次列全"。
- **实测**：`release_check.py` 五项全过（文档一致；安装 `complete` · 120 文件 · 1.0.74；整链重放 9/9；材料包判读可声明 3 项 / 不能声明 5 项；闸门用例 39 项通过）；全套 **274 项测试通过**（1 项如实跳过）。

## 复核（本记录写完后重打包）

- 本记录写在上面的运行之后，故重新打包 1.0.74 并重跑 `release_check.py`：五项仍全过、`check_install=complete`。

## 未覆盖边界

- 示例测试只覆盖 schema.md 的**第一段** JSON（整份 exam.json 示例）；第二段是七选五的单组片段，只断言它仍是片段、不接进构建。
- "一次列全"只覆盖结构校验与功能覆盖两个阶段；两者仍是先后执行（先结构、后功能），所以一份坏数据最少仍需两轮——把两阶段合并成一次需要先证明第二阶段遇到畸形结构时不会崩，尚未做。
- 没有真实 Windows / 宿主 / 真实试卷的实机证据（同前几版声明）。

---

# 1.0.73 一页主流程复查

## 本次实际执行

最初的需求里有一条是"先规划整体的 harness：第一步、第二步、第三步，然后用户需要去判断哪一些"。此前这套顺序散在 `SKILL.md`（44,256 字节）与 `references/` 各文档里，助手得自己拼，也容易跳步——**返工轮次正是问题②③（慢、费额度）的主要来源**。

- **新增 `references/harness.md`（第一步到第十三步）**：每步只写"谁做（🧑 老师决定 / 🤖 助手执行）→ 命令 → 判定标准 → 需要时再打开哪份文档"；标 🧑 的只有第 3 步（范围）与第 4 步（功能七项多选），并写明"未回答不得默认整卷/全部功能"。这一页是**路由而非副本**：细节一律指向原文档，避免两处说法漂移；页内出现的脚本与参数直接受 `check_docs.py` 的既有核对（脚本可达、参数真实）。
- **让它成为唯一必读入口**：`SKILL.md` 开头与 `README.md` 顶部各加一条链接（同时满足"references 无孤儿"检查）。
- **新增编号连续性规则**：`check_docs.py` 的 `step_sequence_problems`——主流程文档的「第 N 步」必须从 1 连续递增，配反向用例（好样例不误报、漏号与重号必须报）。
- **过程中抓到自己的一个静默失效缺陷**：该规则第一版用了 `^` 却忘了 `re.M`，于是只在字符串开头匹配到一个步骤，真实文档**根本没被核对**（`check_docs` 照样报"文档一致"）。反向用例当场失败，暴露了这一点；加上 `re.M` 后，`references/harness.md` 的 1…13 才真正被核对（实测输出 `['1'…'13']`、无问题）。这与 1.0.70 的 `declared_test_count` 是同一类问题：**检查器自己也会静默失效**。
- **把"只要听力"写进主流程**：第 3 步选 A 即只要听力，同一套 Skill，不需要另装听力版（对应问题⑥）。
- **实测**：`release_check.py` 五项全过（文档一致；安装 `complete` · 119 文件 · 1.0.73；整链重放 9/9；材料包判读可声明 3 项 / 不能声明 5 项；闸门用例 39 项通过）；全套 **271 项测试通过**（1 项如实跳过）。

## 复核（本记录写完后重打包）

- 本记录写在上面的运行之后，故重新打包 1.0.73 并重跑 `release_check.py`：五项仍全过、`check_install=complete`。

## 未覆盖边界

- 主流程页只规定**顺序与判定标准**，不能代替任何一步的实质工作；它减少的是"拼顺序、跳步、重复返工"的成本，不改变"内容仍要人工复核"的要求。
- 步骤编号规则只防漏号/重号/乱序，不保证步骤内容完整；步骤增删时仍要人工确认该页与 `SKILL.md` 不冲突（两处内容不复制正是为此）。
- Windows / 豆包 / WorkBuddy 真机与真实试卷仍未验证（同 1.0.71、1.0.72 的边界声明）。

---

# 1.0.72 Windows 验收清单实跑复查

## 本次实际执行

真机（Windows / 豆包 / WorkBuddy）仍然没有，但**清单本身**可以按原文在本机逐条跑：把 `py -3 scripts\x.py`
换成本机解释器，看输出是否就是文档写的那句话。1.0.72 把这件事实跑了一遍并固化成测试。

- **逐条实跑（在解压后的 1.0.71 包上，1.0.72 内容相同）**：
  - §3 `check_install.py` → `status=complete`、`version=1.0.71`、`checked_files=117`（与文档一致）。
  - §4 `doctor.py --minutes 20` → 默认输出先给中文提示再给 JSON，`capability=no_ffmpeg`、`next_step` 指向"直接接入原始音频"；文档"重点看输出 JSON 里的 capability"属实。
  - §5 `build.py examples/demo-exam.json output/demo --source-ledger examples/source-ledger.json` → 文档列的五个文件（`index.html`、`打开课件.html`、`exam.json`、`build-report.json`、`answer-audit.json`）全部出现（另有 `ECDICT-LICENSE.txt`）；`verify_output.py` → `status=passed`、`comparison=exact`。
  - §6 `node scripts/browser_check.cjs output/demo`：**没有** Playwright 时只打一句中文说明、写 `status=not_available`、不崩；**有** Playwright + Chrome 时 `status=passed`、`errors=[]`、17 项检查（6 项如实跳过）。
  - §7 `package_lesson.py`：两道门都缺时退出码 1，报错同时列出"缺少浏览器点击验收"与"人工复核清单未完成——缺少 qa-report.md"；加 `--allow-unchecked` 得 `preview_only_browser_check_pending`；补齐浏览器验收与 `qa-report.md` 后得 `browser_checked`（`delivery-report.json` 记 `qa_report.status=ok`）。
  - §9 第 7 步 `qa_report.py init` → 9 条待填；`check` 未填时退出码 1、`status=needs_fix`；逐条写 `结论：` 后 `check` → `ok`。
- **由此抓到一处文档偏差**：§7 原本只写"没有当期浏览器验收就失败"，实际同时要求人工复核清单。老师照文档补完浏览器验收、再跑一次才会撞上第二堵墙（多一轮返工，正是问题②"生成久"的一个来源）。§7 与"`browser_checked` 条件"两条 bullet 已改正，写明两道门都要过。
- **固化成测试**：新增 `tests/test_windows_checklist.py`（6 项）——按原文抓 `py -3 …` 命令，验证脚本与 `examples/` 输入存在；验证可复制的命令块里没有 `.sh`／`sudo`／`chmod`／`/tmp/`（只查代码块：正文里"不要求运行 .sh"的提醒不算违规）；真跑 §5 构建/核验、§7 两道门、§9 第 7 步，逐条断言文档承诺的输出。首次运行抓到上面那处偏差，修好后全绿。
- **实测**：`release_check.py` 五项全过（安装 `complete` · 118 文件 · 1.0.72；整链重放 9/9；闸门用例 38 项通过）；全套 **270 项测试通过**（1 项如实跳过）。

## 复核（本记录写完后重打包）

- 本记录写在上面的运行之后，故重新打包 1.0.72 并重跑 `release_check.py`：五项仍全过、`check_install=complete`、ZIP 内 `release-check` 残留为 0。

## 未覆盖边界

- **不是 Windows 真机证据**：本版证明的是"清单里写的命令与预期输出在本机（macOS）成立，且自动化可守"，`winget`/`where.exe`/Edge 双击/盘符与中文路径的**真实 Windows 行为仍未被执行过**。
- 清单测试只覆盖 §5/§7/§9 三类可离线复现的步骤；§1/§2/§4/§6 的环境判定依赖具体机器，只做文本与存在性检查。

---

# 1.0.71 Windows 清单与帮助文字复查

## 本次实际执行

问题①是"Windows 一定要能跑通"。真机验证只能等 Windows 机器，但**老师照着 Windows 清单做**这条路完全可以在本机查——文档缺陷会直接变成"卡在第 0 步"。

- **两个「第 0 步」**：`docs/WINDOWS.md` 顶部是"## 0. 一条命令跑完，把文件发回"，清单里又有"## 0. 打开正确的目录和终端"。老师说"第 0 步"指代不清。顶部那条改为不带编号的「先跑这一条：跑完把文件发回（推荐第一步）」，编号清单仍是 0–7（`## 1. Python` 起）。
- **一处交叉引用指错**：原文"下面第 9 节是逐步清单"——第 9 节其实是"自动 CI 证明了什么，还需要你证明什么"，逐步清单是 0–7 节。已改正。
- **写死的数字腐烂**：清单里写"当前约 27 项"测试，而本版实际 264 项。改为"项数以 CI 实际输出为准，不在这里写死——写死过 27，后来涨到两百多，差点让人以为 CI 只跑那么点"。这是**去掉重复来源**而不是再加一个要同步的数字。
- **新增规则并当场验证**：`check_docs.py` 增加 `numbered_section_problems`——同一份文档不得出现两个同号 `## N.` 小节；规则收窄到 `## 数字.` + 空格，因此 `## 1.0.69：` 版本小节与 `### 1.1 …` 子小节不会误报。先对全部 29 份文档扫了一遍：只有 WINDOWS.md 那一个真重复被命中，改完归零；`tests/test_check_docs.py` 加反向用例（好样例不误报、重复样例必须报）。
- **帮助文字去掉 POSIX 路径**：`scripts/extract_package.py` 的用法示例原为 `/tmp/new`、`/path/to/skill`、`/tmp/old`，Windows 老师或豆包/WorkBuddy 助手照抄会失败；改为普通目录名（`新版本目录`／`现有技能目录`／`备份目录`）并补一句 `"D:\新版本"` 的写法。
- **实测**：`release_check.py` 五项全过（文档一致；安装 `complete` · 117 文件 · 1.0.71；整链重放 9/9；材料包判读可声明 3 项 / 不能声明 5 项；闸门用例 38 项通过）；全套 **264 项测试通过**（1 项如实跳过）。

## 复核（本记录写完后重打包）

- 本记录写在上面的运行之后，故重新打包 1.0.71 并重跑 `release_check.py`：五项仍全过、`check_install=complete`、ZIP 内 `release-check` 残留为 0。

## 未覆盖边界

- **仍然没有在真实 Windows 上跑过**；本版只消除了"照着文档做会卡住/看错"的缺陷，不能当作 Windows 可用性的证据。判定仍以真机 `smoke_report.py --zip` 的报告为准。
- 编号唯一性规则只覆盖 `## N.` 这一种小节写法；`###` 层的编号不做强制（版本小节与子小节混排时规则会误报）。

---

# 1.0.70 发布包残留旧报告与文档结构复查

## 本次实际执行

- **复盘 1.0.69 的包发现真问题**：ZIP 里含根目录的 `release-check.md` / `release-check.json`——脚本从 1.0.68 起已把报告改写到 `dist/release-check/`，根目录这两个是 1.0.67 的残留（写着"通过 3 / 失败 2"、版本 1.0.67），会跟着包发给老师，让人误读成这一版验收没过。1.0.69 的 120 个 ZIP 条目里就有它们，只是当时没逐条翻包。
- **修法（两道闸门，同源）**：`scripts/check_docs.py` 新增 `stale_report_problems`（包根目录不得有验收报告），`scripts/package_skill.py` 的打包排除复用同一份 `ROOT_REPORT_RESIDUE`，`tests/test_check_docs.py` 加反向用例（干净目录不误报、md/json 都报、两处清单必须同源）。残留文件已删除。
- **顺手修好一条静默失效的检查**：README 的测试数量只在写成"测试总数 **N**"时才被核对，而 README 早已改成"**N 项测试通过**"，因此长期未被核对。现 `declared_test_count` 两种写法都认（读不到才算"没写"），并由它立刻报出 README 的 262 与实际 263 不符——证明这条检查真的在工作了。
- **文档结构归位 + 已知限制**：`ROADMAP` 的 1.0.69 条目回到版本列表（原落在状态表之后）、状态表标题更新到 1.0.70；新增**「已知限制」**表（跨页照片不自动裁切、图片选项不能点词查词、同一大题内分值混排、Word/WPS 文本框与表格答案与照片识别需人工核对、缺 ffmpeg/whisper 时听力只给静音候选），每条都指到代码证据。`docs/RELEASE-NOTES.md` 同步加「已知限制」一节给老师看。
- **实测**：`release_check.py` 五项全过（文档一致；安装 `complete` · 117 个文件 · 1.0.70；整链重放 9/9；材料包判读可声明 3 项 / 不能声明 5 项；闸门用例 37 项通过）；全套 **263 项测试通过**（1 项如实跳过）；ZIP 118 个条目，`release-check` 残留为 0。

## 复核（本记录写完后重打包）

- 本记录是在上述运行**之后**写进来的，所以重新打了一次包并重跑 `release_check.py`：五项仍全过、`check_install=complete`、ZIP 内 `release-check` 残留仍为 0（版本 1.0.70）。

## 未覆盖边界

- 仍只覆盖本机可自动化的部分：真实试卷内容、答案正确性、听力边界、Windows 与豆包/WorkBuddy 宿主端到端都没有变化。
- 「已知限制」表是能力边界声明，不自动核对；将来放宽某条边界时须同步改表（`check_docs.py` 抓不到这类漂移）。

---

# 1.0.69 本版说明与对应关系复查

## 本次实际执行

- 新增 `docs/RELEASE-NOTES.md`：面向老师的一页（四条课堂反馈怎么修、新增能力、省时间与额度、交付更严格、你要做什么），README 顶部链接；与《老师一页说明》（怎么用）分工明确。
- `docs/ROADMAP.md` 的「当前状态」表补一段**与发布验收的对应关系**：每一行由上表由 `release_check.py` 的五项检查覆盖（文档一致／安装完整／整链重放／材料包判读／闸门用例），避免"表里说有、命令却不查"。
- 实测（解压后的 1.0.69）：`release_check.py` 五项全过；全套 **260 项测试通过**（1 项如实跳过）；`check_install=complete`。
- 仍未实机验证 Windows 与宿主；`RELEASE-NOTES.md` 结尾已如实写明这一点，并说明真机报告是把"未验证"变成结论的依据。

## 未覆盖边界

- 更新说明是文档，无法自动核对"老师是否照做"；本版只保证它与代码行为一致（由 `release_check` 的重放与闸门用例间接守住）。
- Windows / 豆包 / WorkBuddy 仍需真机跑一次（同 1.0.56）。

---

# 1.0.68 发布验收一条命令复查

## 本次实际执行

- **新增 `scripts/release_check.py`**：一条命令依次执行——
  1. `check_docs`（文档一致）；2. `check_install`（安装完整）；3. `rehearse_first_use`（老师第一次使用的九步重放，可 `--no-browser`）；
  4. `smoke_report --zip` + `read_acceptance`（材料包判读，列出"可声明/不能声明"）；5. 闸门与一致性用例（结构闸门、交付闸门、文档检查、切句同步、首次使用重放）。
  任一项失败即非零退出；缺工具的项如实标 `skipped`，不计为通过；报告写到 `dist/release-check/`（`dist` 不进发布包）。
- **首次运行就抓到两处真问题**：`scripts/release_check.py` 自己没进文档（`check_docs` 拒收），以及版本未升导致 README 最新小节与 `VERSION` 不一致——正是这条命令要防的"手工漏步"。
- **实测**：五项全过（文档一致、安装 `complete`、整链重放 9/9、材料包判读可声明 3 项、闸门用例 34 项通过）；全套 **260 项测试通过**（1 项如实跳过）。
- **安装完整性**：`complete`。

## 未覆盖边界

- 这条命令仍只覆盖**本机可自动化的部分**；真实试卷、听力边界、宿主端到端仍靠真机材料包与人工复核。
- `skipped`（如无浏览器）不计为通过，报告里会写明跳过了什么；发布记录需要据此说明缺什么。
- Windows / 豆包 / WorkBuddy 仍需真机跑一次（同 1.0.56）。

---

# 1.0.67 发布前必跑固化复查

1.0.66 做出了可重放的整链命令，本版把它写进发布流程，防止"只在工作树跑过测试就发布"。

## 本次实际执行

- `docs/UPDATE.md` 新增「发布前必跑（维护者）」：在**解压出来的发布包**里执行
  `py -3 scripts\rehearse_first_use.py` 与 `py -3 scripts\smoke_report.py --zip`，两条都通过再发布；
  并写明"只在工作树里跑测试不算发布验收"、建议至少在目标老师的平台上跑过重放。
- `docs/ROADMAP.md` 状态表新增「发布前整链重放」一行：判定标准 `failed=0`；缺工具的步骤允许 `skipped`，但必须在发布记录里写明缺什么。
- **实测**（解压后的 1.0.67 包）：`check_install=complete`；`check_docs` 一致；重放脚本九步全过（见 1.0.66 记录）；全套 **260 项通过**（1 项如实跳过）。
- **安装完整性**：`complete`。

## 未覆盖边界

- 文档只能要求"跑过"，跑没跑仍取决于人；本版的做法是**把命令与判定标准写成可照抄的两行**，并让报告自己给出 `failed/skipped` 计数。
- Windows / 豆包 / WorkBuddy 仍需真机跑一次（同 1.0.56）。

---

# 1.0.66 首次使用重放复查

前面各版分别验证过每一环，但缺一条**从零开始、按文档顺序**的整链重放。

## 本次实际执行

- **新增 `scripts/rehearse_first_use.py`**：一条命令跑九步——安装完整性 → 老师选范围与功能 → 图片版试卷登记 → 图片版答案绑定 → 构建 → 产物核验 → 浏览器验收 → 人工复核清单 → 打包；每步记录真实状态与输出，写出 `first-use-report.json/.md`；缺工具标 `skipped` 且不算通过。
- **本机实测（带浏览器，工作目录在 /tmp）**：**9 步全过、0 失败、0 跳过**
  - 安装 `complete`（1.0.65、113 文件）；
  - 选范围与功能：整卷讲评，七项全记，开启批注/查词/速对答案/篇章精读；
  - 图片版试卷：2 张跨页照片 → `logical_pages=4`、`problems=0`；
  - 图片版答案：`image_transcription`，2 题；
  - 构建 `structural_checks_passed`（模板 1.0.65）、核验 `passed`；
  - 浏览器 16 通过 / 7 如实跳过、`errors=0`；
  - 人工复核清单 15 条，未填写 `check` 退出 1，填写后 15/15；
  - 打包 `browser_checked`。
- **降级路径**：`--no-browser` 时打包自动加 `--allow-unchecked`，状态记为 `preview_only_browser_check_pending` 并写明"无浏览器验收，按文档交付待验收版"。
- **跑出来的两个脚本自身问题**：`cwd` 切到工作目录后 `scripts/<脚本>.py` 这类相对路径失效（改为按包根解析）；两页夹具用同一张图被 `image_pages` 正当判为 `duplicate_page`（改为两页不同——否则测的是夹具的错，不是流程）。
- **自动测试**：新增 `tests/test_first_use_rehearsal.py`（`--no-browser` 重放，断言八步可重放、浏览器一步必须 `skipped`、报告写明边界）。macOS + Python 3.11.0b2 上 **260 项通过**（1 项如实跳过）。
- **安装完整性**：`complete`。

## 未覆盖边界

- 重放用的是**包内示例卷**（内容与答案都是合成夹具），因此证明的是"这条路径能走通"，**不证明**真实试卷识别、答案正确性与听力边界。
- 浏览器一步在 CI/无 Playwright 环境下会如实跳过；真机结论仍以材料包判读为准。
- Windows / 豆包 / WorkBuddy 仍需真机跑一次（同 1.0.56）。

---

# 1.0.65 文档交叉校对复查

同一件事被写在多份文档里（功能编号、产物清单、安装判断标准），写歪一处就会让老师看到互相矛盾的说法。

## 本次实际执行

- **新增三项跨文档检查**（`scripts/check_docs.py`）：
  1. **功能清单**必须与权威来源 `scripts/plan.py` 的 `FEATURES` 顺序与名称一致（位次/名称不符即报，并指出权威写法）；只引用前几项的片段不误报；
  2. **产物清单**：README 与 `docs/TEACHER-QUICKSTART.md` 中含 `index.html` 的代码块所列交付物必须一致（只比对固定交付物词汇表）；
  3. **安装判断标准**：`docs/SETUP.md`、`docs/WINDOWS.md`、`docs/TEACHER-QUICKSTART.md` 都必须写明"跑 `check_install` 到 `complete` 才算装上"。
- **第一版检查器太宽，被自己的测试纠正**：产物清单检查最初扫描所有代码块，把 README 的仓库目录树、`schema.md`、`FAQ.md` 也算成交付物，报了 23 条"缺失"；已收窄为"含 `index.html` 的代码块 ∩ 交付物词汇表"。
- **反向验证**：逻辑抽成 `feature_list_problems`／`install_claim_problems`／`deliverable_names`（纯函数），4 项用例分别覆盖"功能名写错／顺序写反／只说 check_install／把示例代码块当产物清单"，另加 1 项仓库整体一致用例。
- **实测**：`check_docs.py` → `文档一致：命令、参数、版本、链接与测试数量都对得上。`；`tests/test_check_docs.py` 11 项通过；全套 **259 项通过**（1 项如实跳过）。
- **安装完整性**：`complete`。

## 未覆盖边界

- 只校对可机械判定的三件事；同一事实的文字表述差异仍靠人读。
- 功能清单检查要求文档写出完整七项才比对。
- Windows / 豆包 / WorkBuddy 仍需真机材料包回传（同 1.0.56）。

---

# 1.0.64 收尾盘点（目标逐条对照）

## 本次实际执行

- **把目标逐条对照写成状态表**（[ROADMAP](ROADMAP.md) 的「当前状态」）：①Windows ②生成久 ③省 token ④豆包/WorkBuddy ⑤功能选择 ⑥只要听力 ⑦不许乱编，以及派生的结构由试卷决定、课堂反馈、分值、图片选项、跨页照片、文档一致性、交付闸门——每条都给出**证据在哪**（脚本 / 测试 / 验证记录 / 版本）。
- **区分"已实现+自动验证"与"缺真机"**：仅 ①Windows 与 ④宿主两项仍缺真机实跑；这两项已备好材料包（`smoke_report.py --zip` → 发回 → `read_acceptance.py` 判读），并在状态表里写明"不跑完不要写成已验证"。
- **README 增加状态指针与演示方式**：指向 ROADMAP 状态表；并给出用仓库自带**合成演示卷**一条命令看成品的方式（明确标注演示卷只用于看功能）。
- **回归确认**：`check_docs.py` 一致（脚本/参数/版本/链接/测试数量）；`tests/test_gates_fire.py` 与 `tests/test_delivery_gates_fire.py` 全通过；全套 255 项通过（1 项如实跳过）。
- **安装完整性**：`complete`。

## 未覆盖边界

- 状态表里的"证据在哪"指向的是**自动验证**；真实试卷、真实听力与真机宿主的结论仍以材料包判读为准。
- 表格是人工维护的（由 `check_docs` 保证版本/链接/参数一致，但不校验表格文字本身与代码同步）；新增能力时应同步补一行。

---

# 1.0.63 发布包整链自检复查（并新增老师一页说明）

代码侧加固收口后，这版做两件"给人用"的事：给老师一页说明，以及**在发布包本身**上把整条链跑一遍并留档。

## 本次实际执行（从 1.0.63 的 ZIP 解压后执行）

1. **安装**：`check_install.py` → `complete`，版本 1.0.63，113 个文件。
2. **计划**：`plan.py make --confirmed --range B --features 1,2,3,6` → 「范围：整卷讲评 · 开启的功能：批注、查词、速对答案、写作迁移」。
3. **构建**：`build.py examples/demo-exam.json OUT --source-ledger examples/source-ledger.json --plan plan.json` → `structural_checks_passed`，档位 `full`，模板核验 `passed`（1.0.63）。
4. **产物核验**：`verify_output.py` → `passed`。
5. **真实浏览器**：`browser_check.cjs`（本机 Chrome）→ **16 项通过 / 7 项跳过、`errors` 为空**；跳过项均为「功能未开启」或「本课件没有可测数据」（如 deep_reading 未开、无听力数据），如实记录、不计为通过。
6. **人工复核清单**：`qa_report.py init` 生成 **15 条**；未填写时 `check` **退出 1**；逐条填写真实结论后 `check` → `ok 15/15`。
7. **打包**：`package_lesson.py` → `browser_checked`（浏览器证据 + 已完成的 qa-report 同时满足）。
8. **材料包判读**：`smoke_report.py --no-browser --zip` 产出 `smoke-report-darwin.zip`，`read_acceptance.py` 判读为：可声明「安装完整／构建与核验通过／打包链路可用」；**不可声明**「浏览器点击已执行」（本轮用了 `--no-browser`）、「可交付 browser_checked」、「Windows 已完成」、「真实试卷与听力边界已验收」、「宿主端到端」。这正是这套判读要防的"把跳过当成通过"。

## 新增文档

- `docs/TEACHER-QUICKSTART.md`：老师一页说明（安装三条路径与"`complete` 才算装上"、开工前的两个问题、只要听力选 A、材料清单、产物清单、上课前抽查、遇到问题发 `smoke-report-windows.zip`、不要手工改 `index.html`）。README 顶部与 `SKILL.md` 均已链接。

## 未覆盖边界

- 本次自检用的是**仓库自带示例卷**，因此不能证明真实试卷识别、答案比对与听力边界；这三项必须在真实卷上做并写进 `qa-report.md`。
- 浏览器验收用 `--no-browser` 的材料包不含点击结论；带浏览器的材料包在 1.0.56 的记录里已验证过完整放行。
- **Windows / 豆包工作 / WorkBuddy 仍未实机验证**：需要在真机跑 `smoke_report.py --zip` 并把 zip 发回判读，这是本目标里唯一还缺外部条件的待办。

---

# 1.0.62 交付闸门反向验证复查

1.0.61 证明了结构闸门会拦；本版补齐交付这一层。

## 本次实际执行

- **新增 `tests/test_delivery_gates_fire.py`（14 项）**，全部断言"必须拒绝 + 报错文字说明该改什么"：
  - 打包闸门：缺浏览器证据、证据指纹属于上一版 HTML、媒体指纹与产物不符、检查项含 `failed`、`errors` 非空、缺 `qa-report.md`、清单未填（报错带「结论」）、ZIP 落在输出目录内；
  - 放行口径：`--allow-unchecked` 只给 `preview_only_browser_check_pending`，`delivery-report.json` 写明"未经验证"；证据齐全给 `browser_checked` 并如实记录 passed/skipped 与跳过项名称；
  - 产物闸门：模板指纹不一致、内嵌数据与 `exam.json` 不符、媒体文件被删（报错带文件名）；
  - 安装完整性：整仓复制判 `complete`；删 `assets/lesson.html` 或改 `VERSION` 判 `incomplete_install`。
- **修掉的四处测试自身问题**（注入缺陷没打中目标闸门）：改 `index.html` 会先被模板校验拦下（改为写错 `html_sha256`）；媒体指纹用例先触发 qa 缺失（先填清单）；演示卷无媒体目录（改为从 `verify_output` 资源表取文件，无媒体则如实跳过）；安装用例的残缺目录缺文件过多（改为整仓复制再删/改）。
- **自动测试**：macOS + Python 3.11.0b2 上 **255 项全部通过**。
- **安装完整性**：`complete`。

## 未覆盖边界

- 反向验证覆盖"闸门会拦"；**闸门是否该在此时拦**仍由设计决定（例如跳过项一律不算通过是刻意的）。
- 演示卷没有媒体，`test_missing_media_file_is_refused_with_its_name` 在本机会如实跳过；带音频/页图的同类断言在交付链测试里覆盖。
- 仍未实机验证 Windows / 豆包 / WorkBuddy（同 1.0.56，等材料包回传）。

---

# 1.0.61 闸门反向验证复查

本会话里我自己造成过两次**假检查**：占位符断言因条目正文含「非占位」而永真；文档检查器把同一行另一脚本的参数算错。合法输入通过 ≠ 检查会拦。

## 本次实际执行

- **新增 `tests/test_gates_fire.py`**：把 20+ 条闸门写成数据（名称 → 注入缺陷 → 期望报错片段），统一断言"必须拦住 + 报错文字带实际值"。
  覆盖：生词词形/次数、语境义引文与词形、结构依据与段落、句子精讲引文与译文、重复解析、占位文字、挖空落在半个词上、证据引文、答案不在选项、缺 answer_source、听力证据区间、`kind_preset` 非法、每小题分值大于总分、逐句译文条数不符与抄英文、图片选项字母不匹配、文化背景缺来源/引文编造。
- **覆盖率守卫**：枚举 `grounding.py` 与 `culture.py` 里的 `validate_*`，要求每个都在注册表里有反向用例；第一次运行就抓出漏配的 `culture.validate_culture`。
- **正面用例**：同一份示例卷在无缺陷时必须 `structural_checks_passed`，否则"拦住了"没有对照。
- **修掉的测试自身问题**（都是"注入的缺陷没打到目标闸门"，不是产品缺陷）：`word='repair'` 在引文 `repairs` 里其实存在（检查顺序先报引文不是子串）；`answer='D'` 在选项里存在，触发的是干扰项缺失；逐句译文只给 2 条时先触发条数不符，没走到「抄英文」那条；听力证据用例在无音频节上先报了别的错。
- **自动测试**：macOS + Python 3.11.0b2 上 **241 项全部通过**。
- **安装完整性**：`complete`。

## 未覆盖边界

- 覆盖的是**结构/证据闸门**；交付闸门（浏览器证据、qa-report、指纹）的反向用例分散在 `test_workflow.py`、`test_delivery_chain.py`、`test_option_images.py` 里，本版没有合并到一张表。
- 覆盖率守卫按函数名枚举 `validate_*`；写成别名的校验不会被发现。
- 仍未实机验证 Windows / 豆包 / WorkBuddy（同 1.0.56，等材料包回传）。

---

# 1.0.60 改写型重复交人工复查

1.0.59 能算准"逐字重复"，但"换一种说法讲同一件事"才是更容易漏的一类。

## 本次实际执行

- **先验证再设计**：拿一组真实改写（`先看首段的例子，再回到题干核对时间与动作。` vs `先读第一段的例子，然后对照题干检查时间和动作。`）测字符相似度，`difflib` 只有 **0.54**；把阈值降到 0.5 以下则无关内容全部涌入。**结论：字符级相似度不能用来判断中文改写。**
- **因此不做"相似度检测"，改为人工清单**：`cost.review_pairs()` 把同类内容（analysis / type_note / pitfall / strategy / context / note / why / explanation）按**位置 + 字数 + 开头 60 字**并排列出；`cost.py --duplicates` 直接打印。
- **弱信号（明确标注为"可能同源"）**：两处存在 **≥10 字连续相同**时给出提示与那截相同文字——这是"抄一句再改"的典型痕迹。实测示例卷：可稳定列出各字段条目，构造的"共用一句 + 各自补充"能被提示，而**纯改写不会被断言成重复**（仍留在人工清单里）。
- **构建报告**：`authoring_cost` 增加 `review_index`（各类条目与位置）、`same_phrase_total`、`same_phrase_hints`（前 5 组）；条目数 ≥8 或存在同源弱信号时写一条**不阻断**的待核项。
- **qa-report**：第 2 节自动多一条「去重复核：本卷 N 处…脚本判断不了换一种说法讲同一件事（连续相同片段提示 M 组）；请并排扫读，清单见 build-report.json 的 authoring_cost.review_index」。
- **自动测试**：`tests/test_cost.py` 新增 4 项（清单按位置列出、≥10 字相同给提示、**改写不被断言成重复**、构建报告带清单且不阻断）。macOS + Python 3.11.0b2 上全套通过。
- **安装完整性**：`complete`。

## 未覆盖边界

- 机器在这里**只做排列与弱信号**，不做判断；"是不是在讲同一件事"仍由人（qa-report 第 2 节）确认。这是刻意的边界，不包装成检测能力。
- "≥10 字连续相同"会漏掉完全改写、也会在合法复用固定表述（如题型术语）时提示，属参考信号。
- Windows / 豆包 / WorkBuddy 仍需真机材料包回传（同 1.0.56）。

---

# 1.0.59 重复内容检测复查

"省 token/省积分"里能纯脚本算准的一块：白写两遍。

## 本次实际执行

- **四类检测**（`cost.duplicates`）：逐字重复引文（≥20 字符）、跨节完全相同的解析文字（≥30 字符；构建只拦同一节内）、高度相似解析（difflib ≥0.9）、同一节里重复的词条。
- **实测（仓库示例卷）**：3 组重复引文、约 **288 字符**可省，清单给出位置与省字：
  - `sections[0].questions[0].evidence[0].quote` ↔ `sections[0].logic_steps[1].quote`（51 字符，省 51）
  - `sections[0].structure[0].quote` ↔ `sections[0].vocabulary[0].quote`（47 字符，省 47）
  - `sections[0].structure[1].quote` ↔ `sessions…sentences[0].quote` ↔ `writing_bank[0].quote`（95 字符，省 190）
- **长度下限**：先做过一版没有下限，示例卷立刻报出 44 组"完全相同解析"（都是两三个字的短串）——已给引文（20）与解析（30）都加下限，避免把短串重复刷成噪音。
- **构建报告**：`authoring_cost` 增加 `estimated_saving/repeated_quotes/exact_prose/near_prose/duplicate_entries`；重复量 ≥200 字符且占需编写量 ≥10% 时写一条**不阻断**的提示进 `warnings` 与 `pending_items`（qa-report 会列出）。
- **口径写进输出**：`重复内容检测只做字面比较；相似不代表可删，删改前要确认教学上确实重复。` 脚本不自动删除、不把相似度当错误。
- **自动测试**：`tests/test_cost.py` 新增 6 项（重复引文与省字计算、跨节近似、同节重复词条、干净卷子零报告、`analyze` 汇总与提示、构建报告只提醒不阻断）。macOS + Python 3.11.0b2 上全套通过。
- **安装完整性**：`complete`。

## 未覆盖边界

- 只做**字面**比较：换一种说法讲同一件事（真正的重复讲解）检测不到，那属于语义复核，仍归 qa-report 第 2 节人工。
- 相似度阈值 0.9、下限 20/30 是经验值；调高会漏、调低会吵。
- 同一句原文被多处以不同用途引用（structure / sentences / writing_bank）是**合法**的，脚本只报"它出现了几次"，不判断该不该合并。
- Windows / 豆包 / WorkBuddy 仍需真机材料包回传（同 1.0.56）。

---

# 1.0.58 文档一致性复查

二十多轮改动后，文档漂移已经开始伤人：老师照着文档敲的命令可能报"没有这个参数"。

## 本次实际执行

- **新增 `scripts/check_docs.py`**，五类可验证检查：脚本可达（双向，内部工具白名单）、命令行参数真实存在、版本三处一致、`references/` 无孤儿、README 最新小节的测试数量。
- **首次运行抓出 6 处**：
  1. `README.md` 把构建参数 `--profile` 记在 `scripts/preferences.py` 名下（实际属于 `scripts/build.py`）；
  2. `SKILL.md` 里的 `--plan` 归属 `plan.py`（实际属于 `build.py`）；
  3. `SKILL.md` 里的 `--source-images` 归属 `image_pages.py`（实际属于 `answers.py`）；
  4. `docs/SETUP.md` 里的 `--network` 归属 `check_install.py`（实际属于 `host_probe.py`）；
  5. README 写的测试总数与实际差 37 项；
  6. 参数归属本身过粗（同一行多个脚本时全部算到第一个）——检查器改为**按"同一行里前面最近的脚本"归属**，误报消失。
- **修复方式**：前四处是文档没写清脚本路径（只写 `build.py`／`answers.py`），已补成 `scripts/…`；测试数量已更正；检查器按最近脚本归属并只在**最新版本小节**核对数量（旧小节是历史数字）。
- **接入测试**：`tests/test_check_docs.py` 7 项，既有"仓库文档必须一致"，也有**反向验证**（同一行两脚本的参数归属、假参数会被抓、`choices` 能解析），确保检查器不是永远返回 ok。
- **实测**：修复后 `python3 scripts/check_docs.py` → `文档一致：命令、参数、版本、链接与测试数量都对得上。`
- **安装完整性**：`complete`。

## 未覆盖边界

- 只检查**可验证**的一致性（路径/参数/版本/链接/数量）；文字表述是否过时、示例是否仍最优，仍靠人读。
- 参数检查只看 `scripts/<脚本名>.py` 形式的引用；纯文字提到的脚本（如"构建脚本"）不在范围内。
- Windows / 豆包 / WorkBuddy 仍需真机材料包回传（同 1.0.56）。

---

# 1.0.57 逐句译文展示复查

1.0.54 完成数据与校验层（每句一条、句数不符阻断、未译进待核项），本轮补展示：老师课堂上要的两种用法都可用。

## 本次实际执行

- **两种形态**：段落旁新增「逐句译文」开关——打开后整段逐句（每句一行：原文句 + 中文）；**原文句本身可点**，点一下只看该句译文，再点同句恢复整段逐句，关掉开关全部收起。
- **不静默留白**：未翻译的句子在页面写「本句未译（构建报告里已列为待核项）」；切句与数据条数不一致时直接写"对不上，请重新构建核对"，拒绝显示错位译文。
- **不泄漏答案**：`hasHiddenBlanks` 生效时逐句译文与段落译文一起被隐藏，文案提示"先揭示本段听写空"；本节重置会清掉 `ui.sentenceMode`。
- **两边切句一致（关键契约）**：模板 JS 新增 `splitSentences`，与 `scripts/sentence_split.py` 同一套规则。新增 `tests/test_sentence_split_sync.py`：**从模板里抽出函数源码**丢给 node，对同一份语料（`Mr. Li`、`3.5`、引号句、`...`、`U.S.`、换行、空串等 12 条）逐句比对 Python 与 JS 的结果——否则会出现"构建通过但页面译文错位"。
- **真实浏览器**：新增 `sentence-translations-display`（行数=分句数、未译有标注、点句只剩一行、再点恢复、关闭收起）；六题型合成夹具 23 项通过。
- **夹具**：`make_browser_fixture` 给第一节第一段加逐句译文，**最后一句故意留空**，用来验证"未译"如实显示并进入待核项。
- **自动测试**：macOS + Python 3.11.0b2 上全套通过。
- **安装完整性**：`complete`。

## 未覆盖边界

- 逐句译文只在**有该数据的段落**出现；没写的段落不显示开关（不猜、不自动翻译）。
- 单句模式下原文的其他标注（听写空、线索高亮、文字批注）仍在左侧原文列显示，逐句块只做对照；两者不互相替代。
- 真实卷的译文质量仍须人工核对（qa-report 第 2 节那条）。
- Windows / 豆包 / WorkBuddy 仍需真机材料包回传。

---

# 1.0.56 真机验收材料包复查

目标里"Windows 必须 ok"「豆包/WorkBuddy 表现」一直挂着"未实机验证"。障碍不只是设备，还有**流程缺口**：跑完不知道发回什么，收到的人也不知道这份报告能证明什么。

## 本次实际执行

- **一键产出**：`smoke_report.py --zip` 跑完 7 步后，把 `smoke-report.json`、`smoke-report.md`、`host-probe.json` 打包为 `smoke-report-<平台>.zip`（只含报告文本，不含课件媒体与试卷内容），并打印判读命令。宿主探测结果同时落盘（第 3 步明细里也带出三条安装路径的可用性）。
- **严格判读** `scripts/read_acceptance.py`（支持 `.json` / 目录 / `.zip`）输出两张清单：
  - 可声明：安装完整、构建与核验通过、浏览器点击已执行、可交付 `browser_checked`、来自 Windows 且流程全过时才算 Windows 验收完成；
  - 不可声明：`skipped`/`failed` 的下游项、非 Windows 报告的 Windows 结论、**真实试卷/答案/听力边界**（报告用示例卷）、**豆包工作/WorkBuddy 端到端**。
- **实测**：本机（编辑后未重新打包、清单过期）跑 `--no-browser --zip` → 通过 1 / 失败 2 / 跳过 4，判读输出"可以据此声明：（无）"，并逐条列出失败与跳过步骤；`--no-browser` 的报告被明确标为**不能**支持"按钮与播放已验证"。重新打包后同一命令全绿，判读给出安装/构建/核验/打包声明，同时仍把"真实卷、宿主、Windows"列为未证明。
- **真跑出来的第二个 bug（已在 1.0.56 内修掉）**：在解压包里跑一次带浏览器的验收包，第 7 步「打包交付」**失败**——因为 1.0.44 起打包同时要求浏览器证据与 qa-report.md，而自检脚本没有（也不该有）人工复核结论；原逻辑用 allow_unchecked=not browser_ok，浏览器通过时反而走了完整闸门。现在自检一律按**待验收版**打包并写明原因（示例卷自检不填人工复核清单，qa-report.md 必须由人写）；判读据此区分：可以声明「打包链路可用」，**不能**声明「可交付 browser_checked」。
- **文档与 CI**：`docs/WINDOWS.md` 顶部新增「一条命令跑完，把文件发回」；`docs/SETUP.md` 同步；`.github/workflows/compatibility.yml` 的三个平台体检任务各加一步判读，日志里直接给出该平台的结论。
- **自动测试**：新增 `tests/test_read_acceptance.py` 9 项，其中一项**真跑一次** `smoke_report.py --no-browser --zip` 并断言产物可判读、`host-probe.json` 落盘、zip 可读且不夸大。
- **安装完整性**：`complete`。

## 未覆盖边界

- 材料包能证明的是**这台机器上的工具链**；它不覆盖真实试卷、听力边界、教学质量，也不覆盖豆包工作/WorkBuddy 的宿主链路——判读里写死了这三条"不能声明"。
- **仍需你（或老师）在真机上跑一次**并发回 zip，才能把目标里的 Windows/宿主待办改成"已验证"。CI 的 Windows runner 只能证明代码路径，不等于老师的电脑。
- 逐句译文展示层仍未做（口径待确认）。

---

# 1.0.55 宿主适配复查（沙箱拦网络）

真实反馈截图：WorkBuddy 里助手先 `git clone github.com` 被沙箱 TLS 拦下、再直连失败，最后靠网页抓取绕过——这些轮次与额度是白花的，因为探测脚本只说「安装不完整」，没给可照做的路径。

## 本次实际执行

- **三条安装路径**（`host_probe.install_paths`，按可靠性排序）：`teacher_uploaded_zip`（最稳；没确实拿到附件写 `unknown`，不猜）→ `raw_files_fetch` → `git_clone`；每条都带「怎么做」。
- **可选网络探测** `--network`：只发 **HEAD**、`timeout=4`、不读响应体、不写盘；HTTPError 也算网络通。不加开关时 `available='not_probed'`、`network_probed=False`。实测本机：`raw_files_fetch=yes`、`git_clone=yes`（本机网络畅通）；沙箱拦 git 的情形由测试用假 `urlopen` 覆盖为 `no`。
- **指引**：安装不完整时先输出「请老师上传 ZIP → 抓 raw 文件 → 不要反复试 git clone」，再补一条「必须 `check_install.py` 到 `complete` 才算装上；只能说**完整包下载受限，尚未完整安装**」。空目录实测：状态 `incomplete_install`，指引包含上述全部要点。
- **不下载的证明**：测试把 `urllib.request.urlopen` 换成记录器 + 假响应，断言方法为 `HEAD`、超时 ≤10 秒、且一旦读取响应体就失败。
- **文档**：`docs/SETUP.md` 把「老师上传 ZIP」写成网络受限时的第一条路；`references/host-compatibility.md` 写入探测字段与三条路径。
- **自动测试**：新增 `tests/test_host_probe.py` 8 项。macOS + Python 3.11.0b2 上全套通过。
- **安装完整性**：`complete`。

## 未覆盖边界

- **仍未在真实豆包工作/WorkBuddy 上跑过**：本版只做到「探测 + 指引 + 禁止谎报」；真实宿主的附件接口、预览限制、脚本执行权限仍需实机确认（目标里那项待办）。
- `teacher_uploaded_zip` 的可用性只能由老师是否真的上传决定，探测无法代替。
- 逐句译文展示层、Windows 实机同样待外部条件。

---

# 1.0.54 逐句译文数据层复查

课堂反馈第 4 条「没有句子翻译」：展示层做成"整篇逐句"还是"点某句看该句"尚未确定，但两者都依赖同一份对齐数据。本版先做数据与校验层。

## 本次实际执行

- **新字段**：`paragraph.sentence_translations`，每句一条、顺序与原文一致。
- **切句器** `scripts/sentence_split.py`：句末 `.` `!` `?` `…`（可带引号/右括号）之后必须是**空白或行尾**才算一句；内置常见缩写表。实测：`Mr. Li is 14 years old. He likes Chinese knots! What about you?` → 3 句；`The price is 3.5 yuan.` 不误切；`He said, "I am ready." Then he left.` → 2 句。
- **校验（阻断）**：条数与切出的句数不一致 → `逐句译文有 1 条，按句切分原文是 3 句`；整条为空数组 → 拒绝；译文里没有中文 → `不能把英文原句抄一遍`。
- **校验（不阻断但必须可见）**：未翻译的句子写空字符串占位，构建把 `章节 A 段落 p1 有 1 句未翻译（第 [2] 句，共 3 句）` 写进 `warnings`，并**进入 `pending_items`**（顺带修好一个既有缺口：`validate()` 的警告此前写在「已记入待核项」却从未进入待核项）。
- **qa-report**：构建产物含逐句译文时，第 2 节自动多一条「逐句译文：每句译文与原文分句一一对应，未译句子已在待核项列出（由构建校验对齐，语义仍须人工核对）」。
- **成本统计**：`sentence_translations` 计入 `cost.py` 的作者编写量，并接受同一套占位符检查。
- **自动测试**：新增 `tests/test_sentence_translations.py` 8 项。macOS + Python 3.11.0b2 上全套通过。
- **安装完整性**：`complete`。

## 未覆盖边界

- **展示层未做**：页面还没有"逐句译文"的显示方式，等口径确认（整篇逐句 / 点句显示）。数据已就绪，展示是纯前端改动。
- 切句按标点规则，不解析引号内的省略句（如 `"..." he said.`）——这类句子会被切成两句，作者按切分结果写译文即可；规则固定，所以不会错位。
- Windows/豆包/WorkBuddy 仍未实机验证（同前）。

---

# 1.0.53 跨页照片复查

老师给的真实卷面照片是**翻开的书**：一张横版图（2406×1743）里并排两页。此前页清单是"1 张 = 1 页"，漏页与页序核对看不出这一点。

## 本次实际执行

- **登记**：`image_pages.py` 新增 `--spread`（全部跨页）、`--spread-files`（只标指定文件）、`--pages-per-image`（默认 2）。清单写入 `layout=spread`、`pages_per_image`、`logical_pages`，逐页写 `spread`/`pages_in_image`；竖版图片被标记为跨页时报 `spread_not_landscape`。
- **语义**：`page_count` 仍是**图片张数**（指纹与交付以文件为准），`logical_pages` 是**真实页数**；两者都进核对记录。
- **构建**：`quality_gate` 对跨页原卷给一条**不阻断**的警告 `source_spread_pages`：「3 张图共 6 页，逐页核对题号与漏页时必须左右页分别看」。台账页指纹与集合指纹的校验逻辑不变（仍按文件核对）。
- **实测**（合成图，240×160 横版 / 120×200 竖版）：全部跨页 → `page_count=2`、`logical_pages=4`；混合批次 → 只标指定文件、`logical_pages=3`；竖版误标 → `spread_not_landscape`；未声明跨页 → 不出现 `layout`/`logical_pages`（行为不变）；跨页提醒在**有台账时**出现且不阻断（同用例先验证无台账时 `source_pages_digest` 仍会拦下）。
- **自动测试**：`tests/test_image_inputs.py` 新增 5 项（共 23 项）。macOS + Python 3.11.0b2 上全套通过。
- **文档**：`references/image-inputs.md` 新增「跨页照片（拍翻开的书）」小节，含两条命令与"张数 vs 页数都要写进核对记录"的要求。
- **安装完整性**：`complete`。

## 未覆盖边界

- **不自动裁切**：本版只登记与提醒，不把一张跨页图切成两张（纯标准库无法可靠解码 JPEG；需要裁图时由老师或助手用系统工具手动裁）。
- 页序核对仍需人工按左右页看；机器只做到"张数/页数/指纹/重复/缺号"这一层。
- 句子翻译仍未做（口径待确认）；Windows/豆包/WorkBuddy 仍未实机验证。

---

# 1.0.52 分值显示复查

分值自 1.0.47 起可从试卷标题读进台账与骨架（`score_per_question`/`score_total`、`paper_info.full_score/minutes`），但页面一直没显示。

## 本次实际执行

- **数据**：`scaffold` 把卷首说明写进 exam.json 的根级 `full_score`/`exam_minutes`；每节的 `score_per_question`/`score_total` 沿用 1.0.47 的解析。
- **页面**：
  - 表头显示「满分 120 分 · 考试用时 90 分钟」（来自试卷卷首说明）；
  - 每节标题显示「本大题 10 分 · 每小题 1 分」，听力节同样显示；
  - 用 `textContent` 断言卷首（打印样式下 `<p>` 可能被隐藏，`innerText` 会漏读——这正是第一次回归失败的原因）。
- **校验**：`score_per_question`/`score_total`/`full_score`/`exam_minutes` 必须是**大于 0 的数字**（`0`、负数、布尔、字符串都报错）；`score_per_question > score_total` 报错并说明"请核对试卷标题"；考试级字段统一用 `ValueError`（与其它输入错误一致）。
- **不阻断的提示**：标题说"每小题 1 分、共 30 分（按此应有 30 题）"而本节只放 2 题时，`build-report.json` 的 `warnings` 给出一条可照做的提示：`若这次只做部分小题（如阅读理解只做 A 篇）属正常，否则请核对题号或分值`。**没有**升级成阻断——"只做阅读 A"是老师选过的范围。
- **真实浏览器**：新增回归 `scores-and-exam-info-render`（卷首满分/用时、每个有分值板块的标题），合成初中卷 **25 项检查全过、0 跳过**。
- **自动测试**：`tests/test_scaffold_structure.py` 新增 3 项（卷首与分值进骨架、异常分值被拒、对不上只提醒不阻断）。macOS + Python 3.11.0b2 上 **189 项全部通过**。
- **安装完整性**：`complete`。

## 未覆盖边界

- 只展示**试卷标题里写出的**分值；原卷没有写分值的卷子，页面不显示（不猜）。
- 小题单独给分（同一大题内不同分值，如"每小题1分，其中第10题2分"）目前无法逐题表达——只有 `score_per_question` 一个值。
- 双页照片标注、句子翻译仍未做；Windows/豆包/WorkBuddy 仍未实机验证。

---

# 1.0.51 图片选项复查（初中卷「听句子选图」）

初中卷的听说应用第一节、部分图表题选项是图片；此前 `options` 只能文字，助手只能写"图A/图B"。

## 本次实际执行

- **新字段**：`question.option_images = {"A":"assets/q1-a.png",...}` 与可选 `option_alts`；`options` 里保留同样字母（值可为空），文字与图片选项可混用。
- **构建**：新增 `media_map()` 复制"字母 → 图片"，命名 `assets/Q<题号>-opt-<字母>.png`，写入 `resources`。
- **跨工具媒体指纹**：`verify_output.py` 与 `scripts/browser_check.cjs` 都加入 `option_images` 的值。单独测了这条契约：构建后 node 端收集的媒体集合与 `verify_output` 完全一致（1.0.37 就是这里漏一处，导致带多页页图的整类课件永远被 `package_lesson` 拒绝）。
- **校验**：含 `option_images` 时必须是**非空对象**；字母必须在 `options` 里；`options` 中既无文字又无图片的字母要报错；图片路径不能为空。实测三类错误都被拦下（`没有对应选项的字母` / `既没有文字也没有图片` / `option_images` 非空对象）。
- **真实浏览器**：新增 `option-images-render-and-select`——逐张断言 `img.complete && naturalWidth>0`（真的加载出来），并点击第一张图片选项断言仍能点选；合成夹具 5 项测试全过。
- **自动测试**：新增 `tests/test_option_images.py` 5 项（构建复制与指纹、跨工具媒体一致、三类校验错误、文字与图片混用、真实浏览器加载与点选）。macOS + Python 3.11.0b2 上全套通过。
- **文档**：`references/image-inputs.md` 增加「图片选项」小节（把 A/B/C 小图分别裁出来；页图仍登记在 `origin.page_images`）；`references/schema.md`、`SKILL.md` 写明不要用"图A/图B"文字代替图片。
- **安装完整性**：`complete`。

## 未覆盖边界

- 图片选项**没有**可点单词，因此没有"带读与翻译"（课堂反馈 2 针对的是文字选项）。
- 图片需要老师/助手自己裁切；本版不自动从整页照片里切分选项小图。
- 分值展示、双页照片标注、句子翻译仍未做；Windows/豆包/WorkBuddy 仍未实机验证。

---

# 1.0.50 课堂反馈复查（字号 / 选项查词 / 短语固搭）

老师已在班上使用，反馈四条 + 一个问题（含 WorkBuddy 安装截图两张）。

## 本次实际执行

- **反馈 1「答案解析字体不能调大」**：`.analysis-panel{font-size:17px}` 与 `.analysis h4{font-size:17px}`、`.analysis-panel .type-note{font-size:14px}`、`.answer-evidence{font-size:15px}`、`.option-reason strong{font-size:14px}` 都是**固定像素**，而字号控件只改 `--size`，所以解析区不响应。已全部改为 `calc(var(--size) - …)`。真实浏览器回归 `analysis-font-scales-with-font-control`：打开解析→连点两次放大→断言 `#q-… .analysis-panel` 的 computed font-size 变大，再调回并断言复原。
- **反馈 2「完形填空选项单词点一下没有带读和翻译」**：选项文字本来就带 `.word` 节点，但点击处理器先命中 `[data-action="choose"]`（选择选项）而返回；「选项辨析」里更是**没有渲染选项原文**。现在：解析展开后点选项里的单词＝查词+系统发音（未展开时仍是点选，保持既有规则）；「选项辨析」补上选项原文并同样可点词。回归 `option-word-opens-dictionary-after-reveal` 断言点词后浮窗出现、显示该词、带「系统发音」按钮，且解析不会被关掉。
- **反馈 3「短语和固搭识别不出来」**：划选在课堂态由 `#v10Selection`（划选工具）接管，它先 `hideQuick()` 再 `stopImmediatePropagation()`，查词浮窗永远不会出现；而它对多词短语只按整串查离线词库，查不到就**不显示任何义项**。现在按链式查询：本篇语境义 → 整串通用义 → **按词查（明确标注"按词查「word」"）**，并显示课件里该词的**固搭/搭配**；确实没有时如实写"离线词库未收录这个短语：可点单个单词查，或按「查词 / 朗读」详查"。回归 `selection-shows-phrase-meaning-or-collocation` 用跨两个单词节点的真实划选断言划选工具必须给出义项说明。
- **三条回归都必须还原状态**：新检查会打开解析/浮窗/划选工具，起初污染了后面的 `only-one-analysis-open-per-section`（在普通演示课件上直接失败）。现在每个新检查收尾都把解析展开状态、浮窗、选区还原，普通演示课件 17 项通过、3 项如实跳过。
- **反馈 4「没有句子翻译」**：未改。现状是**段落译文**（`paragraph.translation`，必填）与**句子精讲**里的译文（`sentences[].translation`）；老师要的若是"整篇逐句译文"或"点某句显示该句译文"，做法不同，需先确认口径（见下）。
- **「只处理听力的 skill」**：同一套 Skill 的范围 **A**（`plan.py menu` 回复 A；命令行 `plan.py make --confirmed --range A`）。实测：选 A 后 `generation_scope.section_ids=['L1']`、`mode=intensive`、只保留 1 节、音频照常内嵌。`SKILL.md` 已写明"不需要另装一个听力版"。
- **安装截图（WorkBuddy）**：`git clone github.com` 被沙箱 TLS 拦下、`github.com` 直连被拦但网页抓取可用。`references/host-compatibility.md` 增加实测处置：**优先让老师把发布 ZIP 作为附件上传**，其次逐个抓 `raw.githubusercontent.com`，且必须 `check_install=complete` 才算装上。
- **自动测试**：macOS + Python 3.11.0b2 上 **181 项全部通过**；初中夹具 23 项浏览器检查全过。
- **安装完整性**：`complete`。

## 未覆盖边界

- 反馈 4（句子翻译）未实现，口径待确认。
- 单词发音依赖系统语音（`speechSynthesis`）；没有系统英语语音的环境只有释义、没有带读。
- 固搭来自课件里作者填写的 `collocations`，不是自动抽取；课件没写固搭时，划选只到"按词查"这一层。
- 图片选项、分值展示、双页照片标注仍未做（同 1.0.49）。
- 仍未在真实 Windows / 豆包工作 / WorkBuddy 上跑过（同 1.0.16）。

---

# 1.0.49 初中题型与"宣告优先"复查

用户第二次指出"强制生成听力、阅读理解、完形填空和语法填空"，并举例**初中卷会出现短文填空**。

## 本次实际执行

- **定位真正的原因**：代码已在 1.0.46/1.0.47 改为按试卷结构生成，但**指令层仍在强制六题型**——`SKILL.md` 与 `references/regression.md` 写着"章节顶栏只显示本卷实际存在的题型入口：听力、阅读、七选五、完形、语法填空、写作"，`README.md` 同款两处，速对答案也写成"板块仅按听力、阅读、七选五、完形填空、语法填空聚合"。助手读的就是这些句子。
- **逐处改为按试卷**：上述五处 + `references/generation-planning.md`（指定板块的举例改为听说应用/语法选择/配对阅读/短文填空/读写综合）与 `references/dependency-recovery.md`；并写明"不要套用固定六种题型，也不要把试卷上没有的板块加上去"。
- **`scope.py` 别名补齐**：新增 听说应用/听力理解（listening）、任务型阅读（reading）、配对阅读/信息匹配/阅读填空（seven）、语法选择（cloze）、短文填空/词汇运用/单词拼写（grammar）、读写综合/读后续写/概要写作（writing）；匹配同时按 `id`／`kind`／`group` 命中，所以试卷自己的名字即使不在别名表也能选中。
- **宣告优先**：把"呈现方式"收敛成唯一判断源 `preset()`，优先级 = `kind_preset` 宣告 > 题型名/别名 > 内容推断 > custom；`is_listening/is_writing/is_grammar` 只看它。改前 `is_writing = preset=='writing' or 有写作字段`，于是夹具里那节"阅读理解"（复用了带 `writing_steps/teacher_model` 的素材）被渲染成 **`四、阅读理解 · 任务型阅读 2 项写作`**；改后为 `2 题`。Python 与两份 JS 副本同步修改。
- **听力标签**：只有小标签是数字时才加 `Test `，初中卷不再出现"Test 听说应用"。
- **合成初中卷实测**（含短文填空与配对阅读；素材与录音均为合成界面测试数据）：真实 Chrome 渲染出的章节入口与侧边栏板块都是试卷的六个板块——`一、听说应用 / 二、语法选择 / 三、完形填空 / 四、阅读理解 / 五、配对阅读 / 六、短文填空`；每节标题 `Test 1 第 1–2 题`、`二、语法选择 · 语法选择 2 题` … `六、短文填空 · 短文填空 2 题`；**20 项浏览器检查全过、0 跳过**。
- **自动测试**：新增"宣告优先"与"三份实现同一优先级"两项，并把听力检测测试改为记录新规则（题型名已说明不是听力时，残留挖空不改变呈现方式）；构建仍会拦下"把听力节改名成 reading 却留着逐题音频"。macOS + Python 3.11.0b2 上 **181 项全部通过**。
- **安装完整性**：`complete`。

## 未覆盖边界

- 文档已改为按试卷，但**助手是否照做仍取决于它是否读这几段**；本版只能用指令 + 校验双管：渲染与构建都会拒绝与试卷不符的板块（构建拦"逐题音频出现在非听力节"，浏览器拦"章节入口 ≠ 试卷板块"）。
- 图片选项、分值展示、双页照片标注仍未做（同 1.0.48）。
- 仍未在真实 Windows / 豆包工作 / WorkBuddy 上跑过（同 1.0.16）。

---

# 1.0.48 真卷链路复查（图片版试卷 + 图片版答案）

按用户要求"先不改功能，用一份真卷跑完整链路看还缺什么"。素材：九年级上册 Unit 1 适应性训练卷（卷面照片两张、每张两页；答案照片一张）。只做其中"四、阅读理解 A"这一块。

## 本次实际执行

- **图片登记**：在台账目录下跑 `image_pages.py`，2 张卷面 + 1 张答案，`problems=0`，得到集合指纹 `29d5ffd1…`（卷面）与 `b09793eb…`（答案）；页路径为相对路径。
- **图片版答案**：`answers.py extract 答案转录.txt --source-images answer-inventory.json` → `count=36`、`answer_source_kind=image_transcription`；`unparsed` 4 行（76—80 的主观题答案不会被当成"题号+答案"）。51—55 解析为 `D D B C A`，与答案照片一致。
- **走查中修掉的真 bug**：构建、模板核验、答案审计都通过，但页面上这一节渲染成了 **`Test A 第 51–55 题` 并带听力播放器**。运行时确认 `sectionPreset=reading` 而 `isListeningSection=true`：JS 里 `!!(s.audio||s.audio_note||s.blanks)` 对 `blanks: []` 返回 **true**（`!![]` 为真），Python 侧 `bool([])` 为假，所以只有 `assets/lesson.html` 与 `scripts/browser_check.cjs` 出错。连带后果：`reconcile()` 把**已跑过并通过**的 `only-one-analysis-open-per-section`、`paragraph-translation-toggles` 降级为"没有可测数据"，交付报告少报已验证项。
- **修复**：三份判据改为 `(s.blanks||[]).length>0`；补上 `browser_check.cjs` 中 7 处仍按题型名比较的地方（`s.kind==='listening'` 等，其中一处使自定义题型名的听力课不做播放验收）；浏览器主循环新增"非听力节 h2 不得以 `Test ` 开头"的断言。
- **修复后真卷实测**：构建 `structural_checks_passed`（0.15 秒，模板核验 `passed`、模板版本 1.0.48）；答案审计 `review_required`，5 题全部 `official`；质量闸门 `automated_checks_passed`，警告 1 条 `answer_key_image_transcription`（图片转录，按设计固定报出）；待核项 2 条（图片答案须逐题比对；第 52 题正确选项与证据句无完全相同词形）。真实 Chrome **13 项 PASS / 4 项如实 SKIP**（无多页、deep_reading 未开、writing_transfer 未开、无听力数据），`errors` 为空；`qa_report init` 13 条、填写后 `check=ok`、`package_lesson` → `browser_checked`，ZIP 内含 `sources/A-paper-1.jpg`（原卷页图随课件交付）。
- **第 52 题待核项**：机器比对报"正确选项与证据句没有共同实词（ideas/names/register/telling）"，实为 `name→names`、`idea→ideas`、`Tell→telling` 的单复数与同义转述；对照答案照片 `51—55 DDBCA` 后确认语义对应成立。**这是 review 项不是阻断项**，也说明该检查偏词形匹配，遇到转述会持续产生需要人工消解的噪音。
- **回归锁**：新增 `tests/test_listening_detection.py` 3 项（Python 判据、两份 JS 的静态锁：不得用数组真值判断听力、不得按题型名判断呈现方式、真实浏览器锁）。
- **安装完整性**：`complete`。

## 未覆盖边界

- 本次只做了「四、阅读理解 A」一块，**没有**做听说应用、语法选择、完形填空、短文填空、配对阅读与读写综合；整卷链路仍未跑通。
- **图片选项仍不支持**：这份卷「听说应用·听句子选图」的选项是图片，`options` 只能文字，模板也没有图片选项渲染。
- **分值只记录不展示**：`score_per_question`/`score_total`/`paper_info` 已能读进台账，页面不显示满分与每小题分值。
- **双页照片**：一张照片含两页（横向 2406×1743），页清单只能记成 1 张=1 页，"漏页/页序"的机器核对看不出这一点。
- 主观题答案（76—80）与范文（81）不会进 `answers.json`，落在 `unparsed` 等人工处理。
- 仍未在真实 Windows / 豆包工作 / WorkBuddy 上跑过（同 1.0.16）。

---

# 1.0.47 骨架不再替老师补题型复查

用户指出的第二点："我们现在强制生成听力、阅读理解、完形填空和语法填空。"

## 本次实际执行

- **改前证据**：`scripts/scaffold.py` 的 `build_ledger()` 里每个大题都写成 `{'kind':'reading','title':f'待确认题型 {index+1}'}`，且每节固定追加同样的待办：`['确认 kind 与题型标题','核对段落边界与空位','听力补 audio 与原文','写作补题目要求与范文归属']`；`exam_from_ledger()` 再给每节追加 `补 translation / structure / sentences / vocabulary / quick_words / writing_bank …`。**没有听力的卷子也会被要求补音频。**
- **现在按试卷读结构**（用一份中考式卷面文字实测，含大题标题、分值、页脚、"六、读写综合 A/B"）：

  ```
  S1 kind=听说应用  title=听说应用(30分，共30分)                    per=None total=30
  S2 kind=语法选择  title=语法选择(本大题共10小题，每小题1分，共10分)   per=1.0  total=10
  S3 kind=完形填空  title=完形填空(本大题共10小题，每小题1分，共10分)   per=1.0  total=10
  S4 kind=阅读理解  title=阅读理解(本大题共15小题，每小题2分，共30分)   per=2.0  total=30
  S5 kind=短文填空  title=短文填空(本大题共10小题，每小题1.5分，共15分) per=1.5  total=15
  S6 kind=读写综合  title=A. 回答问题(本题共5小题，每小题2分，共10分)  per=2.0  total=10
  S7 kind=读写综合  title=B. 书面表达(本题15分)                    per=None total=15
  ```
  卷头标题进 `title`，卷首说明进 `paper_info={'full_score':120.0,'minutes':90.0}`，页脚进 `ignored_lines`，都不再混进原文段落；A/B 小标题各自成节但同属"读写综合"一个导航入口；"本题15分"只记整题分值，不会写成每小题 15 分。
- **待办按节自己的题型生成**：只有阅读和写作的卷子，`S1（阅读理解）` 的待办里**没有** `audio`、**没有** `writing_steps`；`S2（书面表达）` 才有写作待办；听力节反而明确要求 `audio`/`blanks`。全局待办写明「本次原卷的题型只有这些：…；不要补原卷没有的题型」。
- **空节不静默丢弃**：`一、听说应用` 这类选项为图片、文本解析不到小题的大题会保留，并提示「本节没有解析到小题：核对是否为图片选项、图表题或跨栏排版，按原卷补题号与题干」。1.0.46 之前它会被 `if s['questions'] or s['paragraphs']` 过滤掉，整道大题消失。
- **预设推断**：补充常见大题名别名（听说应用/听说→listening、语法选择→cloze、短文填空→grammar、配对阅读/信息匹配→seven），并把 Python、页面模板、`browser_check.cjs` 三份 `KIND_ALIASES` 同步为同一张表，新增测试锁住三处一致（防止以后再漂移）。
- **文档同步**：`SKILL.md` 里"听力／阅读／七选五／完形／语法填空／写作各占一个入口""成品必须有能播的听力"以及 `references/schema.md` 的"常见听力3、阅读4…"改为按试卷；并写明原卷没有的题型不生成、不提示补全。
- **自动测试**：新增 `tests/test_scaffold_structure.py` 7 项；macOS + Python 3.11.0b2 上 **176 项全部通过**。
- **安装完整性**：`complete`。

## 未覆盖边界

- **图片选项尚未支持**：这份真实卷的"听说应用·听句子选图"选项是图片，`options` 目前只能是文字，解析不到就只会提示人工补题号；模板也没有图片选项的渲染。
- **分值只记录、不展示**：`score_per_question` / `score_total` / `paper_info.full_score` 已进台账与骨架，但页面暂不显示满分与每小题分值。
- 大题标题识别依赖中文序号（一、二、三…）与"每小题X分/共Y分"这类写法；只有字母小标题（A./B.）需要跟在中文大题标题之后才会被当成小节。
- 仍未在真实 Windows / 豆包工作 / WorkBuddy 上跑过（同 1.0.16）。

---

# 1.0.46 章节结构由试卷决定复查

用户指出"这些结构主要应该由老师的试卷来决定"。核对代码后确认三处是模板在替试卷做主：题型限死六种；导航按固定题型顺序重排并用写死的中文标签覆盖试卷板块名；栏目要求按题型名写死。

## 本次实际执行

- **改前证据（代码位置）**：`scripts/build.py` 的 `KINDS={'listening','reading','seven','cloze','grammar','writing'}` 是封闭集合；模板 `assets/lesson.html` 的 `CHAPTER_KIND_ORDER=['listening','reading','seven','cloze','grammar','writing']` 决定分组顺序、`CHAPTER_KIND_LABEL` 决定显示名；`validate_features` 用 `kind in {'reading','seven','cloze','grammar'}` 这类条件要求栏目。
- **新增 `scripts/section_kinds.py`**：`kind`（试卷题型名）与 `kind_preset`（呈现预设，缺省按题型名别名与本节内容推断）分离；`group`/`group_title`/`short` 决定导航分组、板块名与小标签；`shape()` 给出本节实际有什么（原文段数/是否多段/音频/写作/客观题）；`groups()` 按**首次出现顺序**分组。`build.py`、`scope.py`、`quality_gate.py`、`audio_wiring.py`、`answer_audit.py`、`scaffold.py`、`browser_check.cjs` 与模板全部改用它。
- **模板**：`renderChapterBar()` 改为 `chapterGroups()`（试卷顺序 + 试卷名称），侧边栏 `#nav` 分组同样按试卷；`chapterShort/chapterLabel` 支持 `section.short` 与试卷板块名；全部 32 处 `s.kind==='listening'|'writing'|'grammar'|'reading'` 与 `!==` 判断改为 `isListeningSection/isWritingSection/isGrammarSection`（按预设与内容判断）；"速对答案"的范围选项由固定题型清单改为按试卷板块生成（`fastGroups()`），并排除写作节。
- **栏目要求**：改为 `音频→blanks`、`有原文→quick_words/vocabulary`、`两段以上且非听力→sentences`（开精读再加 structure、开写作迁移再加 writing_bank）、`写作形状→writing_steps/teacher_model`、`写作节不要求段落译文`；`preset=='seven'` 才要求每题 `logic_links`，`preset=='grammar'` 才要求知识卡。
- **合成夹具实测**（`tests/make_paper_structure_fixture.py`，素材与录音均为合成的界面测试数据）：同一份材料按"第一部分 听力（听力理解）/ 第二部分 语言运用（完形填空、词汇运用）/ 第三部分 阅读理解（任务型阅读、阅读填空）/ 第四部分 写作（读后续写）"排列。`build-report.json` 的 `feature_coverage.sections` 保留试卷题型名与其顺序：听力理解/完形填空/词汇运用/任务型阅读/阅读填空/读后续写；`section_kinds.groups()` 得到 4 个板块、节数 `[1,2,2,1]`（"第二部分 语言运用"确实把完形与词汇运用并成一组）。
- **连带修正**：把板块顺序反转而不改题号时，`quality_gate` 报 `question_order` 并阻断——顺序由试卷决定的同时，题号也必须随试卷顺序递增。
- **真实浏览器验收**：新增 `chapter-bar-follows-paper-structure`（章节组数量、顺序、名称、`data-group`、侧边栏分组、每个菜单内的节序都必须等于试卷数据）与 `custom-kinds-get-tools-from-content`（`读后续写` 显示写作区、`听力理解` 显示 `Test 1`、`任务型阅读` 显示原文区）。该夹具 **18 项全部 PASS、0 跳过**；普通演示课件 14 PASS / 3 SKIP（无多页页图、无自定义题型名，如实跳过）。
- **自动测试**：新增 `tests/test_paper_structure.py` 6 项（题型名与顺序、分组、题号顺序、`kind_preset` 校验、按试卷名/预设/板块选择与精听模式、栏目要求随材料变化）+ 真实浏览器一项。macOS + Python 3.11.0b2 上 **169 项全部通过**。
- **安装完整性**：`complete`。

## 未覆盖边界

- `kind_preset` 的别名表（`KIND_ALIASES`）覆盖常见中英文题型名；完全生僻的题型名若不写 `kind_preset`，呈现方式按"有音频→听力、有写作材料→写作、其余按阅读"推断，可能与试卷意图不同——此时应显式写 `kind_preset`。
- 兼容性：旧课件（六种 `kind`）继续可用；唯一可见变化是导航顺序改为数据顺序（若旧数据本身顺序与之前固定顺序不同，导航顺序会变，这正是本版要修的行为）。未提供自动迁移"重排过的旧数据"的工具。
- 仍未在真实 Windows / 豆包工作 / WorkBuddy 上跑过（同 1.0.16）。

---

# 1.0.45 构建报错复查（一次列全 / 中文 / 带实际值）

本版针对"生成特别久、特别费 token"的**返工**环节：助手每看一条报错就要改一处、重建一次整卷。

## 本次实际执行

- **先量清楚瓶颈**：合成大卷（12 节 / 24 题 / 104KB exam.json；`/tmp` 夹具）`build.py` 总耗时 **0.39 秒**，`render_and_write` 0.375 秒，`quality_gate` 0.005 秒、`answer_audit` 0.003 秒、`validate` 0.003 秒；`--dictionary-scope full`（HTML 4.3MB）总耗时 **0.25 秒**；`verify_output` 0.01 秒。**脚本不是瓶颈**，返工轮次才是。
- **改前实测（用仓库里的 1.0.13 基线 `_work/upstream1013/scripts/build.py` 跑同一夹具）**：同一节注入 5 个问题（生词词频错、选项少一项、缺 analysis、writing_bank 缺 frame、挖空指向不存在段落），旧版只报 **1** 条：`共 1 处问题…- A: Quick word count must match this section`。
- **改后同一夹具**：一次构建报出 **5** 条中文问题，且每条带实际值：
  - `章节 A 的生词 'loose' 在本节原文实际出现 1 次，条目写的是 9；请按原文改成实际次数`
  - `第 21 题选项数不符：本节要求 4 项，实际 3 项（['A', 'B', 'C']）`
  - `第 22 题缺少 analysis：讲评正文不能空着`
  - `章节 A 的 writing_bank 缺少 frame；写作迁移要写清分类、选用理由、句式框架、使用场景、示例句与自查点`
  - `章节 A 的挖空指向了不存在的段落 'NOPE'；本节段落为 ['A-p1', 'A-p2']`
  - 末尾固定提示：`（上面每条都已给出实际值；改完直接重跑同一条命令。字段含义见 references/schema.md，引文回填用 scripts/quotes.py fill）`
- **做法**：`validate_section` 的每组检查（章节头/段落表/生词/来源页图/写作积累/逻辑步骤/追问/迁移/范文分析/文化背景/挖空/听力/题号存在性/每道题/下划线空位/五类内容校验器）改为独立兜住异常并继续；`validate()` 的兜底消息也改成中文并说明这是未预期的数据结构问题。挖空已在上面报过时跳过 `validate_blank_tokens`，避免同一处报两遍（实测从 6 条降到 5 条）。
- **中文化**：`scripts/*.py` 中所有 assert/raise 的报错文字实现零英文（改前 `build.py` 58 条、`audio.py` 15 条、`culture.py` 5 条、`verify_output.py` 7 条、`align_whisperx.py` 5 条、`prepare_whisper.py` 5 条、`check_install.py` 1 条）。`audio.py` 直接透传 ffmpeg stderr 的两处改为"中文说明 + 原始输出"。
- **新增 `tests/test_messages.py` 13 项**：静态锁（AST 遍历 `scripts/*.py`，assert/raise 的报错文字必须含中文、assert 必须有说明）+ 反向验证（写回英文、去掉说明都必须被抓到）+ 行为锁（词频真实次数、选项要求/实际项数、证据引文与段落 ID、`--profile quick` 提示、一次构建列全并给出 `references/schema.md` 与 `scripts/quotes.py fill`、挖空不重复报、文化背景必须有来源且引文必须是本篇子串）。
- **自动测试**：macOS + Python 3.11.0b2 上 162 项全部通过。
- **安装完整性**：`complete`。

## 未覆盖边界

- 报错中文化只覆盖脚本内部文字；**外部工具（ffmpeg/ffprobe/whisper.cpp/Playwright）自身的英文输出仍原样附带**，这是刻意保留的原始证据，不做翻译。
- "一次列全"仅限于**同一节内部**：`validate_section` 目前仍按"章节"为界收集，若第 1 节就失败，其余章节不会被跳过（每节都会检查），但同一节内的检查组是全部执行的。
- 仍未在真实 Windows / 豆包工作 / WorkBuddy 上跑过（同 1.0.16）。

---

# 1.0.44 人工复核清单工具化复查

本版把 `SKILL.md`、`references/source-verification.md`、`references/culture-background.md`、`references/regression.md`、`references/schema.md`、`docs/WINDOWS.md` 六处反复要求的"把结论写进 qa-report.md"做成可生成、可拒绝的工具，并把它接进交付闸门。

## 本次实际执行

- **缺口确认**：全仓检索 `qa_report|qa-report` 只有文档与 `package_lesson` 的说明，**没有任何脚本生成或读取该文件**；一份空核对表与一份写着"没问题"的核对表在 `delivery-report.json` 里无法区分。
- **新增 `scripts/qa_report.py`**（`init` / `check`，均支持 `--file`、`--json`）：
  - `init` 在 1.0.44 发布包解压目录里（`examples/demo-exam.json`，范围 A）生成 **11 条**条目，内容取自实际证据而非空模板：答案审计 `official/inferred/sample/unresolved` 计数、`answer-audit.json` 的 review 与 blocking 逐题条目、静音自动分段（`quality_gate.warnings` 中 `audio_alignment_auto_silence`）的**具体段落名**、浏览器已执行操作名列表与跳过项（跳过项带"该功能未经验证"）、`build-report.json` 的 `pending_items`；无听力/无跳过/无待核时也有对应"无"条目，五个章节**不会出现空章节**。
  - `check` 实测拒绝：文件缺失（`status=missing`，提示用 `init` 生成）；未填写 → 每条"结论过短（空）"、`concluded=0`；`待填/待补充/待核/TODO/XXX/略` 单独成句 → "结论仍是占位文字"（占位判定在过短之前，报出的是真实原因）；结论 5 字 → 过短；6 字 → `ok` 且 `concluded==items`；把第 3 节标题改掉 → "缺少章节"；把文件清空成散文 → "没有任何复选框条目"。**反过来，"已逐题核对原卷，无待核项。"这类含占位词的正常句子返回 `ok`**——占位判定改为"去掉占位词后剩余内容不足 6 字"，避免交付闸门逼人改写诚实结论。
  - 只读 `- [ ]` 复选框行，正文里的"结论："不会被误判。
  - 已存在 `qa-report.md` 时 `init` 拒绝覆盖并退出 1，需显式 `--force`（避免抹掉已填写的结论）。
- **交付闸门**：`package_lesson.py` 原来只查浏览器证据；现在 `browser_ok and qa['status']=='ok'` 才打包，拒绝信息把两类原因合并（缺浏览器验收 / 清单未完成并给出处理命令）。`--allow-unchecked` 仍可交付"待验收版"。`delivery-report.json` 新增 `qa_report`：`{status,items,concluded,problems}`。
- **端到端（1.0.44 发布包解压目录，非工作树）**：`plan.py make` → `build.py --plan` → `verify_output`（`passed`，模板 `1.0.44`）→ 真实 Chrome 跑 `browser_check.cjs`（`passed=11 skipped=4`，`errors` 为空）→ `qa_report.py init`（11 条）→ 未填写时 `package_lesson.py` 退出 1、**没有生成 ZIP** → 逐条写入真实结论 → `check` 返回 `ok`（`11/11`）→ 打包 `status=browser_checked`，`delivery-report.json` 的 `qa_report` 为 `{ok,11,11,[]}`，ZIP 内**包含 `qa-report.md`**。再把结论改回 `待填` 并用 `--allow-unchecked` 打包 → `preview_only_browser_check_pending`，`delivery-report.json` 如实记录 `qa_report.status=needs_fix`、`0/11` 与 11 条问题。
- **文档同步**：`SKILL.md` 把第 1 节的"在 qa-report.md 分层记录"改为先说明 `qa_report.py init/check` 与交付闸门；`README.md` 增加 1.0.44 章节与产物说明。
- **自动测试**：macOS + Python 3.11.0b2 上 149 项全部通过（新增 `tests/test_qa_report.py` 10 项：证据落条、空目录空章节、宿主报告缺项名不崩、CLI 覆盖保护与退出码、空/占位/过短结论、含"待核"的正常句子不被误拒、缺文件缺章节与清空、散文不误判、章节固定唯一）。
- **安装完整性**：`complete`。

## 未覆盖边界

- `qa-report.md` 的内容真实性仍由人（Agent）负责：`check` 只能拒绝"空着"和"写着待填"，**不能判断结论是否真的核对过**。这正是本版刻意保留的边界，不把它包装成内容验证。
- 未在真实 Windows/豆包工作/WorkBuddy 上跑过 `init/check`（同 1.0.16）。
- 条目模板来自当前已有的报告字段；`answer-audit.json` 若新增分类，需同步 `collect()`，否则新分类不会出现在清单里（现有测试不含该回归）。

---

# 1.0.43 更新流程工具化复查

本版把 `docs/UPDATE.md` 里"核对—安全解压—确认完整—比较—替换"这套手工流程做成一条可校验的命令。

## 本次实际执行

- **核对**：用真实发布包生成同版 `SHA256SUMS.txt`，`extract_package.py` 返回 `verification.status=passed`；把校验值改成全 0 → 报「压缩包指纹与 SHA256SUMS.txt 不一致，不要使用这个文件」并退出 1；清单里换成别的文件名 → 报「没有这个压缩包的条目」。
- **安全解压**：构造含 `../escaped.txt`、`/absolute.txt`、`.hidden/secret`、`__MACOSX/junk`、符号链接 5 个恶意条目的压缩包 → 全部被拒并**逐条列出原因**（越界、绝对路径、隐藏文件、符号链接），退出 1；实测解压目录外**没有生成 escaped.txt**、没有创建 symlink，只有 `fine.txt` 这类安全条目被写出。这比旧实现（`prepare_whisper.unpack` 静默 `continue`）更严格：危险条目现在会阻断整个更新。
- **完整性**：真实包解压后 `installation.status=complete`（93 文件）；平铺与"多包一层目录"两种包结构都能定位到包根。
- **比较**：与相同版本比较得 `unchanged=93, added=0, changed=0, removed=0`；把目标的 `VERSION` 改成 `0.0.1` 后，它被列进 `locally_modified`（"你自己改过、与官方清单不一致"）。
- **应用**：缺 `--backup` → 拒绝且**目标文件未被改动**（VERSION 仍是 0.0.1）；带 `--backup` → 备份目录保留旧 VERSION、目标更新为新版、**老师的 `我的笔记.md` 仍在**；再次 `--apply --backup` 同一目录 → 拒绝覆盖已有备份。
- **文档同步**：`docs/UPDATE.md` 第 2、3 步改为使用该脚本，并写明"缺 `--backup` 会拒绝执行"。
- **自动测试**：macOS + Python 3.11.0b2 上 139 项全部通过（新增 `tests/test_update_flow.py` 6 项）。
- **安装完整性**：`complete`，94 个文件。

## 未覆盖边界

- 未对真实 GitHub Release（含 `english-exam-demo.zip` 等条目）联调；测试使用本仓库自行打的包与合成恶意包。
- 应用步骤是覆盖式复制，不做三方合并：`locally_modified` 的文件会被新版覆盖（报告里已提示先备份，且备份是强制的）。
- Windows 与真实宿主仍未实机验收（同 1.0.16）。

---

# 1.0.42 功能选择回退路径复查

本版把"没有多选控件时用编号清单"这条一直靠助手手写的路径变成可执行、可校验的工具。

## 本次实际执行

- **背景**：功能选择要求七项全记，漏记任意一项 `apply_plan` 会以「请记录全部可选功能的选择」阻断；而弱宿主（豆包工作 / WorkBuddy）没有真多选控件，走"编号清单"回退时由助手手工把"1、3、5"转成 JSON——正是最容易漏项的一步。
- **新增 `scripts/plan.py`** 并实测：
  - `menu`：打印范围（A 精听 / B 整卷 / C 指定板块）与七项功能编号菜单，供宿主原样展示；
  - `make --confirmed --range C --sections reading,A --features 1、3、5`：产出七项全记的计划，且 `apply_plan` 直接接受（实测 `annotations/quick_answers/deep_reading` 为真，其余为假）；
  - `--range A --features 基础讲评即可`：`sections=listening, mode=intensive`，七项全假（仅基础功能）；
  - `--features 全部` 与 `沿用上次 --previous`：均正确；
  - `check`：完整计划报 `ok`；删掉一项后报 `功能必须七项全记：缺 ['dictionary']` 并退出 1。
- **拒绝代替老师回答**：缺少 `--confirmed` 时直接报错且**不写文件**（实测磁盘上无计划产物），符合"未回答不默认开始"的规则。
- **错误路径均有可执行提示**（均退出 1、无 traceback）：C 未给 `--sections`、编号越界、上一份计划不存在、无法识别的输入。
- **文档同步**：`references/teacher-options.md`、`references/host-compatibility.md`、`SKILL.md` 均改为指向 `plan.py`，并要求不要手写 JSON。
- **自动测试**：macOS + Python 3.11.0b2 上 132 项全部通过（新增 `tests/test_plan.py` 7 项，含"必须能被 apply_plan 接受"的端到端断言）。
- **安装完整性**：`complete`，92 个文件。

## 未覆盖边界

- 菜单文案与实际宿主的多选控件呈现仍需在真实豆包/WorkBuddy 上看一次；本版只保证编号清单这条回退路径正确。
- 工具不判断"老师是否真的回答过"，`--confirmed` 仍是使用者的声明；这是刻意保留的人工判断点。
- Windows 与真实宿主仍未实机验收（同 1.0.16）。

---

# 1.0.41 普通课件验收误判复查

本版修掉 1.0.37 引入的一个严重回归：**没有页图的普通课件在浏览器验收环节直接失败**，无法交付。

## 本次实际执行

- **发现方式**：执行"从解压出来的包里跑最普通那条链"（构建 `examples/demo-exam.json` → 真实浏览器验收 → 打包）时，验收在 `multi-page-origin-renders-every-page` 处中断：`fixture must ship a multi-page section, otherwise this check is vacuous`。该断言本意是防夹具空转，却对**任何**课件生效，因此老师没有页图的普通课件一律验收失败。
- **修复**：通用检查在没有多页页图时改用 `skip(...)` 并给出原因；"夹具必须带多页"改由测试 `test_browser_fixture_ships_a_multi_page_section` 保证（空转防线放在夹具侧，不放在老师课件侧）。
- **修复后实测**：
  - 普通示例（无页图、无听力）：**20 通过 / 2 跳过**（多页页图、听力挖空不适用），`status=passed`，可打包为 `browser_checked`；
  - 六题型界面夹具：**25 通过 / 0 跳过**，多页检查照常实际执行。
- **新增真实浏览器测试**：`test_an_ordinary_lesson_passes_the_real_browser_check` 使用系统 Chrome（自动探测，找不到则跳过）跑最普通课件，断言 `status=passed` 且"多页"项在 `skipped` 中——该测试在 1.0.37 的代码上会失败，能守住此类回归。
- **过程记录**：本轮我在打包后又修改了测试文件，导致安装清单过期、全量测试一度 6 失败 1 错误；重新生成清单后 **125 项全部通过**（无 Playwright 时 1 项跳过）。
- **安装完整性**：`complete`，90 个文件。

## 未覆盖边界

- "跳过"仍表示未验证；多页页图这一项只在带多页页图的课件上被实际执行（夹具保证每次标准运行都会执行）。
- 真实浏览器测试依赖本机 Chrome/Edge 与 Playwright 模块，缺失时跳过而非失败（CI 环境属此类）。
- Windows 与真实宿主仍未实机验收（同 1.0.16）。

---

# 1.0.40 全配置交付链复查

本版把 1.0.39 的教训固化为常设测试：新功能必须走完整交付链，只验一环会漏掉跨工具契约。

## 本次实际执行

- **新增 `tests/test_delivery_chain.py`（7 项）**，对每个受支持配置执行「构建 → 模板核验 → 浏览器证据 → 打包」并断言 `browser_checked`：默认全功能、全部功能关闭、快速档、整本词库范围、多页页图、**只要听力**（`selection=L1, mode=intensive, audio_mode=folder`，实测交付内只含 L1、`audio_delivery.mode=folder`）。
- **真·跨工具契约测试**：不依赖 Playwright（浏览器脚本在启动浏览器前已算出 `media_sha256`），直接比对浏览器验收的媒体集合与 `verify_output` 的资源集合。实测多页课件两边都含 `sources/A-paper-{1,2}.png`。
- **反向验证（证明测试不是安慰剂）**：把 1.0.37 的缺陷重新注入——从浏览器脚本的媒体收集中删掉 `page_images`——该测试**立即失败**，信息为"浏览器验收与模板核验必须指纹同一组媒体，否则交付门槛会拒绝整类课件"；恢复后通过。
- **覆盖缺口说明**：此前"只要听力"只验到构建成功，没有走到打包；本版补齐，确认它在 intensive + 目录音频下同样能交付。
- **自动测试**：macOS + Python 3.11.0b2 上 123 项全部通过。
- **安装完整性**：`complete`，90 个文件。

## 未覆盖边界

- 交付链矩阵使用**合成的浏览器证据**（`engine=unit-test-fixture`）校验工具间契约；真实点击验收仍由 `browser_check.cjs --stress` 在实机运行（本机已单独跑通 25 项全通过）。
- 多数配置基于原创阅读示例；真实整卷的材料识别与音频切点仍不在覆盖范围内。
- Windows 与真实宿主仍未实机验收（同 1.0.16）。

---

# 1.0.39 验收报告诚实性与多页媒体一致性复查

本版修掉两个问题：验收报告把"未执行"写成"通过"，以及我自己在 1.0.37 引入的多页交付阻断。

## 本次实际执行

- **发现"没跑也算通过"**：用全部七个扩展都关闭的课件跑 `browser_check.cjs --stress`，输出 **23 项全部 PASS**；但其中 `offline-lookup-serves-lesson-words`、`deep-reading-structure-renders-and-locates`、`writing-transfer-tab-renders`、`quick-answers-whole-and-kind-no-analysis-side-effects` 四项因功能关闭/无数据而**从未执行**，却照样打印 PASS。
- **修复后复验**：
  - 关闭全部扩展：**19 通过 / 4 跳过**，逐项给出原因（"功能 dictionary 未开启，本项未执行"等）；
  - 全部开启：**25 通过 / 0 跳过**，行为不变。
  - 同时把 `quick_answers` 与 `classroom_tools` 关闭时的"入口必须隐藏"断言并入 `selected-features-controls`，避免降级后丢掉这部分检查。
- **交付报告披露**：`delivery-report.json` 新增 `browser_checks`（通过/跳过计数）与 `browser_checks_skipped`（逐项原因），`scope` 明确"跳过项未经验证，不能当作已通过"。
- **顺带修掉 1.0.37 引入的真实阻断**：`verify_output` 已把 `page_images` 计入 `resource_sha256`，而 `browser_check.cjs` 仍在按 `origin.page_image` 收集媒体，二者不一致 → **任何含多页页图的课件在 `package_lesson` 一律被判"缺少与当前 HTML 对应的浏览器点击验收"**。实测确认后已统一收集逻辑，多页课件现在可以正常打包为 `browser_checked`。
- **自动测试**：macOS + Python 3.11.0b2 上 116 项全部通过，新增 2 项（交付报告披露跳过项；浏览器验收与模板核验收集同一组媒体）。
- **安装完整性**：`complete`，89 个文件。

## 未覆盖边界

- "跳过"只说明该项在本课件不适用，不代表该功能被验证过；功能开启时的检查仍由默认全开运行覆盖。
- 跨工具媒体一致性用源码级断言守护（浏览器脚本无法在单元测试里执行），真实一致性仍以每次实机运行与打包为准。
- Windows 与真实宿主仍未实机验收（同 1.0.16）。

---

# 1.0.38 文档承诺与实现一致性复查

本版不改代码，修正三处"说得比实现满"的用户文档。

## 本次实际执行

- **发现**：1.0.35 已把查词默认改为"只内置本篇出现的词"，但用户文档未同步——
  - `README.md` 致谢段："公开版内置 **10,836 条 ECDICT 离线释义**"；
  - `docs/FAQ.md`「离线时哪些功能能用」："……本地听力、**词库**、批注和课堂工具可以离线使用"；
  - `docs/FAQ.md` 词典条目："内置释义仍可用"；
  - `README.md` 功能表："内置 ECDICT 基础释义"。
  按字面理解，老师会以为**任意生词**都能离线查，实际默认只覆盖本篇的词。
- **修正**：四处均改为明确边界——随包附带整本词库，但每份课件默认只内联本篇出现的词；要任意生词离线可查需 `--dictionary-scope full`（体积明显变大）。
- **反向核对**：README 的输入格式表本就写着"PDF、完整试卷照片"与"Word / DOCX、PDF、图片或文字"，与 1.0.36/1.0.37 的图片支持一致，无需修改；`docs/SETUP.md` 无词库相关承诺。
- **自动测试**：macOS + Python 3.11.0b2 上 114 项全部通过（本版无代码改动，测试数不变）。
- **安装完整性**：`complete`，89 个文件。

## 未覆盖边界

- 只核对了与近期改动直接相关的承诺（词库范围）；其余文档表述未逐句复核。
- 词汇/词典类文档无法由测试断言，只能人工比对，后续改动仍可能再次漂移。

---

# 1.0.37 图片版试卷多页交付复查

本版补上 1.0.36 留下的限制：图片版试卷一节跨多页时，过去只能挂一张页图。

## 本次实际执行

- **实测多页构建**：给示例节加 `origin={"exam_page":2,"page_images":["page-2.png","page-3.png"]}`，构建后 `exam.json` 内为 `["sources/A-paper-1.png","sources/A-paper-2.png"]`，两页都落盘；`verify_output` 返回 `passed`，且 `resource_sha256` **同时包含两页**（因此浏览器证据与交付打包都绑定到两页，改动任一页都会使旧证据失效）。
- **校验实测**：`page_images: []`（空数组）与 `page_images:["ok.png",3]`（混入非字符串）均被拒绝，报错直接点名字段 `origin.page_images`；只写 `page_image` 的旧数据不受影响。
- **界面验收**：夹具新增两页页图，「出处」弹窗断言 `#originDialog .origin-pages img` 数量等于页数；并加 `assert.ok(multiPage, ...)`，**夹具缺少多页章节即失败**——避免像 1.0.25/1.0.27 那样出现"检查空转"。`browser_check.cjs --stress` 由 24 项增至 **25 项全部通过**。
- **模板改动**：`assets/lesson.html` 的出处弹窗由单张 `<img>` 改为按 `page_images`（缺省回落到 `[page_image]`）逐页渲染；单页时输出的 `alt` 与旧版一致。模板版本与 SHA256 已更新（`0f7a5135…`）并在构建时校验通过。
- **自动测试**：macOS + Python 3.11.0b2 上 114 项全部通过（`tests/test_image_inputs.py` 增至 16 项，覆盖多页构建、多页指纹与两类非法 `page_images`）。
- **安装完整性**：`complete`，89 个文件。

## 未覆盖边界

- 仍是合成图片；真实照片的识别准确率与版式（跨栏、跨页续句）未实测。
- 「出处」弹窗按页纵向排列，未做缩放/翻页控件；页数很多时滚动较长。
- Windows 与真实宿主仍未实机验收（同 1.0.16）。

---

# 1.0.36 图片版材料（无 PDF）支持复查

本版补上"老师只给图片、没有 PDF"这一常见情形的工具、门槛与文档。

## 本次实际执行

- **页集合登记**：构造 9 张图片（编号缺 3、其中两页内容完全相同）运行 `image_pages.py`，正确得到自然排序（`page-2` 在 `page-10` 前）、逐页 `sha256` 与宽高，并报出 `duplicate_page`("与第 4 页内容完全相同：同一页拍了两遍，或漏拍了别的页") 与 `possible_missing_page`（"编号 1–10 之间缺 [3]"），有报错时退出码为 1。空文件、损坏图片、混入非图片、路径不在台账目录下均有对应代码。
- **台账校验**：以图片集合为一组 `sources`（`kind=image_pages` + `pages`）建立台账后——
  - 一致时 `status=automated_checks_passed`；
  - **重拍/替换某页** → `source_page_hash` 阻断；
  - **只调换页顺序**（文件与哈希都没改）→ `source_pages_digest` 阻断。
- **图片版答案溯源**：`answers.py extract 转录文本 --source-images 页清单` 产出 `answer_source_kind=image_transcription`、`answer_source_sha256=<图片集合指纹>`、`answer_source_pages`，并保留转录文本指纹；构建固定报出 `answer_key_image_transcription` 待核项（"必须逐题与答案原图比对"），而不把它当作机器核对通过的官方答案。非图片清单会被拒绝并提示用 `image_pages.py`。
- **修复过程**：首次实现把页路径写成相对**图片目录**，而台账按相对**台账目录**解析，导致三页全部报 `source_page_hash`；已改为按当前目录/`--relative-to` 输出，并新增 `path_outside_base` 提示，避免同类静默错位。
- **文档**：新增 `references/image-inputs.md`（确认形态 → 登记 → 台账 → 转录与独立盘点 → 图片答案 → 页图随包 → 必过检查 → 不能说的话），并在 SKILL.md、SETUP.md 接入；README 同步说明"不必先转 PDF"。
- **自动测试**：macOS + Python 3.11.0b2 上 111 项全部通过（新增 13 项）。
- **安装完整性**：`complete`，89 个文件。

## 未覆盖边界

- 图片识别本身由宿主的视觉能力/OCR 完成，本机没有真实试卷照片，**未实测识别准确率**；工具只解决顺序、重复、缺失、指纹与溯源，不保证识别零错误。
- 未测试 HEIC 等特殊格式与超大扫描件的内存占用（此类会落在 `unsupported_file` 或由宿主处理）。
- `section.origin.page_image` 仍为**每节一张**；多页章节需选代表页，整套图片随交付文件夹保留。
- Windows 与真实宿主仍未实机验收（同 1.0.16）。

---

# 1.0.35 离线词库范围与体积复查

本版解决"只要开查词就内联整本 4MB 词库"的问题，并补上离线查词的实机验收。

## 本次实际执行

- **实测三种配置**（同一份示例课件）：关闭查词约 245KB；默认 `lesson` 范围 **264 条 / 374,678 字节**；`--dictionary-scope full` **10,836 条 / 4,432,318 字节**。默认配置体积缩小约 **11.8 倍**。
- **覆盖检查**：本篇出现的 137 个英文词元中 133 个命中内置词库（**97%**）；未命中的 4 个是 `mia`、`willow`（专有名词）与 `journal`、`writer`（经核对**整本词库也不含**），并非范围裁剪造成的遗漏。
- **离线查词实机验收**：新增检查在**禁止一切外部请求**的页面里查询本篇的词，断言仍能出释义且来源为内置词库（`ECDICT`/离线）。同时把"查词开启却没有任何内置词条"由静默跳过改为**断言失败**——首次运行时它正是这样暴露了夹具把 `dictionary` 写成空对象、导致该检查形同虚设的问题。浏览器验收 23 → **24 项**。
- **报告新增字段**：`build-report.json` 的 `dictionary.scope` 与 `dictionary.entries`，并把"lesson 范围查不到本篇以外的词、离线不可用"写进同一份报告。
- **自动测试**：macOS + Python 3.11.0b2 上 98 项全部通过；新增 `test_dictionary_scope_defaults_to_lesson_words_only`（本篇词保留、非本篇词 `withdraw` 不出现、体积更小、报告记录 scope）。
- **安装完整性**：`complete`，86 个文件。

## 未覆盖边界

- 默认范围改变了"任意词离线可查"这一旧行为：这是有意的体积取舍，已在报告与文档写明，并保留 `--dictionary-scope full` 一键恢复；**若老师坚持课件完全离线且要查课外词，应显式使用 full**。
- 词库本身是 ECDICT 的约 1.08 万条子集，不是全量；未收录词在任何范围下都走在线词典。
- Windows 与真实宿主仍未实机验收（同 1.0.16）。

---

# 1.0.34 课堂不变式验收复查

本版把两条写在文档里、却从未被验收过的课堂规则补上实机断言。

## 本次实际执行

- **「每节最多展开一道解析」**（`SKILL.md`「每节最多展开一道解析」／`regression.md`「任意视图最多一道解析展开」）：原有检查对每道题"点开再点关"，**从未同时打开两道**，因此该不变式形同未测。新增检查：打开第 1 道解析（断言可见）→ 打开第 2 道（断言可见）→ 断言第 1 道已隐藏，且该节 `.analysis:not([hidden])` 计数为 1。实测通过（`only-one-analysis-open-per-section`）。
- **「开启挖空不得泄漏答案与译文」**：原有检查在"尚未展开任何解析/译文"的状态下开启挖空，即使实现漏了清理也会通过。改为按真实泄漏顺序验证：先展开一道解析、再展开一段译文，然后开启「关键表达挖空」，断言该解析已收起、该节不再有可见译文、且 `ui.openAnswers` 不含本节题目。实测通过。
- **实测总数**：`node scripts/browser_check.cjs FIXTURE --stress` 由 22 项增至 **23 项全部通过**。
- **自动测试**：macOS + Python 3.11.0b2 上 97 项全部通过。
- **安装完整性**：`complete`，86 个文件。

## 未覆盖边界

- 两条不变式均为"本轮实测通过"，实现未改动；它们守护的是"改版不会悄悄破坏这两条规则"。
- 主题检查仍只验证六种主题可切换与记忆，未断言换色后的对比度数值。
- Windows 与真实宿主仍未实机验收（同 1.0.16）。

---

# 1.0.33 题号盘点独立性与漏题检查复查

本版修掉一个"检查形同虚设"的设计缺陷：按推荐流程生成的课件，漏题不会被发现。

## 本次实际执行

- **定位**：`scaffold.py` 的 `exam_from_ledger` 用 `[str(q['id']) for s in data['sections'] for q in s['questions']]` 生成 `expected_question_ids`，来源正是那份可能漏题的解析结果；而 `build.validate` 的"无漏题"检查正是拿它与实际题目比对——两者同源，恒等。
- **复现影响**：若解析漏掉第 12 题，expected 同步变成 `['11']`，声明题号与实际题号依然一致，构建照常通过。`references/regression.md` 第 1 条要求的"题号盘点独立于OCR结果"在推荐流程里无法成立。
- **修复后实测**：`scaffold.py exam` 现在输出 `expected_question_ids_source: "machine_draft"` 并给出待办；用该骨架构建被阻断，错误为「题号清单来自机器草稿……构建的"无漏题"检查不成立……请按原卷（含跨页、跨栏）独立盘点题号，改正 `expected_question_ids` 后把该字段改为 `checked` 或删除」。把字段改为 `checked` 后该错误消失（仅余骨架未填教学内容的正常报错）。
- **一致性**：`scope.select` 使用 `copy.deepcopy(exam)`，标记字段在筛选与 `--plan` 路径中都会保留；仓库示例与界面夹具不含该字段，行为不变。
- **自动测试**：macOS + Python 3.11.0b2 上 97 项全部通过；`tests/test_ingest.py` 的骨架链路测试新增断言（标记存在、machine_draft 被阻断、改为 checked 后不再报该错误）。
- **安装完整性**：`complete`，86 个文件。

## 未覆盖边界

- 该门禁只强制"必须独立核对"，无法自动核实核对本身是否认真；老师的原卷盘点仍可能出现人为遗漏。
- 旧的、已生成但未带该字段的骨架不受影响（保持原行为），若要享受该检查需重新 scaffold 一次。
- Windows 与真实宿主仍未实机验收（同 1.0.16）。

---

# 1.0.32 CI 实机体检任务复查

本版把一键体检报告接进跨平台工作流，让 Windows 上的脚本级验证不再依赖维护者手动操作。

## 本次实际执行

- **新增 `smoke` 任务**：矩阵 `windows-latest` / `macos-latest` / `ubuntu-latest`，运行 `python scripts/smoke_report.py --no-browser --workdir smoke-output --report-dir smoke-report`，随后用 `actions/upload-artifact@v4`（`if: always()`）上传 `smoke-report/`；运行步骤 `continue-on-error: true`，让报告本身成为结论而不是门禁。
- **按 CI 原样本地验证**：在仓库根目录执行完全相同的命令，得到 6 通过 / 1 跳过（浏览器按 `--no-browser` 跳过），`smoke-report.json` 与 `smoke-report.md` 正常写出，退出码 0；验证后清理了产物目录。
- **YAML 校验**：工作流可被解析（jobs: test / doctor / smoke），`smoke` 矩阵与步骤名称符合预期，文件内无制表符。
- **边界**：CI 的 Windows 报告覆盖"安装完整性 / 宿主能力 / 示例构建 / 模板核验 / 打包"；**浏览器点击验收仍只在真机执行**（报告会标注 skipped）。这条任务只有推送后才会产生产物，本机无法代为运行。
- **自动测试**：macOS + Python 3.11.0b2 上 97 项全部通过。
- **安装完整性**：`complete`，86 个文件（`.github/` 属仓库基础设施，按设计不进入技能包）。

## 未覆盖边界

- 尚未在真实 GitHub runner 上运行过（本机无法触发），首次推送后需查看 `smoke-report-windows-latest` 产物确认。
- CI 报告不含浏览器验收，也不含真实试卷、真实答案册与真实听力切点。
- 豆包工作 / WorkBuddy 仍需在对应宿主里执行同一命令。

---

# 1.0.31 一键实机体检报告复查

本版新增一个交付给老师的"一条命令出报告"工具，用来收集 Windows / 豆包 / WorkBuddy 的实机数据。

## 本次实际执行

- **完整跑通（含浏览器）**：在本机执行 `python3 scripts/smoke_report.py`（设置 `PLAYWRIGHT_MODULE`），七步全部通过——运行环境、安装完整性（84 文件 complete）、宿主能力（`delivery=browser_check_possible`、`audio=no_ffmpeg`）、示例构建（quality_gate/answer_audit/template 均通过）、模板与产物核验（`comparison=exact`）、浏览器点击验收（`status=passed`，19 项检查、0 错误、engine=chromium）、打包交付（`status=browser_checked`）。
- **跳过浏览器路径**：`--no-browser` 时 6 通过 1 跳过，打包状态正确降级为 `preview_only_browser_check_pending`；`smoke-report.json` / `smoke-report.md` 均正常写出。
- **报告内容**：每步含状态、摘要与**实际输出尾部**（构建报告、核验结果、浏览器输出等），便于回传后定位；文件头写明"只证明这些步骤在这台机器上执行过，不代表真实试卷内容已验收"。
- **自动测试**：macOS + Python 3.11.0b2 上 97 项全部通过；新增 `tests/test_smoke.py`（断言七步齐全、失败数为 0、跳步被标注、报告为合法 JSON 与 Markdown、交付 ZIP 生成）。
- **安装完整性**：`complete`，86 个文件。

## 未覆盖边界

- 本机跑通不等于 Windows / 豆包 / WorkBuddy 跑通——这正是需要老师回传报告的原因。
- 体检用的是仓库原创示例与合成音频，不覆盖真实试卷、真实答案册版式与真实听力切点。
- 报告不含安装/下载动作，因此不能证明网络受限环境下的依赖获取路径。

---

# 1.0.30 六题型官方答案端到端复查

本版不改产品功能，把"整卷 + 官方答案"这条最有代表性的真实链路固化为回归测试。

## 本次实际执行

- **构造**：以界面验收夹具的六题型课件为基础，把**听力 / 阅读 / 七选五 / 完形**四类客观题共 8 道全部标记为 `answer_status=official`，用文本答案原件写出答案表（`answers.py extract` 解析，`unparsed=0`），并在台账中逐题登记 `answer_reference`、登记 `role=answers` 原件的指纹。
- **完整构建实测**：`structural_checks_passed`、`quality_gate=automated_checks_passed`、`answer_audit` 无 blocking（8 道官方答案全部与答案原件核对一致）、听力音频内嵌 3 段、模板校验通过。仅有两条 `cloze_answer_too_long` 进入 review 清单——那是夹具把完形答案写成句子所致，属"提请人工复核"而非阻断，符合设计。
- **固化为测试**：新增 `test_six_kinds_with_official_answers_pass_the_whole_chain`，覆盖"答案表解析 → 台账登记 → 构建 → quality_gate/answer_audit 通过"。上一轮（1.0.29）的语法填空缺陷若复发，或指纹/页码依据被绕过，此测试会直接失败。
- **自动测试**：macOS + Python 3.11.0b2 上 96 项全部通过。
- **安装完整性**：`complete`，84 个文件。

## 未覆盖边界

- 仍是合成材料与合成音频；真实试卷的 OCR、真实答案册的版式（表格型、跨行）以及真实听力切点仍需实机验证。
- 反向验证仍聚焦答案链；教学内容正确性依旧依赖人工复核。
- Windows 与真实宿主仍未实机验收（同 1.0.16）。

---

# 1.0.29 语法填空答案解析复查

本版修掉一个会让整个"语法填空"题型无法通过答案门禁的缺陷。

## 本次实际执行

- **复现**：构造含字母答案与语法填空单词答案的答案原件（`21-25 ABCDA`、`56. which`、`57. where`、`58. has been`、`59. to make`）。修复前 `answers.py extract` 只解析出 21–25，其余四行全部进入 `unparsed`（原因"含数字但未识别出题号+答案"）。
- **确认下游阻断**：对一份 `answer_status=official` 的语法填空题运行 `quality_gate`，得到 `answer_key_entry_missing`（"答案原件解析表里没有第 56 题，无法证明这是官方答案"）——即任何带官方答案的语法填空都会被卡死，而文档建议的"换一份可读的答案原件"无法解决，因为解析器结构上只认 A–H 字母。
- **修复后复验**：
  - 解析结果包含 `56:which`、`57:where`、`58:has been`、`59:to make`，`unparsed` 为空；
  - 变体写法 `59. which/that`、`61. which (that)` 取第一个变体；`60. to make (to do)` 去掉变体提示括号得 `to make`；
  - 反例：`21. What does the man suggest?` 与超长陈述句均**不**被当作答案（`answers` 为空）；
  - 语法填空题的 `answer_key_entry_missing` 消失；把答案原件改成冲突值（`that`）仍以 `answer_key_mismatch` 阻断。
- **自动测试**：macOS + Python 3.11.0b2 上 95 项全部通过，新增 3 项（单词/短语答案提取、题干不被误读、语法填空 official 答案的命中与冲突）。
- **安装完整性**：`complete`，84 个文件。

## 未覆盖边界

- 只覆盖常见答案原件写法（`N.`、`N、`、`N `，含 `/` 或括号变体）；表格型、跨行续写的答案版式仍可能需要人工整理或在 `unparsed` 中逐行确认。
- 单词答案仍要求是英文且不超过 4 个词；超长或纯中文答案不会被自动采纳（宁可留在 `unparsed` 人工确认，也不误收）。
- Windows 与真实宿主仍未实机验收（同 1.0.16）。

---

# 1.0.28 生成计划 profile 字段复查

本版修掉一个"文档要求写、代码静默忽略"的配置字段，其失败模式正是老师抱怨的生成过慢。

## 本次实际执行

- **复现**：准备缺少 sentences/structure/writing_bank 的课件数据与一份 `"profile":"quick"` 的计划。
  - 只传 `--plan`（计划里已是 quick）→ 构建按 full 要求执行，**exit 1**：`A: missing feature content sentences`；
  - 同一份计划再加 `--profile quick` → **exit 0**，报告 `profile: quick`。
  说明 `apply_plan` 只读取 `sections`/`mode`/`features`，`profile` 从未被使用。
- **修复后复验**：
  - 只传 `--plan`（计划 quick）→ exit 0，报告 `profile: quick`，`missing_enrichment=[sentences, structure, writing_bank]`；
  - 计划不含 profile → 按 full 执行（缺精读则按预期失败）；
  - 显式 `--profile full` + 计划 quick → 显式参数生效（按 full 执行）；
  - 计划写非法值 `fast` → 明确报错，不静默降级为 full。
- **修复内容**：`build()` 的 profile 解析改为"命令行 → 计划 → full"，`--profile` 默认值改为未指定；`apply_plan` 校验并保留 `profile`，写入 `generation_preferences`。
- **自动测试**：macOS + Python 3.11.0b2 上 92 项全部通过，新增 `test_plan_profile_is_honoured_without_the_cli_flag`（含显式参数覆盖）与 `test_plan_rejects_an_unknown_profile`。
- **安装完整性**：`complete`，84 个文件。

## 未覆盖边界

- 只验证 profile 的读取与优先级，未测量 quick/full 在真实大卷上的实际耗时差异（需真实材料）。
- 计划里其余字段（材料路径、各阶段状态）仍只是记录，不参与构建。
- Windows 与真实宿主仍未实机验收（同 1.0.16）。

---

# 1.0.27 精听挖空与逐段译文实机验收复查

本版不改产品功能，继续打开此前从未在浏览器中执行过的核心交互。上一轮（1.0.26）用同样方法翻出了一个真实缺陷，本轮把用户最关心的"遮住关键词语"与"逐段译文"补上实机断言。

## 本次实际执行

- **精听挖空**：新增检查断言——勾选「关键表达挖空」后，被遮位置渲染为占位符 `____` 而不是单词；**开启期间该节答案不会停留在展开状态**（`ui.openAnswers` 不含该节题目）；点击该空后显示的文字等于**转写原文中该区间的真实切片**。实测通过（`listening-dictation-hides-and-reveals-real-words`）。
- **逐段译文**：新增检查断言——译文默认隐藏；点「本段中译」后出现且内容非空；再次点击收起。实测通过（`paragraph-translation-toggles`）。
- **实测总数**：`node scripts/browser_check.cjs FIXTURE --stress` 由 20 项扩为 **22 项全部通过**，另含章节导航与词句、字号主题持久化、速对答案、画笔四工具、批注与课堂弹窗、教师改答案校验与恢复、文化卡片与定位、深读结构渲染与定位、写作迁移标签、功能开关、听力播放与倍速、内嵌音频隔离、六种异常恢复、禁用脚本静态指引。
- **过程记录**：本轮我的断言又错了一次——译文块与按钮是**兄弟节点**（`button` 在 `.pactions` 内，`.translation` 在其外），初次用 `xpath=..` 找不到目标；改为 `../..` 后通过。属断言写错，产品行为正确。
- **自动测试**：macOS + Python 3.11.0b2 上 90 项全部通过。
- **安装完整性**：`complete`，84 个文件。

## 未覆盖边界

- 挖空检查验证"遮住的是原文真实切片"与"不泄漏答案"，未逐空核对全部空位与逐空揭示/全显/重置三种操作的组合。
- 译文检查验证显示与收起，未核对译文语义正确性（那需要人工比对）。
- 浏览器验收仍依赖本机 Node + Playwright + 浏览器；CI 只跑标准库测试。
- Windows 与真实宿主仍未实机验收（同 1.0.16）。

---

# 1.0.26 深读标签盲区与结构定位失效复查

本版由一个覆盖盲区牵出一个真实交互缺陷：篇章结构的"定位原文"按钮此前点击无效。

## 本次实际执行

- **先补盲区**：浏览器验收脚本对"篇章精读／写作迁移"两个标签**只验证关闭时不出现，从不打开**。本轮实际切到这两个标签，断言内容渲染与定位行为。
- **随即暴露真实缺陷**：新增断言后立即失败——点击结构条目**没有产生任何原文高亮**。定位到模板：事件处理是 `const step=s.logic_steps?.[+b.dataset.index]`，而结构条目渲染的按钮**没有 `data-index`**，`+undefined` 为 `NaN`，`s.logic_steps[NaN]` 为 `undefined`，因此 `state.marks` 不会被写入。`inquiry`（课堂追问）的定位按钮同样缺 `data-index`，存在同一问题。
- **修复**：结构条目与追问条目补 `data-kind` / `data-index`，处理函数按 `data-kind` 选择 `s.structure` / `s.inquiry` / `s.logic_steps`；结构条目改为用其 `quote` 高亮来源句（该字段自 1.0.15 起为必填，此前只在构建校验中使用）。`logic_steps` 与 `bankLocate` 原本就带 `data-index`，行为不变。
- **实测**：`node scripts/browser_check.cjs FIXTURE --stress` 由 18 项扩展为 **20 项全部通过**，新增 `deep-reading-structure-renders-and-locates`（结构行数量=structure+logic_steps，且点击后对应段落被标记）与 `writing-transfer-tab-renders`（写作迁移卡片数量=writing_bank 数量，且"定位原句"能标记来源段落）。
- **过程记录**：本轮我自己的断言也错过两次——先按 `.logic-card` 计数（该 class 同时用于结构与逻辑信号词，2+2=4），后按"标记数量增加"判断（处理函数会先清空 `state.marks`，数量可能下降）。两次都是断言写错、产品行为正确，已改为精确断言。
- **自动测试**：macOS + Python 3.11.0b2 上 90 项全部通过；模板哈希已按 1.0.26 更新并在构建时核对通过。
- **安装完整性**：`complete`，84 个文件。

## 未覆盖边界

- 本轮只验证"点击后该段落被标记"，未逐条核对高亮范围与视觉呈现（文化背景与证据句高亮另有覆盖）。
- 浏览器验收仍依赖本机 Node + Playwright + 浏览器，CI 只跑标准库测试。
- Windows 与真实宿主仍未实机验收（同 1.0.16）。

---

# 1.0.25 文化背景界面验收盲区复查

本版修掉一个"检查存在但从未执行"的覆盖盲区：文化背景卡片的界面验收一直被静默跳过。

## 本次实际执行

- **定位盲区**：`scripts/browser_check.cjs` 的文化背景检查条件是"课件含 `culture_background` 且数量非零"，而 `tests/make_browser_fixture.py` 从 1.0.14 起只设置 `culture_note`（无必要背景的说明）。因此该检查自加入起从未运行，文化背景的折叠、来源展示与"定位到原文"交互没有任何自动验收记录。
- **修复**：夹具改为携带一条合法文化背景条目（真实原文引句 + `reading_connection` + 带 `supports` 的来源），构建时通过 `scripts/culture.py` 校验；界面检查现在会实际打开卡片并点击定位。
- **实测**：`node scripts/browser_check.cjs FIXTURE --stress` 返回 **18 项全部通过**，含新增实际执行的 `culture-card-and-source-location`；其余为章节导航与词句、字号主题持久化、速对答案、画笔四工具与撤销清空、批注与课堂弹窗、教师改答案的校验与恢复、功能开关、窄屏导航、听力播放与倍速、内嵌音频在阻断外部文件后仍播放、六种异常恢复、禁用脚本静态指引。
- **防回归**：新增测试断言夹具必须携带可被 `validate_culture` 通过的 `culture_background`，避免再次退化为静默跳过。
- **自动测试**：macOS + Python 3.11.0b2 上 90 项全部通过。
- **安装完整性**：`complete`，84 个文件。

## 未覆盖边界

- 夹具中的文化背景是界面测试条目，不主张真实文化结论；真实背景的事实正确性仍需人工查证来源。
- 该界面验收依赖本机 Node + Playwright + 浏览器，CI 工作流只跑标准库测试，因此这条仍需在装了浏览器工具的机器上执行（本机已执行）。
- Windows 与真实宿主仍未实机验收（同 1.0.16）。

---

# 1.0.24 答案溯源指纹链路复查

本版补上答案真实性链条中长期缺失的一环，并首次为整条链建立回归测试。

## 本次实际执行

- **实测链条各道门禁**（构造完整台账 + 答案原件 + 解析表，逐一破坏）：
  - official 答案但台账缺 `answer_reference` → `answer_provenance` 阻断；
  - 台账没有 `role=answers` 原件 → `official_answer_file` 阻断；
  - `answers.json` 缺 `answer_source_sha256` → `answer_key_provenance` 阻断；
  - **解析表指纹与台账登记的答案原件不一致 → 新增 `answer_key_not_registered` 阻断**（修复前可通过）；
  - official 答案与解析表冲突 → `answer_key_mismatch` 阻断；
  - 解析表缺该题 → `answer_key_entry_missing` 阻断；
  - 全部一致 → `structural_checks_passed` 且 `answer_audit=answer_checks_passed`，`official=1`。
- **修复内容**：`quality_gate.py` 在存在 official 答案时，要求解析表指纹等于台账 `role=answers` 原件的 sha256；台账该原件未登记指纹时也会阻断。
- **自动测试**：macOS + Python 3.11.0b2 上 89 项全部通过；新增 `tests/test_provenance.py` 8 项锁定上述七种情形。
- **安装完整性**：`complete`，84 个文件。

## 未覆盖边界

- 只验证"解析表来自台账登记的那份文件"；答案原件本身是否被正确识别、答案数值是否与答案 PDF 版式一致，仍需人工逐页核对。
- 未能覆盖多份答案原件（分卷答案）的复杂登记方式，当前按"解析表指纹命中任一 `role=answers` 原件"处理。
- Windows 与真实宿主仍未实机验收（同 1.0.16）。

---

# 1.0.23 版本比较与"降级更新"复查

本版修掉一个会让人把较新安装覆盖成较旧版本的缺陷。

## 本次实际执行

- **复现**：本机 `VERSION=1.0.22`、GitHub 公开最新为 `v1.0.13`，`check_update.py --json` 返回 `status=update_available` 并把下载旧包的步骤放在第一位。按该提示操作会把较新的 `scripts/` 覆盖成较旧的，可能重新引入 1.0.16 已修的 Windows 崩溃。
- **根因**：版本判断是字符串相等（`normalise(current)==latest`），既没有语义排序，也没有"本机更新"这一分支。
- **修复后复验**：同一环境下返回 `status=newer_than_release`，步骤第一条为「本机 1.0.22 比公开最新版 1.0.13 更新……无需降级」，并提示如需回到公开版必须先备份。
- **比较规则实测**：`1.0.2 < 1.0.10`、`1.0.9 < 1.0.10`、`1.9.0 < 1.10.0`；`1.0.15-dev < 1.0.15` 且 `1.0.15-dev > 1.0.14`；`v1.0.13 == 1.0.13`；`1.2 == 1.2.0`。
- **自动测试**：macOS + Python 3.11.0b2 上 81 项全部通过；新增 `tests/test_update.py` 12 项，覆盖排序、预发布后缀、`--offline`、网络失败回退为 `unknown_remote`，以及"较新安装绝不被建议降级"。
- **安装完整性**：`complete`，83 个文件。

## 未覆盖边界

- 联网分支用打桩响应测试，未对 GitHub API 的限流、代理与异常 tag 格式做真实联调；`--offline` 分支已在实机跑通。
- 未验证 SkillHub 等第三方渠道的版本同步（文档已说明不由本脚本负责）。
- Windows 与真实宿主仍未实机验收（同 1.0.16）。

---

# 1.0.22 录入环节健壮性与覆盖率复查

本版修掉"读试卷/读答案"这一入口环节的四处崩溃，并补上此前完全缺失的录入链路测试。

## 本次实际执行

- **复现四处崩溃**（构造坏输入后实际运行）：
  - `extract.py` + 非 zip 文件 → `zipfile.BadZipFile` 堆栈；
  - `extract.py` + zip 无 `word/document.xml` → `KeyError` 堆栈；
  - `extract.py` + DOCX 无 `w:body` → `TypeError: 'NoneType' object is not iterable`；
  - `answers.py` + 非 zip 文件 → `BadZipFile` 堆栈（其 except 未包含该异常）。
- **修复后复验**：四种情况均输出单行中文 `ERROR:` 并返回 1，stderr 无 `Traceback`；有效 DOCX 的抽取与答案解析结果不变（段落/表格/图片顺序、区间与圈号答案）。
- **发现并修掉 `quotes.py check` 的误报（1.0.15 引入的回归）**：篇章结构条目使用 `paragraph_ids`（复数），而 `check` 只认 `paragraph_id`，导致仓库自带示例被误报 2 条"缺少可对应的 paragraph_id"——也就是说所有开启篇章精读的课件都会在 `quotes.py check` 得到假的 `needs_fix`。修复后示例为 `quotes_checked=10, problems=[], status=ok`；把结构引文改成原文里没有的句子后仍能正确报出 `不是所引用段落的逐字子串`。`fill` 同时对单段条目自动定位，对多段条目要求写明 `quote_ref.paragraph_id` 并给出可照抄的示例。
- **新增测试**：`tests/test_ingest.py` 13 项，覆盖上述错误路径、答案区间/圈号解析、重复答案冲突进入 `unparsed`、`answers.py check` 在 official 不一致时 `blocked`（推断答案不一致不阻断）、`extract → answers → scaffold ledger → scaffold exam` 端到端链路（题号、选项 A–D、official 答案、`expected_question_ids`），以及 `quotes.py` 的 fill/check 正例与三类拒绝路径。
- **自动测试**：macOS + Python 3.11.0b2 上 69 项全部通过。
- **安装完整性**：`complete`，82 个文件。

## 未覆盖边界

- 未测试真实 WPS/Word 产出的复杂 DOCX（文本框、图片环绕、修订痕迹、页眉页脚）；文本框中的题干不会被 `w:body` 直接遍历到，仍需人工核对。
- PDF 路径本机未验证（依赖外部渲染/OCR 工具）。
- Windows 与真实宿主仍未实机验收（同 1.0.16）。

---

# 1.0.21 听力与快速档实机验证复查

本版不改功能，补齐此前完全缺失的两条实机验证：听力音频播放，以及快速档。

## 本次实际执行

- **听力（内嵌模式）**：构造含两个话轮的听力课（真实 WAV、`audio_scope=full_paper`、`audio_alignment.mode=unsegmented`、一处精听挖空），构建 `status=structural_checks_passed`、`quality_gate=automated_checks_passed`、`audio_embedded=true`、`embedded_count=1`；`pending_items` 如实标注"听力未分段"。浏览器实测通过 `listening-and-question-media-play-and-speed` 与 `embedded-audio-with-external-audio-blocked`（阻断外部 audio 后内嵌录音仍播放）。
- **听力（目录模式）**：`--audio-mode folder` 构建 `mode=folder`、`embedded_count=0`，`audio/L1.wav` 随包，浏览器播放与倍速通过；内嵌专用检查按预期跳过。
- **抗坍塌校验**：最初把问句与答句合成一个段落时，构建以 `L1: dialogue_collapsed` 阻断；按话轮拆成两段后通过。说明该规则确实在工作。
- **快速档**：在删除句子精讲 / 篇章结构 / 写作积累的数据上以 `--profile quick` 构建成功，`missing_enrichment` 列出 `sentences`/`structure`/`writing_bank`，`delivery_status=quick_profile_content_and_browser_review_required`，`pending_items` 含快速档提示；同一数据用默认 `full` 档按预期被拒。快速档页面通过全部 8 项浏览器检查（功能开关仍为全开）。
- **自动测试**：macOS + Python 3.11.0b2 上 56 项全部通过，新增 `test_listening_lesson_embeds_audio_and_supports_folder_mode` 与 `test_quick_profile_allows_missing_enrichment_but_full_rejects_it`。
- **安装完整性**：`complete`，81 个文件。

## 未覆盖边界

- 本机没有 ffmpeg/ffprobe，因此**未验证**真实切片：本次使用"整卷原音未分段"档，逐题裁剪、静音分段与 WhisperX 对齐仍未实机执行。
- 音频为合成 1 秒静音，只证明播放器与内嵌链路可用，不证明真实语境的切点或识别正确。
- Windows 与真实宿主仍未实机验收（同 1.0.16）。

---

# 1.0.20 缩小范围重建的陈旧素材复查

本版修掉一个会向老师交付无关文件的缺陷：缩小范围重建时，上一轮范围的音频与页图会残留并被一起打包。

## 本次实际执行

- **复现**：构造含 A、B 两节的示例（B 带 `origin.page_image`），先整卷构建得到 `out/sources/B-paper.png`；再用 `--sections A` 重建到同一目录，该文件仍然存在，而 `package_lesson.py` 会打包整个目录 → 交付 ZIP 含不属于本课的页图（真实听力任务下即上一轮的切片音频）。
- **修复后**：构建按自己上一轮写出的 `.build-manifest.json` 删除不再产出的文件；同一流程下 `sources/B-paper.png` 被清除，交付 ZIP 中不再出现。
- **安全性**：手工放入输出目录的 `教师备注.txt`、`sources/我的图.png` 在重建后均保留（清单只记录构建自己产出的路径）；同范围重建幂等，仍需要的素材不被误删；`.build-manifest.json` 以 `.` 开头，确认未进入交付 ZIP。
- **自动测试**：macOS + Python 3.11.0b2 上 54 项全部通过，新增 `test_narrower_rebuild_drops_stale_media_but_keeps_teacher_files` 覆盖"清除陈旧素材 + 保留教师文件"。
- **安装完整性**：`complete`，81 个文件。

## 未覆盖边界

- 清单机制只覆盖构建自己产出的文件；如果输出目录里混入其它工具产生的旧文件，不会被自动清理。
- 旧版构建没有清单，升级后第一次重建不会清理更早留下的陈旧文件；需要时手动删除或先用新版重建一次。
- Windows 与真实宿主仍未实机验收（同 1.0.16）。

---

# 1.0.19 Windows 换行与哈希一致性复查

本版修掉一个只在 Windows 上出现的指纹错位，并加了静态与动态两道守门。

## 本次实际执行

- **复现**：把构建产物的 `index.html` 换成 CRLF（模拟 Windows 的 `write_text`）后，`verify_output` 报 `html_sha256=cd388120…`，而原始字节哈希为 `05c0de04…`；同一个文件出现两个值。
- **修复后**：同一 CRLF 文件两者一致（`05c0de04…`）且 `status=passed`；LF 产物行为不变（`cd388120…`）。
- **定位边界**：`package_lesson.py` 本就使用 `read_bytes()`，交付门槛并未被此缺陷卡住；受影响的是 `build-report.json` 的 `template_verification.html_sha256` 与 `browser-check.json` 的 `html_sha256` 同名不同值，会误导助手判断证据过期。
- **全量审计**：`check_install`、`package_skill`、`package_lesson`、`verify_output`、`quality_gate`、`audio`、`answers`、`audio_wiring`、`scaffold`、`prepare_whisper`、`align_whisperx` 的哈希均已确认基于原始字节。
- **自动测试**：macOS + Python 3.11.0b2 上 53 项全部通过，含新增的 CRLF 动态回归测试与"禁止对 `read_text` 结果做 sha256"的静态守门。
- **安装完整性**：`complete`，81 个文件。

## 未覆盖边界

- 仍未在真实 Windows 上执行；CRLF 为模拟写入，不是真机验证。
- Windows 与真实宿主实机验收仍未完成（同 1.0.16）。

---

# 1.0.18 关闭查词不再夹带词库复查

本版修掉"未选扩展仍生成内容"的一个实际漏洞，并给出可复现的体积数据。

## 本次实际执行

- **复现漏洞**：用 `features.dictionary=false` 的计划构建示例，`exam.json` 仍含 10,836 条词典、`index.html` 为 4,432,140 字节——开关没有真正生效。
- **修复后实测**：同一份示例，关闭查词时 `dictionary` 条目为 0、`index.html` 为 250,724 字节（约 4.18MB / 18 倍差距）；开启查词时仍为 4,432,140 字节，行为不变。
- **浏览器验收补上开关覆盖**：`scripts/browser_check.cjs` 原先无条件点击 `#annotate`，因此"关闭批注"这一受支持配置根本无法验收（首次运行以"element is not visible"失败）。已改为按 `exam.features` 分支：关闭批注时跳过画笔检查并断言入口隐藏；并新增关闭查词时断言 `#lookupForm` 隐藏。
- **实测两种配置**：默认全开产物 8 项全部通过（含画笔/箭头/矩形/椭圆/撤销/清空）；关闭批注+查词的产物 7 项全部通过（画笔项按未选跳过，并断言两个入口隐藏）。说明去掉词库只减少体积，不削弱功能，且未选扩展确实不显示入口。
- **自动测试**：macOS + Python 3.11.0b2 上 51 项全部通过；新增 `test_dictionary_payload_respects_the_feature_toggle` 断言关闭时无 `dictionary`/`legacy_dictionary` 且 HTML 更小。
- **安装完整性**：`complete`，81 个文件。

## 未覆盖边界

- 本版只处理词库这一项大负载；音频与页面图仍按素材实际大小打包，体积取决于老师提供的原卷。
- 关闭查词后的离线查词行为是"入口隐藏"，未评估在线词典回退；如需离线查词请保持开启。
- Windows 与真实宿主仍未实机验收（同 1.0.16）。

---

# 1.0.17 反套话复查

本版针对"AI 用通用套话冒充本题讲解"补上可执行的构建门禁。

## 本次实际执行

- **实测阻断**：把示例第 22 题的 `analysis` 改成与第 21 题相同后，构建非零退出并报 `A: A/22: analysis 与第 21 题完全相同，像是复制套话；请按本题材料分别编写`。
- **自动测试**：macOS + Python 3.11.0b2 上 50 项全部通过。`tests/test_grounding.py` 增至 9 项，新增复制套话（四个字段）、重复解题步骤、空辨析、雷同辨析、占位标记等断言，并含"策略不含占位"的误判防护。
- **无误伤**：仓库原创示例（两题内容本就不同）构建仍然通过，`structural_checks_passed` / `automated_checks_passed`。
- **安装完整性**：`package_skill.py` 返回 `status=complete`，81 个文件。

## 未覆盖边界

- 套话检测只覆盖"完全相同"这一确定性信号；措辞略有改动的空泛讲解仍可能通过，语义质量仍需人工复核。
- Windows 与真实宿主仍未实机验收（同 1.0.16）。

---

# 1.0.16 Windows 控制台与宿主探测复查

本版修掉一个会在中文 Windows 上直接阻断"第一条命令"的编码缺陷，并把 Windows 可移植性与宿主能力探测变成可重复的自动检查。

## 本次实际执行

- **复现原缺陷**：`PYTHONIOENCODING=cp1252 python3 scripts/check_install.py` 在修改前报 `UnicodeEncodeError: 'charmap' codec can't encode characters`；输出经管道重定向时同样触发，而助手抓取输出几乎总是走管道。`package_skill.py`、`cost.py` 同样复现。
- **修复后复验**：三个入口在 `PYTHONIOENCODING=cp1252` 下均无 `UnicodeEncodeError`、无 traceback；`check_update.py` 原本已自行 `reconfigure`，未受影响。
- **自动测试**：macOS + Python 3.11.0b2 上 47 项全部通过。其中 `tests/test_portability.py` 7 项扫描全部脚本（禁止 `shell=True`/`os.system`，文本 I/O 与文本模式子进程必须显式编码，POSIX 调用按 `os.name` 分支，CLI 入口必须强制 UTF-8）并实跑 cp1252 控制台；`tests/test_windows_paths.py` 4 项直接进入 Windows 专用分支（LOCALAPPDATA 下的 `.exe` 查找、Windows 运行时目录、进程组创建、超时用 taskkill 结束进程树）；`tests/test_host_probe.py` 5 项覆盖能力探测与回退说明。
- **宿主探测实跑**：`scripts/host_probe.py --json` 正确报告 read_package / write_files / run_python / node / playwright / browser / ffmpeg / whisper；未设 `PLAYWRIGHT_MODULE` 时为 `preview_only_browser_check_pending`，设置后变为 `browser_check_possible`，说明结论跟随真实能力变化。
- **安装完整性**：`scripts/package_skill.py` 重新生成清单后返回 `status=complete`，79 个文件。

## 发布前修复

- `check_install.py`、`package_skill.py`、`cost.py` 入口新增 `force_utf8()`；`check_update.py` 原本已用 `reconfigure`。
- `package_skill.py` 读取 `VERSION` 由隐式编码改为显式 `encoding='utf-8'`。

## 未覆盖边界

- **Windows 仍未实机执行**：上述修复由 cp1252 模拟与静态扫描验证，未在真实 Windows 上跑完整链路；`docs/WINDOWS.md` 的实机清单仍需执行后才算通过。
- **真实宿主未实测**：豆包工作、WorkBuddy 未实机验收；`host_probe` 报告的是本机能力，不替代该宿主的端到端实测。
- **听力工具未安装**：ffmpeg / whisper 本机缺失，听力档位的实跑未验证。

---

# 1.0.15 内容锚定与可测性复查

本版把"教学内容不许编造"变成构建规则，给构建补上耗时与编写量报告，并增加宿主回退与 Windows 验收文档。以下为本机实际执行结果与未覆盖边界。

## 本次实际执行

- **安装完整性**：`python3 scripts/check_install.py` 对 1.0.15 完整包返回 `status=complete`，逐文件校验 76 个文件，无哈希差异。
- **自动测试**：`python3 -m unittest discover -s tests` 在 macOS + Python 3.11.0b2 上 31 项全部通过，含新增的 6 项引文锚定测试与 4 项编写量/耗时测试。
- **反编造确实阻断构建**：把 `structure[0].quote` 改成原文中不存在的句子后，构建非零退出并输出 `A: structure[0]: quote 不在所引用段落的原文中`；vocabulary 缺少 context/quote、quote 不含该词形、听力挖空遮半词或标点，均由 `tests/test_grounding.py` 断言拒绝。
- **示例构建**：构建原创阅读示例成功；`quality_gate=automated_checks_passed`、`answer_audit=answer_checks_passed`、模板核验 `status=passed`（comparison=exact，`template_version=1.0.15`）。
- **耗时与编写量可见**：`build-report.json` 的 `timing` 记录 prepare_audio / validate / quality_gate / answer_audit / render_and_write；`authoring_cost` 记录 `authored_chars=1285`、`inline_quotes=10`、`estimated_quote_ref_saving=300`。注入的离线词典不会被计入编写量（有专门测试锁定）。
- **真实浏览器操作**：本机 Chrome 152（Playwright 驱动，headless）运行 `scripts/browser_check.cjs`，8 项全部通过；`browser-check.json` 绑定所测 `index.html` 的 SHA256（`cd388120…`），`errors` 为空。
- **交付门槛**：`python3 scripts/package_lesson.py` 在存在当期浏览器记录时返回 `status=browser_checked`。

## 发布前修复

- `cost.py` 首次接入构建时，把注入的 10,836 条离线词典当成"需编写内容"（`authored_chars` 一度为 317,892）。已让分析跳过 `dictionary`/`legacy_dictionary`，并加回归测试锁定。
- `examples/demo-reading.json` 与 `demo-exam.json` 保持字节一致，同步补上真实的 structure quote；`source-ledger.json` 的来源哈希随之更新（源完整性链条按预期拦下了旧哈希）。

## 未覆盖边界（不冒充已验证）

- **Windows 未实机执行**：跨平台工作流只在配置层面就绪，本机无法运行 `windows-latest`。`docs/WINDOWS.md` 已明确标注"作者尚未在真实 Windows 上跑完整链路"，其命令与判定标准要实机执行后才算通过。
- **WhisperX / ffmpeg 未安装**：WhisperX 对齐、真实分段与音频播放未实机验收；本次浏览器检查用的是无音频的原创阅读示例。
- **无真实试卷**：构建使用仓库原创示例，不能作为真实试卷识别、答案正确性或教学质量的证明。
- **宿主未实测**：`references/host-compatibility.md` 的宿主判断是先验说明，已按"通常具备 / 不确定 / 以实测为准"限定；WorkBuddy、豆包工作与纯聊天窗口本次均未实机验收。
- **CI 不等于整卷验收**：绿色只代表标准库测试通过，不含 Node/Playwright 浏览器操作，也不含真实材料。

---

# 1.0.14 功能复查记录

本版把开发分支（1.0.14-dev）并入正式版本，重点是 WhisperX 原文对齐、生成前功能多选、文化背景可溯源规范和备课编辑就地输入。以下为本机实际执行的结果与未覆盖边界。

## 本次实际执行

- **安装完整性**：`python3 scripts/check_install.py` 对 1.0.14 完整包返回 `status=complete`，逐文件校验 70 个文件，无哈希差异。
- **自动测试**：`python3 -m unittest discover -s tests` 在 macOS + Python 3.11.0b2 上 21 项全部通过，含文化背景规范、功能选择、WhisperX 准备与音频复用、交付门槛等。
- **示例构建**：`python3 scripts/build.py examples/demo-exam.json OUT --source-ledger examples/source-ledger.json` 构建原创阅读示例成功；`quality_gate=automated_checks_passed`、`answer_audit=answer_checks_passed`、模板核验 `status=passed`（comparison=exact，`template_version=1.0.14`）。
- **真实浏览器操作**：用本机 Chrome 152（Playwright 驱动，headless）运行 `scripts/browser_check.cjs`，8 项全部通过：章节导航与词句、字号与主题持久化、速对答案两种模式且无解析副作用、画笔/箭头/矩形/椭圆/撤销/清空、批注与课堂弹窗、教师改答案的校验与持久化/恢复/导入、功能开关受控、窄屏导航与弹窗。`browser-check.json` 绑定所测 `index.html` 的 SHA256（`4da2462d…`），与 build-report 一致，`errors` 为空。
- **交付门槛**：`python3 scripts/package_lesson.py` 在存在当期浏览器记录时返回 `status=browser_checked`。

## 发布前修复

- 开发分支把 1.0.13 的已发布说明误改为包含新开关「批注、查词」；正式版恢复 1.0.13 原文，并在 1.0.14 章节说明这两个开关。
- `VERSION` 与 `assets/template-manifest.json` 从 `1.0.14-dev` 提升为 `1.0.14`；模板 SHA256 未变（`44dab9df…`）。
- 打包前 `install-manifest.json` 因内容修改而过期，会令 `check_install` 返回 `incomplete_install`，并使 `doctor` 提前返回、缺少 `capability` 字段（自动测试因此 1 失败 1 错误）。用 `scripts/package_skill.py` 重新生成清单后 21 项全部通过。这是发布顺序问题，不是运行缺陷。

## 未覆盖边界（不冒充已验证）

- **Windows 未实机执行**：本次仅在 macOS 运行。跨平台路径、UTF-8 控制台与便携工具定位由自动测试覆盖（含 `tests/test_whisper_setup.py` 的 Windows 架构与摘要检查），但不等同于 Windows 实机整卷生成，仍需在 Windows 上另做一次真实小样验收。
- **WhisperX / ffmpeg 未安装**：本机没有 ffmpeg、ffprobe、whisper-cli，因此 WhisperX 对齐、真实分段与音频播放未实机验收；实际转写准确性仍需真实听力材料复核。~~`align_whisperx.py` 的校验与拒绝逻辑由自动测试覆盖~~ —— **此处当时的说法不成立**：全仓 `tests/` 当时没有任何文件引用 `align_whisperx.py`。该模块的校验与拒绝逻辑是在 **1.0.99** 才补上自动测试（`tests/test_align_whisperx.py` 12 项，并做了反向测试）。
- **无真实试卷**：构建使用仓库原创示例，不能作为真实试卷识别、答案正确性或教学质量的证明。
- **宿主与手机未实测**：豆包工作、WorkBuddy 的整卷链路与手机浏览器（含微信内置浏览器）本次未实测。
- **1.0.13 无独立验证记录**：本文件此前停在 1.0.12；1.0.13 的变动未单独留档，如需追溯应以对应提交的跨平台工作流结果为准。

---

# 1.0.12 启动与交付可靠性复查（历史记录）

本版新增真实浏览器操作脚本 `scripts/browser_check.cjs`，报告绑定所测 HTML 的 SHA256。测试入口与源码随仓库保留，可重复运行。此前版本记录附在后文。

- 本机 Chrome：六题型原创/合成测试材料构建成功；逐节导航、逐题解析、逐段译文、词句弹窗、六主题、字号刷新保存、速对答案两种模式、四种实际画笔/撤销/清空、课堂弹窗通过。
- 听力：实际播放整段及两题音频、切换倍速；阻断外部 audio 文件后内嵌录音仍能播放。测试声音为合成音，不能用于证明真实语境切点。
- 异常恢复：禁用系统朗读、存储不可用、旧课堂记录损坏、小组积分记录损坏、缺少原生 dialog、缺少 Canvas 均能继续导航和打开课堂工具。禁用 JavaScript 时可见静态打开指引。缺少能力的功能明确不可用，不冒充完整环境。
- 文件验收：十项 Python 测试含缺失/过期浏览器记录拦截、HTML 截断拒绝、跨章节段落 ID 冲突拒绝、中文/空格路径、听力内嵌等。
- 持续集成：Windows/macOS/Linux × Python 3.9/3.11；另加入 Windows Edge、Linux Chromium、macOS WebKit 实际点击。每次发布查看对应提交的 [工作流结果](https://github.com/hututu-ai/english-exam-studio/actions/workflows/compatibility.yml)，失败不计为通过。

**验证边界**：上述浏览器测试经本机 HTTP 打开产物，不是 file:// 双击或 WorkBuddy/豆包整卷生成实机认证。WorkBuddy 以前生成过真实课件，豆包完整实机链路仍未验证。待教师提供具体故障文件、系统和打开方式后才能判定那一次失败原因。源码/模板一致、浏览器可操作与教学内容正确分别核对。

---

# 1.0.7 功能复查记录

本次围绕老师反馈复查生成范围、生成耗时、Windows 环境、音频交付和速对答案。测试材料为原创示例与合成音频；合成音频只用于验证播放器，不证明真实试卷的切点或解析正确。

| 要求 | 本版措施与检查 | 验证边界 |
| --- | --- | --- |
| Windows 可用 | 中文与空格路径、UTF-8、便携工具定位、依赖命令超时、构建和成品核验加入自动测试 | 每次发布以对应提交的 Windows/macOS/Linux 工作流结果为准；不等于每一种 Agent 整卷实机验收 |
| 生成更快 | 先选范围，只处理相关材料；复用带时间转写和切片；原音相同文件只打包一次；局部修改不重新生成整卷 | 未用多台教师电脑测完整生成耗时，不承诺固定分钟数或提速百分比 |
| 首次选择范围 | SKILL、快捷调用元数据、README 和安装教程统一先询问；脚本支持整卷、题型、章节与精听 | 弹窗由宿主提供；无弹窗时用对话问，未答不默认整卷 |
| 部分生成 | 仅阅读、仅精听分别构建并核验；未选听力不因缺录音阻止阅读输出；精听模式二次构建继续保留 | 所选板块仍用完整功能档，快速档需用户明确选择 |
| 防止漏题 | 全范围生成保留原定题号清单；未知章节或 all 与其他条件混用直接提示错误 | 原文、答案和题号仍需从输入材料独立整理台账 |
| 速对答案 | 实际点击分范围、逐题/批量显答与隐藏、多答案、来源、题号跳转；写作不混入；原有解析状态保持 | 本机 Chrome 测试；1280、800、390 像素宽度弹窗无横向溢出 |
| 听力随 HTML 交付 | 把成品复制到不含 audio 目录的临时目录，实际播放整段、两道题录音、0.5/0.75 倍速；切章暂停，展开解析保留播放器 | 页面由本机静态预览打开；播放的是合成测试音频，真实语义边界须按卷抽查 |
| 下载卡住 | 先复用可运行工具；缺失、不能运行和缺编码器分别处理；安装尝试有总时限；超时停止，续做可完成板块 | 不改变教师代理设置，也不能保证第三方下载服务永不出错 |
| 豆包使用说明 | README 给出完整包、能力确认、选择范围、生成与验收的步骤 | 尚未完成豆包整卷实机验收；不虚构固定技能导入菜单 |
| 原有外观 | 六种浅色主题均实际切换；保留原文与题目、逐题解析、译文及教师工具 | 本次重点检查新增及受影响路径，不把它写成所有功能全覆盖 |

## 可复核的自动检查

[跨平台工作流](https://github.com/hututu-ai/english-exam-studio/actions/workflows/compatibility.yml) 对 Windows、macOS、Linux 分别使用 Python 3.9 与 3.11，运行八项测试、构建原创阅读示例并核验输出。请查看所下载版本对应的提交结果。

测试包含：范围与顺序、原定题号清单、未选板块跳过、环境工具可执行性、命令超时、分节数据无损合并、内嵌与外置音频、损坏音频检测、带时间转写复用、原音/时间窗变更后的切片重做。

## 每张新试卷仍应检查

生成成功报告分别列出结构、来源台账、音频字节/解码、实际播放和语义边界的完成情况。老师上课前抽查答案及关键音频。工具缺失时只报告实际交付的功能；未分段原音不能当作逐题精听已完成。
