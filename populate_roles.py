import requests, sqlite3, json, re
from bs4 import BeautifulSoup

def clean(s):
    if not s:
        return ""
    # Transliterate cyrillic if needed
    trans = str.maketrans("абвгдеёжзийклмнопрстуфхцчшщъыьэюяўқғҳ", "abvgdeejziyklmnoprstufxc4ww_y_eyauqgh")
    s = s.lower().translate(trans)
    return re.sub(r"[^a-z0-9]", "", s)

def run():
    print("Logging into eMaktab as teacher...")
    session = requests.Session()
    data = {
        'exceededAttempts': 'False',
        'ReturnUrl': '',
        'FingerprintId': '',
        'login': 'toxtasinovafarida',
        'password': 'Farida82'
    }
    headers = {'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64)'}
    session.post('https://login.emaktab.uz/', data=data, headers=headers)

    with open('/home/ubuntu/emaktab_2025/school_classes_cache.json') as f:
        cache = json.load(f)

    conn = sqlite3.connect('/home/ubuntu/emaktab_2025/database.sqlite3')
    cur = conn.cursor()

    try:
        cur.execute("ALTER TABLE Logins ADD COLUMN role VARCHAR DEFAULT 'student';")
        conn.commit()
        print("Added role column to Logins table.")
    except Exception:
        pass

    # 1. Clean up 7A extra 16 accounts (IDs 494-509) inserted today
    cur.execute("DELETE FROM Logins WHERE id >= 494 AND id <= 509 AND grade = '7A';")
    print(f"Deleted {cur.rowcount} extra 7A accounts from DB.")
    conn.commit()

    # 2. Ensure all 10A accounts have last_login = 1
    cur.execute("UPDATE Logins SET last_login = 1 WHERE grade = '10A';")
    print(f"Updated {cur.rowcount} 10A accounts to last_login = 1.")
    conn.commit()

    # 3. For 7A specifically (16 accounts): 9 students, 7 parents
    parents_7a = {
        "rasuljondjumaboyev",
        "xalilovazaynabxon",
        "azizaxonumridinova",
        "nizomjon.yoqubov",
        "abdusharofotajonova",
        "azamatyakubova",
        "qaxramontodjiboyev"
    }
    cur.execute("SELECT id, username FROM Logins WHERE grade = '7A';")
    for lid, u in cur.fetchall():
        r = "parent" if u in parents_7a else "student"
        cur.execute("UPDATE Logins SET role = ? WHERE id = ?", (r, lid))
    conn.commit()

    # 4. For 10A specifically (40 accounts): 22 students, 18 parents
    students_10a = {
        "abdulazizovfayzullox", "gulnigoralijonova", "alijonovamuxlisaxon0", "dilyorbekasqaraliyev",
        "muxammadsobiraxmadjo", "xamidullo.azamjonov", "dilmurodbuzrikov", "setoraiminova",
        "maftuna.ismoilova290", "k.qurbonboyev0809201", "marjona_maxammatova", "abduxalilmashrapov",
        "mirzabaxromovas", "muxammatazizorifov", "rustamjonovaz2002201", "mexrbonrustamjonova",
        "maftuna.toxirjonova1", "usmonjontoshmamatov", "izzatillo.tursunboye", "bibinurumurzoqova",
        "bexruzbek.xoldarov", "zakiyaxonerkinjonova"
    }
    cur.execute("SELECT id, username FROM Logins WHERE grade = '10A';")
    for lid, u in cur.fetchall():
        r = "student" if u in students_10a else "parent"
        cur.execute("UPDATE Logins SET role = ? WHERE id = ?", (r, lid))
    conn.commit()

    # 5. For all other classes, fetch rosters and classify
    cur.execute("SELECT DISTINCT grade FROM Logins;")
    all_grades = [r[0] for r in cur.fetchall()]

    for g in all_grades:
        if g in ["7A", "10A"]:
            continue
        cdata = cache.get(g)
        if not cdata or not cdata.get('class_id'):
            # default to student if unknown class (e.g. 10V, 2015)
            cur.execute("UPDATE Logins SET role = 'student' WHERE grade = ?", (g,))
            conn.commit()
            continue

        cid = cdata['class_id']
        s_res = session.get(f'https://schools.emaktab.uz/v2/class?class={cid}&view=members', timeout=10)
        s_soup = BeautifulSoup(s_res.text, 'html.parser')
        student_names = [a.text.strip() for a in s_soup.find_all('a', href=lambda h: h and '/v2/user/user?' in h) if a.text.strip()]

        p_res = session.get(f'https://schools.emaktab.uz/v2/class?class={cid}&view=members&group=parents', timeout=10)
        p_soup = BeautifulSoup(p_res.text, 'html.parser')
        parent_names = []
        for tr in p_soup.find_all('tr'):
            if tr.find('th'): continue
            tds = tr.find_all('td')
            if len(tds) > 1:
                a = tds[1].find('a', href=lambda h: h and '/v2/user/user?' in h)
                if a and a.text.strip():
                    parent_names.append(a.text.strip())

        cur.execute("SELECT id, username FROM Logins WHERE grade = ?;", (g,))
        rows = cur.fetchall()
        for lid, u in rows:
            cu = clean(u)
            st_score = 0
            for name in student_names:
                parts = [clean(p) for p in name.split() if len(clean(p)) > 2]
                matched = sum(1 for p in parts if p in cu or cu in p)
                if matched > st_score:
                    st_score = matched

            pr_score = 0
            for name in parent_names:
                parts = [clean(p) for p in name.split() if len(clean(p)) > 2]
                matched = sum(1 for p in parts if p in cu or cu in p)
                if matched > pr_score:
                    pr_score = matched

            role = "parent" if pr_score > st_score else "student"
            cur.execute("UPDATE Logins SET role = ? WHERE id = ?", (role, lid))

        conn.commit()

    # Print summary of all classes
    print("\n=== FINAL CLASS BREAKDOWN IN DATABASE ===")
    cur.execute("""
        SELECT grade,
               count(*),
               sum(case when role = 'student' then 1 else 0 end),
               sum(case when role = 'parent' then 1 else 0 end),
               sum(case when last_login = 1 then 1 else 0 end)
        FROM Logins
        GROUP BY grade
        ORDER BY grade;
    """)
    for g, tot, st, pr, succ in cur.fetchall():
        pct = round(succ / tot * 100, 1) if tot > 0 else 0
        print(f"• {g:5}: {tot:2} ta | (oquvchi:{st:2}, ota-ona:{pr:2}) | ✅ {succ:2} ({pct}%)")

    conn.close()

if __name__ == '__main__':
    run()
