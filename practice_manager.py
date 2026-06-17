from __future__ import annotations

import argparse
import json
import os
import random
import re
from pathlib import Path
from typing import Any


DEFAULT_DATA_PATH = Path('practice_questions.json')
ANSWER_LABELS = ['A', 'B', 'C', 'D']
STOP_WORDS = {'q', 'quit', 'exit', 'back'}


def load_questions(data_path: Path) -> list[dict[str, Any]]:
    questions = json.loads(data_path.read_text(encoding='utf-8'))
    for question in questions:
        question.setdefault('answer', '')
        question['wrong_count'] = int(question.get('wrong_count', 0) or 0)
    return questions


def save_questions(data_path: Path, questions: list[dict[str, Any]]) -> None:
    data_path.write_text(
        json.dumps(questions, ensure_ascii=False, indent=2),
        encoding='utf-8',
    )


def normalize_text(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r'\s+', '', text)
    text = re.sub(r'[，。！？、,.;:：\-()（）\[\]{}"“”‘’<>《》]', '', text)
    return text


def question_search_blob(question: dict[str, Any]) -> str:
    parts = [str(question.get('number', '')), str(question.get('type', '')), question.get('stem', '')]
    options = question.get('options', {})
    if isinstance(options, dict):
        parts.extend(str(value) for value in options.values())
    return normalize_text(' '.join(parts))


def search_questions(questions: list[dict[str, Any]], query: str, limit: int = 10) -> list[dict[str, Any]]:
    normalized_query = normalize_text(query)
    if not normalized_query:
        return []

    results: list[tuple[int, dict[str, Any]]] = []
    for question in questions:
        blob = question_search_blob(question)
        if normalized_query in blob:
            score = blob.find(normalized_query)
            results.append((score, question))

    results.sort(key=lambda item: (item[0], int(item[1].get('number', 10**9))))
    return [question for _, question in results[:limit]]


def render_question(question: dict[str, Any], show_answer: bool = False) -> str:
    lines = [
        f"#{question.get('number', '?')} [{question.get('type', '')}]",
        question.get('stem', ''),
    ]
    options = question.get('options', {})
    if isinstance(options, dict):
        for label in ANSWER_LABELS:
            if label in options:
                lines.append(f"{label}. {options[label]}")
    if show_answer:
        answer = question.get('answer', '')
        wrong_count = question.get('wrong_count', 0)
        lines.append(f"答案: {answer if answer else '未录入'}")
        lines.append(f"错题次数: {wrong_count}")
    return '\n'.join(lines)


def resolve_answer(question: dict[str, Any], user_input: str) -> str:
    candidate = user_input.strip().upper()
    options = question.get('options', {})
    if candidate in ANSWER_LABELS:
        return candidate
    if isinstance(options, dict):
        normalized_input = normalize_text(user_input)
        for label, option_text in options.items():
            if normalize_text(str(option_text)) == normalized_input:
                return label
    return user_input.strip()


def normalize_answer(question: dict[str, Any], answer_value: str) -> str:
    candidate = str(answer_value).strip()
    if not candidate:
        return ''

    candidate_upper = candidate.upper()
    if candidate_upper in ANSWER_LABELS:
        return candidate_upper

    options = question.get('options', {})
    if isinstance(options, dict):
        normalized_candidate = normalize_text(candidate)
        for label, option_text in options.items():
            if normalize_text(str(option_text)) == normalized_candidate:
                return label

    return candidate


def answers_match(question: dict[str, Any], stored_answer: str, user_answer: str) -> bool:
    normalized_stored = normalize_answer(question, stored_answer)
    normalized_user = normalize_answer(question, user_answer)

    if normalized_stored.upper() in ANSWER_LABELS and normalized_user.upper() in ANSWER_LABELS:
        return normalized_stored.upper() == normalized_user.upper()

    return normalize_text(normalized_stored) == normalize_text(normalized_user)


def prompt(text: str) -> str:
    return input(text).strip()


def clear_screen() -> None:
    os.system('clear')


def choose_question_interactively(questions: list[dict[str, Any]]) -> dict[str, Any] | None:
    while True:
        query = prompt('输入题目关键词、题号，或输入 q 退出: ')
        if query.lower() in STOP_WORDS:
            return None

        if query.isdigit():
            for question in questions:
                if int(question.get('number', -1)) == int(query):
                    return question

        matches = search_questions(questions, query)
        if not matches:
            print('没有找到匹配题目。')
            continue

        print('\n匹配结果:')
        for index, question in enumerate(matches, start=1):
            stem = question.get('stem', '')
            preview = stem if len(stem) <= 60 else stem[:60] + '...'
            print(f"{index}. #{question.get('number', '?')} {preview}")

        choice = prompt('选择序号，或回车重新搜索: ')
        if not choice:
            continue
        if choice.lower() in STOP_WORDS:
            return None
        if choice.isdigit() and 1 <= int(choice) <= len(matches):
            return matches[int(choice) - 1]

        print('无效选择。')


def fill_answer_mode(questions: list[dict[str, Any]], data_path: Path) -> None:
    while True:
        question = choose_question_interactively(questions)
        if question is None:
            return

        clear_screen()
        print(render_question(question, show_answer=True))
        print()
        print('输入正确答案，支持 A/B/C/D 或直接输入选项文字。输入 q 返回搜索。')

        while True:
            user_answer = prompt('答案: ')
            if user_answer.lower() in STOP_WORDS:
                clear_screen()
                break

            resolved_answer = resolve_answer(question, user_answer)
            question['answer'] = resolved_answer
            question.setdefault('wrong_count', 0)
            save_questions(data_path, questions)
            clear_screen()
            print(render_question(question, show_answer=True))
            print(f'已保存答案: {resolved_answer}')
            print()
            break


def self_test_mode(questions: list[dict[str, Any]], data_path: Path) -> None:
    candidates = [question for question in questions if question.get('answer')]
    if not candidates:
        print('当前没有已录入答案的题目，先进入填正确答案模式。')
        return

    random.shuffle(candidates)
    index = 0
    while True:
        if index >= len(candidates):
            random.shuffle(candidates)
            index = 0

        question = candidates[index]
        index += 1

        clear_screen()
        print(render_question(question, show_answer=False))
        print()
        user_answer = prompt('你的答案(A/B/C/D，q 退出): ')
        if user_answer.lower() in STOP_WORDS:
            return

        resolved_answer = resolve_answer(question, user_answer)
        stored_answer = question.get('answer', '')
        is_correct = answers_match(question, stored_answer, resolved_answer)
        correct_answer = normalize_answer(question, stored_answer)

        if not is_correct:
            question['wrong_count'] = int(question.get('wrong_count', 0)) + 1
            save_questions(data_path, questions)

        clear_screen()
        print(render_question(question, show_answer=True))
        print(f'你的答案: {resolved_answer}')
        print(f'正确答案: {correct_answer}')
        print('结果: 正确' if is_correct else '结果: 错误')
        print('按回车继续，或输入 q 退出。')
        if prompt('') .lower() in STOP_WORDS:
            return


def main() -> None:
    parser = argparse.ArgumentParser(description='Practice question manager')
    parser.add_argument('--data', default=str(DEFAULT_DATA_PATH), help='JSON data file path')
    parser.add_argument(
        '--mode',
        choices=['fill', 'test'],
        help='fill: search and record answers; test: random self-test',
    )
    args = parser.parse_args()

    data_path = Path(args.data)
    questions = load_questions(data_path)

    mode = args.mode
    if not mode:
        clear_screen()
        print('请选择模式:')
        print('1. fill  录入正确答案')
        print('2. test  自测模式')
        choice = prompt('输入 1 或 2: ')
        mode = 'fill' if choice == '1' else 'test'

    if mode == 'fill':
        fill_answer_mode(questions, data_path)
    else:
        self_test_mode(questions, data_path)


if __name__ == '__main__':
    main()