# OCR Practice Manager

This workspace contains a small question bank pipeline:

- `web_extract.py` extracts structured questions from `problems src/practice.html`
- `practice_manager.py` manages the generated `practice_questions.json`

## Files

- `practice_questions.json`: structured question data
- `practice_manager.py`: interactive terminal tool for recording answers and self-testing
- `web_extract.py`: HTML extractor that builds the JSON file from the exported practice page

## Requirements

Create and use the project virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

## Regenerate the question bank

If you update the HTML export, rebuild the JSON with:

```bash
python3 web_extract.py
```

This reads `problems src/practice.html` by default and writes `practice_questions.json`.

If you want to extract from another HTML export, pass the path explicitly:

```bash
python3 web_extract.py "problems src/simulated self-test 1.html" -o practice_questions.json
```

The same command works with other exports, such as `problems src/practice.html`.

## Practice Manager

Run the interactive manager from the project root:

```bash
python3 practice_manager.py
```

You can also pass a mode explicitly:

```bash
python3 practice_manager.py --mode fill
python3 practice_manager.py --mode test
```

### Mode 1: Fill Answers

Use this mode to search for a question, select it, and store the correct answer in `practice_questions.json`.

Workflow:

1. Search by keyword or question number.
2. Pick one result from the match list.
3. Enter the correct answer.
4. The script saves it into the JSON file.

It accepts either:

- `A`, `B`, `C`, `D`
- the option text itself, for example `刘伯承、邓小平`

### Mode 2: Self-Test

Use this mode to practice questions that already have an answer saved.

Behavior:

- The script randomly shows one question at a time.
- You type your answer.
- It compares your input against the saved answer.
- Wrong attempts increment `wrong_count`.
- Questions that are answered correctly several times in a row are marked as remembered and appear less often later.

## Stored Fields

Each question in `practice_questions.json` includes:

- `number`: question number
- `type`: question type
- `stem`: question stem
- `options`: multiple-choice options
- `answer`: saved correct answer
- `wrong_count`: how many times you got it wrong in self-test
- `correct_streak`: consecutive correct answers
- `remembered`: whether the question has been marked as remembered

## Tips

- Use `q`, `quit`, `exit`, or `back` to leave a prompt.
- If you want to start over, edit `practice_questions.json` and clear the stored answer/state fields for selected questions.
- The self-test mode keeps remembered questions in rotation, but reduces how often they appear.
