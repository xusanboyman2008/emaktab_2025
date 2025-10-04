import asyncio
import json
import os
import random
from asyncio import to_thread
from collections import defaultdict

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ChatAction
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, reply_keyboard_remove, InlineKeyboardButton, \
    InlineKeyboardMarkup, WebAppInfo, FSInputFile
from telegraph import Telegraph

from database import get_all_logins, create_logins_data, create_login, create_user, get_all_users, create_school, \
    update_user, add_captcha_id, get_free_captcha, get_school_number, create_database_back_up, \
    create_or_change_user_role
from database import get_all_schools
from send_aiohttps_requests import send_request_main

# Create account once (not inside the handler every time!)
telegraph = Telegraph()
telegraph.create_account(short_name="xusanboy")

# url = 'https://submergible-sigrid-unrabbinical.ngrok-free.dev'
url = os.getenv('URL', "https://emaktab-2025.onrender.com/")
# Token = '7234794963:AAHQa70czYEIVlrPRTPiv_-6IvhcYzlVJ9M'
Token = os.getenv('TOKEN', "8301189313:AAE-XVcbyn4emNHDgEi7yJZFRroehh8DrNQ")
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


@dp.message(CommandStart())
async def start(message: Message, command: CommandStart, state: FSMContext):
    await state.clear()
    lan = await create_user(tg_id=message.from_user.id, first_name=message.from_user.first_name,
                            username=message.from_user.username if message.from_user.username is not None else "")
    payload = command.args
    if payload:
        if payload.startswith("logins"):
            school_id = payload.split("_")[1]
            is_admin = payload.split('_')[2]
            user = await create_user(tg_id=message.from_user.id)
            school_number = await get_school_number(id=int(school_id))
            if int(user.school_id) != int(school_id) and user.role != 'Owner':
                base_text = "🚫 Ushbu maktabga oid ma’lumotlar siz uchun emas. "

                msg = await message.answer("⏳ Promoting...")

                frames = []
                for i in range(len(base_text) + 1):
                    rotated = base_text[i:] + base_text[:i]
                    # apply random styling so it's always unique
                    styled = "".join(style_char(ch) for ch in rotated)
                    frames.append(styled)

                # Animate with style changes
                for frame in frames:
                    await msg.edit_text(frame, parse_mode="HTML")
                    await asyncio.sleep(0.2)
                await msg.edit_text(base_text)
                return
            msg = await message.answer('Iltiomos biroz kutib turing')
            logins = await get_all_logins(school2=school_id)

            s_t, f_t = "", ""
            s, f = 0, 0

            for i in logins:
                def format_time(dt):
                    return dt.strftime("%d.%m.%Y %H:%M") + " ⏰"

                def mask_text(text: str, is_admin: bool) -> str:
                    return text[:2] + "*" * 8
                row = f"""
                <b>ID:</b> {i.id}<br>
                <b>👤 Login:</b> {mask_text(i.username, is_admin)}<br>
                <b>🔑 Parol:</b> {mask_text(i.password, is_admin)}<br>
                <b>📌 Holat:</b> {'✅ Kirilgan' if i.last_login else '❌ Kirilmagan'}<br>
                <b>⏰ So‘nggi kirish vaqti:</b> {format_time(i.updated_at)}<br>
                <hr>
                """
                if i.last_login:
                    s += 1
                    s_t += row
                else:
                    f += 1
                    f_t += row

            # Stats page
            stats_html = f"""
            <h3>{school_number.school_number}-maktabning 📊 Umumiy statistika</h3>
            <b>👥 Jami loginlar:</b> {s + f}<br>
            <b>✅ Muvaffaqiyatli kirganlar:</b> {s}<br>
            <b>❌ Muvaffaqiyatsiz urinishlar:</b> {f}<br>
            <b>📈 Muvaffaqiyat foizi:</b> {round((s / (s + f) * 100), 1)}%<br><br>
            <a href="{{success_url}}">✅ Kirilgan loginlarni ko‘rish</a><br>
            <a href="{{fail_url}}">❌ Kirilmagan loginlarni ko‘rish</a>
            """""

            success_html = f"<h3>✅ Kirilgan loginlar ({s} ta)</h3>" + (
                    s_t or "—") + "<br><a href='{stats_url}'>⬅️ Orqaga</a>"
            # Create failed logins page
            fail_html = f"<h3>❌ Kirilmagan loginlar ({f} ta)</h3>" + (
                    f_t or "—") + "<br><a href='{stats_url}'>⬅️ Orqaga</a>"

            # Create empty stats first (we’ll insert URLs later)
            stats_page = await to_thread(
                telegraph.create_page,
                title="Loginlar statistikasi",
                html_content=stats_html.replace("{success_url}", "#").replace("{fail_url}", "#")
            )
            stats_url = stats_page["url"]

            # Create success page
            success_page = await to_thread(
                telegraph.create_page,
                title="✅ Kirilgan loginlar",
                html_content=success_html.format(stats_url=stats_url)
            )
            success_url = success_page["url"]

            # Create fail page
            fail_page = await to_thread(
                telegraph.create_page,
                title="❌ Kirilmagan loginlar",
                html_content=fail_html.format(stats_url=stats_url)
            )
            fail_url = fail_page["url"]

            # Update stats page with proper links
            final_stats_html = stats_html.replace("{success_url}", success_url).replace("{fail_url}", fail_url)
            await to_thread(
                telegraph.edit_page,
                path=stats_page["path"],
                title="Loginlar statistikasi",
                html_content=final_stats_html
            )

            # Send main page to user
            await msg.edit_text(f'<a href="{stats_url}">📖 Loginlar statistikasi va tafsilotlari</a>',protect_content=True)
            await state.clear()
        if payload == 'owner':
            users = await get_all_users()
            for user in users:
                if user.role == 'supporter' or user.role == 'owner':
                    await bot.send_message(
                        text=f'<a href="tg://user?id={message.from_user.id}">Foydalanuvchiga maktab yaratish kerak</a>',
                        chat_id=user.tg_id)
            await message.answer('Siz bilan tez orada ma`sul shaxslar aloqaga chiqishadi')
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
        await message.reply(f'Hi {message.from_user.first_name}\n{lan.lang}',
                            reply_markup=reply_keyboard_remove.ReplyKeyboardRemove())
        return
    await message.reply(f'hi {message.from_user.full_name}')
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
    await message.answer(f"<b>{text}</b>",)
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
                   "tg_id": message.from_user.id, 'login_id': False}}
    response = await send_request_main(login)
    print(response)
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
                           school_number_id=school_id)
    await state.set_state(Next.login)
    return


async def login_schedule(user=None):
    all_logins = await get_all_logins()
    logins = {}
    for login in all_logins:
        logins[login.id] = {"login_id": login.id, "password": login.password, "username": login.username,
                            "last_cookie": login.last_cookie,
                            'last_login': login.last_login, 'school_id': login.school, "tg_id": user}
    response = await send_request_main(logins)
    for sid, data in response.items():
        await create_logins_data(login_id=sid, last_login=data['last_login'], last_cookie=data['last_cookie'])
    grouped = defaultdict(dict)
    for user_id, data in response.items():
        school_id = data["school_id"]
        grouped[school_id][user_id] = data
    grouped = dict(grouped)

    if not user:
            users = await get_all_users()
            bot_data = await bot.get_me()
            print(grouped)
            for user2 in users:
                try:
                    if not user2.school_id:
                        pass
                    print(user2.school_id, user2.tg_id)
                    if user2.tg_id != 6588631008:
                        send_message = grouped.get(user2.school_id)
                        print(grouped.get(str(user2.school_id)))
                        if send_message:
                            s = 0
                            f = 0
                            for id, login_2 in send_message.items():
                                if login_2.get('last_login'):
                                    s += 1
                                else:
                                    f += 1
                            await bot.send_message(
                                chat_id=int(user2.tg_id),
                                text=(
                                    f"Jami loginlar: {f + s}\n"
                                f"Kirilgan loginlar soni: {s}\n"
                                f"Kirilmagan loginlar soni: {f if f else 0}\n"
                                f'Barcha loginlarni korish uchun <a href="https://t.me/{bot_data.username}?start=logins_{user2.school_id}_{True if user2.role == "admin" else False}"> bu yerga bosing</a>'
                                ), parse_mode='HTML'
                            )
                    else:
                        s = 0
                        f = 0
                        for send_message, data in grouped.items():
                            for id, login_2 in data.items():
                                if login_2.get('last_login'):
                                    s += 1
                                else:
                                    f += 1
                        send_message = grouped
                        pretty_json = json.dumps(send_message, indent=2, ensure_ascii=False, default=str)
                        chunks = split_text(pretty_json, MAX_LEN)
                        for i, chunk in enumerate(chunks, 1):
                            await bot.send_message(chat_id=user2.tg_id, text=
                            f"successful logins:{s}\nFailure: {f}\n```json\n{chunk}\n```",
                                                   parse_mode="MarkdownV2"
                                                   )
                except:
                    pass
    else:
        send_message = grouped
        pretty_json = json.dumps(send_message, indent=2, ensure_ascii=False, default=str)
        chunks = split_text(pretty_json, MAX_LEN)
        for i, chunk in enumerate(chunks, 1):
            await bot.send_message(chat_id=user, text=
            f"```json\n{chunk}\n```",
                                   parse_mode="MarkdownV2"
                                   )
    return


@dp.message(F.text == '/all')
async def all_logins(message: Message):
    await message.answer('Login progress just started')
    await login_schedule(False)
    return


MAX_LEN = 4000  # Telegram safe limit for Markdown text


def split_text(text, chunk_size=MAX_LEN):
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

    send_users = [message.from_user.id,tg_id]

    tasks = []
    await create_or_change_user_role(tg_id,role)
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
    while True:
        await asyncio.sleep(60)
        await login_schedule()
        await create_database_back_up()
        cat = FSInputFile("database.json")
        users = await get_all_users()
        for user in users:
            if user.role=='owner':
                await bot.send_document(chat_id=6588631008, document=cat)
        await asyncio.sleep(3600 * 24)


@dp.message(CommandStart)
async def show_json(message: Message):
    if message.text[:5] == 'clear':
        if message.text[5:].isdigit():
            await bot.delete_messages(chat_id=message.from_user.id, message_ids=[messages for messages in range(
                message.message_id - int(message.text[5:]), message.message_id + 1)])
            return
        for i in range(0, 1000, 50):
            try:
                print(i)
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
    chunks = split_text(pretty_json, MAX_LEN)

    for i, chunk in enumerate(chunks, 1):
        await message.reply(
            f"```json\n{chunk}\n```",
            parse_mode="MarkdownV2"
        )
    return


async def main():
    await dp.start_polling(bot)


if __name__ == '__main__':
    try:
        print('bot running')
        asyncio.run(main())
    except KeyboardInterrupt:
        print('bot stopped')
    except RuntimeError:
        print('bot crashed')
