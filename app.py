import re
import time
from flask import Flask, render_template, request, redirect, url_for, session, flash
import mysql.connector

app = Flask(__name__, template_folder='cirrms-system/templates', static_folder='cirrms-system/static')
app.secret_key = 'ilayang_butnong_secret_key'

db_config = {
    'host': 'localhost',
    'user': 'root',
    'password': 'mosquito17',
    'database': 'cirrms_db'
}

def get_db_connection():
    return mysql.connector.connect(**db_config)

INAPPROPRIATE_WORDS = [
    'fuck', 'shit', 'bitch', 'asshole', 'bastard', 'crap', 'dick', 'pussy', 'cunt', 'slut', 'whore', 'idiot', 'stupid',
    'bobo', 'tanga', 'gago', 'tarantado', 'ulol', 'putangina', 'pukingina', 'tangina', 'bwisit', 
    'leche', 'puta', 'kantot', 'kupal', 'bayag', 'tae', 'inutil', 'hayop', 'puki', 'titi', 'tamod'
]

def contains_profanity(text):
    normalized = re.sub(r'[^\w\s]', '', text.lower())
    words = normalized.split()
    for word in words:
        if word in INAPPROPRIATE_WORDS:
            return True
    for bad_word in INAPPROPRIATE_WORDS:
        if bad_word in normalized:
            return True
    return False

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

        # Save to Database
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
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM admins WHERE username = %s AND password = %s", (username, password))
        admin = cursor.fetchone()
        cursor.close()
        conn.close()

        if admin:
            session['admin_logged_in'] = True
            session['admin_username'] = admin['username']
            return redirect(url_for('admin_dashboard'))
        else:
            flash('Invalid admin credentials.', 'error')

    return render_template('login.html')

@app.route('/admin/dashboard')
def admin_dashboard():
    if not session.get('admin_logged_in'):
        flash('Please login to access the admin dashboard.', 'error')
        return redirect(url_for('admin_login'))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM incidents ORDER BY created_at DESC")
    incidents = cursor.fetchall()
    cursor.close()
    conn.close()

    return render_template('dashboard.html', incidents=incidents)

@app.route('/admin/logs')
def admin_logs():
    if not session.get('admin_logged_in'):
        flash('Please login to access the admin logs.', 'error')
        return redirect(url_for('admin_login'))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT logs.id AS log_id, logs.incident_id, logs.admin_username, 
               logs.action_taken, logs.status_updated, logs.logged_at,
               incidents.resident_name, incidents.incident_type, incidents.location
        FROM incident_logs logs
        JOIN incidents ON logs.incident_id = incidents.id
        ORDER BY logs.logged_at DESC
    """)
    logs = cursor.fetchall()
    cursor.close()
    conn.close()

    return render_template('logs.html', logs=logs)

@app.route('/admin/update_incident/<int:id>', methods=['POST'])
def update_incident(id):
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True, buffered=True)

    cursor.execute("SELECT status FROM incidents WHERE id = %s", (id,))
    existing_incident = cursor.fetchone()

    if existing_incident and existing_incident['status'] == 'Resolved':
        cursor.close()
        conn.close()
        flash(f'Incident #INC-{"%04d" % id} is already Resolved and cannot be modified.', 'error')
        return redirect(url_for('admin_dashboard'))

    status = request.form['status']
    priority = request.form['priority']
    action_taken = request.form['action_taken']
    admin_username = session.get('admin_username', 'admin')

    cursor.execute("""
        UPDATE incidents 
        SET status = %s, priority = %s, action_taken = %s 
        WHERE id = %s
    """, (status, priority, action_taken, id))

    cursor.execute("SELECT id FROM incident_logs WHERE incident_id = %s", (id,))
    existing_log = cursor.fetchone()

    if existing_log:
        cursor.execute("""
            UPDATE incident_logs 
            SET admin_username = %s, action_taken = %s, status_updated = %s, logged_at = CURRENT_TIMESTAMP
            WHERE incident_id = %s
        """, (admin_username, action_taken, status, id))
    else:
        cursor.execute("""
            INSERT INTO incident_logs (incident_id, admin_username, action_taken, status_updated)
            VALUES (%s, %s, %s, %s)
        """, (id, admin_username, action_taken, status))

    conn.commit()
    cursor.close()
    conn.close()

    if status == 'Resolved':
        flash(f'Incident #INC-{"%04d" % id} marked as Resolved and is now permanently locked.', 'success')
    else:
        flash(f'Incident #INC-{"%04d" % id} updated successfully.', 'success')

    return redirect(url_for('admin_dashboard'))

@app.route('/admin/logout')
def admin_logout():
    session.clear()
    flash('Logged out successfully.', 'info')
    return redirect(url_for('admin_login'))

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

import os

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)