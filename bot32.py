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
    from ddgs import DDGS
except ImportError:
    DDGS = None
    print("[UYARI] ddgs yüklü değil. pip install ddgs")

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

# ============ AGNES AI KEY ============
AGNES_API_KEY = os.getenv("AGNES_API_KEY", "sk-gaIHqUgmoEdIv3rYV5MUgDPRGqQzQ4PKFQMQK38LgS5lXeK1")
if not AGNES_API_KEY:
    print("[UYARI] AGNES_API_KEY bulunamadı! Görsel/video üretimi çalışmaz.")


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
            print("[DB MIGRATION] users tablosuna 'language' kolonu eklendi.")
        except Exception as e:
            print(f"[DB MIGRATION HATA] language: {e}")

    if not column_exists("users", "is_admin"):
        try:
            c.execute("ALTER TABLE users ADD COLUMN is_admin INTEGER DEFAULT 0")
            conn.commit()
            print("[DB MIGRATION] users tablosuna 'is_admin' kolonu eklendi.")
        except Exception as e:
            print(f"[DB MIGRATION HATA] is_admin: {e}")

    if not column_exists("users", "avatar"):
        try:
            c.execute("ALTER TABLE users ADD COLUMN avatar TEXT")
            conn.commit()
            print("[DB MIGRATION] users tablosuna 'avatar' kolonu eklendi.")
        except Exception as e:
            print(f"[DB MIGRATION HATA] avatar: {e}")

    if not column_exists("users", "email"):
        try:
            c.execute("ALTER TABLE users ADD COLUMN email TEXT")
            conn.commit()
            print("[DB MIGRATION] users tablosuna 'email' kolonu eklendi.")
        except Exception as e:
            print(f"[DB MIGRATION HATA] email: {e}")

    try:
        c.execute("DELETE FROM bot_memory WHERE image_data IS NOT NULL AND image_data != ''")
        conn.commit()
        deleted = c.rowcount
        if deleted > 0:
            print(f"[DB MIGRATION] {deleted} eski görsel mesaj temizlendi.")
    except Exception as e:
        print(f"[DB MIGRATION HATA] görsel temizleme: {e}")

    try:
        c.execute("UPDATE bot_memory SET image_data = NULL WHERE image_data IS NOT NULL")
        conn.commit()
    except Exception:
        pass

    c.execute("SELECT COUNT(*) FROM users WHERE username = ?", ("crewampfilms",))
    if c.fetchone()[0] == 0:
        hashed = generate_password_hash("123")
        c.execute("INSERT INTO users (username, email, password, is_admin, language) VALUES (?, ?, ?, 1, 'tr')",
                  ("crewampfilms", "crszbot052@gmail.com", hashed))
        conn.commit()
        print("[DB] Admin oluşturuldu: crewampfilms / 123")
    else:
        c.execute("UPDATE users SET is_admin = 1 WHERE username = ?", ("crewampfilms",))
        conn.commit()
        print("[DB] Admin yetkisi garanti edildi: crewampfilms")

    c.execute("SELECT COUNT(*) FROM users WHERE username = ?", ("crew",))
    if c.fetchone()[0] == 0:
        hashed2 = generate_password_hash("123")
        c.execute("INSERT INTO users (username, email, password, is_admin, language) VALUES (?, ?, ?, 1, 'tr')",
                  ("crew", "", hashed2))
        conn.commit()
        print("[DB] Admin oluşturuldu: crew / 123")
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


def update_user_language(username, language):
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("UPDATE users SET language = ? WHERE LOWER(username) = LOWER(?)", (language, username))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"[DB LANG HATA] {e}")
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
        c.execute("""SELECT role, content FROM bot_memory
                     WHERE username = ?
                     ORDER BY id DESC LIMIT ?""", (username, limit))
        rows = c.fetchall()
        conn.close()
        rows.reverse()
        return [{"role": r[0], "content": r[1] or ""} for r in rows]
    except Exception as e:
        print(f"[MEMORY GET HATA] {e}")
        return []


def memory_clear(username):
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("DELETE FROM bot_memory WHERE username = ?", (username,))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"[MEMORY CLEAR HATA] {e}")
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


# ============ GÜNCELLENMİŞ WEB ARAMA (ddgs ile çoklu site sonucu) ============
def web_search(query, max_results=6):
    """
    DuckDuckGo'nun gerçek arama sonuçlarını (ddgs) kullanır - API key gerekmez,
    Google'a yakın kapsamda farklı sitelerden (haber, forum, resmi kaynak vb.) sonuç döner.
    Eskiden sadece DuckDuckGo Instant Answer API kullanılıyordu, o da çoğu sorguda boş
    dönüyordu çünkü sadece ansiklopedik konularda cevap veriyor.
    """
    results = []

    if DDGS is None:
        print("[SEARCH] ddgs kurulu değil, sadece Wikipedia fallback kullanılacak.")
    else:
        try:
            with DDGS() as ddgs:
                search_results = list(ddgs.text(
                    query,
                    region="tr-tr",
                    safesearch="moderate",
                    max_results=max_results
                ))
            for r in search_results:
                title = r.get("title", "")
                body = r.get("body", "")
                href = r.get("href", "")
                if title and body:
                    results.append(f"[{href}] {title}: {body[:300]}")
        except Exception as e:
            print(f"[SEARCH] ddgs hata: {e}")

    # Wikipedia'yı ek bağlam olarak her zaman dene (hızlı/net tanımlar için faydalı)
    if requests is not None:
        try:
            for lang in ["tr", "en"]:
                wiki_api = f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{requests.utils.quote(query)}"
                r = requests.get(wiki_api, timeout=6)
                if r.status_code == 200:
                    d = r.json()
                    extract = d.get("extract", "")
                    title = d.get("title", "")
                    if extract and len(extract) > 50:
                        results.insert(0, f"[Wikipedia-{lang.upper()}] {title}: {extract[:400]}")
                        break
        except Exception as e:
            print(f"[SEARCH] Wikipedia hata: {e}")

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
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
        "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8"
    }
    info = []

    try:
        if platform == "tiktok":
            oembed = f"https://www.tiktok.com/oembed?url={url}"
            r = requests.get(oembed, headers=headers, timeout=8)
            if r.status_code == 200:
                d = r.json()
                info.append(f"[TikTok] Başlık: {d.get('title', 'N/A')}")
                info.append(f"[TikTok] Yazar: {d.get('author_name', 'N/A')} (@{d.get('author_unique_id', '')})")

        elif platform == "instagram":
            oembed = f"https://graph.facebook.com/v18.0/instagram_oembed?url={url}"
            r = requests.get(oembed, headers=headers, timeout=8)
            if r.status_code == 200:
                d = r.json()
                info.append(f"[Instagram] Yazar: {d.get('author_name', 'N/A')}")
                if d.get('title'):
                    info.append(f"[Instagram] Başlık: {d.get('title')}")
            else:
                r2 = requests.get(url, headers=headers, timeout=8)
                if r2.status_code == 200:
                    html = r2.text
                    og_desc = re.search(r'<meta[^>]+property="og:description"[^>]+content="([^"]+)"', html)
                    og_title = re.search(r'<meta[^>]+property="og:title"[^>]+content="([^"]+)"', html)
                    if og_title:
                        info.append(f"[Instagram] Başlık: {og_title.group(1)}")
                    if og_desc:
                        info.append(f"[Instagram] Açıklama: {og_desc.group(1)[:300]}")

        elif platform == "twitter":
            oembed = f"https://publish.twitter.com/oembed?url={url}&omit_script=1"
            r = requests.get(oembed, headers=headers, timeout=8)
            if r.status_code == 200:
                d = r.json()
                info.append(f"[Twitter/X] Yazar: {d.get('author_name', 'N/A')}")
                if d.get('html'):
                    tweet_text = re.sub(r'<[^>]+>', ' ', d['html'])
                    tweet_text = re.sub(r'\s+', ' ', tweet_text).strip()
                    info.append(f"[Twitter/X] İçerik: {tweet_text[:500]}")

        elif platform == "youtube":
            oembed = f"https://www.youtube.com/oembed?url={url}&format=json"
            r = requests.get(oembed, headers=headers, timeout=8)
            if r.status_code == 200:
                d = r.json()
                info.append(f"[YouTube] Başlık: {d.get('title', 'N/A')}")
                info.append(f"[YouTube] Kanal: {d.get('author_name', 'N/A')}")

        elif platform == "reddit":
            json_url = url.rstrip("/") + ".json"
            r = requests.get(json_url, headers=headers, timeout=8)
            if r.status_code == 200:
                data = r.json()
                if isinstance(data, list) and len(data) > 0:
                    post = data[0].get("data", {}).get("children", [{}])[0].get("data", {})
                    info.append(f"[Reddit] Başlık: {post.get('title', 'N/A')}")
                    info.append(f"[Reddit] Subreddit: r/{post.get('subreddit', 'N/A')}")
                    if post.get('selftext'):
                        info.append(f"[Reddit] İçerik: {post['selftext'][:500]}")

        elif platform == "github":
            parts = url.rstrip("/").split("/")
            if len(parts) >= 2:
                api_url = f"https://api.github.com/repos/{parts[-2]}/{parts[-1]}"
                r = requests.get(api_url, headers=headers, timeout=8)
                if r.status_code == 200:
                    d = r.json()
                    info.append(f"[GitHub] Repo: {d.get('full_name', 'N/A')}")
                    info.append(f"[GitHub] Açıklama: {d.get('description', 'N/A')}")
                    info.append(f"[GitHub] Yıldız: {d.get('stargazers_count', 0)}")

        elif platform == "spotify":
            oembed = f"https://open.spotify.com/oembed?url={url}"
            r = requests.get(oembed, headers=headers, timeout=8)
            if r.status_code == 200:
                d = r.json()
                info.append(f"[Spotify] Başlık: {d.get('title', 'N/A')}")
                info.append(f"[Spotify] Sanatçı: {d.get('author_name', 'N/A')}")

    except Exception as e:
        print(f"[SOCIAL] {platform} hata: {e}")

    return "\n".join(info) if info else ""


def should_search(msg):
    triggers = ["araştır", "araştıralım", "güncel", "son dakika", "haber", "bugün", "2025", "2026", "kimdir", "nedir", "nasıl yapılır", "fiyat", "kaç tl", "ne zaman", "nerede", "web'de", "internetten", "search", "google"]
    m = msg.lower()
    return any(t in m for t in triggers)


# ============ GELİŞMİŞ MEDYA ALGILAYICI (TYPO TOLERANSLI) ============
def detect_media_request(text):
    if not text:
        return None, None
    t = text.strip()
    lower = t.lower()

    image_keywords = ["fotoğraf", "fotograf", "resim", "görsel", "gorsel", "image", "picture", "photo", "çiz", "ciz", "resmet"]
    video_keywords = ["video", "vidyo", "klip", "film", "animasyon"]
    create_verbs = ["oluştur", "olustur", "oluşt", "olust", "yap", "yapsana", "üret", "uret", "hazırla", "hazirla", "çiz", "ciz", "çeksene", "ceksene", "istiyorum", "isterim", "göster", "goster"]

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
    if not AGNES_API_KEY:
        return None, "Görsel üretimi için .env dosyasına AGNES_API_KEY ekle."
    
    try:
        print(f"[AI IMAGE] Agnes ile üretiliyor: {prompt[:60]}...")
        url = "https://apihub.agnes-ai.com/v1/images/generations"
        headers = {
            "Authorization": f"Bearer {AGNES_API_KEY}",
            "Content-Type": "application/json"
        }
        data = {
            "model": "agnes-image-2.5-flash",
            "prompt": prompt,
            "size": "1K",
            "ratio": "1:1",
            "extra_body": {"response_format": "url"}
        }
        
        r = requests.post(url, headers=headers, json=data, timeout=120)
        
        if r.status_code == 200:
            res_data = r.json()
            image_url = res_data.get("data", [{}])[0].get("url")
            
            if not image_url:
                return None, "Agnes API görsel URL'si döndürmedi."
            
            img_r = requests.get(image_url, timeout=60)
            if img_r.status_code == 200:
                filename = f"img_{uuid.uuid4().hex[:12]}.jpg"
                filepath = os.path.join(AI_IMAGE_DIR, filename)
                with open(filepath, "wb") as f:
                    f.write(img_r.content)
                print(f"[AI IMAGE] Başarılı: {filename}")
                return filename, None
            else:
                return None, f"Görsel indirilemedi (HTTP {img_r.status_code})"
        elif r.status_code == 401:
            return None, "Agnes API anahtarı geçersiz."
        elif r.status_code == 402:
            return None, "Agnes API kredisi bitmiş. Ücretsiz limitin dolmuş olabilir."
        else:
            return None, f"Agnes API hatası: HTTP {r.status_code} - {r.text[:100]}"
            
    except Exception as e:
        print(f"[AI IMAGE HATA] {e}")
        return None, str(e)


# ============ GÜNCELLENMİŞ VİDEO OLUŞTURMA (AGNES 2.5 FLASH, DAYANIKLI HATA YÖNETİMİ) ============
def generate_video(prompt):
    """
    Agnes AI (agnes-video-2.5-flash) ile video üretir.
    Eski versiyona göre: ham API cevaplarını loglar (debug için), 'status' alanı
    farklı isimde gelirse de yakalar (status/state), görev ID'si bulunamazsa
    sessizce geçmez, timeout ve bağlantı hatalarını ayrı ele alır.
    """
    if not AGNES_API_KEY:
        return None, "Video üretimi için .env dosyasına AGNES_API_KEY ekle."

    try:
        print(f"[AI VIDEO] Agnes ile üretiliyor: {prompt[:60]}...")
        url = "https://apihub.agnes-ai.com/v1/videos"
        headers = {
            "Authorization": f"Bearer {AGNES_API_KEY}",
            "Content-Type": "application/json"
        }
        data = {
            "model": "agnes-video-2.5-flash",
            "prompt": prompt,
            "mode": "text",
            "seconds": "4",
            "size": "720P",
            "aspect_ratio": "16:9"
        }

        max_retries = 3
        for attempt in range(1, max_retries + 1):
            try:
                print(f"[AI VIDEO] Görev oluşturuluyor (deneme {attempt}/{max_retries})...")
                r = requests.post(url, headers=headers, json=data, timeout=30)

                # DEBUG: ham cevabı her zaman logla - gerçek hatayı görmek için
                print(f"[AI VIDEO DEBUG] HTTP {r.status_code} - Body: {r.text[:500]}")

                if r.status_code in (200, 201):
                    try:
                        res_data = r.json()
                    except Exception:
                        return None, f"API geçersiz JSON döndü: {r.text[:200]}"

                    task_id = (res_data.get("video_id") or res_data.get("task_id")
                               or res_data.get("id") or res_data.get("data", {}).get("id"))
                    if not task_id:
                        return None, f"Görev ID'si alınamadı. Ham cevap: {json.dumps(res_data)[:300]}"

                    print(f"[AI VIDEO] Görev oluşturuldu: {task_id}. Bekleniyor...")

                    for poll_count in range(60):
                        time.sleep(5)
                        status_url = f"https://apihub.agnes-ai.com/agnesapi?video_id={task_id}&model_name=agnes-video-2.5-flash"
                        try:
                            status_r = requests.get(status_url, headers=headers, timeout=30)
                        except Exception as e:
                            print(f"[AI VIDEO POLL {poll_count}] Bağlantı hatası: {e}")
                            continue

                        print(f"[AI VIDEO POLL {poll_count}] HTTP {status_r.status_code} - {status_r.text[:300]}")

                        if status_r.status_code != 200:
                            continue

                        try:
                            status_data = status_r.json()
                        except Exception:
                            continue

                        status = (status_data.get("status") or status_data.get("state") or "").lower()
                        video_url = status_data.get("url") or status_data.get("video_url")

                        if video_url or status in ("completed", "success", "succeeded"):
                            if video_url:
                                vid_r = requests.get(video_url, timeout=120)
                                if vid_r.status_code != 200:
                                    return None, f"Video indirilemedi (HTTP {vid_r.status_code})"
                                filename = f"vid_{uuid.uuid4().hex[:12]}.mp4"
                                filepath = os.path.join(AI_VIDEO_DIR, filename)
                                with open(filepath, "wb") as f:
                                    f.write(vid_r.content)
                                print(f"[AI VIDEO] Başarılı: {filename}")
                                return filename, None
                            else:
                                return None, "Durum tamamlandı olarak geldi ama video URL'si yok."

                        if status in ("failed", "error"):
                            err_obj = status_data.get("error", {}) or {}
                            err_msg = err_obj.get("message") if isinstance(err_obj, dict) else str(err_obj)
                            if not err_msg:
                                err_msg = json.dumps(status_data)[:200]
                            return None, f"Video üretimi başarısız: {err_msg}"

                    return None, "Video zaman aşımına uğradı (5 dakika doldu)."

                elif r.status_code == 503:
                    if attempt < max_retries:
                        wait_time = 15
                        print(f"[AI VIDEO] Kuyruk dolu (503). {wait_time} saniye bekleniyor...")
                        time.sleep(wait_time)
                        continue
                    else:
                        return None, "Video kuyruğu şu an dolu. Lütfen birkaç dakika sonra tekrar dene."

                elif r.status_code == 429:
                    return None, "Video isteği limiti aşıldı. Lütfen biraz sonra tekrar dene."

                elif r.status_code == 401:
                    return None, f"Agnes API anahtarı geçersiz. Cevap: {r.text[:200]}"
                elif r.status_code == 402:
                    return None, "Agnes API kredisi bitmiş."
                elif r.status_code == 404:
                    return None, f"Endpoint bulunamadı (404) - API adresi değişmiş olabilir: {url}"
                else:
                    return None, f"Agnes Video API hatası: HTTP {r.status_code} - {r.text[:300]}"

            except requests.exceptions.Timeout:
                print(f"[AI VIDEO HATA] Deneme {attempt} zaman aşımına uğradı.")
                if attempt < max_retries:
                    time.sleep(5)
                    continue
                return None, "İstek zaman aşımına uğradı, sunucu yanıt vermedi."
            except requests.exceptions.ConnectionError as e:
                print(f"[AI VIDEO HATA] Deneme {attempt} bağlantı hatası: {e}")
                if attempt < max_retries:
                    time.sleep(5)
                    continue
                return None, "API sunucusuna bağlanılamadı."
            except Exception as e:
                print(f"[AI VIDEO HATA] Deneme {attempt}: {e}")
                if attempt < max_retries:
                    time.sleep(5)
                    continue
                return None, str(e)

        return None, "Video üretilemedi."

    except Exception as e:
        print(f"[AI VIDEO HATA] {e}")
        return None, str(e)


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
            print(f"[MEDIA] Görsel isteği algılandı: {media_prompt}")
            filename, err = generate_image(media_prompt)
            if filename:
                memory_add(username, "user", user_message, None, user_lang)
                reply_text = f"İşte fotoğrafın hazır! **İstek:** {media_prompt}"
                memory_add(username, "assistant", reply_text, None, user_lang)
                return json.dumps({
                    "text": reply_text,
                    "media_type": "image",
                    "media_url": f"/ai-images/{filename}",
                    "prompt": media_prompt
                })
            else:
                memory_add(username, "user", user_message, None, user_lang)
                reply_text = f"Fotoğraf oluşturamadım. {err}"
                memory_add(username, "assistant", reply_text, None, user_lang)
                return reply_text

        elif media_type == "video":
            print(f"[MEDIA] Video isteği algılandı: {media_prompt}")
            filename, err = generate_video(media_prompt)
            if filename:
                memory_add(username, "user", user_message, None, user_lang)
                reply_text = f"İşte videon hazır! **İstek:** {media_prompt}"
                memory_add(username, "assistant", reply_text, None, user_lang)
                return json.dumps({
                    "text": reply_text,
                    "media_type": "video",
                    "media_url": f"/ai-videos/{filename}",
                    "prompt": media_prompt
                })
            else:
                memory_add(username, "user", user_message, None, user_lang)
                reply_text = f"Video oluşturamadım. {err}"
                memory_add(username, "assistant", reply_text, None, user_lang)
                return reply_text

    detected_lang = None
    lang_commands = {
        "ingilizce": "en", "english": "en", "speak english": "en",
        "almanca": "de", "deutsch": "de", "german": "de",
        "fransızca": "fr", "français": "fr", "french": "fr",
        "ispanyolca": "es", "español": "es", "spanish": "es",
        "arapça": "ar", "arabic": "ar",
        "rusça": "ru", "russian": "ru",
        "italyanca": "it", "italian": "it",
        "portekizce": "pt", "portuguese": "pt",
        "hollandaca": "nl", "dutch": "nl",
        "türkçe": "tr", "turkish": "tr",
    }
    msg_low = user_message.lower()
    for keyword, code in lang_commands.items():
        if keyword in msg_low and any(w in msg_low for w in ["konuş", "yaz", "cevap", "speak", "reply", "answer", "devam", "continue"]):
            detected_lang = code
            break

    active_lang_code = detected_lang or user_lang
    active_lang_name = SUPPORTED_LANGUAGES.get(active_lang_code, "Türkçe")

    if detected_lang and detected_lang != user_lang:
        update_user_language(username, detected_lang)
        user_lang = detected_lang

    if is_owner:
        persona = (
            f"Senin adın {APP_STATE['bot_name']}. Karşındaki kişi senin sahibin crewampfilms. "
            "Onunla konuşurken samimi, rahat ve gerektiğinde hafif arsız bir dille konuş. "
            "ÖNEMLİ: 'kanka', 'kardeşim', 'bro', 'dostum' gibi hitaplar KULLANMA. Doğrudan hitap et veya ismiyle seslen. "
            "Asla resmi olma, uzun yıllardır arkadaşmışsınız gibi davran. "
            "Kodları uygun markdown blokları içinde, adım adım açıklamaları numaralandırılmış listeler halinde sun. "
            "Ayrica sen FOTOGRAF ve VIDEO olusturabilirsin. Kullanici 'fotograf olustur: ...' veya 'video olustur: ...' dediginde sistem otomatik olarak medya uretir. "
            "Sen bu ozelligi biliyorsun, kullaniciya bu konuda yardimci ol."
        )
    elif samimi_mode:
        persona = f"Senin adın {APP_STATE['bot_name']}. Karşındaki kullanıcı ({username}) ile samimi, dostça bir dille konuş. 'kanka' gibi hitaplar kullanma. Ayrica 'fotograf olustur: ...' veya 'video olustur: ...' yazarak medya uretebilecegini bil."
    else:
        persona = f"Senin adın {APP_STATE['bot_name']}. Karşındaki kullanıcı ({username}) ile resmi, kibar ve yardımcı bir dille konuş. Ayrica 'fotograf olustur: ...' veya 'video olustur: ...' yazarak medya uretilebilecegini bil."

    lang_instruction = (
        f"\n\nCok onemli dil kurali: Su andan itibaren SADECE {active_lang_name} ({active_lang_code.upper()}) dilinde yanit ver. "
        f"Onceki mesajlarda farkli dilde konusmus olsan bile, bundan sonraki TUM yanitlarini {active_lang_name} dilinde ver. "
        f"Kullanici 'devam et', 'konus', 'yaz' gibi bir sey derse bile {active_lang_name} dilinde devam et."
    )
    persona += lang_instruction

    memory = memory_get(username, limit=20)
    messages = [{"role": "system", "content": persona}]

    for m in memory:
        content = m.get("content", "") or ""
        if not content:
            content = "[Bos mesaj]"
        messages.append({"role": m["role"], "content": content})

    if image_data:
        if "," in image_data:
            image_url = image_data
        else:
            image_url = f"data:image/jpeg;base64,{image_data}"
        messages.append({
            "role": "user",
            "content": [
                {"type": "text", "text": user_message if user_message else "Bu fotograftaki nedir? Analiz et."},
                {"type": "image_url", "image_url": {"url": image_url}}
            ]
        })
        model_chain = ["qwen/qwen3.8-27b"]
    else:
        social_context = ""
        platform, url = detect_social_url(user_message)
        if platform and url:
            print(f"[SOCIAL] {platform} tespit edildi: {url}")
            social_data = fetch_social_content(platform, url)
            if social_data:
                social_context = (
                    f"\n\n===== DIS KAYNAK ICERIGI ({platform.upper()}) =====\n"
                    f"{social_data}\n"
                    f"================================================\n\n"
                    f"Yukaridaki verilere dayanarak kullanicinin sorusunu yanitla."
                )
            else:
                social_context = f"\n\n[NOT] {platform} linkinden icerik cekilemedi."

        search_context = ""
        if not social_context and should_search(user_message):
            print(f"[WEB SEARCH] '{user_message}'")
            search_result = web_search(user_message)
            if search_result:
                search_context = (
                    f"\n\n===== WEB ARASTIRMASI SONUCLARI =====\n"
                    f"{search_result}\n"
                    f"======================================\n\n"
                    f"Yukaridaki bilgileri kullanarak kullanicinin sorusuna {active_lang_name} dilinde yanit ver."
                )

        url_check = re.search(r"(https?://[^\s]+)", user_message)
        if url_check and not platform:
            social_context = (
                f"\n\n[NOT] Kullanici bir link paylasti ama bu link desteklenen platformlardan degil. "
                f"Desteklenen: TikTok, Instagram, Twitter/X, YouTube, Reddit, GitHub, Spotify."
            )

        full_message = user_message + social_context + search_context
        messages.append({"role": "user", "content": full_message})
        model_chain = ["openai/gpt-oss-120b", "openai/gpt-oss-20b"]

    memory_add(username, "user", user_message if user_message else "[Fotograf]", None, active_lang_code)

    last_error = None
    for model_name in model_chain:
        try:
            print(f"[MODEL] Deneniyor: {model_name} (dil: {active_lang_code})")
            completion = client.chat.completions.create(
                model=model_name, messages=messages, temperature=0.7, max_tokens=1500, timeout=30.0
            )
            reply = completion.choices[0].message.content.strip()
            if reply:
                print(f"[MODEL] Başarılı: {model_name}")
                memory_add(username, "assistant", reply, None, active_lang_code)
                return reply
        except Exception as e:
            last_error = str(e)
            err = last_error.lower()
            print(f"[MODEL HATA] {model_name}: {err[:200]}")
            if "api key" in err or "401" in err or "invalid_api_key" in err:
                return "API anahtari gecersiz. .env dosyasindaki GROQ_API_KEY'i kontrol et."
            if "rate" in err or "429" in err:
                print(f"[MODEL] Rate limit, sonraki model deneniyor...")
                continue
            continue

    if last_error:
        return f"Modeller yanit vermedi. Son hata: {last_error[:300]}"
    return "Bilinmeyen bir hata olustu."


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


@app.route("/ai-images/<path:filename>")
def serve_ai_image(filename):
    if ".." in filename or "/" in filename or "\\" in filename:
        return "Geçersiz", 400
    return send_from_directory(AI_IMAGE_DIR, filename)


@app.route("/ai-videos/<path:filename>")
def serve_ai_video(filename):
    if ".." in filename or "/" in filename or "\\" in filename:
        return "Geçersiz", 400
    return send_from_directory(AI_VIDEO_DIR, filename)


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
    const CACHE_NAME = 'crszbot-v2';
    self.addEventListener('install', e => { self.skipWaiting(); });
    self.addEventListener('activate', e => { e.waitUntil(self.clients.claim()); });
    self.addEventListener('fetch', e => {
        if (e.request.method !== 'GET') return;
        e.respondWith(fetch(e.request).catch(() => caches.match(e.request)));
    });
    """
    return app.response_class(sw, mimetype="application/javascript")


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


@app.route("/memory/clear", methods=["POST"])
def clear_memory():
    if 'username' not in session:
        return jsonify({"status": "error", "message": "Giriş yapmadın."}), 403
    memory_clear(session['username'])
    return jsonify({"status": "success", "message": "Bot hafızası temizlendi."})


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
        except (json.JSONDecodeError, TypeError):
            pass

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
    language = data.get("language", "tr").strip()

    if language not in SUPPORTED_LANGUAGES:
        language = "tr"

    if not username or not password:
        return jsonify({"status": "error", "message": "Kullanıcı adı ve şifre zorunludur."})

    existing = get_user_from_db(username)

    if action == "register":
        if existing: return jsonify({"status": "error", "message": "Bu kullanıcı adı zaten alınmış."})
        if len(password) < 3: return jsonify({"status": "error", "message": "Şifre en az 3 karakter olmalı."})
        ok = create_user(username, email, password, is_admin=False, language=language)
        if not ok: return jsonify({"status": "error", "message": "Kayıt oluşturulamadı."})
        session.permanent = True
        session['username'] = username
        return jsonify({"status": "success", "message": "Kayıt başarılı!", "username": username, "is_admin": False, "language": language})

    elif action == "login":
        if existing and check_password_hash(existing["password"], password):
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
        return jsonify({"status": "error", "message": "Giriş yapmadın."}), 403
    data = request.get_json(silent=True) or {}
    APP_STATE["bot_name"] = data.get("bot_name", APP_STATE["bot_name"])
    save_bot_name_to_db(APP_STATE["bot_name"])
    if "language" in data and data["language"] in SUPPORTED_LANGUAGES:
        update_user_language(session['username'], data["language"])
    return jsonify({"status": "success", "message": "Profil güncellendi."})


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


@app.route("/admin/users", methods=["GET"])
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
        return jsonify({"status": "error", "message": "Kullanıcı yok."}), 404
    new_val = 0 if row[0] else 1
    c.execute("UPDATE users SET is_admin = ? WHERE id = ?", (new_val, user_id))
    conn.commit()
    conn.close()
    return jsonify({"status": "success", "is_admin": bool(new_val)})


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
            --primary-gradient: linear-gradient(135deg, var(--accent1) 0%, var(--accent2) 50%, var(--accent3) 100%);
            --text-main: #F8FAFC;
            --text-muted: #94A3B8;

            --lg-blur: 40px;
            --lg-saturate: 200%;
            --lg-brightness: 1.1;
            --lg-tint: rgba(255,255,255,0.04);
            --lg-tint-2: rgba(255,255,255,0.08);
            --lg-border: rgba(255,255,255,0.18);
            --lg-border-soft: rgba(255,255,255,0.08);
            --lg-highlight: rgba(255,255,255,0.5);
            --lg-shadow: 0 8px 32px rgba(0,0,0,0.4);

            --tx-smooth: cubic-bezier(0.22, 1, 0.36, 1);
            --tx-bounce: cubic-bezier(0.34, 1.56, 0.64, 1);
        }
        * { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Inter', sans-serif; -webkit-tap-highlight-color: transparent; }
        html, body {
            background-color: var(--bg-deep);
            color: var(--text-main);
            height: 100%; width: 100%;
            overflow: hidden; position: fixed;
            top: 0; left: 0; right: 0; bottom: 0;
            transition: background-color 0.5s var(--tx-smooth);
        }

        .lg {
            position: relative;
            isolation: isolate;
            background: var(--lg-tint);
            backdrop-filter: blur(var(--lg-blur)) saturate(var(--lg-saturate)) brightness(var(--lg-brightness));
            -webkit-backdrop-filter: blur(var(--lg-blur)) saturate(var(--lg-saturate)) brightness(var(--lg-brightness));
            border: 1px solid var(--lg-border-soft);
            border-radius: 20px;
            box-shadow:
                var(--lg-shadow),
                inset 0 1px 0 0 var(--lg-highlight),
                inset 0 -1px 0 0 rgba(0,0,0,0.15),
                inset 0 0 30px 0 rgba(255,255,255,0.03);
            overflow: hidden;
        }
        .lg::before {
            content: '';
            position: absolute;
            inset: 0;
            border-radius: inherit;
            background:
                radial-gradient(ellipse 60% 40% at 20% 0%, rgba(255,255,255,0.15), transparent 60%),
                radial-gradient(ellipse 40% 30% at 80% 100%, rgba(255,255,255,0.06), transparent 60%);
            pointer-events: none;
            z-index: 1;
            opacity: 0.9;
        }
        .lg::after {
            content: '';
            position: absolute;
            top: 0; left: 10%; right: 10%;
            height: 1px;
            background: linear-gradient(90deg,
                transparent 0%,
                rgba(255,255,255,0.6) 30%,
                rgba(255,255,255,0.9) 50%,
                rgba(255,255,255,0.6) 70%,
                transparent 100%);
            pointer-events: none;
            z-index: 2;
        }
        .lg > * { position: relative; z-index: 3; }

        .sidebar, .main-workspace, header, .control-panel, .modal-card, .auth-card,
        .stat-card, .new-chat-btn, .footer-btn, .icon-action-btn, .input-wrapper,
        .music-item, .user-item, .toggle-row, .logo-option, .tab-buttons,
        .toast, .slider-row, .range-row, .color-picker-row {
            background: var(--lg-tint);
            backdrop-filter: blur(var(--lg-blur)) saturate(var(--lg-saturate));
            -webkit-backdrop-filter: blur(var(--lg-blur)) saturate(var(--lg-saturate));
            border: 1px solid var(--lg-border-soft);
            position: relative;
            overflow: hidden;
        }
        .sidebar::before, .main-workspace::before, header::before,
        .control-panel::before, .modal-card::before, .auth-card::before {
            content: '';
            position: absolute; top: 0; left: 8%; right: 8%;
            height: 1px;
            background: linear-gradient(90deg, transparent, rgba(255,255,255,0.5), transparent);
            pointer-events: none; z-index: 2;
        }

        button, .footer-btn, .new-chat-btn, .history-item, .icon-action-btn,
        .upload-icon-btn, .send-btn, .tab-btn, .msg-action-btn, .logo-option,
        .user-item .usr-btn, .copy-code-btn {
            transition: transform 0.2s var(--tx-bounce),
                        background 0.3s var(--tx-smooth),
                        box-shadow 0.3s var(--tx-smooth),
                        color 0.25s ease,
                        border-color 0.25s ease !important;
        }
        button:active, .footer-btn:active, .new-chat-btn:active,
        .history-item:active, .icon-action-btn:active, .upload-icon-btn:active,
        .send-btn:active, .tab-btn:active {
            transform: scale(0.95);
        }
        button:hover, .footer-btn:hover, .new-chat-btn:hover,
        .history-item:hover, .icon-action-btn:hover {
            box-shadow: 0 0 24px rgba(59, 130, 246, 0.22),
                        inset 0 1px 0 rgba(255,255,255,0.15);
        }

        @keyframes musicToggle {
            0% { transform: scale(1) rotate(0deg); }
            25% { transform: scale(1.2) rotate(-10deg); }
            50% { transform: scale(0.92) rotate(10deg); }
            75% { transform: scale(1.1) rotate(-5deg); }
            100% { transform: scale(1) rotate(0deg); }
        }
        .icon-action-btn.music-toggling { animation: musicToggle 0.65s var(--tx-bounce); }
        @keyframes mutedPulse {
            0%, 100% { box-shadow: 0 0 0 0 rgba(248, 113, 113, 0.6); }
            50% { box-shadow: 0 0 0 12px rgba(248, 113, 113, 0); }
        }
        .icon-action-btn.muted { animation: mutedPulse 1.6s infinite; }

        @keyframes themeSunMoon {
            0% { transform: rotate(0deg) scale(1); }
            50% { transform: rotate(180deg) scale(1.25); }
            100% { transform: rotate(360deg) scale(1); }
        }
        .icon-action-btn.theme-toggling { animation: themeSunMoon 0.85s var(--tx-smooth); }

        @keyframes msgSlideLeft {
            from { opacity: 0; transform: translateX(-24px) scale(0.97); }
            to { opacity: 1; transform: translateX(0) scale(1); }
        }
        @keyframes msgSlideRight {
            from { opacity: 0; transform: translateX(24px) scale(0.95); }
            to { opacity: 1; transform: translateX(0) scale(1); }
        }
        .msg-bubble.user.msg-new { animation: msgSlideLeft 0.4s var(--tx-smooth) both; }
        .msg-bubble.bot.msg-new { animation: msgSlideRight 0.4s var(--tx-smooth) both; }

        @keyframes modalIn {
            from { opacity: 0; transform: scale(0.93) translateY(12px); }
            to { opacity: 1; transform: scale(1) translateY(0); }
        }
        .modal-overlay.active .modal-card { animation: modalIn 0.42s var(--tx-smooth) both; }

        .ripple {
            position: absolute;
            border-radius: 50%;
            background: rgba(255, 255, 255, 0.35);
            transform: scale(0);
            animation: rippleAnim 0.65s ease-out;
            pointer-events: none;
            z-index: 999;
        }
        @keyframes rippleAnim { to { transform: scale(4); opacity: 0; } }
        button, .footer-btn, .new-chat-btn, .send-btn, .icon-action-btn,
        .upload-icon-btn, .tab-btn, .msg-action-btn, .history-item, .logo-option {
            position: relative; overflow: hidden;
        }

        @keyframes spin { to { transform: rotate(360deg); } }
        .spinner {
            display: inline-block; width: 14px; height: 14px;
            border: 2px solid rgba(255,255,255,0.1);
            border-top-color: var(--accent1);
            border-radius: 50%;
            animation: spin 0.8s linear infinite;
            vertical-align: middle; margin-right: 6px;
        }

        .slider-row {
            display: flex; align-items: center; gap: 10px;
            margin-bottom: 10px; padding: 8px 12px;
            border-radius: 12px;
        }
        .slider-row label { flex: 0 0 110px; font-size: 11px; color: var(--text-muted); }
        .slider-row input[type="range"] { flex: 1; accent-color: var(--accent1); }
        .slider-row span { font-size: 11px; color: #fff; min-width: 40px; text-align: right; }

        #bgMedia { position: fixed; inset: 0; z-index: -3; width: 100%; height: 100%; object-fit: cover; display: none; }
        #bgMedia.active { display: block; }
        #bgVideo { position: fixed; inset: 0; z-index: -3; width: 100%; height: 100%; object-fit: cover; display: none; }
        #bgVideo.active { display: block; }
        #bgOverlay { position: fixed; inset: 0; z-index: -2; background: rgba(0,0,0,0.65); backdrop-filter: blur(2px); display: none; }
        #bgOverlay.active { display: block; }
        #authOverlay {
            position: fixed; inset: 0;
            background: rgba(7, 7, 10, 0.85);
            backdrop-filter: blur(40px) saturate(180%);
            -webkit-backdrop-filter: blur(40px) saturate(180%);
            z-index: 2000; display: flex; align-items: center; justify-content: center;
            padding: 20px; transition: opacity 0.4s ease;
        }
        #authOverlay.hidden { display: none; }
        .auth-card {
            width: 100%; max-width: 420px; padding: 30px;
            border-radius: 24px;
        }
        .auth-tabs { display: flex; gap: 10px; margin-bottom: 20px; background: rgba(0,0,0,0.25); padding: 4px; border-radius: 12px; }
        .auth-tab { flex: 1; padding: 10px; text-align: center; font-size: 13px; font-weight: 600; color: var(--text-muted); cursor: pointer; border-radius: 8px; transition: 0.2s; }
        .auth-tab.active { background: rgba(255,255,255,0.1); color: #fff; }
        .auth-input { width: 100%; background: rgba(255,255,255,0.05); border: 1px solid var(--lg-border-soft); border-radius: 12px; padding: 12px 16px; color: white; font-size: 14px; margin-bottom: 14px; outline: none; transition: 0.2s; }
        .auth-input:focus { border-color: var(--accent1); box-shadow: 0 0 0 3px rgba(59,130,246,0.2); }
        .auth-label { font-size: 11px; color: var(--text-muted); display: flex; align-items: center; gap: 6px; margin-bottom: 6px; margin-top: 4px; }
        .lang-select { width: 100%; background: rgba(255,255,255,0.05); border: 1px solid var(--lg-border-soft); border-radius: 12px; padding: 12px 16px; color: white; font-size: 14px; margin-bottom: 14px; outline: none; cursor: pointer; }
        .lang-select option { background: #0f172a; color: #fff; padding: 8px; }
        .auth-btn { width: 100%; background: var(--primary-gradient); color: white; border: none; padding: 12px; border-radius: 12px; font-weight: 600; cursor: pointer; font-size: 14px; box-shadow: 0 4px 15px rgba(59,130,246,0.3); }
        .auth-btn:disabled { opacity: 0.6; cursor: wait; }
        .modal-overlay { display: none; position: fixed; inset: 0; background: rgba(0,0,0,0.65); backdrop-filter: blur(10px); -webkit-backdrop-filter: blur(10px); z-index: 1500; align-items: center; justify-content: center; padding: 20px; }
        .modal-overlay.active { display: flex; }
        .modal-card { width: 100%; max-width: 560px; max-height: 90vh; overflow-y: auto; border-radius: 22px; padding: 25px; }
        .modal-card h3 { font-size: 15px; margin-bottom: 14px; color: #fff; display: flex; align-items: center; gap: 8px; }
        .modal-label { font-size: 10px; color: var(--text-muted); text-transform: uppercase; margin-bottom: 4px; display: block; margin-top: 10px; }
        .aurora-bg { position: fixed; inset: 0; pointer-events: none; z-index: -1; filter: blur(140px); opacity: {{ app_state.theme.aurora_opacity }}; overflow: hidden; transition: opacity 0.4s ease; }
        .aurora-blob { position: absolute; border-radius: 50%; transition: background 0.4s ease; }
        .blob-1 { width: 350px; height: 350px; background: var(--accent1); top: -50px; left: -50px; }
        .blob-2 { width: 450px; height: 450px; background: var(--accent2); bottom: -50px; right: -50px; }
        .blob-3 { width: 300px; height: 300px; background: var(--accent3); top: 40%; left: 40%; opacity: 0.5; }
        .app-layout { display: flex; height: 100dvh; width: 100vw; padding: 12px; gap: 12px; overflow: hidden; }
        .sidebar { width: 260px; min-width: 260px; display: flex; flex-direction: column; padding: 14px; gap: 10px; height: calc(100dvh - 24px); flex-shrink: 0; border-radius: 22px; }
        .logo-area { display: flex; align-items: center; gap: 10px; padding-bottom: 10px; border-bottom: 1px solid var(--lg-border-soft); }
        .logo-icon { width: 34px; height: 34px; background: var(--primary-gradient); border-radius: 10px; display: flex; align-items: center; justify-content: center; color: white; flex-shrink: 0; box-shadow: 0 4px 12px rgba(59,130,246,0.35); }
        .logo-text { min-width: 0; flex: 1; }
        .logo-text h1 { font-size: 13px; font-weight: 700; color: #fff; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
        .logo-text p { font-size: 10px; color: var(--text-muted); }
        .new-chat-btn { padding: 9px; border-radius: 12px; font-size: 12px; font-weight: 500; cursor: pointer; display: flex; align-items: center; justify-content: center; gap: 6px; color: #fff; }
        .new-chat-btn:hover { border-color: var(--accent1) !important; }
        .quick-stats { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; margin-top: 4px; }
        .stat-card { border-radius: 12px; padding: 8px; text-align: center; }
        .stat-card .stat-value { font-size: 15px; font-weight: 700; color: #fff; }
        .stat-card .stat-label { font-size: 9px; color: var(--text-muted); text-transform: uppercase; margin-top: 2px; }
        .chat-history-list { flex: 1; overflow-y: auto; display: flex; flex-direction: column; gap: 4px; min-height: 0; padding-right: 2px; }
        .history-item { padding: 9px 10px; border-radius: 10px; font-size: 12px; color: var(--text-muted); cursor: pointer; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; display: flex; align-items: center; gap: 8px; transition: 0.2s; }
        .history-item:hover { background: rgba(255,255,255,0.05) !important; }
        .history-item.active { background: rgba(59, 130, 246, 0.18) !important; color: #fff !important; border-color: rgba(59,130,246,0.3) !important; }
        .sidebar-footer { border-top: 1px solid var(--lg-border-soft); padding-top: 8px; display: flex; flex-direction: column; gap: 6px; }
        .footer-btn { border-radius: 10px; color: #fff; padding: 8px; font-size: 12px; cursor: pointer; display: flex; align-items: center; gap: 8px; }
        .main-workspace { flex: 1; display: flex; flex-direction: column; height: calc(100dvh - 24px); overflow: hidden; min-width: 0; position: relative; border-radius: 22px; }
        header { padding: 12px 18px; border-bottom: 1px solid var(--lg-border-soft); display: flex; justify-content: space-between; align-items: center; flex-shrink: 0; gap: 8px; border-radius: 22px 22px 0 0; }
        header h2 { font-size: 13px; font-weight: 600; color: #E2E8F0; display: flex; align-items: center; gap: 6px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
        .menu-toggle-btn { display: none; background: transparent; border: 1px solid var(--lg-border-soft); color: #fff; padding: 6px; border-radius: 8px; cursor: pointer; align-items: center; justify-content: center; flex-shrink: 0; }
        .status-badge { font-size: 10px; color: #38BDF8; background: rgba(56, 189, 248, 0.1); border: 1px solid rgba(56, 189, 248, 0.2); padding: 3px 8px; border-radius: 20px; display: flex; align-items: center; gap: 5px; flex-shrink: 0; white-space: nowrap; }
        .status-dot { width: 5px; height: 5px; background: #38BDF8; border-radius: 50%; box-shadow: 0 0 6px #38BDF8; }
        .icon-action-btn { color: #38BDF8; padding: 6px; border-radius: 10px; cursor: pointer; display: flex; align-items: center; justify-content: center; flex-shrink: 0; border: 1px solid rgba(56,189,248,0.2); }
        .icon-action-btn.muted { color: #F87171; border-color: rgba(248,113,113,0.3) !important; }
        .icon-action-btn.recording { color: #F87171; border-color: #F87171 !important; animation: pulseRec 1.2s infinite; }
        @keyframes pulseRec { 0%,100% { box-shadow: 0 0 0 0 rgba(248,113,113,0.7); } 50% { box-shadow: 0 0 0 8px rgba(248,113,113,0); } }
        .chat-container { flex: 1; padding: 16px; overflow-y: auto; overflow-x: hidden; display: flex; flex-direction: column; gap: 14px; min-height: 0; -webkit-overflow-scrolling: touch; }
        .msg-bubble { max-width: 85%; padding: 12px 16px; border-radius: 16px; font-size: 13px; line-height: 1.55; word-break: break-word; overflow-wrap: anywhere; position: relative; backdrop-filter: blur(20px) saturate(180%); -webkit-backdrop-filter: blur(20px) saturate(180%); }
        .msg-bubble.user { background: rgba(255,255,255,0.06); border: 1px solid var(--lg-border-soft); align-self: flex-start; color: #CBD5E1; }
        .msg-bubble.bot { background: rgba(20, 25, 40, 0.55); border: 1px solid rgba(59, 130, 246, 0.3); color: white; align-self: flex-end; width: 100%; max-width: 90%; }
        .msg-bubble b { display: block; font-size: 10px; margin-bottom: 4px; opacity: 0.7; text-transform: uppercase; }
        .msg-img { max-width: 100%; border-radius: 10px; margin-top: 6px; display: block; }
        .msg-actions { position: absolute; top: 6px; right: 6px; opacity: 0; transition: 0.2s; display: flex; gap: 4px; z-index: 10; }
        .msg-bubble:hover .msg-actions { opacity: 1; }
        .msg-action-btn { background: rgba(255,255,255,0.1); border: none; color: #fff; padding: 4px 6px; border-radius: 6px; font-size: 11px; cursor: pointer; display: flex; align-items: center; justify-content: center; }
        .typing-dots { display: inline-flex; gap: 3px; vertical-align: middle; }
        .typing-dots span { width: 6px; height: 6px; border-radius: 50%; background: #38BDF8; display: inline-block; animation: typingBounce 1.4s infinite ease-in-out both; }
        .typing-dots span:nth-child(1) { animation-delay: -0.32s; }
        .typing-dots span:nth-child(2) { animation-delay: -0.16s; }
        @keyframes typingBounce { 0%, 80%, 100% { transform: scale(0.6); opacity: 0.5; } 40% { transform: scale(1); opacity: 1; } }
        pre { background: rgba(4,4,6,0.6) !important; border: 1px solid var(--lg-border-soft); border-radius: 10px; padding: 10px; margin: 8px 0; overflow-x: auto; max-width: 100%; }
        code { font-family: 'Consolas', 'Monaco', monospace; font-size: 12px; color: #38BDF8; }
        .code-container { margin: 8px 0; max-width: 100%; }
        .code-header { display: flex; justify-content: space-between; align-items: center; font-size: 11px; color: var(--text-muted); margin-bottom: 4px; }
        .copy-code-btn { background: rgba(255,255,255,0.1); border: none; color: #fff; padding: 3px 6px; border-radius: 6px; font-size: 10px; cursor: pointer; }
        .control-panel { padding: 12px 16px; border-top: 1px solid var(--lg-border-soft); display: flex; gap: 10px; align-items: center; flex-shrink: 0; width: 100%; border-radius: 0 0 22px 22px; }
        .input-wrapper { border-radius: 14px; display: flex; align-items: center; padding: 0 10px; flex: 1; min-width: 0; }
        .input-wrapper input { background: transparent; border: none; outline: none; color: white; padding: 10px 6px; font-size: 13px; width: 100%; min-width: 0; }
        .upload-icon-btn { background: transparent; border: none; color: var(--text-muted); cursor: pointer; padding: 4px; display: flex; align-items: center; flex-shrink: 0; }
        .upload-icon-btn:hover { color: var(--accent1); }
        .send-btn { background: var(--primary-gradient); color: white; border: none; padding: 10px 18px; border-radius: 14px; font-weight: 600; font-size: 13px; cursor: pointer; display: flex; align-items: center; gap: 6px; flex-shrink: 0; box-shadow: 0 4px 15px rgba(59,130,246,0.3); }
        .avatar-btn { width: 34px; height: 34px; border-radius: 10px; background: var(--primary-gradient); color: #fff; display: flex; align-items: center; justify-content: center; font-weight: 700; cursor: pointer; overflow: hidden; flex-shrink: 0; border: 1px solid var(--lg-border-soft); }
        .avatar-btn img { width: 100%; height: 100%; object-fit: cover; }
        @media(max-width: 850px) {
            .app-layout { padding: 8px; gap: 8px; }
            .sidebar { position: fixed; top: 8px; left: 8px; height: calc(100dvh - 16px); z-index: 1000; box-shadow: 20px 0 60px rgba(0,0,0,0.9); transform: translateX(-110%); transition: transform 0.3s ease; width: 260px; min-width: 260px; }
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
        ::-webkit-scrollbar-thumb { background: rgba(255, 255, 255, 0.12); border-radius: 10px; }
        ::-webkit-scrollbar-track { background: transparent; }
        .color-picker-row { display: flex; align-items: center; gap: 10px; margin-bottom: 8px; padding: 6px 10px; border-radius: 10px; }
        .color-picker-row label { flex: 1; font-size: 11px; color: var(--text-muted); }
        .color-picker-row input[type="color"] { width: 40px; height: 30px; border: 1px solid var(--lg-border-soft); border-radius: 8px; background: transparent; cursor: pointer; }
        .range-row { display: flex; align-items: center; gap: 10px; margin-bottom: 8px; padding: 6px 10px; border-radius: 10px; }
        .range-row label { flex: 1; font-size: 11px; color: var(--text-muted); }
        .range-row input[type="range"] { flex: 1; accent-color: var(--accent1); }
        .range-row span { font-size: 11px; color: #fff; min-width: 30px; text-align: right; }
        .logo-picker { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; margin-top: 8px; }
        .logo-option { border-radius: 12px; padding: 10px; display: flex; align-items: center; justify-content: center; cursor: pointer; color: #fff; }
        .logo-option:hover { border-color: var(--accent1) !important; }
        .logo-option.selected { border-color: var(--accent1) !important; background: rgba(59,130,246,0.15) !important; }
        .music-item { display: flex; align-items: center; gap: 8px; padding: 8px 10px; border-radius: 10px; margin-bottom: 6px; font-size: 12px; }
        .music-item .name { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: #fff; }
        .music-item .del-btn { background: rgba(239,68,68,0.15); border: 1px solid rgba(239,68,68,0.3); color: #F87171; padding: 4px 8px; border-radius: 8px; font-size: 10px; cursor: pointer; }
        .user-item { display: flex; align-items: center; gap: 8px; padding: 8px 10px; border-radius: 10px; margin-bottom: 6px; font-size: 12px; }
        .user-item .name { flex: 1; min-width: 0; color: #fff; }
        .user-item .name small { color: var(--text-muted); font-size: 10px; display: flex; align-items: center; gap: 4px; margin-top: 2px; }
        .user-item .admin-badge { font-size: 9px; padding: 2px 6px; background: rgba(52,211,153,0.15); color: #34D399; border-radius: 6px; }
        .user-item .usr-btn { background: rgba(255,255,255,0.05); border: 1px solid var(--lg-border-soft); color: #fff; padding: 4px 8px; border-radius: 8px; font-size: 10px; cursor: pointer; }
        .user-item .usr-btn.danger { background: rgba(239,68,68,0.15); color: #F87171; border-color: rgba(239,68,68,0.3); }
        .toggle-row { display:flex; align-items:center; gap:10px; padding:10px; border-radius: 12px; margin-top: 4px; }
        .toggle-row label { flex:1; font-size:12px; color:#fff; display:flex; align-items:center; gap:6px; }
        .toggle-row input[type="checkbox"] { width:20px; height:20px; accent-color:var(--accent1); cursor:pointer; }
        .toast { position: fixed; top: 20px; left: 50%; transform: translateX(-50%) translateY(-100px); color: #fff; padding: 14px 22px; border-radius: 16px; font-size: 14px; font-weight: 500; z-index: 9999; box-shadow: 0 10px 40px rgba(0,0,0,0.6); transition: transform 0.35s var(--tx-bounce), opacity 0.3s ease; max-width: 90vw; text-align: center; border: 1px solid var(--lg-border-soft); }
        .toast.show { transform: translateX(-50%) translateY(0); }
        .toast.success { border-color: #34D399 !important; }
        .toast.error { border-color: #F87171 !important; }
        .tab-buttons { display: flex; gap: 6px; margin-bottom: 14px; padding: 4px; border-radius: 12px; }
        .tab-btn { flex: 1; padding: 8px; text-align: center; font-size: 11px; font-weight: 600; color: var(--text-muted); cursor: pointer; border-radius: 8px; }
        .tab-btn.active { background: rgba(255,255,255,0.1) !important; color: #fff !important; }
        .loading-chats { text-align: center; padding: 20px; font-size: 11px; color: var(--text-muted); }
        .download-btn { display: inline-flex; align-items: center; gap: 6px; background: rgba(56,189,248,0.15); color: #38BDF8; padding: 8px 14px; border-radius: 10px; font-size: 12px; font-weight: 600; text-decoration: none; border: 1px solid rgba(56,189,248,0.3); margin-top: 8px; transition: 0.2s; }
        .download-btn:hover { background: rgba(56,189,248,0.25); box-shadow: 0 0 12px rgba(56,189,248,0.3); }
    </style>
</head>
<body>

    <img id="bgMedia" alt="">
    <video id="bgVideo" autoplay muted loop playsinline></video>
    <div id="bgOverlay"></div>
    <audio id="bgMusic" loop></audio>

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
                    <option value="{{ code }}" {% if code == 'tr' %}selected{% endif %}>
                        {{ name }} ({{ code.upper() }})
                    </option>
                    {% endfor %}
                </select>
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

            <label class="modal-label">Botun Sana Yanıt Vereceği Dil</label>
            <select id="modalLanguage" class="lang-select">
                {% for code, name in supported_languages.items() %}
                <option value="{{ code }}" {% if code == user_language %}selected{% endif %}>
                    {{ name }} ({{ code.upper() }})
                </option>
                {% endfor %}
            </select>

            <div class="toggle-row" style="margin-top: 10px;">
                <label>
                    <i data-lucide="brain" width="14" height="14" style="color: var(--accent1);"></i>
                    Bot Hafızasını Temizle (Önceki sohbeti unutur)
                </label>
                <button class="auth-btn" style="width:auto; padding:8px 14px; font-size:12px; background: rgba(239,68,68,0.15); color: #F87171; border: 1px solid rgba(239,68,68,0.3);" onclick="clearBotMemory()">Temizle</button>
            </div>

            <div style="display: flex; gap: 8px; margin-top: 14px;">
                <button class="auth-btn" onclick="saveProfile()">Kaydet</button>
                <button class="auth-btn" style="background: rgba(255,255,255,0.1);" onclick="closeModal('profileModal')">İptal</button>
            </div>
            <div style="margin-top: 14px; border-top: 1px solid var(--lg-border-soft); padding-top: 12px;">
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

                <label class="modal-label">Liquid Glass Ayarları</label>
                <div class="slider-row">
                    <label>Blur Miktarı</label>
                    <input type="range" id="liquidBlur" min="0" max="80" step="1" value="40" oninput="updateLiquidBlur(this.value)">
                    <span id="liquidBlurVal">40px</span>
                </div>
                <div class="slider-row">
                    <label>Doygunluk</label>
                    <input type="range" id="liquidSaturate" min="100" max="300" step="10" value="200" oninput="updateLiquidSaturate(this.value)">
                    <span id="liquidSaturateVal">200%</span>
                </div>
                <div class="slider-row">
                    <label>Parlaklık</label>
                    <input type="range" id="liquidBrightness" min="0.8" max="1.4" step="0.05" value="1.1" oninput="updateLiquidBrightness(this.value)">
                    <span id="liquidBrightnessVal">1.1</span>
                </div>

                <label class="modal-label">Opaklık Ayarları</label>
                <div class="range-row">
                    <label>Cam Yoğunluğu</label>
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

                <label class="modal-label">Click Sesi</label>
                <div class="toggle-row">
                    <label>Tıklama sesi aktif</label>
                    <input type="checkbox" id="clickSoundToggle" checked onchange="toggleClickSound(this.checked)">
                </div>

                <div style="display: flex; gap: 8px; margin-top: 16px;">
                    <button class="auth-btn" onclick="saveTheme()">Kaydet ve Uygula</button>
                    <button class="auth-btn" style="background: rgba(255,255,255,0.1);" onclick="resetTheme()">Sıfırla</button>
                </div>
            </div>

            <div id="adminTab-users" style="display:none;">
                <p style="font-size:11px; color: v
