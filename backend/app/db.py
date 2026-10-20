"""Approved forms, kept for good — one row per form the secretary approved.

SQLite: a single file (work/forms.db) that Python reads and writes on its own —
no server, no password, no install. Open it with "DB Browser for SQLite". Only
this module touches the database, so moving to PostgreSQL later is a change here.

The page image is copied next to it (work/approved_pages/) and the row keeps the
path, so the row survives even after the batch itself is deleted. Approving the
same page again (after a fix) updates its row — never a duplicate.

A second table (`approved_rows`, below) holds the same approved forms the way the
Excel file does — one row per commitment number — for the "רשומות במערכת" panel.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import shutil
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image

from app.config import WORK_DIR
from app.fields import FIELDS, MULTI_SEPARATOR
from app.models import Batch, ExtractedField, FormRecord, SourceFile, now

DB_PATH = WORK_DIR / "forms.db"
PAGES_DIR = WORK_DIR / "approved_pages"
_LOCK = threading.Lock()

TEXT_FIELDS = ("first_name", "last_name", "national_id", "sample_received_date", "sending_entity")
LIST_FIELDS = ("central_numbers", "commitment_numbers")  # כמה ערכים — נשמרים כרשימה (JSON)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS approved_forms (
    form_key             TEXT PRIMARY KEY,
    first_name           TEXT,
    last_name            TEXT,
    national_id          TEXT,
    central_numbers      TEXT,
    sample_received_date TEXT,
    sending_entity       TEXT,
    commitment_numbers   TEXT,
    source_file          TEXT,
    page_number          INTEGER,
    page_image           TEXT,
    batch_id             TEXT,
    record_id            TEXT,
    approved_at          TEXT,
    updated_at           TEXT
)
"""


def _connect(path: Path | None = None) -> sqlite3.Connection:
    path = path or DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute(_SCHEMA)
    return conn


def form_key(page_png: Path) -> str:
    """The page's own fingerprint (its pixels): the same form is always the same row."""
    with Image.open(page_png) as page:
        digest = hashlib.sha256(f"{page.mode}:{page.size}".encode("ascii"))
        digest.update(page.tobytes())
    return digest.hexdigest()[:24]


def save_approved(record: FormRecord, source: SourceFile, page_png: Path,
                  path: Path | None = None, pages_dir: Path | None = None) -> str:
    """Insert or update the row for this approved form. Returns its key."""
    key = form_key(page_png)
    pages_dir = pages_dir or PAGES_DIR
    pages_dir.mkdir(parents=True, exist_ok=True)
    image = pages_dir / f"{key}.png"
    shutil.copyfile(page_png, image)

    values = {k: " | ".join(record.fields[k].values) for k in TEXT_FIELDS}
    values.update({k: json.dumps(record.fields[k].values, ensure_ascii=False) for k in LIST_FIELDS})
    stamp = now()
    row = {
        "form_key": key, **values,
        "source_file": source.filename, "page_number": record.page_number,
        "page_image": str(image), "batch_id": record.batch_id, "record_id": record.record_id,
        "approved_at": stamp, "updated_at": stamp,
    }
    columns = ", ".join(row)
    marks = ", ".join(f":{c}" for c in row)
    # אישור חוזר של אותו טופס: מעדכנים את השורה, ושומרים את מועד האישור הראשון
    updates = ", ".join(f"{c} = excluded.{c}" for c in row if c not in ("form_key", "approved_at"))
    with _LOCK, _connect(path) as conn:
        conn.execute(f"INSERT INTO approved_forms ({columns}) VALUES ({marks}) "
                     f"ON CONFLICT(form_key) DO UPDATE SET {updates}", row)
    with _LOCK, _rows_conn(path) as conn:
        _save_rows(conn, key, record, source, image)
    return key


def list_approved(path: Path | None = None) -> list[dict]:
    """Every approved form, newest first; the list fields come back as lists."""
    with _LOCK, _connect(path) as conn:
        rows = conn.execute("SELECT * FROM approved_forms ORDER BY updated_at DESC").fetchall()
    out = []
    for row in rows:
        item = dict(row)
        for k in LIST_FIELDS:
            item[k] = json.loads(item[k] or "[]")
        out.append(item)
    return out


# ------------------------------------------------------------ "רשומות במערכת"
#
# רק טפסים שאושרו ב"אישור הטופס" — כמו הקובץ לאקסל: שורה לכל מספר התחייבות (מספרים
# מרכזיים נשארים יחד בתא אחד). אישור חוזר של אותו טופס (אותו עמוד) מחליף את השורות שלו —
# אף פעם לא מוסיף. הפאנל שולף תמיד טווח של תאריכי אישור (ברירת מחדל: היום) — לא את כל
# המאגר; לכן יש אינדקס על מועד האישור.

LIST_LIMIT = 1000  # תקרה לשורות במסך אחד; הייצוא מוציא את כל הטווח
ROW_FIELDS = ("first_name", "last_name", "national_id", "central_numbers",
              "sample_received_date", "sending_entity", "commitment_number")

_ROWS_SCHEMA = """
CREATE TABLE IF NOT EXISTS approved_rows (
    row_id               INTEGER PRIMARY KEY AUTOINCREMENT,
    form_key             TEXT NOT NULL,
    row_index            INTEGER NOT NULL,
    record_id            TEXT,
    batch_id             TEXT,
    first_name           TEXT,
    last_name            TEXT,
    national_id          TEXT,
    central_numbers      TEXT,
    sample_received_date TEXT,
    received_iso         TEXT,
    sending_entity       TEXT,
    commitment_number    TEXT,
    source_name          TEXT,
    page_number          INTEGER,
    page_image           TEXT,
    search_text          TEXT,
    record               TEXT,
    source               TEXT,
    approved_at          TEXT NOT NULL,
    updated_at           TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS approved_rows_at ON approved_rows (approved_at);
CREATE INDEX IF NOT EXISTS approved_rows_form ON approved_rows (form_key);
CREATE INDEX IF NOT EXISTS approved_rows_commitment ON approved_rows (commitment_number);
"""

_PREPARED: set[str] = set()


def _rows_conn(path: Path | None = None) -> sqlite3.Connection:
    conn = _connect(path)
    conn.executescript(_ROWS_SCHEMA)
    where = str(path or DB_PATH)
    if where not in _PREPARED:
        _PREPARED.add(where)
        _first_use(conn, Path(where))
    return conn


def _first_use(conn: sqlite3.Connection, db_file: Path) -> None:
    """Once per database: remove what the earlier "save every form" version left
    behind (unapproved forms, by Noa's decision 20/10/2026), and bring forms approved
    before this table existed into it, so the panel shows them too."""
    conn.execute("DROP TABLE IF EXISTS records")
    conn.execute("DROP TABLE IF EXISTS record_numbers")
    shutil.rmtree(db_file.parent / "record_pages", ignore_errors=True)

    old = conn.execute(
        "SELECT * FROM approved_forms WHERE form_key NOT IN (SELECT DISTINCT form_key FROM approved_rows)"
    ).fetchall()
    for row in old:
        commitments = json.loads(row["commitment_numbers"] or "[]") or [""]
        central = MULTI_SEPARATOR.join(json.loads(row["central_numbers"] or "[]"))
        for index, number in enumerate(commitments):
            values = {
                "first_name": row["first_name"] or "", "last_name": row["last_name"] or "",
                "national_id": row["national_id"] or "", "central_numbers": central,
                "sample_received_date": row["sample_received_date"] or "",
                "sending_entity": row["sending_entity"] or "", "commitment_number": number,
            }
            _insert_row(conn, {
                "form_key": row["form_key"], "row_index": index, "record_id": row["record_id"],
                "batch_id": row["batch_id"], **values,
                "received_iso": _iso_date(values["sample_received_date"]),
                "source_name": row["source_file"], "page_number": row["page_number"],
                "page_image": row["page_image"], "search_text": _search_text(values, row["source_file"]),
                "record": None, "source": None,  # נשמר לפני הטבלה — אפשר לראות ולייצא, לא לפתוח
                "approved_at": row["updated_at"] or row["approved_at"] or now(),
                "updated_at": row["updated_at"] or now(),
            })
    # "אושר" = האישור האחרון (גם לשורות שנשמרו כשהעמודה הציגה את האישור הראשון)
    conn.execute("UPDATE approved_rows SET approved_at = updated_at WHERE approved_at != updated_at")


def _save_rows(conn: sqlite3.Connection, key: str, record: FormRecord, source: SourceFile, image: Path) -> None:
    """The approved form as Excel rows: replaces this form's earlier rows. "אושר" is
    the latest approval (Noa's decision, 20/10/2026)."""
    stamp = now()
    conn.execute("DELETE FROM approved_rows WHERE form_key = ?", (key,))
    commitments = record.fields["commitment_numbers"].values or [""]
    for index, number in enumerate(commitments):
        values = {k: MULTI_SEPARATOR.join(record.fields[k].values) for k in ROW_FIELDS if k in record.fields}
        values["commitment_number"] = number
        _insert_row(conn, {
            "form_key": key, "row_index": index, "record_id": record.record_id, "batch_id": record.batch_id,
            **values, "received_iso": _iso_date(values["sample_received_date"]),
            "source_name": record.source_name, "page_number": record.page_number, "page_image": str(image),
            "search_text": _search_text(values, record.source_name),
            "record": json.dumps(dataclasses.asdict(record), ensure_ascii=False),
            "source": json.dumps({
                "index": source.index, "filename": source.filename, "kind": source.kind,
                "page_count": source.page_count, "sha256": source.sha256, "joined": source.joined,
            }, ensure_ascii=False),
            "approved_at": stamp, "updated_at": stamp,
        })


def _insert_row(conn: sqlite3.Connection, row: dict) -> None:
    columns = ", ".join(row)
    marks = ", ".join(f":{c}" for c in row)
    conn.execute(f"INSERT INTO approved_rows ({columns}) VALUES ({marks})", row)


def _iso_date(value: str) -> str:
    """DD/MM/YYYY → YYYY-MM-DD, for filtering by date. Empty when not a valid date."""
    parts = (value or "").split(MULTI_SEPARATOR)[0].strip().split("/")
    if len(parts) == 3 and all(p.isdigit() for p in parts) and len(parts[2]) == 4:
        return f"{parts[2]}-{int(parts[1]):02d}-{int(parts[0]):02d}"
    return ""


def _search_text(values: dict, source_name: str) -> str:
    return (" ".join(str(v) for v in values.values()) + " " + (source_name or "")).lower()


def _utc(value: str) -> str:
    """Any ISO time from the browser → the stored format (UTC, seconds)."""
    moment = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc).isoformat(timespec="seconds")


def _where(start: str, end: str, q: str = "", sender: str = "", received_from: str = "",
           received_to: str = "") -> tuple[str, list]:
    """The filters the panel, its counts and its export share. The approval range
    is required: the panel never loads the whole store."""
    clauses, params = ["approved_at >= ?", "approved_at < ?"], [_utc(start), _utc(end)]
    if q.strip():
        clauses.append("search_text LIKE ?")
        params.append(f"%{q.strip().lower()}%")
    if sender.strip():
        clauses.append("sending_entity = ?")
        params.append(sender.strip())
    if received_from:
        clauses.append("received_iso != '' AND received_iso >= ?")
        params.append(received_from)
    if received_to:
        clauses.append("received_iso != '' AND received_iso <= ?")
        params.append(received_to)
    return " AND ".join(clauses), params


def list_rows(start: str, end: str, *, limit: int | None = LIST_LIMIT, path: Path | None = None,
              **filters) -> dict:
    """The panel: the rows approved in the range, how many forms they come from,
    the senders to filter by, and which commitment numbers appear in another form."""
    where, params = _where(start, end, **filters)
    with _LOCK, _rows_conn(path) as conn:
        totals = conn.execute(
            f"SELECT COUNT(*) AS rows, COUNT(DISTINCT form_key) AS forms FROM approved_rows WHERE {where}",
            params).fetchone()
        senders = [r["sending_entity"] for r in conn.execute(
            "SELECT DISTINCT sending_entity FROM approved_rows WHERE approved_at >= ? AND approved_at < ? "
            "AND sending_entity != '' ORDER BY sending_entity", params[:2])]
        sql = f"SELECT * FROM approved_rows WHERE {where} ORDER BY approved_at DESC, form_key, row_index"
        if limit is not None:
            sql += f" LIMIT {int(limit)}"
        rows = [dict(r) for r in conn.execute(sql, params)]
        dupes = _duplicates(conn, rows)
    for row in rows:
        row["can_open"] = bool(row.get("record"))
        row["duplicates"] = dupes.get(row["row_id"], [])
        for heavy in ("record", "source", "search_text", "page_image"):
            row.pop(heavy, None)
    return {"rows": rows, "total_rows": totals["rows"], "forms": totals["forms"],
            "senders": senders, "truncated": len(rows) < totals["rows"]}


def rows_for_export(start: str, end: str, *, path: Path | None = None, **filters) -> list[dict]:
    """Everything in the range and filters, oldest first — no screen limit."""
    where, params = _where(start, end, **filters)
    with _LOCK, _rows_conn(path) as conn:
        return [dict(r) for r in conn.execute(
            f"SELECT * FROM approved_rows WHERE {where} ORDER BY approved_at, form_key, row_index", params)]


def _duplicates(conn: sqlite3.Connection, rows: list[dict]) -> dict[int, list[dict]]:
    """For each row: other approved forms with the same commitment number. Shown, never merged."""
    numbers = sorted({r["commitment_number"] for r in rows if (r["commitment_number"] or "").strip()})
    found: dict[int, list[dict]] = {}
    others: dict[str, list[dict]] = {}
    for start in range(0, len(numbers), 500):
        chunk = numbers[start:start + 500]
        marks = ", ".join("?" for _ in chunk)
        for other in conn.execute(
                "SELECT commitment_number, form_key, source_name, approved_at FROM approved_rows "
                f"WHERE commitment_number IN ({marks})", chunk):
            others.setdefault(other["commitment_number"], []).append(dict(other))
    for row in rows:
        same = [o for o in others.get(row["commitment_number"], []) if o["form_key"] != row["form_key"]]
        if same:
            found[row["row_id"]] = same
    return found


def form_of(key: str, path: Path | None = None) -> dict | None:
    """The saved form behind a panel row: its record (to reopen) and where it came from."""
    with _LOCK, _rows_conn(path) as conn:
        row = conn.execute("SELECT * FROM approved_rows WHERE form_key = ? ORDER BY row_index LIMIT 1",
                           (key,)).fetchone()
    return dict(row) if row else None


def load_batch(batch_id: str, path: Path | None = None) -> tuple[Batch, dict[str, Path]] | None:
    """The approved forms of one upload, rebuilt for the review screen (after a restart),
    and where each one's page image is kept. Forms saved without a full record are skipped."""
    with _LOCK, _rows_conn(path) as conn:
        rows = conn.execute(
            "SELECT record, source, page_image FROM approved_rows WHERE batch_id = ? AND row_index = 0 "
            "AND record IS NOT NULL ORDER BY source_name, page_number", (batch_id,)).fetchall()
    if not rows:
        return None
    batch = Batch(batch_id=batch_id, status="completed")
    images: dict[str, Path] = {}
    for row in rows:
        record = record_from_json(row["record"])
        source = json.loads(row["source"])
        if not any(s.index == source["index"] for s in batch.sources):
            batch.sources.append(SourceFile(**source))
        batch.records.append(record)
        batch.pages.append({"source_index": record.source_index, "page_number": record.page_number,
                            "status": "done", "record_id": record.record_id})
        images[record.record_id] = Path(row["page_image"])
    batch.sources.sort(key=lambda s: s.index)
    batch.records.sort(key=lambda r: (r.source_index, r.page_number))
    batch.total_pages = batch.processed_pages = batch.found_pages = len(batch.records)
    return batch, images


def record_from_json(text: str) -> FormRecord:
    data = json.loads(text)
    known_field = {f.name for f in dataclasses.fields(ExtractedField)}
    fields = {}
    for key, raw in (data.pop("fields", None) or {}).items():
        raw = {k: v for k, v in raw.items() if k in known_field}
        raw["region"] = tuple(raw["region"]) if raw.get("region") else None
        raw["value_regions"] = [tuple(r) if r else None for r in raw.get("value_regions") or []]
        fields[key] = ExtractedField(**raw)
    known = {f.name for f in dataclasses.fields(FormRecord)}
    record = FormRecord(**{k: v for k, v in data.items() if k in known}, fields=fields)
    for spec in FIELDS:  # שדה שנוסף לרשימה אחרי שהטופס נשמר
        record.fields.setdefault(spec.key, ExtractedField(key=spec.key))
    return record


def delete_form(key: str, path: Path | None = None) -> dict | None:
    """Remove one approved form for good: its panel rows, its approved row and its
    kept page image. Returns where it came from, so its other images can go too."""
    with _LOCK, _rows_conn(path) as conn:
        row = conn.execute("SELECT * FROM approved_rows WHERE form_key = ? LIMIT 1", (key,)).fetchone()
        images = [r["page_image"] for r in conn.execute(
            "SELECT page_image FROM approved_forms WHERE form_key = ?", (key,))]
        conn.execute("DELETE FROM approved_rows WHERE form_key = ?", (key,))
        conn.execute("DELETE FROM approved_forms WHERE form_key = ?", (key,))
    if row is None:
        return None
    for image in {*images, row["page_image"]}:
        if image:
            Path(image).unlink(missing_ok=True)
    return dict(row)
