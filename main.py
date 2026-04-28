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

with app.app_context():
    db.create_all()

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
        "color": r.color
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
            color=data.get('color', '')
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
            --dark: #2C251B;
            --bg: #FDFBF7;
            --muted: rgba(44, 37, 27, 0.4);
            --border: rgba(44, 37, 27, 0.1);
        }
        
        body, html {
            margin: 0; padding: 0; font-family: 'Outfit', sans-serif;
            background-color: var(--bg); color: var(--dark);
            -webkit-font-smoothing: antialiased;
            min-height: 100vh; overflow-x: hidden;
        }

        /* --- Header --- */
        .header-container {
            display: flex; align-items: center; justify-content: center; position: relative;
            padding: 60px 20px 20px 20px; animation: fadeIn 0.8s ease-out forwards; max-width: 600px; margin: 0 auto;
        }
        .header {
            font-size: 32px; font-weight: 500; letter-spacing: 2px;
            color: var(--accent); text-transform: lowercase; user-select: none; cursor: pointer;
        }
        .sort-btn {
            position: absolute; right: 20px; bottom: 24px;
            width: 36px; height: 36px; border-radius: 50%;
            display: flex; align-items: center; justify-content: center;
            cursor: pointer; transition: background 0.2s; color: var(--muted);
        }
        .sort-btn:hover { background: rgba(0,0,0,0.04); color: var(--dark); }
        .sort-btn svg { width: 18px; height: 18px; stroke: currentColor; stroke-width: 2; fill: none; }

        /* --- Reminders List --- */
        .list-container {
            max-width: 600px; margin: 0 auto; padding: 0 20px;
            padding-bottom: 150px;
        }

        @keyframes slideUpFade {
            from { opacity: 0; transform: translateY(15px); }
            to { opacity: 1; transform: translateY(0); }
        }

        .reminder-item {
            padding: 20px 0 20px 16px; border-bottom: 1px solid var(--border);
            cursor: pointer; transition: all 0.4s cubic-bezier(0.165, 0.84, 0.44, 1);
            user-select: none; -webkit-user-select: none; -webkit-touch-callout: none;
            animation: slideUpFade 0.4s ease-out forwards;
            opacity: 0; transform-origin: top; border-left: 4px solid transparent;
        }

        .reminder-item:hover { transform: translateX(4px); }
        .reminder-item.completed { opacity: 0.35; border-left-color: transparent !important; }
        .reminder-item.completed:hover { transform: translateX(0); }

        .reminder-content-wrapper { pointer-events: none; }

        .reminder-text {
            font-size: 20px; font-weight: 400; line-height: 1.5;
            transition: color 0.4s, text-decoration 0.4s;
            word-wrap: break-word; overflow-wrap: break-word; white-space: pre-wrap;
        }
        
        .reminder-item.completed .reminder-text { text-decoration: line-through; color: var(--muted); }

        .reminder-meta {
            display: flex; gap: 12px; margin-top: 8px; font-size: 13px;
            color: var(--muted); font-weight: 300; transition: opacity 0.4s;
        }
        .reminder-meta span { display: flex; align-items: center; gap: 4px; }
        .meta-icon { width: 14px; height: 14px; stroke: currentColor; stroke-width: 2; fill: none; }

        /* --- Chat Bubble Input --- */
        .chat-bubble-container {
            position: fixed; bottom: -150px; left: 50%; transform: translateX(-50%);
            width: calc(100% - 40px); max-width: 500px;
            transition: bottom 0.5s cubic-bezier(0.175, 0.885, 0.32, 1.275);
            z-index: 100;
        }
        
        .chat-bubble-container.show { bottom: 40px; }

        .chat-bubble {
            background: var(--dark); border-radius: 30px;
            padding: 12px 16px 12px 24px; display: flex; align-items: flex-end; gap: 16px;
            box-shadow: 0 15px 35px rgba(44, 37, 27, 0.25);
            transition: border-radius 0.3s ease;
        }

        .chat-bubble textarea {
            flex: 1; border: none; outline: none; background: transparent;
            font-size: 18px; font-family: inherit; color: var(--bg);
            font-weight: 300; resize: none; overflow-y: auto; line-height: 1.4;
            max-height: 120px; padding: 0; margin: 0; margin-bottom: 6px;
        }
        .chat-bubble textarea::placeholder { color: rgba(253, 251, 247, 0.5); }

        .send-btn {
            background: var(--accent); color: var(--dark); border: none; border-radius: 50%;
            width: 40px; height: 40px; flex-shrink: 0; display: flex; align-items: center; justify-content: center;
            cursor: pointer; transition: transform 0.2s; margin-bottom: 2px;
        }
        .send-btn:active { transform: scale(0.9); }
        .send-btn svg { width: 20px; height: 20px; stroke: currentColor; stroke-width: 2; fill: none; margin-left: 2px;}

        /* --- Context Menu --- */
        .context-menu {
            position: fixed; background: white; border-radius: 16px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.15); padding: 8px; min-width: 180px; z-index: 200;
            display: none; opacity: 0; transform: scale(0.95); transform-origin: top left;
            transition: opacity 0.2s, transform 0.2s; border: 1px solid var(--border);
        }
        .context-menu.show { display: flex; flex-direction: column; opacity: 1; transform: scale(1); }

        .cm-item {
            padding: 12px 16px; font-size: 15px; cursor: pointer; border-radius: 8px;
            transition: background 0.2s; display: flex; align-items: center; gap: 10px;
        }
        .cm-item:hover { background: rgba(0,0,0,0.03); }
        .cm-item.danger { color: #ef4444; }
        .cm-item svg { width: 16px; height: 16px; stroke: currentColor; stroke-width: 2; fill: none; }
        .cm-divider { height: 1px; background: var(--border); margin: 4px 0; }

        /* --- Sort Menu --- */
        #sort-menu { width: 160px; }

        /* --- Modals --- */
        .modal {
            display: none; position: fixed; top: 0; left: 0; right: 0; bottom: 0;
            background: rgba(44, 37, 27, 0.4); backdrop-filter: blur(6px); z-index: 300;
            align-items: center; justify-content: center; opacity: 0; transition: opacity 0.3s;
        }
        .modal.show { display: flex; opacity: 1; }
        .modal-content {
            background: var(--bg); padding: 32px; border-radius: 24px; width: 90%; max-width: 400px;
            display: flex; flex-direction: column; gap: 20px;
            transform: translateY(20px) scale(0.95); transition: transform 0.4s cubic-bezier(0.175, 0.885, 0.32, 1.275);
            box-shadow: 0 20px 40px rgba(0,0,0,0.2);
        }
        .modal.show .modal-content { transform: translateY(0) scale(1); }
        
        .modal-title { font-size: 20px; font-weight: 500; color: var(--dark); margin: 0;}
        
        .modal-input {
            width: 100%; box-sizing: border-box; padding: 14px 16px; border: 1px solid var(--border);
            border-radius: 12px; font-family: inherit; font-size: 16px; outline: none; background: transparent;
            color: var(--dark); transition: border-color 0.3s;
        }
        textarea.modal-input { resize: vertical; min-height: 100px; line-height: 1.5; }
        .modal-input:focus { border-color: var(--accent); }

        /* Color Picker */
        .color-grid { display: grid; grid-template-columns: repeat(6, 1fr); gap: 12px; justify-items: center; }
        .color-swatch {
            width: 40px; height: 40px; border-radius: 50%; cursor: pointer;
            border: 2px solid transparent; transition: transform 0.2s; box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }
        .color-swatch:hover { transform: scale(1.1); }
        .color-swatch.active { border-color: var(--dark); transform: scale(1.1); }
        .color-clear { background: transparent; border: 2px dashed #d1d5db; box-shadow: none; display: flex; align-items: center; justify-content: center;}
        .color-clear svg { width: 20px; height: 20px; stroke: #9ca3af; }

        .preset-grid { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 8px; }
        .preset-card {
            border: 1px solid var(--border); border-radius: 12px; padding: 16px 8px; text-align: center;
            cursor: pointer; transition: all 0.2s;
        }
        .preset-card.active { border-color: var(--accent); background: rgba(193, 177, 154, 0.1); }
        .preset-card:hover { transform: translateY(-2px); }
        .preset-name { font-weight: 500; font-size: 16px; margin-bottom: 4px; }
        .preset-desc { font-size: 12px; color: var(--muted); }
        
        .modal-actions { display: flex; gap: 12px; justify-content: flex-end; }
        .btn {
            padding: 12px 20px; border-radius: 12px; font-family: inherit; font-size: 15px; font-weight: 500;
            cursor: pointer; border: none; transition: all 0.2s;
        }
        .btn-cancel { background: transparent; color: var(--muted); }
        .btn-cancel:hover { color: var(--dark); background: rgba(0,0,0,0.05); }
        .btn-save { background: var(--accent); color: var(--dark); }
        .btn-save:hover { filter: brightness(0.95); transform: translateY(-2px); box-shadow: 0 4px 12px rgba(193, 177, 154, 0.4);}

        ::-webkit-scrollbar { width: 0px; background: transparent; }
    </style>
</head>
<body>

    <div class="header-container">
        <div class="header" onclick="toggleBubble()">bamboo.</div>
        <div class="sort-btn" onclick="openSortMenu(event)">
            <svg viewBox="0 0 24 24"><path d="M4 6h16 M7 12h10 M10 18h4" stroke-linecap="round"></path></svg>
        </div>
    </div>

    <div class="list-container" id="reminder-list"></div>

    <div class="chat-bubble-container" id="chat-bubble">
        <div class="chat-bubble">
            <textarea id="reminder-input" placeholder="Type a reminder..." rows="1"></textarea>
            <button class="send-btn" onclick="sendReminder()">
                <svg viewBox="0 0 24 24"><path d="M22 2L11 13 M22 2l-7 20-4-9-9-4 20-7z" stroke-linejoin="round"></path></svg>
            </button>
        </div>
    </div>

    <!-- Context Menu -->
    <div id="context-menu" class="context-menu">
        <div class="cm-item" onclick="handleCmAction('edit')">
            <svg viewBox="0 0 24 24"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7 M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" stroke-linejoin="round"></path></svg> Edit
        </div>
        <div class="cm-item" onclick="handleCmAction('color')">
            <svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"></circle><path d="M12 2a14.5 14.5 0 0 0 0 20 14.5 14.5 0 0 0 0-20"></path></svg> Color
        </div>
        <div class="cm-item" onclick="handleCmAction('notes')">
            <svg viewBox="0 0 24 24"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z M14 2v6h6 M16 13H8 M16 17H8 M10 9H8"></path></svg> Add Notes
        </div>
        <div class="cm-item" onclick="handleCmAction('schedule')">
            <svg viewBox="0 0 24 24"><path d="M3 4h18v16H3z M16 2v4 M8 2v4 M3 10h18"></path></svg> Schedule
        </div>
        <div class="cm-divider"></div>
        <div class="cm-item danger" onclick="handleCmAction('delete')">
            <svg viewBox="0 0 24 24"><path d="M3 6h18 M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2 M10 11v6 M14 11v6"></path></svg> Delete
        </div>
    </div>

    <!-- Sort Menu -->
    <div id="sort-menu" class="context-menu">
        <div class="cm-item" onclick="setSortMode('default')">
            <svg viewBox="0 0 24 24"><path d="M12 20V4 M5 13l7 7 7-7"></path></svg> Newest First
        </div>
        <div class="cm-item" onclick="setSortMode('color')">
            <svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"></circle><path d="M12 2a14.5 14.5 0 0 0 0 20 14.5 14.5 0 0 0 0-20"></path></svg> By Color
        </div>
        <div class="cm-item" onclick="setSortMode('schedule')">
            <svg viewBox="0 0 24 24"><path d="M3 4h18v16H3z M16 2v4 M8 2v4 M3 10h18"></path></svg> By Schedule
        </div>
    </div>

    <!-- Universal Modal -->
    <div class="modal" id="action-modal" onclick="closeIfOutside(event)">
        <div class="modal-content" onclick="event.stopPropagation()">
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
        function haptic(pattern = 10) {
            if (window.ReactNativeWebView) {
                let style = 'light';
                if (Array.isArray(pattern)) style = pattern.length > 2 ? 'heavy' : 'medium';
                else if (pattern >= 40) style = 'medium';
                window.ReactNativeWebView.postMessage(JSON.stringify({ type: 'HAPTIC', style: style }));
                return;
            }
            if (navigator.vibrate) { try { navigator.vibrate(pattern); } catch(e) {} }
        }

        let currentContextMenuTarget = null;
        let pressTimer;
        let remindersData = [];
        let currentSortMode = 'default';

        const tx = document.getElementById('reminder-input');
        tx.addEventListener('input', function() {
            this.style.height = 'auto';
            this.style.height = (this.scrollHeight) + 'px';
            if (this.value === '') this.style.height = '24px';
        });
        
        tx.addEventListener('keydown', function(e) {
            if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendReminder(); }
        });

        async function fetchReminders() {
            const res = await fetch('/api/reminders');
            remindersData = await res.json();
            renderReminders();
        }

        function renderReminders() {
            let sorted = [...remindersData];
            
            // Sort Active items based on mode
            sorted.sort((a, b) => {
                if(a.completed !== b.completed) return a.completed ? 1 : -1;
                
                if (currentSortMode === 'color') {
                    if ((a.color || '') === (b.color || '')) return b.id - a.id;
                    return (a.color || '').localeCompare(b.color || '');
                } else if (currentSortMode === 'schedule') {
                    const aSch = (a.schedule_preset && a.schedule_preset !== 'none') ? 1 : 0;
                    const bSch = (b.schedule_preset && b.schedule_preset !== 'none') ? 1 : 0;
                    if (aSch === bSch) return b.id - a.id;
                    return bSch - aSch;
                } else {
                    return b.id - a.id; // Default: Newest first
                }
            });

            const list = document.getElementById('reminder-list');
            list.innerHTML = sorted.map((r, index) => {
                const delay = index * 0.05;
                
                let metaHtml = `<span><svg class="meta-icon" viewBox="0 0 24 24"><path d="M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20z M12 6v6l4 2"></path></svg> ${r.updated_at || 'Just now'}</span>`;
                if(r.schedule_preset && r.schedule_preset !== 'none') {
                    metaHtml += `<span><svg class="meta-icon" viewBox="0 0 24 24"><path d="M3 4h18v16H3z M16 2v4 M8 2v4 M3 10h18"></path></svg> ${r.schedule_preset} (${r.notifications_sent} sent)</span>`;
                }
                if(r.notes) {
                    metaHtml += `<span><svg class="meta-icon" viewBox="0 0 24 24"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path></svg> Has notes</span>`;
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
                            <div class="reminder-text">${r.text}</div>
                            <div class="reminder-meta">${metaHtml}</div>
                        </div>
                    </div>
                `;
            }).join('');
        }

        document.body.addEventListener('click', (e) => {
            const isItem = e.target.closest('.reminder-item');
            const isModal = e.target.closest('.modal');
            const isMenu = e.target.closest('.context-menu');
            const isBubble = e.target.closest('.chat-bubble-container');
            const isHeader = e.target.closest('.header');
            const isSortBtn = e.target.closest('.sort-btn');
            
            if(!isMenu) {
                document.getElementById('context-menu').classList.remove('show');
                document.getElementById('sort-menu').classList.remove('show');
            }

            if(!isItem && !isModal && !isMenu && !isBubble && !isHeader && !isSortBtn) {
                const bubble = document.getElementById('chat-bubble');
                if (bubble.classList.contains('show')) {
                    if (document.getElementById('reminder-input').value.trim() === '') {
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
            haptic(10);
            const bubble = document.getElementById('chat-bubble');
            if(bubble.classList.contains('show')) bubble.classList.remove('show');
            else {
                bubble.classList.add('show');
                setTimeout(() => document.getElementById('reminder-input').focus(), 300);
            }
        }

        function openSortMenu(e) {
            e.stopPropagation();
            haptic(10);
            const menu = document.getElementById('sort-menu');
            menu.classList.add('show');
            
            const btnRect = e.currentTarget.getBoundingClientRect();
            menu.style.top = (btnRect.bottom + 8) + 'px';
            menu.style.left = (btnRect.right - 160) + 'px';
        }

        function setSortMode(mode) {
            haptic(15);
            currentSortMode = mode;
            document.getElementById('sort-menu').classList.remove('show');
            renderReminders();
        }

        function getTimestamp() {
            const now = new Date();
            let hours = now.getHours();
            const ampm = hours >= 12 ? 'PM' : 'AM';
            hours = hours % 12;
            hours = hours ? hours : 12; 
            const minutes = now.getMinutes().toString().padStart(2, '0');
            return `Today at ${hours}:${minutes} ${ampm}`;
        }

        async function sendReminder() {
            const input = document.getElementById('reminder-input');
            const text = input.value.trim();
            if(!text) return;

            await fetch('/api/reminders', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({text: text, updated_at: getTimestamp()})
            });
            
            input.value = '';
            input.style.height = '24px';
            document.getElementById('chat-bubble').classList.remove('show');
            haptic(50);
            fetchReminders();
        }

        async function handleItemClick(e, id, completeStatus) {
            if(e.button === 2) return; 
            haptic(15);
            await fetch(`/api/reminders/${id}`, {
                method: 'PUT', headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({completed: completeStatus, updated_at: getTimestamp()})
            });
            fetchReminders();
        }

        function handleContextMenu(e, rJsonStr) {
            e.preventDefault();
            const r = JSON.parse(rJsonStr.replace(/&quot;/g, '"').replace(/&#39;/g, "'"));
            currentContextMenuTarget = r;
            
            const menu = document.getElementById('context-menu');
            menu.classList.add('show');
            
            let x = e.clientX || (e.touches && e.touches[0].clientX);
            let y = e.clientY || (e.touches && e.touches[0].clientY);
            
            if (x + 180 > window.innerWidth) x = window.innerWidth - 190;
            if (y + 260 > window.innerHeight) y = window.innerHeight - 270;

            menu.style.left = `${x}px`;
            menu.style.top = `${y}px`;
        }

        function handleTouchStart(e, rJsonStr) {
            pressTimer = setTimeout(() => {
                handleContextMenu(e, rJsonStr);
                haptic([30, 40]);
            }, 600);
        }

        function handleTouchEnd(e) { clearTimeout(pressTimer); }

        function handleCmAction(action) {
            document.getElementById('context-menu').classList.remove('show');
            haptic(15);
            if(!currentContextMenuTarget) return;

            const r = currentContextMenuTarget;
            if(action === 'delete') { deleteReminder(r.id); return; }
            openModal(action, r);
        }

        async function deleteReminder(id) {
            await fetch(`/api/reminders/${id}`, { method: 'DELETE' });
            fetchReminders();
        }

        const COLORS = ['#fda4af', '#86efac', '#d8b4fe', '#fdba74', '#7dd3fc'];

        function openModal(action, r) {
            document.getElementById('modal-target-id').value = r.id;
            document.getElementById('modal-action-type').value = action;
            
            const title = document.getElementById('modal-title');
            const body = document.getElementById('modal-body');
            
            if(action === 'edit') {
                title.textContent = 'Edit Details';
                body.innerHTML = `<textarea id="modal-input-val" class="modal-input">${r.text.replace(/"/g, '&quot;')}</textarea>`;
                document.getElementById('action-modal').classList.add('show');
                setTimeout(() => document.getElementById('modal-input-val').focus(), 100);
            } else if (action === 'notes') {
                title.textContent = 'Add Notes';
                body.innerHTML = `<textarea id="modal-input-val" class="modal-input" placeholder="Type details here...">${r.notes || ''}</textarea>`;
                document.getElementById('action-modal').classList.add('show');
                setTimeout(() => document.getElementById('modal-input-val').focus(), 100);
            } else if (action === 'schedule') {
                title.textContent = 'Schedule Notifications';
                document.getElementById('modal-schedule-val').value = r.schedule_preset || 'none';
                body.innerHTML = `
                    <div style="font-size:14px; color:var(--muted); margin-bottom:16px;">We'll remind you based on the preset.</div>
                    <div class="preset-grid">
                        <div class="preset-card ${r.schedule_preset==='day'?'active':''}" onclick="setPreset(this, 'day')">
                            <div class="preset-name">Day</div><div class="preset-desc">3 days</div>
                        </div>
                        <div class="preset-card ${r.schedule_preset==='week'?'active':''}" onclick="setPreset(this, 'week')">
                            <div class="preset-name">Week</div><div class="preset-desc">2 weeks</div>
                        </div>
                        <div class="preset-card ${r.schedule_preset==='month'?'active':''}" onclick="setPreset(this, 'month')">
                            <div class="preset-name">Month</div><div class="preset-desc">1 month</div>
                        </div>
                    </div>
                `;
                document.getElementById('action-modal').classList.add('show');
                if (Notification.permission !== "granted") Notification.requestPermission();
            } else if (action === 'color') {
                title.textContent = 'Choose Color';
                document.getElementById('modal-color-val').value = r.color || '';
                
                let colorHtml = '<div class="color-grid">';
                colorHtml += `<div class="color-swatch color-clear ${!r.color ? 'active' : ''}" onclick="setColor(this, '')"><svg fill="none"><path d="M18 6L6 18M6 6l12 12" stroke-linecap="round"/></svg></div>`;
                COLORS.forEach(c => {
                    colorHtml += `<div class="color-swatch ${r.color === c ? 'active' : ''}" style="background: ${c}" onclick="setColor(this, '${c}')"></div>`;
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
        function closeIfOutside(e) { if(e.target.id === 'action-modal') closeModal(); }

        async function saveModal() {
            haptic([20, 30]);
            const id = document.getElementById('modal-target-id').value;
            const action = document.getElementById('modal-action-type').value;
            
            const payload = { updated_at: getTimestamp() };
            if(action === 'edit') payload.text = document.getElementById('modal-input-val').value;
            if(action === 'notes') payload.notes = document.getElementById('modal-input-val').value;
            if(action === 'schedule') {
                payload.schedule_preset = document.getElementById('modal-schedule-val').value;
                payload.schedule_start = Date.now();
                payload.notifications_sent = 0;
            }
            if(action === 'color') payload.color = document.getElementById('modal-color-val').value;

            await fetch(`/api/reminders/${id}`, {
                method: 'PUT', headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(payload)
            });

            closeModal();
            fetchReminders();
        }

        setInterval(async () => {
            if(Notification.permission !== 'granted') return;
            const now = Date.now();
            for (let r of remindersData) {
                if (r.completed || !r.schedule_preset || r.schedule_preset === 'none') continue;
                let targetCount = 0, msInterval = 0;
                if (r.schedule_preset === 'day') { targetCount = 3; msInterval = 24 * 60 * 60 * 1000; } 
                else if (r.schedule_preset === 'week') { targetCount = 14; msInterval = 24 * 60 * 60 * 1000; } 
                else if (r.schedule_preset === 'month') { targetCount = 15; msInterval = 48 * 60 * 60 * 1000; }
                
                if (r.notifications_sent < targetCount) {
                    const nextTrigger = r.schedule_start + (r.notifications_sent * msInterval);
                    if (now >= nextTrigger) {
                        new Notification("bamboo.", { body: r.text, icon: "https://cdn-icons-png.flaticon.com/512/3221/3221845.png" });
                        r.notifications_sent++;
                        await fetch(`/api/reminders/${r.id}`, {
                            method: 'PUT', headers: {'Content-Type': 'application/json'},
                            body: JSON.stringify({notifications_sent: r.notifications_sent})
                        });
                    }
                }
            }
        }, 60000);

        fetchReminders();
    </script>
</body>
</html>
"""

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
