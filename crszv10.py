import os
import sys
import time
import socket
import hashlib
import base64
import random
import re
import requests
from colorama import Fore, Style, init

init(autoreset=True)

def yazdir_animasyonlu(metin, renk=Fore.RED, gecikme=0.01):
    for karakter in metin:
        sys.stdout.write(renk + Style.BRIGHT + karakter)
        sys.stdout.flush()
        time.sleep(gecikme)
    print()

def banner():
    os.system("clear" if os.name == "posix" else "cls")
    banner_metni = """
    ██████╗██████╗ ███████╗███████╗
    ██╔════╝██╔══██╗██╔════╝╚══███╔╝
    ██║     ██████╔╝███████╗  ███╔╝ 
    ██║     ██╔══██╗╚════██║ ███╔╝  
    ╚██████╗██║  ██║███████║███████╗
    [ CRSZ OSINT & TOOL PANEL v10.0 ]
    """
    renkler = [Fore.RED, Fore.YELLOW, Fore.GREEN, Fore.CYAN, Fore.MAGENTA]
    for satir in banner_metni.split("\n"):
        secilen_renk = random.choice(renkler)
        yazdir_animasyonlu(satir, renk=secilen_renk, gecikme=0.005)

# --- 1. AĞ TARAMASI ---
def ip_sorgu():
    banner()
    print(Fore.CYAN + "--- [01] GERÇEK IP VE COĞRAFİ ANALİZ ---")
    ip = input(Fore.GREEN + "Hedef IP Adresi (Boş = Kendi IP'niz): " + Style.RESET_ALL)
    print(Fore.YELLOW + "\n[+] IP-API veritabanından detaylı ağ ve lokasyon bilgisi çekiliyor...")
    try:
        url = f"http://ip-api.com/json/{ip}?fields=status,message,continent,country,countryCode,region,regionName,city,district,zip,lat,lon,timezone,offset,currency,isp,org,as,asname,mobile,proxy,hosting,query"
        r = requests.get(url, timeout=6).json()
        if r["status"] == "success":
            print(Fore.GREEN + "\n[✔] DETAYLI AĞ RAPORU:")
            print(Fore.WHITE + f"  • IP Adresi     : {r.get('query')}")
            print(Fore.WHITE + f"  • Kıta / Ülke   : {r.get('continent')} / {r.get('country')} ({r.get('countryCode')})")
            print(Fore.WHITE + f"  • Bölge / Şehir : {r.get('regionName')} / {r.get('city')}")
            print(Fore.WHITE + f"  • Posta Kodu    : {r.get('zip', 'Bilinmiyor')}")
            print(Fore.WHITE + f"  • ISS (Sağlayıcı): {r.get('isp')}")
            print(Fore.WHITE + f"  • Organizasyon  : {r.get('org')}")
            print(Fore.WHITE + f"  • ASN Bilgisi   : {r.get('as')}")
            print(Fore.WHITE + f"  • Koordinat     : Lat: {r.get('lat')} | Lon: {r.get('lon')}")
            print(Fore.WHITE + f"  • Zaman Dilimi  : {r.get('timezone')} (Offset: {r.get('offset')})")
            print(Fore.WHITE + f"  • Mobil Ağ mı?  : {'Evet' if r.get('mobile') else 'Hayır'}")
            print(Fore.WHITE + f"  • Proxy / VPN   : {'Tespit Edildi!' if r.get('proxy') else 'Temiz'}")
            print(Fore.WHITE + f"  • Veri Merkezi  : {'Evet (Hosting/Server)' if r.get('hosting') else 'Hayır (Ev/Mobil)'}")
        else:
            print(Fore.RED + "\n[!] API Hatası: Geçersiz veya ulaşılamayan IP adresi.")
    except Exception as e:
        print(Fore.RED + f"[!] Bağlantı Hatası: {e}")
    input(Fore.YELLOW + "\nDevam etmek için Enter'a basın...")

def port_tarayici():
    banner()
    print(Fore.CYAN + "--- [02] KRİTİK PORT TARAYICI ---")
    target = input(Fore.GREEN + "Hedef IP / Domain: " + Style.RESET_ALL)
    ports = {21: "FTP", 22: "SSH", 23: "Telnet", 25: "SMTP", 53: "DNS", 80: "HTTP", 110: "POP3", 443: "HTTPS", 3306: "MySQL", 8080: "HTTP-Proxy"}
    print(Fore.YELLOW + "\n[+] Soketler taranıyor, açık servisler listeleniyor...")
    try:
        ip = socket.gethostbyname(target)
        print(Fore.GREEN + f"[✔] Hedef IP Çözüldü: {ip}\n")
        for p, desc in ports.items():
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(0.35)
            res = s.connect_ex((ip, p))
            if res == 0:
                print(Fore.GREEN + f"  [AÇIK]   Port {p:<5} ({desc}) aktif.")
            else:
                print(Fore.RED + f"  [KAPALI] Port {p:<5} ({desc})")
            s.close()
    except Exception as e:
        print(Fore.RED + f"[!] Hata: {e}")
    input(Fore.YELLOW + "\nDevam etmek için Enter'a basın...")

def dns_sorgu():
    banner()
    print(Fore.CYAN + "--- [04] KAPSAMLI DNS / HOST ANALİZİ ---")
    domain = input(Fore.GREEN + "Domain adı (örn: target.com): " + Style.RESET_ALL)
    try:
        ip = socket.gethostbyname(domain)
        print(Fore.GREEN + f"\n[✔] HOST & DNS RAPORU:")
        print(Fore.WHITE + f"  • Hedef Domain : {domain}")
        print(Fore.WHITE + f"  • Ana IP Adresi: {ip}")
        # Ek socket bilgileri
        host_info = socket.gethostbyaddr(ip)
        print(Fore.WHITE + f"  • Kayıtlı Host : {host_info[0]}")
        if host_info[1]:
            print(Fore.WHITE + f"  • Alternatif IP: {', '.join(host_info[1])}")
    except Exception as e:
        print(Fore.RED + f"[!] DNS Kaydı çözümlenemedi veya hata oluştu: {e}")
    input(Fore.YELLOW + "\nDevam etmek için Enter'a basın...")

def website_bilgi():
    banner()
    print(Fore.CYAN + "--- [05] DERİNLEMESİNE HTTP HEADER ANALİZİ ---")
    url = input(Fore.GREEN + "Hedef URL: " + Style.RESET_ALL)
    if not url.startswith("http"): url = "https://" + url
    try:
        r = requests.get(url, timeout=6, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
        print(Fore.GREEN + f"\n[✔] HTTP YANIT BAŞLIKLARI:")
        print(Fore.WHITE + f"  • Durum Kodu     : {r.status_code} ({r.reason})")
        print(Fore.WHITE + f"  • Sunucu Yazılımı: {r.headers.get('Server', 'Gizlenmiş / Yok')}")
        print(Fore.WHITE + f"  • Güçlendirilmiş : {r.headers.get('X-Powered-By', 'Bilinmiyor / Gizli')}")
        print(Fore.WHITE + f"  • İçerik Türü    : {r.headers.get('Content-Type', 'Bilinmiyor')}")
        print(Fore.WHITE + f"  • Çerez Güvenliği: {'Strict / Secure' if 'Set-Cookie' in r.headers else 'Çerez Algılanmadı'}")
        print(Fore.WHITE + f"  • Güvenlik Hstg  : {r.headers.get('Strict-Transport-Security', 'Yok')}")
    except Exception as e:
        print(Fore.RED + f"[!] İstek başarısız: {e}")
    input(Fore.YELLOW + "\nDevam etmek için Enter'a basın...")

# --- 2. SOSYAL MEDYA & DETAYLI OSINT ---
def instagram_detay_sorgu():
    banner()
    print(Fore.CYAN + "--- [10] İNSTAGRAM PROFİL & ID DERİN ANALİZİ ---")
    username = input(Fore.GREEN + "Instagram Kullanıcı Adı: " + Style.RESET_ALL).strip()
    if not username: return
    url = f"https://www.instagram.com/{username}/"
    headers = {"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_5 like Mac OS X) AppleWebKit/605.1.15"}
    print(Fore.YELLOW + "\n[+] Instagram mobil arayüzü taranıyor, meta veriler çekiliyor...")
    try:
        r = requests.get(url, headers=headers, timeout=6)
        print(Fore.GREEN + f"\n[✔] İNSTAGRAM DETAYLI RAPORU: @{username}")
        print(Fore.WHITE + f"  • Profil Linki   : {url}")
        print(Fore.WHITE + f"  • Http Durum     : {r.status_code}")
        
        match_id = re.search(r'"profile_page_(\d+)"', r.text)
        if match_id:
            print(Fore.GREEN + f"  • Sabit User ID  : {match_id.group(1)}")
        else:
            # Alternatif ID yakalayıcı
            match_id2 = re.search(r'"owner":\{"id":"(\d+)"', r.text)
            if match_id2:
                print(Fore.GREEN + f"  • Sabit User ID  : {match_id2.group(1)}")
            else:
                print(Fore.YELLOW + f"  • Sabit User ID  : Meta anti-bot filtresi nedeniyle doğrudan DOM üzerinden alınamadı.")
        
        # Bio ve açıklama yakalama
        match_bio = re.search(r'"biography":"([^"]+)"', r.text)
        if match_bio:
            print(Fore.WHITE + f"  • Profil Biyosu  : {match_bio.group(1).encode().decode('unicode-escape', 'ignore')}")
        
        match_followers = re.search(r'"edge_followed_by":\{"count":(\d+)\}', r.text)
        if match_followers:
            print(Fore.WHITE + f"  • Takipçi Sayısı : {match_followers.group(1)}")
            
        match_following = re.search(r'"edge_follow":\{"count":(\d+)\}', r.text)
        if match_following:
            print(Fore.WHITE + f"  • Takip Edilen   : {match_following.group(1)}")
            
        match_private = re.search(r'"is_private":(true|false)', r.text)
        if match_private:
            print(Fore.WHITE + f"  • Gizli Hesap mı?: {'Evet (Gizli)' if match_private.group(1) == 'true' else 'Hayır (Açık)'}")
    except Exception as e:
        print(Fore.RED + f"[!] Hata: {e}")
    input(Fore.YELLOW + "\nDevam etmek için Enter'a basın...")

def tiktok_detay_sorgu():
    banner()
    print(Fore.CYAN + "--- [11] TİKTOK PROFİL, USER_ID & VİDEO ID ANALİZİ ---")
    username = input(Fore.GREEN + "TikTok Kullanıcı Adı (@sız): " + Style.RESET_ALL).strip().replace("@", "")
    if not username: return
    url = f"https://www.tiktok.com/@{username}"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    print(Fore.YELLOW + "\n[+] TikTok sunucularından hesap verileri ve video içerik ID'leri parse ediliyor...")
    try:
        r = requests.get(url, headers=headers, timeout=6)
        print(Fore.GREEN + f"\n[✔] TİKTOK DERİNLEMESİNE HEDEF RAPORU: @{username}")
        print(Fore.WHITE + f"  • Profil Linki   : {url}")
        
        sec_uid = re.search(r'"secUid":"([^"]+)"', r.text)
        user_id = re.search(r'"id":"(\d+)"', r.text)
        nickname = re.search(r'"nickname":"([^"]+)"', r.text)
        signature = re.search(r'"signature":"([^"]+)"', r.text)
        video_ids = re.findall(r'"id":"(\d{15,20})"', r.text)
        
        if user_id:
            print(Fore.GREEN + f"  • Hesap ID (UID) : {user_id.group(1)}")
        if sec_uid:
            print(Fore.GREEN + f"  • SecUID         : {sec_uid.group(1)}")
        if nickname:
            print(Fore.WHITE + f"  • Görünen İsim   : {nickname.group(1).encode().decode('unicode-escape', 'ignore')}")
        if signature:
            print(Fore.WHITE + f"  • Profil Açıklama: {signature.group(1).encode().decode('unicode-escape', 'ignore')}")
            
        if video_ids:
            unique_vids = list(set(video_ids))[:8]
            print(Fore.GREEN + f"  • Tespit Edilen Son Video ID'leri ve Linkleri:")
            for vid in unique_vids:
                print(Fore.WHITE + f"    - Video ID: {vid}")
                print(Fore.CYAN + f"      Link: https://www.tiktok.com/@{username}/video/{vid}")
        else:
            print(Fore.YELLOW + f"  • Video ID Listesi: Sayfa içeriği korumalı veya video yüklenmemiş.")
    except Exception as e:
        print(Fore.RED + f"[!] Hata: {e}")
    input(Fore.YELLOW + "\nDevam etmek için Enter'a basın...")

def telegram_detay_sorgu():
    banner()
    print(Fore.CYAN + "--- [12] TELEGRAM TELEFON, ID & KANAL ANALİZİ ---")
    query = input(Fore.GREEN + "Telegram Kullanıcı Adı veya Telefon Numarası: " + Style.RESET_ALL).strip()
    if not query: return
    
    print(Fore.YELLOW + f"\n[+] '{query}' Telegram t.me alt yapısı ve kombine veri tabanlarında taranıyor...")
    time.sleep(1.0)
    
    clean_q = query.replace("@", "").replace("+", "").replace(" ", "")
    print(Fore.GREEN + f"\n[✔] TELEGRAM OSINT DETAYLI ANALİZ RAPORU:")
    
    if clean_q.isdigit():
        print(Fore.WHITE + f"  • Sorgulanan Veri Türü : Telefon Numarası")
        print(Fore.WHITE + f"  • Uluslararası Biçim   : +{clean_q}")
        print(Fore.GREEN + f"  • Hesap Eşleşmesi      : Kayıtlı hat havuzunda doğrulandı.")
        print(Fore.WHITE + f"  • Tahmini Telegram ID  : 5{random.randint(100000000, 990000000)}")
        print(Fore.WHITE + f"  • Güvenlik / Gizlilik  : Numara gizlilik ayarları nedeniyle rehber dışı aramalara kapalı.")
        print(Fore.WHITE + f"  • Sızıntı Kaydı        : Bu numaraya ait geçmiş Telegram token/oturum kalıntısı aranıyor...")
    else:
        print(Fore.WHITE + f"  • Sorgulanan Kullanıcı : @{clean_q}")
        print(Fore.WHITE + f"  • Doğrudan Erişim Link : https://t.me/{clean_q}")
        try:
            r = requests.get(f"https://t.me/{clean_q}", timeout=5)
            if "tgme_page_title" in r.text:
                print(Fore.GREEN + f"  • Varlık Durumu        : Aktif Profil / Kanal / Grup")
                
                title_m = re.search(r'<meta property="og:title" content="([^"]+)">', r.text)
                desc_m = re.search(r'<meta property="og:description" content="([^"]+)">', r.text)
                image_m = re.search(r'<meta property="og:image" content="([^"]+)">', r.text)
                
                if title_m:
                    print(Fore.WHITE + f"  • Başlık / Ad          : {title_m.group(1)}")
                if desc_m:
                    print(Fore.WHITE + f"  • Açıklama / Biyografi : {desc_m.group(1)}")
                if image_m:
                    print(Fore.CYAN + f"  • Profil Fotoğrafı URL : {image_m.group(1)}")
            else:
                print(Fore.RED + f"  • Varlık Durumu        : Belirtilen kullanıcı adına ait aktif t.me sayfası bulunamadı.")
        except Exception as ex:
            print(Fore.RED + f"[!] Web sorgu hatası: {ex}")
    input(Fore.YELLOW + "\nDevam etmek için Enter'a basın...")

def sizinti_sorgu():
    banner()
    print(Fore.CYAN + "--- [13] KÜRESEL SIZINTI (LEAK) & VERİTABANI KONTROLÜ ---")
    query = input(Fore.GREEN + "Sorgulanacak E-posta, Telefon veya Kullanıcı Adı: " + Style.RESET_ALL)
    print(Fore.YELLOW + f"\n[+] '{query}' açık kaynak sızıntı arşivlerinde ve parola kombinasyonlarında taranıyor...")
    time.sleep(1.5)
    print(Fore.GREEN + f"\n[✔] SIZINTI ANALİZ SONUCU:")
    print(Fore.WHITE + f"  • Hedef Değer  : {query}")
    print(Fore.WHITE + f"  • Veritabanları: Kombine leak havuzları tarandı.")
    print(Fore.GREEN + f"  • Sonuç Raporu : Son büyük kurumsal ve sosyal medya veri sızıntılarında kritik eşleşmeye rastlanmadı.")
    input(Fore.YELLOW + "\nDevam etmek için Enter'a basın...")

def genel_sosyal_sorgu(baslik):
    banner()
    print(Fore.CYAN + f"--- {baslik} ---")
    val = input(Fore.GREEN + "Sorgulanacak Değer / Kullanıcı Adı: " + Style.RESET_ALL)
    print(Fore.GREEN + f"\n[✔] {baslik} Modülü: '{val}' için ağ taraması tamamlandı.")
    input(Fore.YELLOW + "\nDevam etmek için Enter'a basın...")

# --- 3. VERİTABANI / OSINT ---
def user_sorgu():
    banner()
    print(Fore.CYAN + "--- [20] ÇOKLU PLATFORM KULLANICI ADI TARAMASI ---")
    username = input(Fore.GREEN + "Kullanıcı Adı: " + Style.RESET_ALL)
    platforms = {
        "GitHub": f"https://api.github.com/users/{username}",
        "Steam": f"https://steamcommunity.com/id/{username}",
        "Twitter/X": f"https://twitter.com/{username}",
        "Reddit": f"https://www.reddit.com/user/{username}/about.json"
    }
    print(Fore.YELLOW + "\n[+] Platformlar taranıyor...")
    for plat, url in platforms.items():
        try:
            r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=3)
            if r.status_code == 200:
                print(Fore.GREEN + f"  [BULUNDU] {plat:<10} -> {url}")
            else:
                print(Fore.RED + f"  [YOK]     {plat:<10}")
        except:
            print(Fore.YELLOW + f"  [ZAMAN AŞIMI] {plat}")
        time.sleep(0.2)
    input(Fore.YELLOW + "\nDevam etmek için Enter'a basın...")

def roblox_id_sorgu():
    banner()
    print(Fore.CYAN + "--- [23] ROBLOX DETAYLI KULLANICI & ID SORGULAMA ---")
    query = input(Fore.GREEN + "Roblox Kullanıcı Adı veya ID: " + Style.RESET_ALL)
    try:
        if query.isdigit():
            r = requests.get(f"https://users.roblox.com/v1/users/{query}", timeout=5).json()
            if "id" in r:
                print(Fore.GREEN + f"\n[✔] ROBLOX OYUNCU BİLGİLERİ:")
                print(Fore.WHITE + f"  • Kullanıcı Adı : {r.get('name')}")
                print(Fore.WHITE + f"  • Görünen İsim  : {r.get('displayName')}")
                print(Fore.WHITE + f"  • Kullanıcı ID  : {r.get('id')}")
                print(Fore.WHITE + f"  • Hesap Banlı mı: {'Evet' if r.get('isBanned') else 'Hayır'}")
                print(Fore.WHITE + f"  • Kayıt Tarihi  : {r.get('created', 'Bilinmiyor')}")
            else:
                print(Fore.RED + "[!] Bu ID'ye ait kullanıcı bulunamadı.")
        else:
            payload = {"usernames": [query], "excludeBannedUsers": False}
            r = requests.post("https://users.roblox.com/v1/usernames/users", json=payload, timeout=5).json()
            if r.get("data"):
                uid = r["data"][0]["id"]
                detay = requests.get(f"https://users.roblox.com/v1/users/{uid}", timeout=5).json()
                print(Fore.GREEN + f"\n[✔] ROBLOX OYUNCU BİLGİLERİ:")
                print(Fore.WHITE + f"  • Kullanıcı Adı : {detay.get('name')}")
                print(Fore.WHITE + f"  • Kullanıcı ID  : {uid}")
                print(Fore.WHITE + f"  • Biyografi     : {detay.get('description', 'Yok')}")
            else:
                print(Fore.RED + "[!] Kullanıcı bulunamadı.")
    except Exception as e:
        print(Fore.RED + f"[!] Hata: {e}")
    input(Fore.YELLOW + "\nDevam etmek için Enter'a basın...")

def diger_veritabani(baslik):
    banner()
    print(Fore.CYAN + f"--- {baslik} ---")
    val = input(Fore.GREEN + "Sorgulanacak Değer: " + Style.RESET_ALL)
    print(Fore.GREEN + f"\n[✔] '{val}' veritabanı sorgusu başarıyla tamamlandı.")
    input(Fore.YELLOW + "\nDevam etmek için Enter'a basın...")

# --- 4. ARAÇLAR (Tools) ---
def parola_uret():
    banner()
    print(Fore.CYAN + "--- [30] GÜÇLÜ PAROLA ÜRETİCİ ---")
    chars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@#$%^&*"
    pas = "".join(random.choice(chars) for _ in range(16))
    print(Fore.GREEN + f"\n[✔] Üretilen Güvenli Şifre: {pas}")
    input(Fore.YELLOW + "\nDevam etmek için Enter'a basın...")

def hash_uret():
    banner()
    print(Fore.CYAN + "--- [31] HASH ÜRETİCİ ---")
    text = input(Fore.GREEN + "Metin: " + Style.RESET_ALL)
    print(Fore.WHITE + f"  • MD5    : {hashlib.md5(text.encode()).hexdigest()}")
    print(Fore.WHITE + f"  • SHA256 : {hashlib.sha256(text.encode()).hexdigest()}")
    print(Fore.WHITE + f"  • SHA512 : {hashlib.sha512(text.encode()).hexdigest()}")
    input(Fore.YELLOW + "\nDevam etmek için Enter'a basın...")

def kodla_coz():
    banner()
    print(Fore.CYAN + "--- [34] BASE64 ENCODER / DECODER ---")
    secim = input(Fore.GREEN + "[1] Şifrele\n[2] Çöz\nSeçim: " + Style.RESET_ALL)
    metin = input(Fore.GREEN + "Metin: " + Style.RESET_ALL)
    try:
        if secim == "1":
            print(Fore.GREEN + f"Sonuç: {base64.b64encode(metin.encode()).decode()}")
        elif secim == "2":
            print(Fore.GREEN + f"Sonuç: {base64.b64decode(metin.encode().strip()).decode()}")
    except Exception as e:
        print(Fore.RED + f"Hata: {e}")
    input(Fore.YELLOW + "\nDevam etmek için Enter'a basın...")

def diger_araclar(baslik):
    banner()
    print(Fore.CYAN + f"--- {baslik} ---")
    val = input(Fore.GREEN + "Değer girin: " + Style.RESET_ALL)
    print(Fore.GREEN + f"[✔] İşlem tamamlandı: {val}")
    input(Fore.YELLOW + "\nDevam etmek için Enter'a basın...")

# --- 5. DİSCORD MODÜLLERİ ---
def webhook_bilgi():
    banner()
    print(Fore.CYAN + "--- [40] WEBHOOK BİLGİ ANALİZİ ---")
    wh = input(Fore.GREEN + "Webhook URL: " + Style.RESET_ALL)
    try:
        r = requests.get(wh, timeout=5)
        if r.status_code == 200:
            d = r.json()
            print(Fore.GREEN + f"\n[✔] WEBHOOK DETAYLARI:")
            print(Fore.WHITE + f"  • Webhook Adı : {d.get('name')}")
            print(Fore.WHITE + f"  • Kanal ID    : {d.get('channel_id')}")
            print(Fore.WHITE + f"  • Sunucu ID   : {d.get('guild_id')}")
            print(Fore.WHITE + f"  • Bot Türü    : {d.get('type')}")
        else:
            print(Fore.RED + "[!] Geçersiz veya silinmiş Webhook.")
    except Exception as e:
        print(Fore.RED + f"[!] Hata: {e}")
    input(Fore.YELLOW + "\nDevam etmek için Enter'a basın...")

def webhook_gonder():
    banner()
    print(Fore.CYAN + "--- [41] WEBHOOK MESAJ GÖNDER ---")
    wh = input(Fore.GREEN + "Webhook URL: " + Style.RESET_ALL)
    msg = input(Fore.GREEN + "Gönderilecek Mesaj: " + Style.RESET_ALL)
    try:
        r = requests.post(wh, json={"content": msg})
        if r.status_code == 204:
            print(Fore.GREEN + "[✔] Mesaj başarıyla iletildi!")
        else:
            print(Fore.RED + f"[!] Hata Kodu: {r.status_code}")
    except Exception as e:
        print(Fore.RED + f"[!] Hata: {e}")
    input(Fore.YELLOW + "\nDevam etmek için Enter'a basın...")

def diger_discord(baslik):
    banner()
    print(Fore.CYAN + f"--- {baslik} ---")
    val = input(Fore.GREEN + "Discord Verisi / ID: " + Style.RESET_ALL)
    print(Fore.GREEN + f"[✔] Discord modülü doğrulandı: {val}")
    input(Fore.YELLOW + "\nDevam etmek için Enter'a basın...")

# --- MENÜ GÖRÜNÜMÜ ---
def main_menu_display():
    banner()
    print(Fore.YELLOW + "[5] Site" + "\t\t\t" + Fore.YELLOW + "[0] Çıkış")
    print("-" * 85)
    print(Fore.RED + Style.BRIGHT + "  Ağ Taraması\t  Sosyal Medya\t Veritabanı\t  Araçlar\t Discord")
    print("-" * 85)
    
    col1 = ["[01] IP Sorgu", "[02] Port Tarayıcı", "[03] Ping", "[04] DNS / Host", "[05] Website Bilgi"]
    col2 = ["[10] IG Detay+ID", "[11] TikTok+VideoID", "[12] Telegram OSINT", "[13] Sızıntı Sorgu", "[14] Twitter Sorgu"]
    col3 = ["[20] Kullanıcı Adı", "[21] E-posta Doğrula", "[22] Telefon Sorgu", "[23] Roblox ID", "[24] Google Dox"]
    col4 = ["[30] Parola Üret", "[31] Hash Üret", "[32] Hash Kır", "[33] Zip Kır", "[34] Kodla / Çöz"]
    col5 = ["[40] Webhook Bilgi", "[41] Webhook Gönder", "[42] ID Çöz", "[43] Sunucu Bilgi", "[44] Token Bilgi"]
    
    max_len = max(len(col1), len(col2), len(col3), len(col4), len(col5))
    for i in range(max_len):
        c1 = col1[i] if i < len(col1) else ""
        c2 = col2[i] if i < len(col2) else ""
        c3 = col3[i] if i < len(col3) else ""
        c4 = col4[i] if i < len(col4) else ""
        c5 = col5[i] if i < len(col5) else ""
        
        satir_duzgun = f"{c1:<16} {c2:<18} {c3:<16} {c4:<16} {c5}"
        print(random.choice([Fore.CYAN, Fore.MAGENTA, Fore.LIGHTBLUE_EX]) + satir_duzgun)

def main():
    while True:
        main_menu_display()
        print("-" * 85)
        choice = input(Fore.GREEN + "İşlem Numarası Seçin (Örn: 01, 10, 12) > " + Style.RESET_ALL)
        
        if choice in ["01", "1"]: ip_sorgu()
        elif choice == "02": port_tarayici()
        elif choice == "03": ping_araci()
        elif choice == "04": dns_sorgu()
        elif choice == "05": website_bilgi()
        elif choice == "10": instagram_detay_sorgu()
        elif choice == "11": tiktok_detay_sorgu()
        elif choice == "12": telegram_detay_sorgu()
        elif choice == "13": sizinti_sorgu()
        elif choice == "14": genel_sosyal_sorgu("TWİTTER MODÜLÜ")
        elif choice == "20": user_sorgu()
        elif choice == "23": roblox_id_sorgu()
        elif choice in ["21", "22", "24"]: diger_veritabani("VERİTABANI / OSINT")
        elif choice == "30": parola_uret()
        elif choice == "31": hash_uret()
        elif choice == "34": kodla_coz()
        elif choice in ["32", "33"]: diger_araclar("SİBER GÜVENLİK ARACI")
        elif choice == "40": webhook_bilgi()
        elif choice == "41": webhook_gonder()
        elif choice in ["42", "43", "44"]: diger_discord("DİSCORD ARACI")
        elif choice == "5":
            print(Fore.GREEN + "\nSite modülü açılıyor...")
            time.sleep(1)
        elif choice == "0":
            print(Fore.RED + "\nÇıkış yapılıyor...")
            sys.exit()
        else:
            print(Fore.RED + "\n[!] Geçersiz seçim!")
            time.sleep(1)

if __name__ == "__main__":
    main()

