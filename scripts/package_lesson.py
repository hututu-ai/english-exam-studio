#!/usr/bin/env python3
"""Package a checked lesson, binding browser evidence to the exact HTML bytes."""
import argparse, hashlib, json, zipfile
from pathlib import Path
from verify_output import verify_output
from platform_tools import force_utf8

def package(output, destination, allow_unchecked=False):
    out=Path(output).resolve();dest=Path(destination).resolve()
    if dest==out or out in dest.parents:raise ValueError('ZIP 必须放在输出文件夹外，避免递归打包')
    verify_output(out)
    digest=hashlib.sha256((out/'index.html').read_bytes()).hexdigest()
    evidence=out/'browser-check.json'
    report=json.loads(evidence.read_text(encoding='utf-8')) if evidence.exists() else {}
    passed=report.get('status')=='passed' and report.get('html_sha256')==digest and bool(report.get('checks')) and all(isinstance(c,dict) and c.get('status')=='passed' for c in report['checks']) and not report.get('errors') and bool(report.get('engine'))
    if not passed and not allow_unchecked:raise ValueError('缺少与当前 HTML 对应的浏览器点击验收；先运行 browser_check.cjs 或宿主浏览器验收。无法验收时只可用 --allow-unchecked 交付待验收版')
    status='browser_checked' if passed else 'preview_only_browser_check_pending'
    (out/'delivery-report.json').write_text(json.dumps({'status':status,'html_sha256':digest,'browser_report':'browser-check.json' if passed else None,'scope':'Checks apply only to this artifact; teaching accuracy and exact audio boundaries require source review.'},ensure_ascii=False,indent=2),encoding='utf-8')
    dest.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(dest,'w',zipfile.ZIP_DEFLATED) as z:
        for p in sorted(out.rglob('*')):
            if p.is_symlink():raise ValueError('交付文件夹不能包含软链接：'+str(p))
            if p.is_file() and not any(x.startswith('.') for x in p.relative_to(out).parts):z.write(p,p.relative_to(out).as_posix())
    with zipfile.ZipFile(dest) as z:
        if z.testzip() is not None or z.read('index.html')!=(out/'index.html').read_bytes():raise ValueError('ZIP 完整性检查失败')
    return {'status':status,'zip':str(dest),'html_sha256':digest,'zip_sha256':hashlib.sha256(dest.read_bytes()).hexdigest()}
if __name__=='__main__':
    force_utf8();p=argparse.ArgumentParser();p.add_argument('output');p.add_argument('zip');p.add_argument('--allow-unchecked',action='store_true');a=p.parse_args()
    try:print(json.dumps(package(a.output,a.zip,a.allow_unchecked),ensure_ascii=False))
    except (ValueError,OSError) as e:p.exit(1,str(e)+'\n')
