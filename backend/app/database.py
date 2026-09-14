import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .classifier import classify
from .config import SEARCH_GROUPS
from .parser import JobDraft


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Database:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.migrate()

    def migrate(self):
        self.connection.executescript("""
        CREATE TABLE IF NOT EXISTS search_groups (
          id TEXT PRIMARY KEY, name TEXT NOT NULL, query TEXT NOT NULL,
          enabled INTEGER NOT NULL DEFAULT 1, priority INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS jobs (
          id INTEGER PRIMARY KEY, higheredjobs_id TEXT UNIQUE, title TEXT, institution TEXT,
          location TEXT, city TEXT, state TEXT, salary TEXT, posted_date TEXT,
          first_seen_at TEXT NOT NULL, last_seen_at TEXT NOT NULL, higheredjobs_url TEXT UNIQUE NOT NULL,
          apply_url TEXT, raw_description TEXT, normalized_description TEXT,
          description_status TEXT NOT NULL DEFAULT 'Pending', active INTEGER NOT NULL DEFAULT 1,
          application_status TEXT NOT NULL DEFAULT 'New', notes TEXT NOT NULL DEFAULT '',
          created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS job_search_matches (
          job_id INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
          search_group_id TEXT NOT NULL REFERENCES search_groups(id),
          first_matched_at TEXT NOT NULL, last_matched_at TEXT NOT NULL,
          PRIMARY KEY (job_id, search_group_id)
        );
        CREATE TABLE IF NOT EXISTS sponsorship_analysis (
          job_id INTEGER PRIMARY KEY REFERENCES jobs(id) ON DELETE CASCADE,
          status TEXT NOT NULL, confidence TEXT NOT NULL, evidence TEXT, evidence_context TEXT,
          matched_terms TEXT NOT NULL DEFAULT '[]', classifier_version TEXT NOT NULL, analyzed_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS scrape_runs (
          id INTEGER PRIMARY KEY, started_at TEXT NOT NULL, completed_at TEXT,
          groups_run TEXT NOT NULL, jobs_discovered INTEGER NOT NULL DEFAULT 0,
          new_jobs INTEGER NOT NULL DEFAULT 0, updated_jobs INTEGER NOT NULL DEFAULT 0,
          errors TEXT NOT NULL DEFAULT '[]'
        );
        """)
        self.connection.executemany(
            "INSERT OR IGNORE INTO search_groups (id,name,query,priority) VALUES (?,?,?,?)",
            [(identifier, name, query, index) for index, (identifier, name, query) in enumerate(SEARCH_GROUPS)],
        )
        self.connection.commit()

    def groups(self):
        return [dict(row) | {"enabled": bool(row["enabled"])} for row in self.connection.execute("SELECT * FROM search_groups ORDER BY priority")]

    def set_group_enabled(self, group_id: str, enabled: bool):
        cursor = self.connection.execute("UPDATE search_groups SET enabled=? WHERE id=?", (enabled, group_id))
        self.connection.commit()
        return cursor.rowcount > 0

    def start_run(self, group_ids: list[str]) -> int:
        cursor = self.connection.execute("INSERT INTO scrape_runs(started_at,groups_run) VALUES (?,?)", (utcnow(), json.dumps(group_ids)))
        self.connection.commit()
        return cursor.lastrowid

    def finish_run(self, run_id: int, discovered: int, new: int, updated: int, errors: list[dict]):
        self.connection.execute("UPDATE scrape_runs SET completed_at=?, jobs_discovered=?, new_jobs=?, updated_jobs=?, errors=? WHERE id=?", (utcnow(), discovered, new, updated, json.dumps(errors), run_id))
        self.connection.commit()

    def latest_run(self):
        row = self.connection.execute("SELECT * FROM scrape_runs ORDER BY id DESC LIMIT 1").fetchone()
        if not row: return None
        result = dict(row); result["groups_run"] = json.loads(result["groups_run"]); result["errors"] = json.loads(result["errors"])
        return result

    def upsert(self, draft: JobDraft, group_id: str) -> bool:
        now = utcnow()
        existing = self.connection.execute("SELECT id FROM jobs WHERE higheredjobs_id=? OR higheredjobs_url=?", (draft.higheredjobs_id, draft.higheredjobs_url)).fetchone()
        values = (draft.title, draft.institution, draft.location, draft.city, draft.state, draft.salary, draft.posted_date, draft.apply_url, draft.raw_description, draft.normalized_description, now)
        if existing:
            job_id = existing["id"]
            self.connection.execute("""UPDATE jobs SET title=COALESCE(?,title), institution=COALESCE(?,institution), location=COALESCE(?,location), city=COALESCE(?,city), state=COALESCE(?,state), salary=COALESCE(?,salary), posted_date=COALESCE(?,posted_date), apply_url=COALESCE(?,apply_url), raw_description=COALESCE(?,raw_description), normalized_description=COALESCE(?,normalized_description), last_seen_at=?, active=1, updated_at=? WHERE id=?""", values + (now, job_id))
            is_new = False
        else:
            cursor = self.connection.execute("""INSERT INTO jobs(higheredjobs_id,title,institution,location,city,state,salary,posted_date,first_seen_at,last_seen_at,higheredjobs_url,apply_url,raw_description,normalized_description,description_status,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (draft.higheredjobs_id, draft.title, draft.institution, draft.location, draft.city, draft.state, draft.salary, draft.posted_date, now, now, draft.higheredjobs_url, draft.apply_url, draft.raw_description, draft.normalized_description, "Complete" if draft.normalized_description else "Pending", now, now))
            job_id, is_new = cursor.lastrowid, True
        self.connection.execute("INSERT INTO job_search_matches(job_id,search_group_id,first_matched_at,last_matched_at) VALUES (?,?,?,?) ON CONFLICT(job_id,search_group_id) DO UPDATE SET last_matched_at=excluded.last_matched_at", (job_id, group_id, now, now))
        if draft.normalized_description:
            result = classify(draft.normalized_description).as_dict()
            self.connection.execute("INSERT INTO sponsorship_analysis(job_id,status,confidence,evidence,evidence_context,matched_terms,classifier_version,analyzed_at) VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(job_id) DO UPDATE SET status=excluded.status,confidence=excluded.confidence,evidence=excluded.evidence,evidence_context=excluded.evidence_context,matched_terms=excluded.matched_terms,classifier_version=excluded.classifier_version,analyzed_at=excluded.analyzed_at", (job_id, result["status"], result["confidence"], result["evidence"], result["evidence_context"], json.dumps(result["matched_terms"]), result["classifier_version"], now))
        self.connection.commit()
        return is_new

    def jobs(self, query: str = "", group: str = "", sponsorship: str = "", application_status: str = "", days: str = "7", sort: str = "newest", page: int = 1, per_page: int = 50):
        clauses, values = ["1=1"], []
        if query:
            clauses.append("(j.title LIKE ? OR j.institution LIKE ? OR j.location LIKE ?)"); values += [f"%{query}%"] * 3
        if group:
            group_ids = [item for item in group.split(",") if item]
            if group_ids:
                placeholders = ",".join("?" for _ in group_ids)
                clauses.append(f"EXISTS (SELECT 1 FROM job_search_matches gm WHERE gm.job_id=j.id AND gm.search_group_id IN ({placeholders}))")
                values.extend(group_ids)
        if sponsorship: clauses.append("sa.status=?"); values.append(sponsorship)
        if application_status: clauses.append("j.application_status=?"); values.append(application_status)
        elif days != "all": clauses.append("j.application_status != 'Skipped'")
        if days not in ("", "all"):
            clauses.append("j.posted_date >= date('now', ?)"); values.append(f"-{int(days)} days")
        order = {"oldest":"j.posted_date ASC", "first_seen":"j.first_seen_at DESC", "institution":"j.institution COLLATE NOCASE", "title":"j.title COLLATE NOCASE", "state":"j.state COLLATE NOCASE"}.get(sort, "j.posted_date DESC")
        where = " AND ".join(clauses)
        total = self.connection.execute(f"SELECT COUNT(*) FROM jobs j LEFT JOIN sponsorship_analysis sa ON sa.job_id=j.id WHERE {where}", values).fetchone()[0]
        rows = self.connection.execute(f"""SELECT j.*, COALESCE(sa.status,'Unavailable') sponsorship_status, COALESCE(sa.confidence,'-') confidence, sa.evidence, sa.evidence_context, sa.matched_terms, GROUP_CONCAT(sg.name, ' | ') search_groups FROM jobs j LEFT JOIN sponsorship_analysis sa ON sa.job_id=j.id LEFT JOIN job_search_matches jm ON jm.job_id=j.id LEFT JOIN search_groups sg ON sg.id=jm.search_group_id WHERE {where} GROUP BY j.id ORDER BY {order}, j.id DESC LIMIT ? OFFSET ?""", values + [per_page, (page - 1) * per_page]).fetchall()
        return {"items": [dict(row) | {"active":bool(row["active"]), "matched_terms":json.loads(row["matched_terms"] or "[]")} for row in rows], "total": total, "page": page, "per_page": per_page}

    def update_job(self, job_id: int, values: dict):
        allowed = {"application_status", "notes"}; changes = {k:v for k,v in values.items() if k in allowed}
        if not changes: return False
        sets = ", ".join(f"{key}=?" for key in changes) + ", updated_at=?"
        cursor = self.connection.execute(f"UPDATE jobs SET {sets} WHERE id=?", [*changes.values(), utcnow(), job_id]); self.connection.commit(); return cursor.rowcount > 0

    def mark_opened(self, job_id: int):
        self.connection.execute("UPDATE jobs SET application_status=CASE WHEN application_status='New' THEN 'Opened' ELSE application_status END, updated_at=? WHERE id=?", (utcnow(),job_id)); self.connection.commit()

    def reanalyze(self):
        rows = self.connection.execute("SELECT id,normalized_description FROM jobs WHERE normalized_description IS NOT NULL").fetchall()
        for row in rows:
            result = classify(row["normalized_description"]).as_dict(); now=utcnow()
            self.connection.execute("INSERT INTO sponsorship_analysis(job_id,status,confidence,evidence,evidence_context,matched_terms,classifier_version,analyzed_at) VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(job_id) DO UPDATE SET status=excluded.status,confidence=excluded.confidence,evidence=excluded.evidence,evidence_context=excluded.evidence_context,matched_terms=excluded.matched_terms,classifier_version=excluded.classifier_version,analyzed_at=excluded.analyzed_at", (row["id"],result["status"],result["confidence"],result["evidence"],result["evidence_context"],json.dumps(result["matched_terms"]),result["classifier_version"],now))
        self.connection.commit(); return len(rows)
