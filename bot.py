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
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import (
    Message, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove,
    InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo, FSInputFile, CallbackQuery
)
from telegraph import Telegraph
from telegraph.exceptions import RetryAfterError

from database import (
    get_all_logins, create_logins_data, bulk_create_logins_data, create_login, create_user,
    get_all_users, create_school, update_user, add_captcha_id,
    get_free_captcha, get_school_number, create_or_change_user_role,
    init, give_captcha_100, get_all_schools, get_grade, get_logins_grade_for_web,
    get_login_by_id, delete_login, update_login_credentials,
    get_school_stats, get_overall_stats, delete_school,
    get_school_grades, get_class_stats
)
from send_aiohttps_requests import send_request_main
import dns_resolver  # Fast DNS resolution for login.emaktab.uz

OWNER_TG_ID = 6588631008
url = os.getenv('URL', "https://emaktab-2025.onrender.com")
Token = os.getenv('TOKEN', "8301189313:AAEePiO5uaAMA01sbQLOts6TguUaztlbNaw")

bot = Bot(token=Token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

telegraph = Telegraph()
try:
    telegraph.create_account(short_name="emaktab_helper")
except Exception as e:
    print("Telegraph init:", e)


# -------------------------------------------------------------------------
# FSM States
# -------------------------------------------------------------------------
class SchoolAdd(StatesGroup):
    school_number = State()
    school_place = State()
    days = State()


class LoginAdd(StatesGroup):
    school_id = State()
    grade = State()
    username = State()
    password = State()


class EditLoginPwd(StatesGroup):
    login_id = State()
    school_id = State()
    grade = State()
    page = State()
    new_password = State()


# -------------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------------
def is_owner(tg_id: int) -> bool:
    return int(tg_id) == OWNER_TG_ID


def main_reply_keyboard(is_admin: bool) -> ReplyKeyboardMarkup:
    if is_admin:
        return ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="🏫 Maktablar"), KeyboardButton(text="📊 To'liq Hisobot")],
                [KeyboardButton(text="🔄 Hozir tekshirish (/all)"), KeyboardButton(text="➕ Maktab qo'shish")],
                [KeyboardButton(text="➕ Login qo'shish"), KeyboardButton(text="💾 DB Backup")]
            ],
            resize_keyboard=True
        )
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🏫 Maktablar"), KeyboardButton(text="📊 Statistika")],
            [KeyboardButton(text="➕ Login qo'shish"), KeyboardButton(text="ℹ️ Yordam")]
        ],
        resize_keyboard=True
    )


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
    return InlineKeyboardMarkup(inline_keyboard=rows)


# -------------------------------------------------------------------------
# Telegraph Helper (Preserved)
# -------------------------------------------------------------------------
async def create_page_safe(telegraph_instance, title, content):
    while True:
        try:
            return await asyncio.to_thread(
                telegraph_instance.create_page,
                title=title,
                author_name='eMaktab',
                html_content=content
            )
        except RetryAfterError as e:
            await asyncio.sleep(e.retry_after)
        except Exception as e:
            print(f"Telegraph error: {e}")
            return {"url": ""}


# -------------------------------------------------------------------------
# /start Command Handler
# -------------------------------------------------------------------------
@dp.message(CommandStart())
async def start_handler(message: Message, command: CommandStart, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    user = await create_user(
        tg_id=user_id,
        first_name=message.from_user.first_name or "",
        username=message.from_user.username or ""
    )
    admin = is_owner(user_id) or (user and user.role in ("owner", "admin"))

    payload = command.args
    if payload:
        # Deep links e.g. school link
        if payload == 'owner':
            users = await get_all_users()
            for u in users:
                if u.role in ('supporter', 'owner') or u.tg_id == OWNER_TG_ID:
                    try:
                        await bot.send_message(
                            chat_id=u.tg_id,
                            text=f'👤 <a href="tg://user?id={user_id}">Foydalanuvchi</a> maktab yaratishni so‘ramoqda.'
                        )
                    except Exception:
                        pass
            await message.answer("Siz bilan tez orada administratorlar aloqaga chiqishadi.")
            return

        if payload == 'clear':
            await message.answer("Bosh menyu:", reply_markup=main_reply_keyboard(admin))
            return

        # School invite URL join
        school_joined = await update_user(user_id, payload)
        if school_joined:
            await message.answer(
                f"✅ Siz <b>{school_joined.place}</b> dagi <b>{school_joined.school_number}-maktab</b>ga ulandingiz!",
                reply_markup=main_reply_keyboard(admin)
            )
            return

    greeting = (
        f"👑 <b>Xush kelibsiz, Bosh Administrator!</b>\n\n"
        f"Tizim to'liq nazoratingiz ostida. Quyidagi tugmalar orqali maktablar, sinflar, loginlar "
        f"va parollarni boshqarishingiz, kunlik hisobotlarni ko'rishingiz mumkin."
    ) if admin else (
        f"👋 <b>Assalomu alaykum, {message.from_user.first_name}!</b>\n\n"
        f"eMaktab avtomatlashtirish botiga xush kelibsiz.\n"
        f"Quyidagi menyu orqali maktablar statistikasini kuzatishingiz mumkin."
    )

    await message.answer(greeting, reply_markup=main_reply_keyboard(admin))


# -------------------------------------------------------------------------
# Schools Listing & Inspection
# -------------------------------------------------------------------------
@dp.message(F.text == "🏫 Maktablar")
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
        btn_text = f"🏫 {s.school_number}-maktab ({s.place})"
        buttons.append([InlineKeyboardButton(text=btn_text, callback_data=f"view_sch_{s.id}")])

    if admin:
        buttons.append([InlineKeyboardButton(text="➕ Yangi maktab qo'shish", callback_data="admin_add_school")])

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
        btn_text = f"🏫 {s.school_number}-maktab ({s.place})"
        buttons.append([InlineKeyboardButton(text=btn_text, callback_data=f"view_sch_{s.id}")])

    if admin:
        buttons.append([InlineKeyboardButton(text="➕ Yangi maktab qo'shish", callback_data="admin_add_school")])

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
    admin = is_owner(callback.from_user.id)

    total = stats["total"]
    success = stats["success"]
    fail = stats["fail"]
    pct = stats["pct"]
    fail_pct = round(100.0 - pct, 1) if total > 0 else 0.0

    lines = [
        f"🏫 <b>{school.school_number}-maktab</b> ({school.place})",
        f"📅 Muddati: {school.expire_at.strftime('%d.%m.%Y') if school.expire_at else 'Muddatsiz'}",
        "",
        f"📊 <b>Umumiy ko'rsatkichlar:</b>",
        f"• 👥 Jami loginlar: <b>{total} ta</b>",
        f"• ✅ Muvaffaqiyatli kirilgan: <b>{success} ta ({pct}%)</b>",
        f"• ❌ Kirilmagan (xato): <b>{fail} ta ({fail_pct}%)</b>",
        ""
    ]

    if grades:
        lines.append("📚 <b>Sinflar kesimida:</b>")
        for g in grades:
            cstats = await get_class_stats(school_id, g)
            c_tot = cstats["total"]
            c_succ = cstats["success"]
            c_pct = cstats["pct"]
            status_ico = "🟢" if c_pct == 100.0 else ("🟡" if c_pct >= 50.0 else "🔴")
            lines.append(f"• {status_ico} <b>{g}-sinf:</b> {c_tot} ta login | ✅ {c_succ} ta ({c_pct}%)")
    else:
        lines.append("<i>Ushbu maktabda hali sinflar/loginlar mavjud emas.</i>")

    keyboard_rows = []
    if admin:
        keyboard_rows.append([
            InlineKeyboardButton(text="🔍 Sinflar va Loginlar (Boshqarish)", callback_data=f"asch_gr_{school_id}")
        ])
        keyboard_rows.append([
            InlineKeyboardButton(text="🔄 Qayta tekshirish", callback_data=f"asch_chk_{school_id}"),
            InlineKeyboardButton(text="🗑 Maktabni o'chirish", callback_data=f"cdel_sch_{school_id}")
        ])

    keyboard_rows.append([
        InlineKeyboardButton(text="🔄 Yangilash", callback_data=f"view_sch_{school_id}"),
        InlineKeyboardButton(text="🔙 Maktablar ro'yxati", callback_data="list_schools")
    ])

    try:
        await callback.message.edit_text(
            "\n".join(lines),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard_rows)
        )
    except TelegramBadRequest:
        pass


# -------------------------------------------------------------------------
# Owner: School Grades Inspection & Management
# -------------------------------------------------------------------------
@dp.callback_query(F.data.startswith("asch_gr_"))
async def admin_school_grades_callback(callback: CallbackQuery):
    if not is_owner(callback.from_user.id):
        await callback.answer("🚫 Ruxsat berilmagan!", show_alert=True)
        return

    school_id = int(callback.data.split("asch_gr_")[1])
    school = await get_school_number(id=school_id)
    grades = await get_school_grades(school_id)

    if not grades:
        await callback.answer("Ushbu maktabda hech qanday sinf topilmadi.", show_alert=True)
        return

    text = (
        f"🏫 <b>{school.school_number}-maktab sinflari:</b>\n"
        f"<i>Login va parollarni ko'rish, tahrirlash yoki o'chirish uchun sinfni tanlang:</i>"
    )

    rows = []
    current_row = []
    for g in grades:
        cstats = await get_class_stats(school_id, g)
        btn_text = f"📚 {g} ({cstats['total']} ta)"
        current_row.append(InlineKeyboardButton(text=btn_text, callback_data=f"agrd_{school_id}_{g}_1"))
        if len(current_row) == 2:
            rows.append(current_row)
            current_row = []
    if current_row:
        rows.append(current_row)

    rows.append([InlineKeyboardButton(text="🔙 Maktabga qaytish", callback_data=f"view_sch_{school_id}")])

    try:
        await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
    except TelegramBadRequest:
        pass


@dp.callback_query(F.data.startswith("agrd_"))
async def admin_grade_logins_callback(callback: CallbackQuery):
    if not is_owner(callback.from_user.id):
        await callback.answer("🚫 Ruxsat berilmagan!", show_alert=True)
        return

    # format: agrd_{school_id}_{grade}_{page}
    parts = callback.data.split("_")
    school_id = int(parts[1])
    grade = parts[2]
    page = int(parts[3])

    school = await get_school_number(id=school_id)
    all_logins_in_grade = await get_all_logins(school2=school_id, grade=grade)

    if not all_logins_in_grade:
        await callback.answer("Ushbu sinfda loginlar topilmadi.", show_alert=True)
        return

    page_size = 6
    total_pages = (len(all_logins_in_grade) + page_size - 1) // page_size
    page = max(1, min(page, total_pages))

    start_idx = (page - 1) * page_size
    current_page_logins = all_logins_in_grade[start_idx:start_idx + page_size]

    text_lines = [
        f"🏫 <b>{school.school_number}-maktab</b> | 📚 <b>{grade}-sinf</b>",
        f"👥 Jami o'quvchilar: <b>{len(all_logins_in_grade)} ta</b>",
        f"📄 Sahifa: <b>{page}/{total_pages}</b>",
        "",
        "<i>Boshqarish (parolni ko'rish, o'zgartirish, test qilish) uchun o'quvchini tanlang:</i>"
    ]

    rows = []
    for l in current_page_logins:
        status_ico = "✅" if l.last_login else "❌"
        rows.append([
            InlineKeyboardButton(
                text=f"{status_ico} {l.username}",
                callback_data=f"vlog_{l.id}_{school_id}_{grade}_{page}"
            )
        ])

    nav_row = []
    if page > 1:
        nav_row.append(InlineKeyboardButton(text="⬅️ Oldingi", callback_data=f"agrd_{school_id}_{grade}_{page - 1}"))
    nav_row.append(InlineKeyboardButton(text=f"• {page}/{total_pages} •", callback_data="noop"))
    if page < total_pages:
        nav_row.append(InlineKeyboardButton(text="Keyingi ➡️", callback_data=f"agrd_{school_id}_{grade}_{page + 1}"))
    if nav_row:
        rows.append(nav_row)

    rows.append([
        InlineKeyboardButton(text="🔙 Sinflarga qaytish", callback_data=f"asch_gr_{school_id}"),
        InlineKeyboardButton(text="🏫 Maktabga", callback_data=f"view_sch_{school_id}")
    ])

    try:
        await callback.message.edit_text(
            "\n".join(text_lines),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows)
        )
    except TelegramBadRequest:
        pass


# -------------------------------------------------------------------------
# Owner: Single Login Inspection & Actions (View, Edit, Test, Delete)
# -------------------------------------------------------------------------
@dp.callback_query(F.data.startswith("vlog_"))
async def admin_view_single_login_callback(callback: CallbackQuery):
    if not is_owner(callback.from_user.id):
        await callback.answer("🚫 Ruxsat berilmagan!", show_alert=True)
        return

    # format: vlog_{login_id}_{school_id}_{grade}_{page}
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
    status_str = "✅ Muvaffaqiyatli kirilgan" if login_obj.last_login else "❌ Kirilmagan (xato)"
    upd_time = login_obj.updated_at.strftime("%d.%m.%Y %H:%M") if login_obj.updated_at else "Ma'lumot yo'q"

    text = (
        f"👤 <b>O'quvchi hisob ma'lumotlari:</b>\n\n"
        f"🏫 <b>Maktab:</b> {school_name}\n"
        f"📚 <b>Sinf:</b> {login_obj.grade}\n"
        f"👤 <b>Login:</b> <code>{login_obj.username}</code>\n"
        f"🔑 <b>Parol:</b> <code>{login_obj.password}</code>\n"
        f"📌 <b>Holat:</b> {status_str}\n"
        f"⏰ <b>So'nggi yangilanish:</b> {upd_time}\n"
    )

    rows = [
        [
            InlineKeyboardButton(text="✏️ Parolni o'zgartirish", callback_data=f"epwd_{login_id}_{school_id}_{grade}_{page}"),
            InlineKeyboardButton(text="🔄 Kirishni tekshirish", callback_data=f"tlog_{login_id}_{school_id}_{grade}_{page}")
        ],
        [
            InlineKeyboardButton(text="🗑 Loginni o'chirish", callback_data=f"cdlog_{login_id}_{school_id}_{grade}_{page}")
        ],
        [
            InlineKeyboardButton(text="🔙 Sinf ro'yxatiga qaytish", callback_data=f"agrd_{school_id}_{grade}_{page}")
        ]
    ]

    try:
        await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
    except TelegramBadRequest:
        pass


@dp.callback_query(F.data.startswith("tlog_"))
async def admin_test_single_login_callback(callback: CallbackQuery):
    if not is_owner(callback.from_user.id):
        await callback.answer("🚫 Ruxsat berilmagan!", show_alert=True)
        return

    # format: tlog_{login_id}_{school_id}_{grade}_{page}
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

    # Test login live
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

    # Re-fetch from DB
    updated_login = await get_login_by_id(login_id)
    school = await get_school_number(id=school_id)
    status_str = "✅ Muvaffaqiyatli kirildi!" if succ else "❌ Kirib bo'lmadi (parol yoki login xato)!"

    text = (
        f"👤 <b>Tekshiruv natijasi:</b>\n\n"
        f"👤 <b>Login:</b> <code>{updated_login.username}</code>\n"
        f"🔑 <b>Parol:</b> <code>{updated_login.password}</code>\n"
        f"📌 <b>Natija:</b> {status_str}\n"
    )

    rows = [
        [
            InlineKeyboardButton(text="✏️ Parolni o'zgartirish", callback_data=f"epwd_{login_id}_{school_id}_{grade}_{page}"),
            InlineKeyboardButton(text="🔄 Qayta tekshirish", callback_data=f"tlog_{login_id}_{school_id}_{grade}_{page}")
        ],
        [
            InlineKeyboardButton(text="🗑 Loginni o'chirish", callback_data=f"cdlog_{login_id}_{school_id}_{grade}_{page}")
        ],
        [
            InlineKeyboardButton(text="🔙 Sinf ro'yxatiga qaytish", callback_data=f"agrd_{school_id}_{grade}_{page}")
        ]
    ]

    try:
        await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
    except TelegramBadRequest:
        pass


@dp.callback_query(F.data.startswith("epwd_"))
async def admin_edit_pwd_prompt_callback(callback: CallbackQuery, state: FSMContext):
    if not is_owner(callback.from_user.id):
        await callback.answer("🚫 Ruxsat berilmagan!", show_alert=True)
        return

    # format: epwd_{login_id}_{school_id}_{grade}_{page}
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
        f"✏️ <b>{login_obj.username}</b> uchun yangi parolni kiriting:\n\n"
        f"<i>(Bekor qilish uchun 'Bekor qilish' deb yozing)</i>"
    )
    await callback.answer()


@dp.message(EditLoginPwd.new_password)
async def admin_save_new_pwd(message: Message, state: FSMContext):
    if not is_owner(message.from_user.id):
        await state.clear()
        return

    new_pwd = message.text.strip()
    data = await state.get_data()
    await state.clear()

    if new_pwd.lower() in ("bekor qilish", "cancel", "/cancel"):
        await message.answer("Amal bekor qilindi.", reply_markup=main_reply_keyboard(True))
        return

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
        await message.answer("❌ Parolni yangilashda xatolik yuz berdi.", reply_markup=main_reply_keyboard(True))


@dp.callback_query(F.data.startswith("cdlog_"))
async def admin_confirm_delete_login_callback(callback: CallbackQuery):
    if not is_owner(callback.from_user.id):
        await callback.answer("🚫 Ruxsat berilmagan!", show_alert=True)
        return

    # format: cdlog_{login_id}_{school_id}_{grade}_{page}
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
        f"⚠️ <b>DIQQAT!</b>\n\n"
        f"Haqiqatan ham <code>{login_obj.username}</code> loginini butunlay o'chirmoqchimisiz?"
    )

    rows = [
        [
            InlineKeyboardButton(text="🗑 Ha, o'chirish", callback_data=f"dolog_{login_id}_{school_id}_{grade}_{page}"),
            InlineKeyboardButton(text="❌ Bekor qilish", callback_data=f"vlog_{login_id}_{school_id}_{grade}_{page}")
        ]
    ]

    try:
        await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
    except TelegramBadRequest:
        pass


@dp.callback_query(F.data.startswith("dolog_"))
async def admin_do_delete_login_callback(callback: CallbackQuery):
    if not is_owner(callback.from_user.id):
        await callback.answer("🚫 Ruxsat berilmagan!", show_alert=True)
        return

    # format: dolog_{login_id}_{school_id}_{grade}_{page}
    parts = callback.data.split("_")
    login_id = int(parts[1])
    school_id = int(parts[2])
    grade = parts[3]
    page = int(parts[4])

    await delete_login(login_id)
    await callback.answer("🗑 Login muvaffaqiyatli o'chirildi!", show_alert=True)

    # Return to grade logins
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
        f"⚠️ <b>DIQQAT! MAKTABNI O'CHIRISH!</b>\n\n"
        f"Haqiqatan ham <b>{school.school_number}-maktab</b>ni va unga tegishli barcha loginlarni o'chirmoqchimisiz?\n"
        f"Bu amalni ortga qaytarib bo'lmaydi!"
    )
    rows = [
        [
            InlineKeyboardButton(text="🗑 Ha, butunlay o'chirilsin", callback_data=f"dodel_sch_{school_id}"),
            InlineKeyboardButton(text="❌ Bekor qilish", callback_data=f"view_sch_{school_id}")
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
    await callback.answer("🗑 Maktab va uning barcha loginlari o'chirildi!", show_alert=True)
    await list_schools_callback(callback)


# -------------------------------------------------------------------------
# Owner: Re-check Specific School
# -------------------------------------------------------------------------
@dp.callback_query(F.data.startswith("asch_chk_"))
async def admin_check_school_callback(callback: CallbackQuery):
    if not is_owner(callback.from_user.id):
        await callback.answer("🚫 Ruxsat berilmagan!", show_alert=True)
        return

    school_id = int(callback.data.split("asch_chk_")[1])
    school = await get_school_number(id=school_id)
    logins = await get_all_logins(school2=school_id)

    if not logins:
        await callback.answer("Ushbu maktabda tekshirish uchun loginlar yo'q.", show_alert=True)
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

    # Re-render school page
    callback.data = f"view_sch_{school_id}"
    await view_school_callback(callback)


# -------------------------------------------------------------------------
# Overall Statistics & Daily Report Builder
# -------------------------------------------------------------------------
async def generate_overall_report_content():
    stats = await get_overall_stats()
    total = stats["total"]
    success = stats["success"]
    fail = stats["fail"]
    pct = stats["pct"]
    fail_pct = round(100.0 - pct, 1) if total > 0 else 0.0

    today_str = datetime.now(ZoneInfo("Asia/Tashkent")).strftime("%d.%m.%Y %H:%M")

    lines = [
        f"📊 <b>EMAKTAB TIZIMI HISOBOTI</b>",
        f"📅 Sana: <b>{today_str}</b>",
        "",
        f"📈 <b>Umumiy ko'rsatkichlar:</b>",
        f"• 👥 Jami loginlar: <b>{total} ta</b>",
        f"• ✅ Muvaffaqiyatli kirilgan: <b>{success} ta ({pct}%)</b>",
        f"• ❌ Kirilmagan (xatolik): <b>{fail} ta ({fail_pct}%)</b>",
        "",
        f"🏫 <b>Maktablar kesimida statistika:</b>"
    ]

    inline_buttons = []

    for s_info in stats["schools"]:
        s = s_info["school"]
        s_tot = s_info["total"]
        s_succ = s_info["success"]
        s_fail = s_info["fail"]
        s_pct = s_info["pct"]
        s_fail_pct = round(100.0 - s_pct, 1) if s_tot > 0 else 0.0

        status_ico = "🟢" if s_pct == 100.0 else ("🟡" if s_pct >= 50.0 else "🔴")
        lines.append(
            f"• {status_ico} <b>{s.school_number}-maktab</b> ({s.place}):\n"
            f"   Jami: {s_tot} ta | ✅ {s_succ} ({s_pct}%) | ❌ {s_fail} ({s_fail_pct}%)"
        )
        inline_buttons.append([
            InlineKeyboardButton(
                text=f"🏫 {s.school_number}-maktabni ko'rish ({s_pct}%)",
                callback_data=f"view_sch_{s.id}"
            )
        ])

    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=inline_buttons)


@dp.message(F.text.in_({"📊 Statistika", "📊 To'liq Hisobot"}))
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


async def send_json():
    print("Avtomatik tekshiruv boshlandi...")
    await login_schedule()
    await send_daily_report_to_owner()


# -------------------------------------------------------------------------
# Owner: Run All Re-check (/all)
# -------------------------------------------------------------------------
async def login_schedule(user_id: int | None = None):
    all_logins = await get_all_logins()
    if not all_logins:
        print("Bazada loginlar mavjud emas.")
        return

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


@dp.message(F.text.in_({"/all", "🔄 Hozir tekshirish (/all)"}))
async def all_logins_handler(message: Message):
    if not is_owner(message.from_user.id):
        # Allow running, but notify
        pass
    msg = await message.answer("⏳ Barcha maktablar loginlarini tekshirish boshlandi...")
    await login_schedule(message.from_user.id)
    report_text, markup = await generate_overall_report_content()
    await msg.edit_text(f"✅ <b>Tekshiruv yakunlandi!</b>\n\n{report_text}", reply_markup=markup)


# -------------------------------------------------------------------------
# Owner: DB Backup Command
# -------------------------------------------------------------------------
@dp.message(F.text.in_({"💾 DB Backup", "/backup"}))
async def db_backup_handler(message: Message):
    if not is_owner(message.from_user.id):
        await message.answer("🚫 Bu amal faqat Bosh Administrator uchun.")
        return
    if os.path.exists("database.sqlite3"):
        doc = FSInputFile("database.sqlite3")
        await message.answer_document(doc, caption="💾 SQLite ma'lumotlar bazasi nusxasi")
    else:
        await message.answer("Ma'lumotlar bazasi fayli topilmadi.")


# -------------------------------------------------------------------------
# School Creation
# -------------------------------------------------------------------------
@dp.message(F.text.in_({"➕ Maktab qo'shish", "/school"}))
async def start_add_school(message: Message, state: FSMContext):
    if not is_owner(message.from_user.id):
        await message.answer("🚫 Maktab qo'shish faqat Bosh Administrator uchun.")
        return
    await message.answer(
        "Maktab raqamini kiriting (masalan: 24):",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="Menuga qaytish")]],
            resize_keyboard=True
        )
    )
    await state.set_state(SchoolAdd.school_number)


@dp.callback_query(F.data == "admin_add_school")
async def start_add_school_callback(callback: CallbackQuery, state: FSMContext):
    if not is_owner(callback.from_user.id):
        await callback.answer("🚫 Ruxsat berilmagan!", show_alert=True)
        return
    await callback.message.answer(
        "Maktab raqamini kiriting (masalan: 24):",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="Menuga qaytish")]],
            resize_keyboard=True
        )
    )
    await state.set_state(SchoolAdd.school_number)
    await callback.answer()


@dp.message(SchoolAdd.school_number)
async def process_school_number(message: Message, state: FSMContext):
    if message.text == "Menuga qaytish":
        await state.clear()
        await message.answer("Bekor qilindi.", reply_markup=main_reply_keyboard(True))
        return
    if not message.text.isdigit():
        await message.answer("Iltimos, faqat raqam kiriting:")
        return
    await state.update_data(school_number=int(message.text))
    await message.answer("Maktab manzilini kiriting (masalan: Toshkent shahar):")
    await state.set_state(SchoolAdd.school_place)


@dp.message(SchoolAdd.school_place)
async def process_school_place(message: Message, state: FSMContext):
    if message.text == "Menuga qaytish":
        await state.clear()
        await message.answer("Bekor qilindi.", reply_markup=main_reply_keyboard(True))
        return
    await state.update_data(school_place=message.text.strip())
    await message.answer("Necha kun amal qilishini kiriting (masalan: 365):")
    await state.set_state(SchoolAdd.days)


@dp.message(SchoolAdd.days)
async def process_school_days(message: Message, state: FSMContext):
    if message.text == "Menuga qaytish":
        await state.clear()
        await message.answer("Bekor qilindi.", reply_markup=main_reply_keyboard(True))
        return
    if not message.text.isdigit():
        await message.answer("Iltimos, faqat kunlar sonini (raqam) kiriting:")
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
        reply_markup=main_reply_keyboard(True)
    )


# -------------------------------------------------------------------------
# Single Login Addition Flow
# -------------------------------------------------------------------------
@dp.message(F.text.in_({"➕ Login qo'shish", "/login"}))
async def start_add_login(message: Message, state: FSMContext):
    user = await create_user(tg_id=message.from_user.id)
    schools = await get_all_schools()
    if not schools:
        await message.answer("Avval maktab yaratilishi kerak.")
        return

    # Choose school
    buttons = [[InlineKeyboardButton(text=f"🏫 {s.school_number}-maktab ({s.place})", callback_data=f"sel_sch_{s.id}")] for s in schools]
    await message.answer("Login qo'shiladigan maktabni tanlang:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await state.set_state(LoginAdd.school_id)


@dp.callback_query(LoginAdd.school_id, F.data.startswith("sel_sch_"))
async def login_choose_school(callback: CallbackQuery, state: FSMContext):
    school_id = int(callback.data.split("sel_sch_")[1])
    await state.update_data(school_id=school_id)
    await callback.message.edit_text("Sinfni tanlang:", reply_markup=grades_button(1))
    await state.set_state(LoginAdd.grade)


@dp.callback_query(LoginAdd.grade, F.data.startswith("selgrade_"))
async def login_choose_grade(callback: CallbackQuery, state: FSMContext):
    grade = callback.data.split("selgrade_")[1]
    await state.update_data(grade=grade)
    await callback.message.edit_text(f"Tanlangan sinf: <b>{grade}</b>\n\nFoydalanuvchi loginini kiriting:\n(Masalan: xusanboyabdulxayev)")
    await state.set_state(LoginAdd.username)


@dp.callback_query(LoginAdd.grade, F.data.startswith("gpage_"))
async def login_grade_page(callback: CallbackQuery):
    p = int(callback.data.split("gpage_")[1])
    try:
        await callback.message.edit_reply_markup(reply_markup=grades_button(p))
    except TelegramBadRequest:
        pass


@dp.message(LoginAdd.username)
async def login_enter_user(message: Message, state: FSMContext):
    username = message.text.strip()
    await state.update_data(username=username)
    await message.answer(f"<code>{username}</code> uchun parolni kiriting:")
    await state.set_state(LoginAdd.password)


@dp.message(LoginAdd.password)
async def login_enter_pwd(message: Message, state: FSMContext):
    password = message.text.strip()
    data = await state.get_data()
    await state.clear()

    school_id = data.get("school_id")
    grade = data.get("grade")
    username = data.get("username")

    msg = await message.answer(f"⏳ <code>{username}</code> tekshirilmoqda...")

    payload = {
        "1": {
            "username": username,
            "password": password,
            "last_login": False,
            "last_cookie": "",
            "tg_id": message.from_user.id,
            "grade": grade,
            "school_id": school_id
        }
    }
    res = await send_request_main(payload)
    succ = res.get("1", {}).get("last_login", False)
    cookie = res.get("1", {}).get("last_cookie", "")

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
        await msg.edit_text(f"🎉 <b>{username}</b> muvaffaqiyatli saqlandi va tizimga kirildi! ✅")
    else:
        await msg.edit_text(f"⚠️ <b>{username}</b> saqlandi, lekin tizimga kirib bo'lmadi (parol xato bo'lishi mumkin) ❌")


# -------------------------------------------------------------------------
# Batch Add Logins (e.g. "add user:pass, user2:pass")
# -------------------------------------------------------------------------
@dp.message(F.text.startswith("add "))
async def batch_add_handler(message: Message):
    user = await create_user(message.from_user.id)
    school_id = user.school_id
    if not school_id:
        await message.answer("Iltimos, avval biror maktabga ulaning yoki adminga murojaat qiling.")
        return

    raw_items = message.text[4:].split(",")
    valid_entries = []
    for item in raw_items:
        if ":" in item:
            u, p = item.strip().split(":", 1)
            valid_entries.append((u.strip(), p.strip()))

    if not valid_entries:
        await message.answer("Format xato. Masalan: add user1:pass1, user2:pass2")
        return

    msg = await message.answer(f"⏳ {len(valid_entries)} ta login tekshirilmoqda...")
    payload = {
        str(idx): {
            "username": u,
            "password": p,
            "last_login": False,
            "last_cookie": "",
            "tg_id": message.from_user.id,
            "grade": user.grade or "1A",
            "school_id": school_id
        }
        for idx, (u, p) in enumerate(valid_entries)
    }

    res = await send_request_main(payload)
    for idx, (u, p) in enumerate(valid_entries):
        sid = str(idx)
        succ = res.get(sid, {}).get("last_login", False)
        cookie = res.get(sid, {}).get("last_cookie", "")
        await create_login(
            username=u,
            password=p,
            last_login=succ,
            cookie=cookie,
            grade=user.grade or "1A",
            school_number_id=school_id,
            tg_id=message.from_user.id
        )

    s_count = sum(1 for d in res.values() if d.get("last_login"))
    await msg.edit_text(f"✅ Yakunlandi! Jami: {len(valid_entries)} ta, Kirildi: {s_count} ta, Xato: {len(valid_entries) - s_count} ta.")


# -------------------------------------------------------------------------
# Help & Info
# -------------------------------------------------------------------------
@dp.message(F.text.in_({"ℹ️ Yordam", "/help"}))
async def help_handler(message: Message):
    admin = is_owner(message.from_user.id)
    text = (
        "🤖 <b>eMaktab Avtomatlashtirish Boti</b>\n\n"
        "• <b>🏫 Maktablar</b> — Barcha maktablar va ularning umumiy muvaffaqiyat statistikasini ko'rish.\n"
        "• <b>📊 Statistika</b> — Tizim bo'yicha to'liq hisobot.\n"
        "• <b>➕ Login qo'shish</b> — Yangi login va parollarni tizimga kiritish.\n"
    )
    if admin:
        text += (
            "\n👑 <b>Bosh Administrator Imkoniyatlari:</b>\n"
            "• Har bir maktab va sinfdagi login/parollarni ko'rish\n"
            "• Parollarni o'zgartirish va o'chirish\n"
            "• Har bir o'quvchi hisobini alohida test qilish\n"
            "• Yangi maktab qo'shish va o'chirish\n"
            "• Har kuni ertalab 07:00 da to'liq statistik hisobot va DB nusxasini olish"
        )
    await message.answer(text, reply_markup=main_reply_keyboard(admin))


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


async def main():
    await init()
    await dp.start_polling(bot, skip_updates=True)


if __name__ == '__main__':
    try:
        print('Bot ishga tushdi...')
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print('Bot to‘xtatildi.')
