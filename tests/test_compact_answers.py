"""Regression checks for numbered word answers sharing a DOCX paragraph."""
import sys, unittest, tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import answers

class CompactAnswersTests(unittest.TestCase):
    def test_adjacent_numbers(self):
        self.assertEqual(answers.expand('56. named57. it58. faithful59. presence 60. telling'),
                         {'56':'named','57':'it','58':'faithful','59':'presence','60':'telling'})
    def test_multiword_and_variant(self):
        self.assertEqual(answers.expand('61. Despite 62. was introduced 63. uncommon 64. a65. which/that'),
                         {'61':'Despite','62':'was introduced','63':'uncommon','64':'a','65':'which'})
    def test_unicode_number_separator(self):
        self.assertEqual(answers.expand('56．named57、it'), {'56':'named','57':'it'})
    def test_preserve_letter_range(self):
        self.assertEqual(answers.expand('21-25 ABCDA'),dict(zip(map(str,range(21,26)),'ABCDA')))
    def test_extract_keeps_original_line(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'key.txt';p.write_text('56. named57. it58. faithful',encoding='utf-8')
            result=answers.extract(p)
            self.assertEqual(len(result['answers']),3)
            self.assertIn('56. named57. it58. faithful',str(result))
