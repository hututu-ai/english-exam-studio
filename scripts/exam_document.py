#!/usr/bin/env python3
"""Load an exam.json, and say so in Chinese when the file is something else.

`exam.json`、`generation-plan.json`、`source-ledger.json` 常常都放在同一个 `WORK/` 目录里，
把计划或台账当成试卷传进来是很常见的失手。以前这种情况会漏出英文报错
（`AttributeError: 'str' object has no attribute 'get'`、`TypeError: string indices must be integers`），
看起来像程序坏了，实际只是给错了文件——助手会因此白白重试好几轮。

    from exam_document import load

    document=load('WORK/exam.json')     # 形状不对时抛中文 ValueError
"""
import json
from pathlib import Path


def read_json(path):
    """读一个 JSON 文件；坏了就给中文原因（不把 json 模块的英文原文甩给老师）。"""
    path=Path(path)
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except json.JSONDecodeError as error:
        raise ValueError(f'{path} 不是合法 JSON：第 {error.lineno} 行第 {error.colno} 列读不通；'
                         '请检查引号是否成对、逗号是否多余、括号是否闭合') from None


def load(path):
    """读 JSON 并确认顶层形状像 exam.json；不像就抛出带原因的中文 ValueError。"""
    path=Path(path)
    document=read_json(path)
    if not isinstance(document,dict):
        raise ValueError(f'{path} 的顶层应该是 JSON 对象（exam.json 的格式），当前是 {type(document).__name__}')
    sections=document.get('sections')
    if not isinstance(sections,list) or any(not isinstance(section,dict) for section in sections):
        # 计划文件里的 sections 是板块名（字符串或 "a,b" 这样的字符串），试卷里是「每节一个对象」。
        looks_like_plan=isinstance(sections,str) or (isinstance(sections,list) and any(isinstance(section,str) for section in sections))
        hint='；这个文件看起来像 generation-plan.json（计划里的 sections 是板块名，exam.json 的 sections 是「每节一个对象」）' if looks_like_plan else ''
        raise ValueError(f'{path} 不像 exam.json：sections 应该是「每节一个对象」的数组，当前是 {type(sections).__name__}{hint}')
    return document
