from __future__ import annotations

import argparse
import json
import re
import textwrap
import time
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urljoin, urlparse
from urllib.error import URLError
from urllib.request import Request, urlopen


ANSWER_LABELS = ['A', 'B', 'C', 'D']
TOTAL_QUESTION_RE = re.compile(r'题量[:：]\s*(\d+)')
HOST_RE = re.compile(r'_HOST_\s*=\s*["\'](?P<host>[^"\']+)["\']')
CP_RE = re.compile(r'_CP_\s*=\s*["\'](?P<cp>[^"\']+)["\']')
COURSE_ID_RE = re.compile(r'id="courseId"[^>]*value="(?P<value>\d+)"')
CLASS_ID_RE = re.compile(r'id="classId"[^>]*value="(?P<value>\d+)"')
CPI_RE = re.compile(r'id="cpi"[^>]*value="(?P<value>\d+)"')
OPENC_RE = re.compile(r'id="openc"[^>]*value="(?P<value>[^"]+)"')
TEST_PAPER_ID_RE = re.compile(r'id="testPaperId"[^>]*value="(?P<value>\d+)"')
TEST_USER_RELATION_ID_RE = re.compile(r'id="testUserRelationId"[^>]*value="(?P<value>\d+)"')
ENC_RE = re.compile(r'id="enc"[^>]*value="(?P<value>[^"]+)"')
REMAIN_TIME_RE = re.compile(r'id="remainTime"[^>]*value="(?P<value>[^"]+)"')
ENC_LAST_UPDATE_TIME_RE = re.compile(r'id="encLastUpdateTime"[^>]*value="(?P<value>[^"]+)"')
CURRENT_TIME_RE = re.compile(r'window\["currentTime"\]\s*=\s*["\'](?P<value>\d+)["\']')

QUESTION_BLOCK_RE = re.compile(
    r'<div class="whiteDiv questionLi singleQuesId ans-cc mainhet" data="(?P<question_id>\d+)">(?P<body>.*?)<div class="nextDiv">',
    re.S,
)
TITLE_RE = re.compile(r'<h3[^>]*class="mark_name[^\"]*"[^>]*>(?P<value>.*?)</h3>', re.S)
TYPE_SPAN_RE = re.compile(r'<span[^>]*class="colorShallow"[^>]*>(?P<value>.*?)</span>', re.S)
OPTION_RE = re.compile(
    r'<div[^>]*class="[^"]*answerBg[^"]*singleoption[^"]*"[^>]*>\s*'
    r'<span[^>]*data="(?P<label>[ABCD])"[^>]*>.*?</span>\s*'
    r'<div[^>]*class="fl answer_p"[^>]*>(?P<value>.*?)</div>',
    re.S,
)
ANSWER_INPUT_RE = re.compile(r'id="answer(?P<question_id>\d+)"[^>]*value="(?P<value>[^"]*)"')
VISIBLE_ANSWER_RE = re.compile(r'<span[^>]*class="yoursanswer"[^>]*>(?P<value>.*?)</span>', re.S)


class HTMLTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)

    def get_text(self) -> str:
        return ''.join(self.parts)


def normalize_whitespace(text: str) -> str:
    return re.sub(r'\s+', ' ', text).strip()


def strip_tags(html: str) -> str:
    parser = HTMLTextParser()
    parser.feed(html)
    parser.close()
    return parser.get_text()


def clean_text(html: str) -> str:
    text = normalize_whitespace(unescape(strip_tags(html)))
    return text.replace('我的答案:', '').replace('正确答案:', '').strip('。；; ')


def _required_match(pattern: re.Pattern[str], text: str, label: str) -> str:
    match = pattern.search(text)
    if not match:
        raise ValueError(f'无法从 test.html 解析 {label}')
    return match.group('value')


def _optional_match(pattern: re.Pattern[str], text: str) -> str:
    match = pattern.search(text)
    return match.group('value') if match else ''


def parse_page_metadata(html: str) -> dict[str, str]:
    host_match = HOST_RE.search(html)
    cp_match = CP_RE.search(html)
    if not host_match or not cp_match:
        raise ValueError('无法从 test.html 解析站点主机信息')

    host_value = host_match.group('host')
    if host_value.startswith('//'):
        host_value = 'https:' + host_value
    elif not host_value.startswith('http://') and not host_value.startswith('https://'):
        host_value = 'https://' + host_value.lstrip('/')

    return {
        'host': host_value,
        'cp': cp_match.group('cp'),
        'course_id': _required_match(COURSE_ID_RE, html, 'courseId'),
        'class_id': _required_match(CLASS_ID_RE, html, 'classId'),
        'cpi': _required_match(CPI_RE, html, 'cpi'),
        'openc': _required_match(OPENC_RE, html, 'openc'),
        'test_paper_id': _required_match(TEST_PAPER_ID_RE, html, 'testPaperId'),
        'test_user_relation_id': _required_match(TEST_USER_RELATION_ID_RE, html, 'testUserRelationId'),
        'enc': _required_match(ENC_RE, html, 'enc'),
        'remain_time': _required_match(REMAIN_TIME_RE, html, 'remainTime'),
        'relation_answer_last_update_time': _optional_match(ENC_LAST_UPDATE_TIME_RE, html)
        or _optional_match(CURRENT_TIME_RE, html),
    }


def parse_total_questions(html: str) -> int:
    match = TOTAL_QUESTION_RE.search(html)
    if not match:
        raise ValueError('无法从 test.html 解析题量')
    return int(match.group(1))


def build_question_url(metadata: dict[str, str], start_index: int) -> str:
    base_path = urljoin(metadata['host'].rstrip('/') + '/', metadata['cp'].lstrip('/') + '/')
    query = {
        'keyboardDisplayRequiresUserAction': '1',
        'courseId': metadata['course_id'],
        'classId': metadata['class_id'],
        'tId': metadata['test_paper_id'],
        'id': metadata['test_user_relation_id'],
        'p': '1',
        'start': str(start_index),
        'monitorStatus': '0',
        'monitorOp': '-1',
        'examsystem': '0',
        'qbanksystem': '0',
        'qbankbackurl': '',
        'remainTimeParam': metadata['remain_time'],
        'relationAnswerLastUpdateTime': metadata['relation_answer_last_update_time'],
        'enc': metadata['enc'],
        'cpi': metadata['cpi'],
        'openc': metadata['openc'],
        'newMooc': 'true',
        'webSnapshotMonitor': '0',
    }
    return base_path + 'exam/test/reVersionTestStartNew?' + urlencode(query)


def debug_print(debug: bool, message: str) -> None:
    if debug:
        print(f'[debug] {message}')


def fetch_html(
    url: str,
    cookie: str | None = None,
    timeout: int = 30,
    debug: bool = False,
    retries: int = 3,
) -> str:
    parsed_url = urlparse(url)
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Referer': f'{parsed_url.scheme}://{parsed_url.netloc}{parsed_url.path}',
        'Origin': f'{parsed_url.scheme}://{parsed_url.netloc}',
    }
    if cookie:
        headers['Cookie'] = cookie

    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            req = Request(url, headers=headers)
            with urlopen(req, timeout=timeout) as response:
                charset = response.headers.get_content_charset() or 'utf-8'
                html = response.read().decode(charset, errors='replace')

            debug_print(debug, f'GET {url}')
            debug_print(debug, f'HTML length={len(html)}')
            preview = textwrap.shorten(normalize_whitespace(html), width=280, placeholder=' ...')
            debug_print(debug, f'HTML preview: {preview}')
            if '无权访问' in html or '权限' in html:
                debug_print(debug, 'response contains an access-denied message')
            return html
        except (URLError, OSError, TimeoutError) as error:
            last_error = error
            debug_print(debug, f'fetch failed on attempt {attempt}/{retries}: {error}')
            if attempt >= retries:
                break
            time.sleep(min(2 ** (attempt - 1), 5))

    assert last_error is not None
    raise last_error


def parse_question_page(html: str) -> dict[str, Any]:
    block_match = QUESTION_BLOCK_RE.search(html)
    if not block_match:
        raise ValueError('无法在题目页中定位题目块')

    question_id = block_match.group('question_id')
    body = block_match.group('body')
    question: dict[str, Any] = {
        'number': None,
        'type': '',
        'stem': '',
        'options': {},
        'answer': '',
    }

    title_match = TITLE_RE.search(body)
    if title_match:
        title_text = clean_text(title_match.group('value'))
        number_match = re.match(r'^(\d+)\.\s*(.*)$', title_text)
        if number_match:
            question['number'] = int(number_match.group(1))
            title_text = number_match.group(2).strip()
        type_match = TYPE_SPAN_RE.search(body)
        if type_match:
            question['type'] = clean_text(type_match.group('value')).strip('()（） ')
        question['stem'] = title_text.replace('我的答案:', '').strip()

    options: dict[str, str] = {}
    for match in OPTION_RE.finditer(body):
        label = match.group('label').strip().upper()
        if label in ANSWER_LABELS:
            options[label] = clean_text(match.group('value'))
    question['options'] = {label: options[label] for label in ANSWER_LABELS if label in options}

    visible_answer_match = VISIBLE_ANSWER_RE.search(body)
    if visible_answer_match:
        question['answer'] = clean_text(visible_answer_match.group('value')).upper()
    else:
        answer_match = ANSWER_INPUT_RE.search(body) or ANSWER_INPUT_RE.search(html)
        if answer_match and answer_match.group('question_id') == question_id:
            question['answer'] = answer_match.group('value').strip().upper()

    return question


def extract_all_questions(
    index_html_path: Path,
    cookie: str | None = None,
    timeout: int = 30,
    debug: bool = False,
    delay: float = 0.1,
) -> list[dict[str, Any]]:
    seed_html = index_html_path.read_text(encoding='utf-8')
    metadata = parse_page_metadata(seed_html)
    total_questions = parse_total_questions(seed_html)

    debug_print(debug, f'seed html: {index_html_path}')
    debug_print(debug, f'total questions: {total_questions}')
    debug_print(debug, f'course/class/tId: {metadata["course_id"]}/{metadata["class_id"]}/{metadata["test_paper_id"]}')

    questions: list[dict[str, Any]] = []
    for start_index in range(total_questions):
        url = build_question_url(metadata, start_index)
        page_html = fetch_html(url, cookie=cookie, timeout=timeout, debug=debug)
        question = parse_question_page(page_html)
        questions.append(question)
        debug_print(
            debug,
            f'parsed question {len(questions)}/{total_questions}: #{question.get("number", "?")} '
            f'[{question.get("type", "")}] {question.get("stem", "")[:80]}',
        )
        print(f'Extracted {len(questions)}/{total_questions}')
        if delay > 0 and len(questions) < total_questions:
            time.sleep(delay)

    return questions


def main() -> None:
    parser = argparse.ArgumentParser(description='Extract all questions from the paginated test.html format.')
    parser.add_argument(
        '--html',
        dest='html_path_option',
        default='',
        help='Path to the exported test HTML file.',
    )
    parser.add_argument(
        'html_path',
        nargs='?',
        default='problems src/test.html',
        help='Path to the exported test HTML file.',
    )
    parser.add_argument(
        '-o',
        '--output',
        default='all_questions_raw.json',
        help='Output JSON file path.',
    )
    parser.add_argument(
        '--cookie',
        default='',
        help='Optional Cookie header value if the exam site requires authentication.',
    )
    parser.add_argument(
        '--timeout',
        type=int,
        default=30,
        help='Timeout in seconds for each page request.',
    )
    parser.add_argument(
        '--debug',
        action='store_true',
        help='Print fetched HTML previews and parsed question summaries.',
    )
    parser.add_argument(
        '--delay',
        type=float,
        default=0.1,
        help='Delay in seconds between requests.',
    )
    args = parser.parse_args()

    html_path = Path(args.html_path_option or args.html_path)
    output_path = Path(args.output)
    questions = extract_all_questions(
        html_path,
        cookie=args.cookie.strip() or None,
        timeout=args.timeout,
        debug=args.debug,
        delay=args.delay,
    )
    output_path.write_text(json.dumps(questions, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'Extracted {len(questions)} questions to {output_path}')


if __name__ == '__main__':
    main()
