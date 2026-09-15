"""补上"从未被任何测试触发过"的显式判据（对应用户最在意的一条：闸门必须真的会拦人）。

来历：把"每条判据的说明是否在测试里被断言过"的覆盖面从三个交付文件（`verify_output` /
`package_lesson` / `qa_report`）扩到**全部随包发布的脚本**后，一次量出 **24 条从未被任何测试
提到过**的判据，分布在 `prepare_whisper`（6）、`audio`（4）、`import_timed_text`（3）、
`extract_package`（2）、`preferences`（2）、`scope`/`plan`/`build`/`parts`/`fetch_package`/
`quotes`/`image_pages`（各 1）。这些判据改松了不会有任何测试报警——而它们守的正是"不许乱编"
那一类底线（引用必须落在完整词上、转写引文必须与切点吻合、备份不能覆盖技能目录……）。

本文件逐条用**真实夹具**把它们触发一遍；只有一处（`audio.cut` 的引文核验）需要 ffmpeg 才能走到，
本机与 CI 都没有，于是那条如实 `skipTest` 并写明原因——它在装了 ffmpeg 的机器上会真的跑。
末尾的守卫把"以后新加的判据说明必须出现在测试里"钉住，防止再退回去。
"""
import argparse
import hashlib
import io
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import types
import unittest
import wave
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'tests'))
import audio
import extract
import check_install
import answers
import align_whisperx
import extract_package
import fetch_package
import image_pages
import import_timed_text
import package_skill
import parts
import plan
import preferences
import prepare_whisper as setup
import quotes
import scope

SHIPS = package_skill.shipped_files


def wav_bytes(frames=8000, rate=8000, channels=1, width=2, declared_frames=None):
    """真实 WAV 字节；`declared_frames` 用来造"声明帧数大于实际数据"的截断文件。"""
    buffer = io.BytesIO()
    with wave.open(buffer, 'wb') as handle:
        handle.setnchannels(channels)
        handle.setsampwidth(width)
        handle.setframerate(rate)
        handle.writeframes(b'\x00' * frames * width * channels)
    data = bytearray(buffer.getvalue())
    if declared_frames is not None:
        declared = declared_frames * width * channels
        struct.pack_into('<I', data, 4, 36 + declared)
        struct.pack_into('<I', data, data.find(b'data') + 4, declared)
    return bytes(data)


class PrepareWhisperRaises(unittest.TestCase):
    """`prepare_whisper.py` 的 6 条判据：预算、路径安全、体积、不覆盖旧目录、CLI 范围。"""

    def test_time_budget_is_enforced_not_silently_exceeded(self):
        with self.assertRaises(TimeoutError) as caught:
            setup.remaining(__import__('time').monotonic() - 1)
        self.assertIn('依赖准备已达到时间预算', str(caught.exception))

    def test_unsafe_archive_paths_are_refused(self):
        for bad in ('../escape', '/absolute/path', 'dir\\win', 'C:evil', 'a/../../b'):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError) as caught:
                    setup.safe_name(bad)
                self.assertIn('压缩包里出现不安全的路径', str(caught.exception))

    def test_oversized_zip_is_refused_before_extracting(self):
        """真实 2GB 夹具造不出来（判据本身就是体积），所以用假的 infolist 声明体积；
        走的是真代码路径里的 `sum(file_size)>2GB` 那一行。"""
        class FakeZip:
            def __init__(self, *a, **k): pass
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def infolist(self): return [types.SimpleNamespace(file_size=3_000_000_000, filename='huge.bin')]

        with tempfile.TemporaryDirectory() as temp:
            archive = Path(temp) / 'runtime.zip'
            archive.write_bytes(b'not really a zip')
            with mock.patch.object(setup.zipfile, 'is_zipfile', lambda path: True), \
                 mock.patch.object(setup.zipfile, 'ZipFile', FakeZip):
                with self.assertRaises(ValueError) as caught:
                    setup.unpack(archive, Path(temp) / 'out')
        self.assertIn('超过 2GB', str(caught.exception))

    def test_oversized_tar_is_refused_before_extracting(self):
        class FakeTar:
            def __init__(self, *a, **k): pass
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def getmembers(self): return [types.SimpleNamespace(size=3_000_000_000, name='huge.bin', isfile=lambda: False)]

        with tempfile.TemporaryDirectory() as temp:
            archive = Path(temp) / 'runtime.tar.gz'
            archive.write_bytes(b'not really a tar')
            with mock.patch.object(setup.zipfile, 'is_zipfile', lambda path: False), \
                 mock.patch.object(setup.tarfile, 'open', FakeTar):
                with self.assertRaises(ValueError) as caught:
                    setup.unpack(archive, Path(temp) / 'out')
        self.assertIn('超过 2GB', str(caught.exception))

    def test_existing_but_unrecognised_runtime_is_refused_not_overwritten(self):
        """Windows 分支：旧目录存在但不能用时，保留旧目录让人诊断，绝不覆盖。"""
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'whisper-v1').mkdir()
            payload = b'pretend-runtime-archive'
            releases = [{'tag_name': 'v1', 'assets': [{'name': 'whisper-bin-x64.zip',
                                                       'digest': 'sha256:' + hashlib.sha256(payload).hexdigest(),
                                                       'browser_download_url': 'https://example.invalid/x.zip'}]}]

            def fake_fetch(url, target=None, deadline=None):
                if 'releases' in url:
                    return releases
                Path(target).write_bytes(payload)
                return Path(target)

            with mock.patch.object(setup, 'fetch', fake_fetch), \
                 mock.patch.object(setup.platform, 'system', lambda: 'Windows'), \
                 mock.patch.object(setup.platform, 'machine', lambda: 'AMD64'), \
                 mock.patch.object(setup, 'os', types.SimpleNamespace(name='nt', environ=os.environ,
                                                                     path=os.path, cpu_count=os.cpu_count)), \
                 mock.patch.object(setup, 'whisper_bin', lambda: None):
                with self.assertRaises(ValueError) as caught:
                    setup.prepare(str(root), True, 60)
            self.assertIn('目标运行时已存在但未识别为可用', str(caught.exception))
            self.assertIn('保留旧目录', str(caught.exception))

    def test_cli_rejects_out_of_range_budget(self):
        """时间预算的范围在命令行上是硬判据：老师被要求"延长前取得同意"，不能悄悄放大。"""
        with tempfile.TemporaryDirectory() as temp:
            done = subprocess.run([sys.executable, str(ROOT / 'scripts' / 'prepare_whisper.py'),
                                   '--seconds', '5', '--root', temp],
                                  capture_output=True, text=True, encoding='utf-8', errors='replace')
        self.assertEqual(1, done.returncode)
        self.assertIn('时间预算范围 15–3600 秒', done.stderr)


class AudioRaises(unittest.TestCase):
    """`audio.py` 的 4 条判据：外部命令失败、空 WAV、截断 WAV、切点引文不匹配。"""

    def test_external_command_failure_is_reported_with_exit_code(self):
        with self.assertRaises(ValueError) as caught:
            audio.run([sys.executable, '-c', 'import sys; sys.exit(3)'])
        self.assertIn('外部命令执行失败', str(caught.exception))

    def test_wav_without_playable_frames_is_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / 'empty.wav'
            target.write_bytes(wav_bytes(frames=0))
            with self.assertRaises(ValueError) as caught:
                audio.probe(target)
        self.assertIn('WAV 没有可播放的音频帧', str(caught.exception))

    def test_truncated_wav_is_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / 'cut.wav'
            target.write_bytes(wav_bytes(frames=1600, declared_frames=8000))
            with self.assertRaises(ValueError) as caught:
                audio.probe(target)
        self.assertIn('WAV 文件已截断', str(caught.exception))

    def test_quote_that_does_not_match_the_cut_is_refused(self):
        """切点上的引文必须与那段转写吻合——"不能改音频去迁就引文"。

        走的是 `cut()` 的复用分支（输出目录里已有片段），因此不需要 ffmpeg 去裁剪；
        只有 `probe()` 需要 ffprobe，这里用桩替掉，因为本判据考的是引文核验、不是探测。
        """
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            source = base / 'full.wav'
            source.write_bytes(wav_bytes(frames=8000))
            from audio import sha256 as source_sha
            out = base / 'out'
            out.mkdir()
            # cut() 的完整原音默认转成 mp3（.wav 不在 AUDIO_COPY_SUFFIXES 里），
            # 复用分支要求它就是 full.mp3——摆对了这一步，这条判据就不需要 ffmpeg。
            (out / 'full.mp3').write_bytes(b'pretend-mp3')
            (out / 'L1.mp3').write_bytes(b'pretend-mp3')
            (out / 'segments.json').write_text(json.dumps({
                'source_audio_sha256': source_sha(source),
                'segments': [{'id': 'L1', 'start': 0.0, 'end': 1.0, 'audio': 'L1.mp3'}]}), encoding='utf-8')
            manifest = base / 'manifest.json'
            manifest.write_text(json.dumps({
                'expected_count': 1, 'kind': 'text',
                'segments': [{'id': 'L1', 'start': 0.0, 'end': 1.0, 'verified': True, 'evidence': '第 1 题原文',
                              'question_ids': ['1'], 'opening_quote': '这是故意写错的引文内容'}]}), encoding='utf-8')
            transcript = base / 'transcript.json'
            transcript.write_text(json.dumps({
                'source_audio_sha256': source_sha(source),
                'segments': [{'start': 0.2, 'end': 0.6, 'text': 'the quick brown fox jumps over the lazy dog'}]}),
                                  encoding='utf-8')
            args = argparse.Namespace(input=str(source), manifest=str(manifest), out=str(out), transcript=str(transcript),
                                      allow_unverified=False, resume=True, threads=1, jobs=1)
            with mock.patch.object(audio, 'probe', lambda path: 1.0):
                with self.assertRaises(ValueError) as caught:
                    audio.cut(args)
        message = str(caught.exception)
        self.assertIn('与该切点的转写不匹配', message)
        self.assertIn('不能改音频去迁就引文', message)


class TimedTextRaises(unittest.TestCase):
    """`import_timed_text.py` 的 3 条判据：坏时间行、缺文字、没有有效时间段。"""

    def write(self, name, body):
        temp = tempfile.mkdtemp()
        path = Path(temp) / name
        path.write_text(body, encoding='utf-8')
        return path

    def test_unparsable_time_line_is_reported_with_the_line(self):
        path = self.write('bad.srt', '1\n00:00:0 --> later\n你好\n')
        with self.assertRaises(ValueError) as caught:
            import_timed_text.parse(path)
        self.assertIn('无法解析字幕时间行', str(caught.exception))

    def test_segment_without_text_is_refused(self):
        path = self.write('empty.srt', '1\n00:00:00,000 --> 00:00:01,000\n\n2\n00:00:01,000 --> 00:00:02,000\n有字\n')
        with self.assertRaises(ValueError) as caught:
            import_timed_text.parse(path)
        self.assertIn('字幕片段缺少文字', str(caught.exception))

    def test_file_without_any_time_range_is_refused(self):
        path = self.write('plain.srt', '这里只有台词\n没有时间轴\n')
        with self.assertRaises(ValueError) as caught:
            import_timed_text.parse(path)
        self.assertIn('字幕没有有效时间段', str(caught.exception))


class ExtractPackageRaises(unittest.TestCase):
    """`extract_package.py` 的 2 条判据：解压体积上限、备份目录不得与技能目录重叠。"""

    def test_archive_over_the_size_cap_is_refused(self):
        import zipfile
        with tempfile.TemporaryDirectory() as temp:
            archive = Path(temp) / 'bundle.zip'
            with zipfile.ZipFile(archive, 'w') as bundle:
                bundle.writestr('SKILL.md', 'x' * 200)
            with mock.patch.object(extract_package, 'SIZE_CAP', 10):
                with self.assertRaises(ValueError) as caught:
                    extract_package.safe_extract(archive, Path(temp) / 'out')
        self.assertIn('压缩包解压后过大，拒绝解压', str(caught.exception))

    def test_backup_overlapping_the_skill_folder_is_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            current = Path(temp) / 'english-exam-studio'
            current.mkdir()
            extracted = Path(temp) / 'extracted'
            extracted.mkdir()
            with self.assertRaises(ValueError) as caught:
                extract_package.apply_update(current, extracted, current)
        self.assertIn('备份目录不能与技能目录重叠', str(caught.exception))


class PreferencesRaises(unittest.TestCase):
    """`preferences.py` 的 2 条判据：没有先问老师、没有记录全部功能选择。"""

    def test_plan_without_teachers_confirmation_is_refused(self):
        with self.assertRaises(ValueError) as caught:
            preferences.apply_plan({}, {'confirmed': False, 'mode': 'lesson', 'sections': 'all', 'features': {}})
        self.assertIn('请先询问老师生成范围和所需功能', str(caught.exception))

    def test_plan_missing_some_feature_choices_is_refused(self):
        with self.assertRaises(ValueError) as caught:
            preferences.apply_plan({}, {'confirmed': True, 'mode': 'lesson', 'sections': 'all',
                                        'features': {'annotations': True}})
        self.assertIn('请记录全部可选功能的选择', str(caught.exception))


class ScopeAndPlanRaises(unittest.TestCase):
    """两条"选不出来就不许开工"的判据：`scope.py` 空选择、`plan.py` 编号越界。"""

    def test_selecting_nothing_is_refused(self):
        with self.assertRaises(ValueError) as caught:
            scope.select({'sections': []}, 'all')
        self.assertIn('没有选中任何板块', str(caught.exception))

    def test_out_of_range_feature_number_is_refused(self):
        with self.assertRaises(ValueError) as caught:
            plan.parse_features('9')
        self.assertIn('超出范围 1–', str(caught.exception))
        self.assertIn(f'1–{len(plan.FEATURES)}', str(caught.exception))


class BuildRaises(unittest.TestCase):
    """`build.py` 的空 WAV 判据：音频登记了但里面一帧都没有，必须拦住而不是产出一份哑课件。"""

    def test_empty_wav_in_the_material_is_refused(self):
        import build
        import contextlib
        import make_browser_fixture as fixture
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            source, output = base / 'in', base / 'out'
            with contextlib.redirect_stdout(io.StringIO()):   # 夹具会把构建报告打到 stdout，测试输出不必跟着刷屏
                fixture.make(source, output)
            document = json.loads((source / 'exam.json').read_text(encoding='utf-8'))
            target = None
            for section in document.get('sections', []):
                if section.get('audio'):
                    target = source / section['audio']
                    break
            if target is None:
                self.skipTest('这套夹具没有登记外置音频，本判据无对象可测')
            target.write_bytes(wav_bytes(frames=0))
            with self.assertRaises(ValueError) as caught:
                build.build(str(source / 'exam.json'), str(output), source_ledger=str(source / 'source-ledger.json'))
        self.assertIn('WAV 音频为空', str(caught.exception))


class PartsRaises(unittest.TestCase):
    """`parts.py` 的串节判据：分节文件里的 id 与文件名不符时，禁止合并。"""

    def test_section_file_with_mismatched_id_is_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            source = base / 'exam.json'
            source.write_text(json.dumps({'sections': [{'id': 'A'}]}), encoding='utf-8')
            work = base / 'parts'
            work.mkdir()
            (work / '_meta.json').write_text(json.dumps({'section_order': ['A'], '_source': str(source.resolve())}), encoding='utf-8')
            (work / 'A.json').write_text(json.dumps({'id': 'B'}), encoding='utf-8')
            with self.assertRaises(ValueError) as caught:
                parts.merge(work, base / 'merged.json')
        self.assertIn('分节文件 ID 与文件名不符', str(caught.exception))


class FetchPackageRaises(unittest.TestCase):
    """`fetch_package.py` 的版本判据：包版本与要求的版本不一致时必须说清是哪一个。"""

    def test_version_mismatch_names_both_versions(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            (base / 'install-manifest.json').write_text(json.dumps({'version': '9.9.9', 'files': {'SKILL.md': 'x'}}),
                                                        encoding='utf-8')
            with self.assertRaises(ValueError) as caught:
                fetch_package.fetch_package('file://' + str(base), str(base / 'out'), expected_version='1.0.117')
        self.assertIn('这个包的版本是 9.9.9', str(caught.exception))
        self.assertIn('1.0.117', str(caught.exception))


class QuotesRaises(unittest.TestCase):
    """`quotes.py` 的范围判据：引用指向不存在的段落时，必须列出问题而不是写出空引用。"""

    def test_quote_pointing_at_a_missing_paragraph_is_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'exam.json'
            path.write_text(json.dumps({
                'sections': [
                    {'id': 'A', 'kind': 'reading', 'questions': [], 'paragraphs': [{'id': 'p1', 'text': 'Hello world.'}]},
                    {'id': 'B', 'kind': 'reading', 'questions': [
                        {'id': '1', 'paragraph_id': 'missing', 'quote_ref': {'chars': [0, 5]}}]}],
            }, ensure_ascii=False), encoding='utf-8')
            with self.assertRaises(ValueError) as caught:
                quotes.fill(path, None)
        self.assertIn('引用范围有问题', str(caught.exception))
        self.assertIn('指向不存在的段落', str(caught.exception))


class ImagePagesRaises(unittest.TestCase):
    """`image_pages.py` 的"没图片就别硬编页"判据。"""

    def test_folder_without_images_is_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            empty = Path(temp) / 'empty'
            empty.mkdir()
            with self.assertRaises(ValueError) as caught:
                image_pages.inventory([], empty, 'paper')
        self.assertIn('没有找到图片文件', str(caught.exception))


class SecondBatchRaises(unittest.TestCase):
    """第二批判据：把守卫的口径改成"中文按 5 字、ASCII 按 8 字"之后，又揭出 10 条。

    它们以前算"已覆盖"，其实是靠 `DOCX `、`files`、`SRT /` 这类通用 ASCII 片段撞上的——
    等于没覆盖。这里逐条用真实夹具触发，把假通过变成真覆盖。
    """

    def docx_without_body(self, path):
        import zipfile
        with zipfile.ZipFile(path, 'w') as bundle:
            bundle.writestr('word/document.xml',
                            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"/>')
        return path

    def test_missing_build_tools_are_reported_before_downloading(self):
        """没有 CMake/C++ 时先说清楚，而不是先下载源码再报错。"""
        with tempfile.TemporaryDirectory() as temp:
            with mock.patch.object(setup, 'whisper_bin', lambda: None), \
                 mock.patch.object(setup.shutil, 'which', lambda name: None):
                with self.assertRaises(ValueError) as caught:
                    setup.prepare(temp, True, 60)
        self.assertIn('缺少 CMake/C++ 编译工具', str(caught.exception))

    def test_bad_manifest_shape_is_reported_not_crashed(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'install-manifest.json').write_text(json.dumps({'files': ['SKILL.md']}), encoding='utf-8')
            report = check_install.check(root)
        self.assertEqual('incomplete_install', report['status'])
        self.assertIn('安装清单格式不对', ' '.join(report['errors']))

    def test_docx_answer_without_body_is_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            path = self.docx_without_body(Path(temp) / 'answers.docx')
            with self.assertRaises(ValueError) as caught:
                answers.docx_text(path)
        self.assertIn('答案 DOCX 缺少正文 w:body', str(caught.exception))

    def test_plan_segment_missing_fields_is_refused_before_environment_check(self):
        """计划写错时不能先报"没装 WhisperX"——那会让人去装一个用不上的依赖。"""
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            source = base / 'full.wav'
            source.write_bytes(wav_bytes())
            plan_file = base / 'plan.json'
            plan_file.write_text(json.dumps({'segments': [{'id': 'L1', 'start': 0.0, 'end': 1.0}]}), encoding='utf-8')
            with self.assertRaises(ValueError) as caught:
                align_whisperx.align(str(source), str(plan_file), str(base / 'out'), str(base / 'cache'))
        self.assertIn('每段都必须写 id、start、end、text', str(caught.exception))

    def test_empty_whisper_transcript_is_not_marked_as_recognised(self):
        with tempfile.TemporaryDirectory() as temp:
            stem = Path(temp) / 'part'

            def fake_run(command, timeout=600, include_stderr=False):
                Path(str(stem) + '.json').write_text(json.dumps({'segments': []}), encoding='utf-8')
                return ''

            with mock.patch.object(audio, 'whisper_exe', lambda: 'whisper-cli'), \
                 mock.patch.object(audio, 'run', fake_run):
                with self.assertRaises(ValueError) as caught:
                    audio.whisper_rows(Path(temp) / 'a.wav', 'model.bin', 'en', stem, 4, 60)
        self.assertIn('Whisper 返回空转写', str(caught.exception))

    def test_transcript_from_an_unknown_source_is_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            source = base / 'full.wav'
            source.write_bytes(wav_bytes())
            transcript = base / 'other.json'
            transcript.write_text(json.dumps({'source_audio_sha256': '0' * 64,
                                              'segments': [{'start': 0.0, 'end': 1.0, 'text': 'hello there friend'}]}),
                                  encoding='utf-8')
            args = argparse.Namespace(input=str(source), out=str(base / 'out'), reuse=False, transcript=str(transcript),
                                      model=None, timeout=60, jobs=1, threads=1, no_asr=False, no_gpu=True,
                                      min_gap=1.0, language='en')
            with self.assertRaises(ValueError) as caught:
                audio.analyze(args)
        self.assertIn('外部转写必须绑定当前原音 SHA256', str(caught.exception))

    def test_asr_timeout_says_what_to_change(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            source = base / 'full.wav'
            source.write_bytes(wav_bytes(frames=16000))
            model = base / 'model.bin'
            model.write_bytes(b'pretend-model')
            args = argparse.Namespace(input=str(source), out=str(base / 'out'), reuse=False, transcript=None,
                                      model=str(model), timeout=7, jobs=1, threads=1, no_asr=False, no_gpu=True,
                                      min_gap=1.0, language='en')

            def timeout(*a, **k):
                raise subprocess.TimeoutExpired(cmd='whisper-cli', timeout=7)

            with mock.patch.object(audio, 'find_silences', lambda path: []), \
                 mock.patch.object(audio, 'split_points', lambda *a, **k: []), \
                 mock.patch.object(audio, 'run', lambda *a, **k: ''), \
                 mock.patch.object(audio, 'whisper_rows', timeout):
                with self.assertRaises(ValueError) as caught:
                    audio.analyze(args)
        self.assertIn('ASR 超时', str(caught.exception))
        self.assertIn('--no-asr', str(caught.exception))

    def test_plain_text_has_no_real_cut_points(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'plain.txt'
            path.write_text('这里只有台词\n没有时间轴\n', encoding='utf-8')
            with self.assertRaises(ValueError) as caught:
                import_timed_text.parse(path)
        self.assertIn('支持 SRT / VTT / 带时间 JSON', str(caught.exception))

    def test_docx_without_body_is_refused_when_reading_the_paper(self):
        import zipfile
        with tempfile.TemporaryDirectory() as temp:
            path = self.docx_without_body(Path(temp) / 'paper.docx')
            with zipfile.ZipFile(path) as archive:
                with self.assertRaises(ValueError) as caught:
                    extract.document_body(archive)
        self.assertIn('DOCX 缺少正文 w:body', str(caught.exception))

    def test_manifest_without_files_list_is_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            (base / 'install-manifest.json').write_text(json.dumps({'version': '1.0.117'}), encoding='utf-8')
            with self.assertRaises(ValueError) as caught:
                fetch_package.fetch_package('file://' + str(base), str(base / 'out'))
        self.assertIn('里没有 files 清单', str(caught.exception))


CJK = __import__('re').compile(r'[\u4e00-\u9fff]')
# 要文件系统/压缩层真的出错才会走到，无法用真实夹具触发；软链接那条另有用例。
EXEMPT_RAISES = {
    ('package_lesson.py', 'ZIP 完整性检查失败'): '要文件系统/压缩层真的出错才会走到，无法用真实夹具触发；软链接那条另有用例',
}


def unmentioned_messages(root=ROOT, exempt=None):
    """发布脚本里"说明文字从未出现在任何测试中"的判据清单。

    中文按 5 字窗口匹配（测试常只断言其中一段），ASCII 按 8 字。为什么要分开：一开始照搬
    "一律 5 字窗口"的旧口径，结果一次变异验证**没抓住**——塞进脚本的 `ZQPROBE9917` 被判成
    "已被提到"，因为 5 字窗口 `PROBE` 命中了测试里的 `FFPROBE_BIN`。5 字窗口对短英文词太松。
    """
    root = Path(root).resolve()
    exempt = EXEMPT_RAISES if exempt is None else exempt
    tests = '\n'.join(path.read_text(encoding='utf-8') for path in (root / 'tests').glob('*.py'))

    def mentioned(text):
        for i in range(max(0, len(text) - 4)):
            window = text[i:i + 5]
            if CJK.search(window) and window in tests:
                return True
        return any(text[i:i + 8] in tests for i in range(max(0, len(text) - 7)))

    import ast
    absent = []
    for path in SHIPS(root):
        if path.suffix != '.py' or path.parent.name != 'scripts':
            continue
        name = path.name
        for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
            if not isinstance(node, ast.Raise) or not isinstance(node.exc, ast.Call) or not node.exc.args:
                continue
            pieces = [piece.value for piece in ast.walk(node.exc.args[0])
                      if isinstance(piece, ast.Constant) and isinstance(piece.value, str) and len(piece.value) >= 8]
            if not pieces:
                continue
            if any((name, text[:24]) in exempt for text in pieces):
                continue
            if not any(mentioned(text) for text in pieces):
                absent.append((name, node.lineno, pieces[0][:30]))
    return absent


class EveryReleaseCriterionIsMentionedInTests(unittest.TestCase):
    """守卫：随包发布的每个脚本里，每条判据的说明都必须能在测试里找到。

    口径见 `unmentioned_messages()` 的说明；范围是**全部发布脚本**（不只交付三文件）。
    判据措辞改了而测试没跟上，这条会失败；范围缩了（比如只扫一部分脚本）也等于空转，
    所以另有断言钉住扫描范围本身。
    """

    def test_scan_covers_every_shipped_script(self):
        names = [p.relative_to(ROOT).as_posix() for p in SHIPS(ROOT) if p.suffix == '.py' and p.parent.name == 'scripts']
        self.assertGreaterEqual(len(names), 25, '随包发布的脚本应有几十个，少了说明扫描范围漂了')
        for required in ('scripts/build.py', 'scripts/audio.py', 'scripts/quote' + 's.py'):
            self.assertIn(required, names)

    def test_no_script_was_added_without_a_test_mentioning_its_messages(self):
        absent = unmentioned_messages()
        self.assertEqual([], absent, '这些判据的说明没有任何测试提到过（判据改松不会有人发现）：' + repr(absent))

    def test_the_guard_itself_bites(self):
        """守卫自己的反向验证：临时把一条没人提到的判据写进发布脚本，它必须报出来。

        变异文本用罕见字，保证没有任何 5/8 字窗口在测试里撞车——否则就是"用例看着写了、
        其实守卫压根咬不动"（这正是上一版口径的真实翻车方式）。
        """
        target = ROOT / 'scripts' / 'parts.py'
        original = target.read_text(encoding='utf-8')
        # 变异串在运行时拼出来：直接写成字面量的话，它会出现在**本文件**里，守卫于是判定
        # "已被测试提到"——那就成了自己骗自己（上一版正是这么翻的车）。
        rare = ''.join(['獬豸', '甪端', '饕餮', '貔貅', '睚眦', '螭吻'])
        tests_text = '\n'.join(path.read_text(encoding='utf-8') for path in (ROOT / 'tests').glob('*.py'))
        self.assertNotIn(rare, tests_text, '变异串不能出现在测试里，否则这条反向验证是假的')
        probe = f'\ndef _mutation_probe():\n    raise ValueError("{rare}")\n'
        try:
            target.write_text(original + probe, encoding='utf-8')
            found = [row for row in unmentioned_messages() if row[0] == 'parts.py']
            self.assertTrue(found, '变异判据写进了发布脚本，守卫却没报——这条守卫是假的')
            self.assertIn(rare[:2], found[0][2])
        finally:
            target.write_text(original, encoding='utf-8')
        self.assertEqual(original, target.read_text(encoding='utf-8'), '验证后必须逐字节还原，不能留下改动')
        self.assertEqual([], [row for row in unmentioned_messages() if row[0] == 'parts.py'], '还原后不该还有问题')


if __name__ == '__main__':
    unittest.main()
