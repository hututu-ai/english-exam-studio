# 第三方来源与许可

## 随包分发的词库

- 文件：`assets/offline-dictionary.json`。
- 来源：[skywind3000/ECDICT](https://github.com/skywind3000/ECDICT)，公开包筛选的 10,836 条基础词条；每条保留来源标签。
- 许可：MIT，完整原文见 [assets/ECDICT-LICENSE.txt](assets/ECDICT-LICENSE.txt)，保留上游版权行。
- 这是供课堂基础查询使用的子集，不是完整 ECDICT、官方高考词频库或语境义生成模型。释义与词形资料可能仍有局限，可结合实际原句核对。
- 创建者旧课件中的私人词库、教辅内容与未单独确认分发来源的数据不包含在公开包中。模板仍支持用户按权限提供自己的词条。

## 运行时可选查询

- [Wiktionary](https://en.wiktionary.org/)：在线英文释义，来源与适用许可按返回结果及来源页面显示。
- [Free Dictionary API](https://dictionaryapi.dev/)：可选备用，录音、例句与许可按实际响应处理，不保证所有词均有录音或双口音。
- [Oxford Learner’s Dictionaries](https://www.oxfordlearnersdictionaries.com/)：人工详查外链；本项目没有打包其商业词典数据库。

在线结果不是 ECDICT 子集的一部分，也不因本项目使用 MIT 许可而自动改变其来源许可。当前查询只发送所查词语，结果缓存限当前页面内存；录音播放与浏览器系统语音分开标示。

## 外部工具

- [FFmpeg](https://ffmpeg.org/)：读取、分析与裁剪音频；程序和依赖不随 Skill ZIP 分发。
- [whisper.cpp](https://github.com/ggml-org/whisper.cpp)：可选本地转写路线；程序及模型不随包分发。
- Python 及浏览器由运行环境提供。

## 教学与流程参考

- [ReadingText2html](https://github.com/vincenthan2012-hub/ReadingText2html)：参考了结构化教学数据、篇章分析与读写迁移的设计思路。
- [ffmpeg-audio-processing](https://github.com/chunpu/agent-skills/tree/main/skills/ffmpeg-audio-processing)：参考音频属性检查、静音检测与裁剪工作流。

本项目的整卷模板和辅助脚本为独立实现；参考项目的源代码、原视频和原示例材料没有随本仓库打包。

## 输入材料与生成结果

项目许可覆盖本仓库的代码、模板、文档与原创示例；不自动覆盖使用者提供的试卷、答案、录音、教材或生成结果中引用的第三方内容。公开仓库和 Release 不包含开发时使用的真实考试卷、原卷听力、教辅整册或课堂记录。
