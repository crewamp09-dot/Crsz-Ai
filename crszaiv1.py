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

# ============ .ENV DESTEĞİ ============
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

# ============ DİZİNLER ============
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
MUSIC_DIR = os.path.join(UPLOAD_DIR, "music")
BG_DIR = os.path.join(UPLOAD_DIR, "background")
AVATAR_DIR = os.path.join(UPLOAD_DIR, "avatars")
STATIC_DIR = os.path.join(BASE_DIR, "static")
DB_FILE = os.path.join(BASE_DIR, "crszbot.db")

os.makedirs(MUSIC_DIR, exist_ok=True)
os.makedirs(BG_DIR, exist_ok=True)
os.makedirs(AVATAR_DIR, exist_ok=True)
os.makedirs(STATIC_DIR, exist_ok=True)

# API KEY .env DOSYASINDAN OKUNUR - KODA YAZMA!
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
if not GROQ_API_KEY:
    print("[UYARI] GROQ_API_KEY bulunamadı! .env dosyasına ekleyin.")
client = Groq(api_key=GROQ_API_KEY)


# ============ RATE LIMITER ============
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


# ============ VERİTABANI ============
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
        is_admin INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS chats (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT, title TEXT, messages TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    conn.commit()
    c.execute("SELECT COUNT(*) FROM users WHERE username = ?", ("crewampfilms",))
    if c.fetchone()[0] == 0:
        hashed = generate_password_hash("123")
        c.execute("INSERT INTO users (username, email, password, is_admin) VALUES (?, ?, ?, 1)",
                  ("crewampfilms", "crszbot052@gmail.com", hashed))
        conn.commit()
        print("[DB] Admin oluşturuldu: crewampfilms / 123")
    conn.close()


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
    except Exception as e:
        print(f"[DB GET HATA] {e}")
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
    except Exception as e:
        print(f"[DB SET HATA] {e}")
        return False


def db_get_music_list():
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT id, filename, original_name FROM music ORDER BY id ASC")
        rows = c.fetchall()
        conn.close()
        return [{"id": r[0], "filename": r[1], "original_name": r[2]} for r in rows]
    except Exception as e:
        print(f"[DB MUSIC HATA] {e}")
        return []


def get_user_from_db(username):
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT id, username, email, password, avatar, is_admin FROM users WHERE LOWER(username) = LOWER(?)", (username,))
        row = c.fetchone()
        conn.close()
        if row:
            return {"id": row[0], "username": row[1], "email": row[2], "password": row[3], "avatar": row[4] or "", "is_admin": bool(row[5])}
        return None
    except Exception as e:
        print(f"[DB USER HATA] {e}")
        return None


def create_user(username, email, password, is_admin=False):
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("INSERT INTO users (username, email, password, is_admin) VALUES (?, ?, ?, ?)",
                  (username, email, generate_password_hash(password), 1 if is_admin else 0))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"[DB CREATE USER HATA] {e}")
        return False


def save_user_avatar(username, filename):
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("UPDATE users SET avatar = ? WHERE LOWER(username) = LOWER(?)", (filename, username))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"[DB AVATAR HATA] {e}")
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
    except Exception as e:
        print(f"[DB DELETE CHAT HATA] {e}")
        return False


# ============ APP STATE ============
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


def save_theme_to_db(theme): db_set("theme", theme)
def save_logo_to_db(icon): db_set("logo_icon", icon)
def save_bot_name_to_db(name): db_set("bot_name", name)


def is_admin_user(username):
    if not username: return False
    if username.lower() in [u.lower() for u in ADMIN_USERS]: return True
    u = get_user_from_db(username)
    return bool(u and u.get("is_admin"))


# ============ WEB SEARCH ============
def web_search(query, max_results=4):
    if requests is None: return ""
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        url = f"https://html.duckduckgo.com/html/?q={requests.utils.quote(query)}"
        r = requests.get(url, headers=headers, timeout=8)
        if r.status_code != 200: return ""
        html = r.text
        results = re.findall(r'<a[^>]*class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>.*?<a[^>]*class="result__snippet"[^>]*>(.*?)</a>', html, re.DOTALL)
        if not results:
            results = re.findall(r'<a[^>]*class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', html, re.DOTALL)
        out = []
        for item in results[:max_results]:
            if len(item) >= 2:
                title = re.sub(r'<[^>]+>', '', item[1]).strip()
                snippet = re.sub(r'<[^>]+>', '', item[2]).strip() if len(item) > 2 else ""
                out.append(f"- {title}: {snippet[:250]}")
        return "\n".join(out)
    except Exception as e:
        print("Web search hatası:", e)
        return ""


def should_search(msg):
    triggers = ["araştır", "araştıralım", "güncel", "son dakika", "haber", "bugün", "2025", "2026", "kimdir", "nedir", "nasıl yapılır", "fiyat", "kaç tl", "ne zaman", "nerede", "web'de", "internetten", "search", "google"]
    m = msg.lower()
    return any(t in m for t in triggers)


# ============ AI RESPONSE ============
def get_ai_response(username, user_message, image_data=None):
    is_owner = is_admin_user(username)
    if not is_owner and ("samimi" in user_message.lower() and ("konuş" in user_message.lower() or "ol" in user_message.lower())):
        user_samimi_status[username] = True
    samimi_mode = is_owner or user_samimi_status.get(username, False)

    if is_owner:
        persona = (
            f"Senin adın {APP_STATE['bot_name']}. Karşındaki kişi senin sahibin crewampfilms. "
            "Onunla konuşurken samimi, rahat ve gerektiğinde hafif arsız bir dille konuş. "
            "ÖNEMLİ: 'kanka', 'kardeşim', 'bro', 'dostum' gibi hitaplar KULLANMA. Doğrudan hitap et veya ismiyle seslen. "
            "Asla resmi olma, uzun yıllardır arkadaşmışsınız gibi davran. "
            "Kodları uygun markdown blokları içinde, adım adım açıklamaları numaralandırılmış listeler halinde sun."
        )
    elif samimi_mode:
        persona = f"Senin adın {APP_STATE['bot_name']}. Karşındaki kullanıcı ({username}) ile samimi, dostça bir dille konuş. 'kanka' gibi hitaplar kullanma."
    else:
        persona = f"Senin adın {APP_STATE['bot_name']}. Karşındaki kullanıcı ({username}) ile resmi, kibar ve yardımcı bir dille konuş."

    messages = [{"role": "system", "content": persona}]

    if image_data:
        if "," in image_data: image_data = image_data.split(",", 1)[1]
        messages.append({"role": "user", "content": [
            {"type": "text", "text": user_message if user_message else "Bu fotoğraftaki nedir? Analiz et."},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_data}"}}
        ]})
        model_chain = ["meta-llama/llama-4-scout-17b-16e-instruct", "meta-llama/llama-4-maverick-17b-128e-instruct"]
    else:
        search_context = ""
        if should_search(user_message):
            print(f"[WEB SEARCH] '{user_message}'")
            search_context = web_search(user_message)
            if search_context:
                search_context = f"\n\n[WEB ARAŞTIRMASI SONUÇLARI]\n{search_context}\n\nYukarıdaki güncel bilgileri kullanarak doğal bir yanıt ver."
        full_message = user_message + search_context
        messages.append({"role": "user", "content": full_message})
        model_chain = ["openai/gpt-oss-20b", "openai/gpt-oss-120b"]

    last_error = None
    for model_name in model_chain:
        try:
            print(f"[MODEL] Deneniyor: {model_name}")
            completion = client.chat.completions.create(
                model=model_name, messages=messages, temperature=0.7, max_tokens=1500, timeout=30.0
            )
            reply = completion.choices[0].message.content.strip()
            if reply:
                print(f"[MODEL] Başarılı: {model_name}")
                return reply
        except Exception as e:
            last_error = str(e)
            err = last_error.lower()
            print(f"[MODEL HATA] {model_name}: {err[:200]}")
            if "api key" in err or "401" in err or "invalid_api_key" in err:
                return "API anahtarı geçersiz. Groq konsolundan yeni anahtar alman gerekiyor."
            if "rate" in err or "429" in err:
                return "Şu an çok fazla istek var, birkaç saniye sonra tekrar dene."
            continue

    if last_error: return f"Modeller yanıt vermedi. Son hata: {last_error[:300]}"
    return "Bilinmeyen bir hata oluştu."


# ============ ROUTES ============
@app.route("/")
def dashboard():
    current_user = session.get('username', "")
    is_admin = is_admin_user(current_user) if current_user else False
    music_list = db_get_music_list()
    user_avatar = ""
    if current_user:
        u = get_user_from_db(current_user)
        if u: user_avatar = u.get("avatar", "")
    return render_template_string(
        HTML_TEMPLATE, app_state=APP_STATE, current_user=current_user,
        is_admin=is_admin, logged_in='username' in session,
        music_list=music_list, user_avatar=user_avatar
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


@app.route("/static/<path:filename>")
def serve_static(filename):
    return send_from_directory(STATIC_DIR, filename)


# ============ PWA ============
@app.route("/manifest.json")
def manifest():
    return jsonify({
        "name": APP_STATE["bot_name"],
        "short_name": "CrszBot",
        "start_url": "/",
        "display": "standalone",
        "background_color": APP_STATE["theme"]["bg_deep"],
        "theme_color": APP_STATE["theme"]["accent1"],
        "orientation": "portrait",
        "icons": [
            {"src": "/static/icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any maskable"},
            {"src": "/static/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any maskable"}
        ]
    })


@app.route("/service-worker.js")
def service_worker():
    sw = """
    const CACHE_NAME = 'crszbot-v1';
    self.addEventListener('install', e => { self.skipWaiting(); });
    self.addEventListener('activate', e => { e.waitUntil(self.clients.claim()); });
    self.addEventListener('fetch', e => {
        if (e.request.method !== 'GET') return;
        e.respondWith(fetch(e.request).catch(() => caches.match(e.request)));
    });
    """
    return app.response_class(sw, mimetype="application/javascript")


# ============ BAKIM MODU ============
@app.route("/maintenance/check", methods=["GET"])
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


# ============ CHAT ============
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
        traceback.print_exc()
        return jsonify({"reply": f"Sunucu hatası: {str(e)}", "status": "error"}), 500


@app.route("/auth", methods=["POST"])
@rate_limit(max_calls=10, window_seconds=60)
def auth():
    data = request.get_json(silent=True) or {}
    action = data.get("action")
    username = data.get("username", "").strip()
    email = data.get("email", "").strip()
    password = data.get("password", "").strip()

    if not username or not password:
        return jsonify({"status": "error", "message": "Kullanıcı adı ve şifre zorunludur."})

    existing = get_user_from_db(username)

    if action == "register":
        if existing: return jsonify({"status": "error", "message": "Bu kullanıcı adı zaten alınmış."})
        if len(password) < 3: return jsonify({"status": "error", "message": "Şifre en az 3 karakter olmalı."})
        ok = create_user(username, email, password, is_admin=False)
        if not ok: return jsonify({"status": "error", "message": "Kayıt oluşturulamadı."})
        session.permanent = True
        session['username'] = username
        return jsonify({"status": "success", "message": "Kayıt başarılı!", "username": username, "is_admin": False})

    elif action == "login":
        if existing and check_password_hash(existing["password"], password):
            session.permanent = True
            session['username'] = existing["username"]
            return jsonify({"status": "success", "message": "Giriş başarılı!", "username": existing["username"], "is_admin": existing["is_admin"]})
        return jsonify({"status": "error", "message": "Hatalı kullanıcı adı veya şifre!"})

    return jsonify({"status": "error", "message": "Geçersiz işlem."})


@app.route("/logout", methods=["POST"])
def logout():
    session.pop('username', None)
    return jsonify({"status": "success", "message": "Çıkış yapıldı."})


@app.route("/update-profile", methods=["POST"])
def update_profile():
    if 'username' not in session:
        return jsonify({"status": "error", "message": "Giriş yapmadın."}), 403
    data = request.get_json(silent=True) or {}
    APP_STATE["bot_name"] = data.get("bot_name", APP_STATE["bot_name"])
    save_bot_name_to_db(APP_STATE["bot_name"])
    return jsonify({"status": "success", "message": "Profil güncellendi."})


# ============ CHATS API ============
@app.route("/chats", methods=["GET"])
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


# ============ AVATAR ============
@app.route("/upload-avatar", methods=["POST"])
def upload_avatar():
    if 'username' not in session:
        return jsonify({"status": "error", "message": "Giriş yapmadın."}), 403
    if 'file' not in request.files:
        return jsonify({"status": "error", "message": "Dosya yok."}), 400
    file = request.files['file']
    if file.filename == "": return jsonify({"status": "error", "message": "Dosya seçilmedi."}), 400
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in [".png", ".jpg", ".jpeg", ".webp", ".gif"]:
        return jsonify({"status": "error", "message": "Sadece PNG/JPG/WEBP/GIF."}), 400
    unique_name = f"av_{uuid.uuid4().hex[:12]}{ext}"
    filepath = os.path.join(AVATAR_DIR, unique_name)
    file.save(filepath)
    save_user_avatar(session['username'], unique_name)
    return jsonify({"status": "success", "avatar": unique_name, "message": "Avatar güncellendi."})


# ============ ADMIN USERS ============
@app.route("/admin/users", methods=["GET"])
def admin_users_list():
    if 'username' not in session or not is_admin_user(session['username']):
        return jsonify({"status": "error"}), 403
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT id, username, email, is_admin, created_at FROM users ORDER BY id ASC")
    rows = c.fetchall()
    conn.close()
    users = [{"id": r[0], "username": r[1], "email": r[2], "is_admin": bool(r[3]), "created_at": r[4]} for r in rows]
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
        return jsonify({"status": "error", "message": "Kullanıcı yok."}), 404
    new_val = 0 if row[0] else 1
    c.execute("UPDATE users SET is_admin = ? WHERE id = ?", (new_val, user_id))
    conn.commit()
    conn.close()
    return jsonify({"status": "success", "is_admin": bool(new_val)})


# ============ ADMIN: TEMA ============
@app.route("/admin/update-theme", methods=["POST"])
def admin_update_theme():
    if 'username' not in session or not is_admin_user(session['username']):
        return jsonify({"status": "error", "message": "Yetkin yok."}), 403
    data = request.get_json(silent=True) or {}
    theme = APP_STATE.get("theme", {})
    for key in ["bg_deep", "accent1", "accent2", "accent3", "glass_opacity", "aurora_opacity"]:
        if key in data: theme[key] = data[key]
    APP_STATE["theme"] = theme
    save_theme_to_db(theme)
    if "logo_icon" in data:
        APP_STATE["logo_icon"] = data["logo_icon"]
        save_logo_to_db(data["logo_icon"])
    return jsonify({"status": "success", "message": "Tema güncellendi.", "theme": theme, "logo_icon": APP_STATE["logo_icon"]})


@app.route("/admin/get-theme", methods=["GET"])
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
    filepath = os.path.join(BG_DIR, unique_name)
    file.save(filepath)
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
        return jsonify({"status": "error", "message": "Desteklenmeyen format."}), 400
    current = db_get_music_list()
    if len(current) >= 3:
        return jsonify({"status": "error", "message": "Maksimum 3 müzik."}), 400
    unique_name = f"music_{uuid.uuid4().hex[:12]}{ext}"
    filepath = os.path.join(MUSIC_DIR, unique_name)
    file.save(filepath)
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


@app.route("/music-list", methods=["GET"])
def music_list_api():
    return jsonify({"status": "success", "music": db_get_music_list()})


# ============ 404 ============
@app.errorhandler(404)
def not_found(e):
    return """
    <!DOCTYPE html>
    <html><head><meta charset="UTF-8"><title>404 - Bulunamadı</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">
    <style>
        body { background:#07070a; color:#fff; font-family: 'Inter',sans-serif;
               display:flex; align-items:center; justify-content:center; height:100vh; margin:0;
               overflow:hidden; position: relative; }
        body::before {
            content:''; position: fixed; inset: -100px;
            background: radial-gradient(circle at 20% 30%, #3B82F6, transparent 40%),
                        radial-gradient(circle at 80% 70%, #8B5CF6, transparent 40%),
                        radial-gradient(circle at 50% 50%, #06B6D4, transparent 40%);
            filter: blur(140px); opacity: 0.35; z-index: -1;
        }
        .box { text-align:center; padding:50px 40px; background:rgba(255,255,255,0.04);
               border:1px solid rgba(255,255,255,0.08); border-radius:28px;
               backdrop-filter: blur(24px); -webkit-backdrop-filter: blur(24px);
               max-width: 420px; box-shadow: 0 25px 60px rgba(0,0,0,0.7); }
        h1 { font-size:96px; margin:0; line-height: 1; font-weight: 800;
             background: linear-gradient(135deg,#3B82F6,#8B5CF6,#06B6D4);
             -webkit-background-clip:text; background-clip:text; -webkit-text-fill-color:transparent; }
        h2 { font-size: 18px; margin: 12px 0; color: #fff; font-weight: 700; }
        p { color:#94A3B8; margin: 12px 0 28px; font-size: 14px; line-height: 1.5; }
        a { background: linear-gradient(135deg,#3B82F6,#8B5CF6); color:#fff; padding:14px 28px;
            border-radius:14px; text-decoration:none; font-weight:600; display:inline-block;
            font-size: 14px; transition: transform 0.2s, box-shadow 0.2s;
            box-shadow: 0 6px 20px rgba(59,130,246,0.35); }
        a:hover { transform: translateY(-2px); box-shadow: 0 10px 28px rgba(59,130,246,0.5); }
    </style>
    </head><body>
        <div class="box">
            <h1>404</h1>
            <h2>Sayfa Bulunamadı</h2>
            <p>Aradığın sayfa burada yok.<br>Ana sayfaya dönüp tekrar dene.</p>
            <a href="/">← Ana Sayfaya Dön</a>
        </div>
    </body></html>
    """, 404


# ============ HTML ============
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
            --glass-bg: rgba(255, 255, 255, {{ app_state.theme.glass_opacity }});
            --glass-border: rgba(255, 255, 255, 0.08);
            --primary-gradient: linear-gradient(135deg, var(--accent1) 0%, var(--accent2) 50%, var(--accent3) 100%);
            --text-main: #F8FAFC;
            --text-muted: #94A3B8;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Inter', sans-serif; -webkit-tap-highlight-color: transparent; }
        html, body {
            background-color: var(--bg-deep);
            color: var(--text-main);
            height: 100%; width: 100%;
            overflow: hidden; position: fixed;
            top: 0; left: 0; right: 0; bottom: 0;
            transition: background-color 0.4s ease;
        }
        #bgMedia { position: fixed; inset: 0; z-index: -3; width: 100%; height: 100%; object-fit: cover; display: none; }
        #bgMedia.active { display: block; }
        #bgVideo { position: fixed; inset: 0; z-index: -3; width: 100%; height: 100%; object-fit: cover; display: none; }
        #bgVideo.active { display: block; }
        #bgOverlay { position: fixed; inset: 0; z-index: -2; background: rgba(0,0,0,0.65); backdrop-filter: blur(2px); display: none; }
        #bgOverlay.active { display: block; }
        #authOverlay {
            position: fixed; inset: 0;
            background: rgba(7, 7, 10, 0.92);
            backdrop-filter: blur(30px); -webkit-backdrop-filter: blur(30px);
            z-index: 2000; display: flex; align-items: center; justify-content: center;
            padding: 20px; transition: opacity 0.4s ease;
        }
        #authOverlay.hidden { display: none; }
        .auth-card {
            width: 100%; max-width: 420px; padding: 30px;
            background: rgba(255, 255, 255, 0.04);
            border: 1px solid var(--glass-border); border-radius: 24px;
            box-shadow: 0 25px 50px rgba(0,0,0,0.6);
            backdrop-filter: blur(20px); -webkit-backdrop-filter: blur(20px);
        }
        .auth-tabs { display: flex; gap: 10px; margin-bottom: 20px; background: rgba(0,0,0,0.3); padding: 4px; border-radius: 12px; }
        .auth-tab { flex: 1; padding: 10px; text-align: center; font-size: 13px; font-weight: 600; color: var(--text-muted); cursor: pointer; border-radius: 8px; transition: 0.2s; }
        .auth-tab.active { background: rgba(255,255,255,0.1); color: #fff; }
        .auth-input { width: 100%; background: rgba(255,255,255,0.05); border: 1px solid var(--glass-border); border-radius: 12px; padding: 12px 16px; color: white; font-size: 14px; margin-bottom: 14px; outline: none; transition: 0.2s; }
        .auth-input:focus { border-color: var(--accent1); box-shadow: 0 0 0 3px rgba(59,130,246,0.2); }
        .auth-btn { width: 100%; background: var(--primary-gradient); color: white; border: none; padding: 12px; border-radius: 12px; font-weight: 600; cursor: pointer; font-size: 14px; box-shadow: 0 4px 15px rgba(59,130,246,0.3); }
        .auth-btn:disabled { opacity: 0.6; cursor: wait; }
        .modal-overlay { display: none; position: fixed; inset: 0; background: rgba(0,0,0,0.7); backdrop-filter: blur(10px); -webkit-backdrop-filter: blur(10px); z-index: 1500; align-items: center; justify-content: center; padding: 20px; }
        .modal-overlay.active { display: flex; }
        .modal-card { width: 100%; max-width: 560px; max-height: 90vh; overflow-y: auto; background: #0d1117; border: 1px solid var(--glass-border); border-radius: 20px; padding: 25px; }
        .modal-card h3 { font-size: 15px; margin-bottom: 14px; color: #fff; display: flex; align-items: center; gap: 8px; }
        .modal-label { font-size: 10px; color: var(--text-muted); text-transform: uppercase; margin-bottom: 4px; display: block; margin-top: 10px; }
        .aurora-bg { position: fixed; inset: 0; pointer-events: none; z-index: -1; filter: blur(140px); opacity: {{ app_state.theme.aurora_opacity }}; overflow: hidden; transition: opacity 0.4s ease; }
        .aurora-blob { position: absolute; border-radius: 50%; transition: background 0.4s ease; }
        .blob-1 { width: 350px; height: 350px; background: var(--accent1); top: -50px; left: -50px; }
        .blob-2 { width: 450px; height: 450px; background: var(--accent2); bottom: -50px; right: -50px; }
        .blob-3 { width: 300px; height: 300px; background: var(--accent3); top: 40%; left: 40%; opacity: 0.5; }
        .app-layout { display: flex; height: 100dvh; width: 100vw; padding: 12px; gap: 12px; overflow: hidden; }
        .glass-card { background: var(--glass-bg); backdrop-filter: blur(20px) saturate(180%); -webkit-backdrop-filter: blur(20px) saturate(180%); border: 1px solid var(--glass-border); border-radius: 16px; }
        .sidebar { width: 260px; min-width: 260px; display: flex; flex-direction: column; padding: 14px; gap: 10px; height: calc(100dvh - 24px); flex-shrink: 0; }
        .logo-area { display: flex; align-items: center; gap: 10px; padding-bottom: 10px; border-bottom: 1px solid var(--glass-border); }
        .logo-icon { width: 34px; height: 34px; background: var(--primary-gradient); border-radius: 10px; display: flex; align-items: center; justify-content: center; color: white; flex-shrink: 0; }
        .logo-text { min-width: 0; flex: 1; }
        .logo-text h1 { font-size: 13px; font-weight: 700; color: #fff; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
        .logo-text p { font-size: 10px; color: var(--text-muted); }
        .new-chat-btn { background: rgba(255,255,255,0.05); border: 1px solid var(--glass-border); color: #fff; padding: 9px; border-radius: 10px; font-size: 12px; font-weight: 500; cursor: pointer; display: flex; align-items: center; justify-content: center; gap: 6px; transition: 0.2s; }
        .new-chat-btn:hover { background: rgba(255,255,255,0.1); border-color: var(--accent1); }
        .quick-stats { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; margin-top: 4px; }
        .stat-card { background: rgba(255,255,255,0.03); border: 1px solid var(--glass-border); border-radius: 10px; padding: 8px; text-align: center; }
        .stat-card .stat-value { font-size: 15px; font-weight: 700; color: #fff; }
        .stat-card .stat-label { font-size: 9px; color: var(--text-muted); text-transform: uppercase; margin-top: 2px; }
        .chat-history-list { flex: 1; overflow-y: auto; display: flex; flex-direction: column; gap: 4px; min-height: 0; }
        .history-item { padding: 9px 10px; border-radius: 8px; font-size: 12px; color: var(--text-muted); cursor: pointer; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; display: flex; align-items: center; gap: 8px; }
        .history-item:hover, .history-item.active { background: rgba(59, 130, 246, 0.15); color: #fff; }
        .sidebar-footer { border-top: 1px solid var(--glass-border); padding-top: 8px; display: flex; flex-direction: column; gap: 6px; }
        .footer-btn { background: transparent; border: 1px solid var(--glass-border); color: #fff; padding: 8px; border-radius: 8px; font-size: 12px; cursor: pointer; display: flex; align-items: center; gap: 8px; transition: 0.2s; }
        .footer-btn:hover { background: rgba(255,255,255,0.06); }
        .main-workspace { flex: 1; display: flex; flex-direction: column; height: calc(100dvh - 24px); overflow: hidden; min-width: 0; position: relative; }
        header { padding: 12px 18px; border-bottom: 1px solid var(--glass-border); display: flex; justify-content: space-between; align-items: center; background: rgba(10, 10, 15, 0.4); flex-shrink: 0; gap: 8px; }
        header h2 { font-size: 13px; font-weight: 600; color: #E2E8F0; display: flex; align-items: center; gap: 6px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
        .menu-toggle-btn { display: none; background: transparent; border: 1px solid var(--glass-border); color: #fff; padding: 6px; border-radius: 8px; cursor: pointer; align-items: center; justify-content: center; flex-shrink: 0; }
        .status-badge { font-size: 10px; color: #38BDF8; background: rgba(56, 189, 248, 0.1); border: 1px solid rgba(56, 189, 248, 0.2); padding: 3px 8px; border-radius: 20px; display: flex; align-items: center; gap: 5px; flex-shrink: 0; white-space: nowrap; }
        .status-dot { width: 5px; height: 5px; background: #38BDF8; border-radius: 50%; box-shadow: 0 0 6px #38BDF8; }
        .icon-action-btn { background: rgba(56,189,248,0.1); border: 1px solid rgba(56,189,248,0.3); color: #38BDF8; padding: 6px; border-radius: 8px; cursor: pointer; display: flex; align-items: center; justify-content: center; flex-shrink: 0; transition: 0.2s; }
        .icon-action-btn:hover { background: rgba(56,189,248,0.2); }
        .icon-action-btn.muted { color: #F87171; border-color: rgba(248,113,113,0.3); background: rgba(248,113,113,0.1); }
        .icon-action-btn.recording { color: #F87171; border-color: #F87171; background: rgba(248,113,113,0.2); animation: pulseRec 1.2s infinite; }
        @keyframes pulseRec { 0%,100% { box-shadow: 0 0 0 0 rgba(248,113,113,0.7); } 50% { box-shadow: 0 0 0 8px rgba(248,113,113,0); } }
        .chat-container { flex: 1; padding: 16px; overflow-y: auto; overflow-x: hidden; display: flex; flex-direction: column; gap: 14px; min-height: 0; -webkit-overflow-scrolling: touch; }
        .msg-bubble { max-width: 85%; padding: 12px 16px; border-radius: 12px; font-size: 13px; line-height: 1.55; word-break: break-word; overflow-wrap: anywhere; position: relative; }
        .msg-bubble.user { background: rgba(255, 255, 255, 0.05); border: 1px solid var(--glass-border); align-self: flex-start; color: #CBD5E1; }
        .msg-bubble.bot { background: rgba(20, 25, 40, 0.8); border: 1px solid rgba(59, 130, 246, 0.3); color: white; align-self: flex-end; width: 100%; max-width: 90%; }
        .msg-bubble b { display: block; font-size: 10px; margin-bottom: 4px; opacity: 0.7; text-transform: uppercase; }
        .msg-img { max-width: 100%; border-radius: 8px; margin-top: 6px; display: block; }
        .msg-actions { position: absolute; top: 6px; right: 6px; opacity: 0; transition: 0.2s; display: flex; gap: 4px; }
        .msg-bubble:hover .msg-actions { opacity: 1; }
        .msg-action-btn { background: rgba(255,255,255,0.1); border: none; color: #fff; padding: 3px 6px; border-radius: 4px; font-size: 11px; cursor: pointer; }
        .msg-action-btn:hover { background: rgba(255,255,255,0.2); }
        .typing-dots { display: inline-flex; gap: 3px; vertical-align: middle; }
        .typing-dots span { width: 6px; height: 6px; border-radius: 50%; background: #38BDF8; display: inline-block; animation: typingBounce 1.4s infinite ease-in-out both; }
        .typing-dots span:nth-child(1) { animation-delay: -0.32s; }
        .typing-dots span:nth-child(2) { animation-delay: -0.16s; }
        @keyframes typingBounce {
            0%, 80%, 100% { transform: scale(0.6); opacity: 0.5; }
            40% { transform: scale(1); opacity: 1; }
        }
        pre { background: #040406 !important; border: 1px solid var(--glass-border); border-radius: 8px; padding: 10px; margin: 8px 0; overflow-x: auto; max-width: 100%; }
        code { font-family: 'Consolas', 'Monaco', monospace; font-size: 12px; color: #38BDF8; }
        .code-container { margin: 8px 0; max-width: 100%; }
        .code-header { display: flex; justify-content: space-between; align-items: center; font-size: 11px; color: var(--text-muted); margin-bottom: 4px; }
        .copy-code-btn { background: rgba(255,255,255,0.1); border: none; color: #fff; padding: 3px 6px; border-radius: 4px; font-size: 10px; cursor: pointer; }
        .control-panel { padding: 12px 16px; border-top: 1px solid var(--glass-border); background: rgba(10, 10, 15, 0.9); display: flex; gap: 10px; align-items: center; flex-shrink: 0; width: 100%; }
        .input-wrapper { background: rgba(255, 255, 255, 0.04); border: 1px solid var(--glass-border); border-radius: 12px; display: flex; align-items: center; padding: 0 10px; flex: 1; min-width: 0; }
        .input-wrapper input { background: transparent; border: none; outline: none; color: white; padding: 10px 6px; font-size: 13px; width: 100%; min-width: 0; }
        .upload-icon-btn { background: transparent; border: none; color: var(--text-muted); cursor: pointer; padding: 4px; display: flex; align-items: center; flex-shrink: 0; }
        .upload-icon-btn:hover { color: var(--accent1); }
        .send-btn { background: var(--primary-gradient); color: white; border: none; padding: 10px 18px; border-radius: 12px; font-weight: 600; font-size: 13px; cursor: pointer; display: flex; align-items: center; gap: 6px; flex-shrink: 0; }
        .avatar-btn { width: 34px; height: 34px; border-radius: 10px; background: var(--primary-gradient); color: #fff; display: flex; align-items: center; justify-content: center; font-weight: 700; cursor: pointer; overflow: hidden; flex-shrink: 0; border: 1px solid var(--glass-border); }
        .avatar-btn img { width: 100%; height: 100%; object-fit: cover; }
        @media(max-width: 850px) {
            .app-layout { padding: 8px; gap: 8px; }
            .sidebar { position: fixed; top: 8px; left: 8px; height: calc(100dvh - 16px); z-index: 1000; background: #0d1117; box-shadow: 20px 0 60px rgba(0,0,0,0.9); transform: translateX(-110%); transition: transform 0.3s ease; width: 260px; min-width: 260px; }
            .sidebar.mobile-open { transform: translateX(0); }
            .menu-toggle-btn { display: flex; }
            .main-workspace { height: calc(100dvh - 16px); }
            header { padding: 10px 12px; }
            .chat-container { padding: 12px; }
            .control-panel { padding: 10px; gap: 8px; }
            .msg-bubble { font-size: 12.5px; padding: 10px 13px; max-width: 92%; }
            .send-btn { padding: 10px 14px; }
            .send-btn span { display: none; }
        }
        @media(max-width: 400px) {
            .send-btn { padding: 10px 12px; }
            .upload-icon-btn { padding: 2px; }
            .input-wrapper { padding: 0 6px; }
        }
        .sidebar-overlay { display: none; position: fixed; inset: 0; background: rgba(0,0,0,0.6); backdrop-filter: blur(4px); -webkit-backdrop-filter: blur(4px); z-index: 999; }
        .sidebar-overlay.active { display: block; }
        ::-webkit-scrollbar { width: 4px; height: 4px; }
        ::-webkit-scrollbar-thumb { background: rgba(255, 255, 255, 0.1); border-radius: 10px; }
        ::-webkit-scrollbar-track { background: transparent; }
        .color-picker-row { display: flex; align-items: center; gap: 10px; margin-bottom: 8px; }
        .color-picker-row label { flex: 1; font-size: 11px; color: var(--text-muted); }
        .color-picker-row input[type="color"] { width: 40px; height: 30px; border: 1px solid var(--glass-border); border-radius: 6px; background: transparent; cursor: pointer; }
        .range-row { display: flex; align-items: center; gap: 10px; margin-bottom: 8px; }
        .range-row label { flex: 1; font-size: 11px; color: var(--text-muted); }
        .range-row input[type="range"] { flex: 1; accent-color: var(--accent1); }
        .range-row span { font-size: 11px; color: #fff; min-width: 30px; text-align: right; }
        .logo-picker { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; margin-top: 8px; }
        .logo-option { background: rgba(255,255,255,0.04); border: 1px solid var(--glass-border); border-radius: 10px; padding: 10px; display: flex; align-items: center; justify-content: center; cursor: pointer; transition: 0.2s; color: #fff; }
        .logo-option:hover { background: rgba(255,255,255,0.1); border-color: var(--accent1); }
        .logo-option.selected { border-color: var(--accent1); background: rgba(59,130,246,0.15); }
        .music-item { display: flex; align-items: center; gap: 8px; padding: 8px 10px; background: rgba(255,255,255,0.03); border: 1px solid var(--glass-border); border-radius: 8px; margin-bottom: 6px; font-size: 12px; }
        .music-item .name { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: #fff; }
        .music-item .del-btn { background: rgba(239,68,68,0.15); border: 1px solid rgba(239,68,68,0.3); color: #F87171; padding: 4px 8px; border-radius: 6px; font-size: 10px; cursor: pointer; }
        .user-item { display: flex; align-items: center; gap: 8px; padding: 8px 10px; background: rgba(255,255,255,0.03); border: 1px solid var(--glass-border); border-radius: 8px; margin-bottom: 6px; font-size: 12px; }
        .user-item .name { flex: 1; min-width: 0; color: #fff; }
        .user-item .name small { color: var(--text-muted); font-size: 10px; display: block; }
        .user-item .admin-badge { font-size: 9px; padding: 2px 6px; background: rgba(52,211,153,0.15); color: #34D399; border-radius: 4px; }
        .user-item .usr-btn { background: rgba(255,255,255,0.05); border: 1px solid var(--glass-border); color: #fff; padding: 4px 8px; border-radius: 6px; font-size: 10px; cursor: pointer; }
        .user-item .usr-btn.danger { background: rgba(239,68,68,0.15); color: #F87171; border-color: rgba(239,68,68,0.3); }
        .toggle-row { display:flex; align-items:center; gap:10px; padding:10px; background:rgba(255,255,255,0.03); border:1px solid var(--glass-border); border-radius:10px; margin-top: 4px; }
        .toggle-row label { flex:1; font-size:12px; color:#fff; }
        .toggle-row input[type="checkbox"] { width:20px; height:20px; accent-color:var(--accent1); cursor:pointer; }
        .toast { position: fixed; top: 20px; left: 50%; transform: translateX(-50%) translateY(-100px); background: #0d1117; border: 1px solid var(--accent1); color: #fff; padding: 14px 22px; border-radius: 14px; font-size: 14px; font-weight: 500; z-index: 9999; box-shadow: 0 10px 40px rgba(0,0,0,0.6); transition: transform 0.3s ease, opacity 0.3s ease; max-width: 90vw; text-align: center; backdrop-filter: blur(20px); }
        .toast.show { transform: translateX(-50%) translateY(0); }
        .toast.success { border-color: #34D399; }
        .toast.error { border-color: #F87171; }
        .tab-buttons { display: flex; gap: 6px; margin-bottom: 14px; background: rgba(0,0,0,0.3); padding: 4px; border-radius: 10px; }
        .tab-btn { flex: 1; padding: 8px; text-align: center; font-size: 11px; font-weight: 600; color: var(--text-muted); cursor: pointer; border-radius: 6px; transition: 0.2s; }
        .tab-btn.active { background: rgba(255,255,255,0.1); color: #fff; }
    </style>
</head>
<body>

    <img id="bgMedia" alt="">
    <video id="bgVideo" autoplay muted loop playsinline></video>
    <div id="bgOverlay"></div>

    <audio id="bgMusic" loop></audio>

    <div id="authOverlay" class="{% if logged_in %}hidden{% endif %}">
        <div class="auth-card">
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
            </div>
            <input type="text" id="authUsername" class="auth-input" placeholder="Kullanıcı Adı" autocomplete="username">
            <input type="password" id="authPassword" class="auth-input" placeholder="Şifre" autocomplete="current-password">
            <button class="auth-btn" id="authSubmitBtn" onclick="handleAuth()">Giriş Yap</button>
        </div>
    </div>

    <div class="modal-overlay" id="profileModal">
        <div class="modal-card">
            <h3><i data-lucide="user-cog" width="16" height="16" style="color: var(--accent1);"></i> Profil ve Bot Ayarları</h3>
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
            <div style="display: flex; gap: 8px; margin-top: 14px;">
                <button class="auth-btn" onclick="saveProfile()">Kaydet</button>
                <button class="auth-btn" style="background: rgba(255,255,255,0.1);" onclick="closeModal('profileModal')">İptal</button>
            </div>
            <div style="margin-top: 14px; border-top: 1px solid var(--glass-border); padding-top: 12px;">
                <button class="auth-btn" style="background: rgba(239,68,68,0.15); color: #F87171; border: 1px solid rgba(239,68,68,0.3);" onclick="logout()">
                    <i data-lucide="log-out" width="14" height="14"></i> Çıkış Yap
                </button>
            </div>
        </div>
    </div>

    <div class="modal-overlay" id="adminModal">
        <div class="modal-card">
            <h3><i data-lucide="shield-check" width="16" height="16" style="color: #34D399;"></i> Admin Panel</h3>

            <div class="tab-buttons">
                <div class="tab-btn active" onclick="switchAdminTab('theme', this)">Tema</div>
                <div class="tab-btn" onclick="switchAdminTab('users', this)">Kullanıcılar</div>
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

                <label class="modal-label">Arka Plan Medya (Resim/Video)</label>
                <input type="file" id="themeBgMedia" accept="image/*,video/*" style="display:none" onchange="uploadBackground(event)">
                <div style="display:flex; gap:6px; margin-bottom:8px;">
                    <button class="auth-btn" style="background: rgba(255,255,255,0.1);" onclick="document.getElementById('themeBgMedia').click()">
                        <i data-lucide="upload" width="14" height="14"></i> Medya Yükle
                    </button>
                    <button class="auth-btn" style="background: rgba(255,255,255,0.1);" onclick="clearBgMedia()">Temizle</button>
                </div>

                <label class="modal-label">Müzik Listesi (Max 3)</label>
                <input type="file" id="themeMusic" accept="audio/*" style="display:none" onchange="uploadMusic(event)">
                <div style="display:flex; gap:6px; margin-bottom:8px;">
                    <button class="auth-btn" style="background: rgba(56,189,248,0.15); color: #38BDF8; border: 1px solid rgba(56,189,248,0.3);" onclick="document.getElementById('themeMusic').click()">
                        <i data-lucide="music" width="14" height="14"></i> Müzik Yükle
                    </button>
                </div>
                <div id="musicListContainer">
                    {% for m in music_list %}
                    <div class="music-item">
                        <i data-lucide="music-2" width="14" height="14" style="color:#38BDF8;"></i>
                        <span class="name">{{ m.original_name }}</span>
                        <button class="del-btn" onclick="deleteMusic({{ m.id }})">Sil</button>
                    </div>
                    {% endfor %}
                </div>

                <label class="modal-label">Arka Plan Rengi</label>
                <div class="color-picker-row">
                    <label>Ana Arka Plan</label>
                    <input type="color" id="themeBgDeep" value="{{ app_state.theme.bg_deep }}">
                </div>

                <label class="modal-label">Gradient Renkleri</label>
                <div class="color-picker-row">
                    <label>Renk 1 (Sol)</label>
                    <input type="color" id="themeAccent1" value="{{ app_state.theme.accent1 }}">
                </div>
                <div class="color-picker-row">
                    <label>Renk 2 (Orta)</label>
                    <input type="color" id="themeAccent2" value="{{ app_state.theme.accent2 }}">
                </div>
                <div class="color-picker-row">
                    <label>Renk 3 (Sağ)</label>
                    <input type="color" id="themeAccent3" value="{{ app_state.theme.accent3 }}">
                </div>

                <label class="modal-label">Opaklık Ayarları</label>
                <div class="range-row">
                    <label>Cam Opaklığı</label>
                    <input type="range" id="themeGlassOpacity" min="0" max="0.3" step="0.01" value="{{ app_state.theme.glass_opacity }}">
                    <span id="glassOpacityVal">{{ app_state.theme.glass_opacity }}</span>
                </div>
                <div class="range-row">
                    <label>Aurora Yoğunluğu</label>
                    <input type="range" id="themeAuroraOpacity" min="0" max="0.6" step="0.01" value="{{ app_state.theme.aurora_opacity }}">
                    <span id="auroraOpacityVal">{{ app_state.theme.aurora_opacity }}</span>
                </div>

                <label class="modal-label">Bakım Modu</label>
                <div class="toggle-row">
                    <label>Siteyi bakıma al (sadece adminler girebilir)</label>
                    <input type="checkbox" id="maintenanceToggle" onchange="toggleMaintenance(this.checked)">
                </div>

                <div style="display: flex; gap: 8px; margin-top: 16px;">
                    <button class="auth-btn" onclick="saveTheme()">Kaydet ve Uygula</button>
                    <button class="auth-btn" style="background: rgba(255,255,255,0.1);" onclick="resetTheme()">Sıfırla</button>
                </div>
            </div>

            <div id="adminTab-users" style="display:none;">
                <p style="font-size:11px; color: var(--text-muted); margin-bottom:10px;">Kayıtlı kullanıcılar</p>
                <div id="usersList">Yükleniyor...</div>
            </div>

            <div style="display: flex; gap: 8px; margin-top: 16px;">
                <button class="auth-btn" style="background: rgba(255,255,255,0.1);" onclick="closeModal('adminModal')">Kapat</button>
            </div>
        </div>
    </div>

    <div class="sidebar-overlay" id="sidebarOverlay" onclick="toggleMobileSidebar()"></div>

    <div class="aurora-bg" id="auroraBg">
        <div class="aurora-blob blob-1"></div>
        <div class="aurora-blob blob-2"></div>
        <div class="aurora-blob blob-3"></div>
    </div>

    <div class="app-layout">
        <div class="sidebar glass-card" id="sidebar">
            <div class="logo-area">
                <div class="logo-icon"><i data-lucide="{{ app_state.logo_icon }}" width="16" height="16" id="sidebarLogoIcon"></i></div>
                <div class="logo-text">
                    <h1 id="sidebarBotName">{{ app_state.bot_name }}</h1>
                    <p>AI Studio</p>
                </div>
            </div>
            <button class="new-chat-btn" onclick="startNewChat()">
                <i data-lucide="plus" width="13" height="13"></i> Yeni Sohbet Aç
            </button>
            <div class="quick-stats">
                <div class="stat-card">
                    <div class="stat-value" id="totalReplies">0</div>
                    <div class="stat-label">Cevap</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value" id="totalChats">0</div>
                    <div class="stat-label">Sohbet</div>
                </div>
            </div>
            <div style="font-size: 9px; text-transform: uppercase; color: var(--text-muted); margin-top: 4px;">Sohbetler</div>
            <div class="chat-history-list" id="chatHistoryList">
                <div class="history-item active" onclick="switchChat(0)">
                    <i data-lucide="message-square" width="12" height="12"></i> Varsayılan Sohbet
                </div>
            </div>
            <div class="sidebar-footer">
                <button class="footer-btn" id="adminBtn" style="{% if not is_admin %}display: none;{% endif %} border-color: rgba(52, 211, 153, 0.4); color: #34D399;" onclick="openAdminPanel()">
                    <i data-lucide="shield-check" width="13" height="13"></i> Admin Panel
                </button>
                <button class="footer-btn" onclick="openModal('profileModal')">
                    <i data-lucide="user-cog" width="13" height="13" style="color: var(--accent1);"></i> Profil &amp; Ayarlar
                </button>
            </div>
        </div>

        <div class="main-workspace glass-card">
            <header>
                <div style="display: flex; align-items: center; gap: 10px; min-width: 0;">
                    <button class="menu-toggle-btn" onclick="toggleMobileSidebar()">
                        <i data-lucide="menu" width="16" height="16"></i>
                    </button>
                    <h2><i data-lucide="terminal" width="14" height="14" style="color: var(--accent1);"></i> Otomasyon &amp; AI Stüdyosu</h2>
                </div>
                <div style="display: flex; align-items: center; gap: 8px;">
                    <button class="icon-action-btn" onclick="toggleColorMode()" title="Tema Değiştir" id="themeToggleBtn">
                        <i data-lucide="sun-moon" width="16" height="16"></i>
                    </button>
                    <button class="icon-action-btn" id="musicToggleBtn" onclick="toggleMusic()" title="Müziği Aç/Kapat">
                        <i data-lucide="volume-2" width="16" height="16" id="musicIcon"></i>
                    </button>
                    <div class="status-badge"><div class="status-dot"></div> Aktif</div>
                </div>
            </header>
            <div class="chat-container" id="chatBox">
                <div class="msg-bubble user">
                    <b>Sistem</b>
                    Sistem hazır. Kod, adım adım rehber isteyebilir, fotoğraf yükleyebilir ya da web'de araştırma isteyebilirsin.
                </div>
            </div>
            <div id="imagePreviewContainer" style="padding: 0 16px; display: none;">
                <div style="font-size: 11px; color: #38BDF8; display: flex; align-items: center; gap: 6px; background: rgba(56,189,248,0.1); padding: 4px 8px; border-radius: 6px; width: fit-content;">
                    <span>Fotoğraf Eklendi</span> <span onclick="removeImage()" style="cursor:pointer; font-weight:bold;">×</span>
                </div>
            </div>
            <div class="control-panel">
                <input type="file" id="imageInput" accept="image/*" style="display:none;" onchange="handleImageSelect(event)">
                <button class="upload-icon-btn" onclick="document.getElementById('imageInput').click()" title="Fotoğraf Yükle">
                    <i data-lucide="image" width="18" height="18"></i>
                </button>
                <button class="upload-icon-btn" onclick="toggleVoiceInput()" title="Sesli Yaz" id="voiceBtn">
                    <i data-lucide="mic" width="18" height="18"></i>
                </button>
                <div class="input-wrapper">
                    <input type="text" id="message" placeholder="Mesaj yaz, fotoğraf yükle ya da 'araştır' de..." onkeydown="if(event.key==='Enter') sendMessage()">
                </div>
                <button class="send-btn" onclick="sendMessage()">
                    <span>Gönder</span> <i data-lucide="send" width="13" height="13"></i>
                </button>
            </div>
        </div>
    </div>

    <script>
        lucide.createIcons();
        let authMode = 'login';
        let chats = [{ title: "Varsayılan Sohbet", messages: [] }];
        let activeChatIndex = 0;
        let selectedBase64Image = null;
        let isAdmin = {% if is_admin %}true{% else %}false{% endif %};
        let currentUser = "{{ current_user }}";
        let loggedIn = {% if logged_in %}true{% else %}false{% endif %};
        let selectedLogoIcon = "{{ app_state.logo_icon }}";
        let musicMuted = false;
        let musicPlaylist = [];
        let currentMusicIndex = 0;

        const DEFAULT_THEME = {
            bg_deep: "#07070a", accent1: "#3B82F6", accent2: "#8B5CF6", accent3: "#06B6D4",
            glass_opacity: 0.03, aurora_opacity: 0.25
        };

        // ===== PWA SERVICE WORKER =====
        if ('serviceWorker' in navigator) {
            navigator.serviceWorker.register('/service-worker.js').catch(e => console.log('SW hata:', e));
        }

        // ===== KULLANICI TEMA (localStorage) =====
        (function() {
            const savedMode = localStorage.getItem('crsz_theme_mode') || 'dark';
            if (savedMode === 'light') setTimeout(() => applyColorMode('light'), 50);
        })();

        function applyColorMode(mode) {
            const root = document.documentElement;
            const body = document.body;

            if (mode === 'light') {
                root.style.setProperty('--bg-deep', '#f8fafc');
                root.style.setProperty('--text-main', '#0f172a');
                root.style.setProperty('--text-muted', '#475569');
                root.style.setProperty('--glass-bg', 'rgba(255, 255, 255, 0.75)');
                root.style.setProperty('--glass-border', 'rgba(15, 23, 42, 0.10)');
                body.style.color = '#0f172a';

                let lightStyle = document.getElementById('lightThemeOverride');
                if (!lightStyle) {
                    lightStyle = document.createElement('style');
                    lightStyle.id = 'lightThemeOverride';
                    document.head.appendChild(lightStyle);
                }
                lightStyle.textContent = `
                    body { background: #f8fafc !important; color: #0f172a !important; }
                    header { background: rgba(255, 255, 255, 0.85) !important; border-color: rgba(15,23,42,0.08) !important; }
                    header h2 { color: #0f172a !important; }
                    .glass-card { background: rgba(255, 255, 255, 0.75) !important; border-color: rgba(15,23,42,0.10) !important; box-shadow: 0 4px 20px rgba(15,23,42,0.06) !important; }
                    .logo-text h1 { color: #0f172a !important; }
                    .logo-text p { color: #64748b !important; }
                    .stat-card { background: rgba(15,23,42,0.03) !important; border-color: rgba(15,23,42,0.08) !important; }
                    .stat-card .stat-value { color: #0f172a !important; }
                    .stat-card .stat-label { color: #64748b !important; }
                    .history-item { color: #475569 !important; }
                    .history-item.active { background: rgba(59,130,246,0.12) !important; color: #0f172a !important; }
                    .new-chat-btn { background: rgba(15,23,42,0.04) !important; color: #0f172a !important; border-color: rgba(15,23,42,0.10) !important; }
                    .footer-btn { color: #0f172a !important; border-color: rgba(15,23,42,0.10) !important; }

                    .msg-bubble.user {
                        background: #ffffff !important;
                        border: 1px solid rgba(15,23,42,0.10) !important;
                        color: #0f172a !important;
                        box-shadow: 0 2px 8px rgba(15,23,42,0.04) !important;
                    }
                    .msg-bubble.user b { color: #64748b !important; opacity: 1 !important; }

                    .msg-bubble.bot {
                        background: linear-gradient(135deg, #1e293b, #0f172a) !important;
                        border: 1px solid rgba(59,130,246,0.25) !important;
                        color: #f8fafc !important;
                        box-shadow: 0 4px 16px rgba(15,23,42,0.12) !important;
                    }
                    .msg-bubble.bot b { color: #94a3b8 !important; opacity: 1 !important; }

                    .control-panel { background: rgba(255, 255, 255, 0.85) !important; border-color: rgba(15,23,42,0.08) !important; }
                    .input-wrapper { background: #ffffff !important; border-color: rgba(15,23,42,0.12) !important; }
                    .input-wrapper input { color: #0f172a !important; }
                    .input-wrapper input::placeholder { color: #94a3b8 !important; }
                    .upload-icon-btn { color: #64748b !important; }

                    .msg-action-btn { background: rgba(15,23,42,0.08) !important; color: #0f172a !important; }
                    .msg-action-btn:hover { background: rgba(15,23,42,0.15) !important; }

                    pre { background: #f1f5f9 !important; border-color: rgba(15,23,42,0.08) !important; }
                    code { color: #3b82f6 !important; }

                    .modal-card { background: #ffffff !important; border-color: rgba(15,23,42,0.10) !important; }
                    .modal-card h3 { color: #0f172a !important; }
                    .modal-label { color: #64748b !important; }
                    .auth-input { background: #f8fafc !important; border-color: rgba(15,23,42,0.10) !important; color: #0f172a !important; }
                    .tab-btn { color: #64748b !important; }
                    .tab-btn.active { background: rgba(59,130,246,0.15) !important; color: #0f172a !important; }
                    .tab-buttons { background: rgba(15,23,42,0.05) !important; }
                    .music-item, .user-item, .toggle-row { background: rgba(15,23,42,0.03) !important; border-color: rgba(15,23,42,0.08) !important; }
                    .music-item .name, .user-item .name { color: #0f172a !important; }

                    .aurora-bg { opacity: 0.15 !important; }
                    ::-webkit-scrollbar-thumb { background: rgba(15,23,42,0.15) !important; }
                    .status-badge { background: rgba(59,130,246,0.10) !important; }
                    #bgOverlay { background: rgba(255,255,255,0.55) !important; }
                `;
            } else {
                const oldLight = document.getElementById('lightThemeOverride');
                if (oldLight) oldLight.remove();

                root.style.setProperty('--bg-deep', '{{ app_state.theme.bg_deep }}');
                root.style.setProperty('--text-main', '#F8FAFC');
                root.style.setProperty('--text-muted', '#94A3B8');
                root.style.setProperty('--glass-bg', 'rgba(255, 255, 255, {{ app_state.theme.glass_opacity }})');
                root.style.setProperty('--glass-border', 'rgba(255, 255, 255, 0.08)');
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

        document.addEventListener('keydown', (e) => {
            if (e.ctrlKey && e.key === 'k') { e.preventDefault(); startNewChat(); }
            if (e.ctrlKey && e.key === '/') { e.preventDefault(); document.getElementById('message').focus(); }
            if (e.key === 'Escape') document.querySelectorAll('.modal-overlay.active').forEach(m => m.classList.remove('active'));
        });

        let recognition = null;
        let isRecording = false;

        function toggleVoiceInput() {
            const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
            if (!SR) { showToast("Tarayıcın sesli yazmayı desteklemiyor", "error"); return; }
            const btn = document.getElementById('voiceBtn');
            if (isRecording && recognition) {
                recognition.stop();
                isRecording = false;
                btn.classList.remove('recording');
                return;
            }
            recognition = new SR();
            recognition.lang = 'tr-TR';
            recognition.continuous = false;
            recognition.interimResults = false;
            recognition.onstart = () => { isRecording = true; btn.classList.add('recording'); showToast("Dinliyorum...", "info"); };
            recognition.onresult = (event) => {
                const text = event.results[0][0].transcript;
                const inp = document.getElementById('message');
                inp.value = (inp.value + ' ' + text).trim();
            };
            recognition.onerror = (e) => { isRecording = false; btn.classList.remove('recording'); showToast("Ses hatası: " + e.error, "error"); };
            recognition.onend = () => { isRecording = false; btn.classList.remove('recording'); };
            recognition.start();
        }

        function speakText(idx) {
            const m = chats[activeChatIndex].messages[idx];
            if (!m) return;
            const tmp = document.createElement('div');
            tmp.innerHTML = m.content;
            const text = tmp.innerText;
            if (!('speechSynthesis' in window)) { showToast("Tarayıcın TTS desteklemiyor", "error"); return; }
            window.speechSynthesis.cancel();
            const utter = new SpeechSynthesisUtterance(text);
            utter.lang = 'tr-TR';
            utter.rate = 1.0;
            window.speechSynthesis.speak(utter);
        }

        async function checkMaintenance() {
            try {
                const res = await fetch('/maintenance/check');
                const data = await res.json();
                if (data.enabled && !isAdmin) {
                    document.body.innerHTML = '<div style="background:#07070a; color:#fff; display:flex; align-items:center; justify-content:center; height:100vh; margin:0; font-family:Inter,sans-serif; text-align:center; padding:20px;"><div style="padding:40px; background:rgba(255,255,255,0.04); border:1px solid rgba(255,255,255,0.08); border-radius:24px; backdrop-filter:blur(20px); max-width:400px;"><h1 style="font-size:32px; margin:0 0 12px;">Bakım Modu</h1><p style="color:#94A3B8;">Site şu anda bakımda. Birazdan tekrar dene.</p></div></div>';
                }
            } catch (e) {}
        }
        if (loggedIn) { checkMaintenance(); setInterval(checkMaintenance, 60000); }

        async function toggleMaintenance(enabled) {
            try {
                const res = await fetch('/maintenance/toggle', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ enabled }) });
                const data = await res.json();
                if (data.status === 'success') showToast(enabled ? "Bakım modu AÇIK" : "Bakım modu KAPALI", "success");
            } catch (e) { showToast("Hata", "error"); }
        }

        async function loadMaintenanceStatus() {
            try {
                const res = await fetch('/maintenance/check');
                const data = await res.json();
                const tog = document.getElementById('maintenanceToggle');
                if (tog) tog.checked = !!data.enabled;
            } catch (e) {}
        }

        function showToast(message, type = 'info') {
            const existing = document.querySelector('.toast');
            if (existing) existing.remove();
            const toast = document.createElement('div');
            toast.className = 'toast ' + type;
            toast.innerText = message;
            document.body.appendChild(toast);
            requestAnimationFrame(() => toast.classList.add('show'));
            setTimeout(() => { toast.classList.remove('show'); setTimeout(() => toast.remove(), 400); }, 3000);
        }

        function safeMarkdownParse(text) {
            if (typeof marked !== 'undefined' && marked.parse) {
                try { return marked.parse(text); } catch (e) { console.warn(e); }
            }
            let html = String(text).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
            html = html.replace(/```(\w*)\n([\s\S]*?)```/g, (m, lang, code) => {
                return `<div class="code-container"><div class="code-header"><span>${lang || 'Kod'}</span><button class="copy-code-btn" onclick="copyCode(this)">Kopyala</button></div><pre><code>${code}</code></pre></div>`;
            });
            html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
            html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
            html = html.replace(/\*(.+?)\*/g, '<em>$1</em>');
            html = html.replace(/\n/g, '<br>');
            return html;
        }

        function applyBgMedia(filename, type) {
            const imgEl = document.getElementById('bgMedia');
            const videoEl = document.getElementById('bgVideo');
            const overlay = document.getElementById('bgOverlay');
            if (!filename) { imgEl.classList.remove('active'); videoEl.classList.remove('active'); videoEl.pause(); overlay.classList.remove('active'); return; }
            const bgUrl = '/admin/bg/' + filename;
            if (type === 'video') {
                imgEl.classList.remove('active');
                videoEl.src = bgUrl; videoEl.classList.add('active');
                videoEl.play().catch(e => console.log('video autoplay:', e));
            } else {
                videoEl.classList.remove('active'); videoEl.pause();
                imgEl.src = bgUrl; imgEl.classList.add('active');
            }
            overlay.classList.add('active');
        }

        async function loadThemeFromServer() {
            try {
                const res = await fetch('/admin/get-theme');
                const data = await res.json();
                if (data.status === 'success' && data.theme) {
                    const t = data.theme;
                    applyThemeLocal(t);
                    if (t.bg_media) applyBgMedia(t.bg_media, t.bg_media_type || 'image');
                    if (data.logo_icon) updateLogoIcon(data.logo_icon);
                }
            } catch (e) { console.log('Tema yüklenemedi:', e); }
        }

        async function loadMusic() {
            try {
                const res = await fetch('/music-list');
                const data = await res.json();
                musicPlaylist = data.music || [];
                if (musicPlaylist.length > 0) playMusic(0);
            } catch (e) { console.log('Müzik yüklenemedi:', e); }
        }

        function playMusic(index) {
            const audio = document.getElementById('bgMusic');
            if (musicPlaylist.length === 0) return;
            currentMusicIndex = index % musicPlaylist.length;
            const track = musicPlaylist[currentMusicIndex];
            audio.src = '/uploads/music/' + track.filename;
            audio.volume = 0.4;
            if (!musicMuted) audio.play().catch(e => {});
        }

        document.getElementById('bgMusic').addEventListener('ended', () => { playMusic(currentMusicIndex + 1); });

        function toggleMusic() {
            const audio = document.getElementById('bgMusic');
            const btn = document.getElementById('musicToggleBtn');
            const icon = document.getElementById('musicIcon');
            musicMuted = !musicMuted;
            if (musicMuted) {
                audio.pause();
                btn.classList.add('muted');
                icon.setAttribute('data-lucide', 'volume-x');
            } else {
                if (musicPlaylist.length > 0 && !audio.src) playMusic(0);
                else audio.play().catch(e => {});
                btn.classList.remove('muted');
                icon.setAttribute('data-lucide', 'volume-2');
            }
            lucide.createIcons();
        }

        function applyThemeLocal(theme) {
            const root = document.documentElement;
            root.style.setProperty('--bg-deep', theme.bg_deep);
            root.style.setProperty('--accent1', theme.accent1);
            root.style.setProperty('--accent2', theme.accent2);
            root.style.setProperty('--accent3', theme.accent3);
            root.style.setProperty('--glass-bg', `rgba(255, 255, 255, ${theme.glass_opacity})`);
            document.getElementById('auroraBg').style.opacity = theme.aurora_opacity;
        }

        function updateLogoIcon(iconName) {
            const iconEl = document.getElementById('sidebarLogoIcon');
            if (iconEl) { iconEl.setAttribute('data-lucide', iconName); lucide.createIcons(); }
        }

        document.querySelectorAll('.logo-option').forEach(opt => {
            if (opt.dataset.icon === selectedLogoIcon) opt.classList.add('selected');
            opt.addEventListener('click', () => {
                document.querySelectorAll('.logo-option').forEach(o => o.classList.remove('selected'));
                opt.classList.add('selected');
                selectedLogoIcon = opt.dataset.icon;
            });
        });

        async function uploadBackground(event) {
            const file = event.target.files[0];
            if (!file) return;
            const formData = new FormData(); formData.append('file', file);
            try {
                const res = await fetch('/admin/upload-background', { method: 'POST', body: formData });
                const data = await res.json();
                if (data.status === 'success') { applyBgMedia(data.bg_media, data.bg_media_type); showToast("Arka plan yüklendi!", "success"); }
                else showToast(data.message, "error");
            } catch (err) { showToast("Hata", "error"); }
        }

        async function clearBgMedia() {
            try {
                const res = await fetch('/admin/clear-background', { method: 'POST' });
                const data = await res.json();
                if (data.status === 'success') { applyBgMedia("", ""); showToast("Temizlendi", "success"); }
            } catch (err) { showToast("Hata", "error"); }
        }

        async function uploadMusic(event) {
            const file = event.target.files[0];
            if (!file) return;
            const formData = new FormData(); formData.append('file', file);
            try {
                const res = await fetch('/admin/upload-music', { method: 'POST', body: formData });
                const data = await res.json();
                if (data.status === 'success') {
                    showToast("Müzik yüklendi!", "success");
                    renderMusicList(data.music);
                    musicPlaylist = data.music;
                    if (musicPlaylist.length === 1) playMusic(0);
                } else showToast(data.message, "error");
            } catch (err) { showToast("Hata", "error"); }
        }

        async function deleteMusic(id) {
            if (!confirm("Bu müziği silmek istediğine emin misin?")) return;
            try {
                const res = await fetch('/admin/delete-music/' + id, { method: 'POST' });
                const data = await res.json();
                if (data.status === 'success') { showToast("Silindi", "success"); renderMusicList(data.music); musicPlaylist = data.music; }
            } catch (err) { showToast("Hata", "error"); }
        }

        function renderMusicList(music) {
            const c = document.getElementById('musicListContainer');
            if (!c) return;
            c.innerHTML = '';
            music.forEach(m => {
                c.innerHTML += `<div class="music-item"><i data-lucide="music-2" width="14" height="14" style="color:#38BDF8;"></i><span class="name">${m.original_name}</span><button class="del-btn" onclick="deleteMusic(${m.id})">Sil</button></div>`;
            });
            lucide.createIcons();
        }

        async function saveTheme() {
            if (!isAdmin) { showToast("Yetkin yok.", "error"); return; }
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
                const res = await fetch('/admin/update-theme', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(theme) });
                const data = await res.json();
                if (data.status === 'success') { applyThemeLocal(data.theme); updateLogoIcon(data.logo_icon); showToast("Güncellendi!", "success"); }
                else showToast(data.message, "error");
            } catch (err) { showToast("Bağlantı hatası", "error"); }
        }

        function resetTheme() {
            document.getElementById('themeBgDeep').value = DEFAULT_THEME.bg_deep;
            document.getElementById('themeAccent1').value = DEFAULT_THEME.accent1;
            document.getElementById('themeAccent2').value = DEFAULT_THEME.accent2;
            document.getElementById('themeAccent3').value = DEFAULT_THEME.accent3;
            document.getElementById('themeGlassOpacity').value = DEFAULT_THEME.glass_opacity;
            document.getElementById('themeAuroraOpacity').value = DEFAULT_THEME.aurora_opacity;
            document.getElementById('glassOpacityVal').innerText = DEFAULT_THEME.glass_opacity;
            document.getElementById('auroraOpacityVal').innerText = DEFAULT_THEME.aurora_opacity;
            applyThemeLocal(DEFAULT_THEME);
        }

        async function loadUsers() {
            const c = document.getElementById('usersList');
            c.innerHTML = 'Yükleniyor...';
            try {
                const res = await fetch('/admin/users');
                const data = await res.json();
                if (data.status === 'success') {
                    c.innerHTML = '';
                    data.users.forEach(u => {
                        c.innerHTML += `<div class="user-item"><i data-lucide="user" width="16" height="16" style="color: var(--accent1);"></i><div class="name">${u.username}<small>${u.email || 'e-posta yok'}</small></div>${u.is_admin ? '<span class="admin-badge">ADMIN</span>' : ''}<button class="usr-btn" onclick="toggleAdmin(${u.id})">${u.is_admin ? 'Admin Kaldır' : 'Admin Yap'}</button><button class="usr-btn danger" onclick="deleteUser(${u.id})">Sil</button></div>`;
                    });
                    lucide.createIcons();
                }
            } catch (e) { c.innerHTML = 'Yüklenemedi'; }
        }

        async function toggleAdmin(id) {
            try {
                const res = await fetch('/admin/users/toggle-admin/' + id, { method: 'POST' });
                const data = await res.json();
                if (data.status === 'success') { showToast("Güncellendi", "success"); loadUsers(); }
            } catch (e) {}
        }

        async function deleteUser(id) {
            if (!confirm("Bu kullanıcıyı silmek istediğine emin misin?")) return;
            try {
                const res = await fetch('/admin/users/delete/' + id, { method: 'POST' });
                const data = await res.json();
                if (data.status === 'success') { showToast("Silindi", "success"); loadUsers(); }
                else showToast(data.message, "error");
            } catch (e) {}
        }

        function switchAdminTab(tab, btn) {
            document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            document.getElementById('adminTab-theme').style.display = tab === 'theme' ? 'block' : 'none';
            document.getElementById('adminTab-users').style.display = tab === 'users' ? 'block' : 'none';
            if (tab === 'users') loadUsers();
        }

        async function uploadAvatar(event) {
            const file = event.target.files[0];
            if (!file) return;
            const formData = new FormData(); formData.append('file', file);
            try {
                const res = await fetch('/upload-avatar', { method: 'POST', body: formData });
                const data = await res.json();
                if (data.status === 'success') {
                    showToast("Avatar güncellendi", "success");
                    document.getElementById('profileAvatarBtn').innerHTML = `<img src="/uploads/avatars/${data.avatar}" alt="">`;
                } else showToast(data.message, "error");
            } catch (e) { showToast("Hata", "error"); }
        }

        function toggleMobileSidebar() {
            const s = document.getElementById('sidebar');
            const o = document.getElementById('sidebarOverlay');
            if (s.classList.contains('mobile-open')) { s.classList.remove('mobile-open'); o.classList.remove('active'); }
            else { s.classList.add('mobile-open'); o.classList.add('active'); }
        }
        function openModal(id) { document.getElementById(id).classList.add('active'); }
        function closeModal(id) { document.getElementById(id).classList.remove('active'); }
        function switchAuthTab(mode) {
            authMode = mode;
            const ec = document.getElementById('emailFieldContainer');
            const sb = document.getElementById('authSubmitBtn');
            const lt = document.getElementById('tabLoginBtn');
            const rt = document.getElementById('tabRegisterBtn');
            if (mode === 'register') { ec.style.display = 'block'; sb.innerText = 'Kayıt Ol'; rt.classList.add('active'); lt.classList.remove('active'); }
            else { ec.style.display = 'none'; sb.innerText = 'Giriş Yap'; lt.classList.add('active'); rt.classList.remove('active'); }
        }
        async function handleAuth() {
            const username = document.getElementById('authUsername').value.trim();
            const email = document.getElementById('authEmail').value.trim();
            const password = document.getElementById('authPassword').value.trim();
            if (!username || !password) { showToast("Kullanıcı adı ve şifre zorunlu!", "error"); return; }
            const submitBtn = document.getElementById('authSubmitBtn');
            const originalText = submitBtn.innerText;
            submitBtn.innerText = "İşleniyor..."; submitBtn.disabled = true;
            try {
                const res = await fetch('/auth', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ action: authMode, username, email, password }) });
                const data = await res.json();
                if (data.status === 'success') {
                    currentUser = data.username || username;
                    isAdmin = data.is_admin === true;
                    if (isAdmin) document.getElementById('adminBtn').style.display = 'flex';
                    const overlay = document.getElementById('authOverlay');
                    overlay.style.opacity = '0';
                    setTimeout(() => overlay.classList.add('hidden'), 400);
                    showToast("Giriş başarılı!", "success");
                    setTimeout(() => window.location.reload(), 600);
                } else showToast(data.message || "Giriş başarısız", "error");
            } catch (err) { showToast("Bağlantı hatası", "error"); }
            finally { submitBtn.innerText = originalText; submitBtn.disabled = false; }
        }
        async function logout() {
            try { await fetch('/logout', { method: 'POST' }); showToast("Çıkış", "success"); setTimeout(() => window.location.reload(), 500); } catch (err) {}
        }
        async function saveProfile() {
            const bot_name = document.getElementById('modalBotName').value;
            try {
                const res = await fetch('/update-profile', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ bot_name }) });
                const data = await res.json();
                showToast(data.message, "success");
                document.getElementById('sidebarBotName').innerText = bot_name;
                closeModal('profileModal');
            } catch (err) { showToast("Hata", "error"); }
        }
        function openAdminPanel() {
            if (!isAdmin) { showToast("Bu panel sadece admin için.", "error"); return; }
            openModal('adminModal');
            loadMaintenanceStatus();
        }
        document.getElementById('themeGlassOpacity')?.addEventListener('input', (e) => { document.getElementById('glassOpacityVal').innerText = e.target.value; });
        document.getElementById('themeAuroraOpacity')?.addEventListener('input', (e) => { document.getElementById('auroraOpacityVal').innerText = e.target.value; });
        function handleImageSelect(event) {
            const file = event.target.files[0];
            if (file) {
                const reader = new FileReader();
                reader.onload = function(e) { selectedBase64Image = e.target.result; document.getElementById('imagePreviewContainer').style.display = 'block'; };
                reader.readAsDataURL(file);
            }
        }
        function removeImage() { selectedBase64Image = null; document.getElementById('imagePreviewContainer').style.display = 'none'; document.getElementById('imageInput').value = ''; }
        function startNewChat() {
            chats.push({ title: "Yeni Sohbet " + (chats.length + 1), messages: [] });
            activeChatIndex = chats.length - 1;
            renderChatHistory(); renderActiveChat(); updateStats();
            if (window.innerWidth <= 850) toggleMobileSidebar();
        }
        function switchChat(index) {
            activeChatIndex = index;
            renderChatHistory(); renderActiveChat();
            if (window.innerWidth <= 850) {
                const s = document.getElementById('sidebar'); const o = document.getElementById('sidebarOverlay');
                if (s.classList.contains('mobile-open')) { s.classList.remove('mobile-open'); o.classList.remove('active'); }
            }
        }
        function updateStats() { document.getElementById('totalChats').innerText = chats.length; }
        function renderChatHistory() {
            const list = document.getElementById('chatHistoryList');
            list.innerHTML = '';
            chats.forEach((chat, idx) => {
                list.innerHTML += `<div class="history-item ${idx === activeChatIndex ? 'active' : ''}" onclick="switchChat(${idx})"><i data-lucide="message-square" width="12" height="12"></i> ${chat.title}</div>`;
            });
            lucide.createIcons();
        }
        function escapeHtml(s) { return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;'); }
        function renderActiveChat() {
            const chatBox = document.getElementById('chatBox');
            chatBox.innerHTML = '';
            chats[activeChatIndex].messages.forEach((m, idx) => {
                let imgHtml = m.image ? `<img src="${m.image}" class="msg-img">` : '';
                let actions = `<div class="msg-actions">
                    ${m.sender === 'bot' ? `<button class="msg-action-btn" onclick="speakText(${idx})" title="Sesli Oku">🔊</button>` : ''}
                    <button class="msg-action-btn" onclick="copyMsg(${idx})" title="Kopyala">Kopyala</button>
                    <button class="msg-action-btn" onclick="deleteMsg(${idx})" title="Sil">Sil</button>
                </div>`;
                chatBox.innerHTML += `<div class="msg-bubble ${m.sender}"><b>${escapeHtml(m.name)}</b>${imgHtml}${m.content}${actions}</div>`;
            });
            chatBox.scrollTop = chatBox.scrollHeight;
            lucide.createIcons();
        }
        function copyMsg(idx) {
            const m = chats[activeChatIndex].messages[idx];
            const tmp = document.createElement('div');
            tmp.innerHTML = m.content;
            navigator.clipboard.writeText(tmp.innerText);
            showToast("Kopyalandı", "success");
        }
        function deleteMsg(idx) {
            chats[activeChatIndex].messages.splice(idx, 1);
            renderActiveChat();
        }
        function copyCode(btn) { const pre = btn.parentElement.nextElementSibling; navigator.clipboard.writeText(pre.innerText); btn.innerText = "Kopyalandı!"; setTimeout(() => btn.innerText = "Kopyala", 2000); }
        async function sendMessage() {
            const messageInput = document.getElementById('message');
            const message = messageInput.value.trim();
            if (!message && !selectedBase64Image) return;
            if (chats[activeChatIndex].messages.length === 0 && message) { chats[activeChatIndex].title = message.length > 18 ? message.substring(0, 18) + '...' : message; renderChatHistory(); }
            const currentImg = selectedBase64Image;
            chats[activeChatIndex].messages.push({ sender: 'user', name: currentUser, content: escapeHtml(message), image: currentImg });
            renderActiveChat();
            messageInput.value = ''; removeImage();
            chats[activeChatIndex].messages.push({ sender: 'bot', name: 'Crsz Bot', content: '<span class="typing-dots"><span></span><span></span><span></span></span>' });
            renderActiveChat();
            try {
                const res = await fetch('/chat', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ username: currentUser, message, image: currentImg }) });
                if (!res.ok) throw new Error('Sunucu ' + res.status);
                const data = await res.json();
                chats[activeChatIndex].messages.pop();
                let formattedReply = safeMarkdownParse(data.reply || 'Boş cevap geldi.');
                chats[activeChatIndex].messages.push({ sender: 'bot', name: 'Crsz Bot', content: formattedReply });
                renderActiveChat();
                saveChatToServer();
            } catch (err) {
                chats[activeChatIndex].messages.pop();
                chats[activeChatIndex].messages.push({ sender: 'bot', name: 'Crsz Bot', content: `Bağlantı hatası: ${escapeHtml(err.message)}` });
                renderActiveChat();
            }
        }
        async function saveChatToServer() {
            if (!loggedIn) return;
            try {
                await fetch('/chats/save', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ title: chats[activeChatIndex].title, messages: chats[activeChatIndex].messages }) });
            } catch (e) {}
        }

        loadThemeFromServer();
        loadMusic();

        document.body.addEventListener('click', function initMusic() {
            const audio = document.getElementById('bgMusic');
            if (!musicMuted && audio.src && audio.paused && musicPlaylist.length > 0) audio.play().catch(e => {});
            document.body.removeEventListener('click', initMusic);
        }, { once: true });
    </script>
</body>
</html>
"""

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
