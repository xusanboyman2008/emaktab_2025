import asyncio
import json
import os
import random
from collections import defaultdict

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ChatAction, ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import (
    Message, ReplyKeyboardMarkup, KeyboardButton, reply_keyboard_remove,
    InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo, FSInputFile, CallbackQuery
)
from sqlalchemy.exc import InterfaceError
from telegraph import Telegraph
from telegraph.exceptions import RetryAfterError

from database import (
    get_all_logins, create_logins_data, bulk_create_logins_data, create_login, create_user,
    get_all_users, create_school, update_user, add_captcha_id,
    get_free_captcha, get_school_number, create_or_change_user_role,
    init, give_captcha_100, get_all_schools, get_grade, get_logins_grade_for_web
)
from send_aiohttps_requests import send_request_main

telegraph = Telegraph()
try:
    telegraph.create_account(short_name="emaktab_helper")
except Exception as e:
    print("Telegraph init warning:", e)

url = os.getenv('URL', "https://emaktab-2025.onrender.com")
Token = os.getenv('TOKEN', "8301189313:AAEePiO5uaAMA01sbQLOts6TguUaztlbNaw")

bot = Bot(token=Token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()


class Next(StatesGroup):
    login = State()
    password = State()
    school_number = State()
    school_place = State()
    days = State()


def back_button(input_text=None):
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text='👈 Ortga')]],
        resize_keyboard=True,
        input_field_placeholder=input_text
    )


def style_char(ch: str) -> str:
    if ch.strip() == "":
        return ch
    styles = [
        lambda c: c,
        lambda c: f"<b>{c}</b>",
        lambda c: f"<i>{c}</i>",
    ]
    return random.choice(styles)(ch)


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
                    callback_data=f"grade_{i}_{letter}"
                )
            )
        rows.append(row)

    nav_buttons = [
        InlineKeyboardButton(text="👈", callback_data=f"page_{3 if current_page == 1 else 2 if current_page == 3 else 1}"),
        InlineKeyboardButton(text="👉", callback_data=f"page_{2 if current_page == 1 else 3 if current_page == 2 else 1}"),
    ]
    rows.append(nav_buttons)
    return InlineKeyboardMarkup(inline_keyboard=rows)


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
            print(f"Telegraph limit! Waiting {e.retry_after} sec…")
            await asyncio.sleep(e.retry_after)
        except Exception as e:
            print(f"Telegraph error: {e}")
            return {"url": ""}


async def create_all_schools_report(user, all_schools, all_logins, grades):
    def chunk_list(data, size):
        for i in range(0, len(data), size):
            yield data[i:i + size]

    def format_time(dt):
        return dt.strftime("%d.%m.%Y %H:%M") + " ⏰"

    school_blocks = []

    for school in (all_schools or []):
        school_logins = [l for l in all_logins if str(getattr(l, "school", "")) == str(school.id)]
        if not school_logins:
            continue

        grouped = defaultdict(list)
        for login in school_logins:
            if isinstance(grades, dict):
                grade_name = grades.get(int(login.grade), f"{login.grade}-sinf") if str(login.grade).isdigit() else f"{login.grade}-sinf"
            else:
                grade_name = getattr(grades, "grade", f"{login.grade}-sinf")
            grouped[grade_name].append(login)

        s_t, f_t = "", ""
        s, f = 0, 0

        for grade_name in sorted(grouped.keys()):
            grade_logins = grouped[grade_name]
            success_block = f"<h3>📗 {grade_name} (✅ Kirilganlar)</h3>"
            fail_block = f"<h3>📕 {grade_name} (❌ Kirilmaganlar)</h3>"

            for index, i in enumerate(grade_logins):
                row = f"""
                <b>ID:</b> {index + 1}<br>
                <b>👤 Login:</b> {i.username}<br>
                <b>🔑 Parol:</b> {i.password}<br>
                <b>📌 Holat:</b> {'✅ Kirilgan' if i.last_login else '❌ Kirilmagan'}<br>
                <b>⏰ So‘nggi kirish:</b> {format_time(i.updated_at) if i.updated_at else ''}<br>
                <hr>
                """
                if i.last_login:
                    s += 1
                    success_block += row
                else:
                    f += 1
                    fail_block += row

            s_t += success_block
            f_t += fail_block

        total = s + f

        async def create_split_pages(prefix, html_text, icon):
            pages = []
            parts = list(chunk_list(html_text.split("<hr>"), 80))
            for idx, chunk in enumerate(parts):
                page_html = f"<h3>{icon} {prefix} – {school.school_number}-maktab (sahifa {idx + 1})</h3>" + "<hr>".join(chunk)
                page = await create_page_safe(
                    telegraph,
                    title=f"{school.school_number}-maktab {prefix} ({idx + 1})",
                    content=page_html
                )
                if page and page.get("url"):
                    pages.append(page["url"])
            return "<br>".join(f"<a href='{u}'>{prefix} – sahifa {i + 1}</a>" for i, u in enumerate(pages))

        success_pages_html = await create_split_pages("✅ Kirilganlar", s_t, "✅") if s else "–"
        fail_pages_html = await create_split_pages("❌ Kirilmaganlar", f_t, "❌") if f else "–"

        school_block = f"""
        <h3>{school.school_number}-maktab 📊</h3>
        👥 Jami loginlar: {total}<br>
        ✅ Kirilgan: {s}<br>
        ❌ Kirilmagan: {f}<br>
        📈 Muvaffaqiyat foizi: {round((s / total * 100), 1) if total else 0}%<br>
        """

        if s != 0:
            success_page = await create_page_safe(telegraph, f"{school.school_number}-maktab ✅ Kirilganlar", f"<h3>✅ {school.school_number}-maktab Kirilgan loginlar</h3>{success_pages_html}")
            if success_page and success_page.get("url"):
                school_block += f"<a href='{success_page['url']}'>✅ Kirilgan loginlar ({s} ta)</a><br>"

        if f != 0:
            fail_page = await create_page_safe(telegraph, f"{school.school_number}-maktab ❌ Kirilmaganlar", f"<h3>❌ {school.school_number}-maktab Kirilmagan loginlar</h3>{fail_pages_html}")
            if fail_page and fail_page.get("url"):
                school_block += f"<a href='{fail_page['url']}'>❌ Kirilmagan loginlar ({f} ta)</a><br>"

        school_block += "<hr>"
        school_blocks.append(school_block)

    all_html = "<h3>🏫 Barcha maktablar login statistikasi</h3><br>" + "".join(school_blocks)
    final_page = await create_page_safe(
        telegraph,
        title="Barcha maktablar login statistikasi",
        content=all_html
    )
    return final_page.get("url", "")


@dp.message(CommandStart())
async def start(message: Message, command: CommandStart, state: FSMContext):
    await state.clear()
    lan = await create_user(
        tg_id=message.from_user.id,
        first_name=message.from_user.first_name or "",
        username=message.from_user.username or ""
    )
    payload = command.args
    if payload:
        if payload.startswith("logins"):
            parts = payload.split("_")
            school_id = parts[1] if len(parts) > 1 else None
            grade = parts[3] if len(parts) > 3 else None
            user = await create_user(tg_id=message.from_user.id)

            # Security check: users only access their own school
            if user.role.lower() not in ("admin", "owner"):
                if str(user.school_id) != str(school_id):
                    await message.answer("🚫 Ushbu maktabga oid ma’lumotlar siz uchun emas.")
                    return

            msg = await message.answer('⏳ Iltimos, biroz kuting...')

            # Admin / Owner — show all grades grouped
            if user.role.lower() in ("admin", "owner"):
                all_schools = await get_all_schools()
                all_logins = await get_all_logins()
                grades = await get_logins_grade_for_web(logins={login.grade for login in all_logins})

                stats_url = await create_all_schools_report(
                    user=user,
                    all_schools=all_schools,
                    all_logins=all_logins,
                    grades=grades
                )

                await msg.edit_text(
                    f'<a href="{stats_url}">📖 Barcha maktablar login statistikasi</a>',
                    protect_content=True
                )
                return

            # Regular user — show their own school & grade
            if user.role.lower() == "user":
                all_logins = await get_all_logins(school2=user.school_id, grade=user.grade)
                grade_ids = list({login.grade for login in all_logins})
                grades = []
                for gid in grade_ids:
                    g = await get_grade(id=gid) if str(gid).isdigit() else await get_grade(grade=gid)
                    if g:
                        grades.append(g)

                school_obj = await get_school_number(id=user.school_id)
                if not school_obj:
                    await msg.edit_text("Maktab ma'lumotlari topilmadi.")
                    return

                stats_url = await create_all_schools_report(
                    user=user,
                    all_schools=[school_obj],
                    all_logins=all_logins,
                    grades=grades
                )

                await msg.edit_text(
                    f'<a href="{stats_url}">📖 {school_obj.school_number}-maktab loginlari</a>',
                    protect_content=True
                )
                return

        if payload == 'owner':
            users = await get_all_users()
            for u in users:
                if u.role in ('supporter', 'owner'):
                    try:
                        await bot.send_message(
                            text=f'<a href="tg://user?id={message.from_user.id}">Foydalanuvchiga maktab yaratish kerak</a>',
                            chat_id=u.tg_id
                        )
                    except Exception:
                        pass
            await message.answer("Siz bilan tez orada mas'ul shaxslar aloqaga chiqishadi.")
            return

        if payload == 'clear':
            try:
                await bot.delete_messages(
                    message.chat.id,
                    list(range(max(1, message.message_id - 10), message.message_id + 1))
                )
            except Exception:
                pass
            await message.answer(text='/login - login qo‘shish uchun')
            return

        a = await update_user(message.from_user.id, payload)
        if not a:
            await message.answer("Maktab topilmadi yoki havola eskirgan.")
            return

        await message.answer(f"✅ Siz <b>{a.place}</b> dagi <b>{a.school_number}-maktab</b>ga qo‘shildingiz.")
        return

    if not lan.grade or payload == "grade_change":
        await message.answer('Iltimos sinfingizni tanlang:', reply_markup=grades_button(1))
        return

    data_bot = await bot.get_me()
    await message.reply(
        "<b>👋 Assalomu alaykum!</b>\n\n"
        "📱 Ushbu bot yordamida maktab loginlarini qulay tarzda boshqarishingiz mumkin.\n\n"
        "🧩 Amallar:\n"
        "• <b>/login</b> — yangi login qo‘shish\n"
        "• <b>/all</b> — loginlarni yangilash\n",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[
                InlineKeyboardButton(
                    text="📂 Sinfim loginlarini ko‘rish",
                    url=f"https://t.me/{data_bot.username}?start=logins_{lan.school_id}_True_{lan.grade}"
                )
            ]]
        )
    )


@dp.callback_query(F.data.startswith("grade_"))
async def catch_grade(callback: CallbackQuery):
    data = callback.data.split("grade_")[1]
    number, letter = data.split('_')[0], data.split('_')[1]
    await create_user(tg_id=callback.from_user.id, grade=f"{number}{letter.upper()}")
    await callback.message.edit_text(text=f"Siz {number}-{letter.upper()} sinfini tanladingiz.")


@dp.callback_query(F.data.startswith('page_'))
async def pages(callback_query: CallbackQuery):
    page_num = int(callback_query.data.split("page_")[1])
    try:
        await callback_query.message.edit_text(
            reply_markup=grades_button(page_num),
            text="Iltimos sinfingizni tanlang:"
        )
    except TelegramBadRequest:
        pass


@dp.message(F.text == "/school")
async def school(message: Message, state: FSMContext):
    await message.answer('Maktab raqamini kiriting:')
    await state.set_state(Next.school_number)


@dp.message(Next.school_number)
async def school_number_message(message: Message, state: FSMContext):
    if message.text.isdigit():
        await state.update_data(school_number=int(message.text))
        await message.answer('Maktab manzilini kiriting:')
        await state.set_state(Next.school_place)
    else:
        await message.answer('Iltimos faqat raqamlardan foydalaning:')


@dp.message(Next.school_place)
async def school_place_message(message: Message, state: FSMContext):
    await state.update_data(school_place=message.text)
    await message.answer('Necha kun ishlashini kiriting: (Masalan: 365)')
    await state.set_state(Next.days)


@dp.message(Next.days)
async def next_days_message(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer('Iltimos faqat raqam kiriting:')
        return
    data = await state.get_data()
    a = await create_school(data['school_number'], data['school_place'], int(message.text))
    me = await bot.get_me()
    await message.answer(f"https://t.me/{me.username}?start={a.school_url}")
    await state.clear()


@dp.message(F.text == "/all_schools")
async def get_all_schools_cmd(message: Message):
    schools = await get_all_schools()
    if not schools:
        await message.answer("Hech qanday maktab topilmadi.")
        return
    bot_data = await bot.get_me()
    lines = []
    for i in schools:
        lines.append(f"ID: {i.id} | Maktab: {i.school_number}\nManzil: {i.place}\nURL: https://t.me/{bot_data.username}?start={i.school_url}\nMuddati: {i.expire_at}\n")
    await message.answer("\n".join(lines))


@dp.message(F.text == '/login')
async def start_login(message: Message, state: FSMContext):
    user = await create_user(tg_id=message.from_user.id)
    if not user.school_id:
        bot_data = await bot.get_me()
        await message.answer(
            f"Iltimos, avval maktabga qo‘shiling yoki adminga murojaat qiling:\n"
            f"<a href=\"https://t.me/{bot_data.username}?start=owner\">Admin bilan bog‘lanish</a>"
        )
        return
    await message.reply(
        'Foydalanuvchi loginini kiriting:\n(Masalan: xusanboyabdulxayev)',
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text='Menuga qaytish')]],
            resize_keyboard=True,
            one_time_keyboard=True
        )
    )
    await state.set_state(Next.login)


@dp.message(Next.login)
async def login_step(message: Message, state: FSMContext):
    if message.text == 'Menuga qaytish':
        await state.clear()
        await message.reply('Bekor qilindi.')
        return
    await state.update_data(login=message.text.strip())
    await message.answer(
        f"'{message.text.strip()}' uchun parolni 🔑 kiriting:",
        reply_markup=back_button(input_text='Parolni kiriting 🔑')
    )
    await state.set_state(Next.password)


@dp.message(Next.password)
async def password_step(message: Message, state: FSMContext):
    if message.text == '👈 Ortga':
        data = await state.get_data()
        await message.answer(f"'{data.get('login')}' uchun parolni 🔑 kiriting:")
        return

    password = message.text
    data = await state.get_data()
    login1 = data.get('login')
    user = await create_user(message.from_user.id)
    school_id = user.school_id

    await message.reply(
        f"Login: {login1}\nTekshirilmoqda, iltimos kuting...",
        reply_markup=reply_keyboard_remove.ReplyKeyboardRemove()
    )

    login_req = {'1': {
        'username': login1, 'password': password, 'last_login': False,
        'last_cookie': '', "tg_id": message.from_user.id, 'login_id': False,
        "grade": user.grade
    }}
    response = await send_request_main(login_req)
    bot_username = await bot.get_me()

    if not response['1']['last_login']:
        captcha = user.captcha_for_bot or await get_free_captcha()
        if not user.captcha_for_bot:
            await add_captcha_id(captcha_id=captcha, tg_id=message.from_user.id, is_bot=True)

        await message.answer(
            'Avtomatik kirib bo‘lmadi. Quyidagi Web tugmasini bosib kiring:',
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(
                    text='Web orqali kirish',
                    web_app=WebAppInfo(url=f"{url}?username={login1}&password={password}&tg_id={message.from_user.id}&captcha={captcha}")
                ),
                InlineKeyboardButton(text='Bekor qilish', url=f'https://t.me/{bot_username.username}?start=clear')
            ]])
        )
    else:
        await message.answer(f"{login1} saqlandi va muvaffaqiyatli kirildi 🎉")
        await create_login(
            password=password, username=login1, cookie=response["1"]['last_cookie'],
            last_login=True, school_number_id=school_id, grade=user.grade
        )

    await state.clear()


async def log_in(message, login1, pwd, school_id, captcha, grade):
    login_req = {'1': {'username': login1, 'password': pwd, 'last_login': False, 'last_cookie': '', "tg_id": message.from_user.id}}
    response = await send_request_main(login_req)
    bot_username = await bot.get_me()

    if not response['1']['last_login']:
        await message.reply(
            f'Login: {login1} kira olmadi. Web tugmasi orqali kiring:',
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(
                    text='Web',
                    web_app=WebAppInfo(url=f"{url}?username={login1}&password={pwd}&tg_id={message.from_user.id}&captcha={captcha}")
                ),
                InlineKeyboardButton(text='Bekor qilish', url=f'https://t.me/{bot_username.username}?start=clear')
            ]])
        )
    else:
        await message.answer(f"{login1} saqlandi va muvaffaqiyatli kirildi 🎉")
        await create_login(password=pwd, username=login1, cookie=response["1"]['last_cookie'], last_login=True, school_number_id=school_id, grade=grade)


@dp.message(F.text.startswith("add"))
async def add_logins_batch(message: Message, state: FSMContext):
    text = message.text
    n_message = text[4:].strip() if text.lower().startswith("add ") else text

    user = await create_user(message.from_user.id)
    school_id = user.school_id
    logins = [item.strip() for item in n_message.split(",") if item.strip()]

    batch_size = 5
    for i in range(0, len(logins), batch_size):
        batch = logins[i:i + batch_size]
        tasks = []
        for item in batch:
            try:
                u, p = item.split(":", 1)
                captcha_val = await give_captcha_100()
                tasks.append(log_in(message, u.strip(), p.strip(), school_id, captcha_val, grade=user.grade))
            except ValueError:
                pass
        await asyncio.gather(*tasks, return_exceptions=True)
        await asyncio.sleep(1)


async def login_schedule(user_id: int | None = None):
    all_logins = await get_all_logins()
    if not all_logins:
        print("No logins in DB.")
        return

    logins = {
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

    response = await send_request_main(logins, bot)

    bulk_items = [
        {
            "login_id": sid,
            "last_login": data["last_login"],
            "last_cookie": data["last_cookie"]
        }
        for sid, data in response.items()
    ]
    await bulk_create_logins_data(bulk_items)

    grouped = defaultdict(lambda: defaultdict(dict))
    for uid, data in response.items():
        key = (data["school_id"], data["grade"])
        grouped[key][uid] = data

    bot_data = await bot.get_me()
    users = await get_all_users()

    async def send_to_user(user_obj):
        if not user_obj.school_id or not user_obj.grade:
            return

        school = await get_school_number(id=user_obj.school_id)
        school_num = school.school_number if school else "Noma'lum"

        if user_obj.role in ("admin", "owner"):
            school_grades = {k: v for k, v in grouped.items() if str(k[0]) == str(user_obj.school_id)}
            total_success = sum(sum(1 for d in sg.values() if d.get("last_login")) for sg in school_grades.values())
            total_fail = sum(sum(1 for d in sg.values() if not d.get("last_login")) for sg in school_grades.values())
            total_all = total_success + total_fail

            text = (
                f"🏫 Maktab raqami: {school_num}\n"
                f"📊 Jami loginlar: {total_all}\n"
                f"✅ Kirilgan: {total_success}\n"
                f"❌ Kirilmagan: {total_fail}\n"
                f'<a href="https://t.me/{bot_data.username}?start=logins_{user_obj.school_id}_True_{user_obj.grade}">'
                f"Barcha loginlarni ko‘rish uchun bosing</a>"
            )
            try:
                await bot.send_message(chat_id=user_obj.tg_id, text=text)
            except Exception:
                pass
        else:
            key = (user_obj.school_id, user_obj.grade)
            class_logins = grouped.get(key)
            if not class_logins:
                return

            s = sum(1 for d in class_logins.values() if d.get("last_login"))
            f = sum(1 for d in class_logins.values() if not d.get("last_login"))

            grade_obj = await get_grade(id=user_obj.grade) if str(user_obj.grade).isdigit() else await get_grade(grade=user_obj.grade)
            grade_name = grade_obj.grade if grade_obj else str(user_obj.grade)

            text = (
                f"🏫 Maktab: {school_num} | Sinfi: {grade_name}\n"
                f"📊 Jami loginlar: {s + f}\n"
                f"✅ Kirilgan: {s}\n"
                f"❌ Kirilmagan: {f}\n"
                f'<a href="https://t.me/{bot_data.username}?start=logins_{user_obj.school_id}_False_{user_obj.grade}">'
                f"Barcha loginlarni ko‘rish uchun bosing</a>"
            )
            try:
                await bot.send_message(chat_id=user_obj.tg_id, text=text)
            except Exception:
                pass

    for i in range(0, len(users), 10):
        batch = users[i:i + 10]
        await asyncio.gather(*(send_to_user(u) for u in batch))
        await asyncio.sleep(0.3)


@dp.message(F.text == '/all')
async def all_logins(message: Message):
    await message.answer('Loginlarni tekshirish boshlandi...')
    await login_schedule()
    await message.answer('Tekshirish yakunlandi ✅')


@dp.message(F.text.startswith('/>:)'))
async def give_a_role(message: Message):
    try:
        data = message.text.split('_')[1]
        tg_id_str, role = data.split(':')
        tg_id = int(tg_id_str)
    except (IndexError, ValueError):
        await message.reply("Noto‘g‘ri format. Masalan: />:)_<tg_id>:<role>")
        return

    await create_or_change_user_role(tg_id, role)
    final_text = (
        f"✨👑 <b>Foydalanuvchi {tg_id}</b> {role.capitalize()} roliga o‘tkazildi "
        f"@{message.from_user.username} tomonidan 🎉"
    )
    await message.answer(final_text)


async def send_json():
    print('Avtomatik tekshiruv boshlandi...')
    await login_schedule()
    if os.path.exists("database.sqlite3"):
        cat = FSInputFile("database.sqlite3")
        users = await get_all_users()
        for user in users:
            if user.role == 'owner':
                try:
                    await bot.send_document(chat_id=user.tg_id, document=cat)
                except Exception:
                    pass


@dp.message(Command("json"))
async def show_json(message: Message):
    msg_dict = message.model_dump()
    pretty_json = json.dumps(msg_dict, indent=2, ensure_ascii=False, default=str)
    await message.reply(f"<pre><code class=\"language-json\">{pretty_json[:3800]}</code></pre>")


async def main():
    await init()
    await dp.start_polling(bot, skip_updates=True)


if __name__ == '__main__':
    try:
        print('Bot ishga tushdi...')
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print('Bot to‘xtatildi.')
