#!/usr/bin/env python3
# CRSZ HACK PANEL v4.0 - TAM OSINT

import os, json, requests, socket, whois
from datetime import datetime
from colorama import init
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.align import Align
from fake_useragent import UserAgent
import instaloader
from bs4 import BeautifulSoup

init(autoreset=True)
console = Console()
ua = UserAgent()

CONFIG = {"timeout": 30, "output_dir": "crsz_results"}
if not os.path.exists(CONFIG["output_dir"]):
    os.makedirs(CONFIG["output_dir"])

def save_results(data, filename):
    path = os.path.join(CONFIG["output_dir"], filename)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)
    console.print(f"[green]Kaydedildi: {path}[/green]")

def display_big_header():
    console.clear()
    header = """
    ╔══════════════════════════════════════════════════════════════╗
    ║   ██████╗ ██████╗ ███████╗███████╗  ██╗  ██╗ █████╗  ██████╗██╗  ██╗ ║
    ║  ██╔════╝██╔═══██╗╚══███╔╝╚══███╔╝  ██║  ██║██╔══██╗██╔════╝██║ ██╔╝ ║
    ║  ██║     ██║   ██║  ███╔╝   ███╔╝   ███████║███████║██║     █████╔╝  ║
    ║  ██║     ██║   ██║ ███╔╝   ███╔╝    ██╔══██║██╔══██║██║     ██╔═██╗  ║
    ║  ╚██████╗╚██████╔╝███████╗███████╗  ██║  ██║██║  ██║╚██████╗██║  ██╗ ║
    ║   ╚═════╝ ╚═════╝ ╚══════╝╚══════╝  ╚═╝  ╚═╝╚═╝  ╚═╝ ╚═════╝╚═╝  ╚═╝ ║
    ║              CRSZ HACK PANEL v4.0 - TAM OSINT                      ║
    ║         TikTok + Instagram + IP + Email + Username                  ║
    ╚══════════════════════════════════════════════════════════════════════╝
    """
    console.print(Align.center(header, style="bold red"))

# ---- IP KONUM ----
def get_ip_info(ip):
    try:
        r = requests.get(f"http://ip-api.com/json/{ip}", timeout=10)
        data = r.json()
        if data.get("status") == "success":
            return {
                "ip": ip,
                "country": data.get("country"),
                "city": data.get("city"),
                "region": data.get("regionName"),
                "isp": data.get("isp"),
                "lat": data.get("lat"),
                "lon": data.get("lon")
            }
    except:
        pass
    return None

# ---- EMAIL SIZINTI KONTROLÜ ----
def check_email_breach(email):
    try:
        r = requests.get(f"https://haveibeenpwned.com/api/v3/breachedaccount/{email}", 
                         headers={"hibp-api-key": ""}, timeout=10)
        if r.status_code == 200:
            breaches = r.json()
            return [b.get("Name") for b in breaches]
    except:
        pass
    return []

# ---- KULLANICI ADI SORGU (Sherlock benzeri) ----
def check_username_sherlock(username):
    sites = {
        "github": f"https://github.com/{username}",
        "twitter": f"https://twitter.com/{username}",
        "reddit": f"https://www.reddit.com/user/{username}",
        "youtube": f"https://www.youtube.com/@{username}",
        "pinterest": f"https://www.pinterest.com/{username}",
        "tumblr": f"https://{username}.tumblr.com"
    }
    found = []
    for name, url in sites.items():
        try:
            r = requests.get(url, timeout=5)
            if r.status_code == 200:
                found.append(name)
        except:
            pass
    return found

# ---- TELEFON DOĞRULAMA (numverify - ücretsiz 100 sorgu/ay) ----
def check_phone(phone):
    # API anahtarı almak için numverify.com'a kayıt ol
    api_key = "YOUR_FREE_API_KEY"
    if api_key == "YOUR_FREE_API_KEY":
        return {"error": "API anahtarı gerekli - numverify.com'dan ücretsiz al"}
    try:
        r = requests.get(f"http://apilayer.net/api/validate?access_key={api_key}&number={phone}")
        data = r.json()
        if data.get("valid"):
            return {
                "phone": phone,
                "country": data.get("country_name"),
                "location": data.get("location"),
                "carrier": data.get("carrier"),
                "line_type": data.get("line_type")
            }
    except:
        pass
    return None

# ---- ALAN ADI WHOIS ----
def get_whois(domain):
    try:
        w = whois.whois(domain)
        return {
            "domain": domain,
            "registrar": w.registrar,
            "creation_date": str(w.creation_date),
            "expiration_date": str(w.expiration_date),
            "name_servers": w.name_servers[:3] if w.name_servers else []
        }
    except:
        return None

class TikTokOSINT:
    def __init__(self, username):
        self.username = username
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": ua.random})

    def get_user_info(self):
        try:
            url = f"https://www.tiktok.com/@{self.username}"
            resp = self.session.get(url, timeout=30)
            if resp.status_code != 200:
                return None
            soup = BeautifulSoup(resp.text, 'html.parser')
            script = soup.find("script", id="__NEXT_DATA__")
            if not script:
                return None
            data = json.loads(script.string)
            user = data.get("props", {}).get("pageProps", {}).get("userInfo", {})
            if not user:
                return None
            return {
                "username": self.username,
                "full_name": user.get("user", {}).get("uniqueId", ""),
                "nickname": user.get("user", {}).get("nickname", ""),
                "bio": user.get("user", {}).get("bioDescription", ""),
                "follower_count": user.get("stats", {}).get("followerCount", 0),
                "following_count": user.get("stats", {}).get("followingCount", 0),
                "verified": user.get("user", {}).get("verified", False)
            }
        except:
            return None

class InstagramOSINT:
    def __init__(self, username):
        self.username = username
        self.loader = instaloader.Instaloader(quiet=True, user_agent=ua.random)

    def get_user_info(self):
        try:
            profile = instaloader.Profile.from_username(self.loader.context, self.username)
            return {
                "username": self.username,
                "full_name": profile.full_name,
                "bio": profile.biography[:150],
                "follower_count": profile.followers,
                "following_count": profile.followees,
                "post_count": profile.mediacount,
                "verified": profile.is_verified,
                "private": profile.is_private
            }
        except:
            return None

def main():
    display_big_header()
    print("\n[bold yellow]HEDEF BİLGİLERİ GİR (boş bırakabilirsin):[/bold yellow]")
    tk = input("TikTok kullanıcı adı: ").strip()
    ig = input("Instagram kullanıcı adı: ").strip()
    email = input("Email adresi: ").strip()
    phone = input("Telefon numarası (ülke koduyla, örn: 905551234567): ").strip()
    domain = input("Alan adı (örnek.com): ").strip()
    username = input("Genel kullanıcı adı (sorgu için): ").strip()

    results = {
        "timestamp": datetime.now().isoformat(),
        "tiktok": None,
        "instagram": None,
        "email_breaches": [],
        "ip_info": None,
        "phone_info": None,
        "whois": None,
        "username_found": []
    }

    if tk:
        tik = TikTokOSINT(tk)
        results["tiktok"] = tik.get_user_info()
        if results["tiktok"]:
            console.print(f"[green]✓ TikTok: @{tk}[/green]")
        else:
            console.print(f"[red]✗ TikTok: @{tk} bulunamadı[/red]")

    if ig:
        ins = InstagramOSINT(ig)
        results["instagram"] = ins.get_user_info()
        if results["instagram"]:
            console.print(f"[green]✓ Instagram: @{ig}[/green]")
        else:
            console.print(f"[red]✗ Instagram: @{ig} bulunamadı[/red]")

    if email:
        console.print("[cyan]Email sızıntı kontrolü yapılıyor...[/cyan]")
        results["email_breaches"] = check_email_breach(email)
        if results["email_breaches"]:
            console.print(f"[red]! Email {len(results['email_breaches'])} sızıntıda bulundu[/red]")
        else:
            console.print("[green]Email sızıntıda bulunamadı[/green]")

    if username:
        console.print("[cyan]Kullanıcı adı diğer platformlarda taranıyor...[/cyan]")
        results["username_found"] = check_username_sherlock(username)
        if results["username_found"]:
            console.print(f"[yellow]Bulunan platformlar: {', '.join(results['username_found'])}[/yellow]")

    if phone:
        console.print("[cyan]Telefon doğrulanıyor (numverify)...[/cyan]")
        results["phone_info"] = check_phone(phone)
        if results["phone_info"] and "error" not in results["phone_info"]:
            console.print(f"[green]✓ Telefon geçerli - Ülke: {results['phone_info'].get('country')}[/green]")
        else:
            console.print("[red]✗ Telefon doğrulanamadı veya API anahtarı gerekli[/red]")

    if domain:
        console.print("[cyan]WHOIS sorgulanıyor...[/cyan]")
        results["whois"] = get_whois(domain)
        if results["whois"]:
            console.print(f"[green]✓ WHOIS alındı: {results['whois'].get('registrar')}[/green]")

    # IP kendi IP'ni göster (hedef IP girilemez ama sistem gösterir)
    try:
        own_ip = requests.get("https://api.ipify.org").text
        console.print(f"[cyan]Kendi IP adresin: {own_ip}[/cyan]")
        results["ip_info"] = get_ip_info(own_ip)
        if results["ip_info"]:
            console.print(f"[green]IP Konum: {results['ip_info'].get('city')}, {results['ip_info'].get('country')}[/green]")
    except:
        pass

    fname = f"crsz_osint_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    save_results(results, fname)
    console.print("[bold green]✓ TAM TARAMA TAMAMLANDI![/bold green]")
    console.print(f"[bold yellow]JSON: {fname}[/bold yellow]")

if __name__ == "__main__":
    main()
