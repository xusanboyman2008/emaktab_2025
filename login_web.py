import asyncio

from flask import Flask, request, render_template_string, jsonify
import secrets
import requests

from database import create_login
from login_by_username import login_by_user

app = Flask(__name__)
app.secret_key = secrets.token_urlsafe(32)
captcha_id = "859746ee-eb11-4ec1-9771-b835c710941b"

file = '''<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>Login with Captcha</title>
  <style>
    /* (your CSS kept concise) */
    *{box-sizing:border-box;margin:0;padding:0;font-family:"Segoe UI",Tahoma,Arial,sans-serif}
    body{min-height:100vh;display:flex;align-items:center;justify-content:center;background:linear-gradient(135deg,#4facfe,#00f2fe);padding:20px}
    .container{background:#fff;border-radius:20px;padding:30px 25px;width:100%;max-width:400px;box-shadow:0 10px 30px rgba(0,0,0,.15);display:flex;flex-direction:column;gap:20px}
    h2{text-align:center;font-size:1.6rem;color:#333}
    .input-group{display:flex;flex-direction:column;gap:8px}
    #captchaImage{width:70%}
    .input-group input{padding:12px 14px;border:2px solid #ddd;border-radius:12px;font-size:1rem;outline:none}
    .captcha-section{display:flex;align-items:center;gap:12px;flex-direction:column}
    .captcha-section img{width:120px;height:45px;object-fit:cover;border-radius:10px;border:2px solid #ddd}
    .refresh-btn{background:#4facfe;border:none;border-radius:10px;padding:8px 12px;color:white;cursor:pointer}
    .submit-btn{padding:14px;border:none;border-radius:14px;font-size:1rem;font-weight:700;background:linear-gradient(135deg,#4facfe,#00f2fe);color:#fff;cursor:pointer}
  </style>

  <!-- SweetAlert2 for nicer popups (optional) -->
  <script src="https://cdn.jsdelivr.net/npm/sweetalert2@11"></script>
</head>
<body>
  <form id="loginForm" method="POST" novalidate>
    <div class="container">
      <h2>Login</h2>

      <div class="input-group">
      <input id="captcha_id" name="captcha_id" value="{{ captcha_id }}" style="display:none">
      <input id="tg_id" value="{{ tg_id }}" name="tg_id" style="display:none">
        <label for="username">Username</label>
        <input id="username" name="username" type="text" value="{{ username }}" required />
      </div>
    
      <div class="input-group" style="position:relative;">
        <label for="password">Password</label>
        <div style="position:relative;">
          <input id="password" name="password" type="password" value="{{ password }}" placeholder="Enter your password" style="padding-right:44px" required />
          <button type="button" id="togglePassword" title="Show password" style="position:absolute;right:6px;top:50%;transform:translateY(-50%);border:0;background:transparent;cursor:pointer;padding:6px;border-radius:6px">
            <svg id="eyeOpen" xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8S1 12 1 12z"></path><circle cx="12" cy="12" r="3"></circle>
            </svg>
            <svg id="eyeClosed" xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="display:none">
              <path d="M17.94 17.94A10.94 10.94 0 0 1 12 20c-7 0-11-8-11-8a21.86 21.86 0 0 1 5.06-6.06"></path>
              <path d="M1 1l22 22"></path>
              <path d="M9.88 9.88A3 3 0 0 0 14.12 14.12"></path>
            </svg>
          </button>
        </div>
      </div>

      <div class="input-group">
        <label for="captcha">Captcha</label>
        <div class="captcha-section">
          <input id="captcha" name="captcha" type="text" placeholder="Enter captcha" required />
          <img id="captchaImage" src="https://login.emaktab.uz/captcha/true/{{ captcha_id }}" alt="captcha" />
          <button type="button" class="refresh-btn" onclick="refreshCaptcha()">↻</button>
        </div>
      </div>

      <button type="submit" class="submit-btn">Login</button>
    </div>
  </form>

<script>
document.addEventListener('DOMContentLoaded', function () {
  // password show/hide
  const pwd = document.getElementById('password');
  const toggleBtn = document.getElementById('togglePassword');
  const eyeOpen = document.getElementById('eyeOpen');
  const eyeClosed = document.getElementById('eyeClosed');

  toggleBtn.addEventListener('click', function () {
    const isHidden = pwd.type === 'password';
    pwd.type = isHidden ? 'text' : 'password';
    eyeOpen.style.display = isHidden ? 'none' : 'inline';
    eyeClosed.style.display = isHidden ? 'inline' : 'none';
    toggleBtn.setAttribute('aria-pressed', String(isHidden));
    toggleBtn.title = isHidden ? 'Hide password' : 'Show password';
  });

  // handle AJAX form submit
  const form = document.getElementById('loginForm');
  form.addEventListener('submit', async function (e) {
    e.preventDefault();
    const submitBtn = form.querySelector('button[type="submit"]');
    submitBtn.disabled = true;

    const fd = new FormData(form);
    try {
      const res = await fetch('/login', { method: 'POST', body: fd });
      if (!res.ok) throw new Error('Server returned ' + res.status);
      const data = await res.json();

      if (window.Swal) {
        Swal.fire({
          icon: data.success ? 'success' : 'error',
          title: data.success ? 'Success' : 'Error',
          text: data.message
        });
      } else {
        alert(data.message);
      }

      if (data.success) {
        form.reset();
      } else {
        // refresh captcha on failure
        refreshCaptcha();
      }
    } catch (err) {
      if (window.Swal) {
        Swal.fire('Network error', err.message || String(err), 'error');
      } else {
        alert('Network error: ' + err);
      }
    } finally {
      submitBtn.disabled = false;
    }
  });
});

// refresh captcha function (global)
function refreshCaptcha() {
  const captcha = document.getElementById('captchaImage');
let url = captcha.getAttribute("src");
  console.log(url)
  const base = url;
  captcha.src = base + '?_=' + Date.now();
}
</script>
</body>
</html>
'''

@app.route("/", methods=["GET"])
def home():
    username = request.args.get("username", "")
    password = request.args.get("password", "")
    tg_id = request.args.get("tg_id", "")
    captcha = request.args.get("captcha",captcha_id)
    if not tg_id:
        return jsonify('fuck off bitch who you think are you ')
    return render_template_string(file, username=username, password=password,captcha_id=captcha,tg_id=tg_id)
loop = asyncio.get_event_loop()  # reuse one loop
@app.route("/login", methods=["POST"])
def login():
    username = request.form.get("username", "")
    password = request.form.get("password", "")
    captcha = request.form.get("captcha", "")
    captcha_id = request.form.get("captcha_id", "")
    tg_id = request.form.get("tg_id", "")
    print(username,password,captcha_id,captcha)

    cookie_len,cookie = loop.run_until_complete(login_by_user(username=username, password=password, captcha_text=captcha,captcha_id=captcha_id))
    print(cookie_len)
    if cookie_len>3:
        a = loop.run_until_complete(create_login(password=password,username=username,last_login=True,cookie= cookie,tg_id=tg_id))
        return jsonify({"success": True, "message": "Foydalanuvchi muvaffaqiyatli qo‘shildi!"})
    else:
        return jsonify({"success": False, "message": "Login yoki parol noto‘g‘ri."})


if __name__ == "__main__":
    app.run(debug=True,port=0000)
