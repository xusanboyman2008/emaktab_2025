import asyncio
import json
import os
import random
from asyncio import to_thread
from collections import defaultdict

import pytz
from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ChatAction
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, reply_keyboard_remove, InlineKeyboardButton, \
    InlineKeyboardMarkup, WebAppInfo, FSInputFile, CallbackQuery
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy.exc import InterfaceError
from telegraph import Telegraph
from telegraph.exceptions import RetryAfterError

from database import get_all_logins, create_logins_data, create_login, create_user, get_all_users, create_school, \
    update_user, add_captcha_id, get_free_captcha, get_school_number, \
    create_or_change_user_role, init, give_captcha_100
from database import get_all_schools
from database import get_grade
from database import get_logins_grade_for_web
from send_aiohttps_requests import send_request_main

# Create account once (not inside the handler every time!)
telegraph = Telegraph()
telegraph.create_account(short_name="xusanboy")

# url = 'https://submergible-sigrid-unrabbinical.ngrok-free.dev'
url = os.getenv('URL', "https://emaktab-2025.onrender.com/")
# Token = '7234794963:AAHQa70czYEIVlrPRTPiv_-6IvhcYzlVJ9M'
Token = os.getenv('TOKEN', "8301189313:AAEePiO5uaAMA01sbQLOts6TguUaztlbNaw")
bot = Bot(token=Token, default=DefaultBotProperties(
    parse_mode=ParseMode.HTML
))
dp = Dispatcher()


class Next(StatesGroup):
    login = State()
    password = State()
    school_number = State()
    school_place = State()
    days = State()


def back_button(input_text=None):
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text='👈 Ortga')]], resize_keyboard=True,
                               input_field_placeholder=input_text)


def style_char(ch: str) -> str:
    """Randomly apply bold/italic/code styling to a single character."""
    if ch.strip() == "":  # don't style spaces
        return ch
    styles = [
        lambda c: c,  # plain
        lambda c: f"<b>{c}</b>",  # bold
        lambda c: f"<i>{c}</i>",  # italic
        # lambda c: f"<code>{c}</code>",  # monospace
    ]
    return random.choice(styles)(ch)


def grades_button(current_page: int):
    letters = ["A", "B", "v"]
    buttons = []
    rows = []

    # Define start and end grades for each page
    if current_page == 1:
        start, end = 1, 5  # 1–4
    elif current_page == 2:
        start, end = 5, 9  # 5–8
    else:
        start, end = 9, 12  # 9–12 (Python range is exclusive)

    # Create grade buttons (4 grades × 3 letters = 12 buttons)
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

    # Navigation buttons (👇 don't touch these)
    nav_buttons = [
        InlineKeyboardButton(text="👈",
                             callback_data=f"page_{3 if current_page == 1 else 2 if current_page == 3 else 1}"),
        InlineKeyboardButton(text="👉",
                             callback_data=f"page_{2 if current_page == 1 else 3 if current_page == 2 else 1}"),
    ]
    rows.append(nav_buttons)

    return InlineKeyboardMarkup(inline_keyboard=rows)
async def create_page_safe(telegraph, title, content):
    while True:
        try:
            return await to_thread(
                telegraph,
                title=title,
                author_name='Me',
                html_content=content
            )
        except RetryAfterError as e:
            print(f"Telegraph limit! Waiting {e.retry_after} sec…")
            await asyncio.sleep(e.retry_after)

async def create_all_schools_report(user, all_schools, all_logins, grades):
    """
    Create a Telegraph report listing all schools, each with stats and links
    to their success/fail login lists (paginated if too large).
    """

    def chunk_list(data, size):
        for i in range(0, len(data), size):
            yield data[i:i + size]

    def format_time(dt):
        return dt.strftime("%d.%m.%Y %H:%M") + " ⏰"

    def mask_text(text: str) -> str:
        return text

    school_blocks = []  # all school HTML summaries

    # Loop through every school
    for school in all_schools:
        school_logins = [l for l in all_logins if int(l.school) == int(school.id)]
        if not school_logins:
            continue  # skip schools with no logins

        grouped = defaultdict(list)
        for login in school_logins:
            if isinstance(grades, dict):
                grade_name = grades.get(int(login.grade), f"{login.grade}-sinf")
            else:
                grade_name = getattr(grades, "grade", f"{login.grade}-sinf")
            grouped[grade_name].append(login)

        s_t, f_t = "", ""
        s, f = 0, 0

        # Build HTML for each grade
        for grade_name in sorted(grouped.keys()):
            grade_logins = grouped[grade_name]

            success_block = f"<h3>📗 {grade_name} sinf (✅ Kirilganlar)</h3>"
            fail_block = f"<h3>📕 {grade_name} sinf (❌ Kirilmaganlar)</h3>"

            for index, i in enumerate(grade_logins):
                row = f"""
                <b>ID:</b> {index + 1}<br>
                <b>👤 Login:</b> {mask_text(i.username)}<br>
                <b>🔑 Parol:</b> {mask_text(i.password)}<br>
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

        # --- Create subpages with pagination ---
        async def create_split_pages(prefix, html_text, icon):
            pages = []
            parts = list(chunk_list(html_text.split("<hr>"), 80))
            for idx, chunk in enumerate(parts):
                page_html = f"<h3>{icon} {prefix} – {school.school_number}-maktab (sahifa {idx + 1})</h3>" + "<hr>".join(chunk)
                page = await to_thread(
                    telegraph.create_page,
                    title=f"{school.school_number}-maktab {prefix} ({idx + 1})",
                    html_content=page_html
                )
                pages.append(page["url"])
            return "<br>".join(f"<a href='{url}'>{prefix} – sahifa {i + 1}</a>" for i, url in enumerate(pages))

        success_pages_html = await create_split_pages("✅ Kirilganlar", s_t, "✅") if s else "–"
        fail_pages_html = await create_split_pages("❌ Kirilmaganlar", f_t, "❌") if f else "–"

        # --- Create school-level summary block ---
        school_block = f"""
        <h3>{school.school_number}-maktab 📊</h3>
        👥 Jami loginlar: {total}<br>
        ✅ Kirilgan: {s}<br>
        ❌ Kirilmagan: {f}<br>
        📈 Muvaffaqiyat foizi: {round((s / total * 100), 1) if total else 0}%<br>
        """

        if s != 0:
            await asyncio.sleep(1)   # prevent flood
            success_page = await create_page_safe(telegraph.create_page,f"{school.school_number}-maktab ✅ Kirilganlar",f"<h3>✅ {school.school_number}-maktab Kirilgan loginlar</h3>{success_pages_html}")
            school_block += f"<a href='{success_page['url']}'>✅ Kirilgan loginlar ({s} ta)</a><br>"

        if f != 0:
            fail_page = await to_thread(
                telegraph.create_page,
                title=f"{school.school_number}-maktab ❌ Kirilmaganlar",
                html_content=f"<h3>❌ {school.school_number}-maktab Kirilmagan loginlar</h3>{fail_pages_html}"
            )
            school_block += f"<a href='{fail_page['url']}'>❌ Kirilmagan loginlar ({f} ta)</a><br>"

        school_block += "<hr>"
        school_blocks.append(school_block)

    # --- Final Telegraph page (all schools together) ---
    all_html = "<h3>🏫 Barcha maktablar login statistikasi</h3><br>" + "".join(school_blocks)
    final_page = await to_thread(
        telegraph.create_page,
        title="Barcha maktablar login statistikasi",
        html_content=all_html
    )

    return final_page["url"]


@dp.message(CommandStart())
async def start(message: Message, command: CommandStart, state: FSMContext):
    await state.clear()
    lan = await create_user(tg_id=message.from_user.id, first_name=message.from_user.first_name,
                            username=message.from_user.username if message.from_user.username is not None else "")
    payload = command.args
    if payload:
        if payload.startswith("logins"):
            school_id = payload.split("_")[1]
            grade = payload.split("_")[3]
            user = await create_user(tg_id=message.from_user.id)
            school_number = await get_school_number(id=int(school_id))

            # Security check
            if (
                    int(user.school_id) != int(school_id)
                    and int(grade) == int(user.grade)
            ):
                base_text = "🚫 Ushbu maktabga oid ma’lumotlar siz uchun emas."
                msg = await message.answer("⏳ Tekshirilmoqda...")
                for i in range(len(base_text) + 1):
                    rotated = base_text[i:] + base_text[:i]
                    styled = "".join(style_char(ch) for ch in rotated)
                    await msg.edit_text(styled, parse_mode="HTML")
                    await asyncio.sleep(0.2)
                await msg.edit_text(base_text)
                return

            msg = await message.answer('⏳ Iltimos, biroz kuting...')

            # 🧩 Admin / Owner — show all grades grouped
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
                    parse_mode="HTML",
                    protect_content=True
                )


# 🧩 Admin / Owner — show all grades grouped
            if user.role.lower() == "user":
                # ✅ Get the user's school directly
                school_id = user.school_id

                # ✅ Fetch all logins for this school & the user’s grade
                all_logins = await get_all_logins(school2=school_id, grade=user.grade)

                grouped = defaultdict(list)

                # ✅ Step 1: collect unique grade IDs
                grade_ids = list({login.grade for login in all_logins})

                # ✅ Step 2: fetch all grades in one query (use list of ids)
                grades = []
                for gid in grade_ids:
                    grade = await get_grade(id=gid)
                    if grade:
                        grades.append(grade)

                # ✅ Step 3: get the school info
                school_obj = await get_school_number(id=school_id)

                # ✅ Step 4: generate Telegraph report
                stats_url = await create_all_schools_report(
                    user=user,
                    all_schools=[school_obj],  # only this user’s school
                    all_logins=all_logins,
                    grades=grades
                )

                # ✅ Step 5: send the report link
                await msg.edit_text(
                    f'<a href="{stats_url}">📖 {school_obj.school_number}-maktab loginlari</a>',
                    parse_mode="HTML",
                    protect_content=True
                )

                await state.clear()
                return


        if payload == 'owner':
            users = await get_all_users()
            for user in users:
                if user.role == 'supporter' or user.role == 'owner':
                    await bot.send_message(
                        text=f'<a href="tg://user?id={message.from_user.id}">Foydalanuvchiga maktab yaratish kerak</a>',
                        chat_id=user.tg_id)
            await message.answer('Siz bilan tez orada ma`sul shaxslar aloqaga chiqishadi')
            return
    if not lan.grade or payload == "grade_change":
        await message.answer('Iltimos sinfingizni tanlang', reply_markup=grades_button(1))
        return
    if payload:
        if payload == 'clear':
            try:
                await bot.delete_messages(message.chat.id, [messages for messages in
                                                            range(message.message_id - 10, message.message_id + 1)])
                await message.answer(text='/login - login qoshish uchun')
                return
            except:
                pass
        a = await update_user(message.from_user.id, payload)
        if not a:
            await message.delete()
            return

        await message.answer(
            f"✅ Siz <b><i> <u>{a.place}</u></i></b> ning <u><i><b>{a.school_number} </b></i></u>maktabiga qoshildingiz")
        return
    if lan:
            data_bot = await bot.get_me()
            await message.reply(
                "<b>👋 Assalomu alaykum, hurmatli mijoz!</b>\n\n"
                "📱 Ushbu bot yordamida siz maktab loginlarini qulay tarzda boshqarishingiz mumkin.\n\n"
                "🧩 Quyidagi amallar mavjud:\n"
                "• <b>/login</b> — yangi login qo‘shish\n"
                "• 🔍 Quyidagi tugma orqali mavjud loginlarni ko‘rish mumkin 👇",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            InlineKeyboardButton(
                                text="📂 Sinfimning loginlarini ko‘rish",
                                url=f"https://t.me/{data_bot.username}?start=logins_{lan.school_id}_True_{lan.grade}"
                            )
                        ]
                    ]
                ),
            )


            return
    await message.reply(f'hi {message.from_user.full_name}')
    return


@dp.callback_query(F.data.startswith("grade_"))
async def catch_grade(callback: CallbackQuery):
    data = callback.data.split("grade_")[1]
    number, letter = data.split('_')[0], data.split('_')[1]
    user = await create_user(tg_id=callback.from_user.id, grade=f"{number}{letter.upper()}")
    await callback.message.edit_text(text=f"Siz {number}-{letter.upper()} sinfdasiz")


@dp.callback_query(F.data.startswith('page_'))
async def pages(callback_query: CallbackQuery):
    data = callback_query.data.split("page_")
    try:
        await callback_query.message.edit_text(reply_markup=grades_button(int(data[1])),
                                               text="Iltimos sinfingizni tanlang")
        return
    except TelegramBadRequest:
        await callback_query.message.edit_text(reply_markup=grades_button(int(data[1])),
                                               text="<i>Iltimos sinfingizni tanlang</i>", parse_mode='HTML')
        return


@dp.message(F.text == "/school")
async def school(message: Message, state: FSMContext):
    await message.answer('Maktab raqamini kiriting')
    await state.set_state(Next.school_number)
    return


@dp.message(Next.school_number)
async def school_number_message(message: Message, state: FSMContext):
    if message.text.isdigit():
        await message.answer('Maktab manzilini kiriting')
        await state.set_state(Next.school_place)
        await state.update_data(school_number=int(message.text))
        return
    else:
        await message.answer('Iltimos raqamlardan foydalaning')
        await state.set_state(Next.school_number)
        return


@dp.message(Next.school_place)
async def school_place_message(message: Message, state: FSMContext):
    await message.answer('Necha kun ishlashini kiriting: (Namumna:365')
    await state.set_state(Next.days)
    await state.update_data(school_place=message.text)
    return


@dp.message(F.text == "/all_schools")
async def get_asdasdas(message: Message):
    schools = await get_all_schools()
    text = ''
    bot_data = await bot.get_me()
    for i in schools:
        text += f"Id: {i.id}\nNumber: {i.school_number}\nPlace: {i.place}\nURL: https://t.me/{bot_data.username}?start={i.school_url} \nExpire_at: {i.expire_at}\n\n"
    await message.answer(f"<b>{text}</b>", )
    return


@dp.message(Next.days)
async def next_days_message(message: Message, state: FSMContext):
    data = await state.get_data()
    school_number = data['school_number']
    school_place = data['school_place']
    days = message.text
    if not message.text.isdigit():
        await message.answer('Iltimos faqat raqam kiriting')
        await state.set_state(Next.days)
        return
    a = await create_school(school_number, school_place, days)
    me = await bot.get_me()
    await message.answer(f"https://t.me/{me.username}?start={a.school_url}")
    await state.clear()
    return


@dp.message(F.text == '/login')
async def start_login(message: Message, state: FSMContext):
    user = await create_user(tg_id=message.from_user.id)
    if not user.school_id:
        bot_data = await bot.get_me()
        await message.answer(
            f"Iltimos maktabga qoshiling yoki bot yaratuvchisi ga xabar yuboring\n<tg-spoiler>🚫 Agar spam bolsangiz, <a href=\"https://t.me/{bot_data.username}?start=owner\">shu yerni bosing</a> — adminlar siz bilan bog'lanishadi.</tg-spoiler>")
        return
    await message.reply('Foydalanivchi loginini kiriting\n(Na`muna: xusanboyabdulxayev',
                        reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text='Menuga qaytish')]],
                                                         resize_keyboard=True, one_time_keyboard=True,
                                                         input_field_placeholder='logini kiriting'))
    await state.set_state(Next.login)


@dp.message(Next.login)
async def login(message: Message, state: FSMContext):
    if message.text == 'Menuga qaytish':
        await state.clear()
        await message.reply('Bekor qilindi')
        return
    login = message.text
    await message.answer(f"'{login}' uchun parolni 🔑 kiriting:",
                         reply_markup=back_button(input_text='Parolni kiriting 🔑'))
    await state.set_state(Next.password)
    await state.update_data(login=login)


@dp.message(Next.password)
async def password(message: Message, state: FSMContext):
    global asa
    password = message.text
    data = await state.get_data()
    login1 = data['login']
    user = await create_user(message.from_user.id)
    school_id = user.school_id
    if message.text == '👈 Ortga':
        await state.set_state(Next.password)
        await message.answer(f"'{login1}' uchun parolni 🔑 kiriting:")
        return
    await message.reply(f"Login: {login1}\n Password: {password}\n kirilyapti iltimos kuting....",
                        reply_markup=reply_keyboard_remove.ReplyKeyboardRemove())
    login = {'1': {'username': login1, 'password': password, 'last_login': False, 'last_cookie': '',
                   "tg_id": message.from_user.id, 'login_id': False, "grade": user.grade}}
    response = await send_request_main(login)
    bot_username = await bot.get_me()
    a = False
    if not response['1']['last_login']:
        if user.captcha_for_bot is None:
            captcha = await get_free_captcha()
            await add_captcha_id(captcha_id=captcha, tg_id=message.from_user.id, is_bot=True)
        else:
            a = True
            captcha = user.captcha_for_bot
            asa = await message.answer(text='Login kira olamdi shu sabab shu web tugmasini bosib osha joyda kiring',
                                       reply_markup=InlineKeyboardMarkup(
                                           inline_keyboard=[[InlineKeyboardButton(text='Web', web_app=WebAppInfo(
                                               url=f"{url}?username={login1}&password={password}&tg_id={message.from_user.id}&captcha={captcha}")),
                                                             InlineKeyboardButton(text='Bekor qilish',
                                                                                  url=f'https://t.me/{bot_username.username}?start=clear')]]))
    if response["1"]['last_login']:
        if a:
            await asa.edit_text(f"{login1} saqlandi va muaffaiyatli kirildi 🎉")
        else:
            await message.answer(f"{login1} saqlandi va muaffaiyatli kirildi 🎉")
        await create_login(password=password, username=login1, cookie=response["1"]['last_cookie'], last_login=True,
                           school_number_id=school_id, grade=user.grade)
    await state.set_state(Next.login)
    return


async def log_in(message, login1, password, school_id, captcha, grade):
    abad = await message.reply(f"Login: {login1}\n Password: {password}\n kirilyapti iltimos kuting....",
                               reply_markup=reply_keyboard_remove.ReplyKeyboardRemove())
    login = {'1': {'username': login1, 'password': password, 'last_login': False, 'last_cookie': '',
                   "tg_id": message.from_user.id, 'login_id': False}}
    response = await  send_request_main(login)
    print(response)
    bot_username = await bot.get_me()
    a = True
    if not response['1']['last_login']:
        if a:
            response = await  send_request_main(login)
            a = False
        await message.reply(text=f'Login:{login1} kira olamdi shu sabab shu web tugmasini bosib osha joyda kiring',
                            reply_markup=InlineKeyboardMarkup(
                                inline_keyboard=[[InlineKeyboardButton(text='Web', web_app=WebAppInfo(
                                    url=f"{url}?username={login1}&password={password}&tg_id={message.from_user.id}&captcha={captcha}")),
                                                  InlineKeyboardButton(text='Bekor qilish',
                                                                       url=f'https://t.me/{bot_username.username}?start=clear')]]))
    if response["1"]['last_login']:
        await message.answer(f"{login1} saqlandi va muaffaiyatli kirildi 🎉")
        await create_login(password=password, username=login1, cookie=response["1"]['last_cookie'], last_login=True,
                           school_number_id=school_id, grade=grade)
    return


@dp.message(F.text.startswith("add"))
async def password(message: Message, state: FSMContext):
    text = message.text
    if text.lower().startswith("add "):
        n_message = text[4:].strip()
    else:
        n_message = text

    try:
        user = await create_user(message.from_user.id)
    except InterfaceError:
        user = await create_user(message.from_user.id)

    school_id = user.school_id

    # split by comma and clean spaces
    logins = [item.strip() for item in n_message.split(",") if item.strip()]

    # batch size
    batch_size = 10

    for i in range(0, len(logins), batch_size):
        batch = logins[i:i + batch_size]
        tasks = []

        for item in batch:
            try:
                login, pwd = item.split(":", 1)
                tasks.append(
                    log_in(
                        message,
                        login,
                        pwd,
                        school_id,
                        await give_captcha_100(30),
                        grade=user.grade
                    )
                )
            except ValueError:
                pass

        # Run 10 at once, wait before next batch
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Optional small pause between batches (e.g., 2s)
        await asyncio.sleep(2)

    return

async def login_schedule(user: int | None = None):
    # 1️⃣ Load all logins
    all_logins = await get_all_logins()

    # Prepare login dictionary
    logins = {
        login.id: {
            "login_id": login.id,
            "password": login.password,
            "username": login.username,
            "last_cookie": login.last_cookie,
            "last_login": login.last_login,
            "school_id": login.school,
            "tg_id": user,
            "grade": login.grade,
        }
        for login in all_logins
    }

    # 2️⃣ Send login requests concurrently
    response = await send_request_main(logins,bot)
    print("✅ Done login checks")

    # 3️⃣ Update DB for all logins in parallel
    await asyncio.gather(*[
        create_logins_data(
            login_id=sid,
            last_login=data["last_login"],
            last_cookie=data["last_cookie"]
        )
        for sid, data in response.items()
    ])
    print("✅ Done updating database")

    # 4️⃣ Group logins by (school_id, grade)
    grouped = defaultdict(lambda: defaultdict(dict))
    for user_id, data in response.items():
        key = (data["school_id"], data["grade"])
        grouped[key][user_id] = data
    grouped = dict(grouped)

    # 5️⃣ Bot info for links
    bot_data = await bot.get_me()
    bot_data = await bot.get_me()

    # 7️⃣ Otherwise — automatic scheduled sending to all users
    users = await get_all_users()
    print("✅ Got all users")

    async def send_to_user(user_obj):
        if not user_obj.school_id or not user_obj.grade:
            print(user_obj.school_id, user_obj.grade)
            return
        if user_obj.role in ("admin", "owner"):
            # Filter all grades of this school
            school_grades = {k: v for k, v in grouped.items() if k[0] == user_obj.school_id}

            total_success = 0
            total_fail = 0
            total_all = 0

            for send_message in school_grades.values():
                s = sum(1 for d in send_message.values() if d.get("last_login"))
                f = sum(1 for d in send_message.values() if not d.get("last_login"))
                total_success += s
                total_fail += f
                total_all += s + f

            text = (
                f"🏫 Maktab raqami: {(await get_school_number(id=user_obj.school_id)).school_number}\n"
                f"📊 Jami loginlar: {total_all}\n"
                f"✅ Kirilgan: {total_success}\n"
                f"❌ Kirilmagan: {total_fail}\n"
                f'<a href="https://t.me/{bot_data.username}?start=logins_{user_obj.school_id}_True_{user_obj.grade}">'
                f"Barcha loginlarni ko‘rish uchun bu yerga bosing</a>"
            )

            await bot.send_message(chat_id=user_obj.tg_id, text=text, parse_mode="HTML")

        #If user is not admin — send only their own class info
        else:
            print(grouped)
            key = (int(user_obj.school_id), str(user_obj.grade).strip())
            send_message = grouped.get(key)
            if not send_message:
                print("⚠️ No logins found for:", key)
                return

            if not send_message:
                return
            print("DEBUG:", user_obj.school_id, user_obj.grade, grouped.keys())
            s = sum(1 for d in send_message.values() if d.get("last_login"))
            f = sum(1 for d in send_message.values() if not d.get("last_login"))

            text = (
                f"🏫 Maktab raqami: {(await get_school_number(id=user_obj.school_id)).school_number}\n | Sinfi: {(await get_grade(id=user_obj.grade)).grade}\n"
                f"📊 Jami loginlar: {f + s}\n"
                f"✅ Kirilgan: {s}\n"
                f"❌ Kirilmagan: {f}\n"
                f'<a href="https://t.me/{bot_data.username}?start=logins_{user_obj.school_id}_False_{user_obj.grade}">'
                f"Barcha loginlarni ko‘rish uchun bu yerga bosing</a>"
            )

            await bot.send_message(chat_id=user_obj.tg_id, text=text, parse_mode="HTML")

    # Run sending in parallel (safe batch of 10)
    BATCH_SIZE = 10
    for i in range(0, len(users), BATCH_SIZE):
        batch = users[i:i + BATCH_SIZE]
        await asyncio.gather(*(send_to_user(u) for u in batch))
        await asyncio.sleep(0.3)


@dp.message(F.text == '/all')
async def all_logins(message: Message):
    await message.answer('Login progress just started')
    await login_schedule(False)
    return


def split_text(text, chunk_size=4000):
    """Split text into safe chunks for Telegram messages."""
    return [text[i:i + chunk_size] for i in range(0, len(text), chunk_size)]


users_data = {
    "users": {
        123456789: {"status": False},
        987654321: {"status": True}
    }
}


async def keep_typing(tg_id: int):
    """Send TYPING action every 4 seconds for 24 seconds (6 times)."""
    try:
        for _ in range(6):
            await bot.send_chat_action(chat_id=tg_id, action=ChatAction.TYPING)
            await asyncio.sleep(4)
    except TelegramBadRequest:
        pass  # can't send typing to this user


async def animate_message(tg_id: int, base_text: str, final_text: str):
    try:
        msg = await bot.send_message(chat_id=tg_id, text="⏳ Promoting...")
        frames = ["".join(style_char(ch) for ch in base_text[i:] + base_text[:i]) for i in range(len(base_text))]

        for frame in frames:
            await msg.edit_text(frame)
            await asyncio.sleep(0.2)

        await msg.edit_text(final_text, parse_mode="HTML")
    except TelegramBadRequest as e:
        print(f"Cannot send/edit message to {tg_id}: {e}")


@dp.message(F.text.startswith('/>:)'))
async def give_a_role(message: Message):
    try:
        data = message.text.split('_')[1]
        tg_id_str, role = data.split(':')
        tg_id = int(tg_id_str)
    except (IndexError, ValueError):
        await message.reply("Invalid command format. Use: />:)_<tg_id>:<role>")
        return

    send_users = [message.from_user.id, tg_id]

    tasks = []
    await create_or_change_user_role(tg_id, role)
    for user_id in send_users:
        base_text = f" {tg_id} ⭐ promoted to 👑 {role.capitalize()} by @{message.from_user.username} 🎉"
        final_text = (
            f"✨👑 <b><a href=\"tg://user?id={tg_id}\">User</a></b> has been <b>promoted</b> to {role.capitalize()} by "
            f"@{message.from_user.username} 🎉\n\n🚀 Congratulations and good luck! 🔥"
        )

        tasks.append(animate_message(user_id, base_text, final_text))
        tasks.append(keep_typing(user_id))

    # Run all tasks concurrently
    await asyncio.gather(*tasks)


async def send_json():
        print('working')
        await login_schedule()
        cat = FSInputFile("database.sqlite3")
        users = await get_all_users()
        for user in users:
            if user.role == 'owner':
                await bot.send_document(chat_id=user.tg_id, document=cat)


@dp.message(CommandStart)
async def show_json(message: Message):
    if message.text and message.text.startswith('clear'):
        if message.text[5:].isdigit():
            await bot.delete_messages(chat_id=message.from_user.id, message_ids=[messages for messages in range(
                message.message_id - int(message.text[5:]), message.message_id + 1)])
            return
        for i in range(0, 1000, 50):
            try:
                await bot.delete_messages(chat_id=message.from_user.id, message_ids=[messages for messages in
                                                                                     range(message.message_id - 50 + i,
                                                                                           message.message_id + 1 - i)])
            except TelegramBadRequest:
                pass
        return
    if message.text == "True":
        users_data["users"][message.from_user.id] = {"status": True}  # add/update user
    if message.text == "False":
        users_data["users"][message.from_user.id] = {"status": False}  # add/update user

    if message.chat.type != 'private':
        return

    if not users_data["users"].get(message.from_user.id, {"status": False})["status"]:
        await message.delete()
        return
    msg_dict = message.model_dump()
    pretty_json = json.dumps(msg_dict, indent=2, ensure_ascii=False, default=str)
    chunks = split_text(pretty_json, 4000)

    for i, chunk in enumerate(chunks, 1):
        await message.reply(
            f"```json\n{chunk}\n```",
            parse_mode="MarkdownV2"
        )
    return


async def main():
    await init()

    scheduler = AsyncIOScheduler()

    scheduler.add_job(
        send_json,
        trigger="cron",
        hour=7,
        minute=0,
        timezone=pytz.timezone("Asia/Tashkent"),
    )

    scheduler.start()

    await dp.start_polling(bot)



if __name__ == '__main__':
    try:
        print('bot running')
        asyncio.run(main())
    except KeyboardInterrupt:
        print('bot stopped')
    except RuntimeError:
        print('bot crashed')
