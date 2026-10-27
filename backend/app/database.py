import html
import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .classifier import VERSION, classify
from .config import SEARCH_GROUPS
from .parser import JobDraft, normalize_air_description, normalize_hej_description


def decode_entities(text: str | None) -> str | None:
    """Undo HTML escaping, including the double escaping ("&amp;amp;") some listings use."""
    for _ in range(3):
        if not text or "&" not in text:
            break
        decoded = html.unescape(text)
        if decoded == text:
            break
        text = decoded
    return text


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
          categories TEXT NOT NULL DEFAULT '', enabled INTEGER NOT NULL DEFAULT 1, priority INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS jobs (
          id INTEGER PRIMARY KEY, higheredjobs_id TEXT UNIQUE, source TEXT NOT NULL DEFAULT 'higheredjobs',
          source_job_id TEXT, source_url TEXT, title TEXT, institution TEXT,
          location TEXT, city TEXT, state TEXT, salary TEXT, posted_date TEXT,
          application_due_date TEXT,
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
          source TEXT NOT NULL DEFAULT 'higheredjobs',
          groups_run TEXT NOT NULL, jobs_discovered INTEGER NOT NULL DEFAULT 0,
          new_jobs INTEGER NOT NULL DEFAULT 0, updated_jobs INTEGER NOT NULL DEFAULT 0,
          errors TEXT NOT NULL DEFAULT '[]'
        );
        """)
        self._migrate_columns()
        # Config is the source of truth for each group's search; only the enabled choice is the user's.
        self.connection.executemany(
            "INSERT INTO search_groups (id,name,query,categories,priority) VALUES (?,?,?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET name=excluded.name, query=excluded.query, "
            "categories=excluded.categories, priority=excluded.priority",
            [(identifier, name, query, categories, index) for index, (identifier, name, query, categories) in enumerate(SEARCH_GROUPS)],
        )
        # "University IT Titles" repeats the software and systems queries. Disable it once so a
        # user who re-enables it in Search sources keeps that choice across restarts.
        if self.connection.execute("PRAGMA user_version").fetchone()[0] < 1:
            self.connection.execute("UPDATE search_groups SET enabled=0 WHERE id='it'")
            self.connection.execute("PRAGMA user_version=1")
        self.connection.commit()

    def _migrate_columns(self):
        migrations = {
            "jobs": {
                "source": "TEXT NOT NULL DEFAULT 'higheredjobs'",
                "source_job_id": "TEXT",
                "source_url": "TEXT",
                "application_due_date": "TEXT",
            },
            "scrape_runs": {"source": "TEXT NOT NULL DEFAULT 'higheredjobs'"},
            "search_groups": {"categories": "TEXT NOT NULL DEFAULT ''"},
            "sponsorship_analysis": {"signals": "TEXT NOT NULL DEFAULT '[]'"},
        }
        for table, columns in migrations.items():
            existing = {
                row["name"] for row in self.connection.execute(f"PRAGMA table_info({table})")
            }
            for column, definition in columns.items():
                if column not in existing:
                    self.connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
        self.connection.execute(
            "UPDATE jobs SET source='higheredjobs', source_url=higheredjobs_url, source_job_id=higheredjobs_id "
            "WHERE source_url IS NULL"
        )
        self.connection.execute(
            "UPDATE jobs SET description_status='Complete' "
            "WHERE normalized_description IS NOT NULL AND TRIM(normalized_description) != ''"
        )
        self.connection.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS jobs_source_identity "
            "ON jobs(source, source_job_id) WHERE source_job_id IS NOT NULL"
        )
        self.connection.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS jobs_source_url ON jobs(source, source_url) "
            "WHERE source_url IS NOT NULL"
        )

    def groups(self):
        return [dict(row) | {"enabled": bool(row["enabled"])} for row in self.connection.execute("SELECT * FROM search_groups ORDER BY priority")]

    def set_group_enabled(self, group_id: str, enabled: bool):
        cursor = self.connection.execute("UPDATE search_groups SET enabled=? WHERE id=?", (enabled, group_id))
        self.connection.commit()
        return cursor.rowcount > 0

    def start_run(self, group_ids: list[str], source: str = "higheredjobs") -> int:
        cursor = self.connection.execute(
            "INSERT INTO scrape_runs(started_at,source,groups_run) VALUES (?,?,?)",
            (utcnow(), source, json.dumps(group_ids)),
        )
        self.connection.commit()
        return cursor.lastrowid

    def finish_run(self, run_id: int, discovered: int, new: int, updated: int, errors: list[dict]):
        self.connection.execute("UPDATE scrape_runs SET completed_at=?, jobs_discovered=?, new_jobs=?, updated_jobs=?, errors=? WHERE id=?", (utcnow(), discovered, new, updated, json.dumps(errors), run_id))
        self.connection.commit()

    def close_interrupted_runs(self):
        """Mark runs left open by a stopped server as finished, so they no longer look in progress."""
        self.connection.execute(
            "UPDATE scrape_runs SET completed_at=?, errors=? WHERE completed_at IS NULL",
            (utcnow(), json.dumps([{"error": "Run was interrupted before it finished."}])),
        )
        self.connection.commit()

    def latest_run(self, source: str | None = None):
        if source:
            row = self.connection.execute(
                "SELECT * FROM scrape_runs WHERE source=? ORDER BY id DESC LIMIT 1", (source,)
            ).fetchone()
        else:
            row = self.connection.execute("SELECT * FROM scrape_runs ORDER BY id DESC LIMIT 1").fetchone()
        if not row: return None
        result = dict(row); result["groups_run"] = json.loads(result["groups_run"]); result["errors"] = json.loads(result["errors"])
        return result

    def upsert(self, draft: JobDraft, group_id: str | None = None) -> bool:
        return self.upsert_job(draft, group_id)[1]

    def upsert_job(self, draft: JobDraft, group_id: str | None = None) -> tuple[int, bool]:
        now = utcnow()
        # Listing pages and JSON-LD sometimes leave entities like "&amp;" in names.
        draft.title, draft.institution = decode_entities(draft.title), decode_entities(draft.institution)
        source = draft.source or "higheredjobs"
        source_url = draft.source_url or draft.higheredjobs_url
        source_job_id = draft.source_job_id or draft.higheredjobs_id
        existing = self.connection.execute(
            "SELECT id FROM jobs WHERE (source=? AND source_job_id=?) OR (source=? AND source_url=?)",
            (source, source_job_id, source, source_url),
        ).fetchone()
        values = (
            draft.title,
            draft.institution,
            draft.location,
            draft.city,
            draft.state,
            draft.salary,
            draft.posted_date,
            draft.application_due_date,
            draft.apply_url,
            draft.raw_description,
            draft.normalized_description,
            draft.description_status,
        )
        if existing:
            job_id = existing["id"]
            self.connection.execute(
                """UPDATE jobs SET source=?, source_job_id=?, source_url=?,
                title=COALESCE(?,title), institution=COALESCE(?,institution),
                location=COALESCE(?,location), city=COALESCE(?,city), state=COALESCE(?,state),
                salary=COALESCE(?,salary), posted_date=COALESCE(?,posted_date),
                application_due_date=COALESCE(?,application_due_date), apply_url=COALESCE(?,apply_url),
                raw_description=COALESCE(?,raw_description),
                normalized_description=COALESCE(?,normalized_description),
                description_status=CASE
                    WHEN ? IS NOT NULL THEN 'Complete'
                    WHEN description_status='Complete' THEN description_status
                    WHEN ?='Failed' THEN 'Failed'
                    ELSE description_status
                END,
                last_seen_at=?, active=1, updated_at=? WHERE id=?""",
                (source, source_job_id, source_url, *values[:-1], draft.normalized_description,
                 draft.description_status, now, now, job_id),
            )
            is_new = False
        else:
            cursor = self.connection.execute(
                """INSERT INTO jobs(
                higheredjobs_id,source,source_job_id,source_url,title,institution,location,city,state,
                salary,posted_date,application_due_date,first_seen_at,last_seen_at,higheredjobs_url,
                apply_url,raw_description,normalized_description,description_status,created_at,updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    draft.higheredjobs_id,
                    source,
                    source_job_id,
                    source_url,
                    draft.title,
                    draft.institution,
                    draft.location,
                    draft.city,
                    draft.state,
                    draft.salary,
                    draft.posted_date,
                    draft.application_due_date,
                    now,
                    now,
                    source_url,
                    draft.apply_url,
                    draft.raw_description,
                    draft.normalized_description,
                    draft.description_status or ("Complete" if draft.normalized_description else "Pending"),
                    now,
                    now,
                ),
            )
            job_id, is_new = cursor.lastrowid, True
        if group_id:
            self._record_match(job_id, group_id, now)
        if draft.normalized_description:
            self._store_analysis(job_id, draft.normalized_description, draft.institution, now)
        self.connection.commit()
        return job_id, is_new

    def _record_match(self, job_id: int, group_id: str, now: str):
        self.connection.execute(
            "INSERT INTO job_search_matches(job_id,search_group_id,first_matched_at,last_matched_at) VALUES (?,?,?,?) "
            "ON CONFLICT(job_id,search_group_id) DO UPDATE SET last_matched_at=excluded.last_matched_at",
            (job_id, group_id, now, now),
        )

    def saved_jobs(self, source: str) -> dict[str, int]:
        """Source URL -> job id for jobs whose description was captured, so reruns can skip them."""
        rows = self.connection.execute(
            "SELECT source_url, id FROM jobs WHERE source=? AND description_status='Complete' AND source_url IS NOT NULL",
            (source,),
        )
        return {row["source_url"]: row["id"] for row in rows}

    def add_match(self, job_id: int, group_id: str):
        self._record_match(job_id, group_id, utcnow())
        self.connection.commit()

    def clear_jobs(self):
        self.connection.executescript(
            "DELETE FROM sponsorship_analysis; DELETE FROM job_search_matches; DELETE FROM jobs; DELETE FROM scrape_runs;"
        )
        self.connection.commit()

    def jobs(self, query: str = "", group: str = "", sponsorship: str = "", application_status: str = "", days: str = "7", sort: str = "newest", page: int = 1, per_page: int = 50, source: str = "", description: str = "", due: str = ""):
        clauses, values = ["1=1"], []
        if source:
            clauses.append("j.source=?"); values.append(source)
        if query:
            clauses.append("(j.title LIKE ? OR j.institution LIKE ? OR j.location LIKE ?)"); values += [f"%{query}%"] * 3
        if group:
            group_ids = [item for item in group.split(",") if item]
            if group_ids:
                placeholders = ",".join("?" for _ in group_ids)
                clauses.append(f"EXISTS (SELECT 1 FROM job_search_matches gm WHERE gm.job_id=j.id AND gm.search_group_id IN ({placeholders}))")
                values.extend(group_ids)
        statuses = [status for status in sponsorship.split(",") if status]
        if statuses:
            clauses.append(f"sa.status IN ({','.join('?' * len(statuses))})"); values.extend(statuses)
        if description == "complete":
            clauses.append("j.normalized_description IS NOT NULL AND TRIM(j.normalized_description) != ''")
        elif description == "missing":
            clauses.append("(j.normalized_description IS NULL OR TRIM(j.normalized_description) = '')")
        elif description == "failed":
            clauses.append("j.description_status='Failed' AND (j.normalized_description IS NULL OR TRIM(j.normalized_description) = '')")
        if application_status: clauses.append("j.application_status=?"); values.append(application_status)
        elif days != "all" and due != "all": clauses.append("j.application_status != 'Skipped'")
        if days not in ("", "all"):
            clauses.append("(j.source='air' OR j.posted_date >= date('now', ?))"); values.append(f"-{int(days)} days")
        # AIR listings carry a due date instead of a posted date. Undated ones stay in the upcoming view.
        if due == "upcoming":
            clauses.append("(j.application_due_date IS NULL OR j.application_due_date >= date('now', 'localtime'))")
        elif due == "expired":
            clauses.append("j.application_due_date < date('now', 'localtime')")
        elif due.isdigit():
            clauses.append("j.application_due_date BETWEEN date('now', 'localtime') AND date('now', 'localtime', ?)"); values.append(f"+{int(due)} days")
        order = {"oldest":"COALESCE(j.posted_date, substr(j.first_seen_at,1,10)) ASC", "first_seen":"j.first_seen_at DESC", "institution":"j.institution COLLATE NOCASE", "title":"j.title COLLATE NOCASE", "state":"j.state COLLATE NOCASE", "due_soon":"j.application_due_date IS NULL, j.application_due_date ASC", "due_late":"j.application_due_date IS NULL, j.application_due_date DESC"}.get(sort, "COALESCE(j.posted_date, substr(j.first_seen_at,1,10)) DESC")
        where = " AND ".join(clauses)
        total = self.connection.execute(f"SELECT COUNT(*) FROM jobs j LEFT JOIN sponsorship_analysis sa ON sa.job_id=j.id WHERE {where}", values).fetchone()[0]
        rows = self.connection.execute(f"""SELECT j.*, COALESCE(sa.status,'Unavailable') sponsorship_status, COALESCE(sa.confidence,'-') confidence, sa.evidence, sa.evidence_context, sa.matched_terms, COALESCE(sa.signals,'[]') signals, GROUP_CONCAT(sg.name, ' | ') search_groups FROM jobs j LEFT JOIN sponsorship_analysis sa ON sa.job_id=j.id LEFT JOIN job_search_matches jm ON jm.job_id=j.id LEFT JOIN search_groups sg ON sg.id=jm.search_group_id WHERE {where} GROUP BY j.id ORDER BY {order}, j.id DESC LIMIT ? OFFSET ?""", values + [per_page, (page - 1) * per_page]).fetchall()
        return {"items": [dict(row) | {"active":bool(row["active"]), "matched_terms":json.loads(row["matched_terms"] or "[]")} for row in rows], "total": total, "page": page, "per_page": per_page}

    def update_job(self, job_id: int, values: dict):
        allowed = {"application_status", "notes"}; changes = {k:v for k,v in values.items() if k in allowed}
        if not changes: return False
        sets = ", ".join(f"{key}=?" for key in changes) + ", updated_at=?"
        cursor = self.connection.execute(f"UPDATE jobs SET {sets} WHERE id=?", [*changes.values(), utcnow(), job_id]); self.connection.commit(); return cursor.rowcount > 0

    def mark_opened(self, job_id: int):
        self.connection.execute("UPDATE jobs SET application_status=CASE WHEN application_status='New' THEN 'Opened' ELSE application_status END, updated_at=? WHERE id=?", (utcnow(),job_id)); self.connection.commit()

    def _store_analysis(self, job_id: int, description: str, institution: str | None, now: str):
        result = classify(description, institution).as_dict()
        self.connection.execute(
            "INSERT INTO sponsorship_analysis(job_id,status,confidence,evidence,evidence_context,matched_terms,classifier_version,analyzed_at,signals) "
            "VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT(job_id) DO UPDATE SET status=excluded.status,confidence=excluded.confidence,"
            "evidence=excluded.evidence,evidence_context=excluded.evidence_context,matched_terms=excluded.matched_terms,"
            "classifier_version=excluded.classifier_version,analyzed_at=excluded.analyzed_at,signals=excluded.signals",
            (job_id, result["status"], result["confidence"], result["evidence"], result["evidence_context"],
             json.dumps(result["matched_terms"]), result["classifier_version"], now, json.dumps(result["signals"])),
        )

    def reanalyze(self, only_outdated: bool = False) -> int:
        """Re-clean each description and classify it again. raw_description is never changed; the
        cleaned text replaces normalized_description so evidence stays a substring of what is shown."""
        query = (
            "SELECT j.id, j.source, j.raw_description, j.normalized_description, j.title, j.institution FROM jobs j "
            "LEFT JOIN sponsorship_analysis sa ON sa.job_id=j.id WHERE j.normalized_description IS NOT NULL"
        )
        if only_outdated:
            query += " AND (sa.classifier_version IS NULL OR sa.classifier_version != ?)"
        rows = self.connection.execute(query, (VERSION,) if only_outdated else ()).fetchall()
        for row in rows:
            if row["raw_description"]:
                normalize = normalize_air_description if row["source"] == "air" else normalize_hej_description
                text = normalize(row["raw_description"])
            else:
                # Compacted rows lost their HTML. Strip tags only when the stored text still has markup:
                # reparsing plain text would drop things like "<jobs@x.edu>" for good.
                stored = row["normalized_description"]
                has_markup = re.search(r"</?(?:p|div|li|ul|ol|br|b|strong|em|i|span|center|h\d|table|tr|td)\b[^>]*>|&lt;", stored, re.I)
                text = normalize_hej_description(stored) if has_markup else stored
            text = text or row["normalized_description"]
            now = utcnow()
            self.connection.execute("UPDATE jobs SET normalized_description=? WHERE id=?", (text, row["id"]))
            self.connection.execute(
                "UPDATE jobs SET title=?, institution=? WHERE id=?",
                (decode_entities(row["title"]), decode_entities(row["institution"]), row["id"]),
            )
            self._store_analysis(row["id"], text, row["institution"], now)
        self.connection.commit()
        return len(rows)
