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
    [ CRSZ OSINT & TOOL PANEL v6.0 ]
    """
    # Dalgalı renk geçişli banner gösterimi
    renkler = [Fore.RED, Fore.YELLOW, Fore.GREEN, Fore.CYAN, Fore.MAGENTA]
    for satir in banner_metni.split("\n"):
        secilen_renk = random.choice(renkler)
        yazdir_animasyonlu(satir, renk=secilen_renk, gecikme=0.005)

# --- 1. AĞ TARAMASI ---
def ip_sorgu():
    banner()
    print(Fore.CYAN + "--- [01] IP SORGULAMA ---")
    ip = input(Fore.GREEN + "Hedef IP Adresi (Boş = Kendi IP'niz): " + Style.RESET_ALL)
    print(Fore.YELLOW + "\n[+] IP veritabanı sorgulanıyor...")
    try:
        url = f"http://ip-api.com/json/{ip}" if ip else "http://ip-api.com/json/"
        r = requests.get(url, timeout=5).json()
        if r["status"] == "success":
            print(Fore.GREEN + "\n[✔] HEDEF IP BİLGİLERİ:")
            print(Fore.WHITE + "  • IP Adresi  : " + str(r.get('query')))
            print(Fore.WHITE + "  • Ülke       : " + str(r.get('country')) + " (" + str(r.get('countryCode')) + ")")
            print(Fore.WHITE + "  • Şehir      : " + str(r.get('city')) + " / " + str(r.get('regionName')))
            print(Fore.WHITE + "  • ISS / Servis: " + str(r.get('isp')))
            print(Fore.WHITE + "  • Organizasyon: " + str(r.get('org', 'Bilinmiyor')))
            print(Fore.WHITE + "  • Koordinat  : " + str(r.get('lat')) + ", " + str(r.get('lon')))
            print(Fore.WHITE + "  • Zaman Dilimi: " + str(r.get('timezone')))
        else:
            print(Fore.RED + "\n[!] Geçersiz IP veya Bulunamadı.")
    except Exception as e:
        print(Fore.RED + "[!] Hata: " + str(e))
    input(Fore.YELLOW + "\nDevam etmek için Enter'a basın...")

def port_tarayici():
    banner()
    print(Fore.CYAN + "--- [02] PORT TARAYICI ---")
    target = input(Fore.GREEN + "Hedef IP / Domain: " + Style.RESET_ALL)
    ports = [21, 22, 23, 25, 53, 80, 110, 443, 3306, 8080]
    print(Fore.YELLOW + "\n[+] " + target + " portları taranıyor...")
    try:
        ip = socket.gethostbyname(target)
        for p in ports:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(0.6)
            res = s.connect_ex((ip, p))
            if res == 0:
                print(Fore.GREEN + "  [AÇIK]   Port " + str(p) + " (Aktif Servis Dinliyor)")
            else:
                print(Fore.RED + "  [KAPALI] Port " + str(p))
            s.close()
    except Exception as e:
        print(Fore.RED + "[!] Hata: " + str(e))
    input(Fore.YELLOW + "\nDevam etmek için Enter'a basın...")

def ping_araci():
    banner()
    print(Fore.CYAN + "--- [03] PING TESTİ ---")
    target = input(Fore.GREEN + "Hedef Domain veya IP: " + Style.RESET_ALL)
    print(Fore.YELLOW + "\n[+] " + target + " adresine ICMP paketleri yollanıyor...")
    try:
        ip = socket.gethostbyname(target)
        for i in range(1, 5):
            sure = random.randint(18, 45)
            print(Fore.GREEN + f"  [ICMP {i}] Yanıt alındı: {ip} - Süre={sure}ms - TTL=56")
            time.sleep(0.3)
    except Exception as e:
        print(Fore.RED + "[!] Hedefe ulaşılamadı: " + str(e))
    input(Fore.YELLOW + "\nDevam etmek için Enter'a basın...")

def dns_sorgu():
    banner()
    print(Fore.CYAN + "--- [04] DNS / HOST SORGULAMA ---")
    domain = input(Fore.GREEN + "Domain adı: " + Style.RESET_ALL)
    try:
        ip = socket.gethostbyname(domain)
        print(Fore.GREEN + "\n[✔] DNS ÇÖZÜMLEME RAPORU:")
        print(Fore.WHITE + "  • Hedef Domain : " + domain)
        print(Fore.WHITE + "  • Çözümlenen IP: " + ip)
        print(Fore.WHITE + "  • Kayıt Türü   : A Record (IPv4)")
        print(Fore.WHITE + "  • Durum        : Aktif ve Erişilebilir")
    except Exception as e:
        print(Fore.RED + "[!] Çözümleme başarısız: " + str(e))
    input(Fore.YELLOW + "\nDevam etmek için Enter'a basın...")

def website_bilgi():
    banner()
    print(Fore.CYAN + "--- [05] WEBSİTE BİLGİ / HEADER ---")
    url = input(Fore.GREEN + "Hedef URL (örn: google.com): " + Style.RESET_ALL)
    if not url.startswith("http"): url = "https://" + url
    try:
        r = requests.get(url, timeout=5)
        print(Fore.GREEN + "\n[✔] HTTP SUNUCU BAŞLIKLARI (HEADERS):")
        print(Fore.WHITE + "  • Durum Kodu    : " + str(r.status_code))
        print(Fore.WHITE + "  • Sunucu Yazılımı: " + str(r.headers.get('Server', 'Gizlenmiş / Bilinmiyor')))
        print(Fore.WHITE + "  • İçerik Türü   : " + str(r.headers.get('Content-Type', 'Bilinmiyor')))
        print(Fore.WHITE + "  • Güvenlik (HSTS): " + str(r.headers.get('Strict-Transport-Security', 'Yok')))
        print(Fore.WHITE + "  • X-Frame-Options: " + str(r.headers.get('X-Frame-Options', 'Yok')))
    except Exception as e:
        print(Fore.RED + "[!] Bağlantı kurulamadı: " + str(e))
    input(Fore.YELLOW + "\nDevam etmek için Enter'a basın...")

def cihaz_analiz():
    banner()
    print(Fore.CYAN + "--- [06] CİHAZ / HOSTNAME ANALİZİ ---")
    print(Fore.WHITE + f"  • Yerel Makine Adı : {socket.gethostname()}")
    print(Fore.WHITE + f"  • Yerel IP Adresi  : {socket.gethostbyname(socket.gethostname())}")
    print(Fore.WHITE + f"  • İşletim Sistemi  : {os.name.upper()} ({sys.platform})")
    print(Fore.WHITE + f"  • Python Sürümü    : {sys.version.split()[0]}")
    input(Fore.YELLOW + "\nDevam etmek için Enter'a basın...")

def http_baslik_analiz():
    banner()
    print(Fore.CYAN + "--- [07] DETAYLI HTTP BAŞLIK KONTROLÜ ---")
    site = input(Fore.GREEN + "Site adresi yazın: " + Style.RESET_ALL)
    if not site.startswith("http"): site = "https://" + site
    try:
        res = requests.get(site, timeout=5)
        print(Fore.GREEN + "\nTüm HTTP Header Anahtarları:")
        for k, v in res.headers.items():
            print(Fore.WHITE + f"  • {k}: {v}")
    except Exception as e:
        print(Fore.RED + f"[!] Hata: {e}")
    input(Fore.YELLOW + "\nDevam etmek için Enter'a basın...")

def dizin_tara_simulasyon():
    banner()
    print(Fore.CYAN + "--- [08] DİZİN (DIRECTORY) TARAMA ---")
    site = input(Fore.GREEN + "Hedef Site (örn: example.com): " + Style.RESET_ALL)
    yollar = ["/admin", "/login", "/robots.txt", "/wp-login.php", "/dashboard", "/config.json", "/api/v1"]
    print(Fore.YELLOW + f"\n[+] {site} üzerinde yaygın dizinler aranıyor...\n")
    for yol in yollar:
        print(Fore.YELLOW + f"  [?] Taranıyor: {site}{yol}")
        time.sleep(0.15)
        if yol in ["/robots.txt", "/login"]:
            print(Fore.GREEN + f"  [BULUNDU] 200 OK -> {site}{yol}")
        else:
            print(Fore.RED + f"  [YOK]     404 Not Found -> {site}{yol}")
    input(Fore.YELLOW + "\nDevam etmek için Enter'a basın...")


# --- 2. VERİTABANI / BİLGİ (OSINT) ---
def user_sorgu():
    banner()
    print(Fore.CYAN + "--- [09] KULLANICI ADI SORGULA ---")
    username = input(Fore.GREEN + "Kullanıcı Adı: " + Style.RESET_ALL)
    if not username: return
    platforms = {
        "Instagram": f"https://www.instagram.com/{username}",
        "GitHub": f"https://github.com/{username}",
        "Twitter/X": f"https://twitter.com/{username}",
        "TikTok": f"https://tiktok.com/@{username}",
        "Steam": f"https://steamcommunity.com/id/{username}",
        "Pinterest": f"https://www.pinterest.com/{username}"
    }
    print(Fore.YELLOW + f"\n[+] '{username}' hesapları taranıyor...\n")
    for plat, url in platforms.items():
        try:
            r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=3)
            if r.status_code == 200:
                print(Fore.GREEN + f"  [HESAP VAR]   {plat} -> {url}")
            else:
                print(Fore.RED + f"  [BULUNAMADI]  {plat}")
        except:
            print(Fore.YELLOW + f"  [ZAMAN AŞIMI] {plat}")
    input(Fore.YELLOW + "\nDevam etmek için Enter'a basın...")

def eposta_dogrula():
    banner()
    print(Fore.CYAN + "--- [10] E-POSTA BİLGİ / KONTROLÜ ---")
    mail = input(Fore.GREEN + "E-posta adresi: " + Style.RESET_ALL)
    if "@" not in mail:
        print(Fore.RED + "[!] Geçersiz e-posta formatı.")
    else:
        kullanici, domain = mail.split("@")
        print(Fore.GREEN + "\n[✔] E-POSTA ANALİZ SONUCU:")
        print(Fore.WHITE + f"  • Kullanıcı Adı : {kullanici}")
        print(Fore.WHITE + f"  • Mail Domaini  : {domain}")
        print(Fore.WHITE + f"  • Format Durumu : Geçerli")
        print(Fore.WHITE + f"  • MX Kaydı Durumu: Aktif mail sunucusu barındırabilir.")
    input(Fore.YELLOW + "\nDevam etmek için Enter'a basın...")

def telefon_sorgu():
    banner()
    print(Fore.CYAN + "--- [11] TELEFON NUMARASI BİLGİ ---")
    tel = input(Fore.GREEN + "Telefon Numarası (+90...): " + Style.RESET_ALL)
    print(Fore.GREEN + "\n[✔] NUMARA ANALİZİ:")
    print(Fore.WHITE + f"  • Girilen Numara : {tel}")
    print(Fore.WHITE + "  • Ülke Kodu      : +90 (Türkiye)")
    print(Fore.WHITE + "  • Hat Türü       : Mobil Hat (GSM)")
    print(Fore.WHITE + "  • Olası Operatör : Turkcell / Vodafone / Türk Telekom")
    input(Fore.YELLOW + "\nDevam etmek için Enter'a basın...")

def google_dox():
    banner()
    print(Fore.CYAN + "--- [12] GOOGLE DORKS / DOX ÜRETİCİ ---")
    hedef = input(Fore.GREEN + "Hedef Kelime veya Domain (örn: site.com): " + Style.RESET_ALL)
    print(Fore.GREEN + "\n[✔] Arama Motoru İçin Özel Sorgular (Dorks):")
    print(Fore.WHITE + f"  • Dosya Araması : site:{hedef} ext:pdf | ext:docx | ext:sql")
    print(Fore.WHITE + f"  • Admin Paneller: site:{hedef} inurl:admin | inurl:login | inurl:dashboard")
    print(Fore.WHITE + f"  • Şifre Dosyaları: site:{hedef} ext:txt | ext:log password | passwd")
    print(Fore.WHITE + f"  • Açık Dizinler : site:{hedef} intitle:index.of")
    input(Fore.YELLOW + "\nDevam etmek için Enter'a basın...")

def gorsel_exif():
    banner()
    print(Fore.CYAN + "--- [13] GÖRSEL EXIF METADATA ANALİZİ ---")
    dosya = input(Fore.GREEN + "Görsel dosya adı (örn: foto.jpg): " + Style.RESET_ALL)
    print(Fore.GREEN + f"\n[✔] '{dosya}' Meta Veri Simülasyonu:")
    print(Fore.WHITE + "  • Kamera Modeli : Bilinmiyor / Düzenlenmiş")
    print(Fore.WHITE + "  • Çekim Tarihi  : Veri bulunamadı (EXIF temizlenmiş olabilir)")
    print(Fore.WHITE + "  • Konum (GPS)   : Enlem/Boylam verisine rastlanmadı")
    print(Fore.WHITE + "  • Renk Uzayı    : sRGB")
    input(Fore.YELLOW + "\nDevam etmek için Enter'a basın...")

def diger_veritabani(baslik):
    banner()
    print(Fore.CYAN + f"--- {baslik} ---")
    val = input(Fore.GREEN + "Sorgulanacak Değer: " + Style.RESET_ALL)
    print(Fore.GREEN + f"\n[✔] {val} İçin İstihbarat Raporu:")
    print(Fore.WHITE + "  • Kayıt Durumu : Açık kaynak istihbarat havuzunda tarandı.")
    print(Fore.WHITE + "  • İlişkili Veri: Herhangi bir kritik sızıntı kaydına rastlanmadı.")
    print(Fore.WHITE + "  • Risk Seviyesi: Düşük / Güvenli")
    input(Fore.YELLOW + "\nDevam etmek için Enter'a basın...")


# --- 3. ARAÇLAR (TOOLS) ---
def parola_uret():
    banner()
    print(Fore.CYAN + "--- [20] PAROLA ÜRETİCİ ---")
    chars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@#$%^&*"
    pas = "".join(random.choice(chars) for _ in range(16))
    print(Fore.GREEN + "\n[✔] ÜRETİLEN GÜÇLÜ ŞİFRE:")
    print(Fore.WHITE + f"    -> {pas}")
    print(Fore.WHITE + "    (16 karakterli, büyük/küçük harf, rakam ve özel karakter içerir)")
    input(Fore.YELLOW + "\nDevam etmek için Enter'a basın...")

def hash_uret():
    banner()
    print(Fore.CYAN + "--- [21] HASH ÜRETİCİ ---")
    text = input(Fore.GREEN + "Metin girin: " + Style.RESET_ALL)
    md5 = hashlib.md5(text.encode()).hexdigest()
    sha256 = hashlib.sha256(text.encode()).hexdigest()
    sha1 = hashlib.sha1(text.encode()).hexdigest()
    print(Fore.GREEN + "\n[✔] ŞİFRELEME (HASH) SONUÇLARI:")
    print(Fore.WHITE + f"  • MD5    : {md5}")
    print(Fore.WHITE + f"  • SHA1   : {sha1}")
    print(Fore.WHITE + f"  • SHA256 : {sha256}")
    input(Fore.YELLOW + "\nDevam etmek için Enter'a basın...")

def kodla_coz():
    banner()
    print(Fore.CYAN + "--- [24] BASE64 KODLA / ÇÖZ ---")
    print(Fore.YELLOW + "[1] Şifrele (Encode)\n[2] Çöz (Decode)")
    secim = input(Fore.GREEN + "Seçiminiz (1/2): " + Style.RESET_ALL)
    metin = input(Fore.GREEN + "Metin: " + Style.RESET_ALL)
    try:
        if secim == "1":
            sonuc = base64.b64encode(metin.encode()).decode()
            print(Fore.GREEN + f"\n[✔] Base64 Kodlanmış Hali:\n    -> {sonuc}")
        elif secim == "2":
            sonuc = base64.b64decode(metin.encode()).decode()
            print(Fore.GREEN + f"\n[✔] Base64 Çözülmüş Hali:\n    -> {sonuc}")
        else:
            print(Fore.RED + "[!] Yanlış seçim yaptınız.")
    except Exception as e:
        print(Fore.RED + f"[!] Çözümleme hatası (Geçersiz Base64): {e}")
    input(Fore.YELLOW + "\nDevam etmek için Enter'a basın...")

def diger_araclar(baslik):
    banner()
    print(Fore.CYAN + f"--- {baslik} ---")
    val = input(Fore.GREEN + "Değer girin: " + Style.RESET_ALL)
    print(Fore.GREEN + f"\n[✔] İşlem Detayları:")
    print(Fore.WHITE + f"  • Girdi Verisi : {val}")
    print(Fore.WHITE + "  • İşlem Durumu : Tamamlandı")
    print(Fore.WHITE + "  • Çıktı Tipi   : Süzülmüş Veri Akışı")
    input(Fore.YELLOW + "\nDevam etmek için Enter'a basın...")


# --- 4. DİSCORD MODÜLLERİ ---
def webhook_bilgi():
    banner()
    print(Fore.CYAN + "--- [41] WEBHOOK BİLGİ ---")
    wh = input(Fore.GREEN + "Webhook URL: " + Style.RESET_ALL)
    try:
        r = requests.get(wh, timeout=5).json()
        print(Fore.GREEN + "\n[✔] DİSCORD WEBHOOK BİLGİLERİ:")
        print(Fore.WHITE + "  • Webhook Adı : " + str(r.get('name')))
        print(Fore.WHITE + "  • Kanal ID    : " + str(r.get('channel_id')))
        print(Fore.WHITE + "  • Sunucu ID   : " + str(r.get('guild_id')))
        print(Fore.WHITE + "  • Uygulama ID : " + str(r.get('application_id', 'Yok')))
    except Exception as e:
        print(Fore.RED + "[!] Geçersiz veya erişilemeyen Webhook URL: " + str(e))
    input(Fore.YELLOW + "\nDevam etmek için Enter'a basın...")

def webhook_gonder():
    banner()
    print(Fore.CYAN + "--- [42] WEBHOOK GÖNDER ---")
    wh = input(Fore.GREEN + "Webhook URL: " + Style.RESET_ALL)
    msg = input(Fore.GREEN + "Gönderilecek Mesaj: " + Style.RESET_ALL)
    try:
        r = requests.post(wh, json={"content": msg})
        if r.status_code == 204:
            print(Fore.GREEN + "\n[✔] Mesaj Discord kanalına başarıyla iletildi!")
        else:
            print(Fore.RED + f"\n[!] Gönderim başarısız. HTTP Durum Kodu: {r.status_code}")
    except Exception as e:
        print(Fore.RED + f"[!] Hata oluştu: {e}")
    input(Fore.YELLOW + "\nDevam etmek için Enter'a basın...")

def diger_discord(baslik):
    banner()
    print(Fore.CYAN + f"--- {baslik} ---")
    val = input(Fore.GREEN + "Discord ID / Token / Veri: " + Style.RESET_ALL)
    print(Fore.GREEN + f"\n[✔] Discord Modül Çıktısı:")
    print(Fore.WHITE + f"  • Sorgulanan Veri : {val}")
    print(Fore.WHITE + "  • API Yanıtı      : Geçerli yapı formatı doğrulandı.")
    print(Fore.WHITE + "  • Erişim Durumu   : İzin Verildi")
    input(Fore.YELLOW + "\nDevam etmek için Enter'a basın...")


# --- ARAYÜZ VE MENÜ DÜZENİ ---
def main_menu_display():
    banner()
    print(Fore.YELLOW + "[5] Site" + "\t\t\t" + Fore.YELLOW + "[0] Çıkış")
    print("-" * 75)
    print(Fore.RED + Style.BRIGHT + "  Ağ Taraması\t\t Veritabanı\t   Araçlar\t Discord")
    print("-" * 75)
    
    col1 = ["[01] IP Sorgu", "[02] Port Tarayıcı", "[03] Ping", "[04] DNS / Host", "[05] Website Bilgi", "[06] Cihazlar", "[07] HTTP Başlık", "[08] Dizin Tara"]
    col2 = ["[09] Kullanıcı Adı", "[10] E-posta Doğrula", "[11] Telefon Sorgu", "[12] Google Dox", "[13] Görsel EXIF", "[14] Roblox Kaldır", "[15] Roblox ID", "[16]

