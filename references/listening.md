# 听力执行细节

Python 3 + ffmpeg + ffprobe；ASR 使用 whisper-cli 和本地模型，或复用带时间转写。--model 或 WHISPER_MODEL 指向实际模型。先在当前环境寻找可用模型；模型不随包分发，按宿主环境准备。较小模型对专名／口音可能不足，按需用更合适的模型或局部重听复核。

开工先跑 `python3 scripts/doctor.py --minutes 听力时长`：它报告 ffmpeg/ffprobe/whisper-cli、可用模型、建议并发与粗估耗时，并直接给出本次该走哪一档。缺依赖时按输出改走降级档，不要停在安装或下载上。

```bash
python3 scripts/audio.py analyze INPUT_AUDIO --out WORK_AUDIO --model WHISPER_MODEL --jobs 4 --threads 5 [--timeout 900] [--reuse|--no-asr]
python3 scripts/audio.py cut INPUT_AUDIO --manifest SEGMENTS_JSON --out WORK_AUDIO --transcript WORK_AUDIO/transcript.json [--resume|--allow-unverified]
python3 scripts/audio.py cut INPUT_AUDIO --manifest QUESTIONS_JSON --out WORK_AUDIO/questions --transcript WORK_AUDIO/transcript.json
```

analyze 生成 16k 单声道工作副本、transcript.json、silences.json、analysis.json。规范转写格式：`{"segments":[{"start":1.2,"end":4.8,"text":"Text one..."}]}`，秒数相对完整音频；文件内 `source_audio_sha256` 绑定本次原音，换音频后重跑而不会串用旧转写。自动识别 Text one / Text 1 / 第1段是候选，不保证所有录音有口令。

速度与稳定性的默认做法：`--jobs N` 在真实静音处把原音切片并发转写（实测长录音收效明显，短录音自动保持单片）；`--threads` 控制单进程线程；`--reuse` 直接复用匹配指纹的转写；`--resume` 只补做缺失或时长不符的片段；`--timeout` 避免单次 ASR 无限等待，超时后按提示改走降级。whisper.cpp 的 GPU 后端在容器、无显卡或沙箱环境会直接崩溃（进程退出码 139），脚本检测到后自动改用 `-ng` 重跑一次并在 analysis.json 记录 device=cpu；若仍失败，换成静音分段而不是反复重试。

`cut` 会校验首尾引句：segments 里写 `opening_quote`/`closing_quote`（逐字取自本 Text 原文），脚本与切点附近的转写做模糊比对，对不上直接报错。这样“引文—切点—音频”三者一致，也避免有人改音频去迁就引文。输出目录默认拒绝覆盖，`--resume` 复用同名片段，改一两段时不必重编码全部。

智能体结合题干、场景变化、题号提示确认边界。前 5 段通常各 1 题，后续分配必须按卷。去掉试音、例题、总说明；重复两遍默认选第一遍完整正文，另一遍可复核。留约 0.15–0.35 秒自然余量，不切尾辅音。若保留两遍，用一个 Text 覆盖并记录策略。

segments.json 示例（只展示一段，实际数组应与 expected_count 等长）：
```json
{"expected_count":10,"segments":[{"id":"L1","title":"Text 1","question_ids":["1"],"start":32.15,"end":47.6,"verified":true,"evidence":"结合转写、首尾试听确认；首句…末句…；保留第一遍"}]}
```

默认 kind=text 的 cut 拒绝重叠、越界、重复 ID／题号、未核对片段，以重编码裁剪，输出 segments.json 保留源时间、实测时长和资源文件名。脚本验证不是语义核对的替代。

纸面听力原文与 ASR 冲突时回听，不能为了配答案改写声音。每个 Text 一个 section，轮次 paragraph 有 speaker/id/text，可提供真实局部 start/end。挖空用指定 paragraph 的字符起止位置，右端不含。相同词多次出现不得全局替换。局部重听在 question.evidence 填分段局部 start/end；未对齐就不填。

正式交付要保留完整原音频与独立分段文件，验证互斥播放、暂停、倍速、切段停止、实际首中尾播放。整套打包后移动路径再检查一次。

## 课堂精听与自动切段交付

智能体完成时间清单、分段、独立核对和打包；老师提供原始三类材料即可，不要求老师写切段清单或自行操作剪辑软件。录音重复朗读归并同一Text，缺失或低置信度先局部重听核对。

模板支持原题逐题讲评、证据1/2/3次复听、0.5/0.75倍速、可信轮次的跟随定位和逐空听写。按词级时间核对听力，不能以浏览器朗读代替原音。完整录音保留在听力更多菜单，课堂工具不放播放器。

使用scripts/preview.py启动带Range支持的本地预览。实际验证播放器currentTime跳到证据start、按选择次数返回起点、最后停止；普通http.server的播放成功不证明定位可用。移动文件夹后，以file://离线重复验证。

## 每题独立录音与精听选空

先完成每个 Text 的原音对齐，再按题意识别最小完整语境。关系推断保留双方身份线索；行动题保留提议与回应；指代题保留先行词；否定／转折题保留转折前后。两道题可取同一部分，不要求时间顺序或互不重叠。不要把一句答案词裁成孤立音效。分段与逐题清单都放在同一个音频工作目录（逐题清单放 `WORK_AUDIO/questions/segments.json`），构建时用 `--audio-bundle WORK_AUDIO` 自动接线，不手写路径。

单题裁剪清单使用完整原音的绝对秒数，注意不要把 Text 局部秒数传给原音 cut：
```json
{"kind":"question","expected_count":2,"segments":[
  {"id":"Q6","title":"第6题","question_ids":["6"],"start":358.76,"end":373.89,"verified":true,"evidence":"已核对首尾及关系推断所需上下文"},
  {"id":"Q7","title":"第7题","question_ids":["7"],"start":347.48,"end":352.83,"verified":true,"evidence":"已核对告别和去杂货店的完整句子"}
]}
```
`kind=question` 允许重叠与非时间顺序；每片段必须恰好对应一题，题号仍不得重复。导出后独立转写、核对首尾，再检查每个 q.audio 的浏览器解码和播放。exam.json 中 `audio_context` 使用 Text 局部秒数，`q.audio` 是裁后文件。不要混用两个时间基准。

精听空位记录题号与教学目的，通常每段选1—4处关键表达，必要时可更多，以实际题量与语义为准。保留否定结构、搭配完整性和同义替换线索；不为了增加空数去挖无关名词。检查隐藏空不会从翻译或点词暴露答案。界面以舒适阅读宽度和左右内边距呈现，工具只保留一行；手机允许紧凑换行。

小播放器位于每题选项后，默认看题也可播放；Text右上角整段播放保留。修改选项不应重置正在播放的本题录音；整段、单题、完整录音互斥，速度共享，切节停止。


## 统一听力工作区

不再提供“看题听音／对照讲评／精听练习”三个近似页面。题目与单题音频常在，原文为原位折叠栏；显答自动展开并定位，手动开合不改变作答状态。原文上的“关键表达挖空”就地出题，开启时收起答案/相关译文，空位进度可保存。关闭挖空恢复全文，重置本节才清理该节课堂作答。选择、原文开合和挖空切换都不应中断播放。
