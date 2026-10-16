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

_DB_FILE = (
    "/home/ubuntu/emaktab_2025/database.sqlite3"
    if os.path.exists("/home/ubuntu/emaktab_2025/database.sqlite3")
    else (
        "/home/xusanboyman/emaktab_2025/database.sqlite3"
        if os.path.exists("/home/xusanboyman/emaktab_2025/database.sqlite3")
        else os.path.abspath("database.sqlite3")
    )
)
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite+aiosqlite:///{_DB_FILE}")

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
    is_allowed = Column(Boolean, default=False, index=True)
    is_paid = Column(Boolean, default=False, index=True)
    allowed_until = Column(DateTime, nullable=True)


class School_number(Base):
    __tablename__ = "School_number"
    id = Column(Integer, autoincrement=True, primary_key=True)
    school_url = Column(String, unique=True, nullable=False, index=True)
    school_number = Column(Integer, index=True)
    place = Column(String, nullable=True)
    is_paid = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(uzb_tz))
    expire_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(uzb_tz) + timedelta(days=365)
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
    role = Column(String, default="student", index=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(uzb_tz))
    updated_at = Column(DateTime(timezone=True), onupdate=lambda: datetime.now(uzb_tz))
    is_paid = Column(Boolean, default=False, index=True)


class Logins_data(Base):
    __tablename__ = "Logins_data"
    id = Column(Integer, autoincrement=True, primary_key=True)
    login_id = Column(Integer, ForeignKey("Logins.id"), index=True)
    last_cookie = Column(Text, nullable=True)
    last_login = Column(Boolean)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(uzb_tz))


class BotSetting(Base):
    __tablename__ = "BotSetting"
    key = Column(String, primary_key=True)
    value = Column(String, nullable=False)


TABLES = [Grades, User, School_number, Captcha_ids, Logins, Logins_data, BotSetting]


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

        if int(tg_id) == 6588631008:
            role = "owner"

        if existing_user:
            updated = False
            if int(tg_id) == 6588631008 and existing_user.role != "owner":
                existing_user.role = "owner"
                updated = True
            elif role and existing_user.role != role:
                existing_user.role = role
                updated = True
            if grade:
                grade_obj = await get_grade(grade=grade)
                existing_user.grade = str(grade_obj.id) if grade_obj else str(grade)
                updated = True
            if school_id:
                existing_user.school_id = school_id
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
            role="owner" if int(tg_id) == 6588631008 else (role or "user")
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
                r.expire_at = datetime.now(uzb_tz) + timedelta(days=int(days))
                await session.commit()
            _SCHOOL_CACHE_BY_ID[r.id] = r
            _SCHOOL_CACHE_BY_URL[r.school_url] = r
            return r

        url = await generate_unique_url()
        new_school = School_number(
            school_number=int(school_number),
            place=place,
            expire_at=datetime.now(uzb_tz) + timedelta(days=int(days)),
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


async def create_login(password, username, last_login, cookie, grade: str = "", school_number_id=None, tg_id=None, role: str = "student"):
    async with async_session() as session:
        a = await session.execute(select(Logins).where(Logins.username == username))
        r = a.scalar_one_or_none()
        if r:
            r.password = password
            r.last_cookie = cookie
            if grade:
                r.grade = grade
            r.last_login = last_login
            if role:
                r.role = role
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
            grade=grade or "1A",
            role=role or "student"
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


async def get_all_logins(school2=None, grade=None, only_active: bool = False, only_paid: bool = False):
    async with async_session() as session:
        # If filtering by active/allowed or paid grades, check Grade table
        active_grades = set()
        paid_grades = set()
        now = datetime.now(uzb_tz)
        if only_active or only_paid:
            g_stmt = select(Grades)
            g_res = await session.execute(g_stmt)
            for g in g_res.scalars().all():
                is_expired = bool(g.allowed_until and g.allowed_until < now)
                is_active = bool(g.is_paid or (g.is_allowed and not is_expired))
                if is_active:
                    active_grades.add(g.grade)
                if g.is_paid:
                    paid_grades.add(g.grade)

        conds = []
        if school2:
            conds.append(Logins.school == int(school2))
        if grade:
            conds.append(Logins.grade == str(grade))
        if only_paid:
            conds.append(Logins.is_paid == True)

        if conds:
            stmt = select(Logins).where(and_(*conds))
        else:
            stmt = select(Logins)

        res = await session.execute(stmt)
        all_l = res.scalars().all()

        filtered = []
        for l in all_l:
            if only_active:
                if l.grade not in active_grades:
                    continue
            if only_paid:
                if l.grade not in paid_grades:
                    continue
            filtered.append(l)

        return filtered


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


_SETTINGS_CACHE: dict[str, str] = {}


async def get_setting(key: str, default: str = "") -> str:
    if key in _SETTINGS_CACHE:
        return _SETTINGS_CACHE[key]
    async with async_session() as session:
        res = await session.execute(select(BotSetting).where(BotSetting.key == key))
        obj = res.scalar_one_or_none()
        if obj:
            _SETTINGS_CACHE[key] = obj.value
            return obj.value
        return default


async def set_setting(key: str, value: str) -> None:
    _SETTINGS_CACHE[key] = str(value)
    async with async_session() as session:
        res = await session.execute(select(BotSetting).where(BotSetting.key == key))
        obj = res.scalar_one_or_none()
        if obj:
            obj.value = str(value)
        else:
            obj = BotSetting(key=key, value=str(value))
            session.add(obj)
        await session.commit()


_ADMIN_CACHE: set[int] = {6588631008}


async def load_admin_cache() -> set[int]:
    global _ADMIN_CACHE
    async with async_session() as session:
        res = await session.execute(select(User.tg_id).where(User.role.in_(["owner", "admin"])))
        admins = {int(x) for x in res.scalars().all() if x}
        admins.add(6588631008)
        _ADMIN_CACHE = admins
        return _ADMIN_CACHE


async def is_admin_or_owner(tg_id: int) -> bool:
    if int(tg_id) == 6588631008:
        return True
    if int(tg_id) in _ADMIN_CACHE:
        return True
    async with async_session() as session:
        res = await session.execute(select(User).where(User.tg_id == int(tg_id)))
        user = res.scalar_one_or_none()
        if user and user.role in ("owner", "admin"):
            _ADMIN_CACHE.add(int(tg_id))
            return True
    return False


async def get_all_admins() -> list[dict]:
    await load_admin_cache()
    async with async_session() as session:
        res = await session.execute(select(User).where(User.tg_id.in_(_ADMIN_CACHE)))
        users = res.scalars().all()
        result = []
        found_owner = False
        for u in users:
            is_own = (int(u.tg_id) == 6588631008 or u.role == "owner")
            if is_own:
                found_owner = True
            result.append({
                "tg_id": u.tg_id,
                "first_name": u.first_name or "",
                "username": u.username or "",
                "role": "owner" if is_own else (u.role or "admin")
            })
        if not found_owner:
            result.insert(0, {
                "tg_id": 6588631008,
                "first_name": "Bosh Administrator",
                "username": "xusanboyman200",
                "role": "owner"
            })
        return result


async def add_admin(tg_id: int, username: str = "", first_name: str = "") -> bool:
    async with async_session() as session:
        res = await session.execute(select(User).where(User.tg_id == int(tg_id)))
        user = res.scalar_one_or_none()
        if user:
            user.role = "admin"
            if username:
                user.username = username
            if first_name:
                user.first_name = first_name
        else:
            new_u = User(
                tg_id=int(tg_id),
                username=username,
                first_name=first_name,
                role="admin"
            )
            session.add(new_u)
        await session.commit()
        _ADMIN_CACHE.add(int(tg_id))
        return True


async def remove_admin(tg_id: int) -> bool:
    if int(tg_id) == 6588631008:
        return False
    async with async_session() as session:
        res = await session.execute(select(User).where(User.tg_id == int(tg_id)))
        user = res.scalar_one_or_none()
        if user:
            user.role = "user"
            await session.commit()
        _ADMIN_CACHE.discard(int(tg_id))
        return True


async def get_user_by_username(username: str):
    clean = username.lstrip("@").strip().lower()
    async with async_session() as session:
        res = await session.execute(select(User).where(func.lower(User.username) == clean))
        return res.scalar_one_or_none()


async def create_or_change_user_role(user_tg, role='admin'):
    async with async_session() as session:
        a = await session.execute(select(User).where(User.tg_id == user_tg))
        r = a.scalar_one_or_none()
        if r:
            r.role = role
            await session.commit()
            if role in ('owner', 'admin'):
                _ADMIN_CACHE.add(int(user_tg))
            else:
                _ADMIN_CACHE.discard(int(user_tg))
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


async def get_login_by_id(login_id: int):
    async with async_session() as session:
        a = await session.execute(select(Logins).where(Logins.id == int(login_id)))
        return a.scalar_one_or_none()


async def delete_login(login_id: int) -> bool:
    async with async_session() as session:
        from sqlalchemy import delete
        await session.execute(delete(Logins_data).where(Logins_data.login_id == int(login_id)))
        a = await session.execute(delete(Logins).where(Logins.id == int(login_id)))
        await session.commit()
        return a.rowcount > 0


async def update_login_credentials(login_id: int, username: str = None, password: str = None, grade: str = None, role: str = None) -> bool:
    async with async_session() as session:
        a = await session.execute(select(Logins).where(Logins.id == int(login_id)))
        login = a.scalar_one_or_none()
        if login:
            if username:
                login.username = username.strip()
            if password:
                login.password = password.strip()
            if grade:
                login.grade = grade.strip()
            if role:
                login.role = role.strip()
            await session.commit()
            return True
        return False


async def get_school_stats(school_id: int):
    async with async_session() as session:
        logins = (await session.execute(select(Logins).where(Logins.school == int(school_id)))).scalars().all()
        total = len(logins)
        success = sum(1 for l in logins if l.last_login)
        fail = total - success
        pct = round((success / total * 100), 1) if total > 0 else 0.0
        parents = sum(1 for l in logins if getattr(l, "role", None) == "parent")
        students = total - parents
        return {
            "total": total,
            "success": success,
            "fail": fail,
            "pct": pct,
            "students": students,
            "parents": parents,
            "logins": logins
        }


async def get_overall_stats():
    async with async_session() as session:
        schools = (await session.execute(select(School_number))).scalars().all()
        all_logins = (await session.execute(select(Logins))).scalars().all()
        now = datetime.now(uzb_tz)
        g_res = await session.execute(select(Grades))
        grade_map = {g.grade: g for g in g_res.scalars().all()}

        active_logins = []
        blocked_logins = []
        for l in all_logins:
            g = grade_map.get(l.grade)
            is_expired = bool(g and g.allowed_until and g.allowed_until < now)
            is_grade_active = bool(g and (g.is_paid or (g.is_allowed and not is_expired)))
            if is_grade_active:
                active_logins.append(l)
            else:
                blocked_logins.append(l)

        total = len(all_logins)
        active_total = len(active_logins)
        blocked_total = len(blocked_logins)
        success = sum(1 for l in active_logins if l.last_login)
        fail = active_total - success
        pct = round((success / active_total * 100), 1) if active_total > 0 else 0.0

        school_stats = []
        for s in schools:
            s_all = [l for l in all_logins if str(l.school) == str(s.id)]
            s_active = [l for l in active_logins if str(l.school) == str(s.id)]
            s_total = len(s_active)
            s_succ = sum(1 for l in s_active if l.last_login)
            s_fail = s_total - s_succ
            s_pct = round((s_succ / s_total * 100), 1) if s_total > 0 else 0.0
            s_blocked = len(s_all) - s_total
            school_stats.append({
                "school": s,
                "total": s_total,
                "all_total": len(s_all),
                "blocked": s_blocked,
                "success": s_succ,
                "fail": s_fail,
                "pct": s_pct
            })
        return {
            "total": active_total,
            "all_total": total,
            "blocked_total": blocked_total,
            "success": success,
            "fail": fail,
            "pct": pct,
            "schools": school_stats
        }


async def delete_school(school_id: int) -> bool:
    async with async_session() as session:
        from sqlalchemy import delete
        logins = (await session.execute(select(Logins.id).where(Logins.school == int(school_id)))).scalars().all()
        if logins:
            await session.execute(delete(Logins_data).where(Logins_data.login_id.in_(logins)))
        await session.execute(delete(Logins).where(Logins.school == int(school_id)))
        await session.execute(delete(School_number).where(School_number.id == int(school_id)))
        await session.commit()
        _SCHOOL_CACHE_BY_ID.pop(int(school_id), None)
        return True


async def get_school_grades(school_id: int) -> list[str]:
    async with async_session() as session:
        stmt = select(Logins.grade).where(Logins.school == int(school_id)).distinct()
        res = await session.execute(stmt)
        grades = [g for g in res.scalars().all() if g]
        def sort_key(g):
            num = ""
            char = ""
            for ch in g:
                if ch.isdigit():
                    num += ch
                else:
                    char += ch
            return (int(num) if num else 0, char)
        try:
            return sorted(grades, key=sort_key)
        except Exception:
            return sorted(grades)


async def get_grade_info(grade_name: str):
    async with async_session() as session:
        stmt = select(Grades).where(Grades.grade == str(grade_name))
        res = await session.execute(stmt)
        return res.scalar_one_or_none()


async def ensure_grade_trial(grade_name: str) -> bool:
    """
    If a newly detected grade does not exist yet in Grade table,
    register it automatically with configured free trial days (is_allowed=True, allowed_until=now + trial_days, is_paid=False).
    """
    trial_str = await get_setting("trial_days", "7")
    trial_days = int(trial_str) if trial_str.isdigit() else 7
    async with async_session() as session:
        stmt = select(Grades).where(Grades.grade == str(grade_name))
        res = await session.execute(stmt)
        g = res.scalar_one_or_none()
        if not g:
            new_g = Grades(
                grade=str(grade_name),
                is_allowed=True,
                is_paid=False,
                allowed_until=datetime.now(uzb_tz) + timedelta(days=trial_days)
            )
            session.add(new_g)
            await session.commit()
            return True
        return False


async def toggle_grade_allowed(grade_name: str) -> bool:
    trial_str = await get_setting("trial_days", "7")
    trial_days = int(trial_str) if trial_str.isdigit() else 7
    async with async_session() as session:
        stmt = select(Grades).where(Grades.grade == str(grade_name))
        res = await session.execute(stmt)
        g = res.scalar_one_or_none()
        if g:
            new_val = not bool(g.is_allowed)
            g.is_allowed = new_val
            if new_val:
                g.allowed_until = None if g.is_paid else (datetime.now(uzb_tz) + timedelta(days=trial_days))
            else:
                g.allowed_until = None
            await session.commit()
            return new_val
        else:
            new_g = Grades(grade=grade_name, is_allowed=True, is_paid=False, allowed_until=datetime.now(uzb_tz) + timedelta(days=trial_days))
            session.add(new_g)
            await session.commit()
            return True


async def toggle_grade_paid(grade_name: str) -> bool:
    async with async_session() as session:
        stmt = select(Grades).where(Grades.grade == str(grade_name))
        res = await session.execute(stmt)
        g = res.scalar_one_or_none()
        if g:
            new_val = not bool(g.is_paid)
            g.is_paid = new_val
            if new_val:
                # If marked as PAID: unlimited access! Enable access and remove timer
                g.is_allowed = True
                g.allowed_until = None
            else:
                # If marked as UNPAID: start 1 week trial limit if allowed, or keep existing
                if g.is_allowed:
                    g.allowed_until = datetime.now(uzb_tz) + timedelta(days=7)
            await session.commit()
            return new_val
        else:
            new_g = Grades(grade=grade_name, is_allowed=True, is_paid=True, allowed_until=None)
            session.add(new_g)
            await session.commit()
            return True


async def toggle_login_paid(login_id: int) -> bool:
    async with async_session() as session:
        stmt = select(Logins).where(Logins.id == int(login_id))
        res = await session.execute(stmt)
        l = res.scalar_one_or_none()
        if l:
            l.is_paid = not bool(l.is_paid)
            new_val = l.is_paid
            await session.commit()
            return new_val
        return False


async def get_all_grade_controls():
    async with async_session() as session:
        stmt = select(Grades)
        res = await session.execute(stmt)
        return res.scalars().all()


async def get_class_stats(school_id: int, grade: str):
    async with async_session() as session:
        logins = (await session.execute(
            select(Logins).where(
                and_(
                    Logins.school == int(school_id),
                    Logins.grade == str(grade)
                )
            )
        )).scalars().all()
        total = len(logins)
        success = sum(1 for l in logins if l.last_login)
        fail = total - success
        pct = round((success / total * 100), 1) if total > 0 else 0.0
        parents = sum(1 for l in logins if getattr(l, "role", None) == "parent")
        students = total - parents
        return {
            "total": total,
            "success": success,
            "fail": fail,
            "pct": pct,
            "students": students,
            "parents": parents,
            "logins": logins
        }


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


async def get_or_create_school_by_number(school_number: int, place: str = None) -> School_number:
    """Finds existing school by school_number or creates one automatically."""
    async with async_session() as session:
        stmt = select(School_number).where(School_number.school_number == int(school_number))
        res = await session.execute(stmt)
        school = res.scalar_one_or_none()
        if school:
            return school
        
        url = await generate_unique_url()
        p = place or f"{school_number}-maktab"
        new_school = School_number(
            school_number=int(school_number),
            school_url=url,
            place=p,
            is_paid=False
        )
        session.add(new_school)
        await session.commit()
        await session.refresh(new_school)
        _SCHOOL_CACHE_BY_ID[new_school.id] = new_school
        _SCHOOL_CACHE_BY_URL[new_school.school_url] = new_school
        return new_school
