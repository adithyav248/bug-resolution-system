# Multi-Agent Bug Resolution System (Gemini Edition)

This system uses a Multi-Agent architecture powered by Google Gemini to ingest bug reports and logs, execute code to dynamically reproduce the issue, and formulate a verified patch plan.

## Setup
1. Ensure your virtual environment is active.
2. Install dependencies: `pip install -r requirements.txt`
3. Export your Google API Key: `export GOOGLE_API_KEY="AIza..."`

## Execution
Run the system:
`python bug_analyzer.py`

## Traceability & Output
The agents log their decisions to the console. Once finished, check:
- `repro_script.py`: The runnable python script that proves the bug exists.
- `final_report.json`: Structured JSON containing the root cause and fix plan.