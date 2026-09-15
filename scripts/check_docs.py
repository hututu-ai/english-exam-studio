#!/usr/bin/env python3
"""文档一致性检查：让"照着文档做会撞墙"在发布前就被发现。

二十多轮改动之后，最容易腐烂的不是代码而是文档：命令改名、字段新增、版本号、
测试数量、脚本被删——docs 里还写着老样子。老师照着做就会报错，而报错信息会指向
一个根本不存在的参数。这里用机器检查这些**可验证**的一致性：

1. 文档里提到的 `scripts/xxx.py` 必须存在，反之每个脚本都要在文档里出现过（有白名单）；
2. 文档里的命令行参数必须真的存在于那个脚本的 argparse 里；
3. `VERSION` = README 最新版本小节 = `assets/template-manifest.json` 的 template_version；
4. `references/` 里不能有孤儿文档（SKILL.md 或 README 至少要链接一次）；
5. README 里写的"测试总数 N"必须等于真实测试数；
6. 发布包根目录不得残留旧验收报告（报告只写 `dist/release-check/`，根目录那份会被打进 ZIP）；
7. 同一份文档里不得出现两个同号 `## N.` 小节（"第 N 步"必须唯一）；
8. 主流程文档的「第 N 步」必须从 1 连续递增（漏号/重号会让助手跳步）；
9. 文档里的相对链接必须指向真实存在的文件（改名或写错字母会让读者停在 404）。

  python3 scripts/check_docs.py [--json]
"""
import argparse,ast,json,re,sys
from pathlib import Path
from platform_tools import force_utf8

ROOT=Path(__file__).resolve().parents[1]
# 只在开发/发布时出现、不需要老师文档提及的脚本
INTERNAL={'task_contract.py','speech_worker.py','bounded_command.py','platform_tools.py','check_docs.py','read_acceptance.py','sentence_split.py','section_kinds.py','host_probe.py','smoke_report.py','extract_package.py','preview.py','package_skill.py','check_update.py','exam_document.py'}

SCRIPT_MENTION=re.compile(r'scripts[/\\]([A-Za-z_][A-Za-z0-9_]*\.py)')
FLAG_MENTION=re.compile(r'(?<![\w-])(--[a-z][a-z0-9-]*)')

# 发布验收报告只写 dist/release-check/（dist 不进发布包）。根目录若残留旧报告，它会跟着 ZIP
# 发给老师，而且版本号停在旧版（真实发生过：脚本改写到 dist/ 之后，1.0.67 的报告留在根目录被打进 1.0.69 包）。
ROOT_REPORT_RESIDUE=('release-check.json','release-check.md')

def stale_report_problems(root):
    """检查包根目录有没有残留的发布验收报告。纯函数，便于用临时目录反向验证。"""
    root=Path(root)
    return [f'根目录残留 {name}：发布验收报告只写 dist/release-check/；根目录这份会被打进发布包，'
            f'版本号停在旧版，老师会误读成这一版验收没过——请删除'
            for name in ROOT_REPORT_RESIDUE if (root/name).exists()]

NUMBERED_HEADING=re.compile(r'^##\s+(\d+)\.\s')

def numbered_section_problems(label,text):
    """同一份文档里不得出现两个"## 同号. "小节。

    真发生过：`docs/WINDOWS.md` 顶部加了"## 0. 一条命令跑完"之后，原本的"## 0. 打开正确的目录"
    还在——老师按文档说"第 0 步"时指哪一步都说不清。规则收得很窄（`## 数字. 空格`），
    所以 `## 1.0.69：`、`### 1.1 …` 这类版本号与子小节都不会误报。
    """
    seen={}
    duplicates=[]
    for line in text.splitlines():
        match=NUMBERED_HEADING.match(line)
        if match:
            number=match.group(1)
            seen.setdefault(number,[]).append(line.strip())
    for number,lines in sorted(seen.items()):
        if len(lines)>1:
            duplicates.append(f'{label}: 出现了 {len(lines)} 个「## {number}. …」小节（{"；".join(lines)}），'
                              f'编号重复会让"第 {number} 步"指代不清——请给其中一个小节另编号或去掉编号')
    return duplicates

STEP_HEADING=re.compile(r'^#{2,3}\s+第\s*(\d+)\s*步',re.M)

def step_sequence_problems(label,text):
    """主流程类文档的步骤编号必须从 1 连续递增：漏号、重号、乱序都会让"第 N 步"对不上。

    只对含至少三个「第 N 步」小节的文档生效，所以普通文档不会被误报。
    """
    numbers=[int(match.group(1)) for match in STEP_HEADING.finditer(text)]
    if len(numbers)<3:return []
    expected=list(range(1,len(numbers)+1))
    if numbers==expected:return []
    return [f'{label}: 步骤编号应为 1…{len(numbers)} 连续递增，实际是 {"、".join(map(str,numbers))}'
            f'（漏号/重号/乱序会让"第 N 步"对不上，助手会跳步）']

MARKDOWN_LINK=re.compile(r'\]\(([^)\s]+)\)')

INSTALL_PATH_MARKERS={'teacher_uploaded_zip':('附件','teacher_uploaded_zip'),
                      'raw_files_fetch':('raw.githubusercontent.com',),
                      'cdn_jsdelivr':('jsdelivr',),
                      'git_clone':('git clone','git_clone')}

def install_path_doc_problems(documents,order):
    """讲安装的文档必须提到每条安装路径，且顺序与 `host_probe.install_paths()` 一致。

    老师在"没梯子/被沙盒拦"时最依赖这个顺序；文档少写一条或把 git clone 提到前面，
    助手就会去试最不稳的那条。顺序只从"最稳那条（附件/teacher_uploaded_zip）"出现的位置往后比——
    正文里"沙箱常拦 `git clone`"这类前置说明是背景，不是推荐顺序。
    """
    problems=[]
    for label,text in documents:
        lowered=text.lower()
        def find_after(marks,start=0):
            hits=[lowered.find(mark.lower(),start) for mark in marks]
            hits=[hit for hit in hits if hit>=0]
            return min(hits) if hits else -1
        anchor=find_after(INSTALL_PATH_MARKERS[order[0]])
        positions=[]
        for key in order:
            marks=INSTALL_PATH_MARKERS.get(key)
            if marks is None:continue
            if key!=order[0] and anchor<0:continue
            pos=find_after(marks,anchor if key!=order[0] else 0)
            if pos<0:
                problems.append(f'{label}: 没有提到安装路径「{marks[0]}」（宿主探测里它是第 {order.index(key)+1} 条：{" → ".join(order)}）')
            else:positions.append(pos)
        if positions!=sorted(positions):
            problems.append(f'{label}: 安装路径顺序与 scripts/host_probe.py 不一致，应写成 {" → ".join(order)}')
    return problems

def broken_link_problems(root):
    """文档里指向本地文件的相对链接必须真的存在（含 `../references/x.md` 这类跨目录链接）。

    老师与助手都是顺着链接找文档的：改名或写错一个字母，读者就停在 404。
    只查本地相对路径，http(s)、mailto 与纯锚点不查。
    """
    root=Path(root)
    problems=[]
    for path in doc_files():
        for target in MARKDOWN_LINK.findall(path.read_text(encoding='utf-8')):
            if target.startswith(('http://','https://','mailto:','#')):continue
            clean=target.split('#')[0].strip()
            if not clean:continue
            if not (path.parent/clean).exists():
                problems.append(f'{path.relative_to(root)}: 链接指向不存在的文件：{target}')
    return problems

def doc_files(root=None):
    root=Path(root) if root is not None else ROOT
    files=[root/'README.md',root/'SKILL.md']
    files+=sorted((root/'references').glob('*.md'))
    files+=sorted((root/'docs').glob('*.md'))
    return [path for path in files if path.is_file()]

def script_names():
    return sorted(path.name for path in (ROOT/'scripts').glob('*.py'))

def doc_text():
    return '\n'.join(path.read_text(encoding='utf-8') for path in doc_files())

def argparse_options(path):
    """用 AST 取脚本里 argparse 注册过的所有选项字符串。"""
    tree=ast.parse(path.read_text(encoding='utf-8'))
    options=set()
    for node in ast.walk(tree):
        if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute) and node.func.attr=='add_argument':
            for argument in node.args:
                if isinstance(argument,ast.Constant) and isinstance(argument.value,str) and argument.value.startswith('-'):
                    options.add(argument.value)
            for keyword in node.keywords:
                if keyword.arg=='choices' and isinstance(keyword.value,(ast.List,ast.Tuple)):
                    options.update(element.value for element in keyword.value.elts if isinstance(element,ast.Constant))
    return options

def canonical_features():
    """功能菜单的权威来源：scripts/plan.py 的 FEATURES 顺序与名称。"""
    sys.path.insert(0,str(ROOT/'scripts'))
    import plan
    return [(label,note) for _,label,note in plan.FEATURES]

def doc_feature_lists():
    """抓文档里"编号 + 功能名"的清单（行内或分行都算），用来跟权威清单比对。

    只认**连续编号**的行（1、2、3… 或 2、3、4…）。这个正则会顺带命中中文里的常见写法，
    例如"共 4 处问题（原来要两轮）"；那些编号不连续，不该被当成功能清单，
    否则一句正常的话会被报成"第 N 项功能名不对"（真发生过）。
    """
    found=[]
    for path in doc_files():
        rows=[]
        for line in path.read_text(encoding='utf-8').splitlines():
            for match in re.finditer(r'(?:^|\s)([1-9])\s*[.、)]?\s*([\u4e00-\u9fff]{2,6})\s*[（(]',line):
                rows.append((int(match.group(1)),match.group(2)))
        numbers=[number for number,_ in rows]
        consecutive=all(right==left+1 for left,right in zip(numbers,numbers[1:]))
        if rows and consecutive:found.append((path,rows))
    return found

# 交付物词汇表：只比对"课件包里真实会交给老师的文件"，避免把仓库目录树、示例文件名也算进来。
DELIVERABLES={'index.html','打开课件.html','exam.json','build-report.json','answer-audit.json',
              'qa-report.md','delivery-report.json','browser-check.json','ECDICT-LICENSE.txt',
              'audio/','sources/','assets/'}

def deliverable_names(text):
    """只在含 index.html 的代码块里，抓交付物词汇表中的条目。"""
    names=set()
    for block in re.findall(r'```(?:text)?\n(.*?)```',text,re.S):
        if 'index.html' not in block:continue
        for match in re.finditer(r'([A-Za-z0-9_\-]+\.(?:html|json|md)|audio/|sources/|assets/)',block):
            if match.group(1) in DELIVERABLES:names.add(match.group(1))
    return names

def feature_list_problems(label,rows,features):
    """比较一份文档里的"编号+功能名"清单与权威清单，返回问题列表（纯函数，便于反向验证）。"""
    ordered=sorted({number:name for number,name in rows}.items())
    if len(ordered)<len(features):return []          # 只写了部分编号的引用不算清单
    problems=[]
    for index,((number,name),(expected_name,_)) in enumerate(zip(ordered,features),1):
        if number!=index or name!=expected_name:
            problems.append(f'{label}: 功能清单第 {number} 项写成「{name}」，权威菜单（scripts/plan.py）第 {index} 项是「{expected_name}」')
    return problems

def install_claim_problems(documents):
    """讲安装的文档必须写明"check_install 到 complete 才算装上"。"""
    problems=[]
    for label,body in documents:
        if 'check_install' not in body or 'complete' not in body:
            problems.append(f'{label}: 讲安装的文档必须写明「跑 check_install 到 complete 才算装上」，否则老师无法判断装没装上')
    return problems

def status_label_problems(root):
    r"""标着版本号的"当前状态"小节必须跟当前 VERSION 一致。

    真实发生过：`docs/ROADMAP.md` 的「当前状态（按目标逐条对照，1.0.70）」在版本走到 1.0.107 之后
    还挂着 1.0.70——读者会以为那些结论是七十多版之前下的。状态要么跟着版本走，要么别写版本号。

    只看**现役**状态小节：`docs/VERIFICATION.md` 里那种"# 1.0.108 …"的逐版本记录标题本身就带那一版的
    版本号（它描述的是当时做了什么，不是在声明当前状态），按 `^#+\s*1\.0\.\d+` 认出来放行。
    """
    version=(root/'VERSION').read_text(encoding='utf-8').strip()
    problems=[]
    for path in doc_files(root):
        label=str(path.relative_to(root)).replace('\\','/')
        for number,line in enumerate(path.read_text(encoding='utf-8').splitlines(),1):
            if not line.startswith('#') or '当前状态' not in line:continue
            if re.match(r'^#+\s*1\.0\.\d+',line):continue      # 逐版本记录标题，不是现役状态声明
            found=re.findall(r'1\.0\.\d+',line)
            if found and version not in found:
                problems.append(f'{label}:{number}: 标题写的是 {found[0]}，当前版本是 {version}；'
                                '状态小节必须跟着版本走（或干脆不写版本号），否则读者拿到的是旧结论')
    return problems

# 这两份是"历史记录/Windows 专用"，`python ...` 在那里是对的：
#   * docs/VERIFICATION.md 记录的是当时 GitHub Actions 上真实跑过的命令（Actions 里 `python` 可用）；
#   * docs/WINDOWS.md 面向 Windows 老师（`python` 通常可用），也转录了 CI 命令。
BARE_PYTHON_OK={'docs/VERIFICATION.md','docs/WINDOWS.md'}

def command_prefix_problems(root):
    """老师/助手要照抄的命令必须写 `python3`（Windows 老师替换成 `py -3` 或 `python`）。

    实测：macOS 上 `python` 往往不存在（本机 `command -v python` 为空），照抄 `python scripts/xxx.py`
    会直接 command not found，白跑一轮。仓库自己的约定（docs/UPDATE.md、generation-planning.md、
    host-compatibility.md 三处）也是"Windows 用 py -3/python，macOS/Linux 用 python3"，
    所以文档里的命令一律写 python3。
    """
    problems=[]
    for path in doc_files(root):
        label=str(path.relative_to(root)).replace('\\','/')
        if label in BARE_PYTHON_OK:continue
        for number,line in enumerate(path.read_text(encoding='utf-8').splitlines(),1):
            if re.search(r'(?<![\w3])python scripts/',line):
                problems.append(f'{label}:{number}: 命令写成 `python scripts/…`；macOS/Linux 上 python 常常不存在，'
                                '请写 `python3 scripts/…`（Windows 老师按文档说明替换成 py -3 或 python）')
    return problems

CSS_VAR_CONTEXT=re.compile(r'var\(\s*--[a-z0-9-]+|--[a-z0-9-]+\s*:')

def cli_flags(root):
    """所有脚本真正认得的参数：Python 的 argparse + Node 的 browser_check.cjs。"""
    flags=set()
    for path in sorted((root/'scripts').glob('*.py')):flags|=argparse_options(path)
    cjs=root/'scripts'/'browser_check.cjs'
    if cjs.is_file():flags|=set(re.findall(r"'(--[a-z][a-z0-9-]*)'",cjs.read_text(encoding='utf-8')))
    return flags

def css_variables(root):
    """模板里定义的 CSS 自定义属性名（`--size`、`--accent`…）。

    它们在文档里会和命令行参数长得一模一样，但**定义在 assets/lesson.html 里**，所以按定义来源
    区分：模板定义过的名字不算"脚本不认得的参数"。这样以后新增 CSS 变量不必回来改白名单。
    """
    css=(root/'assets'/'lesson.html').read_text(encoding='utf-8')
    return {name for name in re.findall(r'(--[a-z][a-z0-9-]*)\s*:',css)}

def doc_flag_mentions(text,css_vars=()):
    """文档里提到的参数，排除 CSS 自定义属性（`var(--size)`、`--size:`、模板里定义过的名字）。"""
    masked=CSS_VAR_CONTEXT.sub(lambda match:' '*len(match.group(0)),text)
    return {flag for flag in FLAG_MENTION.findall(masked) if flag not in css_vars}

def orphan_flag_problems(root):
    """散文里提到的每个参数都必须真的有脚本认得。

    原有检查只覆盖"同一行里写了 scripts/xxx.py"的参数；而速度、省额度那几页经常在散文里直接写
    参数（例如"用 `--profile quick` 先交付"）。这类写法打错或参数被删时不会被发现——助手照抄就会
    撞上 argparse 报错，白跑一轮（正是"生成特别久"的来源之一）。
    """
    known=cli_flags(root);css_vars=css_variables(root);problems=[]
    for path in doc_files(root):
        text=path.read_text(encoding='utf-8')
        for flag in sorted(doc_flag_mentions(text,css_vars)):
            if flag not in known:
                problems.append(f'{path.relative_to(root)}: 提到参数 {flag}，但没有任何脚本认得它'
                                '（要么是打错，要么参数已删；别让助手照抄后撞 argparse 报错）')
    return problems

def reading_cost_problems(root):
    """harness.md 的"读多少"数字与它引用的 SKILL.md 标记，必须和文件实际状态对得上。

    这两处以前都漂过：写着"两份加起来约 60KB"（实际 73KB）、"本页约 5KB"（实际 8KB），
    还引用了 SKILL.md 里并不存在的字面标记「只在本次有听力时读」（实际文本被 ** 拆开了）。
    省额度就靠这张表，数字错了助手就会多读或少读。
    """
    problems=[]
    harness=(root/'references'/'harness.md').read_text(encoding='utf-8')
    skill=(root/'SKILL.md').read_text(encoding='utf-8')
    schema=(root/'references'/'schema.md').read_text(encoding='utf-8')
    def kb(path):return len((root/path).read_bytes())/1024
    def claimed(pattern):
        found=re.findall(pattern,harness)
        return int(found[0]) if found else None
    def check(pattern,actual,label):
        stated=claimed(pattern)
        if stated is None:
            problems.append(f'references/harness.md: 找不到「{label}」的数字；省额度的表必须写明可核对的读数')
        elif abs(stated-actual)>actual*0.1:
            problems.append(f'references/harness.md: {label} 写的是约 {stated}KB，实际 {actual:.1f}KB（差超过 10%，助手会按错的读数决定读不读）')
    check(r'两份加起来约 (\d+)KB',kb('SKILL.md')+kb('references/schema.md'),'两份大文档合计')
    check(r'本页（约 (\d+)KB）',kb('references/harness.md'),'本页')
    check(r'含「模板行为说明」的小节合计约 (\d+)KB' if '模板行为说明」的小节合计约' in harness else r'标了「模板行为说明」的那几节（约 (\d+)KB）',
          sum(len(part.encode()) for part in re.split(r'\n(?=#{2,3} )',skill) if '模板行为说明' in part)/1024,
          '模板行为说明各节')
    # 引号里点名的 SKILL.md 标记必须在 SKILL.md 里找得到（去掉 ** 这类行内标记后比对）
    for mark in re.findall(r'「([^」]{6,40})」',harness):
        if 'SKILL.md' not in harness.split('「'+mark+'」')[0].split('\n')[-1] and '听力' not in mark:continue
        if mark in ('可跳过','模板行为说明'):continue
        plain=re.sub(r'[*`_]','',mark)
        if plain not in re.sub(r'[*`_]','',skill):
            problems.append(f'references/harness.md: 引用了 SKILL.md 里找不到的标记「{mark}」；标记改名后要同步这张表')
    return problems

def declared_test_count(section_text):
    """取版本小节里声明的测试数量。两种写法都认（"测试总数 **N**" 与 "**N 项测试通过**"）——
    只认第一种时，README 换成第二种写法就会让这条检查静默失效（真发生过，数字漂了 37 也没报）。"""
    for pattern in (r'测试总数 \*\*(\d+)\*\*',r'\*\*(\d+)\s*项测试'):
        found=re.findall(pattern,section_text)
        if found:return int(found[0])
    return None

def check(verbose=True):
    problems=[];notes=[]
    text=doc_text()
    scripts=script_names()
    for name in scripts:
        if name not in text and name not in INTERNAL:
            problems.append(f'脚本没在文档里出现：scripts/{name}（老师不会知道它存在；若是内部工具请加进 INTERNAL）')
    for match in re.finditer(r'scripts/([A-Za-z_][A-Za-z0-9_]*\.py)',text):
        name=match.group(1)
        if name not in scripts:
            problems.append(f'文档指向不存在的脚本：scripts/{name}')
    # 命令行参数：抓 "scripts/xxx.py ... --flag" 同一行内的参数
    # 一行里可能提到多个脚本（例：先用 image_pages.py 登记，再用 answers.py --source-images）；
    # 参数只算到"同一行里它前面最近的那个脚本"头上，否则会把别人的参数算错。
    script_mentions,flag_mentions=SCRIPT_MENTION,FLAG_MENTION
    for path in doc_files():
        for line in path.read_text(encoding='utf-8').splitlines():
            marks=[(match.start(),match.group(1)) for match in script_mentions.finditer(line)]
            if not marks:continue
            for flag_match in flag_mentions.finditer(line):
                owner=None
                for position,name in marks:
                    if position<flag_match.start():owner=name
                if owner is None:continue
                target=ROOT/'scripts'/owner
                if not target.is_file():continue
                if flag_match.group(1) not in argparse_options(target):
                    problems.append(f'{path.relative_to(ROOT)}: scripts/{owner} 没有参数 {flag_match.group(1)}')
    # 版本三处一致
    version=(ROOT/'VERSION').read_text(encoding='utf-8').strip()
    manifest=json.loads((ROOT/'assets'/'template-manifest.json').read_text(encoding='utf-8'))
    if manifest.get('template_version')!=version:
        problems.append(f'模板清单版本 {manifest.get("template_version")} 与 VERSION {version} 不一致')
    readme=(ROOT/'README.md').read_text(encoding='utf-8')
    headings=re.findall(r'^## (\d+\.\d+\.\d+)：',readme,re.M)
    if not headings:problems.append('README 里找不到形如 "## 1.2.3：…" 的版本小节')
    elif headings[0]!=version:
        problems.append(f'README 最新版本小节是 {headings[0]}，与 VERSION {version} 不一致')
    # 孤儿文档
    for path in sorted((ROOT/'references').glob('*.md')):
        name=path.name
        if name not in (ROOT/'SKILL.md').read_text(encoding='utf-8') and name not in readme:
            problems.append(f'references/{name} 没有被 SKILL.md 或 README 链接，老师看不到它')
    # 测试数量
    # 旧版本小节里的测试数量是当时的历史数字，不是错误；只核对最新版本小节。
    sections=re.split(r'^## ',readme,flags=re.M)
    newest=next((block for block in sections if block.startswith(f'{version}：')),'')
    declared=declared_test_count(newest)
    if declared is not None:
        sys.path.insert(0,str(ROOT))
        import unittest
        count=unittest.TestLoader().discover(str(ROOT/'tests')).countTestCases()
        if declared!=count:
            problems.append(f'README 最新版本小节写"测试 {declared} 项"，实际是 {count}')
        else:notes.append(f'测试总数 {count} 与 README 最新小节一致')
    else:notes.append('README 最新版本小节没有写测试总数（可选；写了就会核对）')
    # 交叉校对 1：功能编号清单必须与 plan.py 一致（顺序 + 名称）
    features=canonical_features()
    for path,rows in doc_feature_lists():
        problems+=feature_list_problems(str(path.relative_to(ROOT)),rows,features)
    # 交叉校对 2：README 与老师说明的产物清单必须一致
    readme_names=deliverable_names(readme)
    teacher=(ROOT/'docs'/'TEACHER-QUICKSTART.md')
    if teacher.is_file():
        teacher_names=deliverable_names(teacher.read_text(encoding='utf-8'))
        missing=sorted(readme_names-teacher_names)
        if missing:
            problems.append(f'docs/TEACHER-QUICKSTART.md 的产物清单缺少 README 里列出的：{"、".join(missing)}（老师会跨文档看，两处必须一致）')
    # 交叉校对 3：讲安装的文档都必须写明"check_install 到 complete 才算装上"
    problems+=install_claim_problems([(name,(ROOT/name).read_text(encoding='utf-8'))
                                      for name in ('docs/SETUP.md','docs/WINDOWS.md','docs/TEACHER-QUICKSTART.md')
                                      if (ROOT/name).is_file()])
    notes.append(f'检查了 {len(doc_files())} 份文档、{len(scripts)} 个脚本')
    # 交叉校对 4：发布包根目录不得残留旧验收报告（会被打进 ZIP，版本号停在旧版）
    problems+=stale_report_problems(ROOT)
    # 交叉校对 4b：省额度那张表的读数与标记必须与文件实际一致
    problems+=reading_cost_problems(ROOT)
    # 交叉校对 4c：散文里提到的参数必须真有脚本认得（同行写法已在上面的循环里查过）
    problems+=orphan_flag_problems(ROOT)
    # 交叉校对 4d：可照抄的命令一律用 python3（macOS 上 python 往往不存在）
    problems+=command_prefix_problems(ROOT)
    # 交叉校对 4e：标着版本号的"当前状态"小节必须跟 VERSION 一致
    problems+=status_label_problems(ROOT)
    # 交叉校对 5：同一份文档里不得有两个同号小节（老师按"第 N 步"找不到唯一那一步）
    for path in doc_files():
        text=path.read_text(encoding='utf-8')
        label=str(path.relative_to(ROOT))
        problems+=numbered_section_problems(label,text)
        problems+=step_sequence_problems(label,text)
    # 交叉校对 6：文档里的相对链接必须指向真实文件（改名/写错字母会让读者停在 404）
    problems+=broken_link_problems(ROOT)
    # 交叉校对 7：讲安装的文档必须按 host_probe 的顺序写全四条安装路径
    from host_probe import install_paths
    order=[item['path'] for item in install_paths(ROOT,network=False)]
    install_docs=[(name,(ROOT/name).read_text(encoding='utf-8'))
                  for name in ('docs/TEACHER-QUICKSTART.md','docs/SETUP.md','docs/FAQ.md',
                               'references/host-compatibility.md','SKILL.md')
                  if (ROOT/name).is_file()]
    problems+=install_path_doc_problems(install_docs,order)
    return {'status':'ok' if not problems else 'needs_fix','problems':problems,'notes':notes,'version':version}

def main():
    force_utf8()
    parser=argparse.ArgumentParser(description='检查文档与代码/版本/测试数量是否一致')
    parser.add_argument('--json',action='store_true')
    args=parser.parse_args()
    report=check()
    if args.json:print(json.dumps(report,ensure_ascii=False,indent=2))
    else:
        for note in report['notes']:print('· '+note)
        if report['problems']:
            print(f"\n共 {len(report['problems'])} 处文档不一致：")
            for problem in report['problems']:print('  - '+problem)
        else:print('\n文档一致：命令、参数、版本、链接与测试数量都对得上。')
    return 0 if report['status']=='ok' else 1

if __name__=='__main__':raise SystemExit(main())
