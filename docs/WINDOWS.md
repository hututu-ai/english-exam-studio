# Windows 验收清单：从环境准备到真卷交付

## 先跑这一条：跑完把文件发回（推荐第一步）

```bat
py -3 scripts\smoke_report.py --zip
```

**不想开终端也可以**：直接**双击**压缩包里的 `一键体检.bat`（和 `SKILL.md` 同一层）。它会自己切到脚本所在目录、自动用 `py -3`（没有就退回 `python`）、跑完上面那条命令、并停住让你看路径——**不安装、不下载、不改任何设置**。跑完把打印出来的 `smoke-report-*.zip` 发回即可。

它会依次跑：运行环境 → 安装完整性 → 宿主能力 → 示例构建 → 模板与产物核验 → 浏览器点击验收（有 Node+Playwright+Chrome 时）→ 打包交付，
并把结果写成 `smoke-report.json` / `smoke-report.md` / `host-probe.json`，再打包成 **`smoke-report-windows.zip`**（只含报告文本，不含试卷与音频）。

- **发回**：把这个 zip 发回即可；接收方用一条命令就能严格判读，不会把"跳过的步骤"当成通过：
  `py -3 scripts\read_acceptance.py smoke-report-windows.zip`
- **没有浏览器工具**：用 `py -3 scripts\smoke_report.py --no-browser --zip`。这样得到的报告**不能**支持"按钮与播放已验证"，判读时会如实列为未验证。
- **判读口径**：`skipped` 与 `failed` 一律不算通过；报告用的是**示例卷**，所以它永远不能证明"真实试卷内容/答案/听力边界已验收"；豆包工作 / WorkBuddy 的宿主链路也不在报告范围内。

下面第 0–7 节是逐步清单（想知道每一步在看什么时读）。

本文件给第一次在 Windows 上使用 `english-exam-studio` 的老师和技术支持人员。每一步都是可直接复制执行的命令，命令都在**项目根目录**（能看到 `SKILL.md`、`VERSION`、`scripts\`、`assets\` 的那一层）执行。

先说清边界：本 Skill 的开发和自动测试主要在 macOS 上完成，跨平台代码与 CI 覆盖见第 9 节，但**作者尚未在真实 Windows 机器上跑完整链路**。所以本清单不是"已经验证通过"的声明，而是一份"你要实际跑、并把真实输出记录下来"的验收步骤。没有执行过的检查不要写成通过。

全程不需要管理员权限，不需要永久修改系统 PATH，也不需要运行任何 `.sh` 脚本。

**最省事的做法：先跑这一条命令，再把报告发回。**

```bat
py -3 scripts\smoke_report.py
```

它会按顺序执行「运行环境 → 安装完整性 → 宿主能力 → 示例构建 → 模板与产物核验 → 浏览器点击验收 → 打包交付」，不安装、不下载，并在当前目录写出 `smoke-report.json` 与 `smoke-report.md`。把这两个文件一起发回即可；有失败项时命令返回 1，但报告照样会写出来。想先跳过浏览器验收可加 `--no-browser`，想换目录可用 `--workdir` 与 `--report-dir`。下面的分节是同一套步骤的手工版本，遇到失败时用来定位。


## 0. 打开正确的目录和终端

在项目根目录打开 PowerShell 或 Windows Terminal。最稳的方式是在资源管理器里进入该文件夹，在地址栏输入 `powershell` 回车，或右键选择"在终端中打开"。

确认位置：

```bat
dir SKILL.md
dir scripts\build.py
```

两条命令都能列出文件，说明当前就在项目根目录。下面所有 `py -3 scripts\...` 或 `py -3 scripts/...` 命令都从这里执行。

## 1. Python：优先复用，入口用 `py -3`

### 1.1 先看本机有没有

```bat
py -3 --version
where.exe py
where.exe python
```

- `py -3 --version` 能打印 3.9 或更高版本，就满足要求，不必重装。
- `where.exe python` 用来确认 PATH 上是否有 `python.exe`。
- 如果 `where.exe python` 指向 `...\WindowsApps\python.exe`（Microsoft Store 的应用执行别名），它有时会打开商店而不是运行 Python。这种情况下统一用 `py -3`，不要用裸 `python`。

### 1.2 没有才安装

```bat
winget install Python.Python.3.12
```

安装界面里要勾选 **Add python.exe to PATH**。装完**关闭当前终端、重新打开一个新终端**，再执行一次 `py -3 --version` 和 `where.exe python`。

### 1.3 判定标准

`py -3 --version` 输出 Python 3.9+，并且**重开终端后** `where.exe python` 仍能找到解释器。只有在另一个终端能跑、换一个终端就找不到，说明 PATH 没生效或环境不一致，先解决这一步再往下走。

## 2. FFmpeg / FFprobe：先复用，再安装

只有听力任务才硬性需要它们。没有 ffmpeg 也能完成阅读、七选五、完形、语法填空和写作，听力会退回"整卷原音未分段"档。

### 2.1 先看本机有没有

```bat
where.exe ffmpeg
where.exe ffprobe
ffmpeg -version
ffprobe -version
```

两条 `where.exe` 都要有结果，两条 `-version` 都要能打印版本。**如果刚刚装完 ffmpeg，一定要关闭并重新打开终端再执行这几条**——PATH 只在新终端里生效。

### 2.2 没有时安装

```bat
winget install Gyan.FFmpeg
```

也可以 `scoop install ffmpeg` 或 `choco install ffmpeg-full`，按学校电脑实际可用的包管理器来。装完重开终端，回到 2.1 复验。

### 2.3 不能改 PATH 时的便携版做法

用环境变量只对当前终端/进程指定，不需要管理员权限：

```powershell
$env:FFMPEG_BIN  = "D:\tools\ffmpeg\bin\ffmpeg.exe"
$env:FFPROBE_BIN = "D:\tools\ffmpeg\bin\ffprobe.exe"
```

或者指向同时包含两者的 bin 目录：

```powershell
$env:ENGLISH_EXAM_TOOLS = "D:\tools\ffmpeg\bin"
```

这些变量只影响当前窗口，新开窗口要重新设置。脚本会优先使用它们。（cmd 里对应 `set FFMPEG_BIN=...`。）

### 2.4 记录证据

把 `where.exe` 的实际路径和 `ffmpeg -version`、`ffprobe -version` 的输出记下来，这是下一步 doctor 判断 `capability` 的依据。

## 3. 安装完整性：`status` 必须是 `complete`

```bat
py -3 scripts\check_install.py
```

在输出的 JSON 里找 `"status"`：

- `"status": "complete"`：每个文件与安装清单逐项哈希一致，可以继续。
- `"status": "incomplete_install"`：**不要继续生成，也不要手工修改 `install-manifest.json` 或 `VERSION`。** 按 `errors` 列出的文件补齐。常见原因是只下载到几个文字文件、ZIP 没解压完整、或解压时被安全软件/网盘截断。重新获取完整包、完整解压后再跑一次。
- 遇到下载白名单拦截或超时，如实报告"完整包下载受限，尚未安装成功"，不要用零散文件拼一个 Skill，也不要让老师去运行 `.sh` 更新脚本。

## 4. 环境自检：读懂 `capability`

```bat
py -3 scripts\doctor.py --minutes 20
```

把 `--minutes` 换成本次听力的实际总时长（分钟）。它只用于粗估转写耗时，不是完成时限，也不代表固定时长承诺。

重点看输出 JSON 里的 `capability` 字段，它直接决定听力走哪一档：

| capability | 含义 | 听力怎么走 |
| --- | --- | --- |
| `full_auto` | ffmpeg/ffprobe 可运行且有 MP3 编码器，whisper 可执行文件与本地模型都在 | 每个 Text、每道题自动分段，边界仍需核对 |
| `silence_only` | ffmpeg 可用，但没有可用的 whisper（未安装、名字不对或不在 PATH、或没有模型） | 静音候选分段，边界标"待人工核对" |
| `no_ffmpeg` | ffmpeg/ffprobe 缺失、不能运行，或缺少 libmp3lame 编码器 | 整卷原音未分段，必须在浏览器里实际验证能播 |

同时留意这些字段：`ffmpeg_runnable`、`ffprobe_runnable`、`mp3_encoder`、`whisper_runnable`、`asr_models`、`console_encoding`、`python_ok`。Windows 上报告还会附一条"装完 ffmpeg/whisper 后重开终端让 PATH 生效"的提示。

- `capability=no_ffmpeg` 且 `mp3_encoder=false`：当前 ffmpeg 不能导出 MP3。不要把 AAC 当成 MP3 交付；换一个带 libmp3lame 的构建，或明确交付未分段原音。
- `capability=silence_only` 时，doctor 的 `next_step` 会是 `py -3 scripts\prepare_whisper.py`。是否准备 Whisper 由老师决定，不静默降级，也不因为缺转写就删掉听力章节。
- 判定标准：能说清这次走哪一档、依据是哪个字段。不能只看"doctor 没报错"就宣布环境就绪。

## 5. 小样构建：用自带原创示例练手

示例是纯原创阅读材料，只需要 Python，不需要 FFmpeg、模型或联网：

```bat
py -3 scripts\build.py examples/demo-exam.json output\demo --source-ledger examples/source-ledger.json
```

检查产物：

```bat
dir output\demo
py -3 scripts\verify_output.py output\demo
```

应看到 `index.html`、`打开课件.html`、`exam.json`、`build-report.json`、`answer-audit.json`，且 `verify_output` 的 `status` 是 `passed`（模板与内嵌数据一致）。注意：`build.py` 的 `quality_gate` 通过只代表结构检查通过，**不代表答案、音频和教学内容正确**。

双击 `output\demo\index.html` 用 Edge 打开，试一下逐题显答、原文定位、段落翻译、查词、批注和主题切换。示例没有听力，所以听不到声音是正常的。

路径含中文或空格时，给每个参数加双引号：

```bat
py -3 scripts\build.py "D:\我的课件\exam.json" "D:\输出\lesson" --source-ledger "D:\我的课件\source-ledger.json"
```

## 6. 浏览器验收：Microsoft Edge

`scripts\browser_check.cjs` 需要本机**已经安装**的 Node.js 和 Playwright 模块。它不会自动安装任何东西，也不联网。缺工具时它会如实写入 `not_available`，这不是通过。

### 6.1 确认 Node 在

```bat
node -v
```

### 6.2 指定 Edge 和 Playwright 模块

在 PowerShell 里：

```powershell
$env:BROWSER_ENGINE = "chromium"
$env:CHROME_BIN = "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
$env:PLAYWRIGHT_MODULE = "D:\tools\node_modules\playwright"
node scripts\browser_check.cjs output\demo
```

说明：

- Edge 是 Chromium 内核，所以 `BROWSER_ENGINE` 用默认值 `chromium`，把 `CHROME_BIN` 指向 `msedge.exe` 即可。变量名虽然叫 `CHROME_BIN`，但它接受任何 Chromium 内核浏览器的可执行文件路径；并且只在 `BROWSER_ENGINE=chromium`（默认）时生效。
- `PLAYWRIGHT_MODULE` 指向**已经存在**的 Playwright 模块目录。脚本不下载、不安装。
- Edge 的确切路径以本机为准，可以先试 `where.exe msedge`，或查看 `C:\Program Files (x86)\Microsoft\Edge\Application\`。
- 脚本最多运行 180 秒，只在 `127.0.0.1` 上临时开一个只读本目录的服务，不访问外部词典。

### 6.3 看结果

通过时控制台逐项打印 `PASS ...`，并写入 `output\demo\browser-check.json`，其中 `html_sha256` 与媒体哈希绑定本次产物。要检查 `engine`、`platform`、`browser_version`、`checks`、`errors`；`errors` 不为空就是失败。没有 Node 或没有 Playwright 时不要手写 `browser-check.json` 冒充通过。

### 6.4 没有 Playwright 时怎么办

不安装、不伪造。改用宿主或人工浏览器，按 `references/regression.md` 逐项实际点击，记录动作、结果和截图位置；或经老师同意后再准备 Node + Playwright 重跑。自动脚本没有执行，就不能在报告里写"浏览器验收通过"。

### 6.5 边界

本机 HTTP 自动检查不等于 `file://` 双击、微信附件预览或 WorkBuddy/豆包整卷生成链路通过。最终交付仍建议在 Edge 里双击 `打开课件.html` / `index.html` 复看一次。

## 7. 打包交付：`browser_checked` 与 `preview_only_browser_check_pending`

```bat
py -3 scripts\package_lesson.py output\demo demo.zip
```

- 若**浏览器验收有效**（`browser-check.json` 与当前 `index.html` 指纹一致、`errors` 为空）**并且人工复核清单已完成**（`qa_report.py check` 返回 `ok`）：状态为 `browser_checked`，可以交付。
- 若缺**当期浏览器验收**或**人工复核清单**（两者缺一即拦）：命令会直接失败，并把缺的东西一次列全——常见是"缺少与当前 HTML 对应的浏览器点击验收"和"人工复核清单未完成——缺少 qa-report.md"。浏览器验收见第 6 节，人工复核清单见第 9 节第 7 步（`qa_report.py init` → 填 `结论：` → `check` 返回 `ok`）。**两道门都要过**，只补一道会再撞一次。确需先交付时加 `--allow-unchecked`：

```bat
py -3 scripts\package_lesson.py output\demo demo.zip --allow-unchecked
```

  此时状态是 `preview_only_browser_check_pending`，中文含义是"**待浏览器操作验收版**"：课件本身能用，但还没有真实点击记录。交付说明里必须写明"待验收"，不能说通过，也不能保证可直接上课。

- ZIP 必须放在输出文件夹**之外**。上面的 `demo.zip` 在项目根目录、产物在 `output\demo`，符合要求。
- `browser_checked` 也只证明浏览器点击已完成，**不代替**答案与原件比对、听力边界复核和教学内容核对。`build-report.json` 的 `pending_items` 和 `answer-audit.json` 的 `review` 项仍要逐条处理并写结论。

## 8. Windows 上脚本已经处理掉的坑

| 坑 | 脚本的处理 | 你该怎么做 |
| --- | --- | --- |
| 控制台编码 cp936/cp1252，打印中文崩溃 | 所有脚本入口强制 UTF-8 输出，JSON 与模板显式按 UTF-8 读写 | 正常用 `py -3`；个别老终端仍乱码时可临时 `chcp 65001` |
| whisper.cpp 可执行文件名字不统一 | 按 `whisper-cli(.exe)`、`whisper(.exe)`、`main(.exe)` 依次查找 | 不要为了改名去动脚本；用 `WHISPER_BIN` 指向实际路径 |
| 项目在 D 盘、素材在 C 盘，跨盘符相对路径算不出 | 接线逻辑退回绝对路径 | 命令里路径加双引号 |
| 路径含中文或空格 | 内部用 Path 对象与参数列表，不拼 shell 字符串 | 每个含中文/空格的参数都加双引号 |
| 更新脚本是 `.sh` | 本 Skill 不提供、也不要求运行 `.sh` | Windows 一律用 `py -3` 跑 `.py`，不要装 Git Bash 去跑 shell 脚本 |
| 想永久改 PATH / 要管理员权限 | 支持 `FFMPEG_BIN`、`FFPROBE_BIN`、`ENGLISH_EXAM_TOOLS`、`WHISPER_BIN`、`WHISPER_MODEL` 只对当前进程生效 | 优先复用已有工具；安装走学校允许的包管理器 |

## 9. 自动 CI 证明了什么，还需要你证明什么

`.github/workflows/compatibility.yml` 在 `windows-latest`、`macos-latest`、`ubuntu-latest` 上，用 Python 3.9 和 3.11 各跑一遍 `python -m unittest discover -s tests`（项数以 CI 实际输出为准，不在这里写死——写死过 27，后来涨到两百多，差点让人以为 CI 只跑那么点）。它只依赖 `actions/checkout` 和 `actions/setup-python`，没有 pytest、没有密钥、没有额外下载。旁边还有一个 `continue-on-error: true` 的 doctor 诊断任务，只负责在 Windows 上打印环境自检 JSON。

**CI 能证明的（脚本层面）：**

- 同一套标准库测试在三个系统、两个 Python 版本上都能跑完，覆盖中文/空格路径、UTF-8 读写、范围筛选与顺序、分节拆分与无损合并、内嵌与外置音频、带时间转写复用、切片缓存与失效、缺 ffprobe 降级、安装完整性与模板一致性等。
- `doctor.py` 能在 Windows runner 上执行并输出 JSON。
- 工作流语法与矩阵配置有效。

**CI 不能证明的（必须真机 / 真卷）：**

- 在这台 Windows 上完成一次**真实试卷**的整卷生成；CI 用的是仓库原创示例，不是你的试卷。
- 真实试卷的题号、选项、识别结果、答案出处与教学解析是否正确——这些必须对照原件逐题核对，自动化无法认定。
- 真实听力音频的分段边界、逐题语境和转写准确度；CI runner 上没有 ffmpeg/whisper，也不会听音频。
- Edge 里每个按钮的人工点击；`browser_check.cjs` 需要 Node + Playwright，CI 不安装它们，因此 CI 里**没有**跑浏览器交互。
- WorkBuddy、豆包等宿主的完整生成链路，以及手机/微信里打开成品的效果。
- 你机器上是否有可用的 libmp3lame 编码器——只能靠第 4 步的 `mp3_encoder` 实际判断。

**因此，在声称"Windows 可用"之前，至少要真机 + 真卷做完这一串：**

1. `py -3 scripts\check_install.py` → `status=complete`；
2. `py -3 scripts\doctor.py --minutes <本次听力时长>` → 记下 `capability` 与工具实际路径；
3. 用真实试卷/答案/音频构建，再 `py -3 scripts\verify_output.py <输出目录>` → `passed`；
4. 有 Node + Playwright 时 `node scripts\browser_check.cjs <输出目录>` 全 PASS 且 `errors` 为空；没有就人工按 `references/regression.md` 点击，并如实记录"未做自动验收"；
5. `py -3 scripts\package_lesson.py <输出目录> <输出目录之外的>.zip` → 看清是 `browser_checked` 还是 `preview_only_browser_check_pending`；
6. 用 Edge 打开 `index.html`，抽查关键题答案、证据定位和听力音频首尾；
7. `py -3 scripts\qa_report.py init <输出目录>`，逐条填写 `结论：`，再 `py -3 scripts\qa_report.py check <输出目录>` → `ok`。把以上每一步的**实际输出**（不是期望值）写进 `qa-report.md`。

没有执行过的检查不要写成通过；工具缺失时只报告实际交付的功能。

## 10. 一页速查

```bat
py -3 --version
where.exe py
where.exe python
where.exe ffmpeg
where.exe ffprobe
py -3 scripts\check_install.py
py -3 scripts\doctor.py --minutes 20
py -3 scripts\build.py examples/demo-exam.json output\demo --source-ledger examples/source-ledger.json
py -3 scripts\verify_output.py output\demo
```

```powershell
$env:BROWSER_ENGINE = "chromium"
$env:CHROME_BIN = "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
$env:PLAYWRIGHT_MODULE = "D:\tools\node_modules\playwright"
node scripts\browser_check.cjs output\demo
py -3 scripts\package_lesson.py output\demo demo.zip
```

相关文档：`references/platforms.md`（Windows 与手机适配）、`references/dependency-recovery.md`（依赖下载失败时的有界恢复）、`references/runtime-delivery.md`（启动与交付验收）、`references/regression.md`（课堂功能回归清单）、`docs/VERIFICATION.md`（各版本实际执行与未覆盖边界）。
