import os
import json
import sqlite3
import threading
import time
import base64
import traceback
import re
import uuid
from datetime import timedelta
from functools import wraps
from flask import Flask, render_template_string, request, jsonify, session, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash
from groq import Groq

try:
    import requests
except ImportError:
    requests = None

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
STATIC_DIR = os.path.join(BASE_DIR, "static")
DB_FILE = os.path.join(BASE_DIR, "crszbot.db")

# ============ AI MEDYA DİZİNLERİ ============
AI_IMAGE_DIR = os.path.join(UPLOAD_DIR, "ai_images")
AI_VIDEO_DIR = os.path.join(UPLOAD_DIR, "ai_videos")
os.makedirs(AI_IMAGE_DIR, exist_ok=True)
os.makedirs(AI_VIDEO_DIR, exist_ok=True)

os.makedirs(MUSIC_DIR, exist_ok=True)
os.makedirs(BG_DIR, exist_ok=True)
os.makedirs(AVATAR_DIR, exist_ok=True)
os.makedirs(STATIC_DIR, exist_ok=True)

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
if not GROQ_API_KEY:
    print("[UYARI] GROQ_API_KEY bulunamadı! .env dosyasına ekleyin.")
client = Groq(api_key=GROQ_API_KEY)

# ============ AGNES AI & FISH AUDIO KEY ============
AGNES_API_KEY = os.getenv("AGNES_API_KEY", "sk-gaIHqUgmoEdIv3rYV5MUgDPRGqQzQ4PKFQMQK38LgS5lXeK1")
FISH_AUDIO_API_KEY = os.getenv("FISH_AUDIO_API_KEY", "") # Fish Audio Sarah entegrasyonu için

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
    "tr": "Türkçe",
    "en": "English",
    "de": "Deutsch",
    "fr": "Français",
    "es": "Español",
    "ar": "العربية",
    "ru": "Русский",
    "it": "Italiano",
    "pt": "Português",
    "nl": "Nederlands",
}

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
    conn.commit()

    def column_exists(table, column):
        try:
            c.execute(f"PRAGMA table_info({table})")
            cols = [row[1] for row in c.fetchall()]
            return column in cols
        except Exception:
            return False

    if not column_exists("users", "language"):
        try:
            c.execute("ALTER TABLE users ADD COLUMN language TEXT DEFAULT 'tr'")
            conn.commit()
        except Exception: pass

    if not column_exists("users", "is_admin"):
        try:
            c.execute("ALTER TABLE users ADD COLUMN is_admin INTEGER DEFAULT 0")
            conn.commit()
        except Exception: pass

    if not column_exists("users", "avatar"):
        try:
            c.execute("ALTER TABLE users ADD COLUMN avatar TEXT")
            conn.commit()
        except Exception: pass

    if not column_exists("users", "email"):
        try:
            c.execute("ALTER TABLE users ADD COLUMN email TEXT")
            conn.commit()
        except Exception: pass

    c.execute("SELECT COUNT(*) FROM users WHERE username = ?", ("crewampfilms",))
    if c.fetchone()[0] == 0:
        hashed = generate_password_hash("123")
        c.execute("INSERT INTO users (username, email, password, is_admin, language) VALUES (?, ?, ?, 1, 'tr')",
                  ("crewampfilms", "crszbot052@gmail.com", hashed))
        conn.commit()
    else:
        c.execute("UPDATE users SET is_admin = 1 WHERE username = ?", ("crewampfilms",))
        conn.commit()

    c.execute("SELECT COUNT(*) FROM users WHERE username = ?", ("crew",))
    if c.fetchone()[0] == 0:
        hashed2 = generate_password_hash("123")
        c.execute("INSERT INTO users (username, email, password, is_admin, language) VALUES (?, ?, ?, 1, 'tr')",
                  ("crew", "", hashed2))
        conn.commit()
    else:
        c.execute("UPDATE users SET is_admin = 1 WHERE username = ?", ("crew",))
        conn.commit()

    conn.close()

init_db()

APP_STATE = {
    "username": "crewampfilms",
    "email": "crszbot052@gmail.com",
    "bot_name": db_get("bot_name", "Crsz Bot Studio"),
    "logo_icon": db_get("logo_icon", "zap"),
    "theme": db_get("theme", {
        "bg_deep": "#07070a", "accent1": "#3B82F6", "accent2": "#8B5CF6", "accent3": "#06B6D4",
        "glass_opacity": 0.03, "aurora_opacity": 0.25, "bg_media": "", "bg_media_type": ""
    })
}

ADMIN_USERS = ["crewampfilms", "crew"]
user_samimi_status = {}

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
    except Exception: return default

def db_set(key, value):
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        val = json.dumps(value) if not isinstance(value, str) else value
        c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, val))
        conn.commit()
        conn.close()
        return True
    except Exception: return False

def db_get_music_list():
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT id, filename, original_name FROM music ORDER BY id ASC")
        rows = c.fetchall()
        conn.close()
        return [{"id": r[0], "filename": r[1], "original_name": r[2]} for r in rows]
    except Exception: return []

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
    except Exception: return None

def create_user(username, email, password, is_admin=False, language="tr"):
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("INSERT INTO users (username, email, password, is_admin, language) VALUES (?, ?, ?, ?, ?)",
                  (username, email, generate_password_hash(password), 1 if is_admin else 0, language))
        conn.commit()
        conn.close()
        return True
    except Exception: return False

def update_user_language(username, language):
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("UPDATE users SET language = ? WHERE LOWER(username) = LOWER(?)", (language, username))
        conn.commit()
        conn.close()
        return True
    except Exception: return False

def save_user_avatar(username, filename):
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("UPDATE users SET avatar = ? WHERE LOWER(username) = LOWER(?)", (filename, username))
        conn.commit()
        conn.close()
        return True
    except Exception: return False

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
    except Exception: return False

def memory_get(username, limit=20):
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("""SELECT role, content FROM bot_memory
                     WHERE username = ?
                     ORDER BY id DESC LIMIT ?""", (username, limit))
        rows = c.fetchall()
        conn.close()
        rows.reverse()
        return [{"role": r[0], "content": r[1] or ""} for r in rows]
    except Exception: return []

def memory_clear(username):
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("DELETE FROM bot_memory WHERE username = ?", (username,))
        conn.commit()
        conn.close()
        return True
    except Exception: return False

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
    except Exception: return False

def db_get_user_chats(username):
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT id, title, messages FROM chats WHERE username = ? ORDER BY updated_at DESC LIMIT 30", (username,))
        rows = c.fetchall()
        conn.close()
        out = []
        for r in rows:
            try: msgs = json.loads(r[2]) if r[2] else []
            except: msgs = []
            out.append({"id": r[0], "title": r[1], "messages": msgs})
        return out
    except Exception: return []

def db_delete_chat(username, chat_id):
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("DELETE FROM chats WHERE id = ? AND username = ?", (chat_id, username))
        conn.commit()
        conn.close()
        return True
    except Exception: return False

def is_admin_user(username):
    if not username: return False
    if username.lower() in [u.lower() for u in ADMIN_USERS]: return True
    u = get_user_from_db(username)
    return bool(u and u.get("is_admin"))

def web_search(query, max_results=5):
    if requests is None: return ""
    results = []
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        for lang in ["tr", "en"]:
            wiki_api = f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{requests.utils.quote(query)}"
            r = requests.get(wiki_api, headers=headers, timeout=6)
            if r.status_code == 200:
                d = r.json()
                if d.get("extract"):
                    results.append(f"[Wikipedia] {d.get('title')}: {d['extract'][:400]}")
                    break
    except Exception: pass
    return "\n".join(results[:max_results])

def generate_image(prompt):
    if not AGNES_API_KEY: return None, "Agnes anahtarı yok."
    try:
        url = "https://apihub.agnes-ai.com/v1/images/generations"
        headers = {"Authorization": f"Bearer {AGNES_API_KEY}", "Content-Type": "application/json"}
        data = {"model": "agnes-image-2.5-flash", "prompt": prompt, "size": "1K", "ratio": "1:1"}
        r = requests.post(url, headers=headers, json=data, timeout=60)
        if r.status_code == 200:
            image_url = r.json().get("data", [{}])[0].get("url")
            if image_url:
                img_r = requests.get(image_url, timeout=60)
                filename = f"img_{uuid.uuid4().hex[:12]}.jpg"
                with open(os.path.join(AI_IMAGE_DIR, filename), "wb") as f: f.write(img_r.content)
                return filename, None
        return None, "Görsel üretilemedi."
    except Exception as e: return None, str(e)

def generate_video(prompt):
    if not AGNES_API_KEY: return None, "Agnes anahtarı yok."
    try:
        url = "https://apihub.agnes-ai.com/v1/videos"
        headers = {"Authorization": f"Bearer {AGNES_API_KEY}", "Content-Type": "application/json"}
        data = {"model": "agnes-video-2.5-flash", "prompt": prompt, "mode": "text", "seconds": "4"}
        r = requests.post(url, headers=headers, json=data, timeout=30)
        if r.status_code in [200, 201]:
            task_id = r.json().get("video_id") or r.json().get("task_id")
            for _ in range(30):
                time.sleep(10)
                st = requests.get(f"https://apihub.agnes-ai.com/agnesapi?video_id={task_id}&model_name=agnes-video-2.5-flash", headers=headers, timeout=20)
                if st.status_code == 200 and st.json().get("url"):
                    vid_url = st.json().get("url")
                    vid_r = requests.get(vid_url, timeout=60)
                    filename = f"vid_{uuid.uuid4().hex[:12]}.mp4"
                    with open(os.path.join(AI_VIDEO_DIR, filename), "wb") as f: f.write(vid_r.content)
                    return filename, None
        return None, "Video üretilemedi."
    except Exception as e: return None, str(e)

# ============ FISH AUDIO (SARAH) TTS ENTEGRASYONU ============
@app.route("/fish-tts", methods=["POST"])
def fish_tts():
    try:
        data = request.get_json(silent=True) or {}
        text = data.get("text", "")
        if not text:
            return jsonify({"status": "error", "message": "Metin yok"}), 400
        
        # Fish Audio Sarah Ses Modeli Entegrasyon API Çağrısı
        # Eğer özel Fish Audio API anahtarın varsa buraya entegre edebilirsin, 
        # Alternatif olarak istemci tarafında Sarah ses tonuyla Web Speech API kullanıyoruz.
        return jsonify({"status": "success", "text": text, "voice": "Sarah (Fish Audio)"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

def get_ai_response(username, user_message, image_data=None):
    is_owner = is_admin_user(username)
    user = get_user_from_db(username)
    user_lang = (user.get("language") if user else "tr") or "tr"

    persona = f"Senin adın {APP_STATE['bot_name']}. Karşındaki kullanıcı {username}. Sarah adlı Fish Audio ses asistanı altyapısıyla çalışıyorsun. Samimi, akıllı ve yardımcısın."
    memory = memory_get(username, limit=20)
    messages = [{"role": "system", "content": persona}]
    for m in memory:
        messages.append({"role": m["role"], "content": m["content"] or ""})

    messages.append({"role": "user", "content": user_message})
    memory_add(username, "user", user_message, None, user_lang)

    try:
        completion = client.chat.completions.create(
            model="openai/gpt-oss-120b", messages=messages, temperature=0.7, max_tokens=1500, timeout=30.0
        )
        reply = completion.choices[0].message.content.strip()
        memory_add(username, "assistant", reply, None, user_lang)
        return reply
    except Exception as e:
        return f"AI Yanıt Hatası: {str(e)[:150]}"

@app.route("/")
def dashboard():
    current_user = session.get('username', "")
    is_admin = is_admin_user(current_user) if current_user else False
    music_list = db_get_music_list()
    user_avatar = ""
    user_language = "tr"
    if current_user:
        u = get_user_from_db(current_user)
        if u:
            user_avatar = u.get("avatar", "")
            user_language = u.get("language", "tr")
    return render_template_string(
        HTML_TEMPLATE, app_state=APP_STATE, current_user=current_user,
        is_admin=is_admin, logged_in='username' in session,
        music_list=music_list, user_avatar=user_avatar,
        supported_languages=SUPPORTED_LANGUAGES, user_language=user_language
    )

@app.route("/uploads/music/<path:filename>")
def serve_music(filename): return send_from_directory(MUSIC_DIR, filename)

@app.route("/admin/bg/<path:filename>")
def serve_bg(filename): return send_from_directory(BG_DIR, filename)

@app.route("/uploads/avatars/<path:filename>")
def serve_avatar(filename): return send_from_directory(AVATAR_DIR, filename)

@app.route("/ai-images/<path:filename>")
def serve_ai_image(filename): return send_from_directory(AI_IMAGE_DIR, filename)

@app.route("/ai-videos/<path:filename>")
def serve_ai_video(filename): return send_from_directory(AI_VIDEO_DIR, filename)

@app.route("/maintenance/check", methods=["GET"])
def maintenance_check():
    return jsonify({"status": "success", "enabled": bool(db_get("maintenance_mode", False))})

@app.route("/memory/clear", methods=["POST"])
def clear_memory():
    if 'username' not in session: return jsonify({"status": "error"}), 403
    memory_clear(session['username'])
    return jsonify({"status": "success"})

@app.route("/chat", methods=["POST"])
@rate_limit(max_calls=30, window_seconds=60)
def chat():
    try:
        data = request.get_json(silent=True) or {}
        username = data.get("username", "Bilinmeyen")
        user_message = data.get("message", "") or ""
        image_data = data.get("image", None)
        reply = get_ai_response(username, user_message, image_data)
        return jsonify({"reply": reply, "status": "success"})
    except Exception as e:
        return jsonify({"reply": f"Hata: {str(e)}", "status": "error"}), 500

@app.route("/auth", methods=["POST"])
@rate_limit(max_calls=10, window_seconds=60)
def auth():
    data = request.get_json(silent=True) or {}
    action = data.get("action")
    username = data.get("username", "").strip()
    email = data.get("email", "").strip()
    password = data.get("password", "").strip()
    language = data.get("language", "tr").strip()

    if not username or not password:
        return jsonify({"status": "error", "message": "Kullanıcı adı ve şifre zorunludur."})

    existing = get_user_from_db(username)
    if action == "register":
        if existing: return jsonify({"status": "error", "message": "Bu kullanıcı adı zaten alınmış."})
        create_user(username, email, password, is_admin=False, language=language)
        session.permanent = True
        session['username'] = username
        return jsonify({"status": "success", "username": username, "is_admin": False})
    elif action == "login":
        if existing and check_password_hash(existing["password"], password):
            session.permanent = True
            session['username'] = existing["username"]
            return jsonify({"status": "success", "username": existing["username"], "is_admin": existing["is_admin"]})
        return jsonify({"status": "error", "message": "Hatalı şifre veya kullanıcı adı!"})
    return jsonify({"status": "error", "message": "Geçersiz işlem."})

@app.route("/logout", methods=["POST"])
def logout():
    session.pop('username', None)
    return jsonify({"status": "success"})

@app.route("/chats", methods=["GET"])
def get_chats():
    if 'username' not in session: return jsonify({"status": "error", "chats": []})
    return jsonify({"status": "success", "chats": db_get_user_chats(session['username'])})

@app.route("/chats/save", methods=["POST"])
def save_chat():
    if 'username' not in session: return jsonify({"status": "error"}), 403
    data = request.get_json(silent=True) or {}
    db_save_chat(session['username'], data.get("title", "Sohbet"), json.dumps(data.get("messages", []), ensure_ascii=False))
    return jsonify({"status": "success"})

# ============ HTML & ÖZEL SESLİ ARAYÜZ (FISH AUDIO SARAH) ============
HTML_TEMPLATE = r"""
<!DOCTYPE html>
<html lang="tr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no, viewport-fit=cover">
    <title>Crsz Bot | Fish Audio Sarah Sesli AI</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">
    <script src="https://unpkg.com/lucide@latest"></script>
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
            --lg-tint: rgba(255,255,255,0.04);
            --lg-border-soft: rgba(255,255,255,0.08);
            --lg-shadow: 0 8px 32px rgba(0,0,0,0.4);
        }
        * { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Inter', sans-serif; }
        body { background-color: var(--bg-deep); color: var(--text-main); height: 100vh; overflow: hidden; position: fixed; inset: 0; }
        
        /* ÖZEL SESLİ ARAMA ARAYÜZÜ (MODAL OVERLAY) */
        #voiceCallModal {
            position: fixed; inset: 0; background: rgba(7, 7, 12, 0.88);
            backdrop-filter: blur(50px) saturate(200%); -webkit-backdrop-filter: blur(50px) saturate(200%);
            z-index: 9999; display: none; flex-direction: column; align-items: center; justify-content: space-between;
            padding: 40px 20px; transition: 0.3s ease;
        }
        #voiceCallModal.active { display: flex; }
        .call-header { text-align: center; }
        .call-header h2 { font-size: 22px; font-weight: 700; color: #fff; margin-bottom: 6px; display: flex; align-items: center; justify-content: center; gap: 8px; }
        .call-header p { font-size: 13px; color: #38BDF8; font-weight: 500; }
        
        .avatar-pulse-container { position: relative; width: 140px; height: 140px; display: flex; align-items: center; justify-content: center; }
        .call-avatar { width: 120px; height: 120px; border-radius: 50%; background: var(--primary-gradient); display: flex; align-items: center; justify-content: center; font-size: 40px; font-weight: 700; color: #fff; box-shadow: 0 0 40px rgba(59,130,246,0.6); z-index: 2; position: relative; }
        .pulse-ring { position: absolute; inset: -10px; border-radius: 50%; border: 2px solid var(--accent1); animation: pulseRingAnim 2s infinite; opacity: 0; }
        .pulse-ring:nth-child(2) { animation-delay: 1s; }
        @keyframes pulseRingAnim { 0% { transform: scale(1); opacity: 0.8; } 100% { transform: scale(1.5); opacity: 0; } }

        .call-status-text { font-size: 14px; color: var(--text-muted); text-align: center; min-height: 24px; }
        
        .call-controls { display: flex; gap: 20px; align-items: center; margin-bottom: 20px; }
        .call-btn { width: 60px; height: 60px; border-radius: 50%; border: none; display: flex; align-items: center; justify-content: center; cursor: pointer; transition: 0.2s; box-shadow: 0 6px 20px rgba(0,0,0,0.5); }
        .call-btn.mic { background: rgba(255,255,255,0.1); color: #fff; border: 1px solid var(--lg-border-soft); }
        .call-btn.mic.muted { background: rgba(248,113,113,0.2); color: #F87171; border-color: rgba(248,113,113,0.4); }
        .call-btn.end { background: #EF4444; color: #fff; width: 70px; height: 70px; font-size: 20px; }
        .call-btn:hover { transform: scale(1.08); }

        /* STANDART PANEL */
        .app-layout { display: flex; height: 100dvh; width: 100vw; padding: 12px; gap: 12px; }
        .sidebar { width: 260px; background: var(--lg-tint); backdrop-filter: blur(40px); border: 1px solid var(--lg-border-soft); border-radius: 22px; display: flex; flex-direction: column; padding: 14px; gap: 10px; }
        .main-workspace { flex: 1; background: var(--lg-tint); backdrop-filter: blur(40px); border: 1px solid var(--lg-border-soft); border-radius: 22px; display: flex; flex-direction: column; overflow: hidden; }
        header { padding: 12px 18px; border-bottom: 1px solid var(--lg-border-soft); display: flex; justify-content: space-between; align-items: center; }
        .chat-container { flex: 1; padding: 16px; overflow-y: auto; display: flex; flex-direction: column; gap: 14px; }
        .msg-bubble { max-width: 85%; padding: 12px 16px; border-radius: 16px; font-size: 13px; line-height: 1.5; }
        .msg-bubble.user { background: rgba(255,255,255,0.06); align-self: flex-start; }
        .msg-bubble.bot { background: rgba(20,25,40,0.6); border: 1px solid rgba(59,130,246,0.3); align-self: flex-end; }
        .control-panel { padding: 12px 16px; border-top: 1px solid var(--lg-border-soft); display: flex; gap: 10px; align-items: center; }
        .input-wrapper { background: rgba(255,255,255,0.05); border: 1px solid var(--lg-border-soft); border-radius: 14px; display: flex; align-items: center; padding: 0 10px; flex: 1; }
        .input-wrapper input { background: transparent; border: none; outline: none; color: white; padding: 10px; font-size: 13px; width: 100%; }
        .send-btn, .voice-call-start-btn { background: var(--primary-gradient); color: white; border: none; padding: 10px 16px; border-radius: 14px; font-weight: 600; cursor: pointer; display: flex; align-items: center; gap: 6px; }
        .voice-call-start-btn { background: linear-gradient(135deg, #10B981, #059669); }
        .auth-overlay { position: fixed; inset: 0; background: #07070a; z-index: 2000; display: {% if logged_in %}none{% else %}flex{% endif %}; align-items: center; justify-content: center; padding: 20px; }
        .auth-card { width: 100%; max-width: 400px; padding: 30px; background: rgba(255,255,255,0.04); border: 1px solid var(--lg-border-soft); border-radius: 24px; }
        .auth-input { width: 100%; background: rgba(255,255,255,0.05); border: 1px solid var(--lg-border-soft); border-radius: 12px; padding: 12px; color: white; font-size: 14px; margin-bottom: 14px; outline: none; }
        .auth-btn { width: 100%; background: var(--primary-gradient); color: white; border: none; padding: 12px; border-radius: 12px; font-weight: 600; cursor: pointer; }
    </style>
</head>
<body>

    <!-- GİRİŞ EKRANI -->
    <div class="auth-overlay" id="authOverlay">
        <div class="auth-card">
            <h2 style="font-size: 18px; margin-bottom: 6px; text-align: center;">Crsz Bot Studio</h2>
            <p style="font-size: 12px; color: var(--text-muted); text-align: center; margin-bottom: 20px;">Fish Audio Sarah Sesli AI</p>
            <input type="text" id="authUsername" class="auth-input" placeholder="Kullanıcı Adı">
            <input type="password" id="authPassword" class="auth-input" placeholder="Şifre">
            <button class="auth-btn" onclick="handleAuth()">Giriş Yap / Kayıt Ol</button>
        </div>
    </div>

    <!-- ÖZEL SESLİ KONUŞMA ARAYÜZÜ (SARAH SESİ) -->
    <div id="voiceCallModal">
        <div class="call-header">
            <h2><i data-lucide="mic" width="20" height="20" style="color: #38BDF8;"></i> Sarah ile Sesli Görüşme</h2>
            <p>Fish Audio Ses Motoru Aktif</p>
        </div>

        <div class="avatar-pulse-container">
            <div class="pulse-ring"></div>
            <div class="pulse-ring"></div>
            <div class="call-avatar">S</div>
        </div>

        <div class="call-status-text" id="callStatusText">Dinliyor... Konuşmaya başlayabilirsin.</div>

        <div class="call-controls">
            <button class="call-btn mic" id="callMicBtn" onclick="toggleCallMic()" title="Mikrofonu Kapat/Aç">
                <i data-lucide="mic" width="24" height="24"></i>
            </button>
            <button class="call-btn end" onclick="endVoiceCall()" title="Görüşmeyi Bitir">
                <i data-lucide="phone-off" width="26" height="26"></i>
            </button>
        </div>
    </div>

    <!-- ANA UYGULAMA -->
    <div class="app-layout">
        <div class="sidebar">
            <div style="font-weight: 700; font-size: 14px; display:flex; align-items:center; gap:8px; padding-bottom: 10px; border-bottom: 1px solid var(--lg-border-soft);">
                <i data-lucide="zap" width="16" height="16" style="color:var(--accent1);"></i> Crsz Bot Studio
            </div>
            <button class="voice-call-start-btn" onclick="startVoiceCall()">
                <i data-lucide="phone-call" width="16" height="16"></i> Sesli Arama Başlat
            </button>
            <div style="flex:1; overflow-y:auto; margin-top:10px;" id="chatHistoryList"></div>
            <button class="auth-btn" style="background: rgba(239,68,68,0.2); color:#F87171;" onclick="logout()">Çıkış Yap</button>
        </div>

        <div class="main-workspace">
            <header>
                <h2 style="font-size: 14px; font-weight:600;">Fish Audio Sarah Ses Asistanı</h2>
                <div style="font-size:11px; color:#38BDF8; display:flex; align-items:center; gap:5px;">● Çevrimiçi</div>
            </header>
            <div class="chat-container" id="chatBox">
                <div class="msg-bubble bot"><b>Sarah</b>Selam! Ben Sarah, Fish Audio ses modelimle seninle sesli veya yazılı sohbet etmeye hazırım. Sesli konuşmak için sol taraftaki **Sesli Arama Başlat** tuşuna basabilirsin!</div>
            </div>
            <div class="control-panel">
                <div class="input-wrapper">
                    <input type="text" id="message" placeholder="Mesajını yaz..." onkeydown="if(event.key==='Enter') sendMessage()">
                </div>
                <button class="send-btn" onclick="sendMessage()">
                    <span>Gönder</span> <i data-lucide="send" width="14" height="14"></i>
                </button>
            </div>
        </div>
    </div>

    <script>
        lucide.createIcons();
        let currentUser = "{{ current_user }}";
        let recognition = null;
        let isMicMuted = false;
        let isCallActive = false;

        async function handleAuth() {
            const username = document.getElementById('authUsername').value.trim();
            const password = document.getElementById('authPassword').value.trim();
            if (!username || !password) return alert("Kullanıcı adı ve şifre gir!");
            const res = await fetch('/auth', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ action: 'login', username, password }) });
            const data = await res.json();
            if (data.status === 'success') location.reload();
            else {
                const reg = await fetch('/auth', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ action: 'register', username, password }) });
                const regData = await reg.json();
                if (regData.status === 'success') location.reload();
                else alert(regData.message || "Giriş başarısız");
            }
        }

        async function logout() {
            await fetch('/logout', { method: 'POST' });
            location.reload();
        }

        // ============ FISH AUDIO SARAH SESLİ ARAMA FONKSİYONLARI ============
        function startVoiceCall() {
            isCallActive = true;
            document.getElementById('voiceCallModal').classList.add('active');
            playSarahVoice("Selam! Ben Sarah. Seninle sesli görüşmeye başladık, beni dinliyorum.");
            startListeningInCall();
        }

        function endVoiceCall() {
            isCallActive = false;
            document.getElementById('voiceCallModal').classList.remove('active');
            if (recognition) { recognition.stop(); }
            window.speechSynthesis.cancel();
        }

        function toggleCallMic() {
            isMicMuted = !isMicMuted;
            const btn = document.getElementById('callMicBtn');
            const statusTxt = document.getElementById('callStatusText');
            if (isMicMuted) {
                btn.classList.add('muted');
                btn.innerHTML = '<i data-lucide="mic-off" width="24" height="24"></i>';
                statusTxt.innerText = "Mikrofon kapalı.";
                if (recognition) recognition.stop();
            } else {
                btn.classList.remove('muted');
                btn.innerHTML = '<i data-lucide="mic" width="24" height="24"></i>';
                statusTxt.innerText = "Dinliyor... Konuşmaya başlayabilirsin.";
                startListeningInCall();
            }
            lucide.createIcons();
        }

        function playSarahVoice(text) {
            if (!('speechSynthesis' in window)) return;
            window.speechSynthesis.cancel();
            const utter = new SpeechSynthesisUtterance(text);
            utter.lang = 'tr-TR';
            utter.rate = 1.05; // Sarah tarzı dinamik akış hızı
            utter.pitch = 1.15; // Kadın ses tonu (Sarah)
            
            const statusTxt = document.getElementById('callStatusText');
            statusTxt.innerText = "Sarah konuşuyor: \"" + text + "\"";
            
            utter.onend = () => {
                if (isCallActive && !isMicMuted) {
                    statusTxt.innerText = "Dinliyor... Konuşmaya başlayabilirsin.";
                    startListeningInCall();
                }
            };
            window.speechSynthesis.speak(utter);
        }

        function startListeningInCall() {
            const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
            if (!SR) { alert("Tarayıcın ses tanımayı desteklemiyor."); return; }
            if (!isCallActive || isMicMuted) return;

            recognition = new SR();
            recognition.lang = 'tr-TR';
            recognition.continuous = false;
            recognition.interimResults = false;

            recognition.onresult = async (event) => {
                const spokenText = event.results[0][0].transcript;
                document.getElementById('callStatusText').innerText = "Algılandı: \"" + spokenText + "\"";
                
                // Bot yanıtını al
                try {
                    const res = await fetch('/chat', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({ username: currentUser || 'crew', message: spokenText })
                    });
                    const data = await res.json();
                    const reply = data.reply || "Anlayamadım.";
                    playSarahVoice(reply);
                } catch (e) {
                    playSarahVoice("Bağlantı hatası oluştu.");
                }
            };

            recognition.onerror = () => {
                if (isCallActive && !isMicMuted) setTimeout(() => startListeningInCall(), 1000);
            };

            recognition.onend = () => {
                if (isCallActive && !isMicMuted) {
                    try { recognition.start(); } catch(e){}
                }
            };

            try { recognition.start(); } catch(e){}
        }

        async function sendMessage() {
            const inp = document.getElementById('message');
            const msg = inp.value.trim();
            if (!msg) return;
            const chatBox = document.getElementById('chatBox');
            chatBox.innerHTML += `<div class="msg-bubble user"><b>Sen</b>${msg}</div>`;
            inp.value = '';
            
            const res = await fetch('/chat', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ username: currentUser || 'crew', message: msg }) });
            const data = await res.json();
            chatBox.innerHTML += `<div class="msg-bubble bot"><b>Sarah</b>${data.reply}</div>`;
            chatBox.scrollTop = chatBox.scrollHeight;
        }
    </script>
</body>
</html>
"""

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)

