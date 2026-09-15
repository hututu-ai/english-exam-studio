@echo off
rem 英语实战讲评 Skill —— 一键体检（Windows 双击运行；不安装、不下载、不改设置）
rem 等价于手动执行：py -3 scripts\smoke_report.py --zip
chcp 65001 >nul
cd /d "%~dp0"
if not exist "SKILL.md" (
  echo 没有在技能包根目录运行：这个 .bat 必须和 SKILL.md 放在同一层。
  pause
  exit /b 1
)
set PY=py -3
where py >nul 2>nul || set PY=python
echo.
echo 正在跑体检，约 1 分钟，请不要关窗口...
echo （它只读本机环境、构建自带示例、写报告，不安装任何东西）
echo.
%PY% scripts\smoke_report.py --zip
echo.
echo 跑完了。把上面打印的那个 smoke-report-*.zip 发给助手即可（只含报告文本，不含你的试卷和音频）。
echo 有失败项也正常：报告照样写出来了，发回来才能判读。
pause
