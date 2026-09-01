# COMPASS — Adaptiv CEFR Daraja Aniqlash Ilovasi

Telegram **Mini App**. Test butunlay ilova ichida o'tadi: chap tarafdagi
doimiy «Open» tugmasi yoki `/start` dagi tugma bosilganda Telegram ichida
to'laqonli ilova ochiladi.

Bot: [@COMPASS_testbot](https://t.me/COMPASS_testbot)

```
Beginner → Elementary → Pre-Intermediate →
Intermediate → Upper-Intermediate → Advanced
```

Daraja **hech qachon bittadan ortiq sakramaydi** — bu qat'iy kod qoidasi
(`app/staircase.py`), AI ning fikri emas.

**Til:** ilovadagi hamma matn — topshiriqlar, tugmalar, natija xulosasi —
o'zbek tilida. Faqat javob variantlari (A/B/C/D), tekshiriladigan inglizcha
jumlalar va o'qish matnlari ingliz tilida qoladi, chunki test aynan shularni
o'lchaydi.

**Daraja kodlari:** `A1`…`C2` faqat ichki kalitlar — savollar banki va
bazada ishlatiladi. Foydalanuvchi ularni hech qayerda ko'rmaydi, ekranda
faqat nomlar turadi.

---

## Tez ishga tushirish

```powershell
cd C:\Users\Lenovo\compass-app
.\.venv\Scripts\python.exe run.py
```

Bitta buyruq quyidagilarni qiladi:

1. web serverni ko'taradi (ilova fayllari + API);
2. HTTPS tunnel ochadi va manzilni topadi — birinchi safar `cloudflared`
   avtomatik yuklab olinadi (~55 MB, `.tools/` ga; sekin internetda bu bir
   necha daqiqa olishi mumkin, keyingi safarlar bir zumda ishlaydi);
3. botni ishga tushiradi va **chap tarafdagi doimiy «Open» tugmasini**
   shu manzilga o'rnatadi.

Keyin Telegram'da botga `/start` yozing.

To'xtatish: `Ctrl+C`

> **Diqqat.** `cloudflared` bepul tunneli har ishga tushirishda **yangi
> manzil** beradi va kompyuter o'chsa ilova ham o'chadi. Bu sinash uchun.
> Doimiy ishlatish uchun pastdagi «Hostingga chiqarish» bo'limiga qarang.

---

## Nima qayerda

| Fayl | Vazifasi |
|---|---|
| `app/staircase.py` | **Daraja algoritmi.** Sof kod, AI yo'q — barcha qarorlar shu yerda |
| `app/engine.py` | Sessiya: savol berish, javob baholash, staircase qarorini qo'llash |
| `app/api.py` | Mini App backend: `/api/bootstrap`, `/api/start`, `/api/answer` |
| `app/bot.py` | Bot — ilovaga kirish nuqtasi (menyu tugmasi, `/start`, `/natija`) |
| `app/tg_auth.py` | `initData` HMAC tekshiruvi — foydalanuvchi shu yerdan aniqlanadi |
| `app/questions.py` | Savollar banki: yuklash, tekshirish, blok tanlash |
| `app/ai.py` | Claude API: yozma javobni baholash + yakuniy xulosa |
| `app/store.py` | SQLite: sessiyalar va natijalar |
| `app/notify.py` | Natijani chatga va adminga yuborish |
| `app/tunnel.py` | HTTPS manzil ochish (cloudflared / ngrok) — faqat lokal |
| `render.yaml` | Render.com uchun tayyor sozlama |
| `webapp/` | **Ilovaning o'zi** — `index.html`, `app.js`, `style.css` |
| `data/questions.json` | 132 ta savol (har darajada 22 ta) |
| `run.py` | Hammasini birga ishga tushiradi |

---

## Ilova qanday ishlaydi

**Bosh ekran.** Ism bilan salomlashadi, zinapoyani ko'rsatadi va uchta
holatdan birini beradi: yangi test, yarim qolgan testni davom ettirish,
yoki oldingi natijani ochish.

**Test.** Yuqorida — daraja zinapoyasi (o'tilgan darajalar bo'yalgan, joriysi
kattalashgan). Ostida — blokdagi 5 savolning nuqtalari. Har javobda haptik
javob (telefon titraydi), ekranlar silliq almashadi.

**Daraja o'zgarishi.** Blok tugab daraja o'zgarganda butun ekranni egallovchi
animatsiya chiqadi: `A1 → A2`, yo'nalish o'qi va izoh. Bu 2 soniya turadi —
foydalanuvchi nima bo'layotganini aniq ko'radi.

**Natija.** Katta daraja belgisi, Claude yozgan xulosa, har blok bo'yicha
to'lib boradigan chiziqlar. Natija bir vaqtning o'zida Telegram chatga ham
yuboriladi — ilova yopilgach ham qo'lda qoladi.

**Uzilib qolsa.** Test yarmida ilova yopilsa, holat serverda saqlanadi.
Qayta ochilganda **o'sha savoldan** davom etadi — bosh ekranga qaytmaydi.

### Telegram bilan integratsiya

- mavzu (`--tg-theme-*`) — kunduzgi/tungi rejim avtomatik;
- `expand()` — ilova to'liq balandlikda ochiladi;
- `disableVerticalSwipes()` — tasodifiy surish testni yopib yubormaydi;
- `enableClosingConfirmation()` — test davomida yopishdan oldin so'raydi;
- `BackButton` — testdan chiqish, tasdiqlash bilan;
- `HapticFeedback` — javob, daraja ko'tarilishi, natija.

---

## Algoritm (staircase)

Har blok = 5 savol. Blok tugagach:

| Natija | Qaror |
|---|---|
| **≥ 80%** (4–5 to'g'ri) | Bir pog'ona **yuqoriga**, davom etadi |
| **40–79%** (2–3 to'g'ri) | **Shu daraja** — test to'xtaydi (aniq natija) |
| **< 40%** (0–1 to'g'ri) | Bir pog'ona **pastga**, tasdiqlash uchun yana bir blok |

**To'xtash sabablari:**

- `precise` — 40–79% olindi, aniq daraja topildi;
- `ceiling` — C2 da ham 80%+ (eng yuqori chegara);
- `floor` — A1 da ham 40% dan past (A1 dan boshlash kerak);
- `confirmed_ceiling` — allaqachon yiqilgan darajaga qayta ko'tarilish;
- `max_questions` — 30 savol chegarasi.

### Spetsifikatsiyaga qo'shilgan bitta himoya

Asl qoidada tebranish muammosi bor edi: A2 da 5/5 → B1, B1 da 0/5 → A2,
A2 da yana 5/5 → B1… bu 30 savolgacha aylanardi. Shuning uchun **allaqachon
yiqilgan darajaga ikkinchi marta ko'tarilmaymiz**: pastda o'tib, yuqorida
yiqilish aynan shu chegara topilganini bildiradi. Bu qoidani o'chirish uchun
`staircase.py` dagi `_failed_levels` tekshiruvini olib tashlash kifoya.

`max_questions` bo'lganda yakuniy daraja = **≥40% olingan eng yuqori daraja**.

---

## AI ning roli

AI **daraja qaror qabul qilmaydi**. U faqat ikki ish qiladi:

1. `free_text` javoblarni **ikkilik** (to'g'ri/noto'g'ri) baholaydi;
2. kod aniqlagan daraja haqida o'zbek tilida xulosa yozadi.

Himoya choralari:

- `ANTHROPIC_API_KEY` bo'sh bo'lsa — yozma savollar bankdan umuman
  chiqarib tashlanadi, xulosa shablon matndan tuziladi;
- API xato bersa — shablonga qaytadi, test buzilmaydi;
- AI xulosasida kod bergan daraja yozilmagan bo'lsa — javob rad etilib,
  shablon ishlatiladi (`ai.py` dagi so'nggi tekshiruv).

Model: `claude-opus-5` (`.env` da `CLAUDE_MODEL` orqali o'zgartiriladi).

---

## Xavfsizlik

- **To'g'ri javoblar ilovaga hech qachon yuborilmaydi.** Savollar bittalab
  beriladi, tekshiruv faqat serverda (`questions.public_view`).
- **Telegram ID ga ishonilmaydi.** Ilova yuborgan `initData` ning HMAC-SHA256
  imzosi bot token bilan tekshiriladi; foydalanuvchi FAQAT shundan olinadi.
  Imzo 24 soatdan eski bo'lsa rad etiladi.
- **Sessiya egasi tekshiriladi.** Birov boshqasining `session_id` sini topib
  qo'ysa ham, uning testini davom ettira olmaydi (403).
- `ALLOW_INSECURE_DEV=true` faqat brauzerda sinash uchun — **productionda
  hech qachon yoqmang**, u imzo tekshiruvini chetlab o'tadi.
- `.env` `.gitignore` da — token repozitoriyga tushmaydi.

### `post_init` nega ishlatilmagan

Menyu tugmasini o'rnatishni `Application.post_init` ga bog'lash tabiiy
ko'rinadi, lekin **ishlamaydi**: python-telegram-bot `post_init` ni faqat
`run_polling()` / `run_webhook()` ichida chaqiradi. `run.py` da web server
va bot bitta siklda yashagani uchun hayot sikli qo'lda boshqariladi —
o'shanda `post_init` umuman chaqirilmaydi va tugma jimgina o'rnatilmay
qoladi. Shuning uchun `configure_bot_ui()` `run.py` dan to'g'ridan-to'g'ri
chaqiriladi.

### `tg.sendData()` nega ishlatilmagan

Natijani `Telegram.WebApp.sendData()` orqali botga qaytarish **bu yerda
ishlamaydi**: u faqat *reply-keyboard* tugmasidan ochilgan Mini App'da
mavjud. Inline tugma yoki chap tarafdagi menyu tugmasidan ochilganda
umuman chaqirilmaydi — natija jimgina yo'qolardi.

Shuning uchun natijani **server** yuboradi:

```
Ilova → POST /api/answer → initData HMAC bilan tekshiriladi
                         → staircase qarori hisoblanadi
                         → test tugasa: Claude xulosa yozadi
                         → server Bot API orqali natijani foydalanuvchiga yuboradi
                         → ADMIN_CHAT_ID ga nusxa
```

---

## Testlar

```powershell
.\.venv\Scripts\python.exe tests\test_staircase.py
.\.venv\Scripts\python.exe tests\test_app_flow.py
```

`test_staircase.py` barcha mumkin bo'lgan ball ketma-ketliklarini
(6⁸ ≈ 1.6 mln kombinatsiya) o'ynab chiqadi va tasdiqlaydi: daraja hech qachon
bittadan ortiq sakramaydi, savollar 30 tadan oshmaydi, cheksiz sikl yo'q.

`test_app_flow.py` haqiqiy HTTP so'rovlar bilan to'liq oqimni tekshiradi:
imzo tekshiruvi, begona foydalanuvchi rad etilishi, A1→C2 ko'tarilish,
A1 da to'xtash, uzilgan testni tiklash, tugagan sessiyaning yopiqligi.
Telegram xabari yuborilmaydi (test uni bloklaydi).

---

## Sozlamalar (`.env`)

| Kalit | Ma'nosi |
|---|---|
| `BOT_TOKEN` | @BotFather bergan token |
| `WEBAPP_URL` | Ilova manzili (HTTPS). Bo'sh = tunnel o'zi topadi |
| `MENU_BUTTON_TEXT` | Chap tarafdagi tugma matni (`Open`) |
| `ADMIN_CHAT_ID` | Natijalar nusxasi shu chatga boradi |
| `ANTHROPIC_API_KEY` | Bo'sh = shablon xulosa, yozma savollar yo'q |
| `TUNNEL` | `cloudflared` \| `ngrok` \| `none` |
| `ALLOW_INSECURE_DEV` | Faqat brauzerda sinash uchun |

---

## Bepul serverga chiqarish (Render.com)

Tunnel — faqat sinash uchun: manzil har safar o'zgaradi va kompyuter o'chsa
ilova ham o'chadi. Doimiy ishlashi uchun Render'ning bepul tarifiga qo'yamiz.
Karta talab qilinmaydi.

### Kerakli hisoblar (uchalasi bepul, karta so'ralmaydi)

| Hisob | Nima uchun |
|---|---|
| [GitHub](https://github.com/signup) | kod shu yerda turadi, Render undan oladi |
| [Render](https://render.com) | serverning o'zi (GitHub bilan kiriladi) |
| [Neon](https://neon.tech) | Postgres bazasi — natijalar yo'qolmasligi uchun |
| [UptimeRobot](https://uptimerobot.com) | ixtiyoriy: xizmatni uyg'oq saqlaydi |

### Qadamlar

1. **GitHub'ga yuklang.** `.env` yuklanmaydi (`.gitignore` da) — token
   repozitoriyaga tushmaydi.

   ```powershell
   git init
   git add .
   git commit -m "COMPASS daraja testi"
   git branch -M main
   git remote add origin https://github.com/<foydalanuvchi>/compass-app.git
   git push -u origin main
   ```

2. **Neon'da baza oching.** Yangi loyiha yarating, `Connection string` ni
   nusxalang (`postgresql://…` ko'rinishida).

3. **Render'da xizmat yarating.** New → Blueprint → repozitoriyani tanlang.
   `render.yaml` ni o'zi o'qiydi. Keyin Environment bo'limiga qo'lda yozing:

   | Kalit | Qiymat |
   |---|---|
   | `BOT_TOKEN` | @BotFather bergan token |
   | `ADMIN_IDS` | o'z Telegram ID ingiz (botga `/id` yozib bilasiz) |
   | `DATABASE_URL` | Neon bergan ulanish satri |
   | `ANTHROPIC_API_KEY` | ixtiyoriy |

   `WEBAPP_URL` yozilmaydi — Render o'z manzilini `RENDER_EXTERNAL_URL`
   orqali beradi va ilova uni avtomatik oladi.

4. **Tekshiring.** Deploy tugagach `https://<nom>.onrender.com/api/health`
   ni oching: `"db": "Postgres"` va `"webhook": true` bo'lishi kerak.
   Keyin Telegram'da botga `/start` yozing.

5. **Uyg'oq saqlash (ixtiyoriy).** Bepul tarifda xizmat 15 daqiqa
   tinchlikdan keyin uxlaydi va birinchi so'rov ~1 daqiqa kutadi.
   UptimeRobot'da `https://<nom>.onrender.com/api/health` ga har 5 daqiqada
   so'rov qo'ying — shunda doim uyg'oq turadi.

### Nega webhook, polling emas

Polling'da bot Telegramdan yangiliklarni **o'zi so'rab turadi** — buning
uchun jarayon to'xtamasligi kerak. Uxlab qolgan bepul serverda bu ishlamaydi:
bot uxlaydi va `/start` ga javob bermaydi.

Webhook'da esa Telegram yangilikni **serverga o'zi yuboradi**, va aynan shu
so'rov uxlab qolgan xizmatni uyg'otadi. Shuning uchun `render.yaml` da
`USE_WEBHOOK=true`. Lokalda esa polling qulayroq — `run.py` shuni ishlatadi.

Webhook manzili maxfiy sarlavha (`X-Telegram-Bot-Api-Secret-Token`) bilan
himoyalangan: usiz istalgan odam botga soxta yangilik yubora olardi.

### Ma'lumotlar bazasi haqida

Render'ning bepul diski **vaqtinchalik** — xizmat qayta ishga tushsa SQLite
fayli o'chadi. Shuning uchun serverda Neon Postgres ishlatiladi
(`DATABASE_URL`). `store.py` ikkalasini ham qo'llab-quvvatlaydi: o'zgaruvchi
bo'sh bo'lsa SQLite, to'ldirilgan bo'lsa Postgres.

`DATABASE_URL` ni qo'ymasangiz ham ilova ishlaydi, lekin test tarixi har
qayta ishga tushishda yo'qoladi (natijalarning nusxasi Telegram chatda
qoladi).

## Admin paneli

`ADMIN_IDS` ro'yxatidagi Telegram akkauntlarga ilovaning bosh ekranida
«📊 Natijalar (admin)» tugmasi ko'rinadi. U yerda:

- jami nechta urinish va nechtasi tugallangani;
- darajalar kesimida taqsimot;
- oxirgi 100 ta natija (ism, username, daraja, sana).

Boshqa foydalanuvchilar bu bo'limni ko'rmaydi va `/api/admin/results` ularga
403 qaytaradi — tekshiruv serverda, `initData` imzosidan olingan ID bo'yicha.

O'z ID ingizni bilish uchun botga `/id` yozing.

---

## Savollar bankini kengaytirish

`data/questions.json` — har daraja uchun ro'yxat:

```json
{
  "id": "a2_g_01",
  "level": "A2",
  "skill": "grammar",
  "type": "mcq",
  "question": "Bo'sh joyga mos variantni tanlang:",
  "sentence": "She ___ to school every day.",
  "options": ["go", "goes", "going", "gone"],
  "correct": "goes"
}
```

| Maydon | Tili | Vazifasi |
|---|---|---|
| `question` | **o'zbekcha** | Topshiriq — ekranda sarlavha bo'lib turadi |
| `sentence` | inglizcha | Tekshiriladigan jumla (ixtiyoriy) — gold chiziqli blokda |
| `passage` | inglizcha | O'qish matni (ixtiyoriy) |
| `options` / `correct` | inglizcha | Javob variantlari |

- `skill`: `grammar` | `vocabulary` | `reading` | `writing`
- Bo'sh joy belgisi `___` **faqat** `sentence` ichida bo'ladi, `question` da emas
- Lug'at va o'qish savollari ko'pincha to'liq o'zbekcha yoziladi
  (`sentence` kerak emas), grammatika savollarida esa inglizcha jumla shart
- yozma savol: `"type": "free_text"` + `"min_words": 20`
  (`options` va `correct` kerak emas — uni Claude baholaydi)

Server ishga tushganda bank tekshiriladi: takrorlangan `id`, `correct`
variantlar ichida yo'qligi, darajada 5 tadan kam savol — hammasi xato beradi.
Bir daraja uchun 20–30 ta savol tavsiya etiladi (hozir 22 tadan).

---

## Bu loyihaning `cefr-test` dan farqi

`C:\Users\Lenovo\cefr-test` — **chat rejimi**: test bot chatida, oddiy
tugmalar bilan o'tadi, hosting kerak emas.

Bu loyiha — **Mini App**: test Telegram ichidagi to'laqonli ilovada o'tadi,
HTTPS manzil talab qiladi. Algoritm ikkalasida bir xil.
