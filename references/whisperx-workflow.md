# 统一 WhisperX 处理链路

本次有听力才使用。先问范围与功能；已有原音指纹一致的时间转写先复用。官方 CPU 使用方式与安装说明：https://github.com/m-bain/whisperX 。使用现有后端时，不因为 whisper.cpp 缺失再安装一套。

## 1. 探测与按需准备

```bash
python3 scripts/speech_runtime.py probe
python3 scripts/doctor.py --whisperx-python 环境中的Python
python3 scripts/speech_runtime.py prepare --root 用户目录/whisperx-env --cache 用户目录/speech-cache
```

`EXAM_WHISPERX_PYTHON` 或 `--python` 可指向现有虚拟环境；不解析其可执行文件软链接到系统 Python。Windows 为 Scripts/python.exe，Mac 为 bin/python。

prepare 默认仅报告需要安装的内容与目录；说明修改范围和数 GB 依赖/模型空间，收到安装授权后加 `--install-approved`。复用已有环境；新建独立虚拟环境，默认 CPU，不要求 CUDA/API Key；Windows CPU torch/torchaudio 与 WhisperX 使用固定兼容组合。建议现有 Python 3.12；没有兼容 Python 时先报告，不覆盖系统 Python。安装、资源准备共用有界预算，失败保留完整错误与已完成目录，不无限重装、不使用管理员命令。

```bash
python3 scripts/speech_runtime.py prepare --install-approved --python 现有Python312 --root 用户目录/whisperx-env --cache 用户目录/speech-cache --seconds 120
```

准备包含 WhisperX、英语对齐权重与分句资源。package_ready 只说明包可导入，模型和实际音频仍须试跑。首次转写的 ASR 模型缓存也需要下载，应在上述说明中一并告知并获得许可。

## 2. 短音频试跑 → 转写或复用 → 题组窗口 → 对齐 → 单题语境

```bash
python3 scripts/listening_pipeline.py run --audio WORK/原音.mp3 --exam WORK/exam.json --plan WORK/generation-plan.json --source-ledger WORK/source-ledger.json --python 环境中的Python --cache 用户目录/speech-cache --out WORK/listening --seconds 600
```

没有时间转写时：先真实处理25秒，成功再跑整卷，使用 CPU/int8/Silero VAD，不调用需要个人 token 的说话人分离。脚本记录失败阶段、实际错误与用时。

已有同源时间转写时，加 `--transcript WORK/transcript.json`；严格检查原音指纹与时间范围，跳过 ASR 和短转写，直接查找题组窗口。此时仍需 WhisperX 做精确对齐，已有完整逐词结果可由原有复用流程直接使用。

窗口按答案册原文与录音转写匹配，排除中文开场指令，重复朗读保留一遍并记录候选。`windows.json` 是候选，不是人工精确时间。匹配失败时不给假秒数；Agent 核对实际录音并修订窗口、原文规范化（金额、缩写、数字）。将同源修订窗口用 `--windows WORK/windows-reviewed.json` 继续执行，不从头重做。

`alignment_text` 只能按实际读法规范化，保留 text 原文并填写 normalization_note。没有原件听力原文时，先核对自动转写、按真实题组建立文本，再继续。不要把两遍录音的整段硬对齐成一遍原文。

单题候选从本题 evidence 引句匹配逐词时间，再扩为完整句；输出 `question-contexts.json` 与 `cuts-candidates.json`。找不到或不唯一时列出问题。Agent 继续检查需要的前文/指代/否定/因果/推断语境，必要时扩大范围；允许题间重叠，不只剪答案单词。

## 3. 试听复核 → 真正裁剪 → 构建与浏览器验收

Agent 实际试听首尾并核对题意后，在候选清单逐项写具体 evidence 与 verified=true；未复核时不得直接批量改 true。清单绑定原音，必须消除所有 issues，完整保留题组与单题候选。

```bash
python3 scripts/listening_pipeline.py cut --audio WORK/原音.mp3 --manifest WORK/cuts-reviewed.json --transcript WORK/listening/aligned.json --out WORK/audio-out
```

整段进入 audio-out，单题进入 audio-out/questions，自动沿用既有 audio_wiring 接入 HTML。输出 cuts_verified_by_record 仅指已有实际复核记录并完成裁剪；继续构建与真浏览器播放才可交付。不把录音复制成功、对齐成功或候选已生成当作完整精听验收。

更新文字不重切；同源且切点不变才复用缓存。下载超时/未就绪请报告具体阶段，让老师选择延长或替代路径，不能未经同意降级成未分段整卷原音。
