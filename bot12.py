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

# ============ AGNES AI & FISH AUDIO KEYS ============
AGNES_API_KEY = os.getenv("AGNES_API_KEY", "sk-gaIHqUgmoEdIv3rYV5MUgDPRGqQzQ4PKFQMQK38LgS5lXeK1")
FISH_AUDIO_API_KEY = os.getenv("FISH_AUDIO_API_KEY", "795c65f906f043e09893d56f6c91a0fc")

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


def web_search(query, max_results=5):
    if requests is None: return ""
    results = []
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
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
    except Exception: pass

    if not results:
        try:
            ddg_api = f"https://api.duckduckgo.com/?q={requests.utils.quote(query)}&format=json&no_html=1&skip_disambig=1&t=crszbot"
            r = requests.get(ddg_api, headers=headers, timeout=6)
            if r.status_code == 200:
                d = r.json()
                if d.get("AbstractText"):
                    results.append(f"[DuckDuckGo] {d.get('Heading', '')}: {d['AbstractText'][:400]}")
                elif d.get("Answer"):
                    results.append(f"[DuckDuckGo] {d['Answer']}")
        except Exception: pass

    return "\n".join(results[:max_results])


def detect_media_request(text):
    if not text: return None, None
    t = text.strip()
    lower = t.lower()

    image_keywords = ["fotoğraf", "fotograf", "resim", "görsel", "gorsel", "image", "picture", "photo", "çiz", "ciz", "resmet"]
    video_keywords = ["video", "vidyo", "klip", "film", "animasyon"]
    create_verbs = ["oluştur", "olustur", "yap", "yapsana", "üret", "uret", "hazırla", "hazirla", "çiz", "ciz", "çeksene", "ceksene", "istiyorum", "isterim", "göster", "goster"]

    has_image = any(k in lower for k in image_keywords)
    has_video = any(k in lower for k in video_keywords)
    has_verb = any(v in lower for v in create_verbs)

    if has_video and has_verb:
        prompt = t
        for kw in video_keywords + create_verbs + ["bir", "bana", "lütfen", "acaba"]:
            prompt = re.sub(rf'\b{re.escape(kw)}\b', '', prompt, flags=re.IGNORECASE)
        prompt = re.sub(r'\s+', ' ', prompt).strip(" :,-")
        if len(prompt) < 3: prompt = t
        return "video", prompt

    if has_image and has_verb:
        prompt = t
        for kw in image_keywords + create_verbs + ["bir", "bana", "lütfen", "acaba"]:
            prompt = re.sub(rf'\b{re.escape(kw)}\b', '', prompt, flags=re.IGNORECASE)
        prompt = re.sub(r'\s+', ' ', prompt).strip(" :,-")
        if len(prompt) < 3: prompt = t
        return "image", prompt

    if lower.startswith("/foto") or lower.startswith("/resim") or lower.startswith("/img"):
        prompt = re.sub(r'^/\w+\s*', '', t).strip()
        return ("image", prompt) if prompt else (None, None)
    if lower.startswith("/video") or lower.startswith("/vid"):
        prompt = re.sub(r'^/\w+\s*', '', t).strip()
        return ("video", prompt) if prompt else (None, None)

    return None, None


def generate_image(prompt):
    if not AGNES_API_KEY: return None, "Görsel üretimi için AGNES_API_KEY eksik."
    try:
        url = "https://apihub.agnes-ai.com/v1/images/generations"
        headers = {"Authorization": f"Bearer {AGNES_API_KEY}", "Content-Type": "application/json"}
        data = {"model": "agnes-image-2.5-flash", "prompt": prompt, "size": "1K", "ratio": "1:1", "extra_body": {"response_format": "url"}}
        r = requests.post(url, headers=headers, json=data, timeout=120)
        if r.status_code == 200:
            image_url = r.json().get("data", [{}])[0].get("url")
            if not image_url: return None, "Görsel URL alınamadı."
            img_r = requests.get(image_url, timeout=60)
            if img_r.status_code == 200:
                filename = f"img_{uuid.uuid4().hex[:12]}.jpg"
                filepath = os.path.join(AI_IMAGE_DIR, filename)
                with open(filepath, "wb") as f: f.write(img_r.content)
                return filename, None
        return None, f"Hata: HTTP {r.status_code}"
    except Exception as e: return None, str(e)


def generate_video(prompt):
    if not AGNES_API_KEY: return None, "Video üretimi için AGNES_API_KEY eksik."
    try:
        url = "https://apihub.agnes-ai.com/v1/videos"
        headers = {"Authorization": f"Bearer {AGNES_API_KEY}", "Content-Type": "application/json"}
        data = {"model": "agnes-video-2.5-flash", "prompt": prompt, "mode": "text", "seconds": "4", "size": "720P", "aspect_ratio": "16:9"}
        r = requests.post(url, headers=headers, json=data, timeout=30)
        if r.status_code in [200, 201]:
            task_id = r.json().get("video_id") or r.json().get("task_id") or r.json().get("id")
            if not task_id: return None, "Görev ID alınamadı."
            for _ in range(40):
                time.sleep(10)
                status_url = f"https://apihub.agnes-ai.com/agnesapi?video_id={task_id}&model_name=agnes-video-2.5-flash"
                status_r = requests.get(status_url, headers=headers, timeout=30)
                if status_r.status_code == 200:
                    s_data = status_r.json()
                    if s_data.get("status") == "completed" or s_data.get("url"):
                        video_url = s_data.get("url") or s_data.get("video_url")
                        if video_url:
                            vid_r = requests.get(video_url, timeout=120)
                            filename = f"vid_{uuid.uuid4().hex[:12]}.mp4"
                            filepath = os.path.join(AI_VIDEO_DIR, filename)
                            with open(filepath, "wb") as f: f.write(vid_r.content)
                            return filename, None
            return None, "Video zaman aşımına uğradı."
        return None, f"Hata: HTTP {r.status_code}"
    except Exception as e: return None, str(e)


def get_ai_response(username, user_message, image_data=None):
    is_owner = is_admin_user(username)
    if not is_owner and ("samimi" in user_message.lower() and ("konuş" in user_message.lower() or "ol" in user_message.lower())):
        user_samimi_status[username] = True
    samimi_mode = is_owner or user_samimi_status.get(username, False)

    user = get_user_from_db(username)
    user_lang = (user.get("language") if user else "tr") or "tr"

    if not image_data:
        media_type, media_prompt = detect_media_request(user_message)
        if media_type == "image":
            filename, err = generate_image(media_prompt)
            if filename:
                reply_text = f"İşte fotoğrafın hazır! **İstek:** {media_prompt}"
                memory_add(username, "user", user_message, None, user_lang)
                memory_add(username, "assistant", reply_text, None, user_lang)
                return json.dumps({"text": reply_text, "media_type": "image", "media_url": f"/ai-images/{filename}", "prompt": media_prompt})
            else:
                return f"Fotoğraf oluşturulamadı. {err}"
        elif media_type == "video":
            filename, err = generate_video(media_prompt)
            if filename:
                reply_text = f"İşte videon hazır! **İstek:** {media_prompt}"
                memory_add(username, "user", user_message, None, user_lang)
                memory_add(username, "assistant", reply_text, None, user_lang)
                return json.dumps({"text": reply_text, "media_type": "video", "media_url": f"/ai-videos/{filename}", "prompt": media_prompt})
            else:
                return f"Video oluşturulamadı. {err}"

    persona = (
        f"Senin adın {APP_STATE['bot_name']}. Karşındaki kullanıcı ({username}) ile net, anlaşılır ve doğrudan yardımcı olan bir dille konuş. "
        "Kullanıcının sorularını ve isteklerini çok iyi anla, eksiksiz ve tatmin edici yanıtlar ver. "
        "Kod isteklerinde markdown blokları kullan. 'fotograf olustur: ...' veya 'video olustur: ...' denildiğinde medya üretilebileceğini bil."
    )
    
    memory = memory_get(username, limit=20)
    messages = [{"role": "system", "content": persona}]
    for m in memory:
        messages.append({"role": m["role"], "content": m.get("content", "") or "[Boş]"})

    if image_data:
        image_url = image_data if "," in image_data else f"data:image/jpeg;base64,{image_data}"
        messages.append({"role": "user", "content": [{"type": "text", "text": user_message or "Analiz et."}, {"type": "image_url", "image_url": {"url": image_url}}]})
        model_chain = ["qwen/qwen3.8-27b"]
    else:
        search_context = ""
        if "araştır" in user_message.lower() or "güncel" in user_message.lower():
            sr = web_search(user_message)
            if sr: search_context = f"\n\n[Web Arama Sonuçları]:\n{sr}"
        
        messages.append({"role": "user", "content": user_message + search_context})
        model_chain = ["openai/gpt-oss-120b", "openai/gpt-oss-20b"]

    memory_add(username, "user", user_message or "[Foto]", None, user_lang)

    for model_name in model_chain:
        try:
            completion = client.chat.completions.create(model=model_name, messages=messages, temperature=0.7, max_tokens=1500, timeout=30.0)
            reply = completion.choices[0].message.content.strip()
            if reply:
                memory_add(username, "assistant", reply, None, user_lang)
                return reply
        except Exception: continue

    return "Üzgünüm, şu an yanıt üretemiyorum."


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
        supported_languages=SUPPORTED_LANGUAGES,
        user_language=user_language
    )


@app.route("/fish-tts", methods=["POST"])
def fish_tts():
    """ Fish Audio Sarah Ses Modeli API Entegrasyonu """
    if requests is None: return jsonify({"error": "Requests kütüphanesi yok"}), 500
    data = request.get_json(silent=True) or {}
    text = data.get("text", "").strip()
    if not text: return jsonify({"error": "Metin yok"}), 400

    try:
        url = "https://api.fish.audio/v1/tts"
        headers = {
            "Authorization": f"Bearer {FISH_AUDIO_API_KEY}",
            "Content-Type": "application/json"
        }
        payload = {
            "text": text,
            "reference_id": "7f92f8afb8ec43bf8142931f962f6b7f", # Sarah Ses Modeli
            "format": "mp3",
            "normalize": True
        }
        r = requests.post(url, headers=headers, json=payload, timeout=30)
        if r.status_code == 200:
            b64_audio = base64.b64encode(r.content).decode('utf-8')
            return jsonify({"status": "success", "audio": b64_audio})
        else:
            return jsonify({"status": "error", "message": f"Fish Audio HTTP {r.status_code}"}), 400
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/uploads/music/<path:filename>")
def serve_music(filename): return send_from_directory(MUSIC_DIR, filename)

@app.route("/admin/bg/<path:filename>")
def serve_bg(filename): return send_from_directory(BG_DIR, filename)

@app.route("/uploads/avatars/<path:filename>")
def serve_avatar(filename): return send_from_directory(AVATAR_DIR, filename)

@app.route("/static/<path:filename>")
def serve_static(filename): return send_from_directory(STATIC_DIR, filename)

@app.route("/ai-images/<path:filename>")
def serve_ai_image(filename): return send_from_directory(AI_IMAGE_DIR, filename)

@app.route("/ai-videos/<path:filename>")
def serve_ai_video(filename): return send_from_directory(AI_VIDEO_DIR, filename)

@app.route("/manifest.json")
def manifest():
    return jsonify({
        "name": APP_STATE["bot_name"], "short_name": "CrszBot", "start_url": "/", "display": "standalone",
        "background_color": APP_STATE["theme"]["bg_deep"], "theme_color": APP_STATE["theme"]["accent1"],
        "icons": [{"src": "/static/icon-192.png", "sizes": "192x192", "type": "image/png"}]
    })

@app.route("/service-worker.js")
def service_worker():
    return app.response_class("self.addEventListener('fetch', e => {});", mimetype="application/javascript")

@app.route("/maintenance/check", methods=["GET"])
def maintenance_check(): return jsonify({"status": "success", "enabled": bool(db_get("maintenance_mode", False))})

@app.route("/maintenance/toggle", methods=["POST"])
def maintenance_toggle():
    if 'username' not in session or not is_admin_user(session['username']): return jsonify({"status": "error"}), 403
    enabled = bool((request.get_json(silent=True) or {}).get("enabled", False))
    db_set("maintenance_mode", enabled)
    return jsonify({"status": "success", "enabled": enabled})

@app.route("/memory/clear", methods=["POST"])
def clear_memory():
    if 'username' not in session: return jsonify({"status": "error"}), 403
    memory_clear(session['username'])
    return jsonify({"status": "success", "message": "Hafıza temizlendi."})

@app.route("/chat", methods=["POST"])
@rate_limit(max_calls=30, window_seconds=60)
def chat():
    try:
        data = request.get_json(silent=True) or {}
        username = data.get("username", "Bilinmeyen")
        user_message = data.get("message", "") or ""
        image_data = data.get("image", None)
        reply = get_ai_response(username, user_message, image_data)

        try:
            parsed = json.loads(reply)
            if isinstance(parsed, dict) and parsed.get("media_type"):
                return jsonify({
                    "reply": parsed.get("text", ""),
                    "media_type": parsed.get("media_type"),
                    "media_url": parsed.get("media_url"),
                    "prompt": parsed.get("prompt", ""),
                    "status": "success"
                })
        except (json.JSONDecodeError, TypeError): pass

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

    if not username or not password: return jsonify({"status": "error", "message": "Kullanıcı adı ve şifre zorunlu."})
    existing = get_user_from_db(username)

    if action == "register":
        if existing: return jsonify({"status": "error", "message": "Kullanıcı adı alınmış."})
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

@app.route("/update-profile", methods=["POST"])
def update_profile():
    if 'username' not in session: return jsonify({"status": "error"}), 403
    data = request.get_json(silent=True) or {}
    APP_STATE["bot_name"] = data.get("bot_name", APP_STATE["bot_name"])
    save_bot_name_to_db(APP_STATE["bot_name"])
    if "language" in data: update_user_language(session['username'], data["language"])
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

@app.route("/upload-avatar", methods=["POST"])
def upload_avatar():
    if 'username' not in session: return jsonify({"status": "error"}), 403
    file = request.files.get('file')
    if not file: return jsonify({"status": "error"}), 400
    ext = os.path.splitext(file.filename)[1].lower()
    unique_name = f"av_{uuid.uuid4().hex[:12]}{ext}"
    file.save(os.path.join(AVATAR_DIR, unique_name))
    save_user_avatar(session['username'], unique_name)
    return jsonify({"status": "success", "avatar": unique_name})

@app.route("/admin/users", methods=["GET"])
def admin_users_list():
    if 'username' not in session or not is_admin_user(session['username']): return jsonify({"status": "error"}), 403
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT id, username, email, is_admin, language, created_at FROM users ORDER BY id ASC")
    rows = c.fetchall()
    conn.close()
    return jsonify({"status": "success", "users": [{"id": r[0], "username": r[1], "email": r[2], "is_admin": bool(r[3]), "language": r[4]} for r in rows]})

@app.route("/admin/users/toggle-admin/<int:user_id>", methods=["POST"])
def admin_toggle_admin(user_id):
    if 'username' not in session or not is_admin_user(session['username']): return jsonify({"status": "error"}), 403
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT is_admin FROM users WHERE id = ?", (user_id,))
    row = c.fetchone()
    new_val = 0 if row[0] else 1
    c.execute("UPDATE users SET is_admin = ? WHERE id = ?", (new_val, user_id))
    conn.commit()
    conn.close()
    return jsonify({"status": "success"})

@app.route("/admin/users/delete/<int:user_id>", methods=["POST"])
def admin_delete_user(user_id):
    if 'username' not in session or not is_admin_user(session['username']): return jsonify({"status": "error"}), 403
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("DELETE FROM users WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()
    return jsonify({"status": "success"})

@app.route("/admin/update-theme", methods=["POST"])
def admin_update_theme():
    if 'username' not in session or not is_admin_user(session['username']): return jsonify({"status": "error"}), 403
    data = request.get_json(silent=True) or {}
    theme = APP_STATE.get("theme", {})
    for k in ["bg_deep", "accent1", "accent2", "accent3", "glass_opacity", "aurora_opacity"]:
        if k in data: theme[k] = data[k]
    APP_STATE["theme"] = theme
    save_theme_to_db(theme)
    if "logo_icon" in data:
        APP_STATE["logo_icon"] = data["logo_icon"]
        save_logo_to_db(data["logo_icon"])
    return jsonify({"status": "success", "theme": theme})

@app.route("/admin/get-theme", methods=["GET"])
def admin_get_theme():
    return jsonify({"status": "success", "theme": db_get("theme", APP_STATE.get("theme", {})), "logo_icon": db_get("logo_icon", "zap")})

@app.route("/admin/upload-background", methods=["POST"])
def admin_upload_background():
    if 'username' not in session or not is_admin_user(session['username']): return jsonify({"status": "error"}), 403
    file = request.files.get('file')
    if not file: return jsonify({"status": "error"}), 400
    ext = os.path.splitext(file.filename)[1].lower()
    unique_name = f"bg_{uuid.uuid4().hex[:12]}{ext}"
    file.save(os.path.join(BG_DIR, unique_name))
    APP_STATE["theme"]["bg_media"] = unique_name
    APP_STATE["theme"]["bg_media_type"] = "video" if ext in [".mp4", ".webm"] else "image"
    save_theme_to_db(APP_STATE["theme"])
    return jsonify({"status": "success", "bg_media": unique_name})

@app.route("/admin/clear-background", methods=["POST"])
def admin_clear_background():
    if 'username' not in session or not is_admin_user(session['username']): return jsonify({"status": "error"}), 403
    APP_STATE["theme"]["bg_media"] = ""
    APP_STATE["theme"]["bg_media_type"] = ""
    save_theme_to_db(APP_STATE["theme"])
    return jsonify({"status": "success"})

@app.route("/admin/upload-music", methods=["POST"])
def admin_upload_music():
    if 'username' not in session or not is_admin_user(session['username']): return jsonify({"status": "error"}), 403
    file = request.files.get('file')
    if not file: return jsonify({"status": "error"}), 400
    unique_name = f"music_{uuid.uuid4().hex[:12]}{os.path.splitext(file.filename)[1].lower()}"
    file.save(os.path.join(MUSIC_DIR, unique_name))
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT INTO music (filename, original_name) VALUES (?, ?)", (unique_name, file.filename))
    conn.commit()
    conn.close()
    return jsonify({"status": "success", "music": db_get_music_list()})

@app.route("/admin/delete-music/<int:music_id>", methods=["POST"])
def admin_delete_music(music_id):
    if 'username' not in session or not is_admin_user(session['username']): return jsonify({"status": "error"}), 403
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("DELETE FROM music WHERE id = ?", (music_id,))
    conn.commit()
    conn.close()
    return jsonify({"status": "success", "music": db_get_music_list()})

@app.route("/music-list", methods=["GET"])
def music_list_api(): return jsonify({"status": "success", "music": db_get_music_list()})


# ============ HTML / FRONTEND ============
HTML_TEMPLATE = r"""
<!DOCTYPE html>
<html lang="tr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no, viewport-fit=cover">
    <title>Crsz Bot | Liquid Glass AI Studio</title>
    <link rel="manifest" href="/manifest.json">
    <meta name="theme-color" content="{{ app_state.theme.accent1 }}">
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
            --lg-shadow: 0 8px 32px rgba(0,0,0,0.4);
        }
        * { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Inter', sans-serif; -webkit-tap-highlight-color: transparent; }
        html, body { background-color: var(--bg-deep); color: var(--text-main); height: 100%; width: 100%; overflow: hidden; position: fixed; }
        .lg {
            background: var(--lg-tint);
            backdrop-filter: blur(var(--lg-blur)) saturate(var(--lg-saturate)) brightness(var(--lg-brightness));
            -webkit-backdrop-filter: blur(var(--lg-blur)) saturate(var(--lg-saturate)) brightness(var(--lg-brightness));
            border: 1px solid var(--lg-border-soft); border-radius: 20px; box-shadow: var(--lg-shadow); position: relative; overflow: hidden;
        }
        .sidebar, .main-workspace, header, .control-panel, .modal-card, .auth-card { background: var(--lg-tint); backdrop-filter: blur(var(--lg-blur)); border: 1px solid var(--lg-border-soft); position: relative; }
        #bgMedia, #bgVideo { position: fixed; inset: 0; z-index: -3; width: 100%; height: 100%; object-fit: cover; display: none; }
        #bgMedia.active, #bgVideo.active { display: block; }
        #bgOverlay { position: fixed; inset: 0; z-index: -2; background: rgba(0,0,0,0.65); display: none; }
        #bgOverlay.active { display: block; }
        #authOverlay { position: fixed; inset: 0; background: rgba(7, 7, 10, 0.9); backdrop-filter: blur(40px); z-index: 2000; display: flex; align-items: center; justify-content: center; padding: 20px; }
        #authOverlay.hidden { display: none; }
        .auth-card { width: 100%; max-width: 420px; padding: 30px; border-radius: 24px; }
        .auth-tabs { display: flex; gap: 10px; margin-bottom: 20px; background: rgba(0,0,0,0.25); padding: 4px; border-radius: 12px; }
        .auth-tab { flex: 1; padding: 10px; text-align: center; font-size: 13px; font-weight: 600; color: var(--text-muted); cursor: pointer; border-radius: 8px; }
        .auth-tab.active { background: rgba(255,255,255,0.1); color: #fff; }
        .auth-input, .lang-select { width: 100%; background: rgba(255,255,255,0.05); border: 1px solid var(--lg-border-soft); border-radius: 12px; padding: 12px 16px; color: white; font-size: 14px; margin-bottom: 14px; outline: none; }
        .auth-btn { width: 100%; background: var(--primary-gradient); color: white; border: none; padding: 12px; border-radius: 12px; font-weight: 600; cursor: pointer; font-size: 14px; }
        .modal-overlay { display: none; position: fixed; inset: 0; background: rgba(0,0,0,0.65); backdrop-filter: blur(10px); z-index: 1500; align-items: center; justify-content: center; padding: 20px; }
        .modal-overlay.active { display: flex; }
        .modal-card { width: 100%; max-width: 560px; max-height: 90vh; overflow-y: auto; border-radius: 22px; padding: 25px; }
        .aurora-bg { position: fixed; inset: 0; pointer-events: none; z-index: -1; filter: blur(140px); opacity: {{ app_state.theme.aurora_opacity }}; }
        .aurora-blob { position: absolute; border-radius: 50%; }
        .blob-1 { width: 350px; height: 350px; background: var(--accent1); top: -50px; left: -50px; }
        .blob-2 { width: 450px; height: 450px; background: var(--accent2); bottom: -50px; right: -50px; }
        .app-layout { display: flex; height: 100dvh; width: 100vw; padding: 12px; gap: 12px; overflow: hidden; }
        .sidebar { width: 260px; min-width: 260px; display: flex; flex-direction: column; padding: 14px; gap: 10px; height: calc(100dvh - 24px); border-radius: 22px; }
        .logo-area { display: flex; align-items: center; gap: 10px; padding-bottom: 10px; border-bottom: 1px solid var(--lg-border-soft); }
        .logo-icon { width: 34px; height: 34px; background: var(--primary-gradient); border-radius: 10px; display: flex; align-items: center; justify-content: center; color: white; }
        .logo-text h1 { font-size: 13px; font-weight: 700; color: #fff; }
        .logo-text p { font-size: 10px; color: var(--text-muted); }
        .new-chat-btn { padding: 9px; border-radius: 12px; font-size: 12px; font-weight: 500; cursor: pointer; display: flex; align-items: center; justify-content: center; gap: 6px; color: #fff; background: rgba(255,255,255,0.05); border: 1px solid var(--lg-border-soft); }
        .quick-stats { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; margin-top: 4px; }
        .stat-card { border-radius: 12px; padding: 8px; text-align: center; background: rgba(255,255,255,0.03); }
        .stat-card .stat-value { font-size: 15px; font-weight: 700; color: #fff; }
        .stat-card .stat-label { font-size: 9px; color: var(--text-muted); text-transform: uppercase; }
        .chat-history-list { flex: 1; overflow-y: auto; display: flex; flex-direction: column; gap: 4px; }
        .history-item { padding: 9px 10px; border-radius: 10px; font-size: 12px; color: var(--text-muted); cursor: pointer; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; display: flex; align-items: center; gap: 8px; }
        .history-item.active { background: rgba(59, 130, 246, 0.18) !important; color: #fff !important; }
        .sidebar-footer { border-top: 1px solid var(--lg-border-soft); padding-top: 8px; display: flex; flex-direction: column; gap: 6px; }
        .footer-btn { border-radius: 10px; color: #fff; padding: 8px; font-size: 12px; cursor: pointer; display: flex; align-items: center; gap: 8px; background: rgba(255,255,255,0.05); border: 1px solid var(--lg-border-soft); }
        .main-workspace { flex: 1; display: flex; flex-direction: column; height: calc(100dvh - 24px); border-radius: 22px; }
        header { padding: 12px 18px; border-bottom: 1px solid var(--lg-border-soft); display: flex; justify-content: space-between; align-items: center; }
        header h2 { font-size: 13px; font-weight: 600; color: #E2E8F0; display: flex; align-items: center; gap: 6px; }
        .status-badge { font-size: 10px; color: #38BDF8; background: rgba(56, 189, 248, 0.1); border: 1px solid rgba(56, 189, 248, 0.2); padding: 3px 8px; border-radius: 20px; display: flex; align-items: center; gap: 5px; }
        .status-dot { width: 5px; height: 5px; background: #38BDF8; border-radius: 50%; box-shadow: 0 0 6px #38BDF8; }
        .icon-action-btn { color: #38BDF8; padding: 6px; border-radius: 10px; cursor: pointer; background: rgba(255,255,255,0.05); border: 1px solid rgba(56,189,248,0.2); display: flex; align-items: center; justify-content: center; }
        .chat-container { flex: 1; padding: 16px; overflow-y: auto; display: flex; flex-direction: column; gap: 14px; }
        .msg-bubble { max-width: 85%; padding: 12px 16px; border-radius: 16px; font-size: 13px; line-height: 1.55; word-break: break-word; }
        .msg-bubble.user { background: rgba(255,255,255,0.06); border: 1px solid var(--lg-border-soft); align-self: flex-start; color: #CBD5E1; }
        .msg-bubble.bot { background: rgba(20, 25, 40, 0.55); border: 1px solid rgba(59, 130, 246, 0.3); color: white; align-self: flex-end; width: 100%; max-width: 90%; }
        .msg-bubble b { display: block; font-size: 10px; margin-bottom: 4px; opacity: 0.7; text-transform: uppercase; }
        .msg-img { max-width: 100%; border-radius: 10px; margin-top: 6px; display: block; }
        pre { background: rgba(4,4,6,0.6) !important; border: 1px solid var(--lg-border-soft); border-radius: 10px; padding: 10px; margin: 8px 0; overflow-x: auto; }
        code { font-family: monospace; font-size: 12px; color: #38BDF8; }
        .control-panel { padding: 12px 16px; border-top: 1px solid var(--lg-border-soft); display: flex; gap: 10px; align-items: center; }
        .input-wrapper { border-radius: 14px; display: flex; align-items: center; padding: 0 10px; flex: 1; background: rgba(255,255,255,0.05); border: 1px solid var(--lg-border-soft); }
        .input-wrapper input { background: transparent; border: none; outline: none; color: white; padding: 10px 6px; font-size: 13px; width: 100%; }
        .upload-icon-btn { background: transparent; border: none; color: var(--text-muted); cursor: pointer; padding: 4px; display: flex; }
        .send-btn { background: var(--primary-gradient); color: white; border: none; padding: 10px 18px; border-radius: 14px; font-weight: 600; font-size: 13px; cursor: pointer; display: flex; align-items: center; gap: 6px; }
        
        /* FISH AUDIO SARAH SESLİ ARAMA ARAYÜZÜ */
        #voiceCallModal {
            position: fixed; inset: 0; background: rgba(7, 7, 12, 0.92);
            backdrop-filter: blur(50px); z-index: 9999; display: none; flex-direction: column; align-items: center; justify-content: space-between; padding: 40px 20px;
        }
        #voiceCallModal.active { display: flex; }
        .call-avatar { width: 120px; height: 120px; border-radius: 50%; background: var(--primary-gradient); display: flex; align-items: center; justify-content: center; font-size: 40px; font-weight: 700; color: #fff; box-shadow: 0 0 50px rgba(59,130,246,0.7); }
        .call-status-text { font-size: 14px; color: #38BDF8; text-align: center; }
        .call-btn { width: 60px; height: 60px; border-radius: 50%; border: none; display: flex; align-items: center; justify-content: center; cursor: pointer; box-shadow: 0 6px 20px rgba(0,0,0,0.5); }
        .call-btn.mic { background: rgba(255,255,255,0.1); color: #fff; border: 1px solid var(--lg-border-soft); }
        .call-btn.mic.muted { background: rgba(248,113,113,0.2); color: #F87171; }
        .call-btn.end { background: #EF4444; color: #fff; width: 70px; height: 70px; font-size: 20px; }
        .voice-call-start-btn { background: linear-gradient(135deg, #10B981, #059669); color: white; border: none; padding: 10px; border-radius: 12px; font-weight: 600; font-size: 12px; cursor: pointer; display: flex; align-items: center; justify-content: center; gap: 8px; width: 100%; margin-top: 6px; }

        .toast { position: fixed; top: 20px; left: 50%; transform: translateX(-50%) translateY(-100px); color: #fff; padding: 12px 20px; border-radius: 14px; font-size: 13px; z-index: 9999; background: rgba(15,23,42,0.9); border: 1px solid var(--lg-border-soft); transition: 0.3s; }
        .toast.show { transform: translateX(-50%) translateY(0); }
        @media(max-width: 850px) {
            .sidebar { position: fixed; top: 8px; left: 8px; height: calc(100dvh - 16px); z-index: 1000; transform: translateX(-110%); transition: transform 0.3s; }
            .sidebar.mobile-open { transform: translateX(0); }
        }
    </style>
</head>
<body>

    <img id="bgMedia" alt="">
    <video id="bgVideo" autoplay muted loop playsinline></video>
    <div id="bgOverlay"></div>
    <audio id="bgMusic" loop></audio>

    <!-- FISH AUDIO SARAH SESLİ ARAMA MODALI -->
    <div id="voiceCallModal">
        <div style="text-align: center;">
            <h2 style="font-size: 22px; color: #fff; margin-bottom: 6px;">Sarah ile Sesli Görüşme</h2>
            <p style="font-size: 12px; color: #38BDF8;">Fish Audio Sarah (Ultra Gerçekçi Ses Model)</p>
        </div>
        <div class="call-avatar">S</div>
        <div class="call-status-text" id="callStatusText">Dinliyor... Konuşmaya başlayabilirsin.</div>
        <div style="display: flex; gap: 20px; align-items: center;">
            <button class="call-btn mic" id="callMicBtn" onclick="toggleCallMic()"><i data-lucide="mic" width="24" height="24"></i></button>
            <button class="call-btn end" onclick="endVoiceCall()"><i data-lucide="phone-off" width="26" height="26"></i></button>
        </div>
    </div>

    <div id="authOverlay" class="{% if logged_in %}hidden{% endif %}">
        <div class="auth-card lg">
            <h2 style="font-size: 18px; font-weight: 700; color: #fff; text-align: center; margin-bottom: 6px;">Crsz Bot Studio</h2>
            <p style="font-size: 12px; color: var(--text-muted); text-align: center; margin-bottom: 20px;">Giriş Yap veya Kayıt Ol</p>
            <div class="auth-tabs">
                <div class="auth-tab active" id="tabLoginBtn" onclick="switchAuthTab('login')">Giriş Yap</div>
                <div class="auth-tab" id="tabRegisterBtn" onclick="switchAuthTab('register')">Kayıt Ol</div>
            </div>
            <input type="text" id="authUsername" class="auth-input" placeholder="Kullanıcı Adı">
            <input type="password" id="authPassword" class="auth-input" placeholder="Şifre">
            <button class="auth-btn" id="authSubmitBtn" onclick="handleAuth()">Giriş Yap</button>
        </div>
    </div>

    <div class="app-layout">
        <div class="sidebar lg" id="sidebar">
            <div class="logo-area">
                <div class="logo-icon"><i data-lucide="{{ app_state.logo_icon }}" width="16" height="16"></i></div>
                <div class="logo-text">
                    <h1>{{ app_state.bot_name }}</h1>
                    <p>AI Studio</p>
                </div>
            </div>
            <button class="new-chat-btn" onclick="startNewChat()"><i data-lucide="plus" width="13" height="13"></i> Yeni Sohbet</button>
            <button class="voice-call-start-btn" onclick="startVoiceCall()"><i data-lucide="phone-call" width="14" height="14"></i> Sesli Arama (Sarah)</button>
            <div class="quick-stats">
                <div class="stat-card"><div class="stat-value" id="totalChats">1</div><div class="stat-label">Sohbet</div></div>
            </div>
            <div class="chat-history-list" id="chatHistoryList"></div>
            <div class="sidebar-footer">
                <button class="footer-btn" onclick="logout()"><i data-lucide="log-out" width="13" height="13"></i> Çıkış Yap</button>
            </div>
        </div>

        <div class="main-workspace lg">
            <header>
                <h2><i data-lucide="terminal" width="14" height="14" style="color: var(--accent1);"></i> Otomasyon &amp; AI</h2>
                <div class="status-badge"><div class="status-dot"></div> Aktif</div>
            </header>
            <div class="chat-container" id="chatBox">
                <div class="msg-bubble user">
                    <b>Sistem</b>
                    <div>Sistem hazır! Sesli arama için **Sarah** ses modeli aktif edildi. Otomatik konuşma kaldırıldı, sadece sen çağırdığında konuşur.</div>
                </div>
            </div>
            <div class="control-panel">
                <div class="input-wrapper">
                    <input type="text" id="message" placeholder="Mesaj yaz..." onkeydown="if(event.key==='Enter') sendMessage()">
                </div>
                <button class="send-btn" onclick="sendMessage()"><span>Gönder</span> <i data-lucide="send" width="13" height="13"></i></button>
            </div>
        </div>
    </div>

    <script>
        lucide.createIcons();
        let chats = [{ title: "Varsayılan Sohbet", messages: [] }];
        let activeChatIndex = 0;
        let loggedIn = {% if logged_in %}true{% else %}false{% endif %};
        let currentUser = "{{ current_user }}";
        
        let isCallActive = false;
        let isMicMuted = false;
        let callRecognition = null;

        function showToast(msg) {
            const t = document.createElement('div');
            t.className = 'toast'; t.innerText = msg;
            document.body.appendChild(t);
            setTimeout(() => t.classList.add('show'), 100);
            setTimeout(() => { t.classList.remove('show'); setTimeout(() => t.remove(), 300); }, 3000);
        }

        // ============ FISH AUDIO SARAH SESLİ ARAMA ============
        function startVoiceCall() {
            isCallActive = true;
            isMicMuted = false;
            document.getElementById('voiceCallModal').classList.add('active');
            playSarahVoice("Selam! Ben Sarah. Seni dinliyorum.");
            startCallListening();
        }

        function endVoiceCall() {
            isCallActive = false;
            document.getElementById('voiceCallModal').classList.remove('active');
            if (callRecognition) { try { callRecognition.stop(); } catch(e){} }
            showToast("Görüşme sonlandırıldı.");
        }

        function toggleCallMic() {
            isMicMuted = !isMicMuted;
            const btn = document.getElementById('callMicBtn');
            if (isMicMuted) {
                btn.classList.add('muted');
                btn.innerHTML = '<i data-lucide="mic-off" width="24" height="24"></i>';
                if (callRecognition) try { callRecognition.stop(); } catch(e){}
            } else {
                btn.classList.remove('muted');
                btn.innerHTML = '<i data-lucide="mic" width="24" height="24"></i>';
                startCallListening();
            }
            lucide.createIcons();
        }

        async function playSarahVoice(text) {
            const statusTxt = document.getElementById('callStatusText');
            if (statusTxt) statusTxt.innerText = "Sarah: \"" + text + "\"";

            try {
                const res = await fetch('/fish-tts', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ text: text })
                });
                const data = await res.json();
                if (data.status === 'success' && data.audio) {
                    const audio = new Audio("data:audio/mp3;base64," + data.audio);
                    audio.onended = () => {
                        if (isCallActive && !isMicMuted) {
                            if (statusTxt) statusTxt.innerText = "Dinliyor...";
                            startCallListening();
                        }
                    };
                    audio.play().catch(e => console.log(e));
                }
            } catch (e) {
                console.log("TTS Hata:", e);
            }
        }

        function startCallListening() {
            const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
            if (!SR) return;
            if (!isCallActive || isMicMuted) return;

            callRecognition = new SR();
            callRecognition.lang = 'tr-TR';
            callRecognition.continuous = false;
            callRecognition.interimResults = false;

            callRecognition.onresult = async (event) => {
                const spokenText = event.results[0][0].transcript;
                const statusTxt = document.getElementById('callStatusText');
                if (statusTxt) statusTxt.innerText = "Algılandı: \"" + spokenText + "\"";

                try {
                    const res = await fetch('/chat', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({ username: currentUser || 'crew', message: spokenText })
                    });
                    const data = await res.json();
                    let replyText = data.reply || "Anlayamadım.";
                    const tmp = document.createElement('div');
                    tmp.innerHTML = replyText;
                    playSarahVoice(tmp.innerText || replyText);
                } catch (e) {
                    playSarahVoice("Bağlantı hatası.");
                }
            };

            callRecognition.onend = () => {
                if (isCallActive && !isMicMuted) {
                    try { callRecognition.start(); } catch(e){}
                }
            };

            try { callRecognition.start(); } catch(e){}
        }

        async function handleAuth() {
            const username = document.getElementById('authUsername').value.trim();
            const password = document.getElementById('authPassword').value.trim();
            if (!username || !password) return;
            const res = await fetch('/auth', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ action: 'login', username, password })
            });
            const data = await res.json();
            if (data.status === 'success') window.location.reload();
            else showToast(data.message || "Giriş başarısız");
        }

        async function logout() {
            await fetch('/logout', { method: 'POST' });
            window.location.reload();
        }

        function startNewChat() {
            chats.push({ title: "Yeni Sohbet", messages: [] });
            activeChatIndex = chats.length - 1;
            renderActiveChat();
        }

        function renderActiveChat() {
            const box = document.getElementById('chatBox');
            box.innerHTML = '';
            chats[activeChatIndex].messages.forEach(m => {
                box.innerHTML += `<div class="msg-bubble ${m.sender}"><b>${m.name}</b>${m.content}</div>`;
            });
            box.scrollTop = box.scrollHeight;
        }

        async function sendMessage() {
            const inp = document.getElementById('message');
            const msg = inp.value.trim();
            if (!msg) return;
            
            chats[activeChatIndex].messages.push({ sender: 'user', name: currentUser || 'Sen', content: msg });
            renderActiveChat();
            inp.value = '';

            try {
                const res = await fetch('/chat', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ username: currentUser || 'crew', message: msg })
                });
                const data = await res.json();
                chats[activeChatIndex].messages.push({ sender: 'bot', name: 'Crsz Bot', content: marked.parse(data.reply || '') });
                renderActiveChat();
            } catch (e) {
                chats[activeChatIndex].messages.push({ sender: 'bot', name: 'Crsz Bot', content: 'Hata oluştu.' });
                renderActiveChat();
            }
        }
    </script>
</body>
</html>
"""

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)

