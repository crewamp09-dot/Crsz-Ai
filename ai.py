<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="UTF-8">
<title>Modern Giriş</title>
<link href="https://fonts.googleapis.com/css2?family=Roboto:wght@400;500&display=swap" rel="stylesheet">
<style>
  :root{
    --bg:#0f0f0f;
    --glass:#ffffff1a;
    --blur:12px;
    --radius:12px;
    --shadow:0 4px 30px rgba(0,0,0,0.5);
    --primary:#00bcd4;
    --text:#e0e0e0;
  }
  *{margin:0;padding:0;box-sizing:border-box;font-family:'Roboto',sans-serif;}
  body{
    min-height:100vh;
    background:linear-gradient(135deg,#1a1a2e,#16213e);
    display:flex;align-items:center;justify-content:center;
    color:var(--text);
  }
  .login-card{
    background:var(--glass);
    backdrop-filter:blur(var(--blur));
    -webkit-backdrop-filter:blur(var(--blur));
    border-radius:var(--radius);
    box-shadow:var(--shadow);
    width:320px;
    padding:2rem;
    display:flex;flex-direction:column;gap:1.5rem;
  }
  .login-card h2{
    text-align:center;
    font-weight:500;
    color:var(--primary);
  }
  .input-group{
    position:relative;
  }
  .input-group input{
    width:100%;
    padding:0.75rem 1rem;
    border:none;
    border-radius:var(--radius);
    background:rgba(255,255,255,0.1);
    color:var(--text);
    font-size:1rem;
    outline:none;
    transition:background 0.3s;
  }
  .input-group input:focus{
    background:rgba(255,255,255,0.2);
  }
  .input-group label{
    position:absolute;
    top:50%;
    left:1rem;
    transform:translateY(-50%);
    pointer-events:none;
    color:rgba(255,255,255,0.6);
    transition:all 0.3s;
  }
  .input-group input:focus + label,
  .input-group input:not(:placeholder-shown) + label{
    top:0;
    left:0.75rem;
    font-size:0.75rem;
    color:var(--primary);
    transform:translateY(-50%);
    background:var(--glass);
    padding:0 0.25rem;
  }
  .btn{
    width:100%;
    padding:0.75rem;
    border:none;
    border-radius:var(--radius);
    background:var(--primary);
    color:#fff;
    font-size:1rem;
    cursor:pointer;
    transition:background 0.3s;
  }
  .btn:hover{background:#0097a7;}
  .forgot{
    text-align:center;
    font-size:0.9rem;
    color:rgba(255,255,255,0.7);
    text-decoration:none;
    transition:color 0.3s;
  }
  .forgot:hover{color:#fff;}
</style>
</head>
<body>
  <form class="login-card" action="#" method="POST">
    <h2>Giriş Yap</h2>
    <div class="input-group">
      <input type="email" name="email" required placeholder=" ">
      <label>E-posta</label>
    </div>
    <div class="input-group">
      <input type="password" name="password" required placeholder=" ">
      <label>Şifre</label>
    </div>
    <button type="submit" class="btn">Giriş</button>
    <a href="#" class="forgot">Şifremi Unuttum?</a>
  </form>
</body>
</html>


