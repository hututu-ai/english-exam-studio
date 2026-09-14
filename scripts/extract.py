#!/usr/bin/env python3
"""DOCX extraction preserving block order; images kept for visual checking.

Teachers often hand over an old .doc, a PDF renamed .docx, or a partial download.
Those must produce one actionable sentence, never a Python traceback.
"""
import argparse,json,sys,zipfile,xml.etree.ElementTree as ET
from pathlib import Path
from platform_tools import explain_error,force_utf8

NS={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main',
    'mc':'http://schemas.openxmlformats.org/markup-compatibility/2006'}
W_P='{%s}p'%NS['w'];W_T='{%s}t'%NS['w'];W_TXBX='{%s}txbxContent'%NS['w'];MC_FALLBACK='{%s}Fallback'%NS['mc']

def document_body(archive):
    try:root=ET.fromstring(archive.read('word/document.xml'))
    except KeyError:raise ValueError('这个文件里没有 word/document.xml，可能不是 DOCX；老式 .doc、PDF 或改名文件请先转换，或改由宿主读取')
    except ET.ParseError as error:raise ValueError(f'word/document.xml 解析失败，文件可能损坏：{error}')
    body=root.find('w:body',NS)
    if body is None:raise ValueError('DOCX 缺少正文 w:body，文件可能损坏或被截断')
    drop_fallbacks(body)
    return body

def drop_fallbacks(node):
    """Word/WPS 把文本框写成 mc:Choice（现代图形）+ mc:Fallback（VML），**两份文字一模一样**。

    两份都读会让同一道题干出现两次（实测 `11. When does…11. When does…`，而文本框在中文卷里很常见），
    所以只保留 Choice——这也是 OOXML 里 Fallback 的定义：给老版本用的等价副本。
    """
    for element in list(node.iter()):
        for child in list(element):
            if child.tag==MC_FALLBACK:element.remove(child)

def paragraph_text(node):
    """取一个 w:p 的文字：文本框里的段落用换行断开，避免多段文字粘成一句。"""
    parts=[];has_box=False
    for element in node.iter():
        if element.tag==W_TXBX:has_box=True
        elif element is not node and element.tag==W_P:parts.append('\n')
        elif element.tag==W_T and element.text:parts.append(element.text)
    return ''.join(parts).strip(),has_box

def extract(source,out):
    out=Path(out);out.mkdir(parents=True,exist_ok=True);blocks=[]
    with zipfile.ZipFile(source) as archive:
        for node in document_body(archive):
            kind=node.tag.split('}')[-1]
            if kind=='p':
                text,has_box=paragraph_text(node)
                block={'type':'paragraph','text':text}
                if has_box:block['textbox']=True      # 文本框内容已并入本段；顺序仍需对照原件
                blocks.append(block)
            elif kind=='tbl':
                rows=[]
                for row in node.findall('w:tr',NS):
                    rows.append([paragraph_text(cell)[0] for cell in row.findall('w:tc',NS)])
                blocks.append({'type':'table','rows':rows})
        images=[]
        for name in archive.namelist():
            if name.startswith('word/media/') and not name.endswith('/'):
                target=out/'images'/Path(name).name;target.parent.mkdir(parents=True,exist_ok=True)
                target.write_bytes(archive.read(name));images.append(target.relative_to(out).as_posix())
    (out/'extracted.json').write_text(json.dumps({'blocks':blocks,'images':images,'note':'Verify images, layout, underlines and OCR against source.'},ensure_ascii=False,indent=2),encoding='utf-8')
    return {'blocks':blocks,'images':images}

def main():
    force_utf8()
    p=argparse.ArgumentParser();p.add_argument('input');p.add_argument('out');a=p.parse_args()
    try:result=extract(a.input,a.out)
    except zipfile.BadZipFile as error:
        print(f'ERROR: 不是有效的 DOCX（zip）文件：{error}；老式 .doc、PDF 或改名文件请先转换，或改由宿主读取',file=sys.stderr);return 1
    except (OSError,ValueError,KeyError,ET.ParseError) as error:
        print(f'ERROR: {explain_error(error)}',file=sys.stderr);return 1
    print(f"{len(result['blocks'])} blocks; {len(result['images'])} images extracted")
    return 0

if __name__=='__main__':raise SystemExit(main())
