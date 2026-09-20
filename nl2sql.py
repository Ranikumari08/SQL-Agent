import json
import os
import random
import re
import sqlite3
import time
from functools import lru_cache

from dotenv import load_dotenv
from google import genai
from google.genai import errors, types

from prompts import DB_REGISTRY, build_router_prompt, build_system_prompt

load_dotenv()  # read GEMINI_API_KEY from the .env file next to this script
if not (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")):
    raise SystemExit("GEMINI_API_KEY not found. Create a file named .env next to nl2sql.py containing:\n"
                     "GEMINI_API_KEY=your-key")

# Override with GEMINI_MODEL in .env if Google retires this model or you want a bigger one for harder questions.
MODEL = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")
MAX_ROWS = 200

# Transient Google-side errors are retried automatically with exponential backoff (2s, 4s, 8s, ...).
RETRYABLE_CODES = {429, 500, 502, 503, 504}
MAX_API_RETRIES = int(os.getenv("GEMINI_MAX_RETRIES", "5"))
# Optional: comma-separated backup models tried if the main one stays overloaded, e.g. in .env:
#   GEMINI_FALLBACK_MODELS=gemini-3.6-flash-lite
FALLBACK_MODELS = [m.strip() for m in os.getenv("GEMINI_FALLBACK_MODELS", "").split(",") if m.strip()]

client = genai.Client()  # reads GEMINI_API_KEY (or GOOGLE_API_KEY) from the environment


# --------------------------------------------------------------------------- DB access
# If you move to PostgreSQL/MySQL, only get_connection(), get_schema_text() and run_query() need to change.
def get_connection(db_key: str) -> sqlite3.Connection:
    path = DB_REGISTRY[db_key]["path"]
    # mode=ro -> the database engine itself refuses writes, even if validation were bypassed.
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


@lru_cache(maxsize=None)
def get_schema_text(db_key: str, sample_rows: int = 2) -> str:
    """CREATE TABLE statements + a few sample rows per table (samples show real value formats)."""
    conn = get_connection(db_key)
    parts = []
    tables = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
    for t in tables:
        ddl = conn.execute("SELECT sql FROM sqlite_master WHERE name = ?", (t,)).fetchone()[0]
        cur = conn.execute(f'SELECT * FROM "{t}" LIMIT {sample_rows}')
        cols = [d[0] for d in cur.description]
        rows = cur.fetchall()
        sample = "\n".join("  " + json.dumps(dict(zip(cols, r)), default=str) for r in rows)
        parts.append(f"{ddl.strip()};\n-- sample rows from {t}:\n{sample}")
    conn.close()
    return "\n\n".join(parts)


FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|alter|create|replace|truncate|attach|detach|pragma|vacuum|reindex)\b", re.I)


def validate_sql(sql: str) -> str:
    """Cheap safety net; the real protection is the read-only connection."""
    s = sql.strip().rstrip(";").strip()
    if not re.match(r"^(select|with)\b", s, re.I):
        raise ValueError("Only SELECT / WITH queries are allowed.")
    if ";" in s:
        raise ValueError("Multiple statements are not allowed.")
    if FORBIDDEN.search(s):
        raise ValueError("Query contains a forbidden keyword.")
    return s


def run_query(db_key: str, sql: str):
    conn = get_connection(db_key)
    try:
        cur = conn.execute(sql)
        cols = [d[0] for d in cur.description]
        rows = cur.fetchmany(MAX_ROWS)
        return cols, rows
    finally:
        conn.close()


# --------------------------------------------------------------------------- Gemini calls
def _generate_with_retry(model: str, system_prompt: str, user_prompt: str):
    """One model, several attempts. Retries only temporary errors (overload / rate limit / 5xx)."""
    for attempt in range(MAX_API_RETRIES):
        try:
            return client.models.generate_content(
                model=model,
                contents=user_prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    temperature=0.0,                       # deterministic SQL
                    response_mime_type="application/json",  # forces valid JSON output
                ),
            )
        except errors.APIError as e:
            if e.code not in RETRYABLE_CODES or attempt == MAX_API_RETRIES - 1:
                raise
            wait = min(2 ** (attempt + 1), 30) + random.random()
            print(f"  [Gemini busy ({e.code}) - retrying in {wait:.0f}s, attempt {attempt + 2}/{MAX_API_RETRIES}]")
            time.sleep(wait)


def call_gemini(system_prompt: str, user_prompt: str) -> dict:
    last_error = None
    for model in [MODEL] + FALLBACK_MODELS:
        try:
            resp = _generate_with_retry(model, system_prompt, user_prompt)
            break
        except errors.APIError as e:
            if e.code not in RETRYABLE_CODES:
                raise  # bad key / bad model name / bad request: retrying or switching model won't help
            last_error = e
            print(f"  [Model {model} still unavailable]")
    else:
        raise last_error
    text = (resp.text or "").strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.M).strip()  # defensive: strip fences if any
    return json.loads(text)


def route_database(question: str):
    if len(DB_REGISTRY) == 1:
        return next(iter(DB_REGISTRY))
    out = call_gemini(build_router_prompt(), f"Question: {question}")
    key = out.get("database")
    return key if key in DB_REGISTRY else None


# --------------------------------------------------------------------------- main entry point
def ask(question: str, db_key: str = None, history=None, max_retries: int = 2) -> dict:
    db_key = db_key or route_database(question)
    if db_key is None:
        return {"status": "no_database",
                "message": "That question doesn't match any connected database.",
                "available": list(DB_REGISTRY)}

    system_prompt = build_system_prompt(db_key, get_schema_text(db_key), history)
    last_sql, last_error = None, None

    for attempt in range(1, max_retries + 2):
        user_prompt = f"Question: {question}"
        if last_error:
            user_prompt += (f"\n\nYour previous SQL failed.\nSQL:\n{last_sql}\nError: {last_error}\n"
                            "Diagnose the cause, fix it, and return the corrected JSON.")
        out = call_gemini(system_prompt, user_prompt)

        if out.get("needs_clarification") or not out.get("sql"):
            return {"status": "clarification", "database": db_key,
                    "message": out.get("clarification_question") or "Could not build a query.",
                    "interpretation": out.get("interpretation", "")}
        try:
            sql = validate_sql(out["sql"])
            columns, rows = run_query(db_key, sql)
            return {"status": "ok", "database": db_key, "sql": sql, "columns": columns, "rows": rows,
                    "interpretation": out.get("interpretation", ""), "assumptions": out.get("assumptions", []),
                    "confidence": out.get("confidence"), "attempts": attempt,
                    "truncated": len(rows) == MAX_ROWS}
        except Exception as e:  # SQL error, validation error -> feed back and retry
            last_sql, last_error = out.get("sql"), str(e)

    return {"status": "error", "database": db_key, "sql": last_sql, "error": last_error}


# --------------------------------------------------------------------------- CLI
def print_table(columns, rows, limit=25):
    if not rows:
        print("(no rows)")
        return
    shown = rows[:limit]
    widths = [min(max(len(str(c)), *(len(str(r[i])) for r in shown)), 40) for i, c in enumerate(columns)]
    print(" | ".join(str(c).ljust(w) for c, w in zip(columns, widths)))
    print("-+-".join("-" * w for w in widths))
    for r in shown:
        print(" | ".join(str(v)[:40].ljust(w) for v, w in zip(r, widths)))
    if len(rows) > limit:
        print(f"... {len(rows) - limit} more rows not shown")


if __name__ == "__main__":
    print("Databases:", ", ".join(DB_REGISTRY))
    print("Commands: /db <name> to pin a database, /db auto to route automatically, exit to quit.\n")
    pinned, history = None, []
    while True:
        q = input("Question> ").strip()
        if not q:
            continue
        if q.lower() in {"exit", "quit"}:
            break
        if q.startswith("/db"):
            arg = q[3:].strip()
            pinned = None if arg in {"", "auto"} else (arg if arg in DB_REGISTRY else pinned)
            print("Pinned database:", pinned or "auto-route")
            continue

        try:
            result = ask(q, db_key=pinned, history=history)
        except errors.APIError as e:
            if e.code in RETRYABLE_CODES:
                print("\nGemini is temporarily overloaded or rate-limited. Wait a minute and ask again.\n")
            else:
                print(f"\nGemini API problem ({e.code}): {e.message}\n"
                      "Check GEMINI_API_KEY and GEMINI_MODEL in your .env file.\n")
            continue
        except Exception as e:
            print(f"\nUnexpected error: {e}\n")
            continue
        if result["status"] == "ok":
            print(f"\n[{result['database']}] {result['interpretation']}")
            for a in result["assumptions"]:
                print("  assumption:", a)
            print("\nSQL:\n" + result["sql"] + "\n")
            print_table(result["columns"], result["rows"])
            history.append((q, result["sql"]))
        else:
            print("\n", result.get("message") or result.get("error"), "\n")