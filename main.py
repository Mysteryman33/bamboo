import os
from datetime import datetime
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

db_url = os.environ.get('DATABASE_URL', 'sqlite:///bamboo.db')
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# ── DATABASE MODELS ──────────────────────────────────────────────────────────

class Reminder(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    text = db.Column(db.String(500), nullable=False)
    completed = db.Column(db.Boolean, default=False)
    notes = db.Column(db.String(2000), default="")
    updated_at = db.Column(db.String(100), default="")
    created_timestamp = db.Column(db.Float, default=0.0)
    completed_date = db.Column(db.String(20), default="")
    due_timestamp = db.Column(db.Float, default=0.0)
    due_label = db.Column(db.String(200), default="")

with app.app_context():
    db.create_all()

# ── HELPERS ──────────────────────────────────────────────────────────────────

def r_to_dict(r):
    return {
        "id": r.id,
        "text": r.text,
        "completed": r.completed,
        "notes": r.notes or "",
        "updated_at": r.updated_at or "",
        "created_timestamp": r.created_timestamp or 0.0,
        "completed_date": r.completed_date or "",
        "due_timestamp": r.due_timestamp or 0.0,
        "due_label": r.due_label or "",
    }

def clean_text(text):
    """Remove extra whitespace from text"""
    import re
    return re.sub(r"\s+", " ", str(text or "").strip())

# ── ROUTES ───────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/reminders', methods=['GET', 'POST'])
def handle_reminders():
    if request.method == 'POST':
        data = request.json or {}
        text = clean_text(data.get('text', ''))
        
        if not text:
            return jsonify({"error": "text is required"}), 400
        
        new_r = Reminder(
            text=text,
            updated_at=data.get('updated_at', ''),
            created_timestamp=data.get('created_timestamp', 0.0),
            completed_date=data.get('completed_date', ''),
            due_timestamp=data.get('due_timestamp', 0.0),
            due_label=data.get('due_label', ''),
            notes=data.get('notes', ''),
        )
        db.session.add(new_r)
        db.session.commit()
        return jsonify(r_to_dict(new_r)), 201
    
    # GET all reminders
    rems = Reminder.query.all()
    return jsonify([r_to_dict(r) for r in rems])

@app.route('/api/reminders/<int:rid>', methods=['PUT', 'DELETE'])
def handle_reminder(rid):
    r = Reminder.query.get_or_404(rid)
    
    if request.method == 'PUT':
        data = request.json or {}
        
        # Update text if provided
        if 'text' in data:
            r.text = clean_text(data['text'])
        
        # Update other fields
        if 'completed' in data:
            r.completed = bool(data['completed'])
        if 'notes' in data:
            r.notes = data['notes']
        if 'updated_at' in data:
            r.updated_at = data['updated_at']
        if 'completed_date' in data:
            r.completed_date = data['completed_date']
        if 'due_timestamp' in data:
            r.due_timestamp = data['due_timestamp']
        if 'due_label' in data:
            r.due_label = data['due_label']
        
        db.session.commit()
        return jsonify(r_to_dict(r))
    
    # DELETE
    db.session.delete(r)
    db.session.commit()
    return '', 204

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=4000, debug=True, use_reloader=False)
