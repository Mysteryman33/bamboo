import os
import json
import requests
from datetime import datetime, date, timedelta
from flask import Flask, request, jsonify, render_template
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__, template_folder=".")

@app.after_request
def add_no_cache_headers(response):
    if request.path == "/" or request.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response

db_url = os.environ.get('DATABASE_URL', 'sqlite:///local_20260503_202810.db')
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.1-8b-instant")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_API_KEY = "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"

# ── MODELS ──────────────────────────────────────────────────────────────────

class Reminder(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    text = db.Column(db.String(500), nullable=False)
    completed = db.Column(db.Boolean, default=False)
    scheduled_date = db.Column(db.String(50), default="")
    schedule_preset = db.Column(db.String(50), default="none")
    schedule_start = db.Column(db.Float, default=0.0)
    notifications_sent = db.Column(db.Integer, default=0)
    notes = db.Column(db.String(2000), default="")
    updated_at = db.Column(db.String(100), default="")
    color = db.Column(db.String(20), default="")
    created_timestamp = db.Column(db.Float, default=0.0)
    completed_date = db.Column(db.String(20), default="")
    due_timestamp = db.Column(db.Float, default=0.0)
    due_label = db.Column(db.String(200), default="")

class CalendarEvent(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(500), nullable=False)
    date = db.Column(db.String(20), nullable=False)
    time = db.Column(db.String(10), default="")
    end_time = db.Column(db.String(10), default="")
    color = db.Column(db.String(20), default="")
    recurring = db.Column(db.String(20), default="none")
    notes = db.Column(db.String(2000), default="")
    created_timestamp = db.Column(db.Float, default=0.0)

with app.app_context():
    db.create_all()
    try:
        with db.engine.connect() as conn:
            from sqlalchemy import text
            migrations = [
                "ALTER TABLE reminder ADD COLUMN created_timestamp FLOAT DEFAULT 0.0",
                "ALTER TABLE reminder ADD COLUMN completed_date VARCHAR(20) DEFAULT ''",
                "ALTER TABLE reminder ADD COLUMN due_timestamp FLOAT DEFAULT 0.0",
                "ALTER TABLE reminder ADD COLUMN due_label VARCHAR(200) DEFAULT ''",
            ]
            for m in migrations:
                try:
                    conn.execute(text(m))
                    conn.commit()
                except Exception:
                    pass
    except Exception:
        pass

# ── HELPERS ─────────────────────────────────────────────────────────────────

def r_to_dict(r):
    return {
        "id": r.id, "text": r.text, "completed": r.completed,
        "scheduled_date": r.scheduled_date, "schedule_preset": r.schedule_preset,
        "schedule_start": r.schedule_start, "notifications_sent": r.notifications_sent,
        "notes": r.notes, "updated_at": r.updated_at, "color": r.color,
        "created_timestamp": r.created_timestamp or 0.0,
        "completed_date": r.completed_date or "",
        "due_timestamp": r.due_timestamp or 0.0,
        "due_label": r.due_label or "",
    }

def e_to_dict(e):
    return {
        "id": e.id, "title": e.title, "date": e.date, "time": e.time,
        "end_time": e.end_time, "color": e.color,
        "recurring": e.recurring, "notes": e.notes,
        "created_timestamp": e.created_timestamp or 0.0
    }

def ms_to_date_str(ms):
    try:
        if not ms:
            return ""
        return datetime.fromtimestamp(float(ms) / 1000).strftime('%Y-%m-%d')
    except Exception:
        return ""

def event_occurs_on(ev, target_date):
    try:
        base = datetime.strptime(ev.get("date", ""), "%Y-%m-%d").date()
        target = datetime.strptime(target_date, "%Y-%m-%d").date()
    except Exception:
        return False
    recurring = ev.get("recurring") or "none"
    if recurring == "none":
        return base == target
    if target < base:
        return False
    if recurring == "daily":
        return True
    if recurring == "weekdays":
        return target.weekday() < 5
    weekday_aliases = {
        "sunday": 6, "sundays": 6,
        "monday": 0, "mondays": 0,
        "tuesday": 1, "tuesdays": 1,
        "wednesday": 2, "wednesdays": 2,
        "thursday": 3, "thursdays": 3,
        "friday": 4, "fridays": 4,
        "saturday": 5, "saturdays": 5,
    }
    if recurring in weekday_aliases:
        return target.weekday() == weekday_aliases[recurring]
    if recurring == "weekly":
        return target.weekday() == base.weekday()
    if recurring == "monthly":
        return target.day == base.day
    return False

def weekday_name(date_str):
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").strftime("%A").lower()
    except Exception:
        return ""

WEEKDAY_ALIASES = {
    "sunday": "sunday", "sundays": "sunday",
    "monday": "monday", "mondays": "monday",
    "tuesday": "tuesday", "tuesdays": "tuesday",
    "wednesday": "wednesday", "wednesdays": "wednesday",
    "thursday": "thursday", "thursdays": "thursday",
    "friday": "friday", "fridays": "friday",
    "saturday": "saturday", "saturdays": "saturday",
}
WEEKDAY_INDEX = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
}
ALLOWED_RECURRING = {"none", "daily", "weekly", "weekdays", "monthly"}

def task_key(text):
    return " ".join((text or "").lower().split())

def next_date_for_weekday(day_name):
    day = WEEKDAY_ALIASES.get(str(day_name or "").lower())
    if not day:
        return datetime.now().strftime("%Y-%m-%d")
    today_dt = datetime.now().date()
    delta = (WEEKDAY_INDEX[day] - today_dt.weekday()) % 7
    return (today_dt + timedelta(days=delta)).strftime("%Y-%m-%d")

def current_week_date_for_weekday(day_name):
    day = WEEKDAY_ALIASES.get(str(day_name or "").lower())
    if not day:
        return datetime.now().strftime("%Y-%m-%d")
    today_dt = datetime.now().date()
    sunday = today_dt - timedelta(days=(today_dt.weekday() + 1) % 7)
    sunday_based = {"sunday": 0, "monday": 1, "tuesday": 2, "wednesday": 3, "thursday": 4, "friday": 5, "saturday": 6}
    return (sunday + timedelta(days=sunday_based[day])).strftime("%Y-%m-%d")

def sanitize_color(value):
    value = value or ""
    if isinstance(value, str) and len(value) == 7 and value.startswith("#"):
        try:
            int(value[1:], 16)
            return value
        except ValueError:
            return ""
    return ""

def plan_color_for_task(task, item_type="task"):
    text = task_key(f"{task} {item_type}")
    if any(w in text for w in ["breakfast", "lunch", "dinner", "meal", "food", "cook", "snack"]):
        return "#d99a6c"
    if any(w in text for w in ["study", "school", "test", "quiz", "exam", "homework", "assignment", "project", "essay", "read", "work", "socials", "math", "science"]):
        return "#7d9ad6"
    if any(w in text for w in ["exercise", "workout", "run", "walk", "gym", "cardio", "sport", "practice"]):
        return "#6f8f84"
    if any(w in text for w in ["relax", "wind", "sleep", "bed", "skincare", "face care", "shower", "routine", "personal"]):
        return "#9b83c9"
    if any(w in text for w in ["break", "free time", "rest"]):
        return "#8fc49e"
    return "#6f8f84"

def clean_task_text(text):
    import re
    return re.sub(r"\s+([,.!?])", r"\1", re.sub(r"\s+", " ", str(text or ""))).strip()

def reminder_color_for_text(text, fallback=""):
    color = sanitize_color(fallback)
    if color:
        return color
    text = task_key(text)
    if any(w in text for w in ["breakfast", "lunch", "dinner", "meal", "food", "cook", "snack"]):
        return "#d99a6c"
    if any(w in text for w in ["study", "school", "test", "quiz", "exam", "homework", "assignment", "project", "essay", "read", "work", "socials", "math", "science"]):
        return "#7d9ad6"
    if any(w in text for w in ["exercise", "workout", "run", "walk", "gym", "cardio", "sport", "practice"]):
        return "#6f8f84"
    if any(w in text for w in ["relax", "wind", "sleep", "bed", "skincare", "face care", "shower", "routine", "personal"]):
        return "#9b83c9"
    if any(w in text for w in ["break", "free time", "rest"]):
        return "#8fc49e"
    return ""

def normalize_hhmm(value):
    import re
    s = str(value or "").strip()
    m = re.match(r"^(\d{1,2}):(\d{2})$", s)
    if not m:
        return ""
    h, minute = int(m.group(1)), int(m.group(2))
    if h < 0 or h > 23 or minute < 0 or minute > 59:
        return ""
    return f"{h:02d}:{minute:02d}"

def format_clock_label(hhmm):
    value = normalize_hhmm(hhmm)
    if not value:
        return ""
    h, minute = [int(x) for x in value.split(":")]
    suffix = "AM" if h < 12 else "PM"
    hour = h % 12 or 12
    return f"{hour}:{minute:02d} {suffix}"

def build_due_label(due_date, time="", end_time=""):
    try:
        due = datetime.strptime(due_date, "%Y-%m-%d").date()
    except Exception:
        return ""
    today = datetime.now().date()
    if due == today:
        label = "today"
    elif due == today + timedelta(days=1):
        label = "tomorrow"
    else:
        label = due.strftime("%b %-d") if os.name != "nt" else due.strftime("%b %#d")
    time_label = format_clock_label(time)
    if time_label:
        end_label = format_clock_label(end_time)
        label = f"{label} {time_label}{' - ' + end_label if end_label else ''}"
    return label

DAY_START_MIN = 5 * 60
FLEX_DAY_START_MIN = 6 * 60
DAY_END_MIN = 23 * 60

def parse_hhmm(value):
    try:
        if not value or ":" not in str(value):
            return None
        h, m = str(value).split(":", 1)
        h, m = int(h), int(m)
        if h < 0 or h > 23 or m < 0 or m > 59:
            return None
        return h * 60 + m
    except Exception:
        return None

def mins_to_hhmm(mins):
    mins = int(max(0, min(23 * 60 + 59, mins)))
    return f"{mins // 60:02d}:{mins % 60:02d}"

def normalize_plan_duration(value, default=30):
    try:
        duration = int(round(float(value)))
    except Exception:
        duration = default
    return max(5, min(180, duration))

def ranges_overlap(a_start, a_end, b_start, b_end):
    return a_start < b_end and b_start < a_end

def calendar_blocks_for_date(events, target_date):
    blocks = []
    for ev in events or []:
        if not event_occurs_on(ev, target_date):
            continue
        start = parse_hhmm(ev.get("time", ""))
        if start is None:
            continue
        end = parse_hhmm(ev.get("end_time", ""))
        if end is None or end <= start:
            end = start + 60
        start = max(DAY_START_MIN, start)
        end = min(DAY_END_MIN, end)
        if end > start:
            blocks.append({"start": start, "end": end, "title": ev.get("title", "")})
    return sorted(blocks, key=lambda b: (b["start"], b["end"]))

def plan_blocks_for_date(plan_items, target_date, selected_date=""):
    if selected_date and selected_date != target_date:
        return []
    blocks = []
    for item in plan_items or []:
        if not isinstance(item, dict):
            continue
        start = parse_hhmm(item.get("time", ""))
        if start is None:
            continue
        duration = normalize_plan_duration(item.get("duration", 30), 30)
        end = min(DAY_END_MIN, start + duration)
        if end > start:
            blocks.append({"start": start, "end": end, "title": item.get("task", ""), "source": "plan"})
    return sorted(blocks, key=lambda b: (b["start"], b["end"]))

def merge_busy_blocks(blocks):
    merged = []
    for b in sorted(blocks or [], key=lambda x: (x["start"], x["end"])):
        if not merged or b["start"] > merged[-1]["end"]:
            merged.append({**b, "titles": [b.get("title", "")] if b.get("title") else []})
        else:
            merged[-1]["end"] = max(merged[-1]["end"], b["end"])
            if b.get("title"):
                merged[-1].setdefault("titles", []).append(b["title"])
    return merged

def free_windows_for_blocks(blocks, earliest=DAY_START_MIN, latest=DAY_END_MIN, min_duration=15):
    windows = []
    cursor = max(DAY_START_MIN, int(earliest or DAY_START_MIN))
    latest = min(DAY_END_MIN, int(latest or DAY_END_MIN))
    for b in merge_busy_blocks(blocks):
        if b["start"] - cursor >= min_duration:
            windows.append({"start": cursor, "end": b["start"], "minutes": b["start"] - cursor})
        cursor = max(cursor, b["end"])
    if latest - cursor >= min_duration:
        windows.append({"start": cursor, "end": latest, "minutes": latest - cursor})
    return windows

def dates_for_context(message, ui_state, today):
    dates = []
    def add(ds):
        try:
            datetime.strptime(ds, "%Y-%m-%d")
        except Exception:
            return
        if ds not in dates:
            dates.append(ds)
    selected = (ui_state or {}).get("selected_plan_date") or today
    add(selected)
    msg = (message or "").lower()
    base = datetime.strptime(today, "%Y-%m-%d").date()
    if "today" in msg:
        add(today)
    if "tomorrow" in msg:
        add((base + timedelta(days=1)).strftime("%Y-%m-%d"))
    for day in weekdays_from_text(msg):
        add(next_date_for_weekday(day))
    return dates[:3] or [today]

def availability_context_for(message, events, day_plan, ui_state, today):
    selected = (ui_state or {}).get("selected_plan_date") or today
    now_dt = datetime.now()
    context = []
    for ds in dates_for_context(message, ui_state, today):
        earliest = DAY_START_MIN
        if ds == today:
            earliest = max(DAY_START_MIN, now_dt.hour * 60 + now_dt.minute)
        calendar_blocks = [{**b, "source": "calendar"} for b in calendar_blocks_for_date(events, ds)]
        plan_blocks = plan_blocks_for_date(day_plan, ds, selected)
        busy = merge_busy_blocks(calendar_blocks + plan_blocks)
        free = free_windows_for_blocks(busy, earliest=earliest)
        context.append({
            "date": ds,
            "weekday": weekday_name(ds),
            "busy": [
                {"time": f"{mins_to_hhmm(b['start'])}-{mins_to_hhmm(b['end'])}", "title": ", ".join((b.get("titles") or [])[:2])}
                for b in busy[:10]
            ],
            "free": [
                {"time": f"{mins_to_hhmm(w['start'])}-{mins_to_hhmm(w['end'])}", "minutes": w["minutes"]}
                for w in free[:8]
            ],
        })
    return context

def next_open_start(start, duration, occupied):
    latest_start = DAY_END_MIN - normalize_plan_duration(duration)
    if latest_start < DAY_START_MIN:
        return None
    start = max(DAY_START_MIN, min(int(start), latest_start))
    for _ in range(80):
        end = start + duration
        if end > DAY_END_MIN:
            return None
        conflict = next((b for b in occupied if ranges_overlap(start, end, b["start"], b["end"])), None)
        if not conflict:
            return start
        start = max(start + 5, conflict["end"])
        if start > latest_start:
            return None
    return None

def sanitize_day_plan(raw_plan, events, target_date, earliest_min=DAY_START_MIN):
    occupied = calendar_blocks_for_date(events, target_date)
    items = []
    seen = set()
    earliest = max(DAY_START_MIN, min(DAY_END_MIN, int(earliest_min or DAY_START_MIN)))
    raw_items = raw_plan if isinstance(raw_plan, list) else []
    for p in sorted(raw_items, key=lambda x: parse_hhmm((x or {}).get("time", "")) or DAY_START_MIN):
        if not isinstance(p, dict):
            continue
        task = str(p.get("task") or p.get("title") or "").strip()
        if not task:
            continue
        duration = normalize_plan_duration(p.get("duration", 30))
        start = parse_hhmm(p.get("time", ""))
        if start is None:
            start = earliest
        latest_start = DAY_END_MIN - duration
        if latest_start < DAY_START_MIN:
            continue
        start = max(start, earliest)
        start = min(start, latest_start)
        start = next_open_start(start, duration, occupied)
        if start is None:
            continue
        tkey = task_key(task)
        if (tkey == "breakfast" and start > 11 * 60) or (tkey == "lunch" and start > 15 * 60) or (tkey == "dinner" and (start < 16 * 60 or start > 23 * 60)):
            continue
        key = (task_key(task), start)
        if key in seen:
            continue
        seen.add(key)
        item_type = str(p.get("type") or "task").lower()
        if item_type not in {"task", "event", "break", "meal"}:
            item_type = "task"
        color = sanitize_color(p.get("color", "")) or plan_color_for_task(task, item_type)
        items.append({
            "time": mins_to_hhmm(start),
            "task": task[:80],
            "duration": duration,
            "color": color,
            "type": item_type,
        })
        occupied.append({"start": start, "end": start + duration, "title": task})
        occupied.sort(key=lambda b: (b["start"], b["end"]))
        if len(items) >= 14:
            break
    return items

def prep_items_for_upcoming(events, target_date, earliest_min):
    prep_words = ("test", "quiz", "exam", "final", "project", "presentation", "assignment", "essay", "due")
    try:
        target_dt = datetime.strptime(target_date, "%Y-%m-%d").date()
    except Exception:
        return []
    items = []
    slot = max(DAY_START_MIN, earliest_min)
    for offset in range(1, 5):
        ds = (target_dt + timedelta(days=offset)).strftime("%Y-%m-%d")
        for ev in events or []:
            if not event_occurs_on(ev, ds):
                continue
            title = str(ev.get("title", "")).strip()
            notes = str(ev.get("notes", "")).strip()
            text = f"{title} {notes}".lower()
            if not title or not any(w in text for w in prep_words):
                continue
            verb = "study for" if any(w in text for w in ("test", "quiz", "exam", "final")) else "work on"
            items.append({"time": mins_to_hhmm(slot), "task": f"{verb} {title}"[:80], "duration": 45 if offset <= 2 else 30, "color": "#7d9ad6", "type": "task"})
            slot += 60
            if len(items) >= 3:
                return items
    return items

def fallback_day_plan(reminders, events, current_task, pinned_plan, existing_plan, target_date, earliest_min):
    draft = []
    if existing_plan:
        draft.extend(existing_plan[:14])
    if current_task:
        draft.append({"time": mins_to_hhmm(earliest_min), "task": current_task, "duration": 30, "color": "#6f8f84", "type": "task"})
    draft.extend(pinned_plan or [])
    existing_keys = {task_key(p.get("task") or p.get("title")) for p in draft if isinstance(p, dict)}
    for prep in prep_items_for_upcoming(events, target_date, earliest_min):
        if task_key(prep["task"]) not in existing_keys:
            draft.append(prep)
            existing_keys.add(task_key(prep["task"]))
    slot = max(DAY_START_MIN, earliest_min)
    for r in reminders or []:
        if r.get("completed"):
            continue
        if not is_plannable_reminder_text(r.get("text", "")):
            continue
        due_date = ms_to_date_str(r.get("due_timestamp", 0))
        if due_date and due_date > target_date:
            continue
        if due_date and calendar_has_similar_event(events, r.get("text", ""), due_date):
            continue
        draft.append({"time": mins_to_hhmm(slot), "task": r.get("text", "")[:80], "duration": 30, "color": r.get("color") or None, "type": "task"})
        slot += 45
        if len(draft) >= 10:
            break
    if not draft:
        if earliest_min < 10 * 60:
            draft.append({"time": "08:00", "task": "breakfast", "duration": 30, "color": "#d99a6c", "type": "meal"})
        if earliest_min < 14 * 60:
            draft.append({"time": "12:30", "task": "lunch", "duration": 30, "color": "#d99a6c", "type": "meal"})
        if earliest_min < 20 * 60:
            draft.append({"time": "18:30", "task": "dinner", "duration": 45, "color": "#d99a6c", "type": "meal"})
        if earliest_min < 22 * 60 + 30:
            draft.append({"time": "22:15", "task": "wind down", "duration": 30, "color": "#9b83c9", "type": "break"})
    return sanitize_day_plan(draft, events, target_date, earliest_min)

def calendar_has_similar_event(events, title, target_date):
    key = task_key(title)
    if not key or not target_date:
        return False
    for ev in events or []:
        if task_key(ev.get("title", "")) == key and event_occurs_on(ev, target_date):
            return True
    return False

def is_plannable_reminder_text(text):
    key = task_key(text)
    if not key or key in {"hi", "hello", "hey", "test", "ok", "okay", "yo"}:
        return False
    return len(key) >= 3

def event_needs_prep(ev):
    text = task_key(f"{ev.get('title', '')} {ev.get('notes', '')}")
    if not text:
        return False
    prep_words = ("test", "quiz", "exam", "final", "project", "presentation", "assignment", "essay", "due")
    return any(w in text for w in prep_words)

def similar_task_key(a, b, threshold=0.86):
    from difflib import SequenceMatcher
    a, b = task_key(a), task_key(b)
    if not a or not b:
        return False
    if a == b or a in b or b in a:
        return True
    return SequenceMatcher(None, a, b).ratio() >= threshold

def is_meal_task(text):
    return task_key(text) in {"breakfast", "lunch", "dinner"}

def prep_target_key(task):
    key = task_key(task)
    for prefix in ("study for ", "review ", "prep for ", "work on "):
        if key.startswith(prefix):
            key = key[len(prefix):]
    if key.endswith(" prep"):
        key = key[:-5]
    return task_key(key)

def collect_upcoming_prep(events, target_date, target_dt, horizon_days=10):
    upcoming = []
    for offset in range(0, horizon_days + 1):
        ds = (target_dt + timedelta(days=offset)).strftime("%Y-%m-%d")
        for e in events or []:
            if not event_occurs_on(e, ds) or not event_needs_prep(e):
                continue
            title = clean_task_text(e.get("title", ""))
            if not title:
                continue
            existing = next((u for u in upcoming if similar_task_key(u["title"], title)), None)
            if existing:
                if ds < existing["date"]:
                    existing.update({"date": ds, "days_away": offset, "time": e.get("time", ""), "notes": str(e.get("notes", ""))[:80]})
                continue
            upcoming.append({
                "title": title[:70],
                "date": ds,
                "days_away": offset,
                "time": e.get("time", ""),
                "notes": str(e.get("notes", ""))[:80],
                "urgency": "today" if offset == 0 else "tomorrow" if offset == 1 else f"{offset} days",
            })
    return sorted(upcoming, key=lambda u: (u["days_away"], u.get("time") or "99:99", u["title"]))[:8]

def collect_plannable_reminders(reminders, events, target_date):
    out = []
    for r in reminders or []:
        if r.get("completed"):
            continue
        text = clean_task_text(r.get("text", ""))
        if not is_plannable_reminder_text(text):
            continue
        due_date = ms_to_date_str(r.get("due_timestamp", 0))
        if due_date and due_date > target_date:
            continue
        if due_date and calendar_has_similar_event(events, text, due_date):
            continue
        if any(similar_task_key(x["text"], text) for x in out):
            continue
        out.append({
            "text": text[:70],
            "due_date": due_date,
            "due_label": str(r.get("due_label", ""))[:40],
            "color": sanitize_color(r.get("color", "")),
        })
    return out[:12]

def build_planner_context(reminders, events, pinned_plan, existing_plan, target_date, target_dt, earliest_min):
    hard_blocks_raw = calendar_blocks_for_date(events, target_date)
    hard_blocks = [{"title": b["title"][:70], "start": mins_to_hhmm(b["start"]), "end": mins_to_hhmm(b["end"])} for b in hard_blocks_raw]
    free_windows = [
        {"start": mins_to_hhmm(w["start"]), "end": mins_to_hhmm(w["end"]), "minutes": w["minutes"]}
        for w in free_windows_for_blocks(hard_blocks_raw, earliest=earliest_min, min_duration=20)
    ]
    today_events = [e for e in events if event_occurs_on(e, target_date)]
    scheduled = [{
        "title": str(e.get("title", ""))[:70],
        "time": e.get("time", ""),
        "end_time": e.get("end_time", ""),
        "recurring": e.get("recurring", "none"),
        "notes": str(e.get("notes", ""))[:80],
    } for e in today_events[:18]]
    pinned = [{"time": p.get("time", ""), "task": str(p.get("task", ""))[:70], "duration": p.get("duration", 30), "color": p.get("color", ""), "source": p.get("source", "")} for p in pinned_plan[:8]]
    existing = [{"time": p.get("time", ""), "task": str(p.get("task", ""))[:70], "duration": p.get("duration", 30), "source": p.get("source", "generated")} for p in existing_plan[:14]]
    return {
        "hard_blocks": hard_blocks,
        "free_windows": free_windows,
        "scheduled_events": scheduled,
        "reminders": collect_plannable_reminders(reminders, events, target_date),
        "upcoming_prep": collect_upcoming_prep(events, target_date, target_dt),
        "locked_plan": pinned,
        "previous_plan": existing,
    }

def add_basic_day_items(raw_plan, events, target_date, earliest_min):
    plan = [p for p in (raw_plan or []) if isinstance(p, dict)]
    keys = {task_key(p.get("task", "")) for p in plan}
    has_meal_event = {task_key(e.get("title", "")) for e in events if event_occurs_on(e, target_date) and is_meal_task(e.get("title", ""))}
    basics = []
    def add_meal(task, preferred, duration):
        key = task_key(task)
        if key in keys or key in has_meal_event:
            return
        if key == "breakfast" and earliest_min > 10 * 60:
            return
        if key == "lunch" and earliest_min > 14 * 60:
            return
        if key == "dinner" and earliest_min > 20 * 60 + 30:
            return
        start = max(preferred, earliest_min)
        basics.append({"time": mins_to_hhmm(start), "task": task, "duration": duration, "color": "#d99a6c", "type": "meal"})
        keys.add(key)
    add_meal("breakfast", 7 * 60 + 30, 30)
    add_meal("lunch", 12 * 60 + 30, 30)
    add_meal("dinner", 18 * 60 + 30, 45)
    return basics + plan

def polish_day_plan(plan, events, reminders, target_date, earliest_min):
    prep_sources = collect_upcoming_prep(events, target_date, datetime.strptime(target_date, "%Y-%m-%d").date())
    known_prep = [prep_target_key(u["title"]) for u in prep_sources]
    reminder_keys = [task_key(r["text"]) for r in collect_plannable_reminders(reminders, events, target_date)]
    low_value = {"morning routine", "review tomorrow schedule", "review tomorrows schedule", "review tomorrow's schedule", "prepare for bed", "begin winding down"}
    polished, seen, prep_seen = [], [], []
    focus_minutes = 0
    downtime_added = False
    for item in plan or []:
        if not isinstance(item, dict):
            continue
        task = clean_task_text(item.get("task", ""))
        if task:
            task = task[0].lower() + task[1:]
        key = task_key(task)
        if not key or key in low_value:
            continue
        is_prep = any(w in key for w in ("study", "review", "prep", "test", "quiz", "exam", "assignment", "project", "essay"))
        if not is_prep and any(similar_task_key(key, s) for s in seen):
            continue
        matched_prep = next((p for p in known_prep if p and (similar_task_key(prep_target_key(key), p) or p in key)), "")
        if is_prep and not matched_prep:
            continue
        if matched_prep:
            if any(similar_task_key(matched_prep, p) for p in prep_seen):
                continue
            prep_seen.append(matched_prep)
        if key in reminder_keys or matched_prep or is_meal_task(key) or not is_prep:
            duration = normalize_plan_duration(item.get("duration", 30))
            if key in {"relax", "relaxation", "relaxation time", "free time", "downtime"}:
                if downtime_added:
                    continue
                duration = min(duration, 45)
                item["type"] = "break"
                task = "free time" if "free" in key or "relax" in key else task
                downtime_added = True
            if is_prep:
                if focus_minutes >= 165:
                    continue
                duration = min(duration, 75)
                focus_minutes += duration
            item["duration"] = duration
            item["task"] = task[:80]
            polished.append(item)
            seen.append(key)
    return polished

def supplement_urgent_prep(plan, events, target_date, earliest_min):
    upcoming = [u for u in collect_upcoming_prep(events, target_date, datetime.strptime(target_date, "%Y-%m-%d").date()) if u["days_away"] <= 1]
    if not upcoming:
        return plan
    out = [dict(p) for p in (plan or []) if isinstance(p, dict)]
    existing_targets = [prep_target_key(p.get("task", "")) for p in out]
    focus_minutes = sum(normalize_plan_duration(p.get("duration", 30)) for p in out if prep_target_key(p.get("task", "")) in existing_targets and any(w in task_key(p.get("task", "")) for w in ("study", "review", "prep", "test", "quiz", "exam")))
    for u in upcoming:
        target = prep_target_key(u["title"])
        if any(similar_task_key(target, existing) for existing in existing_targets):
            continue
        if focus_minutes >= 150:
            break
        replacement_idx = next((i for i, p in enumerate(out) if task_key(p.get("task", "")) in {"free time", "relax", "relaxation", "relaxation time", "downtime", "break"}), None)
        item = {"time": mins_to_hhmm(earliest_min), "task": f"study for {u['title']}", "duration": 45, "color": "#7d9ad6", "type": "task"}
        if replacement_idx is not None:
            item["time"] = out[replacement_idx].get("time") or item["time"]
            out[replacement_idx] = item
        else:
            latest = earliest_min
            for p in out:
                start = parse_hhmm(p.get("time", ""))
                if start is not None:
                    latest = max(latest, start + normalize_plan_duration(p.get("duration", 30)))
            item["time"] = mins_to_hhmm(latest)
            out.append(item)
        existing_targets.append(target)
        focus_minutes += 45
    return out

def finalize_day_plan(raw_plan, reminders, events, target_date, earliest_min):
    with_basics = add_basic_day_items(raw_plan, events, target_date, earliest_min)
    sanitized = sanitize_day_plan(with_basics, events, target_date, earliest_min)
    polished = polish_day_plan(sanitized, events, reminders, target_date, earliest_min)
    polished = supplement_urgent_prep(polished, events, target_date, earliest_min)
    final = sanitize_day_plan(add_basic_day_items(polished, events, target_date, earliest_min), events, target_date, earliest_min)
    return final[:12]

def smart_fallback_day_plan(reminders, events, current_task, pinned_plan, existing_plan, target_date, target_dt, earliest_min):
    context = build_planner_context(reminders, events, pinned_plan, existing_plan, target_date, target_dt, earliest_min)
    draft = []
    if current_task:
        draft.append({"time": mins_to_hhmm(earliest_min), "task": current_task, "duration": 30, "color": plan_color_for_task(current_task), "type": "task"})
    draft.extend(pinned_plan or [])
    if existing_plan:
        draft.extend(existing_plan[:8])
    slot = earliest_min
    for r in context["reminders"][:4]:
        draft.append({"time": mins_to_hhmm(slot), "task": r["text"], "duration": 30, "color": r.get("color") or plan_color_for_task(r["text"]), "type": "task"})
        slot += 45
    for u in context["upcoming_prep"][:3]:
        duration = 60 if u["days_away"] <= 1 else 45
        draft.append({"time": mins_to_hhmm(slot), "task": f"study for {u['title']}", "duration": duration, "color": "#7d9ad6", "type": "task"})
        slot += duration + 15
    return finalize_day_plan(draft, reminders, events, target_date, earliest_min)

def parse_time_text_to_min(raw):
    raw = str(raw or "").strip().lower().replace(".", "")
    m = __import__("re").match(r"^(\d{1,2})(?::(\d{2}))?\s*(am|pm)?$", raw)
    if not m:
        return None
    h = int(m.group(1))
    minute = int(m.group(2) or 0)
    mer = m.group(3)
    if h > 23 or minute > 59:
        return None
    if mer == "pm" and h < 12:
        h += 12
    if mer == "am" and h == 12:
        h = 0
    return h * 60 + minute

def parse_time_range_from_text(text):
    import re
    msg = str(text or "").lower()
    m = re.search(r"(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)\s*(?:-|–|—|to|until|till)\s*(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)", msg)
    if not m:
        return None
    start = parse_time_text_to_min(m.group(1))
    end = parse_time_text_to_min(m.group(2))
    if start is None or end is None:
        return None
    if end <= start and end < 12 * 60:
        end += 12 * 60
    if end <= start:
        return None
    return mins_to_hhmm(start), mins_to_hhmm(end)

def weekdays_from_text(text):
    import re
    msg = str(text or "").lower()
    order = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    aliases = {
        "mon": "monday", "monday": "monday", "mondays": "monday",
        "tue": "tuesday", "tues": "tuesday", "tuesday": "tuesday", "tuesdays": "tuesday",
        "wed": "wednesday", "weds": "wednesday", "wednesday": "wednesday", "wednesdays": "wednesday",
        "thu": "thursday", "thur": "thursday", "thurs": "thursday", "thursday": "thursday", "thursdays": "thursday",
        "fri": "friday", "friday": "friday", "fridays": "friday",
        "sat": "saturday", "saturday": "saturday", "saturdays": "saturday",
        "sun": "sunday", "sunday": "sunday", "sundays": "sunday",
    }
    range_match = re.search(r"\b(mon(?:days?)?|tues?(?:days?)?|wed(?:nesdays?)?|thu(?:rs?|rsday|rsdays)?|fri(?:days?)?|sat(?:urdays?)?|sun(?:days?)?)\b\s*(?:-|–|—|to|through|thru)\s*\b(mon(?:days?)?|tues?(?:days?)?|wed(?:nesdays?)?|thu(?:rs?|rsday|rsdays)?|fri(?:days?)?|sat(?:urdays?)?|sun(?:days?)?)\b", msg)
    if range_match:
        start = aliases.get(range_match.group(1))
        end = aliases.get(range_match.group(2))
        if start and end:
            a, b = order.index(start), order.index(end)
            if a <= b:
                return order[a:b + 1]
    found = []
    for token in re.findall(r"\b(mon(?:days?)?|tues?(?:days?)?|wed(?:nesdays?)?|thu(?:rs?|rsday|rsdays)?|fri(?:days?)?|sat(?:urdays?)?|sun(?:days?)?)\b", msg):
        day = aliases.get(token)
        if day and day not in found:
            found.append(day)
    return found

def normalize_ai_actions(actions, user_message=""):
    """Repair common model-shaped action mistakes before the client executes them."""
    if not isinstance(actions, list):
        return []
    allowed_types = {
        "add_reminder", "complete_reminder", "delete_reminder", "update_reminder",
        "add_event", "add_weekly_schedule", "delete_event", "update_event",
        "add_plan_item", "add_plan_items", "update_plan_item", "update_plan_items",
        "delete_plan_item", "delete_plan_items", "update_day_plan",
        "clear_day_plan", "clear_calendar", "clear_reminders", "clear_everything",
        "clear_conversation", "generate_day_plan", "set_timer", "cancel_timer",
        "set_current_task", "clear_current_task", "set_view", "set_sort",
        "select_calendar_day",
    }
    list_actions = [dict(a) for a in actions if isinstance(a, dict) and a.get("type") in allowed_types]
    used = set()
    out = []
    today = datetime.now().strftime("%Y-%m-%d")
    msg = (user_message or "").lower()
    msg_days = weekdays_from_text(msg)
    msg_time_range = parse_time_range_from_text(msg)

    for i, action in enumerate(list_actions):
        if i in used:
            continue
        if "end" in action and "end_time" not in action:
            action["end_time"] = action.pop("end")
        if "rec" in action and "recurring" not in action:
            action["recurring"] = action.pop("rec")
        if action.get("type") in ("add_event", "update_event") and msg_days and msg_time_range:
            title = str(action.get("title") or "").strip()
            if not title:
                title = "school" if "school" in msg else ""
            if title:
                out.append({
                    "type": "add_weekly_schedule",
                    "title": title,
                    "items": [{"day": day, "time": msg_time_range[0], "end_time": msg_time_range[1], "notes": action.get("notes") or ""} for day in msg_days],
                    "color": sanitize_color(action.get("color")),
                    "notes": action.get("notes") or "",
                })
                used.add(i)
                continue
        if (
            action.get("type") == "add_event"
            and "weekday" in msg
            and "monday" in msg
            and action.get("time")
        ):
            title_key = task_key(action.get("title"))
            siblings = [
                (j, other) for j, other in enumerate(list_actions)
                if j != i and j not in used and other.get("type") == "add_event"
                and task_key(other.get("title")) == title_key
                and (other.get("time") or "") == (action.get("time") or "")
                and (other.get("end_time") or "") != (action.get("end_time") or "")
            ]
            if siblings:
                sibling_idx, sibling = siblings[0]
                base, monday = action, sibling
                if (sibling.get("recurring") or "none").lower() in ("daily", "weekdays", "weekly"):
                    base, monday = sibling, action
                items = [{"day": "monday", "time": monday.get("time") or base.get("time") or "", "end_time": monday.get("end_time") or "", "notes": monday.get("notes") or ""}]
                for day in ["tuesday", "wednesday", "thursday", "friday"]:
                    items.append({"day": day, "time": base.get("time") or "", "end_time": base.get("end_time") or "", "notes": base.get("notes") or ""})
                out.append({
                    "type": "add_weekly_schedule",
                    "title": action.get("title") or sibling.get("title") or "",
                    "items": items,
                    "color": sanitize_color(action.get("color") or sibling.get("color")),
                    "notes": action.get("notes") or sibling.get("notes") or "",
                })
                used.add(i)
                used.add(sibling_idx)
                continue
        if action.get("type") == "add_event" and str(action.get("recurring", "")).lower() == "weekdays":
            title_key = task_key(action.get("title"))
            overrides = []
            for j, other in enumerate(list_actions):
                if i == j or j in used or other.get("type") != "add_event":
                    continue
                day = WEEKDAY_ALIASES.get(str(other.get("recurring", "")).lower())
                if day and task_key(other.get("title")) == title_key:
                    overrides.append((j, day, other))
            if overrides:
                items = []
                override_days = set()
                for idx, day, other in overrides:
                    used.add(idx)
                    override_days.add(day)
                    items.append({
                        "day": day,
                        "time": other.get("time") or action.get("time") or "",
                        "end_time": other.get("end_time") or action.get("end_time") or "",
                        "notes": other.get("notes") or action.get("notes") or "",
                    })
                for day in ["monday", "tuesday", "wednesday", "thursday", "friday"]:
                    if day not in override_days:
                        items.append({
                            "day": day,
                            "time": action.get("time") or "",
                            "end_time": action.get("end_time") or "",
                            "notes": action.get("notes") or "",
                        })
                out.append({
                    "type": "add_weekly_schedule",
                    "title": action.get("title") or "",
                    "items": items,
                    "color": sanitize_color(action.get("color")),
                    "notes": action.get("notes") or "",
                })
                used.add(i)
                continue

        if action.get("type") in ("add_event", "update_event"):
            if action.get("type") == "update_event":
                for field in ["title", "date", "time", "end_time"]:
                    if field in action and (action.get(field) is None or str(action.get(field)).strip() == ""):
                        action.pop(field, None)
            day = WEEKDAY_ALIASES.get(str(action.get("recurring", "")).lower())
            if day:
                action["recurring"] = "weekly"
                if not action.get("date") or action.get("date") == "*":
                    action["date"] = current_week_date_for_weekday(day)
            elif "recurring" in action and str(action.get("recurring", "none")).lower() not in ALLOWED_RECURRING:
                action["recurring"] = "none"
            elif "recurring" in action:
                action["recurring"] = str(action.get("recurring", "none")).lower()
            if action.get("type") == "add_event" and (not action.get("date") or action.get("date") == "*"):
                action["date"] = today
            if action.get("type") == "add_event" and action.get("recurring") == "weekdays" and "weekday" in msg:
                action["date"] = current_week_date_for_weekday("monday")
            if "color" in action:
                action["color"] = sanitize_color(action.get("color"))

        if action.get("type") == "add_weekly_schedule":
            fixed_items = []
            for item in action.get("items", []):
                if not isinstance(item, dict):
                    continue
                day = WEEKDAY_ALIASES.get(str(item.get("day", "")).lower())
                if day:
                    fixed_items.append({**item, "day": day})
            action["items"] = fixed_items
            action["color"] = sanitize_color(action.get("color"))

        if action.get("type") == "update_day_plan" and not isinstance(action.get("plan"), list):
            task = action.get("task") or action.get("title")
            if task and action.get("time"):
                action = {
                    "type": "add_plan_item",
                    "time": action.get("time"),
                    "task": task,
                    "duration": action.get("duration") or 30,
                    "color": sanitize_color(action.get("color")),
                }

        out.append(action)
    return out

def repair_recurring_event_anchor(ev):
    """Keep recurring schedule anchors close without moving them onto the wrong weekday."""
    recurring = (ev.recurring or "none").lower()
    if recurring not in {"weekly", "weekdays"}:
        return False
    try:
        base = datetime.strptime(ev.date, "%Y-%m-%d").date()
    except Exception:
        return False
    today_dt = datetime.now().date()
    if base < today_dt - timedelta(days=6) or base > today_dt + timedelta(days=7):
        return False
    if recurring == "weekdays":
        anchored = datetime.strptime(next_date_for_weekday("monday"), "%Y-%m-%d").date()
    else:
        anchored = datetime.strptime(next_date_for_weekday(base.strftime("%A").lower()), "%Y-%m-%d").date()
    if anchored != base:
        ev.date = anchored.strftime("%Y-%m-%d")
        return True
    return False

def truncate_for_groq(text, max_chars=4000):
    """Ensure we never send too much to Groq"""
    if len(text) > max_chars:
        return text[:max_chars] + "...[truncated]"
    return text

def groq_chat(messages, max_tokens=800, json_mode=False):
    if not GROQ_API_KEY:
        app.config["LAST_GROQ_ERROR"] = "missing api key"
        return None
    # Keep the system prompt intact and trim older chat only if context gets huge.
    system_messages = [m for m in messages if m.get("role") == "system"]
    other_messages = [m for m in messages if m.get("role") != "system"]
    budget = 18000 - sum(len(m.get("content", "")) for m in system_messages)
    trimmed_others = []
    for m in reversed(other_messages):
        content = m.get("content", "")
        if len(content) <= budget:
            trimmed_others.insert(0, m)
            budget -= len(content)
        elif budget > 500:
            trimmed_others.insert(0, {**m, "content": content[:budget]})
            budget = 0
            break
    messages = system_messages + trimmed_others
    try:
        payload = {
            "model": GROQ_MODEL,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": 0.3
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        resp = requests.post(GROQ_URL, json=payload, headers={
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json"
        }, timeout=15)
        data = resp.json()
        if resp.status_code >= 400:
            app.config["LAST_GROQ_ERROR"] = f"Groq HTTP {resp.status_code}: {data}"
            print(app.config["LAST_GROQ_ERROR"])
            return None
        if "choices" not in data:
            app.config["LAST_GROQ_ERROR"] = f"Groq missing choices: {data}"
            print(app.config["LAST_GROQ_ERROR"])
            return None
        app.config["LAST_GROQ_ERROR"] = ""
        return data["choices"][0]["message"]["content"]
    except Exception as e:
        app.config["LAST_GROQ_ERROR"] = f"Groq error: {e}"
        print(app.config["LAST_GROQ_ERROR"])
        return None

def ai_error_reply():
    err = str(app.config.get("LAST_GROQ_ERROR", "") or "").lower()
    if "invalid_api_key" in err or "invalid api key" in err or "401" in err:
        return "ai api key is invalid or not loaded. your app data is still safe."
    if "rate_limit" in err or "rate limit" in err or "429" in err:
        return "ai is rate limited for a few minutes. your app data is still safe."
    if "model" in err and ("not found" in err or "does not exist" in err or "decommission" in err):
        return "ai model is unavailable. check the model name. your app data is still safe."
    if "messages" in err and "json" in err:
        return "ai request format needs json wording. your app data is still safe."
    return "i could not reach the ai service right now. your app data is still safe."

def parse_json_object(raw):
    if not raw:
        return None
    clean = raw.strip()
    if clean.startswith("```"):
        parts = clean.split("```")
        for p in parts:
            if p.startswith("json"):
                clean = p[4:].strip()
                break
            if "{" in p:
                clean = p.strip()
                break
    idx = clean.find("{")
    if idx >= 0:
        clean = clean[idx:]
    end = clean.rfind("}")
    if end >= 0:
        clean = clean[:end+1]
    return json.loads(clean)

def claims_state_change(text):
    t = (text or "").lower()
    return any(w in t for w in [
        "added", "updated", "removed", "deleted", "cleared", "changed",
        "scheduled", "created", "moved", "marked", "cancelled", "started"
    ])

def list_of_dicts(value):
    if isinstance(value, dict):
        return [value]
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]

def find_plan_item_server(day_plan, target=""):
    items = list_of_dicts(day_plan)
    target_key = task_key(target)
    if target_key:
        for item in items:
            if task_key(item.get("task", "")) == target_key:
                return item
        for item in items:
            key = task_key(item.get("task", ""))
            if key and (target_key in key or key in target_key):
                return item
    now_min = datetime.now().hour * 60 + datetime.now().minute
    timed = []
    for item in items:
        start = parse_hhmm(item.get("time", ""))
        if start is not None:
            timed.append((start, item))
    if not timed:
        return None
    current = [item for start, item in timed if start <= now_min < start + normalize_plan_duration(item.get("duration", 30))]
    if current:
        return current[-1]
    future = [(start, item) for start, item in timed if start >= now_min]
    return sorted(future or timed, key=lambda x: x[0])[0][1]

def recent_plan_item_server(day_plan, ui_state):
    recent = list_of_dicts((ui_state or {}).get("recent_actions", []))
    for row in reversed(recent):
        action = row.get("action") if isinstance(row.get("action"), dict) else row
        if not isinstance(action, dict):
            continue
        target = action.get("target_task") or action.get("task") or action.get("title") or action.get("text") or ""
        item = None
        if action.get("id"):
            item = next((p for p in list_of_dicts(day_plan) if str(p.get("id", "")) == str(action.get("id"))), None)
        if not item and target:
            item = find_plan_item_server(day_plan, target)
        if item:
            return item
    return find_plan_item_server(day_plan)

def parse_duration_minutes_server(text):
    import re
    s = str(text or "").lower()
    total = 0
    words = {"one": 1, "two": 2, "three": 3, "four": 4}
    hr = re.search(r"\b(\d+|one|two|three|four)\s*(h|hr|hrs|hour|hours)\b", s)
    mn = re.search(r"\b(\d+)\s*(m|min|mins|minute|minutes)\b", s)
    if hr:
        total += (words.get(hr.group(1)) or int(hr.group(1))) * 60
    if mn:
        total += int(mn.group(1))
    return max(5, min(180, total)) if total else 0

def parse_clock_reference_server(text, default_pm=True):
    import re
    s = str(text or "").lower()
    m = re.search(r"\b(?:at\s*)?(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b", s)
    if not m:
        return None
    h = int(m.group(1))
    minute = int(m.group(2) or 0)
    mer = m.group(3)
    if h > 23 or minute > 59:
        return None
    if mer == "pm" and h < 12:
        h += 12
    elif mer == "am" and h == 12:
        h = 0
    elif not mer and default_pm and 1 <= h <= 11:
        h += 12
    return h * 60 + minute

def duration_after_word_server(text, word):
    import re
    s = str(text or "").lower()
    idx = s.find(word)
    if idx < 0:
        return 0
    chunk = s[idx:idx + 120]
    words = {"one": 1, "two": 2, "three": 3, "four": 4}
    m = re.search(r"\b(\d+|one|two|three|four)\s*(h|hr|hrs|hour|hours|m|min|mins|minute|minutes)\b", chunk)
    if not m:
        return 0
    amount = words.get(m.group(1)) or int(m.group(1))
    unit = m.group(2)
    return max(5, min(180, amount * 60 if unit.startswith("h") else amount))

def selected_date_from_ui(ui_state, today):
    ds = (ui_state or {}).get("selected_plan_date") or today
    try:
        datetime.strptime(ds, "%Y-%m-%d")
        return ds
    except Exception:
        return today

def study_task_for_scheduled(events, target_date):
    try:
        target_dt = datetime.strptime(target_date, "%Y-%m-%d").date()
    except Exception:
        target_dt = datetime.now().date()
    upcoming = collect_upcoming_prep(events or [], target_date, target_dt, horizon_days=7)
    urgent = [u for u in upcoming if u.get("days_away", 9) <= 2]
    names = [u["title"] for u in urgent[:2]]
    if not names:
        return "study scheduled work"
    if len(names) == 1:
        return f"study for {names[0]}"
    return "study for " + " and ".join(names)

def existing_dinner_item(day_plan, ui_state):
    item = find_plan_item_server(day_plan, "dinner")
    if item:
        return item
    snapshot = (ui_state or {}).get("day_snapshot") or {}
    for visible in list_of_dicts(snapshot.get("visible_items", [])):
        if task_key(visible.get("task", "")) == "dinner":
            return visible
    return None

def remembered_day_pref(ui_state, key, default=None):
    mem = (ui_state or {}).get("day_memory") or {}
    return mem.get(key, default) if isinstance(mem, dict) else default

def rounded_now_min_for_day(target_date, today):
    if target_date == today:
        now = datetime.now()
        return max(FLEX_DAY_START_MIN, min(DAY_END_MIN, ((now.hour * 60 + now.minute + 4) // 5) * 5))
    return FLEX_DAY_START_MIN

def build_evening_study_dinner_plan(message, day_plan, ui_state, today, events):
    low = str(message or "").lower()
    target_date = selected_date_from_ui(ui_state, today)
    now_min = rounded_now_min_for_day(target_date, today)
    dinner = existing_dinner_item(day_plan, ui_state)
    dinner_start_existing = parse_hhmm((dinner or {}).get("time", ""))
    dinner_duration = duration_after_word_server(low, "dinner") or remembered_day_pref(ui_state, "dinner_duration", 0) or normalize_plan_duration((dinner or {}).get("duration", 30))
    study_duration = duration_after_word_server(low, "study") or remembered_day_pref(ui_state, "study_duration", 0) or 60
    sleep_part = low[low.find("sleep"):] if "sleep" in low else ""
    sleep_min = parse_clock_reference_server(sleep_part, default_pm=True) if sleep_part else None
    dinner_last = bool(remembered_day_pref(ui_state, "dinner_last", False)) or "last" in low or "before that" in low or "before dinner" in low

    if sleep_min is not None:
        dinner_start = max(now_min, sleep_min - dinner_duration)
        study_start = max(now_min, dinner_start - study_duration)
        if study_start + study_duration > dinner_start:
            dinner_start = min(23 * 60 - dinner_duration, study_start + study_duration)
    elif dinner_last:
        if dinner_start_existing is not None and dinner_start_existing - study_duration >= now_min:
            dinner_start = dinner_start_existing
            study_start = dinner_start - study_duration
        else:
            study_start = now_min
            dinner_start = study_start + study_duration
    elif dinner_start_existing is not None:
        dinner_start = dinner_start_existing
        study_start = max(now_min, dinner_start - study_duration)
        if study_start + study_duration > dinner_start:
            dinner_start = study_start + study_duration
    else:
        study_start = now_min
        dinner_start = study_start + study_duration

    dinner_start = max(16 * 60, min(23 * 60 - dinner_duration, dinner_start))
    study_start = max(now_min, dinner_start - study_duration)
    if study_start + study_duration > dinner_start:
        dinner_start = min(23 * 60 - dinner_duration, study_start + study_duration)
    task = study_task_for_scheduled(events or [], target_date)
    return [
        {"type": "task", "time": mins_to_hhmm(study_start), "task": task, "duration": study_duration, "color": plan_color_for_task(task)},
        {"type": "meal", "time": mins_to_hhmm(dinner_start), "task": "dinner", "duration": dinner_duration, "color": "#d99a6c"},
    ]

def visible_flexible_items(ui_state, day_plan):
    snapshot = (ui_state or {}).get("day_snapshot") or {}
    items = list_of_dicts(snapshot.get("visible_items", []))
    if not items:
        items = list_of_dicts(day_plan)
    out = []
    for item in items:
        if item.get("fixed") or item.get("source") == "calendar":
            continue
        task = clean_task_text(item.get("task", ""))
        if not task:
            continue
        out.append({
            "id": item.get("id", ""),
            "task": task,
            "time": item.get("time", ""),
            "duration": normalize_plan_duration(item.get("duration", 30)),
            "color": sanitize_color(item.get("color", "")) or plan_color_for_task(task),
            "type": item.get("type") or ("meal" if is_meal_task(task) else "task"),
        })
    return out

def build_dinner_last_plan(day_plan, ui_state, today):
    target_date = selected_date_from_ui(ui_state, today)
    now_min = rounded_now_min_for_day(target_date, today)
    items = visible_flexible_items(ui_state, day_plan)
    dinner = next((i for i in items if task_key(i.get("task", "")) == "dinner"), None)
    dinner_duration = remembered_day_pref(ui_state, "dinner_duration", 0) or normalize_plan_duration((dinner or {}).get("duration", 30))
    non_dinner = [i for i in items if task_key(i.get("task", "")) != "dinner"]
    latest_end = now_min
    for item in non_dinner:
        start = parse_hhmm(item.get("time", ""))
        if start is None:
            continue
        latest_end = max(latest_end, start + normalize_plan_duration(item.get("duration", 30)))
    existing_start = parse_hhmm((dinner or {}).get("time", ""))
    dinner_start = max(latest_end, existing_start or 18 * 60 + 30, 16 * 60)
    dinner_start = min(dinner_start, 23 * 60 - dinner_duration)
    return [{
        "id": (dinner or {}).get("id", ""),
        "task": "dinner",
        "time": mins_to_hhmm(dinner_start),
        "duration": dinner_duration,
        "color": "#d99a6c",
        "type": "meal",
    }]

def life_fast_lane(message, day_plan, ui_state, today, events=None, reminders=None):
    import re
    msg = str(message or "").strip()
    low = msg.lower()
    now_time = datetime.now().strftime("%H:%M")
    target_date = selected_date_from_ui(ui_state, today)

    if re.search(r"\b(clear|reset|wipe)\s+(my\s+)?day\b|\bclear\s+day\s+plan\b", low):
        return {"mode": "execute", "reply": "day cleared", "question": None, "actions": [{"type": "clear_day_plan"}], "fast_lane": True}

    if "dinner" in low and "study" in low and ("before" in low or "sleep" in low or remembered_day_pref(ui_state, "dinner_last", False)):
        plan = build_evening_study_dinner_plan(message, day_plan, ui_state, today, events or [])
        return {"mode": "execute", "reply": "evening plan updated", "question": None, "actions": [{"type": "update_day_plan", "plan": plan, "replace_scope": "evening"}], "fast_lane": True}

    m = re.search(r"\bmake\s+dinner\s+(?:the\s+)?last\s+thing\b|\bdinner\s+last\b", low)
    if m:
        return {"mode": "execute", "reply": "moved dinner last", "question": None, "actions": [{"type": "update_day_plan", "plan": build_dinner_last_plan(day_plan, ui_state, today)}], "fast_lane": True}

    m = re.search(r"\b(?:i'?m|i am)\s+(?:doing|working on|starting)\s+(.+?)(?:\s+right now|\s+now)?$", low)
    if m:
        task = clean_task_text(m.group(1))
        if task:
            return {"mode": "execute", "reply": f"added {task} now", "question": None, "actions": [{"type": "add_plan_item", "task": task, "time": now_time, "duration": 30, "color": plan_color_for_task(task)}], "fast_lane": True}

    duration = parse_duration_minutes_server(low)
    if duration and re.search(r"\b(for|take|takes|last|lasts|gonna go for|going to go for|make (it|that))\b", low) and not ("study" in low and "dinner" in low):
        item = recent_plan_item_server(day_plan, ui_state)
        action = {"type": "update_plan_item", "duration": duration}
        if item and item.get("id"):
            action["id"] = item.get("id")
        elif item and item.get("task"):
            action["target_task"] = item.get("task")
        else:
            action["position"] = "current"
        return {"mode": "execute", "reply": f"updated to {duration} minutes", "question": None, "actions": [action], "fast_lane": True}

    m = re.search(r"\b(?:move|shift|push)\s+(.+?)\s+(later|earlier|back)\b", low)
    if m:
        target = clean_task_text(m.group(1))
        minutes = duration or 15
        if m.group(2) in ("earlier", "back"):
            minutes = -minutes
        item = find_plan_item_server(day_plan, target)
        action = {"type": "update_plan_item", "relative_minutes": minutes}
        if item and item.get("id"):
            action["id"] = item.get("id")
        else:
            action["target_task"] = target
        direction = "earlier" if minutes < 0 else "later"
        return {"mode": "execute", "reply": f"moved {target} {direction}", "question": None, "actions": [action], "fast_lane": True}

    m = re.search(r"\bafter\s+(that|it|this)\s+(?:can\s+u\s+|can\s+you\s+|could\s+u\s+|could\s+you\s+)?(?:add|put|schedule)\s+(.+)$", low)
    if m:
        ref = recent_plan_item_server(day_plan, ui_state)
        task = clean_task_text(m.group(2))
        start = parse_hhmm(ref.get("time", "")) if ref else None
        if task and start is not None:
            time = mins_to_hhmm(start + normalize_plan_duration(ref.get("duration", 30)))
            return {"mode": "execute", "reply": f"added {task}", "question": None, "actions": [{"type": "add_plan_item", "task": task, "time": time, "duration": 30, "color": plan_color_for_task(task)}], "fast_lane": True}

    return None

# ── ROUTES ───────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/reminders', methods=['GET', 'POST'])
def handle_reminders():
    if request.method == 'POST':
        data = request.json
        text = clean_task_text(data.get('text', ''))
        color = reminder_color_for_text(text, data.get('color', ''))
        new_r = Reminder(
            text=text,
            updated_at=data.get('updated_at', ''),
            color=color,
            created_timestamp=data.get('created_timestamp', 0.0),
            completed_date=data.get('completed_date', ''),
            due_timestamp=data.get('due_timestamp', 0.0),
            due_label=data.get('due_label', ''),
            notes=data.get('notes', ''),
            schedule_preset=data.get('schedule_preset', 'none'),
            schedule_start=data.get('schedule_start', 0.0),
            notifications_sent=data.get('notifications_sent', 0)
        )
        db.session.add(new_r)
        db.session.commit()
        return jsonify(r_to_dict(new_r)), 201
    rems = Reminder.query.all()
    return jsonify([r_to_dict(r) for r in rems])

@app.route('/api/reminders/<int:rid>', methods=['PUT', 'DELETE'])
def handle_reminder(rid):
    r = Reminder.query.get_or_404(rid)
    if request.method == 'PUT':
        data = request.json
        if 'text' in data:
            data['text'] = clean_task_text(data.get('text', ''))
        if 'color' in data:
            data['color'] = reminder_color_for_text(data.get('text') or r.text, data.get('color', ''))
        fields = ['text','completed','scheduled_date','schedule_preset','schedule_start',
                  'notifications_sent','notes','updated_at','color','created_timestamp',
                  'completed_date','due_timestamp','due_label']
        for f in fields:
            if f in data:
                setattr(r, f, data[f])
        db.session.commit()
        return jsonify(r_to_dict(r))
    db.session.delete(r)
    db.session.commit()
    return '', 204

@app.route('/api/calendar', methods=['GET', 'POST'])
def handle_calendar():
    if request.method == 'POST':
        data = request.json
        ev = CalendarEvent(
            title=data.get('title',''), date=data.get('date',''),
            time=data.get('time',''), end_time=data.get('end_time',''),
            color=data.get('color',''),
            recurring=data.get('recurring','none'), notes=data.get('notes',''),
            created_timestamp=data.get('created_timestamp',0.0)
        )
        db.session.add(ev)
        db.session.commit()
        return jsonify(e_to_dict(ev)), 201
    evs = CalendarEvent.query.all()
    changed = False
    for ev in evs:
        changed = repair_recurring_event_anchor(ev) or changed
    if changed:
        db.session.commit()
    return jsonify([e_to_dict(e) for e in evs])

@app.route('/api/calendar/<int:eid>', methods=['PUT', 'DELETE'])
def handle_event(eid):
    e = CalendarEvent.query.get_or_404(eid)
    if request.method == 'PUT':
        data = request.json
        for f in ['title','date','time','end_time','color','recurring','notes']:
            if f in data:
                setattr(e, f, data[f])
        db.session.commit()
        return jsonify(e_to_dict(e))
    db.session.delete(e)
    db.session.commit()
    return '', 204

@app.route('/api/life-chat', methods=['POST'])
def life_chat():
    data = request.json
    message = data.get('message', '')
    reminders = data.get('reminders', [])
    events = data.get('events', [])
    history = data.get('history', [])
    day_plan = data.get('day_plan', [])
    ui_state = data.get('ui_state', {})
    now_str = datetime.now().strftime('%A, %B %d, %Y %H:%M')
    today = datetime.now().strftime('%Y-%m-%d')
    fast = life_fast_lane(message, day_plan, ui_state, today, events, reminders)
    if fast:
        return jsonify(fast)
    return run_life_agent(message, reminders, events, history, day_plan, ui_state, now_str, today)

    # Compact data — keep it under token budget
    rem_compact = [{"id": r["id"], "text": r["text"][:70], "due": ms_to_date_str(r.get("due_timestamp", 0)), "done": r.get("completed", False), "notes": r.get("notes","")[:50]} for r in reminders[:35]]
    ev_compact = [{"id": e["id"], "title": e["title"][:70], "date": e["date"], "day": weekday_name(e.get("date","")), "time": e.get("time",""), "end": e.get("end_time",""), "rec": e.get("recurring","none"), "color": e.get("color",""), "notes": e.get("notes","")[:50]} for e in events[:40]]
    plan_compact = [{"id": p.get("id",""), "time": p.get("time",""), "task": p.get("task","")[:70], "duration": p.get("duration",0), "color": p.get("color","")} for p in day_plan[:16]]
    anchors = []
    for p in day_plan[:18]:
        task = (p.get("task") or "").lower()
        if any(word in task for word in ["dinner", "lunch", "breakfast", "school", "sleep", "bed", "work"]):
            anchors.append({"task": p.get("task","")[:60], "time": p.get("time",""), "duration": p.get("duration",0)})

    reminders_text = json.dumps(rem_compact)
    events_text = json.dumps(ev_compact)
    plan_text = json.dumps(plan_compact)

    system_prompt = f"""You are bamboo, a calm life OS. Output ONLY JSON:
{{"reply":"short lowercase reply","question":null,"actions":[]}}

STATE
now={now_str}; today={today}
ui={json.dumps(ui_state)}
reminders={reminders_text}
calendar={events_text}
day_plan={plan_text}
anchors={json.dumps(anchors)}

TOOLS
reminders: add_reminder(text,due_date,due_label,notes), update_reminder(id,text,due_date,due_label,notes,completed), complete_reminder(id), delete_reminder(id).
calendar: add_event(title,date,time,end_time,recurring,color,notes), update_event(id plus only changed fields), delete_event(id), add_weekly_schedule(title,items[day,time,end_time,notes],color).
day plan for ui.selected_plan_date: add_plan_item(time,task,duration,color), add_plan_items(items[time,task,duration,color]), update_plan_item(id or target_task/position/time plus changed fields), update_plan_items(items[]), delete_plan_item(id or target_task/position/time), delete_plan_items(items[]), update_day_plan(plan[time,task,duration,color],full_replace,replace_scope) for multi-item revisions, clear_day_plan, generate_day_plan.
app: clear_calendar, clear_reminders, clear_everything, clear_conversation, set_current_task, clear_current_task, set_timer(label,seconds), cancel_timer, set_view(reminders|dashboard|calendar|life_rest|life_chat), set_sort(default|due), select_calendar_day(date).

POLICY
Choose ask/propose/execute/answer. Ask only if required info is missing. Propose times instead of executing when user asks "what do you think"; execute when user accepts.
Calendar is durable truth. Day plan is flexible for selected day. Reminders are lightweight tasks. Timer/current task are temporary.
Use ui.recent_actions for "it/that/when/change it/on calendar". Use ui.selected_plan_events for selected-day schedule.
Broad delete requests: "remove everything/start fresh" => clear_everything. "from calendar/calendar only" => clear_calendar. "reminders only" => clear_reminders. "chat/history" => clear_conversation.
For risky destructive actions, still output the tool; the app will show yes/no confirmation before executing.
Calendar edits are surgical: if changing color, duration, title, etc. send only id/type plus that field. Never blank or resend unrelated fields.
Recurring habits/routines belong on calendar. If user says everyday/daily/weekday, create or update recurring calendar events. Also update selected day plan if it affects that day.
For "after X every day", find X in calendar/plan, place new item after X using X end_time or duration; make it recurring daily if the relationship is durable.
If user changes duration ("it should be 15 mins"), update latest matching plan item and matching calendar event only if it exists.
For adding one plan item, use add_plan_item, never update_day_plan. For changing one item, use update_plan_item.
update_day_plan is surgical by default: include only tasks the user asked to add/change, and do not change unrelated plan items. Only set full_replace:true for an explicit whole-day replan/replace request.
Day plan generation priority: hard calendar blocks first, user day-specific requests, upcoming calendar prep, reminders, then meals/breaks/routines.
Flexible day-plan items must fit completely inside 05:00-23:00. Never schedule before 05:00 or ending after 23:00.
Use add_weekly_schedule for weekday schedules with exceptions; never recurring="mondays" or date="*". Valid recurring: none,daily,weekly,weekdays,monthly.
Do not invent meanings. Keep titles literal. If you claim a change, include the action. Replies stay brief and specific."""
    messages = []
    for h in history[-16:]:
        messages.append({"role": h["role"], "content": str(h["content"])[:400]})
    messages.append({"role": "user", "content": message[:500]})

    result = groq_chat([{"role": "system", "content": system_prompt}] + messages, max_tokens=900, json_mode=True)
    
    if not result:
        return jsonify({
            "reply": ai_error_reply(),
            "question": None,
            "error": True,
            "actions": []
        })
    
    try:
        parsed = parse_json_object(result)
        if parsed.get("question"):
            parsed["actions"] = []
        reply_text = (parsed.get("reply") or "").strip()
        proposal = reply_text.lower().startswith(("how about", "would ", "does ")) or "?" in reply_text
        if proposal and parsed.get("actions"):
            parsed["question"] = parsed.get("question") or reply_text
            parsed["actions"] = []
        actions = parsed.get("actions", [])
        parsed["actions"] = normalize_ai_actions(actions, message)
        if not parsed["actions"] and claims_state_change(parsed.get("reply", "")):
            correction_prompt = system_prompt + """

Your previous response claimed the app changed but returned no action.
Return JSON again. If the user asked for a change, include the exact tool action.
If no tool is safe, ask a question. Never claim a change without actions."""
            corrected = groq_chat(
                [{"role": "system", "content": correction_prompt}] + messages + [{"role": "assistant", "content": json.dumps(parsed)}],
                max_tokens=500,
                json_mode=True
            )
            if corrected:
                fixed = parse_json_object(corrected)
                if fixed:
                    parsed = fixed
                    if parsed.get("question"):
                        parsed["actions"] = []
                    parsed["actions"] = normalize_ai_actions(parsed.get("actions", []), message)
        if parsed["actions"] and not parsed.get("question"):
            reply = (parsed.get("reply") or "").lower()
            if not reply or any(word in reply for word in ["clearing", "removed", "cleared"]) and any(a.get("type","").startswith("clear_") for a in parsed["actions"]):
                parsed["reply"] = "i can do that."
        if (parsed.get("reply") or "").strip().lower() in ("got it", "okay", "ok", "sure", "done"):
            if not parsed.get("actions"):
                parsed["question"] = parsed.get("question") or "what should i do next?"
                parsed["reply"] = parsed["question"]
        if parsed.get("reply"):
            parsed["reply"] = str(parsed.get("reply")).strip()
            if parsed["reply"]:
                parsed["reply"] = parsed["reply"][0].lower() + parsed["reply"][1:]
        return jsonify(parsed)
    except Exception as e:
        print(f"Life chat parse error: {e}, result: {result}")
        fallback = (result or "").strip()
        if not fallback:
            fallback = "what should i do next?"
        return jsonify({"reply": fallback, "question": fallback if "?" in fallback else None, "actions": []})

def run_life_agent(message, reminders, events, history, day_plan, ui_state, now_str, today):
    reminders = list_of_dicts(reminders)
    events = list_of_dicts(events)
    day_plan = list_of_dicts(day_plan)
    rem_compact = [{"id": r.get("id"), "text": str(r.get("text", ""))[:80], "due": ms_to_date_str(r.get("due_timestamp", 0)), "done": bool(r.get("completed", False))} for r in reminders[:30]]
    ev_compact = [{"id": e.get("id"), "title": str(e.get("title", ""))[:80], "date": e.get("date", ""), "time": e.get("time", ""), "end_time": e.get("end_time", ""), "recurring": e.get("recurring", "none"), "color": e.get("color", "")} for e in events[:40]]
    plan_compact = [{"id": p.get("id", ""), "time": p.get("time", ""), "task": str(p.get("task", ""))[:80], "duration": p.get("duration", 0), "color": p.get("color", "")} for p in day_plan[:16]]
    now_dt = datetime.now()
    state = {
        "now": now_str,
        "current_time_12h": now_dt.strftime('%I:%M %p').lstrip('0').lower(),
        "current_time_24h": now_dt.strftime('%H:%M'),
        "today": today,
        "ui": ui_state,
        "reminders": rem_compact,
        "calendar": ev_compact,
        "day_plan": plan_compact,
        "availability": availability_context_for(message, events, day_plan, ui_state, today),
    }
    system_prompt = f"""You are bamboo, the operator for this app. The user can type anything. Decide fast: answer, ask one follow-up, or run tools. Prefer tools for clear requests. Return ONLY JSON:
{{"mode":"answer|ask|execute|confirm","reply":"short lowercase text","question":null,"actions":[]}}

STATE={json.dumps(state)}

TOOLS:
reminders: add_reminder(text,due_date,due_label,notes), update_reminder(id,...), complete_reminder(id), delete_reminder(id), clear_reminders.
calendar: add_event(title,date,time,end_time,recurring,color,notes), update_event(id plus only changed fields), delete_event(id), add_weekly_schedule(title,items[day,time,end_time,notes],color), clear_calendar.
day plan for ui.selected_plan_date: add_plan_item(time,task,duration,color), add_plan_items(items[]), update_plan_item(id or target_task/position/time plus changed fields), update_plan_items(items[]), delete_plan_item(...), delete_plan_items(items[]), update_day_plan(plan[],full_replace,replace_scope), clear_day_plan, generate_day_plan.
app: set_view(view), select_calendar_day(date), set_sort(default|due|color), set_current_task(task), clear_current_task, set_timer(label,seconds), cancel_timer, clear_conversation, clear_everything.

RULES:
- Tool contract: all tool times must be 24-hour "HH:MM". A range like 1-3pm is time="13:00", end_time="15:00"; 1-3 with an activity/school context should usually mean afternoon unless morning is clearly intended.
- Follow-up repair: phrases like "make it pm", "no, 24 hour format", "change that to 1-3", "fix the time" refer to the most recent relevant event/plan action in STATE.ui.recent_actions/history. Preserve the title/date/recurring rule and preserve duration/end_time unless the user changes it.
- Day memory: STATE.ui.day_memory stores user preferences for the selected day, like dinner_last, dinner_duration, study_duration, sleep_time, and recent requests. Respect it unless the user changes it.
- Day snapshot: STATE.ui.day_snapshot is the current visible My Day truth. Use visible_items/free_windows/hard_events to cross-reference requests before editing the plan.
- Multi-command requests should usually return multiple actions or one coherent update_day_plan. Do not satisfy only the last clause.
- If one message gives multiple durations, bind each duration to the nearest task phrase. Example: "dinner 10 mins ... study 2 hrs" means dinner duration 10 and study duration 120.
- "whatever i'm studying" means the relevant upcoming scheduled tests/projects/assignments from calendar/reminders, not the most recent arbitrary plan item.
- Never update a calendar event time without preserving or setting end_time when the original/request had a range.
- If user asks for a change, return mode execute and actions. Never say something changed without actions.
- If user asks to clear/delete/remove calendar events, use {{"type":"clear_calendar"}}.
- If user asks to open/go/show calendar, use {{"type":"set_view","view":"calendar"}}.
- If user asks to clear/delete/remove everything, use {{"type":"clear_everything"}}.
- If user asks to clear reminders, use {{"type":"clear_reminders"}}.
- If user asks to clear chat/history, use {{"type":"clear_conversation"}}.
- If user asks the current time/date/day, answer from STATE.current_time_12h / STATE.today. Do not use calendar event times unless they ask about a specific event.
- For "am i free", "when am i free", "what is open", "can i fit", and similar availability questions, answer directly from STATE.availability. Do not create actions unless the user asks to schedule something.
- If the user gives a specific time/range and it overlaps busy blocks, say what conflicts and suggest the nearest free windows. If it is free, say yes and mention the window.
- If the user names a date/day, use that date over the selected UI day. If the date is missing for an availability question, use ui.selected_plan_date when present, otherwise today.
- If user says now/right now for a plan item, use STATE.current_time_24h and execute update_plan_item or add_plan_item; do not ask what time.
- When adding or moving a selected-day plan item for today, never choose a time before STATE.current_time_24h.
- Day-plan items must fit completely inside 05:00-23:00. Never schedule a flexible plan item before 05:00 or ending after 23:00.
- If the user asks to add a plan task without a time, choose the next open slot today after STATE.current_time_24h, respecting calendar blocks in STATE.calendar and existing STATE.day_plan.
- Day plan can be edited with add_plan_item, update_plan_item, delete_plan_item, update_plan_items, and clear_day_plan. Support task, time, duration, color, title/name changes, and relative moves.
- For day-plan tasks, choose calm app-matching colors when adding/changing items: #6f8f84 health/exercise, #7d9ad6 school/study/work, #d99a6c meals, #9b83c9 personal/wind-down, #8fc49e breaks/rest.
- If the user says "add it/this/that to my day plan" and the referenced thing is not clear from history/state, ask what to add. Never create a plan item literally named it/this/that.
- For "15 minutes later", "one hour later", "shift it later", or "now", update the referenced/latest/current/next plan item instead of asking.
- If upcoming calendar contains tests/quizzes/exams/projects/assignments, day-plan generation should add useful prep/study/work time around hard calendar blocks.
- For broad day-plan requests like rearrange, optimize, make this fit, plan around my schedule, or change the whole agenda: build a full update_day_plan with logical times, set full_replace:true, then use mode confirm so the app shows yes/no before changing several items.
- For single clear edits like "move exercise 15 minutes later", "make study blue", "delete dinner", execute the single plan tool directly without confirmation.
- When making a full plan revision, preserve user-requested tasks, respect calendar hard blocks, remove overlaps, choose realistic gaps, and keep today after STATE.current_time_24h.
- When using update_day_plan without full_replace:true, be surgical: include only the changed/added flexible tasks and leave everything else alone. Calendar events are already displayed, so do not include hard calendar events.
- For ambiguous plan requests, make a reasonable one-step choice, execute it, and briefly say what you did. Ask only when the task/date itself is unknown.
- Ask only if required info is missing. Do not ask confirmation for direct commands like "clear calendar".
- Use confirm only when scope is genuinely vague and destructive.
- Calendar is durable truth; day plan is flexible selected-day execution; reminders are lightweight tasks.
- Habit/goal requests like "i want to start exercising" should be productive in one response: suggest a small realistic starter plan and, if the user clearly asks to schedule it, create recurring calendar events plus a near-term day-plan item when appropriate. If they only express intent, do not execute; offer one concrete default they can accept.
- Reminders are for lightweight one-off tasks. Calendar is for commitments/routines. Day plan is for today's flexible execution.
- Reminder quality: clean obvious typos, spacing, and casing in reminder text while preserving meaning. Choose a color when adding/updating reminders: health/exercise #6f8f84, school/work #7d9ad6, food #d99a6c, personal #9b83c9, break/rest #8fc49e.
- If a reminder/task has a concrete date or time, include due_date on add_reminder. The app will mirror dated reminders onto calendar, so do not duplicate with add_event unless the user explicitly asks for a separate calendar event or it is a durable schedule/routine.
- If the user asks for a scheduled commitment/routine rather than a lightweight reminder, use calendar tools instead of reminder tools.
- Use history/state for references like it, that, do it, from calendar.
- Calendar updates are surgical: only id/type plus changed fields.
- Weekday schedules with different days/times must use add_weekly_schedule, not a single add_event or update_event.
- Recurring habits belong on calendar. Everyday/weekly => recurring event.
- Keep titles literal, replies brief."""
    messages = [{"role": "system", "content": system_prompt}]
    for h in history[-8:]:
        messages.append({"role": h.get("role", "user"), "content": str(h.get("content", ""))[:350]})
    messages.append({"role": "user", "content": str(message)[:500]})
    result = groq_chat(messages, max_tokens=450, json_mode=True)
    if not result:
        return jsonify({"reply": ai_error_reply(), "question": None, "error": True, "actions": []})
    try:
        parsed = parse_json_object(result)
        if not isinstance(parsed, dict):
            raise ValueError("model returned non-object")
        if parsed.get("question") or parsed.get("mode") == "ask":
            parsed["actions"] = []
        parsed["actions"] = normalize_ai_actions(parsed.get("actions", []), message)
        if not parsed["actions"] and (parsed.get("mode") == "execute" or claims_state_change(parsed.get("reply", ""))):
            corrected = groq_chat(
                messages + [{"role": "assistant", "content": json.dumps(parsed)}, {"role": "user", "content": "mode execute requires actions. return corrected json with the exact tool actions, or mode ask with one question."}],
                max_tokens=350,
                json_mode=True
            )
            if corrected:
                fixed = parse_json_object(corrected)
                if isinstance(fixed, dict):
                    parsed = fixed
                    if parsed.get("question") or parsed.get("mode") == "ask":
                        parsed["actions"] = []
                    parsed["actions"] = normalize_ai_actions(parsed.get("actions", []), message)
        if not parsed.get("actions") and (parsed.get("mode") == "execute" or claims_state_change(parsed.get("reply", ""))):
            parsed["mode"] = "ask"
            parsed["question"] = "what exactly should i change?"
            parsed["reply"] = parsed["question"]
        if parsed.get("mode") == "confirm" and parsed.get("actions"):
            parsed["confirm"] = True
        parsed.setdefault("reply", "")
        parsed.setdefault("question", None)
        parsed.setdefault("actions", [])
        if parsed["reply"]:
            parsed["reply"] = str(parsed["reply"]).strip()
            parsed["reply"] = parsed["reply"][0].lower() + parsed["reply"][1:] if parsed["reply"] else ""
        return jsonify(parsed)
    except Exception as e:
        print(f"Life agent parse error: {e}, result: {result}")
        return jsonify({"reply": "i could not parse that cleanly. try again?", "question": "try again with the change you want?", "actions": []})

def generate_day_plan_v2():
    data = request.json or {}
    reminders = list_of_dicts(data.get('reminders', []))
    events = list_of_dicts(data.get('events', []))
    current_task = data.get('current_task', '')
    pinned_plan = list_of_dicts(data.get('pinned_plan', []))
    existing_plan = list_of_dicts(data.get('existing_plan', []))
    regeneration_count = int(data.get('regeneration_count', 0) or 0)
    target_date = data.get('target_date') or datetime.now().strftime('%Y-%m-%d')
    actual_today = datetime.now().strftime('%Y-%m-%d')
    try:
        target_dt = datetime.strptime(target_date, "%Y-%m-%d").date()
    except Exception:
        target_date = actual_today
        target_dt = datetime.now().date()
    today = target_date
    now_dt = datetime.now()
    now_str = now_dt.strftime('%A, %B %d, %Y %H:%M')
    if target_date == actual_today:
        current_min = now_dt.hour * 60 + now_dt.minute
        earliest_min = max(FLEX_DAY_START_MIN, min(DAY_END_MIN, ((current_min + 4) // 5) * 5))
        start_note = f"start at or after {mins_to_hhmm(earliest_min)} because this is today"
    else:
        earliest_min = FLEX_DAY_START_MIN
        start_note = f"plan the useful day from {mins_to_hhmm(FLEX_DAY_START_MIN)} onward"

    planner_context = build_planner_context(reminders, events, pinned_plan, existing_plan, target_date, target_dt, earliest_min)
    state = {
        "now": now_str,
        "planning_date": target_date,
        "weekday": weekday_name(target_date),
        "regeneration_count": regeneration_count,
        "start_rule": start_note,
        "current_task": current_task[:80] or "",
        **planner_context,
    }

    prompt = f"""You are Bamboo's AI day-planning brain. Reason like a humane scheduler, then return strict JSON.

STATE JSON:
{json.dumps(state)}

Return ONLY this JSON shape:
{{"plan":[{{"time":"HH:MM","task":"short literal task","duration":30,"color":"#hex or null","type":"task|break|meal","why":"short private reason"}}]}}

Planning principles:
- Calendar blocks are hard reality and are already displayed in My Day. Never return calendar events, school, band, tests, appointments, or reminder mirrors that are in scheduled_events/hard_blocks.
- Use free_windows as your map. Every flexible task must fit inside a free window after the start_rule.
- Preserve locked_plan items as much as possible. Keep useful previous_plan items when still relevant, but remove stale filler.
- Choose the few high-leverage things, not everything. A good plan is calm and doable.
- Add prep only for real upcoming_prep items. Prefer 1 focused session per distinct test/project. If there are several similar/typo-like tests, consolidate instead of duplicating.
- Put urgent/energy-heavy work earlier in the available evening, meals at sane times, and breaks after longer focus.
- Reminders are lightweight tasks. Fit only reminders listed in reminders; never duplicate a reminder that appears as a scheduled event.
- If today is already late, do not invent morning/early afternoon tasks.

Hard rules:
- Times must be 24-hour HH:MM.
- Every returned item must fit completely inside 05:00-23:00.
- Durations are 5-180 minutes. Prefer 25, 30, 45, 60, 75, 90.
- Max 8 returned items unless the day is genuinely open.
- No duplicate or near-duplicate tasks.
- No generic filler like "morning routine", "review tomorrow", or "prepare for bed" unless explicitly in reminders/locked_plan.
- Meals: breakfast before 11:00, lunch before 15:00, dinner 16:00-23:00 when the user wants it late.
- Colors: #6f8f84 health/exercise, #7d9ad6 school/study/work, #d99a6c meals, #9b83c9 personal/wind-down, #8fc49e breaks/rest."""

    result = groq_chat([{"role": "user", "content": prompt}], max_tokens=700, json_mode=True)
    if not result:
        return jsonify(smart_fallback_day_plan(reminders, events, current_task, pinned_plan, existing_plan, target_date, target_dt, earliest_min))
    try:
        parsed = parse_json_object(result)
        if isinstance(parsed, dict):
            parsed_plan = parsed.get("plan", [])
        else:
            parsed_plan = []
        parsed_plan = parsed_plan if isinstance(parsed_plan, list) else []
        plan = finalize_day_plan(parsed_plan, reminders, events, target_date, earliest_min)
        if not plan:
            plan = smart_fallback_day_plan(reminders, events, current_task, pinned_plan, existing_plan, target_date, target_dt, earliest_min)
        return jsonify(plan)
    except Exception as e:
        print(f"Day plan parse error: {e}, result: {result}")
        return jsonify(smart_fallback_day_plan(reminders, events, current_task, pinned_plan, existing_plan, target_date, target_dt, earliest_min))

@app.route('/api/generate-day-plan', methods=['POST'])
def generate_day_plan():
    return generate_day_plan_v2()
    data = request.json
    reminders = data.get('reminders', [])
    events = data.get('events', [])
    current_task = data.get('current_task', '')
    pinned_plan = data.get('pinned_plan', [])
    existing_plan = data.get('existing_plan', [])
    regeneration_count = int(data.get('regeneration_count', 0) or 0)
    target_date = data.get('target_date') or datetime.now().strftime('%Y-%m-%d')
    now_str = datetime.now().strftime('%A, %B %d, %Y %H:%M')
    today = target_date
    actual_today = datetime.now().strftime('%Y-%m-%d')
    target_dt = datetime.strptime(target_date, "%Y-%m-%d").date()
    if target_date == actual_today:
        now_hour = datetime.now().hour
        now_min = datetime.now().minute
        start_note = "start from current time approximately"
    else:
        now_hour = 6
        now_min = 0
        start_note = "plan the full day from morning onward"

    plan_reminders = []
    for r in reminders:
        if r.get("completed"):
            continue
        due_date = ms_to_date_str(r.get("due_timestamp", 0))
        if due_date and due_date > today:
            continue
        plan_reminders.append({"text": r["text"][:60], "due_label": r.get("due_label","")[:30], "due_date": due_date, "color": r.get("color","")})
    rem_compact = plan_reminders[:15]
    today_events = [e for e in events if event_occurs_on(e, today)]
    ev_compact = [{"title": e["title"][:60], "time": e.get("time",""), "end_time": e.get("end_time",""), "recurring": e.get("recurring","none"), "notes": e.get("notes","")[:60]} for e in today_events[:15]]
    upcoming = []
    for offset in range(1, 15):
        ds = (target_dt + timedelta(days=offset)).strftime("%Y-%m-%d")
        for e in events:
            if event_occurs_on(e, ds):
                upcoming.append({"date": ds, "title": e.get("title","")[:60], "time": e.get("time",""), "notes": e.get("notes","")[:60]})
        if len(upcoming) >= 12:
            break
    pinned_compact = [{"time": p.get("time",""), "task": p.get("task","")[:60], "duration": p.get("duration",30), "color": p.get("color","")} for p in pinned_plan[:5]]
    existing_compact = [{"time": p.get("time",""), "task": p.get("task","")[:60], "duration": p.get("duration",30), "source": p.get("source","generated")} for p in existing_plan[:12]]

    prompt = f"""You are a day planner. Now: {now_str}. Planning date: {target_date}. Planning start: {now_hour}:{now_min:02d}.

Reminders (tasks to fit in): {json.dumps(rem_compact)}
Scheduled events for selected date: {json.dumps(ev_compact)}
Upcoming calendar events after selected date: {json.dumps(upcoming[:12])}
Current user-set task: {current_task[:80] or "none"}
Locked plan items to preserve exactly: {json.dumps(pinned_compact)}
Previous generated plan draft: {json.dumps(existing_compact)}
Regeneration number: {regeneration_count}

Create a realistic flexible plan for the selected date using this priority:
1. Hard stacked things: scheduled calendar events for the selected date are fixed blocks. They are already shown separately in the app, so use them as blocked time but do not return them as plan items.
2. User-requested day-specific things: locked/current/existing plan tasks matter next.
3. Upcoming calendar events: if something is coming soon, add reasonable prep/study/work time only when useful.
4. Reminders: fit reminders into remaining open space.
5. Meals, breaks, routines, free time: fill naturally without overpacking.
Treat the previous generated plan as the current stable plan unless inputs changed.

Return ONLY a JSON array (no wrapper object):
[
  {{"time":"HH:MM","task":"short task name","duration":30,"color":"#hex or null","type":"event|task|break|meal"}}
]

Rules:
- time in 24h format
- duration in minutes
- max 12 items
- be realistic — don't overpack
- {start_note}
- preserve locked plan items exactly and keep the current user-set task near the beginning of the plan
- if regenerating with no new user prompt and the inputs did not change, keep the previous generated plan essentially the same; only remove duplicates or impossible overlaps
- never duplicate the same task unless the user explicitly asked for repeated sessions
- do not schedule anything before the current time unless it is a fixed scheduled event already in progress
- scheduled events are fixed commitments and are displayed automatically; do not include them in the returned JSON
- do not return "blocked" placeholder items; leave scheduled-event time empty unless adding a real flexible task around it
- never include a recurring event unless it occurs on the selected planning date; the Scheduled events for selected date list is the only event list to use
- future-dated reminders should not be planned today; reminders shown here are undated, overdue, or due today
- color: green=health/exercise, blue=work/study, orange=food/meal, purple=personal, null=default"""

    result = groq_chat([{"role": "user", "content": prompt}], max_tokens=700)
    
    if not result:
        return jsonify([])
    
    try:
        clean = result.strip()
        if clean.startswith("```"):
            parts = clean.split("```")
            for p in parts:
                if p.startswith("json"): clean = p[4:].strip(); break
                elif "[" in p or "{" in p: clean = p.strip(); break
        idx = clean.find("[")
        if idx >= 0: clean = clean[idx:]
        end = clean.rfind("]")
        if end >= 0: clean = clean[:end+1]
        parsed = json.loads(clean)
        return jsonify(parsed if isinstance(parsed, list) else [])
    except Exception as e:
        print(f"Day plan parse error: {e}, result: {result}")
        return jsonify([])

@app.route('/api/parse-date', methods=['POST'])
def parse_date():
    data = request.json
    text = clean_task_text(data.get('text', ''))
    now = datetime.now()
    tomorrow = (now.date() + timedelta(days=1)).strftime("%Y-%m-%d")
    now_str = now.strftime('%A, %B %d, %Y %H:%M')

    prompt = f"""You are Bamboo's reminder parser. Parse the user's reminder into clean app data.

Server local now: {now_str}
Tomorrow's date: {tomorrow}
User text: "{text[:220]}"

Return ONLY one JSON object with exactly these keys:
{{
  "has_date": true,
  "clean_text": "short corrected reminder title without date/time words",
  "due_date": "YYYY-MM-DD",
  "time": "HH:MM or empty",
  "end_time": "HH:MM or empty",
  "label": "friendly due label",
  "color": "#hex or empty",
  "confidence": 0.0
}}

Rules:
- Understand typos and shorthand: tmrw/tmr/tom = tomorrow, rn = now.
- Fix obvious reminder typos in clean_text, especially missing vowels: "drnk watr" -> "drink water".
- If there is no date or time, return has_date false but still return clean_text and optional color.
- If there is a time but no date, use today when that time is still ahead, otherwise tomorrow.
- If the user gives a date but no time, leave time empty.
- If the user says "at 5" without am/pm, use 17:00 unless the wording clearly means morning.
- For ranges like "1-3pm", set time 13:00 and end_time 15:00.
- clean_text should remove date/time fragments like "tmrw at 5" and fix obvious typos, but never invent a different task.
- School/work/test/homework colors use #7d9ad6, health/exercise #6f8f84, food #d99a6c, personal/rest #9b83c9, breaks/free time #8fc49e, otherwise empty.
- label should describe the due date/time, not repeat the task. Example: "tomorrow 5:00 PM".
- Never include timestamp_ms; the server will compute it."""

    result = groq_chat([{"role": "user", "content": prompt}], max_tokens=220, json_mode=True)
    parsed = parse_json_object(result) if result else None
    if not isinstance(parsed, dict):
        return jsonify({
            "has_date": False,
            "clean_text": text,
            "due_date": "",
            "time": "",
            "end_time": "",
            "label": "",
            "color": reminder_color_for_text(text),
            "timestamp_ms": 0
        })

    clean_text = clean_task_text(parsed.get("clean_text") or text) or text
    color = reminder_color_for_text(clean_text, parsed.get("color", ""))
    due_date = str(parsed.get("due_date") or "").strip()
    time = normalize_hhmm(parsed.get("time", ""))
    end_time = normalize_hhmm(parsed.get("end_time", ""))
    has_date = bool(parsed.get("has_date")) and bool(due_date)

    try:
        due = datetime.strptime(due_date, "%Y-%m-%d").date()
    except Exception:
        has_date = False
        due = None

    if not has_date:
        return jsonify({
            "has_date": False,
            "clean_text": clean_text,
            "due_date": "",
            "time": "",
            "end_time": "",
            "label": "",
            "color": color,
            "timestamp_ms": 0
        })

    stamp_time = datetime.strptime(time, "%H:%M").time() if time else datetime.strptime("09:00", "%H:%M").time()
    timestamp_ms = int(datetime.combine(due, stamp_time).timestamp() * 1000)
    label = clean_task_text(parsed.get("label") or build_due_label(due_date, time, end_time))
    if not label or task_key(label) == task_key(clean_text):
        label = build_due_label(due_date, time, end_time)

    return jsonify({
        "has_date": True,
        "clean_text": clean_text,
        "due_date": due_date,
        "time": time,
        "end_time": end_time,
        "label": label,
        "color": color,
        "timestamp_ms": timestamp_ms
    })


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=4000, debug=True, use_reloader=False)
