import os
import secrets
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Optional

import httpx
from fastapi import FastAPI, Form, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import create_engine, String, Integer, DateTime, ForeignKey, select, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, Session

BASE = Path(__file__).resolve().parent
DB_URL = os.getenv("DATABASE_URL", "sqlite:///./bookflow.db")
connect_args = {"check_same_thread": False} if DB_URL.startswith("sqlite") else {}
engine = create_engine(DB_URL, connect_args=connect_args)

class Base(DeclarativeBase): pass

class Business(Base):
    __tablename__ = "businesses"
    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String, unique=True)
    name: Mapped[str] = mapped_column(String)
    phone: Mapped[str] = mapped_column(String, default="")
    address: Mapped[str] = mapped_column(String, default="Beograd")
    timezone: Mapped[str] = mapped_column(String, default="Europe/Belgrade")
    currency: Mapped[str] = mapped_column(String, default="RSD")
    owner_chat_id: Mapped[str] = mapped_column(String, default="")
    rebook_days: Mapped[int] = mapped_column(Integer, default=42)
    admin_key: Mapped[str] = mapped_column(String, default="demo123")

class Service(Base):
    __tablename__ = "services"
    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id"))
    name: Mapped[str] = mapped_column(String)
    duration_min: Mapped[int] = mapped_column(Integer)
    price_rsd: Mapped[int] = mapped_column(Integer)

class Employee(Base):
    __tablename__ = "employees"
    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id"))
    name: Mapped[str] = mapped_column(String)
    active: Mapped[int] = mapped_column(Integer, default=1)

class Appointment(Base):
    __tablename__ = "appointments"
    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id"))
    service_id: Mapped[int] = mapped_column(ForeignKey("services.id"))
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"))
    customer_name: Mapped[str] = mapped_column(String)
    phone: Mapped[str] = mapped_column(String)
    pet_name: Mapped[str] = mapped_column(String, default="")
    note: Mapped[str] = mapped_column(Text, default="")
    starts_at: Mapped[datetime] = mapped_column(DateTime)
    ends_at: Mapped[datetime] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String, default="confirmed")
    manage_token: Mapped[str] = mapped_column(String, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

Base.metadata.create_all(engine)

def seed():
    with Session(engine) as s:
        key = request.cookies.get("bookflow_admin")
        b = s.scalar(select(Business).where(Business.admin_key == key))
        if not b:
            b = Business(slug="milo-grooming", name="Milo Grooming Beograd", phone="+381 60 000 0000", address="Beograd, Srbija")
            s.add(b); s.flush()
        if not s.scalar(select(Service).where(Service.business_id == b.id)):
            s.add_all([
                Service(business_id=b.id, name="Kupanje + feniranje", duration_min=60, price_rsd=2200),
                Service(business_id=b.id, name="Kompletan grooming", duration_min=90, price_rsd=3500),
                Service(business_id=b.id, name="Е iЕЎanje", duration_min=60, price_rsd=2500),
                Service(business_id=b.id, name="Nega noktiju", duration_min=30, price_rsd=900),
            ])
        if not s.scalar(select(Employee).where(Employee.business_id == b.id)):
            s.add_all([Employee(business_id=b.id, name="Ana"), Employee(business_id=b.id, name="Marko")])
        s.commit()
seed()

app = FastAPI(title="BookFlow Pro")
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")
templates = Jinja2Templates(directory=BASE / "templates")

WEEKDAY = ["Pon", "Uto", "Sre", "ДЊet", "Pet", "Sub", "Ned"]

def get_business(s, slug):
    b = s.scalar(select(Business).where(Business.slug == slug))
    if not b: raise HTTPException(404, "Business not found")
    return b

def overlaps(start1, end1, start2, end2):
    return start1 < end2 and start2 < end1

def slots_for(s, b_id: int, employee_id: int, service: Service, d: date):
    # Mon-Sat 09:00-18:00, Sunday closed. Duration-aware collision handling.
    if d.weekday() == 6: return []
    opening = datetime.combine(d, time(9, 0)); closing = datetime.combine(d, time(18, 0))
    appts = list(s.scalars(select(Appointment).where(
        Appointment.business_id == b_id,
        Appointment.employee_id == employee_id,
        Appointment.starts_at >= datetime.combine(d, time.min),
        Appointment.starts_at <= datetime.combine(d, time.max),
        Appointment.status != "cancelled"
    )))
    out = []; cur = opening
    while cur + timedelta(minutes=service.duration_min) <= closing:
        end = cur + timedelta(minutes=service.duration_min)
        if cur > datetime.now() and not any(overlaps(cur, end, a.starts_at, a.ends_at) for a in appts):
            out.append(cur.strftime("%H:%M"))
        cur += timedelta(minutes=30)
    return out

async def telegram_notify(text: str, chat_id: str = ""):
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat = chat_id or os.getenv("TELEGRAM_CHAT_ID", "")
    if token and chat:
        async with httpx.AsyncClient(timeout=8) as client:
            try:
                await client.post(f"https://api.telegram.org/bot{token}/sendMessage", json={"chat_id": chat, "text": text})
            except Exception:
                pass

def admin_ok(request: Request, business=None):
    key = request.cookies.get("bookflow_admin")
    if not key:
        return False
    if business is not None:
        return key == business.admin_key
    with Session(engine) as s:
        return s.scalar(select(Business).where(Business.admin_key == key)) is not None

@app.get("/", response_class=HTMLResponse)
def home(): return RedirectResponse("/b/milo-grooming")

@app.get("/b/{slug}", response_class=HTMLResponse)
def booking(request: Request, slug: str, day: Optional[str] = None, service_id: Optional[int] = None, employee_id: Optional[int] = None):
    with Session(engine) as s:
        b = get_business(s, slug)
        services = list(s.scalars(select(Service).where(Service.business_id == b.id).order_by(Service.id)))
        employees = list(s.scalars(select(Employee).where(Employee.business_id == b.id, Employee.active == 1)))
        d = date.fromisoformat(day) if day else date.today() + timedelta(days=1)
        service = s.get(Service, service_id) if service_id else (services[0] if services else None)
        employee = s.get(Employee, employee_id) if employee_id else (employees[0] if employees else None)
        slots = slots_for(s, b.id, employee.id, service, d) if service and employee else []
        days = [date.today() + timedelta(days=i) for i in range(1, 15)]
        return templates.TemplateResponse(request, "booking.html", {"b": b, "services": services, "employees": employees, "day": d, "service": service, "employee": employee, "slots": slots, "days": days, "weekday": WEEKDAY})

@app.post("/b/{slug}/book", response_class=HTMLResponse)
async def book(request: Request, slug: str, service_id: int = Form(...), employee_id: int = Form(...), day: str = Form(...), slot: str = Form(...), customer_name: str = Form(...), phone: str = Form(...), pet_name: str = Form(""), note: str = Form("")):
    start = datetime.combine(date.fromisoformat(day), time.fromisoformat(slot))
    with Session(engine) as s:
        b = get_business(s, slug); service = s.get(Service, service_id); employee = s.get(Employee, employee_id)
        if not service or service.business_id != b.id or not employee or employee.business_id != b.id: raise HTTPException(400)
        end = start + timedelta(minutes=service.duration_min)
        existing = list(s.scalars(select(Appointment).where(Appointment.employee_id == employee.id, Appointment.starts_at < end, Appointment.ends_at > start, Appointment.status != "cancelled")))
        if existing:
            return RedirectResponse(f"/b/{slug}?day={day}&service_id={service_id}&employee_id={employee_id}&error=taken", 303)
        a = Appointment(business_id=b.id, service_id=service.id, employee_id=employee.id, customer_name=customer_name.strip(), phone=phone.strip(), pet_name=pet_name.strip(), note=note.strip(), starts_at=start, ends_at=end, manage_token=secrets.token_urlsafe(24))
        s.add(a); s.commit(); s.refresh(a)
        await telegram_notify(f"рџ”” Nova rezervacija В· {b.name}\n{customer_name}\n{service.name} В· {employee.name}\n{start:%d.%m.%Y %H:%M}\n{phone}", b.owner_chat_id)
        return templates.TemplateResponse(request, "success.html", {"b": b, "a": a, "service": service, "employee": employee})

@app.get("/manage/{token}", response_class=HTMLResponse)
def manage(request: Request, token: str):
    with Session(engine) as s:
        a = s.scalar(select(Appointment).where(Appointment.manage_token == token))
        if not a: raise HTTPException(404)
        return templates.TemplateResponse(request, "manage.html", {"a": a, "b": s.get(Business, a.business_id), "service": s.get(Service, a.service_id), "employee": s.get(Employee, a.employee_id)})

@app.post("/manage/{token}/cancel")
def cancel(token: str):
    with Session(engine) as s:
        a = s.scalar(select(Appointment).where(Appointment.manage_token == token))
        if not a: raise HTTPException(404)
        a.status = "cancelled"; s.commit()
    return RedirectResponse(f"/manage/{token}", 303)

@app.get("/admin/login", response_class=HTMLResponse)
def login_page(request: Request): return templates.TemplateResponse(request, "login.html", {})

@app.post("/admin/login")
def login(key: str = Form(...)):
    with Session(engine) as s:
        b = s.scalar(select(Business).where(Business.admin_key == key))
        if not b:
            return RedirectResponse("/admin/login?error=1", 303)
    r = RedirectResponse("/admin", 303)
    r.set_cookie("bookflow_admin", key, httponly=True, samesite="lax")
    return r
@app.get("/admin/logout")
def logout():
    r = RedirectResponse("/admin/login", 303); r.delete_cookie("bookflow_admin"); return r

@app.get("/admin", response_class=HTMLResponse)
def admin(request: Request):
    if not admin_ok(request): return RedirectResponse("/admin/login")
    with Session(engine) as s:
        key = request.cookies.get("bookflow_admin")
        b = s.scalar(select(Business).where(Business.admin_key == key))
        rows = []
        for a in s.scalars(select(Appointment).where(Appointment.business_id == b.id).order_by(Appointment.starts_at.desc()).limit(200)):
            rows.append((a, s.get(Service, a.service_id), s.get(Employee, a.employee_id)))
        services = list(s.scalars(select(Service).where(Service.business_id == b.id)))
        employees = list(s.scalars(select(Employee).where(Employee.business_id == b.id)))
        today = date.today(); today_count = sum(1 for a,_,_ in rows if a.starts_at.date() == today and a.status != "cancelled")
        upcoming = sum(1 for a,_,_ in rows if a.starts_at >= datetime.now() and a.status != "cancelled")
        customers = len({a.phone for a,_,_ in rows})
        revenue = sum(svc.price_rsd for a,svc,_ in rows if a.status == "done")
        return templates.TemplateResponse(request, "admin.html", {"b": b, "rows": rows, "services": services, "employees": employees, "today_count": today_count, "upcoming": upcoming, "customers": customers, "revenue": revenue})

@app.post("/admin/{aid}/status")
def status(request: Request, aid: int, status: str = Form(...)):
    if not admin_ok(request): raise HTTPException(403)
    if status not in {"confirmed", "done", "cancelled", "no_show"}: raise HTTPException(400)
    with Session(engine) as s:
        a = s.get(Appointment, aid)
        if not a: raise HTTPException(404)
        a.status = status; s.commit()
    return RedirectResponse("/admin", 303)

@app.post("/admin/service")
def add_service(request: Request, name: str = Form(...), duration_min: int = Form(...), price_rsd: int = Form(...)):
    if not admin_ok(request): raise HTTPException(403)
    with Session(engine) as s:
        key = request.cookies.get("bookflow_admin")
        b = s.scalar(select(Business).where(Business.admin_key == key))
        s.add(Service(business_id=b.id, name=name, duration_min=duration_min, price_rsd=price_rsd)); s.commit()
    return RedirectResponse("/admin#settings", 303)

@app.post("/admin/employee")
def add_employee(request: Request, name: str = Form(...)):
    if not admin_ok(request): raise HTTPException(403)
    with Session(engine) as s:
        key = request.cookies.get("bookflow_admin")
        b = s.scalar(select(Business).where(Business.admin_key == key))
        s.add(Employee(business_id=b.id, name=name)); s.commit()
    return RedirectResponse("/admin#settings", 303)






