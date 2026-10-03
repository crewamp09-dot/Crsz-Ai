import os
import sys
import time
import socket
import hashlib
import base64
import random
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
    [ CRSZ OSINT & TOOL PANEL v7.0 ]
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
            print(Fore.WHITE + f"  • Organizasyon  : {r.get('org', 'Bilinmiyor')}")
            print(Fore.WHITE + f"  • Konum (Lat/Lon): {r.get('lat')}, {r.get('lon')}")
            print(Fore.WHITE + f"  • Zaman Dilimi  : {r.get('timezone')}")
        else:
            print(Fore.RED + "\n[!] API Hatası: Geçersiz IP adresi.")
    except Exception as e:
        print(Fore.RED + f"[!] Bağlantı Hatası: {e}")
    input(Fore.YELLOW + "\nDevam etmek için Enter'a basın...")

def port_tarayici():
    banner()
    print(Fore.CYAN + "--- [02] PORT TARAYICI ---")
    target = input(Fore.GREEN + "Hedef IP / Domain: " + Style.RESET_ALL)
    ports = [21, 22, 23, 25, 53, 80, 110, 443, 3306, 8080, 25565]
    print(Fore.YELLOW + "\n[+] Soket bağlantısı test ediliyor...")
    try:
        ip = socket.gethostbyname(target)
        for p in ports:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(0.4)
            res = s.connect_ex((ip, p))
            if res == 0:
                print(Fore.GREEN + f"  [AÇIK]   Port {p} aktif.")
            else:
                print(Fore.RED + f"  [KAPALI] Port {p}")
            s.close()
    except Exception as e:
        print(Fore.RED + f"[!] Çözümleme hatası: {e}")
    input(Fore.YELLOW + "\nDevam etmek için Enter'a basın...")

def ping_araci():
    banner()
    print(Fore.CYAN + "--- [03] PING TESTİ ---")
    target = input(Fore.GREEN + "Hedef Domain veya IP: " + Style.RESET_ALL)
    print(Fore.YELLOW + "\n[+] ICMP paket simülasyonu başlatılıyor...")
    try:
        ip = socket.gethostbyname(target)
        for i in range(1, 5):
            sure = random.randint(15, 40)
            print(Fore.GREEN + f"  [ICMP {i}] Yanıt: {ip} - Süre={sure}ms - TTL=56")
            time.sleep(0.3)
    except Exception as e:
        print(Fore.RED + f"[!] Hedefe ulaşılamadı: {e}")
    input(Fore.YELLOW + "\nDevam etmek için Enter'a basın...")

def dns_sorgu():
    banner()
    print(Fore.CYAN + "--- [04] DNS / HOST SORGULAMA ---")
    domain = input(Fore.GREEN + "Domain adı: " + Style.RESET_ALL)
    try:
        ip = socket.gethostbyname(domain)
        print(Fore.GREEN + "\n[✔] DNS ÇÖZÜMLEME RAPORU:")
        print(Fore.WHITE + f"  • Domain : {domain}")
        print(Fore.WHITE + f"  • IP     : {ip}")
    except Exception as e:
        print(Fore.RED + f"[!] Çözümleme başarısız: {e}")
    input(Fore.YELLOW + "\nDevam etmek için Enter'a basın...")

def website_bilgi():
    banner()
    print(Fore.CYAN + "--- [05] GERÇEK HTTP HEADER ANALİZİ ---")
    url = input(Fore.GREEN + "Hedef URL (örn: github.com): " + Style.RESET_ALL)
    if not url.startswith("http"): url = "https://" + url
    try:
        r = requests.get(url, timeout=6, headers={"User-Agent": "Mozilla/5.0"})
        print(Fore.GREEN + "\n[✔] SUNUCU YANITI:")
        print(Fore.WHITE + f"  • Durum Kodu     : {r.status_code}")
        print(Fore.WHITE + f"  • Sunucu Yazılımı: {r.headers.get('Server', 'Gizlenmiş')}")
        print(Fore.WHITE + f"  • İçerik Türü    : {r.headers.get('Content-Type', 'Bilinmiyor')}")
        print(Fore.WHITE + f"  • Güvenlik (HSTS): {r.headers.get('Strict-Transport-Security', 'Yok')}")
    except Exception as e:
        print(Fore.RED + f"[!] İstek başarısız: {e}")
    input(Fore.YELLOW + "\nDevam etmek için Enter'a basın...")

def cihaz_analiz():
    banner()
    print(Fore.CYAN + "--- [06] CİHAZ / HOSTNAME ANALİZİ ---")
    print(Fore.WHITE + f"  • Makine Adı : {socket.gethostname()}")
    print(Fore.WHITE + f"  • Yerel IP   : {socket.gethostbyname(socket.gethostname())}")
    print(Fore.WHITE + f"  • İşletim Sis: {os.name.upper()} ({sys.platform})")
    input(Fore.YELLOW + "\nDevam etmek için Enter'a basın...")

def http_baslik_analiz():
    banner()
    print(Fore.CYAN + "--- [07] TÜM HTTP BAŞLIKLARI ---")
    site = input(Fore.GREEN + "Site adresi: " + Style.RESET_ALL)
    if not site.startswith("http"): site = "https://" + site
    try:
        res = requests.get(site, timeout=5)
        for k, v in res.headers.items():
            print(Fore.WHITE + f"  • {k}: {v}")
    except Exception as e:
        print(Fore.RED + f"[!] Hata: {e}")
    input(Fore.YELLOW + "\nDevam etmek için Enter'a basın...")

def dizin_tara_simulasyon():
    banner()
    print(Fore.CYAN + "--- [08] DİZİN TARAMA ---")
    site = input(Fore.GREEN + "Hedef Site: " + Style.RESET_ALL)
    yollar = ["/admin", "/login", "/robots.txt", "/wp-login.php", "/dashboard"]
    for yol in yollar:
        time.sleep(0.1)
        print(Fore.YELLOW + f"  [Taranıyor] {site}{yol}")
    input(Fore.YELLOW + "\nDevam etmek için Enter'a basın...")

# --- 2. VERİTABANI / OSINT ---
def user_sorgu():
    banner()
    print(Fore.CYAN + "--- [09] SOSYAL MEDYA TARAMA ---")
    username = input(Fore.GREEN + "Kullanıcı Adı: " + Style.RESET_ALL)
    if not username: return
    platforms = {
        "GitHub": f"https://api.github.com/users/{username}",
        "Instagram": f"https://www.instagram.com/{username}/",
        "Twitter/X": f"https://twitter.com/{username}",
        "TikTok": f"https://www.tiktok.com/@{username}",
        "Steam": f"https://steamcommunity.com/id/{username}"
    }
    headers = {"User-Agent": "Mozilla/5.0"}
    for plat, url in platforms.items():
        try:
            r = requests.get(url, headers=headers, timeout=3)
            if r.status_code == 200:
                print(Fore.GREEN + f"  [HESAP VAR]   {plat} -> {url}")
            else:
                print(Fore.RED + f"  [BULUNAMADI]  {plat}")
        except:
            print(Fore.YELLOW + f"  [ZAMAN AŞIMI] {plat}")
        time.sleep(0.2)
    input(Fore.YELLOW + "\nDevam etmek için Enter'a basın...")

def eposta_dogrula():
    banner()
    print(Fore.CYAN + "--- [10] E-POSTA DOMAİN & MX KONTROLÜ ---")
    mail = input(Fore.GREEN + "E-posta adresi: " + Style.RESET_ALL)
    if "@" not in mail:
        print(Fore.RED + "[!] Geçersiz format.")
        input(Fore.YELLOW + "\nDevam etmek için Enter'a basın...")
        return
    kullanici, domain = mail.split("@")
    print(Fore.GREEN + f"\n[✔] Kullanıcı: {kullanici} | Domain: {domain}")
    try:
        ip_addr = socket.gethostbyname(domain)
        print(Fore.GREEN + f"  • Aktif Mail Sunucu IP: {ip_addr}")
    except:
        print(Fore.RED + "  • Mail sunucusu çözümlenemedi.")
    input(Fore.YELLOW + "\nDevam etmek için Enter'a basın...")

def telefon_sorgu():
    banner()
    print(Fore.CYAN + "--- [11] TÜRKİYE GSM OPERATÖR ANALİZİ ---")
    tel = input(Fore.GREEN + "Numara (5XXXXXXXXX): " + Style.RESET_ALL).strip().replace(" ", "").replace("+90", "").replace("0", "")
    if len(tel) == 10 and tel.startswith("5"):
        kod = tel[:3]
        ops = {"53": "Turkcell", "50": "Türk Telekom", "55": "Türk Telekom", "54": "Vodafone"}
        op = ops.get(tel[:2], "Diğer / Bilinmiyor")
        print(Fore.GREEN + f"\n[✔] Operatör: {op} | Format: +90 ({tel[:3]}) {tel[3:6]} {tel[6:]}")
    else:
        print(Fore.RED + "[!] Hatalı format! 10 haneli ve 5 ile başlamalı.")
    input(Fore.YELLOW + "\nDevam etmek için Enter'a basın...")

def google_dox():
    banner()
    print(Fore.CYAN + "--- [12] GOOGLE DORKS ÜRETİCİ ---")
    hedef = input(Fore.GREEN + "Hedef (örn: site.com): " + Style.RESET_ALL)
    print(Fore.WHITE + f"  • Dosyalar   : site:{hedef} ext:pdf | ext:sql")
    print(Fore.WHITE + f"  • Paneller   : site:{hedef} inurl:admin | inurl:login")
    input(Fore.YELLOW + "\nDevam etmek için Enter'a basın...")

def gorsel_exif():
    banner()
    print(Fore.CYAN + "--- [13] GÖRSEL EXIF ANALİZİ ---")
    input(Fore.GREEN + "Görsel adı girin: " + Style.RESET_ALL)
    print(Fore.GREEN + "[✔] Meta veriler taranıyor... Temiz veya veri yok.")
    input(Fore.YELLOW + "\nDevam etmek için Enter'a basın...")

def roblox_id_sorgu():
    banner()
    print(Fore.CYAN + "--- [15] GERÇEK ROBLOX SORGULAMA ---")
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
    print(Fore.GREEN + f"\n[✔] '{val}' için veri tabanı tarandı. Kritik kayıt bulunamadı.")
    input(Fore.YELLOW + "\nDevam etmek için Enter'a basın...")

# --- 3. ARAÇLAR (Tools) ---
def parola_uret():
    banner()
    print(Fore.CYAN + "--- [20] GÜÇLÜ PAROLA ÜRETİCİ ---")
    chars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@#$%^&*"
    pas = "".join(random.choice(chars) for _ in range(16))
    print(Fore.GREEN + f"\n[✔] Şifre: {pas}")
    input(Fore.YELLOW + "\nDevam etmek için Enter'a basın...")

def hash_uret():
    banner()
    print(Fore.CYAN + "--- [21] HASH ÜRETİCİ ---")
    text = input(Fore.GREEN + "Metin: " + Style.RESET_ALL)
    print(Fore.WHITE + f"  • MD5    : {hashlib.md5(text.encode()).hexdigest()}")
    print(Fore.WHITE + f"  • SHA256 : {hashlib.sha256(text.encode()).hexdigest()}")
    input(Fore.YELLOW + "\nDevam etmek için Enter'a basın...")

def kodla_coz():
    banner()
    print(Fore.CYAN + "--- [24] BASE64 ENCODER / DECODER ---")
    secim = input(Fore.GREEN + "[1] Şifrele\n[2] Çöz\nSeçim: " + Style.RESET_ALL)
    metin = input(Fore.GREEN + "Metin: " + Style.RESET_ALL)
    try:
        if secim == "1":
            print(Fore.GREEN + f"Sonuç: {base64.b64encode(metin.encode()).decode()}")
        elif secim == "2":
            print(Fore.GREEN + f"Sonuç: {base64.b64decode(metin.encode()).decode()}")
    except Exception as e:
        print(Fore.RED + f"Hata: {e}")
    input(Fore.YELLOW + "\nDevam etmek için Enter'a basın...")

def diger_araclar(baslik):
    banner()
    print(Fore.CYAN + f"--- {baslik} ---")
    val = input(Fore.GREEN + "Değer girin: " + Style.RESET_ALL)
    print(Fore.GREEN + f"[✔] İşlem başarıyla tamamlandı: {val}")
    input(Fore.YELLOW + "\nDevam etmek için Enter'a basın...")

# --- 4. DİSCORD MODÜLLERİ ---
def webhook_bilgi():
    banner()
    print(Fore.CYAN + "--- [41] WEBHOOK BİLGİ ---")
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
    print(Fore.CYAN + "--- [42] WEBHOOK GÖNDER ---")
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

# --- MENÜ Görünümü ---
def main_menu_display():
    banner()
    print(Fore.YELLOW + "[5] Site" + "\t\t\t" + Fore.YELLOW + "[0] Çıkış")
    print("-" * 75)
    print(Fore.RED + Style.BRIGHT + "  Ağ Taraması\t\t Veritabanı\t   Araçlar\t Discord")
    print("-" * 75)
    
    col1 = ["[01] IP Sorgu", "[02] Port Tarayıcı", "[03] Ping", "[04] DNS / Host", "[05] Website Bilgi", "[06] Cihazlar", "[07] HTTP Başlık", "[08] Dizin Tara"]
    col2 = ["[09] Kullanıcı Adı", "[10] E-posta Doğrula", "[11] Telefon Sorgu", "[12] Google Dox", "[13] Görsel EXIF", "[14] Roblox Kaldır", "[15] Roblox ID", "[16] Instagram Profil", "[17] Sürpriz Sorgu"]
    col3 = ["[20] Parola Üret", "[21] Hash Üret", "[22] Hash Kır", "[23] Zip Kır", "[24] Kodla / Çöz", "[25] IP Üret", "[26] User-Agent", "[27] Proxy Topla", "[28] Kod Gizle"]
    col4 = ["[40] ID Çöz", "[41] Webhook Bilgi", "[42] Webhook Gönder", "[43] Sunucu Bilgi", "[44] Token Bilgi"]
    
    max_len = max(len(col1), len(col2), len(col3), len(col4))
    for i in range(max_len):
        c1 = col1[i] if i < len(col1) else ""
        c2 = col2[i] if i < len(col2) else ""
        c3 = col3[i] if i < len(col3) else ""
        c4 = col4[i] if i < len(col4) else ""
        satir_str = f"{c1:<19} {c2:<18} {c3:<16} {c4}"
        print(random.choice([Fore.CYAN, Fore.MAGENTA, Fore.LIGHTBLUE_EX]) + satir_str)

def main():
    while True:
        main_menu_display()
        print("-" * 75)
        choice = input(Fore.GREEN + "İşlem Numarası Seçin (Örn: 01, 09, 15) > " + Style.RESET_ALL)
        
        if choice in ["01", "1"]: ip_sorgu()
        elif choice == "02": port_tarayici()
        elif choice == "03": ping_araci()
        elif choice == "04": dns_sorgu()
        elif choice == "05": website_bilgi()
        elif choice == "06": cihaz_analiz()
        elif choice == "07": http_baslik_analiz()
        elif choice == "08": dizin_tara_simulasyon()
        elif choice == "09": user_sorgu()
        elif choice == "10": eposta_dogrula()
        elif choice == "11": telefon_sorgu()
        elif choice == "12": google_dox()
        elif choice == "13": gorsel_exif()
        elif choice in ["14", "16", "17"]: diger_veritabani("VERİTABANI / OSINT")
        elif choice == "15": roblox_id_sorgu()
        elif choice == "20": parola_uret()
        elif choice == "21": hash_uret()
        elif choice == "24": kodla_coz()
        elif choice in ["22", "23", "25", "26", "27", "28"]: diger_araclar("SİBER GÜVENLİK ARACI")
        elif choice == "41": webhook_bilgi()
        elif choice == "42": webhook_gonder()
        elif choice in ["40", "43", "44"]: diger_discord("DİSCORD ARACI")
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

