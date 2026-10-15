#!/usr/bin/env python3
"""
eMaktab Automation Pipeline:
1. Teacher authentication via schools.emaktab.uz with dynamic school discovery
2. Class roster & parent extraction
3. Password reset trigger (Joriy parolni o'chirish)
4. Temporary password extraction
5. Activation / New password set
6. Remote SQLite DB sync
"""

import re
import sys
import sqlite3
import requests
from bs4 import BeautifulSoup

DEFAULT_SCHOOL_ID = "1000006479820"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/155.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "uz-UZ,uz;q=0.9,en-US;q=0.8",
}

KNOWN_PROTECTED_TEACHERS = [
    "To'xtasinova Farida",
    "Orziqulova Muxayyo",
    "Abdunazarova Ominaxon",
    "Masharipova Farida",
    "Xaydarova Manzuraxon",
    "Norov Fayoziddin",
    "Maxammatova Dilnoza",
    "Qurbonova Nargiza",
    "Xoshimova Achaxon",
    "Kamolova Yorkinoy",
]

def clean_uz_name_tokens(text):
    if not text:
        return []
    s = str(text).lower()
    replacements = [
        ('ў', 'o'), ('ғ', 'g'), ('қ', 'q'), ('ҳ', 'h'),
        ('ч', 'ch'), ('ш', 'sh'), ('щ', 'sh'), ('ё', 'yo'),
        ('ю', 'yu'), ('я', 'ya'), ('ц', 'ts'), ('э', 'e'),
        ('а', 'a'), ('б', 'b'), ('в', 'v'), ('г', 'g'), ('д', 'd'),
        ('е', 'e'), ('ж', 'j'), ('з', 'z'), ('и', 'i'), ('й', 'y'),
        ('к', 'k'), ('л', 'l'), ('м', 'm'), ('н', 'n'), ('о', 'o'),
        ('п', 'p'), ('р', 'r'), ('с', 's'), ('т', 't'), ('у', 'u'),
        ('ф', 'f'), ('х', 'x'), ('ы', 'i'), ('ъ', ''), ('ь', '')
    ]
    for cyr, lat in replacements:
        s = s.replace(cyr, lat)
    s = re.sub(r"['`’ʻʼ]", '', s)
    tokens = [re.sub(r'[^a-z0-9]', '', w) for w in re.split(r'\s+', s)]
    return [t for t in tokens if len(t) >= 3]

def check_name_is_teacher(candidate_name, teacher_tokens_list):
    c_tokens = set(clean_uz_name_tokens(candidate_name))
    if not c_tokens:
        return False
    for t_tokens in teacher_tokens_list:
        common = c_tokens.intersection(t_tokens)
        if len(common) >= 2:
            return True
        if len(c_tokens) == 1 and len(t_tokens) == 1 and common:
            return True
        for tok in common:
            if len(tok) >= 8:
                return True
    return False

class EMaktabResetter:
    def __init__(self, school_id=DEFAULT_SCHOOL_ID):
        self.school_id = school_id
        self.school_name = "Maktab"
        self.teacher_username = ""
        self.teacher_password = ""
        self.teacher_user_id = ""
        self.school_teacher_uids = set()
        self.school_teacher_pids = set()
        self.school_teacher_names = set()
        self.teacher_token_sets = []
        self.protected_teacher_logins = set()
        self.session = requests.Session()
        self.session.headers.update(HEADERS)

        # Pre-seed protected teachers
        for t in KNOWN_PROTECTED_TEACHERS:
            toks = set(clean_uz_name_tokens(t))
            if toks and toks not in self.teacher_token_sets:
                self.teacher_token_sets.append(toks)
            self.school_teacher_names.add(self.normalize_name(t))

    @staticmethod
    def normalize_name(name):
        if not name:
            return ""
        tokens = clean_uz_name_tokens(name)
        return "".join(tokens)

    def is_teacher_account(self, person_id=None, user_id=None, login=None, role_text=None, name=None):
        """Strict multi-tier check to guarantee teacher immunity."""
        if login:
            l_clean = str(login).strip().lower()
            if self.teacher_username and l_clean == self.teacher_username.lower():
                return True
            if l_clean in self.protected_teacher_logins:
                return True
        if user_id:
            u_clean = str(user_id).strip()
            if u_clean in self.school_teacher_uids:
                return True
            if self.teacher_user_id and u_clean == str(self.teacher_user_id):
                return True
        if person_id:
            p_clean = str(person_id).strip()
            if p_clean in self.school_teacher_pids:
                return True
        if name:
            if check_name_is_teacher(name, self.teacher_token_sets):
                return True
            norm_name = self.normalize_name(name)
            if norm_name and norm_name in self.school_teacher_names:
                return True
            for t_norm in self.school_teacher_names:
                if len(norm_name) >= 7 and (norm_name in t_norm or t_norm in norm_name):
                    return True
        if role_text:
            rt = str(role_text).lower()
            if any(k in rt for k in ["o‘qituvchi", "o'qituvchi", "xodim", "direktor", "administrator", "zamdirektor", "boshqaruvchi", "psixolog", "kutubxonachi"]):
                return True
        return False

    def login_teacher(self, username, password):
        login_url = "https://login.emaktab.uz/"
        data = {
            "exceededAttempts": "False",
            "ReturnUrl": "https://schools.emaktab.uz/v2/school",
            "FingerprintId": "f32ca74923772137f61e061adaec9982",
            "login": username,
            "password": password,
            "Captcha.Input": "",
            "Captcha.Id": ""
        }
        resp = self.session.post(login_url, data=data, allow_redirects=True, timeout=15)
        cookies = self.session.cookies.get_dict()
        if "UZDnevnikAuth_a" not in cookies and "UZDnevnikAuth" not in str(self.session.cookies):
            raise RuntimeError("Teacher login failed: noto'g'ri login yoki parol.")

        self.teacher_username = username.strip().lower()
        self.teacher_password = password
        self.protected_teacher_logins.add(username.strip().lower())

        # Discover school ID from redirect URL or page
        m = re.search(r"school=(\d+)", resp.url)
        if m:
            self.school_id = m.group(1)
        else:
            sch_resp = self.session.get("https://schools.emaktab.uz/v2/school", allow_redirects=True, timeout=15)
            m = re.search(r"school=(\d+)", sch_resp.url)
            if m:
                self.school_id = m.group(1)
            resp = sch_resp

        # Discover school title
        soup = BeautifulSoup(resp.text, "html.parser")
        title = soup.find("h1") or soup.find("title")
        if title:
            raw_title = title.text.strip().replace(" - eMaktab", "").replace(" - Дневnik", "")
            self.school_name = raw_title

        # Find teacher user ID and cache all school teachers
        try:
            m_user = re.search(r"/v2/user/user\?user=(\d+)", resp.text)
            if m_user:
                self.teacher_user_id = m_user.group(1)
                self.school_teacher_uids.add(str(self.teacher_user_id))
        except Exception:
            self.teacher_user_id = ""

        self.school_teacher_uids = self.get_school_teacher_uids()
        return True

    def get_school_teacher_uids(self):
        """Fetches and caches all teacher user IDs and names in the school to prevent resetting them as parents."""
        teacher_uids = set()
        if getattr(self, "teacher_user_id", None):
            teacher_uids.add(str(self.teacher_user_id))
        try:
            for page in range(1, 20):
                url = f"https://schools.emaktab.uz/v2/school?school={self.school_id}&view=members&group=teachers&page={page}"
                res = self.session.get(url, timeout=10)
                soup = BeautifulSoup(res.text, "html.parser")
                t = soup.find("table")
                if not t:
                    break
                rows = t.find_all("tr")
                found_in_page = False
                for tr in rows:
                    links = tr.find_all("a", href=lambda h: h and "/v2/user/user?" in h)
                    if links:
                        found_in_page = True
                        uid = links[0]["href"].split("user=")[1].split("&")[0]
                        teacher_uids.add(str(uid))
                        names_found = []
                        for lk in links:
                            txt = lk.text.strip()
                            if txt:
                                names_found.append(txt)
                            tit = lk.get("title", "").strip()
                            if tit:
                                names_found.append(tit)
                        for t_name in names_found:
                            toks = set(clean_uz_name_tokens(t_name))
                            if toks and toks not in self.teacher_token_sets:
                                self.teacher_token_sets.append(toks)
                            norm = self.normalize_name(t_name)
                            if norm:
                                self.school_teacher_names.add(norm)
                if not found_in_page:
                    break
        except Exception as e:
            print(f"Error caching teacher uids: {e}")
        return teacher_uids

    def get_teacher_classes(self):
        """Fetches all classes accessible to the teacher."""
        url = f"https://schools.emaktab.uz/v2/myclasses?school={self.school_id}"
        resp = self.session.get(url, timeout=15)
        soup = BeautifulSoup(resp.text, "html.parser")
        classes = []
        for a in soup.find_all("a", href=True):
            if "/v2/class?" in a["href"] and "class=" in a["href"]:
                cid = a["href"].split("class=")[1].split("&")[0]
                name = a.text.strip()
                if name and cid and not any(c["class_id"] == cid for c in classes):
                    classes.append({"name": name, "class_id": cid})

        # If none in myclasses, check school classes list
        if not classes:
            s_url = f"https://schools.emaktab.uz/v2/school?school={self.school_id}&view=classes"
            s_resp = self.session.get(s_url, timeout=15)
            s_soup = BeautifulSoup(s_resp.text, "html.parser")
            for a in s_soup.find_all("a", href=True):
                if "/v2/class?" in a["href"] and "class=" in a["href"]:
                    cid = a["href"].split("class=")[1].split("&")[0]
                    name = a.text.strip()
                    if name and cid and not any(c["class_id"] == cid for c in classes):
                        classes.append({"name": name, "class_id": cid})
        return classes

    def get_teacher_classes_with_counts(self):
        """
        Fetches all classes accessible to the teacher along with accurate
        student and parent counts (excluding ANY teacher from the school).
        """
        import re
        from concurrent.futures import ThreadPoolExecutor
        from bs4 import BeautifulSoup

        classes = self.get_teacher_classes()

        if not hasattr(self, 'school_teacher_uids') or not self.school_teacher_uids:
            self.school_teacher_uids = self.get_school_teacher_uids()

        def fetch_counts(c):
            cid = c['class_id']
            s_cnt = 0
            p_cnt = 0
            try:
                # 1. Students count
                s_res = self.session.get(f'https://schools.emaktab.uz/v2/class?class={cid}&view=members', timeout=10)
                s_soup = BeautifulSoup(s_res.text, 'html.parser')
                s_table = s_soup.find('table')
                if s_table:
                    for tr in s_table.find_all('tr'):
                        if tr.find('a', href=lambda h: h and '/v2/user/user?' in h):
                            s_cnt += 1

                # 2. Parents count (excluding ANY teacher from the school)
                p_res = self.session.get(f'https://schools.emaktab.uz/v2/class?class={cid}&view=members&group=parents', timeout=10)
                p_soup = BeautifulSoup(p_res.text, 'html.parser')
                p_table = p_soup.find('table')
                if p_table:
                    for tr in p_table.find_all('tr'):
                        if tr.find('th'):
                            continue
                        links = tr.find_all('a', href=lambda h: h and '/v2/user/user?' in h)
                        if links:
                            parent_uid = links[0]['href'].split('user=')[1].split('&')[0]
                            if parent_uid in self.school_teacher_uids:
                                continue
                            p_cnt += 1
            except Exception as e:
                print(f"Error fetching counts for class {cid}: {e}")

            total = s_cnt + p_cnt
            label = f"{c['name']} ({s_cnt}+{p_cnt})={total}" if (s_cnt or p_cnt) else c['name']
            return {
                'name': c['name'],
                'class_id': str(cid),
                'students_count': s_cnt,
                'parents_count': p_cnt,
                'total': total,
                'label': label
            }

        with ThreadPoolExecutor(max_workers=8) as ex:
            enriched_classes = list(ex.map(fetch_counts, classes))

        return enriched_classes

    def get_class_members(self, class_id):
        url = f"https://schools.emaktab.uz/v2/class?class={class_id}&view=members"
        resp = self.session.get(url, timeout=15)
        soup = BeautifulSoup(resp.text, "html.parser")
        table = soup.find("table")
        if not table:
            return []

        students = []
        for tr in table.find_all("tr"):
            link = tr.find("a", href=lambda h: h and "person=" in h and "view=review" in h)
            if link:
                m = re.search(r"person=(\d+)", link["href"])
                if m:
                    pid = m.group(1)
                    tds = tr.find_all("td")
                    name = tds[1].text.strip() if len(tds) > 1 else link.text.strip()
                    students.append({"person_id": pid, "name": name, "retgroup": class_id})
        return students

    def get_class_parents(self, class_id):
        """
        Fetches all parents for a class, STRICTLY excluding any teacher accounts.
        """
        url = f"https://schools.emaktab.uz/v2/class?class={class_id}&view=members&group=parents"
        try:
            resp = self.session.get(url, timeout=15)
            soup = BeautifulSoup(resp.text, "html.parser")
            table = soup.find("table")
            if not table:
                return []

            parents = []
            seen_pids = set()
            for tr in table.find_all("tr"):
                if tr.find("th"):
                    continue
                links = tr.find_all("a", href=lambda h: h and "/v2/user/user?" in h)
                if not links:
                    continue
                p_uid = links[0]["href"].split("user=")[1].split("&")[0]
                p_name = links[1].text.strip() if len(links) > 1 else links[0].text.strip()

                # STRICT EXCLUSION: If user_id or name belongs to any teacher in the school
                if str(p_uid) in self.school_teacher_uids or str(p_uid) == str(getattr(self, "teacher_user_id", "")) or self.is_teacher_account(user_id=p_uid, name=p_name):
                    par_link = tr.find("a", href=lambda h: h and "person=" in h)
                    if par_link:
                        pm = re.search(r"person=(\d+)", par_link["href"])
                        if pm:
                            self.school_teacher_pids.add(str(pm.group(1)))
                    continue

                par_link = tr.find("a", href=lambda h: h and "person=" in h)
                if par_link:
                    pm = re.search(r"person=(\d+)", par_link["href"])
                    if pm:
                        pid = str(pm.group(1))
                        if pid not in seen_pids and pid not in self.school_teacher_pids and not self.is_teacher_account(person_id=pid, user_id=p_uid, name=p_name):
                            seen_pids.add(pid)
                            parents.append({
                                "person_id": pid,
                                "name": p_name,
                                "user_id": str(p_uid),
                                "retgroup": class_id
                            })
            return parents
        except Exception as e:
            print(f"Error fetching class parents for {class_id}: {e}")
            return []

    def get_person_info(self, person_id, retgroup, user_id=None, name=None, fetch_parents=False):
        pw_url = f"https://schools.emaktab.uz/v2/admin/persons/person?person={person_id}&school={self.school_id}&view=password&retgroup={retgroup}"
        resp = self.session.get(pw_url, timeout=15)
        soup = BeautifulSoup(resp.text, "html.parser")
        content = soup.find("div", id="content") or soup.find("div", class_="content") or soup

        login_el = content.find("dd", class_="bold") or content.find("dd")
        login = login_el.text.strip() if login_el else None

        # Check role strictly from content area, NOT from the navbar header!
        role_el = content.find(lambda tag: tag.name == "p" and any(k in tag.text.lower() for k in ["o‘quvchi", "o'quvchi", "ota-ona", "xodim", "o‘qituvchi", "o'qituvchi", "direktor", "zamdirektor"]))
        role_text = role_el.text.strip().lower() if role_el else ""

        # Extract name from content if not provided
        if not name:
            h_tag = content.find(["h2", "h1", "h3"])
            if h_tag:
                name = h_tag.text.strip()

        # Check user_id strictly if present inside content, or passed from caller
        p_user_id = user_id
        if not p_user_id:
            for a in content.find_all("a", href=True):
                if "/v2/user/user?" in a["href"]:
                    m_u = re.search(r"user=(\d+)", a["href"])
                    if m_u:
                        p_user_id = m_u.group(1)
                        break

        is_teacher = self.is_teacher_account(person_id=person_id, user_id=p_user_id, login=login, role_text=role_text, name=name)
        if is_teacher:
            if login:
                self.protected_teacher_logins.add(login.lower())
            if person_id:
                self.school_teacher_pids.add(str(person_id))
            if p_user_id:
                self.school_teacher_uids.add(str(p_user_id))

        # Check if reset button exists
        form = content.find("form", action=lambda a: a and "view=password" in a)
        token = None
        has_active_password = False
        if form:
            t_input = form.find("input", attrs={"name": "__RequestVerificationToken"})
            if t_input:
                token = t_input.get("value")
            submit = form.find("input", attrs={"type": "submit"})
            if submit and "o‘chirish" in submit.get("value", ""):
                has_active_password = True

        # Check parents only if explicitly requested
        parents = []
        if fetch_parents:
            par_url = f"https://schools.emaktab.uz/v2/admin/persons/person?person={person_id}&school={self.school_id}&view=parents&retgroup={retgroup}"
            try:
                par_resp = self.session.get(par_url, timeout=15)
                par_soup = BeautifulSoup(par_resp.text, "html.parser")
                par_content = par_soup.find("div", id="content") or par_soup
                for tr in par_content.find_all("tr"):
                    u_link = tr.find("a", href=lambda h: h and "/v2/user/user?" in h)
                    p_uid = u_link["href"].split("user=")[1].split("&")[0] if u_link else ""
                    par_name = u_link.text.strip() if u_link else ""
                    if p_uid and self.is_teacher_account(user_id=p_uid, name=par_name):
                        continue

                    par_link = tr.find("a", href=lambda h: h and "person=" in h and "view=review" in h)
                    if par_link:
                        pm = re.search(r"person=(\d+)", par_link["href"])
                        if pm:
                            p_pid = str(pm.group(1))
                            if not self.is_teacher_account(person_id=p_pid, user_id=p_uid, name=par_name):
                                parents.append({"person_id": p_pid, "name": par_name or par_link.text.strip(), "user_id": p_uid})
            except Exception as e:
                print(f"Error fetching parents for {person_id}: {e}")

        return {
            "person_id": person_id,
            "login": login,
            "token": token,
            "has_active_password": has_active_password,
            "parents": parents,
            "is_teacher": is_teacher,
            "user_id": p_user_id,
            "role_text": role_text,
            "name": name
        }

    def trigger_reset(self, person_id, retgroup, token, login=None, user_id=None, name=None):
        if self.is_teacher_account(person_id=person_id, user_id=user_id, login=login, name=name):
            raise RuntimeError(f"XAVFSIZLIK: O'qituvchi hisobining ({login or person_id}) parolini o'chirish qat'iyan man etiladi!")

        action_url = f"https://schools.emaktab.uz/v2/admin/persons/person?person={person_id}&school={self.school_id}&view=password&retgroup={retgroup}"
        payload = {
            "__RequestVerificationToken": token,
            "change": "Joriy parolni o‘chirish "
        }
        resp = self.session.post(action_url, data=payload, timeout=15)
        soup = BeautifulSoup(resp.text, "html.parser")

        # Parse temporary password
        temp_pwd = None
        dl = soup.find("dl", class_="info")
        if dl:
            dts = [dt.text.strip().lower() for dt in dl.find_all("dt")]
            dds = [dd.text.strip() for dd in dl.find_all("dd")]
            for dt_text, dd_text in zip(dts, dds):
                if any(k in dt_text for k in ["boshlang'ich", "vaqtinchalik", "parol"]):
                    if dd_text and "o‘chirish" not in dd_text:
                        temp_pwd = dd_text
                        break
        return resp.status_code, temp_pwd, resp.text

    def activate_student_account(self, login, temp_pwd, new_pwd, user_id=None, name=None):
        if self.is_teacher_account(login=login, user_id=user_id, name=name):
            raise RuntimeError(f"XAVFSIZLIK: O'qituvchi loginiga ({login}) yangi parol o'rnatish qat'iyan man etiladi!")

        client = requests.Session()
        client.headers.update(HEADERS)
        login_url = "https://login.emaktab.uz/"
        data = {
            "exceededAttempts": "False",
            "ReturnUrl": "",
            "FingerprintId": "",
            "login": login,
            "password": temp_pwd,
            "Captcha.Input": "",
            "Captcha.Id": ""
        }
        r = client.post(login_url, data=data, allow_redirects=True, timeout=15)
        soup = BeautifulSoup(r.text, "html.parser")

        token_inp = soup.find("input", attrs={"name": "Token"})
        if token_inp:
            token = token_inp.get("value")
            login_val = soup.find("input", attrs={"name": "Login"})
            login_str = login_val.get("value") if login_val else login
            ntype = soup.find("input", attrs={"name": "ChangePasswordNotificationType"})
            ntype_val = ntype.get("value") if ntype else "EmailOrPhone"

            post_data = {
                "Token": token,
                "Login": login_str,
                "ChangePasswordNotificationType": ntype_val,
                "Password": new_pwd,
                "RepeatedPassword": new_pwd
            }
            sub_headers = {
                "Referer": r.url,
                "Origin": "https://login.emaktab.uz"
            }
            client.headers.update(sub_headers)
            sub_r = client.post("https://login.emaktab.uz/passwordchanged", data=post_data, allow_redirects=True, timeout=15)
            
            # Check success
            if any(k in sub_r.text.lower() for k in ["o‘zgartirildi", "muvaffaqiyatli", "userfeed", "tiklash"]) or "passwordchanged" not in sub_r.url.lower():
                return True, sub_r.url, "", False

            # Detect password history constraint (e.g. cannot reuse last 3 passwords)
            raw_low = sub_r.text.lower()
            is_history_err = any(k in raw_low for k in [
                "oxirgi 3", "oxirgi uch", "avvalgi", "bir xil bo‘lmasligi", "takrorlash",
                "предыдущ", "совпадать с предыдущими", "совпадать с последними", "нельзя повторять"
            ])

            err_msg = ""
            soup2 = BeautifulSoup(sub_r.text, "html.parser")
            err_el = soup2.find(class_=re.compile(r"validation-summary-errors|field-validation-error|alert-danger|error-message"))
            if err_el:
                err_msg = err_el.text.strip()
            if not err_msg:
                m = re.search(r'(?:parol|пароль)[^<>\n\r]{5,120}', sub_r.text, re.IGNORECASE)
                if m:
                    err_msg = m.group(0).strip()
            if not err_msg:
                err_msg = "eMaktab parollar tarixi cheklovi: Oxirgi 3 ta parolni qayta ishlatish mumkin emas!" if is_history_err else f"Parolni o'rnatish rad etildi (HTTP {sub_r.status_code})"

            return False, sub_r.url, err_msg, is_history_err

        return False, r.url, "Login sahifasida Token topilmadi", False

    def sync_to_db(self, db_path, username, password, grade="10A", school=1, role="student"):
        clean_grade = grade.replace("-", "").replace(" ", "").upper()
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        
        # 1. Ensure school exists in School_number
        sch_id = 1
        if isinstance(school, int):
            cur.execute("SELECT id FROM School_number WHERE id = ? OR school_number = ?", (school, school))
            s_row = cur.fetchone()
            if s_row:
                sch_id = s_row[0]
            else:
                cur.execute("INSERT INTO School_number (school_number, place) VALUES (?, ?)", (school, f"{school}-maktab"))
                sch_id = cur.lastrowid
        else:
            cur.execute("SELECT id FROM School_number LIMIT 1")
            s_row = cur.fetchone()
            if s_row:
                sch_id = s_row[0]

        # 2. Ensure Grade exists in Grade table with trial
        cur.execute("SELECT id FROM Grade WHERE UPPER(REPLACE(grade, '-', '')) = ?", (clean_grade,))
        g_row = cur.fetchone()
        if not g_row:
            cur.execute("INSERT INTO Grade (grade, is_allowed, is_paid, allowed_until) VALUES (?, 1, 0, datetime('now', '+7 days'))", (clean_grade,))

        # 3. Insert or Update in Logins table
        cur.execute("SELECT id FROM Logins WHERE username = ?", (username.strip(),))
        row = cur.fetchone()
        if row:
            lid = row[0]
            cur.execute("""
                UPDATE Logins 
                SET school = ?, password = ?, grade = ?, last_login = 1, role = ?, is_paid = 1, updated_at = CURRENT_TIMESTAMP 
                WHERE id = ?
            """, (sch_id, password.strip(), clean_grade, role, lid))
        else:
            cur.execute("""
                INSERT INTO Logins (school, username, password, grade, last_login, role, is_paid, created_at, updated_at)
                VALUES (?, ?, ?, ?, 1, ?, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """, (sch_id, username.strip(), password.strip(), clean_grade, role))
            lid = cur.lastrowid

        # 4. Record history in Logins_data
        cur.execute("INSERT INTO Logins_data (login_id, last_login, created_at) VALUES (?, 1, CURRENT_TIMESTAMP)", (lid,))
        
        conn.commit()
        conn.close()

    def process_person(self, person_id, retgroup, new_password, db_path="database.sqlite3", grade="10A", school=1, user_id=None, name=None, role="student"):
        info = self.get_person_info(person_id, retgroup, user_id=user_id, name=name)
        login = info.get("login")
        token = info.get("token")
        p_name = name or info.get("name")
        p_uid = user_id or info.get("user_id")

        if not login:
            return False, "No login found", info

        # Strict check if login or person belongs to any teacher
        if info.get("is_teacher") or self.is_teacher_account(person_id=person_id, user_id=p_uid, login=login, name=p_name, role_text=info.get("role_text")):
            return True, f"Skipped teacher account ({login})", info

        if not token:
            return False, f"No verification token for {login}", info

        status, temp_pwd, _ = self.trigger_reset(person_id, retgroup, token, login=login, user_id=p_uid, name=p_name)
        if not temp_pwd:
            return False, f"Failed to extract temporary password for {login} (HTTP {status})", info

        ok, final_url, err_msg, is_history_err = self.activate_student_account(login, temp_pwd, new_password, user_id=p_uid, name=p_name)
        if not ok:
            return False, f"Activation failed for {login}: {err_msg}", {"error": err_msg, "is_history": is_history_err}

        self.sync_to_db(db_path, login, new_password, grade, school, role=role)
        return True, f"Success: {login} reset and set to {new_password}", info

    def get_target_accounts(self, selected_classes, mode="both", max_workers=10):
        """
        Discovers and retrieves logins for all target members of selected_classes.
        mode can be:
          - 'parents': Only parents (strictly excluding teachers)
          - 'students': Only students
          - 'both': Both students and parents (strictly excluding teachers)
        Returns: list of dicts with keys:
          - person_id, login, name, role ('student' or 'parent'), class_id, class_name, token
        """
        from concurrent.futures import ThreadPoolExecutor

        targets_to_fetch = []
        seen_pids = set()

        for cls in selected_classes:
            cid = str(cls["class_id"])
            cname = cls["name"]

            # 1. Students if requested
            if mode in ["students", "both"]:
                students = self.get_class_members(cid)
                for st in students:
                    pid = str(st["person_id"])
                    st_name = st.get("name", "")
                    if pid not in seen_pids and not self.is_teacher_account(person_id=pid, name=st_name):
                        seen_pids.add(pid)
                        targets_to_fetch.append({
                            "person_id": pid,
                            "name": st_name,
                            "role": "student",
                            "class_id": cid,
                            "class_name": cname
                        })

            # 2. Parents if requested
            if mode in ["parents", "both"]:
                parents = self.get_class_parents(cid)
                for par in parents:
                    pid = str(par["person_id"])
                    p_uid = par.get("user_id")
                    par_name = par.get("name", "")
                    if pid not in seen_pids and not self.is_teacher_account(person_id=pid, user_id=p_uid, name=par_name):
                        seen_pids.add(pid)
                        targets_to_fetch.append({
                            "person_id": pid,
                            "name": par_name,
                            "role": "parent",
                            "class_id": cid,
                            "class_name": cname,
                            "user_id": p_uid
                        })

        def fetch_info(item):
            try:
                info = self.get_person_info(
                    item["person_id"],
                    item["class_id"],
                    user_id=item.get("user_id"),
                    name=item.get("name")
                )
                # Strict Teacher check
                if info.get("is_teacher") or self.is_teacher_account(
                    person_id=item["person_id"],
                    user_id=info.get("user_id") or item.get("user_id"),
                    login=info.get("login"),
                    role_text=info.get("role_text"),
                    name=item.get("name")
                ):
                    return None
                login = info.get("login")
                if not login:
                    return None
                return {
                    **item,
                    "name": item.get("name") or info.get("name") or login,
                    "login": login,
                    "token": info.get("token"),
                    "has_active_password": info.get("has_active_password", False)
                }
            except Exception as e:
                print(f"Error fetching info for {item.get('name')}: {e}")
                return None

        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            results = list(ex.map(fetch_info, targets_to_fetch))

        # Filter out None and any teacher logins
        valid_targets = []
        for r in results:
            if r and r.get("login") and not self.is_teacher_account(login=r["login"], person_id=r["person_id"], user_id=r.get("user_id"), name=r.get("name")):
                valid_targets.append(r)

        return valid_targets

    def reset_target_accounts(self, target_accounts, new_password, db_path="database.sqlite3", progress_callback=None):
        """
        Executes password reset ONLY for the pre-approved target_accounts list.
        """
        sch_match = re.search(r"(\d+)", self.school_name)
        sch_num = int(sch_match.group(1)) if sch_match else 14

        total_accounts = len(target_accounts)
        stats = {
            "total_accounts": total_accounts,
            "done_accounts": 0,
            "total_students": sum(1 for a in target_accounts if a.get("role") == "student"),
            "done_students": 0,
            "total_parents": sum(1 for a in target_accounts if a.get("role") == "parent"),
            "done_parents": 0,
            "success_count": 0,
            "fail_count": 0,
            "current_user": "Boshlanmoqda...",
            "is_complete": False
        }

        if progress_callback:
            progress_callback(stats)

        history_error_count = 0
        for idx, acc in enumerate(target_accounts, 1):
            login = acc.get("login")
            person_id = acc.get("person_id")
            cid = acc.get("class_id")
            cname = acc.get("class_name", "")
            role = acc.get("role", "student")
            clean_grade = cname.replace("-", "").replace(" ", "").upper()

            stats["done_accounts"] = idx
            if role == "student":
                stats["done_students"] += 1
                stats["current_user"] = f"O'quvchi: {login}"
            else:
                stats["done_parents"] += 1
                stats["current_user"] = f"Ota-ona: {login}"

            acc_uid = acc.get("user_id")
            acc_name = acc.get("name")

            # HARD CRITICAL SAFEGUARD
            if self.is_teacher_account(person_id=person_id, user_id=acc_uid, login=login, name=acc_name):
                print(f"SKIPPING PROTECTED TEACHER: {login}")
                continue

            ok, msg, res_info = self.process_person(person_id, cid, new_password, db_path, clean_grade, sch_num, user_id=acc_uid, name=acc_name, role=role)
            if ok:
                stats["success_count"] += 1
            else:
                stats["fail_count"] += 1
                is_hist = False
                if isinstance(res_info, dict):
                    is_hist = res_info.get("is_history", False)
                if is_hist:
                    history_error_count += 1
                    # If first 2 accounts fail with history constraint (or on small list, 1), abort early!
                    if history_error_count >= 2 or (total_accounts <= 2 and history_error_count >= 1):
                        stats["abort_reason"] = "history_error"
                        stats["abort_message"] = f"eMaktab xavfsizlik cheklovi: '{new_password}' paroli ushbu hisoblarda oxirgi 3 marta ishlatilgan parollar ro'yxatida mavjud! eMaktab qoidasiga binoan oxirgi 3 ta paroldan birini qayta ishlatish mumkin emas."
                        stats["is_complete"] = True
                        if progress_callback:
                            progress_callback(stats)
                        break

            if progress_callback and (idx % 2 == 0 or idx == total_accounts):
                progress_callback(stats)

        stats["is_complete"] = True
        stats["current_user"] = "Yakunlandi"
        if progress_callback:
            progress_callback(stats)

        return stats

    def reset_class_full(self, class_id, class_name, new_password, db_path="database.sqlite3", progress_callback=None, mode="both"):
        """
        Processes entire class: students and/or parents based on mode ('students', 'parents', 'both').
        """
        target_accounts = self.get_target_accounts([{"class_id": class_id, "name": class_name}], mode=mode)
        return self.reset_target_accounts(target_accounts, new_password, db_path=db_path, progress_callback=progress_callback)
