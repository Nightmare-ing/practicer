from __future__ import annotations

import argparse
import json
import re
from html import unescape
from html.parser import HTMLParser
from pathlib import Path


QUESTION_BLOCK_CLASS = re.compile(r'\bmarBom60\b.*\bquestionLi\b.*\bscroll_\d+\b')
QUESTION_NUMBER_RE = re.compile(r'^(\d+)\.\s*')
QUESTION_TYPE_RE = re.compile(r'^[（(]([^）)]+)[）)]')
OPTION_RE = re.compile(r'^([ABCD])[\.．、:]?\s*(.*)$')
ANSWER_RE = re.compile(r'^[ABCD](?:\s*[，,、/\\]\s*[ABCD])*$', re.IGNORECASE)


def normalize_whitespace(text: str) -> str:
	return re.sub(r'\s+', ' ', text).strip()


def clean_question_title(text: str) -> tuple[str | None, str | None, str]:
	text = normalize_whitespace(unescape(text))
	text = QUESTION_NUMBER_RE.sub('', text)

	question_type = None
	while True:
		match = QUESTION_TYPE_RE.match(text)
		if not match:
			break
		question_type = match.group(1).strip()
		text = text[match.end():].strip()

	text = text.replace('我的答案:', '').strip()
	text = text.rstrip('。；;')
	return None, question_type, text


def clean_option_text(text: str) -> tuple[str | None, str]:
	text = normalize_whitespace(unescape(text))
	text = text.replace('我的答案:', '').strip()
	text = text.rstrip('。；;')

	match = OPTION_RE.match(text)
	if not match:
		return None, text

	label = match.group(1)
	option_text = match.group(2).strip()
	return label, option_text


def clean_answer_text(text: str) -> str:
	text = normalize_whitespace(unescape(text))
	text = text.replace('正确答案:', '').replace('我的答案:', '').strip()
	text = text.rstrip('。；;')
	if ANSWER_RE.match(text):
		return text.upper().replace(' ', '')
	return text


class PracticeHTMLParser(HTMLParser):
	def __init__(self) -> None:
		super().__init__(convert_charrefs=True)
		self.questions: list[dict[str, object]] = []
		self._div_depth = 0
		self._in_question = False
		self._in_title = False
		self._in_option = False
		self._in_answer = False
		self._current_title_parts: list[str] = []
		self._current_option_parts: list[str] = []
		self._current_answer_parts: list[str] = []
		self._current_question: dict[str, object] | None = None

	def handle_starttag(self, tag: str, attrs):
		attrs_dict = dict(attrs)

		if tag == 'div':
			class_name = attrs_dict.get('class', '')
			is_question_block = bool(QUESTION_BLOCK_CLASS.search(class_name))
			if is_question_block and not self._in_question:
				self._in_question = True
				self._div_depth = 1
				self._current_question = {
					'number': None,
					'type': None,
					'stem': '',
					'options': {},
					'answer': '',
				}
				return

			if self._in_question:
				self._div_depth += 1
			return

		if not self._in_question:
			return

		if tag == 'h3':
			class_name = attrs_dict.get('class', '')
			if 'mark_name' in class_name:
				self._in_title = True
				self._current_title_parts = []
			return

		if tag == 'li':
			self._in_option = True
			self._current_option_parts = []
			return

		if tag == 'span':
			class_name = attrs_dict.get('class', '')
			if 'rightAnswerContent' in class_name:
				self._in_answer = True
				self._current_answer_parts = []
			return

		if tag == 'br':
			if self._in_title:
				self._current_title_parts.append(' ')
			elif self._in_option:
				self._current_option_parts.append(' ')
			elif self._in_answer:
				self._current_answer_parts.append(' ')

	def handle_endtag(self, tag: str):
		if not self._in_question:
			return

		if tag == 'h3' and self._in_title:
			raw_title = ''.join(self._current_title_parts)
			number_match = QUESTION_NUMBER_RE.match(normalize_whitespace(unescape(raw_title)))
			if self._current_question is not None and number_match:
				self._current_question['number'] = int(number_match.group(1))
			_, question_type, stem = clean_question_title(raw_title)
			if self._current_question is not None:
				self._current_question['type'] = question_type
				self._current_question['stem'] = stem
			self._in_title = False
			self._current_title_parts = []
			return

		if tag == 'li' and self._in_option:
			raw_option = ''.join(self._current_option_parts)
			label, option_text = clean_option_text(raw_option)
			if label and self._current_question is not None:
				options = self._current_question['options']
				assert isinstance(options, dict)
				options[label] = option_text
			self._in_option = False
			self._current_option_parts = []
			return

		if tag == 'span' and self._in_answer:
			raw_answer = ''.join(self._current_answer_parts)
			answer = clean_answer_text(raw_answer)
			if self._current_question is not None:
				self._current_question['answer'] = answer
			self._in_answer = False
			self._current_answer_parts = []
			return

		if tag == 'div' and self._in_question:
			self._div_depth -= 1
			if self._div_depth <= 0:
				if self._current_question is not None:
					options = self._current_question['options']
					assert isinstance(options, dict)
					ordered_options = {
						label: options[label]
						for label in ['A', 'B', 'C', 'D']
						if label in options and options[label]
					}
					self._current_question['options'] = ordered_options
					self.questions.append(self._current_question)
				self._in_question = False
				self._current_question = None
				self._current_title_parts = []
				self._current_option_parts = []
				self._current_answer_parts = []
				self._in_answer = False

	def handle_data(self, data: str):
		if self._in_title:
			self._current_title_parts.append(data)
		elif self._in_option:
			self._current_option_parts.append(data)
		elif self._in_answer:
			self._current_answer_parts.append(data)


def extract_questions(html_path: Path) -> list[dict[str, object]]:
	parser = PracticeHTMLParser()
	parser.feed(html_path.read_text(encoding='utf-8'))
	parser.close()
	return parser.questions


def main() -> None:
	parser = argparse.ArgumentParser(description='Extract structured practice questions from a web HTML export.')
	parser.add_argument(
		'html_path',
		nargs='?',
		default='problems src/practice.html',
		help='Path to the exported HTML file.',
	)
	parser.add_argument(
		'-o',
		'--output',
		default='practice_questions.json',
		help='Output JSON file path.',
	)
	args = parser.parse_args()

	html_path = Path(args.html_path)
	output_path = Path(args.output)

	questions = extract_questions(html_path)
	output_path.write_text(json.dumps(questions, ensure_ascii=False, indent=2), encoding='utf-8')

	print(f'Extracted {len(questions)} questions to {output_path}')


if __name__ == '__main__':
	main()
