import asyncio
import json
import time
from database import (
    init, create_school, create_login, get_all_logins,
    bulk_create_logins_data, bulk_update_logins
)
from send_aiohttps_requests import send_request_main
import dns_resolver  # Fast DNS mapping

RAW_DATA = {
  "1A": [
    {"umgulsinimomova": "12345678"},
    {"maxliyoxon_mahmudova": "12345678"},
    {"k.zoxidaxon": "12345678"},
    {"otajonova.dilafruz12": "12345678"},
    {"ortiqova.feruzaxon06": "12345678"},
    {"rejavaliyevadurdonax": "12345678"},
    {"mxarramxon": "12345678"},
    {"dildoraxonnazarova02": "12345678"},
    {"nazipovamavjudaxon": "12345678"},
    {"oylarxonmamadaliyeva": "12345678"},
    {"siddiqova.salimaxon": "12345678"},
    {"maxpuzaxon.xasanova": "12345678"},
    {"fruzayahyayeva": "12345678"},
    {"madinaxonxusanova071": "12345678"},
    {"muxayyoxonxaydarova1": "12345678"},
    {"nasibaxonumurzoqova": "12345678"},
    {"xalimova.shaxnozaxon": "12345678"},
    {"xalimova.xilolaxon": "12345678"},
    {"munojatxonyuldashev": "12345678"},
    {"yuldashevazulfiya190": "12345678"},
    {"gulmiraxon.yunusova9": "12345678"},
    {"muzayyana_abdurasulo": "12345678"},
    {"osiyoxon.alijonova11": "12345678"},
    {"javohir.azamjonov092": "12345678"},
    {"dilnura.ilxomjonova1": "12345678"},
    {"muhammadyoqubismoilj": "12345678"},
    {"ismoilov_halimjon": "12345678"},
    {"erkinjonov.asadbek03": "12345678"},
    {"alyorbekabduxomitov": "12345678"},
    {"marufovadurdona02201": "12345678"},
    {"karimova.bibisora021": "12345678"},
    {"maxamadraximov_m": "12345678"},
    {"nizomiddinov_muhridd": "12345678"},
    {"muhammadziyoo1803201": "12345678"},
    {"m_odinajonov": "12345678"},
    {"maxsudmaxsudjonov": "12345678"},
    {"murodjonova.m2210201": "12345678"},
    {"samiyaxonisomidinova": "12345678"},
    {"xamraliyevaruxsora": "12345678"},
    {"z.zulhumor": "12345678"},
    {"tursunaliyevaimonaxo": "12345678"},
    {"xoldarovabdulaziz201": "12345678"},
    {"mqurbunjonov": "12345678"},
    {"oyatillo_xomidjonov": "12345678"},
    {"nurjahonturdaliyeva": "12345678"},
    {"fotimaabdisamadova": "12345678"}
  ],
  "3V": [
    {"akbaraliabdumanopov": "12345678"},
    {"nematullo_aliyev": "12345678"},
    {"rahmataliyevumidjon": "12345678"},
    {"shalolaxon.q": "12345678"},
    {"marifatxon.odilova": "12345678"},
    {"xabibullayeva0108201": "12345678"},
    {"yoldashaliyeva.b": "12345678"},
    {"safinayolbarsova": "12345678"},
    {"dilmurodbuzrikov": "123456789"},
    {"mubinaxonamirova": "123456789"},
    {"fotima_raxmonjonova": "123456789"},
    {"rayxonoysobirjonova": "123456789"},
    {"davlatboyev.dostonbe": "12345678"},
    {"bunyodbek.karimjonov": "12345678"},
    {"ilxombekodinayev": "12345678"},
    {"jumagulodinayeva": "12345678"},
    {"tolibjonova_nigina": "12345678"},
    {"mamatursunovk": "12345678m"},
    {"lapasovmaqsud": "12345678l"},
    {"maxpuzaxonxojayeva": "12345678m"},
    {"nargizamansurova0219": "12345678n"},
    {"nilufar.botayeva0719": "12345678n"},
    {"yuldashaliyeva_a": "12345678"},
    {"zahriddinoxunov": "12345678"},
    {"rayhonabonu.o": "12345678"},
    {"odiljon.odilov031120": "12345678"},
    {"kminxojiddinova": "12345678"},
    {"durdona.abdirasilova": "12345678d"},
    {"masturaxonberdimurod": "12345678m"},
    {"gulchexraxona3005199": "12345678g"},
    {"shaxrambekshavkatov": "12345678"},
    {"tursunaliyeva1305201": "12345678"},
    {"sevaraxon.akramova07": "12345678"},
    {"isakova.irodaxon1019": "12345678i"},
    {"abduqodirovam2806201": "12345678"},
    {"erkinjonovimron": "12345678"},
    {"muhammadziyoo2712201": "12345678"},
    {"ssaydaxmatovna": "12345678"},
    {"abdurasulov.a0908201": "12345678"},
    {"raxmonjonova.zuxra": "123456789"},
    {"irodaxonotakishiyeva": "12345678i"},
    {"dildora.xojayeva3108": "12345678d"},
    {"sabinaxon_abdullajon": "12345678"},
    {"mamtisakov": "12345678"},
    {"dostonbek_abdumannob": "12345678"},
    {"jumaboyeva_husnora": "12345678"},
    {"mahliyomamatursunova": "12345678"},
    {"ibroximjonova.m11201": "12345678"},
    {"minxojiddinovs": "12345678"},
    {"mashrabovrahmatillo": "12345678"},
    {"mxudoynazarova170320": "12345678"},
    {"raxmonjonovabdullox": "12345678"},
    {"muhammadazizx1310201": "12345678"},
    {"saidaxon_xabibullaye": "12345678"},
    {"asalxonyuldashaliyev": "12345678"},
    {"abdurasulovvasliddin": "12345678"},
    {"m.axmadjonova1007201": "12345678"},
    {"ashurovaxidoyatxon": "12345678"},
    {"diloromashurova10199": "12345678"},
    {"mkamoliddinova030220": "12345678"},
    {"xolisxonergasheva199": "12345678"},
    {"mamashodiyevar": "12345678"}
  ]
}


async def main():
    print("═══════════════════════════════════════════════════")
    print("📊 EMAKTAB BOT TEST & PERFORMANCE BENCHMARK")
    print("═══════════════════════════════════════════════════")

    # Step 1: Initialize Database
    t_db_start = time.time()
    await init()
    school = await create_school(1, "Test Maktab", 365)
    school_id = school.id
    print(f"✅ DB initialized with School ID: {school_id}")

    # Step 2: Save test cases to database
    total_added = 0
    for grade_name, accounts in RAW_DATA.items():
        for acc in accounts:
            for username, password in acc.items():
                await create_login(
                    password=password,
                    username=username,
                    last_login=False,
                    cookie="",
                    grade=grade_name,
                    school_number_id=school_id
                )
                total_added += 1

    print(f"✅ Saved {total_added} test accounts into database in {time.time() - t_db_start:.2f}s")

    # Step 3: Fetch all logins from DB to test the real batch flow
    all_logins = await get_all_logins(school2=school_id)
    print(f"📦 Loaded {len(all_logins)} logins from DB ready for checking.")

    students_payload = {
        login.id: {
            "login_id": login.id,
            "username": login.username,
            "password": login.password,
            "last_login": login.last_login,
            "last_cookie": login.last_cookie or "",
            "school_id": login.school,
            "grade": login.grade
        }
        for login in all_logins
    }

    # Step 4: Run the verification benchmark
    print("\n🚀 Starting concurrent verification across all 108 accounts...")
    t_check_start = time.time()

    results = await send_request_main(students_payload)

    t_check_end = time.time()
    total_time = t_check_end - t_check_start

    # Step 5: Save results to DB
    history_records = [
        {
            "login_id": sid,
            "last_login": data["last_login"],
            "last_cookie": data["last_cookie"]
        }
        for sid, data in results.items()
    ]
    await bulk_create_logins_data(history_records)

    # Step 6: Compute statistics
    success_count = sum(1 for d in results.values() if d.get("last_login"))
    fail_count = sum(1 for d in results.values() if not d.get("last_login"))

    print("\n═══════════════════════════════════════════════════")
    print("🏁 BENCHMARK RESULTS")
    print("═══════════════════════════════════════════════════")
    print(f"👥 Jami loginlar: {len(results)}")
    print(f"✅ Muvaffaqiyatli kirilgan (Success): {success_count}")
    print(f"❌ Xato yoki kirilmagan (Failed): {fail_count}")
    print(f"⏱️ Jami ketgan vaqt: {total_time:.2f} soniya ({total_time/60:.2f} daqiqa)")
    print(f"⚡ O'rtacha tezlik: {len(results)/total_time:.2f} login/soniya")
    print("═══════════════════════════════════════════════════")


if __name__ == "__main__":
    asyncio.run(main())
