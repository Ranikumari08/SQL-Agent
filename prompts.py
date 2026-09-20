"""
Prompts + database registry for the NL -> SQL engine.

To add a new database: add one entry to DB_REGISTRY (path/connection info, description,
business rules, few-shot examples). Nothing else needs to change.
"""
from datetime import date

# --------------------------------------------------------------------------- dialect hints
DIALECT_HINTS = {
    "sqlite": """- Dates are stored as ISO text 'YYYY-MM-DD'. Use date(), strftime('%Y-%m', col), date('now'), date('now','-30 days').
- There is no ILIKE; use LOWER(col) LIKE '%text%'.
- String concatenation uses ||. There is no CONCAT().
- Integer / integer is integer division. Multiply by 100.0 or CAST(x AS REAL) before dividing.
- Window functions and CTEs (WITH) are supported. Use LIMIT (not TOP / FETCH FIRST).
- There is no DATEDIFF; use julianday(a) - julianday(b) for day differences.
- Age in years: CAST((julianday('now') - julianday(date_of_birth)) / 365.25 AS INTEGER).""",
    "postgresql": """- Use DATE_TRUNC, EXTRACT, CURRENT_DATE, INTERVAL arithmetic. Use ILIKE for case-insensitive match.
- Every non-aggregated SELECT column must appear in GROUP BY.
- Cast before dividing integers: x::numeric / y. Use LIMIT.""",
    "mysql": """- Use DATE_FORMAT, DATEDIFF, CURDATE(), DATE_SUB(CURDATE(), INTERVAL 30 DAY). Use CONCAT() for strings.
- Every non-aggregated SELECT column must appear in GROUP BY (ONLY_FULL_GROUP_BY). Use LIMIT.""",
}

# --------------------------------------------------------------------------- registry
DB_REGISTRY = {
    "ecommerce": {
        "path": "databases/ecommerce.db",
        "dialect": "sqlite",
        "description": "Online retail store: customers, product catalogue with categories, orders, order line items, "
                       "product reviews and product returns. Currency is INR.",
        "business_rules": [
            "Revenue / sales = SUM(order_items.quantity * order_items.unit_price) over orders whose status <> 'cancelled'.",
            "Profit = SUM(order_items.quantity * (order_items.unit_price - products.cost)) over non-cancelled orders.",
            "orders.total_amount already equals the sum of that order's line items; prefer it for order-level questions "
            "(e.g. average order value) and use order_items for product/category-level questions.",
            "categories is a two-level tree: parent categories (parent_category_id IS NULL, e.g. 'Electronics') and "
            "sub-categories. products.category_id always points to a SUB-category. For parent-level questions join "
            "categories twice (sub -> parent).",
            "'Active customers' = customers with at least one non-cancelled order in the period asked about.",
            "Return rate = returned order items / delivered order items. product_returns links via order_item_id.",
            "orders.status values: 'processing', 'shipped', 'delivered', 'cancelled'. loyalty_tier values: "
            "'Bronze', 'Silver', 'Gold', 'Platinum'.",
            "Customer full name = first_name || ' ' || last_name.",
        ],
        "examples": [
            {
                "question": "Who are the top 5 customers by total spend in 2025, and which city are they from?",
                "sql": """SELECT c.customer_id,
       c.first_name || ' ' || c.last_name AS customer_name,
       c.city,
       ROUND(SUM(oi.quantity * oi.unit_price), 2) AS total_spent
FROM customers c
JOIN orders o ON o.customer_id = c.customer_id
JOIN order_items oi ON oi.order_id = o.order_id
WHERE o.status <> 'cancelled'
  AND o.order_date >= '2025-01-01' AND o.order_date < '2026-01-01'
GROUP BY c.customer_id, customer_name, c.city
ORDER BY total_spent DESC
LIMIT 5;""",
            },
            {
                "question": "Show month-over-month revenue growth percentage for 2025.",
                "sql": """WITH monthly AS (
    SELECT strftime('%Y-%m', o.order_date) AS month,
           SUM(oi.quantity * oi.unit_price) AS revenue
    FROM orders o
    JOIN order_items oi ON oi.order_id = o.order_id
    WHERE o.status <> 'cancelled'
      AND o.order_date >= '2024-12-01' AND o.order_date < '2026-01-01'
    GROUP BY month
),
with_prev AS (
    SELECT month, revenue, LAG(revenue) OVER (ORDER BY month) AS prev_revenue
    FROM monthly
)
SELECT month,
       ROUND(revenue, 2) AS revenue,
       ROUND(100.0 * (revenue - prev_revenue) / NULLIF(prev_revenue, 0), 2) AS mom_growth_pct
FROM with_prev
WHERE month >= '2025-01'
ORDER BY month;""",
            },
            {
                "question": "What is the best-selling product in each parent category by units sold?",
                "sql": """WITH product_sales AS (
    SELECT p.product_id,
           p.name AS product_name,
           parent.name AS parent_category,
           SUM(oi.quantity) AS units_sold
    FROM products p
    JOIN categories sub ON sub.category_id = p.category_id
    JOIN categories parent ON parent.category_id = sub.parent_category_id
    JOIN order_items oi ON oi.product_id = p.product_id
    JOIN orders o ON o.order_id = oi.order_id
    WHERE o.status <> 'cancelled'
    GROUP BY p.product_id, p.name, parent.name
),
ranked AS (
    SELECT *, RANK() OVER (PARTITION BY parent_category ORDER BY units_sold DESC) AS rnk
    FROM product_sales
)
SELECT parent_category, product_name, units_sold
FROM ranked
WHERE rnk = 1
ORDER BY parent_category;""",
            },
            {
                "question": "Which customers signed up but never placed an order?",
                "sql": """SELECT c.customer_id, c.first_name || ' ' || c.last_name AS customer_name, c.signup_date
FROM customers c
WHERE NOT EXISTS (SELECT 1 FROM orders o WHERE o.customer_id = c.customer_id)
ORDER BY c.signup_date
LIMIT 100;""",
            },
        ],
    },
    "hr": {
        "path": "databases/hr.db",
        "dialect": "sqlite",
        "description": "Company HR system: departments, employees (with manager hierarchy), salary history, projects and "
                       "assignments, leave requests and yearly performance reviews. Salaries are annual, in INR.",
        "business_rules": [
            "Current headcount / 'employees' means status = 'Active' unless the question mentions resigned/attrition.",
            "employees.manager_id is a self-reference to employees.employee_id. The CEO has manager_id NULL.",
            "employees.salary is the CURRENT salary; salary_history has one row per raise (effective_date, salary).",
            "Attrition rate for a year = employees whose termination_date falls in that year / employees who were "
            "employed at any point in that year.",
            "Tenure in years = (end - hire_date) where end = termination_date for resigned staff, else today.",
            "performance_reviews.rating is 1 (poor) to 5 (outstanding); reviewer_id is the reviewing manager.",
            "leave_requests.status is 'Approved', 'Pending' or 'Rejected'. Days taken = julianday(end_date) - "
            "julianday(start_date) + 1 (inclusive). Count only 'Approved' leave as leave taken.",
            "project_assignments.allocation_pct is the % of the employee's time on that project. An employee's total "
            "allocation across Active projects should be <= 100.",
        ],
        "examples": [
            {
                "question": "Which active employees earn more than the average salary of their own department?",
                "sql": """SELECT e.employee_id,
       e.first_name || ' ' || e.last_name AS employee_name,
       d.name AS department,
       e.salary,
       ROUND(da.avg_salary, 2) AS dept_avg_salary
FROM employees e
JOIN departments d ON d.department_id = e.department_id
JOIN (SELECT department_id, AVG(salary) AS avg_salary
      FROM employees WHERE status = 'Active' GROUP BY department_id) da
  ON da.department_id = e.department_id
WHERE e.status = 'Active' AND e.salary > da.avg_salary
ORDER BY e.salary - da.avg_salary DESC
LIMIT 100;""",
            },
            {
                "question": "List managers with the number of active direct reports, for managers with more than 5.",
                "sql": """SELECT m.employee_id AS manager_id,
       m.first_name || ' ' || m.last_name AS manager_name,
       m.job_title,
       COUNT(e.employee_id) AS direct_reports
FROM employees m
JOIN employees e ON e.manager_id = m.employee_id AND e.status = 'Active'
GROUP BY m.employee_id, manager_name, m.job_title
HAVING COUNT(e.employee_id) > 5
ORDER BY direct_reports DESC;""",
            },
            {
                "question": "What was the attrition rate per department in 2024?",
                "sql": """SELECT d.name AS department,
       SUM(CASE WHEN e.termination_date >= '2024-01-01' AND e.termination_date < '2025-01-01' THEN 1 ELSE 0 END) AS leavers,
       COUNT(*) AS employed_in_2024,
       ROUND(100.0 * SUM(CASE WHEN e.termination_date >= '2024-01-01' AND e.termination_date < '2025-01-01' THEN 1 ELSE 0 END)
             / COUNT(*), 2) AS attrition_pct
FROM employees e
JOIN departments d ON d.department_id = e.department_id
WHERE e.hire_date < '2025-01-01'
  AND (e.termination_date IS NULL OR e.termination_date >= '2024-01-01')
GROUP BY d.name
ORDER BY attrition_pct DESC;""",
            },
        ],
    },
    "hospital": {
        "path": "databases/hospital.db",
        "dialect": "sqlite",
        "description": "Multi-branch hospital: doctors, patients, appointments, diagnoses (ICD codes), prescriptions, "
                       "medicines and billing. Currency is INR.",
        "business_rules": [
            "Only appointments with status = 'Completed' have diagnoses, prescriptions and a bill.",
            "appointments.status values: 'Scheduled' (future), 'Completed', 'Cancelled', 'No-Show'.",
            "No-show rate = No-Show appointments / all appointments whose date is in the past (exclude 'Scheduled').",
            "Outstanding balance = billing.total_amount - billing.paid_amount (only for payment_status <> 'Paid').",
            "Hospital revenue = SUM(billing.paid_amount) unless the question says 'billed' (then use total_amount).",
            "patients.insurance_provider is NULL for self-paying patients.",
            "Patient full name = first_name || ' ' || last_name. Doctor names already include 'Dr.'.",
            "A 'repeat / returning patient' has more than one Completed appointment.",
            "prescriptions.dosage is 'morning-afternoon-night' doses per day, e.g. '1-0-1'.",
        ],
        "examples": [
            {
                "question": "Which 5 doctors have the highest no-show percentage (min 30 past appointments)?",
                "sql": """SELECT d.name AS doctor_name,
       d.specialization,
       COUNT(*) AS past_appointments,
       SUM(CASE WHEN a.status = 'No-Show' THEN 1 ELSE 0 END) AS no_shows,
       ROUND(100.0 * SUM(CASE WHEN a.status = 'No-Show' THEN 1 ELSE 0 END) / COUNT(*), 2) AS no_show_pct
FROM doctors d
JOIN appointments a ON a.doctor_id = d.doctor_id
WHERE a.status <> 'Scheduled'
GROUP BY d.doctor_id, d.name, d.specialization
HAVING COUNT(*) >= 30
ORDER BY no_show_pct DESC
LIMIT 5;""",
            },
            {
                "question": "Total outstanding balance by insurance provider, with self-paying patients labelled.",
                "sql": """SELECT COALESCE(p.insurance_provider, 'Self-pay') AS insurance_provider,
       COUNT(*) AS unpaid_or_partial_bills,
       ROUND(SUM(b.total_amount - b.paid_amount), 2) AS outstanding_balance
FROM billing b
JOIN appointments a ON a.appointment_id = b.appointment_id
JOIN patients p ON p.patient_id = a.patient_id
WHERE b.payment_status <> 'Paid'
GROUP BY COALESCE(p.insurance_provider, 'Self-pay')
ORDER BY outstanding_balance DESC;""",
            },
            {
                "question": "Which medicine is prescribed most often for each severe diagnosis description?",
                "sql": """WITH counts AS (
    SELECT dg.description AS diagnosis,
           m.name AS medicine,
           COUNT(*) AS times_prescribed
    FROM diagnoses dg
    JOIN prescriptions pr ON pr.appointment_id = dg.appointment_id
    JOIN medicines m ON m.medicine_id = pr.medicine_id
    WHERE dg.severity = 'Severe'
    GROUP BY dg.description, m.name
),
ranked AS (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY diagnosis ORDER BY times_prescribed DESC, medicine) AS rn
    FROM counts
)
SELECT diagnosis, medicine, times_prescribed
FROM ranked
WHERE rn = 1
ORDER BY diagnosis;""",
            },
        ],
    },
}

# --------------------------------------------------------------------------- prompts
ROUTER_PROMPT = """You route user questions to the correct database.

Available databases:
{db_list}

Return ONLY JSON: {{"database": "<key>", "reason": "<short reason>"}}
If the question clearly cannot be answered by any database, use {{"database": "none", "reason": "..."}}.
If it mentions concepts from several databases, choose the one that holds the main entity being asked about."""


def build_router_prompt() -> str:
    lines = "\n".join(f'- "{k}": {v["description"]}' for k, v in DB_REGISTRY.items())
    return ROUTER_PROMPT.format(db_list=lines)


def _format_examples(examples) -> str:
    return "\n\n".join(f"Question: {e['question']}\nSQL:\n{e['sql']}" for e in examples)


def _format_history(history) -> str:
    if not history:
        return "(none)"
    return "\n".join(f"- Q: {q}\n  SQL: {' '.join(s.split())}" for q, s in history[-3:])


def build_system_prompt(db_key: str, schema_text: str, history=None) -> str:
    cfg = DB_REGISTRY[db_key]
    dialect = cfg["dialect"]
    rules = "\n".join(f"- {r}" for r in cfg["business_rules"])
    return f"""You are a senior data analyst and expert {dialect.upper()} query writer. You translate business questions \
into a single, correct, efficient, read-only SQL query for the database described below.

TODAY'S DATE: {date.today().isoformat()}  (use it to resolve "today", "this year", "last month", "last 30 days", etc.)

# DATABASE: {db_key}
{cfg["description"]}

# SCHEMA (authoritative - use ONLY these tables and columns)
{schema_text}

# BUSINESS DEFINITIONS (follow these exactly when the question uses these concepts)
{rules}

# {dialect.upper()} DIALECT NOTES
{DIALECT_HINTS[dialect]}

# HOW TO THINK (do this silently before writing SQL)
1. Identify: the entity being asked about, the metric(s), filters, time range, grouping level (grain), sorting and limit.
2. Choose the minimum set of tables and the join path using the foreign keys in the schema.
3. Watch the GRAIN. If you join two one-to-many tables (e.g. orders -> items AND orders -> payments) values get \
duplicated. Aggregate each branch in its own CTE/subquery first, then join the results.
4. Use CTEs (WITH) for multi-step logic. Use window functions for rankings, top-N-per-group, running totals, \
period-over-period change, percent of total, and moving averages.
   - Top-N per group: ROW_NUMBER() (unique) or RANK() (ties allowed) with PARTITION BY, then filter in an outer query.
   - Period-over-period: LAG()/LEAD() over the ordered period.
5. "Never / without / no ..." means an anti-join: NOT EXISTS (preferred) or LEFT JOIN ... WHERE right.key IS NULL.
6. "At least one / any" means EXISTS or a HAVING COUNT filter. "All / every" means compare counts or use NOT EXISTS.
7. Percentages and ratios: multiply by 100.0 first, guard the denominator with NULLIF(x, 0), ROUND to 2 decimals.
8. Filters on dates use half-open ranges (col >= start AND col < next_start); never wrap an indexed column in a function \
inside WHERE when a range works.
9. Apply WHERE (row filters) before GROUP BY, and HAVING only for filters on aggregates.
10. Text matching from the user is case-insensitive and partial unless they give an exact code/ID.

# OUTPUT RULES
- Generate exactly ONE statement, starting with SELECT or WITH. NEVER produce INSERT, UPDATE, DELETE, DROP, ALTER, \
CREATE, PRAGMA, ATTACH or any statement that changes data or schema. If asked to modify data, refuse via the JSON below.
- Never invent tables, columns, values or business rules. If the schema cannot answer the question, say so.
- Select only the columns needed, with clear snake_case aliases. Include a readable name next to any ID. Never SELECT *.
- Alias every aggregate and computed column. Qualify every column with its table alias when more than one table is used.
- ORDER BY whenever the question implies ranking or a sequence. For "top N" use LIMIT N. For open-ended listings that could \
return many rows add LIMIT 100. Do not add LIMIT to aggregations that are naturally small (e.g. one row per month).
- Ties: for "the top/best/highest" with a single expected answer, break ties deterministically with a secondary ORDER BY.
- If the question is genuinely ambiguous in a way that changes the result (e.g. "best" with no metric and no rule above \
defines it), pick the most reasonable interpretation, state it in "assumptions", and continue. Set needs_clarification=true \
ONLY when you cannot make a sensible assumption or the data does not exist.
- Use the follow-up context below to resolve pronouns like "them", "that", "those" or "the same for ...".

# EXAMPLES (style and correctness reference for this database)
{_format_examples(cfg["examples"])}

# RECENT CONVERSATION (for follow-up questions)
{_format_history(history)}

# RESPONSE FORMAT
Return ONLY a JSON object, no markdown fences, no prose outside JSON:
{{
  "interpretation": "one sentence restating what the user wants",
  "assumptions": ["any assumption you made, or empty list"],
  "sql": "the SQL query as a single string, or an empty string if it cannot be answered",
  "confidence": 0.0,
  "needs_clarification": false,
  "clarification_question": "only when needs_clarification is true or the request is refused, else empty string"
}}"""