import os
import time
import re
import mysql.connector
from flask import Flask, render_template, request, redirect, url_for, session, flash

app = Flask(__name__)
app.secret_key = 'cirrms_secret_key_secure_barangay'

def get_db_connection():
    return mysql.connector.connect(
        host=os.environ.get('DB_HOST', 'sql.freedb.tech'),
        user=os.environ.get('DB_USER', 'u_G5ctnQ'),
        password=os.environ.get('DB_PASSWORD', 'ySrGeMfiQ7Sa'),
        database=os.environ.get('DB_NAME', 'freedb_SlzV8ViE'),
        port=int(os.environ.get('DB_PORT', 3306))
    )

INAPPROPRIATE_WORDS = [
    'fuck', 'shit', 'bitch', 'asshole', 'bastard', 'crap', 'dick', 'pussy', 'cunt', 'slut', 'whore', 'idiot', 'stupid',
    'bobo', 'tanga', 'gago', 'tarantado', 'ulol', 'putangina', 'pukingina', 'tangina', 'bwisit', 
    'leche', 'puta', 'kantot', 'kupal', 'bayag', 'tae', 'inutil', 'hayop', 'puki', 'titi', 'tamod'
]

def contains_profanity(text):
    text_lower = text.lower()
    return any(word in text_lower for word in INAPPROPRIATE_WORDS)

def is_spam(text):
    if re.search(r'(.)\1{4,}', text):
        return True
    return False

@app.route('/', methods=['GET', 'POST'])
def home():
    if session.get('admin_logged_in'):
        return redirect(url_for('admin_dashboard'))

    if request.method == 'POST':
        name = request.form['resident_name'].strip()
        contact = request.form['contact_number'].strip()
        incident_type = request.form['incident_type']
        location = request.form['location'].strip()
        description = request.form['description'].strip()
        last_submission = session.get('last_submission_time', 0)

        if time.time() - last_submission < 15:
            flash('Spam protection alert: Please wait 15 seconds before submitting another incident report.', 'error')
            return redirect(url_for('home'))

        if not re.match(r'^[A-Za-z\s]+$', name):
            flash('Full Name can only contain letters and spaces (no numbers or symbols).', 'error')
            return redirect(url_for('home'))

        if not re.match(r'^\d{11}$', contact):
            flash('Contact Number must be exactly 11 numeric digits (no letters).', 'error')
            return redirect(url_for('home'))

        if len(description) < 10:
            flash('Incident description is too short. Please provide at least 10 characters of detail.', 'error')
            return redirect(url_for('home'))

        if is_spam(name) or is_spam(location) or is_spam(description):
            flash('Submission rejected: Repetitive character patterns or spam detected.', 'error')
            return redirect(url_for('home'))

        if contains_profanity(name) or contains_profanity(location) or contains_profanity(description):
            flash('Submission rejected: Inappropriate or offensive language detected.', 'error')
            return redirect(url_for('home'))
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO incidents (resident_name, contact_number, incident_type, location, description)
            VALUES (%s, %s, %s, %s, %s)
        """, (name, contact, incident_type, location, description))
        conn.commit()
        cursor.close()
        conn.close()

        session['last_submission_time'] = time.time()
        flash('Incident report submitted successfully to Barangay Ilayang Butnong!', 'success')
        return redirect(url_for('home'))

    return render_template('index.html')

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if session.get('admin_logged_in'):
        return redirect(url_for('admin_dashboard'))

    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password'].strip()

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM admins WHERE username = %s AND password = %s", (username, password))
        admin = cursor.fetchone()
        cursor.close()
        conn.close()

        if admin:
            session['admin_logged_in'] = True
            session['admin_username'] = admin['username']
            flash('Welcome back, Barangay Official!', 'success')
            return redirect(url_for('admin_dashboard'))
        else:
            flash('Invalid username or password. Please try again.', 'error')
            return redirect(url_for('admin_login'))

    return render_template('login.html')


@app.route('/admin/logout')
def admin_logout():
    session.clear()
    flash('Logged out successfully.', 'info')
    return redirect(url_for('admin_login'))

@app.route('/admin/dashboard')
def admin_dashboard():
    if not session.get('admin_logged_in'):
        flash('Access denied. Please log in as an administrator.', 'error')
        return redirect(url_for('admin_login'))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM incidents ORDER BY created_at DESC")
    incidents = cursor.fetchall()
    cursor.close()
    conn.close()

    return render_template('dashboard.html', incidents=incidents)


@app.route('/admin/incident/update/<int:id>', methods=['POST'])
def update_incident(id):
    if not session.get('admin_logged_in'):
        flash('Access denied.', 'error')
        return redirect(url_for('admin_login'))

    new_priority = request.form.get('priority')
    new_status = request.form.get('status')
    action_taken = request.form.get('action_taken')
    admin_user = session.get('admin_username', 'admin')

    conn = get_db_connection()
    cursor = conn.cursor(buffered=True, dictionary=True)

    cursor.execute("SELECT status FROM incidents WHERE id = %s", (id,))
    current_record = cursor.fetchone()
    
    if current_record and current_record['status'] == 'Resolved':
        cursor.close()
        conn.close()
        flash('Error: This incident record is permanently locked and cannot be modified.', 'error')
        return redirect(url_for('admin_dashboard'))

    cursor.execute("""
        UPDATE incidents 
        SET priority = %s, status = %s, action_taken = %s 
        WHERE id = %s
    """, (new_priority, new_status, action_taken, id))

    cursor.execute("SELECT id FROM incident_logs WHERE incident_id = %s", (id,))
    existing_log = cursor.fetchone()

    if existing_log:
        cursor.execute("""
            UPDATE incident_logs 
            SET action_taken = %s, status_updated_to = %s, admin_user = %s, timestamp = CURRENT_TIMESTAMP
            WHERE incident_id = %s
        """, (action_taken, new_status, admin_user, id))
    else:
        cursor.execute("""
            INSERT INTO incident_logs (incident_id, action_taken, status_updated_to, admin_user)
            VALUES (%s, %s, %s, %s)
        """, (id, action_taken, new_status, admin_user))

    conn.commit()
    cursor.close()
    conn.close()

    flash(f'Incident #INC-{id:04d} updated and recorded in audit logs successfully.', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/logs')
def admin_logs():
    if not session.get('admin_logged_in'):
        flash('Access denied.', 'error')
        return redirect(url_for('admin_login'))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT incident_logs.*, incidents.resident_name, incidents.incident_type 
        FROM incident_logs
        JOIN incidents ON incident_logs.incident_id = incidents.id
        ORDER BY incident_logs.timestamp DESC
    """)
    logs = cursor.fetchall()
    cursor.close()
    conn.close()

    return render_template('logs.html', logs=logs)

@app.route('/api/unread_count')
def unread_count():
    if not session.get('admin_logged_in'):
        return {'unread_count': 0}

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT COUNT(*) AS count FROM incidents WHERE status = 'Pending'")
    result = cursor.fetchone()
    cursor.close()
    conn.close()

    return {'unread_count': result['count'] if result else 0}

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)