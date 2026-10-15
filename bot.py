import re
import io
import html
from gemini_ai import (
    ask_gemini, extract_logins_from_image, extract_logins_from_document,
    extract_logins_from_text, process_audio_voice,
    extract_teacher_credentials, match_user_class_with_options,
    extract_teacher_from_image, extract_teacher_from_doc
)
from emaktab_auto import auto_detect_login
from reset_and_register import EMaktabResetter
from md_styler import render_styled_text

import asyncio
import json
import os
import random
from collections import defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ChatAction, ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import CommandStart, Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import (
    Message, ReplyKeyboardRemove,
    InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo, FSInputFile, BufferedInputFile, CallbackQuery,
    MessageGenerationStopped
)
from telegraph import Telegraph
from telegraph.exceptions import RetryAfterError

from database import (
    get_or_create_school_by_number,
    get_all_logins, create_logins_data, bulk_create_logins_data, create_login, create_user,
    get_all_users, create_school, update_user, add_captcha_id,
    get_free_captcha, get_school_number, create_or_change_user_role,
    init, give_captcha_100, get_all_schools, get_grade, get_logins_grade_for_web,
    get_login_by_id, delete_login, update_login_credentials,
    get_school_stats, get_overall_stats, delete_school,
    get_school_grades, get_class_stats,
    toggle_grade_allowed, toggle_grade_paid, toggle_login_paid, get_grade_info, get_all_grade_controls,
    ensure_grade_trial,
    get_setting, set_setting, is_admin_or_owner, get_all_admins, add_admin, remove_admin, get_user_by_username
)
from send_aiohttps_requests import send_request_main
import dns_resolver  # Fast DNS resolution for login.emaktab.uz

OWNER_TG_ID = 6588631008
url = os.getenv('URL', "https://emaktab-2025.onrender.com")
Token = os.getenv('TOKEN', "8301189313:AAFApmwNLY9AlccUQtfXP5PfV0kvg0RBQr8")
DB_PATH = '/home/ubuntu/emaktab_2025/database.sqlite3' if os.path.exists('/home/ubuntu/emaktab_2025/database.sqlite3') else '/home/xusanboyman/emaktab_2025/database.sqlite3'

bot = Bot(token=Token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
active_ai_tasks: dict[int, asyncio.Task] = {}

def get_cached_school_classes_breakdown():
    cache_path = os.path.join(os.path.dirname(__file__), "school_classes_cache.json")
    if os.path.exists(cache_path):
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

telegraph = Telegraph()
try:
    telegraph.create_account(short_name="emaktab_helper")
except Exception as e:
    print("Telegraph init:", e)


async def create_page_safe(telegraph_instance, title, content):
    try:
        page = await asyncio.to_thread(
            telegraph_instance.create_page,
            title=title[:60],
            author_name='eMaktab Bot',
            html_content=content
        )
        return page
    except RetryAfterError as e:
        await asyncio.sleep(e.retry_after)
        return await create_page_safe(telegraph_instance, title, content)
    except Exception as e:
        print(f"Telegraph creation error: {e}")
        return {"url": ""}


# -------------------------------------------------------------------------
# FSM States
# -------------------------------------------------------------------------
class SchoolAdd(StatesGroup):
    school_number = State()
    school_place = State()
    days = State()


class UserAuth(StatesGroup):
    waiting_for_password = State()

async def check_user_access(tg_id: int) -> bool:
    """Open access: any user can add logins and receives a 7-day trial."""
    return True

class LoginAdd(StatesGroup):
    credentials = State()
    username = State()
    password = State()


class EditLoginPwd(StatesGroup):
    login_id = State()
    school_id = State()
    grade = State()
    page = State()
    new_password = State()


class AdminConfigStates(StatesGroup):
    waiting_for_new_admin = State()
    waiting_for_custom_time = State()
    waiting_for_custom_trial = State()


class TeacherResetStates(StatesGroup):
    waiting_for_creds = State()
    confirm_reset = State()
    choosing_class = State()
    choosing_mode = State()
    entering_new_password = State()
    review_confirmation = State()



# -------------------------------------------------------------------------
# Helpers & Animated Emojis (IslomjonAnimeEmoji & DecorationEmojiPack & RestrictedEmoji)
# -------------------------------------------------------------------------
EMOJI = {
    # Maktab va Ta'lim
    "school": "5265002646397285605",     # 🏫 Maktab
    "books": "5373098009640836781",      # 📚 Sinflar
    "book": "5226512880362332956",       # 📖 Sinf
    "grad": "5375163339154399459",       # 🎓 Bitiruvchi
    "users": "5372926953978341366",      # 👥 Jami o'quvchilar
    "user": "5373012449597335010",       # 👤 O'quvchi

    # IslomjonAnimeEmoji (Yangi porlovchi animatsiyalar)
    "owner": "5431684550424011313",      # 👑 Bosh Admin Toji (IslomjonAnime)
    "admin": "5361561289397121939",      # ⭐ Admin Yulduzi (IslomjonAnime)
    "check": "5350486389806868244",      # ✅ Muvaffaqiyatli Check (IslomjonAnime)
    "cross": "5273914604752216432",      # ❌ Xato / Bekor (IslomjonAnime)
    "paid": "5415722549281561774",       # 🟢 To'langan yashil (IslomjonAnime)
    "trial": "5415803109983133508",      # 🟡 Sinovda sariq (IslomjonAnime)
    "failed": "5416044289576673808",     # 🔴 Qulflangan qizil (IslomjonAnime)
    "lock": "5350619413533958825",       # 🔐 Qulf (IslomjonAnime)
    "dev": "5429398777419014515",        # 👨‍💻 Dasturchi (IslomjonAnime)

    # DecorationEmojiPack (Yangi zamonaviy animatsiyalar)
    "settings": "5213470220030585409",   # ⚙️ Aylanuvchi Sozlamalar (Decoration)
    "tools": "5213214428958306222",      # 🛠 Asboblar (Decoration)
    "clock": "5215394081911351762",      # ⏰ Qo'ng'iroqli Soat (Decoration)
    "hourglass": "5215327832040811010",  # ⏳ Qumsoat (Decoration)
    "memo": "5215672443036772796",       # 📝 Hisobot / Qism (Decoration)
    "diamond": "5215377245639549895",    # 💎 Olmos (Decoration)
    "gift": "5215440433198413312",       # 🎁 Sovg'a (Decoration)
    "party": "5215628200578655810",      # 🎉 Muvaffaqiyat (Decoration)
    "pin": "5213260226194583825",        # 📌 Pin (Decoration)
    "flash": "5215356457997837659",      # ⚡️ Chaqmoq (Decoration)
    "money": "5213403875670765022",      # 💳 To'lov / Karta (Decoration)
    "system": "5215186239853964761",     # 🖥 Kompyuter (Decoration)
    "db": "5215352343419167936",         # 💿 Disk / Baza (Decoration)
    "database": "5215352343419167936",   # 💿 Baza
    "alert": "5213134259098761044",      # ⚠️ Ogohlantirish (Decoration)
    "warning": "5213134259098761044",    # ⚠️ Ogohlantirish (Decoration)
    "bell": "5215372534060428125",       # 🔔 Qo'ng'iroq (Decoration)
    "camera": "5215685959298853284",     # 📷 Kamera (Decoration)
    "tip": "5215356457997837659",        # 💡 Maslahat / Chaqmoq
    "link": "5215391376081954505",       # 🔗 Havola (Decoration)

    # Qo'shimcha klassik emojilar
    "stats": "5431577498364158238",      # 📊 Statistika
    "chart_up": "5373001317042101552",   # 📈 Ko'rsatkichlar
    "chart_down": "5361748661640372834", # 📉 Xatolik
    "refresh": "5264727218734524899",    # 🔄 Yangilash / Qayta tekshirish
    "plus": "5226945370684140473",       # ➕ Qo'shish
    "edit": "5334673106202010226",       # ✏️ Parol tahrirlash
    "search": "5188217332748527444",     # 🔍 Qidirish
    "key": "5330115548900501467",        # 🔑 Parol
    "bot": "5312078301165012884",        # 🤖 AI Robot
    "robot": "5312078301165012884",      # 🤖 Robot
    "calendar": "5431897022456145283",   # 📆 Sana
    "wave": "5472055112702629499",       # 👋 Salom
    "thinking": "5456125285160226779",   # 💭 Thinking
    "arrow_down": "5406745015365943482", # ⬇️ Down arrow
}

EMOJI_FALLBACK = {
    "school": "🏫",
    "stats": "📊",
    "chart_up": "📈",
    "chart_down": "📉",
    "books": "📚",
    "book": "📖",
    "users": "👥",
    "user": "👤",
    "owner": "👑",
    "admin": "⭐",
    "clock": "⏰",
    "hourglass": "⏳",
    "refresh": "🔄",
    "plus": "➕",
    "check": "✅",
    "cross": "❌",
    "edit": "✏️",
    "memo": "📝",
    "search": "🔍",
    "lock": "🔐",
    "key": "🔑",
    "bot": "🤖",
    "robot": "🤖",
    "tip": "💡",
    "party": "🎉",
    "system": "🖥",
    "db": "💿",
    "database": "💿",
    "calendar": "📆",
    "tools": "🛠",
    "settings": "⚙️",
    "paid": "🟢",
    "trial": "🟡",
    "failed": "🔴",
    "warning": "⚠️",
    "alert": "⚠️",
    "money": "💳",
    "wave": "👋",
    "grad": "🎓",
    "thinking": "💭",
    "arrow_down": "⬇️",
    "diamond": "💎",
    "gift": "🎁",
    "pin": "📌",
    "flash": "⚡️",
    "dev": "👨‍💻",
    "bell": "🔔",
    "camera": "📷",
    "link": "🔗",
}


def tg_icon(name: str, fallback: str = "") -> str:
    cid = EMOJI.get(name)
    fb = fallback or EMOJI_FALLBACK.get(name, "✨")
    if cid:
        # Standard native tg://emoji link format rendered as live animated emoji by AyuGram & Telegram Desktop
        return f'<a href="tg://emoji?id={cid}">{fb}</a>'
    return fb


def make_btn(text: str, callback_data: str = None, url: str = None, emoji: str = None, style: str = None) -> InlineKeyboardButton:
    cid = EMOJI.get(emoji) if emoji else None
    fb = EMOJI_FALLBACK.get(emoji, "") if emoji else ""
    clean_text = text.strip()

    # Determine if text already starts with an emoji
    has_emoji = any(clean_text.startswith(val) for val in list(EMOJI_FALLBACK.values()) + ["🔙", "⬅️", "➡️", "🌐", "📄", "➕", "❌", "✅"] if val)

    if not has_emoji and fb:
        button_text = f"{fb} {clean_text}"
    else:
        button_text = clean_text

    kwargs = {"text": button_text}
    if url:
        kwargs["url"] = url
    else:
        kwargs["callback_data"] = callback_data

    if cid:
        kwargs["icon_custom_emoji_id"] = str(cid)

    # Style resolution (Bot API 9.4)
    cb = callback_data or ""
    t_lower = button_text.lower()
    if style:
        kwargs["style"] = style
    elif cb == "main_menu" or "asosiy menyu" in t_lower or "bosh menyu" in t_lower or "orqaga" in t_lower or "qaytish" in t_lower:
        # Blue for backing to home / back
        kwargs["style"] = "primary"
    elif ("o'chirish" in t_lower or "ochirish" in t_lower or "delete" in t_lower or "dolog_" in cb or "cdlog_" in cb or "cdel_sch_" in cb or "deladm_" in cb):
        # Red for delete buttons
        kwargs["style"] = "danger"
    elif emoji in ("check", "paid"):
        kwargs["style"] = "success"

    return InlineKeyboardButton(**kwargs)


def is_owner(tg_id: int) -> bool:
    return int(tg_id) == OWNER_TG_ID


def main_inline_keyboard(is_admin: bool, school_id: int = 1, schools: list = None, is_owner_user: bool = False) -> InlineKeyboardMarkup:
    rows = []
    
    # 🏫 School buttons
    if schools:
        for s in schools:
            rows.append([
                make_btn(f"{s.school_number}-maktab ({s.place})", callback_data=f"view_sch_{s.id}", emoji="school")
            ])
    else:
        rows.append([
            make_btn("Maktablar va Sinflar", callback_data="list_schools", emoji="school")
        ])

    if is_admin:
        rows.append([
            make_btn("To'liq Hisobot", callback_data="main_stats", emoji="stats"),
            make_btn("Telegraph Hisoboti", callback_data="make_telegraph_report", emoji="memo")
        ])
        rows.append([
            make_btn("Qayta tekshirish (/all)", callback_data="admin_run_all", emoji="refresh")
        ])
        rows.append([
            make_btn("Sinflar Nazorati (Ruxsat/To'lov)", callback_data="admin_grades_ctrl_1", emoji="tools"),
        ])
        rows.append([
            make_btn("O'qituvchi orqali parollarni yangilash", callback_data="teacher_reset_start", emoji="key")
        ])
        rows.append([
            make_btn("Sozlamalar", callback_data="admin_settings_menu", emoji="settings")
        ])

        rows.append([
            make_btn("Maktablar ro'yxati", callback_data="list_schools", emoji="school"),
            make_btn("AI Yordamchi", callback_data="main_help", emoji="bot")
        ])
    else:
        rows.append([
            make_btn("Statistika", callback_data="main_stats", emoji="stats"),
            make_btn("Telegraph Hisoboti", callback_data="make_telegraph_report", emoji="memo")
        ])
        rows.append([
            make_btn("AI Yordamchi", callback_data="main_help", emoji="bot")
        ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def cancel_inline_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        make_btn("Bekor qilish", callback_data="main_menu", emoji="cross")
    ]])


def grades_button(current_page: int):
    letters = ["A", "B", "V"]
    rows = []
    if current_page == 1:
        start, end = 1, 5
    elif current_page == 2:
        start, end = 5, 9
    else:
        start, end = 9, 12

    for i in range(start, end):
        row = []
        for letter in letters:
            row.append(
                InlineKeyboardButton(
                    text=f"{i}-{letter}",
                    callback_data=f"selgrade_{i}{letter}"
                )
            )
        rows.append(row)

    nav_buttons = [
        InlineKeyboardButton(text="⬅️", callback_data=f"gpage_{3 if current_page == 1 else 2 if current_page == 3 else 1}"),
        InlineKeyboardButton(text="➡️", callback_data=f"gpage_{2 if current_page == 1 else 3 if current_page == 2 else 1}"),
    ]
    rows.append(nav_buttons)
    rows.append([make_btn("Bekor qilish", callback_data="main_menu", emoji="cross")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# -------------------------------------------------------------------------
# Main Menu & Start Command
# -------------------------------------------------------------------------
@dp.message(CommandStart())
async def start_handler(message: Message, state: FSMContext, command: CommandObject = None):
    await state.clear()
    user_id = message.from_user.id

    user = await create_user(
        tg_id=user_id,
        first_name=message.from_user.first_name or "",
        username=message.from_user.username or ""
    )
    admin = await is_admin_or_owner(user_id)
    owner_user = is_owner(user_id)
    all_schools = await get_all_schools()

    greeting = (
        f"{tg_icon('owner', '👑')} <b>Boshqaruv Paneli</b>\n\n"
        f"• Tizim: <b>Faol</b> | {tg_icon('school')} Maktablar: <b>{len(all_schools)} ta</b>\n"
        f"• {tg_icon('tip', '💡')} <i>Savollarga AI javob beradi.</i>"
    ) if owner_user else ((
        f"{tg_icon('admin', '⭐')} <b>Administrator Paneli</b>\n\n"
        f"• Tizim: <b>Faol</b> | {tg_icon('school')} Maktablar: <b>{len(all_schools)} ta</b>"
    ) if admin else (
        f"{tg_icon('wave', '👋')} <b>Assalomu alaykum, {message.from_user.first_name}!</b>\n\n"
        f"eMaktab monitoring tizimi.\n"
        f"• {tg_icon('tip', '💡')} <i>Savollarga AI javob beradi.</i>"
    ))

    await message.answer(greeting, reply_markup=main_inline_keyboard(admin, schools=all_schools, is_owner_user=owner_user))


@dp.callback_query(F.data == "main_menu")
async def main_menu_callback(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    user_id = callback.from_user.id
    admin = await is_admin_or_owner(user_id)
    owner_user = is_owner(user_id)
    all_schools = await get_all_schools()
    text = (
        f"{tg_icon('owner', '👑')} <b>Bosh boshqaruv menyusi:</b>"
    ) if owner_user else ((
        f"{tg_icon('admin', '⭐')} <b>Administrator menyusi:</b>"
    ) if admin else (
        f"{tg_icon('wave', '👋')} <b>Bosh menyu:</b>"
    ))
    try:
        await callback.message.edit_text(text, reply_markup=main_inline_keyboard(admin, schools=all_schools, is_owner_user=owner_user))
    except TelegramBadRequest:
        pass


@dp.callback_query(F.data == "main_help")
async def help_callback(callback: CallbackQuery):
    admin = is_owner(callback.from_user.id)
    text = (
        "🤖 <b>eMaktab Avtomatlashtirish Boti (100% Inline Rejim)</b>\n\n"
        "• <b>🏫 14-maktab</b> — Maktab va sinflar bo'yicha to'liq statistika hamda loginlar.\n"
        "• <b>📊 Statistika</b> — Tizim bo'yicha umumiy hisobot.\n"
        "• <b>➕ Login qo'shish</b> — Yangi login va parollarni kiritish.\n"
    )
    if admin:
        text += (
            "\n👑 <b>Bosh Administrator Imkoniyatlari:</b>\n"
            "• Har bir sinfdagi login/parollarni ko'rish va tahrirlash\n"
            "• Parollarni o'zgartirish va o'chirish\n"
            "• Har bir o'quvchi hisobini alohida test qilish\n"
            "• Har kuni ertalab 07:00 da avtomatik hisobot va DB backup olish"
        )
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        make_btn("Asosiy Menyu", callback_data="main_menu")
    ]])
    try:
        await callback.message.edit_text(text, reply_markup=kb)
    except TelegramBadRequest:
        pass


# -------------------------------------------------------------------------
# Schools Listing & Inspection
# -------------------------------------------------------------------------
@dp.message(Command("schools"))
async def list_schools_command(message: Message):
    schools = await get_all_schools()
    admin = is_owner(message.from_user.id)
    if not schools:
        text = "ℹ️ Hozircha bazada hech qanday maktab mavjud emas."
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="➕ Maktab qo'shish", callback_data="admin_add_school")
        ]]) if admin else None
        await message.answer(text, reply_markup=kb)
        return

    text = "🏫 <b>Barcha maktablar ro'yxati:</b>\n<i>Statistikani ko'rish uchun maktabni tanlang:</i>"
    buttons = []
    for s in schools:
        buttons.append([make_btn(f"{s.school_number}-maktab ({s.place})", callback_data=f"view_sch_{s.id}", emoji="school")])

    buttons.append([make_btn("Asosiy Menyu", callback_data="main_menu", emoji="back")])
    await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))


@dp.callback_query(F.data == "list_schools")
async def list_schools_callback(callback: CallbackQuery):
    schools = await get_all_schools()
    admin = is_owner(callback.from_user.id)
    if not schools:
        await callback.message.edit_text("ℹ️ Hozircha bazada maktablar mavjud emas.")
        return

    text = "🏫 <b>Barcha maktablar ro'yxati:</b>\n<i>Statistikani ko'rish uchun maktabni tanlang:</i>"
    buttons = []
    for s in schools:
        buttons.append([make_btn(f"{s.school_number}-maktab ({s.place})", callback_data=f"view_sch_{s.id}", emoji="school")])

    buttons.append([make_btn("Asosiy Menyu", callback_data="main_menu", emoji="back")])
    try:
        await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    except TelegramBadRequest:
        pass


@dp.callback_query(F.data.startswith("view_sch_"))
async def view_school_callback(callback: CallbackQuery):
    school_id = int(callback.data.split("view_sch_")[1])
    school = await get_school_number(id=school_id)
    if not school:
        await callback.answer("Maktab topilmadi!", show_alert=True)
        return

    stats = await get_school_stats(school_id)
    grades = await get_school_grades(school_id)
    admin = await is_admin_or_owner(callback.from_user.id)

    total = stats["total"]
    success = stats["success"]
    fail = stats["fail"]
    pct = stats["pct"]
    fail_pct = round(100.0 - pct, 1) if total > 0 else 0.0

    st_cnt = stats.get("students", total)
    pr_cnt = stats.get("parents", 0)
    lines = [
        f"{tg_icon('school', '🏫')} <b>{school.school_number}-maktab</b> ({school.place})",
        f"• {tg_icon('users', '👥')} Jami: <b>{total} ta</b> (o'quvchi:{st_cnt}, ota-ona:{pr_cnt}) | {tg_icon('check', '✅')} <b>{success} ({pct}%)</b> | {tg_icon('cross', '❌')} <b>{fail}</b>",
        ""
    ]

    if grades:
        lines.append(f"{tg_icon('books', '📚')} <b>Sinflar:</b>")
        now = datetime.now()
        for g in grades:
            cstats = await get_class_stats(school_id, g)
            c_tot = cstats["total"]
            c_succ = cstats["success"]
            pct_val = cstats["pct"]
            pct_disp = f"{int(pct_val)}%" if pct_val.is_integer() else f"{pct_val}%"
            c_st = cstats.get("students", 0)
            c_pr = cstats.get("parents", 0)

            g_info = await get_grade_info(g)
            is_allowed = bool(getattr(g_info, 'is_allowed', False)) if g_info else False
            is_paid = bool(getattr(g_info, 'is_paid', False)) if g_info else False
            allowed_until = getattr(g_info, 'allowed_until', None) if g_info else None
            is_trial_active = bool(is_allowed and (not allowed_until or allowed_until >= now))

            if is_paid:
                status_ico = tg_icon('paid', '🟢')
                tag_str = "To'langan"
            elif is_trial_active:
                rem_d = (allowed_until - now).days if allowed_until else 7
                status_ico = tg_icon('trial', '🟡')
                tag_str = f"Ruxsatda ({max(1, rem_d)}k)"
            else:
                status_ico = tg_icon('failed', '🔴')
                tag_str = "Qulflangan"

            lines.append(f"• {status_ico} <b>{g}:</b> {c_tot} ta | (oquvchi:{c_st}, ota-ona:{c_pr}) | {tg_icon('check', '✅')} {c_succ} ({pct_disp}) <i>[{tag_str}]</i>")
    else:
        lines.append("<i>Sinflar mavjud emas.</i>")

    keyboard_rows = []
    if admin:
        keyboard_rows.append([
            make_btn("Sinflar va Loginlar (Boshqarish)", callback_data=f"asch_gr_{school_id}", emoji="search")
        ])
        admin_act_row = [
            make_btn("Qayta tekshirish", callback_data=f"asch_chk_{school_id}", emoji="refresh")
        ]
        if is_owner(callback.from_user.id):
            admin_act_row.append(make_btn("Maktabni o'chirish", callback_data=f"cdel_sch_{school_id}", emoji="cross"))
        keyboard_rows.append(admin_act_row)

    keyboard_rows.append([
        make_btn("Yangilash", callback_data=f"view_sch_{school_id}", emoji="refresh"),
        make_btn("Asosiy Menyu", callback_data="main_menu", emoji="school")
    ])

    try:
        await callback.message.edit_text(
            "\n".join(lines),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard_rows)
        )
    except TelegramBadRequest:
        pass


# -------------------------------------------------------------------------
# Owner: Grade Control & Payment Management Panel (Sorted by School > Grade)
# -------------------------------------------------------------------------
async def render_grades_control_panel(callback: CallbackQuery, school_id: int, page: int):
    schools = await get_all_schools()
    if not schools:
        await callback.answer("Bazada maktablar topilmadi.", show_alert=True)
        return

    schools = sorted(schools, key=lambda s: s.school_number or 0)
    current_school = next((s for s in schools if s.id == school_id), schools[0])
    grades = await get_school_grades(current_school.id)

    if not grades:
        await callback.answer(f"{current_school.school_number}-maktabda sinflar topilmadi.", show_alert=True)
        return

    page_size = 6
    total_pages = (len(grades) + page_size - 1) // page_size
    page = max(1, min(page, total_pages))

    start_idx = (page - 1) * page_size
    curr_grades = grades[start_idx:start_idx + page_size]

    text_lines = [
        f"{tg_icon('settings')} <b>Sinflar Nazorati va To'lov Boshqaruvi:</b>\n",
        f"{tg_icon('school')} <b>Maktab:</b> {current_school.school_number}-maktab ({current_school.place})",
        f"Sinflarning tizimga kirishiga <b>Ruxsat</b> ({tg_icon('paid')}/{tg_icon('cross')}) va <b>To'lov holatini</b> ({tg_icon('money')}/{tg_icon('cross')}) boshqarishingiz mumkin.\n",
        f"{tg_icon('memo')} Sahifa: <b>{page}/{total_pages}</b>"
    ]

    rows = []

    if len(schools) > 1:
        sch_row = []
        for s in schools:
            is_active = (s.id == current_school.id)
            lbl = f"{s.school_number}-maktab"
            ico = "check" if is_active else "school"
            sch_row.append(make_btn(lbl, callback_data=f"admin_grades_ctrl_{s.id}_1", emoji=ico))
            if len(sch_row) == 2:
                rows.append(sch_row)
                sch_row = []
        if sch_row:
            rows.append(sch_row)

    now = datetime.now()
    for g in curr_grades:
        g_info = await get_grade_info(g)
        is_allowed = bool(getattr(g_info, 'is_allowed', False)) if g_info else False
        is_paid = bool(getattr(g_info, 'is_paid', False)) if g_info else False
        allowed_until = getattr(g_info, 'allowed_until', None) if g_info else None

        if is_allowed:
            if is_paid:
                allow_lbl = "Ruxsatda (Cheksiz)"
                allow_ico = "paid"
            elif allowed_until and allowed_until < now:
                allow_lbl = "Limit tugadi"
                allow_ico = "trial"
            else:
                rem_days = (allowed_until - now).days if allowed_until else 7
                allow_lbl = f"Ruxsatda ({max(1, rem_days)}k)"
                allow_ico = "paid"
        else:
            allow_lbl = "Qulflangan"
            allow_ico = "lock"

        paid_lbl = "To'langan" if is_paid else "To'lanmagan"
        paid_ico = "money" if is_paid else "cross"

        rows.append([
            make_btn(f"{g}", callback_data=f"agrd_{current_school.id}_{g}_1", emoji="books"),
            make_btn(allow_lbl, callback_data=f"tg_allow_{current_school.id}_{g}_{page}", emoji=allow_ico),
            make_btn(paid_lbl, callback_data=f"tg_paid_{current_school.id}_{g}_{page}", emoji=paid_ico)
        ])

    nav_row = []
    if page > 1:
        nav_row.append(make_btn("Oldingi", callback_data=f"admin_grades_ctrl_{current_school.id}_{page - 1}", emoji="chart_down"))
    nav_row.append(make_btn(f"{page}/{total_pages}", callback_data="noop"))
    if page < total_pages:
        nav_row.append(make_btn("Keyingi", callback_data=f"admin_grades_ctrl_{current_school.id}_{page + 1}", emoji="chart"))
    if nav_row:
        rows.append(nav_row)

    rows.append([make_btn("Bosh menyuga", callback_data="main_menu", emoji="refresh")])

    keyboard = InlineKeyboardMarkup(inline_keyboard=rows)
    try:
        await callback.message.edit_text("\n".join(text_lines), reply_markup=keyboard)
    except TelegramBadRequest:
        try:
            await callback.message.edit_reply_markup(reply_markup=keyboard)
        except TelegramBadRequest:
            pass


@dp.callback_query(F.data.startswith("admin_grades_ctrl_"))
async def admin_grades_control_list_callback(callback: CallbackQuery):
    if not await is_admin_or_owner(callback.from_user.id):
        await callback.answer("🚫 Ruxsat berilmagan!", show_alert=True)
        return

    parts = callback.data.split("_")
    schools = await get_all_schools()
    default_sch_id = schools[0].id if schools else 1

    school_id = int(parts[3]) if len(parts) > 4 else default_sch_id
    page = int(parts[4]) if len(parts) > 4 else int(parts[3]) if len(parts) > 3 else 1

    await render_grades_control_panel(callback, school_id, page)


@dp.callback_query(F.data.startswith("tg_allow_"))
async def admin_toggle_grade_allow_callback(callback: CallbackQuery):
    if not await is_admin_or_owner(callback.from_user.id):
        await callback.answer("🚫 Ruxsat berilmagan!", show_alert=True)
        return

    # format: tg_allow_{school_id}_{grade_name}_{page}
    parts = callback.data.split("_")
    school_id = int(parts[2])
    grade_name = parts[3]
    page = int(parts[4])

    new_val = await toggle_grade_allowed(grade_name)
    status_str = "faollashtirildi (kirishga ruxsat berildi) ✅" if new_val else "qulflab qo'yildi (kirish to'xtatildi) 🔴"
    await callback.answer(f"{grade_name}-sinf {status_str}", show_alert=False)

    await render_grades_control_panel(callback, school_id, page)


@dp.callback_query(F.data.startswith("tg_paid_"))
async def admin_toggle_grade_paid_callback(callback: CallbackQuery):
    if not await is_admin_or_owner(callback.from_user.id):
        await callback.answer("🚫 Ruxsat berilmagan!", show_alert=True)
        return

    # format: tg_paid_{school_id}_{grade_name}_{page}
    parts = callback.data.split("_")
    school_id = int(parts[2])
    grade_name = parts[3]
    page = int(parts[4])

    new_val = await toggle_grade_paid(grade_name)
    status_str = "to'langan deb belgilandi 💳" if new_val else "to'lanmagan deb belgilandi 🚫"
    await callback.answer(f"{grade_name}-sinf {status_str}", show_alert=False)

    await render_grades_control_panel(callback, school_id, page)


# -------------------------------------------------------------------------
# Owner: School Grades Inspection & Management
# -------------------------------------------------------------------------
@dp.callback_query(F.data.startswith("asch_gr_"))
async def admin_school_grades_callback(callback: CallbackQuery):
    if not await is_admin_or_owner(callback.from_user.id):
        await callback.answer("🚫 Ruxsat berilmagan!", show_alert=True)
        return

    school_id = int(callback.data.split("asch_gr_")[1])
    school = await get_school_number(id=school_id)
    grades = await get_school_grades(school_id)

    if not grades:
        await callback.answer("Ushbu maktabda hech qanday sinf topilmadi.", show_alert=True)
        return

    text = (
        f"{tg_icon('school')} <b>{school.school_number}-maktab sinflari:</b>\n"
        f"<i>Login va parollarni ko'rish, tahrirlash yoki o'chirish uchun sinfni tanlang:</i>"
    )

    rows = []
    current_row = []
    for g in grades:
        cstats = await get_class_stats(school_id, g)
        c_tot = cstats["total"]
        c_st = cstats.get("students", 0)
        c_pr = cstats.get("parents", 0)
        btn_text = f"{g} (o:{c_st}, p:{c_pr}) ({c_tot} ta)"
        current_row.append(make_btn(btn_text, callback_data=f"agrd_{school_id}_{g}_1", emoji="books"))
        if len(current_row) == 2:
            rows.append(current_row)
            current_row = []
    if current_row:
        rows.append(current_row)

    rows.append([make_btn("Maktabga qaytish", callback_data=f"view_sch_{school_id}", emoji="school")])

    try:
        await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
    except TelegramBadRequest:
        pass


@dp.callback_query(F.data.startswith("allgrd_"))
@dp.callback_query(F.data.startswith("agrd_all_"))
async def admin_grade_all_logins_and_passwords_callback(callback: CallbackQuery):
    if not await is_admin_or_owner(callback.from_user.id):
        await callback.answer("🚫 Ruxsat berilmagan!", show_alert=True)
        return

    # format: allgrd_{school_id}_{grade} or agrd_all_{school_id}_{grade}
    parts = callback.data.split("_")
    if callback.data.startswith("allgrd_"):
        school_id = int(parts[1])
        grade = parts[2]
    else:
        school_id = int(parts[2])
        grade = parts[3]

    school = await get_school_number(id=school_id)
    school_name = f"{school.school_number}-maktab" if school else f"{school_id}"
    all_logins_in_grade = await get_all_logins(school2=school_id, grade=grade)

    if not all_logins_in_grade:
        await callback.answer("Ushbu sinfda loginlar topilmadi.", show_alert=True)
        return

    await callback.answer("⏳ Login va parollar saralanmoqda...", show_alert=False)

    async def fetch_item(l):
        prof = await get_student_profile_data(l.username, l.password, l.last_cookie, fast_only=True)
        name = prof.get("full_name") or format_name_from_username(l.username)
        role = getattr(l, "role", "student") or "student"
        return {
            "login": l.username,
            "password": l.password,
            "role": role,
            "name": name,
            "last_login": l.last_login
        }

    items = await asyncio.gather(*[fetch_item(l) for l in all_logins_in_grade])

    students = [x for x in items if x["role"] != "parent"]
    parents = [x for x in items if x["role"] == "parent"]

    # Sorted alphabetically by name within each group
    students.sort(key=lambda x: str(x["name"]).lower())
    parents.sort(key=lambda x: str(x["name"]).lower())

    text_parts = [
        f"{tg_icon('memo')} <b>{school_name} | {grade}-sinf barcha login va parollari:</b>",
        f"• {tg_icon('users')} Jami hisoblar: <b>{len(items)} ta</b> (🎓 O'quvchilar: {len(students)}, 👨‍👩‍👦 Ota-onalar: {len(parents)})\n"
    ]

    if students:
        text_parts.append(f"🎓 <b>O'QUVCHILAR (STUDENTS) — {len(students)} ta:</b>")
        for idx, s in enumerate(students, 1):
            ico = tg_icon('check', '✅') if s.get('last_login') else tg_icon('cross', '❌')
            s_name = html.escape(str(s['name']))
            s_login = html.escape(str(s['login']))
            s_pass = html.escape(str(s['password']))
            text_parts.append(
                f"{idx}. <b>{s_name}</b> {ico}\n"
                f"   • Login: <code>{s_login}</code>\n"
                f"   • Parol: <code>{s_pass}</code>"
            )
        text_parts.append("")

    if parents:
        text_parts.append(f"👨‍👩‍👦 <b>OTA-ONALAR (PARENTS) — {len(parents)} ta:</b>")
        for idx, p in enumerate(parents, 1):
            ico = tg_icon('check', '✅') if p.get('last_login') else tg_icon('cross', '❌')
            p_name = html.escape(str(p['name']))
            p_login = html.escape(str(p['login']))
            p_pass = html.escape(str(p['password']))
            text_parts.append(
                f"{idx}. <b>{p_name}</b> {ico}\n"
                f"   • Login: <code>{p_login}</code>\n"
                f"   • Parol: <code>{p_pass}</code>"
            )

    full_text = "\n".join(text_parts)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [make_btn("⬅️ Sinf ro'yxatiga qaytish", callback_data=f"agrd_{school_id}_{grade}_1", emoji="books")],
        [make_btn("🏫 Maktabga", callback_data=f"view_sch_{school_id}", emoji="school")]
    ])

    if len(full_text) <= 4000:
        try:
            await callback.message.edit_text(full_text, reply_markup=kb)
        except Exception:
            try:
                await callback.message.answer(full_text, reply_markup=kb)
            except Exception:
                await callback.message.answer(re.sub(r'<[^>]+>', '', full_text), reply_markup=kb, parse_mode=None)
    else:
        try:
            await callback.message.edit_text(
                f"📋 <b>{school_name} | {grade}-sinf hisoblari ({len(items)} ta):</b>\n<i>Quyida to'liq ro'yxat chiqarilmoqda...</i>"
            )
        except Exception:
            pass

        chunks = []
        cur = []
        cur_len = 0
        for block in full_text.split("\n\n"):
            if cur_len + len(block) + 2 > 3500:
                if cur:
                    chunks.append("\n\n".join(cur))
                cur = [block]
                cur_len = len(block)
            else:
                cur.append(block)
                cur_len += len(block) + 2
        if cur:
            chunks.append("\n\n".join(cur))

        for i, ch in enumerate(chunks):
            reply_markup = kb if i == len(chunks) - 1 else None
            try:
                await callback.message.answer(ch, reply_markup=reply_markup)
            except Exception:
                await callback.message.answer(re.sub(r'<[^>]+>', '', ch), reply_markup=reply_markup, parse_mode=None)


@dp.callback_query(F.data.startswith("agrd_"))
async def admin_grade_logins_callback(callback: CallbackQuery):
    if not await is_admin_or_owner(callback.from_user.id):
        await callback.answer("🚫 Ruxsat berilmagan!", show_alert=True)
        return

    # format: agrd_{school_id}_{grade}_{page}
    parts = callback.data.split("_")
    if len(parts) < 4 or not parts[1].isdigit():
        return

    school_id = int(parts[1])
    grade = parts[2]
    page = int(parts[3])

    school = await get_school_number(id=school_id)
    all_logins_in_grade = await get_all_logins(school2=school_id, grade=grade)

    if not all_logins_in_grade:
        await callback.answer("Ushbu sinfda loginlar topilmadi.", show_alert=True)
        return

    # Sort: Students first, then Parents; within each group, sort alphabetically by username
    all_logins_in_grade.sort(key=lambda l: (1 if getattr(l, "role", "student") == "parent" else 0, l.username.lower()))

    page_size = 6
    total_pages = (len(all_logins_in_grade) + page_size - 1) // page_size
    page = max(1, min(page, total_pages))

    start_idx = (page - 1) * page_size
    current_page_logins = all_logins_in_grade[start_idx:start_idx + page_size]

    s_cnt = sum(1 for x in all_logins_in_grade if getattr(x, "role", "student") != "parent")
    p_cnt = len(all_logins_in_grade) - s_cnt

    text_lines = [
        f"{tg_icon('school')} <b>{school.school_number}-maktab</b> | {tg_icon('books')} <b>{grade}-sinf</b>",
        f"{tg_icon('users')} Jami hisoblar: <b>{len(all_logins_in_grade)} ta</b> (o'quvchi: {s_cnt}, ota-ona: {p_cnt})",
        f"{tg_icon('memo')} Sahifa: <b>{page}/{total_pages}</b>",
        "",
        "<i>Boshqarish (parolni ko'rish, o'zgartirish, test qilish) uchun hisobni tanlang:</i>"
    ]

    rows = []
    for l in current_page_logins:
        status_ico = "check" if l.last_login else "cross"
        role_label = "parent" if getattr(l, "role", "student") == "parent" else "student"
        rows.append([
            make_btn(
                f"{l.username} ({role_label})",
                callback_data=f"vlog_{l.id}_{school_id}_{grade}_{page}",
                emoji=status_ico
            )
        ])

    nav_row = []
    if page > 1:
        nav_row.append(make_btn("Oldingi", callback_data=f"agrd_{school_id}_{grade}_{page - 1}", emoji="chart_down"))
    nav_row.append(make_btn(f"{page}/{total_pages}", callback_data="noop"))
    if page < total_pages:
        nav_row.append(make_btn("Keyingi", callback_data=f"agrd_{school_id}_{grade}_{page + 1}", emoji="chart"))
    if nav_row:
        rows.append(nav_row)

    rows.append([
        make_btn("📋 Barcha login va parollar", callback_data=f"allgrd_{school_id}_{grade}", emoji="memo")
    ])
    rows.append([
        make_btn("Sinflarga qaytish", callback_data=f"asch_gr_{school_id}", emoji="books"),
        make_btn("Maktabga", callback_data=f"view_sch_{school_id}", emoji="school")
    ])

    try:
        await callback.message.edit_text(
            "\n".join(text_lines),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows)
        )
    except TelegramBadRequest:
        pass


# -------------------------------------------------------------------------
# Owner: Single Login Actions (View, Edit, Test, Delete)
# -------------------------------------------------------------------------
_STUDENT_PROFILE_CACHE = {}

def format_name_from_username(username: str) -> str:
    cleaned = re.sub(r'\d+$', '', username.strip())
    parts = cleaned.replace("_", ".").split(".")
    words = [p.capitalize() for p in parts if p]
    if len(words) >= 2:
        return f"{words[0]} {words[1]}"
    elif len(words) == 1:
        return words[0]
    return username

async def get_student_profile_data(username: str, password: str, cookie: str = None, fast_only: bool = False):
    key = username.strip().lower()
    if key in _STUDENT_PROFILE_CACHE:
        return _STUDENT_PROFILE_CACHE[key]

    import aiohttp
    full_name = None
    school_name = None
    grade_name = None

    if cookie and "UZDnevnikAuth_a" in cookie:
        try:
            cookie_dict = {}
            for part in cookie.split(";"):
                if "=" in part:
                    k, v = part.strip().split("=", 1)
                    if v:
                        cookie_dict[k] = v
            timeout = aiohttp.ClientTimeout(total=2.5)
            async with aiohttp.ClientSession(cookies=cookie_dict, timeout=timeout) as session:
                async with session.get("https://emaktab.uz/marks", headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
                }) as resp:
                    if resp.status == 200:
                        html_text = await resp.text()
                        m_marks = re.search(r'window\.__MARKS__INITIAL__STATE__\s*=\s*(\{.*?\});', html_text)
                        if m_marks:
                            data = json.loads(m_marks.group(1))
                            mems = data.get("context", {}).get("schoolMemberships", [])
                            if mems:
                                mem = mems[0]
                                fn = mem.get("firstName", "")
                                ln = mem.get("lastName", "")
                                full_name = f"{fn} {ln}".strip()
                                school_name = mem.get("schoolName", "")
                                groups = mem.get("groups", [])
                                if groups:
                                    grade_name = groups[0].get("groupName", "")
        except Exception:
            pass

    if not full_name and not fast_only:
        try:
            from emaktab_auto import auto_detect_login
            res = await auto_detect_login(username, password)
            if res.get("success"):
                full_name = res.get("full_name")
                school_name = res.get("school_name")
                grade_name = res.get("grade")
        except Exception:
            pass

    if not full_name:
        full_name = format_name_from_username(username)

    res_data = {
        "full_name": full_name,
        "school_name": school_name,
        "grade": grade_name
    }
    if full_name:
        _STUDENT_PROFILE_CACHE[key] = res_data
    return res_data


def render_single_login_text(login_obj, school_name: str, prof: dict = None) -> str:
    prof = prof or {}
    status_str = f"{tg_icon('check')} Muvaffaqiyatli kirilgan" if login_obj.last_login else f"{tg_icon('cross')} Kirilmagan (xato)"
    upd_time = login_obj.updated_at.strftime("%d.%m.%Y %H:%M") if login_obj.updated_at else "Ma'lumot yo'q"
    paid_str = f"{tg_icon('money')} To'langan {tg_icon('check')}" if getattr(login_obj, 'is_paid', True) else f"{tg_icon('cross')} To'lanmagan (qulflangan)"

    is_parent = getattr(login_obj, "role", "student") == "parent"
    role_uz = "Ota-ona" if is_parent else "O'quvchi"
    role_en = "parent" if is_parent else "student"

    person_title = prof.get("full_name") or f"{login_obj.username}"
    display_school = prof.get("school_name") or school_name
    grade_val = prof.get("grade") or f"{login_obj.grade}-sinf"
    if not grade_val.endswith("-sinf") and not grade_val.endswith("sinf"):
        grade_val = f"{grade_val}-sinf"

    return (
        f"{tg_icon('user')} <b>{role_uz} ({role_en}):</b> <b>{person_title}</b>\n"
        f"🏫 <b>Maktab:</b> {display_school}\n"
        f"📚 <b>Sinf:</b> {grade_val}\n"
        f"• Login: <code>{login_obj.username}</code>\n"
        f"• Parol: <code>{login_obj.password}</code>\n"
        f"• Holat: {status_str} | {paid_str}\n"
        f"• {tg_icon('clock')} <code>{upd_time}</code>"
    )


@dp.callback_query(F.data.startswith("vlog_"))
async def admin_view_single_login_callback(callback: CallbackQuery):
    if not await is_admin_or_owner(callback.from_user.id):
        await callback.answer("🚫 Ruxsat berilmagan!", show_alert=True)
        return

    parts = callback.data.split("_")
    login_id = int(parts[1])
    school_id = int(parts[2])
    grade = parts[3]
    page = int(parts[4])

    login_obj = await get_login_by_id(login_id)
    if not login_obj:
        await callback.answer("Login topilmadi!", show_alert=True)
        return

    school = await get_school_number(id=school_id)
    school_name = f"{school.school_number}-maktab" if school else f"{school_id}"

    prof = await get_student_profile_data(login_obj.username, login_obj.password, login_obj.last_cookie)
    text = render_single_login_text(login_obj, school_name, prof)

    pay_btn_text = "To'lanmagan qilish" if getattr(login_obj, 'is_paid', True) else "To'langan deb belgilash"
    pay_btn_ico = "cross" if getattr(login_obj, 'is_paid', True) else "money"

    rows = [
        [
            make_btn(pay_btn_text, callback_data=f"tpay_log_{login_id}_{school_id}_{grade}_{page}", emoji=pay_btn_ico)
        ],
        [
            make_btn("Parolni o'zgartirish", callback_data=f"epwd_{login_id}_{school_id}_{grade}_{page}", emoji="edit"),
            make_btn("Kirishni tekshirish", callback_data=f"tlog_{login_id}_{school_id}_{grade}_{page}", emoji="refresh")
        ],
        [
            make_btn("Loginni o'chirish", callback_data=f"cdlog_{login_id}_{school_id}_{grade}_{page}", emoji="cross")
        ],
        [
            make_btn("Sinf ro'yxatiga qaytish", callback_data=f"agrd_{school_id}_{grade}_{page}", emoji="books")
        ]
    ]

    try:
        await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
    except TelegramBadRequest:
        pass


@dp.callback_query(F.data.startswith("tpay_log_"))
async def admin_toggle_login_payment_callback(callback: CallbackQuery):
    if not await is_admin_or_owner(callback.from_user.id):
        await callback.answer("🚫 Ruxsat berilmagan!", show_alert=True)
        return

    parts = callback.data.split("_")
    login_id = int(parts[2])
    school_id = int(parts[3])
    grade = parts[4]
    page = int(parts[5])

    new_val = await toggle_login_paid(login_id)
    msg = "To'langan deb belgilandi!" if new_val else "To'lanmagan (qulflangan) deb belgilandi!"
    await callback.answer(msg, show_alert=True)

    # Re-render single login view
    login_obj = await get_login_by_id(login_id)
    school = await get_school_number(id=school_id)
    school_name = f"{school.school_number}-maktab" if school else f"{school_id}"

    prof = await get_student_profile_data(login_obj.username, login_obj.password, login_obj.last_cookie)
    text = render_single_login_text(login_obj, school_name, prof)

    pay_btn_text = "To'lanmagan qilish" if getattr(login_obj, 'is_paid', True) else "To'langan deb belgilash"
    pay_btn_ico = "cross" if getattr(login_obj, 'is_paid', True) else "money"

    rows = [
        [
            make_btn(pay_btn_text, callback_data=f"tpay_log_{login_id}_{school_id}_{grade}_{page}", emoji=pay_btn_ico)
        ],
        [
            make_btn("Parolni o'zgartirish", callback_data=f"epwd_{login_id}_{school_id}_{grade}_{page}", emoji="edit"),
            make_btn("Kirishni tekshirish", callback_data=f"tlog_{login_id}_{school_id}_{grade}_{page}", emoji="refresh")
        ],
        [
            make_btn("Loginni o'chirish", callback_data=f"cdlog_{login_id}_{school_id}_{grade}_{page}", emoji="cross")
        ],
        [
            make_btn("Sinf ro'yxatiga qaytish", callback_data=f"agrd_{school_id}_{grade}_{page}", emoji="books")
        ]
    ]

    keyboard = InlineKeyboardMarkup(inline_keyboard=rows)
    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except TelegramBadRequest:
        try:
            await callback.message.edit_reply_markup(reply_markup=keyboard)
        except TelegramBadRequest:
            pass


@dp.callback_query(F.data.startswith("tlog_"))
async def admin_test_single_login_callback(callback: CallbackQuery):
    if not await is_admin_or_owner(callback.from_user.id):
        await callback.answer("🚫 Ruxsat berilmagan!", show_alert=True)
        return

    parts = callback.data.split("_")
    login_id = int(parts[1])
    school_id = int(parts[2])
    grade = parts[3]
    page = int(parts[4])

    login_obj = await get_login_by_id(login_id)
    if not login_obj:
        await callback.answer("Login topilmadi!", show_alert=True)
        return

    await callback.answer("⏳ eMaktab serveriga ulanilmoqda...", show_alert=False)

    payload = {
        login_obj.id: {
            "login_id": login_obj.id,
            "username": login_obj.username,
            "password": login_obj.password,
            "last_login": False,
            "last_cookie": "",
            "tg_id": callback.from_user.id,
            "grade": login_obj.grade
        }
    }
    res = await send_request_main(payload)
    succ = res.get(login_obj.id, {}).get("last_login", False)

    updated_login = await get_login_by_id(login_id)
    status_str = "✅ Muvaffaqiyatli kirildi!" if succ else "❌ Kirib bo'lmadi (parol yoki login xato)!"

    text = (
        f"👤 <b>Tekshiruv natijasi:</b>\n\n"
        f"👤 <b>Login:</b> <code>{updated_login.username}</code>\n"
        f"🔑 <b>Parol:</b> <code>{updated_login.password}</code>\n"
        f"📌 <b>Natija:</b> {status_str}\n"
    )

    rows = [
        [
            make_btn("Parolni o'zgartirish", callback_data=f"epwd_{login_id}_{school_id}_{grade}_{page}", emoji="edit"),
            make_btn("Qayta tekshirish", callback_data=f"tlog_{login_id}_{school_id}_{grade}_{page}", emoji="refresh")
        ],
        [
            make_btn("Loginni o'chirish", callback_data=f"cdlog_{login_id}_{school_id}_{grade}_{page}", emoji="cross")
        ],
        [
            make_btn("Sinf ro'yxatiga qaytish", callback_data=f"agrd_{school_id}_{grade}_{page}", emoji="books")
        ]
    ]

    try:
        await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
    except TelegramBadRequest:
        pass


@dp.callback_query(F.data.startswith("epwd_"))
async def admin_edit_pwd_prompt_callback(callback: CallbackQuery, state: FSMContext):
    if not await is_admin_or_owner(callback.from_user.id):
        await callback.answer("🚫 Ruxsat berilmagan!", show_alert=True)
        return

    parts = callback.data.split("_")
    login_id = int(parts[1])
    school_id = int(parts[2])
    grade = parts[3]
    page = int(parts[4])

    login_obj = await get_login_by_id(login_id)
    if not login_obj:
        await callback.answer("Login topilmadi!", show_alert=True)
        return

    await state.set_state(EditLoginPwd.new_password)
    await state.update_data(
        login_id=login_id,
        school_id=school_id,
        grade=grade,
        page=page
    )

    await callback.message.answer(
        f"✏️ <b>{login_obj.username}</b> uchun yangi parolni kiriting:",
        reply_markup=cancel_inline_keyboard()
    )
    await callback.answer()


@dp.message(EditLoginPwd.new_password)
async def admin_save_new_pwd(message: Message, state: FSMContext):
    if not await is_admin_or_owner(message.from_user.id):
        await state.clear()
        return

    new_pwd = message.text.strip()
    data = await state.get_data()
    await state.clear()

    login_id = data.get("login_id")
    school_id = data.get("school_id")
    grade = data.get("grade")
    page = data.get("page", 1)

    ok = await update_login_credentials(login_id=login_id, password=new_pwd)
    if ok:
        await message.answer(
            f"✅ Parol muvaffaqiyatli saqlandi: <code>{new_pwd}</code>\n"
            f"Endi ushbu loginni qayta tekshirishingiz mumkin.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="🔄 Kirishni tekshirish", callback_data=f"tlog_{login_id}_{school_id}_{grade}_{page}"),
                InlineKeyboardButton(text="👤 Loginga qaytish", callback_data=f"vlog_{login_id}_{school_id}_{grade}_{page}")
            ]])
        )
    else:
        await message.answer("❌ Parolni yangilashda xatolik yuz berdi.", reply_markup=main_inline_keyboard(True, school_id=1))


@dp.callback_query(F.data.startswith("cdlog_"))
async def admin_confirm_delete_login_callback(callback: CallbackQuery):
    if not await is_admin_or_owner(callback.from_user.id):
        await callback.answer("🚫 Ruxsat berilmagan!", show_alert=True)
        return

    parts = callback.data.split("_")
    login_id = int(parts[1])
    school_id = int(parts[2])
    grade = parts[3]
    page = int(parts[4])

    login_obj = await get_login_by_id(login_id)
    if not login_obj:
        await callback.answer("Login topilmadi!", show_alert=True)
        return

    text = (
        f"{tg_icon('cross')} <b>DIQQAT!</b>\n\n"
        f"Haqiqatan ham <code>{login_obj.username}</code> loginini butunlay o'chirmoqchimisiz?"
    )

    rows = [
        [
            make_btn("Ha, o'chirish", callback_data=f"dolog_{login_id}_{school_id}_{grade}_{page}", emoji="cross"),
            make_btn("Bekor qilish", callback_data=f"vlog_{login_id}_{school_id}_{grade}_{page}", emoji="check")
        ]
    ]

    try:
        await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
    except TelegramBadRequest:
        pass


@dp.callback_query(F.data.startswith("dolog_"))
async def admin_do_delete_login_callback(callback: CallbackQuery):
    if not await is_admin_or_owner(callback.from_user.id):
        await callback.answer("🚫 Ruxsat berilmagan!", show_alert=True)
        return

    parts = callback.data.split("_")
    login_id = int(parts[1])
    school_id = int(parts[2])
    grade = parts[3]
    page = int(parts[4])

    await delete_login(login_id)
    await callback.answer("Login muvaffaqiyatli o'chirildi!", show_alert=True)

    callback.data = f"agrd_{school_id}_{grade}_{page}"
    await admin_grade_logins_callback(callback)


# -------------------------------------------------------------------------
# Owner: Delete School
# -------------------------------------------------------------------------
@dp.callback_query(F.data.startswith("cdel_sch_"))
async def admin_confirm_delete_school_callback(callback: CallbackQuery):
    if not is_owner(callback.from_user.id):
        await callback.answer("🚫 Ruxsat berilmagan!", show_alert=True)
        return

    school_id = int(callback.data.split("cdel_sch_")[1])
    school = await get_school_number(id=school_id)
    if not school:
        await callback.answer("Maktab topilmadi!", show_alert=True)
        return

    text = (
        f"{tg_icon('cross')} <b>DIQQAT! MAKTABNI O'CHIRISH!</b>\n\n"
        f"Haqiqatan ham <b>{school.school_number}-maktab</b>ni va unga tegishli barcha loginlarni o'chirmoqchimisiz?"
    )
    rows = [
        [
            make_btn("Ha, o'chirilsin", callback_data=f"dodel_sch_{school_id}", emoji="cross"),
            make_btn("Bekor qilish", callback_data=f"view_sch_{school_id}", emoji="check")
        ]
    ]
    try:
        await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
    except TelegramBadRequest:
        pass


@dp.callback_query(F.data.startswith("dodel_sch_"))
async def admin_do_delete_school_callback(callback: CallbackQuery):
    if not is_owner(callback.from_user.id):
        await callback.answer("🚫 Ruxsat berilmagan!", show_alert=True)
        return

    school_id = int(callback.data.split("dodel_sch_")[1])
    await delete_school(school_id)
    await callback.answer("🗑 Maktab o'chirildi!", show_alert=True)
    await list_schools_callback(callback)


# -------------------------------------------------------------------------
# Owner: Re-check Specific School or All Logins Inline
# -------------------------------------------------------------------------
@dp.callback_query(F.data.startswith("asch_chk_"))
async def admin_check_school_callback(callback: CallbackQuery):
    if not await is_admin_or_owner(callback.from_user.id):
        await callback.answer("🚫 Ruxsat berilmagan!", show_alert=True)
        return

    school_id = int(callback.data.split("asch_chk_")[1])
    school = await get_school_number(id=school_id)
    logins = await get_all_logins(school2=school_id, only_active=True)

    if not logins:
        await callback.answer("Ushbu maktabda tekshirish uchun faol loginlar yo'q.", show_alert=True)
        return

    await callback.answer(f"⏳ {school.school_number}-maktab loginlari tekshirilmoqda...", show_alert=False)

    payload = {
        l.id: {
            "login_id": l.id,
            "username": l.username,
            "password": l.password,
            "last_login": l.last_login,
            "last_cookie": l.last_cookie,
            "tg_id": callback.from_user.id,
            "grade": l.grade,
            "school_id": l.school
        }
        for l in logins
    }
    await send_request_main(payload)
    await callback.answer("✅ Tekshiruv yakunlandi!", show_alert=True)

    callback.data = f"view_sch_{school_id}"
    await view_school_callback(callback)


@dp.callback_query(F.data == "admin_run_all")
async def admin_run_all_callback(callback: CallbackQuery):
    if not await is_admin_or_owner(callback.from_user.id):
        await callback.answer("🚫 Ruxsat berilmagan!", show_alert=True)
        return

    await callback.answer("⏳ Barcha maktablar loginlari tekshirilmoqda...", show_alert=False)
    await login_schedule(callback.from_user.id)
    await callback.answer("✅ Tekshiruv yakunlandi!", show_alert=True)
    await main_stats_callback(callback)


# -------------------------------------------------------------------------
# Overall Statistics & Reports
# -------------------------------------------------------------------------
async def generate_overall_report_content():
    stats = await get_overall_stats()
    active_tot = stats["total"]
    all_tot = stats.get("all_total", active_tot)
    blocked_tot = stats.get("blocked_total", 0)
    success = stats["success"]
    fail = stats["fail"]
    pct = stats["pct"]
    fail_pct = round(100.0 - pct, 1) if active_tot > 0 else 0.0

    today_str = datetime.now(ZoneInfo("Asia/Tashkent")).strftime("%d.%m.%Y %H:%M")

    lines = [
        f"{tg_icon('stats', '📊')} <b>EMAKTAB TIZIMI HISOBOTI</b> ({today_str})",
        f"• {tg_icon('users', '👥')} Faol loginlar: <b>{active_tot} ta</b> (Qulflangan: {blocked_tot} ta) | {tg_icon('check', '✅')} <b>{success} ({pct}%)</b> | {tg_icon('cross', '❌')} <b>{fail}</b>",
        "",
        f"{tg_icon('school', '🏫')} <b>Maktablar:</b>"
    ]

    inline_buttons = []
    for s_info in stats["schools"]:
        s = s_info["school"]
        s_tot = s_info["total"]
        s_succ = s_info["success"]
        s_fail = s_info["fail"]
        s_pct = s_info["pct"]
        s_blk = s_info.get("blocked", 0)

        status_ico = tg_icon('paid', '🟢') if s_pct == 100.0 else (tg_icon('trial', '🟡') if s_pct >= 50.0 else tg_icon('failed', '🔴'))
        lines.append(
            f"• {status_ico} <b>{s.school_number}-maktab:</b> {s_tot} ta faol (qulflangan: {s_blk} ta) | {tg_icon('check', '✅')} {s_succ} ({s_pct}%) | {tg_icon('cross', '❌')} {s_fail}"
        )
        inline_buttons.append([
            make_btn(
                f"{s.school_number}-maktabni ko'rish ({s_pct}%)",
                callback_data=f"view_sch_{s.id}",
                emoji="school"
            )
        ])

    inline_buttons.append([
        make_btn("Telegraph Hisoboti Yaratish", callback_data="make_telegraph_report", emoji="memo")
    ])
    inline_buttons.append([make_btn("Asosiy Menyu", callback_data="main_menu", emoji="school")])
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=inline_buttons)


async def generate_telegraph_report_pages(is_admin: bool) -> list[dict]:
    all_schools = await get_all_schools()
    all_logins = await get_all_logins()

    pages = []
    today_str = datetime.now(ZoneInfo('Asia/Tashkent')).strftime('%d.%m.%Y %H:%M')
    total_all = len(all_logins)
    succ_all = sum(1 for l in all_logins if l.last_login)
    fail_all = total_all - succ_all
    pct_all = round(succ_all / total_all * 100, 1) if total_all > 0 else 0.0

    # 1. Overview Summary Page
    p1_html = [
        "<h3>🏫 eMaktab Avtomatlashtirish Tizimi Hisoboti</h3>",
        f"<p>📅 Sanasi: <b>{today_str}</b></p>",
        "<hr>",
        f"<p><b>📈 Umumiy ko'rsatkichlar:</b><br>",
        f"• 👥 Jami loginlar: <b>{total_all} ta</b><br>",
        f"• ✅ Muvaffaqiyatli kirilgan: <b>{succ_all} ta ({pct_all}%)</b><br>",
        f"• ❌ Kirilmagan (xatolik): <b>{fail_all} ta</b></p><hr>"
    ]

    def g_sort_key(g):
        num = ""
        char = ""
        for ch in str(g):
            if ch.isdigit():
                num += ch
            elif ch.isalpha():
                char += ch
        return (int(num) if num else 999, char)

    sorted_schools = sorted(all_schools or [], key=lambda s: s.school_number or 0)
    for school in sorted_schools:
        s_logins = [l for l in all_logins if str(getattr(l, "school", "")) == str(school.id)]
        if not s_logins:
            continue
        s_count = sum(1 for l in s_logins if l.last_login)
        s_pct = round(s_count / len(s_logins) * 100, 1) if s_logins else 0.0
        p1_html.append(f"<h4>🏫 {school.school_number}-maktab ({school.place}): {s_count}/{len(s_logins)} ta ({s_pct}%)</h4>")
        grouped = defaultdict(list)
        for l in s_logins:
            grouped[f"{l.grade}-sinf"].append(l)
        for g_name in sorted(grouped.keys(), key=g_sort_key):
            gl = grouped[g_name]
            g_raw = g_name.replace("-sinf", "").strip()
            g_info = await get_grade_info(g_raw)
            is_allowed = bool(getattr(g_info, 'is_allowed', False)) if g_info else False
            is_paid = bool(getattr(g_info, 'is_paid', False)) if g_info else False
            allowed_until = getattr(g_info, 'allowed_until', None) if g_info else None
            is_trial_active = bool(is_allowed and (not allowed_until or allowed_until >= datetime.now()))

            if is_paid:
                status_ico = "🟢"
                tag_str = "To'langan"
            elif is_trial_active:
                status_ico = "🟡"
                tag_str = "Ruxsatda (Sinov)"
            else:
                status_ico = "🔴"
                tag_str = "Qulflangan"

            g_ok = sum(1 for x in gl if x.last_login)
            p1_html.append(f"<p>{status_ico} <b>{g_name}</b>: {g_ok}/{len(gl)} ta kirilgan <i>[{tag_str}]</i></p>")

    p1 = await create_page_safe(telegraph, title="eMaktab — Umumiy Hisobot", content="".join(p1_html))
    if p1.get("url"):
        pages.append({"title": "📊 Umumiy Hisobot (Xulosa)", "url": p1["url"]})

    # 2. Detailed credential pages (Only for Admin; never exposed to non-admins)
    if is_admin:
        chunk_size = 100
        for idx_start in range(0, total_all, chunk_size):
            chunk_logins = all_logins[idx_start:idx_start + chunk_size]
            part_num = (idx_start // chunk_size) + 1
            total_parts = (total_all + chunk_size - 1) // chunk_size

            chunk_html = [
                f"<h3>📋 Login va Parollar ({part_num}/{total_parts}-qism)</h3>",
                f"<p>📅 Sana: <b>{today_str}</b></p><hr>"
            ]
            
            grouped = defaultdict(list)
            for l in chunk_logins:
                grouped[f"{l.grade}-sinf"].append(l)

            for g_name in sorted(grouped.keys(), key=g_sort_key):
                gl = grouped[g_name]
                chunk_html.append(f"<p><b>📚 {g_name} ({len(gl)} ta):</b></p><ul>")
                for i_sub, item in enumerate(gl, 1):
                    status_str = "✅" if item.last_login else "❌"
                    chunk_html.append(f"<li>{i_sub}. <b>{item.username}</b> | <code>{item.password}</code> [{status_str}]</li>")
                chunk_html.append("</ul>")

            p_det = await create_page_safe(telegraph, title=f"eMaktab Loginlar ({part_num}/{total_parts})", content="".join(chunk_html))
            if p_det.get("url"):
                pages.append({"title": f"📑 Login va Parollar {part_num}-qism", "url": p_det["url"]})

    return pages


@dp.callback_query(F.data == "make_telegraph_report")
@dp.message(Command("telegraph"))
async def telegraph_report_handler(event: Message | CallbackQuery):
    user_id = event.from_user.id
    admin = await is_admin_or_owner(user_id)
    
    if isinstance(event, CallbackQuery):
        await event.answer("⏳ Telegraph hisoboti tayyorlanmoqda...", show_alert=False)
        
    pages = await generate_telegraph_report_pages(admin)
    
    if not pages:
        text = "❌ Telegraph sahifasini yaratishda xatolik yuz berdi."
        kb = InlineKeyboardMarkup(inline_keyboard=[[make_btn("Asosiy Menyu", callback_data="main_menu")]])
    else:
        text = f"📄 <b>Telegraph Hisobotlari Tayyor!</b>\n\nKerakli sahifani ochish uchun tugmani bosing:"
        btn_rows = []
        for p in pages:
            btn_rows.append([make_btn(f"🌐 {p['title']}", url=p['url'])])
        btn_rows.append([make_btn("Asosiy Menyu", callback_data="main_menu")])
        kb = InlineKeyboardMarkup(inline_keyboard=btn_rows)

    if isinstance(event, Message):
        await event.answer(text, reply_markup=kb)
    else:
        try:
            await event.message.edit_text(text, reply_markup=kb)
        except TelegramBadRequest:
            pass


@dp.callback_query(F.data == "main_stats")
async def main_stats_callback(callback: CallbackQuery):
    report_text, markup = await generate_overall_report_content()
    try:
        await callback.message.edit_text(report_text, reply_markup=markup)
    except TelegramBadRequest:
        pass


@dp.message(Command("stats"))
async def stats_command_handler(message: Message):
    report_text, markup = await generate_overall_report_content()
    await message.answer(report_text, reply_markup=markup)


# -------------------------------------------------------------------------
# Automated Daily Report to Owner
# -------------------------------------------------------------------------
async def send_daily_report_to_owner():
    print("📢 Kunlik hisobot egasiga yuborilmoqda...")
    try:
        report_text, markup = await generate_overall_report_content()
        await bot.send_message(
            chat_id=OWNER_TG_ID,
            text=f"🌅 <b>XAYRLI TONG! KUNLIK AVTOMATIK HISOBOT:</b>\n\n{report_text}",
            reply_markup=markup
        )
    except Exception as e:
        print("⚠️ Kunlik hisobot yuborishda xatolik:", e)

    if os.path.exists("database.sqlite3"):
        try:
            doc = FSInputFile("database.sqlite3")
            await bot.send_document(
                chat_id=OWNER_TG_ID,
                document=doc,
                caption="💾 Kunlik ma'lumotlar bazasi nusxasi (backup)"
            )
        except Exception as e:
            print("⚠️ Backup yuborishda xatolik:", e)


async def login_schedule(user_id: int | None = None, filter_ids: list[int] | None = None):
    # Process logins whose class is active (either PAID without limit, or ALLOWED within 1-week trial)
    all_logins = await get_all_logins(only_active=True)
    if not all_logins:
        print("Bazada faol va ruxsat berilgan loginlar mavjud emas.")
        return {}

    if filter_ids:
        all_logins = [l for l in all_logins if l.id in filter_ids]

    payload = {
        login.id: {
            "login_id": login.id,
            "password": login.password,
            "username": login.username,
            "last_cookie": login.last_cookie,
            "last_login": login.last_login,
            "school_id": login.school,
            "tg_id": user_id,
            "grade": login.grade,
        }
        for login in all_logins
    }

    response = await send_request_main(payload, bot)

    bulk_items = [
        {
            "login_id": sid,
            "last_login": data["last_login"],
            "last_cookie": data["last_cookie"]
        }
        for sid, data in response.items()
    ]
    await bulk_create_logins_data(bulk_items)
    return response


async def send_json():
    """
    Staggered check: Runs across batches leading up to 07:00,
    re-checks any failed logins with a calm pause, and then sends the daily report at 07:00.
    """
    print("🌅 Rejali tekshiruv boshlandi (bosqichma-bosqich)...")
    res1 = await login_schedule()

    # Identify any logins that failed due to temporary eMaktab server load or timeouts
    failed_ids = [sid for sid, d in res1.items() if not d.get("last_login")]
    if failed_ids:
        print(f"⚠️ {len(failed_ids)} ta login kirmay qoldi. 2 daqiqadan so'ng qayta tekshiriladi (re-check)...")
        await asyncio.sleep(120)  # Calm interval to let eMaktab rate limits recover
        await login_schedule(filter_ids=failed_ids)

    print("📢 Barcha tekshiruvlar va qayta urinishlar yakunlandi. Kunlik hisobot yuborilmoqda...")
    await send_daily_report_to_owner()


# -------------------------------------------------------------------------



@dp.message(Command("all"))
async def all_logins_command(message: Message):
    if not await is_admin_or_owner(message.from_user.id):
        await message.answer("🚫 Ushbu buyruq faqat administrator uchun.")
        return
    msg = await message.answer("⏳ Barcha maktablar loginlarini tekshirish boshlandi...")
    await login_schedule(message.from_user.id)
    report_text, markup = await generate_overall_report_content()
    await msg.edit_text(f"✅ <b>Tekshiruv yakunlandi!</b>\n\n{report_text}", reply_markup=markup)


@dp.callback_query(F.data == "admin_db_backup")
@dp.message(Command("backup"))
async def db_backup_handler(event: Message | CallbackQuery):
    user_id = event.from_user.id
    if not is_owner(user_id):
        if isinstance(event, CallbackQuery):
            await event.answer("🚫 Bu amal faqat Bosh Administrator uchun.", show_alert=True)
        return

    if os.path.exists("database.sqlite3"):
        doc = FSInputFile("database.sqlite3")
        if isinstance(event, Message):
            await event.answer_document(doc, caption="💾 SQLite ma'lumotlar bazasi nusxasi")
        else:
            await event.message.answer_document(doc, caption="💾 SQLite ma'lumotlar bazasi nusxasi")
            await event.answer()
    else:
        if isinstance(event, CallbackQuery):
            await event.answer("Bazani topshiriqda xatolik.", show_alert=True)


# -------------------------------------------------------------------------
# Admin & Bot Configuration Panel
# -------------------------------------------------------------------------
@dp.callback_query(F.data == "admin_settings_menu")
@dp.message(Command("settings"))
@dp.message(Command("admin"))
@dp.message(Command("panel"))
async def admin_settings_menu_handler(event: Message | CallbackQuery, state: FSMContext):
    await state.clear()
    user_id = event.from_user.id
    if not await is_admin_or_owner(user_id):
        if isinstance(event, CallbackQuery):
            await event.answer("🚫 Ruxsat berilmagan!", show_alert=True)
        return

    owner_flag = is_owner(user_id)
    admins = await get_all_admins()
    check_time = await get_setting("check_time", "07:00")
    trial_days = await get_setting("trial_days", "7")

    text = (
        f"{tg_icon('settings')} <b>Sozlamalar va Adminlar</b>\n\n"
        f"• {tg_icon('owner')} Bosh Admin: <code>{OWNER_TG_ID}</code>\n"
        f"• {tg_icon('admin')} Adminlar: <b>{len(admins)} nafar</b>\n"
        f"• {tg_icon('clock')} Tekshiruv: <code>{check_time}</code> | {tg_icon('hourglass')} Sinov: <code>{trial_days} kun</code>"
    )

    rows = []
    if owner_flag:
        rows.append([
            make_btn("Adminlarni boshqarish", callback_data="admin_manage_users", emoji="users")
        ])
        rows.append([
            make_btn("Tekshiruv vaqti", callback_data="admin_set_sched_time", emoji="clock"),
            make_btn("Sinov muddati", callback_data="admin_set_trial_days", emoji="hourglass")
        ])
    rows.append([
        make_btn("Tizim holati (Server & DB)", callback_data="admin_sys_info", emoji="system")
    ])
    if owner_flag:
        rows.append([
            make_btn("DB Backup olish", callback_data="admin_db_backup", emoji="database")
        ])
    rows.append([
        make_btn("Asosiy Menyu", callback_data="main_menu", emoji="refresh")
    ])

    kb = InlineKeyboardMarkup(inline_keyboard=rows)
    if isinstance(event, Message):
        await event.answer(text, reply_markup=kb)
    else:
        try:
            await event.message.edit_text(text, reply_markup=kb)
        except TelegramBadRequest:
            pass


@dp.callback_query(F.data == "admin_manage_users")
async def admin_manage_users_callback(callback: CallbackQuery, state: FSMContext = None):
    if state:
        await state.clear()
    if not is_owner(callback.from_user.id):
        await callback.answer("🚫 Bu amal faqat Bosh Administrator uchun!", show_alert=True)
        return

    admins = await get_all_admins()
    lines = [
        f"{tg_icon('users')} <b>ADMINLAR VA HUQUQLAR BOSHQARUVI</b>\n",
        "Adminlar tizimga kirish, sinflarni boshqarish, to'lov holatini o'zgartirish va login/parollarni ko'rish huquqiga ega bo'ladilar.\n",
        "<b>Mavjud Administratorlar:</b>"
    ]

    rows = []
    for a in admins:
        tg_id = a["tg_id"]
        fname = a["first_name"] or "Foydalanuvchi"
        uname = f"@{a['username']}" if a["username"] else f"ID: {tg_id}"
        role_ico = tg_icon('owner') if a["role"] == "owner" else tg_icon('admin')
        lines.append(f"{role_ico} <b>{fname}</b> ({uname} | <code>{tg_id}</code>)")

        if a["role"] != "owner" and int(tg_id) != OWNER_TG_ID:
            rows.append([
                make_btn(
                    f"{fname} ({uname}) ni o'chirish",
                    callback_data=f"adm_demote_{tg_id}",
                    emoji="cross"
                )
            ])

    rows.append([
        make_btn("Yangi Admin qo'shish", callback_data="admin_add_admin_prompt", emoji="plus")
    ])
    rows.append([
        make_btn("Yangilash", callback_data="admin_manage_users", emoji="refresh"),
        make_btn("Sozlamalarga qaytish", callback_data="admin_settings_menu", emoji="settings")
    ])

    try:
        await callback.message.edit_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
    except TelegramBadRequest:
        pass


@dp.callback_query(F.data == "admin_add_admin_prompt")
async def admin_add_admin_prompt_callback(callback: CallbackQuery, state: FSMContext):
    if not is_owner(callback.from_user.id):
        await callback.answer("🚫 Faqat Bosh Administrator!", show_alert=True)
        return

    await state.set_state(AdminConfigStates.waiting_for_new_admin)
    text = (
        "➕ <b>YANGI ADMIN QO'SHISH</b>\n\n"
        "Quyidagi usullardan biri orqali yangi adminni belgilang:\n"
        "1. Foydalanuvchining <b>Telegram ID</b> raqamini yuboring (masalan: <code>5432194711</code>)\n"
        "2. Foydalanuvchining <b>@username</b> sini yuboring (masalan: <code>@informatik14</code>)\n"
        "3. Yoki uning birorta xabarini <b>Forward (Uzatish)</b> qiling!\n\n"
        "<i>Bekor qilish uchun pastdagi tugmani bosing:</i>"
    )
    await callback.message.edit_text(text, reply_markup=cancel_inline_keyboard())


@dp.message(AdminConfigStates.waiting_for_new_admin)
async def process_add_new_admin_message(message: Message, state: FSMContext):
    if not is_owner(message.from_user.id):
        await state.clear()
        return

    target_tg_id = None
    target_username = ""
    target_name = ""

    if message.forward_from:
        target_tg_id = message.forward_from.id
        target_username = message.forward_from.username or ""
        target_name = message.forward_from.full_name or message.forward_from.first_name or ""
    elif message.forward_sender_name:
        await message.answer(
            "⚠️ Ushbu foydalanuvchida xabarni uzatishda profil maxfiyligi yopiq.\n"
            "Iltimos, uning raqamli <b>Telegram ID</b> sini yoki <b>@username</b> sini yozing:",
            reply_markup=cancel_inline_keyboard()
        )
        return
    else:
        text = message.text.strip()
        if text.isdigit():
            target_tg_id = int(text)
        elif text.startswith("@") or text.isalnum():
            clean_u = text.lstrip("@").strip()
            db_user = await get_user_by_username(clean_u)
            if db_user:
                target_tg_id = db_user.tg_id
                target_username = db_user.username
                target_name = db_user.first_name or ""
            else:
                await message.answer(
                    f"❌ <code>@{clean_u}</code> foydalanuvchisi bot bazasidan topilmadi.\n"
                    f"Foydalanuvchi botga avval kamida 1 marta /start bosgan bo'lishi kerak yoki uning raqamli <b>Telegram ID</b> sini kiriting:",
                    reply_markup=cancel_inline_keyboard()
                )
                return

    if not target_tg_id:
        await message.answer("⚠️ Noto'g'ri ma'lumot kiritildi. Iltimos, Telegram ID yoki @username kiriting:", reply_markup=cancel_inline_keyboard())
        return

    await add_admin(target_tg_id, username=target_username, first_name=target_name)
    await state.clear()

    display_info = f"<b>{target_name}</b> (@{target_username})" if target_username else f"ID: <code>{target_tg_id}</code>"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [make_btn("Adminlar ro'yxatiga qaytish", callback_data="admin_manage_users")],
        [make_btn("Asosiy Menyu", callback_data="main_menu")]
    ])
    await message.answer(f"🎉 <b>Muvaffaqiyatli!</b>\n\n{display_info} administrator etib tayinlandi va to'liq boshqaruv huquqiga ega bo'ldi.", reply_markup=kb)


@dp.callback_query(F.data.startswith("adm_demote_"))
async def admin_demote_callback(callback: CallbackQuery, state: FSMContext = None):
    if not is_owner(callback.from_user.id):
        await callback.answer("🚫 Faqat Bosh Administrator!", show_alert=True)
        return
    demote_id = int(callback.data.split("adm_demote_")[1])
    if demote_id == OWNER_TG_ID:
        await callback.answer("Bosh administratorni o'chirib bo'lmaydi!", show_alert=True)
        return

    ok = await remove_admin(demote_id)
    if ok:
        await callback.answer("✅ Admin roli olib tashlandi!", show_alert=True)
    else:
        await callback.answer("Xatolik yuz berdi.", show_alert=True)
    await admin_manage_users_callback(callback, state)


@dp.callback_query(F.data == "admin_set_sched_time")
async def admin_set_sched_time_callback(callback: CallbackQuery, state: FSMContext = None):
    if state:
        await state.clear()
    if not is_owner(callback.from_user.id):
        await callback.answer("🚫 Faqat Bosh Administrator!", show_alert=True)
        return

    cur_time = await get_setting("check_time", "07:00")
    text = (
        f"{tg_icon('clock')} <b>KUNLIK AVTOMATIK TEKSHIRUV VAQTI</b>\n\n"
        f"Hozirgi belgilangan vaqt: <b>{cur_time}</b> (Toshkent vaqti bilan)\n\n"
        f"Bot har kuni ushbu vaqtda barcha ruxsat berilgan maktab va sinflarni tekshiradi va hisobot tayyorlaydi.\n\n"
        f"<i>Tezkor vaqtlardan birini tanlang yoki o'zingiz kiriting:</i>"
    )

    times = ["05:00", "06:00", "07:00", "08:00"]
    btn_row = []
    for t in times:
        ico = "check" if t == cur_time else "clock"
        btn_row.append(make_btn(t, callback_data=f"set_stime_{t}", emoji=ico))

    kb = InlineKeyboardMarkup(inline_keyboard=[
        btn_row[:2],
        btn_row[2:],
        [make_btn("Boshqa vaqt kiritish (HH:MM)", callback_data="admin_prompt_custom_time", emoji="edit")],
        [make_btn("Sozlamalarga qaytish", callback_data="admin_settings_menu", emoji="settings")]
    ])
    try:
        await callback.message.edit_text(text, reply_markup=kb)
    except TelegramBadRequest:
        pass


@dp.callback_query(F.data.startswith("set_stime_"))
async def admin_set_stime_value_callback(callback: CallbackQuery, state: FSMContext = None):
    if not is_owner(callback.from_user.id):
        await callback.answer("🚫 Faqat Bosh Administrator!", show_alert=True)
        return
    val = callback.data.split("set_stime_")[1]
    await set_setting("check_time", val)
    await callback.answer(f"✅ Tekshiruv vaqti {val} ga o'zgartirildi!", show_alert=True)
    await admin_set_sched_time_callback(callback, state)


@dp.callback_query(F.data == "admin_prompt_custom_time")
async def admin_prompt_custom_time_callback(callback: CallbackQuery, state: FSMContext):
    if not is_owner(callback.from_user.id):
        await callback.answer("🚫 Faqat Bosh Administrator!", show_alert=True)
        return
    await state.set_state(AdminConfigStates.waiting_for_custom_time)
    await callback.message.edit_text(
        f"{tg_icon('edit')} Yangi tekshiruv vaqtini <b>HH:MM</b> formatida kiriting (masalan: <code>06:30</code> yoki <code>07:15</code>):",
        reply_markup=cancel_inline_keyboard()
    )


@dp.message(AdminConfigStates.waiting_for_custom_time)
async def process_custom_time_message(message: Message, state: FSMContext):
    if not is_owner(message.from_user.id):
        await state.clear()
        return
    text = message.text.strip()
    try:
        parts = text.split(":")
        h = int(parts[0])
        m = int(parts[1])
        if not (0 <= h <= 23 and 0 <= m <= 59):
            raise ValueError()
        formatted = f"{h:02d}:{m:02d}"
    except Exception:
        await message.answer(f"{tg_icon('cross')} Noto'g'ri vaqt formati! Iltimos, <code>07:00</code> yoki <code>06:30</code> kabi kiriting:", reply_markup=cancel_inline_keyboard())
        return

    await set_setting("check_time", formatted)
    await state.clear()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [make_btn("Sozlamalarga qaytish", callback_data="admin_settings_menu", emoji="settings")]
    ])
    await message.answer(f"{tg_icon('check')} Tekshiruv vaqti <b>{formatted}</b> ga o'rnatildi!", reply_markup=kb)


@dp.callback_query(F.data == "admin_set_trial_days")
async def admin_set_trial_days_callback(callback: CallbackQuery, state: FSMContext = None):
    if state:
        await state.clear()
    if not is_owner(callback.from_user.id):
        await callback.answer("🚫 Faqat Bosh Administrator!", show_alert=True)
        return

    cur_days = await get_setting("trial_days", "7")
    text = (
        f"{tg_icon('hourglass')} <b>BEPUL SINOV MUDDATI (FREE TRIAL)</b>\n\n"
        f"Hozirgi sinov muddati: <b>{cur_days} kun</b>\n\n"
        f"Yangi maktab yoki yangi sinf qo'shilganda unga avtomatik shu muddatga bepul ruxsat beriladi.\n\n"
        f"<i>Kerakli muddatni tanlang:</i>"
    )

    days_opts = ["3", "5", "7", "14", "30"]
    rows = []
    curr_row = []
    for d in days_opts:
        ico = "check" if d == cur_days else "hourglass"
        curr_row.append(make_btn(f"{d} kun", callback_data=f"set_tdays_{d}", emoji=ico))
        if len(curr_row) == 3:
            rows.append(curr_row)
            curr_row = []
    if curr_row:
        rows.append(curr_row)

    rows.append([make_btn("Boshqa muddat kiritish", callback_data="admin_prompt_custom_trial", emoji="edit")])
    rows.append([make_btn("Sozlamalarga qaytish", callback_data="admin_settings_menu", emoji="settings")])

    try:
        await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
    except TelegramBadRequest:
        pass


@dp.callback_query(F.data.startswith("set_tdays_"))
async def admin_set_tdays_value_callback(callback: CallbackQuery, state: FSMContext = None):
    if not is_owner(callback.from_user.id):
        await callback.answer("🚫 Faqat Bosh Administrator!", show_alert=True)
        return
    val = callback.data.split("set_tdays_")[1]
    await set_setting("trial_days", val)
    await callback.answer(f"✅ Sinov muddati {val} kunga o'zgartirildi!", show_alert=True)
    await admin_set_trial_days_callback(callback, state)


@dp.callback_query(F.data == "admin_prompt_custom_trial")
async def admin_prompt_custom_trial_callback(callback: CallbackQuery, state: FSMContext):
    if not is_owner(callback.from_user.id):
        await callback.answer("🚫 Faqat Bosh Administrator!", show_alert=True)
        return
    await state.set_state(AdminConfigStates.waiting_for_custom_trial)
    await callback.message.edit_text(
        f"{tg_icon('edit')} Yangi sinov muddatini kunlarda butun son sifatida kiriting (masalan: <code>10</code>):",
        reply_markup=cancel_inline_keyboard()
    )


@dp.message(AdminConfigStates.waiting_for_custom_trial)
async def process_custom_trial_message(message: Message, state: FSMContext):
    if not is_owner(message.from_user.id):
        await state.clear()
        return
    text = message.text.strip()
    if not text.isdigit() or int(text) < 1 or int(text) > 365:
        await message.answer(f"{tg_icon('cross')} Iltimos, 1 dan 365 gacha bo'lgan kun sonini kiriting:", reply_markup=cancel_inline_keyboard())
        return

    await set_setting("trial_days", text)
    await state.clear()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [make_btn("Sozlamalarga qaytish", callback_data="admin_settings_menu", emoji="settings")]
    ])
    await message.answer(f"{tg_icon('check')} Bepul sinov muddati <b>{text} kun</b> qilib belgilandi!", reply_markup=kb)


@dp.callback_query(F.data == "admin_sys_info")
async def admin_sys_info_callback(callback: CallbackQuery):
    if not await is_admin_or_owner(callback.from_user.id):
        await callback.answer("🚫 Ruxsat berilmagan!", show_alert=True)
        return

    db_size = "Noma'lum"
    if os.path.exists("database.sqlite3"):
        sz_bytes = os.path.getsize("database.sqlite3")
        db_size = f"{sz_bytes / (1024 * 1024):.2f} MB"

    stats = await get_overall_stats()
    all_schools = await get_all_schools()
    active_logins = await get_all_logins(only_active=True)

    text = (
        f"{tg_icon('system')} <b>Tizim va Server Holati</b>\n\n"
        f"• {tg_icon('db')} Baza: <b>{db_size}</b> | {tg_icon('school')} Maktablar: <b>{len(all_schools or [])} ta</b>\n"
        f"• {tg_icon('users')} Jami: <b>{stats['total']} ta</b> (Faol: <b>{len(active_logins)}</b>)\n"
        f"• {tg_icon('check')} Kirildi: <b>{stats['success']} ({stats['pct']}%)</b> | {tg_icon('cross')} Xato: <b>{stats['fail']}</b>\n"
        f"• {tg_icon('clock')} Vaqt: <b>Asia/Tashkent</b> (Port: <b>8480</b>)"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [make_btn("Yangilash", callback_data="admin_sys_info", emoji="refresh")],
        [make_btn("Sozlamalarga qaytish", callback_data="admin_settings_menu", emoji="settings")]
    ])
    try:
        await callback.message.edit_text(text, reply_markup=kb)
    except TelegramBadRequest:
        pass


# -------------------------------------------------------------------------
# -------------------------------------------------------------------------
# Teacher Login & Password Reset Automation Pipeline (/boost & /teacher)
# -------------------------------------------------------------------------
@dp.callback_query(F.data == "teacher_reset_start")
@dp.message(Command("teacher"))
@dp.message(Command("boost"))
async def teacher_reset_start_handler(event: CallbackQuery | Message, state: FSMContext):
    user_id = event.from_user.id
    if not await is_admin_or_owner(user_id):
        if isinstance(event, CallbackQuery):
            await event.answer("🚫 Bu funksiya faqat adminlar uchun!", show_alert=True)
        else:
            await event.answer("🚫 Bu funksiya faqat adminlar uchun!")
        return

    # Check if credentials passed directly with command (e.g. /boost login pass or /boost login:pass)
    if isinstance(event, Message) and event.text:
        raw_cmd = event.text.strip()
        cmd_parts = raw_cmd.split(maxsplit=1)
        if len(cmd_parts) > 1:
            cmd_args = cmd_parts[1].strip()
            u, p = await extract_teacher_credentials(cmd_args) or (None, None)
            if u and p:
                status_msg = await event.answer(f"{tg_icon('refresh', '⏳')} <i>Login va parol tahlil qilinmoqda...</i>")
                await process_teacher_login_flow(status_msg, state, u, p)
                return

    await state.set_state(TeacherResetStates.waiting_for_creds)
    text = (
        f"{tg_icon('key', '🔑')} <b>O'qituvchi orqali parollarni yangilash (/boost)</b>\n\n"
        "O'qituvchining eMaktab login va parolini yuboring:\n"
        "• <b>Matn ko'rinishida</b> (masalan: <code>login: user parol: pass</code> yoki <code>/boost login parol</code>)\n"
        "• <b>Rasm / Skrinshot</b> (login va parol ko'ringan foto)\n"
        "• <b>Fayl yoki Hujjat</b> (.txt, .docx, .pdf)\n\n"
        f"{tg_icon('bot', '🤖')} <i>AI login ma'lumotlarini avtomatik ajratib oladi va tekshiradi.</i>"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="tchr_cancel")]
    ])
    if isinstance(event, CallbackQuery):
        await event.message.answer(text, reply_markup=kb)
        await event.answer()
    else:
        await event.answer(text, reply_markup=kb)


@dp.callback_query(F.data == "tchr_cancel")
async def teacher_reset_cancel_handler(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ Jarayon bekor qilindi.")
    await callback.answer()


async def process_teacher_login_flow(status_msg: Message, state: FSMContext, u: str, p: str):
    await status_msg.edit_text(
        f"{tg_icon('refresh', '⏳')} <b>eMaktab tizimiga kirilmoqda...</b>\n"
        f"👤 Login: <code>{u}</code>\n"
        "<i>Iltimos kuting, maktab va sinflar tahlil qilinmoqda...</i>"
    )

    resetter = EMaktabResetter()
    try:
        await asyncio.to_thread(resetter.login_teacher, u, p)
        classes = await asyncio.to_thread(resetter.get_teacher_classes_with_counts)
    except Exception as e:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="tchr_cancel")]
        ])
        await status_msg.edit_text(
            f"{tg_icon('cross', '❌')} <b>eMaktab tizimiga kirishda xatolik!</b>\n\n"
            f"⚠️ <b>Sabab:</b> {e}\n"
            "Login yoki parol noto'g'ri bo'lishi mumkin. Qaytadan urinib ko'ring:",
            reply_markup=kb
        )
        return

    if not classes:
        await status_msg.edit_text(
            f"{tg_icon('cross', '⚠️')} <b>eMaktabga kirildi, lekin bu profilga biriktirilgan sinflar topilmadi!</b>\n"
            f"👤 O'qituvchi: <code>{u}</code>\n"
            f"🏫 Maktab: <b>{resetter.school_name}</b>"
        )
        await state.clear()
        return

    await state.update_data(
        teacher_user=u,
        teacher_pass=p,
        school_id=resetter.school_id,
        school_name=resetter.school_name,
        classes=classes,
        selected_class_ids=[]
    )
    await state.set_state(TeacherResetStates.choosing_class)

    kb = make_classes_selection_keyboard(classes, set())
    text = make_classes_selection_text(classes, set(), resetter.school_name, u)
    await status_msg.edit_text(text, reply_markup=kb)


@dp.message(TeacherResetStates.waiting_for_creds, F.text | F.photo | F.document)
async def teacher_reset_creds_handler(message: Message, state: FSMContext):
    status_msg = await message.answer(f"{tg_icon('refresh', '⏳')} <i>Login va parol tahlil qilinmoqda...</i>")
    u, p = None, None

    if message.text:
        u, p = await extract_teacher_credentials(message.text) or (None, None)
    elif message.photo:
        photo = message.photo[-1]
        file_info = await message.bot.get_file(photo.file_id)
        buf = io.BytesIO()
        await message.bot.download_file(file_info.file_path, destination=buf)
        img_bytes = buf.getvalue()

        if message.caption:
            res = await extract_teacher_credentials(message.caption)
            if res:
                u, p = res
        if not u or not p:
            res = await extract_teacher_from_image(img_bytes, mime_type="image/jpeg")
            if res:
                u, p = res
    elif message.document:
        doc = message.document
        file_info = await message.bot.get_file(doc.file_id)
        buf = io.BytesIO()
        await message.bot.download_file(file_info.file_path, destination=buf)
        doc_bytes = buf.getvalue()

        if message.caption:
            res = await extract_teacher_credentials(message.caption)
            if res:
                u, p = res
        if not u or not p:
            res = await extract_teacher_from_doc(doc_bytes, file_name=doc.file_name or "file")
            if res:
                u, p = res

    if not u or not p:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="tchr_cancel")]
        ])
        await status_msg.edit_text(
            f"{tg_icon('cross', '❌')} <b>O'qituvchi login va paroli aniqlanmadi!</b>\n\n"
            "Iltimos, ma'lumotlarni aniq ko'rsatgan holda qaytadan yuboring:",
            reply_markup=kb
        )
        return

    await process_teacher_login_flow(status_msg, state, u, p)


def make_classes_selection_keyboard(classes: list[dict], selected_ids: set[str]) -> InlineKeyboardMarkup:
    rows = []
    row = []
    for c in classes:
        cid = str(c["class_id"])
        is_sel = cid in selected_ids
        mark = "✅ " if is_sel else "▫️ "
        label = c.get("label", c["name"])
        btn_text = f"{mark}{label}"
        row.append(InlineKeyboardButton(text=btn_text, callback_data=f"tchr_tog_{cid}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)

    all_selected = len(selected_ids) == len(classes) and len(classes) > 0
    toggle_all_text = "❌ Barchasini bekor qilish" if all_selected else "⚡️ Barchasini tanlash"
    rows.append([InlineKeyboardButton(text=toggle_all_text, callback_data="tchr_togall")])

    total_people = sum(c.get("total", 0) for c in classes if str(c["class_id"]) in selected_ids)
    if selected_ids:
        if total_people > 0:
            confirm_text = f"➡️ Davom etish ({len(selected_ids)} ta sinf | {total_people} kishi)"
        else:
            confirm_text = f"➡️ Davom etish ({len(selected_ids)} ta sinf)"
    else:
        confirm_text = "➡️ Davom etish"

    rows.append([
        InlineKeyboardButton(text=confirm_text, callback_data="tchr_finish_select")
    ])
    rows.append([
        InlineKeyboardButton(text="❌ Bekor qilish", callback_data="tchr_cancel")
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def make_classes_selection_text(classes: list[dict], selected_ids: set[str], school_name: str, teacher_user: str = "") -> str:
    sel_names = [c.get("label", c["name"]) for c in classes if str(c["class_id"]) in selected_ids]
    total_people = sum(c.get("total", 0) for c in classes if str(c["class_id"]) in selected_ids)
    sel_str = "\n".join([f"• <b>{n}</b>" for n in sel_names]) if sel_names else "<i>hech biri tanlanmagan</i>"
    teacher_line = f"\n{tg_icon('user', '👤')} <b>O'qituvchi:</b> <code>{teacher_user}</code>" if teacher_user else ""
    people_str = f"\n👥 <b>Jami hisoblar:</b> <b>{total_people} ta</b>" if total_people > 0 else ""
    return (
        f"{tg_icon('check', '✅')} <b>O'qituvchi hisobiga muvaffaqiyatli kirildi!</b>\n\n"
        f"{tg_icon('school', '🏫')} <b>Maktab:</b> {school_name}"
        f"{teacher_line}\n"
        f"{tg_icon('books', '📚')} <b>Mavjud sinflar ({len(classes)} ta)</b>\n\n"
        f"📌 <b>Tanlangan sinflar ({len(sel_names)}/{len(classes)}):</b>\n{sel_str}{people_str}\n\n"
        "Tugmalarda: <b>Sinf (o'quvchilar + ota-onalar)=jami</b> ko'rsatilgan.\n"
        "Kerakli sinflarni tanlang va <b>«➡️ Davom etish»</b> tugmasini bosing:"
    )


@dp.callback_query(F.data == "tchr_confirm_no")
async def teacher_confirm_no_handler(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(f"{tg_icon('cross', '❌')} Jarayon bekor qilindi.")
    await callback.answer()


@dp.callback_query(F.data == "tchr_confirm_yes")
async def teacher_confirm_yes_handler(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    classes = data.get("classes", [])
    school_name = data.get("school_name", "Maktab")
    teacher_user = data.get("teacher_user", "")

    if not classes or not any("label" in c for c in classes):
        u = data.get("teacher_user", "toxtasinovafarida")
        p = data.get("teacher_pass", "Farida82")
        resetter = EMaktabResetter()
        try:
            await callback.answer("Sinflar va hisoblar soni olinmoqda...")
            await asyncio.to_thread(resetter.login_teacher, u, p)
            classes = await asyncio.to_thread(resetter.get_teacher_classes_with_counts)
            school_name = resetter.school_name
            teacher_user = u
            await state.update_data(teacher_user=u, teacher_pass=p, school_id=resetter.school_id, school_name=school_name, classes=classes)
        except Exception:
            pass

    if not classes:
        await callback.answer("Sinflar topilmadi! Qaytadan login yuboring.", show_alert=True)
        return

    await state.set_state(TeacherResetStates.choosing_class)
    selected_ids = set(data.get("selected_class_ids", []))
    kb = make_classes_selection_keyboard(classes, selected_ids)
    text = make_classes_selection_text(classes, selected_ids, school_name, teacher_user)
    try:
        await callback.message.edit_text(text, reply_markup=kb)
    except TelegramBadRequest:
        pass
    await callback.answer()


@dp.callback_query(TeacherResetStates.choosing_class, F.data.startswith("tchr_tog_"))
async def teacher_toggle_class_callback(callback: CallbackQuery, state: FSMContext):
    cid = callback.data.replace("tchr_tog_", "")
    data = await state.get_data()
    classes = data.get("classes", [])
    school_name = data.get("school_name", "Maktab")
    teacher_user = data.get("teacher_user", "")
    selected_ids = set(data.get("selected_class_ids", []))

    matched = next((c for c in classes if str(c.get("class_id")) == str(cid)), None)
    if not matched:
        await callback.answer("Sinf topilmadi!", show_alert=True)
        return

    if cid in selected_ids:
        selected_ids.remove(cid)
        alert_text = f"▫️ {matched['name']} olib tashlandi"
    else:
        selected_ids.add(cid)
        alert_text = f"✅ {matched['name']} tanlandi"

    await state.update_data(selected_class_ids=list(selected_ids))

    kb = make_classes_selection_keyboard(classes, selected_ids)
    text = make_classes_selection_text(classes, selected_ids, school_name, teacher_user)

    try:
        await callback.message.edit_text(text, reply_markup=kb)
    except TelegramBadRequest:
        pass
    await callback.answer(alert_text)


@dp.callback_query(TeacherResetStates.choosing_class, F.data == "tchr_togall")
async def teacher_toggle_all_classes_callback(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    classes = data.get("classes", [])
    school_name = data.get("school_name", "Maktab")
    teacher_user = data.get("teacher_user", "")
    selected_ids = set(data.get("selected_class_ids", []))

    if len(selected_ids) == len(classes):
        selected_ids.clear()
        alert_text = "Barcha sinflar bekor qilindi"
    else:
        selected_ids = {str(c["class_id"]) for c in classes}
        alert_text = "Barcha sinflar tanlandi"

    await state.update_data(selected_class_ids=list(selected_ids))

    kb = make_classes_selection_keyboard(classes, selected_ids)
    text = make_classes_selection_text(classes, selected_ids, school_name, teacher_user)

    try:
        await callback.message.edit_text(text, reply_markup=kb)
    except TelegramBadRequest:
        pass
    await callback.answer(alert_text)


def make_mode_selection_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👨‍👩‍👦 Faqat Ota-onalar", callback_data="tchr_mode_parents")],
        [InlineKeyboardButton(text="👨‍🎓 Faqat O'quvchilar", callback_data="tchr_mode_students")],
        [InlineKeyboardButton(text="👥 O'quvchilar va Ota-onalar", callback_data="tchr_mode_both")],
        [InlineKeyboardButton(text="🔙 Orqaga (Sinflar)", callback_data="tchr_back_to_classes")],
        [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="tchr_cancel")]
    ])


def make_mode_selection_text(classes: list[dict], school_name: str, teacher_user: str = "") -> str:
    classes_names = ", ".join([f"<b>{c.get('label', c['name'])}</b>" for c in classes])
    total_people = sum(c.get("total", 0) for c in classes)
    total_students = sum(c.get("students_count", 0) for c in classes)
    total_parents = sum(c.get("parents_count", 0) for c in classes)
    teacher_line = f"\n{tg_icon('user', '👤')} <b>O'qituvchi:</b> <code>{teacher_user}</code>" if teacher_user else ""
    return (
        f"{tg_icon('check', '✅')} <b>Sinflar tanlandi ({len(classes)} ta)</b>\n\n"
        f"{tg_icon('school', '🏫')} <b>Maktab:</b> {school_name}{teacher_line}\n"
        f"{tg_icon('books', '📚')} <b>Tanlangan sinflar:</b> {classes_names}\n"
        f"👥 <b>Jami hisoblar:</b> {total_people} ta (🎓 {total_students} o'quvchi, 👨‍👩‍👦 {total_parents} ota-ona)\n\n"
        "🎯 <b>Kimlarning parolini yangilamoqchisiz?</b>\n"
        "Quyidagi toifalardan birini tanlang:\n\n"
        "• <b>👨‍👩‍👦 Faqat Ota-onalar</b> — faqat ota-onalar (o'qituvchilar mutlaqo hisobga olinmaydi)\n"
        "• <b>👨‍🎓 Faqat O'quvchilar</b> — faqat sinf o'quvchilari\n"
        "• <b>👥 O'quvchilar va Ota-onalar</b> — o'quvchilar va ota-onalar birga (o'qituvchisiz)"
    )


@dp.callback_query(TeacherResetStates.choosing_class, F.data == "tchr_finish_select")
async def teacher_finish_selection_callback(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    classes = data.get("classes", [])
    selected_ids = set(data.get("selected_class_ids", []))

    if not selected_ids:
        await callback.answer("⚠️ Iltimos, kamida bitta sinfni tanlang!", show_alert=True)
        return

    selected_classes = [c for c in classes if str(c.get("class_id")) in selected_ids]
    await state.update_data(selected_classes=selected_classes)
    await state.set_state(TeacherResetStates.choosing_mode)

    text = make_mode_selection_text(selected_classes, data.get("school_name", "Maktab"), data.get("teacher_user", ""))
    kb = make_mode_selection_keyboard()
    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()


@dp.message(TeacherResetStates.choosing_class, F.text)
async def teacher_class_text_handler(message: Message, state: FSMContext):
    data = await state.get_data()
    classes = data.get("classes", [])
    school_name = data.get("school_name", "Maktab")
    selected_ids = set(data.get("selected_class_ids", []))
    raw_text = message.text.strip().lower()

    if raw_text in ["tayyor", "finish", "yakunlash", "next", "bo'ldi", "boldi", "davom"]:
        if not selected_ids:
            await message.answer("⚠️ Iltimos, kamida bitta sinfni tanlang!")
            return
        selected_classes = [c for c in classes if str(c.get("class_id")) in selected_ids]
        await state.update_data(selected_classes=selected_classes)
        await state.set_state(TeacherResetStates.choosing_mode)

        text = make_mode_selection_text(selected_classes, school_name, data.get("teacher_user", ""))
        kb = make_mode_selection_keyboard()
        await message.answer(text, reply_markup=kb)
        return

    if raw_text in ["barchasi", "hammasi", "all"]:
        selected_ids = {str(c["class_id"]) for c in classes}
        await state.update_data(selected_class_ids=list(selected_ids))
        kb = make_classes_selection_keyboard(classes, selected_ids)
        text = make_classes_selection_text(classes, selected_ids, school_name, data.get("teacher_user", ""))
        await message.answer(f"✅ Barcha sinflar tanlandi!\n\n{text}", reply_markup=kb)
        return

    matched = await match_user_class_with_options(message.text, classes)
    if not matched:
        await message.answer(
            f"{tg_icon('cross', '❌')} <b>'{message.text}'</b> sinfi topilmadi.\n\n"
            "Iltimos, yuqoridagi tugmalardan birini bosing yoki sinf nomini to'g'ri yozing."
        )
        return

    cid = str(matched["class_id"])
    if cid in selected_ids:
        selected_ids.remove(cid)
        action_str = f"▫️ <b>{matched['name']}</b> olib tashlandi"
    else:
        selected_ids.add(cid)
        action_str = f"✅ <b>{matched['name']}</b> tanlandi"

    await state.update_data(selected_class_ids=list(selected_ids))
    kb = make_classes_selection_keyboard(classes, selected_ids)
    text = make_classes_selection_text(classes, selected_ids, school_name, data.get("teacher_user", ""))
    await message.answer(f"{action_str}\n\n{text}", reply_markup=kb)


@dp.callback_query(TeacherResetStates.choosing_mode, F.data.startswith("tchr_mode_"))
async def teacher_mode_selection_callback(callback: CallbackQuery, state: FSMContext):
    mode = callback.data.replace("tchr_mode_", "")
    mode_labels = {
        "parents": "👨‍👩‍👦 Faqat Ota-onalar (o'qituvchisiz)",
        "students": "👨‍🎓 Faqat O'quvchilar",
        "both": "👥 O'quvchilar va Ota-onalar (o'qituvchisiz)"
    }
    mode_title = mode_labels.get(mode, "O'quvchilar va Ota-onalar")
    await state.update_data(target_mode=mode, mode_label=mode_title)
    await state.set_state(TeacherResetStates.entering_new_password)

    data = await state.get_data()
    selected_classes = data.get("selected_classes", [])
    classes_str = ", ".join([f"<b>{c['name']}</b>" for c in selected_classes])

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="12345678a (Standart)", callback_data="tchr_pwd_default")],
        [InlineKeyboardButton(text="🔙 Orqaga (Toifa)", callback_data="tchr_back_to_mode")],
        [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="tchr_cancel")]
    ])
    await callback.message.edit_text(
        f"{tg_icon('check', '✅')} <b>Tanlangan toifa:</b> {mode_title}\n"
        f"📚 <b>Sinflar:</b> {classes_str}\n\n"
        f"{tg_icon('lock', '🔐')} Ushbu hisoblar uchun o'rnatiladigan <b>yangi parolni</b> kiriting:\n"
        "<i>(Yoki standart <code>12345678a</code> tugmasini bosing)</i>",
        reply_markup=kb
    )
    await callback.answer()


@dp.message(TeacherResetStates.choosing_mode, F.text)
async def teacher_mode_text_handler(message: Message, state: FSMContext):
    raw = message.text.strip().lower()
    if any(k in raw for k in ["ota", "ona", "parent"]):
        mode = "parents"
    elif any(k in raw for k in ["oquvchi", "o'quvchi", "student"]):
        mode = "students"
    else:
        mode = "both"

    mode_labels = {
        "parents": "👨‍👩‍👦 Faqat Ota-onalar (o'qituvchisiz)",
        "students": "👨‍🎓 Faqat O'quvchilar",
        "both": "👥 O'quvchilar va Ota-onalar (o'qituvchisiz)"
    }
    mode_title = mode_labels.get(mode, "O'quvchilar va Ota-onalar")
    await state.update_data(target_mode=mode, mode_label=mode_title)
    await state.set_state(TeacherResetStates.entering_new_password)

    data = await state.get_data()
    selected_classes = data.get("selected_classes", [])
    classes_str = ", ".join([f"<b>{c['name']}</b>" for c in selected_classes])

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="12345678a (Standart)", callback_data="tchr_pwd_default")],
        [InlineKeyboardButton(text="🔙 Orqaga (Toifa)", callback_data="tchr_back_to_mode")],
        [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="tchr_cancel")]
    ])
    await message.answer(
        f"{tg_icon('check', '✅')} <b>Tanlangan toifa:</b> {mode_title}\n"
        f"📚 <b>Sinflar:</b> {classes_str}\n\n"
        f"{tg_icon('lock', '🔐')} Ushbu hisoblar uchun o'rnatiladigan <b>yangi parolni</b> kiriting:\n"
        "<i>(Yoki standart <code>12345678a</code> tugmasini bosing)</i>",
        reply_markup=kb
    )


@dp.callback_query(TeacherResetStates.entering_new_password, F.data == "tchr_pwd_default")
async def teacher_pwd_default_callback(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await prepare_teacher_review_screen(callback.message, state, "12345678a")


@dp.callback_query(TeacherResetStates.entering_new_password, F.data.startswith("tchr_pwd_quick_"))
async def teacher_pwd_quick_callback(callback: CallbackQuery, state: FSMContext):
    new_pwd = callback.data.replace("tchr_pwd_quick_", "")
    await callback.answer(f"Tanlandi: {new_pwd}")
    await prepare_teacher_review_screen(callback.message, state, new_pwd)


@dp.message(TeacherResetStates.entering_new_password, F.text)
async def teacher_pwd_text_handler(message: Message, state: FSMContext):
    new_pwd = message.text.strip()
    if len(new_pwd) < 6:
        await message.answer(f"{tg_icon('cross', '❌')} Parol kamida 6 ta belgidan iborat bo'lishi kerak. Qaytadan kiriting:")
        return
    await prepare_teacher_review_screen(message, state, new_pwd)


async def prepare_teacher_review_screen(target_message: Message, state: FSMContext, new_pwd: str):
    data = await state.get_data()
    t_user = data["teacher_user"]
    t_pass = data["teacher_pass"]
    s_id = data.get("school_id", "1000006479820")
    s_name = data.get("school_name", "Maktab")
    selected_classes = data.get("selected_classes", [])
    target_mode = data.get("target_mode", "both")
    mode_label = data.get("mode_label", "O'quvchilar va Ota-onalar")

    classes_names = ", ".join([c["name"] for c in selected_classes])

    loading_text = (
        f"{tg_icon('refresh', '⏳')} <b>Tanlangan hisoblar ro'yxati tekshirilmoqda...</b>\n\n"
        f"{tg_icon('school', '🏫')} <b>Maktab:</b> {s_name}\n"
        f"{tg_icon('books', '📚')} <b>Sinflar:</b> {classes_names}\n"
        f"🎯 <b>Toifa:</b> {mode_label}\n\n"
        "<i>Hisoblar loginlari olinmoqda va barcha o'qituvchilar tekshirilib, qat'iy chiqarib tashlanmoqda...</i>"
    )
    if hasattr(target_message, "edit_text"):
        status_msg = target_message
        try:
            await status_msg.edit_text(loading_text)
        except Exception:
            status_msg = await target_message.answer(loading_text)
    else:
        status_msg = await target_message.answer(loading_text)

    def fetch_targets():
        resetter = EMaktabResetter(school_id=s_id)
        resetter.login_teacher(t_user, t_pass)
        resetter.school_name = s_name
        targets = resetter.get_target_accounts(selected_classes, mode=target_mode)
        return resetter, targets

    try:
        resetter, target_accounts = await asyncio.to_thread(fetch_targets)
    except Exception as e:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Orqaga (Toifa)", callback_data="tchr_back_to_mode")],
            [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="tchr_cancel")]
        ])
        await status_msg.edit_text(f"❌ <b>Hisoblarni olishda xatolik:</b> {e}", reply_markup=kb)
        return

    if not target_accounts:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Orqaga (Toifa)", callback_data="tchr_back_to_mode")],
            [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="tchr_cancel")]
        ])
        await status_msg.edit_text(
            f"⚠️ <b>Belgilangan toifa ({mode_label}) bo'yicha hech qanday hisob topilmadi!</b>\n\n"
            "Ushbu sinfda tanlangan toifadagi a'zolar mavjud emas yoki ular o'qituvchi bo'lganligi sababli himoyalanib chiqarib tashlangan.",
            reply_markup=kb
        )
        return

    await state.update_data(
        target_accounts=target_accounts,
        new_password=new_pwd
    )
    await state.set_state(TeacherResetStates.review_confirmation)

    # Format login review list: "just login"
    student_logins = [acc["login"] for acc in target_accounts if acc.get("role") == "student" and acc.get("login")]
    parent_logins = [acc["login"] for acc in target_accounts if acc.get("role") == "parent" and acc.get("login")]
    all_logins = [acc["login"] for acc in target_accounts if acc.get("login")]

    lines = []
    if target_mode == "parents":
        lines.append(f"👨‍👩‍👦 <b>Ota-onalar loginlari ({len(parent_logins)} ta):</b>")
        for idx, lgn in enumerate(parent_logins, 1):
            lines.append(f"{idx}. <code>{lgn}</code>")
    elif target_mode == "students":
        lines.append(f"🎓 <b>O'quvchilar loginlari ({len(student_logins)} ta):</b>")
        for idx, lgn in enumerate(student_logins, 1):
            lines.append(f"{idx}. <code>{lgn}</code>")
    else:
        if student_logins:
            lines.append(f"🎓 <b>O'quvchilar loginlari ({len(student_logins)} ta):</b>")
            for idx, lgn in enumerate(student_logins, 1):
                lines.append(f"{idx}. <code>{lgn}</code>")
        if parent_logins:
            if lines:
                lines.append("")
            lines.append(f"👨‍👩‍👦 <b>Ota-onalar loginlari ({len(parent_logins)} ta):</b>")
            for idx, lgn in enumerate(parent_logins, 1):
                lines.append(f"{idx}. <code>{lgn}</code>")

    header = (
        f"📋 <b>Tasdiqlash: Yangilanadigan loginlar ro'yxati (jami {len(all_logins)} ta hisob)</b>\n\n"
        f"{tg_icon('school', '🏫')} <b>Maktab:</b> {s_name}\n"
        f"{tg_icon('books', '📚')} <b>Sinflar:</b> {classes_names}\n"
        f"🎯 <b>Toifa:</b> {mode_label}\n"
        f"{tg_icon('lock', '🔐')} <b>Yangi parol:</b> <code>{new_pwd}</code>\n\n"
        "👤 <b>Tanlangan hisoblar loginlari:</b>\n"
    )

    footer = (
        f"\n\n🛡 <b>Qat'iy xavfsizlik:</b> Barcha o'qituvchi hisoblari mutlaqo himoyalangan va ro'yxatdan chiqarilgan! O'qituvchilar parollariga mutlaqo tegilmaydi.\n\n"
        f"⚠️ <b>Diqqat:</b> Yuqoridagi <b>{len(all_logins)} ta</b> hisobning barchasiga yangi parol o'rnatiladi.\n"
        f"Parollarni yangilashga rozimisiz?"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Roziman / Tasdiqlayman", callback_data="tchr_final_execute")],
        [InlineKeyboardButton(text="🔙 Orqaga (Toifa)", callback_data="tchr_back_to_mode")],
        [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="tchr_cancel")]
    ])

    full_text = header + "\n".join(lines) + footer
    if len(full_text) <= 3900:
        await status_msg.edit_text(full_text, reply_markup=kb)
    else:
        # Split across clean chunked messages so 100% of logins are shown to the user
        chunk_size = 50
        await status_msg.edit_text(header + f"<i>(Jami {len(all_logins)} ta hisob quyida to'liq ko'rsatiladi):</i>")
        for i in range(0, len(lines), chunk_size):
            chunk = lines[i:i + chunk_size]
            chunk_body = "\n".join(chunk)
            is_last = (i + chunk_size) >= len(lines)
            if not is_last:
                await status_msg.answer(f"📋 <b>Loginlar ro'yxati (davomi {i+1}-{i+len(chunk)}):</b>\n\n{chunk_body}")
            else:
                last_msg = (
                    f"📋 <b>Loginlar ro'yxati ({i+1}-{i+len(chunk)}):</b>\n\n"
                    f"{chunk_body}"
                    f"{footer}"
                )
                await status_msg.answer(last_msg, reply_markup=kb)


@dp.callback_query(TeacherResetStates.review_confirmation, F.data == "tchr_final_execute")
async def teacher_final_execute_callback(callback: CallbackQuery, state: FSMContext):
    await callback.answer("Jarayon boshlanmoqda...")
    data = await state.get_data()
    new_pwd = data.get("new_password", "12345678a")
    await execute_teacher_reset_process(callback.message, state, new_pwd)


@dp.callback_query(F.data == "tchr_back_to_classes")
async def teacher_back_to_classes_callback(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    classes = data.get("classes", [])
    school_name = data.get("school_name", "Maktab")
    teacher_user = data.get("teacher_user", "")
    selected_ids = set(data.get("selected_class_ids", []))

    await state.set_state(TeacherResetStates.choosing_class)
    kb = make_classes_selection_keyboard(classes, selected_ids)
    text = make_classes_selection_text(classes, selected_ids, school_name, teacher_user)
    try:
        await callback.message.edit_text(text, reply_markup=kb)
    except TelegramBadRequest:
        pass
    await callback.answer()


@dp.callback_query(F.data == "tchr_back_to_mode")
async def teacher_back_to_mode_callback(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    selected_classes = data.get("selected_classes", [])
    school_name = data.get("school_name", "Maktab")
    teacher_user = data.get("teacher_user", "")

    await state.set_state(TeacherResetStates.choosing_mode)
    text = make_mode_selection_text(selected_classes, school_name, teacher_user)
    kb = make_mode_selection_keyboard()
    try:
        await callback.message.edit_text(text, reply_markup=kb)
    except TelegramBadRequest:
        pass
    await callback.answer()


async def execute_teacher_reset_process(message: Message, state: FSMContext, new_pwd: str):
    data = await state.get_data()

    t_user = data.get("teacher_user")
    t_pass = data.get("teacher_pass")
    s_id = data.get("school_id", "1000006479820")
    s_name = data.get("school_name", "Maktab")
    target_mode = data.get("target_mode", "both")
    mode_label = data.get("mode_label", "O'quvchilar va Ota-onalar")
    target_accounts = data.get("target_accounts", [])
    selected_classes = data.get("selected_classes", [])

    if not target_accounts and selected_classes:
        resetter_init = EMaktabResetter(school_id=s_id)
        resetter_init.login_teacher(t_user, t_pass)
        target_accounts = resetter_init.get_target_accounts(selected_classes, mode=target_mode)

    if not target_accounts:
        await state.clear()
        await message.answer("❌ Yangilanadigan hisoblar topilmadi.")
        return

    total_classes = len(selected_classes)
    classes_names = ", ".join([c["name"] for c in selected_classes])

    status_msg = await message.answer(
        f"{tg_icon('refresh', '⏳')} <b>Parollarni yangilash boshlandi...</b>\n\n"
        f"{tg_icon('school', '🏫')} <b>Maktab:</b> {s_name}\n"
        f"{tg_icon('books', '📚')} <b>Sinflar:</b> {classes_names}\n"
        f"🎯 <b>Toifa:</b> {mode_label}\n"
        f"{tg_icon('lock', '🔐')} <b>Yangi parol:</b> <code>{new_pwd}</code>\n\n"
        f"<i>Jami {len(target_accounts)} ta hisob qayta ishlanmoqda...</i>"
    )

    last_edit_time = 0
    loop = asyncio.get_running_loop()

    def progress_callback(stats):
        nonlocal last_edit_time
        import time
        now = time.time()
        if now - last_edit_time < 2.5 and not stats.get("is_complete"):
            return
        last_edit_time = now

        text = (
            f"{tg_icon('refresh', '⚡️')} <b>Parollarni yangilash davom etmoqda...</b>\n\n"
            f"{tg_icon('school', '🏫')} <b>Maktab:</b> {s_name}\n"
            f"{tg_icon('books', '📚')} <b>Sinflar:</b> {classes_names}\n"
            f"🎯 <b>Toifa:</b> {mode_label}\n"
            f"👥 <b>Jami hisoblar:</b> {stats['done_accounts']}/{stats['total_accounts']}\n"
            f"🎓 <b>O'quvchilar:</b> {stats['done_students']}/{stats['total_students']}\n"
            f"👨‍👩‍👦 <b>Ota-onalar:</b> {stats['done_parents']}/{stats['total_parents']}\n"
            f"✅ <b>Muvaffaqiyatli:</b> {stats['success_count']} | ❌ <b>Xato:</b> {stats['fail_count']}\n"
            f"🔄 <b>Hozirgi hisob:</b> <code>{stats['current_user']}</code>"
        )
        asyncio.run_coroutine_threadsafe(
            safe_edit_status(status_msg, text),
            loop
        )

    async def safe_edit_status(msg, text):
        try:
            await msg.edit_text(text)
        except Exception:
            pass

    def run_worker():
        resetter = EMaktabResetter(school_id=s_id)
        resetter.login_teacher(t_user, t_pass)
        resetter.school_name = s_name

        stats = resetter.reset_target_accounts(
            target_accounts=target_accounts,
            new_password=new_pwd,
            db_path=DB_PATH,
            progress_callback=progress_callback
        )
        return stats

    try:
        final_stats = await asyncio.to_thread(run_worker)

        # 1. Check if aborted due to eMaktab 3-password history constraint
        if final_stats.get("abort_reason") == "history_error":
            await state.set_state(TeacherResetStates.entering_new_password)
            await state.update_data(
                teacher_user=t_user,
                teacher_pass=t_pass,
                school_id=s_id,
                school_name=s_name,
                target_mode=target_mode,
                mode_label=mode_label,
                target_accounts=target_accounts,
                selected_classes=selected_classes
            )

            abort_kb = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="12345678b", callback_data="tchr_pwd_quick_12345678b"),
                    InlineKeyboardButton(text="12345678c", callback_data="tchr_pwd_quick_12345678c")
                ],
                [
                    InlineKeyboardButton(text="Maktab2026!", callback_data="tchr_pwd_quick_Maktab2026!"),
                    InlineKeyboardButton(text="Emaktab777", callback_data="tchr_pwd_quick_Emaktab777")
                ],
                [InlineKeyboardButton(text="❌ Jarayonni bekor qilish", callback_data="tchr_cancel")]
            ])

            abort_text = (
                f"⚠️ <b>eMaktab parollar tarixi cheklovi aniqlandi!</b>\n\n"
                f"❌ Kiritilgan <code>{new_pwd}</code> paroli ushbu hisoblarda <b>oxirgi 3 marta ishlatilgan parollar</b> ro'yxatida mavjud bo'lgani sababli eMaktab qabul qilmadi.\n\n"
                f"🛡 <b>eMaktab xavfsizlik qoidasi:</b> Oxirgi 3 ta paroldan birini qayta qo'yish taqiqlangan.\n\n"
                f"✍️ <b>Iltimos, boshqa yangi parol kiriting:</b>\n"
                f"<i>(Matn orqali yangi parol yozing yoki yuqoridagi tezkor variantlardan birini bosing)</i>"
            )
            await status_msg.edit_text(abort_text, reply_markup=abort_kb)
            return

        # Success path: clear state
        await state.clear()

        single_grade = selected_classes[0]["name"].replace("-", "").replace(" ", "").upper() if len(selected_classes) == 1 else ""

        if final_stats["success_count"] > 0:
            final_text = (
                f"{tg_icon('check', '🎉')} <b>Parollarni yangilash muvaffaqiyatli yakunlandi!</b>\n\n"
                f"{tg_icon('school', '🏫')} <b>Maktab:</b> {s_name}\n"
                f"{tg_icon('books', '📚')} <b>Sinflar ({total_classes} ta):</b> {classes_names}\n"
                f"🎯 <b>Toifa:</b> {mode_label}\n"
                f"{tg_icon('lock', '🔐')} <b>Yangi parol:</b> <code>{new_pwd}</code>\n\n"
                f"👥 <b>Jami yangilangan hisoblar:</b> <b>{final_stats['success_count']} ta</b>\n"
                f"🎓 <b>O'quvchilar:</b> {final_stats['done_students']}/{final_stats['total_students']}\n"
                f"👨‍👩‍👦 <b>Ota-onalar:</b> {final_stats['done_parents']}/{final_stats['total_parents']}\n"
            )
            if final_stats["fail_count"] > 0:
                final_text += f"❌ <b>Jami xatoliklar:</b> {final_stats['fail_count']} ta\n"
            final_text += (
                f"\n💾 <b>Barcha yangilangan hisoblar ({final_stats['success_count']} ta) bot bazasiga (Logins jadvaliga) to'liq qo'shildi va faollashtirildi!</b>\n"
                "🛡 <i>Barcha o'qituvchi hisoblari mutlaqo tegilmasdan saqlandi!</i>"
            )

            buttons = []
            if single_grade:
                buttons.append([make_btn(f"📋 {single_grade}-sinf barcha login va parollari", callback_data=f"allgrd_1_{single_grade}", emoji="memo")])
            buttons.append([make_btn("🏫 Maktablar bo'limi", callback_data="schools_list", emoji="school")])
            buttons.append([make_btn("Asosiy Menyu", callback_data="main_menu", emoji="back")])

            await status_msg.edit_text(
                final_text,
                reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
            )
        else:
            retry_kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔄 Boshqa parol bilan qayta urinish", callback_data="teacher_reset_start")],
                [InlineKeyboardButton(text="Asosiy Menyu", callback_data="main_menu")]
            ])
            await status_msg.edit_text(
                f"❌ <b>Hech qanday hisobning paroli yangilanmadi!</b>\n\n"
                f"⚠️ <b>Jami xatolar:</b> {final_stats['fail_count']} ta\n"
                "Bunga eMaktab parollar tarixi yoki vaqtinchalik cheklov sabab bo'lgan bo'lishi mumkin.\n\n"
                "Iltimos, boshqa yangi parol bilan qayta urinib ko'ring:",
                reply_markup=retry_kb
            )

    except Exception as e:
        await status_msg.edit_text(f"❌ <b>Jarayonda xatolik yuz berdi:</b> {e}")



# -------------------------------------------------------------------------
# School Creation
# -------------------------------------------------------------------------
@dp.callback_query(F.data == "admin_add_school")
@dp.message(Command("school"))
async def start_add_school(event: Message | CallbackQuery, state: FSMContext):
    user_id = event.from_user.id
    if not await is_admin_or_owner(user_id):
        return
    text = "Maktab raqamini kiriting (masalan: 14):"
    if isinstance(event, Message):
        await event.answer(text, reply_markup=cancel_inline_keyboard())
    else:
        await event.message.answer(text, reply_markup=cancel_inline_keyboard())
        await event.answer()
    await state.set_state(SchoolAdd.school_number)


@dp.message(SchoolAdd.school_number)
async def process_school_number(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Iltimos, faqat raqam kiriting:", reply_markup=cancel_inline_keyboard())
        return
    await state.update_data(school_number=int(message.text))
    await message.answer("Maktab manzilini kiriting (masalan: 14-maktab):", reply_markup=cancel_inline_keyboard())
    await state.set_state(SchoolAdd.school_place)


@dp.message(SchoolAdd.school_place)
async def process_school_place(message: Message, state: FSMContext):
    await state.update_data(school_place=message.text.strip())
    await message.answer("Necha kun amal qilishini kiriting (masalan: 365):", reply_markup=cancel_inline_keyboard())
    await state.set_state(SchoolAdd.days)


@dp.message(SchoolAdd.days)
async def process_school_days(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Iltimos, faqat kunlar sonini (raqam) kiriting:", reply_markup=cancel_inline_keyboard())
        return
    data = await state.get_data()
    await state.clear()

    school = await create_school(
        school_number=data["school_number"],
        place=data["school_place"],
        days=int(message.text)
    )
    me = await bot.get_me()
    invite_url = f"https://t.me/{me.username}?start={school.school_url}"
    await message.answer(
        f"✅ <b>{school.school_number}-maktab</b> muvaffaqiyatli yaratildi!\n\n"
        f"🔗 Qo'shilish havolasi:\n{invite_url}",
        reply_markup=main_inline_keyboard(True, school_id=school.id)
    )


# Single Login Addition Flow (Auto School & Grade Detection)
# -------------------------------------------------------------------------
@dp.callback_query(F.data == "admin_add_login_start")
@dp.message(Command("login"))
async def start_add_login(event: Message | CallbackQuery, state: FSMContext):
    await create_user(tg_id=event.from_user.id)
    text = (
        "🔐 <b>eMaktab loginini kiriting:</b>\n\n"
        "💡 Maktab va sinfni tanlash shart emas — tizim profil orqali avtomatik aniqlaydi!\n\n"
        "Quyidagicha yuborishingiz mumkin:\n"
        "1️⃣ <code>login:parol</code> (masalan: <code>olimjon:12345678</code>)\n"
        "2️⃣ Yoki faqat <code>login</code> yuboring, parol keyin so'raladi.\n"
        "3️⃣ Rasm (skrinshot) yoki ovozli xabar yuborishingiz ham mumkin."
    )
    if isinstance(event, Message):
        await event.answer(text, reply_markup=cancel_inline_keyboard())
    else:
        await event.message.edit_text(text, reply_markup=cancel_inline_keyboard())
        await event.answer()
    await state.set_state(LoginAdd.credentials)


@dp.message(LoginAdd.credentials)
async def login_enter_credentials(message: Message, state: FSMContext):
    text = message.text.strip()
    if ":" in text:
        username, password = text.split(":", 1)
        await state.clear()
        await process_auto_add_login(message, username.strip(), password.strip())
    else:
        await state.update_data(username=text)
        await message.answer(f"<code>{text}</code> uchun parolni kiriting:", reply_markup=cancel_inline_keyboard())
        await state.set_state(LoginAdd.password)


@dp.message(LoginAdd.username)
async def login_enter_user(message: Message, state: FSMContext):
    username = message.text.strip()
    await state.update_data(username=username)
    await message.answer(f"<code>{username}</code> uchun parolni kiriting:", reply_markup=cancel_inline_keyboard())
    await state.set_state(LoginAdd.password)


@dp.message(LoginAdd.password)
async def login_enter_pwd(message: Message, state: FSMContext):
    password = message.text.strip()
    data = await state.get_data()
    await state.clear()
    username = data.get("username", "").strip()
    await process_auto_add_login(message, username, password)


async def process_auto_add_login(message: Message, username: str, password: str):
    msg = await message.answer(f"⏳ <code>{username}</code> tekshirilmoqda va sinf/maktab aniqlanmoqda...")

    detect_res = await auto_detect_login(username, password)
    succ = detect_res.get("success", False)
    cookie = detect_res.get("cookie", "")
    grade = detect_res.get("grade", "1A")
    school_name = detect_res.get("school_name", "14-maktab")
    full_name = detect_res.get("full_name", "")
    school_num = detect_res.get("school_number", 14)

    # Automatically find or create the school in DB!
    target_school = await get_or_create_school_by_number(school_number=school_num, place=school_name)
    school_id = target_school.id

    await create_login(
        username=username,
        password=password,
        last_login=succ,
        cookie=cookie,
        grade=grade,
        school_number_id=school_id,
        tg_id=message.from_user.id
    )

    admin = is_owner(message.from_user.id)
    if succ:
        name_str = f"\n👤 O'quvchi: <b>{full_name}</b>" if full_name else ""
        res_text = (
            f"🎉 <b>{username}</b> muvaffaqiyatli saqlandi va kirdi! ✅\n"
            f"🏫 Maktab: <b>{school_name}</b>\n"
            f"📗 Sinf: <b>{grade}</b>"
            f"{name_str}"
        )
    else:
        res_text = f"⚠️ <b>{username}</b> saqlandi, lekin tizimga kirib bo'lmadi ❌\n(Login yoki parol xato)"

    await msg.edit_text(res_text, reply_markup=main_inline_keyboard(admin, school_id=school_id))


# -------------------------------------------------------------------------
# Batch Add Logins ("add user:pass, user2:pass")
# -------------------------------------------------------------------------
@dp.message(F.text.startswith("add "))
async def batch_add_handler(message: Message):
    user = await create_user(message.from_user.id)
    default_school_id = user.school_id or 1
    raw_items = message.text[4:].split(",")
    valid_entries = []
    for item in raw_items:
        if ":" in item:
            u, p = item.strip().split(":", 1)
            valid_entries.append((u.strip(), p.strip()))

    if not valid_entries:
        await message.answer("Format xato. Masalan: add user1:pass1, user2:pass2", reply_markup=cancel_inline_keyboard())
        return

    msg = await message.answer(f"⏳ {len(valid_entries)} ta login tekshirilmoqda va sinflari aniqlanmoqda...")

    schools = await get_all_schools()
    s_count = 0

    for u, p in valid_entries:
        detect_res = await auto_detect_login(u, p)
        succ = detect_res.get("success", False)
        cookie = detect_res.get("cookie", "")
        grade = detect_res.get("grade", "1A")
        school_num = detect_res.get("school_number", 14)

        target_school = await get_or_create_school_by_number(school_number=school_num, place=f"{school_num}-maktab")
        s_id = target_school.id

        if succ:
            s_count += 1

        await create_login(
            username=u,
            password=p,
            last_login=succ,
            cookie=cookie,
            grade=grade,
            school_number_id=s_id,
            tg_id=message.from_user.id
        )

    admin = is_owner(message.from_user.id)
    await msg.edit_text(
        f"✅ Yakunlandi! Jami: {len(valid_entries)} ta, Kirildi: {s_count} ta, Xato: {len(valid_entries) - s_count} ta.\nSinflar avtomatik aniqlandi va saqlandi.",
        reply_markup=main_inline_keyboard(admin, school_id=default_school_id)
    )


# -------------------------------------------------------------------------
# Role Assignment (Owner Command)
# -------------------------------------------------------------------------
@dp.message(F.text.startswith('/>:)'))
async def give_a_role(message: Message):
    if not is_owner(message.from_user.id):
        return
    try:
        data = message.text.split('_')[1]
        tg_id_str, role = data.split(':')
        tg_id = int(tg_id_str)
    except (IndexError, ValueError):
        await message.reply("Format: />:)_<tg_id>:<role>")
        return

    await create_or_change_user_role(tg_id, role)
    await message.answer(f"👑 Foydalanuvchi {tg_id} {role} roliga o'tkazildi.")


@dp.callback_query(F.data == "noop")
async def noop_callback(callback: CallbackQuery):
    await callback.answer()


# -------------------------------------------------------------------------
# Gemini AI Chat Handler (responds to general questions and messages)
# -------------------------------------------------------------------------
def parse_credentials_from_text(text: str) -> list[tuple[str, str]]:
    """
    Intelligently parses credentials from user messages.
    Supports:
      - login xusanboy
parol 12345
      - login: xusanboy
parol: 12345
      - user:pass, user2:pass2
      - add user:pass
    """
    entries = []
    text_clean = text.strip()
    if text_clean.startswith("add "):
        text_clean = text_clean[4:].strip()

    # Pattern 1: Explicit login ... parol ...
    p_lp = re.findall(r'(?:login|foydalanuvchi|user)?[:\s]*([a-zA-Z0-9._-]+)\s+(?:parol|password|kod|pass)[:\s]*([^\s,;]+)', text_clean, re.IGNORECASE)
    if p_lp:
        for u, p in p_lp:
            if u.lower() not in ('login', 'parol', 'user', 'password') and len(u) >= 3:
                entries.append((u.strip(), p.strip()))
        if entries:
            return entries

    # Pattern 2: user:pass, user2:pass2
    p_colon = re.findall(r'([a-zA-Z0-9._-]+)\s*[:=]\s*([^\s,;]+)', text_clean)
    if p_colon:
        for u, p in p_colon:
            if u.lower() not in ('login', 'parol', 'user', 'password') and len(u) >= 3:
                entries.append((u.strip(), p.strip()))
        if entries:
            return entries

    return entries


async def handle_logins_batch_execution(message: Message, credentials: list[tuple[str, str]]):
    """Processes, verifies on eMaktab, detects grade/school and reports status for one or multiple logins."""
    is_multi = len(credentials) > 1
    wait_text = f"⏳ {len(credentials)} ta login tekshirilmoqda..." if is_multi else f"⏳ <code>{credentials[0][0]}</code> tekshirilmoqda va eMaktabga kirilmoqda..."
    status_msg = await message.answer(wait_text)
    await message.bot.send_chat_action(chat_id=message.chat.id, action=ChatAction.TYPING)

    succ_list = []
    fail_list = []

    for u, p in credentials:
        detect_res = await auto_detect_login(u, p)
        succ = detect_res.get("success", False)
        cookie = detect_res.get("cookie", "")
        grade = detect_res.get("grade", "1A")
        full_name = detect_res.get("full_name", "")
        school_num = detect_res.get("school_number", 14)
        err_msg = detect_res.get("error", "Login yoki parol noto'g'ri")

        if succ:
            target_school = await get_or_create_school_by_number(school_number=school_num, place=f"{school_num}-maktab")
            await ensure_grade_trial(grade)
            await create_login(
                username=u,
                password=p,
                last_login=succ,
                cookie=cookie,
                grade=grade,
                school_number_id=target_school.id,
                tg_id=message.from_user.id
            )
            succ_list.append({
                "username": u,
                "grade": grade,
                "school": school_num,
                "name": full_name or "O'quvchi"
            })
        else:
            fail_list.append({
                "username": u,
                "reason": err_msg
            })

    admin = is_owner(message.from_user.id)

    if not is_multi:
        # Single login detailed report
        if succ_list:
            item = succ_list[0]
            resp_text = (
                f"🎉 <b>Muvaffaqiyatli kirildi!</b> ✅\n\n"
                f"👤 <b>Login:</b> <code>{item['username']}</code>\n"
                f"🏫 <b>Maktab:</b> {item['school']}-maktab\n"
                f"📗 <b>Sinf:</b> {item['grade']}\n"
                f"🎓 <b>O'quvchi:</b> {item['name']}\n\n"
                f"<i>Login bazaga saqlandi va faol holatga keltirildi.</i>"
            )
        else:
            item = fail_list[0]
            resp_text = (
                f"❌ <b>Tizimga kirib bo'lmadi!</b>\n\n"
                f"👤 <b>Login:</b> <code>{item['username']}</code>\n"
                f"⚠️ <b>Sabab:</b> {item['reason']}\n\n"
                f"<i>Iltimos, parol yoki login to'g'ri yozilganini qayta tekshiring.</i>"
            )
    else:
        # Multiple logins report
        lines = [
            f"📊 <b>Natija:</b> Jami: <b>{len(credentials)} ta</b> | ✅ Kirildi: <b>{len(succ_list)} ta</b> | ❌ Xato: <b>{len(fail_list)} ta</b>\n"
        ]
        if succ_list:
            lines.append("<b>✅ Muvaffaqiyatli kirilganlar:</b>")
            for item in succ_list:
                lines.append(f"• <code>{item['username']}</code> — {item['grade']}-sinf ({item['name']})")
        if fail_list:
            lines.append("\n<b>❌ Kirilmaganlar:</b>")
            for item in fail_list:
                lines.append(f"• <code>{item['username']}</code> ({item['reason']})")
        resp_text = "\n".join(lines)

    await status_msg.edit_text(resp_text, reply_markup=main_inline_keyboard(admin))


@dp.stopped_message_generation()
async def stopped_message_generation_handler(event: MessageGenerationStopped):
    draft_id = event.draft_id
    task = active_ai_tasks.pop(draft_id, None)
    if task and not task.done():
        task.cancel()
    try:
        await bot.send_message(
            chat_id=event.chat.id,
            text="⏹️ <i>Javob yaratish to'xtatildi.</i>",
            parse_mode="HTML"
        )
    except Exception:
        pass


@dp.message(F.text & ~F.text.startswith("/"))
async def ai_chat_handler(message: Message, state: FSMContext):
    curr_state = await state.get_state()
    if curr_state:
        return

    # Check if user sent login and password directly in message!
    creds = parse_credentials_from_text(message.text)
    if creds:
        await handle_logins_batch_execution(message, creds)
        return

    # Otherwise, handle via Gemini AI with Mira Thinking indicator & Live Timer
    user_name = message.from_user.full_name or message.from_user.first_name or ""
    await message.bot.send_chat_action(chat_id=message.chat.id, action=ChatAction.TYPING)

    chat_id = message.chat.id
    draft_id = random.randint(100000, 999999)
    think_ico = tg_icon("thinking", "💭")

    # Send visible Mira-style animated Thinking message bubble with custom emoji
    thinking_msg = await message.answer(f"{think_ico} Thinking\n0s", parse_mode="HTML")

    # Also register native Telegram draft if supported
    try:
        await message.bot.send_message_draft(
            chat_id=chat_id,
            draft_id=draft_id,
            text="",
            can_stop=True
        )
    except Exception:
        pass

    start_time = asyncio.get_event_loop().time()
    is_admin = await is_admin_or_owner(message.from_user.id)
    ai_task = asyncio.create_task(ask_gemini(message.text, user_name=user_name, is_admin=is_admin))
    active_ai_tasks[draft_id] = ai_task

    try:
        while not ai_task.done():
            await asyncio.sleep(1)
            if not ai_task.done():
                elapsed = int(asyncio.get_event_loop().time() - start_time)
                try:
                    await thinking_msg.edit_text(f"{think_ico} Thinking\n{elapsed}s", parse_mode="HTML")
                except Exception:
                    pass
                try:
                    await message.bot.send_message_draft(
                        chat_id=chat_id,
                        draft_id=draft_id,
                        text=f"{think_ico} Thinking\n{elapsed}s",
                        parse_mode="HTML",
                        can_stop=True
                    )
                except Exception:
                    pass

        raw_reply = await ai_task
    except asyncio.CancelledError:
        return
    finally:
        active_ai_tasks.pop(draft_id, None)



    styled_reply = render_styled_text(raw_reply)

    try:
        await thinking_msg.edit_text(styled_reply, parse_mode="HTML")
    except Exception:
        try:
            await thinking_msg.edit_text(raw_reply, parse_mode=None)
        except Exception:
            await message.answer(raw_reply, parse_mode=None)



# -------------------------------------------------------------------------
# File / Document / Image to Login Handler (Reads Excel, PDF, Word, TXT, Photos via Gemini AI)
# -------------------------------------------------------------------------
@dp.message(F.photo | F.document)
async def file_or_image_login_handler(message: Message, state: FSMContext):
    bot_obj = message.bot
    file_id = None
    file_name = ""
    mime_type = ""

    if message.photo:
        file_id = message.photo[-1].file_id
        file_name = "photo.jpg"
        mime_type = "image/jpeg"
    elif message.document:
        file_id = message.document.file_id
        file_name = message.document.file_name or "document"
        mime_type = message.document.mime_type or "application/octet-stream"

    if not file_id:
        return

    doc_type_icon = tg_icon("memo", "📄") if message.document else tg_icon("camera", "📸")
    status_msg = await message.answer(
        f"{doc_type_icon} <b>'{file_name}' qabul qilindi!</b>\n"
        f"🤖 Gemini AI yordamida fayl ichidagi barcha o'quvchi login va parollari aniqlanmoqda..."
    )
    await bot_obj.send_chat_action(chat_id=message.chat.id, action=ChatAction.TYPING)

    try:
        # Download file into memory
        file_info = await bot_obj.get_file(file_id)
        buf = io.BytesIO()
        await bot_obj.download_file(file_info.file_path, destination=buf)
        file_bytes = buf.getvalue()

        # Extract logins using AI
        extracted = await extract_logins_from_document(file_bytes, filename=file_name, mime_type=mime_type)

        if not extracted:
            await status_msg.edit_text(
                f"⚠️ <b>'{file_name}' faylida hech qanday login va parol topilmadi.</b>\n\n"
                f"Iltimos, fayl ichida loginlar va parollar aniq ko'rsatilganligini tekshiring "
                f"(masalan: Excel, Word, PDF, TXT yoki skrinshot ko'rinishida)."
            )
            return

        await status_msg.edit_text(
            f"⏳ Faylda <b>{len(extracted)} ta</b> login topildi!\n"
            f"Tizimga ulanib, sinflar va maktablar avtomatik aniqlanmoqda..."
        )

        added_ok = 0
        failed_cnt = 0
        results_summary = []

        for item in extracted:
            u = str(item.get("username", "")).strip()
            p = str(item.get("password", "")).strip()
            if not u or not p:
                continue

            detect_res = await auto_detect_login(u, p)
            succ = detect_res.get("success", False)
            cookie = detect_res.get("cookie", "")
            grade = detect_res.get("grade", "1A")
            full_name = detect_res.get("full_name", "")
            school_num = detect_res.get("school_number", 14)

            if not succ:
                failed_cnt += 1
                results_summary.append(f"• ❌ <code>{u}</code> (kirmadi — bazaga qo'shilmadi)")
                continue

            # Only add to database if successfully authenticated!
            added_ok += 1
            student_desc = full_name if full_name else 'Oquvchi'
            results_summary.append(f"• ✅ <b>{u}</b> ({grade}-sinf, {student_desc})")

            # Auto find or create school
            target_school = await get_or_create_school_by_number(school_number=school_num, place=f"{school_num}-maktab")

            await create_login(
                username=u,
                password=p,
                last_login=True,
                cookie=cookie,
                grade=grade,
                school_number_id=target_school.id,
                tg_id=message.from_user.id
            )

        summary_text = (
            f"🎉 <b>Fayl muvaffaqiyatli qayta ishlandi!</b>\n"
            f"📁 <b>Fayl:</b> <code>{file_name}</code>\n"
            f"📊 <b>Natija:</b> Jami topildi: <b>{len(extracted)} ta</b> | ✅ Qo'shildi: <b>{added_ok} ta</b> | ❌ Xato: <b>{failed_cnt} ta</b>\n\n"
            + "\n".join(results_summary[:25])
        )
        if len(results_summary) > 25:
            summary_text += f"\n<i>... va yana {len(results_summary) - 25} ta login bazaga kiritildi.</i>"

        admin = is_owner(message.from_user.id)
        all_schools = await get_all_schools()
        await status_msg.edit_text(summary_text, reply_markup=main_inline_keyboard(admin, schools=all_schools, is_owner_user=admin))

    except Exception as e:
        print("File processing error:", e)
        await status_msg.edit_text(f"⚠️ Faylni qayta ishlashda xatolik yuz berdi: {e}")



# -------------------------------------------------------------------------
# Voice & Audio Message Handler (Listens, Transcribes & Executes Logins/Answers)
# -------------------------------------------------------------------------
@dp.message(F.voice | F.audio)
async def voice_audio_message_handler(message: Message, state: FSMContext):
    bot_obj = message.bot
    file_id = message.voice.file_id if message.voice else message.audio.file_id
    mime_type = "audio/ogg" if message.voice else (message.audio.mime_type or "audio/mp3")

    status_msg = await message.answer("🎧 Ovozli xabar tinglanmoqda va tahlil qilinmoqda...")
    await bot_obj.send_chat_action(chat_id=message.chat.id, action=ChatAction.TYPING)

    try:
        file_info = await bot_obj.get_file(file_id)
        buf = io.BytesIO()
        await bot_obj.download_file(file_info.file_path, destination=buf)
        audio_bytes = buf.getvalue()

        user_name = message.from_user.full_name or message.from_user.first_name or ""
        is_admin = await is_admin_or_owner(message.from_user.id)
        result = await process_audio_voice(audio_bytes, mime_type=mime_type, user_name=user_name, is_admin=is_admin)

        msg_type = result.get("type", "chat")
        transcript = result.get("transcript", "").strip()

        if msg_type == "credentials" and result.get("logins"):
            creds = [(x["username"], x["password"]) for x in result["logins"] if x.get("username") and x.get("password")]
            if creds:
                prompt_line = f"🗣 <i>«{transcript}»</i>" if transcript else ""
                await status_msg.edit_text(
                    prompt_line + "\n\n⏳ Ovozda login aniqlandi, eMaktabga kirish tekshirilmoqda..."
                )
                await handle_logins_batch_execution(message, creds)
                return

        # If voice contains conversational or command transcript, route to ask_gemini with admin status
        if transcript:
            reply = await ask_gemini(transcript, user_name=user_name, is_admin=is_admin)
        else:
            reply = result.get("reply", "Ovozli xabaringiz tushunildi.")

        styled_reply = render_styled_text(reply)
        trans_header = f"🗣 <i>«{transcript}»</i>\n\n" if transcript else ""

        try:
            await status_msg.edit_text(trans_header + styled_reply)
        except Exception:
            await status_msg.edit_text(trans_header + reply, parse_mode=None)

    except Exception as e:
        print("Voice audio processing error:", e)
        await status_msg.edit_text(f"⚠️ Ovozli xabarni qayta ishlashda xatolik yuz berdi: {e}")


async def main():
    await init()
    await dp.start_polling(bot, skip_updates=True)


if __name__ == '__main__':
    try:
        print('Bot ishga tushdi...')
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print('Bot to‘xtatildi.')
