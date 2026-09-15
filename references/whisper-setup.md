# 先准备工具，再完成精听

1.0.119 默认处理入口为 [统一 WhisperX 链路](whisperx-workflow.md)。先记录老师本次范围与功能。下文 whisper.cpp 命令仅供已存在的备选环境使用，不因缺少它而安装另一套；不经老师同意降级。


Whisper.cpp 程序与语音模型是两份东西；只有程序没有模型不能转写。默认使用本地 base 多语言模型（约 142 MiB），复用已有可用模型，不反复下载。程序和模型都可放用户目录，不需要老师填写 AI API。

1. doctor 检查实际 Agent 所在系统、ffmpeg/ffprobe、whisper-cli、模型。云端容器安装仅作用于该容器，不能宣称装进老师电脑。
2. 缺 Whisper 时先运行 `python3 scripts/prepare_whisper.py` 输出准备方案，说明下载位置、约 142 MiB 模型与额外程序文件、网络来源和权限。已有授权即继续；需要额外权限按宿主机制申请，不替老师修改系统设置。
3. 在允许下载/写用户目录后执行 `python3 scripts/prepare_whisper.py --install`。Windows 默认 LOCALAPPDATA/english-exam-studio，Mac 默认 ~/.cache/english-exam-studio；可用 --root 指向宿主可写工作目录。下载来自官方 whisper.cpp GitHub 和官方链接的 ggerganov/whisper.cpp 模型仓库，校验模型 SHA256；Windows 选择匹配架构且附 SHA256 的便携程序包。安全解压，忽略软链接/隐藏项，拒绝目录越界。
4. macOS/Linux 缺程序时，脚本只在现有 CMake/C++ 工具可用的情况下在用户目录编译 CPU 版。缺编译工具时停止并说明；Agent 可在已有 Homebrew 等受支持环境中、获得对应安装权限后准备工具，不要求老师照抄 sudo。脚本不安装 Python、Homebrew、编译器或管理员软件。
5. 首次准备预算默认 120 秒，超时终止当前任务进程树。说明进度与剩余项，老师愿意等待可用 `--seconds 600` 等延长；网络白名单拒绝则请求平台授权或改用老师已认可的渠道，不反复绕路、不改代理。失败产生的残片/源码目录不能当可用安装；有旧可用程序就保留，修复失败目录前先检查并只处理本次残片。
6. 准备成功保存 runtime.json，之后自动发现。自定义 root 用仅当前进程的 WHISPER_BIN、WHISPER_MODEL 指定，或者把模型目录传给 doctor。状态 ready_for_smoke_test 仅表示程序和模型就绪：必须抽取真实录音 15–30 秒，转写并核对内容和时间戳；GPU 失败可退 CPU。还需要 FFmpeg/FFprobe 做解码、裁剪和验证。然后再跑整段/逐题分段与浏览器播放检查。

## 硅基流动可选云端路径（2026-09-14 核对）

[官方价格页](https://siliconflow.cn/pricing) 当前把 XingChenAGI/XingChenGSR-V1.0、Qwen/Qwen3-ASR-1.7B 等语音模型列为免费。价格/限额可能改变，调用前看实际账户与模型卡，不写“永久免费、无额度限制”。免费服务不等于可匿名调用，也不等于模型权重可自由下载。

[官方通用转写接口](https://docs.siliconflow.cn/docs/api/audio-transcriptions-post) 使用 API Key，公开规格为不超过 1 小时/50MB，响应示例只有 text；此文档列举的 model 仍是 SenseVoiceSmall/TeleSpeechASR，不能据此确认新 GSR 的具体入参、英语表现、是否忠实逐字输出及时间戳支持。

因此本版把 GSR 作为候选，不声称已经实测接通。用户选择云端时，先核对当前模型卡/API 文档、是否支持英语与音频格式，再经授权用短录音试调，检查真实返回字段；原音需上传第三方，说明去向。Key 通过安全环境变量/宿主凭据提供，不写进 Skill、exam.json、HTML、日志或公开仓库，不把作者密钥发给所有老师。

只有文字结果可用于内容校对，不能伪造逐词时间戳。没有时间戳时还需本地对齐或按已核对音频片段组织时间轴，不能平分整卷秒数。GSR 如会润色、增补识别结果，应与纸面原文和实际录音比对；精听必须使用真实听到的表达。

默认课堂 HTML 不增加必填 API 设置，不上传录音。只有生成阶段选择云端才接入；已有课件离线讲评不依赖这个云服务。
