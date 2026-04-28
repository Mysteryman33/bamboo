import os
from flask import Flask, request, jsonify, render_template_string
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)

# Using local_v6 to include color column
db_url = os.environ.get('DATABASE_URL', 'sqlite:///local_v6.db')
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

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

with app.app_context():
    db.create_all()
    # Safe migration: add new columns if they don't exist (won't break existing DB)
    try:
        with db.engine.connect() as conn:
            from sqlalchemy import text
            try:
                conn.execute(text("ALTER TABLE reminder ADD COLUMN created_timestamp FLOAT DEFAULT 0.0"))
                conn.commit()
            except Exception:
                pass
            try:
                conn.execute(text("ALTER TABLE reminder ADD COLUMN completed_date VARCHAR(20) DEFAULT ''"))
                conn.commit()
            except Exception:
                pass
    except Exception:
        pass

def r_to_dict(r):
    return {
        "id": r.id, 
        "text": r.text, 
        "completed": r.completed,
        "scheduled_date": r.scheduled_date, 
        "schedule_preset": r.schedule_preset,
        "schedule_start": r.schedule_start,
        "notifications_sent": r.notifications_sent,
        "notes": r.notes, 
        "updated_at": r.updated_at,
        "color": r.color,
        "created_timestamp": r.created_timestamp or 0.0,
        "completed_date": r.completed_date or ""
    }

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
            completed_date=data.get('completed_date', '')
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
        if 'text' in data: r.text = data['text']
        if 'completed' in data: r.completed = data['completed']
        if 'scheduled_date' in data: r.scheduled_date = data['scheduled_date']
        if 'schedule_preset' in data: r.schedule_preset = data['schedule_preset']
        if 'schedule_start' in data: r.schedule_start = data['schedule_start']
        if 'notifications_sent' in data: r.notifications_sent = data['notifications_sent']
        if 'notes' in data: r.notes = data['notes']
        if 'updated_at' in data: r.updated_at = data['updated_at']
        if 'color' in data: r.color = data['color']
        if 'created_timestamp' in data: r.created_timestamp = data['created_timestamp']
        if 'completed_date' in data: r.completed_date = data['completed_date']
        db.session.commit()
        return jsonify(r_to_dict(r))
    elif request.method == 'DELETE':
        db.session.delete(r)
        db.session.commit()
        return '', 204

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>bamboo.</title>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600&display=swap" rel="stylesheet">
    <style>
        :root {
            --accent: #C1B19A;
            --accent-warm: #D4C4AD;
            --dark: #2C251B;
            --bg: #FDFBF7;
            --surface: #F5F1EA;
            --muted: rgba(44, 37, 27, 0.38);
            --muted-med: rgba(44, 37, 27, 0.55);
            --border: rgba(44, 37, 27, 0.09);
            --border-med: rgba(44, 37, 27, 0.14);
            --green: #5A8A6A;
            --green-light: rgba(90, 138, 106, 0.12);
        }
        
        *, *::before, *::after { box-sizing: border-box; }

        body, html {
            margin: 0; padding: 0; font-family: 'Outfit', sans-serif;
            background-color: var(--bg); color: var(--dark);
            -webkit-font-smoothing: antialiased;
            min-height: 100vh; overflow-x: hidden;
        }

        @keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
        @keyframes slideUpFade {
            from { opacity: 0; transform: translateY(12px); }
            to { opacity: 1; transform: translateY(0); }
        }
        @keyframes slideInLeft {
            from { opacity: 0; transform: translateX(-24px); }
            to { opacity: 1; transform: translateX(0); }
        }

        /* ── HEADER ── */
        .header-container {
            display: flex; align-items: center; justify-content: center;
            position: relative; padding: 52px 20px 16px 20px;
            max-width: 600px; margin: 0 auto;
            animation: fadeIn 0.6s ease-out;
        }
        .header {
            font-size: 30px; font-weight: 500; letter-spacing: 3px;
            color: var(--accent); text-transform: lowercase;
            user-select: none; cursor: pointer;
            transition: opacity 0.2s;
        }
        .header:active { opacity: 0.6; }

        .menu-btn {
            position: absolute; left: 20px; bottom: 20px;
            width: 38px; height: 38px; border-radius: 10px;
            display: flex; flex-direction: column; align-items: center;
            justify-content: center; gap: 5px;
            cursor: pointer; transition: background 0.2s;
        }
        .menu-btn:hover { background: rgba(0,0,0,0.04); }
        .menu-btn span {
            display: block; width: 18px; height: 1.5px;
            background: var(--muted); border-radius: 2px;
            transition: background 0.2s;
        }
        .menu-btn:hover span { background: var(--dark); }

        .sort-btn {
            position: absolute; right: 20px; bottom: 20px;
            width: 38px; height: 38px; border-radius: 10px;
            display: flex; align-items: center; justify-content: center;
            cursor: pointer; transition: background 0.2s; color: var(--muted);
        }
        .sort-btn:hover { background: rgba(0,0,0,0.04); color: var(--dark); }
        .sort-btn svg { width: 17px; height: 17px; stroke: currentColor; stroke-width: 2; fill: none; stroke-linecap: round; }

        /* ── SIDE DRAWER ── */
        .drawer-overlay {
            position: fixed; inset: 0; background: rgba(44,37,27,0.3);
            backdrop-filter: blur(4px); z-index: 400;
            opacity: 0; pointer-events: none; transition: opacity 0.3s;
        }
        .drawer-overlay.show { opacity: 1; pointer-events: all; }

        .drawer {
            position: fixed; top: 0; left: 0; bottom: 0; width: 300px;
            background: var(--bg); z-index: 500;
            transform: translateX(-100%); transition: transform 0.38s cubic-bezier(0.165, 0.84, 0.44, 1);
            display: flex; flex-direction: column;
            border-right: 1px solid var(--border);
            box-shadow: 4px 0 40px rgba(44,37,27,0.08);
        }
        .drawer.show { transform: translateX(0); }

        .drawer-header {
            padding: 60px 28px 24px 28px;
            border-bottom: 1px solid var(--border);
        }
        .drawer-logo { font-size: 22px; font-weight: 500; letter-spacing: 3px; color: var(--accent); }
        .drawer-sub { font-size: 13px; color: var(--muted); margin-top: 4px; font-weight: 300; }

        .drawer-nav { padding: 16px 12px; flex: 1; }
        .drawer-nav-item {
            display: flex; align-items: center; gap: 14px;
            padding: 13px 16px; border-radius: 12px; cursor: pointer;
            font-size: 15px; font-weight: 400; color: var(--muted-med);
            transition: all 0.2s; margin-bottom: 2px;
        }
        .drawer-nav-item:hover, .drawer-nav-item.active {
            background: var(--surface); color: var(--dark);
        }
        .drawer-nav-item svg { width: 18px; height: 18px; stroke: currentColor; stroke-width: 1.8; fill: none; flex-shrink: 0; stroke-linecap: round; stroke-linejoin: round; }

        .drawer-footer { padding: 20px 28px; border-top: 1px solid var(--border); }
        .drawer-stat { font-size: 13px; color: var(--muted); font-weight: 300; line-height: 1.8; }

        /* ── MAIN VIEW WRAPPER ── */
        .view { display: none; }
        .view.active { display: block; }

        /* ── REMINDERS LIST ── */
        .list-container {
            max-width: 600px; margin: 0 auto; padding: 4px 20px 160px 20px;
        }

        .section-label {
            font-size: 11px; font-weight: 500; letter-spacing: 1.5px;
            text-transform: uppercase; color: var(--muted); padding: 20px 0 10px 0;
        }

        .reminder-item {
            padding: 18px 0 18px 16px; border-bottom: 1px solid var(--border);
            cursor: pointer; transition: all 0.3s cubic-bezier(0.165, 0.84, 0.44, 1);
            user-select: none; -webkit-user-select: none;
            animation: slideUpFade 0.35s ease-out forwards;
            opacity: 0; border-left: 3px solid transparent;
            border-radius: 0;
        }
        .reminder-item:hover { transform: translateX(4px); background: rgba(0,0,0,0.015); border-radius: 0 8px 8px 0; }
        .reminder-item.completed { opacity: 0.3; border-left-color: transparent !important; }
        .reminder-item.completed:hover { transform: none; background: transparent; }
        .reminder-content-wrapper { pointer-events: none; }

        .reminder-text {
            font-size: 18px; font-weight: 400; line-height: 1.5;
            transition: color 0.3s; word-wrap: break-word; white-space: pre-wrap;
        }
        .reminder-item.completed .reminder-text { text-decoration: line-through; color: var(--muted); }

        .reminder-meta {
            display: flex; flex-wrap: wrap; gap: 10px; margin-top: 7px;
            font-size: 12px; color: var(--muted); font-weight: 300;
        }
        .reminder-meta span { display: flex; align-items: center; gap: 4px; }
        .meta-icon { width: 12px; height: 12px; stroke: currentColor; stroke-width: 2; fill: none; flex-shrink: 0; }

        .days-badge {
            display: inline-flex; align-items: center; gap: 4px;
            background: var(--green-light); color: var(--green);
            padding: 2px 8px; border-radius: 20px; font-size: 11px; font-weight: 500;
        }

        /* ── CHAT BUBBLE ── */
        .chat-bubble-container {
            position: fixed; bottom: -160px; left: 50%; transform: translateX(-50%);
            width: calc(100% - 40px); max-width: 520px;
            transition: bottom 0.45s cubic-bezier(0.175, 0.885, 0.32, 1.275); z-index: 100;
        }
        .chat-bubble-container.show { bottom: 36px; }

        .chat-bubble {
            background: var(--dark); border-radius: 28px;
            padding: 14px 14px 14px 22px; display: flex; align-items: flex-end; gap: 14px;
            box-shadow: 0 20px 50px rgba(44, 37, 27, 0.3);
        }
        .chat-bubble textarea {
            flex: 1; border: none; outline: none; background: transparent;
            font-size: 17px; font-family: inherit; color: var(--bg);
            font-weight: 300; resize: none; overflow-y: auto; line-height: 1.45;
            max-height: 120px; padding: 0; margin: 0; margin-bottom: 5px;
        }
        .chat-bubble textarea::placeholder { color: rgba(253, 251, 247, 0.4); }

        .send-btn {
            background: var(--accent); color: var(--dark); border: none; border-radius: 50%;
            width: 42px; height: 42px; flex-shrink: 0; display: flex;
            align-items: center; justify-content: center;
            cursor: pointer; transition: transform 0.2s, filter 0.2s; margin-bottom: 1px;
        }
        .send-btn:active { transform: scale(0.88); }
        .send-btn svg { width: 19px; height: 19px; stroke: currentColor; stroke-width: 2; fill: none; margin-left: 2px; stroke-linecap: round; stroke-linejoin: round; }

        /* ── CONTEXT MENU ── */
        .context-menu {
            position: fixed; background: var(--bg); border-radius: 16px;
            box-shadow: 0 12px 48px rgba(0,0,0,0.14); padding: 8px; min-width: 180px; z-index: 200;
            display: none; opacity: 0; transform: scale(0.94); transform-origin: top left;
            transition: opacity 0.18s, transform 0.18s; border: 1px solid var(--border-med);
        }
        .context-menu.show { display: flex; flex-direction: column; opacity: 1; transform: scale(1); }
        .cm-item {
            padding: 11px 16px; font-size: 14px; cursor: pointer; border-radius: 9px;
            transition: background 0.15s; display: flex; align-items: center; gap: 10px; color: var(--dark);
        }
        .cm-item:hover { background: var(--surface); }
        .cm-item.danger { color: #ef4444; }
        .cm-item svg { width: 15px; height: 15px; stroke: currentColor; stroke-width: 2; fill: none; stroke-linecap: round; stroke-linejoin: round; }
        .cm-divider { height: 1px; background: var(--border); margin: 4px 0; }

        #sort-menu { width: 165px; }

        /* ── MODALS ── */
        .modal {
            display: none; position: fixed; inset: 0;
            background: rgba(44, 37, 27, 0.35); backdrop-filter: blur(8px); z-index: 300;
            align-items: flex-end; justify-content: center; opacity: 0; transition: opacity 0.25s;
        }
        .modal.show { display: flex; opacity: 1; }
        .modal-content {
            background: var(--bg); padding: 28px 24px 36px; border-radius: 28px 28px 0 0;
            width: 100%; max-width: 560px;
            display: flex; flex-direction: column; gap: 18px;
            transform: translateY(40px); transition: transform 0.38s cubic-bezier(0.175, 0.885, 0.32, 1.275);
            box-shadow: 0 -8px 40px rgba(0,0,0,0.1);
        }
        .modal.show .modal-content { transform: translateY(0); }

        .modal-handle { width: 40px; height: 4px; background: var(--border-med); border-radius: 2px; margin: 0 auto -4px; }
        .modal-title { font-size: 18px; font-weight: 500; color: var(--dark); margin: 0; }

        .modal-input {
            width: 100%; padding: 14px 16px; border: 1px solid var(--border-med);
            border-radius: 14px; font-family: inherit; font-size: 16px; outline: none;
            background: var(--surface); color: var(--dark); transition: border-color 0.2s;
        }
        textarea.modal-input { resize: vertical; min-height: 90px; line-height: 1.5; }
        .modal-input:focus { border-color: var(--accent); background: var(--bg); }

        /* Color Picker */
        .color-grid { display: grid; grid-template-columns: repeat(6, 1fr); gap: 10px; justify-items: center; }
        .color-swatch {
            width: 38px; height: 38px; border-radius: 50%; cursor: pointer;
            border: 2.5px solid transparent; transition: transform 0.2s, border-color 0.2s;
            box-shadow: 0 2px 8px rgba(0,0,0,0.08);
        }
        .color-swatch:hover { transform: scale(1.12); }
        .color-swatch.active { border-color: var(--dark); transform: scale(1.12); }
        .color-clear { background: transparent; border: 2px dashed #d1d5db; box-shadow: none; display: flex; align-items: center; justify-content: center; }
        .color-clear svg { width: 18px; height: 18px; stroke: #9ca3af; stroke-width: 2; fill: none; }

        .preset-grid { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 8px; }
        .preset-card {
            border: 1.5px solid var(--border-med); border-radius: 14px; padding: 16px 8px;
            text-align: center; cursor: pointer; transition: all 0.2s; background: var(--surface);
        }
        .preset-card.active { border-color: var(--accent); background: rgba(193, 177, 154, 0.12); }
        .preset-card:hover { transform: translateY(-2px); }
        .preset-name { font-weight: 500; font-size: 15px; margin-bottom: 3px; }
        .preset-desc { font-size: 11px; color: var(--muted); }

        .modal-actions { display: flex; gap: 10px; justify-content: flex-end; }
        .btn {
            padding: 12px 22px; border-radius: 12px; font-family: inherit; font-size: 15px; font-weight: 500;
            cursor: pointer; border: none; transition: all 0.2s;
        }
        .btn-cancel { background: var(--surface); color: var(--muted-med); }
        .btn-cancel:hover { color: var(--dark); }
        .btn-save { background: var(--accent); color: var(--dark); }
        .btn-save:hover { filter: brightness(0.93); transform: translateY(-1px); }

        /* ── DASHBOARD ── */
        .dashboard-container {
            max-width: 600px; margin: 0 auto; padding: 8px 20px 160px 20px;
        }

        .dash-card {
            background: var(--surface); border-radius: 20px; padding: 24px;
            margin-bottom: 14px; border: 1px solid var(--border);
            animation: slideUpFade 0.4s ease-out forwards; opacity: 0;
        }
        .dash-card:nth-child(2) { animation-delay: 0.06s; }
        .dash-card:nth-child(3) { animation-delay: 0.12s; }
        .dash-card:nth-child(4) { animation-delay: 0.18s; }

        .dash-card-label {
            font-size: 11px; font-weight: 500; letter-spacing: 1.5px;
            text-transform: uppercase; color: var(--muted); margin-bottom: 16px;
        }

        /* Streak */
        .streak-display { display: flex; align-items: baseline; gap: 8px; margin-bottom: 6px; }
        .streak-num { font-size: 56px; font-weight: 300; line-height: 1; color: var(--dark); }
        .streak-unit { font-size: 18px; color: var(--muted); font-weight: 300; }
        .streak-sub { font-size: 13px; color: var(--muted); font-weight: 300; }

        .streak-dots { display: flex; gap: 6px; margin-top: 16px; flex-wrap: wrap; }
        .streak-dot {
            width: 28px; height: 28px; border-radius: 8px; display: flex;
            align-items: center; justify-content: center; font-size: 11px; font-weight: 500;
            transition: all 0.2s;
        }
        .streak-dot.done { background: var(--dark); color: var(--bg); }
        .streak-dot.today { background: var(--accent); color: var(--dark); }
        .streak-dot.miss { background: var(--border-med); color: var(--muted); }
        .streak-dot.future { background: transparent; border: 1.5px dashed var(--border-med); color: var(--muted); }

        /* Stats row */
        .stats-row { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 10px; }
        .stat-cell { text-align: center; }
        .stat-val { font-size: 28px; font-weight: 300; color: var(--dark); line-height: 1; }
        .stat-lbl { font-size: 11px; color: var(--muted); margin-top: 4px; font-weight: 300; }

        /* Active schedules */
        .schedule-item {
            display: flex; align-items: center; justify-content: space-between;
            padding: 12px 0; border-bottom: 1px solid var(--border);
        }
        .schedule-item:last-child { border-bottom: none; padding-bottom: 0; }
        .schedule-item-text { font-size: 14px; font-weight: 400; flex: 1; margin-right: 12px; }
        .schedule-item-badge {
            background: var(--green-light); color: var(--green);
            padding: 3px 10px; border-radius: 20px; font-size: 11px; font-weight: 500;
            white-space: nowrap; flex-shrink: 0;
        }
        .no-schedules { font-size: 14px; color: var(--muted); text-align: center; padding: 12px 0; }

        ::-webkit-scrollbar { width: 0px; background: transparent; }
    </style>
</head>
<body>

    <!-- DRAWER -->
    <div class="drawer-overlay" id="drawer-overlay" onclick="closeDrawer()"></div>
    <div class="drawer" id="drawer">
        <div class="drawer-header">
            <div class="drawer-logo">bamboo.</div>
            <div class="drawer-sub">your quiet reminder space</div>
        </div>
        <div class="drawer-nav">
            <div class="drawer-nav-item active" id="nav-reminders" onclick="switchView('reminders')">
                <svg viewBox="0 0 24 24"><path d="M9 5H7a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2h-2M9 5a2 2 0 0 0 2 2h2a2 2 0 0 0 2-2M9 5a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2"></path><path d="M9 12h6M9 16h4"></path></svg>
                Reminders
            </div>
            <div class="drawer-nav-item" id="nav-dashboard" onclick="switchView('dashboard')">
                <svg viewBox="0 0 24 24"><rect x="3" y="3" width="7" height="7" rx="1"></rect><rect x="14" y="3" width="7" height="7" rx="1"></rect><rect x="3" y="14" width="7" height="7" rx="1"></rect><rect x="14" y="14" width="7" height="7" rx="1"></rect></svg>
                Dashboard
            </div>
        </div>
        <div class="drawer-footer">
            <div class="drawer-stat" id="drawer-stats">— reminders</div>
        </div>
    </div>

    <div class="header-container">
        <div class="menu-btn" onclick="openDrawer()">
            <span></span><span></span><span></span>
        </div>
        <div class="header" id="header-title" onclick="toggleBubble()">bamboo.</div>
        <div class="sort-btn" id="sort-btn-wrapper" onclick="openSortMenu(event)">
            <svg viewBox="0 0 24 24"><path d="M4 6h16M7 12h10M10 18h4"></path></svg>
        </div>
    </div>

    <!-- REMINDERS VIEW -->
    <div class="view active" id="view-reminders">
        <div class="list-container" id="reminder-list"></div>
    </div>

    <!-- DASHBOARD VIEW -->
    <div class="view" id="view-dashboard">
        <div class="dashboard-container" id="dashboard-content"></div>
    </div>

    <!-- Chat Bubble -->
    <div class="chat-bubble-container" id="chat-bubble">
        <div class="chat-bubble">
            <textarea id="reminder-input" placeholder="add a reminder..." rows="1"></textarea>
            <button class="send-btn" onclick="sendReminder()">
                <svg viewBox="0 0 24 24"><path d="M22 2L11 13M22 2l-7 20-4-9-9-4 20-7z"></path></svg>
            </button>
        </div>
    </div>

    <!-- Context Menu -->
    <div id="context-menu" class="context-menu">
        <div class="cm-item" onclick="handleCmAction('edit')">
            <svg viewBox="0 0 24 24"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path></svg> Edit
        </div>
        <div class="cm-item" onclick="handleCmAction('color')">
            <svg viewBox="0 0 24 24"><circle cx="13.5" cy="6.5" r=".5" fill="currentColor"></circle><circle cx="17.5" cy="10.5" r=".5" fill="currentColor"></circle><circle cx="8.5" cy="7.5" r=".5" fill="currentColor"></circle><circle cx="6.5" cy="12.5" r=".5" fill="currentColor"></circle><path d="M12 2C6.5 2 2 6.5 2 12s4.5 10 10 10c.926 0 1.648-.746 1.648-1.688 0-.437-.18-.835-.437-1.125-.29-.289-.438-.652-.438-1.125a1.64 1.64 0 0 1 1.668-1.668h1.996c3.051 0 5.555-2.503 5.555-5.554C21.965 6.012 17.461 2 12 2z"></path></svg> Color
        </div>
        <div class="cm-item" onclick="handleCmAction('notes')">
            <svg viewBox="0 0 24 24"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8zM14 2v6h6M16 13H8M16 17H8M10 9H8"></path></svg> Notes
        </div>
        <div class="cm-item" onclick="handleCmAction('schedule')">
            <svg viewBox="0 0 24 24"><rect x="3" y="4" width="18" height="18" rx="2" ry="2"></rect><line x1="16" y1="2" x2="16" y2="6"></line><line x1="8" y1="2" x2="8" y2="6"></line><line x1="3" y1="10" x2="21" y2="10"></line></svg> Schedule
        </div>
        <div class="cm-divider"></div>
        <div class="cm-item danger" onclick="handleCmAction('delete')">
            <svg viewBox="0 0 24 24"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path></svg> Delete
        </div>
    </div>

    <!-- Sort Menu -->
    <div id="sort-menu" class="context-menu">
        <div class="cm-item" onclick="setSortMode('default')">
            <svg viewBox="0 0 24 24"><path d="M12 20V4M5 13l7 7 7-7"></path></svg> Newest First
        </div>
        <div class="cm-item" onclick="setSortMode('color')">
            <svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"></circle><path d="M12 2a14.5 14.5 0 0 0 0 20 14.5 14.5 0 0 0 0-20"></path></svg> By Color
        </div>
        <div class="cm-item" onclick="setSortMode('schedule')">
            <svg viewBox="0 0 24 24"><rect x="3" y="4" width="18" height="18" rx="2"></rect><line x1="16" y1="2" x2="16" y2="6"></line><line x1="8" y1="2" x2="8" y2="6"></line><line x1="3" y1="10" x2="21" y2="10"></line></svg> By Schedule
        </div>
    </div>

    <!-- Universal Modal (bottom sheet) -->
    <div class="modal" id="action-modal" onclick="closeIfOutside(event)">
        <div class="modal-content" onclick="event.stopPropagation()">
            <div class="modal-handle"></div>
            <h3 class="modal-title" id="modal-title">Edit</h3>
            <div id="modal-body"></div>
            <input type="hidden" id="modal-target-id">
            <input type="hidden" id="modal-action-type">
            <input type="hidden" id="modal-schedule-val">
            <input type="hidden" id="modal-color-val">
            <div class="modal-actions">
                <button class="btn btn-cancel" onclick="closeModal()">Cancel</button>
                <button class="btn btn-save" onclick="saveModal()">Save</button>
            </div>
        </div>
    </div>

    <script>
        /* ── HAPTICS ── */
        function haptic(pattern = 10) {
            if (window.ReactNativeWebView) {
                let style = 'light';
                if (Array.isArray(pattern)) style = pattern.length > 2 ? 'heavy' : 'medium';
                else if (pattern >= 40) style = 'medium';
                window.ReactNativeWebView.postMessage(JSON.stringify({ type: 'HAPTIC', style }));
                return;
            }
            if (navigator.vibrate) { try { navigator.vibrate(pattern); } catch(e) {} }
        }

        /* ── STATE ── */
        let currentContextMenuTarget = null;
        let pressTimer;
        let remindersData = [];
        let currentSortMode = 'default';
        let currentView = 'reminders';

        /* ── TEXTAREA AUTO-RESIZE ── */
        const tx = document.getElementById('reminder-input');
        tx.addEventListener('input', function() {
            this.style.height = 'auto';
            this.style.height = this.scrollHeight + 'px';
            if (!this.value) this.style.height = '24px';
        });
        tx.addEventListener('keydown', function(e) {
            if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendReminder(); }
        });

        /* ── TIMESTAMP HELPERS ── */
        function getTimestamp() {
            const now = new Date();
            let hours = now.getHours();
            const ampm = hours >= 12 ? 'PM' : 'AM';
            hours = hours % 12 || 12;
            const minutes = now.getMinutes().toString().padStart(2, '0');
            return `Today at ${hours}:${minutes} ${ampm}`;
        }

        function getTodayStr() {
            const now = new Date();
            return `${now.getFullYear()}-${String(now.getMonth()+1).padStart(2,'0')}-${String(now.getDate()).padStart(2,'0')}`;
        }

        /* Smart relative timestamp: keep existing stored string but
           rewrite "Today at..." labels based on the stored unix timestamp */
        function smartTimestamp(updatedAt, createdTimestamp) {
            // If we have a precise unix timestamp, use it
            if (createdTimestamp && createdTimestamp > 0) {
                const now = Date.now();
                const diff = now - createdTimestamp;
                const days = Math.floor(diff / 86400000);
                const date = new Date(createdTimestamp);
                const hours = date.getHours();
                const ampm = hours >= 12 ? 'PM' : 'AM';
                const h = hours % 12 || 12;
                const m = date.getMinutes().toString().padStart(2,'0');
                const time = `${h}:${m} ${ampm}`;

                if (days === 0) return `Today at ${time}`;
                if (days === 1) return `Yesterday at ${time}`;
                if (days === 2) return `2 days ago`;
                if (days === 3) return `3 days ago`;
                if (days === 4) return `4 days ago`;
                if (days === 5) return `5 days ago`;
                // Older: show actual date
                const months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
                return `${months[date.getMonth()]} ${date.getDate()}`;
            }
            // Fallback: use stored string as-is
            return updatedAt || 'Just now';
        }

        /* Days remaining for schedule */
        function getDaysRemaining(r) {
            if (!r.schedule_preset || r.schedule_preset === 'none' || !r.schedule_start) return null;
            let totalDays = 0, msInterval = 86400000;
            if (r.schedule_preset === 'day')   { totalDays = 3;  msInterval = 86400000; }
            if (r.schedule_preset === 'week')  { totalDays = 14; msInterval = 86400000; }
            if (r.schedule_preset === 'month') { totalDays = 30; msInterval = 172800000; }

            const remaining = totalDays - (r.notifications_sent || 0);
            return remaining > 0 ? remaining : 0;
        }

        /* ── FETCH & RENDER ── */
        async function fetchReminders() {
            const res = await fetch('/api/reminders');
            remindersData = await res.json();
            renderReminders();
            updateDrawerStats();
            if (currentView === 'dashboard') renderDashboard();
        }

        function renderReminders() {
            let sorted = [...remindersData];
            sorted.sort((a, b) => {
                if (a.completed !== b.completed) return a.completed ? 1 : -1;
                if (currentSortMode === 'color') {
                    if ((a.color||'') === (b.color||'')) return b.id - a.id;
                    return (a.color||'').localeCompare(b.color||'');
                } else if (currentSortMode === 'schedule') {
                    const aS = (a.schedule_preset && a.schedule_preset !== 'none') ? 1 : 0;
                    const bS = (b.schedule_preset && b.schedule_preset !== 'none') ? 1 : 0;
                    if (aS === bS) return b.id - a.id;
                    return bS - aS;
                }
                return b.id - a.id;
            });

            const list = document.getElementById('reminder-list');
            
            const active = sorted.filter(r => !r.completed);
            const done   = sorted.filter(r => r.completed);

            let html = '';
            if (active.length === 0 && done.length === 0) {
                html = `<div style="text-align:center; padding: 60px 0; color: var(--muted); font-size:15px; font-weight:300;">
                    nothing here yet.<br><span style="font-size:13px; opacity:0.6;">tap bamboo. to add one</span>
                </div>`;
            } else {
                active.forEach((r, i) => { html += renderItem(r, i); });
                if (done.length > 0) {
                    html += `<div class="section-label" style="animation-delay:${active.length*0.05}s; animation: slideUpFade 0.35s ease-out forwards; opacity:0;">Completed</div>`;
                    done.forEach((r, i) => { html += renderItem(r, active.length + i + 1); });
                }
            }
            list.innerHTML = html;
        }

        function renderItem(r, index) {
            const delay = index * 0.045;
            const timeStr = smartTimestamp(r.updated_at, r.created_timestamp);
            const daysLeft = getDaysRemaining(r);

            let metaHtml = `<span><svg class="meta-icon" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"></circle><polyline points="12 6 12 12 16 14"></polyline></svg>${timeStr}</span>`;

            if (daysLeft !== null) {
                metaHtml += `<span class="days-badge"><svg class="meta-icon" viewBox="0 0 24 24"><rect x="3" y="4" width="18" height="18" rx="2"></rect><line x1="16" y1="2" x2="16" y2="6"></line><line x1="8" y1="2" x2="8" y2="6"></line><line x1="3" y1="10" x2="21" y2="10"></line></svg>${daysLeft}d left</span>`;
            }
            if (r.notes) {
                metaHtml += `<span><svg class="meta-icon" viewBox="0 0 24 24"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path></svg>notes</span>`;
            }

            const rJson = JSON.stringify(r).replace(/'/g, "&#39;").replace(/"/g, "&quot;");
            const borderStyle = (r.color && !r.completed) ? `border-left-color: ${r.color};` : '';

            return `
                <div class="reminder-item ${r.completed ? 'completed' : ''}" 
                     style="animation-delay: ${delay}s; ${borderStyle}"
                     onclick="handleItemClick(event, ${r.id}, ${!r.completed})"
                     oncontextmenu="handleContextMenu(event, '${rJson}')"
                     ontouchstart="handleTouchStart(event, '${rJson}')"
                     ontouchend="handleTouchEnd(event)"
                     ontouchcancel="handleTouchEnd(event)">
                    <div class="reminder-content-wrapper">
                        <div class="reminder-text">${escapeHtml(r.text)}</div>
                        <div class="reminder-meta">${metaHtml}</div>
                    </div>
                </div>`;
        }

        function escapeHtml(str) {
            return str.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
        }

        /* ── DASHBOARD ── */
        function renderDashboard() {
            const today = getTodayStr();
            const total = remindersData.length;
            const completed = remindersData.filter(r => r.completed).length;
            const active = total - completed;

            // Streak: did user complete ≥1 task each day?
            // Build a map of completed_date → count
            const completedByDate = {};
            remindersData.forEach(r => {
                if (r.completed && r.completed_date) {
                    completedByDate[r.completed_date] = (completedByDate[r.completed_date] || 0) + 1;
                }
            });

            // Calculate streak (consecutive days ending today/yesterday)
            let streak = 0;
            const checkDate = new Date();
            // If today has completions, start from today; else start from yesterday
            const todayHas = completedByDate[today] > 0;
            if (!todayHas) checkDate.setDate(checkDate.getDate() - 1);

            for (let i = 0; i < 365; i++) {
                const d = checkDate.toISOString().slice(0,10);
                if (completedByDate[d]) { streak++; checkDate.setDate(checkDate.getDate() - 1); }
                else break;
            }

            // Build last 14 days dot display
            const dots = [];
            for (let i = 13; i >= 0; i--) {
                const d = new Date(); d.setDate(d.getDate() - i);
                const ds = d.toISOString().slice(0,10);
                const dayLabel = ['Su','Mo','Tu','We','Th','Fr','Sa'][d.getDay()];
                if (ds === today) dots.push({label: dayLabel, type: completedByDate[ds] ? 'done' : 'today'});
                else if (ds < today) dots.push({label: dayLabel, type: completedByDate[ds] ? 'done' : 'miss'});
                else dots.push({label: dayLabel, type: 'future'});
            }

            const dotsHtml = dots.map(d => `<div class="streak-dot ${d.type}">${d.label}</div>`).join('');

            // Active schedules
            const scheduled = remindersData.filter(r => !r.completed && r.schedule_preset && r.schedule_preset !== 'none');
            let scheduledHtml = '';
            if (scheduled.length === 0) {
                scheduledHtml = `<div class="no-schedules">No active schedules</div>`;
            } else {
                scheduledHtml = scheduled.map(r => {
                    const left = getDaysRemaining(r);
                    return `<div class="schedule-item">
                        <div class="schedule-item-text">${escapeHtml(r.text)}</div>
                        <div class="schedule-item-badge">${left}d left</div>
                    </div>`;
                }).join('');
            }

            const streakMsg = streak === 0 ? "Complete a task to start your streak" :
                              streak === 1 ? "Keep it up — day 2 tomorrow!" :
                              `${streak} days strong 🌿`;

            document.getElementById('dashboard-content').innerHTML = `
                <div style="padding-top: 4px;"></div>
                
                <div class="dash-card" style="animation-delay:0s">
                    <div class="dash-card-label">Streak</div>
                    <div class="streak-display">
                        <div class="streak-num">${streak}</div>
                        <div class="streak-unit">day${streak !== 1 ? 's' : ''}</div>
                    </div>
                    <div class="streak-sub">${streakMsg}</div>
                    <div class="streak-dots" style="margin-top:20px">${dotsHtml}</div>
                </div>

                <div class="dash-card" style="animation-delay:0.06s">
                    <div class="dash-card-label">Overview</div>
                    <div class="stats-row">
                        <div class="stat-cell">
                            <div class="stat-val">${total}</div>
                            <div class="stat-lbl">Total</div>
                        </div>
                        <div class="stat-cell">
                            <div class="stat-val">${active}</div>
                            <div class="stat-lbl">Active</div>
                        </div>
                        <div class="stat-cell">
                            <div class="stat-val">${completed}</div>
                            <div class="stat-lbl">Done</div>
                        </div>
                    </div>
                </div>

                <div class="dash-card" style="animation-delay:0.12s">
                    <div class="dash-card-label">Scheduled Reminders</div>
                    ${scheduledHtml}
                </div>
            `;
        }

        /* ── DRAWER & VIEW SWITCHING ── */
        function openDrawer() {
            haptic(10);
            document.getElementById('drawer').classList.add('show');
            document.getElementById('drawer-overlay').classList.add('show');
        }
        function closeDrawer() {
            document.getElementById('drawer').classList.remove('show');
            document.getElementById('drawer-overlay').classList.remove('show');
        }

        function switchView(view) {
            haptic(10);
            closeDrawer();
            currentView = view;
            document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
            document.querySelectorAll('.drawer-nav-item').forEach(n => n.classList.remove('active'));
            document.getElementById(`view-${view}`).classList.add('active');
            document.getElementById(`nav-${view}`).classList.add('active');
            document.getElementById('header-title').textContent = view === 'dashboard' ? 'dashboard.' : 'bamboo.';
            document.getElementById('sort-btn-wrapper').style.display = view === 'dashboard' ? 'none' : '';
            document.getElementById('chat-bubble').classList.remove('show');
            if (view === 'dashboard') renderDashboard();
        }

        function updateDrawerStats() {
            const active = remindersData.filter(r => !r.completed).length;
            document.getElementById('drawer-stats').textContent = `${active} active reminder${active !== 1 ? 's' : ''}`;
        }

        /* ── BODY CLICK HANDLER ── */
        document.body.addEventListener('click', (e) => {
            const isItem    = e.target.closest('.reminder-item');
            const isModal   = e.target.closest('.modal');
            const isMenu    = e.target.closest('.context-menu');
            const isBubble  = e.target.closest('.chat-bubble-container');
            const isHeader  = e.target.closest('.header');
            const isSortBtn = e.target.closest('.sort-btn');
            const isMenuBtn = e.target.closest('.menu-btn');
            const isDrawer  = e.target.closest('.drawer');

            if (!isMenu) {
                document.getElementById('context-menu').classList.remove('show');
                document.getElementById('sort-menu').classList.remove('show');
            }

            if (!isItem && !isModal && !isMenu && !isBubble && !isHeader && !isSortBtn && !isMenuBtn && !isDrawer && currentView === 'reminders') {
                const bubble = document.getElementById('chat-bubble');
                if (bubble.classList.contains('show')) {
                    if (!document.getElementById('reminder-input').value.trim()) {
                        bubble.classList.remove('show');
                    }
                } else {
                    haptic(10);
                    bubble.classList.add('show');
                    setTimeout(() => document.getElementById('reminder-input').focus(), 300);
                }
            }
        });

        function toggleBubble() {
            if (currentView !== 'reminders') return;
            haptic(10);
            const bubble = document.getElementById('chat-bubble');
            if (bubble.classList.contains('show')) bubble.classList.remove('show');
            else {
                bubble.classList.add('show');
                setTimeout(() => document.getElementById('reminder-input').focus(), 300);
            }
        }

        function openSortMenu(e) {
            e.stopPropagation(); haptic(10);
            const menu = document.getElementById('sort-menu');
            menu.classList.add('show');
            const r = e.currentTarget.getBoundingClientRect();
            menu.style.top  = (r.bottom + 8) + 'px';
            menu.style.left = (r.right - 165) + 'px';
        }

        function setSortMode(mode) {
            haptic(15); currentSortMode = mode;
            document.getElementById('sort-menu').classList.remove('show');
            renderReminders();
        }

        /* ── SEND ── */
        async function sendReminder() {
            const input = document.getElementById('reminder-input');
            const text = input.value.trim();
            if (!text) return;
            const now = Date.now();
            await fetch('/api/reminders', {
                method: 'POST', headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ text, updated_at: getTimestamp(), created_timestamp: now })
            });
            input.value = ''; input.style.height = '24px';
            document.getElementById('chat-bubble').classList.remove('show');
            haptic(50); fetchReminders();
        }

        /* ── ITEM CLICK (toggle complete) ── */
        async function handleItemClick(e, id, completeStatus) {
            if (e.button === 2) return;
            haptic(15);
            const today = getTodayStr();
            await fetch(`/api/reminders/${id}`, {
                method: 'PUT', headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    completed: completeStatus,
                    updated_at: getTimestamp(),
                    completed_date: completeStatus ? today : ''
                })
            });
            fetchReminders();
        }

        /* ── CONTEXT MENU ── */
        function handleContextMenu(e, rJsonStr) {
            e.preventDefault();
            const r = JSON.parse(rJsonStr.replace(/&quot;/g, '"').replace(/&#39;/g, "'"));
            currentContextMenuTarget = r;
            const menu = document.getElementById('context-menu');
            menu.classList.add('show');
            let x = e.clientX || (e.touches && e.touches[0].clientX);
            let y = e.clientY || (e.touches && e.touches[0].clientY);
            if (x + 195 > window.innerWidth) x = window.innerWidth - 200;
            if (y + 270 > window.innerHeight) y = window.innerHeight - 275;
            menu.style.left = `${x}px`; menu.style.top = `${y}px`;
        }

        function handleTouchStart(e, rJsonStr) {
            pressTimer = setTimeout(() => { handleContextMenu(e, rJsonStr); haptic([30, 40]); }, 600);
        }
        function handleTouchEnd() { clearTimeout(pressTimer); }

        function handleCmAction(action) {
            document.getElementById('context-menu').classList.remove('show');
            haptic(15);
            if (!currentContextMenuTarget) return;
            if (action === 'delete') { deleteReminder(currentContextMenuTarget.id); return; }
            openModal(action, currentContextMenuTarget);
        }

        async function deleteReminder(id) {
            await fetch(`/api/reminders/${id}`, { method: 'DELETE' });
            fetchReminders();
        }

        /* ── MODALS ── */
        const COLORS = ['#fda4af', '#86efac', '#d8b4fe', '#fdba74', '#7dd3fc', '#f9a8d4'];

        function openModal(action, r) {
            document.getElementById('modal-target-id').value = r.id;
            document.getElementById('modal-action-type').value = action;
            const title = document.getElementById('modal-title');
            const body  = document.getElementById('modal-body');

            if (action === 'edit') {
                title.textContent = 'Edit';
                body.innerHTML = `<textarea id="modal-input-val" class="modal-input">${r.text.replace(/"/g,'&quot;')}</textarea>`;
                document.getElementById('action-modal').classList.add('show');
                setTimeout(() => document.getElementById('modal-input-val').focus(), 100);
            } else if (action === 'notes') {
                title.textContent = 'Notes';
                body.innerHTML = `<textarea id="modal-input-val" class="modal-input" placeholder="Add details...">${r.notes || ''}</textarea>`;
                document.getElementById('action-modal').classList.add('show');
                setTimeout(() => document.getElementById('modal-input-val').focus(), 100);
            } else if (action === 'schedule') {
                title.textContent = 'Schedule';
                document.getElementById('modal-schedule-val').value = r.schedule_preset || 'none';
                body.innerHTML = `
                    <div style="font-size:13px; color:var(--muted); margin-bottom:14px; font-weight:300;">We'll send you reminders over the selected period.</div>
                    <div class="preset-grid">
                        <div class="preset-card ${r.schedule_preset==='day'?'active':''}" onclick="setPreset(this,'day')">
                            <div class="preset-name">Day</div><div class="preset-desc">3 notifs</div>
                        </div>
                        <div class="preset-card ${r.schedule_preset==='week'?'active':''}" onclick="setPreset(this,'week')">
                            <div class="preset-name">Week</div><div class="preset-desc">14 notifs</div>
                        </div>
                        <div class="preset-card ${r.schedule_preset==='month'?'active':''}" onclick="setPreset(this,'month')">
                            <div class="preset-name">Month</div><div class="preset-desc">15 notifs</div>
                        </div>
                    </div>`;
                document.getElementById('action-modal').classList.add('show');
                if (Notification.permission !== 'granted') Notification.requestPermission();
            } else if (action === 'color') {
                title.textContent = 'Color';
                document.getElementById('modal-color-val').value = r.color || '';
                let colorHtml = '<div class="color-grid">';
                colorHtml += `<div class="color-swatch color-clear ${!r.color?'active':''}" onclick="setColor(this,'')"><svg viewBox="0 0 24 24" fill="none"><path d="M18 6L6 18M6 6l12 12" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg></div>`;
                COLORS.forEach(c => {
                    colorHtml += `<div class="color-swatch ${r.color===c?'active':''}" style="background:${c}" onclick="setColor(this,'${c}')"></div>`;
                });
                colorHtml += '</div>';
                body.innerHTML = colorHtml;
                document.getElementById('action-modal').classList.add('show');
            }
        }

        function setPreset(el, preset) {
            haptic(10);
            document.querySelectorAll('.preset-card').forEach(c => c.classList.remove('active'));
            el.classList.add('active');
            document.getElementById('modal-schedule-val').value = preset;
        }

        function setColor(el, color) {
            haptic(10);
            document.querySelectorAll('.color-swatch').forEach(c => c.classList.remove('active'));
            el.classList.add('active');
            document.getElementById('modal-color-val').value = color;
        }

        function closeModal() { document.getElementById('action-modal').classList.remove('show'); }
        function closeIfOutside(e) { if (e.target.id === 'action-modal') closeModal(); }

        async function saveModal() {
            haptic([20, 30]);
            const id     = document.getElementById('modal-target-id').value;
            const action = document.getElementById('modal-action-type').value;
            const payload = { updated_at: getTimestamp() };
            if (action === 'edit')     payload.text = document.getElementById('modal-input-val').value;
            if (action === 'notes')    payload.notes = document.getElementById('modal-input-val').value;
            if (action === 'schedule') {
                payload.schedule_preset   = document.getElementById('modal-schedule-val').value;
                payload.schedule_start    = Date.now();
                payload.notifications_sent = 0;
            }
            if (action === 'color') payload.color = document.getElementById('modal-color-val').value;
            await fetch(`/api/reminders/${id}`, {
                method: 'PUT', headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(payload)
            });
            closeModal(); fetchReminders();
        }

        /* ── NOTIFICATION SCHEDULER ── */
        setInterval(async () => {
            if (Notification.permission !== 'granted') return;
            const now = Date.now();
            for (let r of remindersData) {
                if (r.completed || !r.schedule_preset || r.schedule_preset === 'none') continue;
                let targetCount = 0, msInterval = 86400000;
                if (r.schedule_preset === 'day')   { targetCount = 3;  msInterval = 86400000; }
                if (r.schedule_preset === 'week')  { targetCount = 14; msInterval = 86400000; }
                if (r.schedule_preset === 'month') { targetCount = 15; msInterval = 172800000; }
                if (r.notifications_sent < targetCount) {
                    const nextTrigger = r.schedule_start + (r.notifications_sent * msInterval);
                    if (now >= nextTrigger) {
                        new Notification("bamboo.", { body: r.text, icon: "https://cdn-icons-png.flaticon.com/512/3221/3221845.png" });
                        r.notifications_sent++;
                        await fetch(`/api/reminders/${r.id}`, {
                            method: 'PUT', headers: {'Content-Type': 'application/json'},
                            body: JSON.stringify({ notifications_sent: r.notifications_sent })
                        });
                    }
                }
            }
        }, 60000);

        /* ── INIT ── */
        fetchReminders();
    </script>
</body>
</html>
"""

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
