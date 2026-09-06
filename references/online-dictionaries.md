# 教学词典与在线补充

默认先显示本篇已编写的语境义与对应原句，再提供通用词典义和在线补充。离线核心查词不依赖网络；在线词典不作为高考考纲、当前考试词频或自动句内消歧依据。

## 本地优先的查词流程

1. 输入、点词或划词后，检索当前篇章的生词速查和重点词汇。已编写语境义优先；其他篇章的词义不能冒充本篇义，未编写时直接展示通用义。
2. 以词库 `exchange` 等真实词形资料还原词元，并显示还原关系；不规则词形不能仅靠删后缀猜测。通用中文释义按照词性及实际换行显示，不将字面 `\n` 原样堆叠。
3. 保留词典窗口内连续输入查询、发音、停止、放大、词汇积累与外部详查。Oxford 详查只是词条网页链接，不代表接入其官方 API。
4. 在线补充仅发送所查单词/词组。主资源失败或未返回可用义项时切换另一个资源，双源失败仍保留本地结果。超时、未收录和网络失败分别处理；请求序号/取消机制防止旧词结果覆盖新词。缓存仅在当前页面内存中，不承诺刷新或离线后保留在线结果。

[ECDICT](https://github.com/skywind3000/ECDICT) 是已集成的 MIT 许可词典数据；公开包携带 10,836 条来源明确的基础释义，生成时按实际打包数量记录。其官方字段包含中文义、音标和 `exchange` 词形映射；不假定词库本身已经附带可用录音。用户自有的一词多义和搭配辨析可按需提供；公开包不附带私人旧词库。

## 无密钥双源

### Wiktionary

当前默认资源使用英文 Wiktionary 的定义接口：

```js
const response = await fetch(
  'https://en.wiktionary.org/api/rest_v1/page/definition/' + encodeURIComponent(word)
);
if (!response.ok) throw new Error(String(response.status));
const entries = (await response.json()).en;
```

[请求示例](https://en.wiktionary.org/api/rest_v1/page/definition/engagement) · [对应词条](https://en.wiktionary.org/wiki/engagement)

主要补充英文词性、定义和实际返回的例句。不能把 `data.en` 的英文释义标成中文教学解释，也不能由这个定义接口推定有音标或英美双录音。接口返回的 HTML 先取纯文本，再转义显示。

Wiktionary 词条是开放内容，文本通常依 CC BY-SA 4.0 / GFDL 及词条所列附加条件使用；外部引用和声音可能另有许可。应保留词条链接及许可说明，软件开源与内容许可分开处理。[内容许可说明](https://en.wiktionary.org/wiki/Wiktionary:Copyrights)

### Free Dictionary API

```js
const response = await fetch(
  'https://api.dictionaryapi.dev/api/v2/entries/en/' + encodeURIComponent(word)
);
if (!response.ok) throw new Error(String(response.status));
const entries = await response.json();
```

[官方接口与返回示例](https://dictionaryapi.dev/) · [开源仓库](https://github.com/meetDeveloper/freeDictionaryAPI)

官方文档提供无密钥的英文词典请求。响应可含 `meanings`、例句、`phonetic`、`phonetics.audio`，以及同反义词；具体字段和每词覆盖以实际返回为准。展示音频时保留实际链接和可核实口音信息，未标口音不要猜测。界面读取的 `license`、`sourceUrls` 与录音各自来源应保留；项目代码 GPL-3.0 不等于所有词条及音频都适用同一许可。

录音与来源链接必须为有效 HTTP(S) 地址；外部数据不作为可执行代码插入课件。

## 词典录音与系统朗读

词典返回了可播放音频时，标为“词典录音”并保留来源；系统朗读使用浏览器 Web Speech API `speechSynthesis`，明确标为“系统朗读”。两者均与试卷音频互斥，提供停止操作。没有录音、加载失败或没有所选口音时保留本地文字结果并如实反馈。

系统声库随设备、浏览器和安装情况变化；实际口音以选中的 `voice.lang` 为准。`localService=true` 才表示本地语音服务，不能把所有系统英语声库都承诺为离线可用。[MDN：语音服务来源](https://developer.mozilla.org/en-US/docs/Web/API/SpeechSynthesisVoice/localService)

## 验证边界

2026-09-05 的历史记录包含一次本机 Chrome 对 Wiktionary 返回 200 的跨域查询，也出现过外部服务超时；Free Dictionary API 历史探测出现过 403、超时或连接重置。这些是特定时间和环境的结果，不代表当前持续可用或持续不可用。

2026-09-06 本轮先核查了官方用法和代码路径；子任务的只读 HTTP 探测被执行环境网络权限拦截，不能据此判断接口故障。本轮现场可用性以最终浏览器实测记录为准，文档不预先写成通过。

浏览器能否直调还受网络与远端 CORS 控制影响。MediaWiki 的匿名 REST 跨域需要服务端允许；不能用仅在命令行成功的请求代替课件浏览器跨域验收。[官方 CORS 文档](https://www.mediawiki.org/wiki/Manual:CORS)

生成阶段用 AI 编写语境义、结构化开放数据及商业词典授权属于可选扩展，见 [API 接入取舍](api-options.md)。

## 2026-09-06 本轮实际验证

本机独立 Chrome 从课件页面查询 hello，优先 Free Dictionary API 未连接成功后自动转到 Wiktionary，后者返回 HTTP 200，释义与例句成功显示。此结果只证明本次该词请求成功，不承诺后续网络或每词覆盖。录音、许可字段展示及404/失败切换另用模拟响应检查，不能据此声称已播放 Free Dictionary API 的真实录音。
