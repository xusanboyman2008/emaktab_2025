import asyncio
import json
import os
import random
import string
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import Column, Integer, String, ForeignKey, select, DateTime, BigInteger, Boolean, and_, Text
from sqlalchemy.ext.asyncio import AsyncAttrs, create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase


async def generate_unique_url(length: int = 15):
    # all ascii letters (uppercase + lowercase) + digits
    chars = string.ascii_letters + string.digits

    # build random string of given zzlength
    ready_text = ''.join(random.choice(chars) for _ in range(length))

    # check if this already exists in DB
    b = await get_school_number(url=ready_text)
    if b:
        ready_text += random.choice(chars)  # ensure uniqueness

    return ready_text


# DATABASE_URL = "sqlite+aiosqlite:///database.sqlite3"
DATABASE_URL = os.getenv(
    "DATABASE",
    "postgresql+asyncpg://postgres:xrRYDEKhqdREgqIfzTQDWeVTvYqCZPix@yamabiko.proxy.rlwy.net:43589/railway"
)


# DATABASE_URL = "postgresql+asyncpg://postgres:QHySkhdRasjxuaYbaqKlXurHZxqPOvxV@tramway.proxy.rlwy.net:24181/railway"
engine = create_async_engine(DATABASE_URL, future=True)
async_session = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)


class Base(AsyncAttrs, DeclarativeBase):
    pass


class Grades(Base):
    __tablename__ = "Grade"
    id = Column(Integer, autoincrement=True, primary_key=True)
    grade = Column(Text)


class School_number(Base):
    __tablename__ = "School_number"
    id = Column(Integer, autoincrement=True, primary_key=True)
    school_url = Column(String, unique=True, nullable=False)
    school_number = Column(Integer)
    place = Column(String, nullable=True)
    is_paid = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.now)
    expire_at = Column(
        DateTime,
        default=lambda: datetime.now() + timedelta(days=365)
    )


class Captcha_ids(Base):
    __tablename__ = "Captcha_ids"
    id = Column(Integer, autoincrement=True, primary_key=True)
    captcha_id = Column(Text, unique=True, nullable=False)
    is_occupied = Column(Boolean, default=False)
    last_used = Column(DateTime, default=datetime.now)


class User(Base):
    __tablename__ = "User"
    id = Column(Integer, autoincrement=True, primary_key=True)
    first_name = Column(String)
    username = Column(String, nullable=False)
    tg_id = Column(BigInteger, unique=True)
    role = Column(String, default="user")
    lang = Column(String, default='uz')
    grade = Column(Text, nullable=True)
    captcha_for_web = Column(Text, ForeignKey("Captcha_ids.captcha_id"), nullable=True)
    captcha_for_bot = Column(Text, ForeignKey("Captcha_ids.captcha_id"), nullable=True)
    school_id = Column(Integer, ForeignKey("School_number.id"))


class Logins(Base):
    __tablename__ = "Logins"
    id = Column(Integer, autoincrement=True, primary_key=True)
    school = Column(Integer, ForeignKey("School_number.id"))
    username = Column(String)
    password = Column(String)
    grade = Column(Text, nullable=False)
    last_cookie = Column(Text, nullable=True)
    last_login = Column(Boolean)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, onupdate=datetime.now)


class Logins_data(Base):
    __tablename__ = "Logins_data"
    id = Column(Integer, autoincrement=True, primary_key=True)
    login_id = Column(Integer, ForeignKey("Logins.id"))
    last_cookie = Column(Text, nullable=True)
    last_login = Column(Boolean)
    created_at = Column(DateTime, default=datetime.now)


TABLES = [User, School_number, Captcha_ids, Logins, Logins_data]


def row_to_dict(row):
    return {c.name: getattr(row, c.name) for c in row.__table__.columns}


async def get_all_Database():
    async with async_session() as session:
        backup = {}
        for model in TABLES:
            result = await session.execute(select(model))
            rows = result.scalars().all()
            if rows:
                backup[model.__tablename__] = [row_to_dict(r) for r in rows]

        print(backup)  # or return backup
        return backup


async def create_grades():
    async with async_session() as session:
        async with session.begin():
            for i in range(1, 12):
                for j in ["A", "B", "V", "G"]:
                    new_grade = Grades(grade=f"{i}{j}")
                    session.add(new_grade)
            await session.commit()
            return True


async def get_grade(grade=None, id=None):
    async with async_session() as session:
        async with session.begin():
            if id:
                a = await session.execute(select(Grades).where(Grades.id == id))
            else:
                a = await session.execute(select(Grades).where(Grades.grade == grade))
            r = a.scalar_one_or_none()
            if r:
                return r
            return None


async def create_user(tg_id, grade=None, first_name=None, username=None):
    async with async_session() as session:
        async with session.begin():
            # Check if user already exists
            result = await session.execute(select(User).where(User.tg_id == int(tg_id)))
            existing_user = result.scalar_one_or_none()

            if existing_user:
                # Update grade if provided and valid
                if grade:
                    grade_obj = await get_grade(grade)
                    if grade_obj:
                        existing_user.grade = grade_obj.id  # or grade_obj if it's a relationship
                        await session.commit()
                    else:
                        print(f"[WARN] Grade '{grade}' not found in database.")
                return existing_user

            # Create new user
            new_user = User(
                tg_id=tg_id,
                first_name=first_name,
                username=username or "",
            )

            # Assign grade if exists
            if grade:
                grade_obj = await get_grade(grade)
                if grade_obj:
                    new_user.grade = grade_obj.id  # or grade_obj depending on your model
                else:
                    print(f"[WARN] Grade '{grade}' not found in database.")

            session.add(new_user)
            await session.commit()
            await session.flush()
            return new_user


async def update_user(Tg_id, school_url):
    async with async_session() as session:
        async with session.begin():
            a = await session.execute(select(User).where(User.tg_id == Tg_id))
            r = a.scalar_one_or_none()
            school_id = await get_school_number(school_url)
            if not school_id:
                return False
            if r:
                r.school_id = school_id.id
                await session.commit()
                return school_id
            return False


async def create_school(school_number, place, days, edit=False):
    async with async_session() as session:
        async with session.begin():
            a = await session.execute(
                select(School_number.school_number).where(
                    and_(
                        School_number.school_number == int(school_number),
                        School_number.place == place
                    )
                )
            )
            r = a.scalar_one_or_none()
            if r:
                if edit:
                    r.expire_at = datetime.now() + timedelta(days=int(days))
                    await session.commit()
                    return r
                return r

            url = await generate_unique_url()
            new_school = School_number(
                school_number=int(school_number),
                place=place,
                expire_at=datetime.now() + timedelta(days=int(days)),
                school_url=url
            )
            session.add(new_school)
            await session.commit()
            await session.flush()
            return new_school


async def get_school_number(url=None, id=None):
    async with async_session() as session:
        async with session.begin():
            if url:
                a = await session.execute(select(School_number).where(School_number.school_url == url))
            if id:
                print(id)
                a = await session.execute(select(School_number).where(School_number.id == id))
            r = a.scalar_one_or_none()
            if r:
                return r
            return False


async def get_free_captcha():
    async with async_session() as session:
        async with session.begin():
            a = await session.execute(select(Captcha_ids).where(Captcha_ids.is_occupied == False))
            r = a.scalars().all()
            if r:
                return r[0].captcha_id
            return False


async def create_captcha_ids(captcha_id):
    async with async_session() as session:
        async with session.begin():
            a = await session.execute(select(Captcha_ids).where(Captcha_ids.captcha_id == captcha_id))
            r = a.scalar_one_or_none()
            if r:
                return False
            new_captcha_id = Captcha_ids(captcha_id=captcha_id)
            session.add(new_captcha_id)
            await session.commit()
            return True


async def update_captcha_id(captcha_id):
    async with async_session() as session:
        async with session.begin():
            a = await session.execute(select(Captcha_ids).where(Captcha_ids.captcha_id == captcha_id))
            r = a.scalar_one_or_none()
            if r:
                r.last_used = datetime.now()
                if not r.is_occupied:
                    r.is_occupied = True
                await session.commit()
                return True
            return False


async def add_captcha_id(captcha_id, tg_id, is_bot):
    async with async_session() as session:
        async with session.begin():
            user_id = await create_user(tg_id=tg_id)
            a = await session.execute(select(User).where(User.id == user_id.id))
            r = a.scalar_one_or_none()
            if r:
                await update_captcha_id(captcha_id=captcha_id)
                if is_bot:
                    r.captcha_for_bot = captcha_id
                else:
                    r.captcha_for_web = captcha_id
            await session.commit()


async def create_login(password, username, last_login, cookie, grade: str, school_number_id=None, tg_id=None):
    async with async_session() as session:
        async with session.begin():
            a = await session.execute(select(Logins).where(Logins.username == username))
            r = a.scalar_one_or_none()
            if r:
                return False
            if tg_id:
                user = await create_user(tg_id)
                new_login = Logins(password=password, username=username, last_login=last_login, last_cookie=cookie,
                                   school=user.school_id, grade=grade)
            else:
                new_login = Logins(password=password, username=username, last_login=last_login, last_cookie=cookie,
                                   school=school_number_id, grade=grade)
            session.add(new_login)
            await session.commit()
            return True


async def get_all_users():
    async with async_session() as session:
        async with session.begin():
            r = await session.execute(select(User))
            a = r.scalars().all()
            if a:
                return a
            return None


async def give_captcha_100(id):
    async with async_session() as session:
        async with session.begin():
            # build the query first, then execute
            result = await session.execute(
                select(Captcha_ids).where(Captcha_ids.id == id)
            )

            # get one record
            row = result.scalar_one_or_none()

            if row:
                return row.captcha_id  # works if Captcha_ids has a .captcha_id field
            else:
                # try another random ID if not found
                return await give_captcha_100(id + random.randint(1, 300))


async def create_logins_data(login_id, last_login, last_cookie):
    async with async_session() as session:
        async with session.begin():
            new_logins_data = Logins_data(login_id=login_id, last_login=last_login, last_cookie=last_cookie)
            session.add(new_logins_data)
            await session.commit()
            return True


async def get_all_logins(school2=None, grade=None):
    async with async_session() as session:
        async with session.begin():
            if school2:
                if grade:
                    a = await session.execute(
                        select(Logins).where(and_(Logins.school == int(school2), Logins.grade == int(grade))))
                else:
                    a = await session.execute(select(Logins).where(Logins.school == int(school2)))
            else:
                a = await session.execute(select(Logins))
            b = a.scalars().all()
            users = []
            for i in b:
                print(i.school)
                school = await get_school_number(id=int(i.school))
                if not school2 and school == False:
                    if school.expire_at > datetime.now():
                        users.append(i)
                else:
                    users.append(i)
            return b


async def update_logins(login_id, last_login, last_cookie, password=None):
    async with async_session() as session:
        async with session.begin():
            a = await session.execute(select(Logins).where(Logins.id == login_id))
            r = a.scalar_one_or_none()
            if r:
                if password:
                    r.password = password
                r.last_cookie = last_cookie
                r.last_login = last_login
                await session.commit()
                return True


async def get_all_captcha():
    async with async_session() as session:
        async with session.begin():
            a = await session.execute(select(Captcha_ids))
            r = a.scalars().all()
            c = 0
            for i in r:
                c += 1
            return c


async def create_or_change_user_role(user_tg, role='Admin'):
    async with async_session() as session:
        async with session.begin():
            a = await session.execute(select(User).where(User.tg_id == user_tg))
            r = a.scalar_one_or_none()
            if a:
                r.role = role
                await session.commit()
                return True
            return False


async def get_all_schools():
    async with async_session() as session:
        async with session.begin():
            a = await session.execute(select(School_number))
            r = a.scalars().all()
            if r:
                return r
            return False


async def init():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def add_captchas_by():
    with open("output.txt", "r") as f:
        for line in f:
            value = line.strip()
            await create_captcha_ids(value)


async def create_database_back_up():
    data = await get_all_Database()
    with open('database.json', 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4, default=str)
        return True


async def read_logins():
    file_path = Path("database12.json")  # Path to your file

    # Read JSON file asynchronously (in a background thread)
    data = await asyncio.to_thread(
        lambda: json.load(open(file_path, "r", encoding="utf-8"))
    )

    # Access the "Logins" list
    logins = data.get("Logins", [])

    # Loop through each login item
    for login in logins:
        username = login.get("username")
        password = login.get("password")
        last_login = login.get("last_login")
        cookie = login.get("last_cookie")
        created_at = login.get("created_at")
        grade = login.get("grade")
        school_id = login.get("school")
        await create_login(username=username, password=password, last_login=last_login, cookie=cookie, grade=grade,
                           school_number_id=school_id)

        print(f"👤 {username} | 🔑 {password} | 🕒 {created_at} | ✅ {last_login}")

    return logins


async def main():
    await init()
    await read_logins()
    # await create_grades()
    # await add_captchas_by()
    # await create_database_back_up()  # run your DB init


if __name__ == "__main__":
    import asyncio, sys
    if sys.platform.startswith("win"):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    try:
        asyncio.run(main())
    except RuntimeError as e:
        # Ignore harmless Windows SSL cleanup error
        if "Event loop is closed" not in str(e):
            raise
