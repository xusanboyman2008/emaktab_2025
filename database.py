import asyncio
import json
import os
import random
import string
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import (
    Column, Integer, String, ForeignKey, select, DateTime,
    BigInteger, Boolean, and_, Text, func, event
)
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import (
    AsyncAttrs, create_async_engine, async_sessionmaker, AsyncSession
)
from sqlalchemy.orm import DeclarativeBase

uzb_tz = timezone(timedelta(hours=5))

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///database.sqlite3")

# SQLite Performance Pragma configuration (WAL mode, fast sync, RAM cache)
@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    try:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL;")
        cursor.execute("PRAGMA synchronous=NORMAL;")
        cursor.execute("PRAGMA cache_size=-64000;")  # 64MB cache
        cursor.execute("PRAGMA temp_store=MEMORY;")
        cursor.execute("PRAGMA mmap_size=268435456;") # 256MB memory map
        cursor.close()
    except Exception:
        pass

engine = create_async_engine(
    DATABASE_URL,
    future=True,
    pool_pre_ping=True
)
async_session = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

# In-memory LRU/dict caches to avoid repeated database roundtrips
_SCHOOL_CACHE_BY_ID = {}
_SCHOOL_CACHE_BY_URL = {}
_GRADE_CACHE_BY_ID = {}
_GRADE_CACHE_BY_NAME = {}


class Base(AsyncAttrs, DeclarativeBase):
    pass


class Grades(Base):
    __tablename__ = "Grade"
    id = Column(Integer, autoincrement=True, primary_key=True)
    grade = Column(Text, index=True)


class School_number(Base):
    __tablename__ = "School_number"
    id = Column(Integer, autoincrement=True, primary_key=True)
    school_url = Column(String, unique=True, nullable=False, index=True)
    school_number = Column(Integer, index=True)
    place = Column(String, nullable=True)
    is_paid = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(uzb_tz))
    expire_at = Column(
        DateTime,
        default=lambda: datetime.now() + timedelta(days=365)
    )


class Captcha_ids(Base):
    __tablename__ = "Captcha_ids"
    id = Column(Integer, autoincrement=True, primary_key=True)
    captcha_id = Column(Text, unique=True, nullable=False, index=True)
    is_occupied = Column(Boolean, default=False, index=True)
    last_used = Column(DateTime(timezone=True), default=lambda: datetime.now(uzb_tz))


class User(Base):
    __tablename__ = "User"
    id = Column(Integer, autoincrement=True, primary_key=True)
    first_name = Column(String)
    username = Column(String, nullable=False)
    tg_id = Column(BigInteger, unique=True, index=True)
    role = Column(String, default="user", index=True)
    lang = Column(String, default='uz')
    grade = Column(Text, nullable=True, index=True)
    captcha_for_web = Column(Text, ForeignKey("Captcha_ids.captcha_id"), nullable=True)
    captcha_for_bot = Column(Text, ForeignKey("Captcha_ids.captcha_id"), nullable=True)
    school_id = Column(Integer, ForeignKey("School_number.id"), index=True)


class Logins(Base):
    __tablename__ = "Logins"
    id = Column(Integer, autoincrement=True, primary_key=True)
    school = Column(Integer, ForeignKey("School_number.id"), index=True)
    username = Column(String, index=True)
    password = Column(String)
    grade = Column(Text, nullable=False, index=True)
    last_cookie = Column(Text, nullable=True)
    last_login = Column(Boolean, index=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(uzb_tz))
    updated_at = Column(DateTime(timezone=True), onupdate=lambda: datetime.now(uzb_tz))


class Logins_data(Base):
    __tablename__ = "Logins_data"
    id = Column(Integer, autoincrement=True, primary_key=True)
    login_id = Column(Integer, ForeignKey("Logins.id"), index=True)
    last_cookie = Column(Text, nullable=True)
    last_login = Column(Boolean)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(uzb_tz))


TABLES = [User, School_number, Captcha_ids, Logins, Logins_data]


async def generate_unique_url(length: int = 15):
    chars = string.ascii_letters + string.digits
    ready_text = ''.join(random.choice(chars) for _ in range(length))
    b = await get_school_number(url=ready_text)
    if b:
        ready_text += random.choice(chars)
    return ready_text


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
        return backup


async def create_grades():
    async with async_session() as session:
        result = await session.execute(select(Grades).limit(1))
        if result.scalar_one_or_none():
            # Populate cache
            all_g = await session.execute(select(Grades))
            for g in all_g.scalars().all():
                _GRADE_CACHE_BY_ID[g.id] = g
                _GRADE_CACHE_BY_NAME[g.grade] = g
            return True

        for i in range(1, 12):
            for j in ["A", "B", "V", "G"]:
                new_grade = Grades(grade=f"{i}{j}")
                session.add(new_grade)
        await session.commit()

        all_g = await session.execute(select(Grades))
        for g in all_g.scalars().all():
            _GRADE_CACHE_BY_ID[g.id] = g
            _GRADE_CACHE_BY_NAME[g.grade] = g
        return True


async def get_grade(grade=None, id=None):
    if id is not None and id in _GRADE_CACHE_BY_ID:
        return _GRADE_CACHE_BY_ID[id]
    if grade and str(grade).strip() in _GRADE_CACHE_BY_NAME:
        return _GRADE_CACHE_BY_NAME[str(grade).strip()]

    async with async_session() as session:
        if id is not None:
            a = await session.execute(select(Grades).where(Grades.id == int(id)))
        elif grade:
            a = await session.execute(select(Grades).where(Grades.grade == str(grade).strip()))
        else:
            return None
        obj = a.scalar_one_or_none()
        if obj:
            _GRADE_CACHE_BY_ID[obj.id] = obj
            _GRADE_CACHE_BY_NAME[obj.grade] = obj
        return obj


async def create_user(tg_id, grade=None, first_name=None, username=None, school_id=None, role=None):
    async with async_session() as session:
        result = await session.execute(select(User).where(User.tg_id == int(tg_id)))
        existing_user = result.scalar_one_or_none()

        if existing_user:
            updated = False
            if grade:
                grade_obj = await get_grade(grade=grade)
                existing_user.grade = str(grade_obj.id) if grade_obj else str(grade)
                updated = True
            if school_id:
                existing_user.school_id = school_id
                updated = True
            if role:
                existing_user.role = role
                updated = True
            if first_name and existing_user.first_name != first_name:
                existing_user.first_name = first_name
                updated = True
            if username and existing_user.username != username:
                existing_user.username = username
                updated = True
            if updated:
                await session.commit()
            return existing_user

        grade_val = None
        if grade:
            grade_obj = await get_grade(grade=grade)
            grade_val = str(grade_obj.id) if grade_obj else str(grade)

        new_user = User(
            tg_id=int(tg_id),
            first_name=first_name or "",
            username=username or "",
            school_id=school_id,
            grade=grade_val,
            role=role or "user"
        )
        session.add(new_user)
        await session.commit()
        return new_user


async def get_logins_grade_for_web(logins):
    if not logins:
        return {}
    login_ids = []
    for i in logins:
        try:
            login_ids.append(int(i))
        except (ValueError, TypeError):
            continue
    if not login_ids:
        return {}

    # Check cache first
    result = {}
    missing_ids = []
    for lid in login_ids:
        if lid in _GRADE_CACHE_BY_ID:
            result[lid] = _GRADE_CACHE_BY_ID[lid].grade
        else:
            missing_ids.append(lid)

    if missing_ids:
        async with async_session() as session:
            db_res = await session.execute(
                select(Grades).where(Grades.id.in_(missing_ids))
            )
            for g in db_res.scalars().all():
                _GRADE_CACHE_BY_ID[g.id] = g
                _GRADE_CACHE_BY_NAME[g.grade] = g
                result[g.id] = g.grade

    return result


async def update_user(Tg_id, school_url):
    async with async_session() as session:
        a = await session.execute(select(User).where(User.tg_id == Tg_id))
        r = a.scalar_one_or_none()
        school_id = await get_school_number(url=school_url)
        if not school_id or not r:
            return False
        r.school_id = school_id.id
        await session.commit()
        return school_id


async def create_school(school_number, place, days, edit=False):
    async with async_session() as session:
        a = await session.execute(
            select(School_number).where(
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
            _SCHOOL_CACHE_BY_ID[r.id] = r
            _SCHOOL_CACHE_BY_URL[r.school_url] = r
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
        _SCHOOL_CACHE_BY_ID[new_school.id] = new_school
        _SCHOOL_CACHE_BY_URL[new_school.school_url] = new_school
        return new_school


async def get_school_number(url=None, id=None):
    if id is not None and id in _SCHOOL_CACHE_BY_ID:
        return _SCHOOL_CACHE_BY_ID[id]
    if url and url in _SCHOOL_CACHE_BY_URL:
        return _SCHOOL_CACHE_BY_URL[url]

    async with async_session() as session:
        if url:
            stmt = select(School_number).where(School_number.school_url == url)
        elif id is not None:
            try:
                stmt = select(School_number).where(School_number.id == int(id))
            except (ValueError, TypeError):
                return None
        else:
            return None
        a = await session.execute(stmt)
        obj = a.scalar_one_or_none()
        if obj:
            _SCHOOL_CACHE_BY_ID[obj.id] = obj
            _SCHOOL_CACHE_BY_URL[obj.school_url] = obj
        return obj


async def get_free_captcha():
    async with async_session() as session:
        stmt = select(Captcha_ids.captcha_id).where(Captcha_ids.is_occupied == False).limit(1)
        res = await session.execute(stmt)
        cid = res.scalar_one_or_none()
        if cid:
            return cid
    try:
        from captcha_finder import get_live_captcha_id
        return await get_live_captcha_id()
    except Exception:
        return None


async def create_captcha_ids(captcha_id):
    async with async_session() as session:
        a = await session.execute(select(Captcha_ids).where(Captcha_ids.captcha_id == captcha_id))
        if a.scalar_one_or_none():
            return False
        session.add(Captcha_ids(captcha_id=captcha_id))
        await session.commit()
        return True


async def update_captcha_id(captcha_id):
    async with async_session() as session:
        a = await session.execute(select(Captcha_ids).where(Captcha_ids.captcha_id == captcha_id))
        r = a.scalar_one_or_none()
        if r:
            r.last_used = datetime.now(uzb_tz)
            r.is_occupied = True
            await session.commit()
            return True
        return False


async def add_captcha_id(captcha_id, tg_id, is_bot):
    async with async_session() as session:
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


async def create_login(password, username, last_login, cookie, grade: str = "", school_number_id=None, tg_id=None):
    async with async_session() as session:
        a = await session.execute(select(Logins).where(Logins.username == username))
        r = a.scalar_one_or_none()
        if r:
            r.password = password
            r.last_cookie = cookie
            if grade:
                r.grade = grade
            r.last_login = last_login
            await session.commit()
            return False

        school = school_number_id
        if tg_id:
            u_res = await session.execute(select(User).where(User.tg_id == int(tg_id)))
            user = u_res.scalar_one_or_none()
            if user:
                if not school:
                    school = user.school_id
                if not grade and user.grade:
                    grade = user.grade

        new_login = Logins(
            password=password,
            username=username,
            last_login=last_login,
            last_cookie=cookie,
            school=school,
            grade=grade or "1A"
        )
        session.add(new_login)
        await session.commit()
        return True


async def get_all_users():
    async with async_session() as session:
        r = await session.execute(select(User))
        return r.scalars().all()


async def give_captcha_100(id=None):
    async with async_session() as session:
        stmt = select(Captcha_ids.captcha_id).order_by(func.random()).limit(1)
        result = await session.execute(stmt)
        captcha = result.scalar_one_or_none()
        if captcha:
            return captcha
    try:
        from captcha_finder import get_live_captcha_id
        return await get_live_captcha_id()
    except Exception:
        return "f61a11f3-1cee-448c-ad2b-fd2eee8f9b2d"


async def create_logins_data(login_id, last_login, last_cookie):
    async with async_session() as session:
        new_logins_data = Logins_data(login_id=login_id, last_login=last_login, last_cookie=last_cookie)
        session.add(new_logins_data)
        await session.commit()
        return True


async def bulk_create_logins_data(items: list[dict]):
    """High-speed batch insert of login history in a single transaction."""
    if not items:
        return True
    async with async_session() as session:
        records = [
            Logins_data(
                login_id=item["login_id"],
                last_login=item["last_login"],
                last_cookie=item["last_cookie"]
            )
            for item in items
        ]
        session.add_all(records)
        await session.commit()
        return True


async def get_all_logins(school2=None, grade=None):
    async with async_session() as session:
        if school2:
            if grade:
                stmt = select(Logins).where(
                    and_(
                        Logins.school == int(school2),
                        Logins.grade == str(grade)
                    )
                )
            else:
                stmt = select(Logins).where(Logins.school == int(school2))
        else:
            stmt = select(Logins)
        a = await session.execute(stmt)
        return a.scalars().all()


async def update_logins(login_id, last_login, last_cookie, password=None):
    async with async_session() as session:
        a = await session.execute(select(Logins).where(Logins.id == login_id))
        r = a.scalar_one_or_none()
        if r:
            if password:
                r.password = password
            r.last_cookie = last_cookie
            r.last_login = last_login
            await session.commit()
            return True
        return False


async def bulk_update_logins(items: list[dict]):
    """High-speed batch update of logins in a single transaction."""
    if not items:
        return True
    async with async_session() as session:
        for item in items:
            lid = item.get("login_id")
            if not lid:
                continue
            a = await session.execute(select(Logins).where(Logins.id == lid))
            r = a.scalar_one_or_none()
            if r:
                r.last_login = item["last_login"]
                r.last_cookie = item["last_cookie"]
                if "password" in item and item["password"]:
                    r.password = item["password"]
        await session.commit()
        return True


async def get_all_captcha():
    async with async_session() as session:
        a = await session.execute(select(func.count(Captcha_ids.id)))
        return a.scalar() or 0


async def create_or_change_user_role(user_tg, role='admin'):
    async with async_session() as session:
        a = await session.execute(select(User).where(User.tg_id == user_tg))
        r = a.scalar_one_or_none()
        if r:
            r.role = role
            await session.commit()
            return True
        return False


async def get_all_schools(only_exist=False):
    async with async_session() as session:
        a = await session.execute(select(School_number))
        schools = a.scalars().all()
        for s in schools:
            _SCHOOL_CACHE_BY_ID[s.id] = s
            _SCHOOL_CACHE_BY_URL[s.school_url] = s
        return schools


async def init():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await create_grades()
    await get_all_schools()


async def add_captchas_by():
    if not os.path.exists("output.txt"):
        return
    with open("output.txt", "r") as f:
        for line in f:
            value = line.strip()
            if value:
                await create_captcha_ids(value)


async def create_database_back_up():
    data = await get_all_Database()
    with open('database.json', 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4, default=str)
        return True


async def main():
    await init()


if __name__ == "__main__":
    import sys
    if sys.platform.startswith("win"):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    try:
        asyncio.run(main())
    except RuntimeError as e:
        if "Event loop is closed" not in str(e):
            raise
