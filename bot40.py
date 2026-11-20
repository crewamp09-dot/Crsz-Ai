import os
import json
import sqlite3
import threading
import time
import uuid
import queue
import traceback
import re
from collections import Counter
from datetime import datetime, timedelta
from functools import wraps
from types import SimpleNamespace

from flask import (
    Flask, render_template_string, request, jsonify,
    session, send_from_directory, Response, stream_with_context
)
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
AI_IMAGE_DIR = os.path.join(UPLOAD_DIR, "ai_images")
FILES_DIR = os.path.join(UPLOAD_DIR, "ai_files")
DB_FILE = os.path.join(BASE_DIR, "crszbot.db")

for d in (UPLOAD_DIR, MUSIC_DIR, BG_DIR, AVATAR_DIR, STATIC_DIR, AI_IMAGE_DIR, FILES_DIR):
    os.makedirs(d, exist_ok=True)

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
if not GROQ_API_KEY:
    print("[UYARI] GROQ_API_KEY bulunamadı! .env dosyasına ekleyin.")
client = Groq(api_key=GROQ_API_KEY)

AGNES_API_KEY = os.getenv("AGNES_API_KEY", "")
if not AGNES_API_KEY:
    print("[UYARI] AGNES_API_KEY bulunamadı! Görsel üretimi için .env dosyasına ekleyin.")

ALLOWED_DOC_EXTENSIONS = {".txt", ".md", ".csv", ".log", ".pdf"}
MAX_DOC_CHARS = 12000

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


BOT_MODES = {
    "normal": {"label": "Normal", "icon": "message-circle", "instruction": ""},
    "technical": {
        "label": "Teknik Uzman",
        "icon": "cpu",
        "instruction": (
            "\n\nMOD: TEKNIK UZMAN. Cevaplarini kesin, teknik terimlerle, dogru kutuphane/fonksiyon adlariyla ver. "
            "Gereksiz sohbet etme, gereksiz giris cumleleri kullanma, direkt teknik cozume gec. "
            "Kod gerekiyorsa tam ve calisir kod ver, yarim birakma."
        )
    },
    "teacher": {
        "label": "Öğretmen",
        "icon": "graduation-cap",
        "instruction": (
            "\n\nMOD: OGRETMEN. Konuyu sifirdan, adim adim, basit ornekler kullanarak anlat. "
            "Karmasik terimleri kullandiginda hemen parantez icinde ne anlama geldigini acikla. "
            "Anlatim sonunda kisa bir ozet veya kontrol sorusu sor."
        )
    },
    "funny": {
        "label": "Esprili",
        "icon": "smile",
        "instruction": (
            "\n\nMOD: ESPRILI ARKADAS. Samimi, esprili, bol emoji kullanan rahat bir dille konus. "
            "Dogru bilgiyi vermekten odun verme ama anlatimini eglenceli hale getir."
        )
    },
    "concise": {
        "label": "Kısa & Öz",
        "icon": "zap",
        "instruction": (
            "\n\nMOD: KISA VE OZ. Cevaplarini mumkun oldugunca kisa tut. Gereksiz aciklama, giris veya "
            "tekrar yapma. Sadece istenen bilgiyi dogrudan ver, en fazla birkac cumle veya madde kullan."
        )
    },
    "motivational": {
        "label": "Motivasyonel Koç",
        "icon": "flame",
        "instruction": (
            "\n\nMOD: MOTIVASYONEL KOC. Kullaniciyi tesvik eden, pozitif ve enerjik bir dille konus. "
            "Zorluklari cozulebilir adimlara bol, kullaniciyi harekete gecmeye tesvik et."
        )
    },
}

SUPPORTED_LANGUAGES = {
    "tr": "Türkçe", "en": "English", "de": "Deutsch", "fr": "Français",
    "es": "Español", "ar": "العربية", "ru": "Русский", "it": "Italiano",
    "pt": "Português", "nl": "Nederlands",
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
        bot_mode TEXT DEFAULT 'normal',
        custom_personality TEXT DEFAULT '',
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
            return column in [row[1] for row in c.fetchall()]
        except Exception:
            return False

    migrations = [
        ("users", "language", "ALTER TABLE users ADD COLUMN language TEXT DEFAULT 'tr'"),
        ("users", "is_admin", "ALTER TABLE users ADD COLUMN is_admin INTEGER DEFAULT 0"),
        ("users", "avatar", "ALTER TABLE users ADD COLUMN avatar TEXT"),
        ("users", "email", "ALTER TABLE users ADD COLUMN email TEXT"),
        ("users", "bot_mode", "ALTER TABLE users ADD COLUMN bot_mode TEXT DEFAULT 'normal'"),
        ("users", "custom_personality", "ALTER TABLE users ADD COLUMN custom_personality TEXT DEFAULT ''"),
    ]
    for tbl, col, sql in migrations:
        if not column_exists(tbl, col):
            try:
                c.execute(sql)
                conn.commit()
            except Exception as e:
                print(f"[DB MIGRATION HATA] {tbl}.{col}: {e}")

    try:
        c.execute("DELETE FROM bot_memory WHERE image_data IS NOT NULL AND image_data != ''")
        c.execute("UPDATE bot_memory SET image_data = NULL WHERE image_data IS NOT NULL")
        conn.commit()
    except Exception:
        pass

    for admin_name, admin_email in [("crewampfilms", "crszbot052@gmail.com"), ("crew", "")]:
        c.execute("SELECT COUNT(*) FROM users WHERE username = ?", (admin_name,))
        if c.fetchone()[0] == 0:
            c.execute(
                "INSERT INTO users (username, email, password, is_admin, language) VALUES (?, ?, ?, 1, 'tr')",
                (admin_name, admin_email, generate_password_hash("123"))
            )
            conn.commit()
        else:
            c.execute("UPDATE users SET is_admin = 1 WHERE username = ?", (admin_name,))
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
            try:
                return json.loads(row[0])
            except Exception:
                return row[0]
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
        c.execute(
            "SELECT id, username, email, password, avatar, is_admin, language, bot_mode, custom_personality "
            "FROM users WHERE LOWER(username) = LOWER(?)",
            (username,)
        )
        row = c.fetchone()
        conn.close()
        if row:
            return {
                "id": row[0], "username": row[1], "email": row[2], "password": row[3],
                "avatar": row[4] or "", "is_admin": bool(row[5]), "language": row[6] or "tr",
                "bot_mode": row[7] or "normal", "custom_personality": row[8] or ""
            }
        return None
    except Exception as e:
        print(f"[DB USER HATA] {e}")
        return None


def create_user(username, email, password, is_admin=False, language="tr"):
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute(
            "INSERT INTO users (username, email, password, is_admin, language) VALUES (?, ?, ?, ?, ?)",
            (username, email, generate_password_hash(password), 1 if is_admin else 0, language)
        )
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


def update_user_bot_mode(username, bot_mode):
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("UPDATE users SET bot_mode = ? WHERE LOWER(username) = LOWER(?)", (bot_mode, username))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"[DB MODE HATA] {e}")
        return False


def update_user_custom_personality(username, text):
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("UPDATE users SET custom_personality = ? WHERE LOWER(username) = LOWER(?)", (text, username))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"[DB PERSONALITY HATA] {e}")
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
        c.execute(
            "INSERT INTO bot_memory (username, role, content, image_data, language) VALUES (?, ?, ?, NULL, ?)",
            (username, role, content, language)
        )
        c.execute(
            """DELETE FROM bot_memory WHERE username = ? AND id NOT IN (
                SELECT id FROM bot_memory WHERE username = ? ORDER BY id DESC LIMIT 20
            )""",
            (username, username)
        )
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
        c.execute(
            """SELECT role, content FROM bot_memory
               WHERE username = ?
               ORDER BY id DESC LIMIT ?""",
            (username, limit)
        )
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
            try:
                msgs = json.loads(r[2]) if r[2] else []
            except Exception:
                msgs = []
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
    if not username:
        return False
    if username.lower() in [u.lower() for u in ADMIN_USERS]:
        return True
    u = get_user_from_db(username)
    return bool(u and u.get("is_admin"))


def web_search(query, max_results=6):
    results = []
    if DDGS is not None:
        try:
            with DDGS() as ddgs:
                search_results = list(ddgs.text(query, region="tr-tr", safesearch="moderate", max_results=max_results))
            for r in search_results:
                title = r.get("title", "")
                body = r.get("body", "")
                href = r.get("href", "")
                if title and body:
                    results.append(f"[{href}] {title}: {body[:300]}")
        except Exception as e:
            print(f"[SEARCH] ddgs hata: {e}")

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
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8"
    }
    info = []
    try:
        if platform == "tiktok":
            r = requests.get(f"https://www.tiktok.com/oembed?url={url}", headers=headers, timeout=8)
            if r.status_code == 200:
                d = r.json()
                info.append(f"[TikTok] Başlık: {d.get('title', 'N/A')}")
                info.append(f"[TikTok] Yazar: {d.get('author_name', 'N/A')} (@{d.get('author_unique_id', '')})")
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
                    info.append(f"[GitHub] Repo: {d.get('full_name', 'N/A')}")
                    info.append(f"[GitHub] Açıklama: {d.get('description', 'N/A')}")
                    info.append(f"[GitHub] Yıldız: {d.get('stargazers_count', 0)}")
        elif platform == "spotify":
            r = requests.get(f"https://open.spotify.com/oembed?url={url}", headers=headers, timeout=8)
            if r.status_code == 200:
                d = r.json()
                info.append(f"[Spotify] Başlık: {d.get('title', 'N/A')}")
                info.append(f"[Spotify] Sanatçı: {d.get('author_name', 'N/A')}")
    except Exception as e:
        print(f"[SOCIAL] {platform} hata: {e}")
    return "\n".join(info) if info else ""


def should_search(msg):
    triggers = [
        "araştır", "araştıralım", "güncel", "son dakika", "haber", "bugün",
        "2025", "2026", "kimdir", "nedir", "nasıl yapılır", "fiyat", "kaç tl",
        "ne zaman", "nerede", "web'de", "internetten", "search", "google"
    ]
    m = msg.lower()
    return any(t in m for t in triggers)


def detect_media_request(text):
    if not text:
        return None, None
    t = text.strip()
    lower = t.lower()

    image_keywords = ["fotoğraf", "fotograf", "resim", "görsel", "gorsel", "image", "picture", "photo", "çiz", "ciz", "resmet"]
    create_verbs = ["oluştur", "olustur", "oluşt", "olust", "yap", "yapsana", "üret", "uret", "hazırla", "hazirla", "çiz", "ciz", "çeksene", "ceksene", "istiyorum", "isterim", "göster", "goster"]

    has_image = any(k in lower for k in image_keywords)
    has_verb = any(v in lower for v in create_verbs)

    if has_image and has_verb:
        prompt = t
        for kw in image_keywords + create_verbs + ["bir", "bana", "lütfen", "acaba"]:
            prompt = re.sub(rf'\b{re.escape(kw)}\b', '', prompt, flags=re.IGNORECASE)
        prompt = re.sub(r'\s+', ' ', prompt).strip(" :,-")
        if len(prompt) < 3:
            prompt = t
        return "image", prompt

    if lower.startswith("/foto") or lower.startswith("/resim") or lower.startswith("/img"):
        prompt = re.sub(r'^/\w+\s*', '', t).strip()
        return ("image", prompt) if prompt else (None, None)

    return None, None


def generate_image(prompt):
    if not AGNES_API_KEY:
        return None, "Görsel üretimi için .env dosyasına AGNES_API_KEY ekle."
    if requests is None:
        return None, "requests paketi kurulu değil."

    try:
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
                return filename, None
            return None, f"Görsel indirilemedi (HTTP {img_r.status_code})"
        if r.status_code == 401:
            return None, "Agnes API anahtarı geçersiz."
        if r.status_code == 402:
            return None, "Agnes API kredisi bitmiş."
        return None, f"Agnes API hatası: HTTP {r.status_code}"
    except Exception as e:
        return None, str(e)


def extract_document_text(filepath, ext):
    ext = ext.lower()
    try:
        if ext == ".pdf":
            try:
                from pypdf import PdfReader
            except ImportError:
                try:
                    from PyPDF2 import PdfReader
                except ImportError:
                    return None, "PDF okumak için 'pip install pypdf' kur veya .txt yükle."
            reader = PdfReader(filepath)
            text = "\n".join((page.extract_text() or "") for page in reader.pages).strip()
        else:
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                text = f.read().strip()

        if not text:
            return None, "Belgeden metin çıkarılamadı."

        truncated = len(text) > MAX_DOC_CHARS
        text = text[:MAX_DOC_CHARS]
        if truncated:
            text += "\n\n[...belge uzunluk sınırı nedeniyle kırpıldı...]"
        return text, None
    except Exception as e:
        return None, str(e)


def get_ai_response(username, user_message, image_data=None, document_text=None, document_name=None):
    is_owner = is_admin_user(username)
    if not is_owner and ("samimi" in user_message.lower() and ("konuş" in user_message.lower() or "ol" in user_message.lower())):
        user_samimi_status[username] = True
    samimi_mode = is_owner or user_samimi_status.get(username, False)

    user = get_user_from_db(username)
    user_lang = (user.get("language") if user else "tr") or "tr"
    user_bot_mode = (user.get("bot_mode") if user else "normal") or "normal"
    mode_instruction = BOT_MODES.get(user_bot_mode, BOT_MODES["normal"])["instruction"]

    if not image_data:
        media_type, media_prompt = detect_media_request(user_message)
        if media_type == "image":
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
            memory_add(username, "user", user_message, None, user_lang)
            reply_text = f"Fotoğraf oluşturamadım. {err}"
            memory_add(username, "assistant", reply_text, None, user_lang)
            return reply_text

    detected_lang = None
    lang_commands = {
        "ingilizce": "en", "english": "en", "speak english": "en",
        "almanca": "de", "deutsch": "de", "german": "de",
        "fransızca": "fr", "français": "fr", "french": "fr",
        "ispanyolca": "es", "español": "es", "spanish": "es",
        "arapça": "ar", "arabic": "ar", "rusça": "ru", "russian": "ru",
        "italyanca": "it", "italian": "it", "portekizce": "pt", "portuguese": "pt",
        "hollandaca": "nl", "dutch": "nl", "türkçe": "tr", "turkish": "tr",
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

    if is_owner:
        persona = (
            f"Senin adın {APP_STATE['bot_name']}. Karşındaki kişi senin sahibin crewampfilms. "
            "Onunla konuşurken samimi, rahat ve gerektiğinde hafif arsız bir dille konuş. "
            "ÖNEMLİ: 'kanka', 'kardeşim', 'bro', 'dostum' gibi hitaplar KULLANMA. "
            "Kodları uygun markdown blokları içinde, adım adım açıklamaları numaralandırılmış listeler halinde sun."
        )
    elif samimi_mode:
        persona = f"Senin adın {APP_STATE['bot_name']}. Karşındaki kullanıcı ({username}) ile samimi ve dostça konuş. 'kanka' kullanma."
    else:
        persona = f"Senin adın {APP_STATE['bot_name']}. Karşındaki kullanıcı ({username}) ile resmi ve yardımcı konuş."

    persona += f"\n\nDil kurali: SADECE {active_lang_name} ({active_lang_code.upper()}) dilinde yanit ver."
    persona += mode_instruction

    custom_personality = (user.get("custom_personality") if user else "") or ""
    if custom_personality:
        persona += f"\n\nKullanicinin ozel kisilik talebi: \"{custom_personality}\"."

    memory = memory_get(username, limit=20)
    messages = [{"role": "system", "content": persona}]
    for m in memory:
        messages.append({"role": m["role"], "content": m.get("content") or "[Bos mesaj]"})

    if image_data:
        image_url = image_data if "," in image_data else f"data:image/jpeg;base64,{image_data}"
        messages.append({
            "role": "user",
            "content": [
                {"type": "text", "text": user_message if user_message else "Bu fotograftaki nedir? Analiz et."},
                {"type": "image_url", "image_url": {"url": image_url}}
            ]
        })
        model_chain = ["qwen/qwen3.8-27b"]
    else:
        doc_context = f"\n\n===== BELGE ({document_name or 'belge'}) =====\n{document_text}\n=================================" if document_text else ""
        social_context = ""
        platform, url = detect_social_url(user_message)
        if platform and url:
            sdata = fetch_social_content(platform, url)
            if sdata:
                social_context = f"\n\n===== SOSYAL ({platform.upper()}) =====\n{sdata}\n==============================="
        search_context = ""
        if not social_context and should_search(user_message):
            sres = web_search(user_message)
            if sres:
                search_context = f"\n\n===== WEB SONUCLARI =====\n{sres}\n==========================="

        messages.append({"role": "user", "content": user_message + doc_context + social_context + search_context})
        model_chain = ["openai/gpt-oss-120b", "openai/gpt-oss-20b"]

    memory_add(username, "user", user_message if user_message else "[Fotograf]", None, active_lang_code)

    last_error = None
    for model_name in model_chain:
        try:
            completion = client.chat.completions.create(
                model=model_name, messages=messages, temperature=0.7, max_tokens=1500, timeout=30.0
            )
            reply = (completion.choices[0].message.content or "").strip()
            if reply:
                memory_add(username, "assistant", reply, None, active_lang_code)
                return reply
        except Exception as e:
            last_error = str(e)
            if "401" in last_error.lower() or "invalid_api_key" in last_error.lower():
                return "API anahtari gecersiz. GROQ_API_KEY'i kontrol et."
            continue

    return f"Modeller yanit vermedi. {last_error or 'Bilinmeyen hata'}"


@app.route("/")
def dashboard():
    current_user = session.get('username', "")
    is_admin = is_admin_user(current_user) if current_user else False
    music_list = db_get_music_list()
    user_avatar = "tr"
    user_language = "tr"
    user_bot_mode = "normal"
    user_custom_personality = ""
    if current_user:
        u = get_user_from_db(current_user)
        if u:
            user_avatar = u.get("avatar", "")
            user_language = u.get("language", "tr")
            user_bot_mode = u.get("bot_mode", "normal")
            user_custom_personality = u.get("custom_personality", "")
    return render_template_string(
        HTML_TEMPLATE, app_state=APP_STATE, current_user=current_user,
        is_admin=is_admin, logged_in='username' in session,
        music_list=music_list, user_avatar=user_avatar,
        supported_languages=SUPPORTED_LANGUAGES, user_language=user_language,
        bot_modes=BOT_MODES, user_bot_mode=user_bot_mode,
        user_custom_personality=user_custom_personality
    )


@app.route("/uploads/music/<path:filename>")
def serve_music(filename):
    return send_from_directory(MUSIC_DIR, filename)


@app.route("/admin/bg/<path:filename>")
def serve_bg(filename):
    if ".." in filename or "/" in filename or "\\" in filename:
        return "Geçersiz", 400
    filepath = os.path.join(BG_DIR, filename)
    if not os.path.exists(filepath):
        return "Dosya yok", 404
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


@app.route("/upload-document", methods=["POST"])
@rate_limit(max_calls=15, window_seconds=60)
def upload_document():
    if 'username' not in session:
        return jsonify({"status": "error", "message": "Giriş yapmadın."}), 403
    if 'file' not in request.files:
        return jsonify({"status": "error", "message": "Dosya yok."}), 400
    file = request.files['file']
    if not file.filename:
        return jsonify({"status": "error", "message": "Dosya seçilmedi."}), 400
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_DOC_EXTENSIONS:
        return jsonify({"status": "error", "message": "Desteklenmeyen format."}), 400

    tmp_name = f"doc_{uuid.uuid4().hex[:12]}{ext}"
    tmp_path = os.path.join(UPLOAD_DIR, tmp_name)
    file.save(tmp_path)
    text, err = extract_document_text(tmp_path, ext)
    try:
        os.remove(tmp_path)
    except Exception:
        pass
    if err:
        return jsonify({"status": "error", "message": err}), 400
    return jsonify({"status": "success", "document_text": text, "document_name": file.filename})


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
    return jsonify({"status": "success", "enabled": bool(db_get("maintenance_mode", False))})


@app.route("/maintenance/toggle", methods=["POST"])
def maintenance_toggle():
    if 'username' not in session or not is_admin_user(session['username']):
        return jsonify({"status": "error"}), 403
    enabled = bool((request.get_json(silent=True) or {}).get("enabled", False))
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
        username = session.get("username") or data.get("username", "Bilinmeyen")
        reply = get_ai_response(
            username,
            data.get("message", "") or "",
            data.get("image"),
            data.get("document_text"),
            data.get("document_name")
        )
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
        except Exception:
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
    username = (data.get("username") or "").strip()
    email = (data.get("email") or "").strip()
    password = (data.get("password") or "").strip()
    language = (data.get("language") or "tr").strip()
    if language not in SUPPORTED_LANGUAGES:
        language = "tr"
    if not username or not password:
        return jsonify({"status": "error", "message": "Kullanıcı adı ve şifre zorunludur."})

    existing = get_user_from_db(username)
    if action == "register":
        if existing:
            return jsonify({"status": "error", "message": "Bu kullanıcı adı zaten alınmış."})
        if len(password) < 3:
            return jsonify({"status": "error", "message": "Şifre en az 3 karakter olmalı."})
        if not create_user(username, email, password, is_admin=False, language=language):
            return jsonify({"status": "error", "message": "Kayıt oluşturulamadı."})
        session.permanent = True
        session['username'] = username
        return jsonify({"status": "success", "message": "Kayıt başarılı!", "username": username, "is_admin": False, "language": language})

    if action == "login":
        if existing and check_password_hash(existing["password"], password):
            session.permanent = True
            session['username'] = existing["username"]
            return jsonify({
                "status": "success", "message": "Giriş başarılı!",
                "username": existing["username"], "is_admin": existing["is_admin"],
                "language": existing.get("language", "tr")
            })
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


@app.route("/update-mode", methods=["POST"])
def update_mode():
    if 'username' not in session:
        return jsonify({"status": "error", "message": "Giriş yapmadın."}), 403
    mode = (request.get_json(silent=True) or {}).get("mode", "normal")
    if mode not in BOT_MODES:
        return jsonify({"status": "error", "message": "Geçersiz mod."}), 400
    update_user_bot_mode(session['username'], mode)
    return jsonify({"status": "success", "mode": mode, "label": BOT_MODES[mode]["label"]})


@app.route("/update-personality", methods=["POST"])
def update_personality():
    if 'username' not in session:
        return jsonify({"status": "error", "message": "Giriş yapmadın."}), 403
    text = ((request.get_json(silent=True) or {}).get("personality") or "").strip()[:500]
    update_user_custom_personality(session['username'], text)
    return jsonify({"status": "success", "personality": text})


@app.route("/chats", methods=["GET"])
def get_chats():
    if 'username' not in session:
        return jsonify({"status": "error", "chats": []})
    return jsonify({"status": "success", "chats": db_get_user_chats(session['username'])})


@app.route("/chats/save", methods=["POST"])
def save_chat():
    if 'username' not in session:
        return jsonify({"status": "error"}), 403
    data = request.get_json(silent=True) or {}
    db_save_chat(session['username'], data.get("title", "Sohbet"), json.dumps(data.get("messages", []), ensure_ascii=False))
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
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in [".png", ".jpg", ".jpeg", ".webp", ".gif"]:
        return jsonify({"status": "error", "message": "Sadece PNG/JPG/WEBP/GIF."}), 400
    unique_name = f"av_{uuid.uuid4().hex[:12]}{ext}"
    file.save(os.path.join(AVATAR_DIR, unique_name))
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
    return jsonify({
        "status": "success",
        "users": [{"id": r[0], "username": r[1], "email": r[2], "is_admin": bool(r[3]), "language": r[4], "created_at": r[5]} for r in rows]
    })


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
        if key in data:
            theme[key] = data[key]
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
    file = request.files.get('file')
    if not file or not file.filename:
        return jsonify({"status": "error"}), 400
    ext = os.path.splitext(file.filename)[1].lower()
    is_video = ext in [".mp4", ".webm", ".ogg", ".mov"]
    unique_name = f"bg_{uuid.uuid4().hex[:12]}{ext}"
    file.save(os.path.join(BG_DIR, unique_name))
    APP_STATE["theme"]["bg_media"] = unique_name
    APP_STATE["theme"]["bg_media_type"] = "video" if is_video else "image"
    save_theme_to_db(APP_STATE["theme"])
    return jsonify({"status": "success", "bg_media": unique_name, "bg_media_type": APP_STATE["theme"]["bg_media_type"]})


@app.route("/admin/clear-background", methods=["POST"])
def admin_clear_background():
    if 'username' not in session or not is_admin_user(session['username']):
        return jsonify({"status": "error"}), 403
    APP_STATE["theme"]["bg_media"] = ""
    APP_STATE["theme"]["bg_media_type"] = ""
    save_theme_to_db(APP_STATE["theme"])
    return jsonify({"status": "success"})


@app.route("/admin/upload-music", methods=["POST"])
def admin_upload_music():
    if 'username' not in session or not is_admin_user(session['username']):
        return jsonify({"status": "error"}), 403
    file = request.files.get('file')
    if not file or not file.filename:
        return jsonify({"status": "error"}), 400
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in [".mp3", ".wav", ".ogg", ".m4a", ".aac", ".flac"]:
        return jsonify({"status": "error", "message": "Desteklenmeyen format."}), 400
    if len(db_get_music_list()) >= 3:
        return jsonify({"status": "error", "message": "Maksimum 3 müzik."}), 400
    unique_name = f"music_{uuid.uuid4().hex[:12]}{ext}"
    file.save(os.path.join(MUSIC_DIR, unique_name))
    conn = sqlite3.connect(DB_FILE)
    conn.execute("INSERT INTO music (filename, original_name) VALUES (?, ?)", (unique_name, file.filename))
    conn.commit()
    conn.close()
    return jsonify({"status": "success", "music": db_get_music_list()})


@app.route("/admin/delete-music/<int:music_id>", methods=["POST"])
def admin_delete_music(music_id):
    if 'username' not in session or not is_admin_user(session['username']):
        return jsonify({"status": "error"}), 403
    conn = sqlite3.connect(DB_FILE)
    row = conn.execute("SELECT filename FROM music WHERE id = ?", (music_id,)).fetchone()
    if row:
        fp = os.path.join(MUSIC_DIR, row[0])
        if os.path.exists(fp):
            try:
                os.remove(fp)
            except Exception:
                pass
        conn.execute("DELETE FROM music WHERE id = ?", (music_id,))
        conn.commit()
    conn.close()
    return jsonify({"status": "success", "music": db_get_music_list()})


@app.route("/music-list", methods=["GET"])
def music_list_api():
    return jsonify({"status": "success", "music": db_get_music_list()})


HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="tr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no, viewport-fit=cover">
    <title>Crsz Bot | Liquid Glass AI Studio</title>
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
        }
        * { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Inter', sans-serif; }
        html, body { background-color: var(--bg-deep); color: var(--text-main); height: 100%; width: 100%; overflow: hidden; }
        .app-layout { display: flex; height: 100dvh; width: 100vw; padding: 12px; gap: 12px; }
        .sidebar { width: 260px; background: var(--lg-tint); border: 1px solid var(--lg-border-soft); border-radius: 22px; padding: 14px; display: flex; flex-direction: column; gap: 10px; backdrop-filter: blur(var(--lg-blur)); }
        .main-workspace { flex: 1; background: var(--lg-tint); border: 1px solid var(--lg-border-soft); border-radius: 22px; display: flex; flex-direction: column; overflow: hidden; backdrop-filter: blur(var(--lg-blur)); }
        header { padding: 12px 18px; border-bottom: 1px solid var(--lg-border-soft); display: flex; justify-content: space-between; align-items: center; }
        .chat-container { flex: 1; padding: 16px; overflow-y: auto; display: flex; flex-direction: column; gap: 12px; }
        .msg-bubble { max-width: 85%; padding: 12px 16px; border-radius: 16px; font-size: 13px; line-height: 1.55; word-break: break-word; }
        .msg-bubble.user { background: rgba(255,255,255,0.06); align-self: flex-start; }
        .msg-bubble.bot { background: rgba(20,25,40,0.65); border: 1px solid rgba(59,130,246,0.3); align-self: flex-end; width: 100%; max-width: 90%; }
        .control-panel { padding: 12px 16px; border-top: 1px solid var(--lg-border-soft); display: flex; gap: 10px; align-items: center; }
        .input-wrapper { flex: 1; background: rgba(255,255,255,0.05); border: 1px solid var(--lg-border-soft); border-radius: 14px; padding: 0 12px; display: flex; align-items: center; }
        .input-wrapper input { width: 100%; background: transparent; border: none; color: #fff; padding: 10px 6px; outline: none; }
        .send-btn { background: var(--primary-gradient); color: #fff; border: none; padding: 10px 18px; border-radius: 14px; font-weight: 600; cursor: pointer; }
        .footer-btn, .new-chat-btn { width: 100%; background: rgba(255,255,255,0.05); border: 1px solid var(--lg-border-soft); color: #fff; padding: 9px; border-radius: 12px; cursor: pointer; font-size: 12px; text-align: left; }
        .chat-history-list { flex: 1; overflow-y: auto; display: flex; flex-direction: column; gap: 6px; }
        .history-item { padding: 8px 10px; border-radius: 10px; font-size: 12px; color: var(--text-muted); cursor: pointer; }
        .history-item.active { background: rgba(59,130,246,0.2); color: #fff; }
        .sidebar-footer { display: flex; flex-direction: column; gap: 6px; border-top: 1px solid var(--lg-border-soft); padding-top: 8px; }
        #authOverlay { position: fixed; inset: 0; background: rgba(7,7,10,0.9); display: flex; align-items: center; justify-content: center; z-index: 2000; }
        #authOverlay.hidden { display: none; }
        .auth-card { width: 100%; max-width: 380px; background: rgba(20,25,40,0.85); border: 1px solid var(--lg-border-soft); border-radius: 20px; padding: 24px; }
        .auth-input, .lang-select { width: 100%; background: rgba(255,255,255,0.06); border: 1px solid var(--lg-border-soft); border-radius: 10px; padding: 10px 12px; color: #fff; margin-bottom: 10px; }
        .auth-btn { width: 100%; background: var(--primary-gradient); color: #fff; border: none; padding: 11px; border-radius: 10px; font-weight: 600; cursor: pointer; }
        .modal-overlay { display: none; position: fixed; inset: 0; background: rgba(0,0,0,0.7); z-index: 1500; align-items: center; justify-content: center; padding: 16px; }
        .modal-overlay.active { display: flex; }
        .modal-card { width: 100%; max-width: 540px; max-height: 88vh; overflow-y: auto; background: #0f172a; border: 1px solid var(--lg-border-soft); border-radius: 20px; padding: 20px; }
        .tab-buttons { display: flex; gap: 6px; margin-bottom: 12px; }
        .tab-btn { flex: 1; padding: 8px; border-radius: 8px; background: rgba(255,255,255,0.05); color: var(--text-muted); text-align: center; cursor: pointer; font-size: 12px; }
        .tab-btn.active { background: rgba(59,130,246,0.25); color: #fff; }
        .toast { position: fixed; top: 18px; left: 50%; transform: translateX(-50%); background: #1e293b; color: #fff; padding: 10px 18px; border-radius: 12px; z-index: 9999; font-size: 13px; }
        pre { background: rgba(0,0,0,0.5); padding: 10px; border-radius: 10px; overflow-x: auto; margin: 8px 0; }
        code { color: #38BDF8; font-family: monospace; }
    </style>
</head>
<body>
    <div id="authOverlay" class="{% if logged_in %}hidden{% endif %}">
        <div class="auth-card">
            <h2 style="margin-bottom:14px;">{{ app_state.bot_name }}</h2>
            <input type="text" id="authUsername" class="auth-input" placeholder="Kullanıcı Adı">
            <input type="password" id="authPassword" class="auth-input" placeholder="Şifre">
            <button class="auth-btn" onclick="handleAuth()">Giriş Yap</button>
        </div>
    </div>

    <div class="modal-overlay" id="profileModal">
        <div class="modal-card">
            <h3>Profil & Bot Ayarları</h3>
            <label style="font-size:11px;color:#94A3B8;">Bot Adı</label>
            <input type="text" id="modalBotName" class="auth-input" value="{{ app_state.bot_name }}">
            <label style="font-size:11px;color:#94A3B8;">Dil</label>
            <select id="modalLanguage" class="lang-select">
                {% for code, name in supported_languages.items() %}
                <option value="{{ code }}" {% if code == user_language %}selected{% endif %}>{{ name }}</option>
                {% endfor %}
            </select>
            <label style="font-size:11px;color:#94A3B8;">Mod</label>
            <select id="modalBotModeSelect" class="lang-select">
                {% for key, m in bot_modes.items() %}
                <option value="{{ key }}" {% if key == user_bot_mode %}selected{% endif %}>{{ m.label }}</option>
                {% endfor %}
            </select>
            <textarea id="modalCustomPersonality" class="auth-input" rows="2" placeholder="Özel kişilik...">{{ user_custom_personality }}</textarea>
            <div style="display:flex;gap:8px;margin-top:8px;">
                <button class="auth-btn" onclick="saveProfile()">Kaydet</button>
                <button class="auth-btn" style="background:#334155;" onclick="closeModal('profileModal')">Kapat</button>
            </div>
            <button class="auth-btn" style="background:#7f1d1d;margin-top:10px;" onclick="logout()">Çıkış Yap</button>
        </div>
    </div>

    <div class="app-layout">
        <div class="sidebar">
            <div style="font-weight:700;font-size:14px;">{{ app_state.bot_name }}</div>
            <button class="new-chat-btn" onclick="startNewChat()">+ Yeni Sohbet</button>
            <div class="chat-history-list" id="chatHistoryList"></div>
            <div class="sidebar-footer">
                <button class="footer-btn" onclick="openModal('profileModal')">Profil & Ayarlar</button>
            </div>
        </div>
        <div class="main-workspace">
            <header>
                <h2>AI Stüdyosu</h2>
                <span style="font-size:12px;color:#38BDF8;">{{ current_user or 'Misafir' }}</span>
            </header>
            <div class="chat-container" id="chatBox"></div>
            <div id="imagePreviewContainer" style="display:none;padding:0 16px;font-size:12px;color:#38BDF8;">Fotoğraf eklendi <span onclick="removeImage()" style="cursor:pointer;">×</span></div>
            <div id="docPreviewContainer" style="display:none;padding:0 16px;font-size:12px;color:#34D399;"><span id="docPreviewName"></span> <span onclick="removeDocument()" style="cursor:pointer;">×</span></div>
            <div class="control-panel">
                <input type="file" id="imageInput" accept="image/*" style="display:none;" onchange="handleImageSelect(event)">
                <button class="footer-btn" style="width:auto;padding:8px 10px;" onclick="document.getElementById('imageInput').click()">Görsel</button>
                <input type="file" id="docInput" accept=".txt,.md,.csv,.log,.pdf" style="display:none;" onchange="handleDocumentSelect(event)">
                <button class="footer-btn" style="width:auto;padding:8px 10px;" onclick="document.getElementById('docInput').click()">Belge</button>
                <div class="input-wrapper">
                    <input type="text" id="message" placeholder="Mesaj yaz..." onkeydown="if(event.key==='Enter') sendMessage()">
                </div>
                <button class="send-btn" onclick="sendMessage()">Gönder</button>
            </div>
        </div>
    </div>

    <script>
        let chats = [{ title: "Varsayılan Sohbet", messages: [] }];
        let activeChatIndex = 0;
        let selectedBase64Image = null;
        let selectedDocumentText = null;
        let selectedDocumentName = null;
        let isAdmin = {% if is_admin %}true{% else %}false{% endif %};
        let currentUser = "{{ current_user }}";
        let loggedIn = {% if logged_in %}true{% else %}false{% endif %};
        let isInitialLoad = true;
        let animatingMessageIndex = -1;

        function showToast(msg) {
            const t = document.createElement('div');
            t.className = 'toast';
            t.innerText = msg;
            document.body.appendChild(t);
            setTimeout(() => t.remove(), 2500);
        }

        function escapeHtml(s) {
            return String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
        }

        function safeMarkdownParse(text) {
            if (typeof marked !== 'undefined' && marked.parse) {
                try { return marked.parse(String(text || '')); } catch (e) {}
            }
            return escapeHtml(text).replace(/\n/g, '<br>');
        }

        function openModal(id) { document.getElementById(id).classList.add('active'); }
        function closeModal(id) { document.getElementById(id).classList.remove('active'); }

        async function handleAuth() {
            const username = document.getElementById('authUsername').value.trim();
            const password = document.getElementById('authPassword').value.trim();
            const res = await fetch('/auth', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ action: 'login', username, password })
            });
            const d = await res.json();
            if (d.status === 'success') window.location.reload();
            else showToast(d.message || 'Giriş başarısız');
        }

        async function logout() {
            await fetch('/logout', { method: 'POST' });
            window.location.reload();
        }

        async function saveProfile() {
            await fetch('/update-profile', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ bot_name: document.getElementById('modalBotName').value, language: document.getElementById('modalLanguage').value }) });
            await fetch('/update-mode', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ mode: document.getElementById('modalBotModeSelect').value }) });
            await fetch('/update-personality', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ personality: document.getElementById('modalCustomPersonality').value }) });
            showToast('Kaydedildi');
            closeModal('profileModal');
        }

        function handleImageSelect(e) {
            const f = e.target.files[0];
            if (!f) return;
            const r = new FileReader();
            r.onload = ev => { selectedBase64Image = ev.target.result; document.getElementById('imagePreviewContainer').style.display = 'block'; };
            r.readAsDataURL(f);
        }
        function removeImage() { selectedBase64Image = null; document.getElementById('imagePreviewContainer').style.display = 'none'; }

        async function handleDocumentSelect(e) {
            const f = e.target.files[0];
            if (!f) return;
            const fd = new FormData();
            fd.append('file', f);
            const res = await fetch('/upload-document', { method: 'POST', body: fd });
            const d = await res.json();
            if (d.status === 'success') {
                selectedDocumentText = d.document_text;
                selectedDocumentName = d.document_name;
                document.getElementById('docPreviewName').innerText = d.document_name;
                document.getElementById('docPreviewContainer').style.display = 'block';
            } else showToast(d.message || 'Belge hatası');
        }
        function removeDocument() { selectedDocumentText = null; selectedDocumentName = null; document.getElementById('docPreviewContainer').style.display = 'none'; }

        function renderChatHistory() {
            const el = document.getElementById('chatHistoryList');
            el.innerHTML = chats.map((c, i) => `<div class="history-item ${i === activeChatIndex ? 'active' : ''}" onclick="switchChat(${i})">${escapeHtml(c.title)}</div>`).join('');
        }

        function renderActiveChat() {
            const box = document.getElementById('chatBox');
            const msgs = (chats[activeChatIndex] && chats[activeChatIndex].messages) || [];
            box.innerHTML = msgs.map(m => `<div class="msg-bubble ${m.sender}"><b>${escapeHtml(m.name)}</b>${m.content}</div>`).join('');
            box.scrollTop = box.scrollHeight;
        }

        function switchChat(i) { activeChatIndex = i; renderChatHistory(); renderActiveChat(); }
        function startNewChat() { chats.push({ title: 'Yeni Sohbet ' + (chats.length + 1), messages: [] }); activeChatIndex = chats.length - 1; renderChatHistory(); renderActiveChat(); }

        async function saveChatToServer() {
            if (!loggedIn || !chats[activeChatIndex]) return;
            await fetch('/chats/save', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(chats[activeChatIndex]) });
        }

        async function sendMessage() {
            const inp = document.getElementById('message');
            const msg = inp.value.trim();
            if (!msg && !selectedBase64Image) return;
            const msgs = chats[activeChatIndex].messages;
            msgs.push({ sender: 'user', name: currentUser || 'Sen', content: escapeHtml(msg) });
            inp.value = '';
            const img = selectedBase64Image, dt = selectedDocumentText, dn = selectedDocumentName;
            removeImage(); removeDocument();
            msgs.push({ sender: 'bot', name: 'Crsz Bot', content: 'Yanıt hazırlanıyor...' });
            const botMsg = msgs[msgs.length - 1];
            renderActiveChat();

            try {
                const res = await fetch('/chat', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ username: currentUser, message: msg, image: img, document_text: dt, document_name: dn })
                });
                const d = await res.json();
                botMsg.content = d.media_type === 'image' && d.media_url
                    ? `${escapeHtml(d.reply)}<br><img src="${d.media_url}" style="max-width:100%;border-radius:10px;margin-top:6px;">`
                    : safeMarkdownParse(d.reply || 'Boş yanıt');
            } catch (e) {
                botMsg.content = 'Hata: ' + escapeHtml(e.message);
            }
            renderActiveChat();
            saveChatToServer();
        }

        (async function init() {
            if (loggedIn) {
                const r = await fetch('/chats');
                const d = await r.json();
                if (d.status === 'success' && d.chats.length) { chats = d.chats; activeChatIndex = 0; }
            }
            renderChatHistory();
            renderActiveChat();
        })();
    </script>
</body>
</html>
"""

TL = threading.local()
MAX_OUT = int(os.getenv("MAX_OUT_TOKENS", "32000"))
MAX_CONT = int(os.getenv("MAX_CONTINUATIONS", "6"))
FILE_THRESHOLD = int(os.getenv("CODE_FILE_THRESHOLD", "300"))

CODE_RULES = (
    "\n\nKOD YAZMA KURALLARI: Kod yazarken satir veya uzunluk siniri YOKTUR. Istenen kodu EKSIKSIZ ve calisir "
    "sekilde yaz; 'geri kalani ayni', '...', 'buraya ekle' gibi kisaltma veya yer tutucu KULLANMA. "
    "Kodu her zaman dil etiketli tek bir ``` blogu icinde ver (ornek: ```python)."
)

EXT = {
    "python": "py", "py": "py", "javascript": "js", "js": "js", "html": "html",
    "css": "css", "json": "json", "sql": "sql", "lua": "lua", "bash": "sh"
}

STOP = set("""
bunu bunun şunu için nasıl nedir neden yapabilir yapar misin mısın musun bana sana lütfen olarak gibi daha çok kadar
ama fakat veya ile olan olur oldu değil var yok evet hayır tamam merhaba selam teşekkürler sonra şimdi biraz bile
""".split())

FENCE = re.compile(r"```([\w+#\-.]*)[^\n]*\n(.*?)```", re.S)


def install_update(g):
    app_ref = g["app"]
    db_path = g["DB_FILE"]
    cli = g["client"]
    admin_fn = g["is_admin_user"]
    rl_fn = g["rate_limit"]

    def db():
        return sqlite3.connect(db_path)

    cn = db()
    cn.execute("CREATE TABLE IF NOT EXISTS usage_log (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT, day TEXT, ts TEXT, text TEXT)")
    cn.execute("CREATE TABLE IF NOT EXISTS bans (id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT, value TEXT, reason TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP)")
    cn.execute("CREATE TABLE IF NOT EXISTS user_quota (username TEXT PRIMARY KEY, daily_limit INTEGER)")
    cn.execute("CREATE TABLE IF NOT EXISTS announcements (id INTEGER PRIMARY KEY AUTOINCREMENT, text TEXT, created_by TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP, active INTEGER DEFAULT 1)")
    cn.commit()
    cn.close()

    def cur_user():
        return session.get("username") or ""

    def is_banned(kind, value):
        if not value:
            return False
        c = db()
        r = c.execute("SELECT 1 FROM bans WHERE kind=? AND LOWER(value)=LOWER(?)", (kind, value)).fetchone()
        c.close()
        return r is not None

    def today_str():
        return datetime.now().strftime("%Y-%m-%d")

    @app_ref.before_request
    def plus_guard():
        user = cur_user()
        admin = bool(user and admin_fn(user))
        ip = request.remote_addr or "unknown"
        if not admin and is_banned("ip", ip):
            return jsonify({"status": "error", "message": "IP adresin engellendi."}), 403
        if user and not admin and is_banned("user", user):
            return jsonify({"status": "error", "message": "Hesabın engellendi."}), 403

        if request.path in ("/chat", "/chat-stream") and request.method == "POST":
            if not user:
                return jsonify({"status": "error", "message": "Giriş yapmalısın."}), 403
            d = request.get_json(silent=True) or {}
            now = datetime.now()
            c = db()
            c.execute(
                "INSERT INTO usage_log (username, day, ts, text) VALUES (?,?,?,?)",
                (user, now.strftime("%Y-%m-%d"), now.strftime("%Y-%m-%d %H:%M:%S"), (d.get("message") or "")[:300])
            )
            c.commit()
            c.close()
        return None

    def split_long_code(reply):
        if reply.count("```") % 2 == 1:
            reply += "\n```"

        def repl(m):
            lang = (m.group(1) or "").lower()
            code = m.group(2)
            lines = code.splitlines()
            if len(lines) < FILE_THRESHOLD:
                return m.group(0)
            fname = f"kod_{uuid.uuid4().hex[:10]}.{EXT.get(lang, 'txt')}"
            with open(os.path.join(FILES_DIR, fname), "w", encoding="utf-8") as f:
                f.write(code.rstrip("\n") + "\n")
            preview = "\n".join(lines[:10])
            return f"**{len(lines)} satırlık kod dosya olarak hazırlandı:**\n\n```{lang}\n{preview}\n```\n\n[{fname} indir](/ai-files/{fname})"

        return FENCE.sub(repl, reply)

    orig_get = g["get_ai_response"]

    def wrapped_get(username, user_message, *a, **kw):
        res = orig_get(username, user_message, *a, **kw)
        if isinstance(res, str) and not res.lstrip().startswith("{"):
            return split_long_code(res)
        return res

    g["get_ai_response"] = wrapped_get

    @app_ref.route("/ai-files/<path:name>")
    def plus_ai_file(name):
        if not cur_user():
            return "Giriş gerekli", 403
        if not re.fullmatch(r"[\w.\-]+", name):
            return "Geçersiz", 400
        return send_from_directory(FILES_DIR, name, as_attachment=True)

    @app_ref.route("/chat-stream", methods=["POST"])
    @rl_fn(max_calls=30, window_seconds=60)
    def chat_stream():
        data = request.get_json(silent=True) or {}
        user = cur_user()
        q = queue.Queue()

        def worker():
            try:
                out = g["get_ai_response"](
                    user, data.get("message", "") or "", data.get("image"),
                    data.get("document_text"), data.get("document_name")
                )
                q.put(("f", out))
            except Exception as e:
                q.put(("e", str(e)))

        threading.Thread(target=worker, daemon=True).start()

        def stream_gen():
            while True:
                try:
                    kind, val = q.get(timeout=15)
                except queue.Empty:
                    yield ": ping\n\n"
                    continue
                if kind == "e":
                    yield "data: " + json.dumps({"t": "e", "m": val}, ensure_ascii=False) + "\n\n"
                    return
                ev = {"t": "f", "reply": val}
                try:
                    p = json.loads(val)
                    if isinstance(p, dict) and p.get("media_type"):
                        ev = {"t": "f", "reply": p.get("text", ""), "media_type": p.get("media_type"), "media_url": p.get("media_url")}
                except Exception:
                    pass
                yield "data: " + json.dumps(ev, ensure_ascii=False) + "\n\n"
                return

        return Response(stream_with_context(stream_gen()), mimetype="text/event-stream")


install_update(globals())

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)

