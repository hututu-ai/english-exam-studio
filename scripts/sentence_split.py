#!/usr/bin/env python3
"""把一段原文切成句子，供逐句译文对齐使用（构建校验用，展示层只在需要时镜像）。

规则固定、可预期，宁可保守也不乱切：

* 句末标点 `.` `!` `?` `…`（可带引号、右括号）之后**必须是空白或行尾**才算一句结束，
  所以 `3.5`、`U.S.` 这类不会被切开；
* 常见缩写（Mr. / Dr. / etc. / e.g. …）后的点不算句末；
* 返回的每句保留原标点，且**去掉首尾空白**——逐句译文必须与这个列表一一对应。

对齐检查的价值在于：句数对不上时，译文与句子就会错位；这时必须阻断，而不是"看着差不多"。
"""
import re

ABBREVIATIONS={'mr','mrs','ms','dr','prof','st','no','vs','etc','eg','ie','am','pm','us','uk','sr','jr','mt','ft','approx','dept','est'}

SENTENCE_END=re.compile(r"[.!?…]+['\"”’)\]]*")

def split_sentences(text):
    text=' '.join(str(text or '').split())
    if not text:return []
    sentences=[];start=0
    for match in SENTENCE_END.finditer(text):
        end=match.end()
        if end<len(text) and not text[end].isspace():continue      # 在词内部（小数、缩写、网址）
        head=text[start:match.start()].strip()
        token=re.split(r'[\s(\["\'“‘]+',head)[-1].lower().replace('.','') if head else ''
        if token in ABBREVIATIONS:continue
        piece=text[start:end].strip()
        if piece:sentences.append(piece)
        start=end
    rest=text[start:].strip()
    if rest:sentences.append(rest)
    return sentences
