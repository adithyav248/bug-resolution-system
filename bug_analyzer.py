import os
import sys

# --- LOAD ENVIRONMENT VARIABLES AUTOMATICALLY ---
from dotenv import load_dotenv
load_dotenv()

# Check for API key before anything else loads
if not os.environ.get("GOOGLE_API_KEY"):
    print("\n❌ Error: GOOGLE_API_KEY is not set.")
    print("Please create a .env file in this folder and add: GOOGLE_API_KEY=your_api_key_here")
    sys.exit(1)
# ----------------------------------------------

import json
import subprocess
from typing import TypedDict, List, Dict, Any
from pydantic import BaseModel, Field

# LangChain / LangGraph / Google Gemini imports
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import StateGraph, END

# ==========================================
# 1. ENVIRONMENT & MINI-REPO INITIALIZATION
# ==========================================

def initialize_mini_repo():
    """Creates a sample buggy repository, bug report, and logs for the agents to process."""
    os.makedirs("mini_repo", exist_ok=True)
    
    processor_code = """
def process_refund(transaction):
    amount = transaction.get('amount', 0)
    exchange_rate = transaction.get('exchange_rate')
    
    # BUG: If exchange_rate is explicitly 0, this causes a ZeroDivisionError
    if exchange_rate is not None:
        base_amount = amount / exchange_rate
    else:
        base_amount = amount
        
    # Standard refund fee is 2%
    return base_amount * 0.98
"""
    bug_report = """# Bug Report: Crash on zero exchange rate refunds
**Title**: Batch processor crashes on failed transactions
**Symptoms**: The batch refund processor crashes completely when processing certain failed transactions.
**Expected Behavior**: It should process the refund gracefully or reject it without crashing the entire batch.
**Actual Behavior**: System exits with an unhandled exception.
**Environment**: Python 3.10
**Hints**: We recently introduced a database change where `exchange_rate` is explicitly set to `0` instead of `null` for non-foreign transactions."""

    logs = """[INFO] 2023-11-01 10:00:00 - Started batch refund job
[DEBUG] 2023-11-01 10:00:01 - Processed tx_001 successfully.
[WARN] 2023-11-01 10:00:02 - Database connection latency high.
[INFO] 2023-11-01 10:00:03 - Processing tx_002...
[ERROR] 2023-11-01 10:00:03 - Fatal error in refund processor.
Traceback (most recent call last):
  File "batch_runner.py", line 42, in <module>
    process_refund({'amount': 100, 'exchange_rate': 0})
  File "/app/mini_repo/processor.py", line 7, in process_refund
    base_amount = amount / exchange_rate
ZeroDivisionError: division by zero
[INFO] 2023-11-01 10:00:04 - Batch job failed."""

    with open("mini_repo/processor.py", "w") as f: f.write(processor_code.strip())
    with open("mini_repo/bug_report.md", "w") as f: f.write(bug_report.strip())
    with open("mini_repo/logs.txt", "w") as f: f.write(logs.strip())
    
    return {
        "processor.py": processor_code.strip(),
        "bug_report.md": bug_report.strip(),
        "logs.txt": logs.strip()
    }

# ==========================================
# 2. STATE DEFINITION & PYDANTIC MODELS
# ==========================================

class SystemState(TypedDict):
    repo_files: Dict[str, str]
    iteration: int
    
    # Agent Outputs
    triage_summary: dict
    log_evidence: dict
    repro_script: str
    repro_output: str
    repro_success: bool
    fix_plan: dict
    reviewer_feedback: dict
    final_output: dict

# Structured Outputs for LLMs
class TriageOutput(BaseModel):
    symptoms: str
    expected_behavior: str
    actual_behavior: str
    environment: str
    prioritized_hypotheses: List[str]

class LogAnalysisOutput(BaseModel):
    stack_traces: List[str]
    error_signatures: List[str]
    anomalies: List[str]

class ReproOutput(BaseModel):
    repro_script_code: str = Field(description="Minimal python script to reproduce the bug. Do not include markdown blocks like ```python, just raw code.")
    rationale: str

class FixPlanOutput(BaseModel):
    root_cause_hypothesis: str
    confidence: str
    patch_plan: str
    validation_plan: str

class ReviewerOutput(BaseModel):
    is_repro_minimal: bool
    is_fix_safe: bool
    feedback: str

# ==========================================
# 3. AGENT NODES
# ==========================================

# Use Gemini 1.5 Pro for highly capable coding and reasoning
llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0.1)

def print_trace(agent_name, message):
    print(f"\n\033[94m[{agent_name}]\033[0m: {message}")

def triage_agent(state: SystemState):
    print_trace("Triage Agent", "Analyzing bug report...")
    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are an expert triage engineer. Extract key details from the bug report."),
        ("user", "Bug Report:\n{bug_report}")
    ])
    chain = prompt | llm.with_structured_output(TriageOutput)
    res = chain.invoke({"bug_report": state['repo_files']['bug_report.md']})
    
    return {"triage_summary": res.model_dump()}

def log_analyst_agent(state: SystemState):
    print_trace("Log Analyst", "Scanning logs for stack traces and anomalies...")
    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are a log analysis expert. Find stack traces and error signatures. Ignore standard INFO noise."),
        ("user", "Logs:\n{logs}")
    ])
    chain = prompt | llm.with_structured_output(LogAnalysisOutput)
    res = chain.invoke({"logs": state['repo_files']['logs.txt']})
    
    return {"log_evidence": res.model_dump()}

def reproduction_agent(state: SystemState):
    print_trace("Reproduction Agent", "Constructing minimal repro script...")
    prompt = ChatPromptTemplate.from_messages([
        ("system", """You are a Reproduction Agent. Write a minimal Python script to reproduce the bug described.
Your script should import the buggy function from the repository and trigger the error.
Repository Files available:
{repo_files}

Triage Info: {triage}
Log Evidence: {logs}

Return ONLY valid python code in the 'repro_script_code' field. DO NOT wrap it in markdown code blocks."""),
        ("user", "Generate the repro script.")
    ])
    
    repo_files_str = "\n".join([f"--- {k} ---\n{v}" for k,v in state['repo_files'].items()])
    chain = prompt | llm.with_structured_output(ReproOutput)
    
    res = chain.invoke({
        "repo_files": repo_files_str,
        "triage": state['triage_summary'],
        "logs": state['log_evidence']
    })
    
    # Robust Markdown Stripping in case Gemini wraps the python code
    script_code = res.repro_script_code.strip()
    if script_code.startswith("```"):
        lines = script_code.split('\n')
        if lines[0].startswith("```"): lines = lines[1:]
        if lines[-1].startswith("```"): lines = lines[:-1]
        script_code = "\n".join(lines)
    
    # TOOL EXECUTION: Write and execute the script
    script_path = "repro_script.py"
    with open(script_path, "w") as f:
        f.write("import sys\nsys.path.append('./mini_repo')\n") # Ensure import works
        f.write(script_code)
    
    print_trace("Reproduction Agent", f"Executing repro script using subprocess: {script_path}")
    process = subprocess.run(["python", script_path], capture_output=True, text=True)
    
    output = f"STDOUT:\n{process.stdout}\nSTDERR:\n{process.stderr}"
    
    # Check if we successfully reproduced an error (ZeroDivisionError)
    success = process.returncode != 0 and "ZeroDivisionError" in process.stderr
    print_trace("Reproduction Agent", f"Repro Success: {success}")
    
    return {
        "repro_script": script_code,
        "repro_output": output,
        "repro_success": success
    }

def fix_planner_agent(state: SystemState):
    print_trace("Fix Planner Agent", "Proposing root-cause and patch plan based on repro results...")
    prompt = ChatPromptTemplate.from_messages([
        ("system", """You are a Fix Planner. Based on the triage, logs, and reproduction output, propose a root cause and a patch plan.
Triage: {triage}
Repro Success: {repro_success}
Repro Output: {repro_output}
Buggy Code:
{code}
"""),
        ("user", "Propose the fix plan.")
    ])
    chain = prompt | llm.with_structured_output(FixPlanOutput)
    res = chain.invoke({
        "triage": state["triage_summary"],
        "repro_success": state["repro_success"],
        "repro_output": state["repro_output"],
        "code": state["repo_files"]["processor.py"]
    })
    
    return {"fix_plan": res.model_dump()}

def reviewer_agent(state: SystemState):
    print_trace("Reviewer Agent", "Critiquing the reproduction script and patch plan...")
    prompt = ChatPromptTemplate.from_messages([
        ("system", """You are a Principal Engineer reviewing a bug fix. 
Evaluate:
1. Is the repro script minimal and does it accurately reflect the bug report?
2. Is the fix plan safe and correct?

Repro Script:
{repro}

Fix Plan:
{fix_plan}
"""),
        ("user", "Provide your review.")
    ])
    chain = prompt | llm.with_structured_output(ReviewerOutput)
    res = chain.invoke({
        "repro": state["repro_script"],
        "fix_plan": state["fix_plan"]
    })
    
    iteration = state.get("iteration", 0) + 1
    print_trace("Reviewer Agent", f"Feedback: {res.feedback}")
    
    return {
        "reviewer_feedback": res.model_dump(),
        "iteration": iteration
    }

def output_formatter(state: SystemState):
    print_trace("System", "Formatting final JSON output...")
    final_report = {
        "bug_summary": state["triage_summary"],
        "evidence": state["log_evidence"],
        "repro_details": {
            "artifact_path": "repro_script.py",
            "script_code": state["repro_script"],
            "execution_output": state["repro_output"],
            "reproduced_successfully": state["repro_success"]
        },
        "resolution": state["fix_plan"],
        "reviewer_notes": state["reviewer_feedback"],
        "open_questions": "Are there other upstream systems injecting `exchange_rate: 0`?"
    }
    
    with open("final_report.json", "w") as f:
        json.dump(final_report, f, indent=4)
        
    return {"final_output": final_report}

# ==========================================
# 4. ROUTING & GRAPH DEFINITION
# ==========================================

def reviewer_router(state: SystemState):
    feedback = state["reviewer_feedback"]
    iteration = state["iteration"]
    
    # If the reviewer approved it or we hit max retries, finish.
    if iteration >= 2 or (feedback["is_repro_minimal"] and feedback["is_fix_safe"]):
        print_trace("Router", "Plans approved or max retries reached. Routing to Output.")
        return "Output"
    else:
        print_trace("Router", "Revisions requested. Routing back to Reproduction.")
        return "Reproduction"

def build_graph():
    workflow = StateGraph(SystemState)
    
    workflow.add_node("Triage", triage_agent)
    workflow.add_node("LogAnalysis", log_analyst_agent)
    workflow.add_node("Reproduction", reproduction_agent)
    workflow.add_node("FixPlanner", fix_planner_agent)
    workflow.add_node("Reviewer", reviewer_agent)
    workflow.add_node("Output", output_formatter)
    
    workflow.set_entry_point("Triage")
    workflow.add_edge("Triage", "LogAnalysis")
    workflow.add_edge("LogAnalysis", "Reproduction")
    workflow.add_edge("Reproduction", "FixPlanner")
    workflow.add_edge("FixPlanner", "Reviewer")
    
    workflow.add_conditional_edges(
        "Reviewer",
        reviewer_router,
        {
            "Output": "Output",
            "Reproduction": "Reproduction"
        }
    )
    workflow.add_edge("Output", END)
    
    return workflow.compile()

# ==========================================
# 5. EXECUTION ENTRY POINT
# ==========================================

if __name__ == "__main__":
    print("Initializing mini-repo...")
    repo_files = initialize_mini_repo()
    
    initial_state = {
        "repo_files": repo_files,
        "iteration": 0
    }
    
    app = build_graph()
    
    print("\nStarting Multi-Agent Workflow...\n" + "="*40)
    final_state = app.invoke(initial_state)
    print("="*40)
    
    print("\n✅ Workflow complete. Artifacts generated:")
    print(" - \033[92mrepro_script.py\033[0m (Runnable minimal reproduction)")
    print(" - \033[92mfinal_report.json\033[0m (Structured Root Cause & Patch Plan)")