import aiohttp
import asyncio
import os
import json
import sqlite3
import re
from pathlib import Path
from md_styler import add_custom_emoji, delete_custom_emoji, list_custom_emojis

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

DB_PATH = str(Path(__file__).parent / "database.sqlite3")

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

def tool_extend_grade_access(grade: str, days: int = 30):
    """Sinf to'lovini berilgan kunga uzaytiradi (standart 30 kun), is_paid va is_allowed ni yoqadi, sinfdagi barcha loginlarni faollashtiradi."""
    try:
        g_clean = grade.strip().upper().replace("-", "").replace(" ", "")
        con = sqlite3.connect(DB_PATH)
        cur = con.cursor()
        
        cur.execute("SELECT id FROM Grade WHERE UPPER(grade) = ?;", (g_clean,))
        row = cur.fetchone()
        if not row:
            cur.execute(
                "INSERT INTO Grade (grade, is_allowed, is_paid, allowed_until) VALUES (?, 1, 1, datetime('now', ?));",
                (g_clean, f"+{days} days")
            )
        else:
            cur.execute(
                "UPDATE Grade SET is_allowed = 1, is_paid = 1, allowed_until = datetime(COALESCE(allowed_until, 'now'), ?) WHERE UPPER(grade) = ?;",
                (f"+{days} days", g_clean)
            )
        
        cur.execute("UPDATE Logins SET is_paid = 1, updated_at = datetime('now') WHERE REPLACE(UPPER(grade), '-', '') = ?;", (g_clean,))
        updated_logins = cur.rowcount
        
        cur.execute("SELECT allowed_until FROM Grade WHERE UPPER(grade) = ?;", (g_clean,))
        until_row = cur.fetchone()
        exp_date = until_row[0] if until_row else "Noma'lum"

        con.commit()
        con.close()
        return {
            "success": True,
            "sinf": g_clean,
            "uzaytirilgan_kun": days,
            "yangi_muddati": str(exp_date),
            "faollashtirilgan_loginlar": updated_logins,
            "message": f"{g_clean}-sinf to'lovi va ruxsati {days} kunga uzaytirildi (amal qilish muddati: {exp_date}). Sinfdagi {updated_logins} ta login faollashtirildi."
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

def tool_bulk_update_passwords_in_grade(grade: str, new_password: str):
    """Muayyan sinfdagi (masalan '7A') barcha o'quvchi va ota-onalar parolini bir martada yangi umumiy parolga o'zgartiradi."""
    try:
        g_clean = grade.strip().upper().replace("-", "").replace(" ", "")
        p_clean = new_password.strip()
        if len(p_clean) < 6:
            return {"success": False, "error": "Yangi parol kamida 6 belgidan iborat bo'lishi kerak."}
        
        con = sqlite3.connect(DB_PATH)
        cur = con.cursor()
        cur.execute(
            "UPDATE Logins SET password = ?, last_cookie = NULL, updated_at = datetime('now') WHERE REPLACE(UPPER(grade), '-', '') = ?;",
            (p_clean, g_clean)
        )
        count = cur.rowcount
        con.commit()
        con.close()
        if count == 0:
            return {"success": False, "error": f"{g_clean}-sinfida hech qanday login topilmadi."}
        return {
            "success": True,
            "sinf": g_clean,
            "yangi_parol": p_clean,
            "yangilangan_loginlar_soni": count,
            "message": f"{g_clean}-sinfidagi barcha {count} ta login paroli muvaffaqiyatli '{p_clean}' ga o'zgartirildi va sessiyalari yangilandi."
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

def tool_add_student_login(username: str, password: str, grade: str, school_number: int = 14, role: str = "student"):
    """Bazada yangi o'quvchi yoki ota-ona loginini ro'yxatdan o'tkazadi / qo'shadi."""
    try:
        u_clean = username.strip()
        p_clean = password.strip()
        g_clean = grade.strip().upper().replace("-", "").replace(" ", "")
        r_clean = role.strip().lower()
        if r_clean not in ["student", "parent"]:
            r_clean = "student"
        
        con = sqlite3.connect(DB_PATH)
        cur = con.cursor()
        
        cur.execute("SELECT id FROM School_number WHERE school_number = ? LIMIT 1;", (school_number,))
        s_row = cur.fetchone()
        if s_row:
            school_id = s_row[0]
        else:
            cur.execute("SELECT id FROM School_number LIMIT 1;")
            s_row = cur.fetchone()
            school_id = s_row[0] if s_row else 1
            
        cur.execute("SELECT id FROM Logins WHERE username = ?;", (u_clean,))
        existing = cur.fetchone()
        if existing:
            lid = existing[0]
            cur.execute(
                "UPDATE Logins SET password = ?, grade = ?, school = ?, is_paid = 1, role = ?, last_login = 1, updated_at = datetime('now') WHERE id = ?;",
                (p_clean, g_clean, school_id, r_clean, lid)
            )
            msg = f"{u_clean} logini allaqachon mavjud edi, ma'lumotlari yangilandi ({g_clean}-sinf, {r_clean})."
        else:
            cur.execute(
                "INSERT INTO Logins (school, username, password, grade, last_login, created_at, updated_at, is_paid, role) VALUES (?, ?, ?, ?, 1, datetime('now'), datetime('now'), 1, ?);",
                (school_id, u_clean, p_clean, g_clean, r_clean)
            )
            lid = cur.lastrowid
            cur.execute(
                "INSERT INTO Logins_data (login_id, last_cookie, last_login, created_at) VALUES (?, NULL, 1, datetime('now'));",
                (lid,)
            )
            msg = f"{u_clean} ({g_clean}-sinf, {r_clean}) muvaffaqiyatli bazaga qo'shildi."
            
        con.commit()
        con.close()
        return {"success": True, "login_id": lid, "username": u_clean, "grade": g_clean, "message": msg}
    except Exception as e:
        return {"success": False, "error": str(e)}

def tool_clean_grade_logins(grade: str, failed_only: bool = True):
    """Sinfdagi loginlarni tozalaydi (failed_only=True bo'lsa faqat xato berayotganlarni, False bo'lsa barcha loginlarni o'chiradi)."""
    try:
        g_clean = grade.strip().upper().replace("-", "").replace(" ", "")
        con = sqlite3.connect(DB_PATH)
        cur = con.cursor()
        
        if failed_only:
            cur.execute("SELECT id FROM Logins WHERE REPLACE(UPPER(grade), '-', '') = ? AND last_login = 0;", (g_clean,))
        else:
            cur.execute("SELECT id FROM Logins WHERE REPLACE(UPPER(grade), '-', '') = ?;", (g_clean,))
            
        ids = [r[0] for r in cur.fetchall()]
        if not ids:
            con.close()
            target_str = "xato berayotgan" if failed_only else "hech qanday"
            return {"success": True, "ochirilgan_soni": 0, "message": f"{g_clean}-sinfida {target_str} loginlar topilmadi."}
            
        placeholders = ','.join('?' for _ in ids)
        cur.execute(f"DELETE FROM Logins_data WHERE login_id IN ({placeholders});", ids)
        cur.execute(f"DELETE FROM Logins WHERE id IN ({placeholders});", ids)
        deleted_count = cur.rowcount
        con.commit()
        con.close()
        
        target_desc = "ishlamayotgan (xato) loginlar" if failed_only else "barcha loginlar"
        return {
            "success": True,
            "sinf": g_clean,
            "ochirilgan_soni": deleted_count,
            "message": f"{g_clean}-sinfidagi {deleted_count} ta {target_desc} bazadan tozalandi."
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

def tool_reset_grade_login_status(grade: str):
    """Sinfdagi barcha loginlarning sessiya va kuki holatini qayta tekshirishga tayyorlaydi (last_cookie ni tozalaydi)."""
    try:
        g_clean = grade.strip().upper().replace("-", "").replace(" ", "")
        con = sqlite3.connect(DB_PATH)
        cur = con.cursor()
        cur.execute("UPDATE Logins SET last_cookie = NULL, updated_at = datetime('now') WHERE REPLACE(UPPER(grade), '-', '') = ?;", (g_clean,))
        count = cur.rowcount
        con.commit()
        con.close()
        return {
            "success": True,
            "sinf": g_clean,
            "yangilangan_loginlar": count,
            "message": f"{g_clean}-sinfidagi {count} ta login sessiyasi tozalandi va qayta tekshirishga tayyorlandi."
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

def tool_get_school_detailed_report(school_number: int = 14):
    """Maktab bo'yicha to'liq va kengaytirilgan analitik hisobot (sinflar, to'lovlar, faol/xato loginlar ulushi)."""
    try:
        con = sqlite3.connect(DB_PATH)
        cur = con.cursor()
        
        cur.execute("SELECT id, school_number, place, is_paid, expire_at FROM School_number WHERE school_number = ? LIMIT 1;", (school_number,))
        s_row = cur.fetchone()
        school_info = {}
        if s_row:
            school_info = {
                "maktab_raqami": s_row[1],
                "nomi_joyi": s_row[2],
                "to'langan": bool(s_row[3]),
                "tugash_muddati": str(s_row[4]) if s_row[4] else "Cheksiz"
            }
            
        cur.execute("SELECT grade, is_allowed, is_paid, allowed_until FROM Grade ORDER BY grade;")
        grades_status = {r[0].upper(): {"allowed": bool(r[1]), "paid": bool(r[2]), "until": str(r[3]) if r[3] else None} for r in cur.fetchall()}
        
        cur.execute("""
            SELECT grade, 
                   COUNT(*) as total,
                   SUM(CASE WHEN last_login = 1 THEN 1 ELSE 0 END) as ok_cnt,
                   SUM(CASE WHEN role = 'parent' THEN 1 ELSE 0 END) as parent_cnt,
                   SUM(CASE WHEN is_paid = 1 THEN 1 ELSE 0 END) as paid_cnt
            FROM Logins
            GROUP BY grade
            ORDER BY grade;
        """)
        rows = cur.fetchall()
        sinflar_tahlili = []
        total_all = 0
        total_ok = 0
        
        for g, total, ok, parents, paids in rows:
            g_up = g.upper().replace("-", "").replace(" ", "")
            st = grades_status.get(g_up, {"allowed": True, "paid": True, "until": None})
            fail = total - (ok or 0)
            students = total - (parents or 0)
            total_all += total
            total_ok += (ok or 0)
            sinflar_tahlili.append({
                "sinf": g,
                "jami_loginlar": total,
                "ishlayotgan": ok or 0,
                "ishlamayotgan": fail,
                "o'quvchilar": students,
                "ota_onalar": parents or 0,
                "to'langan_loginlar": paids or 0,
                "sinf_ruxsati": "Ruxsat etilgan" if st["allowed"] else "Qulflangan",
                "sinf_to'lovi": "To'langan" if st["paid"] else "To'lanmagan",
                "amal_qilish_muddati": st["until"] or "Belgilanmagan"
            })
            
        con.close()
        success_rate = round((total_ok / total_all * 100), 1) if total_all > 0 else 0
        return {
            "maktab": school_info or f"{school_number}-maktab",
            "jami_sinflar_soni": len(sinflar_tahlili),
            "jami_loginlar": total_all,
            "muvaffaqiyatli_kirilgan": total_ok,
            "xatolik_berayotgan": total_all - total_ok,
            "muvaffaqiyat_foizi": f"{success_rate}%",
            "sinflar_kesimida": sinflar_tahlili
        }
    except Exception as e:
        return {"error": str(e)}

async def tool_manage_captchas(action: str = "status", count: int = 10):
    """Avtomatik kapchalar omborini boshqaradi: 'status' (kapchalar soni va holati), 'harvest' (yangi kapchalar yig'ish), 'clean' (yaroqsiz va eskilarni tozalash)."""
    try:
        from captcha_manager import get_captcha_pool_status, harvest_fresh_captchas, cleanup_old_or_invalid_captchas
        act = action.strip().lower()
        if act == "harvest":
            harvested = await harvest_fresh_captchas(target_count=count)
            pool_stat = get_captcha_pool_status()
            return {
                "success": True,
                "action": "harvest",
                "yangi_kapchalar_soni": len(harvested),
                "jami_ombor": pool_stat["jami_kapchalar"],
                "message": f"Muvaffaqiyatli {len(harvested)} ta yangi kapcha yig'ildi va tekshirilib bazaga saqlandi. Hozirgi jami kapchalar: {pool_stat['jami_kapchalar']} ta."
            }
        elif act in ["clean", "cleanup"]:
            c_res = await cleanup_old_or_invalid_captchas(max_pool_size=25)
            return {
                "success": True,
                "action": "clean",
                "ochirilgan_yaroqsiz": c_res["deleted_invalid"],
                "ochirilgan_eski": c_res["deleted_oldest"],
                "qolgan_kapchalar": c_res["remaining"],
                "message": f"Kapchalar tozalandi: {c_res['deleted_invalid']} ta yaroqsiz o'chirildi, {c_res['deleted_oldest']} ta eski kesildi. Faol kapchalar: {c_res['remaining']} ta."
            }
        else:
            stat = get_captcha_pool_status()
            return {
                "success": True,
                "action": "status",
                "holat": stat,
                "message": f"Hozirda bazada {stat['jami_kapchalar']} ta kapcha mavjud ({stat['bosh_kapchalar']} ta bo'sh, {stat['band_kapchalar']} ta band). Eng yangisi: {stat['eng_yangi_sana']}."
            }
    except Exception as e:
        return {"success": False, "error": str(e)}

def tool_add_school(school_number: int, place: str, days: int = 365):
    """Faqat administrator uchun: Tizimga yangi maktab qo'shadi va uning faollik muddatini belgilaydi."""
    try:
        import uuid
        con = sqlite3.connect(DB_PATH)
        cur = con.cursor()
        cur.execute("SELECT id FROM School WHERE school_number = ?;", (school_number,))
        if cur.fetchone():
            con.close()
            return {"success": False, "error": f"{school_number}-maktab allaqachon mavjud."}
        url_key = str(uuid.uuid4())[:8]
        cur.execute("INSERT INTO School (school_number, place, school_url, allowed_until) VALUES (?, ?, ?, datetime('now', ?));",
                    (school_number, place.strip(), url_key, f"+{days} days"))
        con.commit()
        con.close()
        return {"success": True, "message": f"{school_number}-maktab ({place}) {days} kun muddat bilan tizimga muvaffaqiyatli qo'shildi."}
    except Exception as e:
        return {"success": False, "error": str(e)}

def tool_backup_database():
    """Faqat administrator uchun: SQLite ma'lumotlar bazasi zaxira holatini va hajmini qaytaradi."""
    if os.path.exists(DB_PATH):
        sz = round(os.path.getsize(DB_PATH) / (1024 * 1024), 2)
        return {"success": True, "file": DB_PATH, "hajmi_mb": sz, "message": f"SQLite ma'lumotlar bazasi zaxira nusxasi mavjud ({sz} MB)."}
    return {"success": False, "error": "Baza fayli topilmadi."}

def tool_run_all_check():
    """Faqat administrator uchun: Barcha maktablar va sinflardagi loginlarni eMaktab tizimiga qayta tekshirishni (all check) tasdiqlaydi."""
    return {
        "success": True,
        "message": "Barcha maktablar va sinflardagi loginlarni eMaktab tizimiga kirishini tekshirish jarayoni boshlandi."
    }

def tool_teacher_get_classes(teacher_username: str, teacher_password: str):
    """Faqat administrator uchun: O'qituvchi logini orqali tizimga kirib, unga biriktirilgan barcha mavjud sinflar va o'quvchilar sonini oladi."""
    try:
        from reset_and_register import EMaktabResetter
        resetter = EMaktabResetter()
        resetter.login_teacher(teacher_username.strip(), teacher_password.strip())
        classes = resetter.get_teacher_classes_with_counts()
        return {
            "success": True,
            "maktab": resetter.school_name,
            "maktab_id": resetter.school_id,
            "o‘qituvchi": teacher_username.strip(),
            "jami_sinflar": len(classes),
            "sinflar": [{"sinf": c.get("name"), "sinf_id": c.get("class_id"), "o‘quvchilar": c.get("student_count", 0)} for c in classes]
        }
    except Exception as e:
        return {"success": False, "error": f"O'qituvchi kabinetiga kirishda xatolik: {str(e)}"}

def tool_teacher_harvest_and_reset(
    teacher_username: str,
    teacher_password: str,
    class_names: str = "all",
    mode: str = "both",
    new_password: str = "12345678a"
):
    """Faqat administrator uchun: O'qituvchi kabinetidan sinflarni tortib olib (harvest), o'quvchi va ota-onalar parolini yangilaydi (reset) va bazaga sinxronlaydi."""
    try:
        from reset_and_register import EMaktabResetter
        resetter = EMaktabResetter()
        resetter.login_teacher(teacher_username.strip(), teacher_password.strip())
        all_classes = resetter.get_teacher_classes_with_counts()
        if not all_classes:
            return {"success": False, "error": "O'qituvchiga biriktirilgan hech qanday sinf topilmadi."}

        target_classes = []
        if isinstance(class_names, str):
            if class_names.strip().lower() in ("all", "hamma", "barchasi", "*"):
                target_classes = all_classes
            else:
                wanted = [c.strip().upper().replace("-", "").replace(" ", "") for c in class_names.split(",") if c.strip()]
                target_classes = [c for c in all_classes if c.get("name", "").upper().replace("-", "").replace(" ", "") in wanted]
        elif isinstance(class_names, list):
            wanted = [str(c).strip().upper().replace("-", "").replace(" ", "") for c in class_names]
            target_classes = [c for c in all_classes if c.get("name", "").upper().replace("-", "").replace(" ", "") in wanted]

        if not target_classes:
            target_classes = all_classes

        # Target accounts discovery
        target_accounts = resetter.get_target_accounts(target_classes, mode=mode)
        if not target_accounts:
            return {
                "success": False,
                "error": f"Tanlangan sinflarda ({', '.join(c['name'] for c in target_classes)}) reset qilinadigan loginlar topilmadi."
            }

        # Reset & sync execution
        stats = resetter.reset_target_accounts(
            target_accounts=target_accounts,
            new_password=new_password.strip(),
            db_path=DB_PATH
        )

        return {
            "success": True,
            "maktab": resetter.school_name,
            "ishlangan_sinflar": [c["name"] for c in target_classes],
            "yangi_parol": new_password.strip(),
            "jami_hisoblar": stats.get("total_accounts", 0),
            "muvaffaqiyatli": stats.get("success_count", 0),
            "xato": stats.get("fail_count", 0),
            "o‘quvchilar": stats.get("total_students", 0),
            "ota_onalar": stats.get("total_parents", 0)
        }
    except Exception as e:
        return {"success": False, "error": f"O'qituvchi orqali parollarni tiklashda xatolik: {str(e)}"}

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
    },
    {
        "name": "tool_extend_grade_access",
        "description": "Faqat administrator uchun: Muayyan sinfning (masalan '7A' yoki '7-A') to'lovi va ruxsatini berilgan kunga (standart 30 kun) uzaytirish, sinfdagi barcha loginlarni faollashtirish.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "grade": {"type": "STRING", "description": "Sinf nomi (masalan: '7A', '4B')"},
                "days": {"type": "INTEGER", "description": "Uzaytirish kunlari soni (masalan: 30, 60, 90. Standart 30 kun)"}
            },
            "required": ["grade"]
        }
    },
    {
        "name": "tool_bulk_update_passwords_in_grade",
        "description": "Faqat administrator uchun: Muayyan sinfdagi (masalan '7A') barcha o'quvchi va ota-onalar parolini bir martada yangi umumiy parolga ommaviy almashtirish.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "grade": {"type": "STRING", "description": "Sinf nomi (masalan: '7A', '4B')"},
                "new_password": {"type": "STRING", "description": "Barcha hisoblar uchun yangi umumiy parol (masalan '12345678b')"}
            },
            "required": ["grade", "new_password"]
        }
    },
    {
        "name": "tool_add_student_login",
        "description": "Faqat administrator uchun: Bazaga yangi o'quvchi yoki ota-ona loginini qo'shish yoki mavjudini yangilash.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "username": {"type": "STRING", "description": "eMaktab logini"},
                "password": {"type": "STRING", "description": "Parol"},
                "grade": {"type": "STRING", "description": "Sinf nomi (masalan '7A')"},
                "school_number": {"type": "INTEGER", "description": "Maktab raqami (standart 14)"},
                "role": {"type": "STRING", "description": "Rol: 'student' (o'quvchi) yoki 'parent' (ota-ona). Standart 'student'"}
            },
            "required": ["username", "password", "grade"]
        }
    },
    {
        "name": "tool_clean_grade_logins",
        "description": "Faqat administrator uchun: Muayyan sinfdagi ishlamayotgan (xato) yoki barcha loginlarni bazadan tozalash/o'chirish.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "grade": {"type": "STRING", "description": "Sinf nomi (masalan '7A')"},
                "failed_only": {"type": "BOOLEAN", "description": "Faqat xato loginlarni o'chirish uchun True, sinfdagi barcha hisoblarni o'chirish uchun False. Standart True"}
            },
            "required": ["grade"]
        }
    },
    {
        "name": "tool_reset_grade_login_status",
        "description": "Faqat administrator uchun: Muayyan sinfdagi barcha loginlarning sessiyalarini tozalash va ularni qayta tekshirishga tayyorlash.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "grade": {"type": "STRING", "description": "Sinf nomi (masalan '7A')"}
            },
            "required": ["grade"]
        }
    },
    {
        "name": "tool_get_school_detailed_report",
        "description": "Faqat administrator uchun: Maktab bo'yicha to'liq analitik hisobot (sinflar soni, o'quvchilar/ota-onalar, to'langan/to'lanmagan sinflar, faol va xato loginlar ulushi).",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "school_number": {"type": "INTEGER", "description": "Maktab raqami (standart 14)"}
            }
        }
    },
    {
        "name": "tool_manage_captchas",
        "description": "Faqat administrator uchun: Avtomatik kapchalar omborini boshqarish. 'status' (hozirgi kapchalar soni va holati), 'harvest' (yangi kapchalar yig'ish), 'clean' (yaroqsiz va eskilarni tozalash).",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "'status', 'harvest' yoki 'clean'. Standart: 'status'"},
                "count": {"type": "INTEGER", "description": "Yangi yig'iladigan kapchalar soni (standart 10)"}
            }
        }
    },
    {
        "name": "tool_add_custom_emoji",
        "description": "Faqat administrator uchun: Yangi animatsiyali premium custom emoji qo'shish yoki mavjudini yangilash. Masalan: emoji_char='🚀', custom_emoji_id='5429398777419014515', label='Raketa'. Shundan so'ng bot ushbu emojini barcha xabarlar va menyu tugmalarida avtomatik ishlatadi.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "emoji_char": {"type": "STRING", "description": "Standart unicode emoji belgisi (masalan '🚀', '🔥', '✨')"},
                "custom_emoji_id": {"type": "STRING", "description": "Telegram Custom Emoji ID raqami (faqat raqamlar)"},
                "label": {"type": "STRING", "description": "Emoji nomi yoki izoh (masalan 'Raketa')"}
            },
            "required": ["emoji_char", "custom_emoji_id"]
        }
    },
    {
        "name": "tool_delete_custom_emoji",
        "description": "Faqat administrator uchun: Ro'yxatdan biror custom emojini o'chirish.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "emoji_char": {"type": "STRING", "description": "O'chirilishi kerak bo'lgan emoji"}
            },
            "required": ["emoji_char"]
        }
    },
    {
        "name": "tool_list_custom_emojis",
        "description": "Faqat administrator uchun: Barcha tizimda saqlangan animatsiyali custom emojilar va ularning ID raqamlari ro'yxatini ko'rish.",
        "parameters": {"type": "OBJECT", "properties": {}}
    },
    {
        "name": "tool_add_school",
        "description": "Faqat administrator uchun: Tizimga yangi maktab qo'shish va uning amal qilish muddatini belgilash.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "school_number": {"type": "INTEGER", "description": "Maktab raqami (masalan 15)"},
                "place": {"type": "STRING", "description": "Maktab joylashuvi yoki nomi (masalan '15-maktab')"},
                "days": {"type": "INTEGER", "description": "Amal qilish muddati (kunlarda, standart 365)"}
            },
            "required": ["school_number", "place"]
        }
    },
    {
        "name": "tool_backup_database",
        "description": "Faqat administrator uchun: Ma'lumotlar bazasining zaxira nusxasi (backup) holatini tayyorlash.",
        "parameters": {"type": "OBJECT", "properties": {}}
    },
    {
        "name": "tool_run_all_check",
        "description": "Faqat administrator uchun: Barcha maktablar va sinflardagi hisoblar (loginlar) eMaktabga kirishini tekshirishni boshlash.",
        "parameters": {"type": "OBJECT", "properties": {}}
    },
    {
        "name": "tool_teacher_get_classes",
        "description": "Faqat administrator uchun: O'qituvchi logini va paroli orqali tizimga kirib, unga biriktirilgan barcha sinflar va o'quvchilar sonini olish.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "teacher_username": {"type": "STRING", "description": "O'qituvchining eMaktab logini"},
                "teacher_password": {"type": "STRING", "description": "O'qituvchining eMaktab paroli"}
            },
            "required": ["teacher_username", "teacher_password"]
        }
    },
    {
        "name": "tool_teacher_harvest_and_reset",
        "description": "Faqat administrator uchun: O'qituvchi logini orqali sinflarning o'quvchi va ota-onalar loginlarini tortib olib (harvest), parollarini yangilab, bazaga yozish.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "teacher_username": {"type": "STRING", "description": "O'qituvchining eMaktab logini"},
                "teacher_password": {"type": "STRING", "description": "O'qituvchining eMaktab paroli"},
                "class_names": {"type": "STRING", "description": "Qayta ishlanadigan sinflar ro'yxati (masalan '7-A, 8-B' yoki 'all' barcha sinflar uchun)"},
                "mode": {"type": "STRING", "description": "Kimlarning paroli yangilanishi: 'both' (o'quvchi va ota-ona), 'students' (faqat o'quvchi), 'parents' (faqat ota-ona)"},
                "new_password": {"type": "STRING", "description": "Yangi o'rnatiladigan parol (standart '12345678a')"}
            },
            "required": ["teacher_username", "teacher_password"]
        }
    }
]

ADMIN_TOOL_NAMES = {tool["name"] for tool in ADMIN_FUNCTION_DECLARATIONS}

SYSTEM_INSTRUCTION = (
    "Siz eMaktab tizimi bo'yicha aqlli yordamchisiz. "
    "Siz va Administrator tizimni birgalikda to'liq boshqarasiz. "
    "Botda hech qanday murakkab slash buyruqlar yo'q — barcha amallar va vazifalar tabiiy suhbat orqali siz tomoningizdan bajariladi. "
    "Administratorlar (asosiy ega va 5432194711) o'qituvchi login va parolini yuborishi, sinflarni tortib olish (teacher harvester) "
    "hamda o'quvchi va ota-onalar parolini yangilash (reset) so'rovlarini to'liq boshqarishi mumkin. "
    "Agar administrator o'qituvchi logini va parolini bersa yoki sinflar ro'yxatini / parollarni tiklashni so'rasa, "
    "tegishli tool_teacher_get_classes yoki tool_teacher_harvest_and_reset funksiyalaridan foydalaning. "
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

_GLOBAL_AIOHTTP_SESSION: aiohttp.ClientSession | None = None

async def get_gemini_session() -> aiohttp.ClientSession:
    """Returns a shared persistent ClientSession with connection pooling, DNS caching and keep-alive."""
    global _GLOBAL_AIOHTTP_SESSION
    if _GLOBAL_AIOHTTP_SESSION is None or _GLOBAL_AIOHTTP_SESSION.closed:
        connector = aiohttp.TCPConnector(
            limit=30,
            ttl_dns_cache=300,
            enable_cleanup_closed=True,
            keepalive_timeout=75
        )
        timeout = aiohttp.ClientTimeout(total=20, connect=3)
        _GLOBAL_AIOHTTP_SESSION = aiohttp.ClientSession(connector=connector, timeout=timeout)
    return _GLOBAL_AIOHTTP_SESSION

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
            "Siz uning topshirig'i bo'yicha barcha ma'lumotlar bazasini ko'rish, o'zgartirish va animatsiyali premium custom emojilarni boshqarish vakolatiga egasiz.\n"
            "Mavjud boshqaruv qobiliyatlaringiz:\n"
            "- Custom emojilarni qo'shish/sozlash: `tool_add_custom_emoji`, `tool_delete_custom_emoji`, `tool_list_custom_emojis`\n"
            "- Sinf to'lovini uzaytirish: `tool_extend_grade_access`\n"
            "- Sinf parollarini ommaviy almashtirish: `tool_bulk_update_passwords_in_grade`\n"
            "- Yangi o'quvchi qo'shish: `tool_add_student_login`\n"
            "- Xato loginlarni tozalash: `tool_clean_grade_logins`\n"
            "- Maktab hisoboti: `tool_get_school_detailed_report`\n"
            "- Kapchalar: `tool_manage_captchas`\n"
            "- Sessiyalarni yangilash: `tool_reset_grade_login_status`\n"
            "- Sinf holati: `tool_set_grade_status`\n"
            "- Yakka login paroli/o'chirish: `tool_update_student_password`, `tool_delete_student_login`"
        )
    else:
        tools_schema = [{"function_declarations": PUBLIC_FUNCTION_DECLARATIONS}]
        system_inst = (
            SYSTEM_INSTRUCTION + "\n"
            "DIQQAT: Ushbu foydalanuvchi ODDIY FOYDALANUVCHI (administrator emas).\n"
            "Bazada saqlangan o'quvchilar shaxsiy ma'lumotlarini (login, parol, ism) bermang. Faqat umumiy statistikani ayting (`tool_get_system_stats`)."
        )

    session = await get_gemini_session()

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
                    "temperature": 0.4,
                    "maxOutputTokens": 750
                }
            }

            try:
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
                            elif fname == "tool_add_custom_emoji":
                                f_result = add_custom_emoji(**fargs)
                            elif fname == "tool_delete_custom_emoji":
                                f_result = delete_custom_emoji(**fargs)
                            elif fname == "tool_list_custom_emojis":
                                f_result = list_custom_emojis()
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
                            elif fname == "tool_extend_grade_access":
                                f_result = tool_extend_grade_access(**fargs)
                            elif fname == "tool_bulk_update_passwords_in_grade":
                                f_result = tool_bulk_update_passwords_in_grade(**fargs)
                            elif fname == "tool_add_student_login":
                                f_result = tool_add_student_login(**fargs)
                            elif fname == "tool_clean_grade_logins":
                                f_result = tool_clean_grade_logins(**fargs)
                            elif fname == "tool_reset_grade_login_status":
                                f_result = tool_reset_grade_login_status(**fargs)
                            elif fname == "tool_get_school_detailed_report":
                                f_result = tool_get_school_detailed_report(**fargs)
                            elif fname == "tool_manage_captchas":
                                f_result = await tool_manage_captchas(**fargs)
                            elif fname == "tool_add_school":
                                f_result = tool_add_school(**fargs)
                            elif fname == "tool_backup_database":
                                f_result = tool_backup_database()
                            elif fname == "tool_run_all_check":
                                f_result = tool_run_all_check()
                            elif fname == "tool_teacher_get_classes":
                                f_result = await asyncio.to_thread(tool_teacher_get_classes, **fargs)
                            elif fname == "tool_teacher_harvest_and_reset":
                                f_result = await asyncio.to_thread(tool_teacher_harvest_and_reset, **fargs)
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


async def extract_logins_intent_ai(text: str, reply_text: str = "") -> list[tuple[str, str]]:
    """
    Uses Gemini AI to intelligently extract student logins and their intended passwords
    from user messages, quoted messages, lists, overrides ('use 12345678v for all', etc.).
    Returns a list of (username, password) tuples.
    Returns [] if no login intent or credentials found.
    """
    raw_content = ""
    if reply_text:
        raw_content += f"Javob berilgan (reply) xabar:\n«««\n{reply_text[:15000]}\n»»»\n\n"
    raw_content += f"Foydalanuvchi xabari:\n«««\n{text[:15000]}\n»»»"

    prompt = (
        "Quyidagi foydalanuvchi xabaridan (va agar mavjud bo'lsa reply qilingan xabardan) eMaktab loginlari va parollarini ajratib ol.\n"
        "QOIDALAR:\n"
        "1. Agar 'use <parol> for all', 'hamma loginlarga <parol>', '<parol> qilib kir' kabi ko'rsatma bo'lsa, ro'yxatdagi har bir haqiqiy loginga shu parolni biriktir.\n"
        "2. 'Kirilmaganlar', 'Muvaffaqiyatli', 'Natija', 'Jami', 'Xato', 'Login', 'Parol', 'Sinf', 'Maktab' sarlavhalari LOGIN EMAS!\n"
        "3. '(Login yoki parol noto'g'ri)' xatolik sababi, login yoki parol emas!\n"
        "4. 'yoki', 'va', 'bilan', 'for', 'all', 'those', 'use', 'instead' so'zlari LOGIN EMAS!\n"
        "5. Agar hech qanday login/parol kiritish yoki yangilash maqsadi bo'lmasa (oddiy savol, suhbat bo'lsa), bo'sh ro'yxat qaytar: {\"logins\": []}\n\n"
        "Faqat quyidagi aniq JSON formatida qaytar:\n"
        "{\"logins\": [{\"username\": \"login1\", \"password\": \"parol1\"}, ...]}\n\n"
        "Matn:\n" + raw_content
    )

    for api_key in get_ordered_api_keys():
        for model_name in FALLBACK_MODELS:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
            payload = {
                "contents": [{"parts": [{"text": prompt}]}]
            }
            try:
                session = await get_gemini_session()
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
                                stopwords = {
                                    'kirilmaganlar', 'muvaffaqiyatli', 'natija', 'jami', 'xato',
                                    'login', 'parol', 'sinf', 'maktab', 'yoki', 'va', 'bilan',
                                    'all', 'those', 'for', 'use', 'instead'
                                }
                                for item in raw_list:
                                    u = str(item.get("username", "")).strip()
                                    p = str(item.get("password", "")).strip()
                                    if " " in u and not u.startswith("http"):
                                        u = u.replace(" ", "")
                                    if u and p and u.lower() not in stopwords and len(u) >= 3 and len(p) >= 3:
                                        clean_list.append((u, p))
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

