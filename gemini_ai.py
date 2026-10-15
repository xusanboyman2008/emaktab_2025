import aiohttp
import os
import json
import sqlite3
import re

GEMINI_API_KEYS = [
    os.getenv("GEMINI_API_KEY", "AQ.Ab8RN6Ih3gXnAjLQbEFdU1mh_-fGMbC0qJ7FuCGOBAhmSGmr5g"),
    os.getenv("GEMINI_BACKUP_KEY", "AQ.Ab8RN6LZKD2CWTEmAtJ2Q7O6-J-Ed12HrXcinzqpJb6FBGF80A")
]
_CURRENT_KEY_IDX = 0

def get_ordered_api_keys() -> list[str]:
    """Returns keys starting with the currently active key for seamless rotation & cycling."""
    global _CURRENT_KEY_IDX
    n = len(GEMINI_API_KEYS)
    return [GEMINI_API_KEYS[(i + _CURRENT_KEY_IDX) % n] for i in range(n)]

def mark_key_exhausted(exhausted_key: str):
    """When a key runs out of quota or credits, immediately switch active index to next key."""
    global _CURRENT_KEY_IDX
    if exhausted_key in GEMINI_API_KEYS:
        idx = GEMINI_API_KEYS.index(exhausted_key)
        if idx == _CURRENT_KEY_IDX:
            _CURRENT_KEY_IDX = (_CURRENT_KEY_IDX + 1) % len(GEMINI_API_KEYS)
            print(f"🔄 Switched active Gemini API key from index {idx} to {_CURRENT_KEY_IDX} (...{GEMINI_API_KEYS[_CURRENT_KEY_IDX][-6:]})")

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-flash-lite-latest")

DB_PATH = '/home/ubuntu/emaktab_2025/database.sqlite3' if os.path.exists('/home/ubuntu/emaktab_2025/database.sqlite3') else '/home/xusanboyman/emaktab_2025/database.sqlite3'

def tool_get_system_stats():
    """eMaktab tizimidagi barcha maktablar, sinflar, loginlar soni, kirilgan va kirilmaganlar umumiy statistikasini qaytaradi."""
    try:
        con = sqlite3.connect(DB_PATH)
        cur = con.cursor()
        cur.execute("SELECT count(*) FROM Logins;")
        total = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM Logins WHERE last_login = 1;")
        succ = cur.fetchone()[0]
        fail = total - succ
        cur.execute("SELECT grade, count(*), sum(case when last_login=1 then 1 else 0 end) FROM Logins GROUP BY grade ORDER BY grade;")
        classes = [{"sinf": g, "jami": cnt, "ishlayapti": ok or 0, "xato": cnt - (ok or 0)} for g, cnt, ok in cur.fetchall()]
        cur.execute("SELECT id, school_number, place FROM School_number;")
        schools = [{"id": r[0], "raqam": r[1], "joy": r[2]} for r in cur.fetchall()]
        con.close()
        return {"jami_loginlar": total, "kirilgan": succ, "kirilmagan": fail, "sinflar": classes, "maktablar": schools}
    except Exception as e:
        return {"error": str(e)}

def tool_get_failed_logins(sinf: str = None):
    """Xatolik berayotgan (kirilmagan/last_login=0) loginlar ro'yxatini qaytaradi."""
    try:
        con = sqlite3.connect(DB_PATH)
        cur = con.cursor()
        if sinf:
            cur.execute("SELECT id, username, password, grade FROM Logins WHERE last_login = 0 AND grade = ?;", (sinf.upper().strip(),))
        else:
            cur.execute("SELECT id, username, password, grade FROM Logins WHERE last_login = 0 LIMIT 30;")
        rows = [{"id": r[0], "login": r[1], "parol": r[2], "sinf": r[3]} for r in cur.fetchall()]
        con.close()
        return {"xato_loginlar": rows, "jami_xato_soni": len(rows)}
    except Exception as e:
        return {"error": str(e)}

def tool_find_student_login(username: str):
    """Bazada ma'lum bir login bo'yicha o'quvchi ma'lumotlarini qidiradi (faqat administrator)."""
    try:
        con = sqlite3.connect(DB_PATH)
        cur = con.cursor()
        cur.execute("SELECT id, school, username, grade, last_login, password, is_paid, updated_at FROM Logins WHERE username LIKE ?;", (f"%{username.strip()}%",))
        rows = [{"id": r[0], "maktab_id": r[1], "login": r[2], "sinf": r[3], "kirilgan": bool(r[4]), "parol": r[5], "tolangan": bool(r[6]), "yangilangan": str(r[7])} for r in cur.fetchall()]
        con.close()
        return {"topilganlar": rows, "soni": len(rows)}
    except Exception as e:
        return {"error": str(e)}

def tool_get_grade_logins(grade: str):
    """Muayyan sinfdagi barcha loginlar, parollar, to'lov va holatini qaytaradi (faqat administrator)."""
    try:
        g_clean = grade.strip().upper().replace("-", "").replace(" ", "")
        con = sqlite3.connect(DB_PATH)
        cur = con.cursor()
        cur.execute("SELECT id, username, password, grade, last_login, is_paid, updated_at FROM Logins WHERE REPLACE(UPPER(grade), '-', '') = ? ORDER BY username;", (g_clean,))
        rows = [{"id": r[0], "login": r[1], "parol": r[2], "sinf": r[3], "kirilgan": bool(r[4]), "tolangan": bool(r[5]), "yangilangan": str(r[6])} for r in cur.fetchall()]
        con.close()
        return {"sinf": g_clean, "jami_loginlar": len(rows), "loginlar": rows}
    except Exception as e:
        return {"error": str(e)}

def tool_update_student_password(username: str, new_password: str):
    """O'quvchi yoki ota-onaning eMaktab parolini bazada yangilaydi."""
    try:
        con = sqlite3.connect(DB_PATH)
        cur = con.cursor()
        cur.execute("SELECT id, username, grade FROM Logins WHERE username = ? OR username LIKE ?;", (username.strip(), f"%{username.strip()}%"))
        row = cur.fetchone()
        if not row:
            con.close()
            return {"success": False, "error": f"'{username}' logini bazadan topilmadi."}
        lid, u_name, grade = row
        cur.execute("UPDATE Logins SET password = ?, last_cookie = NULL, updated_at = datetime('now') WHERE id = ?;", (new_password.strip(), lid))
        con.commit()
        con.close()
        return {"success": True, "message": f"{u_name} ({grade}-sinf) paroli muvaffaqiyatli '{new_password}' ga o'zgartirildi."}
    except Exception as e:
        return {"success": False, "error": str(e)}

def tool_set_login_payment_status(username: str, is_paid: bool):
    """Yakka o'quvchi/ota-ona loginining to'lov holatini belgilaydi (True = to'langan, False = to'lanmagan/qulflangan)."""
    try:
        con = sqlite3.connect(DB_PATH)
        cur = con.cursor()
        cur.execute("SELECT id, username, grade FROM Logins WHERE username = ? OR username LIKE ?;", (username.strip(), f"%{username.strip()}%"))
        row = cur.fetchone()
        if not row:
            con.close()
            return {"success": False, "error": f"'{username}' logini bazadan topilmadi."}
        lid, u_name, grade = row
        val = 1 if is_paid else 0
        cur.execute("UPDATE Logins SET is_paid = ?, updated_at = datetime('now') WHERE id = ?;", (val, lid))
        con.commit()
        con.close()
        holat = "To'langan deb belgilandi" if is_paid else "To'lanmagan (qulflangan) deb belgilandi"
        return {"success": True, "message": f"{u_name} ({grade}-sinf) hisobi: {holat}."}
    except Exception as e:
        return {"success": False, "error": str(e)}

def tool_set_grade_status(grade: str, is_allowed: bool = None, is_paid: bool = None, trial_days: int = 7):
    """Sinfning ruxsat va to'lov holatini sozlaydi (masalan: 7A ni to'langan qilish, yoki sinfni qulflash/ochish)."""
    try:
        g_clean = grade.strip().upper().replace("-", "").replace(" ", "")
        con = sqlite3.connect(DB_PATH)
        cur = con.cursor()
        cur.execute("SELECT grade, is_allowed, is_paid, allowed_until FROM Grade WHERE UPPER(grade) = ?;", (g_clean,))
        row = cur.fetchone()
        if not row:
            cur.execute("INSERT INTO Grade (grade, is_allowed, is_paid, allowed_until) VALUES (?, ?, ?, NULL);",
                        (g_clean, 1 if is_allowed is not False else 0, 1 if is_paid else 0))
            con.commit()
        
        updates = []
        params = []
        if is_paid is not None:
            updates.append("is_paid = ?")
            params.append(1 if is_paid else 0)
            if is_paid:
                updates.append("is_allowed = 1")
                updates.append("allowed_until = NULL")
        if is_allowed is not None and not is_paid:
            updates.append("is_allowed = ?")
            params.append(1 if is_allowed else 0)
            if is_allowed:
                updates.append("allowed_until = datetime('now', ?)")
                params.append(f"+{trial_days} days")
            else:
                updates.append("allowed_until = NULL")

        if updates:
            params.append(g_clean)
            cur.execute(f"UPDATE Grade SET {', '.join(updates)} WHERE UPPER(grade) = ?;", params)
            con.commit()

        con.close()
        return {"success": True, "message": f"{g_clean}-sinf holati muvaffaqiyatli yangilandi."}
    except Exception as e:
        return {"success": False, "error": str(e)}

def tool_delete_student_login(username: str):
    """O'quvchi yoki ota-ona loginini bazadan to'liq o'chiradi."""
    try:
        con = sqlite3.connect(DB_PATH)
        cur = con.cursor()
        cur.execute("SELECT id, username, grade FROM Logins WHERE username = ? OR username LIKE ?;", (username.strip(), f"%{username.strip()}%"))
        row = cur.fetchone()
        if not row:
            con.close()
            return {"success": False, "error": f"'{username}' logini bazadan topilmadi."}
        lid, u_name, grade = row
        cur.execute("DELETE FROM Logins_data WHERE login_id = ?;", (lid,))
        cur.execute("DELETE FROM Logins WHERE id = ?;", (lid,))
        con.commit()
        con.close()
        return {"success": True, "message": f"{u_name} ({grade}-sinf) logini bazadan muvaffaqiyatli o'chirildi."}
    except Exception as e:
        return {"success": False, "error": str(e)}

def tool_set_bot_setting(key: str, value: str):
    """Bot sozlamalarini o'zgartiradi (masalan: check_time -> '07:00' yoki '06:30')."""
    try:
        con = sqlite3.connect(DB_PATH)
        cur = con.cursor()
        cur.execute("INSERT INTO BotSetting (key, value, updated_at) VALUES (?, ?, datetime('now')) ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at;", (key.strip(), value.strip()))
        con.commit()
        con.close()
        return {"success": True, "message": f"Sozlama '{key}' muvaffaqiyatli '{value}' ga o'zgartirildi."}
    except Exception as e:
        return {"success": False, "error": str(e)}

PUBLIC_FUNCTION_DECLARATIONS = [
    {
        "name": "tool_get_system_stats",
        "description": "Tizimdagi barcha maktablar va sinflar kesimida umumiy statistika (kirilgan va kirilmagan loginlar soni, qaysi sinflar kirganligi). Hech qanday shaxsiy login yoki parol berilmaydi, faqat umumiy hisobot.",
        "parameters": {"type": "OBJECT", "properties": {}}
    }
]

ADMIN_FUNCTION_DECLARATIONS = [
    {
        "name": "tool_get_grade_logins",
        "description": "Faqat administrator uchun: Muayyan sinfdagi (masalan '7A') barcha o'quvchi va ota-onalar loginlari, parollari, to'lov va kirish holatlarini ro'yxat qilib ko'rish.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "grade": {"type": "STRING", "description": "Sinf nomi (masalan: '7A', '4B')"}
            },
            "required": ["grade"]
        }
    },
    {
        "name": "tool_get_failed_logins",
        "description": "Faqat administrator uchun: Tizimga kirishda xatolik berayotgan loginlar, ularning parollari va sinflarini ko'rish.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "sinf": {"type": "STRING", "description": "Muayyan sinf (masalan: '4B', '7A'). Agar berilmasa, barcha sinflardan olinadi."}
            }
        }
    },
    {
        "name": "tool_find_student_login",
        "description": "Faqat administrator uchun: Bazada o'quvchi loginini qidirish, uning paroli, sinfi, to'lovi va holatini tekshirish.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "username": {"type": "STRING", "description": "O'quvchi logini"}
            },
            "required": ["username"]
        }
    },
    {
        "name": "tool_update_student_password",
        "description": "Faqat administrator uchun: Biror loginning parolini yangilash.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "username": {"type": "STRING", "description": "Login (username)"},
                "new_password": {"type": "STRING", "description": "Yangi parol"}
            },
            "required": ["username", "new_password"]
        }
    },
    {
        "name": "tool_set_login_payment_status",
        "description": "Faqat administrator uchun: Muayyan loginning to'langan/to'lanmagan holatini o'zgartirish.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "username": {"type": "STRING", "description": "Login (username)"},
                "is_paid": {"type": "BOOLEAN", "description": "To'langan bo'lsa True, to'lanmagan/qulflangan bo'lsa False"}
            },
            "required": ["username", "is_paid"]
        }
    },
    {
        "name": "tool_set_grade_status",
        "description": "Faqat administrator uchun: Sinfning ruxsat yoki to'lov holatini sozlash (masalan 7A ni to'langan qilish, yoki qulflash/ochish).",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "grade": {"type": "STRING", "description": "Sinf nomi (masalan '7A', '10B')"},
                "is_allowed": {"type": "BOOLEAN", "description": "Sinfga ruxsat berish (True) yoki qulflash (False)"},
                "is_paid": {"type": "BOOLEAN", "description": "Sinf to'langan (True) yoki yo'q (False)"},
                "trial_days": {"type": "INTEGER", "description": "Ruxsat berilganda sinov kunlari soni (standart 7 kun)"}
            },
            "required": ["grade"]
        }
    },
    {
        "name": "tool_delete_student_login",
        "description": "Faqat administrator uchun: Loginni bazadan butunlay o'chirish.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "username": {"type": "STRING", "description": "O'chirilishi kerak bo'lgan login"}
            },
            "required": ["username"]
        }
    },
    {
        "name": "tool_set_bot_setting",
        "description": "Faqat administrator uchun: Bot sozlamasini o'zgartirish (masalan: check_time -> '07:00').",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "key": {"type": "STRING", "description": "Sozlama kaliti (masalan 'check_time')"},
                "value": {"type": "STRING", "description": "Yangi qiymat (masalan '07:00')"}
            },
            "required": ["key", "value"]
        }
    }
]

ADMIN_TOOL_NAMES = {tool["name"] for tool in ADMIN_FUNCTION_DECLARATIONS}

SYSTEM_INSTRUCTION = (
    "Siz eMaktab tizimi bo'yicha aqlli yordamchisiz. "
    "QAT'IY QOIDA: Javoblaringiz nihoyatda ixcham, qisqa va aniq bo'lsin. "
    "Keraksiz uzun kirish, lutf yoki xulosalarsiz, minimal so'zlar bilan javob bering. "
    "Foydalanuvchi oddiy matn yozsa yoki salomlashsa, 1-2 jumlada qisqa javob bering. "
    "Statistika yoki ma'lumot so'ralsa, eng zarur raqam va faktlarni qisqa formatda bering. "
    "O'zbek tilida so'zlang."
)


FALLBACK_MODELS = [
    os.getenv("GEMINI_MODEL", "gemini-flash-lite-latest"),
    "gemini-flash-latest",
    "gemini-2.5-flash"
]

import io
import base64

async def ask_gemini(prompt: str, user_name: str = "", is_admin: bool = False) -> str:
    """Asynchronously calls Gemini API with active key cycling and role-based tool support."""
    context_prefix = f"[Foydalanuvchi: {user_name} | Rol: {'Administrator' if is_admin else 'Oddiy foydalanuvchi'}]\n" if user_name else ""
    user_text = f"{context_prefix}{prompt}"

    if is_admin:
        tools_schema = [{"function_declarations": PUBLIC_FUNCTION_DECLARATIONS + ADMIN_FUNCTION_DECLARATIONS}]
        system_inst = (
            SYSTEM_INSTRUCTION + "\n"
            "DIQQAT: Ushbu foydalanuvchi tizim ADMINISTRATORI (Owner/Admin) hisoblanadi.\n"
            "Siz uning topshirig'i bo'yicha barcha ma'lumotlar bazasini ko'rish (o'quvchi va ota-onalar loginlari, parollari, sinflar ro'yxati, to'lovlar, xatolar) "
            "va unga har qanday O'ZGARTIRISH kiritish (parolni yangilash, to'lov/ruxsat holatini sozlash, loginni o'chirish, sozlamalarni yangilash) CHEKSIZ VAKOLATIGA EGASIZ. "
            "Administrator so'ragan har qanday ma'lumotni to'liq bering va buyurgan o'zgartirishlarini bajaring."
        )
    else:
        tools_schema = [{"function_declarations": PUBLIC_FUNCTION_DECLARATIONS}]
        system_inst = (
            SYSTEM_INSTRUCTION + "\n"
            "DIQQAT: Ushbu foydalanuvchi ODDIY FOYDALANUVCHI (administrator EMAS).\n"
            "QAT'IY XAVFSIZLIK VA SHAXSIY MA'LUMOTLAR MAXFIYLIGI QOIDALARI:\n"
            "1. Foydalanuvchilar faqat o'z login va parollarini tizimga kiritishlari mumkin (botga login va parol yuborish orqali).\n"
            "2. BAZADAGI O'QUVCHILAR HAQIDAGI SHAXSIY MA'LUMOTLARNI (LOGINLAR, PAROLLAR, ISMLAR) USHBU FOYDALANUVCHIGA O'QIB BERISH YOKI KO'RSATISH MUTLAQO TAQIQLANADI! "
            "Agar foydalanuvchi biror o'quvchi, uning logini yoki paroli haqida so'rasa, 'Shaxsiy ma'lumotlar va login/parollar maxfiy bo'lib, ularni faqat administrator ko'rishi mumkin' deb rad eting.\n"
            "3. Siz oddiy foydalanuvchiga FAQAT umumiy statistika (masalan: qaysi sinflar kirgan, nechta login faol, umumiy tizim holati) haqida javob bera olasiz (`tool_get_system_stats` orqali). "
            "Hech qanday shaxsiy login yoki parol aytilmaydi.\n"
            "4. Bazaga o'zgartirish kiritish (parol almashtirish, o'chirish, to'lovni yoqish) qat'iyan taqiqlangan, faqat administrator uchun mumkin."
        )

    for api_key in get_ordered_api_keys():
        for model_name in FALLBACK_MODELS:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
            contents = [
                {"role": "user", "parts": [{"text": user_text}]}
            ]

            payload = {
                "system_instruction": {
                    "parts": [{"text": system_inst}]
                },
                "tools": tools_schema,
                "contents": contents,
                "generationConfig": {
                    "temperature": 0.5,
                    "maxOutputTokens": 1000
                }
            }

            try:
                timeout = aiohttp.ClientTimeout(total=25, connect=6)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.post(url, json=payload) as resp:
                        if resp.status in (429, 403):
                            print(f"Gemini {model_name} quota/limit ({resp.status}) on key ...{api_key[-6:]}. Rotating key...")
                            mark_key_exhausted(api_key)
                            break  # Break model loop to jump directly to next active API key
                        if resp.status != 200:
                            err_txt = await resp.text()
                            print(f"Gemini {model_name} API error ({resp.status}): {err_txt}")
                            continue

                        data = await resp.json()
                        candidates = data.get("candidates", [])
                        if not candidates:
                            continue
                        candidate = candidates[0]
                        parts = candidate.get("content", {}).get("parts", [])

                        for part in parts:
                            if "functionCall" in part:
                                fc = part["functionCall"]
                                fname = fc.get("name")
                                fargs = fc.get("args", {})
                                
                                # Execute local tool with strict privacy & admin security check
                                if not is_admin and fname != "tool_get_system_stats":
                                    f_result = {
                                        "success": False,
                                        "error": "Ruxsat berilmagan! O'quvchilar shaxsiy ma'lumotlari, login/parollar va o'zgartirishlar faqat administrator uchun ochiq. Siz faqat umumiy statistikani ko'rishingiz mumkin."
                                    }
                                elif fname == "tool_get_system_stats":
                                    f_result = tool_get_system_stats()
                                elif fname == "tool_get_grade_logins":
                                    f_result = tool_get_grade_logins(**fargs)
                                elif fname == "tool_get_failed_logins":
                                    f_result = tool_get_failed_logins(**fargs)
                                elif fname == "tool_find_student_login":
                                    f_result = tool_find_student_login(**fargs)
                                elif fname == "tool_update_student_password":
                                    f_result = tool_update_student_password(**fargs)
                                elif fname == "tool_set_login_payment_status":
                                    f_result = tool_set_login_payment_status(**fargs)
                                elif fname == "tool_set_grade_status":
                                    f_result = tool_set_grade_status(**fargs)
                                elif fname == "tool_delete_student_login":
                                    f_result = tool_delete_student_login(**fargs)
                                elif fname == "tool_set_bot_setting":
                                    f_result = tool_set_bot_setting(**fargs)
                                else:
                                    f_result = {}

                                contents.append(candidate["content"])
                                fr_part = {
                                    "functionResponse": {
                                        "name": fname,
                                        "response": {"result": f_result}
                                    }
                                }
                                if "id" in fc:
                                    fr_part["functionResponse"]["id"] = fc["id"]

                                contents.append({
                                    "role": "user",
                                    "parts": [fr_part]
                                })

                                payload["contents"] = contents
                                async with session.post(url, json=payload) as resp2:
                                    if resp2.status == 200:
                                        data2 = await resp2.json()
                                        res_parts = data2.get("candidates", [{}])[0].get("content", {}).get("parts", [])
                                        if res_parts:
                                            return res_parts[0].get("text", "").strip()
                                    else:
                                        err_txt2 = await resp2.text()
                                        print(f"Gemini {model_name} resp2 error ({resp2.status}): {err_txt2}")
                                    return "Ma'lumotlar tahlil qilindi, biroq javob shakllantirishda xatolik yuz berdi."

                            if "text" in part:
                                return part["text"].strip()

            except Exception as e:
                print(f"Gemini request exception for {model_name}: {e}")
                continue

    return "Kechirasiz, sun'iy intellekt xizmatida vaqtinchalik uzilish yuz berdi. Iltimos, keyinroq qayta urinib ko'ring."

async def extract_logins_from_text(raw_text: str) -> list[dict]:
    """Uses Gemini to extract eMaktab student logins and passwords from text/table."""
    prompt = (
        "Quyidagi matn, ro'yxat yoki fayl tarkibidan barcha eMaktab o'quvchi login va parollarini ajratib ol.\n"
        "Faqat quyidagi aniq JSON formatida qaytar:\n"
        "{\"logins\": [{\"username\": \"login1\", \"password\": \"parol1\"}, ...]}\n"
        "Agar biror loginning paroli bo'lmasa, uni qo'shma. Boshqa hech qanday izoh qo'shma, faqat JSON format:\n\n"
        + raw_text[:35000]
    )

    for api_key in get_ordered_api_keys():
        for model_name in FALLBACK_MODELS:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
            payload = {
                "contents": [
                    {
                        "role": "user",
                        "parts": [{"text": prompt}]
                    }
                ]
            }

            try:
                timeout = aiohttp.ClientTimeout(total=30, connect=6)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.post(url, json=payload) as resp:
                        if resp.status in (429, 403):
                            mark_key_exhausted(api_key)
                            break
                        if resp.status == 200:
                            data = await resp.json()
                            candidates = data.get("candidates", [])
                            if candidates:
                                raw_json = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "").strip()
                                if "```json" in raw_json:
                                    raw_json = raw_json.split("```json")[1].split("```")[0].strip()
                                elif "```" in raw_json:
                                    raw_json = raw_json.split("```")[1].split("```")[0].strip()
                                parsed = json.loads(raw_json)
                                raw_list = parsed.get("logins", [])
                                clean_list = []
                                for item in raw_list:
                                    u = str(item.get("username", "")).strip()
                                    p = str(item.get("password", "")).strip()
                                    if " " in u and not u.startswith("http"):
                                        u = u.replace(" ", "")
                                    if u and p:
                                        clean_list.append({"username": u, "password": p})
                                return clean_list
            except Exception as e:
                continue


    return []

async def extract_logins_from_image(image_bytes: bytes, mime_type: str = "image/jpeg") -> list[dict]:
    """Uses Gemini Vision to read logins/passwords from an image (photo, screenshot, paper list)."""
    b64_data = base64.b64encode(image_bytes).decode('utf-8')
    prompt = (
        "Ushbu rasmdan (ro'yxat, qog'oz, skrinshot yoki jadvaldan) barcha eMaktab o'quvchi login va parollarini ajratib ol. "
        "Faqat quyidagi aniq JSON formatida qaytar:\n"
        "{\"logins\": [{\"username\": \"login1\", \"password\": \"parol1\"}, ...]}\n"
        "Boshqa hech qanday izoh yoki matn qo'shma, faqat JSON format."
    )
    
    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {"text": prompt},
                    {
                        "inline_data": {
                            "mime_type": mime_type,
                            "data": b64_data
                        }
                    }
                ]
            }
        ]
    }
    
    for api_key in get_ordered_api_keys():
        for model_name in FALLBACK_MODELS:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
            try:
                timeout = aiohttp.ClientTimeout(total=30, connect=8)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.post(url, json=payload) as resp:
                        if resp.status in (429, 403):
                            mark_key_exhausted(api_key)
                            break
                        if resp.status == 200:
                            data = await resp.json()
                            candidates = data.get("candidates", [])
                            if candidates:
                                raw_text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                                clean_json = raw_text.strip()
                                if "```json" in clean_json:
                                    clean_json = clean_json.split("```json")[1].split("```")[0].strip()
                                elif "```" in clean_json:
                                    clean_json = clean_json.split("```")[1].split("```")[0].strip()
                                
                                parsed = json.loads(clean_json)
                                return parsed.get("logins", [])
            except Exception as e:
                continue

    
    return []

async def extract_logins_from_document(doc_bytes: bytes, filename: str = "", mime_type: str = "") -> list[dict]:
    """
    Extracts logins and passwords from any document type:
    - Text files (.txt, .csv, .tsv, .log)
    - Excel files (.xlsx, .xls)
    - PDF documents (.pdf)
    - Word documents (.docx)
    - Images (.jpg, .jpeg, .png, .webp, .bmp)
    """
    fn = (filename or "").lower()

    # 1. Image documents
    if (mime_type and mime_type.startswith("image/")) or any(fn.endswith(ext) for ext in [".jpg", ".jpeg", ".png", ".webp", ".bmp"]):
        return await extract_logins_from_image(doc_bytes, mime_type=mime_type or "image/jpeg")

    # 2. Excel spreadsheets
    if any(fn.endswith(ext) for ext in [".xlsx", ".xls"]):
        try:
            import openpyxl
            wb = openpyxl.load_workbook(io.BytesIO(doc_bytes), data_only=True)
            text_lines = []
            for sheetname in wb.sheetnames:
                ws = wb[sheetname]
                for row in ws.iter_rows(values_only=True):
                    row_vals = [str(cell).strip() for cell in row if cell is not None and str(cell).strip()]
                    if row_vals:
                        text_lines.append(" | ".join(row_vals))
            wb.close()
            if text_lines:
                return await extract_logins_from_text("\n".join(text_lines))
        except Exception as e:
            print(f"Excel extraction error: {e}")

    # 3. PDF documents
    if fn.endswith(".pdf") or mime_type == "application/pdf":
        try:
            import pypdf
            reader = pypdf.PdfReader(io.BytesIO(doc_bytes))
            pages_text = []
            for page in reader.pages:
                t = page.extract_text()
                if t:
                    pages_text.append(t)
            full_pdf_text = "\n".join(pages_text).strip()
            if len(full_pdf_text) > 15:
                return await extract_logins_from_text(full_pdf_text)
        except Exception as e:
            print(f"PDF text extraction error: {e}")
        # If scanned PDF or text empty, try Gemini PDF vision
        return await extract_logins_from_image(doc_bytes, mime_type="application/pdf")

    # 4. Word documents (.docx)
    if fn.endswith(".docx"):
        try:
            import zipfile
            import xml.etree.ElementTree as ET
            with zipfile.ZipFile(io.BytesIO(doc_bytes)) as z:
                xml_content = z.read("word/document.xml")
                root = ET.fromstring(xml_content)
                paras = []
                for p in root.findall(".//{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p"):
                    p_text = "".join([t.text or "" for t in p.findall(".//{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t")]).strip()
                    if p_text:
                        paras.append(p_text)
                full_text = "\n".join(paras)

                # Direct regex extraction for exact Login: ... Parol: ... pattern
                matches = re.findall(r"Login:\s*([^\s\n\r]+)[\s\n\r]+Parol:\s*([^\s\n\r]+)", full_text, re.IGNORECASE)
                if matches:
                    results = []
                    for u, p in matches:
                        clean_u = u.strip()
                        clean_p = p.strip()
                        if clean_u and clean_p:
                            results.append({"username": clean_u, "password": clean_p})
                    if results:
                        return results

                if full_text:
                    extracted = await extract_logins_from_text(full_text)
                    for item in extracted:
                        u = str(item.get("username", ""))
                        if " " in u:
                            item["username"] = u.replace(" ", "")
                    return extracted
        except Exception as e:
            print(f"DOCX extraction error: {e}")

    # 5. Plain text, CSV, TSV
    for enc in ["utf-8", "cp1251", "latin-1"]:
        try:
            decoded = doc_bytes.decode(enc).strip()
            if decoded:
                return await extract_logins_from_text(decoded)
        except Exception:
            continue

    return []

async def process_audio_voice(audio_bytes: bytes, mime_type: str = "audio/ogg", user_name: str = "", is_admin: bool = False) -> dict:
    """Listens to voice message/audio using Gemini Multimodal."""
    b64_data = base64.b64encode(audio_bytes).decode('utf-8')
    prompt = (
        "Siz audio xabarni tinglab tahlil qiluvchi eMaktab yordamchisisiz.\n"
        "1. Audioda nima aytilganini diqqat bilan eshiting.\n"
        "2. Agar audioda o'quvchi logini va paroli aytilgan bo'lsa, "
        "ularni ajratib olib quyidagi JSON formatida qaytar:\n"
        "{\"type\": \"credentials\", \"logins\": [{\"username\": \"...\", \"password\": \"...\"}], \"transcript\": \"...\"}\n"
        "3. Agar bu oddiy savol yoki suhbat bo'lsa, audiodagi gapga to'liq, muloyim va foydali javob qaytar:\n"
        "{\"type\": \"chat\", \"transcript\": \"...\", \"reply\": \"...\"}\n"
        "Faqat toza JSON formatida javob ber."
    )

    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {"text": prompt},
                    {
                        "inline_data": {
                            "mime_type": mime_type,
                            "data": b64_data
                        }
                    }
                ]
            }
        ]
    }

    for api_key in get_ordered_api_keys():
        for model_name in FALLBACK_MODELS:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
            try:
                timeout = aiohttp.ClientTimeout(total=35, connect=8)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.post(url, json=payload) as resp:
                        if resp.status in (429, 403):
                            mark_key_exhausted(api_key)
                            break
                        if resp.status == 200:
                            data = await resp.json()
                            candidates = data.get("candidates", [])
                            if candidates:
                                raw = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "").strip()
                                if "```json" in raw:
                                    raw = raw.split("```json")[1].split("```")[0].strip()
                                elif "```" in raw:
                                    raw = raw.split("```")[1].split("```")[0].strip()
                                return json.loads(raw)
            except Exception as e:
                continue


    return {"type": "chat", "transcript": "", "reply": "Ovozli xabarni tushunishda xatolik yuz berdi."}


async def extract_teacher_credentials(text_or_data: str) -> tuple[str, str] | None:
    """Extracts teacher username and password from text, file transcript, or caption."""
    cleaned = text_or_data.strip()
    # Strip command prefix if present (e.g. /boost or /teacher)
    cleaned = re.sub(r"^/(?:boost|teacher)\s*", "", cleaned, flags=re.IGNORECASE).strip()

    # Fast regex match 1: login: ... parol: ...
    m = re.search(r'(?:o[\'`’]?qituvchi|teacher|ustoz|login|user)[:\s]+([a-zA-Z0-9._-]+).*?(?:parol|password|kod|pass)[:\s]+([^\s,;]+)', cleaned, re.IGNORECASE | re.DOTALL)
    if m:
        u, p = m.group(1).strip(), m.group(2).strip()
        if u.lower() not in ('login', 'parol', 'user', 'password') and len(u) >= 3:
            return u, p

    # Fast match 2: username:password or username/password or username;password
    for sep in [":", "/", ";"]:
        if sep in cleaned and len(cleaned.splitlines()) == 1 and " " not in cleaned:
            parts = cleaned.split(sep, 1)
            u, p = parts[0].strip(), parts[1].strip()
            if len(u) >= 3 and len(p) >= 3 and not any(k in u.lower() for k in ["http", "www", "t.me"]):
                return u, p

    # Fast match 3: two words/tokens (e.g. toxtasinovafarida Farida82)
    tokens = cleaned.split()
    if len(tokens) == 2:
        u = re.sub(r"^(?:o[\'`’]?qituvchi|teacher|ustoz|login|user)[:\s]+", "", tokens[0], flags=re.IGNORECASE).strip()
        p = re.sub(r"^(?:parol|password|kod|pass)[:\s]+", "", tokens[1], flags=re.IGNORECASE).strip()
        if len(u) >= 3 and len(p) >= 3 and not any(k in u.lower() for k in ["http", "www", "t.me"]):
            return u, p

    # Fast match 4: two lines
    lines = [ln.strip() for ln in cleaned.splitlines() if ln.strip()]
    if len(lines) == 2:
        u = re.sub(r"^(?:o[\'`’]?qituvchi|teacher|ustoz|login|user)[:\s]+", "", lines[0], flags=re.IGNORECASE).strip()
        p = re.sub(r"^(?:parol|password|kod|pass)[:\s]+", "", lines[1], flags=re.IGNORECASE).strip()
        if len(u) >= 3 and len(p) >= 3 and not any(k in u.lower() for k in ["http", "www", "t.me"]):
            return u, p
    
    prompt = (
        "Quyidagi matndan o'qituvchining eMaktab login va parolini ajratib ol:\n"
        f"{text_or_data[:3000]}\n"
        "Faqat quyidagi aniq JSON formatda qaytar:\n"
        "{\"username\": \"login\", \"password\": \"parol\"}\n"
        "Agar aniq login yoki parol topilmasa, null qaytar."
    )
    for api_key in get_ordered_api_keys():
        for model in FALLBACK_MODELS:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
            try:
                timeout = aiohttp.ClientTimeout(total=10, connect=4)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}) as resp:
                        if resp.status in (429, 403):
                            mark_key_exhausted(api_key)
                            break
                        if resp.status == 200:
                            data = await resp.json()
                            raw = data.get("candidates", [])[0].get("content", {}).get("parts", [{}])[0].get("text", "").strip()
                            if "```json" in raw:
                                raw = raw.split("```json")[1].split("```")[0].strip()
                            elif "```" in raw:
                                raw = raw.split("```")[1].split("```")[0].strip()
                            res = json.loads(raw)
                            if res and res.get("username") and res.get("password"):
                                return str(res["username"]).strip(), str(res["password"]).strip()
            except Exception:
                continue
    return None


async def match_user_class_with_options(user_input: str, available_classes: list[dict]) -> dict | None:
    """Uses AI to match user's class input with available teacher classes."""
    clean_input = user_input.strip().upper().replace(" ", "").replace("-", "")
    for c in available_classes:
        c_clean = c["name"].strip().upper().replace(" ", "").replace("-", "")
        if clean_input == c_clean:
            return c
    
    class_names = [c["name"] for c in available_classes]
    prompt = (
        f"Foydalanuvchi quyidagi sinfni kiritdi: '{user_input}'.\n"
        f"Mavjud sinflar ro'yxati: {json.dumps(class_names, ensure_ascii=False)}\n"
        "Foydalanuvchi kiritgan matnga eng mos keluvchi sinf nomini aniqlang. "
        "Faqat ro'yxatdagi aniq sinf nomini (masalan: '10-A') qaytaring. "
        "Agar umuman mos kelmasa, 'NONE' qaytaring."
    )
    for api_key in get_ordered_api_keys():
        for model in FALLBACK_MODELS:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
            try:
                timeout = aiohttp.ClientTimeout(total=10, connect=4)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}) as resp:
                        if resp.status in (429, 403):
                            mark_key_exhausted(api_key)
                            break
                        if resp.status == 200:
                            data = await resp.json()
                            match = data.get("candidates", [])[0].get("content", {}).get("parts", [{}])[0].get("text", "").strip()
                            for c in available_classes:
                                if c["name"].lower() == match.lower():
                                    return c
            except Exception:
                continue
    return None


async def extract_teacher_from_image(image_bytes: bytes, mime_type: str = "image/jpeg") -> tuple[str, str] | None:
    """Uses Gemini Vision to extract teacher credentials from image/photo/screenshot."""
    import base64
    b64_data = base64.b64encode(image_bytes).decode('utf-8')
    prompt = (
        "Ushbu rasmdan o'qituvchining eMaktab login va parolini ajratib ol. "
        "Faqat quyidagi aniq JSON formatda qaytar:\n"
        "{\"username\": \"login\", \"password\": \"parol\"}\n"
        "Agar aniq login yoki parol topilmasa, null qaytar."
    )
    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {"text": prompt},
                    {
                        "inline_data": {
                            "mime_type": mime_type,
                            "data": b64_data
                        }
                    }
                ]
            }
        ]
    }
    for api_key in get_ordered_api_keys():
        for model_name in FALLBACK_MODELS:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
            try:
                timeout = aiohttp.ClientTimeout(total=20, connect=6)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.post(url, json=payload) as resp:
                        if resp.status in (429, 403):
                            mark_key_exhausted(api_key)
                            break
                        if resp.status == 200:
                            data = await resp.json()
                            raw = data.get("candidates", [])[0].get("content", {}).get("parts", [{}])[0].get("text", "").strip()
                            if "```json" in raw:
                                raw = raw.split("```json")[1].split("```")[0].strip()
                            elif "```" in raw:
                                raw = raw.split("```")[1].split("```")[0].strip()
                            res = json.loads(raw)
                            if res and res.get("username") and res.get("password"):
                                return str(res["username"]).strip(), str(res["password"]).strip()
            except Exception:
                continue
    # Fallback to general login extraction
    try:
        logins = await extract_logins_from_image(image_bytes, mime_type)
        if logins and len(logins) > 0:
            return logins[0].get("username"), logins[0].get("password")
    except Exception:
        pass
    return None


async def extract_teacher_from_doc(doc_bytes: bytes, file_name: str) -> tuple[str, str] | None:
    """Extracts teacher credentials from a document/file."""
    try:
        text = doc_bytes.decode('utf-8', errors='ignore')
        creds = await extract_teacher_credentials(text)
        if creds:
            return creds
    except Exception:
        pass
    try:
        logins = await extract_logins_from_document(doc_bytes, file_name)
        if logins and len(logins) > 0:
            return logins[0].get("username"), logins[0].get("password")
    except Exception:
        pass
    return None

