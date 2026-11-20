import os
import json
import sqlite3
import threading
import time
import base64
import traceback
import re
import uuid
import io
import smtplib
import secrets
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import timedelta, datetime
from functools import wraps
from flask import Flask, render_template_string, request, jsonify, session, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash
from groq import Groq

try:
    import requests
except ImportError:
    requests = None

try:
    import pyotp
    import qrcode
    from qrcode import base64 as qr_base64
except ImportError:
    pyotp = None
    qrcode = None
    print("[UYARI] pyotp / qrcode yüklü değil. pip install pyotp qrcode[pil]")

try:
    import pypdf
except ImportError:
    pypdf = None
    print("[UYARI] pypdf yüklü değil. pip install pypdf")

try:
    import docx
except ImportError:
    docx = None
    print("[UYARI] python-docx yüklü değil. pip install python-docx")

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    print("[UYARI] python-dotenv yüklü değil. pip install python-dotenv")

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "crsz-bot-studio-super-secret-key-2026-change-me")
app.permanent_session_lifetime = timedelta(days=7)
app.config['MAX_CONTENT_LENGTH'] = 200 * 1024 * 1024

app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
MUSIC_DIR = os.path.join(UPLOAD_DIR, "music")
BG_DIR = os.path.join(UPLOAD_DIR, "background")
AVATAR_DIR = os.path.join(UPLOAD_DIR, "avatars")
DOC_DIR = os.path.join(UPLOAD_DIR, "documents")
STATIC_DIR = os.path.join(BASE_DIR, "static")
DB_FILE = os.path.join(BASE_DIR, "crszbot.db")

for d in [MUSIC_DIR, BG_DIR, AVATAR_DIR, DOC_DIR, STATIC_DIR]:
    os.makedirs(d, exist_ok=True)

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
if not GROQ_API_KEY:
    print("[UYARI] GROQ_API_KEY bulunamadı!")
client = Groq(api_key=GROQ_API_KEY)

SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")
BASE_URL = os.getenv("BASE_URL", "http://localhost:5000")


RATE_LIMIT_STORE = {}
RATE_LIMIT_LOCK = threading.Lock()

def rate_limit(max_calls=30, window_seconds=60):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            ip = request.remote_addr or "unknown"
            key = f"{f.__name__}:{ip}"
            now = time.time()
            with RATE_LIMIT_LOCK:
                calls = RATE_LIMIT_STORE.get(key, [])
                calls = [t for t in calls if now - t < window_seconds]
                if len(calls) >= max_calls:
                    return jsonify({"status": "error", "message": f"Çok fazla istek. {window_seconds} saniye bekle."}), 429
                calls.append(now)
                RATE_LIMIT_STORE[key] = calls
            return f(*args, **kwargs)
        return wrapper
    return decorator


SUPPORTED_LANGUAGES = {
    "tr": "Türkçe", "en": "English", "de": "Deutsch", "fr": "Français",
    "es": "Español", "ar": "العربية", "ru": "Русский", "it": "Italiano",
    "pt": "Português", "nl": "Nederlands",
}


# ============ E-POSTA GÖNDERME ============
def send_email(to_email, subject, body_html):
    """SMTP ile e-posta gönder"""
    if not SMTP_USER or not SMTP_PASS:
        print("[MAIL] SMTP ayarları yok, e-posta gönderilemedi.")
        return False
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = SMTP_USER
        msg["To"] = to_email
        msg.attach(MIMEText(body_html, "html"))
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(SMTP_USER, to_email, msg.as_string())
        print(f"[MAIL] Gönderildi: {to_email}")
        return True
    except Exception as e:
        print(f"[MAIL HATA] {e}")
        return False


def send_reset_email(to_email, username, token):
    reset_link = f"{BASE_URL}/reset-password?token={token}"
    html = f"""
    <div style="font-family: Inter, Arial, sans-serif; max-width: 500px; margin: 0 auto; padding: 30px; background: #07070a; color: #fff; border-radius: 16px;">
        <h2 style="background: linear-gradient(135deg, #3B82F6, #8B5CF6); -webkit-background-clip: text; -webkit-text-fill-color: transparent;">
            Crsz Bot Studio
        </h2>
        <p>Merhaba <b>{username}</b>,</p>
        <p>Şifre sıfırlama talebinde bulundun. Aşağıdaki butona tıklayarak yeni şifreni belirleyebilirsin:</p>
        <a href="{reset_link}" style="display: inline-block; padding: 12px 24px; background: linear-gradient(135deg, #3B82F6, #8B5CF6); color: #fff; text-decoration: none; border-radius: 10px; font-weight: 600; margin: 20px 0;">
            Şifremi Sıfırla
        </a>
        <p style="color: #94A3B8; font-size: 12px;">Bu link 1 saat geçerlidir. Eğer bu isteği sen yapmadıysan görmezden gel.</p>
        <p style="color: #64748B; font-size: 11px;">Link çalışmıyorsa: {reset_link}</p>
    </div>
    """
    return send_email(to_email, "Crsz Bot — Şifre Sıfırlama", html)


# ============ DB ============
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
    c.execute("""CREATE TABLE IF NOT EXISTS music (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        filename TEXT, original_name TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE, email TEXT, password TEXT, avatar TEXT,
        language TEXT DEFAULT 'tr',
        is_admin INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS chats (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT, title TEXT, messages TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS bot_memory (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT, role TEXT, content TEXT, image_data TEXT,
        language TEXT DEFAULT 'tr',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    # ============ YENİ TABLOLAR ============
    c.execute("""CREATE TABLE IF NOT EXISTS password_resets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT, token TEXT UNIQUE,
        expires_at TIMESTAMP, used INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS two_factor (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE, secret TEXT, enabled INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS bans (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ip TEXT UNIQUE, reason TEXT,
        banned_by TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS notifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT, title TEXT, message TEXT,
        is_read INTEGER DEFAULT 0, kind TEXT DEFAULT 'info',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS documents (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT, filename TEXT, original_name TEXT,
        text_content TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    conn.commit()

    def column_exists(table, column):
        try:
            c.execute(f"PRAGMA table_info({table})")
            cols = [row[1] for row in c.fetchall()]
            return column in cols
        except Exception:
            return False

    for col, coltype, default in [
        ("language", "TEXT", "'tr'"),
        ("is_admin", "INTEGER", "0"),
        ("avatar", "TEXT", "NULL"),
        ("email", "TEXT", "NULL"),
    ]:
        if not column_exists("users", col):
            try:
                c.execute(f"ALTER TABLE users ADD COLUMN {col} {coltype} DEFAULT {default}")
                conn.commit()
                print(f"[DB MIGRATION] users.{col} eklendi.")
            except Exception as e:
                print(f"[DB MIGRATION HATA] {col}: {e}")

    # Eski görsel mesajları temizle
    try:
        c.execute("DELETE FROM bot_memory WHERE image_data IS NOT NULL AND image_data != ''")
        conn.commit()
    except Exception:
        pass

    # Admin hesapları
    for uname, mail, pwd in [("crewampfilms", "crszbot052@gmail.com", "123"), ("crew", "", "123")]:
        c.execute("SELECT COUNT(*) FROM users WHERE username = ?", (uname,))
        if c.fetchone()[0] == 0:
            hashed = generate_password_hash(pwd)
            c.execute("INSERT INTO users (username, email, password, is_admin, language) VALUES (?, ?, ?, 1, 'tr')",
                      (uname, mail, hashed))
            conn.commit()
            print(f"[DB] Admin oluşturuldu: {uname}")
        else:
            c.execute("UPDATE users SET is_admin = 1 WHERE username = ?", (uname,))
            conn.commit()

    conn.close()


def get_user_from_db(username):
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT id, username, email, password, avatar, is_admin, language FROM users WHERE LOWER(username) = LOWER(?)", (username,))
        row = c.fetchone()
        conn.close()
        if row:
            return {"id": row[0], "username": row[1], "email": row[2], "password": row[3],
                    "avatar": row[4] or "", "is_admin": bool(row[5]), "language": row[6] or "tr"}
        return None
    except Exception as e:
        print(f"[DB USER HATA] {e}")
        return None


def get_user_by_email(email):
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT username FROM users WHERE LOWER(email) = LOWER(?)", (email,))
        row = c.fetchone()
        conn.close()
        return row[0] if row else None
    except Exception:
        return None


def create_user(username, email, password, is_admin=False, language="tr"):
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("INSERT INTO users (username, email, password, is_admin, language) VALUES (?, ?, ?, ?, ?)",
                  (username, email, generate_password_hash(password), 1 if is_admin else 0, language))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"[DB CREATE USER HATA] {e}")
        return False


def change_user_password(username, new_password):
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("UPDATE users SET password = ? WHERE LOWER(username) = LOWER(?)",
                  (generate_password_hash(new_password), username))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"[DB PW CHANGE HATA] {e}")
        return False


def update_user_language(username, language):
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("UPDATE users SET language = ? WHERE LOWER(username) = LOWER(?)", (language, username))
        conn.commit()
        conn.close()
        return True
    except Exception:
        return False


def save_user_avatar(username, filename):
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("UPDATE users SET avatar = ? WHERE LOWER(username) = LOWER(?)", (filename, username))
        conn.commit()
        conn.close()
        return True
    except Exception:
        return False


# ============ ŞİFRE SIFIRLAMA ============
def create_reset_token(username):
    token = secrets.token_urlsafe(32)
    expires = datetime.utcnow() + timedelta(hours=1)
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("UPDATE password_resets SET used = 1 WHERE username = ?", (username,))
        c.execute("INSERT INTO password_resets (username, token, expires_at) VALUES (?, ?, ?)",
                  (username, token, expires.isoformat()))
        conn.commit()
        conn.close()
        return token
    except Exception as e:
        print(f"[RESET TOKEN HATA] {e}")
        return None


def verify_reset_token(token):
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT username, expires_at, used FROM password_resets WHERE token = ?", (token,))
        row = c.fetchone()
        conn.close()
        if not row:
            return None
        username, expires_str, used = row
        if used:
            return None
        try:
            exp = datetime.fromisoformat(expires_str)
        except Exception:
            return None
        if datetime.utcnow() > exp:
            return None
        return username
    except Exception as e:
        print(f"[RESET VERIFY HATA] {e}")
        return None


def mark_reset_used(token):
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("UPDATE password_resets SET used = 1 WHERE token = ?", (token,))
        conn.commit()
        conn.close()
        return True
    except Exception:
        return False


# ============ 2FA ============
def setup_2fa(username):
    """Kullanıcı için 2FA secret oluştur"""
    if not pyotp:
        return None
    secret = pyotp.random_base32()
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM two_factor WHERE username = ?", (username,))
        if c.fetchone()[0] == 0:
            c.execute("INSERT INTO two_factor (username, secret, enabled) VALUES (?, ?, 0)", (username, secret))
        else:
            c.execute("UPDATE two_factor SET secret = ?, enabled = 0 WHERE username = ?", (secret, username))
        conn.commit()
        conn.close()
        return secret
    except Exception as e:
        print(f"[2FA SETUP HATA] {e}")
        return None


def enable_2fa(username, secret, code):
    if not pyotp:
        return False
    try:
        totp = pyotp.TOTP(secret)
        if not totp.verify(code, valid_window=1):
            return False
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("UPDATE two_factor SET enabled = 1, secret = ? WHERE username = ?", (secret, username))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"[2FA ENABLE HATA] {e}")
        return False


def disable_2fa(username):
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("UPDATE two_factor SET enabled = 0 WHERE username = ?", (username,))
        conn.commit()
        conn.close()
        return True
    except Exception:
        return False


def get_2fa_status(username):
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT secret, enabled FROM two_factor WHERE username = ?", (username,))
        row = c.fetchone()
        conn.close()
        if row:
            return {"secret": row[0], "enabled": bool(row[1])}
        return {"secret": None, "enabled": False}
    except Exception:
        return {"secret": None, "enabled": False}


def verify_2fa_code(username, code):
    if not pyotp:
        return False
    status = get_2fa_status(username)
    if not status["enabled"] or not status["secret"]:
        return True  # 2FA açık değilse geç
    try:
        totp = pyotp.TOTP(status["secret"])
        return totp.verify(code, valid_window=1)
    except Exception:
        return False


def generate_qr_base64(username, secret):
    """QR kodunu base64 PNG olarak döndür"""
    if not qrcode or not pyotp:
        return None
    try:
        otp_uri = pyotp.totp.TOTP(secret).provisioning_uri(name=username, issuer_name="Crsz Bot Studio")
        qr = qrcode.QRCode(version=1, box_size=8, border=2)
        qr.add_data(otp_uri)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        return "data:image/png;base64," + base64.b64encode(buf.read()).decode()
    except Exception as e:
        print(f"[QR HATA] {e}")
        return None


# ============ IP BAN ============
def is_ip_banned(ip):
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM bans WHERE ip = ?", (ip,))
        count = c.fetchone()[0]
        conn.close()
        return count > 0
    except Exception:
        return False


def ban_ip(ip, reason="", banned_by="admin"):
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO bans (ip, reason, banned_by) VALUES (?, ?, ?)", (ip, reason, banned_by))
        conn.commit()
        conn.close()
        return True
    except Exception:
        return False


def unban_ip(ip):
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("DELETE FROM bans WHERE ip = ?", (ip,))
        conn.commit()
        conn.close()
        return True
    except Exception:
        return False


def get_banned_ips():
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT ip, reason, banned_by, created_at FROM bans ORDER BY id DESC")
        rows = c.fetchall()
        conn.close()
        return [{"ip": r[0], "reason": r[1] or "", "banned_by": r[2] or "", "created_at": r[3]} for r in rows]
    except Exception:
        return []


def ban_check_decorator(f):
    """IP ban kontrolü için decorator"""
    @wraps(f)
    def wrapper(*args, **kwargs):
        ip = request.remote_addr or "unknown"
        if is_ip_banned(ip):
            return jsonify({"status": "error", "message": "IP adresiniz engellendi."}), 403
        return f(*args, **kwargs)
    return wrapper


# ============ BİLDİRİM ============
def add_notification(username, title, message, kind="info"):
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("INSERT INTO notifications (username, title, message, kind) VALUES (?, ?, ?, ?)",
                  (username, title, message, kind))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"[NOTIF HATA] {e}")
        return False


def get_notifications(username, limit=50):
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT id, title, message, is_read, kind, created_at FROM notifications WHERE username = ? ORDER BY id DESC LIMIT ?",
                  (username, limit))
        rows = c.fetchall()
        conn.close()
        return [{"id": r[0], "title": r[1], "message": r[2], "is_read": bool(r[3]),
                 "kind": r[4], "created_at": r[5]} for r in rows]
    except Exception:
        return []


def mark_notification_read(notif_id, username):
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("UPDATE notifications SET is_read = 1 WHERE id = ? AND username = ?", (notif_id, username))
        conn.commit()
        conn.close()
        return True
    except Exception:
        return False


def mark_all_read(username):
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("UPDATE notifications SET is_read = 1 WHERE username = ?", (username,))
        conn.commit()
        conn.close()
        return True
    except Exception:
        return False


def get_unread_count(username):
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM notifications WHERE username = ? AND is_read = 0", (username,))
        count = c.fetchone()[0]
        conn.close()
        return count
    except Exception:
        return 0


# ============ DOSYA METİN ÇIKARMA ============
def extract_text_from_file(filepath, ext):
    """PDF/DOCX/TXT'den metin çıkar"""
    try:
        if ext == ".pdf" and pypdf:
            reader = pypdf.PdfReader(filepath)
            text = ""
            for page in reader.pages[:30]:  # ilk 30 sayfa
                text += page.extract_text() + "\n"
            return text.strip()
        elif ext == ".docx" and docx:
            document = docx.Document(filepath)
            text = "\n".join([p.text for p in document.paragraphs])
            return text.strip()
        elif ext == ".txt":
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                return f.read().strip()
        else:
            return ""
    except Exception as e:
        print(f"[EXTRACT HATA] {e}")
        return ""


# ============ HAFIZA ============
def memory_add(username, role, content, image_data=None, language="tr"):
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("INSERT INTO bot_memory (username, role, content, image_data, language) VALUES (?, ?, ?, NULL, ?)",
                  (username, role, content, language))
        c.execute("""DELETE FROM bot_memory WHERE username = ? AND id NOT IN (
            SELECT id FROM bot_memory WHERE username = ? ORDER BY id DESC LIMIT 20
        )""", (username, username))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"[MEMORY ADD HATA] {e}")
        return False


def memory_get(username, limit=20):
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT role, content FROM bot_memory WHERE username = ? ORDER BY id DESC LIMIT ?", (username, limit))
        rows = c.fetchall()
        conn.close()
        rows.reverse()
        return [{"role": r[0], "content": r[1] or ""} for r in rows]
    except Exception:
        return []


def memory_clear(username):
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("DELETE FROM bot_memory WHERE username = ?", (username,))
        conn.commit()
        conn.close()
        return True
    except Exception:
        return False


def db_save_chat(username, title, messages_json):
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT id FROM chats WHERE username = ? AND title = ? ORDER BY id DESC LIMIT 1", (username, title))
        row = c.fetchone()
        if row:
            c.execute("UPDATE chats SET messages = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (messages_json, row[0]))
        else:
            c.execute("INSERT INTO chats (username, title, messages) VALUES (?, ?, ?)", (username, title, messages_json))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"[DB SAVE CHAT HATA] {e}")
        return False


def db_get_user_chats(username, search_query=None):
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        if search_query:
            c.execute("""SELECT id, title, messages FROM chats 
                        WHERE username = ? AND (LOWER(title) LIKE ? OR LOWER(messages) LIKE ?)
                        ORDER BY updated_at DESC LIMIT 30""",
                      (username, f"%{search_query.lower()}%", f"%{search_query.lower()}%"))
        else:
            c.execute("SELECT id, title, messages FROM chats WHERE username = ? ORDER BY updated_at DESC LIMIT 30", (username,))
        rows = c.fetchall()
        conn.close()
        out = []
        for r in rows:
            try: msgs = json.loads(r[2]) if r[2] else []
            except: msgs = []
            out.append({"id": r[0], "title": r[1], "messages": msgs})
        return out
    except Exception as e:
        print(f"[DB GET CHATS HATA] {e}")
        return []


def db_delete_chat(username, chat_id):
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("DELETE FROM chats WHERE id = ? AND username = ?", (chat_id, username))
        conn.commit()
        conn.close()
        return True
    except Exception:
        return False


def db_get_music_list():
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT id, filename, original_name FROM music ORDER BY id ASC")
        rows = c.fetchall()
        conn.close()
        return [{"id": r[0], "filename": r[1], "original_name": r[2]} for r in rows]
    except Exception:
        return []


init_db()

APP_STATE = {
    "username": "crewampfilms",
    "email": "crszbot052@gmail.com",
    "bot_name": db_get("bot_name", "Crsz Bot Studio") if 'db_get' in dir() else "Crsz Bot Studio",
    "logo_icon": "zap",
    "theme": {
        "bg_deep": "#07070a", "accent1": "#3B82F6", "accent2": "#8B5CF6", "accent3": "#06B6D4",
        "glass_opacity": 0.03, "aurora_opacity": 0.25, "bg_media": "", "bg_media_type": ""
    }
}


def db_get(key, default=None):
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = c.fetchone()
        conn.close()
        if row:
            try: return json.loads(row[0])
            except: return row[0]
        return default
    except Exception:
        return default


def db_set(key, value):
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        val = json.dumps(value) if not isinstance(value, str) else value
        c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, val))
        conn.commit()
        conn.close()
        return True
    except Exception:
        return False


# APP_STATE'i tekrar doldur (db_get tanımlandıktan sonra)
APP_STATE["bot_name"] = db_get("bot_name", "Crsz Bot Studio")
APP_STATE["logo_icon"] = db_get("logo_icon", "zap")
_theme = db_get("theme", None)
if _theme:
    APP_STATE["theme"].update(_theme)

ADMIN_USERS = ["crewampfilms", "crew"]
user_samimi_status = {}


def save_theme_to_db(theme): db_set("theme", theme)
def save_logo_to_db(icon): db_set("logo_icon", icon)
def save_bot_name_to_db(name): db_set("bot_name", name)


def is_admin_user(username):
    if not username: return False
    if username.lower() in [u.lower() for u in ADMIN_USERS]: return True
    u = get_user_from_db(username)
    return bool(u and u.get("is_admin"))


# ============ WEB SEARCH ============
def web_search(query, max_results=5):
    if requests is None:
        return ""
    results = []
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36",
        "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8"
    }
    try:
        for lang in ["tr", "en"]:
            wiki_api = f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{requests.utils.quote(query)}"
            r = requests.get(wiki_api, headers=headers, timeout=6)
            if r.status_code == 200:
                d = r.json()
                extract = d.get("extract", "")
                title = d.get("title", "")
                if extract and len(extract) > 50:
                    results.append(f"[Wikipedia-{lang.upper()}] {title}: {extract[:400]}")
                    break
    except Exception:
        pass
    if not results:
        try:
            search_api = f"https://tr.wikipedia.org/w/api.php?action=query&list=search&srsearch={requests.utils.quote(query)}&format=json&srlimit=2"
            r = requests.get(search_api, headers=headers, timeout=6)
            if r.status_code == 200:
                data = r.json()
                for item in data.get("query", {}).get("search", [])[:2]:
                    title = item.get("title", "")
                    snippet = re.sub(r'<[^>]+>', '', item.get("snippet", ""))
                    if title and snippet:
                        results.append(f"[Wikipedia] {title}: {snippet[:300]}")
        except Exception:
            pass
    try:
        ddg_api = f"https://api.duckduckgo.com/?q={requests.utils.quote(query)}&format=json&no_html=1&skip_disambig=1&t=crszbot"
        r = requests.get(ddg_api, headers=headers, timeout=6)
        if r.status_code == 200:
            d = r.json()
            if d.get("AbstractText"):
                results.append(f"[DuckDuckGo] {d.get('Heading', '')}: {d['AbstractText'][:400]}")
            elif d.get("Answer"):
                results.append(f"[DuckDuckGo] {d['Answer']}")
    except Exception:
        pass
    if not results:
        return ""
    seen = set()
    unique = []
    for r in results:
        key = r[:80].lower()
        if key not in seen:
            seen.add(key)
            unique.append(r)
    return "\n".join(unique[:max_results])


def detect_social_url(text):
    patterns = {
        "tiktok": r"(?:https?://)?(?:www\.)?tiktok\.com/@[\w.\-]+/video/\d+",
        "instagram": r"(?:https?://)?(?:www\.)?instagram\.com/(?:p|reel|tv)/[\w\-]+",
        "twitter": r"(?:https?://)?(?:www\.)?(?:twitter\.com|x\.com)/\w+/status/\d+",
        "youtube": r"(?:https?://)?(?:www\.)?(?:youtube\.com/watch\?v=|youtu\.be/)[\w\-]+",
        "reddit": r"(?:https?://)?(?:www\.)?reddit\.com/r/[\w\-]+/comments/[\w\-]+",
        "github": r"(?:https?://)?(?:www\.)?github\.com/[\w\-]+/[\w\-]+",
        "spotify": r"(?:https?://)?open\.spotify\.com/(?:track|album|playlist)/[\w]+",
    }
    for platform, pat in patterns.items():
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            url = m.group(0)
            if not url.startswith("http"):
                url = "https://" + url
            return platform, url
    return None, None


def fetch_social_content(platform, url):
    if requests is None:
        return ""
    headers = {"User-Agent": "Mozilla/5.0"}
    info = []
    try:
        if platform == "tiktok":
            r = requests.get(f"https://www.tiktok.com/oembed?url={url}", headers=headers, timeout=8)
            if r.status_code == 200:
                d = r.json()
                info.append(f"[TikTok] Başlık: {d.get('title', 'N/A')}")
                info.append(f"[TikTok] Yazar: {d.get('author_name', 'N/A')}")
        elif platform == "youtube":
            r = requests.get(f"https://www.youtube.com/oembed?url={url}&format=json", headers=headers, timeout=8)
            if r.status_code == 200:
                d = r.json()
                info.append(f"[YouTube] Başlık: {d.get('title', 'N/A')}")
                info.append(f"[YouTube] Kanal: {d.get('author_name', 'N/A')}")
        elif platform == "github":
            parts = url.rstrip("/").split("/")
            if len(parts) >= 2:
                r = requests.get(f"https://api.github.com/repos/{parts[-2]}/{parts[-1]}", headers=headers, timeout=8)
                if r.status_code == 200:
                    d = r.json()
                    info.append(f"[GitHub] {d.get('full_name', '')}: {d.get('description', '')}")
    except Exception:
        pass
    return "\n".join(info) if info else ""


def should_search(msg):
    triggers = ["araştır", "güncel", "son dakika", "haber", "bugün", "2025", "2026", "kimdir", "nedir", "nasıl yapılır", "fiyat", "ne zaman", "nerede", "internetten", "search", "google"]
    m = msg.lower()
    return any(t in m for t in triggers)


# ============ AI YANIT ============
def get_ai_response(username, user_message, image_data=None, file_text=None):
    is_owner = is_admin_user(username)
    if not is_owner and ("samimi" in user_message.lower() and ("konuş" in user_message.lower() or "ol" in user_message.lower())):
        user_samimi_status[username] = True
    samimi_mode = is_owner or user_samimi_status.get(username, False)

    user = get_user_from_db(username)
    user_lang = (user.get("language") if user else "tr") or "tr"
    active_lang_code = user_lang
    active_lang_name = SUPPORTED_LANGUAGES.get(active_lang_code, "Türkçe")

    if is_owner:
        persona = (
            f"Senin adın {APP_STATE['bot_name']}. Karşındaki kişi senin sahibin crewampfilms. "
            "Onunla konuşurken samimi, rahat ve gerektiğinde hafif arsız bir dille konuş. "
            "ÖNEMLİ: 'kanka', 'kardeşim', 'bro' gibi hitaplar KULLANMA. "
            "Kodları uygun markdown blokları içinde sun."
        )
    elif samimi_mode:
        persona = f"Senin adın {APP_STATE['bot_name']}. Kullanıcı ({username}) ile samimi, dostça konuş."
    else:
        persona = f"Senin adın {APP_STATE['bot_name']}. Kullanıcı ({username}) ile resmi, kibar konuş."

    persona += f"\n\nCok onemli: SADECE {active_lang_name} dilinde yanit ver."

    memory = memory_get(username, limit=20)
    messages = [{"role": "system", "content": persona}]

    for m in memory:
        content = m.get("content", "") or "[Bos]"
        messages.append({"role": m["role"], "content": content})

    # ============ DOSYA İÇERİĞİ ============
    if file_text:
        file_context = f"\n\n===== YÜKLENEN DOSYA İÇERİĞİ =====\n{file_text[:8000]}\n===================================\n\nKullanıcı bu dosyayı yükledi. Sorularını bu içeriğe göre yanıtla."
        user_message = (user_message or "Bu dosyayı özetle.") + file_context

    # ============ GÖRSEL ============
    if image_data:
        if "," in image_data:
            image_url = image_data
        else:
            image_url = f"data:image/jpeg;base64,{image_data}"
        messages.append({
            "role": "user",
            "content": [
                {"type": "text", "text": user_message if user_message else "Bu fotograftaki nedir?"},
                {"type": "image_url", "image_url": {"url": image_url}}
            ]
        })
        model_chain = ["qwen/qwen3.8-27b"]
    else:
        social_context = ""
        platform, url = detect_social_url(user_message)
        if platform and url:
            social_data = fetch_social_content(platform, url)
            if social_data:
                social_context = f"\n\n===== DIS KAYNAK ({platform.upper()}) =====\n{social_data}\n"
        search_context = ""
        if not social_context and should_search(user_message):
            search_result = web_search(user_message)
            if search_result:
                search_context = f"\n\n===== WEB ARAMA =====\n{search_result}\n"
        full_message = user_message + social_context + search_context
        messages.append({"role": "user", "content": full_message})
        model_chain = ["openai/gpt-oss-120b", "openai/gpt-oss-20b"]

    memory_add(username, "user", user_message if user_message else "[Medya]", None, active_lang_code)

    last_error = None
    for model_name in model_chain:
        try:
            completion = client.chat.completions.create(
                model=model_name, messages=messages, temperature=0.7, max_tokens=1500, timeout=30.0
            )
            reply = completion.choices[0].message.content.strip()
            if reply:
                memory_add(username, "assistant", reply, None, active_lang_code)
                return reply
        except Exception as e:
            last_error = str(e)
            err = last_error.lower()
            if "api key" in err or "401" in err:
                return "API anahtari gecersiz."
            if "rate" in err or "429" in err:
                return "Cok fazla istek, biraz bekle."
            continue
    if last_error:
        return f"Model hatasi: {last_error[:200]}"
    return "Bilinmeyen hata."


# ============ ROUTES ============
@app.before_request
def check_ip_ban():
    ip = request.remote_addr or "unknown"
    if is_ip_banned(ip):
        if request.path.startswith("/api") or request.is_json:
            return jsonify({"status": "error", "message": "IP engellendi"}), 403
        return "IP adresiniz engellendi.", 403


@app.route("/")
def dashboard():
    current_user = session.get('username', "")
    is_admin = is_admin_user(current_user) if current_user else False
    music_list = db_get_music_list()
    user_avatar = ""
    user_language = "tr"
    has_2fa = False
    unread_count = 0
    if current_user:
        u = get_user_from_db(current_user)
        if u:
            user_avatar = u.get("avatar", "")
            user_language = u.get("language", "tr")
        has_2fa = get_2fa_status(current_user)["enabled"]
        unread_count = get_unread_count(current_user)
    return render_template_string(
        HTML_TEMPLATE, app_state=APP_STATE, current_user=current_user,
        is_admin=is_admin, logged_in='username' in session,
        music_list=music_list, user_avatar=user_avatar,
        supported_languages=SUPPORTED_LANGUAGES,
        user_language=user_language,
        has_2fa=has_2fa, unread_count=unread_count
    )


@app.route("/uploads/music/<path:filename>")
def serve_music(filename):
    return send_from_directory(MUSIC_DIR, filename)


@app.route("/admin/bg/<path:filename>")
def serve_bg(filename):
    if ".." in filename or "/" in filename or "\\" in filename:
        return "Geçersiz", 400
    filepath = os.path.join(BG_DIR, filename)
    if not os.path.exists(filepath): return "Dosya yok", 404
    return send_from_directory(BG_DIR, filename)


@app.route("/uploads/avatars/<path:filename>")
def serve_avatar(filename):
    if ".." in filename or "/" in filename or "\\" in filename:
        return "Geçersiz", 400
    return send_from_directory(AVATAR_DIR, filename)


@app.route("/uploads/documents/<path:filename>")
def serve_document(filename):
    if ".." in filename or "/" in filename or "\\" in filename:
        return "Geçersiz", 400
    return send_from_directory(DOC_DIR, filename)


@app.route("/static/<path:filename>")
def serve_static(filename):
    return send_from_directory(STATIC_DIR, filename)


@app.route("/manifest.json")
def manifest():
    return jsonify({
        "name": APP_STATE["bot_name"], "short_name": "CrszBot", "start_url": "/",
        "display": "standalone", "background_color": APP_STATE["theme"]["bg_deep"],
        "theme_color": APP_STATE["theme"]["accent1"], "orientation": "portrait",
        "icons": [
            {"src": "/static/icon-192.png", "sizes": "192x192", "type": "image/png"},
            {"src": "/static/icon-512.png", "sizes": "512x512", "type": "image/png"}
        ]
    })


@app.route("/service-worker.js")
def service_worker():
    sw = """
    const CACHE_NAME = 'crszbot-v3';
    self.addEventListener('install', e => { self.skipWaiting(); });
    self.addEventListener('activate', e => { e.waitUntil(self.clients.claim()); });
    self.addEventListener('fetch', e => {
        if (e.request.method !== 'GET') return;
        e.respondWith(fetch(e.request).catch(() => caches.match(e.request)));
    });
    """
    return app.response_class(sw, mimetype="application/javascript")


@app.route("/maintenance/check")
def maintenance_check():
    val = db_get("maintenance_mode", False)
    return jsonify({"status": "success", "enabled": bool(val)})


@app.route("/maintenance/toggle", methods=["POST"])
def maintenance_toggle():
    if 'username' not in session or not is_admin_user(session['username']):
        return jsonify({"status": "error"}), 403
    data = request.get_json(silent=True) or {}
    enabled = bool(data.get("enabled", False))
    db_set("maintenance_mode", enabled)
    return jsonify({"status": "success", "enabled": enabled})


@app.route("/memory/clear", methods=["POST"])
def clear_memory():
    if 'username' not in session:
        return jsonify({"status": "error"}), 403
    memory_clear(session['username'])
    return jsonify({"status": "success", "message": "Bot hafızası temizlendi."})


# ============ ŞİFRE DEĞİŞTİR ============
@app.route("/change-password", methods=["POST"])
@rate_limit(max_calls=5, window_seconds=300)
def change_password():
    if 'username' not in session:
        return jsonify({"status": "error", "message": "Giriş yapmadın."}), 403
    data = request.get_json(silent=True) or {}
    current_pw = data.get("current_password", "").strip()
    new_pw = data.get("new_password", "").strip()
    if not current_pw or not new_pw:
        return jsonify({"status": "error", "message": "Tüm alanlar zorunlu."})
    if len(new_pw) < 6:
        return jsonify({"status": "error", "message": "Yeni şifre en az 6 karakter olmalı."})
    user = get_user_from_db(session['username'])
    if not user or not check_password_hash(user["password"], current_pw):
        return jsonify({"status": "error", "message": "Mevcut şifre yanlış."})
    change_user_password(session['username'], new_pw)
    add_notification(session['username'], "Şifre Değiştirildi", "Şifren başarıyla güncellendi.", "success")
    return jsonify({"status": "success", "message": "Şifre güncellendi!"})


# ============ ŞİFREMİ UNUTTUM ============
@app.route("/forgot-password", methods=["POST"])
@rate_limit(max_calls=3, window_seconds=300)
def forgot_password():
    data = request.get_json(silent=True) or {}
    identifier = data.get("identifier", "").strip()
    if not identifier:
        return jsonify({"status": "error", "message": "Kullanıcı adı veya e-posta gerekli."})
    username = None
    if "@" in identifier:
        username = get_user_by_email(identifier)
    else:
        user = get_user_from_db(identifier)
        username = user["username"] if user else None
    if not username:
        # Güvenlik için "bulunamadı" deme, aynı mesaj
        return jsonify({"status": "success", "message": "Eğer böyle bir hesap varsa, sıfırlama linki gönderildi."})
    user = get_user_from_db(username)
    email = user.get("email", "") if user else ""
    if not email:
        return jsonify({"status": "error", "message": "Bu hesaba kayıtlı e-posta yok."})
    token = create_reset_token(username)
    if not token:
        return jsonify({"status": "error", "message": "Token oluşturulamadı."})
    sent = send_reset_email(email, username, token)
    if sent:
        return jsonify({"status": "success", "message": f"Sıfırlama linki {email} adresine gönderildi."})
    else:
        return jsonify({"status": "error", "message": "E-posta gönderilemedi. SMTP ayarlarını kontrol edin."})


@app.route("/reset-password")
def reset_password_page():
    token = request.args.get("token", "")
    if not token:
        return "Geçersiz link", 400
    username = verify_reset_token(token)
    if not username:
        return """
        <html><head><meta charset="utf-8"><title>Geçersiz Link</title>
        <style>body{background:#07070a;color:#fff;font-family:sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;}
        .box{background:rgba(255,255,255,0.05);padding:40px;border-radius:20px;text-align:center;}
        h1{color:#F87171;}</style></head>
        <body><div class="box"><h1>Geçersiz veya Süresi Dolmuş Link</h1>
        <p>Bu şifre sıfırlama linki geçersiz ya da süresi dolmuş.</p>
        <a href="/" style="color:#3B82F6;">Ana sayfaya dön</a></div></body></html>
        """, 400
    # Basit reset formu
    return f"""
    <html><head><meta charset="utf-8"><title>Şifre Sıfırla</title>
    <style>body{{background:#07070a;color:#fff;font-family:sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;}}
    .box{{background:rgba(255,255,255,0.05);padding:40px;border-radius:20px;max-width:400px;width:90%;}}
    h1{{background:linear-gradient(135deg,#3B82F6,#8B5CF6);-webkit-background-clip:text;-webkit-text-fill-color:transparent;}}
    input{{width:100%;padding:12px;margin:10px 0;border-radius:10px;border:1px solid rgba(255,255,255,0.2);background:rgba(255,255,255,0.05);color:#fff;font-size:14px;box-sizing:border-box;}}
    button{{width:100%;padding:12px;border-radius:10px;border:none;background:linear-gradient(135deg,#3B82F6,#8B5CF6);color:#fff;font-weight:600;font-size:14px;cursor:pointer;}}
    .msg{{margin-top:10px;font-size:13px;}}</style></head>
    <body><div class="box"><h1>Yeni Şifre Belirle</h1>
    <p style="color:#94A3B8;font-size:13px;">Kullanıcı: <b>{username}</b></p>
    <input type="password" id="pw1" placeholder="Yeni şifre (min 6)">
    <input type="password" id="pw2" placeholder="Yeni şifre tekrar">
    <button onclick="doReset()">Şifreyi Sıfırla</button>
    <div class="msg" id="msg"></div>
    </div>
    <script>
    async function doReset() {{
        const p1 = document.getElementById('pw1').value;
        const p2 = document.getElementById('pw2').value;
        const msg = document.getElementById('msg');
        if (p1.length < 6) {{ msg.style.color='#F87171'; msg.innerText='Şifre min 6 karakter olmalı'; return; }}
        if (p1 !== p2) {{ msg.style.color='#F87171'; msg.innerText='Şifreler uyuşmuyor'; return; }}
        const r = await fetch('/reset-password-submit', {{
            method: 'POST', headers: {{'Content-Type':'application/json'}},
            body: JSON.stringify({{token:'{token}', new_password: p1}})
        }});
        const d = await r.json();
        msg.style.color = d.status === 'success' ? '#34D399' : '#F87171';
        msg.innerText = d.message;
        if (d.status === 'success') setTimeout(() => window.location.href = '/', 2000);
    }}
    </script></body></html>
    """


@app.route("/reset-password-submit", methods=["POST"])
@rate_limit(max_calls=5, window_seconds=300)
def reset_password_submit():
    data = request.get_json(silent=True) or {}
    token = data.get("token", "")
    new_pw = data.get("new_password", "").strip()
    if not token or len(new_pw) < 6:
        return jsonify({"status": "error", "message": "Geçersiz veri (şifre min 6 karakter)."})
    username = verify_reset_token(token)
    if not username:
        return jsonify({"status": "error", "message": "Token geçersiz veya süresi dolmuş."})
    change_user_password(username, new_pw)
    mark_reset_used(token)
    add_notification(username, "Şifre Sıfırlandı", "Şifren başarıyla sıfırlandı.", "success")
    return jsonify({"status": "success", "message": "Şifren sıfırlandı! Giriş sayfasına yönlendiriliyorsun..."})


# ============ SOHBET ARAMA ============
@app.route("/chats/search")
def search_chats():
    if 'username' not in session:
        return jsonify({"status": "error", "chats": []})
    query = request.args.get("q", "").strip()
    chats = db_get_user_chats(session['username'], search_query=query if query else None)
    return jsonify({"status": "success", "chats": chats})


# ============ DOSYA YÜKLEME ============
@app.route("/upload-document", methods=["POST"])
@rate_limit(max_calls=10, window_seconds=300)
def upload_document():
    if 'username' not in session:
        return jsonify({"status": "error", "message": "Giriş yapmadın."}), 403
    if 'file' not in request.files:
        return jsonify({"status": "error", "message": "Dosya yok."}), 400
    file = request.files['file']
    if file.filename == "":
        return jsonify({"status": "error", "message": "Dosya seçilmedi."}), 400
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in [".pdf", ".docx", ".txt"]:
        return jsonify({"status": "error", "message": "Sadece PDF, DOCX, TXT destekleniyor."}), 400
    unique_name = f"doc_{uuid.uuid4().hex[:12]}{ext}"
    filepath = os.path.join(DOC_DIR, unique_name)
    file.save(filepath)
    # Metin çıkar
    text = extract_text_from_file(filepath, ext)
    if not text:
        return jsonify({"status": "error", "message": "Dosyadan metin çıkarılamadı."}), 400
    # DB'ye kaydet
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("INSERT INTO documents (username, filename, original_name, text_content) VALUES (?, ?, ?, ?)",
                  (session['username'], unique_name, file.filename, text[:50000]))
        conn.commit()
        doc_id = c.lastrowid
        conn.close()
    except Exception as e:
        print(f"[DOC DB HATA] {e}")
        doc_id = None
    preview = text[:500]
    return jsonify({
        "status": "success",
        "message": f"Dosya yüklendi ({len(text)} karakter).",
        "doc_id": doc_id,
        "filename": unique_name,
        "original_name": file.filename,
        "preview": preview,
        "char_count": len(text)
    })


# ============ 2FA ============
@app.route("/2fa/setup", methods=["POST"])
def twofa_setup():
    if 'username' not in session:
        return jsonify({"status": "error", "message": "Giriş yapmadın."}), 403
    if not pyotp:
        return jsonify({"status": "error", "message": "2FA sunucuda aktif değil."})
    secret = setup_2fa(session['username'])
    if not secret:
        return jsonify({"status": "error", "message": "Secret oluşturulamadı."})
    qr_b64 = generate_qr_base64(session['username'], secret)
    return jsonify({
        "status": "success",
        "secret": secret,
        "qr": qr_b64,
        "message": "QR kodu Google Authenticator ile tara."
    })


@app.route("/2fa/enable", methods=["POST"])
def twofa_enable():
    if 'username' not in session:
        return jsonify({"status": "error", "message": "Giriş yapmadın."}), 403
    data = request.get_json(silent=True) or {}
    secret = data.get("secret", "")
    code = data.get("code", "").strip()
    if not secret or not code:
        return jsonify({"status": "error", "message": "Secret ve kod gerekli."})
    if enable_2fa(session['username'], secret, code):
        add_notification(session['username'], "2FA Aktif", "İki faktörlü doğrulama etkinleştirildi.", "success")
        return jsonify({"status": "success", "message": "2FA aktif edildi!"})
    return jsonify({"status": "error", "message": "Kod yanlış. Tekrar dene."})


@app.route("/2fa/disable", methods=["POST"])
def twofa_disable():
    if 'username' not in session:
        return jsonify({"status": "error", "message": "Giriş yapmadın."}), 403
    data = request.get_json(silent=True) or {}
    code = data.get("code", "").strip()
    if not verify_2fa_code(session['username'], code):
        return jsonify({"status": "error", "message": "Kod yanlış."})
    disable_2fa(session['username'])
    add_notification(session['username'], "2FA Kapatıldı", "İki faktörlü doğrulama devre dışı.", "warning")
    return jsonify({"status": "success", "message": "2FA kapatıldı."})


@app.route("/2fa/status")
def twofa_status():
    if 'username' not in session:
        return jsonify({"status": "error"}), 403
    s = get_2fa_status(session['username'])
    return jsonify({"status": "success", "enabled": s["enabled"]})


# ============ BİLDİRİMLER ============
@app.route("/notifications")
def notifications_list():
    if 'username' not in session:
        return jsonify({"status": "error", "notifications": []})
    notifs = get_notifications(session['username'])
    return jsonify({"status": "success", "notifications": notifs,
                    "unread": get_unread_count(session['username'])})


@app.route("/notifications/read/<int:notif_id>", methods=["POST"])
def notification_read(notif_id):
    if 'username' not in session:
        return jsonify({"status": "error"}), 403
    mark_notification_read(notif_id, session['username'])
    return jsonify({"status": "success"})


@app.route("/notifications/read-all", methods=["POST"])
def notification_read_all():
    if 'username' not in session:
        return jsonify({"status": "error"}), 403
    mark_all_read(session['username'])
    return jsonify({"status": "success"})


@app.route("/notifications/send", methods=["POST"])
def notification_send():
    """Admin başka kullanıcıya bildirim gönderebilir"""
    if 'username' not in session or not is_admin_user(session['username']):
        return jsonify({"status": "error"}), 403
    data = request.get_json(silent=True) or {}
    target = data.get("username", "").strip()
    title = data.get("title", "Bildirim").strip()
    message = data.get("message", "").strip()
    if not target or not message:
        return jsonify({"status": "error", "message": "Kullanıcı ve mesaj gerekli."})
    add_notification(target, title, message, "info")
    return jsonify({"status": "success", "message": "Bildirim gönderildi."})


# ============ ADMIN — IP BAN ============
@app.route("/admin/bans")
def admin_bans():
    if 'username' not in session or not is_admin_user(session['username']):
        return jsonify({"status": "error"}), 403
    return jsonify({"status": "success", "bans": get_banned_ips()})


@app.route("/admin/ban", methods=["POST"])
def admin_ban():
    if 'username' not in session or not is_admin_user(session['username']):
        return jsonify({"status": "error"}), 403
    data = request.get_json(silent=True) or {}
    ip = data.get("ip", "").strip()
    reason = data.get("reason", "").strip()
    if not ip:
        return jsonify({"status": "error", "message": "IP adresi gerekli."})
    ban_ip(ip, reason, session['username'])
    return jsonify({"status": "success", "message": f"{ip} engellendi."})


@app.route("/admin/unban", methods=["POST"])
def admin_unban():
    if 'username' not in session or not is_admin_user(session['username']):
        return jsonify({"status": "error"}), 403
    data = request.get_json(silent=True) or {}
    ip = data.get("ip", "").strip()
    if not ip:
        return jsonify({"status": "error", "message": "IP adresi gerekli."})
    unban_ip(ip)
    return jsonify({"status": "success", "message": f"{ip} engeli kaldırıldı."})


# ============ SOHBET ============
@app.route("/chat", methods=["POST"])
@rate_limit(max_calls=30, window_seconds=60)
def chat():
    try:
        data = request.get_json(silent=True) or {}
        username = data.get("username", "Bilinmeyen")
        user_message = data.get("message", "") or ""
        image_data = data.get("image", None)
        file_text = data.get("file_text", None)
        reply = get_ai_response(username, user_message, image_data, file_text)
        return jsonify({"reply": reply, "status": "success"})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"reply": f"Sunucu hatası: {str(e)}", "status": "error"}), 500


# ============ AUTH ============
@app.route("/auth", methods=["POST"])
@rate_limit(max_calls=10, window_seconds=60)
def auth():
    data = request.get_json(silent=True) or {}
    action = data.get("action")
    username = data.get("username", "").strip()
    email = data.get("email", "").strip()
    password = data.get("password", "").strip()
    language = data.get("language", "tr").strip()
    totp_code = data.get("totp_code", "").strip()

    if language not in SUPPORTED_LANGUAGES:
        language = "tr"

    if not username or not password:
        return jsonify({"status": "error", "message": "Kullanıcı adı ve şifre zorunludur."})

    existing = get_user_from_db(username)

    if action == "register":
        if existing: return jsonify({"status": "error", "message": "Bu kullanıcı adı alınmış."})
        if len(password) < 3: return jsonify({"status": "error", "message": "Şifre en az 3 karakter."})
        ok = create_user(username, email, password, is_admin=False, language=language)
        if not ok: return jsonify({"status": "error", "message": "Kayıt oluşturulamadı."})
        session.permanent = True
        session['username'] = username
        add_notification(username, "Hoş Geldin!", f"Crsz Bot Studio'ya kaydın yapıldı. Hoş geldin {username}!", "success")
        return jsonify({"status": "success", "message": "Kayıt başarılı!", "username": username, "is_admin": False, "language": language})

    elif action == "login":
        if existing and check_password_hash(existing["password"], password):
            # 2FA kontrolü
            status_2fa = get_2fa_status(existing["username"])
            if status_2fa["enabled"]:
                if not totp_code:
                    return jsonify({"status": "2fa_required", "message": "2FA kodu gerekli."})
                if not verify_2fa_code(existing["username"], totp_code):
                    return jsonify({"status": "error", "message": "2FA kodu yanlış."})
            session.permanent = True
            session['username'] = existing["username"]
            return jsonify({"status": "success", "message": "Giriş başarılı!",
                          "username": existing["username"], "is_admin": existing["is_admin"],
                          "language": existing.get("language", "tr")})
        return jsonify({"status": "error", "message": "Hatalı kullanıcı adı veya şifre!"})

    return jsonify({"status": "error", "message": "Geçersiz işlem."})


@app.route("/logout", methods=["POST"])
def logout():
    session.pop('username', None)
    return jsonify({"status": "success", "message": "Çıkış yapıldı."})


@app.route("/update-profile", methods=["POST"])
def update_profile():
    if 'username' not in session:
        return jsonify({"status": "error"}), 403
    data = request.get_json(silent=True) or {}
    APP_STATE["bot_name"] = data.get("bot_name", APP_STATE["bot_name"])
    save_bot_name_to_db(APP_STATE["bot_name"])
    if "language" in data and data["language"] in SUPPORTED_LANGUAGES:
        update_user_language(session['username'], data["language"])
    return jsonify({"status": "success", "message": "Profil güncellendi."})


@app.route("/chats")
def get_chats():
    if 'username' not in session:
        return jsonify({"status": "error", "chats": []})
    chats = db_get_user_chats(session['username'])
    return jsonify({"status": "success", "chats": chats})


@app.route("/chats/save", methods=["POST"])
def save_chat():
    if 'username' not in session:
        return jsonify({"status": "error"}), 403
    data = request.get_json(silent=True) or {}
    title = data.get("title", "Sohbet")
    messages = data.get("messages", [])
    db_save_chat(session['username'], title, json.dumps(messages, ensure_ascii=False))
    return jsonify({"status": "success"})


@app.route("/chats/delete/<int:chat_id>", methods=["POST"])
def delete_chat(chat_id):
    if 'username' not in session:
        return jsonify({"status": "error"}), 403
    db_delete_chat(session['username'], chat_id)
    return jsonify({"status": "success"})


@app.route("/upload-avatar", methods=["POST"])
def upload_avatar():
    if 'username' not in session:
        return jsonify({"status": "error"}), 403
    if 'file' not in request.files:
        return jsonify({"status": "error"}), 400
    file = request.files['file']
    if file.filename == "": return jsonify({"status": "error"}), 400
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in [".png", ".jpg", ".jpeg", ".webp", ".gif"]:
        return jsonify({"status": "error", "message": "Sadece resim."}), 400
    unique_name = f"av_{uuid.uuid4().hex[:12]}{ext}"
    file.save(os.path.join(AVATAR_DIR, unique_name))
    save_user_avatar(session['username'], unique_name)
    return jsonify({"status": "success", "avatar": unique_name})


@app.route("/admin/users")
def admin_users_list():
    if 'username' not in session or not is_admin_user(session['username']):
        return jsonify({"status": "error"}), 403
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT id, username, email, is_admin, language, created_at FROM users ORDER BY id ASC")
    rows = c.fetchall()
    conn.close()
    users = [{"id": r[0], "username": r[1], "email": r[2], "is_admin": bool(r[3]),
              "language": r[4], "created_at": r[5]} for r in rows]
    return jsonify({"status": "success", "users": users})


@app.route("/admin/users/delete/<int:user_id>", methods=["POST"])
def admin_delete_user(user_id):
    if 'username' not in session or not is_admin_user(session['username']):
        return jsonify({"status": "error"}), 403
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT username FROM users WHERE id = ?", (user_id,))
    row = c.fetchone()
    if row and row[0].lower() in [u.lower() for u in ADMIN_USERS]:
        conn.close()
        return jsonify({"status": "error", "message": "Ana admin silinemez."}), 400
    c.execute("DELETE FROM users WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()
    return jsonify({"status": "success"})


@app.route("/admin/users/toggle-admin/<int:user_id>", methods=["POST"])
def admin_toggle_admin(user_id):
    if 'username' not in session or not is_admin_user(session['username']):
        return jsonify({"status": "error"}), 403
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT is_admin FROM users WHERE id = ?", (user_id,))
    row = c.fetchone()
    if not row:
        conn.close()
        return jsonify({"status": "error"}), 404
    new_val = 0 if row[0] else 1
    c.execute("UPDATE users SET is_admin = ? WHERE id = ?", (new_val, user_id))
    conn.commit()
    conn.close()
    return jsonify({"status": "success", "is_admin": bool(new_val)})


@app.route("/admin/update-theme", methods=["POST"])
def admin_update_theme():
    if 'username' not in session or not is_admin_user(session['username']):
        return jsonify({"status": "error"}), 403
    data = request.get_json(silent=True) or {}
    theme = APP_STATE.get("theme", {})
    for key in ["bg_deep", "accent1", "accent2", "accent3", "glass_opacity", "aurora_opacity"]:
        if key in data: theme[key] = data[key]
    APP_STATE["theme"] = theme
    save_theme_to_db(theme)
    if "logo_icon" in data:
        APP_STATE["logo_icon"] = data["logo_icon"]
        save_logo_to_db(data["logo_icon"])
    return jsonify({"status": "success", "theme": theme, "logo_icon": APP_STATE["logo_icon"]})


@app.route("/admin/get-theme")
def admin_get_theme():
    return jsonify({
        "status": "success",
        "theme": db_get("theme", APP_STATE.get("theme", {})),
        "logo_icon": db_get("logo_icon", APP_STATE.get("logo_icon", "zap"))
    })


@app.route("/admin/upload-background", methods=["POST"])
def admin_upload_background():
    if 'username' not in session or not is_admin_user(session['username']):
        return jsonify({"status": "error"}), 403
    if 'file' not in request.files: return jsonify({"status": "error"}), 400
    file = request.files['file']
    if file.filename == "": return jsonify({"status": "error"}), 400
    ext = os.path.splitext(file.filename)[1].lower()
    is_video = ext in [".mp4", ".webm", ".ogg", ".mov"]
    unique_name = f"bg_{uuid.uuid4().hex[:12]}{ext}"
    file.save(os.path.join(BG_DIR, unique_name))
    old_bg = APP_STATE["theme"].get("bg_media", "")
    if old_bg:
        old_path = os.path.join(BG_DIR, os.path.basename(old_bg))
        if os.path.exists(old_path) and old_bg != unique_name:
            try: os.remove(old_path)
            except: pass
    APP_STATE["theme"]["bg_media"] = unique_name
    APP_STATE["theme"]["bg_media_type"] = "video" if is_video else "image"
    save_theme_to_db(APP_STATE["theme"])
    return jsonify({"status": "success", "bg_media": unique_name, "bg_media_type": APP_STATE["theme"]["bg_media_type"]})


@app.route("/admin/clear-background", methods=["POST"])
def admin_clear_background():
    if 'username' not in session or not is_admin_user(session['username']):
        return jsonify({"status": "error"}), 403
    old_bg = APP_STATE["theme"].get("bg_media", "")
    if old_bg:
        old_path = os.path.join(BG_DIR, os.path.basename(old_bg))
        if os.path.exists(old_path):
            try: os.remove(old_path)
            except: pass
    APP_STATE["theme"]["bg_media"] = ""
    APP_STATE["theme"]["bg_media_type"] = ""
    save_theme_to_db(APP_STATE["theme"])
    return jsonify({"status": "success"})


@app.route("/admin/upload-music", methods=["POST"])
def admin_upload_music():
    if 'username' not in session or not is_admin_user(session['username']):
        return jsonify({"status": "error"}), 403
    if 'file' not in request.files: return jsonify({"status": "error"}), 400
    file = request.files['file']
    if file.filename == "": return jsonify({"status": "error"}), 400
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in [".mp3", ".wav", ".ogg", ".m4a", ".aac", ".flac"]:
        return jsonify({"status": "error"}), 400
    if len(db_get_music_list()) >= 3:
        return jsonify({"status": "error", "message": "Maks 3 müzik."}), 400
    unique_name = f"music_{uuid.uuid4().hex[:12]}{ext}"
    file.save(os.path.join(MUSIC_DIR, unique_name))
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT INTO music (filename, original_name) VALUES (?, ?)", (unique_name, file.filename))
    conn.commit()
    conn.close()
    return jsonify({"status": "success", "music": db_get_music_list()})


@app.route("/admin/delete-music/<int:music_id>", methods=["POST"])
def admin_delete_music(music_id):
    if 'username' not in session or not is_admin_user(session['username']):
        return jsonify({"status": "error"}), 403
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT filename FROM music WHERE id = ?", (music_id,))
    row = c.fetchone()
    if row:
        filepath = os.path.join(MUSIC_DIR, row[0])
        if os.path.exists(filepath):
            try: os.remove(filepath)
            except: pass
        c.execute("DELETE FROM music WHERE id = ?", (music_id,))
        conn.commit()
    conn.close()
    return jsonify({"status": "success", "music": db_get_music_list()})


@app.route("/music-list")
def music_list_api():
    return jsonify({"status": "success", "music": db_get_music_list()})


@app.errorhandler(404)
def not_found(e):
    return """<html><body style="background:#07070a;color:#fff;font-family:sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;">
    <div style="text-align:center;"><h1 style="font-size:80px;background:linear-gradient(135deg,#3B82F6,#8B5CF6);-webkit-background-clip:text;-webkit-text-fill-color:transparent;">404</h1>
    <p>Sayfa bulunamadı</p><a href="/" style="color:#3B82F6;">Ana sayfa</a></div></body></html>""", 404


# ============ HTML (PARÇA 2'DE GELECEK) ============
HTML_TEMPLATE = r"# ============ HTML ============
HTML_TEMPLATE = r"""
<!DOCTYPE html>
<html lang="tr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no, viewport-fit=cover">
    <title>Crsz Bot | Liquid Glass AI Studio</title>
    <link rel="manifest" href="/manifest.json">
    <meta name="theme-color" content="{{ app_state.theme.accent1 }}">
    <link rel="apple-touch-icon" href="/static/icon-192.png">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">
    <script src="https://unpkg.com/lucide@latest"></script>
    <script src="https://cdn.jsdelivr.net/npm/marked@12.0.0/marked.min.js"></script>
    <style>
        :root {
            --bg-deep: {{ app_state.theme.bg_deep }};
            --accent1: {{ app_state.theme.accent1 }};
            --accent2: {{ app_state.theme.accent2 }};
            --accent3: {{ app_state.theme.accent3 }};
            --primary-gradient: linear-gradient(135deg, var(--accent1) 0%, var(--accent2) 50%, var(--accent3) 100%);
            --text-main: #F8FAFC;
            --text-muted: #94A3B8;
            --lg-blur: 40px;
            --lg-saturate: 200%;
            --lg-brightness: 1.1;
            --lg-tint: rgba(255,255,255,0.04);
            --lg-border-soft: rgba(255,255,255,0.08);
            --lg-highlight: rgba(255,255,255,0.5);
            --lg-shadow: 0 8px 32px rgba(0,0,0,0.4);
            --tx-smooth: cubic-bezier(0.22, 1, 0.36, 1);
            --tx-bounce: cubic-bezier(0.34, 1.56, 0.64, 1);
        }
        * { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Inter', sans-serif; -webkit-tap-highlight-color: transparent; }
        html, body {
            background-color: var(--bg-deep); color: var(--text-main);
            height: 100%; width: 100%; overflow: hidden; position: fixed;
            top: 0; left: 0; right: 0; bottom: 0;
            transition: background-color 0.5s var(--tx-smooth);
        }
        .lg {
            position: relative; isolation: isolate;
            background: var(--lg-tint);
            backdrop-filter: blur(var(--lg-blur)) saturate(var(--lg-saturate)) brightness(var(--lg-brightness));
            -webkit-backdrop-filter: blur(var(--lg-blur)) saturate(var(--lg-saturate)) brightness(var(--lg-brightness));
            border: 1px solid var(--lg-border-soft);
            border-radius: 20px;
            box-shadow: var(--lg-shadow), inset 0 1px 0 0 var(--lg-highlight), inset 0 -1px 0 0 rgba(0,0,0,0.15), inset 0 0 30px 0 rgba(255,255,255,0.03);
            overflow: hidden;
        }
        .lg::after {
            content: ''; position: absolute; top: 0; left: 10%; right: 10%; height: 1px;
            background: linear-gradient(90deg, transparent, rgba(255,255,255,0.6) 50%, transparent);
            pointer-events: none; z-index: 2;
        }
        .lg > * { position: relative; z-index: 3; }
        .sidebar, .main-workspace, header, .control-panel, .modal-card, .auth-card,
        .stat-card, .new-chat-btn, .footer-btn, .icon-action-btn, .input-wrapper,
        .music-item, .user-item, .toggle-row, .logo-option, .tab-buttons,
        .toast, .slider-row, .range-row, .color-picker-row {
            background: var(--lg-tint);
            backdrop-filter: blur(var(--lg-blur)) saturate(var(--lg-saturate));
            border: 1px solid var(--lg-border-soft);
            position: relative; overflow: hidden;
        }
        button { transition: transform 0.2s var(--tx-bounce); position: relative; overflow: hidden; }
        button:active { transform: scale(0.95); }
        @keyframes spin { to { transform: rotate(360deg); } }
        .spinner { display: inline-block; width: 14px; height: 14px; border: 2px solid rgba(255,255,255,0.1); border-top-color: var(--accent1); border-radius: 50%; animation: spin 0.8s linear infinite; vertical-align: middle; margin-right: 6px; }
        .ripple { position: absolute; border-radius: 50%; background: rgba(255, 255, 255, 0.35); transform: scale(0); animation: rippleAnim 0.65s ease-out; pointer-events: none; z-index: 999; }
        @keyframes rippleAnim { to { transform: scale(4); opacity: 0; } }
        #bgMedia, #bgVideo { position: fixed; inset: 0; z-index: -3; width: 100%; height: 100%; object-fit: cover; display: none; }
        #bgMedia.active, #bgVideo.active { display: block; }
        #bgOverlay { position: fixed; inset: 0; z-index: -2; background: rgba(0,0,0,0.65); backdrop-filter: blur(2px); display: none; }
        #bgOverlay.active { display: block; }
        #authOverlay { position: fixed; inset: 0; background: rgba(7, 7, 10, 0.85); backdrop-filter: blur(40px) saturate(180%); z-index: 2000; display: flex; align-items: center; justify-content: center; padding: 20px; transition: opacity 0.4s ease; }
        #authOverlay.hidden { display: none; }
        .auth-card { width: 100%; max-width: 420px; padding: 30px; border-radius: 24px; }
        .auth-tabs { display: flex; gap: 10px; margin-bottom: 20px; background: rgba(0,0,0,0.25); padding: 4px; border-radius: 12px; }
        .auth-tab { flex: 1; padding: 10px; text-align: center; font-size: 13px; font-weight: 600; color: var(--text-muted); cursor: pointer; border-radius: 8px; transition: 0.2s; }
        .auth-tab.active { background: rgba(255,255,255,0.1); color: #fff; }
        .auth-input { width: 100%; background: rgba(255,255,255,0.05); border: 1px solid var(--lg-border-soft); border-radius: 12px; padding: 12px 16px; color: white; font-size: 14px; margin-bottom: 14px; outline: none; }
        .auth-input:focus { border-color: var(--accent1); box-shadow: 0 0 0 3px rgba(59,130,246,0.2); }
        .auth-label { font-size: 11px; color: var(--text-muted); display: flex; align-items: center; gap: 6px; margin-bottom: 6px; margin-top: 4px; }
        .auth-btn { width: 100%; background: var(--primary-gradient); color: white; border: none; padding: 12px; border-radius: 12px; font-weight: 600; cursor: pointer; font-size: 14px; box-shadow: 0 4px 15px rgba(59,130,246,0.3); }
        .auth-btn:disabled { opacity: 0.6; cursor: wait; }
        .auth-btn-secondary { width: 100%; background: rgba(255,255,255,0.08); color: white; border: 1px solid var(--lg-border-soft); padding: 12px; border-radius: 12px; font-weight: 600; cursor: pointer; font-size: 14px; margin-top: 8px; }
        .auth-link { color: #38BDF8; font-size: 12px; text-decoration: none; display: block; text-align: center; margin-top: 12px; cursor: pointer; }
        .auth-link:hover { text-decoration: underline; }
        .lang-select { width: 100%; background: rgba(255,255,255,0.05); border: 1px solid var(--lg-border-soft); border-radius: 12px; padding: 12px 16px; color: white; font-size: 14px; margin-bottom: 14px; outline: none; cursor: pointer; }
        .lang-select option { background: #0f172a; color: #fff; }
        .modal-overlay { display: none; position: fixed; inset: 0; background: rgba(0,0,0,0.65); backdrop-filter: blur(10px); z-index: 1500; align-items: center; justify-content: center; padding: 20px; }
        .modal-overlay.active { display: flex; }
        .modal-card { width: 100%; max-width: 560px; max-height: 90vh; overflow-y: auto; border-radius: 22px; padding: 25px; }
        .modal-card h3 { font-size: 15px; margin-bottom: 14px; color: #fff; display: flex; align-items: center; gap: 8px; }
        .modal-label { font-size: 10px; color: var(--text-muted); text-transform: uppercase; margin-bottom: 4px; display: block; margin-top: 10px; }
        .aurora-bg { position: fixed; inset: 0; pointer-events: none; z-index: -1; filter: blur(140px); opacity: {{ app_state.theme.aurora_opacity }}; overflow: hidden; }
        .aurora-blob { position: absolute; border-radius: 50%; }
        .blob-1 { width: 350px; height: 350px; background: var(--accent1); top: -50px; left: -50px; }
        .blob-2 { width: 450px; height: 450px; background: var(--accent2); bottom: -50px; right: -50px; }
        .blob-3 { width: 300px; height: 300px; background: var(--accent3); top: 40%; left: 40%; opacity: 0.5; }
        .app-layout { display: flex; height: 100dvh; width: 100vw; padding: 12px; gap: 12px; overflow: hidden; }
        .sidebar { width: 260px; min-width: 260px; display: flex; flex-direction: column; padding: 14px; gap: 10px; height: calc(100dvh - 24px); border-radius: 22px; flex-shrink: 0; }
        .logo-area { display: flex; align-items: center; gap: 10px; padding-bottom: 10px; border-bottom: 1px solid var(--lg-border-soft); }
        .logo-icon { width: 34px; height: 34px; background: var(--primary-gradient); border-radius: 10px; display: flex; align-items: center; justify-content: center; color: white; flex-shrink: 0; }
        .logo-text { min-width: 0; flex: 1; }
        .logo-text h1 { font-size: 13px; font-weight: 700; color: #fff; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
        .logo-text p { font-size: 10px; color: var(--text-muted); }
        .new-chat-btn { padding: 9px; border-radius: 12px; font-size: 12px; font-weight: 500; cursor: pointer; display: flex; align-items: center; justify-content: center; gap: 6px; color: #fff; }
        .quick-stats { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; }
        .stat-card { border-radius: 12px; padding: 8px; text-align: center; }
        .stat-card .stat-value { font-size: 15px; font-weight: 700; color: #fff; }
        .stat-card .stat-label { font-size: 9px; color: var(--text-muted); text-transform: uppercase; margin-top: 2px; }
        .search-box { position: relative; }
        .search-box input { width: 100%; background: rgba(255,255,255,0.05); border: 1px solid var(--lg-border-soft); border-radius: 10px; padding: 8px 10px 8px 32px; color: #fff; font-size: 12px; outline: none; }
        .search-box i { position: absolute; left: 10px; top: 50%; transform: translateY(-50%); color: var(--text-muted); }
        .chat-history-list { flex: 1; overflow-y: auto; display: flex; flex-direction: column; gap: 4px; min-height: 0; }
        .history-item { padding: 9px 10px; border-radius: 10px; font-size: 12px; color: var(--text-muted); cursor: pointer; display: flex; align-items: center; gap: 8px; }
        .history-item.active { background: rgba(59, 130, 246, 0.18) !important; color: #fff !important; }
        .sidebar-footer { border-top: 1px solid var(--lg-border-soft); padding-top: 8px; display: flex; flex-direction: column; gap: 6px; }
        .footer-btn { border-radius: 10px; color: #fff; padding: 8px; font-size: 12px; cursor: pointer; display: flex; align-items: center; gap: 8px; justify-content: flex-start; }
        .main-workspace { flex: 1; display: flex; flex-direction: column; height: calc(100dvh - 24px); overflow: hidden; min-width: 0; border-radius: 22px; }
        header { padding: 12px 18px; border-bottom: 1px solid var(--lg-border-soft); display: flex; justify-content: space-between; align-items: center; gap: 8px; }
        header h2 { font-size: 13px; font-weight: 600; color: #E2E8F0; display: flex; align-items: center; gap: 6px; }
        .menu-toggle-btn { display: none; background: transparent; border: 1px solid var(--lg-border-soft); color: #fff; padding: 6px; border-radius: 8px; cursor: pointer; }
        .status-badge { font-size: 10px; color: #38BDF8; background: rgba(56, 189, 248, 0.1); border: 1px solid rgba(56, 189, 248, 0.2); padding: 3px 8px; border-radius: 20px; display: flex; align-items: center; gap: 5px; }
        .status-dot { width: 5px; height: 5px; background: #38BDF8; border-radius: 50%; }
        .icon-action-btn { color: #38BDF8; padding: 6px; border-radius: 10px; cursor: pointer; display: flex; align-items: center; justify-content: center; border: 1px solid rgba(56,189,248,0.2); position: relative; }
        .icon-action-btn .badge { position: absolute; top: -3px; right: -3px; background: #EF4444; color: #fff; font-size: 9px; border-radius: 10px; padding: 1px 5px; font-weight: 700; }
        .chat-container { flex: 1; padding: 16px; overflow-y: auto; display: flex; flex-direction: column; gap: 14px; min-height: 0; }
        .msg-bubble { max-width: 85%; padding: 12px 16px; border-radius: 16px; font-size: 13px; line-height: 1.55; word-break: break-word; position: relative; }
        .msg-bubble.user { background: rgba(255,255,255,0.06); border: 1px solid var(--lg-border-soft); align-self: flex-start; color: #CBD5E1; }
        .msg-bubble.bot { background: rgba(20, 25, 40, 0.55); border: 1px solid rgba(59, 130, 246, 0.3); color: white; align-self: flex-end; width: 100%; max-width: 90%; }
        .msg-bubble b { display: block; font-size: 10px; margin-bottom: 4px; opacity: 0.7; text-transform: uppercase; }
        .msg-actions { position: absolute; top: 6px; right: 6px; opacity: 0; transition: 0.2s; display: flex; gap: 4px; }
        .msg-bubble:hover .msg-actions { opacity: 1; }
        .msg-action-btn { background: rgba(255,255,255,0.1); border: none; color: #fff; padding: 4px 6px; border-radius: 6px; font-size: 11px; cursor: pointer; }
        .typing-dots { display: inline-flex; gap: 3px; vertical-align: middle; }
        .typing-dots span { width: 6px; height: 6px; border-radius: 50%; background: #38BDF8; display: inline-block; animation: typingBounce 1.4s infinite ease-in-out both; }
        .typing-dots span:nth-child(1) { animation-delay: -0.32s; }
        .typing-dots span:nth-child(2) { animation-delay: -0.16s; }
        @keyframes typingBounce { 0%, 80%, 100% { transform: scale(0.6); opacity: 0.5; } 40% { transform: scale(1); opacity: 1; } }
        pre { background: rgba(4,4,6,0.6) !important; border: 1px solid var(--lg-border-soft); border-radius: 10px; padding: 10px; margin: 8px 0; overflow-x: auto; }
        code { font-family: 'Consolas', monospace; font-size: 12px; color: #38BDF8; }
        .code-header { display: flex; justify-content: space-between; align-items: center; font-size: 11px; color: var(--text-muted); margin-bottom: 4px; }
        .copy-code-btn { background: rgba(255,255,255,0.1); border: none; color: #fff; padding: 3px 6px; border-radius: 6px; font-size: 10px; cursor: pointer; }
        .control-panel { padding: 12px 16px; border-top: 1px solid var(--lg-border-soft); display: flex; gap: 10px; align-items: center; width: 100%; border-radius: 0 0 22px 22px; }
        .input-wrapper { border-radius: 14px; display: flex; align-items: center; padding: 0 10px; flex: 1; min-width: 0; }
        .input-wrapper input { background: transparent; border: none; outline: none; color: white; padding: 10px 6px; font-size: 13px; width: 100%; }
        .upload-icon-btn { background: transparent; border: none; color: var(--text-muted); cursor: pointer; padding: 4px; display: flex; align-items: center; }
        .upload-icon-btn:hover { color: var(--accent1); }
        .send-btn { background: var(--primary-gradient); color: white; border: none; padding: 10px 18px; border-radius: 14px; font-weight: 600; font-size: 13px; cursor: pointer; display: flex; align-items: center; gap: 6px; }
        .avatar-btn { width: 34px; height: 34px; border-radius: 10px; background: var(--primary-gradient); color: #fff; display: flex; align-items: center; justify-content: center; font-weight: 700; cursor: pointer; overflow: hidden; }
        .avatar-btn img { width: 100%; height: 100%; object-fit: cover; }
        @media(max-width: 850px) {
            .app-layout { padding: 8px; gap: 8px; }
            .sidebar { position: fixed; top: 8px; left: 8px; height: calc(100dvh - 16px); z-index: 1000; box-shadow: 20px 0 60px rgba(0,0,0,0.9); transform: translateX(-110%); transition: transform 0.3s ease; }
            .sidebar.mobile-open { transform: translateX(0); }
            .menu-toggle-btn { display: flex; }
            .main-workspace { height: calc(100dvh - 16px); }
            .send-btn span { display: none; }
        }
        .sidebar-overlay { display: none; position: fixed; inset: 0; background: rgba(0,0,0,0.6); z-index: 999; }
        .sidebar-overlay.active { display: block; }
        ::-webkit-scrollbar { width: 4px; height: 4px; }
        ::-webkit-scrollbar-thumb { background: rgba(255, 255, 255, 0.12); border-radius: 10px; }
        .color-picker-row, .range-row { display: flex; align-items: center; gap: 10px; margin-bottom: 8px; padding: 6px 10px; border-radius: 10px; }
        .color-picker-row label, .range-row label { flex: 1; font-size: 11px; color: var(--text-muted); }
        .color-picker-row input[type="color"] { width: 40px; height: 30px; border: 1px solid var(--lg-border-soft); border-radius: 8px; background: transparent; cursor: pointer; }
        .range-row input[type="range"] { flex: 1; accent-color: var(--accent1); }
        .range-row span { font-size: 11px; color: #fff; min-width: 30px; text-align: right; }
        .logo-picker { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; margin-top: 8px; }
        .logo-option { border-radius: 12px; padding: 10px; display: flex; align-items: center; justify-content: center; cursor: pointer; color: #fff; }
        .logo-option.selected { border-color: var(--accent1) !important; background: rgba(59,130,246,0.15) !important; }
        .music-item, .user-item, .ban-item, .notif-item { display: flex; align-items: center; gap: 8px; padding: 8px 10px; border-radius: 10px; margin-bottom: 6px; font-size: 12px; }
        .music-item .name, .user-item .name, .ban-item .name { flex: 1; min-width: 0; color: #fff; }
        .user-item .name small { color: var(--text-muted); font-size: 10px; display: block; }
        .del-btn, .usr-btn { background: rgba(239,68,68,0.15); border: 1px solid rgba(239,68,68,0.3); color: #F87171; padding: 4px 8px; border-radius: 8px; font-size: 10px; cursor: pointer; }
        .usr-btn { background: rgba(255,255,255,0.05); border-color: var(--lg-border-soft); color: #fff; }
        .admin-badge { font-size: 9px; padding: 2px 6px; background: rgba(52,211,153,0.15); color: #34D399; border-radius: 6px; }
        .toggle-row { display:flex; align-items:center; gap:10px; padding:10px; border-radius: 12px; }
        .toggle-row label { flex:1; font-size:12px; color:#fff; display:flex; align-items:center; gap:6px; }
        .toggle-row input[type="checkbox"] { width:20px; height:20px; accent-color:var(--accent1); cursor:pointer; }
        .toast { position: fixed; top: 20px; left: 50%; transform: translateX(-50%) translateY(-100px); color: #fff; padding: 14px 22px; border-radius: 16px; font-size: 14px; font-weight: 500; z-index: 9999; box-shadow: 0 10px 40px rgba(0,0,0,0.6); transition: transform 0.35s var(--tx-bounce); max-width: 90vw; text-align: center; border: 1px solid var(--lg-border-soft); background: rgba(15,23,42,0.95); backdrop-filter: blur(20px); }
        .toast.show { transform: translateX(-50%) translateY(0); }
        .toast.success { border-color: #34D399 !important; }
        .toast.error { border-color: #F87171 !important; }
        .tab-buttons { display: flex; gap: 6px; margin-bottom: 14px; padding: 4px; border-radius: 12px; background: rgba(0,0,0,0.2); }
        .tab-btn { flex: 1; padding: 8px; text-align: center; font-size: 11px; font-weight: 600; color: var(--text-muted); cursor: pointer; border-radius: 8px; }
        .tab-btn.active { background: rgba(255,255,255,0.1) !important; color: #fff !important; }
        .loading-chats { text-align: center; padding: 20px; font-size: 11px; color: var(--text-muted); }
        .notif-panel { position: fixed; top: 70px; right: 20px; width: 340px; max-width: 90vw; max-height: 500px; background: rgba(15, 23, 42, 0.95); backdrop-filter: blur(30px); border: 1px solid var(--lg-border-soft); border-radius: 18px; padding: 16px; z-index: 1200; overflow-y: auto; display: none; box-shadow: 0 20px 60px rgba(0,0,0,0.7); }
        .notif-panel.open { display: block; animation: modalIn 0.3s var(--tx-smooth); }
        .notif-item { flex-direction: column; align-items: flex-start; gap: 4px; padding: 10px; }
        .notif-item.unread { background: rgba(59,130,246,0.1); border-left: 3px solid var(--accent1); }
        .notif-item .n-title { font-size: 12px; font-weight: 600; color: #fff; }
        .notif-item .n-msg { font-size: 11px; color: #CBD5E1; }
        .notif-item .n-time { font-size: 9px; color: var(--text-muted); }
        .file-preview-chip { display: inline-flex; align-items: center; gap: 6px; background: rgba(56,189,248,0.1); border: 1px solid rgba(56,189,248,0.3); padding: 4px 10px; border-radius: 8px; font-size: 11px; color: #38BDF8; margin: 6px 16px 0; }
        .qr-display { text-align: center; padding: 16px; background: #fff; border-radius: 12px; margin: 10px 0; }
        .qr-display img { max-width: 220px; }
    </style>
</head>
<body>

    <img id="bgMedia" alt="">
    <video id="bgVideo" autoplay muted loop playsinline></video>
    <div id="bgOverlay"></div>
    <audio id="bgMusic" loop></audio>

    <!-- AUTH OVERLAY -->
    <div id="authOverlay" class="{% if logged_in %}hidden{% endif %}">
        <div class="auth-card lg">
            <div style="text-align: center; margin-bottom: 20px;">
                <h2 style="font-size: 18px; font-weight: 700; color: #fff;">Crsz Bot Studio</h2>
                <p style="font-size: 12px; color: var(--text-muted);">Devam etmek için giriş yapın veya kayıt olun</p>
            </div>
            <div class="auth-tabs">
                <div class="auth-tab active" id="tabLoginBtn" onclick="switchAuthTab('login')">Giriş Yap</div>
                <div class="auth-tab" id="tabRegisterBtn" onclick="switchAuthTab('register')">Kayıt Ol</div>
            </div>
            <div id="emailFieldContainer" style="display: none;">
                <input type="email" id="authEmail" class="auth-input" placeholder="E-Posta Adresi">
                <label class="auth-label">
                    <i data-lucide="bot" width="13" height="13" style="color: var(--accent1);"></i>
                    Botun sana hangi dilde yanıt vermesini istersin?
                </label>
                <select id="authLanguage" class="lang-select">
                    {% for code, name in supported_languages.items() %}
                    <option value="{{ code }}" {% if code == 'tr' %}selected{% endif %}>{{ name }} ({{ code.upper() }})</option>
                    {% endfor %}
                </select>
            </div>
            <input type="text" id="authUsername" class="auth-input" placeholder="Kullanıcı Adı" autocomplete="username">
            <input type="password" id="authPassword" class="auth-input" placeholder="Şifre" autocomplete="current-password">
            <div id="totpFieldContainer" style="display: none;">
                <label class="auth-label">
                    <i data-lucide="shield" width="13" height="13" style="color: #34D399;"></i>
                    2FA Kodu (Google Authenticator)
                </label>
                <input type="text" id="authTotp" class="auth-input" placeholder="6 haneli kod" maxlength="6" inputmode="numeric">
            </div>
            <button class="auth-btn" id="authSubmitBtn" onclick="handleAuth()">Giriş Yap</button>
            <a class="auth-link" onclick="openForgotPassword()">Şifremi Unuttum</a>
        </div>
    </div>

    <!-- FORGOT PASSWORD MODAL -->
    <div class="modal-overlay" id="forgotModal">
        <div class="modal-card" style="max-width: 400px;">
            <h3><i data-lucide="key-round" width="16" height="16" style="color: var(--accent1);"></i> Şifremi Unuttum</h3>
            <p style="font-size: 12px; color: var(--text-muted); margin-bottom: 12px;">Kullanıcı adı veya e-posta adresini gir. Sıfırlama linkini göndereyim.</p>
            <input type="text" id="forgotIdentifier" class="auth-input" placeholder="Kullanıcı adı veya e-posta">
            <button class="auth-btn" onclick="submitForgot()">Sıfırlama Linki Gönder</button>
            <button class="auth-btn-secondary" onclick="closeModal('forgotModal')">İptal</button>
        </div>
    </div>

    <!-- PROFILE MODAL -->
    <div class="modal-overlay" id="profileModal">
        <div class="modal-card">
            <h3><i data-lucide="user-cog" width="16" height="16" style="color: var(--accent1);"></i> Profil ve Ayarlar</h3>
            <label class="modal-label">Avatar</label>
            <div style="display:flex; align-items:center; gap:12px;">
                <div class="avatar-btn" id="profileAvatarBtn" style="width:60px; height:60px; border-radius:16px;">
                    {% if user_avatar %}<img src="/uploads/avatars/{{ user_avatar }}" alt="">{% else %}{{ current_user[0]|upper if current_user else '?' }}{% endif %}
                </div>
                <input type="file" id="avatarInput" accept="image/*" style="display:none" onchange="uploadAvatar(event)">
                <button class="auth-btn" style="width:auto; padding:8px 14px; font-size:12px;" onclick="document.getElementById('avatarInput').click()">Değiştir</button>
            </div>

            <label class="modal-label" style="margin-top:14px;">Bot Adı</label>
            <input type="text" id="modalBotName" class="auth-input" value="{{ app_state.bot_name }}">

            <label class="modal-label">Botun Sana Yanıt Vereceği Dil</label>
            <select id="modalLanguage" class="lang-select">
                {% for code, name in supported_languages.items() %}
                <option value="{{ code }}" {% if code == user_language %}selected{% endif %}>{{ name }} ({{ code.upper() }})</option>
                {% endfor %}
            </select>

            <!-- ŞİFRE DEĞİŞTİRME -->
            <div style="margin-top: 16px; padding-top: 14px; border-top: 1px solid var(--lg-border-soft);">
                <h4 style="font-size: 13px; color: #fff; margin-bottom: 10px; display: flex; align-items: center; gap: 6px;">
                    <i data-lucide="lock" width="14" height="14" style="color: var(--accent1);"></i> Şifre Değiştir
                </h4>
                <input type="password" id="currentPassword" class="auth-input" placeholder="Mevcut şifre">
                <input type="password" id="newPassword" class="auth-input" placeholder="Yeni şifre (min 6)">
                <input type="password" id="newPassword2" class="auth-input" placeholder="Yeni şifre tekrar">
                <button class="auth-btn" onclick="changePassword()">Şifreyi Güncelle</button>
            </div>

            <!-- 2FA -->
            <div style="margin-top: 16px; padding-top: 14px; border-top: 1px solid var(--lg-border-soft);">
                <h4 style="font-size: 13px; color: #fff; margin-bottom: 10px; display: flex; align-items: center; gap: 6px;">
                    <i data-lucide="shield-check" width="14" height="14" style="color: #34D399;"></i> İki Faktörlü Doğrulama (2FA)
                </h4>
                <div id="twofaStatusText" style="font-size: 12px; color: var(--text-muted); margin-bottom: 10px;">
                    Durum: <b id="twofaStatus">...</b>
                </div>
                <div id="twofaSetupArea" style="display: none;">
                    <div class="qr-display" id="qrDisplay"></div>
                    <p style="font-size: 11px; color: var(--text-muted); margin-bottom: 8px;">Google Authenticator ile QR kodunu tara ve 6 haneli kodu gir:</p>
                    <input type="text" id="twofaCode" class="auth-input" placeholder="6 haneli kod" maxlength="6" inputmode="numeric">
                    <input type="hidden" id="twofaSecret">
                </div>
                <button class="auth-btn" id="twofaMainBtn" onclick="toggle2FA()">2FA Kur</button>
            </div>

            <div class="toggle-row" style="margin-top: 10px;">
                <label><i data-lucide="brain" width="14" height="14"></i> Bot Hafızasını Temizle</label>
                <button class="auth-btn" style="width:auto; padding:8px 14px; font-size:12px; background: rgba(239,68,68,0.15); color: #F87171; border: 1px solid rgba(239,68,68,0.3);" onclick="clearBotMemory()">Temizle</button>
            </div>

            <div style="display: flex; gap: 8px; margin-top: 14px;">
                <button class="auth-btn" onclick="saveProfile()">Kaydet</button>
                <button class="auth-btn-secondary" onclick="closeModal('profileModal')">İptal</button>
            </div>
            <div style="margin-top: 14px; border-top: 1px solid var(--lg-border-soft); padding-top: 12px;">
                <button class="auth-btn" style="background: rgba(239,68,68,0.15); color: #F87171; border: 1px solid rgba(239,68,68,0.3);" onclick="logout()">
                    <i data-lucide="log-out" width="14" height="14"></i> Çıkış Yap
                </button>
            </div>
        </div>
    </div>

    <!-- ADMIN MODAL -->
    <div class="modal-overlay" id="adminModal">
        <div class="modal-card">
            <h3><i data-lucide="shield-check" width="16" height="16" style="color: #34D399;"></i> Admin Panel</h3>
            <div class="tab-buttons">
                <div class="tab-btn active" onclick="switchAdminTab('theme', this)">Tema</div>
                <div class="tab-btn" onclick="switchAdminTab('users', this)">Kullanıcılar</div>
                <div class="tab-btn" onclick="switchAdminTab('bans', this)">Banlar</div>
                <div class="tab-btn" onclick="switchAdminTab('notif', this)">Bildirim</div>
            </div>

            <div id="adminTab-theme">
                <label class="modal-label">Site Logosu</label>
                <div class="logo-picker" id="logoPicker">
                    <div class="logo-option" data-icon="zap"><i data-lucide="zap" width="20" height="20"></i></div>
                    <div class="logo-option" data-icon="bot"><i data-lucide="bot" width="20" height="20"></i></div>
                    <div class="logo-option" data-icon="brain"><i data-lucide="brain" width="20" height="20"></i></div>
                    <div class="logo-option" data-icon="sparkles"><i data-lucide="sparkles" width="20" height="20"></i></div>
                    <div class="logo-option" data-icon="cpu"><i data-lucide="cpu" width="20" height="20"></i></div>
                    <div class="logo-option" data-icon="code"><i data-lucide="code" width="20" height="20"></i></div>
                    <div class="logo-option" data-icon="terminal"><i data-lucide="terminal" width="20" height="20"></i></div>
                    <div class="logo-option" data-icon="rocket"><i data-lucide="rocket" width="20" height="20"></i></div>
                </div>

                <label class="modal-label">Arka Plan Medya</label>
                <input type="file" id="themeBgMedia" accept="image/*,video/*" style="display:none" onchange="uploadBackground(event)">
                <div style="display:flex; gap:6px; margin-bottom:8px;">
                    <button class="auth-btn" style="background: rgba(255,255,255,0.1);" onclick="document.getElementById('themeBgMedia').click()"><i data-lucide="upload" width="14" height="14"></i> Medya Yükle</button>
                    <button class="auth-btn" style="background: rgba(255,255,255,0.1);" onclick="clearBgMedia()">Temizle</button>
                </div>

                <label class="modal-label">Müzik (Max 3)</label>
                <input type="file" id="themeMusic" accept="audio/*" style="display:none" onchange="uploadMusic(event)">
                <button class="auth-btn" style="background: rgba(56,189,248,0.15); color: #38BDF8; border: 1px solid rgba(56,189,248,0.3); margin-bottom:8px;" onclick="document.getElementById('themeMusic').click()"><i data-lucide="music" width="14" height="14"></i> Müzik Yükle</button>
                <div id="musicListContainer">
                    {% for m in music_list %}
                    <div class="music-item"><i data-lucide="music-2" width="14" height="14" style="color:#38BDF8;"></i><span class="name">{{ m.original_name }}</span><button class="del-btn" onclick="deleteMusic({{ m.id }})">Sil</button></div>
                    {% endfor %}
                </div>

                <label class="modal-label">Arka Plan Rengi</label>
                <div class="color-picker-row"><label>Ana Arka Plan</label><input type="color" id="themeBgDeep" value="{{ app_state.theme.bg_deep }}"></div>
                <label class="modal-label">Gradient Renkleri</label>
                <div class="color-picker-row"><label>Renk 1</label><input type="color" id="themeAccent1" value="{{ app_state.theme.accent1 }}"></div>
                <div class="color-picker-row"><label>Renk 2</label><input type="color" id="themeAccent2" value="{{ app_state.theme.accent2 }}"></div>
                <div class="color-picker-row"><label>Renk 3</label><input type="color" id="themeAccent3" value="{{ app_state.theme.accent3 }}"></div>

                <label class="modal-label">Cam Yoğunluğu</label>
                <div class="range-row"><input type="range" id="themeGlassOpacity" min="0" max="0.3" step="0.01" value="{{ app_state.theme.glass_opacity }}"><span id="glassOpacityVal">{{ app_state.theme.glass_opacity }}</span></div>
                <label class="modal-label">Aurora Yoğunluğu</label>
                <div class="range-row"><input type="range" id="themeAuroraOpacity" min="0" max="0.6" step="0.01" value="{{ app_state.theme.aurora_opacity }}"><span id="auroraOpacityVal">{{ app_state.theme.aurora_opacity }}</span></div>

                <div class="toggle-row"><label>Bakım Modu</label><input type="checkbox" id="maintenanceToggle" onchange="toggleMaintenance(this.checked)"></div>
                <div class="toggle-row"><label>Click Sesi</label><input type="checkbox" id="clickSoundToggle" checked onchange="toggleClickSound(this.checked)"></div>

                <div style="display: flex; gap: 8px; margin-top: 16px;">
                    <button class="auth-btn" onclick="saveTheme()">Kaydet</button>
                    <button class="auth-btn-secondary" onclick="resetTheme()">Sıfırla</button>
                </div>
            </div>

            <div id="adminTab-users" style="display:none;"><div id="usersList">Yükleniyor...</div></div>

            <div id="adminTab-bans" style="display:none;">
                <h4 style="font-size:13px;color:#fff;margin-bottom:10px;">IP Banla</h4>
                <input type="text" id="banIpInput" class="auth-input" placeholder="IP adresi (örn: 1.2.3.4)">
                <input type="text" id="banReasonInput" class="auth-input" placeholder="Sebep (opsiyonel)">
                <button class="auth-btn" onclick="banIP()">IP Banla</button>
                <h4 style="font-size:13px;color:#fff;margin:16px 0 10px;">Banlı IP'ler</h4>
                <div id="bansList">Yükleniyor...</div>
            </div>

            <div id="adminTab-notif" style="display:none;">
                <h4 style="font-size:13px;color:#fff;margin-bottom:10px;">Bildirim Gönder</h4>
                <input type="text" id="notifTargetUser" class="auth-input" placeholder="Hedef kullanıcı adı">
                <input type="text" id="notifTitle" class="auth-input" placeholder="Başlık">
                <textarea id="notifMessage" class="auth-input" placeholder="Mesaj" rows="4" style="resize: vertical;"></textarea>
                <button class="auth-btn" onclick="sendNotif()">Gönder</button>
            </div>

            <div style="display: flex; gap: 8px; margin-top: 16px;">
                <button class="auth-btn-secondary" onclick="closeModal('adminModal')">Kapat</button>
            </div>
        </div>
    </div>

    <!-- NOTIFICATIONS PANEL -->
    <div class="notif-panel" id="notifPanel">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
            <h3 style="font-size: 14px; color: #fff;">Bildirimler</h3>
            <button class="msg-action-btn" onclick="markAllRead()">Tümünü Okundu İşaretle</button>
        </div>
        <div id="notifList"><div class="loading-chats">Yükleniyor...</div></div>
    </div>

    <div class="sidebar-overlay" id="sidebarOverlay" onclick="toggleMobileSidebar()"></div>

    <div class="aurora-bg" id="auroraBg">
        <div class="aurora-blob blob-1"></div>
        <div class="aurora-blob blob-2"></div>
        <div class="aurora-blob blob-3"></div>
    </div>

    <div class="app-layout">
        <div class="sidebar lg" id="sidebar">
            <div class="logo-area">
                <div class="logo-icon"><i data-lucide="{{ app_state.logo_icon }}" width="16" height="16" id="sidebarLogoIcon"></i></div>
                <div class="logo-text">
                    <h1 id="sidebarBotName">{{ app_state.bot_name }}</h1>
                    <p>AI Studio</p>
                </div>
            </div>
            <button class="new-chat-btn" onclick="startNewChat()"><i data-lucide="plus" width="13" height="13"></i> Yeni Sohbet</button>
            <div class="quick-stats">
                <div class="stat-card"><div class="stat-value" id="totalReplies">0</div><div class="stat-label">Cevap</div></div>
                <div class="stat-card"><div class="stat-value" id="totalChats">0</div><div class="stat-label">Sohbet</div></div>
            </div>
            <div class="search-box">
                <i data-lucide="search" width="12" height="12"></i>
                <input type="text" id="chatSearchInput" placeholder="Sohbet ara..." oninput="searchChatsDebounced()">
            </div>
            <div style="font-size: 9px; text-transform: uppercase; color: var(--text-muted);">Sohbetler</div>
            <div class="chat-history-list" id="chatHistoryList">
                <div class="loading-chats"><span class="spinner"></span> Yükleniyor...</div>
            </div>
            <div class="sidebar-footer">
                <button class="footer-btn" id="adminBtn" style="{% if not is_admin %}display: none;{% endif %} border-color: rgba(52, 211, 153, 0.4); color: #34D399;" onclick="openAdminPanel()"><i data-lucide="shield-check" width="13" height="13"></i> Admin Panel</button>
                <button class="footer-btn" onclick="openModal('profileModal')"><i data-lucide="user-cog" width="13" height="13" style="color: var(--accent1);"></i> Profil & Ayarlar</button>
            </div>
        </div>

        <div class="main-workspace lg">
            <header>
                <div style="display: flex; align-items: center; gap: 10px; min-width: 0;">
                    <button class="menu-toggle-btn" onclick="toggleMobileSidebar()"><i data-lucide="menu" width="16" height="16"></i></button>
                    <h2><i data-lucide="terminal" width="14" height="14" style="color: var(--accent1);"></i> AI Stüdyosu</h2>
                </div>
                <div style="display: flex; align-items: center; gap: 8px;">
                    <button class="icon-action-btn" onclick="toggleNotifPanel()" title="Bildirimler" id="notifBtn">
                        <i data-lucide="bell" width="16" height="16"></i>
                        <span class="badge" id="notifBadge" style="{% if unread_count == 0 %}display:none;{% endif %}">{{ unread_count }}</span>
                    </button>
                    <button class="icon-action-btn" onclick="toggleColorMode()" title="Tema" id="themeToggleBtn"><i data-lucide="sun-moon" width="16" height="16"></i></button>
                    <button class="icon-action-btn" id="musicToggleBtn" onclick="toggleMusic()" title="Müzik"><i data-lucide="volume-2" width="16" height="16" id="musicIcon"></i></button>
                    <div class="status-badge"><div class="status-dot"></div> Aktif</div>
                </div>
            </header>
            <div class="chat-container" id="chatBox">
                <div class="msg-bubble user">
                    <b>Sistem</b>
                    <div style="display: flex; align-items: flex-start; gap: 8px; margin-top: 6px;">
                        <i data-lucide="sparkles" width="16" height="16" style="color: var(--accent1); flex-shrink: 0;"></i>
                        <span>Sistem hazır! PDF/DOCX/TXT dosya yükleyebilir, görsel analiz yaptırabilir, sohbet araması kullanabilirsin.</span>
                    </div>
                </div>
            </div>
            <div id="imagePreviewContainer" style="padding: 0 16px; display: none;">
                <div class="file-preview-chip"><span>📷 Fotoğraf Eklendi</span> <span onclick="removeImage()" style="cursor:pointer; font-weight:bold;">×</span></div>
            </div>
            <div id="filePreviewContainer" style="padding: 0 16px; display: none;">
                <div class="file-preview-chip">
                    <i data-lucide="file-text" width="12" height="12"></i>
                    <span id="filePreviewName">Dosya</span>
                    <span id="filePreviewSize" style="opacity: 0.7;"></span>
                    <span onclick="removeFile()" style="cursor:pointer; font-weight:bold;">×</span>
                </div>
            </div>
            <div class="control-panel">
                <input type="file" id="imageInput" accept="image/*" style="display:none;" onchange="handleImageSelect(event)">
                <input type="file" id="fileInput" accept=".pdf,.docx,.txt" style="display:none;" onchange="handleFileSelect(event)">
                <button class="upload-icon-btn" onclick="document.getElementById('imageInput').click()" title="Fotoğraf"><i data-lucide="image" width="18" height="18"></i></button>
                <button class="upload-icon-btn" onclick="document.getElementById('fileInput').click()" title="Dosya (PDF/DOCX/TXT)"><i data-lucide="file-text" width="18" height="18"></i></button>
                <button class="upload-icon-btn" onclick="toggleVoiceInput()" title="Sesli Yaz" id="voiceBtn"><i data-lucide="mic" width="18" height="18"></i></button>
                <div class="input-wrapper">
                    <input type="text" id="message" placeholder="Mesaj yaz, fotoğraf/dosya yükle ya da 'araştır' de..." onkeydown="if(event.key==='Enter') sendMessage()">
                </div>
                <button class="send-btn" onclick="sendMessage()"><span>Gönder</span> <i data-lucide="send" width="13" height="13"></i></button>
            </div>
        </div>
    </div>

    <script>
        lucide.createIcons();
        let authMode = 'login';
        let chats = [];
        let activeChatIndex = 0;
        let selectedBase64Image = null;
        let selectedFileText = null;
        let selectedFileName = '';
        let isAdmin = {% if is_admin %}true{% else %}false{% endif %};
        let currentUser = "{{ current_user }}";
        let loggedIn = {% if logged_in %}true{% else %}false{% endif %};
        let selectedLogoIcon = "{{ app_state.logo_icon }}";
        let musicMuted = false;
        let musicPlaylist = [];
        let currentMusicIndex = 0;
        let isInitialLoad = true;
        let animatingMessageIndex = -1;
        let clickSoundEnabled = true;
        let has2FA = {% if has_2fa %}true{% else %}false{% endif %};
        let searchTimer = null;

        const DEFAULT_THEME = {
            bg_deep: "#07070a", accent1: "#3B82F6", accent2: "#8B5CF6", accent3: "#06B6D4",
            glass_opacity: 0.03, aurora_opacity: 0.25
        };

        if ('serviceWorker' in navigator) {
            navigator.serviceWorker.register('/service-worker.js').catch(e => console.log('SW:', e));
        }

        let audioCtx = null;
        function initAudioCtx() {
            if (!audioCtx) { try { audioCtx = new (window.AudioContext || window.webkitAudioContext)(); } catch (e) {} }
            return audioCtx;
        }
        function playClickSound() {
            if (!clickSoundEnabled) return;
            const ctx = initAudioCtx(); if (!ctx) return;
            if (ctx.state === 'suspended') ctx.resume();
            const now = ctx.currentTime;
            const osc = ctx.createOscillator(); const gain = ctx.createGain(); const filter = ctx.createBiquadFilter();
            osc.type = 'sine'; osc.frequency.setValueAtTime(900, now); osc.frequency.exponentialRampToValueAtTime(420, now + 0.06);
            filter.type = 'lowpass'; filter.frequency.setValueAtTime(2200, now); filter.Q.value = 0.9;
            gain.gain.setValueAtTime(0.0001, now); gain.gain.exponentialRampToValueAtTime(0.055, now + 0.006);
            gain.gain.exponentialRampToValueAtTime(0.0001, now + 0.08);
            osc.connect(filter); filter.connect(gain); gain.connect(ctx.destination);
            osc.start(now); osc.stop(now + 0.09);
        }
        document.body.addEventListener('click', function wakeAudio() {
            const ctx = initAudioCtx();
            if (ctx && ctx.state === 'suspended') ctx.resume();
        }, { once: true });

        function toggleClickSound(enabled) {
            clickSoundEnabled = !!enabled;
            localStorage.setItem('crsz_click_sound', clickSoundEnabled ? '1' : '0');
            if (clickSoundEnabled) playClickSound();
        }
        (function loadClickSoundPref() {
            const saved = localStorage.getItem('crsz_click_sound');
            if (saved === '0') clickSoundEnabled = false;
            setTimeout(() => {
                const tog = document.getElementById('clickSoundToggle');
                if (tog) tog.checked = clickSoundEnabled;
            }, 300);
        })();

        (function() {
            const savedMode = localStorage.getItem('crsz_theme_mode') || 'dark';
            if (savedMode === 'light') setTimeout(() => applyColorMode('light'), 50);
        })();

        function applyColorMode(mode) {
            const root = document.documentElement; const body = document.body;
            if (mode === 'light') {
                root.style.setProperty('--bg-deep', '#f1f5f9');
                root.style.setProperty('--text-main', '#0f172a');
                root.style.setProperty('--text-muted', '#475569');
                root.style.setProperty('--lg-tint', 'rgba(255,255,255,0.55)');
                root.style.setProperty('--lg-border-soft', 'rgba(15,23,42,0.10)');
                body.style.color = '#0f172a';
                let ls = document.getElementById('lightThemeOverride');
                if (!ls) { ls = document.createElement('style'); ls.id = 'lightThemeOverride'; document.head.appendChild(ls); }
                ls.textContent = `body{background:#f1f5f9!important;color:#0f172a!important}.logo-text h1,header h2{color:#0f172a!important}.logo-text p,.stat-card .stat-label,.history-item{color:#64748b!important}.stat-card .stat-value{color:#0f172a!important}.msg-bubble.user{background:rgba(255,255,255,0.75)!important;color:#0f172a!important}.msg-bubble.bot{background:rgba(30,41,59,0.9)!important;color:#f8fafc!important}.input-wrapper input{color:#0f172a!important}.modal-card h3,.notif-item .n-title{color:#0f172a!important}.auth-input,.lang-select{color:#0f172a!important;background:rgba(255,255,255,0.6)!important}.music-item .name,.user-item .name{color:#0f172a!important}.notif-panel{background:rgba(255,255,255,0.95)!important}.notif-item .n-msg{color:#334155!important}.notif-item.unread{background:rgba(59,130,246,0.15)!important}`;
            } else {
                const ol = document.getElementById('lightThemeOverride');
                if (ol) ol.remove();
                root.style.setProperty('--bg-deep', '{{ app_state.theme.bg_deep }}');
                root.style.setProperty('--text-main', '#F8FAFC');
                root.style.setProperty('--text-muted', '#94A3B8');
                root.style.setProperty('--lg-tint', 'rgba(255, 255, 255, 0.04)');
                root.style.setProperty('--lg-border-soft', 'rgba(255, 255, 255, 0.08)');
                body.style.color = '#F8FAFC';
            }
        }

        function toggleColorMode() {
            const current = localStorage.getItem('crsz_theme_mode') || 'dark';
            const next = current === 'dark' ? 'light' : 'dark';
            localStorage.setItem('crsz_theme_mode', next);
            applyColorMode(next);
            showToast(next === 'dark' ? 'Koyu tema' : 'Açık tema', 'success');
        }

        function showToast(message, type = 'info') {
            const ex = document.querySelector('.toast'); if (ex) ex.remove();
            const t = document.createElement('div');
            t.className = 'toast ' + type; t.innerText = message;
            document.body.appendChild(t);
            requestAnimationFrame(() => t.classList.add('show'));
            setTimeout(() => { t.classList.remove('show'); setTimeout(() => t.remove(), 400); }, 3000);
        }

        function openModal(id) { document.getElementById(id).classList.add('active'); }
        function closeModal(id) { document.getElementById(id).classList.remove('active'); }

        // ============ AUTH ============
        function switchAuthTab(mode) {
            authMode = mode;
            const ec = document.getElementById('emailFieldContainer');
            const sb = document.getElementById('authSubmitBtn');
            const lt = document.getElementById('tabLoginBtn');
            const rt = document.getElementById('tabRegisterBtn');
            const tfa = document.getElementById('totpFieldContainer');
            if (mode === 'register') {
                ec.style.display = 'block'; sb.innerText = 'Kayıt Ol';
                rt.classList.add('active'); lt.classList.remove('active'); tfa.style.display = 'none';
            } else {
                ec.style.display = 'none'; sb.innerText = 'Giriş Yap';
                lt.classList.add('active'); rt.classList.remove('active');
            }
        }

        async function handleAuth() {
            const username = document.getElementById('authUsername').value.trim();
            const email = document.getElementById('authEmail').value.trim();
            const password = document.getElementById('authPassword').value.trim();
            const language = document.getElementById('authLanguage').value;
            const totp = document.getElementById('authTotp').value.trim();
            if (!username || !password) { showToast("Kullanıcı adı ve şifre zorunlu!", "error"); return; }
            const btn = document.getElementById('authSubmitBtn');
            const ot = btn.innerText; btn.innerText = "İşleniyor..."; btn.disabled = true;
            try {
                const res = await fetch('/auth', {
                    method: 'POST', headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ action: authMode, username, email, password, language, totp_code: totp })
                });
                const data = await res.json();
                if (data.status === '2fa_required') {
                    document.getElementById('totpFieldContainer').style.display = 'block';
                    showToast("2FA kodunu gir.", "info");
                } else if (data.status === 'success') {
                    showToast("Giriş başarılı!", "success");
                    setTimeout(() => window.location.reload(), 600);
                } else {
                    showToast(data.message || "Hata", "error");
                }
            } catch (e) { showToast("Bağlantı hatası", "error"); }
            finally { btn.innerText = ot; btn.disabled = false; }
        }

        // ============ FORGOT PASSWORD ============
        function openForgotPassword() { openModal('forgotModal'); }

        async function submitForgot() {
            const id = document.getElementById('forgotIdentifier').value.trim();
            if (!id) { showToast("Kullanıcı adı veya e-posta gir", "error"); return; }
            try {
                const res = await fetch('/forgot-password', {
                    method: 'POST', headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ identifier: id })
                });
                const data = await res.json();
                showToast(data.message, data.status === 'success' ? 'success' : 'error');
                if (data.status === 'success') closeModal('forgotModal');
            } catch (e) { showToast("Bağlantı hatası", "error"); }
        }

        // ============ ŞİFRE DEĞİŞTİR ============
        async function changePassword() {
            const cur = document.getElementById('currentPassword').value;
            const np = document.getElementById('newPassword').value;
            const np2 = document.getElementById('newPassword2').value;
            if (!cur || !np) { showToast("Tüm alanlar zorunlu", "error"); return; }
            if (np !== np2) { showToast("Yeni şifreler uyuşmuyor", "error"); return; }
            if (np.length < 6) { showToast("Yeni şifre en az 6 karakter", "error"); return; }
            try {
                const res = await fetch('/change-password', {
                    method: 'POST', headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ current_password: cur, new_password: np })
                });
                const data = await res.json();
                showToast(data.message, data.status === 'success' ? 'success' : 'error');
                if (data.status === 'success') {
                    document.getElementById('currentPassword').value = '';
                    document.getElementById('newPassword').value = '';
                    document.getElementById('newPassword2').value = '';
                }
            } catch (e) { showToast("Hata", "error"); }
        }

        // ============ 2FA ============
        async function toggle2FA() {
            if (!has2FA) {
                // Kur
                try {
                    const res = await fetch('/2fa/setup', { method: 'POST' });
                    const data = await res.json();
                    if (data.status === 'success') {
                        document.getElementById('qrDisplay').innerHTML = `<img src="${data.qr}" alt="QR">`;
                        document.getElementById('twofaSecret').value = data.secret;
                        document.getElementById('twofaSetupArea').style.display = 'block';
                        document.getElementById('twofaMainBtn').innerText = '2FA Doğrula ve Aktifleştir';
                        document.getElementById('twofaMainBtn').onclick = confirm2FA;
                    } else showToast(data.message, "error");
                } catch (e) { showToast("Hata", "error"); }
            } else {
                // Kapat
                const code = prompt("2FA kapatmak için mevcut 6 haneli kodu gir:");
                if (!code) return;
                try {
                    const res = await fetch('/2fa/disable', {
                        method: 'POST', headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({ code })
                    });
                    const data = await res.json();
                    if (data.status === 'success') { has2FA = false; update2FAUI(); showToast("2FA kapatıldı", "success"); }
                    else showToast(data.message, "error");
                } catch (e) { showToast("Hata", "error"); }
            }
        }

        async function confirm2FA() {
            const secret = document.getElementById('twofaSecret').value;
            const code = document.getElementById('twofaCode').value.trim();
            if (!code || code.length !== 6) { showToast("6 haneli kodu gir", "error"); return; }
            try {
                const res = await fetch('/2fa/enable', {
                    method: 'POST', headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ secret, code })
                });
                const data = await res.json();
                if (data.status === 'success') {
                    has2FA = true; update2FAUI();
                    document.getElementById('twofaSetupArea').style.display = 'none';
                    showToast("2FA aktif!", "success");
                } else showToast(data.message, "error");
            } catch (e) { showToast("Hata", "error"); }
        }

        function update2FAUI() {
            document.getElementById('twofaStatus').innerText = has2FA ? "Aktif" : "Kapalı";
            document.getElementById('twofaStatus').style.color = has2FA ? "#34D399" : "#F87171";
            const btn = document.getElementById('twofaMainBtn');
            btn.innerText = has2FA ? "2FA Kapat" : "2FA Kur";
            btn.onclick = toggle2FA;
        }

        // ============ SOHBET ARAMA ============
        function searchChatsDebounced() {
            clearTimeout(searchTimer);
            searchTimer = setTimeout(searchChats, 350);
        }

        async function searchChats() {
            const q = document.getElementById('chatSearchInput').value.trim();
            if (!loggedIn) return;
            try {
                const url = q ? `/chats/search?q=${encodeURIComponent(q)}` : '/chats';
                const res = await fetch(url);
                const data = await res.json();
                if (data.status === 'success') {
                    chats = data.chats.map(c => ({
                        id: c.id, title: c.title || "Sohbet",
                        messages: Array.isArray(c.messages) ? c.messages : []
                    }));
                    if (chats.length > 0) activeChatIndex = 0;
                    isInitialLoad = false;
                    renderChatHistory(); renderActiveChat(); updateStats();
                }
            } catch (e) { console.error(e); }
        }

        // ============ DOSYA YÜKLEME ============
        async function handleFileSelect(event) {
            const file = event.target.files[0];
            if (!file) return;
            const formData = new FormData();
            formData.append('file', file);
            showToast("Dosya işleniyor...", "info");
            try {
                const res = await fetch('/upload-document', { method: 'POST', body: formData });
                const data = await res.json();
                if (data.status === 'success') {
                    selectedFileText = data.preview;
                    selectedFileName = data.original_name;
                    // Tam metni fetch et
                    // Preview yerine direkt full text'i alacağız
                    // Şimdilik basit tutuyoruz
                    document.getElementById('filePreviewName').innerText = data.original_name;
                    document.getElementById('filePreviewSize').innerText = `(${data.char_count} karakter)`;
                    document.getElementById('filePreviewContainer').style.display = 'block';
                    // Tam metni de sakla (chat'e gönderilecek)
                    const fullRes = await fetch('/chats'); // dummy
                    selectedFileText = data.preview; // Şimdilik preview
                    showToast(`Dosya yüklendi: ${data.original_name}`, "success");
                } else showToast(data.message, "error");
            } catch (e) { showToast("Dosya yüklenemedi", "error"); }
        }

        function removeFile() {
            selectedFileText = null; selectedFileName = '';
            document.getElementById('filePreviewContainer').style.display = 'none';
            document.getElementById('fileInput').value = '';
        }

        // ============ BİLDİRİMLER ============
        async function toggleNotifPanel() {
            const p = document.getElementById('notifPanel');
            if (p.classList.contains('open')) { p.classList.remove('open'); return; }
            p.classList.add('open');
            await loadNotifications();
        }

        async function loadNotifications() {
            try {
                const res = await fetch('/notifications');
                const data = await res.json();
                if (data.status === 'success') {
                    const list = document.getElementById('notifList');
                    if (data.notifications.length === 0) {
                        list.innerHTML = '<div style="text-align:center;padding:20px;font-size:11px;color:var(--text-muted);">Bildirim yok</div>';
                    } else {
                        list.innerHTML = data.notifications.map(n => `
                            <div class="notif-item ${n.is_read ? '' : 'unread'}" onclick="markRead(${n.id})">
                                <div class="n-title">${escapeHtml(n.title)}</div>
                                <div class="n-msg">${escapeHtml(n.message)}</div>
                                <div class="n-time">${n.created_at || ''}</div>
                            </div>
                        `).join('');
                    }
                    updateNotifBadge(data.unread);
                }
            } catch (e) { console.error(e); }
        }

        async function markRead(id) {
            try {
                await fetch('/notifications/read/' + id, { method: 'POST' });
                loadNotifications();
            } catch (e) {}
        }

        async function markAllRead() {
            try {
                await fetch('/notifications/read-all', { method: 'POST' });
                loadNotifications();
            } catch (e) {}
        }

        function updateNotifBadge(count) {
            const badge = document.getElementById('notifBadge');
            if (count > 0) { badge.innerText = count; badge.style.display = 'inline-block'; }
            else { badge.style.display = 'none'; }
        }

        // ============ ADMIN: IP BAN ============
        async function banIP() {
            const ip = document.getElementById('banIpInput').value.trim();
            const reason = document.getElementById('banReasonInput').value.trim();
            if (!ip) { showToast("IP adresi gir", "error"); return; }
            try {
                const res = await fetch('/admin/ban', {
                    method: 'POST', headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ ip, reason })
                });
                const data = await res.json();
                showToast(data.message, data.status === 'success' ? 'success' : 'error');
                if (data.status === 'success') {
                    document.getElementById('banIpInput').value = '';
                    document.getElementById('banReasonInput').value = '';
                    loadBans();
                }
            } catch (e) { showToast("Hata", "error"); }
        }

        async function loadBans() {
            try {
                const res = await fetch('/admin/bans');
                const data = await res.json();
                if (data.status === 'success') {
                    const list = document.getElementById('bansList');
                    if (data.bans.length === 0) {
                        list.innerHTML = '<div style="text-align:center;padding:10px;font-size:11px;color:var(--text-muted);">Banlı IP yok</div>';
                    } else {
                        list.innerHTML = data.bans.map(b => `
                            <div class="ban-item">
                                <div class="name"><b>${escapeHtml(b.ip)}</b><br><small style="color:var(--text-muted);font-size:10px;">${escapeHtml(b.reason || 'Sebep yok')}</small></div>
                                <button class="usr-btn" onclick="unbanIP('${b.ip}')">Kaldır</button>
                            </div>
                        `).join('');
                    }
                }
            } catch (e) {}
        }

        async function unbanIP(ip) {
            try {
                await fetch('/admin/unban', {
                    method: 'POST', headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ ip })
                });
                loadBans();
                showToast("Ban kaldırıldı", "success");
            } catch (e) {}
        }

        // ============ ADMIN: BİLDİRİM GÖNDER ============
        async function sendNotif() {
            const username = document.getElementById('notifTargetUser').value.trim();
            const title = document.getElementById('notifTitle').value.trim() || "Bildirim";
            const message = document.getElementById('notifMessage').value.trim();
            if (!username || !message) { showToast("Kullanıcı ve mesaj gerekli", "error"); return; }
            try {
                const res = await fetch('/notifications/send', {
                    method: 'POST', headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ username, title, message })
                });
                const data = await res.json();
                showToast(data.message, data.status === 'success' ? 'success' : 'error');
                if (data.status === 'success') {
                    document.getElementById('notifTargetUser').value = '';
                    document.getElementById('notifTitle').value = '';
                    document.getElementById('notifMessage').value = '';
                }
            } catch (e) { showToast("Hata", "error"); }
        }

        // ============ GENEL ============
        function handleImageSelect(event) {
            const file = event.target.files[0];
            if (file) {
                const reader = new FileReader();
                reader.onload = e => {
                    selectedBase64Image = e.target.result;
                    document.getElementById('imagePreviewContainer').style.display = 'block';
                };
                reader.readAsDataURL(file);
            }
        }
        function removeImage() {
            selectedBase64Image = null;
            document.getElementById('imagePreviewContainer').style.display = 'none';
            document.getElementById('imageInput').value = '';
        }

        function toggleMobileSidebar() {
            const s = document.getElementById('sidebar');
            const o = document.getElementById('sidebarOverlay');
            s.classList.toggle('mobile-open');
            o.classList.toggle('active');
        }

        function safeMarkdownParse(text) {
            if (typeof marked !== 'undefined' && marked.parse) {
                try { return marked.parse(text); } catch (e) {}
            }
            let html = String(text).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
            html = html.replace(/```(\w*)\n([\s\S]*?)```/g, (m, lang, code) =>
                `<div class="code-container"><div class="code-header"><span>${lang || 'Kod'}</span><button class="copy-code-btn" onclick="copyCode(this)">Kopyala</button></div><pre><code>${code}</code></pre></div>`);
            html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
            html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
            html = html.replace(/\*(.+?)\*/g, '<em>$1</em>');
            html = html.replace(/\n/g, '<br>');
            return html;
        }

        function copyCode(btn) {
            const pre = btn.parentElement.nextElementSibling;
            navigator.clipboard.writeText(pre.innerText);
            btn.innerText = "Kopyalandı!";
            setTimeout(() => btn.innerText = "Kopyala", 2000);
        }

        function escapeHtml(s) {
            return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
        }

        async function logout() {
            try { await fetch('/logout', { method: 'POST' }); location.reload(); } catch (e) {}
        }

        async function saveProfile() {
            const bot_name = document.getElementById('modalBotName').value;
            const language = document.getElementById('modalLanguage').value;
            try {
                await fetch('/update-profile', {
                    method: 'POST', headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ bot_name, language })
                });
                document.getElementById('sidebarBotName').innerText = bot_name;
                showToast("Profil kaydedildi", "success");
                closeModal('profileModal');
            } catch (e) { showToast("Hata", "error"); }
        }

        async function uploadAvatar(event) {
            const file = event.target.files[0]; if (!file) return;
            const fd = new FormData(); fd.append('file', file);
            try {
                const res = await fetch('/upload-avatar', { method: 'POST', body: fd });
                const data = await res.json();
                if (data.status === 'success') {
                    document.getElementById('profileAvatarBtn').innerHTML = `<img src="/uploads/avatars/${data.avatar}">`;
                    showToast("Avatar güncellendi", "success");
                }
            } catch (e) {}
        }

        async function clearBotMemory() {
            if (!confirm("Hafıza temizlensin mi?")) return;
            try {
                await fetch('/memory/clear', { method: 'POST' });
                showToast("Hafıza temizlendi", "success");
            } catch (e) {}
        }

        function openAdminPanel() {
            if (!isAdmin) return;
            openModal('adminModal');
            loadMaintenanceStatus();
        }

        function switchAdminTab(tab, btn) {
            document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            document.getElementById('adminTab-theme').style.display = tab === 'theme' ? 'block' : 'none';
            document.getElementById('adminTab-users').style.display = tab === 'users' ? 'block' : 'none';
            document.getElementById('adminTab-bans').style.display = tab === 'bans' ? 'block' : 'none';
            document.getElementById('adminTab-notif').style.display = tab === 'notif' ? 'block' : 'none';
            if (tab === 'users') loadUsers();
            if (tab === 'bans') loadBans();
        }

        async function toggleMaintenance(enabled) {
            try {
                await fetch('/maintenance/toggle', {
                    method: 'POST', headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ enabled })
                });
                showToast(enabled ? "Bakım AÇIK" : "Bakım KAPALI", "success");
            } catch (e) {}
        }

        async function loadMaintenanceStatus() {
            try {
                const res = await fetch('/maintenance/check');
                const data = await res.json();
                const tog = document.getElementById('maintenanceToggle');
                if (tog) tog.checked = !!data.enabled;
            } catch (e) {}
        }

        async function loadUsers() {
            const c = document.getElementById('usersList');
            c.innerHTML = 'Yükleniyor...';
            try {
                const res = await fetch('/admin/users');
                const data = await res.json();
                if (data.status === 'success') {
                    c.innerHTML = data.users.map(u => `
                        <div class="user-item">
                            <i data-lucide="user" width="16" height="16" style="color: var(--accent1);"></i>
                            <div class="name">${escapeHtml(u.username)}<small>${escapeHtml(u.email || 'e-posta yok')} • ${u.language}</small></div>
                            ${u.is_admin ? '<span class="admin-badge">ADMIN</span>' : ''}
                            <button class="usr-btn" onclick="toggleAdmin(${u.id})">${u.is_admin ? 'Admin Kaldır' : 'Admin Yap'}</button>
                            <button class="usr-btn" style="background:rgba(239,68,68,0.15);color:#F87171;" onclick="deleteUser(${u.id})">Sil</button>
                        </div>
                    `).join('');
                    lucide.createIcons();
                }
            } catch (e) {}
        }

        async function toggleAdmin(id) {
            try { await fetch('/admin/users/toggle-admin/' + id, { method: 'POST' }); loadUsers(); } catch (e) {}
        }

        async function deleteUser(id) {
            if (!confirm("Kullanıcı silinsin mi?")) return;
            try { await fetch('/admin/users/delete/' + id, { method: 'POST' }); loadUsers(); } catch (e) {}
        }

        // ============ TEMA ============
        document.querySelectorAll('.logo-option').forEach(opt => {
            if (opt.dataset.icon === selectedLogoIcon) opt.classList.add('selected');
            opt.addEventListener('click', () => {
                document.querySelectorAll('.logo-option').forEach(o => o.classList.remove('selected'));
                opt.classList.add('selected');
                selectedLogoIcon = opt.dataset.icon;
            });
        });

        async function saveTheme() {
            if (!isAdmin) return;
            const theme = {
                bg_deep: document.getElementById('themeBgDeep').value,
                accent1: document.getElementById('themeAccent1').value,
                accent2: document.getElementById('themeAccent2').value,
                accent3: document.getElementById('themeAccent3').value,
                glass_opacity: parseFloat(document.getElementById('themeGlassOpacity').value),
                aurora_opacity: parseFloat(document.getElementById('themeAuroraOpacity').value),
                logo_icon: selectedLogoIcon
            };
            try {
                const res = await fetch('/admin/update-theme', {
                    method: 'POST', headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify(theme)
                });
                const data = await res.json();
                if (data.status === 'success') {
                    applyThemeLocal(data.theme);
                    updateLogoIcon(data.logo_icon);
                    showToast("Güncellendi!", "success");
                }
            } catch (e) {}
        }

        function resetTheme() {
            document.getElementById('themeBgDeep').value = DEFAULT_THEME.bg_deep;
            document.getElementById('themeAccent1').value = DEFAULT_THEME.accent1;
            document.getElementById('themeAccent2').value = DEFAULT_THEME.accent2;
            document.getElementById('themeAccent3').value = DEFAULT_THEME.accent3;
            document.getElementById('themeGlassOpacity').value = DEFAULT_THEME.glass_opacity;
            document.getElementById('themeAuroraOpacity').value = DEFAULT_THEME.aurora_opacity;
            applyThemeLocal(DEFAULT_THEME);
        }

        function applyThemeLocal(theme) {
            const root = document.documentElement;
            root.style.setProperty('--bg-deep', theme.bg_deep);
            root.style.setProperty('--accent1', theme.accent1);
            root.style.setProperty('--accent2', theme.accent2);
            root.style.setProperty('--accent3', theme.accent3);
            document.getElementById('auroraBg').style.opacity = theme.aurora_opacity;
        }

        function updateLogoIcon(name) {
            const el = document.getElementById('sidebarLogoIcon');
            if (el) { el.setAttribute('data-lucide', name); lucide.createIcons(); }
        }

        // ============ MÜZİK ============
        async function loadMusic() {
            try {
                const res = await fetch('/music-list');
                const data = await res.json();
                musicPlaylist = data.music || [];
                if (musicPlaylist.length > 0) playMusic(0);
            } catch (e) {}
        }

        function playMusic(index) {
            const audio = document.getElementById('bgMusic');
            if (musicPlaylist.length === 0) return;
            currentMusicIndex = index % musicPlaylist.length;
            audio.src = '/uploads/music/' + musicPlaylist[currentMusicIndex].filename;
            audio.volume = 0.4;
            if (!musicMuted) audio.play().catch(e => {});
        }

        document.getElementById('bgMusic').addEventListener('ended', () => playMusic(currentMusicIndex + 1));

        function toggleMusic() {
            const audio = document.getElementById('bgMusic');
            const btn = document.getElementById('musicToggleBtn');
            const icon = document.getElementById('musicIcon');
            musicMuted = !musicMuted;
            if (musicMuted) {
                audio.pause(); btn.classList.add('muted');
                icon.setAttribute('data-lucide', 'volume-x');
            } else {
                audio.play().catch(e => {}); btn.classList.remove('muted');
                icon.setAttribute('data-lucide', 'volume-2');
            }
            lucide.createIcons();
        }

        // ============ SOHBET ============
        async function loadChatsFromServer() {
            if (!loggedIn) {
                chats = [{ title: "Varsayılan Sohbet", messages: [] }];
                activeChatIndex = 0;
                isInitialLoad = false;
                renderChatHistory(); renderActiveChat(); updateStats();
                return;
            }
            try {
                const res = await fetch('/chats');
                const data = await res.json();
                if (data.status === 'success' && data.chats.length > 0) {
                    chats = data.chats.map(c => ({ id: c.id, title: c.title || "Sohbet", messages: c.messages || [] }));
                    activeChatIndex = 0;
                } else {
                    chats = [{ title: "Varsayılan Sohbet", messages: [] }];
                    activeChatIndex = 0;
                }
                isInitialLoad = false;
                renderChatHistory(); renderActiveChat(); updateStats();
            } catch (e) {
                chats = [{ title: "Varsayılan Sohbet", messages: [] }];
                activeChatIndex = 0;
                isInitialLoad = false;
                renderChatHistory(); renderActiveChat(); updateStats();
            }
        }

        function startNewChat() {
            saveChatToServer();
            chats.unshift({ title: "Yeni Sohbet " + (chats.length + 1), messages: [] });
            activeChatIndex = 0;
            isInitialLoad = false;
            renderChatHistory(); renderActiveChat(); updateStats();
            if (window.innerWidth <= 850) toggleMobileSidebar();
        }

        function switchChat(i) {
            activeChatIndex = i;
            isInitialLoad = false;
            renderChatHistory(); renderActiveChat();
            if (window.innerWidth <= 850) toggleMobileSidebar();
        }

        function updateStats() { document.getElementById('totalChats').innerText = chats.length; }

        function renderChatHistory() {
            const list = document.getElementById('chatHistoryList');
            list.innerHTML = '';
            if (chats.length === 0) {
                list.innerHTML = '<div style="text-align:center;padding:20px;font-size:11px;color:var(--text-muted);">Sohbet yok</div>';
                return;
            }
            chats.forEach((c, i) => {
                list.innerHTML += `<div class="history-item ${i === activeChatIndex ? 'active' : ''}" onclick="switchChat(${i})"><i data-lucide="message-square" width="12" height="12"></i> ${escapeHtml(c.title)}</div>`;
            });
            lucide.createIcons();
        }

        function renderActiveChat() {
            const box = document.getElementById('chatBox');
            box.innerHTML = '';
            if (!chats[activeChatIndex]) return;
            chats[activeChatIndex].messages.forEach((m, i) => {
                let imgHtml = m.image ? `<img src="${m.image}" style="max-width:100%;border-radius:10px;margin-top:6px;">` : '';
                let actions = `<div class="msg-actions">
                    ${m.sender === 'bot' ? `<button class="msg-action-btn" onclick="speakText(${i})">🔊</button>` : ''}
                    <button class="msg-action-btn" onclick="copyMsg(${i})">Kopyala</button>
                    <button class="msg-action-btn" onclick="deleteMsg(${i})">Sil</button>
                </div>`;
                const isNew = (!isInitialLoad && i === animatingMessageIndex) ? ' msg-new' : '';
                box.innerHTML += `<div class="msg-bubble ${m.sender}${isNew}"><b>${escapeHtml(m.name)}</b>${imgHtml}${m.content}${actions}</div>`;
            });
            box.scrollTop = box.scrollHeight;
            lucide.createIcons();
            animatingMessageIndex = -1;
        }

        function copyMsg(i) {
            const m = chats[activeChatIndex].messages[i];
            const tmp = document.createElement('div'); tmp.innerHTML = m.content;
            navigator.clipboard.writeText(tmp.innerText);
            showToast("Kopyalandı", "success");
        }
        function deleteMsg(i) {
            chats[activeChatIndex].messages.splice(i, 1);
            renderActiveChat(); saveChatToServer();
        }

        function speakText(i) {
            const m = chats[activeChatIndex].messages[i];
            const tmp = document.createElement('div'); tmp.innerHTML = m.content;
            const u = new SpeechSynthesisUtterance(tmp.innerText);
            u.lang = 'tr-TR';
            window.speechSynthesis.cancel();
            window.speechSynthesis.speak(u);
        }

        let recognition = null, isRecording = false;
        function toggleVoiceInput() {
            const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
            if (!SR) { showToast("Tarayıcı desteklemiyor", "error"); return; }
            const btn = document.getElementById('voiceBtn');
            if (isRecording && recognition) { recognition.stop(); isRecording = false; btn.classList.remove('recording'); return; }
            recognition = new SR();
            recognition.lang = 'tr-TR';
            recognition.onstart = () => { isRecording = true; btn.classList.add('recording'); };
            recognition.onresult = e => {
                const text = e.results[0][0].transcript;
                const inp = document.getElementById('message');
                inp.value = (inp.value + ' ' + text).trim();
            };
            recognition.onend = () => { isRecording = false; btn.classList.remove('recording'); };
            recognition.start();
        }

        async function sendMessage() {
            const inp = document.getElementById('message');
            const msg = inp.value.trim();
            if (!msg && !selectedBase64Image && !selectedFileText) return;
            if (!chats[activeChatIndex]) {
                chats.unshift({ title: "Sohbet", messages: [] });
                activeChatIndex = 0;
            }
            if (chats[activeChatIndex].messages.length === 0 && msg) {
                chats[activeChatIndex].title = msg.length > 18 ? msg.substring(0, 18) + '...' : msg;
                renderChatHistory();
            }
            const img = selectedBase64Image;
            const fileTxt = selectedFileText;
            chats[activeChatIndex].messages.push({
                sender: 'user', name: currentUser,
                content: escapeHtml(msg + (fileTxt ? ` [${selectedFileName}]` : '')),
                image: img
            });
            isInitialLoad = false;
            animatingMessageIndex = chats[activeChatIndex].messages.length - 1;
            renderActiveChat();
            inp.value = ''; removeImage(); removeFile();

            chats[activeChatIndex].messages.push({
                sender: 'bot', name: 'Crsz Bot',
                content: '<span class="typing-dots"><span></span><span></span><span></span></span>'
            });
            animatingMessageIndex = chats[activeChatIndex].messages.length - 1;
            renderActiveChat();
            saveChatToServer();

            try {
                const res = await fetch('/chat', {
                    method: 'POST', headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ username: currentUser, message: msg, image: img, file_text: fileTxt })
                });
                const data = await res.json();
                chats[activeChatIndex].messages.pop();
                chats[activeChatIndex].messages.push({
                    sender: 'bot', name: 'Crsz Bot',
                    content: safeMarkdownParse(data.reply || 'Boş cevap')
                });
                isInitialLoad = false;
                animatingMessageIndex = chats[activeChatIndex].messages.length - 1;
                renderActiveChat();
                saveChatToServer();
            } catch (e) {
                chats[activeChatIndex].messages.pop();
                chats[activeChatIndex].messages.push({
                    sender: 'bot', name: 'Crsz Bot',
                    content: `Hata: ${escapeHtml(e.message)}`
                });
                renderActiveChat();
            }
        }

        async function saveChatToServer() {
            if (!loggedIn || !chats[activeChatIndex]) return;
            try {
                await fetch('/chats/save', {
                    method: 'POST', headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        title: chats[activeChatIndex].title || "Sohbet",
                        messages: chats[activeChatIndex].messages
                    })
                });
            } catch (e) {}
        }

        // Ripple
        function createRipple(e) {
            const btn = e.currentTarget;
            const rect = btn.getBoundingClientRect();
            const circle = document.createElement('span');
            const diameter = Math.max(rect.width, rect.height);
            circle.style.width = circle.style.height = `${diameter}px`;
            circle.style.left = `${e.clientX - rect.left - diameter/2}px`;
            circle.style.top = `${e.clientY - rect.top - diameter/2}px`;
            circle.classList.add('ripple');
            const ex = btn.querySelector('.ripple'); if (ex) ex.remove();
            btn.appendChild(circle);
            setTimeout(() => circle.remove(), 650);
        }
        function bindRipple(el) {
            if (el.dataset.ripple === '1') return;
            el.dataset.ripple = '1';
            el.addEventListener('click', e => { playClickSound(); createRipple(e); });
        }
        document.querySelectorAll('button, .footer-btn, .new-chat-btn, .send-btn, .icon-action-btn, .upload-icon-btn, .tab-btn, .msg-action-btn, .history-item, .logo-option').forEach(bindRipple);

        const observer = new MutationObserver(() => {
            document.querySelectorAll('button:not([data-ripple]), .footer-btn:not([data-ripple]), .new-chat-btn:not([data-ripple]), .send-btn:not([data-ripple]), .icon-action-btn:not([data-ripple]), .upload-icon-btn:not([data-ripple]), .tab-btn:not([data-ripple]), .msg-action-btn:not([data-ripple]), .history-item:not([data-ripple]), .logo-option:not([data-ripple])').forEach(bindRipple);
        });
        observer.observe(document.body, { childList: true, subtree: true });

        // İnit
        update2FAUI();
        loadMusic();
        if (loggedIn) {
            loadChatsFromServer();
            setInterval(() => {
                if (document.getElementById('notifPanel').classList.contains('open')) loadNotifications();
            }, 30000);
        }

        document.body.addEventListener('click', function initMusic() {
            const audio = document.getElementById('bgMusic');
            if (!musicMuted && audio.src && audio.paused && musicPlaylist.length > 0) audio.play().catch(e => {});
            document.body.removeEventListener('click', initMusic);
        }, { once: true });
    </script>
</body>
</html>
""""
<!DOCTYPE html>
<html><body><h1>HTML PARÇA 2'DE GELECEK</h1></body></html>
"""


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
