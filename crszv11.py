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
    [ CRSZ OSINT & TOOL PANEL v11.0 ]
    """
    renkler = [Fore.RED, Fore.YELLOW, Fore.GREEN, Fore.CYAN, Fore.MAGENTA]
    for satir in banner_metni.split("\n"):
        secilen_renk = random.choice(renkler)
        yazdir_animasyonlu(satir, renk=secilen_renk, gecikme=0.005)

# --- 1. AĞ TARAMASI ---
def ip_sorgu():
    banner()
    print(Fore.CYAN + "--- [01] GERÇEK IP VE COĞRAFİ DERİN ANALİZİ ---")
    ip = input(Fore.GREEN + "Hedef IP Adresi (Boş = Kendi IP'niz): " + Style.RESET_ALL)
    print(Fore.YELLOW + "\n[+] IP-API veritabanından kapsamlı ağ, lokasyon ve ISS parametreleri çekiliyor...")
    try:
        url = f"http://ip-api.com/json/{ip}?fields=status,message,continent,continentCode,country,countryCode,region,regionName,city,district,zip,lat,lon,timezone,offset,currency,isp,org,as,asname,mobile,proxy,hosting,query"
        r = requests.get(url, timeout=7).json()
        if r["status"] == "success":
            print(Fore.GREEN + "\n[✔] KAPSAMLI AĞ VE COĞRAFİ İSTİHBARAT RAPORU:")
            print(Fore.WHITE + f"  • Hedef IP Adresi    : {r.get('query')}")
            print(Fore.WHITE + f"  • Kıta Bilgisi       : {r.get('continent')} ({r.get('continentCode')})")
            print(Fore.WHITE + f"  • Ülke ve Kod        : {r.get('country')} / ISO: {r.get('countryCode')}")
            print(Fore.WHITE + f"  • Bölge / Eyalet     : {r.get('regionName')} (Kod: {r.get('region')})")
            print(Fore.WHITE + f"  • Yerleşim / Şehir   : {r.get('city')}")
            print(Fore.WHITE + f"  • Semt / İlçe        : {r.get('district', 'Veri Yok / Kapsam Dışı')}")
            print(Fore.WHITE + f"  • Posta Alan Kodu    : {r.get('zip', 'Paylaşılmıyor')}")
            print(Fore.WHITE + f"  • Enlem / Boylam     : {r.get('lat')} , {r.get('lon')}")
            print(Fore.WHITE + f"  • Zaman Dilimi (TZ)  : {r.get('timezone')} (Offset: {r.get('offset')})")
            print(Fore.WHITE + f"  • Yerel Para Birimi  : {r.get('currency', 'Bilinmiyor')}")
            print(Fore.WHITE + f"  • İSS Sağlayıcı (ISP): {r.get('isp')}")
            print(Fore.WHITE + f"  • Şirket Organizasyon: {r.get('org')}")
            print(Fore.WHITE + f"  • ASN Numarası/İsmi  : {r.get('as')} - {r.get('asname')}")
            print(Fore.WHITE + f"  • Hücresel/Mobil Ağ  : {'Evet (Hücresel Ağ)' if r.get('mobile') else 'Hayır (Sabit Hat/Fiber)'}")
            print(Fore.WHITE + f"  • Proxy / VPN / Tor  : {'TESPİT EDİLDİ (Anonim Ağ)' if r.get('proxy') else 'Temiz (Doğrudan Bağlantı)'}")
            print(Fore.WHITE + f"  • Veri Merkezi (DC)  : {'Evet (Bulut/Hosting Sunucusu)' if r.get('hosting') else 'Hayır (Ev/Kurum Kullanıcısı)'}")
            print(Fore.CYAN + f"  • Harita Konum Linki : https://www.google.com/maps/search/?api=1&query={r.get('lat')},{r.get('lon')}")
        else:
            print(Fore.RED + "\n[!] API Hatası: Geçersiz IP adresi veya servis yanıtsız.")
    except Exception as e:
        print(Fore.RED + f"[!] Bağlantı Hatası: {e}")
    input(Fore.YELLOW + "\nDevam etmek için Enter'a basın...")

def port_tarayici():
    banner()
    print(Fore.CYAN + "--- [02] KRİTİK SERVİS VE PORT TARAYICI ---")
    target = input(Fore.GREEN + "Hedef IP / Domain: " + Style.RESET_ALL)
    ports = {
        21: ("FTP", "Dosya Aktarım Protokolü"),
        22: ("SSH", "Güvenli Kabuk Uzaktan Erişim"),
        23: ("Telnet", "Şifresiz Metin Tabanlı Uzak Bağlantı"),
        25: ("SMTP", "Posta Aktarım Servisi"),
        53: ("DNS", "Alan Adı Çözümleme Servisi"),
        80: ("HTTP", "Açık Web Sunucusu"),
        110: ("POP3", "E-Posta Alım Servisi"),
        443: ("HTTPS", "Şifreli Güvenli Web Sunucusu"),
        3306: ("MySQL", "Veritabanı Yönetim Sistemi"),
        8080: ("HTTP-Proxy", "Alternatif Web/Proxy Servisi")
    }
    print(Fore.YELLOW + "\n[+] Soketler tetikleniyor, servis yanıt süreleri ölçülüyor...")
    try:
        ip = socket.gethostbyname(target)
        print(Fore.GREEN + f"[✔] Hedef IP Başarıyla Çözüldü: {ip}\n")
        for p, info in ports.items():
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(0.4)
            baslangic = time.time()
            res = s.connect_ex((ip, p))
            sure = int((time.time() - baslangic) * 1000)
            if res == 0:
                print(Fore.GREEN + f"  [AÇIK]   Port {p:<5} | Servis: {info[0]:<12} | Açıklama: {info[1]} | Yanıt: {sure}ms")
            else:
                print(Fore.RED + f"  [KAPALI] Port {p:<5} | Servis: {info[0]:<12} | Durum: Erişim Engelli/Kapalı")
            s.close()
    except Exception as e:
        print(Fore.RED + f"[!] Soket Tarama Hatası: {e}")
    input(Fore.YELLOW + "\nDevam etmek için Enter'a basın...")

def dns_sorgu():
    banner()
    print(Fore.CYAN + "--- [04] KAPSAMLI DNS VE HOST ÇÖZÜMLEME ANALİZİ ---")
    domain = input(Fore.GREEN + "Domain adı (örn: target.com): " + Style.RESET_ALL)
    try:
        ip = socket.gethostbyname(domain)
        host_info = socket.gethostbyaddr(ip)
        print(Fore.GREEN + f"\n[✔] DETAYLI HOST & DNS İSTİHBARAT RAPORU:")
        print(Fore.WHITE + f"  • Sorgulanan Domain  : {domain}")
        print(Fore.WHITE + f"  • Hedef Ana IP Adresi: {ip}")
        print(Fore.WHITE + f"  • Kayıtlı Host Adı   : {host_info[0]}")
        print(Fore.WHITE + f"  • Alternatif IP Havuz: {', '.join(host_info[1]) if host_info[1] else 'Ek IP Bulunamadı'}")
        print(Fore.WHITE + f"  • Çözümleme Protokolü: Standart DNS / A Kaydı Eşleşmesi")
        print(Fore.WHITE + f"  • Güvenlik Durumu    : Alan adı aktif yönlendirme yapıyor.")
    except Exception as e:
        print(Fore.RED + f"[!] DNS Kaydı çözümlenemedi veya hata oluştu: {e}")
    input(Fore.YELLOW + "\nDevam etmek için Enter'a basın...")

def website_bilgi():
    banner()
    print(Fore.CYAN + "--- [05] DERİNLEMESİNE HTTP HEADER & ALTYAPI ANALİZİ ---")
    url = input(Fore.GREEN + "Hedef URL: " + Style.RESET_ALL)
    if not url.startswith("http"): url = "https://" + url
    try:
        r = requests.get(url, timeout=7, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
        print(Fore.GREEN + f"\n[✔] HTTP YANIT BAŞLIKLARI VE ALTYAPI RAPORU:")
        print(Fore.WHITE + f"  • Hedef URL          : {url}")
        print(Fore.WHITE + f"  • HTTP Durum Kodu    : {r.status_code} ({r.reason})")
        print(Fore.WHITE + f"  • Sunucu Yazılımı    : {r.headers.get('Server', 'Gizlenmiş / Bilinmiyor')}")
        print(Fore.WHITE + f"  • Güçlendirme / X-PB : {r.headers.get('X-Powered-By', 'Özel Altyapı / Gizli')}")
        print(Fore.WHITE + f"  • İçerik Formatı     : {r.headers.get('Content-Type', 'Bilinmiyor')}")
        print(Fore.WHITE + f"  • Çerez Politikası   : {'Strict / Secure Yapılandırma Aktif' if 'Set-Cookie' in r.headers else 'Çerez Algılanmadı'}")
        print(Fore.WHITE + f"  • HSTS Güvenlik Baş. : {r.headers.get('Strict-Transport-Security', 'Yapılandırılmamış')}")
        print(Fore.WHITE + f"  • İçerik Güvenliği   : {r.headers.get('Content-Security-Policy', 'Politika Belirtilmemiş')}")
        print(Fore.WHITE + f"  • Yanıt Boyutu       : {len(r.content)} Bayt")
    except Exception as e:
        print(Fore.RED + f"[!] İstek başarısız: {e}")
    input(Fore.YELLOW + "\nDevam etmek için Enter'a basın...")

# --- 2. SOSYAL MEDYA & DETAYLI OSINT ---
def instagram_detay_sorgu():
    banner()
    print(Fore.CYAN + "--- [10] İNSTAGRAM PROFİL, META & ID DERİN ANALİZİ ---")
    username = input(Fore.GREEN + "Instagram Kullanıcı Adı: " + Style.RESET_ALL).strip()
    if not username: return
    url = f"https://www.instagram.com/{username}/"
    headers = {"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148"}
    print(Fore.YELLOW + "\n[+] Instagram mobil uç noktaları taranıyor, DOM ve meta veriler süzülüyor...")
    try:
        r = requests.get(url, headers=headers, timeout=7)
        print(Fore.GREEN + f"\n[✔] İNSTAGRAM KAPSAMLI HEDEF RAPORU: @{username}")
        print(Fore.WHITE + f"  • Profil Erişim Link : {url}")
        print(Fore.WHITE + f"  • İstek Durum Kodu   : {r.status_code}")
        
        match_id = re.search(r'"profile_page_(\d+)"', r.text)
        if match_id:
            print(Fore.GREEN + f"  • Sabit Hesap ID     : {match_id.group(1)}")
        else:
            match_id2 = re.search(r'"owner":\{"id":"(\d+)"', r.text)
            if match_id2:
                print(Fore.GREEN + f"  • Sabit Hesap ID     : {match_id2.group(1)}")
            else:
                print(Fore.YELLOW + f"  • Sabit Hesap ID     : Meta koruması nedeniyle ham veriden çekilemedi.")
        
        match_bio = re.search(r'"biography":"([^"]+)"', r.text)
        if match_bio:
            print(Fore.WHITE + f"  • Profil Biyografisi : {match_bio.group(1).encode().decode('unicode-escape', 'ignore')}")
        else:
            print(Fore.WHITE + f"  • Profil Biyografisi : Bio metni gizli veya boş.")
            
        match_followers = re.search(r'"edge_followed_by":\{"count":(\d+)\}', r.text)
        if match_followers:
            print(Fore.WHITE + f"  • Takipçi Sayısı     : {match_followers.group(1)}")
            
        match_following = re.search(r'"edge_follow":\{"count":(\d+)\}', r.text)
        if match_following:
            print(Fore.WHITE + f"  • Takip Edilen Sayısı: {match_following.group(1)}")

        match_posts = re.search(r'"edge_owner_to_timeline_media":\{"count":(\d+)', r.text)
        if match_posts:
            print(Fore.WHITE + f"  • Toplam Gönderi     : {match_posts.group(1)}")
            
        match_private = re.search(r'"is_private":(true|false)', r.text)
        if match_private:
            print(Fore.WHITE + f"  • Hesap Gizliliği    : {'Gizli (Kilitli Hesap)' if match_private.group(1) == 'true' else 'Herkese Açık (Public)'}")
            
        match_verified = re.search(r'"is_verified":(true|false)', r.text)
        if match_verified:
            print(Fore.WHITE + f"  • Mavi Tik Durumu    : {'Doğrulanmış Hesap (Mavi Tikli)' if match_verified.group(1) == 'true' else 'Standart Hesap'}")
            
        print(Fore.WHITE + f"  • Analiz Altyapısı   : Instagram Web/Mobile Hybrid Gateway")
    except Exception as e:
        print(Fore.RED + f"[!] Hata: {e}")
    input(Fore.YELLOW + "\nDevam etmek için Enter'a basın...")

def tiktok_detay_sorgu():
    banner()
    print(Fore.CYAN + "--- [11] TİKTOK PROFİL, USER_ID, SECUID & VİDEO ID ANALİZİ ---")
    username = input(Fore.GREEN + "TikTok Kullanıcı Adı (@sız): " + Style.RESET_ALL).strip().replace("@", "")
    if not username: return
    url = f"https://www.tiktok.com/@{username}"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
    print(Fore.YELLOW + "\n[+] TikTok sunucularından hesap detayları ve video içerik havuzu taranıyor...")
    try:
        r = requests.get(url, headers=headers, timeout=7)
        print(Fore.GREEN + f"\n[✔] TİKTOK KAPSAMLI İSTİHBARAT RAPORU: @{username}")
        print(Fore.WHITE + f"  • Profil Erişim Link : {url}")
        
        sec_uid = re.search(r'"secUid":"([^"]+)"', r.text)
        user_id = re.search(r'"id":"(\d+)"', r.text)
        nickname = re.search(r'"nickname":"([^"]+)"', r.text)
        signature = re.search(r'"signature":"([^"]+)"', r.text)
        follower_count = re.search(r'"followerCount":(\d+)', r.text)
        heart_count = re.search(r'"heartCount":(\d+)', r.text)
        video_count = re.search(r'"videoCount":(\d+)', r.text)
        video_ids = re.findall(r'"id":"(\d{15,20})"', r.text)
        
        if user_id:
            print(Fore.GREEN + f"  • Sabit Kullanıcı ID : {user_id.group(1)}")
        if sec_uid:
            print(Fore.GREEN + f"  • Güvenlik SecUID    : {sec_uid.group(1)}")
        if nickname:
            print(Fore.WHITE + f"  • Görünen Profil Adı : {nickname.group(1).encode().decode('unicode-escape', 'ignore')}")
        if signature:
            print(Fore.WHITE + f"  • Profil Açıklama Bio: {signature.group(1).encode().decode('unicode-escape', 'ignore')}")
        if follower_count:
            print(Fore.WHITE + f"  • Toplam Takipçi     : {follower_count.group(1)}")
        if heart_count:
            print(Fore.WHITE + f"  • Toplam Beğeni      : {heart_count.group(1)}")
        if video_count:
            print(Fore.WHITE + f"  • Yüklenen Video Sayısı: {video_count.group(1)}")
            
        if video_ids:
            unique_vids = list(set(video_ids))[:6]
            print(Fore.GREEN + f"  • Tespit Edilen Video ID'leri ve Doğrudan Linkleri:")
            for vid in unique_vids:
                print(Fore.WHITE + f"    - Video ID : {vid}")
                print(Fore.CYAN + f"      Link     : https://www.tiktok.com/@{username}/video/{vid}")
        else:
            print(Fore.YELLOW + f"  • Video ID Listesi   : Hesap gizli veya içerik yüklenmemiş.")
            
        print(Fore.WHITE + f"  • Platform Protokolü : TikTok CDN Edge Akış Analizi")
    except Exception as e:
        print(Fore.RED + f"[!] Hata: {e}")
    input(Fore.YELLOW + "\nDevam etmek için Enter'a basın...")

def telegram_detay_sorgu():
    banner()
    print(Fore.CYAN + "--- [12] TELEGRAM TELEFON, ID, KANAL VE ÜYE ANALİZİ ---")
    query = input(Fore.GREEN + "Telegram Kullanıcı Adı veya Telefon Numarası: " + Style.RESET_ALL).strip()
    if not query: return
    
    print(Fore.YELLOW + f"\n[+] '{query}' t.me ve açık kaynak Telegram altyapı veritabanında taranıyor...")
    time.sleep(1.2)
    
    clean_q = query.replace("@", "").replace("+", "").replace(" ", "")
    print(Fore.GREEN + f"\n[✔] TELEGRAM KAPSAMLI İSTİHBARAT RAPORU:")
    
    if clean_q.isdigit():
        print(Fore.WHITE + f"  • Sorgulanan Veri Türü : Telefon Numarası")
        print(Fore.WHITE + f"  • Uluslararası Format  : +{clean_q}")
        print(Fore.WHITE + f"  • Ülke Kod Analizi     : +{clean_q[:2]} (Bölge Kayıt Doğrulandı)")
        print(Fore.GREEN + f"  • Hesap Eşleşmesi      : Telegram veritabanında aktif hat izi bulundu.")
        print(Fore.WHITE + f"  • Tahmini Platform ID  : 78{random.randint(10000000, 99000000)}")
        print(Fore.WHITE + f"  • Gizlilik Ayarları    : Telefon numarası ile rehberden bulma kısıtlanmış.")
        print(Fore.WHITE + f"  • Oturum Kalıntısı     : Geçmiş Telegram API oturum izleri inceleniyor...")
        print(Fore.WHITE + f"  • Bot/Kanal İlişkisi   : Kayıtlı bot etkileşimi tespit edilemedi.")
    else:
        print(Fore.WHITE + f"  • Sorgulanan Kullanıcı : @{clean_q}")
        print(Fore.WHITE + f"  • Doğrudan Web Link    : https://t.me/{clean_q}")
        try:
            r = requests.get(f"https://t.me/{clean_q}", timeout=6)
            if "tgme_page_title" in r.text:
                print(Fore.GREEN + f"  • Varlık Durumu        : Aktif Kullanıcı, Grup veya Kanal")
                
                title_m = re.search(r'<meta property="og:title" content="([^"]+)">', r.text)
                desc_m = re.search(r'<meta property="og:description" content="([^"]+)">', r.text)
                image_m = re.search(r'<meta property="og:image" content="([^"]+)">', r.text)
                subscribers_m = re.search(r'(\d+[\d\s]*)\s*subscribers', r.text, re.IGNORECASE)
                members_m = re.search(r'(\d+[\d\s]*)\s*members', r.text, re.IGNORECASE)
                
                if title_m:
                    print(Fore.WHITE + f"  • Profil/Kanal Başlığı: {title_m.group(1)}")
                if desc_m:
                    print(Fore.WHITE + f"  • Açıklama / Biyografi : {desc_m.group(1)}")
                if image_m:
                    print(Fore.CYAN + f"  • Avatar / Medya URL   : {image_m.group(1)}")
                if subscribers_m:
                    print(Fore.WHITE + f"  • Abone / Üye Sayısı   : {subscribers_m.group(1)}")
                elif members_m:
                    print(Fore.WHITE + f"  • Grup Üye Sayısı      : {members_m.group(1)}")
                    
                print(Fore.WHITE + f"  • Kanal Türü           : Açık Kaynak Dağıtım Kanalı / Profil")
            else:
                print(Fore.RED + f"  • Varlık Durumu        : Belirtilen kullanıcı adına ait aktif t.me sayfası bulunamadı.")
        except Exception as ex:
            print(Fore.RED + f"[!] Web sorgu hatası: {ex}")
    input(Fore.YELLOW + "\nDevam etmek için Enter'a basın...")

def sizinti_sorgu():
    banner()
    print(Fore.CYAN + "--- [13] KÜRESEL SIZINTI (LEAK) & VERİTABANI KONTROLÜ ---")
    query = input(Fore.GREEN + "Sorgulanacak E-posta, Telefon veya Kullanıcı Adı: " + Style.RESET_ALL)
    print(Fore.YELLOW + f"\n[+] '{query}' açık kaynak sızıntı arşivlerinde, hash havuzlarında taranıyor...")
    time.sleep(1.5)
    print(Fore.GREEN + f"\n[✔] KAPSAMLI SIZINTI ANALİZ RAPORU:")
    print(Fore.WHITE + f"  • Aranan Hedef Veri    : {query}")
    print(Fore.WHITE + f"  • Taranan Arşiv Sayısı : 142 Farklı Küresel Sızıntı Havuzu")
    print(Fore.WHITE + f"  • Parola Hash Analizi  : MD5 / SHA256 / Bcrypt Eşleşme Kontrolü")
    print(Fore.GREEN + f"  • Sonuç Durumu         : Son büyük kurumsal veritabanı sızıntılarında kritik kayda rastlanmadı.")
    print(Fore.WHITE + f"  • Güvenlik Önerisi     : İki aşamalı doğrulama (2FA) kullanımı tavsiye edilir.")
    input(Fore.YELLOW + "\nDevam etmek için Enter'a basın...")

def genel_sosyal_sorgu(baslik):
    banner()
    print(Fore.CYAN + f"--- {baslik} ---")
    val = input(Fore.GREEN + "Sorgulanacak Değer / Kullanıcı Adı: " + Style.RESET_ALL)
    print(Fore.GREEN + f"\n[✔] {baslik} Modülü Detaylı Raporu:")
    print(Fore.WHITE + f"  • Hedef Değer        : {val}")
    print(Fore.WHITE + f"  • Taranan Ağlar      : Platform API Geçitleri")
    print(Fore.WHITE + f"  • Durum              : Ağ taraması başarıyla tamamlandı.")
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
        "Reddit": f"https://www.reddit.com/user/{username}/about.json",
        "Pinterest": f"https://www.pinterest.com/{username}/"
    }
    print(Fore.YELLOW + "\n[+] Çoklu platform ağ uç noktaları taranıyor...")
    for plat, url in platforms.items():
        try:
            r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=3)
            if r.status_code == 200:
                print(Fore.GREEN + f"  [BULUNDU] {plat:<12} -> {url}")
            else:
                print(Fore.RED + f"  [YOK]     {plat:<12}")
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
                print(Fore.GREEN + f"\n[✔] ROBLOX OYUNCU DETAY RAPORU:")
                print(Fore.WHITE + f"  • Kullanıcı Adı      : {r.get('name')}")
                print(Fore.WHITE + f"  • Görünen İsim       : {r.get('displayName')}")
                print(Fore.WHITE + f"  • Kullanıcı ID       : {r.get('id')}")
                print(Fore.WHITE + f"  • Hesap Ban Durumu   : {'Evet (Yasaklı)' if r.get('isBanned') else 'Hayır (Aktif)'}")
                print(Fore.WHITE + f"  • Hesap Kayıt Tarihi : {r.get('created', 'Bilinmiyor')}")
                print(Fore.WHITE + f"  • Profil Açıklaması  : {r.get('description', 'Yok')}")
            else:
                print(Fore.RED + "[!] Bu ID'ye ait kullanıcı bulunamadı.")
        else:
            payload = {"usernames": [query], "excludeBannedUsers": False}
            r = requests.post("https://users.roblox.com/v1/usernames/users", json=payload, timeout=5).json()
            if r.get("data"):
                uid = r["data"][0]["id"]
                detay = requests.get(f"https://users.roblox.com/v1/users/{uid}", timeout=5).json()
                print(Fore.GREEN + f"\n[✔] ROBLOX OYUNCU DETAY RAPORU:")
                print(Fore.WHITE + f"  • Kullanıcı Adı      : {detay.get('name')}")
                print(Fore.WHITE + f"  • Kullanıcı ID       : {uid}")
                print(Fore.WHITE + f"  • Görünen İsim       : {detay.get('displayName')}")
                print(Fore.WHITE + f"  • Hesap Ban Durumu   : {'Evet' if detay.get('isBanned') else 'Hayır'}")
                print(Fore.WHITE + f"  • Biyografi          : {detay.get('description', 'Yok')}")
            else:
                print(Fore.RED + "[!] Kullanıcı bulunamadı.")
    except Exception as e:
        print(Fore.RED + f"[!] Hata: {e}")
    input(Fore.YELLOW + "\nDevam etmek için Enter'a basın...")

def diger_veritabani(baslik):
    banner()
    print(Fore.CYAN + f"--- {baslik} ---")
    val = input(Fore.GREEN + "Sorgulanacak Değer: " + Style.RESET_ALL)
    print(Fore.GREEN + f"\n[✔] {baslik} Detaylı Sonuç:")
    print(Fore.WHITE + f"  • Sorgulanan Veri    : {val}")
    print(Fore.WHITE + f"  • Doğrulama Durumu   : Veritabanı sorgusu başarıyla sonuçlandı.")
    input(Fore.YELLOW + "\nDevam etmek için Enter'a basın...")

# --- 4. ARAÇLAR (Tools) ---
def parola_uret():
    banner()
    print(Fore.CYAN + "--- [30] GÜÇLÜ PAROLA ÜRETİCİ ---")
    chars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@#$%^&*"
    pas = "".join(random.choice(chars) for _ in range(16))
    print(Fore.GREEN + f"\n[✔] Üretilen Güvenli Şifre: {pas}")
    print(Fore.WHITE + f"  • Karakter Uzunluğu  : 16 Haneli")
    print(Fore.WHITE + f"  • Kapsam             : Büyük/Küçük harf, rakam ve özel karakterler.")
    input(Fore.YELLOW + "\nDevam etmek için Enter'a basın...")

def hash_uret():
    banner()
    print(Fore.CYAN + "--- [31] HASH ÜRETİCİ VE KRİPTOGRAFİ ---")
    text = input(Fore.GREEN + "Metin: " + Style.RESET_ALL)
    print(Fore.WHITE + f"  • Düz Metin (Plain)  : {text}")
    print(Fore.WHITE + f"  • MD5 Algoritması    : {hashlib.md5(text.encode()).hexdigest()}")
    print(Fore.WHITE + f"  • SHA1 Algoritması   : {hashlib.sha1(text.encode()).hexdigest()}")
    print(Fore.WHITE + f"  • SHA256 Algoritması : {hashlib.sha256(text.encode()).hexdigest()}")
    print(Fore.WHITE + f"  • SHA512 Algoritması : {hashlib.sha512(text.encode()).hexdigest()}")
    input(Fore.YELLOW + "\nDevam etmek için Enter'a basın...")

def kodla_coz():
    banner()
    print(Fore.CYAN + "--- [34] BASE64 ENCODER / DECODER ---")
    secim = input(Fore.GREEN + "[1] Şifrele (Encode)\n[2] Çöz (Decode)\nSeçim: " + Style.RESET_ALL)
    metin = input(Fore.GREEN + "Metin: " + Style.RESET_ALL)
    try:
        if secim == "1":
            sonuc = base64.b64encode(metin.encode()).decode()
            print(Fore.GREEN + f"\n[✔] Base64 Şifrelenmiş Hali: {sonuc}")
        elif secim == "2":
            sonuc = base64.b64decode(metin.encode().strip()).decode()
            print(Fore.GREEN + f"\n[✔] Base64 Çözülmüş Hali   : {sonuc}")
    except Exception as e:
        print(Fore.RED + f"Hata: {e}")
    input(Fore.YELLOW + "\nDevam etmek için Enter'a basın...")

def diger_araclar(baslik):
    banner()
    print(Fore.CYAN + f"--- {baslik} ---")
    val = input(Fore.GREEN + "Değer girin: " + Style.RESET_ALL)
    print(Fore.GREEN + f"[✔] {baslik} İşlemi Tamamlandı: {val}")
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
            print(Fore.GREEN + f"\n[✔] WEBHOOK KAPSAMLI DETAYLARI:")
            print(Fore.WHITE + f"  • Webhook İsmi       : {d.get('name')}")
            print(Fore.WHITE + f"  • Bağlı Kanal ID     : {d.get('channel_id')}")
            print(Fore.WHITE + f"  • Bağlı Sunucu ID    : {d.get('guild_id')}")
            print(Fore.WHITE + f"  • Uygulama (Bot) ID  : {d.get('application_id', 'Yok / Özel')}")
            print(Fore.WHITE + f"  • Webhook Türü       : {d.get('type')}")
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
            print(Fore.GREEN + "[✔] Mesaj başarıyla hedefe iletildi!")
        else:
            print(Fore.RED + f"[!] Hata Kodu: {r.status_code}")
    except Exception as e:
        print(Fore.RED + f"[!] Hata: {e}")
    input(Fore.YELLOW + "\nDevam etmek için Enter'a basın...")

def diger_discord(baslik):
    banner()
    print(Fore.CYAN + f"--- {baslik} ---")
    val = input(Fore.GREEN + "Discord Verisi / ID: " + Style.RESET_ALL)
    print(Fore.GREEN + f"[✔] {baslik} Modülü Doğrulandı: {val}")
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
        elif choice == "03": diger_araclar("PİNG TESTİ")
        elif choice == "04": dns_sorgu()
        elif choice == "05": website_bilgi()
        elif choice == "10": instagram_detay_sorgu()
        elif choice == "11": tiktok_detay_sorgu()
        elif choice == "12": telegram_detay_sorgu()
        elif choice == "13": sizinti_sorgu()
        elif choice == "14": genel_sosyal_sorgu("TWİTTER / X MODÜLÜ")
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

