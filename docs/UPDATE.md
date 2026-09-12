# 已经有旧版，怎么更新到最新版

Skill 是一个放在你电脑上的文件夹，不会像手机 App 那样自己升级。新版本发布后，需要把旧文件夹换成新的，或者让助手帮你换。

## 先确认自己是哪个版本

三种办法，任选一种：

1. 打开 Skill 文件夹里的 `VERSION` 文件，里面写着版本号（例如 `1.3.2`）。
2. 让助手运行：

   ```bash
   python3 <Skill目录>/scripts/check_update.py
   ```

   它会告诉你当前版本、最新版本，以及该用哪种方式更新。
3. 直接问助手："我装的 english-exam-studio 是哪个版本？最新版是多少？"

## 更新方法（按你的安装方式选一种）

### 方法 1：让助手更新（推荐，不用自己动文件）

把下面这段发给你的助手：

```text
请把 english-exam-studio Skill 更新到最新版。

步骤：
1. 先读取我当前安装目录里的 VERSION，并备份整个目录（例如复制成 english-exam-studio-backup-旧版本号）。
2. 从 https://github.com/hututu-ai/english-exam-studio/releases/latest 下载最新的 english-exam-studio.zip，解压后用其中的内容替换旧技能文件，保留我的个性化笔记文件（如果我自己记了笔记）。
3. 更新完成后确认 VERSION 已经变成新版本号，并运行 scripts/doctor.py 检查环境是否正常。
4. 最后告诉我：旧版本号 → 新版本号，以及这次更新带来了哪些变化。
```

助手能访问网络、能读写文件时，这是最省事的方式。

### 方法 2：平台里重新导入

1. 打开 [最新版本](https://github.com/hututu-ai/english-exam-studio/releases/latest)，下载 `english-exam-studio.zip`。
2. 在你的 Agent / 平台里找到已安装的技能（WorkBuddy 是「技能 → 已安装」）。
3. 删除旧技能或选择覆盖安装，导入刚下载的 ZIP。
4. 确认技能里能读到新的 `VERSION` 与 `SKILL.md`。

**WorkBuddy 用户注意**：先确认导入的是完整 ZIP（包根目录直接包含 `SKILL.md`），不要用 GitHub 的 `Code → Download ZIP` 源码包——那个解压后会多一层 `english-exam-studio-main` 目录，容易出现技能不可用。

### 方法 3：手动替换文件夹

1. 先备份：把旧的技能文件夹整体复制一份，改名成 `english-exam-studio-backup-旧版本号`。
2. 下载最新 ZIP 并解压，得到里面的 `SKILL.md`、`scripts/`、`assets/`、`references/`、`agents/`、`VERSION` 等文件。
3. 用这些文件替换旧技能目录里的同名文件；旧目录里你自己的笔记文件保留下来。
4. 确认目录结构是 `技能目录/english-exam-studio/SKILL.md`，没有多套一层同名文件夹。

### 方法 4：如果你是 git 安装的

技能目录本身是仓库克隆时，直接更新即可：

```bash
cd <你的技能目录>
git pull
```

## 更新后会怎样

- **已经生成的课件不受影响。** 课件是独立的文件夹/HTML，换 Skill 版本不会改动以前的课件，旧课件照样能打开上课。
- **课堂记录不会丢。** 批注、讲到哪里、课堂选择存在你打开课件时的浏览器里，与 Skill 版本无关；换电脑时仍用课件里的「导出课堂记录 / 导入」搬迁。
- **你的个性化调整会被覆盖。** 这一点要特别注意：如果你改过 `SKILL.md`、模板或脚本，更新会把这些文件换成新版。更新前先备份，或者把这些习惯整理成一份单独的文件（例如 `MY-TEACHING-NOTES.md`），更新后让助手照着重新应用。
- **`exam.json` 不用重做。** 已有试卷的 `exam.json` 仍然可用；新版构建器会照旧读取它，需要时可重新用新版脚本构建一次课件。

## 更新后建议做一次小检查

```bash
python3 <Skill目录>/scripts/doctor.py --minutes 20
python3 <Skill目录>/scripts/build.py <你的exam.json> <输出目录> --source-ledger <台账> --audio-bundle <音频目录>
```

能正常构建，说明新版本在这台电脑上工作正常。听力相关功能依赖本机的 ffmpeg 与语音识别环境，`doctor.py` 会直接告诉你这台机器该走哪一档。

## 各版本更新了什么

版本与更新内容见仓库首页的版本章节，以及 [Releases](https://github.com/hututu-ai/english-exam-studio/releases) 页面。

- **1.0.8**：工具与章节分两行；主题旁显示当前字号，支持直接选择与微调并立即保存；修复导航布局、下拉状态与长标题问题。
- **1.0.7**：修复精听模式在二次构建时丢失、原音重复内嵌、手机速对入口隐藏；实际运行检查音频依赖，统一首次选择范围说明。
- **1.0.6**：新增速对答案、范围选择与精听入口；真正内嵌听力；修正 Windows 文件编码、音频复用与分节丢字段，增加跨平台自动检查。
- **1.0.5**：从本版起仓库版本号与 SkillHub 一致；内容与 1.3.5 相同，另补版本号对照说明。
- **1.3.5**：章节条标签简化为「听力 1」「阅读 A」，阅读等大题可悬停/点按下拉选择小项，浮层不被裁剪，并提高按钮对比度。
- **1.3.4**：章节导航改成顶栏下方一排，点击即可切节，桌面不再为抽屉预留右侧留白。
- **1.3.3**：补上更新指南与 `scripts/check_update.py` 版本自查，功能与 1.3.2 相同。
- **1.3.2**：听力一定接入并分三档降级、答案可溯源核对、Windows 与手机可用、生成更快。
