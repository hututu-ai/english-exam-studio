# 多套试卷批量生成

老师一次提供多套材料时先进入本流程，不把所有材料混进一份 exam.json。

先列每套试卷的名称、试卷文件、答案文件、听力文件；不确定归属、缺页或重名必须请老师确认，不按文件顺序猜。询问本批统一范围、功能与字体，允许个别卷覆盖；得到明确回答后同批不逐套重复询问。只有含听力的卷才准备语音工具。无法对应的一套暂停，其余确认过的继续。

由 Agent 写 batch-input.json（老师不用写 JSON）：confirmed=true、teacher_response=老师本批原话、settings=合法范围与七项 features、papers 数组。每项有唯一 id、materials（paper/answers/audio 对应路径或路径数组），可选 settings 覆盖共用设置。两卷使用相同文件时先确认是否合卷材料，确认后 shared_materials_confirmed=true；不得将别卷答案当作复用缓存。

执行 `python3 scripts/batch.py init batch-input.json --out batch-work`。脚本一次校验全部配对、登记文件指纹，每卷创建独立 generation-plan.json，不覆写已存在批次。它只建立执行队列，不声称已经完成内容生成。

Agent 按队列逐套执行既有生成主流程。在 batch-work/卷ID 下建立独立 exam.json、source-ledger.json、teaching-review.json 和 output/，使用该卷计划正式 build；每卷自己的题号、音频、解析和来源不得交叉复用。默认逐套处理，先完成第一套样例再沿用同批设置；在资源允许且宿主授权时可并行文字，但同时只运行一个重型语音任务。复用已安装模型；音频转写缓存只允许同一原音指纹。

每套独立做浏览器播放与内容复核，写 qa-report.md，再打包。单套失败记录阶段与错误，保留中间文件并继续其他已确认卷；重试只处理未完成步骤。中断后 `python3 scripts/batch.py status batch-work` 查看实际产物与复核结果，不重新 init 覆盖目录。

最终按卷交付 index.html，并提供每卷状态清单。status 读取实际模板、计划、素材、复核和浏览器报告；只要一套缺材料或未验收，整批不能称已完成。批量不会天然更快或更省模型调用，节省来自不重复安装、重复识别和返工。
