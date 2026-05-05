import os
import json
import requests
from datetime import datetime, date, timedelta
from flask import Flask, request, jsonify, render_template_string
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)

db_url = os.environ.get('DATABASE_URL', 'sqlite:///local_20260503_202810.db')
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
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

DAY_START_MIN = 5 * 60
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

def next_open_start(start, duration, occupied):
    start = max(DAY_START_MIN, int(start))
    for _ in range(80):
        end = start + duration
        if end > DAY_END_MIN:
            return None
        conflict = next((b for b in occupied if ranges_overlap(start, end, b["start"], b["end"])), None)
        if not conflict:
            return start
        start = max(start + 5, conflict["end"])
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
        start = max(start, earliest)
        start = next_open_start(start, duration, occupied)
        if start is None:
            continue
        tkey = task_key(task)
        if (tkey == "breakfast" and start > 11 * 60) or (tkey == "lunch" and start > 15 * 60) or (tkey == "dinner" and (start < 16 * 60 or start > 22 * 60)):
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
        due_date = ms_to_date_str(r.get("due_timestamp", 0))
        if due_date and due_date > target_date:
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

def truncate_for_groq(text, max_chars=3000):
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

# ── ROUTES ───────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/api/reminders', methods=['GET', 'POST'])
def handle_reminders():
    if request.method == 'POST':
        data = request.json
        new_r = Reminder(
            text=data.get('text', ''),
            updated_at=data.get('updated_at', ''),
            color=data.get('color', ''),
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
day plan for ui.selected_plan_date: add_plan_item(time,task,duration,color), add_plan_items(items[time,task,duration,color]), update_plan_item(id or target_task/position/time plus changed fields), update_plan_items(items[]), delete_plan_item(id or target_task/position/time), delete_plan_items(items[]), update_day_plan(plan[time,task,duration,color]) ONLY for replacing whole plan, clear_day_plan, generate_day_plan.
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
Day plan generation priority: hard calendar blocks first, user day-specific requests, upcoming calendar prep, reminders, then meals/breaks/routines.
Use add_weekly_schedule for weekday schedules with exceptions; never recurring="mondays" or date="*". Valid recurring: none,daily,weekly,weekdays,monthly.
Do not invent meanings. Keep titles literal. If you claim a change, include the action. Replies stay brief and specific."""
    messages = []
    for h in history[-16:]:
        messages.append({"role": h["role"], "content": str(h["content"])[:400]})
    messages.append({"role": "user", "content": message[:500]})

    result = groq_chat([{"role": "system", "content": system_prompt}] + messages, max_tokens=900, json_mode=True)
    
    if not result:
        err = app.config.get("LAST_GROQ_ERROR", "")
        msg = "ai is rate limited for a few minutes." if "rate_limit" in err or "429" in err else "i could not reach the ai service right now."
        return jsonify({
            "reply": f"{msg} your app data is still safe.",
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
    }
    system_prompt = f"""You are bamboo, the operator for this app. The user can type anything. Decide fast: answer, ask one follow-up, or run tools. Prefer tools for clear requests. Return ONLY JSON:
{{"mode":"answer|ask|execute|confirm","reply":"short lowercase text","question":null,"actions":[]}}

STATE={json.dumps(state)}

TOOLS:
reminders: add_reminder(text,due_date,due_label,notes), update_reminder(id,...), complete_reminder(id), delete_reminder(id), clear_reminders.
calendar: add_event(title,date,time,end_time,recurring,color,notes), update_event(id plus only changed fields), delete_event(id), add_weekly_schedule(title,items[day,time,end_time,notes],color), clear_calendar.
day plan for ui.selected_plan_date: add_plan_item(time,task,duration,color), add_plan_items(items[]), update_plan_item(id or target_task/position/time plus changed fields), update_plan_items(items[]), delete_plan_item(...), delete_plan_items(items[]), update_day_plan(plan[]), clear_day_plan, generate_day_plan.
app: set_view(view), select_calendar_day(date), set_sort(mode), set_current_task(task), clear_current_task, set_timer(label,seconds), cancel_timer, clear_conversation, clear_everything.

RULES:
- If user asks for a change, return mode execute and actions. Never say something changed without actions.
- If user asks to clear/delete/remove calendar events, use {{"type":"clear_calendar"}}.
- If user asks to open/go/show calendar, use {{"type":"set_view","view":"calendar"}}.
- If user asks to clear/delete/remove everything, use {{"type":"clear_everything"}}.
- If user asks to clear reminders, use {{"type":"clear_reminders"}}.
- If user asks to clear chat/history, use {{"type":"clear_conversation"}}.
- If user asks the current time/date/day, answer from STATE.current_time_12h / STATE.today. Do not use calendar event times unless they ask about a specific event.
- If user says now/right now for a plan item, use STATE.current_time_24h and execute update_plan_item or add_plan_item; do not ask what time.
- When adding or moving a selected-day plan item for today, never choose a time before STATE.current_time_24h.
- If the user asks to add a plan task without a time, choose the next open slot today after STATE.current_time_24h, respecting calendar blocks in STATE.calendar and existing STATE.day_plan.
- Day plan can be edited with add_plan_item, update_plan_item, delete_plan_item, update_plan_items, and clear_day_plan. Support task, time, duration, color, title/name changes, and relative moves.
- For day-plan tasks, choose calm app-matching colors when adding/changing items: #6f8f84 health/exercise, #7d9ad6 school/study/work, #d99a6c meals, #9b83c9 personal/wind-down, #8fc49e breaks/rest.
- If the user says "add it/this/that to my day plan" and the referenced thing is not clear from history/state, ask what to add. Never create a plan item literally named it/this/that.
- For "15 minutes later", "one hour later", "shift it later", or "now", update the referenced/latest/current/next plan item instead of asking.
- If upcoming calendar contains tests/quizzes/exams/projects/assignments, day-plan generation should add useful prep/study/work time around hard calendar blocks.
- For broad day-plan requests like rearrange, optimize, make this fit, plan around my schedule, or change the whole agenda: build a full update_day_plan with logical times, then use mode confirm so the app shows yes/no before changing several items.
- For single clear edits like "move exercise 15 minutes later", "make study blue", "delete dinner", execute the single plan tool directly without confirmation.
- When making a full plan revision, preserve user-requested tasks, respect calendar hard blocks, remove overlaps, choose realistic gaps, and keep today after STATE.current_time_24h.
- For ambiguous plan requests, make a reasonable one-step choice, execute it, and briefly say what you did. Ask only when the task/date itself is unknown.
- Ask only if required info is missing. Do not ask confirmation for direct commands like "clear calendar".
- Use confirm only when scope is genuinely vague and destructive.
- Calendar is durable truth; day plan is flexible selected-day execution; reminders are lightweight tasks.
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
        err = app.config.get("LAST_GROQ_ERROR", "")
        msg = "ai is rate limited for a few minutes." if "rate_limit" in err or "429" in err else "i could not reach the ai service right now."
        return jsonify({"reply": f"{msg} your app data is still safe.", "question": None, "error": True, "actions": []})
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
    reminders = data.get('reminders', [])
    events = data.get('events', [])
    current_task = data.get('current_task', '')
    pinned_plan = data.get('pinned_plan', [])
    existing_plan = data.get('existing_plan', [])
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
        earliest_min = max(DAY_START_MIN, min(DAY_END_MIN, ((current_min + 4) // 5) * 5))
        start_note = f"start at or after {mins_to_hhmm(earliest_min)} because this is today"
    else:
        earliest_min = DAY_START_MIN
        start_note = "plan the full day from 05:00 onward"

    plan_reminders = []
    for r in reminders:
        if r.get("completed"):
            continue
        due_date = ms_to_date_str(r.get("due_timestamp", 0))
        if due_date and due_date > today:
            continue
        plan_reminders.append({"text": str(r.get("text", ""))[:60], "due_label": r.get("due_label","")[:30], "due_date": due_date, "color": r.get("color","")})
    today_events = [e for e in events if event_occurs_on(e, today)]
    ev_compact = [{"title": str(e.get("title", ""))[:60], "time": e.get("time",""), "end_time": e.get("end_time",""), "recurring": e.get("recurring","none"), "notes": e.get("notes","")[:60]} for e in today_events[:15]]
    hard_blocks = [{"title": b["title"][:60], "start": mins_to_hhmm(b["start"]), "end": mins_to_hhmm(b["end"])} for b in calendar_blocks_for_date(events, today)]
    upcoming = []
    for offset in range(1, 15):
        ds = (target_dt + timedelta(days=offset)).strftime("%Y-%m-%d")
        for e in events:
            if event_occurs_on(e, ds):
                upcoming.append({"date": ds, "title": str(e.get("title",""))[:60], "time": e.get("time",""), "notes": e.get("notes","")[:60]})
        if len(upcoming) >= 12:
            break
    pinned_compact = [{"time": p.get("time",""), "task": str(p.get("task",""))[:60], "duration": p.get("duration",30), "color": p.get("color","")} for p in pinned_plan[:5]]
    existing_compact = [{"time": p.get("time",""), "task": str(p.get("task",""))[:60], "duration": p.get("duration",30), "source": p.get("source","generated")} for p in existing_plan[:12]]

    prompt = f"""You are bamboo's day planner. Now: {now_str}. Planning date: {target_date}.

Reminders to fit: {json.dumps(plan_reminders[:15])}
Scheduled events for selected date: {json.dumps(ev_compact)}
Hard blocked calendar time: {json.dumps(hard_blocks)}
Upcoming calendar events after selected date: {json.dumps(upcoming[:12])}
Current user-set task: {current_task[:80] or "none"}
Locked plan items to preserve exactly: {json.dumps(pinned_compact)}
Previous generated plan draft: {json.dumps(existing_compact)}
Regeneration number: {regeneration_count}

Create a realistic flexible plan for the selected date using this priority:
1. Calendar events are hard blocks. They are already shown by the app, so do not return them and never overlap them.
2. User-requested day-specific items, locked items, current task, and previous plan tasks.
3. Prep for upcoming calendar events: tests/quizzes/exams/finals/projects/presentations/assignments due in the next 1-4 days should usually create a study/work session today, unless one already exists.
4. Reminders that are undated, overdue, or due on/before the selected date.
5. Meals, breaks, routines, and free time only when useful.

Return ONLY a JSON array:
[{{"time":"HH:MM","task":"short task name","duration":30,"color":"#hex or null","type":"task|break|meal"}}]

Rules:
- day window is 05:00 to 23:00. outside that is sleep/off-plan time.
- {start_note}
- max 12 items. be realistic and do not overpack.
- keep the previous generated plan essentially the same when inputs did not change; only fix duplicates or impossible overlaps.
- never duplicate the same task unless the user explicitly asked for repeated sessions.
- never schedule breakfast after 11:00, lunch after 15:00, or dinner outside 16:00-22:00.
- scheduled events are fixed commitments and displayed automatically; do not include them.
- no blocked placeholder items.
- color: choose a calm app-matching color when useful: #6f8f84 health/exercise, #7d9ad6 work/study, #d99a6c food/meal, #9b83c9 personal/wind-down, #8fc49e break/rest. Use null only if truly generic."""

    result = groq_chat([{"role": "user", "content": prompt}], max_tokens=700)
    if not result:
        return jsonify(fallback_day_plan(reminders, events, current_task, pinned_plan, existing_plan, target_date, earliest_min))
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
        parsed_plan = parsed if isinstance(parsed, list) else []
        existing_plan_keys = {task_key((p or {}).get("task") or (p or {}).get("title")) for p in parsed_plan if isinstance(p, dict)}
        for prep in prep_items_for_upcoming(events, target_date, earliest_min):
            if task_key(prep["task"]) not in existing_plan_keys:
                parsed_plan.append(prep)
                existing_plan_keys.add(task_key(prep["task"]))
        plan = sanitize_day_plan(parsed_plan, events, target_date, earliest_min)
        if not plan:
            plan = fallback_day_plan(reminders, events, current_task, pinned_plan, existing_plan, target_date, earliest_min)
        return jsonify(plan)
    except Exception as e:
        print(f"Day plan parse error: {e}, result: {result}")
        return jsonify(fallback_day_plan(reminders, events, current_task, pinned_plan, existing_plan, target_date, earliest_min))

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
    text = data.get('text', '')
    now_str = datetime.now().strftime('%A, %B %d, %Y %H:%M')
    
    prompt = f"""Date/time parser. Now: {now_str}

Text: "{text[:200]}"

Return ONLY JSON:
- No date: {{"has_date":false}}
- Date found: {{"has_date":true,"timestamp_ms":1234567890000,"label":"human label","due_date":"YYYY-MM-DD"}}"""

    result = groq_chat([{"role": "user", "content": prompt}], max_tokens=150)
    if not result:
        return jsonify({"has_date": False})
    try:
        clean = result.strip()
        if clean.startswith("```"):
            clean = clean.split("```")[1]
            if clean.startswith("json"):
                clean = clean[4:]
        return jsonify(json.loads(clean.strip()))
    except Exception:
        return jsonify({"has_date": False})


# ── HTML ─────────────────────────────────────────────────────────────────────

HTML_TEMPLATE = r"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>bamboo.</title>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@200;300;400;500;600&display=swap" rel="stylesheet">
    <style>
        :root {
            --accent: #C1B19A;
            --accent-warm: #D4C4AD;
            --dark: #2C251B;
            --bg: #FDFBF7;
            --surface: #F5F1EA;
            --muted: rgba(44,37,27,0.38);
            --muted-med: rgba(44,37,27,0.55);
            --border: rgba(44,37,27,0.09);
            --border-med: rgba(44,37,27,0.14);
            --green: #6f8f84;
            --green-light: rgba(90,138,106,0.12);
            --red: #ef4444;
            --red-light: rgba(239,68,68,0.12);
            --blue: #3b82f6;
            --orange: #f97316;
            --life-bg: #07100a;
            --life-green: #6f8f84;
            --life-green-dim: rgba(111,143,132,0.16);
            --life-text: rgba(239,244,239,0.86);
            --life-muted: rgba(239,244,239,0.34);
        }
        *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
        body, html {
            font-family: 'Outfit', sans-serif;
            background: var(--bg); color: var(--dark);
            -webkit-font-smoothing: antialiased;
            min-height: 100vh; overflow-x: hidden;
        }

        @keyframes fadeIn { from{opacity:0}to{opacity:1} }
        @keyframes slideUp { from{opacity:0;transform:translateY(14px)}to{opacity:1;transform:translateY(0)} }
        @keyframes breathe { 0%,100%{opacity:0.55;transform:scale(1)}50%{opacity:0.85;transform:scale(1.05)} }
        @keyframes pulse { 0%,100%{opacity:1}50%{opacity:0.3} }
        @keyframes leafSway { 0%,100%{transform:rotate(-3deg)}50%{transform:rotate(3deg)} }
        @keyframes msgIn { from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:translateY(0)} }
        @keyframes planSlide { from{opacity:0;transform:translateX(-10px)}to{opacity:1;transform:translateX(0)} }
        @keyframes timerPulse { 0%,100%{opacity:1}50%{opacity:0.7} }

        /* ── HEADER ── */
        .header-wrap {
            display:flex;align-items:center;justify-content:center;
            position:relative;padding:52px 20px 16px;
            max-width:600px;margin:0 auto;
        }
        .logo {
            font-size:28px;font-weight:400;letter-spacing:4px;
            color:var(--accent);text-transform:lowercase;
            cursor:pointer;transition:opacity .2s;user-select:none;-webkit-user-select:none;
        }
        .logo:active{opacity:.5}
        .menu-btn {
            position:absolute;left:20px;bottom:20px;
            width:38px;height:38px;border-radius:10px;
            display:flex;flex-direction:column;align-items:center;
            justify-content:center;gap:5px;cursor:pointer;transition:background .2s;
        }
        .menu-btn:hover{background:rgba(0,0,0,.04)}
        .menu-btn span{display:block;width:18px;height:1.5px;background:var(--muted);border-radius:2px;}
        .sort-btn {
            position:absolute;right:20px;bottom:20px;
            width:38px;height:38px;border-radius:10px;
            display:flex;align-items:center;justify-content:center;
            cursor:pointer;transition:background .2s;color:var(--muted);
        }
        .sort-btn:hover{background:rgba(0,0,0,.04);color:var(--dark)}
        .sort-btn svg{width:16px;height:16px;stroke:currentColor;stroke-width:2;fill:none;stroke-linecap:round}

        /* ── DRAWER ── */
        .drawer-overlay{position:fixed;inset:0;background:rgba(44,37,27,.3);backdrop-filter:blur(4px);z-index:700;opacity:0;pointer-events:none;transition:opacity .3s;}
        .drawer-overlay.show{opacity:1;pointer-events:all}
        .drawer{position:fixed;top:0;left:0;bottom:0;width:290px;background:var(--bg);z-index:800;transform:translateX(-100%);transition:transform .38s cubic-bezier(.165,.84,.44,1);display:flex;flex-direction:column;border-right:1px solid var(--border);box-shadow:4px 0 40px rgba(44,37,27,.08);}
        .drawer.show{transform:translateX(0)}
        .drawer-header{padding:56px 24px 20px;border-bottom:1px solid var(--border)}
        .drawer-logo{font-size:20px;font-weight:400;letter-spacing:4px;color:var(--accent)}
        .drawer-sub{font-size:12px;color:var(--muted);margin-top:3px;font-weight:300}
        .drawer-nav{padding:12px 8px;flex:1;overflow-y:auto}
        .nav-item{display:flex;align-items:center;gap:12px;padding:12px 14px;border-radius:11px;cursor:pointer;font-size:14px;font-weight:400;color:var(--muted-med);transition:all .2s;margin-bottom:2px;}
        .nav-item:hover,.nav-item.active{background:var(--surface);color:var(--dark)}
        .nav-item svg{width:16px;height:16px;stroke:currentColor;stroke-width:1.8;fill:none;flex-shrink:0;stroke-linecap:round;stroke-linejoin:round}
        .nav-section{font-size:10px;font-weight:500;letter-spacing:1.5px;text-transform:uppercase;color:var(--muted);padding:10px 14px 4px;opacity:.6}
        .drawer-footer{padding:16px 24px;border-top:1px solid var(--border);font-size:12px;color:var(--muted);font-weight:300}

        /* ── VIEWS ── */
        .view{display:none}
        .view.active{display:block}

        /* ── REMINDERS ── */
        .list-wrap{max-width:600px;margin:0 auto;padding:4px 20px 160px}
        .section-lbl{font-size:10px;font-weight:500;letter-spacing:1.5px;text-transform:uppercase;color:var(--muted);padding:18px 0 8px}
        .reminder-item{
            padding:16px 0 16px 14px;border-bottom:1px solid var(--border);
            cursor:pointer;transition:all .3s;user-select:none;-webkit-user-select:none;
            animation:slideUp .32s ease-out forwards;opacity:0;
            border-left:3px solid transparent;position:relative;background:var(--bg);
        }
        .reminder-item:hover{transform:translateX(3px);background:rgba(0,0,0,.012);border-radius:0 8px 8px 0}
        .reminder-item.completed{opacity:.28;border-left-color:transparent!important}
        .reminder-item.completed:hover{transform:none;background:transparent}
        .reminder-item.overdue{border-left-color:var(--red)!important}
        .r-text{font-size:17px;font-weight:400;line-height:1.45;word-wrap:break-word;white-space:pre-wrap}
        .reminder-item.completed .r-text{text-decoration:line-through;color:var(--muted)}
        .r-meta{display:flex;flex-wrap:wrap;gap:8px;margin-top:6px;font-size:11px;color:var(--muted);font-weight:300}
        .r-meta span{display:flex;align-items:center;gap:3px}
        .meta-ico{width:11px;height:11px;stroke:currentColor;stroke-width:2;fill:none;flex-shrink:0}
        .badge{display:inline-flex;align-items:center;gap:3px;padding:2px 7px;border-radius:20px;font-size:10px;font-weight:500}
        .badge-green{background:var(--green-light);color:var(--green)}
        .badge-red{background:var(--red-light);color:var(--red)}
        .badge-blue{background:rgba(59,130,246,.1);color:var(--blue)}
        .badge-orange{background:rgba(249,115,22,.1);color:var(--orange)}
        .empty-state{text-align:center;padding:60px 0;color:var(--muted);font-size:14px;font-weight:300;line-height:2}

        /* ── CHAT BUBBLE ── */
        .chat-bubble-wrap{position:fixed;bottom:-160px;left:50%;transform:translateX(-50%);width:calc(100% - 40px);max-width:520px;transition:bottom .45s cubic-bezier(.175,.885,.32,1.275);z-index:100}
        .chat-bubble-wrap.show{bottom:36px}
        .chat-bubble{background:var(--dark);border-radius:26px;padding:13px 13px 13px 20px;display:flex;align-items:flex-end;gap:12px;box-shadow:0 20px 50px rgba(44,37,27,.28)}
        .chat-bubble textarea{flex:1;border:none;outline:none;background:transparent;font-size:16px;font-family:inherit;color:var(--bg);font-weight:300;resize:none;overflow-y:auto;line-height:1.45;max-height:100px;padding:0;margin-bottom:4px}
        .chat-bubble textarea::placeholder{color:rgba(253,251,247,.35)}
        .send-btn{background:var(--accent);color:var(--dark);border:none;border-radius:50%;width:40px;height:40px;flex-shrink:0;display:flex;align-items:center;justify-content:center;cursor:pointer;transition:transform .2s;margin-bottom:1px}
        .send-btn:active{transform:scale(.86)}
        .send-btn svg{width:17px;height:17px;stroke:currentColor;stroke-width:2;fill:none;margin-left:2px;stroke-linecap:round;stroke-linejoin:round}

        /* ── CONTEXT MENU ── */
        .ctx-menu{position:fixed;background:var(--bg);border-radius:14px;box-shadow:0 12px 48px rgba(0,0,0,.14);padding:7px;min-width:170px;z-index:200;display:none;opacity:0;transform:scale(.94);transform-origin:top left;transition:opacity .15s,transform .15s;border:1px solid var(--border-med)}
        .ctx-menu.show{display:flex;flex-direction:column;opacity:1;transform:scale(1)}
        .cm-item{padding:10px 14px;font-size:13px;cursor:pointer;border-radius:8px;transition:background .15s;display:flex;align-items:center;gap:9px;color:var(--dark)}
        .cm-item:hover{background:var(--surface)}
        .cm-item.danger{color:#ef4444}
        .cm-item svg{width:14px;height:14px;stroke:currentColor;stroke-width:2;fill:none;stroke-linecap:round;stroke-linejoin:round}
        .cm-divider{height:1px;background:var(--border);margin:3px 0}

        /* ── MODALS ── */
        .modal{display:none;position:fixed;inset:0;background:rgba(44,37,27,.35);backdrop-filter:blur(8px);z-index:300;align-items:flex-end;justify-content:center;opacity:0;transition:opacity .25s}
        .modal.show{display:flex;opacity:1}
        .modal-box{background:var(--bg);padding:24px 20px 36px;border-radius:24px 24px 0 0;width:100%;max-width:560px;display:flex;flex-direction:column;gap:16px;transform:translateY(40px);transition:transform .38s cubic-bezier(.175,.885,.32,1.275);box-shadow:0 -8px 40px rgba(0,0,0,.1)}
        .modal.show .modal-box{transform:translateY(0)}
        .modal-handle{width:36px;height:3px;background:var(--border-med);border-radius:2px;margin:0 auto -4px}
        .modal-title{font-size:17px;font-weight:500}
        .modal-inp{width:100%;padding:13px 15px;border:1px solid var(--border-med);border-radius:13px;font-family:inherit;font-size:15px;outline:none;background:var(--surface);color:var(--dark);transition:border-color .2s}
        textarea.modal-inp{resize:vertical;min-height:80px;line-height:1.5}
        .modal-inp:focus{border-color:var(--accent);background:var(--bg)}
        .color-grid{display:grid;grid-template-columns:repeat(6,1fr);gap:9px;justify-items:center}
        .c-swatch{width:36px;height:36px;border-radius:50%;cursor:pointer;border:2.5px solid transparent;transition:transform .2s,border-color .2s;box-shadow:0 2px 8px rgba(0,0,0,.08)}
        .c-swatch:hover{transform:scale(1.12)}
        .c-swatch.active{border-color:var(--dark);transform:scale(1.12)}
        .c-clear{background:transparent;border:2px dashed #d1d5db;display:flex;align-items:center;justify-content:center}
        .c-clear svg{width:16px;height:16px;stroke:#9ca3af;stroke-width:2;fill:none}
        .preset-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}
        .preset-card{border:1.5px solid var(--border-med);border-radius:12px;padding:14px 8px;text-align:center;cursor:pointer;transition:all .2s;background:var(--surface)}
        .preset-card.active{border-color:var(--accent);background:rgba(193,177,154,.12)}
        .preset-card:hover{transform:translateY(-2px)}
        .preset-name{font-weight:500;font-size:14px;margin-bottom:2px}
        .preset-desc{font-size:10px;color:var(--muted)}
        .modal-actions{display:flex;gap:8px;justify-content:flex-end}
        .btn{padding:11px 20px;border-radius:11px;font-family:inherit;font-size:14px;font-weight:500;cursor:pointer;border:none;transition:all .2s}
        .btn-cancel{background:var(--surface);color:var(--muted-med)}
        .btn-cancel:hover{color:var(--dark)}
        .btn-save{background:var(--accent);color:var(--dark)}
        .btn-save:hover{filter:brightness(.93);transform:translateY(-1px)}

        /* ── CALENDAR ── */
        .cal-wrap{max-width:600px;margin:0 auto;padding:8px 20px 160px}
        .cal-header-row{display:flex;align-items:center;justify-content:space-between;margin-bottom:18px}
        .cal-month-lbl{font-size:19px;font-weight:500}
        .cal-nav{width:34px;height:34px;border-radius:10px;border:none;background:var(--surface);cursor:pointer;display:flex;align-items:center;justify-content:center;color:var(--muted-med);transition:all .2s}
        .cal-nav:hover{background:var(--border-med);color:var(--dark)}
        .cal-nav svg{width:15px;height:15px;stroke:currentColor;stroke-width:2;fill:none;stroke-linecap:round}
        .cal-grid{display:grid;grid-template-columns:repeat(7,1fr);gap:3px;margin-bottom:20px}
        .cal-dl{text-align:center;font-size:10px;font-weight:500;color:var(--muted);padding:7px 0;letter-spacing:.5px}
        .cal-day{aspect-ratio:1;display:flex;flex-direction:column;align-items:center;justify-content:flex-start;padding-top:7px;border-radius:11px;cursor:pointer;transition:all .2s;position:relative;gap:2px}
        .cal-day:hover{background:var(--surface)}
        .cal-day.today{background:var(--dark)}
        .cal-day.today .cal-dn{color:var(--bg)}
        .cal-day.selected{background:var(--accent)}
        .cal-day.selected .cal-dn{color:var(--dark)}
        .cal-day.other-month .cal-dn{color:var(--muted);opacity:.35}
        .cal-dn{font-size:13px;font-weight:400;line-height:1}
        .cal-dot{width:4px;height:4px;border-radius:50%;flex-shrink:0}
        .cal-ev-list{animation:slideUp .28s ease-out}
        .cal-ev-item{display:flex;align-items:center;gap:11px;padding:13px 0;border-bottom:1px solid var(--border);cursor:pointer;transition:transform .2s}
        .cal-ev-item:hover{transform:translateX(3px)}
        .cal-ev-dot{width:9px;height:9px;border-radius:50%;flex-shrink:0}
        .cal-ev-title{font-size:14px;font-weight:400}
        .cal-ev-meta{font-size:11px;color:var(--muted);font-weight:300;margin-top:1px}
        .cal-ev-rec{font-size:9px;color:var(--muted);background:var(--surface);padding:1px 5px;border-radius:6px;display:inline-block;margin-top:2px}
        .cal-add-btn{display:flex;align-items:center;justify-content:center;gap:7px;padding:13px;border:1.5px dashed var(--border-med);border-radius:14px;cursor:pointer;color:var(--muted);font-size:13px;transition:all .2s;margin-top:8px}
        .cal-add-btn:hover{border-color:var(--accent);color:var(--dark);background:rgba(193,177,154,.06)}
        .cal-add-btn svg{width:14px;height:14px;stroke:currentColor;stroke-width:2;fill:none;stroke-linecap:round}
        .reminder-on-cal{background:var(--green-light);border-left:2px solid var(--green)}

        /* ── DASHBOARD ── */
        .dash-wrap{max-width:600px;margin:0 auto;padding:8px 20px 160px}
        .dash-card{background:var(--surface);border-radius:18px;padding:22px;margin-bottom:12px;border:1px solid var(--border);animation:slideUp .38s ease-out forwards;opacity:0}
        .dash-card:nth-child(2){animation-delay:.06s}
        .dash-card:nth-child(3){animation-delay:.12s}
        .dash-lbl{font-size:10px;font-weight:500;letter-spacing:1.5px;text-transform:uppercase;color:var(--muted);margin-bottom:14px}
        .streak-num{font-size:52px;font-weight:200;line-height:1;color:var(--dark)}
        .streak-sub{font-size:12px;color:var(--muted);font-weight:300;margin-top:2px}
        .streak-dots{display:flex;gap:5px;margin-top:14px;flex-wrap:wrap}
        .s-dot{width:26px;height:26px;border-radius:7px;display:flex;align-items:center;justify-content:center;font-size:10px;font-weight:500}
        .s-dot.done{background:var(--dark);color:var(--bg)}
        .s-dot.today{background:var(--accent);color:var(--dark)}
        .s-dot.miss{background:var(--border-med);color:var(--muted)}
        .s-dot.future{background:transparent;border:1.5px dashed var(--border-med);color:var(--muted)}
        .stats-row{display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px}
        .stat-cell{text-align:center}
        .stat-val{font-size:26px;font-weight:300;color:var(--dark);line-height:1}
        .stat-lbl{font-size:10px;color:var(--muted);margin-top:3px;font-weight:300}

        /* ══════════════════════════════════════
           MY LIFE OVERLAY — full rework
        ══════════════════════════════════════ */
        .life-overlay{
            position:fixed;inset:0;
            background:var(--life-bg);
            z-index:600;
            display:flex;flex-direction:column;
            align-items:center;
            overflow:hidden;
            transition:opacity .3s;
        }
        .life-overlay.hidden{display:none}

        /* ambient */
        .life-glow{
            position:absolute;width:500px;height:500px;
            background:radial-gradient(circle,rgba(74,124,89,0.08) 0%,transparent 70%);
            top:40%;left:50%;transform:translate(-50%,-50%);
            pointer-events:none;transition:opacity .5s;
        }

        /* top bar — shared */
        .life-top{
            width:100%;max-width:500px;
            display:flex;align-items:center;justify-content:space-between;
            padding:52px 24px 0;flex-shrink:0;position:relative;z-index:2;
        }
        .life-title-lbl{font-size:11px;font-weight:400;letter-spacing:3px;color:var(--life-muted);text-transform:lowercase}
        .life-top-right{display:flex;align-items:center;gap:8px}
        .life-icon-btn{width:32px;height:32px;border-radius:50%;background:rgba(255,255,255,.06);border:none;display:flex;align-items:center;justify-content:center;cursor:pointer;transition:background .2s}
        .life-icon-btn:hover{background:rgba(255,255,255,.1)}
        .life-icon-btn svg{width:14px;height:14px;stroke:rgba(232,240,235,.4);stroke-width:2;fill:none;stroke-linecap:round;stroke-linejoin:round}

        /* ── RESTING PAGE ── */
        #life-rest{
            flex:1;width:100%;max-width:500px;
            display:flex;flex-direction:column;
            align-items:center;
            overflow:hidden;
            position:relative;z-index:1;
        }

        /* clock */
        .rest-time{
            font-size:76px;font-weight:200;
            color:rgba(232,240,235,0.88);
            letter-spacing:-4px;line-height:1;
            margin-top:28px;
        }
        .rest-date{
            font-size:12px;font-weight:300;
            color:var(--life-muted);letter-spacing:.5px;
            margin-top:5px;margin-bottom:10px;
        }
        .life-day-nav{
            display:flex;align-items:center;gap:10px;margin-bottom:22px;
            color:var(--life-muted);font-size:12px;font-weight:300;
        }
        .life-day-btn{
            width:30px;height:30px;border-radius:50%;border:1px solid rgba(255,255,255,.08);
            background:rgba(255,255,255,.04);color:rgba(232,240,235,.45);
            display:flex;align-items:center;justify-content:center;cursor:pointer;
            transition:background .2s,color .2s,border-color .2s;
        }
        .life-day-btn:hover{background:rgba(255,255,255,.08);color:rgba(232,240,235,.75);border-color:rgba(255,255,255,.14)}
        .life-day-btn svg{width:14px;height:14px;stroke:currentColor;stroke-width:2;fill:none;stroke-linecap:round;stroke-linejoin:round}
        .life-day-chip{
            min-width:92px;text-align:center;padding:6px 10px;border-radius:999px;
            background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.07);
            cursor:pointer;
        }

        /* current + next */
        .rest-now{
            width:100%;padding:0 24px;margin-bottom:6px;
        }
        .rest-now-label{font-size:9px;font-weight:500;letter-spacing:2px;text-transform:uppercase;color:rgba(74,124,89,.7);margin-bottom:6px}
        .rest-now-task{
            font-size:20px;font-weight:400;color:var(--life-text);
            line-height:1.35;
        }
        .rest-next{
            width:100%;padding:0 24px;margin-bottom:20px;
        }
        .rest-next-label{font-size:9px;font-weight:500;letter-spacing:2px;text-transform:uppercase;color:var(--life-muted);margin-bottom:4px}
        .rest-next-task{font-size:13px;font-weight:300;color:var(--life-muted)}

        /* progress bar */
        .rest-progress-wrap{width:calc(100% - 48px);margin:0 24px 20px;position:relative}
        .rest-progress-track{height:2px;background:rgba(255,255,255,.07);border-radius:2px;overflow:hidden}
        .rest-progress-fill{height:100%;background:rgba(74,124,89,.6);border-radius:2px;transition:width 1s linear}
        .rest-progress-label{font-size:10px;color:var(--life-muted);margin-top:5px;text-align:right;font-weight:300}

        /* day plan timeline */
        .rest-plan{
            flex:1;width:100%;overflow-y:auto;
            padding:0 24px 8px;
        }
        .rest-plan::-webkit-scrollbar{display:none}
        .plan-item{
            display:flex;align-items:flex-start;gap:12px;
            padding:8px 0 14px;animation:planSlide .3s ease-out forwards;
            opacity:0;position:relative;min-height:54px;
        }
        .plan-item::before{
            content:'';position:absolute;left:27px;top:22px;
            width:1px;height:calc(100% - 4px);
            background:rgba(255,255,255,.05);
        }
        .plan-item:last-child::before{display:none}
        .plan-time{
            font-size:11px;font-weight:300;color:var(--life-muted);
            width:38px;flex-shrink:0;padding-top:2px;text-align:right;
        }
        .plan-dot{
            width:8px;height:8px;border-radius:50%;flex-shrink:0;
            margin-top:4px;background:rgba(74,124,89,.5);
            box-shadow:0 0 6px rgba(74,124,89,.3);
        }
        .plan-dot.active{background:var(--life-green);box-shadow:0 0 10px rgba(74,124,89,.6);animation:timerPulse 2s ease-in-out infinite}
        .plan-dot.done{background:rgba(255,255,255,.12)}
        .plan-body{min-width:0;flex:1;padding-bottom:2px}
        .plan-task{font-size:14px;font-weight:300;color:var(--life-text);line-height:1.35;flex:1}
        .plan-task.active-task{color:var(--life-text);font-weight:400}
        .plan-task.done-task{color:var(--life-muted);text-decoration:line-through}
        .plan-dur{font-size:10px;color:var(--life-muted);margin-top:4px;font-weight:300;line-height:1.1}
        .plan-event .plan-task{color:rgba(232,240,235,.88);font-weight:400}
        .plan-event .plan-dur{color:rgba(143,196,158,.55)}
        .all-day-stack{margin:0 24px 10px 62px;display:flex;flex-direction:column;gap:6px}
        .all-day-item{
            position:relative;padding:8px 12px 8px 14px;border-radius:10px;
            background:rgba(255,255,255,.045);border:1px solid rgba(255,255,255,.07);
            color:rgba(232,240,235,.78);font-size:12px;font-weight:300;
        }
        .all-day-item::before{
            content:'';position:absolute;left:0;top:7px;bottom:7px;width:3px;
            border-radius:3px;background:var(--all-day-color, rgba(143,196,158,.7));
            box-shadow:0 0 10px var(--all-day-glow, rgba(143,196,158,.18));
        }
        .all-day-label{
            margin:0 24px 6px 62px;color:rgba(232,240,235,.28);
            font-size:10px;text-transform:uppercase;letter-spacing:1.6px;font-weight:500;
        }

        /* bamboo emblem */
        .rest-emblem{
            padding:16px 0 8px;opacity:.35;
            animation:breathe 5s ease-in-out infinite;flex-shrink:0;
        }
        .rest-emblem svg{display:block}

        /* active timer on rest */
        .rest-timer{
            width:calc(100% - 48px);margin:0 24px 12px;
            background:rgba(74,124,89,.12);border:1px solid rgba(74,124,89,.2);
            border-radius:14px;padding:12px 16px;
            display:flex;align-items:center;justify-content:space-between;
        }
        .rest-timer.hidden{display:none}
        .rest-timer-label{font-size:12px;color:rgba(143,196,158,.8);font-weight:300}
        .rest-timer-time{font-size:20px;font-weight:300;color:rgba(143,196,158,.9);letter-spacing:1px;font-variant-numeric:tabular-nums}
        .rest-timer-cancel{background:none;border:none;cursor:pointer;color:var(--life-muted);font-size:11px;font-family:inherit;transition:color .2s}
        .rest-timer-cancel:hover{color:rgba(239,68,68,.7)}

        /* rest input bar */
        .rest-input-wrap{
            width:100%;max-width:500px;
            padding:8px 20px 32px;flex-shrink:0;position:relative;z-index:2;
        }
        .rest-input-row{
            display:flex;align-items:center;gap:10px;
            background:rgba(255,255,255,.05);
            border:1px solid rgba(255,255,255,.08);
            border-radius:22px;padding:11px 11px 11px 18px;
            transition:border-color .2s,background .2s;
        }
        .rest-input-row:focus-within{
            border-color:rgba(74,124,89,.35);
            background:rgba(255,255,255,.07);
        }
        .rest-input{
            flex:1;border:none;outline:none;background:transparent;
            font-size:14px;font-family:inherit;
            color:rgba(232,240,235,.75);font-weight:300;
        }
        .rest-input::placeholder{color:rgba(232,240,235,.2)}
        .rest-send{
            width:34px;height:34px;border-radius:50%;
            background:rgba(74,124,89,.5);border:none;
            display:flex;align-items:center;justify-content:center;
            cursor:pointer;transition:transform .2s,background .2s;flex-shrink:0;
        }
        .rest-send:hover{background:rgba(74,124,89,.7)}
        .rest-send:active{transform:scale(.86)}
        .rest-send svg{width:14px;height:14px;stroke:#fff;stroke-width:2.2;fill:none;stroke-linecap:round;stroke-linejoin:round;margin-left:1px}

        /* generate plan btn */
        .gen-plan-btn{
            display:flex;align-items:center;gap:6px;
            padding:8px 14px;border-radius:20px;
            background:rgba(74,124,89,.15);border:1px solid rgba(74,124,89,.2);
            color:rgba(143,196,158,.7);font-size:12px;font-family:inherit;
            cursor:pointer;transition:all .2s;margin:0 24px 14px;align-self:flex-start;
        }
        .gen-plan-btn:hover{background:rgba(74,124,89,.25);color:rgba(143,196,158,.9)}
        .gen-plan-btn svg{width:12px;height:12px;stroke:currentColor;stroke-width:2;fill:none;stroke-linecap:round}

        /* no plan state */
        .no-plan{
            flex:1;display:flex;flex-direction:column;align-items:center;
            justify-content:center;gap:8px;padding:0 40px;text-align:center;
        }
        .no-plan-text{font-size:13px;font-weight:300;color:var(--life-muted)}

        /* ── AI CHAT PAGE ── */
        #life-chat{
            flex:1;width:100%;max-width:500px;
            display:flex;flex-direction:column;
            overflow:hidden;position:relative;z-index:1;
        }
        #life-chat.hidden{display:none!important}
        #life-rest.hidden{display:none}

        .life-msgs{
            flex:1;overflow-y:auto;
            padding:12px 24px 8px;
            display:flex;flex-direction:column;
            gap:8px;
        }
        .life-msgs::-webkit-scrollbar{display:none}
        .msg-row{
            display:flex;align-items:center;gap:6px;max-width:92%;
        }
        .msg-row-user{align-self:flex-end;flex-direction:row-reverse}
        .msg-row-ai,.msg-row-action{align-self:flex-start}
        .msg-bubble{
            max-width:84%;padding:10px 14px;border-radius:18px;
            font-size:14px;font-weight:300;line-height:1.5;
            animation:msgIn .2s ease-out forwards;
        }
        .msg-user{
            background:rgba(255,255,255,.08);
            color:rgba(232,240,235,.8);
            align-self:flex-end;
            border-radius:18px 18px 4px 18px;
        }
        .msg-ai{
            background:rgba(74,124,89,.16);
            color:rgba(232,240,235,.9);
            align-self:flex-start;
            border-radius:18px 18px 18px 4px;
            border:1px solid rgba(74,124,89,.18);
        }
        .msg-action{
            background:rgba(74,124,89,.1);
            color:rgba(143,196,158,.7);
            align-self:flex-start;font-size:11px;
            border-radius:9px;padding:5px 11px;
            font-weight:300;
        }
        .confirm-card{
            align-self:flex-start;max-width:84%;padding:11px 13px;border-radius:16px 16px 16px 4px;
            background:rgba(74,124,89,.12);border:1px solid rgba(74,124,89,.22);
            color:rgba(232,240,235,.88);font-size:14px;font-weight:300;line-height:1.45;
        }
        .confirm-actions{display:flex;gap:8px;margin-top:10px}
        .confirm-btn{
            border-radius:999px;padding:7px 14px;font:inherit;font-size:12px;cursor:pointer;
            transition:transform .15s,background .15s,border-color .15s,color .15s;
        }
        .confirm-btn:active{transform:scale(.96)}
        .confirm-yes{background:rgba(74,124,89,.85);border:1px solid rgba(143,196,158,.4);color:white}
        .confirm-no{background:transparent;border:1px solid rgba(143,196,158,.35);color:rgba(143,196,158,.75)}
        .msg-tools{display:flex;gap:3px;align-items:center;opacity:0;transition:opacity .15s;flex-shrink:0}
        .msg-row:hover .msg-tools{opacity:1}
        .msg-del,.msg-copy,.msg-retry{
            width:22px;height:22px;border:0;background:transparent;color:rgba(232,240,235,.22);
            display:flex;align-items:center;justify-content:center;border-radius:50%;
            transition:background .15s,color .15s;cursor:pointer;flex-shrink:0;
        }
        .msg-del:hover,.msg-copy:hover,.msg-retry:hover{background:rgba(255,255,255,.08);color:rgba(232,240,235,.55)}
        .msg-del svg,.msg-copy svg,.msg-retry svg{width:12px;height:12px;stroke:currentColor;stroke-width:2;fill:none;stroke-linecap:round;stroke-linejoin:round}
        @media (hover:none){.msg-tools{opacity:.35}}
        .thinking-text{
            align-self:flex-start;color:rgba(232,240,235,.28);
            font-size:12px;font-weight:300;padding:2px 6px 0 6px;
            animation:msgIn .2s ease-out forwards;
        }
        .msg-typing{
            background:rgba(74,124,89,.1);
            color:rgba(143,196,158,.6);
            align-self:flex-start;
            border-radius:18px 18px 18px 4px;
            border:1px solid rgba(74,124,89,.12);
            display:flex;gap:4px;align-items:center;
            padding:13px 16px;
        }
        .typing-dot{width:5px;height:5px;border-radius:50%;background:rgba(143,196,158,.5);animation:pulse 1.2s ease-in-out infinite}
        .typing-dot:nth-child(2){animation-delay:.2s}
        .typing-dot:nth-child(3){animation-delay:.4s}
        .life-clear-chat{
            width:36px;height:36px;border-radius:50%;background:rgba(255,255,255,.05);
            border:0;color:rgba(232,240,235,.45);display:none;align-items:center;justify-content:center;
            cursor:pointer;transition:background .2s,color .2s;
        }
        .life-clear-chat:hover{background:rgba(255,255,255,.09);color:rgba(232,240,235,.75)}
        .life-clear-chat svg{width:16px;height:16px;stroke:currentColor;stroke-width:1.8;fill:none;stroke-linecap:round;stroke-linejoin:round}

        /* chat input bar */
        .life-input-wrap{
            width:100%;padding:8px 20px 32px;flex-shrink:0;
        }
        .life-input-row{
            display:flex;align-items:center;gap:10px;
            background:rgba(255,255,255,.06);
            border:1px solid rgba(255,255,255,.1);
            border-radius:22px;padding:12px 12px 12px 18px;
            transition:border-color .2s,background .2s;
        }
        .life-input-row:focus-within{
            border-color:rgba(74,124,89,.4);
            background:rgba(255,255,255,.08);
        }
        .life-input{
            flex:1;border:none;outline:none;background:transparent;
            font-size:15px;font-family:inherit;
            color:rgba(232,240,235,.85);font-weight:300;
        }
        .life-input::placeholder{color:rgba(232,240,235,.22)}
        .life-send{
            width:36px;height:36px;border-radius:50%;
            background:var(--life-green);border:none;
            display:flex;align-items:center;justify-content:center;
            cursor:pointer;transition:transform .2s,filter .2s;flex-shrink:0;
        }
        .life-send:active{transform:scale(.86)}
        .life-send svg{width:15px;height:15px;stroke:#fff;stroke-width:2.2;fill:none;stroke-linecap:round;stroke-linejoin:round;margin-left:1px}

        /* ── SORT MENU ── */
        #sort-menu{width:160px}

        /* ── TOAST ── */
        .toast{position:fixed;bottom:24px;left:50%;transform:translateX(-50%) scale(.85);background:#4a7c59;color:white;padding:11px 18px;border-radius:22px;display:flex;align-items:center;gap:7px;font-size:13px;font-weight:500;opacity:0;transition:all .3s cubic-bezier(.34,1.56,.64,1);z-index:1000;box-shadow:0 8px 24px rgba(74,124,89,.3)}
        .toast.show{opacity:1;transform:translateX(-50%) scale(1)}
        .toast svg{width:14px;height:14px;stroke:currentColor;stroke-width:2.5;fill:none;stroke-linecap:round;stroke-linejoin:round}

        ::-webkit-scrollbar{width:0;background:transparent}
    </style>
</head>
<body>

<!-- DRAWER -->
<div class="drawer-overlay" id="drawer-overlay" onclick="closeDrawer()"></div>
<div class="drawer" id="drawer">
    <div class="drawer-header">
        <div class="drawer-logo">bamboo.</div>
        <div class="drawer-sub">your quiet space</div>
    </div>
    <div class="drawer-nav">
        <div class="nav-section">Main</div>
        <div class="nav-item" id="nav-life" onclick="openMyLife()">
            <svg viewBox="0 0 24 24"><path d="M12 22V12M12 12C12 7 7 4 3 6M12 12C12 7 17 4 21 6"/></svg>
            my life.
        </div>
        <div class="nav-item active" id="nav-reminders" onclick="switchView('reminders')">
            <svg viewBox="0 0 24 24"><path d="M9 5H7a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2h-2M9 5a2 2 0 0 0 2 2h2a2 2 0 0 0 2-2M9 5a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2"/><path d="M9 12h6M9 16h4"/></svg>
            Reminders
        </div>
        <div class="nav-item" id="nav-dashboard" onclick="switchView('dashboard')">
            <svg viewBox="0 0 24 24"><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></svg>
            Dashboard
        </div>
        <div class="nav-section">Plan</div>
        <div class="nav-item" id="nav-calendar" onclick="switchView('calendar')">
            <svg viewBox="0 0 24 24"><rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>
            Calendar
        </div>
    </div>
    <div class="drawer-footer" id="drawer-stats">— reminders</div>
</div>

<!-- HEADER -->
<div class="header-wrap">
    <div class="menu-btn" onclick="openDrawer()"><span></span><span></span><span></span></div>
    <div class="logo" id="header-title" onclick="toggleBubble()">bamboo.</div>
    <div class="sort-btn" id="sort-btn-wrap" onclick="openSortMenu(event)">
        <svg viewBox="0 0 24 24"><path d="M4 6h16M7 12h10M10 18h4"/></svg>
    </div>
</div>

<!-- VIEWS -->
<div class="view active" id="view-reminders">
    <div class="list-wrap" id="reminder-list"></div>
</div>
<div class="view" id="view-dashboard">
    <div class="dash-wrap" id="dashboard-content"></div>
</div>
<div class="view" id="view-calendar">
    <div class="cal-wrap" id="calendar-content"></div>
</div>

<!-- REMINDER CHAT BUBBLE -->
<div class="chat-bubble-wrap" id="chat-bubble">
    <div class="chat-bubble">
        <textarea id="reminder-input" placeholder="add a reminder..." rows="1"></textarea>
        <button class="send-btn" onclick="sendReminder()">
            <svg viewBox="0 0 24 24"><path d="M22 2L11 13M22 2l-7 20-4-9-9-4 20-7z"/></svg>
        </button>
    </div>
</div>

<!-- CONTEXT MENU -->
<div id="ctx-menu" class="ctx-menu">
    <div class="cm-item" onclick="cmAction('edit')"><svg viewBox="0 0 24 24"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg> Edit</div>
    <div class="cm-item" onclick="cmAction('notes')"><svg viewBox="0 0 24 24"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg> Notes</div>
    <div class="cm-divider"></div>
    <div class="cm-item danger" onclick="cmAction('delete')"><svg viewBox="0 0 24 24"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg> Delete</div>
</div>

<!-- SORT MENU -->
<div id="sort-menu" class="ctx-menu">
    <div class="cm-item" onclick="setSortMode('default')"><svg viewBox="0 0 24 24"><path d="M12 20V4M5 13l7 7 7-7"/></svg> Newest First</div>
    <div class="cm-item" onclick="setSortMode('due')"><svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg> By Due Date</div>
</div>

<!-- REMINDER MODAL -->
<div class="modal" id="modal" onclick="closeIfOutside(event)">
    <div class="modal-box" onclick="event.stopPropagation()">
        <div class="modal-handle"></div>
        <div class="modal-title" id="modal-title">Edit</div>
        <div id="modal-body"></div>
        <input type="hidden" id="modal-rid">
        <input type="hidden" id="modal-action">
        <input type="hidden" id="modal-schedule-val">
        <input type="hidden" id="modal-color-val">
        <div class="modal-actions">
            <button class="btn btn-cancel" onclick="closeModal()">Cancel</button>
            <button class="btn btn-save" onclick="saveModal()">Save</button>
        </div>
    </div>
</div>

<!-- CAL EVENT MODAL -->
<div class="modal" id="cal-modal" onclick="closeCalIfOutside(event)">
    <div class="modal-box" onclick="event.stopPropagation()">
        <div class="modal-handle"></div>
        <div class="modal-title" id="cal-modal-title">New Event</div>
        <div id="cal-modal-body"></div>
        <input type="hidden" id="cal-modal-eid">
        <div class="modal-actions">
            <button class="btn btn-cancel" onclick="closeCalModal()">Cancel</button>
            <button class="btn btn-save" onclick="saveCalEvent()">Save</button>
        </div>
    </div>
</div>

<!-- MY LIFE OVERLAY -->
<div class="life-overlay hidden" id="life-overlay">
    <div class="life-glow"></div>

    <!-- shared top bar -->
    <div class="life-top">
        <div class="life-title-lbl" id="life-top-label">my life.</div>
        <div class="life-top-right">
            <!-- chat toggle (shown on rest page) -->
            <button class="life-icon-btn" id="life-chat-toggle-btn" onclick="switchLifeView('chat')" title="talk to bamboo">
                <svg viewBox="0 0 24 24"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
            </button>
            <!-- back to rest (shown on chat page) -->
            <button class="life-icon-btn" id="life-back-btn" onclick="switchLifeView('rest')" title="back" style="display:none">
                <svg viewBox="0 0 24 24"><path d="M19 12H5M12 5l-7 7 7 7"/></svg>
            </button>
            <button class="life-clear-chat" id="life-clear-chat-btn" onclick="clearLifeConversation()" title="clear chat">
                <svg viewBox="0 0 24 24"><path d="M3 6h18M8 6V4h8v2M6 6l1 14h10l1-14"/></svg>
            </button>
            <!-- menu -->
            <button class="life-icon-btn" onclick="openDrawer()" title="menu">
                <svg viewBox="0 0 24 24"><path d="M4 7h16M4 12h16M4 17h16"/></svg>
            </button>
        </div>
    </div>

    <!-- RESTING PAGE -->
    <div id="life-rest" style="display:flex">
        <!-- clock -->
        <div class="rest-time" id="rest-time">9:00</div>
        <div class="rest-date" id="rest-date"></div>
        <div class="life-day-nav">
            <button class="life-day-btn" onclick="shiftLifeDay(-1)" title="previous day">
                <svg viewBox="0 0 24 24"><path d="M15 18l-6-6 6-6"/></svg>
            </button>
            <div class="life-day-chip" id="life-day-chip" onclick="setLifeDay(getTodayStr())">today</div>
            <button class="life-day-btn" onclick="shiftLifeDay(1)" title="next day">
                <svg viewBox="0 0 24 24"><path d="M9 18l6-6-6-6"/></svg>
            </button>
        </div>

        <!-- active timer -->
        <div class="rest-timer hidden" id="rest-timer">
            <div>
                <div class="rest-timer-label" id="rest-timer-label">timer</div>
                <div class="rest-timer-time" id="rest-timer-display">00:00</div>
            </div>
            <button class="rest-timer-cancel" onclick="cancelTimer()">cancel</button>
        </div>

        <!-- current task -->
        <div class="rest-now" id="rest-now-wrap">
            <div class="rest-now-label">now</div>
            <div class="rest-now-task" id="rest-now-task">what are you up to?</div>
        </div>

        <!-- next task -->
        <div class="rest-next" id="rest-next-wrap" style="display:none">
            <div class="rest-next-label">up next</div>
            <div class="rest-next-task" id="rest-next-task"></div>
        </div>

        <!-- day progress -->
        <div class="rest-progress-wrap">
            <div class="rest-progress-track">
                <div class="rest-progress-fill" id="rest-progress-fill" style="width:0%"></div>
            </div>
            <div class="rest-progress-label" id="rest-progress-label"></div>
        </div>

        <!-- gen plan button -->
        <button class="gen-plan-btn" onclick="generateDayPlan()">
            <svg viewBox="0 0 24 24"><path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/></svg>
            <span id="gen-plan-txt">plan my day</span>
        </button>

        <!-- day timeline -->
        <div id="all-day-events"></div>
        <div class="rest-plan" id="rest-plan">
            <div class="no-plan" id="rest-no-plan">
                <div class="rest-emblem">
                    <svg width="40" height="44" viewBox="0 0 44 44" fill="none">
                        <line x1="22" y1="40" x2="22" y2="10" stroke="rgba(90,138,106,0.7)" stroke-width="2.5" stroke-linecap="round"/>
                        <line x1="22" y1="30" x2="32" y2="22" stroke="rgba(90,138,106,0.6)" stroke-width="2" stroke-linecap="round"/>
                        <path d="M32 22 C36 19 40 18 43 20 C39 22 35 24 32 22Z" fill="rgba(90,138,106,0.6)"/>
                        <line x1="22" y1="22" x2="12" y2="16" stroke="rgba(90,138,106,0.5)" stroke-width="2" stroke-linecap="round"/>
                        <path d="M12 16 C8 13 4 12 1 14 C5 16 9 17 12 16Z" fill="rgba(90,138,106,0.55)"/>
                    </svg>
                </div>
                <div class="no-plan-text">tap "plan my day" and i'll build your schedule</div>
            </div>
        </div>

        <!-- rest input -->
        <div class="rest-input-wrap">
            <div class="rest-input-row">
                <input class="rest-input" id="rest-input" placeholder="tell me what's up..." autocomplete="off">
                <button class="rest-send" onclick="sendRestMsg()">
                    <svg viewBox="0 0 24 24"><path d="M22 2L11 13M22 2l-7 20-4-9-9-4 20-7z"/></svg>
                </button>
            </div>
        </div>
    </div>

    <!-- AI CHAT PAGE -->
    <div id="life-chat" class="hidden" style="display:none;flex-direction:column;flex:1;width:100%;max-width:500px;overflow:hidden">
        <div class="life-msgs" id="life-msgs"></div>
        <div class="life-input-wrap">
            <div class="life-input-row">
                <input class="life-input" id="life-input" placeholder="ask bamboo anything..." autocomplete="off">
                <button class="life-send" onclick="sendLifeMsg()">
                    <svg viewBox="0 0 24 24"><path d="M22 2L11 13M22 2l-7 20-4-9-9-4 20-7z"/></svg>
                </button>
            </div>
        </div>
    </div>
</div>

<script>
/* ── HAPTICS ── */
function haptic(p=10){
    if(window.ReactNativeWebView){let s='light';if(Array.isArray(p))s=p.length>2?'heavy':'medium';else if(p>=40)s='medium';window.ReactNativeWebView.postMessage(JSON.stringify({type:'HAPTIC',style:s}));return;}
    if(navigator.vibrate){try{navigator.vibrate(p);}catch(e){}}
}

/* ── STATE ── */
let remindersData=[], calendarEvents=[], currentView='reminders';
let currentSortMode='default', ctxTarget=null, pressTimer;
let calDate=new Date(), calSelected=null;
let lifeHistory=[], lifeOpen=false, lifeClockInterval=null;
let dayPlan=[], currentTaskOverride=null;
let selectedPlanDate=getTodayStr(), dayPlansByDate={};
let planGenerationCount=0;
let lifeAiBusy=false, lastAiErrorAt=0;
let pendingConfirmActions=null, pendingConfirmText='';
let activeTimer=null, timerInterval=null, timerEndTime=0;
let lifeViewMode='rest'; // 'rest' | 'chat'
let lifeMessages=[];
let lastLocalPlanTask=null;
let lifeActionLog=[];
const LIFE_STORE_KEY='bamboo.life.20260503_202810.v1';

/* ── TEXTAREA ── */
const tx=document.getElementById('reminder-input');
tx.addEventListener('input',function(){this.style.height='auto';this.style.height=this.scrollHeight+'px';if(!this.value)this.style.height='24px';});
tx.addEventListener('keydown',function(e){if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();sendReminder();}});
document.getElementById('life-input').addEventListener('keydown',e=>{if(e.key==='Enter'){e.preventDefault();sendLifeMsg();}});
document.getElementById('rest-input').addEventListener('keydown',e=>{if(e.key==='Enter'){e.preventDefault();sendRestMsg();}});

/* ── UTILS ── */
function getTodayStr(){return dateStr(new Date());}
function getTimestamp(){const now=new Date();let h=now.getHours();const ampm=h>=12?'PM':'AM';h=h%12||12;return`Today at ${h}:${now.getMinutes().toString().padStart(2,'0')} ${ampm}`;}
function escHtml(s){return(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}
function escAttr(s){return escHtml(s).replace(/"/g,'&quot;').replace(/'/g,'&#39;');}
function dateStr(d){return`${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;}
function addDaysToDateStr(ds,delta){const d=new Date(ds+'T12:00:00');d.setDate(d.getDate()+delta);return dateStr(d);}
function isSelectedPlanToday(){return selectedPlanDate===getTodayStr();}
function setLifeDay(ds){
    dayPlansByDate[selectedPlanDate]=dayPlan;
    selectedPlanDate=ds||getTodayStr();
    dayPlan=Array.isArray(dayPlansByDate[selectedPlanDate])?dayPlansByDate[selectedPlanDate]:[];
    if(dayPlan.length)normalizePlan();
    updateLifeClockDisplay();
    updateRestPage();
    saveLifeState();
}
function shiftLifeDay(delta){haptic(10);setLifeDay(addDaysToDateStr(selectedPlanDate,delta));}
function nextDateForWeekday(day){
    const days={sunday:0,monday:1,tuesday:2,wednesday:3,thursday:4,friday:5,saturday:6};
    const target=days[String(day||'').toLowerCase()];
    const d=new Date();
    if(target===undefined)return getTodayStr();
    const diff=(target-d.getDay()+7)%7;
    d.setDate(d.getDate()+diff);
    return dateStr(d);
}
function currentWeekDateForWeekday(day){
    return nextDateForWeekday(day);
}

function saveLifeState(){
    try{
        dayPlansByDate[selectedPlanDate]=dayPlan;
        localStorage.setItem(LIFE_STORE_KEY, JSON.stringify({
            history: lifeHistory.slice(-30),
            messages: lifeMessages.slice(-80),
            dayPlan,
            dayPlansByDate,
            selectedPlanDate,
            currentTaskOverride,
            lastLocalPlanTask,
            planGenerationCount,
            lifeActionLog: lifeActionLog.slice(-20),
            savedFor: getTodayStr()
        }));
    }catch(e){}
}
function loadLifeState(){
    try{
        const raw=localStorage.getItem(LIFE_STORE_KEY);
        if(!raw)return;
        const state=JSON.parse(raw);
        const isToday=state.savedFor===getTodayStr();
        lifeHistory=Array.isArray(state.history)?state.history.slice(-30):[];
        lifeMessages=Array.isArray(state.messages)?state.messages.slice(-80):[];
        dayPlansByDate=state.dayPlansByDate&&typeof state.dayPlansByDate==='object'?state.dayPlansByDate:{};
        selectedPlanDate=state.selectedPlanDate||getTodayStr();
        dayPlan=Array.isArray(dayPlansByDate[selectedPlanDate])?dayPlansByDate[selectedPlanDate]:(Array.isArray(state.dayPlan)?state.dayPlan:[]);
        if(dayPlan.length)normalizePlan();
        currentTaskOverride=isToday?(state.currentTaskOverride||null):null;
        lastLocalPlanTask=isToday?(state.lastLocalPlanTask||null):null;
        planGenerationCount=isToday?(state.planGenerationCount||0):0;
        lifeActionLog=Array.isArray(state.lifeActionLog)?state.lifeActionLog.slice(-20):[];
    }catch(e){}
}
function renderStoredLifeMessages(){
    const msgs=document.getElementById('life-msgs');
    if(!msgs)return;
    msgs.innerHTML='';
    lifeMessages=lifeMessages.map(m=>({...m,id:m.id||`msg-${m.ts||Date.now()}-${Math.random().toString(36).slice(2,7)}`}));
    lifeMessages.forEach(m=>appendLifeMsg(m.role,m.text,false,m.id));
    msgs.scrollTop=msgs.scrollHeight;
}

function smartTime(updatedAt, created){
    if(created&&created>0){
        const now=Date.now(),diff=now-created,days=Math.floor(diff/86400000);
        const d=new Date(created);const h=d.getHours(),ampm=h>=12?'PM':'AM';const hh=h%12||12,mm=d.getMinutes().toString().padStart(2,'0');
        if(days===0)return`Today at ${hh}:${mm} ${ampm}`;
        if(days===1)return`Yesterday`;
        if(days<=5)return`${days} days ago`;
        const M=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
        return`${M[d.getMonth()]} ${d.getDate()}`;
    }
    return updatedAt||'Just now';
}
function getDueBadge(r){
    if(!r.due_timestamp||!r.due_label)return null;
    const diff=r.due_timestamp-Date.now();
    const days=Math.floor(diff/86400000);
    if(diff<0)return{label:r.due_label,cls:'badge-red'};
    if(days===0)return{label:r.due_label,cls:'badge-orange'};
    return{label:r.due_label,cls:'badge-blue'};
}
function getDaysLeft(r){
    if(!r.schedule_preset||r.schedule_preset==='none'||!r.schedule_start)return null;
    let total=0,ms=86400000;
    if(r.schedule_preset==='day'){total=3;ms=86400000;}
    if(r.schedule_preset==='week'){total=14;ms=86400000;}
    if(r.schedule_preset==='month'){total=30;ms=172800000;}
    return Math.max(0,total-(r.notifications_sent||0));
}
function isOverdue(r){const l=getDaysLeft(r);return l!==null&&l<=0;}

function formatMinutes(mins){if(mins<60)return`${mins}m`;const h=Math.floor(mins/60),m=mins%60;return m?`${h}h ${m}m`:`${h}h`;}
function timeToMins(t){if(!t||!String(t).includes(':'))return null;const[h,m]=String(t).split(':').map(Number);if(Number.isNaN(h)||Number.isNaN(m))return null;return h*60+m;}
function nowMins(){const n=new Date();return n.getHours()*60+n.getMinutes();}
function minsTo12(m){const h=Math.floor(m/60)%24,mm=m%60;const ampm=h>=12?'pm':'am';return`${h%12||12}:${mm.toString().padStart(2,'0')}${ampm}`;}

/* ── FETCH ── */
async function fetchAll(){
    const[rR,eR]=await Promise.all([fetch('/api/reminders'),fetch('/api/calendar')]);
    remindersData=await rR.json(); calendarEvents=await eR.json();
    renderReminders(); updateStats();
    if(currentView==='dashboard')renderDashboard();
    if(currentView==='calendar')renderCalendar();
    if(lifeOpen)updateRestPage();
}
async function fetchReminders(){
    const r=await fetch('/api/reminders');remindersData=await r.json();
    renderReminders();updateStats();
    if(currentView==='dashboard')renderDashboard();
    if(currentView==='calendar')renderCalendar();
    if(lifeOpen)updateRestPage();
}
async function fetchCalendar(){
    const r=await fetch('/api/calendar');calendarEvents=await r.json();
    if(currentView==='calendar')renderCalendar();
}

/* ── RENDER REMINDERS ── */
function renderReminders(){
    let sorted=[...remindersData];
    sorted.sort((a,b)=>{
        if(a.completed!==b.completed)return a.completed?1:-1;
        if(currentSortMode==='color'){if((a.color||'')===(b.color||''))return b.id-a.id;return(a.color||'').localeCompare(b.color||'');}
        if(currentSortMode==='schedule'){const aS=(a.schedule_preset&&a.schedule_preset!=='none')?1:0,bS=(b.schedule_preset&&b.schedule_preset!=='none')?1:0;if(aS===bS)return b.id-a.id;return bS-aS;}
        if(currentSortMode==='due'){const aD=a.due_timestamp||0,bD=b.due_timestamp||0;if(!aD&&!bD)return b.id-a.id;if(!aD)return 1;if(!bD)return -1;return aD-bD;}
        return b.id-a.id;
    });
    const active=sorted.filter(r=>!r.completed), done=sorted.filter(r=>r.completed);
    const list=document.getElementById('reminder-list');
    if(active.length===0&&done.length===0){
        list.innerHTML=`<div class="empty-state">nothing here yet.<br><span style="font-size:12px;opacity:.6">tap bamboo. to add one</span></div>`;
        return;
    }
    let html='';
    active.forEach((r,i)=>html+=renderItem(r,i));
    if(done.length){html+=`<div class="section-lbl">Completed</div>`;done.forEach((r,i)=>html+=renderItem(r,active.length+i+1));}
    list.innerHTML=html;
}

function renderItem(r,idx){
    const delay=idx*0.04;
    const due=getDueBadge(r);
    const dLeft=null;
    const over=false;
    const border=(r.color&&!r.completed)?`border-left-color:${r.color};`:'';
    const rJ=JSON.stringify(r).replace(/'/g,"&#39;").replace(/"/g,"&quot;");

    let meta=`<span><svg class="meta-ico" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>${smartTime(r.updated_at,r.created_timestamp)}</span>`;
    if(due)meta+=`<span class="badge ${due.cls}"><svg class="meta-ico" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>${due.label}</span>`;
    if(dLeft!==null&&!over)meta+=`<span class="badge badge-green">${dLeft}d left</span>`;
    if(over)meta+=`<span class="badge badge-red">overdue</span>`;
    if(r.notes)meta+=`<span><svg class="meta-ico" viewBox="0 0 24 24"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>notes</span>`;

    return`<div class="reminder-item ${r.completed?'completed':''} ${over?'overdue':''}"
        id="item-${r.id}" style="animation-delay:${delay}s;${border}"
        onclick="handleItemClick(event,${r.id},${!r.completed})"
        oncontextmenu="handleCtx(event,'${rJ}')"
        ontouchstart="handleTouchStart(event,'${rJ}')"
        ontouchend="handleTouchEnd(event)"
        ontouchcancel="handleTouchEnd(event)">
        <div class="r-text">${escHtml(r.text)}</div>
        <div class="r-meta">${meta}</div>
    </div>`;
}

/* ── SEND REMINDER ── */
async function sendReminder(){
    const input=document.getElementById('reminder-input');
    const text=input.value.trim();if(!text)return;
    const now=Date.now();
    let due_timestamp=0,due_label='';
    try{
        const pr=await fetch('/api/parse-date',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text})});
        const pd=await pr.json();
        if(pd.has_date){due_timestamp=pd.timestamp_ms||0;due_label=pd.label||'';}
    }catch(e){}
    await fetch('/api/reminders',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text,updated_at:getTimestamp(),created_timestamp:now,due_timestamp,due_label})});
    input.value='';input.style.height='24px';
    document.getElementById('chat-bubble').classList.remove('show');
    haptic(50);fetchReminders();
}

/* ── ITEM CLICK ── */
async function handleItemClick(e,id,complete){
    if(e.detail>1)return;
    haptic(15);
    await fetch(`/api/reminders/${id}`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({completed:complete,updated_at:getTimestamp(),completed_date:complete?getTodayStr():''})});
    fetchReminders();
}

/* ── CONTEXT MENU ── */
function handleCtx(e,rJ){
    e.preventDefault();
    ctxTarget=JSON.parse(rJ.replace(/&quot;/g,'"').replace(/&#39;/g,"'"));
    const menu=document.getElementById('ctx-menu');menu.classList.add('show');
    let x=e.clientX,y=e.clientY;
    if(x+190>window.innerWidth)x=window.innerWidth-195;
    if(y+240>window.innerHeight)y=window.innerHeight-245;
    menu.style.left=x+'px';menu.style.top=y+'px';
}
function handleTouchStart(e,rJ){pressTimer=setTimeout(()=>{handleCtx(e,rJ);haptic([30,40]);},600);}
function handleTouchEnd(){clearTimeout(pressTimer);}
function cmAction(act){
    document.getElementById('ctx-menu').classList.remove('show');haptic(15);
    if(!ctxTarget)return;
    if(act==='delete'){deleteReminder(ctxTarget.id);return;}
    openModal(act,ctxTarget);
}
async function deleteReminder(id){await fetch(`/api/reminders/${id}`,{method:'DELETE'});fetchReminders();}

/* ── MODALS ── */
const COLORS=['#6f8f84','#7fa27a','#c88f64','#b89f78','#9b8aa8','#b86f62','#7d8f96','#a7b89a','#d0b58a','#8f9f88'];
function openModal(act,r){
    document.getElementById('modal-rid').value=r.id;
    document.getElementById('modal-action').value=act;
    const title=document.getElementById('modal-title');
    const body=document.getElementById('modal-body');
    if(act==='edit'){
        title.textContent='Edit';
        body.innerHTML=`<textarea id="modal-val" class="modal-inp">${escHtml(r.text)}</textarea>`;
        document.getElementById('modal').classList.add('show');
        setTimeout(()=>document.getElementById('modal-val').focus(),100);
    }else if(act==='notes'){
        title.textContent='Notes';
        body.innerHTML=`<textarea id="modal-val" class="modal-inp" placeholder="Add details...">${escHtml(r.notes||'')}</textarea>`;
        document.getElementById('modal').classList.add('show');
        setTimeout(()=>document.getElementById('modal-val').focus(),100);
    }else if(act==='color'){
        title.textContent='Color';
        document.getElementById('modal-color-val').value=r.color||'';
        let h='<div class="color-grid">';
        h+=`<div class="c-swatch c-clear ${!r.color?'active':''}" onclick="setColor(this,'')"><svg viewBox="0 0 24 24" fill="none"><path d="M18 6L6 18M6 6l12 12" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg></div>`;
        COLORS.forEach(c=>h+=`<div class="c-swatch ${r.color===c?'active':''}" style="background:${c}" onclick="setColor(this,'${c}')"></div>`);
        h+='</div>';body.innerHTML=h;
        document.getElementById('modal').classList.add('show');
    }else if(act==='schedule'){
        title.textContent='Schedule';
        document.getElementById('modal-schedule-val').value=r.schedule_preset||'none';
        body.innerHTML=`<div style="font-size:12px;color:var(--muted);margin-bottom:12px;font-weight:300">Send reminders over the selected period.</div>
        <div class="preset-grid">
            <div class="preset-card ${r.schedule_preset==='day'?'active':''}" onclick="setPreset(this,'day')"><div class="preset-name">Day</div><div class="preset-desc">3 notifs</div></div>
            <div class="preset-card ${r.schedule_preset==='week'?'active':''}" onclick="setPreset(this,'week')"><div class="preset-name">Week</div><div class="preset-desc">14 notifs</div></div>
            <div class="preset-card ${r.schedule_preset==='month'?'active':''}" onclick="setPreset(this,'month')"><div class="preset-name">Month</div><div class="preset-desc">15 notifs</div></div>
        </div>`;
        document.getElementById('modal').classList.add('show');
    }
}
function setColor(el,c){haptic(10);document.querySelectorAll('.c-swatch').forEach(x=>x.classList.remove('active'));el.classList.add('active');document.getElementById('modal-color-val').value=c;}
function setPreset(el,p){haptic(10);document.querySelectorAll('.preset-card').forEach(x=>x.classList.remove('active'));el.classList.add('active');document.getElementById('modal-schedule-val').value=p;}
function closeModal(){document.getElementById('modal').classList.remove('show');}
function closeIfOutside(e){if(e.target.id==='modal')closeModal();}
async function saveModal(){
    haptic([20,30]);
    const id=document.getElementById('modal-rid').value;
    const act=document.getElementById('modal-action').value;
    const payload={updated_at:getTimestamp()};
    if(act==='edit')payload.text=document.getElementById('modal-val').value;
    else if(act==='notes')payload.notes=document.getElementById('modal-val').value;
    else if(act==='schedule'){payload.schedule_preset=document.getElementById('modal-schedule-val').value;payload.schedule_start=Date.now();payload.notifications_sent=0;}
    else if(act==='color')payload.color=document.getElementById('modal-color-val').value;
    await fetch(`/api/reminders/${id}`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
    closeModal();fetchReminders();
}

/* ── CALENDAR ── */
function renderCalendar(){
    const container=document.getElementById('calendar-content');
    const year=calDate.getFullYear(),month=calDate.getMonth();
    const MN=['January','February','March','April','May','June','July','August','September','October','November','December'];
    const today=new Date(),todayStr=getTodayStr();
    const firstDay=new Date(year,month,1).getDay();
    const daysInMonth=new Date(year,month+1,0).getDate();
    const prevDays=new Date(year,month,0).getDate();
    const selStr=calSelected?`${calSelected.getFullYear()}-${String(calSelected.getMonth()+1).padStart(2,'0')}-${String(calSelected.getDate()).padStart(2,'0')}`:'';

    const evMap={};
    calendarEvents.forEach(e=>{
        const dates=getRecurringDates(e, year, month);
        dates.forEach(ds=>{if(!evMap[ds])evMap[ds]=[];evMap[ds].push({...e});});
    });
    remindersData.filter(r=>!r.completed&&r.due_timestamp>0).forEach(r=>{
        const d=new Date(r.due_timestamp);
        const ds=`${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
        if(!evMap[ds])evMap[ds]=[];
        evMap[ds].push({id:'r'+r.id,title:r.text,color:r.color||'#5A8A6A',isReminder:true,date:ds});
    });

    let grid='<div class="cal-dl">Su</div><div class="cal-dl">Mo</div><div class="cal-dl">Tu</div><div class="cal-dl">We</div><div class="cal-dl">Th</div><div class="cal-dl">Fr</div><div class="cal-dl">Sa</div>';
    for(let i=firstDay-1;i>=0;i--){grid+=`<div class="cal-day other-month"><div class="cal-dn">${prevDays-i}</div></div>`;}
    for(let d=1;d<=daysInMonth;d++){
        const ds=`${year}-${String(month+1).padStart(2,'0')}-${String(d).padStart(2,'0')}`;
        const isT=ds===todayStr,isSel=ds===selStr;
        const dots=(evMap[ds]||[]).slice(0,3).map(e=>`<div class="cal-dot" style="background:${e.color||'var(--accent)'}"></div>`).join('');
        grid+=`<div class="cal-day ${isT?'today':''} ${isSel?'selected':''}" onclick="selectDay('${ds}')"><div class="cal-dn">${d}</div>${dots}</div>`;
    }
    const total=Math.ceil((firstDay+daysInMonth)/7)*7;
    for(let d=1;d<=(total-firstDay-daysInMonth);d++){grid+=`<div class="cal-day other-month"><div class="cal-dn">${d}</div></div>`;}

    let evHtml='';
    if(selStr){
        const dayEvs=evMap[selStr]||[];
        const nice=new Date(selStr+'T12:00:00');
        const M=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
        evHtml+=`<div style="font-size:12px;font-weight:500;color:var(--muted);margin-bottom:10px;letter-spacing:.5px">${M[nice.getMonth()]} ${nice.getDate()}</div>`;
        if(dayEvs.length===0){evHtml+=`<div style="color:var(--muted);font-size:13px;font-weight:300;padding:10px 0">Nothing scheduled</div>`;}
        dayEvs.forEach(e=>{
            const timeStr=e.time?`${e.time}${e.end_time?' – '+e.end_time:''}`:e.isReminder?'reminder':'All day';
            const recStr=e.recurring&&e.recurring!=='none'?`<div class="cal-ev-rec">↻ ${e.recurring}</div>`:'';
            const isRem=e.isReminder;
            evHtml+=`<div class="cal-ev-item ${isRem?'reminder-on-cal':''}" onclick="${isRem?`''`:`openCalEvent(${e.id})`}">
                <div class="cal-ev-dot" style="background:${e.color||'var(--accent)'}"></div>
                <div style="flex:1">
                    <div class="cal-ev-title">${escHtml(e.title||'')}</div>
                    <div class="cal-ev-meta">${timeStr}${isRem?' · reminder':''}</div>
                    ${recStr}
                </div>
            </div>`;
        });
    }else{evHtml+=`<div style="color:var(--muted);font-size:13px;font-weight:300;padding:10px 0">Select a day to see events</div>`;}
    evHtml+=`<div class="cal-add-btn" onclick="openAddEvent('${selStr||todayStr}')"><svg viewBox="0 0 24 24"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>Add Event</div>`;

    container.innerHTML=`
        <div class="cal-header-row">
            <button class="cal-nav" onclick="calNav(-1)"><svg viewBox="0 0 24 24"><polyline points="15 18 9 12 15 6"/></svg></button>
            <div class="cal-month-lbl">${MN[month]} ${year}</div>
            <button class="cal-nav" onclick="calNav(1)"><svg viewBox="0 0 24 24"><polyline points="9 18 15 12 9 6"/></svg></button>
        </div>
        <div class="cal-grid">${grid}</div>
        <div class="cal-ev-list">${evHtml}</div>`;
}

function getRecurringDates(ev, year, month){
    const dates=[];
    const baseDate=new Date(ev.date+'T12:00:00');
    if(ev.recurring==='none'||!ev.recurring){
        if(baseDate.getFullYear()===year&&baseDate.getMonth()===month){dates.push(ev.date);}
        return dates;
    }
    const daysInMonth=new Date(year,month+1,0).getDate();
    for(let d=1;d<=daysInMonth;d++){
        const candidate=new Date(year,month,d);
        const ds=`${year}-${String(month+1).padStart(2,'0')}-${String(d).padStart(2,'0')}`;
        if(ev.recurring==='daily'){dates.push(ds);}
        else if(ev.recurring==='weekly'){if(candidate.getDay()===baseDate.getDay())dates.push(ds);}
        else if(ev.recurring==='weekdays'){const day=candidate.getDay();if(day>=1&&day<=5)dates.push(ds);}
        else if(ev.recurring==='monthly'){if(candidate.getDate()===baseDate.getDate())dates.push(ds);}
    }
    return dates;
}

function calNav(dir){calDate.setMonth(calDate.getMonth()+dir);renderCalendar();}
function selectDay(ds){haptic(10);calSelected=new Date(ds+'T12:00:00');renderCalendar();}
function openCalEvent(id){const e=calendarEvents.find(x=>x.id===id);if(e)showCalModal(e);}
function openAddEvent(dateStr){haptic(10);showCalModal(null,dateStr);}

function showCalModal(ev,defaultDate){
    document.getElementById('cal-modal-eid').value=ev?ev.id:'';
    document.getElementById('cal-modal-title').textContent=ev?'Edit Event':'New Event';
    document.getElementById('cal-modal-body').innerHTML=`
        <input class="modal-inp" id="ce-title" placeholder="Event title" value="${ev?escAttr(ev.title):''}">
        <input class="modal-inp" id="ce-date" type="date" value="${ev?ev.date:(defaultDate||getTodayStr())}">
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px">
            <input class="modal-inp" id="ce-time" type="time" value="${ev&&ev.time?ev.time:''}">
            <input class="modal-inp" id="ce-end" type="time" value="${ev&&ev.end_time?ev.end_time:''}">
        </div>
        <select class="modal-inp" id="ce-rec">
            <option value="none" ${!ev||ev.recurring==='none'?'selected':''}>No repeat</option>
            <option value="daily" ${ev&&ev.recurring==='daily'?'selected':''}>Daily</option>
            <option value="weekdays" ${ev&&ev.recurring==='weekdays'?'selected':''}>Weekdays (Mon–Fri)</option>
            <option value="weekly" ${ev&&ev.recurring==='weekly'?'selected':''}>Weekly</option>
            <option value="monthly" ${ev&&ev.recurring==='monthly'?'selected':''}>Monthly</option>
        </select>
        <input class="modal-inp" id="ce-color" placeholder="Color (hex, optional)" value="${ev&&ev.color?escAttr(ev.color):''}">
        <textarea class="modal-inp" id="ce-notes" placeholder="Notes (optional)" style="min-height:60px">${ev?escHtml(ev.notes||''):''}</textarea>
        ${ev?`<div style="text-align:right"><span onclick="deleteCalEvent(${ev.id})" style="font-size:12px;color:var(--red);cursor:pointer">Delete event</span></div>`:''}
    `;
    document.getElementById('cal-modal').classList.add('show');
    setTimeout(()=>document.getElementById('ce-title').focus(),100);
}
function closeCalModal(){document.getElementById('cal-modal').classList.remove('show');}
function closeCalIfOutside(e){if(e.target.id==='cal-modal')closeCalModal();}
async function saveCalEvent(){
    haptic([20,30]);
    const eid=document.getElementById('cal-modal-eid').value;
    const d={title:document.getElementById('ce-title').value,date:document.getElementById('ce-date').value,time:document.getElementById('ce-time').value,end_time:document.getElementById('ce-end').value,recurring:document.getElementById('ce-rec').value,color:document.getElementById('ce-color').value,notes:document.getElementById('ce-notes').value,created_timestamp:Date.now()};
    if(eid){await fetch(`/api/calendar/${eid}`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(d)});}
    else{await fetch('/api/calendar',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(d)});}
    closeCalModal();
    const r=await fetch('/api/calendar');calendarEvents=await r.json();renderCalendar();
}
async function deleteCalEvent(id){
    await fetch(`/api/calendar/${id}`,{method:'DELETE'});
    closeCalModal();const r=await fetch('/api/calendar');calendarEvents=await r.json();renderCalendar();
}

/* ── DASHBOARD ── */
function renderDashboard(){
    const today=getTodayStr();
    const total=remindersData.length,completed=remindersData.filter(r=>r.completed).length,active=total-completed;
    const byDate={};remindersData.forEach(r=>{if(r.completed&&r.completed_date)byDate[r.completed_date]=(byDate[r.completed_date]||0)+1;});
    let streak=0;const cd=new Date();const todayHas=byDate[today]>0;if(!todayHas)cd.setDate(cd.getDate()-1);
    for(let i=0;i<365;i++){const ds=cd.toISOString().slice(0,10);if(byDate[ds]){streak++;cd.setDate(cd.getDate()-1);}else break;}
    const dots=[];
    for(let i=13;i>=0;i--){const d=new Date();d.setDate(d.getDate()-i);const ds=d.toISOString().slice(0,10);const lbl=['Su','Mo','Tu','We','Th','Fr','Sa'][d.getDay()];dots.push({label:lbl,type:ds===today?(byDate[ds]?'done':'today'):ds<today?(byDate[ds]?'done':'miss'):'future'});}
    const dotsHtml=dots.map(d=>`<div class="s-dot ${d.type}">${d.label}</div>`).join('');
    const msg=streak===0?'Complete a task to start':streak===1?'Keep it up!':` ${streak} days strong 🌿`;
    document.getElementById('dashboard-content').innerHTML=`
        <div style="height:4px"></div>
        <div class="dash-card"><div class="dash-lbl">Streak</div><div class="streak-num">${streak}</div><div class="streak-sub">${msg}</div><div class="streak-dots" style="margin-top:16px">${dotsHtml}</div></div>
        <div class="dash-card"><div class="dash-lbl">Overview</div><div class="stats-row"><div class="stat-cell"><div class="stat-val">${total}</div><div class="stat-lbl">Total</div></div><div class="stat-cell"><div class="stat-val">${active}</div><div class="stat-lbl">Active</div></div><div class="stat-cell"><div class="stat-val">${completed}</div><div class="stat-lbl">Done</div></div></div></div>`;
}

/* ── DRAWER / VIEWS ── */
function openDrawer(){haptic(10);document.getElementById('drawer').classList.add('show');document.getElementById('drawer-overlay').classList.add('show');}
function closeDrawer(){document.getElementById('drawer').classList.remove('show');document.getElementById('drawer-overlay').classList.remove('show');}
function switchView(v){
    haptic(10);
    if(lifeOpen)closeMyLife();
    closeDrawer();currentView=v;
    document.querySelectorAll('.view').forEach(x=>x.classList.remove('active'));
    document.querySelectorAll('.nav-item').forEach(x=>x.classList.remove('active'));
    document.getElementById(`view-${v}`).classList.add('active');
    document.getElementById(`nav-${v}`).classList.add('active');
    const titles={reminders:'bamboo.',dashboard:'dashboard.',calendar:'calendar.'};
    document.getElementById('header-title').textContent=titles[v]||'bamboo.';
    document.getElementById('sort-btn-wrap').style.display=v==='reminders'?'':'none';
    document.getElementById('chat-bubble').classList.remove('show');
    if(v==='dashboard')renderDashboard();
    if(v==='calendar')renderCalendar();
}
function updateStats(){
    const a=remindersData.filter(r=>!r.completed).length;
    document.getElementById('drawer-stats').textContent=`${a} active reminder${a!==1?'s':''}`;
}

/* ── BODY CLICK ── */
document.body.addEventListener('click',(e)=>{
    if(!e.target.closest('.ctx-menu'))document.getElementById('ctx-menu').classList.remove('show'),document.getElementById('sort-menu').classList.remove('show');
    if(!e.target.closest('.life-overlay')&&!e.target.closest('.reminder-item')&&!e.target.closest('.modal')&&!e.target.closest('.ctx-menu')&&!e.target.closest('.chat-bubble-wrap')&&!e.target.closest('.logo')&&!e.target.closest('.sort-btn')&&!e.target.closest('.menu-btn')&&!e.target.closest('.drawer')&&currentView==='reminders'){
        const b=document.getElementById('chat-bubble');
        if(b.classList.contains('show')){if(!document.getElementById('reminder-input').value.trim())b.classList.remove('show');}
        else{haptic(10);b.classList.add('show');setTimeout(()=>document.getElementById('reminder-input').focus(),300);}
    }
});
function toggleBubble(){
    if(currentView!=='reminders')return;
    haptic(10);const b=document.getElementById('chat-bubble');
    if(b.classList.contains('show'))b.classList.remove('show');
    else{b.classList.add('show');setTimeout(()=>document.getElementById('reminder-input').focus(),300);}
}
function openSortMenu(e){
    e.stopPropagation();haptic(10);const m=document.getElementById('sort-menu');m.classList.add('show');
    const r=e.currentTarget.getBoundingClientRect();m.style.top=(r.bottom+6)+'px';m.style.left=(r.right-162)+'px';
}
function setSortMode(m){haptic(15);currentSortMode=m;document.getElementById('sort-menu').classList.remove('show');renderReminders();}

/* ══════════════════════════════════════
   MY LIFE SYSTEM
══════════════════════════════════════ */

function openMyLife(silent=false){
    if(!silent)haptic(10);closeDrawer();lifeOpen=true;
    document.querySelectorAll('.nav-item').forEach(x=>x.classList.remove('active'));
    document.getElementById('nav-life').classList.add('active');
    document.getElementById('life-overlay').classList.remove('hidden');
    switchLifeView('rest');
    startLifeClock();
    updateRestPage();
    document.getElementById('rest-input').focus();
}

function closeMyLife(){
    lifeOpen=false;
    document.getElementById('life-overlay').classList.add('hidden');
    document.querySelectorAll('.nav-item').forEach(x=>x.classList.remove('active'));
    const nav=document.getElementById(`nav-${currentView}`);
    if(nav)nav.classList.add('active');
    clearInterval(lifeClockInterval);
}

function switchLifeView(mode){
    lifeViewMode=mode;
    const restEl=document.getElementById('life-rest');
    const chatEl=document.getElementById('life-chat');
    const toggleBtn=document.getElementById('life-chat-toggle-btn');
    const backBtn=document.getElementById('life-back-btn');
    const clearBtn=document.getElementById('life-clear-chat-btn');
    const label=document.getElementById('life-top-label');

    if(mode==='rest'){
        restEl.classList.remove('hidden');
        chatEl.classList.add('hidden');
        restEl.style.display='flex';
        chatEl.style.display='none';
        toggleBtn.style.display='flex';
        backBtn.style.display='none';
        clearBtn.style.display='none';
        label.textContent='my life.';
        setTimeout(()=>document.getElementById('rest-input').focus(),100);
    }else{
        chatEl.classList.remove('hidden');
        restEl.classList.add('hidden');
        restEl.style.display='none';
        chatEl.style.display='flex';
        toggleBtn.style.display='none';
        backBtn.style.display='flex';
        clearBtn.style.display='flex';
        label.textContent='bamboo. ai';
        setTimeout(()=>document.getElementById('life-input').focus(),200);
    }
}

/* ── CLOCK ── */
function startLifeClock(){
    clearInterval(lifeClockInterval);
    updateLifeClockDisplay();
    lifeClockInterval=setInterval(()=>{updateLifeClockDisplay();updateDayProgress();},1000);
}
function updateLifeClockDisplay(){
    const now=isSelectedPlanToday()?new Date():new Date(selectedPlanDate+'T12:00:00');
    let h=now.getHours(),m=now.getMinutes();
    const ampm=h>=12?'PM':'AM';h=h%12||12;
    const el=document.getElementById('rest-time');
    if(el)el.textContent=isSelectedPlanToday()?`${h}:${m.toString().padStart(2,'0')}`:now.toLocaleDateString(undefined,{weekday:'short'});
    const days=['Sunday','Monday','Tuesday','Wednesday','Thursday','Friday','Saturday'];
    const months=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
    const dateEl=document.getElementById('rest-date');
    const chip=document.getElementById('life-day-chip');
    if(chip)chip.textContent=isSelectedPlanToday()?'today':`${months[now.getMonth()]} ${now.getDate()}`;
    if(dateEl)dateEl.textContent=`${days[now.getDay()]}, ${months[now.getMonth()]} ${now.getDate()} · ${ampm}`;
}

/* ── DAY PROGRESS ── */
function updateDayProgress(){
    const fill=document.getElementById('rest-progress-fill');
    const lbl=document.getElementById('rest-progress-label');
    if(!fill)return;
    if(!isSelectedPlanToday()){
        fill.style.width='0%';
        if(lbl)lbl.textContent='selected day';
        return;
    }
    const now=new Date(),startOfDay=6*60,endOfDay=23*60;
    const nowM=now.getHours()*60+now.getMinutes();
    const pct=Math.min(100,Math.max(0,((nowM-startOfDay)/(endOfDay-startOfDay))*100));
    fill.style.width=pct.toFixed(1)+'%';
    const remaining=endOfDay-nowM;
    if(lbl){
        if(remaining>60)lbl.textContent=`${Math.floor(remaining/60)}h ${remaining%60}m left today`;
        else if(remaining>0)lbl.textContent=`${remaining}m left`;
        else lbl.textContent='end of day';
    }
}

/* ── REST PAGE UPDATE ── */
function eventOccursOnClient(ev, ds){
    if(!ev||!ev.date)return false;
    const base=new Date(ev.date+'T12:00:00');
    const target=new Date(ds+'T12:00:00');
    const rec=ev.recurring||'none';
    if(rec==='none'||!rec)return ev.date===ds;
    if(target<base)return false;
    if(rec==='daily')return true;
    if(rec==='weekdays'){const d=target.getDay();return d>=1&&d<=5;}
    if(rec==='weekly')return target.getDay()===base.getDay();
    if(rec==='monthly')return target.getDate()===base.getDate();
    return false;
}
function getCalendarEventsForPlanDate(){return calendarEvents.filter(e=>eventOccursOnClient(e,selectedPlanDate));}
function getAllDayEventsForPlanDate(){return getCalendarEventsForPlanDate().filter(e=>!e.time);}
function calendarEventsAsPlanItems(){
    return getCalendarEventsForPlanDate().filter(e=>e.time).map(e=>{
        const start=timeToMins(e.time),end=timeToMins(e.end_time);
        return {id:`event-${e.id}`,time:e.time,task:e.title,duration:(end!==null&&start!==null&&end>start)?end-start:60,color:e.color||'#8fc49e',source:'event',event:true};
    });
}
function getVisiblePlanItems(){
    const seen=new Set();
    return [...calendarEventsAsPlanItems(),...dayPlan]
        .filter(p=>p&&p.task&&timeToMins(p.time)!==null)
        .sort((a,b)=>timeToMins(a.time)-timeToMins(b.time))
        .filter(p=>{
            const key=`${taskKey(p.task)}|${p.time}`;
            if(seen.has(key))return false;
            seen.add(key);
            return true;
        });
}
function renderAllDayEvents(){
    const wrap=document.getElementById('all-day-events');
    if(!wrap)return;
    const events=getAllDayEventsForPlanDate();
    if(!events.length){wrap.innerHTML='';return;}
    const html=events.map(e=>{
        const c=e.color||'#8fc49e';
        return `<div class="all-day-item" style="--all-day-color:${c};--all-day-glow:${c}33">${escHtml(e.title)}</div>`;
    }).join('');
    wrap.innerHTML=`<div class="all-day-label">all day</div><div class="all-day-stack">${html}</div>`;
}
function updateRestPage(){
    updateDayProgress();
    renderAllDayEvents();
    const visibleItems=getVisiblePlanItems();
    if(visibleItems.length===0){
        document.getElementById('rest-no-plan').style.display='flex';
        document.getElementById('rest-next-wrap').style.display='none';
        if(!currentTaskOverride){
            document.getElementById('rest-now-task').textContent='what are you up to?';
        }
        return;
    }
    document.getElementById('rest-no-plan').style.display='none';
    renderDayPlan();
    updateCurrentNext();
}

function getCurrentPlanItem(){
    const items=getVisiblePlanItems();
    if(!items.length)return null;
    const nm=isSelectedPlanToday()?nowMins():-1;
    let current=null;
    for(let i=0;i<items.length;i++){
        const p=items[i];
        const start=timeToMins(p.time);
        if(start===null)continue;
        const end=start+(p.duration||30);
        if(nm>=start&&nm<end){current=p;break;}
        if(nm<start){if(!current)current=items[i];break;}// upcoming
        current=p; // past
    }
    return current;
}
function getNextPlanItem(){
    const items=getVisiblePlanItems();
    if(!items.length)return null;
    const nm=isSelectedPlanToday()?nowMins():-1;
    for(let i=0;i<items.length;i++){
        const p=items[i];
        const start=timeToMins(p.time);
        if(start===null)continue;
        if(start>nm)return p;
    }
    return null;
}

function updateCurrentNext(){
    const nowEl=document.getElementById('rest-now-task');
    const nowLabel=document.querySelector('.rest-now-label');
    const nextWrap=document.getElementById('rest-next-wrap');
    const nextEl=document.getElementById('rest-next-task');
    if(nowLabel)nowLabel.textContent=isSelectedPlanToday()?'now':'first up';

    // current task override wins
    if(currentTaskOverride&&isSelectedPlanToday()){
        nowEl.textContent=currentTaskOverride;
    }else{
        const cur=getCurrentPlanItem();
        nowEl.textContent=cur?cur.task:'what are you up to?';
    }

    const next=getNextPlanItem();
    if(next){
        nextWrap.style.display='block';
        nextEl.textContent=`${next.task} · ${minsTo12(timeToMins(next.time))}`;
    }else{
        nextWrap.style.display='none';
    }
}

function renderDayPlan(){
    const planEl=document.getElementById('rest-plan');
    if(!planEl)return;
    const nm=isSelectedPlanToday()?nowMins():-1;
    let html='';
    getVisiblePlanItems().forEach((p,i)=>{
        const start=timeToMins(p.time);
        if(start===null)return;
        const end=start+(p.duration||30);
        const isActive=start!==null&&nm>=start&&nm<end;
        const isDone=start!==null&&nm>=end;
        const dotClass=isActive?'active':isDone?'done':'';
        const taskClass=isActive?'active-task':isDone?'done-task':'';
        const dotColor=p.color?`style="background:${p.color};box-shadow:0 0 8px ${p.color}44"`:'';
        html+=`<div class="plan-item ${p.event?'plan-event':''}" style="animation-delay:${i*0.04}s">
            <div class="plan-time">${minsTo12(start)}</div>
            <div class="plan-dot ${dotClass}" ${dotColor}></div>
            <div class="plan-body">
                <div class="plan-task ${taskClass}">${escHtml(p.task)}</div>
                <div class="plan-dur">${formatMinutes(p.duration||30)}</div>
            </div>
        </div>`;
    });
    // keep no-plan div but hide it
    planEl.innerHTML=`<div class="no-plan" id="rest-no-plan" style="display:none"></div>${html}`;
}

function minsToTime24(m){m=Math.max(0,Math.min(1439,Math.round(m)));return`${String(Math.floor(m/60)).padStart(2,'0')}:${String(m%60).padStart(2,'0')}`;}
function rangesOverlap(aStart,aEnd,bStart,bEnd){return aStart<bEnd&&bStart<aEnd;}
function planHardBlocks(){
    return calendarEventsAsPlanItems()
        .map(e=>({start:timeToMins(e.time),end:timeToMins(e.time)+(parseDurationToMinutes(e.duration)||60),task:e.task}))
        .filter(b=>b.start!==null&&b.end>b.start)
        .sort((a,b)=>a.start-b.start);
}
function nextOpenPlanStart(start,duration,blocks){
    let s=Math.max(5*60,Math.round(start));
    for(let i=0;i<80;i++){
        const e=s+duration;
        if(e>23*60)return null;
        const hit=blocks.find(b=>rangesOverlap(s,e,b.start,b.end));
        if(!hit)return s;
        s=Math.max(s+5,hit.end);
    }
    return null;
}
function normalizePlan(){
    const seen=new Set(),blocks=planHardBlocks(),clean=[];
    const earliest=isSelectedPlanToday()?Math.max(5*60,nowMins()):5*60;
    [...dayPlan]
        .filter(p=>p&&p.task&&timeToMins(p.time)!==null)
        .map((p,i)=>({...p,id:p.id||`plan-${Date.now()}-${i}-${Math.random().toString(36).slice(2,7)}`,source:p.source||'generated'}))
        .sort((a,b)=>timeToMins(a.time)-timeToMins(b.time))
        .forEach(p=>{
            const duration=Math.max(5,Math.min(180,parseDurationToMinutes(p.duration)||30));
            const original=timeToMins(p.time);
            if(original!==null&&isSelectedPlanToday()&&original+duration<=nowMins()&&p.source==='generated')return;
            const desired=Math.max(earliest,original);
            const start=nextOpenPlanStart(desired,duration,blocks);
            if(start===null)return;
            const key=`${taskKey(p.task)}|${start}`;
            if(seen.has(key))return;
            seen.add(key);
            clean.push({...p,time:minsToTime24(start),duration});
            blocks.push({start,end:start+duration,task:p.task});
            blocks.sort((a,b)=>a.start-b.start);
        });
    dayPlan=clean.filter(p=>{
        if(p.source==='user')return true;
        const t=taskKey(p.task),m=timeToMins(p.time);
        if(t==='breakfast'&&m>11*60)return false;
        if(t==='lunch'&&m>15*60)return false;
        if(t==='dinner'&&(m<16*60||m>22*60))return false;
        return true;
    }).slice(0,18);
}
function taskKey(s){return(s||'').toLowerCase().replace(/[^\w\s]/g,'').replace(/\s+/g,' ').trim();}
function planColorForTask(task,type='task'){
    const t=taskKey(`${task||''} ${type||''}`);
    if(/\b(breakfast|lunch|dinner|meal|food|cook|snack)\b/.test(t))return'#d99a6c';
    if(/\b(study|school|test|quiz|exam|homework|assignment|project|essay|read|work|socials|math|science)\b/.test(t))return'#7d9ad6';
    if(/\b(exercise|workout|run|walk|gym|cardio|sport|practice)\b/.test(t))return'#6f8f84';
    if(/\b(relax|wind|sleep|bed|skincare|face care|shower|routine|personal)\b/.test(t))return'#9b83c9';
    if(/\b(break|free time|rest)\b/.test(t))return'#8fc49e';
    return'#6f8f84';
}
function parseDurationToMinutes(raw){
    if(raw===undefined||raw===null||raw==='')return null;
    if(typeof raw==='number')return Math.max(1,Math.round(raw));
    const s=String(raw).toLowerCase();
    const hr=s.match(/(\d+(?:\.\d+)?)\s*(h|hr|hrs|hour|hours)/);
    const min=s.match(/(\d+)\s*(m|min|mins|minute|minutes)/);
    let total=0;
    if(hr)total+=Math.round(parseFloat(hr[1])*60);
    if(min)total+=parseInt(min[1],10);
    if(!total&&/^\d+$/.test(s.trim()))total=parseInt(s.trim(),10);
    return total||null;
}
function findPlanItem(act){
    if(act.position){
        const pos=String(act.position).toLowerCase();
        const sorted=[...dayPlan].sort((a,b)=>timeToMins(a.time)-timeToMins(b.time));
        if(pos==='first')return sorted[0]||null;
        if(pos==='last')return sorted[sorted.length-1]||null;
        if(pos==='current')return getCurrentPlanItem();
        if(pos==='next')return getNextPlanItem();
    }
    const id=act.id||act.plan_id;
    if(id){
        const byId=dayPlan.find(p=>p.id===id);
        if(byId)return byId;
    }
    const target=taskKey(act.target_task||act.task||act.title||'');
    if(target){
        const exact=dayPlan.find(p=>taskKey(p.task)===target);
        if(exact)return exact;
        const partial=dayPlan.find(p=>taskKey(p.task).includes(target)||target.includes(taskKey(p.task)));
        if(partial)return partial;
    }
    if(act.time){
        const byTime=dayPlan.find(p=>p.time===act.time);
        if(byTime)return byTime;
    }
    return null;
}
function addPlanItemNearNow(task, duration=30, color='', remember=false){
    if(!task)return;
    const slot=getNowSlot();
    const existing=dayPlan.find(p=>(p.task||'').toLowerCase()===task.toLowerCase());
    if(existing){
        existing.time=slot;
        existing.duration=duration||existing.duration||30;
        existing.color=color||existing.color||planColorForTask(task);
    }else{
        dayPlan.push({time:slot,task,duration,color:color||planColorForTask(task),source:remember?'user':'generated'});
    }
    if(remember)lastLocalPlanTask=task;
    normalizePlan();
    updateRestPage();
    saveLifeState();
}
function removePlanTask(task){
    if(!task)return false;
    const before=dayPlan.length;
    dayPlan=dayPlan.filter(p=>(p.task||'').toLowerCase()!==task.toLowerCase());
    if(currentTaskOverride&&currentTaskOverride.toLowerCase()===task.toLowerCase())currentTaskOverride=null;
    if(lastLocalPlanTask&&lastLocalPlanTask.toLowerCase()===task.toLowerCase())lastLocalPlanTask=null;
    if(before===dayPlan.length)return false;
    normalizePlan();
    updateRestPage();
    saveLifeState();
    return true;
}
function getExistingGeneratedPlan(){
    return dayPlan
        .filter(p=>p&&p.source==='generated')
        .map(p=>({time:p.time,task:p.task,duration:p.duration,color:p.color||'',source:p.source||'generated'}));
}
function addPlanItem(item, remember=false){
    if(!item||!item.task)return false;
    const duration=parseDurationToMinutes(item.duration)||30;
    dayPlan.push({id:item.id||`plan-${Date.now()}-${Math.random().toString(36).slice(2,7)}`,time:item.time||getNowSlot(),task:item.task,duration,color:item.color||planColorForTask(item.task,item.type),source:item.source||'ai'});
    if(remember&&item.locked)lastLocalPlanTask=item.task;
    normalizePlan();
    updateRestPage();
    saveLifeState();
    return true;
}
function updatePlanItem(act){
    let item=findPlanItem(act);
    if(!item){
        const flexible=dayPlan.filter(p=>p&&p.task&&p.source!=='generated').sort((a,b)=>timeToMins(a.time)-timeToMins(b.time));
        if(flexible.length===1)item=flexible[0];
        else item=getNextPlanItem()||getCurrentPlanItem();
    }
    if(!item)return false;
    const rawShift=act.relative_minutes!==undefined?act.relative_minutes:(act.shift_minutes!==undefined?act.shift_minutes:act.delta_minutes);
    const shift=typeof rawShift==='number'?Math.round(rawShift):parseDurationToMinutes(rawShift);
    if(shift){
        const base=timeToMins(item.time);
        if(base!==null)item.time=minsToTime24(base+shift);
    }
    if(act.time)item.time=act.time;
    if(act.task)item.task=act.task;
    const duration=parseDurationToMinutes(act.duration);
    if(duration)item.duration=duration;
    if(act.color!==undefined)item.color=act.color||planColorForTask(item.task);
    else if(!item.color)item.color=planColorForTask(item.task);
    normalizePlan();
    updateRestPage();
    saveLifeState();
    return true;
}
function deletePlanItem(act){
    const item=findPlanItem(act);
    return item?removePlanTask(item.task):false;
}
function getPinnedPlanItems(){
    const pinned=[];
    const seen=new Set();
    dayPlan.forEach(p=>{
        if(!p||!p.task||p.source==='generated')return;
        const key=taskKey(p.task);
        if(!key||seen.has(key))return;
        pinned.push({...p,source:p.source||'ai'});
        seen.add(key);
    });
    [currentTaskOverride].forEach(task=>{
        if(!task)return;
        const key=taskKey(task);
        if(seen.has(key))return;
        const existing=dayPlan.find(p=>taskKey(p.task)===key);
        pinned.push(existing||{task,time:getNowSlot(),duration:30,color:'#6f8f84',source:'user'});
        seen.add(key);
    });
    return pinned;
}
function getNowSlot(){
    const start=Math.max(5*60,Math.min(22*60+30,Math.floor(nowMins()/5)*5));
    return `${String(Math.floor(start/60)%24).padStart(2,'0')}:${String(start%60).padStart(2,'0')}`;
}
function mergePinnedPlanItems(plan){
    const generated=Array.isArray(plan)?plan.map(p=>({...p,source:'generated'})):[];
    const merged=[];
    getPinnedPlanItems().forEach(pin=>{
        const key=taskKey(pin.task);
        if(!key)return;
        merged.push({...pin,source:pin.source||'ai'});
    });
    generated.forEach(item=>{
        const key=taskKey(item.task);
        if(!key||merged.some(p=>taskKey(p.task)===key))return;
        merged.push(item);
    });
    getPinnedPlanItems().forEach(pin=>{
        const key=taskKey(pin.task);
        if(!key)return;
        const idx=merged.findIndex(p=>taskKey(p.task)===key);
        if(idx>=0){
            merged[idx]={...merged[idx],...pin};
        }else{
            merged.unshift({...pin,time:pin.time||getNowSlot(),duration:pin.duration||30,color:pin.color||'#6f8f84',source:pin.source||'ai'});
        }
    });
    dayPlan=merged;
    normalizePlan();
    updateRestPage();
    saveLifeState();
}
function syncActionToPlan(act){
    if(!act)return;
    if(act.type==='set_current_task')addPlanItemNearNow(act.task,parseDurationToMinutes(act.duration)||30,act.color||'');
    if(act.type==='set_timer')addPlanItemNearNow(act.label||'timer',Math.max(5,Math.round((act.seconds||300)/60)),act.color||'#7d8f96');
    if(act.type==='add_reminder'&&act.due_date===getTodayStr()){
        addPlanItemNearNow(act.text,30,act.color||'');
    }
}
function actionLabel(act){
    if(!act)return 'action';
    const target=act.target_task||act.task||act.title||act.text||act.label||act.view||act.mode||act.type;
    return `${act.type}${target?`: ${target}`:''}`;
}
function pushActionResult(results, act, ok, message){
    results.push({ok, type:act.type, action:summarizeAction(act), message:message||(ok?`done: ${actionLabel(act)}`:`couldn't ${actionLabel(act)}`)});
}
function showActionResults(results, showInChat){
    if(!showInChat)return;
    results.forEach(r=>addLifeAction(r.message));
}
function anyActionFailed(results){return results.some(r=>!r.ok);}
function isVaguePlanTask(task){
    return ['it','this','that','thing','stuff','something'].includes(taskKey(task));
}
function actionsNeedPlanConfirm(actions){
    const list=Array.isArray(actions)?actions:[];
    if(list.some(a=>a&&a.type==='update_day_plan'))return true;
    if(list.some(a=>a&&a.type==='update_plan_items'&&Array.isArray(a.items)&&a.items.length>1))return true;
    if(list.filter(a=>a&&a.type==='update_plan_item').length>1)return true;
    if(list.some(a=>a&&a.type==='delete_plan_items'&&Array.isArray(a.items)&&a.items.length>1))return true;
    return false;
}
function summarizeAction(act){
    const keep=['type','id','title','text','task','target_task','position','date','time','end_time','duration','recurring','due_date','due_label','items'];
    const out={};
    keep.forEach(k=>{if(act&&act[k]!==undefined)out[k]=act[k];});
    return out;
}
function sanitizeColor(c){
    return /^#[0-9a-fA-F]{6}$/.test(c||'')?c:'';
}
function parseRelativeMinutesText(msg){
    const s=String(msg||'').toLowerCase();
    let total=0;
    const hr=s.match(/(\d+|one|two)\s*(h|hr|hrs|hour|hours)/);
    const min=s.match(/(\d+)\s*(m|min|mins|minute|minutes)/);
    if(hr){const v=hr[1]==='one'?1:hr[1]==='two'?2:parseInt(hr[1],10);total+=v*60;}
    if(min)total+=parseInt(min[1],10);
    if(!total&&/\blater\b/.test(s))total=15;
    if(/\bearlier\b|\bback\b/.test(s))total=-total;
    return total||0;
}
function weekdayFromRecurring(recurring){
    const r=String(recurring||'').toLowerCase();
    const map={sunday:'sunday',sundays:'sunday',monday:'monday',mondays:'monday',tuesday:'tuesday',tuesdays:'tuesday',wednesday:'wednesday',wednesdays:'wednesday',thursday:'thursday',thursdays:'thursday',friday:'friday',fridays:'friday',saturday:'saturday',saturdays:'saturday'};
    return map[r]||null;
}
function weekdayNameFromDateStr(ds){
    const d=new Date(ds+'T12:00:00');
    return ['sunday','monday','tuesday','wednesday','thursday','friday','saturday'][d.getDay()];
}
function findWeeklyEventForDay(title, day){
    const key=taskKey(title);
    return calendarEvents.find(e=>taskKey(e.title)===key&&(e.recurring||'none')==='weekly'&&weekdayNameFromDateStr(e.date)===day);
}
function normalizeLifeActions(actions, userMessage=''){
    let list=(actions||[]).map(a=>({...a}));
    const msg=String(userMessage||'').toLowerCase();
    const relativeMinutes=parseRelativeMinutesText(msg);
    const used=new Set();
    const expanded=[];
    for(let i=0;i<list.length;i++){
        if(used.has(i))continue;
        const a=list[i];
        if(a.end!==undefined&&a.end_time===undefined){a.end_time=a.end;delete a.end;}
        if(a.rec!==undefined&&a.recurring===undefined){a.recurring=a.rec;delete a.rec;}
        if(['add_plan_item','update_plan_item'].includes(a.type)){
            if(/\bnow\b|right\s*n?ow/.test(msg))a.time=getNowSlot();
            if(relativeMinutes&&a.type==='update_plan_item'&&a.relative_minutes===undefined&&a.shift_minutes===undefined){
                a.relative_minutes=relativeMinutes;
            }
            if(a.color!==undefined)a.color=sanitizeColor(a.color);
            if(a.type==='add_plan_item'&&!a.color&&a.task)a.color=planColorForTask(a.task,a.type);
        }
        if(a.type==='add_event'&&String(a.recurring||'').toLowerCase()==='weekdays'){
            const titleKey=taskKey(a.title);
            const overrides=[];
            list.forEach((b,j)=>{
                if(i===j||used.has(j)||b.type!=='add_event')return;
                const day=weekdayFromRecurring(b.recurring);
                if(day&&taskKey(b.title)===titleKey)overrides.push({idx:j,day,item:b});
            });
            if(overrides.length){
                const overrideDays=new Set(overrides.map(o=>o.day));
                const items=[];
                overrides.forEach(o=>{
                    used.add(o.idx);
                    items.push({day:o.day,time:o.item.time||a.time,end_time:o.item.end_time||a.end_time,notes:o.item.notes||a.notes||''});
                });
                ['monday','tuesday','wednesday','thursday','friday'].forEach(day=>{
                    if(!overrideDays.has(day))items.push({day,time:a.time,end_time:a.end_time,notes:a.notes||''});
                });
                expanded.push({type:'add_weekly_schedule',title:a.title,items,color:sanitizeColor(a.color)});
                used.add(i);
                continue;
            }
        }
        if(a.type==='add_event'||a.type==='update_event'){
            if(a.type==='update_event'){
                ['title','date','time','end_time'].forEach(k=>{if(a[k]===null||String(a[k]||'').trim()==='')delete a[k];});
            }
            const day=weekdayFromRecurring(a.recurring);
            if(day){
                a.recurring='weekly';
                if(!a.date||a.date==='*')a.date=currentWeekDateForWeekday(day);
            }
            if(a.type==='update_event'&&a.recurring===undefined){
                // partial calendar edits should not invent a repeat rule
            }
            if((!a.date||a.date==='*')&&a.type==='add_event')a.date=getTodayStr();
            if(a.color!==undefined)a.color=sanitizeColor(a.color);
        }
        if(a.type==='update_day_plan'&&!Array.isArray(a.plan)){
            const task=a.task||a.title;
            if(task&&a.time){
                expanded.push({type:'add_plan_item',time:a.time,task,duration:a.duration||30,color:sanitizeColor(a.color)});
                continue;
            }
        }
        expanded.push(a);
    }
    return expanded;
}
async function deleteAllCalendarEvents(){
    const ids=[...calendarEvents].map(e=>e.id);
    let made=0;
    for(const id of ids){
        const resp=await fetch(`/api/calendar/${id}`,{method:'DELETE'});
        if(resp.ok)made++;
    }
    calendarEvents=[];
    if(currentView==='calendar')renderCalendar();
    updateRestPage();
    return {made,total:ids.length};
}
async function deleteAllReminders(){
    const ids=[...remindersData].map(r=>r.id);
    let made=0;
    for(const id of ids){
        const resp=await fetch(`/api/reminders/${id}`,{method:'DELETE'});
        if(resp.ok)made++;
    }
    remindersData=[];
    renderReminders();
    updateStats();
    updateRestPage();
    return {made,total:ids.length};
}
function clearPlanState(){
    dayPlan=[];
    dayPlansByDate={};
    currentTaskOverride=null;
    lastLocalPlanTask=null;
    planGenerationCount=0;
    cancelTimer();
    updateRestPage();
    saveLifeState();
}
function rememberActionResults(results){
    if(!results||!results.length)return;
    results.forEach(r=>lifeActionLog.push({ok:r.ok,type:r.type,message:r.message,action:r.action,ts:Date.now()}));
    lifeActionLog=lifeActionLog.slice(-20);
    const compact=results.map(r=>`${r.ok?'done':'failed'} ${r.type}: ${JSON.stringify(r.action)}`).join(' | ');
    lifeHistory.push({role:'assistant',content:`action results: ${compact}`});
    lifeHistory=lifeHistory.slice(-30);
    saveLifeState();
}

/* ── GENERATE DAY PLAN ── */
async function generateDayPlan(){
    haptic(15);
    if(dayPlan.length){
        showToast('day plan already set');
        updateRestPage();
        return false;
    }
    planGenerationCount++;
    const btn=document.getElementById('gen-plan-txt');
    btn.textContent='generating...';
    try{
        const res=await fetch('/api/generate-day-plan',{
            method:'POST',headers:{'Content-Type':'application/json'},
            body:JSON.stringify({
                reminders:remindersData,
                events:calendarEvents,
                current_task:currentTaskOverride||'',
                pinned_plan:getPinnedPlanItems(),
                existing_plan:getExistingGeneratedPlan(),
                regeneration_count:planGenerationCount,
                target_date:selectedPlanDate
            })
        });
        const plan=await res.json();
        if(plan&&plan.length){
            mergePinnedPlanItems(plan);
            updateRestPage();
            saveLifeState();
            showToast('day plan ready');
            btn.textContent='plan my day';
            return true;
        }else{
            showToast('nothing to plan yet');
        }
    }catch(e){showToast('could not generate plan');}
    btn.textContent='plan my day';
    return false;
}

/* ── TIMER ── */
function startTimer(label, seconds){
    clearInterval(timerInterval);
    timerEndTime=Date.now()+seconds*1000;
    const timerEl=document.getElementById('rest-timer');
    const timerLbl=document.getElementById('rest-timer-label');
    if(timerEl){timerEl.classList.remove('hidden');}
    if(timerLbl)timerLbl.textContent=label;
    timerInterval=setInterval(()=>{
        const remaining=Math.max(0,Math.floor((timerEndTime-Date.now())/1000));
        const m=Math.floor(remaining/60),s=remaining%60;
        const disp=document.getElementById('rest-timer-display');
        if(disp)disp.textContent=`${m.toString().padStart(2,'0')}:${s.toString().padStart(2,'0')}`;
        if(remaining===0){
            clearInterval(timerInterval);
            if('Notification' in window && Notification.permission==='granted')new Notification('bamboo.',{body:`${label} done!`});
            showToast(`${label} done ✓`);
            setTimeout(cancelTimer,3000);
        }
    },1000);
    // initial display
    const disp=document.getElementById('rest-timer-display');
    if(disp)disp.textContent=`${Math.floor(seconds/60).toString().padStart(2,'0')}:${(seconds%60).toString().padStart(2,'0')}`;
}
function cancelTimer(){
    clearInterval(timerInterval);
    const timerEl=document.getElementById('rest-timer');
    if(timerEl)timerEl.classList.add('hidden');
}

/* ── REST INPUT ── */
async function sendRestMsg(){
    const input=document.getElementById('rest-input');
    const msg=input.value.trim();if(!msg)return;
    input.value='';haptic(15);
    if(handlePendingConfirmationText(msg))return;
    await sendToLifeAI(msg, true);
}

/* ── LIFE AI CHAT ── */
async function sendLifeMsg(){
    const input=document.getElementById('life-input');
    const msg=input.value.trim();if(!msg)return;
    input.value='';haptic(15);
    if(handlePendingConfirmationText(msg))return;
    addLifeMsg('user',msg);
    lifeHistory.push({role:'user',content:msg});
    saveLifeState();
    await sendToLifeAI(msg, false);
}

async function sendToLifeAI(msg, fromRest){
    if(lifeAiBusy)return;
    lifeAiBusy=true;
    let typingAdded=false;
    if(!fromRest){addTyping();typingAdded=true;}
    try{
        const res=await fetch('/api/life-chat',{
            method:'POST',headers:{'Content-Type':'application/json'},
            body:JSON.stringify({
                message:msg,
                reminders:remindersData.slice(0,35),
                events:calendarEvents.slice(0,35),
                history:lifeHistory.slice(-16),
                day_plan:dayPlan.slice(0,18),
                ui_state:getUiStateForAI()
            })
        });
        const data=await res.json();
        if(typingAdded)removeTyping();

        if(data.error){
            const now=Date.now();
            const reply=data.reply||'ai is unavailable right now.';
            if(fromRest){
                showToast(reply);
            }else if(now-lastAiErrorAt>15000){
                addLifeMsg('ai',reply);
            }
            lastAiErrorAt=now;
            return;
        }

        if(data.question){
            if(fromRest){
                switchLifeView('chat');
                addLifeMsg('user',msg);
            }
            addLifeMsg('ai',data.question);
            if(fromRest)lifeHistory.push({role:'user',content:msg});
            lifeHistory.push({role:'assistant',content:data.question});
            saveLifeState();
            return;
        }

        if(data.actions&&data.actions.length){
            if(fromRest)addLifeMsg('user',msg);
            if(data.confirm||actionsNeedPlanConfirm(data.actions)){
                switchLifeView('chat');
                addLifeConfirm(confirmTextForActions(data.actions), data.actions);
                if(fromRest)lifeHistory.push({role:'user',content:msg});
                lifeHistory.push({role:'assistant',content:`confirmation requested: ${confirmTextForActions(data.actions)}`});
                saveLifeState();
                return;
            }
            const results=await executeLifeActions(data.actions, !fromRest, msg);
            const failed=anyActionFailed(results);
            const reply=failed?(results.find(r=>!r.ok)?.message||'i tried, but one of those changes did not apply.'):(data.reply||'done.');
            if(fromRest){
                if(failed)switchLifeView('chat');
                else showToast(reply);
            }
            addLifeMsg('ai',reply);
            if(fromRest)lifeHistory.push({role:'user',content:msg});
            lifeHistory.push({role:'assistant',content:reply});
            saveLifeState();
            return;
        }

        if(data.reply){
            if(!fromRest){
                addLifeMsg('ai',data.reply);
                lifeHistory.push({role:'assistant',content:data.reply});
                saveLifeState();
            }else{
                // show reply briefly as toast or switch to chat
                if(data.actions&&data.actions.length){
                    showToast(data.reply);
                    addLifeMsg('user',msg);
                    addLifeMsg('ai',data.reply);
                    lifeHistory.push({role:'user',content:msg});
                    lifeHistory.push({role:'assistant',content:data.reply});
                    saveLifeState();
                }else{
                    // switch to chat for conversational responses
                    switchLifeView('chat');
                    addLifeMsg('user',msg);
                    addLifeMsg('ai',data.reply);
                    lifeHistory.push({role:'user',content:msg});
                    lifeHistory.push({role:'assistant',content:data.reply});
                    saveLifeState();
                }
            }
        }
    }catch(e){
        if(typingAdded)removeTyping();
        if(!fromRest)addLifeMsg('ai','something went wrong');
    }finally{
        lifeAiBusy=false;
    }
}

function appendLifeMsg(role, text, scroll=true, id=null){
    const msgs=document.getElementById('life-msgs');
    const msgId=id||`msg-${Date.now()}-${Math.random().toString(36).slice(2,7)}`;
    const row=document.createElement('div');
    row.className=`msg-row msg-row-${role}`;
    row.dataset.id=msgId;
    const div=document.createElement('div');
    div.className=role==='action'?'msg-action':`msg-bubble msg-${role}`;
    div.textContent=text;
    const tools=document.createElement('div');
    tools.className='msg-tools';
    if(role==='user'||role==='ai'){
        const copy=document.createElement('button');
        copy.className='msg-copy';
        copy.title='copy message';
        copy.innerHTML='<svg viewBox="0 0 24 24"><rect x="9" y="9" width="10" height="10" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>';
        copy.onclick=(e)=>{e.stopPropagation();copyLifeMessage(text);};
        tools.appendChild(copy);
    }
    if(role==='ai'&&/rate limited|unavailable|something went wrong|try again/i.test(text||'')){
        const retry=document.createElement('button');
        retry.className='msg-retry';
        retry.title='retry last prompt';
        retry.innerHTML='<svg viewBox="0 0 24 24"><path d="M21 12a9 9 0 1 1-2.64-6.36"/><path d="M21 3v6h-6"/></svg>';
        retry.onclick=(e)=>{e.stopPropagation();retryLastLifePrompt();};
        tools.appendChild(retry);
    }
    const del=document.createElement('button');
    del.className='msg-del';
    del.title='delete message';
    del.innerHTML='<svg viewBox="0 0 24 24"><path d="M18 6L6 18M6 6l12 12"/></svg>';
    del.onclick=(e)=>{e.stopPropagation();deleteLifeMessage(msgId);};
    tools.appendChild(del);
    row.appendChild(div);
    row.appendChild(tools);
    msgs.appendChild(row);
    if(scroll)msgs.scrollTop=msgs.scrollHeight;
    return msgId;
}
function addLifeMsg(role, text){
    const id=appendLifeMsg(role, text);
    lifeMessages.push({id,role,text,ts:Date.now()});
    lifeMessages=lifeMessages.slice(-80);
    saveLifeState();
}
function addLifeAction(text){
    const id=appendLifeMsg('action', text);
    lifeMessages.push({id,role:'action',text,ts:Date.now()});
    lifeMessages=lifeMessages.slice(-80);
    saveLifeState();
}
async function copyLifeMessage(text){
    try{
        await navigator.clipboard.writeText(text||'');
        showToast('copied');
    }catch(e){
        const ta=document.createElement('textarea');
        ta.value=text||'';
        document.body.appendChild(ta);
        ta.select();
        document.execCommand('copy');
        ta.remove();
        showToast('copied');
    }
}
async function retryLastLifePrompt(){
    const last=[...lifeMessages].reverse().find(m=>m.role==='user'&&m.text);
    if(!last){showToast('nothing to retry');return;}
    addLifeMsg('user',last.text);
    lifeHistory.push({role:'user',content:last.text});
    saveLifeState();
    await sendToLifeAI(last.text,false);
}
function destructiveActionTypes(){return new Set(['clear_everything','clear_calendar','clear_reminders','clear_day_plan','clear_conversation','delete_event','delete_reminder','delete_plan_item','delete_plan_items']);}
function needsConfirmation(actions){return (actions||[]).some(a=>destructiveActionTypes().has(a.type));}
function confirmTextForActions(actions){
    const types=(actions||[]).map(a=>a.type);
    if(types.includes('update_day_plan')||types.includes('update_plan_items'))return 'update your day plan timing?';
    if(types.includes('clear_everything'))return 'clear everything and start fresh?';
    if(types.includes('clear_calendar'))return 'clear the calendar?';
    if(types.includes('clear_reminders'))return 'clear all reminders?';
    if(types.includes('clear_day_plan'))return 'clear the day plan?';
    if(types.includes('clear_conversation'))return 'clear this conversation?';
    if(types.some(t=>t.startsWith('delete_')))return 'delete that?';
    return 'do this?';
}
function addLifeConfirm(text, actions){
    pendingConfirmActions=actions;
    pendingConfirmText=text;
    const msgs=document.getElementById('life-msgs');
    const card=document.createElement('div');
    card.className='confirm-card';
    card.id='pending-confirm-card';
    card.innerHTML=`<div>${escHtml(text)}</div><div class="confirm-actions"><button class="confirm-btn confirm-yes" onclick="confirmPendingActions(true)">yes</button><button class="confirm-btn confirm-no" onclick="confirmPendingActions(false)">no</button></div>`;
    msgs.appendChild(card);
    msgs.scrollTop=msgs.scrollHeight;
}
function handlePendingConfirmationText(msg){
    if(!pendingConfirmActions)return false;
    const s=msg.trim().toLowerCase();
    if(['yes','y','yeah','yep','sure','do it','confirm','ok','okay'].includes(s)){addLifeMsg('user',msg);confirmPendingActions(true);return true;}
    if(['no','n','nah','cancel','stop','dont',"don't"].includes(s)){addLifeMsg('user',msg);confirmPendingActions(false);return true;}
    return false;
}
async function confirmPendingActions(yes){
    const card=document.getElementById('pending-confirm-card');
    if(card)card.remove();
    const actions=pendingConfirmActions;
    pendingConfirmActions=null;
    pendingConfirmText='';
    if(!yes){
        addLifeMsg('ai','cancelled.');
        lifeHistory.push({role:'assistant',content:'cancelled.'});
        saveLifeState();
        return;
    }
    addLifeAction('confirmed');
    const results=await executeLifeActions(actions, true);
    const failed=anyActionFailed(results);
    const reply=failed?'i tried, but one of those changes did not apply.':'done.';
    addLifeMsg('ai',reply);
    lifeHistory.push({role:'assistant',content:reply});
    saveLifeState();
}
function deleteLifeMessage(id){
    const row=document.querySelector(`.msg-row[data-id="${id}"]`);
    if(row)row.remove();
    lifeMessages=lifeMessages.filter(m=>m.id!==id);
    saveLifeState();
}
function clearLifeConversation(){
    haptic(15);
    lifeHistory=[];
    lifeMessages=[];
    lifeActionLog=[];
    const msgs=document.getElementById('life-msgs');
    if(msgs)msgs.innerHTML='';
    saveLifeState();
    showToast('conversation cleared');
}
function addTyping(){
    const msgs=document.getElementById('life-msgs');
    const wrap=document.createElement('div');
    wrap.id='life-typing';
    wrap.className='thinking-text';
    wrap.textContent='thinking...';
    msgs.appendChild(wrap);msgs.scrollTop=msgs.scrollHeight;
}
function removeTyping(){const t=document.getElementById('life-typing');if(t)t.remove();}

function getUiStateForAI(){
    return {
        current_view: currentView,
        life_view: lifeViewMode,
        sort_mode: currentSortMode,
        current_task: currentTaskOverride,
        last_local_plan_task: lastLocalPlanTask,
        selected_plan_date: selectedPlanDate,
        selected_plan_events: getCalendarEventsForPlanDate().map(e=>({id:e.id,title:e.title,date:e.date,time:e.time,end_time:e.end_time,recurring:e.recurring,notes:e.notes||''})).slice(0,12),
        selected_calendar_day: calSelected?`${calSelected.getFullYear()}-${String(calSelected.getMonth()+1).padStart(2,'0')}-${String(calSelected.getDate()).padStart(2,'0')}`:'',
        timer_running: !!timerEndTime&&Date.now()<timerEndTime,
        timer_seconds_left: timerEndTime?Math.max(0,Math.floor((timerEndTime-Date.now())/1000)):0,
        recent_actions: lifeActionLog.slice(-8)
    };
}

async function executeLifeActions(actions, showInChat, userMessage=''){
    actions=normalizeLifeActions(actions, userMessage);
    const results=[];
    for(const act of actions){
        try{
            let ok=false;
            if(act.type==='add_reminder'){
                const due_ts=act.due_date?new Date(act.due_date+'T09:00:00').getTime():0;
                const preset=act.schedule_preset||'none';
                const resp=await fetch('/api/reminders',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:act.text,updated_at:getTimestamp(),created_timestamp:Date.now(),due_timestamp:due_ts,due_label:act.due_label||'',color:act.color||'',notes:act.notes||'',schedule_preset:preset,schedule_start:preset==='none'?0:Date.now(),notifications_sent:0})});
                ok=resp.ok; pushActionResult(results,act,ok,ok?`done: reminder "${act.text}"`:'could not add reminder');
            }else if(act.type==='complete_reminder'){
                const resp=await fetch(`/api/reminders/${act.id}`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({completed:true,updated_at:getTimestamp(),completed_date:getTodayStr()})});
                ok=resp.ok; pushActionResult(results,act,ok,ok?'done: marked complete':'could not find that reminder');
            }else if(act.type==='delete_reminder'){
                const resp=await fetch(`/api/reminders/${act.id}`,{method:'DELETE'});
                ok=resp.ok; pushActionResult(results,act,ok,ok?'done: deleted reminder':'could not find that reminder');
            }else if(act.type==='update_reminder'){
                const upd={updated_at:getTimestamp()};
                if(act.text!==undefined)upd.text=act.text;
                if(act.due_date!==undefined){upd.due_timestamp=act.due_date?new Date(act.due_date+'T09:00:00').getTime():0;}
                if(act.due_label!==undefined)upd.due_label=act.due_label||'';
                if(act.color!==undefined)upd.color=act.color||'';
                if(act.notes!==undefined)upd.notes=act.notes||'';
                if(act.completed!==undefined){upd.completed=!!act.completed;upd.completed_date=act.completed?getTodayStr():'';}
                if(act.schedule_preset!==undefined){upd.schedule_preset=act.schedule_preset||'none';upd.schedule_start=upd.schedule_preset==='none'?0:Date.now();upd.notifications_sent=0;}
                const resp=await fetch(`/api/reminders/${act.id}`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(upd)});
                ok=resp.ok; pushActionResult(results,act,ok,ok?'done: reminder updated':'could not find that reminder');
            }else if(act.type==='add_event'){
                const evData={title:act.title,date:act.date,time:act.time||'',end_time:act.end_time||'',recurring:act.recurring||'none',color:act.color||'',notes:act.notes||'',created_timestamp:Date.now()};
                const resp=await fetch('/api/calendar',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(evData)});
                ok=resp.ok; pushActionResult(results,act,ok,ok?`done: calendar "${act.title}"`:'could not add calendar event');
            }else if(act.type==='add_weekly_schedule'){
                const items=Array.isArray(act.items)?act.items:[];
                let made=0;
                for(const item of items){
                    const existing=findWeeklyEventForDay(act.title,item.day);
                    const evData={title:act.title,date:currentWeekDateForWeekday(item.day),time:item.time||'',end_time:item.end_time||'',recurring:'weekly',color:act.color||'',notes:item.notes||act.notes||'',created_timestamp:Date.now()};
                    const resp=existing
                        ? await fetch(`/api/calendar/${existing.id}`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({title:act.title,date:evData.date,time:evData.time,end_time:evData.end_time,recurring:'weekly',color:evData.color,notes:evData.notes})})
                        : await fetch('/api/calendar',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(evData)});
                    if(resp.ok)made++;
                }
                ok=items.length>0&&made===items.length;
                pushActionResult(results,act,ok,ok?`done: weekly ${act.title} schedule (${made} days)`:`only added ${made}/${items.length} schedule days`);
            }else if(act.type==='delete_event'){
                const resp=await fetch(`/api/calendar/${act.id}`,{method:'DELETE'});
                ok=resp.ok; pushActionResult(results,act,ok,ok?'done: removed calendar event':'could not find that event');
            }else if(act.type==='update_event'){
                const upd={};
                if(act.title!==undefined)upd.title=act.title;
                if(act.date!==undefined)upd.date=act.date;
                if(act.time!==undefined)upd.time=act.time||'';
                if(act.end_time!==undefined)upd.end_time=act.end_time||'';
                if(act.recurring!==undefined)upd.recurring=act.recurring||'none';
                if(act.color!==undefined)upd.color=act.color||'';
                if(act.notes!==undefined)upd.notes=act.notes||'';
                const resp=await fetch(`/api/calendar/${act.id}`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(upd)});
                ok=resp.ok; pushActionResult(results,act,ok,ok?'done: calendar updated':'could not find that event');
            }else if(act.type==='add_plan_item'){
                if(isVaguePlanTask(act.task)){
                    ok=false; pushActionResult(results,act,ok,'what should i add to your day plan?');
                }else{
                    ok=addPlanItem(act,true); pushActionResult(results,act,ok,ok?`done: plan "${act.task}"`:'could not add plan item');
                }
            }else if(act.type==='add_plan_items'){
                const items=Array.isArray(act.items)?act.items:[];
                let made=0;
                items.forEach(item=>{if(!isVaguePlanTask(item.task)&&addPlanItem(item,true))made++;});
                ok=items.length>0&&made===items.length;
                pushActionResult(results,act,ok,ok?`done: added ${made} plan items`:`only added ${made}/${items.length} plan items`);
            }else if(act.type==='update_plan_item'){
                ok=updatePlanItem(act); pushActionResult(results,act,ok,ok?'done: plan updated':'could not find that plan item');
            }else if(act.type==='update_plan_items'){
                const items=Array.isArray(act.items)?act.items:[];
                let made=0;
                items.forEach(item=>{if(updatePlanItem(item))made++;});
                ok=items.length>0&&made===items.length;
                pushActionResult(results,act,ok,ok?`done: updated ${made} plan items`:`only updated ${made}/${items.length} plan items`);
            }else if(act.type==='delete_plan_item'){
                ok=deletePlanItem(act); pushActionResult(results,act,ok,ok?'done: removed from plan':'could not find that plan item');
            }else if(act.type==='delete_plan_items'){
                const items=Array.isArray(act.items)?act.items:[];
                let made=0;
                items.forEach(item=>{if(deletePlanItem(item))made++;});
                ok=items.length>0&&made===items.length;
                pushActionResult(results,act,ok,ok?`done: removed ${made} plan items`:`only removed ${made}/${items.length} plan items`);
            }else if(act.type==='update_day_plan'){
                ok=!!(act.plan&&act.plan.length);
                if(ok){dayPlan=act.plan;normalizePlan();updateRestPage();saveLifeState();}
                pushActionResult(results,act,ok,ok?'done: day plan updated':'could not update day plan');
            }else if(act.type==='clear_day_plan'){
                clearPlanState();ok=true;
                pushActionResult(results,act,ok,'done: cleared day plan');
            }else if(act.type==='clear_calendar'){
                const r=await deleteAllCalendarEvents();ok=r.made===r.total;
                pushActionResult(results,act,ok,ok?'done: calendar cleared':`only removed ${r.made}/${r.total} calendar events`);
            }else if(act.type==='clear_reminders'){
                const r=await deleteAllReminders();ok=r.made===r.total;
                pushActionResult(results,act,ok,ok?'done: reminders cleared':`only removed ${r.made}/${r.total} reminders`);
            }else if(act.type==='clear_conversation'){
                clearLifeConversation();ok=true;
                pushActionResult(results,act,ok,'done: conversation cleared');
            }else if(act.type==='clear_everything'){
                const cal=await deleteAllCalendarEvents();
                const rem=await deleteAllReminders();
                clearPlanState();
                ok=cal.made===cal.total&&rem.made===rem.total;
                pushActionResult(results,act,ok,ok?'done: everything cleared':`cleared plan, removed ${cal.made}/${cal.total} calendar and ${rem.made}/${rem.total} reminders`);
            }else if(act.type==='generate_day_plan'){
                ok=await generateDayPlan();
                pushActionResult(results,act,ok,ok?'done: day plan ready':'day plan already set or nothing to plan');
            }else if(act.type==='set_timer'){
                const secs=act.seconds||300;startTimer(act.label||'timer',secs);ok=true;
                pushActionResult(results,act,ok,`done: timer ${act.label||'timer'} ${Math.floor(secs/60)}m`);
            }else if(act.type==='cancel_timer'){
                cancelTimer();ok=true;pushActionResult(results,act,ok,'done: timer cancelled');
            }else if(act.type==='set_current_task'){
                currentTaskOverride=act.task;addPlanItemNearNow(act.task,parseDurationToMinutes(act.duration)||30,act.color||'#6f8f84',true);updateCurrentNext();saveLifeState();ok=true;
                pushActionResult(results,act,ok,`done: now ${act.task}`);
            }else if(act.type==='clear_current_task'){
                currentTaskOverride=null;saveLifeState();updateRestPage();ok=true;
                pushActionResult(results,act,ok,'done: current task cleared');
            }else if(act.type==='set_view'){
                if(act.view==='life_chat'){switchLifeView('chat');ok=true;}
                else if(act.view==='life_rest'){switchLifeView('rest');ok=true;}
                else if(['reminders','dashboard','calendar'].includes(act.view)){closeMyLife();switchView(act.view);ok=true;}
                pushActionResult(results,act,ok,ok?`done: opened ${act.view}`:'could not open that view');
            }else if(act.type==='set_sort'){
                ok=['default','due'].includes(act.mode);
                if(ok){currentSortMode=act.mode;renderReminders();}
                pushActionResult(results,act,ok,ok?`done: sorted by ${act.mode}`:'could not sort that way');
            }else if(act.type==='select_calendar_day'){
                ok=!!act.date;
                if(ok){calSelected=new Date(act.date+'T12:00:00');calDate=new Date(act.date+'T12:00:00');setLifeDay(act.date);if(currentView==='calendar')renderCalendar();}
                pushActionResult(results,act,ok,ok?`done: selected ${act.date}`:'could not select that day');
            }else{
                pushActionResult(results,act,false,`unknown action: ${act.type}`);
            }
            if(ok)syncActionToPlan(act);
        }catch(e){
            pushActionResult(results,act,false,`failed: ${actionLabel(act)}`);
        }
    }
    await fetchAll();
    if(lifeViewMode==='rest')updateRestPage();
    showActionResults(results, showInChat);
    rememberActionResults(results);
    return results;
}
/* ── NOTIFICATIONS ── */
setInterval(async()=>{
    if(!('Notification' in window) || Notification.permission!=='granted')return;
    const now=Date.now();
    for(let r of remindersData){
        if(r.completed||!r.schedule_preset||r.schedule_preset==='none')continue;
        let total=0,ms=86400000;
        if(r.schedule_preset==='day'){total=3;ms=86400000;}
        if(r.schedule_preset==='week'){total=14;ms=86400000;}
        if(r.schedule_preset==='month'){total=15;ms=172800000;}
        if(r.notifications_sent<total){
            const next=r.schedule_start+(r.notifications_sent*ms);
            if(now>=next){
                new Notification("bamboo.",{body:r.text});
                r.notifications_sent++;
                await fetch(`/api/reminders/${r.id}`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({notifications_sent:r.notifications_sent})});
            }
        }
    }
},60000);

/* ── TOAST ── */
function showToast(msg){
    const t=document.createElement('div');t.className='toast';
    t.innerHTML=`<svg viewBox="0 0 24 24"><path d="M20 6L9 17l-5-5"/></svg><span>${escHtml(msg)}</span>`;
    document.body.appendChild(t);setTimeout(()=>t.classList.add('show'),10);
    setTimeout(()=>{t.classList.remove('show');setTimeout(()=>t.remove(),300);},2500);
}

/* ── INIT ── */
loadLifeState();
renderStoredLifeMessages();
updateRestPage();
fetchAll();
setTimeout(()=>openMyLife(true),120);
</script>
</body>
</html>
"""

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=4000, debug=True, use_reloader=False)
