# Windows 与手机适配

这个 Skill 的脚本在 Windows、macOS、Linux 上跑同一套 Python 代码；差异集中在「外部工具怎么装」和「手机怎么打开成品」。开工先跑 `py -3 scripts/doctor.py --minutes 听力时长`，它会按当前系统给出该走哪一档。

## 一、Windows

### 1. 需要装什么

| 用途 | 工具 | 安装方式 |
| --- | --- | --- |
| 必装 | Python 3.9+ | `winget install Python.Python.3.12`，安装时勾选 Add python.exe to PATH |
| 听力切割 | ffmpeg + ffprobe | `winget install Gyan.FFmpeg`，或 `scoop install ffmpeg` / `choco install ffmpeg-full` |
| 听力转写（可选） | whisper.cpp 可执行文件 | 下载 whisper.cpp 的 Windows 预编译包（whisper-bin-x64），把解压目录加进 PATH |
| 听力转写（可选） | 模型 ggml-base.bin / ggml-small.bin | 放进 `%USERPROFILE%\whisper.cpp\models`，或用环境变量 `WHISPER_MODEL` 指向 |
| PDF/扫描卷（可选） | poppler（pdftotext/pdftoppm）、tesseract | `scoop install poppler tesseract` 等 |

装完**重开终端**让 PATH 生效，用 `where.exe ffmpeg`、`where.exe whisper-cli`、`where.exe main.exe` 确认能找到。

### 2. Windows 上会遇到的三个坑（脚本已处理）

1. **可执行文件名字不一样**：whisper.cpp 在不同构建里叫 `whisper-cli.exe`、`whisper.exe` 或 `main.exe`。`scripts/platform_tools.py` 会依次查找这些名字，不用手改脚本。
2. **控制台编码**：中文 Windows 控制台默认 cp936，英文系统是 cp1252，直接打印中文会 `UnicodeEncodeError`。所有脚本在入口处强制 UTF-8 输出，JSON 与模板文件也显式按 UTF-8 读写，中文报错信息不会再崩。
3. **跨盘符路径**：项目在 D 盘、素材在 C 盘时，相对路径算不出来。接线逻辑会退回绝对路径，构建仍然可用。

### 3. Windows 上没有的 mac 能力

- 没有 `say` 命令：不要用系统语音合成生成听力素材，转写一律走 whisper.cpp；确实没有转写环境时用 `analyze --no-asr` 的静音分段档。
- 没有 `sips` / `qlmanage` / `textutil`：PDF 渲染与 OCR 改用 poppler、tesseract 或 LibreOffice（`soffice`）。DOCX 仍可用 `scripts/extract.py`（纯标准库）。
- 路径含空格或中文时，命令里用双引号包住，例如 `py -3 scripts/build.py "D:\课件\exam.json" "D:\输出\lesson"`。

## 二、手机打开成品

### 1. 正确的打开方式

1. 默认内嵌模式的 HTML 含听力；原卷页图、可编辑媒体仍在文件夹内。建议完整发送 ZIP。选择 folder 模式时必须同时携带 audio/。
2. 解压后点 `index.html`，选择「用 Safari / Chrome / Edge 打开」。
3. 微信里收到压缩包时，点右上角「…」→「用其他应用打开」再选浏览器；微信内置浏览器对本地 HTML 支持不稳定，不要用它判断课件是否正常。
4. 手机只适合预览与临时讲评，投屏上课建议用电脑浏览器（Chrome / Edge / Safari 均可）。

### 2. 模板已做的兼容处理

手机白屏的两个真实原因，模板现在都做了处理：

- **旧浏览器缺 API**：`Array.prototype.at`（iOS 15.4 才有）、`String.matchAll`、`Array.flatMap`、`Object.fromEntries`、`<dialog>.showModal`（iOS 15.4）在模板里都有降级实现，缺了也不会整页报错。
- **不支持的 `<dialog>`**：老浏览器会把弹窗内容直接铺在页面上。模板加了 `dialog:not([open]){display:none!important}`，关闭状态一律隐藏，支持的浏览器行为不变。
- **白屏兜底**：脚本没跑起来时，页面会显示一段中文说明，告诉你换浏览器、把文件夹一起拷贝、或在微信里改用「用其他应用打开」，不再是一片空白。
- **ResizeObserver 缺失**：自动换成窗口 `resize` 监听，批注图层不会因此失效。

### 3. 建议的最低版本

推荐使用当前受支持的系统浏览器。兼容补丁不能证明某个旧版本已通过验收；页面仍使用现代 JavaScript 语法，旧浏览器应实际测试。

## 三、交付时要说清的三句话

1. 把整个文件夹一起拷到手机或 U 盘，不要只发 `index.html`。
2. 用浏览器打开，微信里请选「用其他应用打开」。
3. 上课投屏建议用电脑浏览器；手机适合备课抽查。

## 回归与实机边界

`.github/workflows/compatibility.yml` 在 Windows、macOS、Linux 运行相同测试，含中文路径、源码读取、范围筛选、分节往返、音频裁剪缓存与内嵌校验。绿色结果证明这些脚本测试通过；不等于在该系统的 WorkBuddy、豆包和每种浏览器中都已完成整卷生成。先查看 CI，再做一个真实 Text 与一篇阅读的宿主验收。
