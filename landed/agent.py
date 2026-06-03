"""
landed/agent.py
----------------
The heart of Landed: an agentic tool-use loop.

  question -> model writes SQL and calls run_sql -> we execute it on DuckDB
  -> rows (or the error) go back to the model -> it answers, or fixes its
  SQL and tries again.

The model never touches the database directly — it can only go through the
read-only run_sql tool in db.py. SQL errors are fed back as tool results so
the agent can self-correct.
"""

from datetime import date

from .db import get_schema, run_sql, format_result

SYSTEM = """You are Landed, a data analyst agent for a personal job-application pipeline stored in DuckDB.

Today's date: {today}

Database schema:
{schema}

Notes on the data:
- applications.status values: Applied, Screening, Interview, Take-home, Offer, Rejected, Ghosted, Withdrawn.
- "live" applications = status in (Applied, Screening, Interview, Take-home).
- events is the funnel trail per application (Applied, Recruiter Screen, Hiring Manager Call, Technical Interview, Take-home Submitted, Final / Onsite, Offer, Rejection).
- Salary columns are EUR per year.
- applications.channel is the apply method (Inbound, Cold Apply, Referral, Recruiter); applications.source is the specific platform (LinkedIn, Indeed, Internal Referral, ...). For "referral vs cold apply" questions, group by channel, NOT source.
- A "response" means any event OTHER THAN 'Applied'. Response rate = share of applications having at least one such event.
- You are speaking TO the pipeline's owner: answer in second person ("your response rate is..."), never first person.

How to work:
1. Answer every question by calling the run_sql tool — never guess numbers.
2. Write DuckDB SQL. Read-only: a single SELECT or WITH query per call.
3. Joining applications to events fans rows out — use COUNT(DISTINCT ...) where it matters.
4. If a query errors, read the error, fix the SQL, and call the tool again.
5. Final answer: key numbers first, then one or two lines of insight. Short.
6. If the question is ambiguous, pick the most reasonable reading and say the assumption in one clause.
7. Use CURRENT_DATE for relative time windows (e.g. 'last week', 'over 2 weeks ago') instead of hardcoding today's date."""

TOOLS = [{
    "name": "run_sql",
    "description": ("Run one read-only SQL query (DuckDB dialect) against the "
                    "job-application database and get the resulting rows back."),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "A single SELECT or WITH query in DuckDB SQL.",
            }
        },
        "required": ["query"],
    },
}]


def ask(question: str, con, llm, max_steps: int = 6) -> dict:
    """Run the agent loop.

    Returns {"answer": str, "sql": [queries], "results": [per-query result]}
    where each result is {"columns", "rows", "row_count"} or {"error": "..."}.
    """
    system = SYSTEM.format(schema=get_schema(con), today=date.today().isoformat())
    messages = [{"role": "user", "content": [{"type": "text", "text": question}]}]
    sql_log, result_log = [], []

    for _ in range(max_steps):
        resp = llm.chat(system=system, messages=messages, tools=TOOLS)
        messages.append({"role": "assistant", "content": resp["blocks"]})

        if resp["stop_reason"] != "tool_use":
            answer = "".join(b["text"] for b in resp["blocks"]
                             if b["type"] == "text").strip()
            return {"answer": answer or "(no answer)",
                    "sql": sql_log, "results": result_log}

        # Execute every tool call in this turn; errors go back as results
        results = []
        for b in resp["blocks"]:
            if b["type"] == "tool_use" and b["name"] == "run_sql":
                query = (b["input"] or {}).get("query", "")
                sql_log.append(query)
                try:
                    res = run_sql(con, query)
                    result_log.append(res)
                    payload = format_result(res, max_show=50)
                except Exception as e:
                    result_log.append({"error": str(e)})
                    payload = f"SQL ERROR: {e}"
                results.append({"type": "tool_result",
                                "tool_use_id": b["id"],
                                "content": payload})
        messages.append({"role": "user", "content": results})

    return {"answer": "(stopped: agent hit the step limit)",
            "sql": sql_log, "results": result_log}
