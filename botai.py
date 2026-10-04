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

os.makedirs(MUSIC_DIR, exist_ok=True)
os.makedirs(BG_DIR, exist_ok=True)
os.makedirs(AVATAR_DIR, exist_ok=True)
os.makedirs(STATIC_DIR, exist_ok=True)

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
if not GROQ_API_KEY:
    print("[UYARI] GROQ_API_KEY bulunamadı! .env dosyasına ekleyin.")
client = Groq(api_key=GROQ_API_KEY)


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

    # ============ KRİTİK: Eski görsel mesajları temizle ============
    # Groq "content must be a string" hatasının ana kaynağı buydu.
    try:
        c.execute("DELETE FROM bot_memory WHERE image_data IS NOT NULL AND image_data != ''")
        conn.commit()
        deleted = c.rowcount
        if deleted > 0:
            print(f"[DB MIGRATION] {deleted} eski görsel mesaj temizlendi.")
    except Exception as e:
        print(f"[DB MIGRATION HATA] görsel temizleme: {e}")

    # Görsel kolonunu tamamen boşalt (artık kullanmıyoruz)
    try:
        c.execute("UPDATE bot_memory SET image_data = NULL WHERE image_data IS NOT NULL")
        conn.commit()
    except Exception:
        pass

    # crewampfilms admin hesabı
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


# ============ BOT HAFIZA FONKSİYONLARI ============
# ÖNEMLİ: Görseller artık hafızaya kaydedilmiyor (Groq API uyumsuzluğunu önlemek için)
def memory_add(username, role, content, image_data=None, language="tr"):
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        # image_data her zaman None olarak kaydediliyor
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
    """Sadece metin mesajları al - görselleri atla"""
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("""SELECT role, content FROM bot_memory
                     WHERE username = ?
                     ORDER BY id DESC LIMIT ?""", (username, limit))
        rows = c.fetchall()
        conn.close()
        rows.reverse()
        # Görsel yok, sadece metin döner
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


def web_search(query, max_results=5):
    if requests is None:
        return ""

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
    except Exception as e:
        print(f"[SEARCH] Wikipedia hata: {e}")

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
        except Exception as e:
            print(f"[SEARCH] Wikipedia search hata: {e}")

    try:
        ddg_api = f"https://api.duckduckgo.com/?q={requests.utils.quote(query)}&format=json&no_html=1&skip_disambig=1&t=crszbot"
        r = requests.get(ddg_api, headers=headers, timeout=6)
        if r.status_code == 200:
            d = r.json()
            if d.get("AbstractText"):
                results.append(f"[DuckDuckGo] {d.get('Heading', '')}: {d['AbstractText'][:400]}")
            elif d.get("Answer"):
                results.append(f"[DuckDuckGo] {d['Answer']}")
            for topic in d.get("RelatedTopics", [])[:2]:
                if isinstance(topic, dict) and topic.get("Text"):
                    results.append(f"[DuckDuckGo] {topic['Text'][:250]}")
    except Exception as e:
        print(f"[SEARCH] DDG API hata: {e}")

    if len(results) < 2:
        try:
            html_url = f"https://lite.duckduckgo.com/lite/?q={requests.utils.quote(query)}"
            r = requests.get(html_url, headers=headers, timeout=8)
            if r.status_code == 200:
                html = r.text
                links = re.findall(r'<a[^>]*class="result-link"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', html, re.DOTALL)
                snippets = re.findall(r'<td[^>]*class="result-snippet"[^>]*>(.*?)</td>', html, re.DOTALL)
                for i, (link, title) in enumerate(links[:max_results]):
                    title_clean = re.sub(r'<[^>]+>', '', title).strip()
                    snippet = re.sub(r'<[^>]+>', '', snippets[i]).strip() if i < len(snippets) else ""
                    if title_clean:
                        results.append(f"[Web] {title_clean}: {snippet[:250]}")
        except Exception as e:
            print(f"[SEARCH] HTML fallback hata: {e}")

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


# ============ HAFIZALI AI YANITI ============
def get_ai_response(username, user_message, image_data=None):
    is_owner = is_admin_user(username)
    if not is_owner and ("samimi" in user_message.lower() and ("konuş" in user_message.lower() or "ol" in user_message.lower())):
        user_samimi_status[username] = True
    samimi_mode = is_owner or user_samimi_status.get(username, False)

    user = get_user_from_db(username)
    user_lang = (user.get("language") if user else "tr") or "tr"

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
            "Kodları uygun markdown blokları içinde, adım adım açıklamaları numaralandırılmış listeler halinde sun."
        )
    elif samimi_mode:
        persona = f"Senin adın {APP_STATE['bot_name']}. Karşındaki kullanıcı ({username}) ile samimi, dostça bir dille konuş. 'kanka' gibi hitaplar kullanma."
    else:
        persona = f"Senin adın {APP_STATE['bot_name']}. Karşındaki kullanıcı ({username}) ile resmi, kibar ve yardımcı bir dille konuş."

    lang_instruction = (
        f"\n\nCok onemli dil kurali: Su andan itibaren SADECE {active_lang_name} ({active_lang_code.upper()}) dilinde yanit ver. "
        f"Onceki mesajlarda farkli dilde konusmus olsan bile, bundan sonraki TUM yanitlarini {active_lang_name} dilinde ver. "
        f"Kullanici 'devam et', 'konus', 'yaz' gibi bir sey derse bile {active_lang_name} dilinde devam et."
    )
    persona += lang_instruction

    # Sadece metin hafızası - görsel YOK
    memory = memory_get(username, limit=20)
    messages = [{"role": "system", "content": persona}]

    for m in memory:
        content = m.get("content", "") or ""
        if not content:
            content = "[Bos mesaj]"
        messages.append({"role": m["role"], "content": content})

    # ============ KRİTİK: Görsel işleme ============
    if image_data:
        if "," in image_data:
            image_url = image_data
        else:
            image_url = f"data:image/jpeg;base64,{image_data}"
        # Groq'un görsel destekli modeli
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
        # Groq'un metin modelleri
        model_chain = ["openai/gpt-oss-120b", "openai/gpt-oss-20b"]

    # Hafızaya kaydet (görsel kaydedilmiyor)
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
                return "API anahtari gecersiz."
            if "rate" in err or "429" in err:
                return "Su an cok fazla istek var, birkac saniye sonra tekrar dene."
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
        <div class="sidebar lg" id="sidebar">
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
                <div class="loading-chats"><span class="spinner"></span> Yükleniyor...</div>
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

        <div class="main-workspace lg">
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
                    <div style="display: flex; align-items: flex-start; gap: 8px; margin-top: 6px;">
                        <i data-lucide="sparkles" width="16" height="16" style="color: var(--accent1); flex-shrink: 0; margin-top: 2px;"></i>
                        <span>Sistem hazır!</span>
                    </div>
                    <div style="margin-top: 10px; display: flex; flex-direction: column; gap: 6px;">
                        <div style="display: flex; align-items: flex-start; gap: 8px;">
                            <i data-lucide="brain" width="14" height="14" style="color: #38BDF8; flex-shrink: 0; margin-top: 2px;"></i>
                            <span><b style="display: inline; font-size: inherit; opacity: 1;">Hafıza aktif</b>: Önceki mesajları hatırlıyorum, "İngilizce konuş" dediğinde dil değişmiyor.</span>
                        </div>
                        <div style="display: flex; align-items: flex-start; gap: 8px;">
                            <i data-lucide="share-2" width="14" height="14" style="color: #38BDF8; flex-shrink: 0; margin-top: 2px;"></i>
                            <span><b style="display: inline; font-size: inherit; opacity: 1;">Sosyal medya desteği</b>: TikTok, Instagram, Twitter/X, YouTube, Reddit, GitHub, Spotify linklerini atabilirsin.</span>
                        </div>
                        <div style="display: flex; align-items: flex-start; gap: 8px;">
                            <i data-lucide="globe" width="14" height="14" style="color: #38BDF8; flex-shrink: 0; margin-top: 2px;"></i>
                            <span><b style="display: inline; font-size: inherit; opacity: 1;">Dil seçimi</b>: Profil ayarlarından dilini değiştirebilirsin.</span>
                        </div>
                        <div style="display: flex; align-items: flex-start; gap: 8px;">
                            <i data-lucide="search" width="14" height="14" style="color: #38BDF8; flex-shrink: 0; margin-top: 2px;"></i>
                            <span><b style="display: inline; font-size: inherit; opacity: 1;">Web arama</b>: "araştır" dediğinde web'de arama yapıyorum.</span>
                        </div>
                    </div>
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
                    <input type="text" id="message" placeholder="Mesaj yaz, fotoğraf yükle, link at ya da 'araştır' de..." onkeydown="if(event.key==='Enter') sendMessage()">
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
        let chats = [];
        let activeChatIndex = 0;
        let selectedBase64Image = null;
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

        const DEFAULT_THEME = {
            bg_deep: "#07070a", accent1: "#3B82F6", accent2: "#8B5CF6", accent3: "#06B6D4",
            glass_opacity: 0.03, aurora_opacity: 0.25
        };

        if ('serviceWorker' in navigator) {
            navigator.serviceWorker.register('/service-worker.js').catch(e => console.log('SW hata:', e));
        }

        let audioCtx = null;
        function initAudioCtx() {
            if (!audioCtx) {
                try {
                    audioCtx = new (window.AudioContext || window.webkitAudioContext)();
                } catch (e) { console.warn('AudioContext yok:', e); }
            }
            return audioCtx;
        }

        function playClickSound() {
            if (!clickSoundEnabled) return;
            const ctx = initAudioCtx();
            if (!ctx) return;
            if (ctx.state === 'suspended') ctx.resume();
            const now = ctx.currentTime;
            const osc = ctx.createOscillator();
            const gain = ctx.createGain();
            const filter = ctx.createBiquadFilter();
            osc.type = 'sine';
            osc.frequency.setValueAtTime(900, now);
            osc.frequency.exponentialRampToValueAtTime(420, now + 0.06);
            filter.type = 'lowpass';
            filter.frequency.setValueAtTime(2200, now);
            filter.Q.value = 0.9;
            gain.gain.setValueAtTime(0.0001, now);
            gain.gain.exponentialRampToValueAtTime(0.055, now + 0.006);
            gain.gain.exponentialRampToValueAtTime(0.0001, now + 0.08);
            osc.connect(filter);
            filter.connect(gain);
            gain.connect(ctx.destination);
            osc.start(now);
            osc.stop(now + 0.09);
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

        (function loadLiquidSettings() {
            const blur = localStorage.getItem('crsz_lg_blur');
            const sat = localStorage.getItem('crsz_lg_sat');
            const bri = localStorage.getItem('crsz_lg_bri');
            if (blur) { document.documentElement.style.setProperty('--lg-blur', blur + 'px'); }
            if (sat) { document.documentElement.style.setProperty('--lg-saturate', sat + '%'); }
            if (bri) { document.documentElement.style.setProperty('--lg-brightness', bri); }
            setTimeout(() => {
                const b = document.getElementById('liquidBlur'); if (b && blur) b.value = blur;
                const bv = document.getElementById('liquidBlurVal'); if (bv && blur) bv.innerText = blur + 'px';
                const s = document.getElementById('liquidSaturate'); if (s && sat) s.value = sat;
                const sv = document.getElementById('liquidSaturateVal'); if (sv && sat) sv.innerText = sat + '%';
                const br = document.getElementById('liquidBrightness'); if (br && bri) br.value = bri;
                const brv = document.getElementById('liquidBrightnessVal'); if (brv && bri) brv.innerText = bri;
            }, 300);
        })();

        (function() {
            const savedMode = localStorage.getItem('crsz_theme_mode') || 'dark';
            if (savedMode === 'light') setTimeout(() => applyColorMode('light'), 50);
        })();

        function updateLiquidBlur(val) {
            document.documentElement.style.setProperty('--lg-blur', val + 'px');
            document.getElementById('liquidBlurVal').innerText = val + 'px';
            localStorage.setItem('crsz_lg_blur', val);
        }
        function updateLiquidSaturate(val) {
            document.documentElement.style.setProperty('--lg-saturate', val + '%');
            document.getElementById('liquidSaturateVal').innerText = val + '%';
            localStorage.setItem('crsz_lg_sat', val);
        }
        function updateLiquidBrightness(val) {
            document.documentElement.style.setProperty('--lg-brightness', val);
            document.getElementById('liquidBrightnessVal').innerText = val;
            localStorage.setItem('crsz_lg_bri', val);
        }

        function applyColorMode(mode) {
            const root = document.documentElement;
            const body = document.body;
            if (mode === 'light') {
                root.style.setProperty('--bg-deep', '#f1f5f9');
                root.style.setProperty('--text-main', '#0f172a');
                root.style.setProperty('--text-muted', '#475569');
                root.style.setProperty('--lg-tint', 'rgba(255,255,255,0.55)');
                root.style.setProperty('--lg-tint-2', 'rgba(255,255,255,0.7)');
                root.style.setProperty('--lg-border-soft', 'rgba(15,23,42,0.10)');
                root.style.setProperty('--lg-border', 'rgba(15,23,42,0.15)');
                body.style.color = '#0f172a';
                let lightStyle = document.getElementById('lightThemeOverride');
                if (!lightStyle) {
                    lightStyle = document.createElement('style');
                    lightStyle.id = 'lightThemeOverride';
                    document.head.appendChild(lightStyle);
                }
                lightStyle.textContent = `
                    body { background: #f1f5f9 !important; color: #0f172a !important; }
                    .logo-text h1, header h2 { color: #0f172a !important; }
                    .logo-text p, .stat-card .stat-label, .history-item { color: #64748b !important; }
                    .stat-card .stat-value { color: #0f172a !important; }
                    .history-item.active { background: rgba(59,130,246,0.15) !important; color: #0f172a !important; }
                    .new-chat-btn, .footer-btn { color: #0f172a !important; }
                    .msg-bubble.user { background: rgba(255,255,255,0.75) !important; color: #0f172a !important; }
                    .msg-bubble.user b { color: #64748b !important; opacity: 1 !important; }
                    .msg-bubble.bot { background: rgba(30,41,59,0.9) !important; color: #f8fafc !important; }
                    .msg-bubble.bot b { color: #94a3b8 !important; opacity: 1 !important; }
                    .input-wrapper input { color: #0f172a !important; }
                    .input-wrapper input::placeholder { color: #94a3b8 !important; }
                    .upload-icon-btn { color: #64748b !important; }
                    .modal-card h3 { color: #0f172a !important; }
                    .modal-label { color: #64748b !important; }
                    .auth-input, .lang-select { color: #0f172a !important; background: rgba(255,255,255,0.6) !important; }
                    .lang-select option { background: #fff; color: #0f172a; }
                    .tab-btn { color: #64748b !important; }
                    .tab-btn.active { background: rgba(59,130,246,0.15) !important; color: #0f172a !important; }
                    .music-item .name, .user-item .name, .toggle-row label { color: #0f172a !important; }
                    .slider-row label, .range-row label, .color-picker-row label { color: #64748b !important; }
                    .slider-row span, .range-row span { color: #0f172a !important; }
                    .aurora-bg { opacity: 0.15 !important; }
                    ::-webkit-scrollbar-thumb { background: rgba(15,23,42,0.15) !important; }
                    #bgOverlay { background: rgba(255,255,255,0.5) !important; }
                    pre { background: rgba(241,245,249,0.6) !important; }
                    code { color: #3b82f6 !important; }
                `;
            } else {
                const oldLight = document.getElementById('lightThemeOverride');
                if (oldLight) oldLight.remove();
                root.style.setProperty('--bg-deep', '{{ app_state.theme.bg_deep }}');
                root.style.setProperty('--text-main', '#F8FAFC');
                root.style.setProperty('--text-muted', '#94A3B8');
                root.style.setProperty('--lg-tint', 'rgba(255, 255, 255, 0.04)');
                root.style.setProperty('--lg-tint-2', 'rgba(255, 255, 255, 0.08)');
                root.style.setProperty('--lg-border-soft', 'rgba(255, 255, 255, 0.08)');
                root.style.setProperty('--lg-border', 'rgba(255, 255, 255, 0.18)');
                body.style.color = '#F8FAFC';
            }
        }

        function toggleColorMode() {
            const current = localStorage.getItem('crsz_theme_mode') || 'dark';
            const next = current === 'dark' ? 'light' : 'dark';
            document.documentElement.classList.add('theme-transitioning');
            const btn = document.getElementById('themeToggleBtn');
            if (btn) {
                btn.classList.add('theme-toggling');
                setTimeout(() => btn.classList.remove('theme-toggling'), 850);
            }
            localStorage.setItem('crsz_theme_mode', next);
            applyColorMode(next);
            showToast(next === 'dark' ? 'Koyu tema' : 'Açık tema', 'success');
            setTimeout(() => document.documentElement.classList.remove('theme-transitioning'), 750);
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

        async function loadChatsFromServer() {
            if (!loggedIn) {
                if (chats.length === 0) {
                    chats = [{ title: "Varsayılan Sohbet", messages: [] }];
                    activeChatIndex = 0;
                    renderChatHistory(); renderActiveChat(); updateStats();
                }
                isInitialLoad = false;
                return;
            }
            try {
                const res = await fetch('/chats');
                const data = await res.json();
                if (data.status === 'success' && Array.isArray(data.chats) && data.chats.length > 0) {
                    chats = data.chats.map(c => ({
                        id: c.id,
                        title: c.title || "Sohbet",
                        messages: Array.isArray(c.messages) ? c.messages : []
                    }));
                    activeChatIndex = 0;
                } else {
                    chats = [{ title: "Varsayılan Sohbet", messages: [] }];
                    activeChatIndex = 0;
                }
                isInitialLoad = false;
                renderChatHistory(); renderActiveChat(); updateStats();
            } catch (e) {
                console.error('[CHATS] Yüklenemedi:', e);
                chats = [{ title: "Varsayılan Sohbet", messages: [] }];
                activeChatIndex = 0;
                isInitialLoad = false;
                renderChatHistory(); renderActiveChat(); updateStats();
            }
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
            btn.classList.add('music-toggling');
            setTimeout(() => btn.classList.remove('music-toggling'), 700);
            if (musicMuted) {
                audio.pause();
                btn.classList.add('muted');
                icon.setAttribute('data-lucide', 'volume-x');
                showToast("Müzik kapatıldı", "info");
            } else {
                if (musicPlaylist.length > 0 && !audio.src) playMusic(0);
                else audio.play().catch(e => {});
                btn.classList.remove('muted');
                icon.setAttribute('data-lucide', 'volume-2');
                showToast("Müzik açıldı", "info");
            }
            lucide.createIcons();
        }

        function applyThemeLocal(theme) {
            const root = document.documentElement;
            root.style.setProperty('--bg-deep', theme.bg_deep);
            root.style.setProperty('--accent1', theme.accent1);
            root.style.setProperty('--accent2', theme.accent2);
            root.style.setProperty('--accent3', theme.accent3);
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
                        c.innerHTML += `<div class="user-item"><i data-lucide="user" width="16" height="16" style="color: var(--accent1);"></i><div class="name">${u.username}<small>${u.email || 'e-posta yok'} &bull; <i data-lucide="globe" width="10" height="10"></i> ${u.language}</small></div>${u.is_admin ? '<span class="admin-badge">ADMIN</span>' : ''}<button class="usr-btn" onclick="toggleAdmin(${u.id})">${u.is_admin ? 'Admin Kaldır' : 'Admin Yap'}</button><button class="usr-btn danger" onclick="deleteUser(${u.id})">Sil</button></div>`;
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

        async function clearBotMemory() {
            if (!confirm("Bot hafızasını temizlemek istediğine emin misin? Önceki tüm sohbeti unutacak.")) return;
            try {
                const res = await fetch('/memory/clear', { method: 'POST' });
                const data = await res.json();
                if (data.status === 'success') {
                    showToast("Bot hafızası temizlendi!", "success");
                    closeModal('profileModal');
                }
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
            const language = document.getElementById('authLanguage').value;
            if (!username || !password) { showToast("Kullanıcı adı ve şifre zorunlu!", "error"); return; }
            const submitBtn = document.getElementById('authSubmitBtn');
            const originalText = submitBtn.innerText;
            submitBtn.innerText = "İşleniyor..."; submitBtn.disabled = true;
            try {
                const res = await fetch('/auth', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ action: authMode, username, email, password, language }) });
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
            const language = document.getElementById('modalLanguage').value;
            try {
                const res = await fetch('/update-profile', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ bot_name, language }) });
                const data = await res.json();
                showToast("Profil kaydedildi! Dil: " + language.toUpperCase(), "success");
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

        async function startNewChat() {
            await saveChatToServer();
            chats.push({ title: "Yeni Sohbet " + (chats.length + 1), messages: [] });
            activeChatIndex = chats.length - 1;
            isInitialLoad = false;
            animatingMessageIndex = -1;
            renderChatHistory(); renderActiveChat(); updateStats();
            if (window.innerWidth <= 850) toggleMobileSidebar();
        }

        function switchChat(index) {
            activeChatIndex = index;
            isInitialLoad = false;
            animatingMessageIndex = -1;
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
            if (chats.length === 0) {
                list.innerHTML = '<div style="text-align:center;padding:20px;font-size:11px;color:var(--text-muted);">Sohbet yok</div>';
                return;
            }
            chats.forEach((chat, idx) => {
                list.innerHTML += `<div class="history-item ${idx === activeChatIndex ? 'active' : ''}" onclick="switchChat(${idx})"><i data-lucide="message-square" width="12" height="12"></i> ${escapeHtml(chat.title)}</div>`;
            });
            lucide.createIcons();
        }
        function escapeHtml(s) { return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;'); }

        function renderActiveChat() {
            const chatBox = document.getElementById('chatBox');
            chatBox.innerHTML = '';
            if (!chats[activeChatIndex]) {
                chatBox.innerHTML = '<div class="msg-bubble user"><b>Sistem</b>Bir sohbet seç veya yeni bir tane aç.</div>';
                return;
            }
            chats[activeChatIndex].messages.forEach((m, idx) => {
                let imgHtml = m.image ? `<img src="${m.image}" class="msg-img">` : '';
                let actions = `<div class="msg-actions">
                    ${m.sender === 'bot' ? `<button class="msg-action-btn" onclick="speakText(${idx})" title="Sesli Oku"><i data-lucide="volume-2" width="12" height="12"></i></button>` : ''}
                    <button class="msg-action-btn" onclick="copyMsg(${idx})" title="Kopyala"><i data-lucide="copy" width="12" height="12"></i></button>
                    <button class="msg-action-btn" onclick="deleteMsg(${idx})" title="Sil"><i data-lucide="trash-2" width="12" height="12"></i></button>
                </div>`;
                const isNew = (!isInitialLoad && idx === animatingMessageIndex);
                const newClass = isNew ? ' msg-new' : '';
                chatBox.innerHTML += `<div class="msg-bubble ${m.sender}${newClass}"><b>${escapeHtml(m.name)}</b>${imgHtml}${m.content}${actions}</div>`;
            });
            chatBox.scrollTop = chatBox.scrollHeight;
            lucide.createIcons();
            animatingMessageIndex = -1;
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
            isInitialLoad = false;
            animatingMessageIndex = -1;
            renderActiveChat();
            saveChatToServer();
        }
        function copyCode(btn) { const pre = btn.parentElement.nextElementSibling; navigator.clipboard.writeText(pre.innerText); btn.innerText = "Kopyalandı!"; setTimeout(() => btn.innerText = "Kopyala", 2000); }

        async function sendMessage() {
            const messageInput = document.getElementById('message');
            const message = messageInput.value.trim();
            if (!message && !selectedBase64Image) return;
            if (!chats[activeChatIndex]) {
                chats.push({ title: "Sohbet", messages: [] });
                activeChatIndex = chats.length - 1;
            }
            if (chats[activeChatIndex].messages.length === 0 && message) {
                chats[activeChatIndex].title = message.length > 18 ? message.substring(0, 18) + '...' : message;
                renderChatHistory();
            }
            const currentImg = selectedBase64Image;
            chats[activeChatIndex].messages.push({ sender: 'user', name: currentUser, content: escapeHtml(message), image: currentImg });
            isInitialLoad = false;
            animatingMessageIndex = chats[activeChatIndex].messages.length - 1;
            renderActiveChat();
            messageInput.value = ''; removeImage();

            chats[activeChatIndex].messages.push({ sender: 'bot', name: 'Crsz Bot', content: '<span class="typing-dots"><span></span><span></span><span></span></span>' });
            animatingMessageIndex = chats[activeChatIndex].messages.length - 1;
            renderActiveChat();

            saveChatToServer();

            try {
                const res = await fetch('/chat', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ username: currentUser, message, image: currentImg }) });
                if (!res.ok) throw new Error('Sunucu ' + res.status);
                const data = await res.json();
                chats[activeChatIndex].messages.pop();
                let formattedReply = safeMarkdownParse(data.reply || 'Boş cevap geldi.');
                chats[activeChatIndex].messages.push({ sender: 'bot', name: 'Crsz Bot', content: formattedReply });
                isInitialLoad = false;
                animatingMessageIndex = chats[activeChatIndex].messages.length - 1;
                renderActiveChat();
                saveChatToServer();
            } catch (err) {
                chats[activeChatIndex].messages.pop();
                chats[activeChatIndex].messages.push({ sender: 'bot', name: 'Crsz Bot', content: `Bağlantı hatası: ${escapeHtml(err.message)}` });
                isInitialLoad = false;
                animatingMessageIndex = chats[activeChatIndex].messages.length - 1;
                renderActiveChat();
            }
        }

        async function saveChatToServer() {
            if (!loggedIn) return;
            if (!chats[activeChatIndex]) return;
            try {
                const chat = chats[activeChatIndex];
                await fetch('/chats/save', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        title: chat.title || "Sohbet",
                        messages: chat.messages
                    })
                });
            } catch (e) { console.error('[CHATS] Kaydedilemedi:', e); }
        }

        function createRipple(e) {
            const btn = e.currentTarget;
            const rect = btn.getBoundingClientRect();
            const circle = document.createElement('span');
            const diameter = Math.max(rect.width, rect.height);
            const radius = diameter / 2;
            circle.style.width = circle.style.height = `${diameter}px`;
            circle.style.left = `${e.clientX - rect.left - radius}px`;
            circle.style.top = `${e.clientY - rect.top - radius}px`;
            circle.classList.add('ripple');
            const existing = btn.querySelector('.ripple');
            if (existing) existing.remove();
            btn.appendChild(circle);
            setTimeout(() => circle.remove(), 650);
        }

        function bindRipple(el) {
            if (el.dataset.ripple === '1') return;
            el.dataset.ripple = '1';
            el.addEventListener('click', function(e) {
                playClickSound();
                createRipple(e);
            });
        }

        document.querySelectorAll('button, .footer-btn, .new-chat-btn, .send-btn, .icon-action-btn, .upload-icon-btn, .tab-btn, .msg-action-btn, .history-item, .logo-option').forEach(bindRipple);

        const observer = new MutationObserver(() => {
            document.querySelectorAll('button:not([data-ripple]), .footer-btn:not([data-ripple]), .new-chat-btn:not([data-ripple]), .send-btn:not([data-ripple]), .icon-action-btn:not([data-ripple]), .upload-icon-btn:not([data-ripple]), .tab-btn:not([data-ripple]), .msg-action-btn:not([data-ripple]), .history-item:not([data-ripple]), .logo-option:not([data-ripple])').forEach(bindRipple);
        });
        observer.observe(document.body, { childList: true, subtree: true });

        loadThemeFromServer();
        loadMusic();
        loadChatsFromServer();

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
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
