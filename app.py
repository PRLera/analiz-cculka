# -*- coding: utf-8 -*-
from flask import Flask, render_template, request, flash, redirect, url_for, send_from_directory, session
import os
import sqlite3
import json  # === ВАЖНО: для работы с JSON ===
from datetime import datetime
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from basket_analyzer import analyze_uploaded_csv

app = Flask(__name__)
app.secret_key = 'lab_unified_key_2024'

UPLOAD_FOLDER = 'uploads'
REPORTS_FOLDER = 'reports'
DB_PATH = 'app_data.db'

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['REPORTS_FOLDER'] = REPORTS_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(REPORTS_FOLDER, exist_ok=True)


# ============================================
# БАЗА ДАННЫХ
# ============================================
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users 
                 (username TEXT PRIMARY KEY, password_hash TEXT, name TEXT, email TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS history 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT, date TEXT, filename TEXT, pairs_count INTEGER, report_filename TEXT)''')
    admin_user = ('admin', generate_password_hash('admin123'), 'Администратор', 'admin@site.com')
    c.execute('INSERT OR IGNORE INTO users VALUES (?, ?, ?, ?)', admin_user)
    conn.commit()
    conn.close()


def save_history(username, filename, pairs_count, report_filename):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    date_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    c.execute('INSERT INTO history (username, date, filename, pairs_count, report_filename) VALUES (?, ?, ?, ?, ?)',
              (username, date_str, filename, pairs_count, report_filename))
    conn.commit()
    conn.close()


def get_history(username):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute('SELECT date, filename, pairs_count, report_filename FROM history WHERE username = ? ORDER BY date DESC',
              (username,))
    rows = c.fetchall()
    conn.close()
    return [
        {'date': r['date'], 'file': r['filename'], 'pairs': r['pairs_count'], 'report_filename': r['report_filename']}
        for r in rows]


init_db()


# ============================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ============================================
def count_file_lines(filepath):
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return sum(1 for _ in f)
    except Exception as e:
        raise RuntimeError(f"Не удалось прочитать файл: {e}")


# ============================================
# МАРШРУТЫ
# ============================================

@app.route('/', methods=['GET', 'POST'])
def index():
    is_auth = 'username' in session
    user_info = {'name': session.get('name'), 'username': session.get('username')} if is_auth else None

    # По умолчанию данных нет
    result_data = {'filename': '', 'lines': 0, 'analysis': None}

    # === ВОССТАНОВЛЕНИЕ: Если есть сохраненный отчет в сессии ===
    if request.method == 'GET' and session.get('pending_analysis'):
        p = session['pending_analysis']
        report_path = os.path.join(app.config['REPORTS_FOLDER'], p['report_filename'])
        if os.path.exists(report_path):
            try:
                with open(report_path, 'r', encoding='utf-8') as f:
                    analysis = json.load(f)
                result_data = {
                    'filename': p['filename'],
                    'lines': p['lines'],
                    'analysis': analysis
                }
                result_data['analysis']['total_pairs_count'] = p['pairs_count']
                result_data['analysis']['report_filename'] = p['report_filename']
            except Exception:
                pass

    # === ОБРАБОТКА ЗАГРУЗКИ НОВОГО ФАЙЛА ===
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('Файл не выбран', 'error')
            return redirect(request.url)

        file = request.files['file']
        if file.filename == '':
            flash('Файл не выбран', 'error')
            return redirect(request.url)

        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)

        try:
            lines = count_file_lines(filepath)

            if filename.lower().endswith('.csv'):
                report_name = f"{os.path.splitext(filename)[0]}_report.json"
                report_path = os.path.join(app.config['REPORTS_FOLDER'], report_name)
                analysis = analyze_uploaded_csv(filepath, report_path)

                if 'error' not in analysis:
                    total_pairs = len(analysis.get('all_pairs', []))
                    result_data = {
                        'filename': filename,
                        'lines': lines,
                        'analysis': analysis
                    }
                    result_data['analysis']['total_pairs_count'] = total_pairs
                    result_data['analysis']['report_filename'] = report_name

                    flash('Файл загружен, анализ выполнен!', 'success')

                    # === СОХРАНЯЕМ СОСТОЯНИЕ В СЕССИЮ ===
                    session['pending_analysis'] = {
                        'filename': filename,
                        'lines': lines,
                        'pairs_count': total_pairs,
                        'report_filename': report_name
                    }

                    # Если пользователь авторизован -> сохраняем в историю сразу
                    if is_auth:
                        save_history(session['username'], filename, total_pairs, report_name)
                        session.pop('pending_analysis', None)
                else:
                    flash(f'Анализ пар: {analysis["error"]}', 'warning')
            else:
                flash('Строки подсчитаны. Анализ пар доступен только для CSV', 'info')
        except Exception as e:
            flash(f'Ошибка обработки: {str(e)}', 'error')
        finally:
            if os.path.exists(filepath):
                os.remove(filepath)

    return render_template('index.html', result=result_data, is_auth=is_auth, user_info=user_info)


@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'username' in session:
        return redirect(url_for('profile'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        conn.close()

        if user and check_password_hash(user['password_hash'], password):
            session['username'] = user['username']
            session['name'] = user['name']
            session['email'] = user['email']

            # === СОХРАНЕНИЕ ПРЕДЫДУЩЕГО АНАЛИЗА ПОСЛЕ ВХОДА ===
            if session.get('pending_analysis'):
                p = session['pending_analysis']
                save_history(session['username'], p['filename'], p['pairs_count'], p['report_filename'])
                flash('Предыдущий анализ сохранен в вашу историю!', 'info')
                session.pop('pending_analysis', None)

            flash('Вход выполнен успешно!', 'success')
            return redirect(url_for('profile'))
        else:
            flash('Неверный логин или пароль', 'error')

    return render_template('login.html')


@app.route('/register', methods=['POST'])
def register():
    username = request.form.get('username', '').strip()
    password = request.form.get('password', '')
    name = request.form.get('name', '').strip()
    email = request.form.get('email', '').strip()

    if not username or not password:
        flash('Заполните логин и пароль', 'error')
        return redirect(url_for('login'))

    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute('INSERT INTO users (username, password_hash, name, email) VALUES (?, ?, ?, ?)',
                     (username, generate_password_hash(password), name or username, email))
        conn.commit()
        flash('Регистрация успешна! Теперь войдите.', 'success')
    except sqlite3.IntegrityError:
        flash('Такой пользователь уже существует', 'error')
    finally:
        conn.close()

    return redirect(url_for('login'))


@app.route('/profile')
def profile():
    if 'username' not in session:
        flash('Пожалуйста, войдите в систему', 'warning')
        return redirect(url_for('login'))

    history = get_history(session['username'])
    return render_template('profile.html',
                           name=session['name'],
                           username=session['username'],
                           email=session['email'],
                           history=history)


@app.route('/logout')
def logout():
    session.clear()
    flash('Вы вышли из системы', 'info')
    return redirect(url_for('index'))


@app.route('/download/<filename>')
def download_report(filename):
    return send_from_directory(app.config['REPORTS_FOLDER'], filename, as_attachment=True)


@app.route('/download_all/<filename>')
def download_all_report(filename):
    return send_from_directory(app.config['REPORTS_FOLDER'], filename, as_attachment=True)


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)