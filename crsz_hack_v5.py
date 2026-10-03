#!/usr/bin/env python3
# CRSZ HACK PANEL v5.0 - SHERLOCK ENTEGRE, TEK SORULU, EKRANA YAZDIRAN

import os, sys, json, re, time
import requests
from datetime import datetime
from colorama import init, Fore, Style
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.align import Align
from rich.progress import Progress, SpinnerColumn, TextColumn
import instaloader
from fake_useragent import UserAgent
from bs4 import BeautifulSoup
import whois
import socket

init(autoreset=True)
console = Console()
ua = UserAgent()

# ========== SHERLOCK SİTE LİSTESİ (GENİŞLETİLMİŞ) ==========
SITES = {
    "github": "https://github.com/{}",
    "twitter": "https://twitter.com/{}",
    "reddit": "https://www.reddit.com/user/{}",
    "youtube": "https://www.youtube.com/@{}",
    "instagram": "https://www.instagram.com/{}",
    "tiktok": "https://www.tiktok.com/@{}",
    "facebook": "https://www.facebook.com/{}",
    "pinterest": "https://www.pinterest.com/{}",
    "tumblr": "https://{}.tumblr.com",
    "spotify": "https://open.spotify.com/user/{}",
    "soundcloud": "https://soundcloud.com/{}",
    "steam": "https://steamcommunity.com/id/{}",
    "twitch": "https://www.twitch.tv/{}",
    "patreon": "https://www.patreon.com/{}",
    "medium": "https://medium.com/@{}",
    "devianart": "https://www.deviantart.com/{}",
    "vimeo": "https://vimeo.com/{}",
    "imdb": "https://www.imdb.com/user/ur{}",
    "etsy": "https://www.etsy.com/shop/{}",
    "telegram": "https://t.me/{}",
    "discord": "https://discord.com/users/{}",
    "snapchat": "https://www.snapchat.com/add/{}",
    "linkedin": "https://www.linkedin.com/in/{}",
    "whatsapp": "https://wa.me/{}",
    "signal": "https://signal.org/{}",
    "vkontakte": "https://vk.com/{}",
    "odnoklassniki": "https://ok.ru/{}",
    "myspace": "https://myspace.com/{}",
    "flickr": "https://www.flickr.com/people/{}",
    "photobucket": "https://photobucket.com/{}",
    "imgur": "https://imgur.com/user/{}",
    "pastebin": "https://pastebin.com/u/{}",
    "hackernews": "https://news.ycombinator.com/user?id={}",
    "keybase": "https://keybase.io/{}",
    "bitbucket": "https://bitbucket.org/{}",
    "gitlab": "https://gitlab.com/{}",
    "sourceforge": "https://sourceforge.net/u/{}",
    "hackaday": "https://hackaday.io/{}",
    "instructables": "https://www.instructables.com/member/{}",
    "thingiverse": "https://www.thingiverse.com/{}",
    "replit": "https://replit.com/@{}",
    "glitch": "https://glitch.com/@{}",
    "codepen": "https://codepen.io/{}",
    "jsfiddle": "https://jsfiddle.net/user/{}",
    "npm": "https://www.npmjs.com/~{}",
    "pypi": "https://pypi.org/user/{}",
    "rubygems": "https://rubygems.org/profiles/{}",
    "crates": "https://crates.io/users/{}",
    "dockerhub": "https://hub.docker.com/u/{}",
    "hub.docker": "https://hub.docker.com/r/{}/",
    "wordpress": "https://{}.wordpress.com",
    "blogger": "https://{}.blogspot.com",
    "wix": "https://{}.wixsite.com/mysite",
    "weebly": "https://{}.weebly.com",
    "githubio": "https://{}.github.io",
    "netlify": "https://{}.netlify.app",
    "vercel": "https://{}.vercel.app",
    "heroku": "https://{}.herokuapp.com",
    "glitchapp": "https://{}.glitch.me",
    "000webhost": "https://{}.000webhostapp.com",
    "infinityfree": "https://{}.infinityfreeapp.com",
    "awardspace": "https://{}.awardspace.net",
    "byethost": "https://{}.byethost.com",
    "x10host": "https://{}.x10host.com",
    "zoho": "https://{}.zohosites.com",
    "webnode": "https://{}.webnode.com",
    "site123": "https://{}.site123.me",
    "strikingly": "https://{}.strikingly.com",
    "carrd": "https://{}.carrd.co",
    "linktree": "https://linktr.ee/{}",
    "beacons": "https://beacons.ai/{}",
    "allmylinks": "https://allmylinks.com/{}",
    "bio": "https://bio.site/{}",
    "aboutme": "https://about.me/{}",
    "gravatar": "https://en.gravatar.com/{}",
    "disqus": "https://disqus.com/by/{}",
    "redbubble": "https://www.redbubble.com/people/{}",
    "society6": "https://society6.com/{}",
    "artstation": "https://www.artstation.com/{}",
    "behance": "https://www.behance.net/{}",
    "dribbble": "https://dribbble.com/{}",
    "unsplash": "https://unsplash.com/@{}",
    "pexels": "https://www.pexels.com/@{}",
    "fiverr": "https://www.fiverr.com/{}",
    "upwork": "https://www.upwork.com/freelancers/{}",
    "freelancer": "https://www.freelancer.com/u/{}",
    "guru": "https://www.guru.com/freelancers/{}",
    "toptal": "https://www.toptal.com/resume/{}",
    "angelist": "https://angel.co/u/{}",
    "crunchbase": "https://www.crunchbase.com/person/{}",
    "zoominfo": "https://www.zoominfo.com/p/{}",
    "spokeo": "https://www.spokeo.com/{}",
    "pipl": "https://pipl.com/search/?q={}",
    "webmii": "https://webmii.com/people?n={}",
    "peekyou": "https://www.peekyou.com/{}",
    "familytreenow": "https://www.familytreenow.com/{}",
    "truepeoplesearch": "https://www.truepeoplesearch.com/results?name={}",
    "whitepages": "https://www.whitepages.com/name/{}",
    "intelius": "https://www.intelius.com/people/{}",
    "beenverified": "https://www.beenverified.com/people/{}",
    "instantcheckmate": "https://www.instantcheckmate.com/people/{}",
    "checkpeople": "https://www.checkpeople.com/people/{}",
    "publicrecords": "https://publicrecords.com/{}",
    "courtrecords": "https://www.courtrecords.org/people/{}",
    "arrests": "https://arrests.org/{}",
    "mugshots": "https://mugshots.com/{}",
    "voterrecords": "https://www.voterrecords.com/{}",
    "birthrecords": "https://www.birthrecords.com/{}",
    "deathrecords": "https://www.deathrecords.com/{}",
    "marriagerecords": "https://www.marriagerecords.com/{}",
    "divorcerecords": "https://www.divorcerecords.com/{}",
    "propertyrecords": "https://www.propertyrecords.com/{}",
    "businessrecords": "https://www.businessrecords.com/{}",
    "llc": "https://www.llc.com/{}",
    "corp": "https://www.corp.com/{}",
    "nonprofit": "https://www.nonprofit.com/{}",
    "charity": "https://www.charity.com/{}",
    "foundation": "https://www.foundation.com/{}",
    "museum": "https://www.museum.com/{}",
    "library": "https://www.library.com/{}",
    "archive": "https://archive.org/details/@{}",
    "wikimedia": "https://commons.wikimedia.org/wiki/User:{}",
    "wikidata": "https://www.wikidata.org/wiki/User:{}",
    "metawiki": "https://meta.wikimedia.org/wiki/User:{}",
    "mediawiki": "https://www.mediawiki.org/wiki/User:{}",
    "wikiversity": "https://www.wikiversity.org/wiki/User:{}",
    "wikibooks": "https://www.wikibooks.org/wiki/User:{}",
    "wikinews": "https://www.wikinews.org/wiki/User:{}",
    "wikiquote": "https://www.wikiquote.org/wiki/User:{}",
    "wikisource": "https://www.wikisource.org/wiki/User:{}",
    "wikispecies": "https://www.wikispecies.org/wiki/User:{}",
    "wikivoyage": "https://www.wikivoyage.org/wiki/User:{}",
    "wiktionary": "https://www.wiktionary.org/wiki/User:{}",
    "githubgist": "https://gist.github.com/{}",
    "gitlab": "https://gitlab.com/{}",
    "bitbucket": "https://bitbucket.org/{}",
    "sourceforge": "https://sourceforge.net/u/{}",
    "hackaday": "https://hackaday.io/{}",
    "instructables": "https://www.instructables.com/member/{}",
    "thingiverse": "https://www.thingiverse.com/{}",
    "replit": "https://replit.com/@{}",
    "glitch": "https://glitch.com/@{}",
    "codepen": "https://codepen.io/{}",
    "jsfiddle": "https://jsfiddle.net/user/{}",
    "npm": "https://www.npmjs.com/~{}",
    "pypi": "https://pypi.org/user/{}",
    "rubygems": "https://rubygems.org/profiles/{}",
    "crates": "https://crates.io/users/{}",
    "dockerhub": "https://hub.docker.com/u/{}",
    "hub.docker": "https://hub.docker.com/r/{}/",
    "wordpress": "https://{}.wordpress.com",
    "blogger": "https://{}.blogspot.com",
    "wix": "https://{}.wixsite.com/mysite",
    "weebly": "https://{}.weebly.com",
    "githubio": "https://{}.github.io",
    "netlify": "https://{}.netlify.app",
    "vercel": "https://{}.vercel.app",
    "heroku": "https://{}.herokuapp.com",
    "glitchapp": "https://{}.glitch.me",
    "000webhost": "https://{}.000webhostapp.com",
    "infinityfree": "https://{}.infinityfreeapp.com",
    "awardspace": "https://{}.awardspace.net",
    "byethost": "https://{}.byethost.com",
    "x10host": "https://{}.x10host.com",
    "zoho": "https://{}.zohosites.com",
    "webnode": "https://{}.webnode.com",
    "site123": "https://{}.site123.me",
    "strikingly": "https://{}.strikingly.com",
    "carrd": "https://{}.carrd.co",
    "linktree": "https://linktr.ee/{}",
    "beacons": "https://beacons.ai/{}",
    "allmylinks": "https://allmylinks.com/{}",
    "bio": "https://bio.site/{}",
    "aboutme": "https://about.me/{}",
    "gravatar": "https://en.gravatar.com/{}",
    "disqus": "https://disqus.com/by/{}",
    "redbubble": "https://www.redbubble.com/people/{}",
    "society6": "https://society6.com/{}",
    "artstation": "https://www.artstation.com/{}",
    "behance": "https://www.behance.net/{}",
    "dribbble": "https://dribbble.com/{}",
    "unsplash": "https://unsplash.com/@{}",
    "pexels": "https://www.pexels.com/@{}",
    "fiverr": "https://www.fiverr.com/{}",
    "upwork": "https://www.upwork.com/freelancers/{}",
    "freelancer": "https://www.freelancer.com/u/{}",
    "guru": "https://www.guru.com/freelancers/{}",
    "toptal": "https://www.toptal.com/resume/{}",
    "angelist": "https://angel.co/u/{}",
    "crunchbase": "https://www.crunchbase.com/person/{}",
    "zoominfo": "https://www.zoominfo.com/p/{}",
    "spokeo": "https://www.spokeo.com/{}",
    "pipl": "https://pipl.com/search/?q={}",
    "webmii": "https://webmii.com/people?n={}",
    "peekyou": "https://www.peekyou.com/{}",
    "familytreenow": "https://www.familytreenow.com/{}",
    "truepeoplesearch": "https://www.truepeoplesearch.com/results?name={}",
    "whitepages": "https://www.whitepages.com/name/{}",
    "intelius": "https://www.intelius.com/people/{}",
    "beenverified": "https://www.beenverified.com/people/{}",
    "instantcheckmate": "https://www.instantcheckmate.com/people/{}",
    "checkpeople": "https://www.checkpeople.com/people/{}",
    "publicrecords": "https://publicrecords.com/{}",
    "courtrecords": "https://www.courtrecords.org/people/{}",
    "arrests": "https://arrests.org/{}",
    "mugshots": "https://mugshots.com/{}",
    "voterrecords": "https://www.voterrecords.com/{}",
    "birthrecords": "https://www.birthrecords.com/{}",
    "deathrecords": "https://www.deathrecords.com/{}",
    "marriagerecords": "https://www.marriagerecords.com/{}",
    "divorcerecords": "https://www.divorcerecords.com/{}",
    "propertyrecords": "https://www.propertyrecords.com/{}",
    "businessrecords": "https://www.businessrecords.com/{}",
    "llc": "https://www.llc.com/{}",
    "corp": "https://www.corp.com/{}",
    "nonprofit": "https://www.nonprofit.com/{}",
    "charity": "https://www.charity.com/{}",
    "foundation": "https://www.foundation.com/{}",
    "museum": "https://www.museum.com/{}",
    "library": "https://www.library.com/{}",
    "archive": "https://archive.org/details/@{}",
    "wikimedia": "https://commons.wikimedia.org/wiki/User:{}",
    "wikidata": "https://www.wikidata.org/wiki/User:{}",
    "metawiki": "https://meta.wikimedia.org/wiki/User:{}",
    "mediawiki": "https://www.mediawiki.org/wiki/User:{}",
    "wikiversity": "https://www.wikiversity.org/wiki/User:{}",
    "wikibooks": "https://www.wikibooks.org/wiki/User:{}",
    "wikinews": "https://www.wikinews.org/wiki/User:{}",
    "wikiquote": "https://www.wikiquote.org/wiki/User:{}",
    "wikisource": "https://www.wikisource.org/wiki/User:{}",
    "wikispecies": "https://www.wikispecies.org/wiki/User:{}",
    "wikivoyage": "https://www.wikivoyage.org/wiki/User:{}",
    "wiktionary": "https://www.wiktionary.org/wiki/User:{}",
    "githubgist": "https://gist.github.com/{}",
    "gitlab": "https://gitlab.com/{}",
    "bitbucket": "https://bitbucket.org/{}",
    "sourceforge": "https://sourceforge.net/u/{}",
    "hackaday": "https://hackaday.io/{}",
    "instructables": "https://www.instructables.com/member/{}",
    "thingiverse": "https://www.thingiverse.com/{}",
    "replit": "https://replit.com/@{}",
    "glitch": "https://glitch.com/@{}",
    "codepen": "https://codepen.io/{}",
    "jsfiddle": "https://jsfiddle.net/user/{}",
    "npm": "https://www.npmjs.com/~{}",
    "pypi": "https://pypi.org/user/{}",
    "rubygems": "https://rubygems.org/profiles/{}",
    "crates": "https://crates.io/users/{}",
    "dockerhub": "https://hub.docker.com/u/{}",
    "hub.docker": "https://hub.docker.com/r/{}/",
    "wordpress": "https://{}.wordpress.com",
    "blogger": "https://{}.blogspot.com",
    "wix": "https://{}.wixsite.com/mysite",
    "weebly": "https://{}.weebly.com",
    "githubio": "https://{}.github.io",
    "netlify": "https://{}.netlify.app",
    "vercel": "https://{}.vercel.app",
    "heroku": "https://{}.herokuapp.com",
    "glitchapp": "https://{}.glitch.me",
    "000webhost": "https://{}.000webhostapp.com",
    "infinityfree": "https://{}.infinityfreeapp.com",
    "awardspace": "https://{}.awardspace.net",
    "byethost": "https://{}.byethost.com",
    "x10host": "https://{}.x10host.com",
    "zoho": "https://{}.zohosites.com",
    "webnode": "https://{}.webnode.com",
    "site123": "https://{}.site123.me",
    "strikingly": "https://{}.strikingly.com",
    "carrd": "https://{}.carrd.co",
    "linktree": "https://linktr.ee/{}",
    "beacons": "https://beacons.ai/{}",
    "allmylinks": "https://allmylinks.com/{}",
    "bio": "https://bio.site/{}",
    "aboutme": "https://about.me/{}",
    "gravatar": "https://en.gravatar.com/{}",
    "disqus": "https://disqus.com/by/{}",
    "redbubble": "https://www.redbubble.com/people/{}",
    "society6": "https://society6.com/{}",
    "artstation": "https://www.artstation.com/{}",
    "behance": "https://www.behance.net/{}",
    "dribbble": "https://dribbble.com/{}",
    "unsplash": "https://unsplash.com/@{}",
    "pexels": "https://www.pexels.com/@{}",
    "fiverr": "https://www.fiverr.com/{}",
    "upwork": "https://www.upwork.com/freelancers/{}",
    "freelancer": "https://www.freelancer.com/u/{}",
    "guru": "https://www.guru.com/freelancers/{}",
    "toptal": "https://www.toptal.com/resume/{}",
    "angelist": "https://angel.co/u/{}",
    "crunchbase": "https://www.crunchbase.com/person/{}",
    "zoominfo": "https://www.zoominfo.com/p/{}",
    "spokeo": "https://www.spokeo.com/{}",
    "pipl": "https://pipl.com/search/?q={}",
    "webmii": "https://webmii.com/people?n={}",
    "peekyou": "https://www.peekyou.com/{}",
    "familytreenow": "https://www.familytreenow.com/{}",
    "truepeoplesearch": "https://www.truepeoplesearch.com/results?name={}",
    "whitepages": "https://www.whitepages.com/name/{}",
    "intelius": "https://www.intelius.com/people/{}",
    "beenverified": "https://www.beenverified.com/people/{}",
    "instantcheckmate": "https://www.instantcheckmate.com/people/{}",
    "checkpeople": "https://www.checkpeople.com/people/{}",
    "publicrecords": "https://publicrecords.com/{}",
    "courtrecords": "https://www.courtrecords.org/people/{}",
    "arrests": "https://arrests.org/{}",
    "mugshots": "https://mugshots.com/{}",
    "voterrecords": "https://www.voterrecords.com/{}",
    "birthrecords": "https://www.birthrecords.com/{}",
    "deathrecords": "https://www.deathrecords.com/{}",
    "marriagerecords": "https://www.marriagerecords.com/{}",
    "divorcerecords": "https://www.divorcerecords.com/{}",
    "propertyrecords": "https://www.propertyrecords.com/{}",
    "businessrecords": "https://www.businessrecords.com/{}",
    "llc": "https://www.llc.com/{}",
    "corp": "https://www.corp.com/{}",
    "nonprofit": "https://www.nonprofit.com/{}",
    "charity": "https://www.charity.com/{}",
    "foundation": "https://www.foundation.com/{}",
    "museum": "https://www.museum.com/{}",
    "library": "https://www.library.com/{}",
    "archive": "https://archive.org/details/@{}",
    "wikimedia": "https://commons.wikimedia.org/wiki/User:{}",
    "wikidata": "https://www.wikidata.org/wiki/User:{}",
    "metawiki": "https://meta.wikimedia.org/wiki/User:{}",
    "mediawiki": "https://www.mediawiki.org/wiki/User:{}",
    "wikiversity": "https://www.wikiversity.org/wiki/User:{}",
    "wikibooks": "https://www.wikibooks.org/wiki/User:{}",
    "wikinews": "https://www.wikinews.org/wiki/User:{}",
    "wikiquote": "https://www.wikiquote.org/wiki/User:{}",
    "wikisource": "https://www.wikisource.org/wiki/User:{}",
    "wikispecies": "https://www.wikispecies.org/wiki/User:{}",
    "wikivoyage": "https://www.wikivoyage.org/wiki/User:{}",
    "wiktionary": "https://www.wiktionary.org/wiki/User:{}"
}

# ========== FONKSİYONLAR ==========

def display_big_header():
    console.clear()
    header = """
    ╔══════════════════════════════════════════════════════════════════╗
    ║   ██████╗ ██████╗ ███████╗███████╗  ██╗  ██╗ █████╗  ██████╗██╗  ██╗ ║
    ║  ██╔════╝██╔═══██╗╚══███╔╝╚══███╔╝  ██║  ██║██╔══██╗██╔════╝██║ ██╔╝ ║
    ║  ██║     ██║   ██║  ███╔╝   ███╔╝   ███████║███████║██║     █████╔╝  ║
    ║  ██║     ██║   ██║ ███╔╝   ███╔╝    ██╔══██║██╔══██║██║     ██╔═██╗  ║
    ║  ╚██████╗╚██████╔╝███████╗███████╗  ██║  ██║██║  ██║╚██████╗██║  ██╗ ║
    ║   ╚═════╝ ╚═════╝ ╚══════╝╚══════╝  ╚═╝  ╚═╝╚═╝  ╚═╝ ╚═════╝╚═╝  ╚═╝ ║
    ║              CRSZ HACK PANEL v5.0 - FULL OSINT                   ║
    ║         Tek Sorgu ile 100+ Platformda Tarama                      ║
    ╚══════════════════════════════════════════════════════════════════╝
    """
    console.print(Align.center(header, style="bold red"))

# ---- TikTok ----
def get_tiktok(username):
    try:
        url = f"https://www.tiktok.com/@{username}"
        resp = requests.get(url, headers={"User-Agent": ua.random}, timeout=15)
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
            "username": username,
            "full_name": user.get("user", {}).get("uniqueId", ""),
            "nickname": user.get("user", {}).get("nickname", ""),
            "bio": user.get("user", {}).get("bioDescription", "")[:100],
            "follower_count": user.get("stats", {}).get("followerCount", 0),
            "following_count": user.get("stats", {}).get("followingCount", 0),
            "verified": user.get("user", {}).get("verified", False),
            "private": user.get("user", {}).get("privateAccount", False)
        }
    except:
        return None

# ---- Instagram ----
def get_instagram(username):
    try:
        loader = instaloader.Instaloader(quiet=True, user_agent=ua.random)
        profile = instaloader.Profile.from_username(loader.context, username)
        return {
            "username": username,
            "full_name": profile.full_name,
            "bio": profile.biography[:100],
            "follower_count": profile.followers,
            "following_count": profile.followees,
            "post_count": profile.mediacount,
            "verified": profile.is_verified,
            "private": profile.is_private
        }
    except:
        return None

# ---- Email Breach ----
def check_email_breach(email):
    try:
        r = requests.get(f"https://haveibeenpwned.com/api/v3/breachedaccount/{email}", timeout=15)
        if r.status_code == 200:
            return [b.get("Name") for b in r.json()]
    except:
        pass
    return []

# ---- WHOIS ----
def get_whois(domain):
    try:
        w = whois.whois(domain)
        return {
            "domain": domain,
            "registrar": w.registrar,
            "creation_date": str(w.creation_date)[:10] if w.creation_date else "",
            "expiration_date": str(w.expiration_date)[:10] if w.expiration_date else ""
        }
    except:
        return None

# ---- IP Bilgisi ----
def get_ip_info():
    try:
        ip = requests.get("https://api.ipify.org", timeout=10).text
        r = requests.get(f"http://ip-api.com/json/{ip}", timeout=10)
        data = r.json()
        if data.get("status") == "success":
            return {
                "ip": ip,
                "country": data.get("country"),
                "city": data.get("city"),
                "region": data.get("regionName"),
                "isp": data.get("isp")
            }
    except:
        pass
    return None

# ========== SHERLOCK TARAYICI ==========
def sherlock_scan(username):
    console.print("[cyan]🔍 Sherlock taraması başlatılıyor (100+ platform)...[/cyan]")
    found = []
    total = len(SITES)
    count = 0
    
    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), transient=True) as progress:
        task = progress.add_task("[cyan]Taranıyor...", total=total)
        for site, url_template in SITES.items():
            url = url_template.format(username)
            try:
                r = requests.get(url, headers={"User-Agent": ua.random}, timeout=5)
                if r.status_code == 200:
                    found.append((site, url))
            except:
                pass
            count += 1
            progress.advance(task)
    
    return found

# ========== ANA FONKSİYON ==========
def main():
    display_big_header()
    console.print("\n[bold yellow]=== HEDEF KİŞİNİN BİLGİLERİNİ GİR ===[/bold yellow]")
    username = input("[?] Kullanıcı adı (örn: johndoe): ").strip()
    email = input("[?] Email adresi (opsiyonel): ").strip()
    domain = input("[?] Alan adı (opsiyonel, örn: example.com): ").strip()
    
    results = []
    
    # ---- SHERLOCK ----
    if username:
        found_sites = sherlock_scan(username)
        if found_sites:
            results.append("[bold green]✓ SHERLOCK SONUÇLARI:[/bold green]")
            for site, url in found_sites[:20]:  # İlk 20 site
                results.append(f"  [cyan]• {site}:[/cyan] {url}")
            if len(found_sites) > 20:
                results.append(f"  [yellow]... ve {len(found_sites)-20} daha fazla[/yellow]")
        else:
            results.append("[red]✗ Sherlock: Hiçbir platformda bulunamadı[/red]")
    
    # ---- TIKTOK ----
    if username:
        console.print("[cyan]🐧 TikTok taranıyor...[/cyan]")
        tk = get_tiktok(username)
        if tk:
            results.append("\n[bold magenta]📱 TIKTOK PROFİLİ:[/bold magenta]")
            results.append(f"  Kullanıcı: @{tk['username']}")
            results.append(f"  Tam isim: {tk['full_name']}")
            results.append(f"  Takipçi: {tk['follower_count']}")
            results.append(f"  Takip: {tk['following_count']}")
            results.append(f"  Mavi tik: {'✅' if tk['verified'] else '❌'}")
            results.append(f"  Gizli: {'🔒' if tk['private'] else '🌐'}")
            results.append(f"  Bio: {tk['bio']}")
        else:
            results.append("[red]✗ TikTok: @{} bulunamadı[/red]".format(username))
    
    # ---- INSTAGRAM ----
    if username:
        console.print("[cyan]📸 Instagram taranıyor...[/cyan]")
        ig = get_instagram(username)
        if ig:
            results.append("\n[bold green]📷 INSTAGRAM PROFİLİ:[/bold green]")
            results.append(f"  Kullanıcı: @{ig['username']}")
            results.append(f"  Tam isim: {ig['full_name']}")
            results.append(f"  Takipçi: {ig['follower_count']}")
            results.append(f"  Takip: {ig['following_count']}")
            results.append(f"  Gönderi: {ig['post_count']}")
            results.append(f"  Mavi tik: {'✅' if ig['verified'] else '❌'}")
            results.append(f"  Gizli: {'🔒' if ig['private'] else '🌐'}")
            results.append(f"  Bio: {ig['bio']}")
        else:
            results.append("[red]✗ Instagram: @{} bulunamadı[/red]".format(username))
    
    # ---- EMAIL ----
    if email:
        console.print("[cyan]📧 Email sızıntı kontrolü...[/cyan]")
        breaches = check_email_breach(email)
        if breaches:
            results.append(f"\n[bold red]📧 EMAIL SIZINTILARI ({len(breaches)} adet):[/bold red]")
            for b in breaches[:10]:
                results.append(f"  • {b}")
        else:
            results.append("[green]✓ Email sızıntıda bulunamadı[/green]")
    
    # ---- WHOIS ----
    if domain:
        console.print("[cyan]🌐 WHOIS sorgulanıyor...[/cyan]")
        who = get_whois(domain)
        if who:
            results.append("\n[bold yellow]🌐 WHOIS BİLGİLERİ:[/bold yellow]")
            results.append(f"  Domain: {who['domain']}")
            results.append(f"  Kayıtçı: {who['registrar']}")
            results.append(f"  Oluşturma: {who['creation_date']}")
            results.append(f"  Bitiş: {who['expiration_date']}")
    
    # ---- IP ----
    console.print("[cyan]🌍 IP bilgisi alınıyor...[/cyan]")
    ip_info = get_ip_info()
    if ip_info:
        results.append("\n[bold blue]🌍 IP BİLGİLERİ (kendi IP'n):[/bold blue]")
        results.append(f"  IP: {ip_info['ip']}")
        results.append(f"  Ülke: {ip_info['country']}")
        results.append(f"  Şehir: {ip_info['city']}")
        results.append(f"  Bölge: {ip_info['region']}")
        results.append(f"  İSP: {ip_info['isp']}")
    
    # ---- EKRANA YAZDIR ----
    console.clear()
    display_big_header()
    console.print("\n[bold red]========== CRSZ TARAMA SONUÇLARI ==========[/bold red]\n")
    for line in results:
        console.print(line)
    console.print("\n[bold green]✓ Tarama tamamlandı![/bold green]")

if __name__ == "__main__":
    main()
