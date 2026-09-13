# 先选课型，再选功能

安装完成后，若宿主支持对话，询问本次任务；否则首次调用时问。用户已明确或提供可沿用的偏好时简短确认采用即可。没有回答，不默认生成整卷。

第一问：这次做 **独立听力精听 / 整卷讲评 / 指定板块（可多选）**？指定板块按原卷目录选择，精听保留真实 Test 与题号，无需生成阅读等板块。

第二问：扩展内容选哪些？**课堂工具、速对答案、写作迁移、篇章精读、文化背景解读**。支持“全部”“基础讲评即可”“沿用上次设置”；精听推荐基础功能，可另选词句之外的扩展。基础功能保留原文、题目、答案与解析、定位、词句查阅、必要译文、音频/倍速/精听挖空、备课修订及记录导出。未选择的扩展不生成、不显示空入口；不是把完整档偷偷改为快速档。

将老师的两项回答记录成 generation-plan.json，并用 `build.py ... --plan generation-plan.json` 构建：

```json
{"confirmed":true,"sections":"listening","mode":"intensive","features":{"classroom_tools":false,"quick_answers":true,"writing_transfer":false,"deep_reading":false,"culture_background":false}}
```

`sections` 接受 `all`、题型或实际章节 ID 逗号组合，`mode` 为 lesson/intensive，五个功能值必须全部记录。confirmed 只有收到范围和功能回答后才能置 true。迁移旧 exam.json 未带 features 时保留旧功能；新任务必须传计划，不能为了绕过未回答把 confirmed 直接填真。

## 文化背景

选中才编写，每篇精选理解原文确实需要的背景。字段 `culture_background` 为数组，每项含 title、paragraph_id、逐字 quote、explanation、teaching_note、sources（title/url）。外部事实查可靠来源，区分原文信息与背景补充，避免民族性格概括及把背景当答案证据。不为凑数量硬写；本篇没有必要或资料无法确认时用 culture_note 说明。展示在原文之后的折叠卡，保持逐段译文与原文位置。

## 备课编辑

顶栏“备课编辑”→题旁“修改讲解”，可改本班答案、题型、答案依据、解题步骤、选项辨析、方法迁移和易错提醒。选择题答案必须是现有选项；填空可逐行填写可接受答案；解法步骤按教师实际需要，允许少于三步。定位引句仍须来自真实原文。

原参考答案与解析保留，可恢复。修订答案标为“教师修订”，与速对答案同步；不修改来源台账或伪装官方答案。修订存在当前浏览器课堂记录中，换电脑或升级前导出记录，另一台导入恢复。并不自动改写硬盘原 HTML；不要宣称只发送 HTML 就携带浏览器里刚做的修改。

examples/teaching-plan.json 是合成界面测试示例，不是老师的已确认选择；新任务必须从实际回答建立自己的计划。
