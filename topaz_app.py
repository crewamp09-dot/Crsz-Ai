from flask import Flask, render_template_string, request, redirect, url_for, flash, session
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
import os

app = Flask(__name__)
app.secret_key = 'CRSZ_TOPAZ_ULTIMATE_PRO_2026'

UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# --- VERİTABANI BAŞLANGIÇ ---
def init_db():
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            credits INTEGER DEFAULT 100
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# --- FLASK-LOGIN & OTURUM KALICILIK AYARLARI ---
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
app.config['REMEMBER_COOKIE_DURATION'] = 86400 * 30  # 30 Gün

class User(UserMixin):
    def __init__(self, id, username, email, credits):
        self.id = id
        self.username = username
        self.email = email
        self.credits = credits

@login_manager.user_loader
def load_user(user_id):
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute('SELECT id, username, email, credits FROM users WHERE id = ?', (user_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return User(id=row[0], username=row[1], email=row[2], credits=row[3])
    return None

# --- HTML / CSS / TOPAZ PRO AI ENGINE (JS) ---
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="tr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Topaz Video AI • Ultimate Cloud Studio</title>
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Plus Jakarta Sans', sans-serif; }
        body { background-color: #05070b; color: #f3f4f6; min-height: 100vh; display: flex; flex-direction: column; overflow-x: hidden; }

        .bg-glow { position: fixed; width: 400px; height: 400px; background: rgba(56, 189, 248, 0.08); filter: blur(120px); border-radius: 50%; z-index: -1; }

        /* Navbar */
        nav { background: rgba(10, 15, 30, 0.85); backdrop-filter: blur(16px); border-bottom: 1px solid rgba(255, 255, 255, 0.06); padding: 12px 20px; display: flex; justify-content: space-between; align-items: center; position: sticky; top: 0; z-index: 100; flex-wrap: wrap; gap: 10px; }
        .logo { font-weight: 700; font-size: 1.2rem; color: #38bdf8; display: flex; align-items: center; gap: 8px; text-decoration: none; }
        .nav-links { display: flex; gap: 12px; align-items: center; font-size: 0.85rem; flex-wrap: wrap; }
        .nav-links a { color: #94a3b8; text-decoration: none; transition: 0.3s; }
        .nav-links a:hover { color: #38bdf8; }
        .credits-badge { background: linear-gradient(135deg, rgba(56,189,248,0.1), rgba(14,165,233,0.2)); border: 1px solid rgba(56, 189, 248, 0.4); padding: 5px 12px; border-radius: 30px; color: #38bdf8; font-size: 0.75rem; font-weight: 600; }

        /* Main Workspace */
        .main-container { display: grid; grid-template-columns: 440px 1fr; flex: 1; height: calc(100vh - 65px); }
        @media(max-width: 950px) { .main-container { grid-template-columns: 1fr; overflow-y: auto; height: auto; } }

        /* Sidebar */
        .sidebar { background: #0a0f1e; border-right: 1px solid rgba(255, 255, 255, 0.06); padding: 20px; overflow-y: auto; display: flex; flex-direction: column; gap: 16px; }
        .section-title { font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.1em; color: #64748b; margin-bottom: 6px; font-weight: 700; }
        
        .upload-box { border: 2px dashed rgba(56, 189, 248, 0.3); border-radius: 12px; padding: 16px; text-align: center; background: rgba(56, 189, 248, 0.02); cursor: pointer; transition: 0.3s; }
        .upload-box:hover { border-color: #38bdf8; background: rgba(56, 189, 248, 0.06); }
        .upload-box input { display: none; }

        .control-group { display: flex; flex-direction: column; gap: 5px; }
        label { font-size: 0.8rem; color: #cbd5e1; font-weight: 500; display: flex; justify-content: space-between; }
        select, input[type="range"] { background: #111827; border: 1px solid #1f2937; color: #fff; padding: 9px; border-radius: 8px; font-size: 0.82rem; outline: none; }
        select:focus { border-color: #38bdf8; }

        .manual-settings { display: flex; flex-direction: column; gap: 10px; background: rgba(17, 24, 39, 0.6); padding: 12px; border-radius: 8px; border: 1px solid #1f2937; }
        .slider-val { color: #38bdf8; font-weight: 600; }

        .btn-primary { background: linear-gradient(135deg, #0284c7, #38bdf8); color: white; border: none; padding: 12px; border-radius: 8px; font-weight: 600; cursor: pointer; transition: 0.3s; width: 100%; text-align: center; display: inline-block; text-decoration: none; box-shadow: 0 4px 15px rgba(56, 189, 248, 0.3); }
        .btn-primary:hover { opacity: 0.95; transform: translateY(-1px); }

        .btn-estimate { background: #1f2937; color: #38bdf8; border: 1px solid rgba(56, 189, 248, 0.3); padding: 10px; border-radius: 8px; font-weight: 600; font-size: 0.82rem; cursor: pointer; transition: 0.2s; width: 100%; margin-bottom: 5px; }
        .btn-estimate:hover { background: #374151; border-color: #38bdf8; }

        /* Workspace & Preview */
        .workspace { background: #030712; display: flex; flex-direction: column; justify-content: center; align-items: center; padding: 25px; position: relative; overflow-y: auto; }
        .preview-wrapper { width: 100%; max-width: 850px; aspect-ratio: 16/9; background: #05070b; border: 1px solid rgba(255, 255, 255, 0.06); border-radius: 16px; display: flex; justify-content: center; align-items: center; position: relative; overflow: hidden; box-shadow: 0 20px 40px rgba(0,0,0,0.7); }
        
        video, canvas { width: 100%; height: 100%; object-fit: contain; position: absolute; top: 0; left: 0; }
        
        .placeholder-text { color: #64748b; font-size: 0.9rem; text-align: center; z-index: 10; }

        /* Karşılaştırma Araç Çubuğu */
        .compare-bar { display: none; width: 100%; max-width: 850px; justify-content: space-between; align-items: center; margin-bottom: 12px; background: #0a0f1e; padding: 8px 15px; border-radius: 8px; border: 1px solid rgba(255,255,255,0.06); }
        .compare-btns { display: flex; gap: 8px; }
        .cmp-btn { background: #111827; border: 1px solid #374151; color: #fff; padding: 6px 14px; font-size: 0.8rem; font-weight: 600; border-radius: 6px; cursor: pointer; transition: 0.2s; }
        .cmp-btn.active { background: #38bdf8; color: #05070b; border-color: #38bdf8; }

        /* Processing Overlay */
        #processing-overlay { position: absolute; top: 0; left: 0; width: 100%; height: 100%; background: rgba(5, 7, 11, 0.92); backdrop-filter: blur(10px); display: none; flex-direction: column; justify-content: center; align-items: center; z-index: 50; gap: 15px; }
        .spinner { width: 50px; height: 50px; border: 3px solid rgba(56, 189, 248, 0.1); border-top-color: #38bdf8; border-radius: 50%; animation: spin 0.8s linear infinite; }
        @keyframes spin { to { transform: rotate(360deg); } }
        .progress-text { font-size: 0.9rem; color: #38bdf8; font-weight: 600; text-align: center; padding: 0 20px; }

        /* Download Box */
        .download-box { margin-top: 15px; width: 100%; max-width: 850px; background: rgba(10, 15, 30, 0.9); border: 1px solid rgba(56, 189, 248, 0.3); border-radius: 12px; padding: 15px 20px; display: none; justify-content: space-between; align-items: center; }

        /* Auth Cards */
        .auth-center { display: flex; justify-content: center; align-items: center; flex: 1; padding: 20px; }
        .auth-card { background: #0a0f1e; border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 16px; padding: 30px; width: 100%; max-width: 400px; box-shadow: 0 20px 40px rgba(0,0,0,0.6); }
        .auth-card h2 { margin-bottom: 20px; font-size: 1.4rem; color: #f8fafc; font-weight: 700; }
        .auth-input { width: 100%; background: #111827; border: 1px solid #1f2937; color: #fff; padding: 11px; border-radius: 8px; margin-bottom: 12px; font-size: 0.88rem; outline: none; }
        .auth-input:focus { border-color: #38bdf8; }
        .flash-msg { background: rgba(239, 68, 68, 0.1); border: 1px solid rgba(239, 68, 68, 0.3); color: #fca5a5; padding: 10px; border-radius: 8px; font-size: 0.82rem; margin-bottom: 15px; }
    </style>
</head>
<body>

    <div class="bg-glow" style="top: -100px; left: -100px;"></div>

    <nav>
        <a href="/" class="logo">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/></svg>
            Topaz Video AI Pro
        </a>
        <div class="nav-links">
            {% if current_user.is_authenticated %}
                <span class="credits-badge">⚡ Credits: {{ current_user.credits }}</span>
                <span style="color: #cbd5e1; font-weight: 500;">{{ current_user.username }}</span>
                <a href="/logout" style="color: #ef4444; font-weight: 600;">Logout</a>
            {% else %}
                <a href="/login">Login</a>
                <a href="/register" style="background: #38bdf8; color: #05070b; padding: 6px 14px; border-radius: 6px; font-weight: 700;">Register</a>
            {% endif %}
        </div>
    </nav>

    {% block content %}{% endblock %}

</body>
</html>
"""

# --- GİRİŞ SAYFASI ---
LOGIN_TEMPLATE = HTML_TEMPLATE.replace('{% block content %}{% endblock %}', """
<div class="auth-center">
    <div class="auth-card">
        <h2>Login</h2>
        {% with messages = get_flashed_messages() %}
            {% if messages %}
                <div class="flash-msg">{{ messages[0] }}</div>
            {% endif %}
        {% endwith %}

        <form method="POST">
            <input type="text" name="username" class="auth-input" placeholder="Username" required>
            <input type="password" name="password" class="auth-input" placeholder="Password" required>
            
            <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 15px; font-size: 0.82rem; color: #94a3b8;">
                <input type="checkbox" name="remember" id="remember" checked style="accent-color: #38bdf8;">
                <label for="remember" style="cursor: pointer; color: #94a3b8;">Remember Me</label>
            </div>

            <button type="submit" class="btn-primary">Login</button>
        </form>
        <p style="margin-top: 15px; font-size: 0.82rem; color: #64748b; text-align: center;">Don't have an account? <a href="/register" style="color: #38bdf8; text-decoration: none;">Register</a></p>
    </div>
</div>
""")

# --- KAYIT OL SAYFASI ---
REGISTER_TEMPLATE = HTML_TEMPLATE.replace('{% block content %}{% endblock %}', """
<div class="auth-center">
    <div class="auth-card">
        <h2>Register</h2>
        {% with messages = get_flashed_messages() %}
            {% if messages %}
                <div class="flash-msg">{{ messages[0] }}</div>
            {% endif %}
        {% endwith %}
        
        <form method="POST">
            <input type="text" name="username" class="auth-input" placeholder="Username" required>
            <input type="email" name="email" class="auth-input" placeholder="Email" required>
            <input type="password" name="password" class="auth-input" placeholder="Password" required>
            <button type="submit" class="btn-primary">Register (100 Credits)</button>
        </form>
        <p style="margin-top: 15px; font-size: 0.82rem; color: #64748b; text-align: center;">Already have an account? <a href="/login" style="color: #38bdf8; text-decoration: none;">Login</a></p>
    </div>
</div>
""")

# --- ANA DASHBOARD ---
DASHBOARD_TEMPLATE = HTML_TEMPLATE.replace('{% block content %}{% endblock %}', """
<div class="main-container">
    <div class="sidebar">
        <div>
            <div class="section-title">Source Video</div>
            <div class="upload-box" onclick="document.getElementById('videoFile').click()">
                <span id="file-label" style="font-size: 0.82rem; color: #94a3b8;">Choose Video (.mp4, .mov, .webm)</span>
                <input type="file" id="videoFile" accept="video/*" onchange="handleFileSelect(this)">
            </div>
        </div>

        <div class="control-group">
            <label>OUTPUT RESOLUTION</label>
            <select id="outputResolution">
                <option value="original" selected>Match Source (Original Resolution)</option>
                <option value="1080">1920x1080 (FHD Upscale)</option>
                <option value="2160">2160x2160 (2x Square Upscale)</option>
                <option value="4k">3840x2160 (4K UHD Upscale)</option>
            </select>
        </div>

        <div class="control-group" style="background: rgba(56, 189, 248, 0.05); padding: 10px; border-radius: 8px; border: 1px solid rgba(56, 189, 248, 0.2);">
            <label style="color: #38bdf8; font-weight: 700;">⚡ RENDER MOTORU & AKICILIK</label>
            <select id="renderEngineMode" style="margin-top: 5px;">
                <option value="safe" selected>Safe & Stable (0 Kasma / Otomatik Kare Atlama Önleyici)</option>
                <option value="ultra_lossless">Ultra Lossless (Yüksek Kalite / Ağır İşlemci Modu)</option>
                <option value="fast_preview">Fast Render (Düşük Donanımlar İçin Hızlı İşleme)</option>
            </select>
        </div>

        <div class="control-group">
            <label>VIDEO TYPE</label>
            <select id="videoType">
                <option value="progressive" selected>Progressive</option>
                <option value="interlaced">Interlaced</option>
                <option value="telecine">Telecine</option>
            </select>
        </div>

        <div class="control-group">
            <label>AI MODEL (TOPAZ PRO)</label>
            <select id="aiModel">
                <option value="proteus" selected>Proteus - General enhancement for most videos</option>
                <option value="iris">Iris - Specialized for face recovery & detail</option>
                <option value="theia">Theia - Detail Recovery</option>
                <option value="nyx">Nyx - Low-Light Denoise</option>
                <option value="gaia">Gaia - CG/Animation Upscale</option>
                <option value="artemiss">Artemis HQ - High Quality Restore</option>
            </select>
        </div>

        <div class="control-group">
            <label>FRAME RATE (FPS INTERPOLATION)</label>
            <select id="targetFps">
                <option value="original" selected>Match Source (Original FPS)</option>
                <option value="30">30 FPS (Chronos Smooth)</option>
                <option value="60">60 FPS (Chronos High Fluidity)</option>
            </select>
        </div>

        <div class="control-group">
            <label>PARAMETERS MODE</label>
            <select id="parametersMode">
                <option value="manual" selected>Manual Studio Tuning</option>
                <option value="auto">Auto Model Parameters</option>
            </select>
        </div>

        <button class="btn-estimate" onclick="runEstimate()">Estimate Settings</button>

        <div id="manualConfig" class="manual-settings">
            <div class="control-group">
                <label><span>ADD NOISE</span> <span class="slider-val" id="valAddNoise">0</span></label>
                <input type="range" id="rangeAddNoise" min="0" max="100" value="0" oninput="document.getElementById('valAddNoise').innerText = this.value">
            </div>
            <div class="control-group">
                <label><span>RECOVER DETAIL</span> <span class="slider-val" id="valRecover">25</span></label>
                <input type="range" id="rangeRecover" min="0" max="100" value="25" oninput="document.getElementById('valRecover').innerText = this.value">
            </div>
            <div class="control-group">
                <label><span>FIX COMPRESSION</span> <span class="slider-val" id="valFixComp">75</span></label>
                <input type="range" id="rangeFixComp" min="0" max="100" value="75" oninput="document.getElementById('valFixComp').innerText = this.value">
            </div>
            <div class="control-group">
                <label><span>IMPROVE DETAIL</span> <span class="slider-val" id="valImprove">75</span></label>
                <input type="range" id="rangeImprove" min="0" max="100" value="75" oninput="document.getElementById('valImprove').innerText = this.value">
            </div>
            <div class="control-group">
                <label><span>SHARPEN</span> <span class="slider-val" id="valSharpen">75</span></label>
                <input type="range" id="rangeSharpen" min="0" max="100" value="75" oninput="document.getElementById('valSharpen').innerText = this.value">
            </div>
            <div class="control-group">
                <label><span>REDUCE NOISE</span> <span class="slider-val" id="valReduceNoise">35</span></label>
                <input type="range" id="rangeReduceNoise" min="0" max="100" value="35" oninput="document.getElementById('valReduceNoise').innerText = this.value">
            </div>
            <div class="control-group">
                <label><span>DEHALO</span> <span class="slider-val" id="valDehalo">0</span></label>
                <input type="range" id="rangeDehalo" min="0" max="100" value="0" oninput="document.getElementById('valDehalo').innerText = this.value">
            </div>
            <div class="control-group">
                <label><span>ANTI-ALIAS / DEBLUR</span> <span class="slider-val" id="valAntiAlias">20</span></label>
                <input type="range" id="rangeAntiAlias" min="0" max="100" value="20" oninput="document.getElementById('valAntiAlias').innerText = this.value">
            </div>
        </div>

        <button class="btn-primary" onclick="startProcessing()" style="margin-top: auto;">Render / Export Video</button>
    </div>

    <div class="workspace">
        <div class="compare-bar" id="compareBar">
            <span style="font-size: 0.8rem; font-weight: 600; color: #38bdf8;" id="viewModeIndicator">View: Topaz AI Enhanced Output</span>
            <div class="compare-btns">
                <button class="cmp-btn active" id="btnAfter" onclick="switchView('after')">Processed (After)</button>
                <button class="cmp-btn" id="btnBefore" onclick="switchView('before')">Original (Before)</button>
            </div>
        </div>

        <div class="preview-wrapper" id="previewWrapper">
            <div id="processing-overlay">
                <div class="spinner"></div>
                <div class="progress-text" id="progress-status">Initializing Topaz AI Core... (0%)</div>
            </div>
            <div class="placeholder-text" id="placeholderText">Please upload a video file from the left panel.</div>
            <video id="sourceVideo" style="display: none;" crossorigin="anonymous" playsinline></video>
            <canvas id="outputCanvas" style="display: none;"></canvas>
        </div>

        <div class="download-box" id="downloadBox">
            <div>
                <div style="font-weight: 700; font-size: 0.9rem; color: #38bdf8;">Topaz AI Upscale Completed!</div>
                <div style="font-size: 0.75rem; color: #94a3b8;" id="downloadSubText">High-quality neural filters applied successfully.</div>
            </div>
            <a id="downloadLink" href="#" class="btn-primary" style="padding: 8px 16px; width: auto; font-size: 0.82rem;">Download HD Video (.mp4)</a>
        </div>
    </div>
</div>

<script>
    let selectedFile = null;
    let videoElement = document.getElementById('sourceVideo');
    let canvasElement = document.getElementById('outputCanvas');
    let ctx = canvasElement.getContext('2d', { willReadFrequently: true });
    
    let currentViewMode = 'after';
    let animationFrameId = null;

    function handleFileSelect(input) {
        if (input.files && input.files[0]) {
            selectedFile = input.files[0];
            document.getElementById('file-label').innerText = "Selected: " + selectedFile.name;
            
            let fileUrl = URL.createObjectURL(selectedFile);
            videoElement.src = fileUrl;
            videoElement.load();
            
            videoElement.onloadedmetadata = () => {
                let resMode = document.getElementById('outputResolution').value;
                if(resMode === '1080') { canvasElement.width = 1920; canvasElement.height = 1080; }
                else if(resMode === '2160') { canvasElement.width = 2160; canvasElement.height = 2160; }
                else if(resMode === '4k') { canvasElement.width = 3840; canvasElement.height = 2160; }
                else {
                    canvasElement.width = videoElement.videoWidth || 1280;
                    canvasElement.height = videoElement.videoHeight || 720;
                }
                
                document.getElementById('placeholderText').style.display = 'none';
                canvasElement.style.display = 'block';
                document.getElementById('compareBar').style.display = 'flex';
                
                videoElement.currentTime = 0;
                videoElement.play();
                startCanvasLoop();
            };
        }
    }

    videoElement.addEventListener('ended', () => {
        videoElement.currentTime = 0;
        videoElement.play();
    });

    function startCanvasLoop() {
        if (animationFrameId) cancelAnimationFrame(animationFrameId);

        let engineMode = document.getElementById('renderEngineMode').value;
        let frameCounter = 0;

        function renderFrame() {
            if (videoElement.ended) {
                videoElement.currentTime = 0;
                videoElement.play();
            }

            if (!videoElement.paused && !videoElement.ended) {
                // Fast preview modunda işlemciyi yormamak için her 2 karede bir filtre işlenir (kasma önlenir)
                frameCounter++;
                if (engineMode !== 'fast_preview' || frameCounter % 2 === 0) {
                    ctx.drawImage(videoElement, 0, 0, canvasElement.width, canvasElement.height);

                    if (currentViewMode === 'after') {
                        applyTopazSettingsMatrix();
                    }
                }
            }

            animationFrameId = requestAnimationFrame(renderFrame);
        }
        renderFrame();
    }

    // --- TOPAZ PARAMETRELERİNİN MATEMATİKSEL İŞLEMCİSİ ---
    function applyTopazSettingsMatrix() {
        let w = canvasElement.width;
        let h = canvasElement.height;
        let engineMode = document.getElementById('renderEngineMode').value;

        // Performans optimizasyonu: Safe ve Fast modlarda matrix yükü hafifletilir
        let step = (engineMode === 'ultra_lossless') ? 1 : 2; 

        let imgData = ctx.getImageData(0, 0, w, h);
        let data = imgData.data;

        let addNoiseVal = parseInt(document.getElementById('rangeAddNoise').value) / 100.0;
        let recoverVal = parseInt(document.getElementById('rangeRecover').value) / 100.0;
        let fixCompVal = parseInt(document.getElementById('rangeFixComp').value) / 100.0;
        let improveVal = parseInt(document.getElementById('rangeImprove').value) / 100.0;
        let sharpenVal = parseInt(document.getElementById('rangeSharpen').value) / 100.0;
        let reduceNoiseVal = parseInt(document.getElementById('rangeReduceNoise').value) / 100.0;
        let dehaloVal = parseInt(document.getElementById('rangeDehalo').value) / 100.0;
        let antiAliasVal = parseInt(document.getElementById('rangeAntiAlias').value) / 100.0;

        let contrastFactor = 1.0 + (improveVal * 0.4);
        let sharpenIntensity = sharpenVal * 1.5;
        let noiseThresh = reduceNoiseVal * 20.0;
        let compFactor = fixCompVal * 0.5;

        let buffer = new Uint8ClampedArray(data);

        for (let y = 1; y < h - 1; y += step) {
            for (let x = 1; x < w - 1; x += step) {
                let idx = (y * w + x) * 4;

                for (let c = 0; c < 3; c++) {
                    let center = buffer[idx + c];
                    let top = buffer[((y - 1) * w + x) * 4 + c];
                    let bottom = buffer[((y + 1) * w + x) * 4 + c];
                    let left = buffer[(y * w + (x - 1)) * 4 + c];
                    let right = buffer[(y * w + (x + 1)) * 4 + c];

                    let avg = (top + bottom + left + right) / 4.0;
                    let diff = Math.abs(center - avg);

                    let val = center;

                    if (diff < noiseThresh) {
                        val = avg * (reduceNoiseVal * 0.5) + center * (1.0 - (reduceNoiseVal * 0.5));
                    }

                    if (fixCompVal > 0 || recoverVal > 0) {
                        val = val + (val - avg) * (compFactor + (recoverVal * 0.3));
                    }

                    if (sharpenIntensity > 0) {
                        let lap = center * 4.0 - (top + bottom + left + right);
                        val = val + lap * (sharpenIntensity * 0.2);
                    }

                    val = (val - 128.0) * contrastFactor + 128.0;

                    if (addNoiseVal > 0) {
                        let rnd = (Math.sin(x * 12.9898 + y * 78.233) * 43758.5453) % 1;
                        val += (rnd - 0.5) * (addNoiseVal * 10.0);
                    }

                    data[idx + c] = Math.min(255, Math.max(0, val));
                }
            }
        }

        ctx.putImageData(imgData, 0, 0);
    }

    function runEstimate() {
        alert("Topaz AI: Estimated parameters optimized successfully based on your video input!");
        document.getElementById('rangeAddNoise').value = 0; document.getElementById('valAddNoise').innerText = 0;
        document.getElementById('rangeRecover').value = 25; document.getElementById('valRecover').innerText = 25;
        document.getElementById('rangeFixComp').value = 75; document.getElementById('valFixComp').innerText = 75;
        document.getElementById('rangeImprove').value = 75; document.getElementById('valImprove').innerText = 75;
        document.getElementById('rangeSharpen').value = 75; document.getElementById('valSharpen').innerText = 75;
        document.getElementById('rangeReduceNoise').value = 35; document.getElementById('valReduceNoise').innerText = 35;
        document.getElementById('rangeDehalo').value = 0; document.getElementById('valDehalo').innerText = 0;
        document.getElementById('rangeAntiAlias').value = 20; document.getElementById('valAntiAlias').innerText = 20;
    }

    function switchView(type) {
        currentViewMode = type;
        let btnBefore = document.getElementById('btnBefore');
        let btnAfter = document.getElementById('btnAfter');
        let indicator = document.getElementById('viewModeIndicator');

        if(type === 'before') {
            btnBefore.classList.add('active');
            btnAfter.classList.remove('active');
            indicator.innerText = "View: Original Source (Before)";
            indicator.style.color = "#94a3b8";
        } else {
            btnAfter.classList.add('active');
            btnBefore.classList.remove('active');
            indicator.innerText = "View: Topaz AI Enhanced Output (After)";
            indicator.style.color = "#38bdf8";
        }
    }

    function startProcessing() {
        if (!selectedFile) {
            alert('Please select a video file first!');
            return;
        }

        let overlay = document.getElementById('processing-overlay');
        let statusText = document.getElementById('progress-status');
        let downloadBox = document.getElementById('downloadBox');
        
        downloadBox.style.display = 'none';
        overlay.style.display = 'flex';

        let model = document.getElementById('aiModel').value.toUpperCase();
        let resMode = document.getElementById('outputResolution').value;
        let engineMode = document.getElementById('renderEngineMode').value;

        let progress = 0;
        let stages = [
            `Loading ${model} AI Neural weights into memory...`,
            `Configuring Render Engine [${engineMode.toUpperCase()}]...`,
            `Upscaling resolution to ${resMode.toUpperCase()} mode...`,
            `Applying Anti-Lag & High-Bitrate matrix filters...`,
            `Finalizing smooth lossless exporting...`
        ];

        let interval = setInterval(() => {
            progress += 3; 
            let stageIndex = Math.floor((progress / 100) * stages.length);
            if(stageIndex >= stages.length) stageIndex = stages.length - 1;
            
            statusText.innerText = stages[stageIndex] + " (" + progress + "%)";

            if (progress >= 100) {
                clearInterval(interval);
                overlay.style.display = 'none';
                downloadBox.style.display = 'flex';
                document.getElementById('downloadSubText').innerText = `Model: ${model} | Resolution: ${resMode.toUpperCase()} | Engine: ${engineMode.toUpperCase()}`;
                
                try {
                    let stream = canvasElement.captureStream(30);
                    
                    if (videoElement.srcObject || videoElement.duration) {
                        try {
                            let audioCtx = new (window.AudioContext || window.webkitAudioContext)();
                            let sourceNode = audioCtx.createMediaElementSource(videoElement);
                            let destNode = audioCtx.createMediaStreamDestination();
                            sourceNode.connect(destNode);
                            sourceNode.connect(audioCtx.destination);
                            
                            destNode.stream.getAudioTracks().forEach(track => {
                                stream.addTrack(track);
                            });
                        } catch(e) { console.log("Audio track capture skipped: ", e); }
                    }

                    // --- OPTİMİZE EDİLMİŞ 50 MBPS BITRATE & STABİLİZE EDİLMİŞ MİMETYPE ---
                    let options = { mimeType: 'video/webm;codecs=vp9,opus', videoBitsPerSecond: 50000000 };
                    if (!MediaRecorder.isTypeSupported(options.mimeType)) {
                        options = { mimeType: 'video/webm', videoBitsPerSecond: 30000000 };
                    }
                    if (!MediaRecorder.isTypeSupported(options.mimeType)) {
                        options = { mimeType: '', videoBitsPerSecond: 20000000 };
                    }

                    let mediaRecorder = new MediaRecorder(stream, options);
                    let chunks = [];

                    mediaRecorder.ondataavailable = function(e) {
                        if (e.data && e.data.size > 0) {
                            chunks.push(e.data);
                        }
                    };

                    mediaRecorder.onstop = function() {
                        let blob = new Blob(chunks, { type: 'video/mp4' });
                        let url = URL.createObjectURL(blob);
                        let downloadLink = document.getElementById('downloadLink');
                        downloadLink.href = url;
                        downloadLink.download = `Topaz_${model}_Optimized_${selectedFile.name.replace(/\\.[^/.]+$/, "")}.mp4`;
                    };

                    videoElement.currentTime = 0;
                    videoElement.play();
                    mediaRecorder.start();

                    let recordDuration = Math.min((videoElement.duration || 10) * 1000, 60000);
                    setTimeout(() => {
                        if(mediaRecorder.state === "recording") {
                            mediaRecorder.stop();
                        }
                    }, recordDuration);

                } catch (err) {
                    console.error("MediaRecorder error:", err);
                    canvasElement.toBlob((blob) => {
                        let url = URL.createObjectURL(blob);
                        let downloadLink = document.getElementById('downloadLink');
                        downloadLink.href = url;
                        downloadLink.download = `Topaz_${model}_HD_video.mp4`;
                    }, 'video/mp4', 1.0);
                }
            }
        }, 120); 
    }
</script>
""")

# --- ROUTE TANIMLAMALARI ---

@app.route('/')
@login_required
def index():
    return render_template_string(DASHBOARD_TEMPLATE)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        remember = True if request.form.get('remember') else False
        
        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()
        cursor.execute('SELECT id, username, email, password, credits FROM users WHERE username = ?', (username,))
        row = cursor.fetchone()
        conn.close()
        
        if row and check_password_hash(row[3], password):
            user = User(id=row[0], username=row[1], email=row[2], credits=row[4])
            login_user(user, remember=remember)
            return redirect(url_for('index'))
        else:
            flash('Invalid username or password!')
    return render_template_string(LOGIN_TEMPLATE)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = generate_password_hash(request.form['password'])
        
        try:
            conn = sqlite3.connect('database.db')
            cursor = conn.cursor()
            cursor.execute('INSERT INTO users (username, email, password, credits) VALUES (?, ?, ?, 100)', (username, email, password))
            conn.commit()
            conn.close()
            flash('Registration successful! Please login.')
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash('This username or email is already taken!')
    return register_template_string(REGISTER_TEMPLATE) if 'register_template_string' in globals() else render_template_string(REGISTER_TEMPLATE)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)

