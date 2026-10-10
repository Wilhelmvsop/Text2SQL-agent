# Demo Databases

Five SQLite databases for trying the web app's **upload** flow. Drop any `.db` file here onto the
setup screen (or **Settings → Database**). Each one covers a different domain and a different mix of
SQL features, so they also work as quick tests of how well a connected model handles unfamiliar schemas.

The data is synthetic and deterministic. Rebuild identical files with:

```bash
python scripts/make_demo_databases.py
```

"Today" in the data is **2025-10-10** (for questions about overdue loans, the current term, and so on).

| File | Tables | Rows | SQL features it exercises |
|---|---|---:|---|
| `university.db` | departments, professors, students, courses, enrollments | ~4,800 | Multi-hop joins, `NULL` grades for courses still in progress, terms as text |
| `hospital.db` | departments, doctors, patients, appointments, medications, prescriptions | ~5,600 | Status filters, percentages, date-time ranges, nullable insurance |
| `library.db` | authors, books, members, loans | ~4,600 | `NULL` return dates, overdue logic, fines, date arithmetic |
| `streaming.db` | movies, genres, movie_genres, users, watch_events, reviews | ~12,000 | Many-to-many (`movie_genres`), `HAVING`, completion rates |
| `company.db` | departments, employees, salaries, projects, project_assignments | ~1,700 | Manager self-join, salary history (latest row per employee), window functions |

## Questions to Try

Within each list, the questions get harder from top to bottom.

**university.db**
- How many students are in each department?
- Which department has the highest average grade in completed courses?
- List the five students with the highest average grade in 2024 Fall.
- How many students are taking courses this term (2025 Fall) that have not been graded yet?
- Which professors teach more than one course, and how many students have they taught in total?

**hospital.db**
- How many patients have no insurance provider?
- Which doctor completed the most appointments in 2025?
- What is the no-show rate for each department?
- Which medications were prescribed most often, and what is their total cost (unit price × days)?
- Which patients have seen doctors in three or more different departments?

**library.db**
- How many books does each genre have?
- Which books are currently checked out?
- How many loans are overdue today?
- Which members owe the most in fines?
- Which authors' books are borrowed most often by student members?

**streaming.db**
- How many users are on each plan?
- Which genre has the most total watch time?
- What are the best-rated movies with at least 20 reviews?
- What share of views are watched to the end, by age rating?
- Which premium users watched a movie every month from January to September 2025?

**company.db**
- How many active employees does each department have?
- Who reports directly to the CEO?
- What is each employee's current salary? (Use the most recent salary row.)
- Which employees earn more than their manager?
- Which projects are still running, and how many hours per week are assigned to each?
