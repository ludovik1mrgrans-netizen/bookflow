# BookFlow Pro — reusable booking product

Demo product for selling appointment automation to grooming salons and later adapting it to beauty salons, dentists, auto services, tutors, clinics and other appointment businesses.

## What works now
- Serbian customer booking page, RSD pricing
- Services with duration-aware availability
- Multiple employees
- 14-day calendar, 30-minute scheduling grid
- Collision protection (a 90-minute service blocks the full 90 minutes)
- Customer name, phone, pet, notes and consent checkbox
- Confirmation + private cancellation link
- Owner admin login with cookie session
- Dashboard metrics and appointment statuses
- Add services and employees from admin
- Telegram owner notification on a new booking
- Multi-business database foundation via `business_id`

## Windows launch
1. Install Python 3.11+ from python.org and VS Code.
2. Extract this project and open the `bookflow` folder in VS Code.
3. Open **Terminal > New Terminal** and run:

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload
```

4. Open customer demo: http://127.0.0.1:8000/b/milo-grooming
5. Admin: http://127.0.0.1:8000/admin/login
6. Demo admin key: `demo123`

Stop the server with `Ctrl+C`.

## Telegram notifications
Create a Telegram bot with BotFather. Put the values into `.env` (never send or publish the token):

```env
TELEGRAM_BOT_TOKEN=your_token_here
TELEGRAM_CHAT_ID=your_chat_id_here
ADMIN_KEY=replace_this_with_a_long_random_password
```

Restart uvicorn after changing `.env`. If your shell does not load `.env` automatically, set these variables in the shell or use a dotenv loader before production deployment.

## Before selling as a production SaaS
This version is a sales/demo MVP, not yet production-ready. Next production milestones: PostgreSQL, real tenant-specific owner accounts, employee working-hours/holidays, edit/delete settings, rescheduling, reminder worker, customer notification channel, GDPR/privacy text and retention controls, CSRF/rate limiting, audit logs, backups, monitoring, tests, HTTPS/domain and deployment.

## Productization idea
Keep one codebase. Each customer becomes a Business tenant with its own slug, brand, services, employees, schedule and notification destination. Do not fork the source code for each salon.
