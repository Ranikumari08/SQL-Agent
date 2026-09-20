#!/usr/bin/env python3
"""
Creates three SQLite databases with realistic, relational sample data:

  databases/ecommerce.db  - customers, categories, products, orders, order_items, reviews, product_returns
  databases/hr.db         - departments, employees, salary_history, projects, project_assignments,
                            leave_requests, performance_reviews
  databases/hospital.db   - doctors, patients, appointments, diagnoses, medicines, prescriptions, billing

Run:  python seed_databases.py
Data is deterministic (fixed random seed) so results are reproducible.
Only the standard library is needed.
"""
import os
import random
import sqlite3
from datetime import date, timedelta
from itertools import accumulate

random.seed(42)
OUT_DIR = "databases"
TODAY = date.today()

FIRST_NAMES = ["Aarav", "Vivaan", "Aditya", "Arjun", "Sai", "Reyansh", "Krishna", "Ishaan", "Rohan", "Karthik",
               "Ananya", "Diya", "Isha", "Kavya", "Meera", "Priya", "Riya", "Saanvi", "Sneha", "Tanvi",
               "Neha", "Pooja", "Rahul", "Amit", "Vikram", "Deepika", "Suresh", "Lakshmi", "Manoj", "Nisha"]
LAST_NAMES = ["Sharma", "Verma", "Iyer", "Reddy", "Nair", "Patel", "Gupta", "Singh", "Kumar", "Das",
              "Rao", "Mehta", "Joshi", "Menon", "Chopra", "Bose", "Kulkarni", "Shetty", "Pillai", "Naidu"]
CITIES = [("Bengaluru", "Karnataka"), ("Mumbai", "Maharashtra"), ("Delhi", "Delhi"), ("Chennai", "Tamil Nadu"),
          ("Hyderabad", "Telangana"), ("Pune", "Maharashtra"), ("Kolkata", "West Bengal"),
          ("Ahmedabad", "Gujarat"), ("Jaipur", "Rajasthan"), ("Kochi", "Kerala"),
          ("Lucknow", "Uttar Pradesh"), ("Chandigarh", "Chandigarh")]


# ----------------------------------------------------------------------------- helpers
def rand_date(start: date, end: date) -> date:
    if end < start:
        return start
    return start + timedelta(days=random.randint(0, (end - start).days))


def person():
    return random.choice(FIRST_NAMES), random.choice(LAST_NAMES)


def weighted(pairs):
    items, weights = zip(*pairs)
    return random.choices(items, weights)[0]


def make_db(name: str, schema: str) -> sqlite3.Connection:
    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, f"{name}.db")
    if os.path.exists(path):
        os.remove(path)
    conn = sqlite3.connect(path)
    conn.executescript(schema)
    return conn


def insert(conn, table, rows):
    if rows:
        placeholders = ",".join("?" * len(rows[0]))
        conn.executemany(f"INSERT INTO {table} VALUES ({placeholders})", rows)


# ----------------------------------------------------------------------------- ECOMMERCE
ECOM_SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE categories (
    category_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    parent_category_id INTEGER REFERENCES categories(category_id)
);
CREATE TABLE customers (
    customer_id INTEGER PRIMARY KEY,
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    city TEXT,
    state TEXT,
    signup_date TEXT NOT NULL,
    loyalty_tier TEXT NOT NULL CHECK (loyalty_tier IN ('Bronze','Silver','Gold','Platinum'))
);
CREATE TABLE products (
    product_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    category_id INTEGER NOT NULL REFERENCES categories(category_id),
    brand TEXT NOT NULL,
    price REAL NOT NULL,
    cost REAL NOT NULL,
    stock_quantity INTEGER NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE orders (
    order_id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL REFERENCES customers(customer_id),
    order_date TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('processing','shipped','delivered','cancelled')),
    payment_method TEXT NOT NULL,
    shipping_city TEXT,
    total_amount REAL NOT NULL
);
CREATE TABLE order_items (
    order_item_id INTEGER PRIMARY KEY,
    order_id INTEGER NOT NULL REFERENCES orders(order_id),
    product_id INTEGER NOT NULL REFERENCES products(product_id),
    quantity INTEGER NOT NULL,
    unit_price REAL NOT NULL
);
CREATE TABLE reviews (
    review_id INTEGER PRIMARY KEY,
    product_id INTEGER NOT NULL REFERENCES products(product_id),
    customer_id INTEGER NOT NULL REFERENCES customers(customer_id),
    rating INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5),
    review_date TEXT NOT NULL,
    comment TEXT
);
CREATE TABLE product_returns (
    return_id INTEGER PRIMARY KEY,
    order_item_id INTEGER NOT NULL REFERENCES order_items(order_item_id),
    return_date TEXT NOT NULL,
    reason TEXT NOT NULL,
    refund_amount REAL NOT NULL
);
CREATE INDEX idx_orders_customer ON orders(customer_id);
CREATE INDEX idx_orders_date ON orders(order_date);
CREATE INDEX idx_items_order ON order_items(order_id);
CREATE INDEX idx_items_product ON order_items(product_id);
"""


def seed_ecommerce(n_customers=800, n_orders=6000):
    conn = make_db("ecommerce", ECOM_SCHEMA)

    # (singular name, min price, max price) in INR
    catalog = {
        "Electronics": {"Smartphones": ("Smartphone", 12000, 90000), "Laptops": ("Laptop", 30000, 150000),
                        "Headphones": ("Headphones", 800, 25000)},
        "Clothing": {"T-Shirts": ("T-Shirt", 300, 1500), "Jeans": ("Jeans", 900, 3500),
                     "Jackets": ("Jacket", 1500, 8000)},
        "Home & Kitchen": {"Cookware": ("Cookware Set", 500, 6000), "Vacuum Cleaners": ("Vacuum Cleaner", 3000, 25000),
                           "Bedding": ("Bedding Set", 700, 7000)},
        "Books": {"Fiction": ("Novel", 200, 900), "Technology": ("Tech Book", 400, 3500),
                  "Self-Help": ("Self-Help Book", 250, 1200)},
        "Sports": {"Cricket": ("Cricket Kit", 500, 15000), "Yoga": ("Yoga Mat", 400, 4000),
                   "Fitness Equipment": ("Fitness Equipment", 1000, 40000)},
    }
    brands = ["Aurora", "Zenith", "Nimbus", "Vertex", "Lumina", "Orbit", "Kestrel", "Solace", "Ember", "Atlas"]
    series = ["Pro", "Lite", "Max", "Plus", "Classic", "Elite"]

    categories, products, cid, pid = [], [], 0, 0
    for parent, subs in catalog.items():
        cid += 1
        parent_id = cid
        categories.append((parent_id, parent, None))
        for sub, (singular, lo, hi) in subs.items():
            cid += 1
            categories.append((cid, sub, parent_id))
            for _ in range(random.randint(8, 12)):
                pid += 1
                brand = random.choice(brands)
                price = float(round(random.uniform(lo, hi), -1))
                cost = round(price * random.uniform(0.55, 0.8), 2)
                name = f"{brand} {singular} {random.choice(series)} {random.randint(100, 999)}"
                products.append((pid, name, cid, brand, price, cost, random.randint(0, 500),
                                 1 if random.random() < 0.92 else 0))
    insert(conn, "categories", categories)
    insert(conn, "products", products)
    price_of = {p[0]: p[4] for p in products}
    product_ids = list(price_of)

    customers, signup, city_of = [], {}, {}
    for i in range(1, n_customers + 1):
        fn, ln = person()
        city, state = random.choice(CITIES)
        sd = rand_date(date(2022, 1, 1), TODAY - timedelta(days=30))
        tier = weighted([("Bronze", 55), ("Silver", 25), ("Gold", 15), ("Platinum", 5)])
        customers.append((i, fn, ln, f"{fn}.{ln}{i}@example.com".lower(), city, state, sd.isoformat(), tier))
        signup[i], city_of[i] = sd, city
    insert(conn, "customers", customers)

    # Heavy-tailed weights -> a few customers order a lot (realistic for "top customers" queries)
    cum_weights = list(accumulate(random.paretovariate(1.5) for _ in range(n_customers)))
    cust_ids = list(range(1, n_customers + 1))

    orders, items, delivered_items, oi_id = [], [], [], 0
    for oid in range(1, n_orders + 1):
        cust = random.choices(cust_ids, cum_weights=cum_weights)[0]
        odate = rand_date(signup[cust], TODAY)
        age = (TODAY - odate).days
        if age < 3:
            status = "processing"
        elif age < 7:
            status = random.choice(["processing", "shipped"])
        else:
            status = weighted([("delivered", 92), ("cancelled", 8)])
        pay = weighted([("UPI", 45), ("Credit Card", 25), ("Debit Card", 15), ("Net Banking", 8),
                        ("Cash on Delivery", 7)])
        ship_city = city_of[cust] if random.random() < 0.85 else random.choice(CITIES)[0]
        total = 0.0
        for p in random.sample(product_ids, random.choices([1, 2, 3, 4], [50, 30, 15, 5])[0]):
            oi_id += 1
            qty = random.choices([1, 2, 3], [75, 18, 7])[0]
            unit = round(price_of[p] * random.uniform(0.9, 1.0), 2)
            total += qty * unit
            items.append((oi_id, oid, p, qty, unit))
            if status == "delivered":
                delivered_items.append((oi_id, oid, p, cust, odate, qty, unit))
        orders.append((oid, cust, odate.isoformat(), status, pay, ship_city, round(total, 2)))
    insert(conn, "orders", orders)
    insert(conn, "order_items", items)

    returns, reviews, seen = [], [], set()
    reasons = [("Defective product", 35), ("Wrong item received", 15), ("Not as described", 25),
               ("Size/fit issue", 15), ("Changed mind", 10)]
    comments = {1: ["Terrible quality", "Stopped working quickly", "Not worth the money"],
                2: ["Below expectations", "Average at best", "Had some issues"],
                3: ["It's okay", "Decent for the price", "Does the job"],
                4: ["Good product", "Happy with the purchase", "Works well"],
                5: ["Excellent!", "Highly recommend", "Best purchase this year"]}
    for (item_id, oid, p, cust, odate, qty, unit) in delivered_items:
        if random.random() < 0.06:
            rdate = min(odate + timedelta(days=random.randint(3, 20)), TODAY)
            returns.append((len(returns) + 1, item_id, rdate.isoformat(), weighted(reasons), round(qty * unit, 2)))
        if random.random() < 0.25 and (p, cust) not in seen:
            seen.add((p, cust))
            rating = weighted([(1, 5), (2, 8), (3, 15), (4, 32), (5, 40)])
            rvdate = min(odate + timedelta(days=random.randint(5, 30)), TODAY)
            reviews.append((len(reviews) + 1, p, cust, rating, rvdate.isoformat(), random.choice(comments[rating])))
    insert(conn, "product_returns", returns)
    insert(conn, "reviews", reviews)
    conn.commit()
    return conn


# ----------------------------------------------------------------------------- HR
HR_SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE departments (
    department_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    location TEXT NOT NULL,
    annual_budget REAL NOT NULL
);
CREATE TABLE employees (
    employee_id INTEGER PRIMARY KEY,
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    department_id INTEGER NOT NULL REFERENCES departments(department_id),
    manager_id INTEGER REFERENCES employees(employee_id),
    job_title TEXT NOT NULL,
    hire_date TEXT NOT NULL,
    salary REAL NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('Active','Resigned')),
    termination_date TEXT
);
CREATE TABLE salary_history (
    history_id INTEGER PRIMARY KEY,
    employee_id INTEGER NOT NULL REFERENCES employees(employee_id),
    effective_date TEXT NOT NULL,
    salary REAL NOT NULL
);
CREATE TABLE projects (
    project_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    department_id INTEGER NOT NULL REFERENCES departments(department_id),
    start_date TEXT NOT NULL,
    end_date TEXT,
    budget REAL NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('Planned','Active','Completed','On Hold'))
);
CREATE TABLE project_assignments (
    assignment_id INTEGER PRIMARY KEY,
    employee_id INTEGER NOT NULL REFERENCES employees(employee_id),
    project_id INTEGER NOT NULL REFERENCES projects(project_id),
    role TEXT NOT NULL,
    allocation_pct INTEGER NOT NULL,
    UNIQUE (employee_id, project_id)
);
CREATE TABLE leave_requests (
    leave_id INTEGER PRIMARY KEY,
    employee_id INTEGER NOT NULL REFERENCES employees(employee_id),
    leave_type TEXT NOT NULL,
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('Approved','Pending','Rejected'))
);
CREATE TABLE performance_reviews (
    review_id INTEGER PRIMARY KEY,
    employee_id INTEGER NOT NULL REFERENCES employees(employee_id),
    review_year INTEGER NOT NULL,
    rating INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5),
    reviewer_id INTEGER NOT NULL REFERENCES employees(employee_id)
);
CREATE INDEX idx_emp_dept ON employees(department_id);
CREATE INDEX idx_emp_mgr ON employees(manager_id);
"""


def seed_hr(n_employees=300, n_projects=40, n_leaves=1000):
    conn = make_db("hr", HR_SCHEMA)

    depts = [(1, "Executive", "Bengaluru", 60_000_000), (2, "Engineering", "Bengaluru", 400_000_000),
             (3, "Sales", "Mumbai", 180_000_000), (4, "Marketing", "Delhi", 90_000_000),
             (5, "Human Resources", "Pune", 40_000_000), (6, "Finance", "Mumbai", 70_000_000),
             (7, "Operations", "Chennai", 120_000_000), (8, "Customer Support", "Hyderabad", 80_000_000),
             (9, "Product", "Bengaluru", 110_000_000)]
    insert(conn, "departments", depts)
    # junior, senior, lead titles + (junior_lo, junior_hi) annual salary in INR
    titles = {
        2: (["Software Engineer", "Senior Software Engineer", "Engineering Manager"], 900_000, 1_800_000),
        3: (["Sales Executive", "Senior Sales Executive", "Sales Manager"], 500_000, 1_000_000),
        4: (["Marketing Associate", "Senior Marketing Specialist", "Marketing Manager"], 500_000, 1_000_000),
        5: (["HR Associate", "HR Business Partner", "HR Manager"], 450_000, 900_000),
        6: (["Financial Analyst", "Senior Financial Analyst", "Finance Manager"], 600_000, 1_200_000),
        7: (["Operations Associate", "Operations Specialist", "Operations Manager"], 400_000, 850_000),
        8: (["Support Agent", "Senior Support Agent", "Support Team Lead"], 300_000, 600_000),
        9: (["Associate Product Manager", "Product Manager", "Senior Product Manager"], 1_000_000, 2_000_000),
    }
    level_mult = [1.0, 1.7, 2.4]

    employees, history = [], []
    dept_pool = {d[0]: [] for d in depts}

    def make_employee(eid, dept_id, title, lo, hi, manager_id):
        fn, ln = person()
        hire = rand_date(date(2015, 1, 1), TODAY - timedelta(days=45))
        status, term = "Active", None
        if random.random() < 0.10:
            term = hire + timedelta(days=random.randint(180, 1800))
            if term > TODAY:
                term = None
            else:
                status = "Resigned"
        end = term or TODAY
        base = round(random.uniform(lo, hi), -3)
        k = min((end - hire).days // 365, 4)
        hist = [((hire + timedelta(days=365 * i)).isoformat(), round(base / (1.08 ** (k - i)), -2))
                for i in range(k + 1)]
        employees.append((eid, fn, ln, f"{fn}.{ln}{eid}@example.com".lower(), dept_id, manager_id, title,
                          hire.isoformat(), hist[-1][1], status, term.isoformat() if term else None))
        for h in hist:
            history.append((len(history) + 1, eid, h[0], h[1]))
        if status == "Active":
            dept_pool[dept_id].append(eid)

    make_employee(1, 1, "Chief Executive Officer", 12_000_000, 15_000_000, None)
    eid = 1
    for d in depts[1:]:
        eid += 1
        make_employee(eid, d[0], f"Head of {d[1]}", 5_000_000, 8_000_000, 1)
    while eid < n_employees:
        eid += 1
        dept_id = random.choice([d[0] for d in depts[1:]])
        names, lo, hi = titles[dept_id]
        level = random.choices([0, 1, 2], [60, 30, 10])[0]
        manager = random.choice(dept_pool[dept_id]) if dept_pool[dept_id] else 1
        make_employee(eid, dept_id, names[level], lo * level_mult[level], hi * level_mult[level], manager)
    insert(conn, "employees", employees)
    insert(conn, "salary_history", history)

    # Projects and assignments
    active_ids = [e[0] for e in employees if e[9] == "Active"]
    project_words = ["Phoenix", "Atlas", "Nebula", "Horizon", "Catalyst", "Pulse", "Summit", "Beacon", "Vector", "Mosaic"]
    kinds = ["Migration", "Rollout", "Platform", "Revamp", "Initiative", "Automation"]
    projects, assignments = [], []
    roles = ["Lead", "Contributor", "Analyst", "Reviewer", "Coordinator"]
    for pid in range(1, n_projects + 1):
        dept_id = random.choice([d[0] for d in depts[1:]])
        start = rand_date(date(2023, 1, 1), TODAY + timedelta(days=60))
        if start > TODAY:
            status, end = "Planned", None
        else:
            status = weighted([("Active", 45), ("Completed", 40), ("On Hold", 15)])
            end = (start + timedelta(days=random.randint(90, 400))).isoformat() if status == "Completed" else None
        projects.append((pid, f"{random.choice(project_words)} {random.choice(kinds)} {pid}", dept_id,
                         start.isoformat(), end, float(random.randrange(500_000, 20_000_000, 100_000)), status))
        for e in random.sample(active_ids, random.randint(3, 8)):
            assignments.append((len(assignments) + 1, e, pid, random.choice(roles), random.choice([10, 20, 30, 50, 100])))
    insert(conn, "projects", projects)
    insert(conn, "project_assignments", assignments)

    # Leave requests
    leaves = []
    for i in range(1, n_leaves + 1):
        e = random.choice(active_ids)
        start = rand_date(date(2023, 1, 1), TODAY + timedelta(days=30))
        end = start + timedelta(days=random.randint(0, 9))
        ltype = weighted([("Casual", 40), ("Sick", 30), ("Earned", 25), ("Parental", 5)])
        status = weighted([("Approved", 50), ("Pending", 50)]) if start > TODAY else weighted([("Approved", 88), ("Rejected", 12)])
        leaves.append((i, e, ltype, start.isoformat(), end.isoformat(), status))
    insert(conn, "leave_requests", leaves)

    # Performance reviews 2022-2025 for people employed during that year
    reviews = []
    for e in employees:
        if e[5] is None:
            continue
        hire_year = int(e[7][:4])
        term_year = int(e[10][:4]) if e[10] else 9999
        for yr in range(2022, 2026):
            if hire_year < yr <= term_year:
                rating = weighted([(1, 4), (2, 12), (3, 40), (4, 32), (5, 12)])
                reviews.append((len(reviews) + 1, e[0], yr, rating, e[5]))
    insert(conn, "performance_reviews", reviews)
    conn.commit()
    return conn


# ----------------------------------------------------------------------------- HOSPITAL
HOSP_SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE doctors (
    doctor_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    specialization TEXT NOT NULL,
    experience_years INTEGER NOT NULL,
    consultation_fee REAL NOT NULL,
    branch TEXT NOT NULL
);
CREATE TABLE patients (
    patient_id INTEGER PRIMARY KEY,
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    gender TEXT NOT NULL CHECK (gender IN ('Male','Female')),
    date_of_birth TEXT NOT NULL,
    city TEXT NOT NULL,
    blood_group TEXT NOT NULL,
    insurance_provider TEXT
);
CREATE TABLE appointments (
    appointment_id INTEGER PRIMARY KEY,
    patient_id INTEGER NOT NULL REFERENCES patients(patient_id),
    doctor_id INTEGER NOT NULL REFERENCES doctors(doctor_id),
    appointment_date TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('Scheduled','Completed','Cancelled','No-Show')),
    fee_charged REAL NOT NULL
);
CREATE TABLE diagnoses (
    diagnosis_id INTEGER PRIMARY KEY,
    appointment_id INTEGER NOT NULL REFERENCES appointments(appointment_id),
    icd_code TEXT NOT NULL,
    description TEXT NOT NULL,
    severity TEXT NOT NULL CHECK (severity IN ('Mild','Moderate','Severe'))
);
CREATE TABLE medicines (
    medicine_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    unit_price REAL NOT NULL
);
CREATE TABLE prescriptions (
    prescription_id INTEGER PRIMARY KEY,
    appointment_id INTEGER NOT NULL REFERENCES appointments(appointment_id),
    medicine_id INTEGER NOT NULL REFERENCES medicines(medicine_id),
    dosage TEXT NOT NULL,
    duration_days INTEGER NOT NULL
);
CREATE TABLE billing (
    bill_id INTEGER PRIMARY KEY,
    appointment_id INTEGER NOT NULL UNIQUE REFERENCES appointments(appointment_id),
    consultation_fee REAL NOT NULL,
    medicine_charges REAL NOT NULL,
    total_amount REAL NOT NULL,
    paid_amount REAL NOT NULL,
    payment_status TEXT NOT NULL CHECK (payment_status IN ('Paid','Partial','Pending'))
);
CREATE INDEX idx_appt_patient ON appointments(patient_id);
CREATE INDEX idx_appt_doctor ON appointments(doctor_id);
CREATE INDEX idx_appt_date ON appointments(appointment_date);
"""


def seed_hospital(n_patients=1500, n_appointments=8000):
    conn = make_db("hospital", HOSP_SCHEMA)

    specs = [("Cardiology", 1500), ("Dermatology", 900), ("Orthopedics", 1200), ("Pediatrics", 800),
             ("Neurology", 1800), ("General Medicine", 500), ("Gynecology", 1000), ("ENT", 700),
             ("Oncology", 2200), ("Psychiatry", 1300)]
    branches = ["Main Campus", "City Center", "North Wing"]
    doctors = []
    for i in range(1, 31):
        spec, fee = specs[(i - 1) % len(specs)]
        fn, ln = person()
        doctors.append((i, f"Dr. {fn} {ln}", spec, random.randint(2, 35), float(fee + random.choice([0, 100, 200, 300])),
                        random.choice(branches)))
    insert(conn, "doctors", doctors)
    spec_of = {d[0]: d[2] for d in doctors}
    fee_of = {d[0]: d[4] for d in doctors}

    patients = []
    for i in range(1, n_patients + 1):
        fn, ln = person()
        patients.append((i, fn, ln, random.choice(["Male", "Female"]),
                         rand_date(date(1945, 1, 1), date(2024, 12, 31)).isoformat(),
                         random.choice(CITIES)[0],
                         weighted([("O+", 38), ("A+", 22), ("B+", 25), ("AB+", 7), ("O-", 3), ("A-", 2), ("B-", 2), ("AB-", 1)]),
                         weighted([(None, 30), ("Star Health", 25), ("HDFC Ergo", 20), ("ICICI Lombard", 15), ("Niva Bupa", 10)])))
    insert(conn, "patients", patients)

    meds = [("Paracetamol 500mg", "Analgesic", 2.5), ("Ibuprofen 400mg", "Analgesic", 4.0),
            ("Amoxicillin 500mg", "Antibiotic", 12.0), ("Azithromycin 500mg", "Antibiotic", 25.0),
            ("Cetirizine 10mg", "Antihistamine", 3.0), ("Metformin 500mg", "Antidiabetic", 5.0),
            ("Amlodipine 5mg", "Antihypertensive", 6.0), ("Atorvastatin 10mg", "Statin", 9.0),
            ("Omeprazole 20mg", "Antacid", 5.5), ("Pantoprazole 40mg", "Antacid", 8.0),
            ("Salbutamol Inhaler", "Respiratory", 120.0), ("Montelukast 10mg", "Respiratory", 14.0),
            ("Sertraline 50mg", "Antidepressant", 18.0), ("Escitalopram 10mg", "Antidepressant", 15.0),
            ("Gabapentin 300mg", "Neuro", 16.0), ("Levetiracetam 500mg", "Neuro", 22.0),
            ("Diclofenac Gel", "Topical", 85.0), ("Clobetasol Cream", "Topical", 95.0),
            ("Vitamin D3 60K", "Supplement", 30.0), ("Iron + Folic Acid", "Supplement", 6.0),
            ("Ondansetron 4mg", "Antiemetic", 7.0), ("Losartan 50mg", "Antihypertensive", 7.5),
            ("Clopidogrel 75mg", "Antiplatelet", 11.0), ("Tamsulosin 0.4mg", "Urology", 13.0)]
    medicines = [(i + 1, *m) for i, m in enumerate(meds)]
    insert(conn, "medicines", medicines)
    med_price = {m[0]: m[3] for m in medicines}
    med_ids = list(med_price)

    diag = {
        "Cardiology": [("I10", "Essential hypertension"), ("I25.1", "Coronary artery disease")],
        "Dermatology": [("L20.9", "Atopic dermatitis"), ("L70.0", "Acne vulgaris")],
        "Orthopedics": [("M54.5", "Low back pain"), ("M17.9", "Osteoarthritis of knee")],
        "Pediatrics": [("J06.9", "Acute upper respiratory infection"), ("A09", "Infectious gastroenteritis")],
        "Neurology": [("G43.9", "Migraine"), ("G40.9", "Epilepsy")],
        "General Medicine": [("E11.9", "Type 2 diabetes mellitus"), ("J20.9", "Acute bronchitis")],
        "Gynecology": [("N92.6", "Irregular menstruation"), ("N76.0", "Acute vaginitis")],
        "ENT": [("J01.9", "Acute sinusitis"), ("H66.9", "Otitis media")],
        "Oncology": [("C50.9", "Breast cancer follow-up"), ("C34.9", "Lung cancer follow-up")],
        "Psychiatry": [("F41.1", "Generalized anxiety disorder"), ("F32.9", "Depressive episode")],
    }

    appts, diagnoses, prescriptions, bills = [], [], [], []
    doctor_ids = list(spec_of)
    for aid in range(1, n_appointments + 1):
        pat = random.randint(1, n_patients)
        doc = random.choice(doctor_ids)
        adate = rand_date(date(2024, 1, 1), TODAY + timedelta(days=60))
        if adate > TODAY:
            status = "Scheduled"
        else:
            status = weighted([("Completed", 80), ("Cancelled", 12), ("No-Show", 8)])
        fee = fee_of[doc]
        appts.append((aid, pat, doc, adate.isoformat(), status, fee))
        if status != "Completed":
            continue
        for code, desc in random.sample(diag[spec_of[doc]], random.choice([1, 1, 2])):
            diagnoses.append((len(diagnoses) + 1, aid, code, desc, weighted([("Mild", 50), ("Moderate", 35), ("Severe", 15)])))
        med_cost = 0.0
        for m in random.sample(med_ids, random.randint(1, 3)):
            days = random.choice([3, 5, 7, 10, 14, 30])
            dosage = random.choice(["1-0-0", "1-0-1", "1-1-1", "0-0-1"])
            per_day = sum(int(x) for x in dosage.split("-"))
            med_cost += med_price[m] * per_day * days
            prescriptions.append((len(prescriptions) + 1, aid, m, dosage, days))
        med_cost = round(med_cost, 2)
        total = round(fee + med_cost, 2)
        pstatus = weighted([("Paid", 75), ("Partial", 15), ("Pending", 10)])
        paid = total if pstatus == "Paid" else (round(total * random.uniform(0.3, 0.8), 2) if pstatus == "Partial" else 0.0)
        bills.append((len(bills) + 1, aid, fee, med_cost, total, paid, pstatus))
    insert(conn, "appointments", appts)
    insert(conn, "diagnoses", diagnoses)
    insert(conn, "prescriptions", prescriptions)
    insert(conn, "billing", bills)
    conn.commit()
    return conn


# ----------------------------------------------------------------------------- main
if __name__ == "__main__":
    for seeder in (seed_ecommerce, seed_hr, seed_hospital):
        conn = seeder()
        name = seeder.__name__.replace("seed_", "")
        print(f"\n[{name}]")
        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        for t in tables:
            print(f"  {t:<22}{conn.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]:>8} rows")
        conn.close()
    print(f"\nDone. Databases written to ./{OUT_DIR}/")