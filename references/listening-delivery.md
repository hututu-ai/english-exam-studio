# 听力交付与故障处理

默认本次有听力的课件必须同时含题组切片与逐题完整语境切片。build.py 的正式入口通过 scripts/listening_delivery.py 的 check 检查，不能用 quick、内嵌录音或文件能打开代替已分段。

流程：检查安装完整性 → 读取教师范围与材料 → 检查 WhisperX 和 FFmpeg → 在授权范围内准备缺少的工具 → 短音频试跑 → listening_pipeline.py run → 核对题组候选、文字对齐和逐题语境 → 试听并记录核对 → finalize → build.py --audio-bundle 指向 finalize 输出目录 → 浏览器实际播放。

只安装 WhisperX 不能证明分段完成。pipeline 返回 needs_setup 时停止该阶段，说明缺哪个工具或模型；候选片段产生后还需要 finalize，不可只引用整卷 full_audio。超时或网络限制时汇报具体阶段与可恢复文件，下一次续跑，不重做已完成板块。

旧数据中的 audio_scope=full_paper 或 audio_alignment.mode=unsegmented 会被新完成的题组切片替换。不要跳过已有 audio 字段而一直保留整卷录音。构建结果 listening_delivery 必须显示 segmented，统计题组与逐题数量；仍是未分段时不可声称完成精听。

只有老师本次明确只要完整录音或仅题组，才可在计划记录 listening_delivery={mode:full_recording或groups,confirmed:true,teacher_response:老师原话}。独立精听任务不接受降级，需老师重新选择任务范围。该记录由 Agent 根据真实回答填写，禁止编造回答。默认 mode=questions，无需反复询问老师已明确要分段的要求。

字体：课件顶部“正文字体”选择黑体或 Times New Roman。若老师提前明确偏好，可将 exam.json 的 _font_family 设置为 hei 或 times。Times New Roman 不覆盖中文字符；设备缺少该字体时使用系统衬线字体，不偷偷下载或分发商业字体。
