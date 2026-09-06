# 原创阅读演示：Repair, Learn, Share

本例为英语实战讲评 Skill 专门编写，包含两段原创阅读和两道原创题目，附自拟答案、译文、篇章分析、词句和写作迁移。所有题目 answer_status 为 sample，不属于真实考试。

`demo-exam.json` 和 `demo-reading.json` 是同一份阅读示例，保留两个入口便于首次使用。构建本例只需 Python，不需要 FFmpeg、AI API 或听力模型：

```bash
python3 scripts/build.py examples/demo-exam.json output/demo
```

从仓库根目录执行，然后用浏览器打开 output/demo/index.html。试用逐题显答、原文定位、段落翻译、写作迁移、查词、批注和六种浅色主题。

公开示例不附带录音，也不代表完整考试的范围。真实听力由用户提供原始音频后交给 Agent 处理；README 的听力界面截图来自本地原创测试，截图只展示界面。

预先整理好的 JSON 便于验证构建环境；老师制作新试卷时只需给 Agent 材料，不用照着示例手写 JSON。
