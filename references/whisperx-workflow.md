# WhisperX：有原文时优先对齐

先完成材料盘点和范围、扩展选择，只对所选听力准备工具。WhisperX 是默认候选后端；已存在同源且经检查的时间字幕时直接复用，不强制重装。无听力需求不检查或安装语音模型。

## 跨平台准备

在用户可写目录使用独立 Python 3.12 环境（本轮验证版本），不修改系统 Python。Windows 使用环境内 Scripts/python.exe，Mac 使用 bin/python。复用已有完整环境，首次下载前说明内容、目录与约需空间，按宿主授权执行。不能把云端容器安装等同于教师电脑安装。

在环境内安装 `whisperx==3.8.6`，本次测试使用 torch/torchaudio 2.8.0 的组合。Windows 可先从 https://download.pytorch.org/whl/cpu 安装匹配的 CPU torch/torchaudio；不要默认安装 CUDA。Mac 同样采用 CPU，不要求 NVIDIA。任何安装命令设置超时；下载阶段与模型运行阶段分别报告，超时保存状态并说明，不持续重装。

缓存目录包含 align/ 英语对齐权重、nltk/tokenizers/punkt_tab/english/ 分句数据。程序完整不代表资源完整。首次用 whisperx.load_align_model(language_code='en',device='cpu',model_dir=缓存/align) 获取官方英语对齐权重；NLTK 的 punkt_tab 数据放在缓存/nltk。若自动下载被代理安全检查拒绝，不关闭安全检查：可从 NLTK 官方仓库 packages/tokenizers/punkt_tab.zip 获取固定资源并校验，只安全提取 english 下的四个文本文件。未知镜像不可冒充官方源。

先真实跑短音频，确认英文与时间信息，然后处理全套。不要要求每位老师申请 API。Qwen 是难点复核候选，不默认同时下载三套模型；stable-ts 本轮零时长较多，不作为默认。

## 输入与运行

Agent 先根据实际录音确认题组所在时间窗口，处理开场提示和重复朗读。答案册只有一次原文，不能硬对齐整卷两次朗读。没有可信窗口时先用已有转写/音频理解寻找候选，再检查实际首尾。没有原文时先忠实转写、核对，再对齐；WhisperX 对齐不能自动纠正错误原文。

plan.json 格式：

```json
{"segments":[{"id":"L1","start":58.83,"end":74.16,"text":"原件英文原文","alignment_text":"录音实际读法","normalization_note":"仅对齐输入展开金额与缩写，原文保持不变"}]}
```

上述秒数仅为格式示例，不可复制到新录音。Agent 编写，不让老师手工填 JSON。没有规范化时省略 alignment_text 和 normalization_note。£50 按实际录音可展开 fifty pounds；时间、年份等读法必须核对，不一律猜测。教学显示与证据引用仍使用 text。

用对应环境 Python 执行 `scripts/align_whisperx.py AUDIO plan.json --out transcript.json --cache CACHE`，宿主为该进程设置合理超时（例如600秒，长卷按实际预算调整）。输出绑定原音、计划、脚本和版本，完全相同任务可复用。输出 aligned_review_required 只说明已有对齐结果；异常返回非零状态，不补造词时间。

根据题意选择最小完整语境，允许题间重叠，核对否定、原因、指代与句首尾。用现有 audio.py cut --transcript transcript.json 裁剪并试听，不能将模型给出的逐词时间直接标 verified=true。金额、缩写、超短关键词和模型间明显分歧优先复核。对齐窗口不等于单题切片，逐题清单仍须结合题意制定。

切片完成后继续固定模板构建和浏览器播放验收。更新文字解析时只构建；原音与切点未变不重新转写、对齐或切割。
