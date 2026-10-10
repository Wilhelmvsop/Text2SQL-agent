"""Build deterministic SQLite demo databases for trying the web app's upload flow.

    python scripts/make_demo_databases.py [--out examples/databases]

Each database covers a different domain and a different mix of SQL features
(joins, self-joins, many-to-many links, NULLs, date ranges, history tables).
"""
import argparse
import random
import sqlite3
from contextlib import closing
from datetime import date, datetime, timedelta
from pathlib import Path

FIRST = ['Ana', 'Ben', 'Chloe', 'Daniel', 'Elena', 'Farah', 'George', 'Hana', 'Ivan', 'Jia', 'Kofi', 'Lucia',
         'Mateo', 'Nadia', 'Omar', 'Priya', 'Quinn', 'Rosa', 'Sven', 'Tariq', 'Uma', 'Victor', 'Wei', 'Ximena',
         'Yusuf', 'Zoe', 'Aiko', 'Bruno', 'Carmen', 'Dmitri', 'Esther', 'Felix', 'Grace', 'Hugo', 'Isla', 'Jamal']
LAST = ['Silva', 'Chen', 'Okafor', 'Novak', 'Garcia', 'Kim', 'Haddad', 'Muller', 'Rossi', 'Tanaka', 'Singh',
        'Kowalski', 'Andersen', 'Dubois', 'Mensah', 'Ivanova', 'Lopez', 'Nguyen', 'Brown', 'Cohen', 'Patel',
        'Murphy', 'Yilmaz', 'Santos', 'Larsen', 'Moreau', 'Wang', 'Costa', 'Fischer', 'Ahmed']
COUNTRIES = ['Canada', 'USA', 'Mexico', 'Brazil', 'UK', 'Germany', 'France', 'India', 'China', 'Japan', 'Nigeria']
CITIES = ['Toronto', 'Waterloo', 'Ottawa', 'Montreal', 'Vancouver', 'Calgary', 'Halifax', 'Hamilton']


def names(rng: random.Random, count: int) -> list[str]:
    """Unique full names, so questions about a specific person have one answer."""
    pool = [f'{f} {l}' for f in FIRST for l in LAST]
    return rng.sample(pool, count)


def email(name: str, domain: str) -> str:
    return name.lower().replace(' ', '.') + '@' + domain


def day(start: date, end: date, rng: random.Random) -> date:
    return start + timedelta(days=rng.randint(0, (end - start).days))


def build(path: Path, ddl: str, fill) -> dict[str, int]:
    path.unlink(missing_ok=True)
    with closing(sqlite3.connect(path)) as conn, conn:
        conn.execute('PRAGMA foreign_keys=ON')
        conn.executescript(ddl)
        fill(conn)
        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_schema WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        counts = {t: conn.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0] for t in tables}
    with closing(sqlite3.connect(path)) as conn:
        conn.execute('VACUUM')
    return counts


# --- university: grades, terms, NULL grades for courses in progress -------------------------

UNIVERSITY = """
CREATE TABLE departments (department_id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, building TEXT NOT NULL,
    budget REAL NOT NULL);
CREATE TABLE professors (professor_id INTEGER PRIMARY KEY, name TEXT NOT NULL, email TEXT NOT NULL UNIQUE,
    department_id INTEGER NOT NULL REFERENCES departments(department_id), hire_date TEXT NOT NULL,
    title TEXT NOT NULL CHECK (title IN ('Assistant Professor', 'Associate Professor', 'Professor')));
CREATE TABLE students (student_id INTEGER PRIMARY KEY, name TEXT NOT NULL, email TEXT NOT NULL UNIQUE,
    major_department_id INTEGER NOT NULL REFERENCES departments(department_id), enrollment_year INTEGER NOT NULL,
    country TEXT NOT NULL);
CREATE TABLE courses (course_id INTEGER PRIMARY KEY, code TEXT NOT NULL UNIQUE, title TEXT NOT NULL,
    department_id INTEGER NOT NULL REFERENCES departments(department_id), credits INTEGER NOT NULL,
    professor_id INTEGER NOT NULL REFERENCES professors(professor_id));
CREATE TABLE enrollments (enrollment_id INTEGER PRIMARY KEY, student_id INTEGER NOT NULL REFERENCES students(student_id),
    course_id INTEGER NOT NULL REFERENCES courses(course_id), term TEXT NOT NULL,
    grade REAL CHECK (grade BETWEEN 0 AND 100), UNIQUE (student_id, course_id, term));
"""


def fill_university(conn: sqlite3.Connection) -> None:
    rng = random.Random(11)
    depts = [('Computer Science', 'DC', 'CS'), ('Mathematics', 'MC', 'MATH'), ('Physics', 'PHY', 'PHYS'),
             ('Economics', 'HH', 'ECON'), ('Biology', 'B1', 'BIOL'), ('History', 'HH', 'HIST'),
             ('Psychology', 'PAS', 'PSYCH'), ('Statistics', 'M3', 'STAT')]
    conn.executemany('INSERT INTO departments VALUES (?,?,?,?)',
                     [(i, n, b, rng.randint(8, 40) * 100_000) for i, (n, b, _) in enumerate(depts, 1)])
    profs = names(rng, 40)
    titles = ['Assistant Professor', 'Associate Professor', 'Professor']
    conn.executemany('INSERT INTO professors VALUES (?,?,?,?,?,?)', [
        (i, n, email(n, 'uni.example.edu'), (i - 1) % 8 + 1,
         day(date(1995, 1, 1), date(2023, 8, 1), rng).isoformat(), rng.choice(titles))
        for i, n in enumerate(profs, 1)])
    studs = names(rng, 420)
    conn.executemany('INSERT INTO students VALUES (?,?,?,?,?,?)', [
        (i, n, email(n, 'student.example.edu'), rng.choices(range(1, 9), [5, 3, 2, 3, 2, 1, 2, 2])[0],
         rng.randint(2021, 2025), rng.choices(COUNTRIES, [10, 3, 1, 1, 1, 1, 1, 3, 4, 1, 1])[0])
        for i, n in enumerate(studs, 1)])
    topics = ['Introduction to', 'Advanced', 'Topics in', 'Foundations of', 'Applied']
    subjects = {1: ['Algorithms', 'Databases', 'Machine Learning', 'Operating Systems', 'Networks', 'Compilers', 'Security', 'Graphics'],
                2: ['Linear Algebra', 'Calculus', 'Number Theory', 'Real Analysis', 'Combinatorics'],
                3: ['Mechanics', 'Quantum Physics', 'Electromagnetism', 'Thermodynamics'],
                4: ['Microeconomics', 'Macroeconomics', 'Econometrics', 'Game Theory'],
                5: ['Genetics', 'Cell Biology', 'Ecology', 'Evolution'],
                6: ['Ancient Rome', 'Modern Europe', 'Canadian History'],
                7: ['Cognitive Psychology', 'Social Psychology', 'Neuroscience'],
                8: ['Probability', 'Regression', 'Bayesian Statistics', 'Data Analysis']}
    courses, cid = [], 1
    for dept, subs in subjects.items():
        prefix = depts[dept - 1][2]
        for n, sub in enumerate(subs):
            prof = rng.choice([p for p in range(1, 41) if (p - 1) % 8 + 1 == dept])
            courses.append((cid, f'{prefix} {100 + n * 100 + rng.randint(0, 49)}', f'{rng.choice(topics)} {sub}',
                            dept, rng.choice([3, 3, 4, 2]), prof))
            cid += 1
    conn.executemany('INSERT INTO courses VALUES (?,?,?,?,?,?)', courses)
    terms = ['2023 Fall', '2024 Winter', '2024 Fall', '2025 Winter', '2025 Fall']
    rows, eid = [], 1
    for sid in range(1, 421):
        ability = rng.gauss(76, 8)
        for term in rng.sample(terms, rng.randint(2, 5)):
            for course in rng.sample(courses, rng.randint(2, 4)):
                grade = None if term == '2025 Fall' else round(min(100, max(20, rng.gauss(ability, 9))), 1)
                rows.append((eid, sid, course[0], term, grade))
                eid += 1
    conn.executemany('INSERT OR IGNORE INTO enrollments VALUES (?,?,?,?,?)', rows)


# --- hospital: appointments with statuses, prescriptions, nullable insurance --------------

HOSPITAL = """
CREATE TABLE departments (department_id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, floor INTEGER NOT NULL);
CREATE TABLE doctors (doctor_id INTEGER PRIMARY KEY, name TEXT NOT NULL, specialty TEXT NOT NULL,
    department_id INTEGER NOT NULL REFERENCES departments(department_id), years_experience INTEGER NOT NULL);
CREATE TABLE patients (patient_id INTEGER PRIMARY KEY, name TEXT NOT NULL, birth_date TEXT NOT NULL,
    sex TEXT NOT NULL CHECK (sex IN ('F', 'M', 'X')), city TEXT NOT NULL, insurance_provider TEXT);
CREATE TABLE appointments (appointment_id INTEGER PRIMARY KEY, patient_id INTEGER NOT NULL REFERENCES patients(patient_id),
    doctor_id INTEGER NOT NULL REFERENCES doctors(doctor_id), scheduled_at TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('completed', 'cancelled', 'no_show', 'scheduled')),
    reason TEXT NOT NULL, fee REAL NOT NULL);
CREATE TABLE medications (medication_id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, category TEXT NOT NULL,
    unit_price REAL NOT NULL);
CREATE TABLE prescriptions (prescription_id INTEGER PRIMARY KEY,
    appointment_id INTEGER NOT NULL REFERENCES appointments(appointment_id),
    medication_id INTEGER NOT NULL REFERENCES medications(medication_id), dosage TEXT NOT NULL, days INTEGER NOT NULL);
CREATE INDEX appointments_doctor ON appointments(doctor_id, scheduled_at);
"""


def fill_hospital(conn: sqlite3.Connection) -> None:
    rng = random.Random(22)
    depts = [('Cardiology', 3, ['Cardiologist']), ('Pediatrics', 2, ['Pediatrician']),
             ('Orthopedics', 4, ['Orthopedic Surgeon']), ('Neurology', 5, ['Neurologist']),
             ('Family Medicine', 1, ['Family Physician', 'General Practitioner']), ('Dermatology', 2, ['Dermatologist'])]
    conn.executemany('INSERT INTO departments VALUES (?,?,?)', [(i, n, f) for i, (n, f, _) in enumerate(depts, 1)])
    doctors = []
    for i, n in enumerate(names(rng, 30), 1):
        dept = (i - 1) % 6 + 1
        doctors.append((i, f'Dr. {n}', rng.choice(depts[dept - 1][2]), dept, rng.randint(1, 35)))
    conn.executemany('INSERT INTO doctors VALUES (?,?,?,?,?)', doctors)
    insurers = ['Sun Life', 'Manulife', 'Blue Cross', 'Canada Life', None]
    conn.executemany('INSERT INTO patients VALUES (?,?,?,?,?,?)', [
        (i, n, day(date(1940, 1, 1), date(2022, 12, 31), rng).isoformat(), rng.choices('FMX', [48, 48, 4])[0],
         rng.choice(CITIES), rng.choices(insurers, [3, 3, 3, 2, 2])[0])
        for i, n in enumerate(names(rng, 520), 1)])
    reasons = {1: ['Chest pain', 'Heart palpitations', 'Blood pressure check'], 2: ['Vaccination', 'Fever', 'Annual checkup'],
               3: ['Knee pain', 'Back pain', 'Fracture follow-up'], 4: ['Migraine', 'Dizziness', 'Numbness'],
               5: ['Annual physical', 'Flu symptoms', 'Prescription renewal'], 6: ['Rash', 'Acne', 'Mole check']}
    appointments = []
    for aid in range(1, 3201):
        doc = rng.choice(doctors)
        when = datetime(2024, 1, 1, 8) + timedelta(days=rng.randint(0, 700), minutes=30 * rng.randint(0, 17))
        status = 'scheduled' if when.date() > date(2025, 10, 1) else rng.choices(
            ['completed', 'cancelled', 'no_show'], [85, 10, 5])[0]
        appointments.append((aid, rng.randint(1, 520), doc[0], when.isoformat(sep=' ', timespec='minutes'), status,
                             rng.choice(reasons[doc[3]]), rng.choice([75, 120, 150, 200, 250])))
    conn.executemany('INSERT INTO appointments VALUES (?,?,?,?,?,?,?)', appointments)
    meds = [('Amoxicillin', 'Antibiotic', 0.45), ('Azithromycin', 'Antibiotic', 1.10), ('Ibuprofen', 'Pain relief', 0.15),
            ('Acetaminophen', 'Pain relief', 0.10), ('Naproxen', 'Pain relief', 0.30), ('Lisinopril', 'Blood pressure', 0.35),
            ('Amlodipine', 'Blood pressure', 0.40), ('Metoprolol', 'Blood pressure', 0.50), ('Atorvastatin', 'Cholesterol', 0.60),
            ('Sumatriptan', 'Migraine', 2.20), ('Gabapentin', 'Nerve pain', 0.80), ('Hydrocortisone cream', 'Skin', 6.50),
            ('Isotretinoin', 'Skin', 3.10), ('Cetirizine', 'Allergy', 0.20), ('Salbutamol inhaler', 'Respiratory', 18.00)]
    conn.executemany('INSERT INTO medications VALUES (?,?,?,?)', [(i, *m) for i, m in enumerate(meds, 1)])
    rows, pid = [], 1
    for a in appointments:
        if a[4] == 'completed' and rng.random() < 0.55:
            for med in rng.sample(range(1, len(meds) + 1), rng.choice([1, 1, 2])):
                rows.append((pid, a[0], med, rng.choice(['1 tablet daily', '2 tablets daily', '1 tablet twice daily', 'apply twice daily']),
                             rng.choice([5, 7, 10, 14, 30, 90])))
                pid += 1
    conn.executemany('INSERT INTO prescriptions VALUES (?,?,?,?,?)', rows)


# --- library: loans with NULL return dates, overdue fines --------------------------------

LIBRARY = """
CREATE TABLE authors (author_id INTEGER PRIMARY KEY, name TEXT NOT NULL, country TEXT NOT NULL, birth_year INTEGER);
CREATE TABLE books (book_id INTEGER PRIMARY KEY, title TEXT NOT NULL, author_id INTEGER NOT NULL REFERENCES authors(author_id),
    genre TEXT NOT NULL, published_year INTEGER NOT NULL, isbn TEXT NOT NULL UNIQUE, copies INTEGER NOT NULL);
CREATE TABLE members (member_id INTEGER PRIMARY KEY, name TEXT NOT NULL, email TEXT NOT NULL UNIQUE, joined_date TEXT NOT NULL,
    membership TEXT NOT NULL CHECK (membership IN ('standard', 'premium', 'student')));
CREATE TABLE loans (loan_id INTEGER PRIMARY KEY, book_id INTEGER NOT NULL REFERENCES books(book_id),
    member_id INTEGER NOT NULL REFERENCES members(member_id), loan_date TEXT NOT NULL, due_date TEXT NOT NULL,
    returned_date TEXT, fine REAL NOT NULL DEFAULT 0);
"""


def fill_library(conn: sqlite3.Connection) -> None:
    rng = random.Random(33)
    conn.executemany('INSERT INTO authors VALUES (?,?,?,?)', [
        (i, n, rng.choice(COUNTRIES), rng.choice([None] + list(range(1920, 1995))))
        for i, n in enumerate(names(rng, 60), 1)])
    adjectives = ['Silent', 'Hidden', 'Last', 'Broken', 'Golden', 'Distant', 'Forgotten', 'Crimson', 'Endless', 'Quiet',
                  'Northern', 'Burning', 'Paper', 'Glass', 'Midnight']
    nouns = ['River', 'Garden', 'Empire', 'Letter', 'Island', 'Machine', 'Winter', 'Harbor', 'Orchard', 'Signal',
             'Library', 'Mountain', 'Archive', 'Lantern', 'Compass']
    genres = ['Fiction', 'Mystery', 'Science Fiction', 'Fantasy', 'Biography', 'History', 'Science', 'Poetry', 'Romance']
    titles = rng.sample([f'The {a} {n}' for a in adjectives for n in nouns], 200)
    conn.executemany('INSERT INTO books VALUES (?,?,?,?,?,?,?)', [
        (i, t, rng.randint(1, 60), rng.choice(genres), rng.randint(1950, 2025), f'978-{rng.randint(10**9, 10**10 - 1)}',
         rng.choice([1, 1, 2, 3, 5])) for i, t in enumerate(titles, 1)])
    conn.executemany('INSERT INTO members VALUES (?,?,?,?,?)', [
        (i, n, email(n, 'mail.example.com'), day(date(2018, 1, 1), date(2025, 6, 30), rng).isoformat(),
         rng.choices(['standard', 'premium', 'student'], [6, 2, 3])[0]) for i, n in enumerate(names(rng, 350), 1)])
    today = date(2025, 10, 10)
    rows = []
    for lid in range(1, 4001):
        loaned = day(date(2023, 1, 1), today - timedelta(days=1), rng)
        due = loaned + timedelta(days=21)
        returned = None if loaned > today - timedelta(days=40) and rng.random() < 0.6 else \
            loaned + timedelta(days=rng.choices([rng.randint(3, 21), rng.randint(22, 60)], [85, 15])[0])
        if returned and returned > today:
            returned = None
        late_days = ((returned or today) - due).days
        fine = round(max(0, late_days) * 0.25, 2) if returned else 0
        rows.append((lid, rng.randint(1, 200), rng.randint(1, 350), loaned.isoformat(), due.isoformat(),
                     returned.isoformat() if returned else None, fine))
    conn.executemany('INSERT INTO loans VALUES (?,?,?,?,?,?,?)', rows)


# --- streaming: many-to-many genres, ratings, watch events --------------------------------

STREAMING = """
CREATE TABLE movies (movie_id INTEGER PRIMARY KEY, title TEXT NOT NULL, release_year INTEGER NOT NULL,
    runtime_minutes INTEGER NOT NULL, language TEXT NOT NULL,
    age_rating TEXT NOT NULL CHECK (age_rating IN ('G', 'PG', 'PG-13', 'R')));
CREATE TABLE genres (genre_id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE);
CREATE TABLE movie_genres (movie_id INTEGER NOT NULL REFERENCES movies(movie_id),
    genre_id INTEGER NOT NULL REFERENCES genres(genre_id), PRIMARY KEY (movie_id, genre_id));
CREATE TABLE users (user_id INTEGER PRIMARY KEY, username TEXT NOT NULL UNIQUE, country TEXT NOT NULL,
    signup_date TEXT NOT NULL, plan TEXT NOT NULL CHECK (plan IN ('basic', 'standard', 'premium')));
CREATE TABLE watch_events (event_id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(user_id),
    movie_id INTEGER NOT NULL REFERENCES movies(movie_id), watched_at TEXT NOT NULL, minutes_watched INTEGER NOT NULL,
    completed INTEGER NOT NULL CHECK (completed IN (0, 1)));
CREATE TABLE reviews (review_id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(user_id),
    movie_id INTEGER NOT NULL REFERENCES movies(movie_id), stars INTEGER NOT NULL CHECK (stars BETWEEN 1 AND 5),
    created_at TEXT NOT NULL, UNIQUE (user_id, movie_id));
"""


def fill_streaming(conn: sqlite3.Connection) -> None:
    rng = random.Random(44)
    genres = ['Action', 'Comedy', 'Drama', 'Horror', 'Science Fiction', 'Romance', 'Documentary', 'Animation', 'Thriller', 'Crime']
    conn.executemany('INSERT INTO genres VALUES (?,?)', list(enumerate(genres, 1)))
    first = ['Night', 'Echoes', 'Storm', 'Paper', 'Neon', 'Lost', 'Iron', 'Velvet', 'Hollow', 'Bright', 'Second', 'Frozen']
    second = ['City', 'Signal', 'Kingdom', 'Hearts', 'Protocol', 'Summer', 'Frontier', 'Tide', 'Witness', 'Orbit', 'Shadows', 'Dream']
    titles = rng.sample([f'{a} {b}' for a in first for b in second], 140)
    movies = []
    for i, t in enumerate(titles, 1):
        movies.append((i, t, rng.randint(1985, 2025), rng.randint(78, 172),
                       rng.choices(['English', 'French', 'Spanish', 'Korean', 'Japanese', 'Hindi'], [10, 2, 2, 2, 2, 2])[0],
                       rng.choice(['G', 'PG', 'PG-13', 'PG-13', 'R', 'R'])))
    conn.executemany('INSERT INTO movies VALUES (?,?,?,?,?,?)', movies)
    conn.executemany('INSERT INTO movie_genres VALUES (?,?)',
                     [(m[0], g) for m in movies for g in rng.sample(range(1, 11), rng.choice([1, 2, 2, 3]))])
    users = [(i, n.lower().replace(' ', '_') + str(rng.randint(1, 99)), rng.choice(COUNTRIES),
              day(date(2021, 1, 1), date(2025, 8, 31), rng).isoformat(), rng.choices(['basic', 'standard', 'premium'], [4, 4, 2])[0])
             for i, n in enumerate(names(rng, 600), 1)]
    conn.executemany('INSERT INTO users VALUES (?,?,?,?,?)', users)
    quality = {m[0]: rng.gauss(3.4, 0.8) for m in movies}
    events, reviews, seen = [], [], set()
    for eid in range(1, 9001):
        user = rng.choice(users)
        movie = rng.choice(movies)
        start = max(date.fromisoformat(user[3]), date(2024, 1, 1))
        when = datetime.combine(day(start, date(2025, 10, 9), rng), datetime.min.time()) + timedelta(minutes=rng.randint(0, 1439))
        minutes = movie[3] if rng.random() < 0.7 else rng.randint(5, movie[3] - 1)
        events.append((eid, user[0], movie[0], when.isoformat(sep=' ', timespec='minutes'), minutes, int(minutes == movie[3])))
        if minutes == movie[3] and (user[0], movie[0]) not in seen and rng.random() < 0.35:
            seen.add((user[0], movie[0]))
            stars = int(min(5, max(1, round(rng.gauss(quality[movie[0]], 0.9)))))
            reviews.append((len(reviews) + 1, user[0], movie[0], stars, (when + timedelta(hours=2)).isoformat(sep=' ', timespec='minutes')))
    conn.executemany('INSERT INTO watch_events VALUES (?,?,?,?,?,?)', events)
    conn.executemany('INSERT INTO reviews VALUES (?,?,?,?,?)', reviews)


# --- company: manager self-reference, salary history, project staffing -------------------

COMPANY = """
CREATE TABLE departments (department_id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, location TEXT NOT NULL);
CREATE TABLE employees (employee_id INTEGER PRIMARY KEY, name TEXT NOT NULL, email TEXT NOT NULL UNIQUE,
    department_id INTEGER NOT NULL REFERENCES departments(department_id),
    manager_id INTEGER REFERENCES employees(employee_id), job_title TEXT NOT NULL, hire_date TEXT NOT NULL,
    termination_date TEXT);
CREATE TABLE salaries (salary_id INTEGER PRIMARY KEY, employee_id INTEGER NOT NULL REFERENCES employees(employee_id),
    amount REAL NOT NULL, effective_date TEXT NOT NULL);
CREATE TABLE projects (project_id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE,
    department_id INTEGER NOT NULL REFERENCES departments(department_id), start_date TEXT NOT NULL, end_date TEXT,
    budget REAL NOT NULL);
CREATE TABLE project_assignments (project_id INTEGER NOT NULL REFERENCES projects(project_id),
    employee_id INTEGER NOT NULL REFERENCES employees(employee_id), role TEXT NOT NULL, hours_per_week INTEGER NOT NULL,
    PRIMARY KEY (project_id, employee_id));
"""


def fill_company(conn: sqlite3.Connection) -> None:
    rng = random.Random(55)
    depts = [('Engineering', 'Toronto', 'Software Engineer', 'Engineering Manager', 115_000),
             ('Product', 'Toronto', 'Product Manager', 'Director of Product', 120_000),
             ('Sales', 'Vancouver', 'Account Executive', 'Sales Director', 85_000),
             ('Marketing', 'Montreal', 'Marketing Specialist', 'Marketing Director', 80_000),
             ('Finance', 'Toronto', 'Financial Analyst', 'Finance Director', 90_000),
             ('People', 'Waterloo', 'HR Partner', 'Head of People', 78_000),
             ('Support', 'Halifax', 'Support Specialist', 'Support Manager', 62_000)]
    conn.executemany('INSERT INTO departments VALUES (?,?,?)', [(i, d[0], d[1]) for i, d in enumerate(depts, 1)])
    people = names(rng, 230)
    ceo = (1, people[0], email(people[0], 'acme.example.com'), 2, None, 'Chief Executive Officer', '2012-03-01', None)
    rows, heads = [ceo], {}
    for d in range(1, 8):
        eid = len(rows) + 1
        heads[d] = eid
        rows.append((eid, people[eid - 1], email(people[eid - 1], 'acme.example.com'), d, 1, depts[d - 1][3],
                     day(date(2012, 6, 1), date(2018, 12, 31), rng).isoformat(), None))
    while len(rows) < 230:
        eid = len(rows) + 1
        d = rng.choices(range(1, 8), [9, 3, 5, 3, 2, 1, 3])[0]
        senior = [r[0] for r in rows if r[3] == d and r[5].startswith('Senior')]
        manager = rng.choice(senior) if senior and rng.random() < 0.5 else heads[d]
        title = ('Senior ' if rng.random() < 0.25 else '') + depts[d - 1][2]
        hired = day(date(2014, 1, 1), date(2025, 9, 1), rng)
        left = day(hired + timedelta(days=200), date(2025, 9, 30), rng) if rng.random() < 0.12 and hired < date(2024, 1, 1) else None
        rows.append((eid, people[eid - 1], email(people[eid - 1], 'acme.example.com'), d, manager, title,
                     hired.isoformat(), left.isoformat() if left else None))
    conn.executemany('INSERT INTO employees VALUES (?,?,?,?,?,?,?,?)', rows)
    salaries = []
    for r in rows:
        base = depts[r[3] - 1][4] * (2.2 if r[0] == 1 else 1.6 if r[0] in heads.values() else 1.3 if r[5].startswith('Senior') else 1)
        amount, when = round(base * rng.uniform(0.85, 1.1), -2), date.fromisoformat(r[6])
        end = date.fromisoformat(r[7]) if r[7] else date(2025, 10, 1)
        while when <= end:
            salaries.append((len(salaries) + 1, r[0], amount, when.isoformat()))
            when += timedelta(days=365)
            amount = round(amount * rng.uniform(1.0, 1.07), -2)
    conn.executemany('INSERT INTO salaries VALUES (?,?,?,?)', salaries)
    projects = ['Atlas', 'Beacon', 'Cascade', 'Delta', 'Ember', 'Falcon', 'Granite', 'Horizon', 'Ion', 'Juniper',
                'Keystone', 'Lumen', 'Meridian', 'Nimbus', 'Orion', 'Pioneer', 'Quartz', 'Relay']
    prows = []
    for i, n in enumerate(projects, 1):
        start = day(date(2022, 1, 1), date(2025, 6, 1), rng)
        end = start + timedelta(days=rng.randint(90, 500)) if rng.random() < 0.5 else None
        prows.append((i, f'Project {n}', rng.choices(range(1, 8), [6, 3, 2, 2, 1, 1, 1])[0], start.isoformat(),
                      end.isoformat() if end and end < date(2025, 10, 1) else None, rng.randint(5, 120) * 10_000))
    conn.executemany('INSERT INTO projects VALUES (?,?,?,?,?,?)', prows)
    active = [r for r in rows if r[7] is None]
    assignments = set()
    for p in prows:
        team = rng.sample([r for r in active if r[3] == p[2]] or active, min(rng.randint(3, 9), 20))
        team += rng.sample(active, rng.randint(0, 2))
        for k, member in enumerate(team):
            if (p[0], member[0]) not in assignments:
                assignments.add((p[0], member[0]))
                conn.execute('INSERT INTO project_assignments VALUES (?,?,?,?)',
                             (p[0], member[0], 'Lead' if k == 0 else rng.choice(['Contributor', 'Contributor', 'Reviewer']),
                              rng.choice([5, 10, 15, 20, 40])))


DATABASES = {
    'university.db': (UNIVERSITY, fill_university),
    'hospital.db': (HOSPITAL, fill_hospital),
    'library.db': (LIBRARY, fill_library),
    'streaming.db': (STREAMING, fill_streaming),
    'company.db': (COMPANY, fill_company),
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--out', type=Path, default=Path('examples/databases'))
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    for name, (ddl, fill) in DATABASES.items():
        counts = build(args.out / name, ddl, fill)
        size = (args.out / name).stat().st_size / 1024
        print(f'{name:<14} {size:6.0f} KB  ' + ', '.join(f'{t}={n}' for t, n in counts.items()))


if __name__ == '__main__':
    main()
