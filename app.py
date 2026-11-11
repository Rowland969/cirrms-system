import os
import time
import re
import random
import urllib.request
import json
import datetime
import mysql.connector
from flask import Flask, render_template, request, redirect, url_for, session, flash

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY') or 'cirrms_secret_key_secure_barangay'

def get_db_connection():
    return mysql.connector.connect(
        host=os.environ.get('DB_HOST', 'localhost'),
        user=os.environ.get('DB_USER', 'root'),
        password=os.environ.get('DB_PASSWORD', ''),
        database=os.environ.get('DB_NAME', 'cirrms_db'),
        port=int(os.environ.get('DB_PORT', 3306))
    )

def send_verification_email(recipient_email, verify_link):
    api_key = os.environ.get('BREVO_API_KEY')
    sender_email = os.environ.get('SENDER_EMAIL', 'calapisrowland2005@gmail.com')
    
    if not api_key:
        print("WARNING: BREVO_API_KEY not set in environment variables.")
        return False

    url = "https://api.brevo.com/v3/smtp/email"
    
    payload = {
        "sender": {"name": "CIRRMS System", "email": sender_email},
        "to": [{"email": recipient_email}],
        "subject": "CIRRMS Admin Portal - One-Tap Login Verification",
        "htmlContent": f"""
            <div style="font-family: Arial, sans-serif; padding: 20px; background-color: #f4f6f5; border-radius: 8px;">
                <h2 style="color: #1b4332;">Barangay Official Login</h2>
                <p>Hello, you requested access to the CIRRMS Admin Portal.</p>
                <p>Click the button below to instantly verify your identity and log in:</p>
                <a href="{verify_link}" style="display: inline-block; padding: 12px 24px; background-color: #1b4332; color: white; text-decoration: none; border-radius: 6px; font-weight: bold; margin-top: 10px;">Verify & Log In</a>
                <p style="margin-top: 25px; color: #666; font-size: 0.9rem;">If you did not request this, please ignore this email.</p>
            </div>
        """
    }

    try:
        req = urllib.request.Request(
            url, 
            data=json.dumps(payload).encode('utf-8'),
            headers={
                "accept": "application/json",
                "api-key": api_key,
                "content-type": "application/json"
            },
            method="POST"
        )
        
        with urllib.request.urlopen(req) as response:
            return response.status == 201
    except Exception as e:
        print(f"Error sending email via Brevo API: {str(e)}")
        return False

INAPPROPRIATE_WORDS = [
    'fuck', 'shit', 'bitch', 'asshole', 'bastard', 'crap', 'dick', 'pussy', 'cunt', 'slut', 'whore', 'idiot', 'stupid',
    'bobo', 'tanga', 'gago', 'tarantado', 'ulol', 'putangina', 'pukingina', 'tangina', 'bwisit', 
    'leche', 'puta', 'kantot', 'kupal', 'bayag', 'tae', 'inutil', 'hayop', 'puki', 'titi', 'tamod'
]

def contains_profanity(text):
    return any(word in text.lower() for word in INAPPROPRIATE_WORDS)

def is_spam(text):
    return bool(re.search(r'(.)\1{4,}', text))

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
            flash('Full Name can only contain letters and spaces.', 'error')
            return redirect(url_for('home'))

        if not re.match(r'^\d{11}$', contact):
            flash('Contact Number must be exactly 11 numeric digits.', 'error')
            return redirect(url_for('home'))

        if len(description) < 10:
            flash('Incident description is too short (at least 10 characters required).', 'error')
            return redirect(url_for('home'))

        if is_spam(name) or is_spam(location) or is_spam(description) or contains_profanity(description):
            flash('Submission rejected due to content policy filters.', 'error')
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
        flash('Incident report submitted successfully!', 'success')
        return redirect(url_for('home'))

    return render_template('index.html')

@app.route('/admin/login/reset')
def reset_login():
    session.pop('pending_admin', None)
    return redirect(url_for('admin_login'))

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

        if admin:
            verify_token = f"{random.randint(10000000, 99999999)}"
            expiry_time = datetime.datetime.now() + datetime.timedelta(minutes=15)
            
            cursor.execute("""
                UPDATE admins SET verify_token = %s, token_expiry = %s WHERE username = %s
            """, (verify_token, expiry_time, admin['username']))
            conn.commit()
            cursor.close()
            conn.close()

            session['pending_admin'] = admin['username']
            
            verify_link = url_for('verify_tap', username=admin['username'], token=verify_token, _external=True)
            recipient_email = admin.get('email') if admin and admin.get('email') else os.environ.get('SENDER_EMAIL', 'calapisrowland2005@gmail.com')
            
            email_sent = send_verification_email(recipient_email, verify_link)
            
            if email_sent:
                flash('Credentials confirmed! Check your email and click the verification link to log in instantly.', 'success')
            else:
                flash('Failed to send verification email. Check Brevo API settings.', 'error')
        else:
            cursor.close()
            conn.close()
            flash('Invalid username or password.', 'error')
            
        return redirect(url_for('admin_login'))

    return render_template('login.html', awaiting_verification=bool(session.get('pending_admin')))

@app.route('/admin/verify/<token>')
def verify_tap(token):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM admins WHERE verify_token = %s AND token_expiry > UTC_TIMESTAMP()", (token,))
    admin = cursor.fetchone()
    
    if admin:
        cursor.execute("UPDATE admins SET verify_token = NULL, token_expiry = NULL WHERE id = %s", (admin['id'],))
        conn.commit()
        
        session['admin_logged_in'] = True
        session['admin_username'] = admin['username']
        
        cursor.close()
        conn.close()
        
        flash('Verification successful! Welcome to the portal.', 'success')
        return redirect(url_for('admin_dashboard'))
    
    cursor.close()
    conn.close()
    flash('Invalid or expired verification link.', 'error')
    return redirect(url_for('admin_login'))

@app.route('/admin/logout')
def admin_logout():
    session.clear()
    flash('Logged out successfully.', 'info')
    return redirect(url_for('admin_login'))

@app.route('/admin/dashboard')
def admin_dashboard():
    if not session.get('admin_logged_in'):
        flash('Access denied. Please log in.', 'error')
        return redirect(url_for('admin_login'))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT * FROM incidents WHERE status != 'Resolved' ORDER BY id DESC")
        incidents = cursor.fetchall()
    except Exception as e:
        print(f"Database Error on Dashboard: {e}")
        flash(f"Database error loading dashboard: {e}", 'error')
        incidents = []
    finally:
        cursor.close()
        conn.close()

    return render_template('dashboard.html', incidents=incidents)

@app.route('/admin/incident/update/<int:id>', methods=['POST'])
def update_incident(id):
    if not session.get('admin_logged_in'):
        flash('Access denied. Please log in.', 'error')
        return redirect(url_for('admin_login'))

    priority = request.form.get('priority')
    status = request.form.get('status')
    action_taken = request.form.get('action_taken')

    admin_username = session.get('admin_username') or session.get('username') or 'admin'

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        cursor.execute("SELECT * FROM incidents WHERE id = %s", (id,))
        incident = cursor.fetchone()
        
        if not incident:
            flash(f'Incident #INC-{id:04d} not found or already deleted.', 'error')
            return redirect(url_for('admin_dashboard'))

        cursor.execute("""
            UPDATE incidents 
            SET priority = %s, status = %s, action_taken = %s 
            WHERE id = %s
        """, (priority, status, action_taken, id))

        if status == 'Resolved':
            cursor.execute("""
                INSERT INTO incident_logs (incident_id, resident_name, incident_type, location, status_updated_to, action_taken, admin_username)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (
                id, 
                incident['resident_name'], 
                incident['incident_type'], 
                incident['location'], 
                status, 
                action_taken, 
                admin_username
            ))
            flash(f'Incident #INC-{id:04d} resolved and logged!', 'success')
        else:
            flash(f'Incident #INC-{id:04d} updated successfully!', 'success')

        conn.commit()
        
    except Exception as e:
        conn.rollback()
        print(f"Database Error on Update: {e}")
        flash('An internal error occurred while updating the incident.', 'error')
        
    finally:
        cursor.close()
        conn.close()

    return redirect(url_for('admin_dashboard'))

@app.route('/admin/incident/delete/<int:id>', methods=['POST'])
def delete_incident(id):
    if not session.get('admin_logged_in'):
        flash('Access denied.', 'error')
        return redirect(url_for('admin_login'))

    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(buffered=True)
        

        cursor.execute("DELETE FROM incident_logs WHERE incident_id = %s", (id,))      
        cursor.execute("DELETE FROM incidents WHERE id = %s", (id,))
        conn.commit()
        
        flash(f'Incident #INC-{id:04d} has been permanently removed.', 'success')
    except Exception as e:
        if conn:
            conn.rollback()
        print(f"Error deleting incident: {str(e)}")
        flash(f'Error deleting incident: {str(e)}', 'error')
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

    return redirect(url_for('admin_dashboard'))

@app.route('/admin/logs')
def admin_logs():
    if not session.get('admin_logged_in'):
        flash('Access denied. Please log in.', 'error')
        return redirect(url_for('admin_login'))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT * FROM incident_logs ORDER BY timestamp DESC")
        logs = cursor.fetchall()
    except Exception as e:
        print(f"Error loading logs: {e}")
        flash(f"Database error loading logs: {e}", 'error')
        logs = []
    finally:
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