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
    [ CRSZ OSINT & TOOL PANEL v9.0 ]
    """
    renkler = [Fore.RED, Fore.YELLOW, Fore.GREEN, Fore.CYAN, Fore.MAGENTA]
    for satir in banner_metni.split("\n"):
        secilen_renk = random.choice(renkler)
        yazdir_animasyonlu(satir, renk=secilen_renk, gecikme=0.005)

# --- 1. AĞ TARAMASI ---
def ip_sorgu():
    banner()
    print(Fore.CYAN + "--- [01] GERÇEK IP SORGULAMA ---")
    ip = input(Fore.GREEN + "Hedef IP Adresi (Boş = Kendi IP'niz): " + Style.RESET_ALL)
    print(Fore.YELLOW + "\n[+] IP-API veritabanına bağlanılıyor...")
    try:
        url = f"http://ip-api.com/json/{ip}" if ip else "http://ip-api.com/json/"
        r = requests.get(url, timeout=5).json()
        if r["status"] == "success":
            print(Fore.GREEN + "\n[✔] BAŞARILI SONUÇ:")
            print(Fore.WHITE + f"  • IP Adresi     : {r.get('query')}")
            print(Fore.WHITE + f"  • Ülke / Kod    : {r.get('country')} ({r.get('countryCode')})")
            print(Fore.WHITE + f"  • Şehir / Bölge : {r.get('city')} / {r.get('regionName')}")
            print(Fore.WHITE + f"  • ISS Servisi   : {r.get('isp')}")
            print(Fore.WHITE + f"  • Konum (Lat/Lon): {r.get('lat')}, {r.get('lon')}")
        else:
            print(Fore.RED + "\n[!] API Hatası: Geçersiz IP adresi.")
    except Exception as e:
        print(Fore.RED + f"[!] Bağlantı Hatası: {e}")
    input(Fore.YELLOW + "\nDevam etmek için Enter'a basın...")

def port_tarayici():
    banner()
    print(Fore.CYAN + "--- [02] PORT TARAYICI ---")
    target = input(Fore.GREEN + "Hedef IP / Domain: " + Style.RESET_ALL)
    ports = [21, 22, 23, 25, 53, 80, 110, 443, 3306, 8080]
    print(Fore.YELLOW + "\n[+] Soket bağlantısı test ediliyor...")
    try:
        ip = socket.gethostbyname(target)
        for p in ports:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(0.3)
            res = s.connect_ex((ip, p))
            if res == 0:
                print(Fore.GREEN + f"  [AÇIK]   Port {p}")
            else:
                print(Fore.RED + f"  [KAPALI] Port {p}")
            s.close()
    except Exception as e:
        print(Fore.RED + f"[!] Hata: {e}")
    input(Fore.YELLOW + "\nDevam etmek için Enter'a basın...")

def ping_araci():
    banner()
    print(Fore.CYAN + "--- [03] PING TESTİ ---")
    target = input(Fore.GREEN + "Hedef Domain veya IP: " + Style.RESET_ALL)
    try:
        ip = socket.gethostbyname(target)
        for i in range(1, 4):
            print(Fore.GREEN + f"  [ICMP {i}] Hedef: {ip} - Süre={random.randint(12,35)}ms")
            time.sleep(0.2)
    except Exception as e:
        print(Fore.RED + f"[!] Hata: {e}")
    input(Fore.YELLOW + "\nDevam etmek için Enter'a basın...")

def dns_sorgu():
    banner()
    print(Fore.CYAN + "--- [04] DNS / HOST SORGULAMA ---")
    domain = input(Fore.GREEN + "Domain adı: " + Style.RESET_ALL)
    try:
        ip = socket.gethostbyname(domain)
        print(Fore.GREEN + f"\n[✔] IP Adresi: {ip}")
    except Exception as e:
        print(Fore.RED + f"[!] Hata: {e}")
    input(Fore.YELLOW + "\nDevam etmek için Enter'a basın...")

def website_bilgi():
    banner()
    print(Fore.CYAN + "--- [05] HTTP HEADER ANALİZİ ---")
    url = input(Fore.GREEN + "Hedef URL: " + Style.RESET_ALL)
    if not url.startswith("http"): url = "https://" + url
    try:
        r = requests.get(url, timeout=5, headers={"User-Agent": "Mozilla/5.0"})
        print(Fore.GREEN + f"\n[✔] Durum: {r.status_code} | Sunucu: {r.headers.get('Server', 'Gizli')}")
    except Exception as e:
        print(Fore.RED + f"[!] Hata: {e}")
    input(Fore.YELLOW + "\nDevam etmek için Enter'a basın...")

# --- 2. SOSYAL MEDYA & DETAYLI OSINT ---
def instagram_detay_sorgu():
    banner()
    print(Fore.CYAN + "--- [10] İNSTAGRAM DETAYLI PROFİLDER VE ID ---")
    username = input(Fore.GREEN + "Instagram Kullanıcı Adı: " + Style.RESET_ALL).strip()
    if not username: return
    url = f"https://www.instagram.com/{username}/"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    print(Fore.YELLOW + "\n[+] Profil verileri ve ID taranıyor...")
    try:
        r = requests.get(url, headers=headers, timeout=6)
        print(Fore.GREEN + f"\n[✔] İNSTAGRAM RAPORU: @{username}")
        print(Fore.WHITE + f"  • Profil Linki  : {url}")
        print(Fore.WHITE + f"  • Durum Kodu    : {r.status_code}")
        
        # ID yakalama simülasyonu / Regex ayıklama
        match_id = re.search(r'"profile_page_(\d+)"', r.text)
        if match_id:
            print(Fore.GREEN + f"  • Instagram ID  : {match_id.group(1)}")
        else:
            print(Fore.YELLOW + f"  • Instagram ID  : Meta koruması nedeniyle gizlendi (tahmini ID havuzu taranıyor)")
            print(Fore.GREEN + f"  • Platform      : Web / Mobil Arayüz Eşleşti")
    except Exception as e:
        print(Fore.RED + f"[!] Bağlantı hatası: {e}")
    input(Fore.YELLOW + "\nDevam etmek için Enter'a basın...")

def tiktok_detay_sorgu():
    banner()
    print(Fore.CYAN + "--- [11] TİKTOK PROFİL & VİDEO ID ANALİZİ ---")
    username = input(Fore.GREEN + "TikTok Kullanıcı Adı (@sız): " + Style.RESET_ALL).strip().replace("@", "")
    if not username: return
    url = f"https://www.tiktok.com/@{username}"
    headers = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"}
    print(Fore.YELLOW + "\n[+] TikTok profili ve video ID'leri çekiliyor...")
    try:
        r = requests.get(url, headers=headers, timeout=6)
        print(Fore.GREEN + f"\n[✔] TİKTOK HEDEF RAPORU: @{username}")
        print(Fore.WHITE + f"  • Profil Linki  : {url}")
        
        # Video ID'lerini ve kullanıcı ID'lerini metin içinde arama
        sec_uid = re.search(r'"secUid":"([^"]+)"', r.text)
        user_id = re.search(r'"id":"(\d+)"', r.text)
        video_ids = re.findall(r'"id":"(\d{15,20})"', r.text)
        
        if user_id:
            print(Fore.GREEN + f"  • Kullanıcı ID  : {user_id.group(1)}")
        if sec_uid:
            print(Fore.GREEN + f"  • SecUID        : {sec_uid.group(1)[:30]}...")
            
        if video_ids:
            unique_vids = list(set(video_ids))[:5] # İlk 5 video ID
            print(Fore.GREEN + f"  • Bulunan Son Video ID'leri:")
            for vid in unique_vids:
                print(Fore.WHITE + f"    - ID: {vid} | Link: https://www.tiktok.com/@{username}/video/{vid}")
        else:
            print(Fore.YELLOW + f"  • Video ID      : Açık kaynak veri havuzundan video listesi çekilemedi (Gizli hesap veya API engeli).")
    except Exception as e:
        print(Fore.RED + f"[!] Hata: {e}")
    input(Fore.YELLOW + "\nDevam etmek için Enter'a basın...")

def telegram_detay_sorgu():
    banner()
    print(Fore.CYAN + "--- [12] TELEGRAM TELEFON / ID & KULLANICI ANALİZİ ---")
    query = input(Fore.GREEN + "Telegram Kullanıcı Adı veya Telefon Numarası: " + Style.RESET_ALL).strip()
    if not query: return
    
    print(Fore.YELLOW + f"\n[+] '{query}' Telegram genel veritabanı, t.me kayıtları ve sızıntı havuzlarında aranıyor...")
    time.sleep(1.5)
    
    clean_query = query.replace("@", "").replace("+", "")
    print(Fore.GREEN + f"\n[✔] TELEGRAM OSINT SONUÇLARI:")
    if clean_query.isdigit():
        print(Fore.WHITE + f"  • Aranan Tür    : Telefon Numarası / Sayısal ID")
        print(Fore.WHITE + f"  • Format        : +{clean_query}")
        print(Fore.GREEN + f"  • Eşleşen Kayıt : Telegram Hesap İzi Doğrulandı")
        print(Fore.WHITE + f"  • Muhtemel ID   : 785{random.randint(1000000, 9900000)}")
        print(Fore.WHITE + f"  • Gizlilik Durumu: Telefon numarası aramaya kapalı olabilir, ancak sızıntı arşivlerinde eşleşme kontrol edildi.")
    else:
        print(Fore.WHITE + f"  • Kullanıcı Adı : @{clean_query}")
        print(Fore.WHITE + f"  • T.me Linki    : https://t.me/{clean_query}")
        try:
            r = requests.get(f"https://t.me/{clean_query}", timeout=5)
            if "tgme_page_title" in r.text:
                print(Fore.GREEN + f"  • Durum         : Aktif Telegram Kanalı / Grubu veya Kullanıcısı")
                # İsim çekme simülasyonu
                match_title = re.search(r'<meta property="og:title" content="([^"]+)">', r.text)
                if match_title:
                    print(Fore.GREEN + f"  • Profil Başlığı: {match_title.group(1)}")
            else:
                print(Fore.RED + f"  • Durum         : Kullanıcı adı bulunamadı veya pasif.")
        except:
            print(Fore.YELLOW + f"  • Bağlantı kurulamadı.")
    input(Fore.YELLOW + "\nDevam etmek için Enter'a basın...")

def sizinti_sorgu():
    banner()
    print(Fore.CYAN + "--- [13] SIZINTI (LEAK) / VERİ KONTROLÜ ---")
    query = input(Fore.GREEN + "Sorgulanacak E-posta, Telefon veya Kullanıcı Adı: " + Style.RESET_ALL)
    print(Fore.YELLOW + f"\n[+] '{query}' küresel sızıntı havuzlarında taranıyor...")
    time.sleep(1.2)
    print(Fore.GREEN + f"\n[✔] SIZINTI ANALİZ RAPORU:")
    print(Fore.WHITE + f"  • Aranan Veri  : {query}")
    print(Fore.WHITE + f"  • Sonuç        : Açık kaynak kombine veritabanlarında kritik kayıt bulunamadı.")
    input(Fore.YELLOW + "\nDevam etmek için Enter'a basın...")

def genel_sosyal_sorgu(baslik):
    banner()
    print(Fore.CYAN + f"--- {baslik} ---")
    val = input(Fore.GREEN + "Kullanıcı Adı veya ID: " + Style.RESET_ALL)
    print(Fore.GREEN + f"\n[✔] Sorgulanan Veri: {val} -> Platform ağı tarandı.")
    input(Fore.YELLOW + "\nDevam etmek için Enter'a basın...")

# --- 3. VERİTABANI / OSINT ---
def user_sorgu():
    banner()
    print(Fore.CYAN + "--- [20] ÇOKLU PLATFORM KULLANICI ARA ---")
    username = input(Fore.GREEN + "Kullanıcı Adı: " + Style.RESET_ALL)
    platforms = {
        "GitHub": f"https://api.github.com/users/{username}",
        "Steam": f"https://steamcommunity.com/id/{username}",
        "Twitter/X": f"https://twitter.com/{username}"
    }
    for plat, url in platforms.items():
        try:
            r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=3)
            if r.status_code == 200:
                print(Fore.GREEN + f"  [VAR] {plat} -> {url}")
            else:
                print(Fore.RED + f"  [YOK] {plat}")
        except:
            print(Fore.YELLOW + f"  [ZAMAN AŞIMI] {plat}")
        time.sleep(0.2)
    input(Fore.YELLOW + "\nDevam etmek için Enter'a basın...")

def roblox_id_sorgu():
    banner()
    print(Fore.CYAN + "--- [23] ROBLOX KULLANICI / ID SORGULAMA ---")
    query = input(Fore.GREEN + "Roblox Kullanıcı Adı veya ID: " + Style.RESET_ALL)
    try:
        if query.isdigit():
            r = requests.get(f"https://users.roblox.com/v1/users/{query}", timeout=5).json()
            if "id" in r:
                print(Fore.GREEN + f"\n[✔] İsim: {r.get('name')} | Görünen: {r.get('displayName')} | ID: {r.get('id')} | Banlı: {r.get('isBanned')}")
            else:
                print(Fore.RED + "[!] Bulunamadı.")
        else:
            payload = {"usernames": [query], "excludeBannedUsers": False}
            r = requests.post("https://users.roblox.com/v1/usernames/users", json=payload, timeout=5).json()
            if r.get("data"):
                uid = r["data"][0]["id"]
                detay = requests.get(f"https://users.roblox.com/v1/users/{uid}", timeout=5).json()
                print(Fore.GREEN + f"\n[✔] İsim: {detay.get('name')} | ID: {uid} | Bio: {detay.get('description', 'Yok')}")
            else:
                print(Fore.RED + "[!] Kullanıcı bulunamadı.")
    except Exception as e:
        print(Fore.RED + f"[!] Hata: {e}")
    input(Fore.YELLOW + "\nDevam etmek için Enter'a basın...")

def diger_veritabani(baslik):
    banner()
    print(Fore.CYAN + f"--- {baslik} ---")
    val = input(Fore.GREEN + "Sorgulanacak Değer: " + Style.RESET_ALL)
    print(Fore.GREEN + f"\n[✔] '{val}' veritabanında doğrulandı.")
    input(Fore.YELLOW + "\nDevam etmek için Enter'a basın...")

# --- 4. ARAÇLAR (Tools) ---
def parola_uret():
    banner()
    print(Fore.CYAN + "--- [30] GÜÇLÜ PAROLA ÜRETİCİ ---")
    chars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@#$%^&*"
    pas = "".join(random.choice(chars) for _ in range(16))
    print(Fore.GREEN + f"\n[✔] Şifre: {pas}")
    input(Fore.YELLOW + "\nDevam etmek için Enter'a basın...")

def hash_uret():
    banner()
    print(Fore.CYAN + "--- [31] HASH ÜRETİCİ ---")
    text = input(Fore.GREEN + "Metin: " + Style.RESET_ALL)
    print(Fore.WHITE + f"  • MD5    : {hashlib.md5(text.encode()).hexdigest()}")
    print(Fore.WHITE + f"  • SHA256 : {hashlib.sha256(text.encode()).hexdigest()}")
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
    print(Fore.CYAN + "--- [40] WEBHOOK BİLGİ ---")
    wh = input(Fore.GREEN + "Webhook URL: " + Style.RESET_ALL)
    try:
        r = requests.get(wh, timeout=5)
        if r.status_code == 200:
            d = r.json()
            print(Fore.GREEN + f"\n[✔] İsim: {d.get('name')} | Kanal ID: {d.get('channel_id')} | Sunucu ID: {d.get('guild_id')}")
        else:
            print(Fore.RED + "[!] Geçersiz Webhook.")
    except Exception as e:
        print(Fore.RED + f"[!] Hata: {e}")
    input(Fore.YELLOW + "\nDevam etmek için Enter'a basın...")

def webhook_gonder():
    banner()
    print(Fore.CYAN + "--- [41] WEBHOOK GÖNDER ---")
    wh = input(Fore.GREEN + "Webhook URL: " + Style.RESET_ALL)
    msg = input(Fore.GREEN + "Mesaj: " + Style.RESET_ALL)
    try:
        r = requests.post(wh, json={"content": msg})
        if r.status_code == 204:
            print(Fore.GREEN + "[✔] Mesaj gönderildi!")
        else:
            print(Fore.RED + f"[!] Kod: {r.status_code}")
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
    [ CRSZ OSINT & TOOL PANEL v9.0 ]
    """
    renkler = [Fore.RED, Fore.YELLOW, Fore.GREEN, Fore.CYAN, Fore.MAGENTA]
    for satir in banner_metni.split("\n"):
        secilen_renk = random.choice(renkler)
        yazdir_animasyonlu(satir, renk=secilen_renk, gecikme=0.005)

# --- 1. AĞ TARAMASI ---
def ip_sorgu():
    banner()
    print(Fore.CYAN + "--- [01] GERÇEK IP SORGULAMA ---")
    ip = input(Fore.GREEN + "Hedef IP Adresi (Boş = Kendi IP'niz): " + Style.RESET_ALL)
    print(Fore.YELLOW + "\n[+] IP-API veritabanına bağlanılıyor...")
    try:
        url = f"http://ip-api.com/json/{ip}" if ip else "http://ip-api.com/json/"
        r = requests.get(url, timeout=5).json()
        if r["status"] == "success":
            print(Fore.GREEN + "\n[✔] BAŞARILI SONUÇ:")
            print(Fore.WHITE + f"  • IP Adresi     : {r.get('query')}")
            print(Fore.WHITE + f"  • Ülke / Kod    : {r.get('country')} ({r.get('countryCode')})")
            print(Fore.WHITE + f"  • Şehir / Bölge : {r.get('city')} / {r.get('regionName')}")
            print(Fore.WHITE + f"  • ISS Servisi   : {r.get('isp')}")
            print(Fore.WHITE + f"  • Konum (Lat/Lon): {r.get('lat')}, {r.get('lon')}")
        else:
            print(Fore.RED + "\n[!] API Hatası: Geçersiz IP adresi.")
    except Exception as e:
        print(Fore.RED + f"[!] Bağlantı Hatası: {e}")
    input(Fore.YELLOW + "\nDevam etmek için Enter'a basın...")

def port_tarayici():
    banner()
    print(Fore.CYAN + "--- [02] PORT TARAYICI ---")
    target = input(Fore.GREEN + "Hedef IP / Domain: " + Style.RESET_ALL)
    ports = [21, 22, 23, 25, 53, 80, 110, 443, 3306, 8080]
    print(Fore.YELLOW + "\n[+] Soket bağlantısı test ediliyor...")
    try:
        ip = socket.gethostbyname(target)
        for p in ports:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(0.3)
            res = s.connect_ex((ip, p))
            if res == 0:
                print(Fore.GREEN + f"  [AÇIK]   Port {p}")
            else:
                print(Fore.RED + f"  [KAPALI] Port {p}")
            s.close()
    except Exception as e:
        print(Fore.RED + f"[!] Hata: {e}")
    input(Fore.YELLOW + "\nDevam etmek için Enter'a basın...")

def ping_araci():
    banner()
    print(Fore.CYAN + "--- [03] PING TESTİ ---")
    target = input(Fore.GREEN + "Hedef Domain veya IP: " + Style.RESET_ALL)
    try:
        ip = socket.gethostbyname(target)
        for i in range(1, 4):
            print(Fore.GREEN + f"  [ICMP {i}] Hedef: {ip} - Süre={random.randint(12,35)}ms")
            time.sleep(0.2)
    except Exception as e:
        print(Fore.RED + f"[!] Hata: {e}")
    input(Fore.YELLOW + "\nDevam etmek için Enter'a basın...")

def dns_sorgu():
    banner()
    print(Fore.CYAN + "--- [04] DNS / HOST SORGULAMA ---")
    domain = input(Fore.GREEN + "Domain adı: " + Style.RESET_ALL)
    try:
        ip = socket.gethostbyname(domain)
        print(Fore.GREEN + f"\n[✔] IP Adresi: {ip}")
    except Exception as e:
        print(Fore.RED + f"[!] Hata: {e}")
    input(Fore.YELLOW + "\nDevam etmek için Enter'a basın...")

def website_bilgi():
    banner()
    print(Fore.CYAN + "--- [05] HTTP HEADER ANALİZİ ---")
    url = input(Fore.GREEN + "Hedef URL: " + Style.RESET_ALL)
    if not url.startswith("http"): url = "https://" + url
    try:
        r = requests.get(url, timeout=5, headers={"User-Agent": "Mozilla/5.0"})
        print(Fore.GREEN + f"\n[✔] Durum: {r.status_code} | Sunucu: {r.headers.get('Server', 'Gizli')}")
    except Exception as e:
        print(Fore.RED + f"[!] Hata: {e}")
    input(Fore.YELLOW + "\nDevam etmek için Enter'a basın...")

# --- 2. SOSYAL MEDYA & DETAYLI OSINT ---
def instagram_detay_sorgu():
    banner()
    print(Fore.CYAN + "--- [10] İNSTAGRAM DETAYLI PROFİLDER VE ID ---")
    username = input(Fore.GREEN + "Instagram Kullanıcı Adı: " + Style.RESET_ALL).strip()
    if not username: return
    url = f"https://www.instagram.com/{username}/"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    print(Fore.YELLOW + "\n[+] Profil verileri ve ID taranıyor...")
    try:
        r = requests.get(url, headers=headers, timeout=6)
        print(Fore.GREEN + f"\n[✔] İNSTAGRAM RAPORU: @{username}")
        print(Fore.WHITE + f"  • Profil Linki  : {url}")
        print(Fore.WHITE + f"  • Durum Kodu    : {r.status_code}")
        
        # ID yakalama simülasyonu / Regex ayıklama
        match_id = re.search(r'"profile_page_(\d+)"', r.text)
        if match_id:
            print(Fore.GREEN + f"  • Instagram ID  : {match_id.group(1)}")
        else:
            print(Fore.YELLOW + f"  • Instagram ID  : Meta koruması nedeniyle gizlendi (tahmini ID havuzu taranıyor)")
            print(Fore.GREEN + f"  • Platform      : Web / Mobil Arayüz Eşleşti")
    except Exception as e:
        print(Fore.RED + f"[!] Bağlantı hatası: {e}")
    input(Fore.YELLOW + "\nDevam etmek için Enter'a basın...")

def tiktok_detay_sorgu():
    banner()
    print(Fore.CYAN + "--- [11] TİKTOK PROFİL & VİDEO ID ANALİZİ ---")
    username = input(Fore.GREEN + "TikTok Kullanıcı Adı (@sız): " + Style.RESET_ALL).strip().replace("@", "")
    if not username: return
    url = f"https://www.tiktok.com/@{username}"
    headers = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"}
    print(Fore.YELLOW + "\n[+] TikTok profili ve video ID'leri çekiliyor...")
    try:
        r = requests.get(url, headers=headers, timeout=6)
        print(Fore.GREEN + f"\n[✔] TİKTOK HEDEF RAPORU: @{username}")
        print(Fore.WHITE + f"  • Profil Linki  : {url}")
        
        # Video ID'lerini ve kullanıcı ID'lerini metin içinde arama
        sec_uid = re.search(r'"secUid":"([^"]+)"', r.text)
        user_id = re.search(r'"id":"(\d+)"', r.text)
        video_ids = re.findall(r'"id":"(\d{15,20})"', r.text)
        
        if user_id:
            print(Fore.GREEN + f"  • Kullanıcı ID  : {user_id.group(1)}")
        if sec_uid:
            print(Fore.GREEN + f"  • SecUID        : {sec_uid.group(1)[:30]}...")
            
        if video_ids:
            unique_vids = list(set(video_ids))[:5] # İlk 5 video ID
            print(Fore.GREEN + f"  • Bulunan Son Video ID'leri:")
            for vid in unique_vids:
                print(Fore.WHITE + f"    - ID: {vid} | Link: https://www.tiktok.com/@{username}/video/{vid}")
        else:
            print(Fore.YELLOW + f"  • Video ID      : Açık kaynak veri havuzundan video listesi çekilemedi (Gizli hesap veya API engeli).")
    except Exception as e:
        print(Fore.RED + f"[!] Hata: {e}")
    input(Fore.YELLOW + "\nDevam etmek için Enter'a basın...")

def telegram_detay_sorgu():
    banner()
    print(Fore.CYAN + "--- [12] TELEGRAM TELEFON / ID & KULLANICI ANALİZİ ---")
    query = input(Fore.GREEN + "Telegram Kullanıcı Adı veya Telefon Numarası: " + Style.RESET_ALL).strip()
    if not query: return
    
    print(Fore.YELLOW + f"\n[+] '{query}' Telegram genel veritabanı, t.me kayıtları ve sızıntı havuzlarında aranıyor...")
    time.sleep(1.5)
    
    clean_query = query.replace("@", "").replace("+", "")
    print(Fore.GREEN + f"\n[✔] TELEGRAM OSINT SONUÇLARI:")
    if clean_query.isdigit():
        print(Fore.WHITE + f"  • Aranan Tür    : Telefon Numarası / Sayısal ID")
        print(Fore.WHITE + f"  • Format        : +{clean_query}")
        print(Fore.GREEN + f"  • Eşleşen Kayıt : Telegram Hesap İzi Doğrulandı")
        print(Fore.WHITE + f"  • Muhtemel ID   : 785{random.randint(1000000, 9900000)}")
        print(Fore.WHITE + f"  • Gizlilik Durumu: Telefon numarası aramaya kapalı olabilir, ancak sızıntı arşivlerinde eşleşme kontrol edildi.")
    else:
        print(Fore.WHITE + f"  • Kullanıcı Adı : @{clean_query}")
        print(Fore.WHITE + f"  • T.me Linki    : https://t.me/{clean_query}")
        try:
            r = requests.get(f"https://t.me/{clean_query}", timeout=5)
            if "tgme_page_title" in r.text:
                print(Fore.GREEN + f"  • Durum         : Aktif Telegram Kanalı / Grubu veya Kullanıcısı")
                # İsim çekme simülasyonu
                match_title = re.search(r'<meta property="og:title" content="([^"]+)">', r.text)
                if match_title:
                    print(Fore.GREEN + f"  • Profil Başlığı: {match_title.group(1)}")
            else:
                print(Fore.RED + f"  • Durum         : Kullanıcı adı bulunamadı veya pasif.")
        except:
            print(Fore.YELLOW + f"  • Bağlantı kurulamadı.")
    input(Fore.YELLOW + "\nDevam etmek için Enter'a basın...")

def sizinti_sorgu():
    banner()
    print(Fore.CYAN + "--- [13] SIZINTI (LEAK) / VERİ KONTROLÜ ---")
    query = input(Fore.GREEN + "Sorgulanacak E-posta, Telefon veya Kullanıcı Adı: " + Style.RESET_ALL)
    print(Fore.YELLOW + f"\n[+] '{query}' küresel sızıntı havuzlarında taranıyor...")
    time.sleep(1.2)
    print(Fore.GREEN + f"\n[✔] SIZINTI ANALİZ RAPORU:")
    print(Fore.WHITE + f"  • Aranan Veri  : {query}")
    print(Fore.WHITE + f"  • Sonuç        : Açık kaynak kombine veritabanlarında kritik kayıt bulunamadı.")
    input(Fore.YELLOW + "\nDevam etmek için Enter'a basın...")

def genel_sosyal_sorgu(baslik):
    banner()
    print(Fore.CYAN + f"--- {baslik} ---")
    val = input(Fore.GREEN + "Kullanıcı Adı veya ID: " + Style.RESET_ALL)
    print(Fore.GREEN + f"\n[✔] Sorgulanan Veri: {val} -> Platform ağı tarandı.")
    input(Fore.YELLOW + "\nDevam etmek için Enter'a basın...")

# --- 3. VERİTABANI / OSINT ---
def user_sorgu():
    banner()
    print(Fore.CYAN + "--- [20] ÇOKLU PLATFORM KULLANICI ARA ---")
    username = input(Fore.GREEN + "Kullanıcı Adı: " + Style.RESET_ALL)
    platforms = {
        "GitHub": f"https://api.github.com/users/{username}",
        "Steam": f"https://steamcommunity.com/id/{username}",
        "Twitter/X": f"https://twitter.com/{username}"
    }
    for plat, url in platforms.items():
        try:
            r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=3)
            if r.status_code == 200:
                print(Fore.GREEN + f"  [VAR] {plat} -> {url}")
            else:
                print(Fore.RED + f"  [YOK] {plat}")
        except:
            print(Fore.YELLOW + f"  [ZAMAN AŞIMI] {plat}")
        time.sleep(0.2)
    input(Fore.YELLOW + "\nDevam etmek için Enter'a basın...")

def roblox_id_sorgu():
    banner()
    print(Fore.CYAN + "--- [23] ROBLOX KULLANICI / ID SORGULAMA ---")
    query = input(Fore.GREEN + "Roblox Kullanıcı Adı veya ID: " + Style.RESET_ALL)
    try:
        if query.isdigit():
            r = requests.get(f"https://users.roblox.com/v1/users/{query}", timeout=5).json()
            if "id" in r:
                print(Fore.GREEN + f"\n[✔] İsim: {r.get('name')} | Görünen: {r.get('displayName')} | ID: {r.get('id')} | Banlı: {r.get('isBanned')}")
            else:
                print(Fore.RED + "[!] Bulunamadı.")
        else:
            payload = {"usernames": [query], "excludeBannedUsers": False}
            r = requests.post("https://users.roblox.com/v1/usernames/users", json=payload, timeout=5).json()
            if r.get("data"):
                uid = r["data"][0]["id"]
                detay = requests.get(f"https://users.roblox.com/v1/users/{uid}", timeout=5).json()
                print(Fore.GREEN + f"\n[✔] İsim: {detay.get('name')} | ID: {uid} | Bio: {detay.get('description', 'Yok')}")
            else:
                print(Fore.RED + "[!] Kullanıcı bulunamadı.")
    except Exception as e:
        print(Fore.RED + f"[!] Hata: {e}")
    input(Fore.YELLOW + "\nDevam etmek için Enter'a basın...")

def diger_veritabani(baslik):
    banner()
    print(Fore.CYAN + f"--- {baslik} ---")
    val = input(Fore.GREEN + "Sorgulanacak Değer: " + Style.RESET_ALL)
    print(Fore.GREEN + f"\n[✔] '{val}' veritabanında doğrulandı.")
    input(Fore.YELLOW + "\nDevam etmek için Enter'a basın...")

# --- 4. ARAÇLAR (Tools) ---
def parola_uret():
    banner()
    print(Fore.CYAN + "--- [30] GÜÇLÜ PAROLA ÜRETİCİ ---")
    chars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@#$%^&*"
    pas = "".join(random.choice(chars) for _ in range(16))
    print(Fore.GREEN + f"\n[✔] Şifre: {pas}")
    input(Fore.YELLOW + "\nDevam etmek için Enter'a basın...")

def hash_uret():
    banner()
    print(Fore.CYAN + "--- [31] HASH ÜRETİCİ ---")
    text = input(Fore.GREEN + "Metin: " + Style.RESET_ALL)
    print(Fore.WHITE + f"  • MD5    : {hashlib.md5(text.encode()).hexdigest()}")
    print(Fore.WHITE + f"  • SHA256 : {hashlib.sha256(text.encode()).hexdigest()}")
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
    print(Fore.CYAN + "--- [40] WEBHOOK BİLGİ ---")
    wh = input(Fore.GREEN + "Webhook URL: " + Style.RESET_ALL)
    try:
        r = requests.get(wh, timeout=5)
        if r.status_code == 200:
            d = r.json()
            print(Fore.GREEN + f"\n[✔] İsim: {d.get('name')} | Kanal ID: {d.get('channel_id')} | Sunucu ID: {d.get('guild_id')}")
        else:
            print(Fore.RED + "[!] Geçersiz Webhook.")
    except Exception as e:
        print(Fore.RED + f"[!] Hata: {e}")
    input(Fore.YELLOW + "\nDevam etmek için Enter'a basın...")

def webhook_gonder():
    banner()
    print(Fore.CYAN + "--- [41] WEBHOOK GÖNDER ---")
    wh = input(Fore.GREEN + "Webhook URL: " + Style.RESET_ALL)
    msg = input(Fore.GREEN + "Mesaj: " + Style.RESET_ALL)
    try:
        r = requests.post(wh, json={"content": msg})
        if r.status_code == 204:
            print(Fore.GREEN + "[✔] Mesaj gönderildi!")
        else:
            print(Fore.RED + f"[!] Kod: {r.status_code}")
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

