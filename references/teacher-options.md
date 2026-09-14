# 先选课型，再选功能

安装完成后，若宿主支持对话，先邀请老师上传本次试卷、参考答案和有则提供的听力音频；否则首次调用时问。先快速盘点附件有哪些题型、答案是否含听力原文，再按实际材料询问以下两项，可以一次问完。只追问所选范围的缺失材料，安装阶段不下载语音模型。用户已明确或提供可沿用的偏好时简短确认采用即可。没有回答，不默认生成整卷。

第一问：这次做 **独立听力精听 / 整卷讲评 / 指定板块（可多选）**？指定板块按原卷目录选择，精听保留真实 Test 与题号，无需生成阅读等板块。

第二问：扩展内容选哪些？**课堂批注、查词、速对答案、课堂工具、篇章精读、写作迁移、文化背景解读**。支持“全部”“基础讲评即可”“沿用上次设置”；精听推荐基础功能，可另选词句之外的扩展。基础功能保留原文、题目、答案与解析、定位、必要译文、音频/倍速/精听挖空、备课修订及记录导出。未选择的扩展不生成、不显示空入口；不是把完整档偷偷改为快速档。

将老师的两项回答记录成 generation-plan.json，并用 `build.py ... --plan generation-plan.json` 构建：

```json
{"confirmed":true,"sections":"listening","mode":"intensive","profile":"full","features":{"annotations":false,"dictionary":false,"classroom_tools":false,"quick_answers":true,"writing_transfer":false,"deep_reading":false,"culture_background":false}}
```

`sections` 接受 `all`、题型或实际章节 ID 逗号组合，`mode` 为 lesson/intensive，`profile` 为 full/quick，七个功能值必须全部记录。confirmed 只有收到范围和功能回答后才能置 true。迁移旧 exam.json 未带 features 时保留旧功能；新任务必须传计划，不能为了绕过未回答把 confirmed 直接填真。

`profile` 的优先级：命令行 `--profile` 最高，其次计划里的 `profile`，都没有时为 `full`。也就是说老师同意"先出可上课版"时，把 `profile":"quick"` 写进计划即可，不必再额外记一个命令行参数；写错的值（例如 `fast`）会被明确拒绝，不会静默按 full 运行。

## 文化背景

选中才编写，每篇精选理解原文确实需要的背景。字段 `culture_background` 为数组，每项含 `title`、`paragraph_id`、逐字 `quote`、`explanation`（背景事实）、`reading_connection`（这段背景怎样解释本篇，不能与 explanation 重复）、`teaching_note`（课堂怎么用）、`sources`（每项要有 `title`、http(s) 的 `url` 与 `supports`——这条来源支撑哪一句背景）。少任何一栏构建都会拦下并说明缺哪一栏。外部事实查可靠来源，区分原文信息与背景补充，避免民族性格概括及把背景当答案证据。不为凑数量硬写；本篇没有必要或资料无法确认时用 culture_note 说明。本篇顶部“文化背景”可直接打开；原文之后也保留折叠卡，保持逐段译文与原文位置。

## 备课编辑

顶栏“备课编辑”后，展开解析，点击虚线框内的题型、步骤、答案依据或方法迁移即可直接输入，失去焦点保存，Esc取消。答案、定位依据和其他复杂字段仍用题旁“修改讲解”，可改本班答案、题型、答案依据、解题步骤、选项辨析、方法迁移和易错提醒。选择题答案必须是现有选项；填空可逐行填写可接受答案；解法步骤按教师实际需要，允许少于三步。定位引句仍须来自真实原文。

原参考答案与解析保留，可恢复。修订答案标为“教师修订”，与速对答案同步；不修改来源台账或伪装官方答案。修订存在当前浏览器课堂记录中，换电脑或升级前导出记录，另一台导入恢复。并不自动改写硬盘原 HTML；不要宣称只发送 HTML 就携带浏览器里刚做的修改。

examples/teaching-plan.json 是合成界面测试示例，不是老师的已确认选择；新任务必须从实际回答建立自己的计划。

## 多选交互必须落实

范围为单选（指定板块时再多选）；功能用宿主真正支持的多选控件展示上述七项，只有勾选项启用，不预选全部。宿主仅支持单选时不能伪装多选，改为编号清单，让老师一次回复多个编号（例如“1、2、5”），也支持全部、都不要、沿用上次。不逐项问七轮。未回复保持待确认，不开始重处理。annotations 控制画笔和文字批注；dictionary 控制输入查词、点击查词及划选查词；词句教学内容与查词工具区分。原件、答案溯源、基本讲解、播放、备课编辑及记录导出不因关闭扩展而消失。

**编号清单与计划直接交给脚本，不要手写。** 无多选控件时先打印菜单：

```bash
python3 scripts/plan.py menu
```

老师回复后原样转换（编号顺序就是菜单顺序，七项一定会全记）：

```bash
python3 scripts/plan.py make --confirmed --range B --features 1,3,5 --out generation-plan.json
python3 scripts/plan.py make --confirmed --range C --sections reading,A --features 沿用上次 --previous 上次的plan.json
python3 scripts/plan.py check generation-plan.json
```

`--range`：A 独立听力精听（intensive）/ B 整卷（all）/ C 指定板块（需 `--sections`）。`--features` 接受编号、`全部`、`基础讲评即可`、`沿用上次`。**`--confirmed` 是必填**：只有真的收到老师回答才加，脚本不替老师回答（缺它会直接报错，不会写出一份假计划）。

文化背景被选中时，必须执行 [本篇文化背景规范](culture-background.md)：原文切入、已查证背景、回到本篇的理解和课堂讲述。新生成数据必须填写 reading_connection 与来源 supports，并完成语义复核；不接受测试占位卡或通用百科拼贴。
