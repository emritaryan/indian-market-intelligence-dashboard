"""Local-only Kite login backend. Run from backend: python -m uvicorn main:app --reload"""
import json
import os
from pathlib import Path
from threading import RLock

import win32crypt
from fastapi import FastAPI, HTTPException, Request, Query
from fastapi.responses import JSONResponse
from kiteconnect import KiteConnect
from kiteconnect.exceptions import TokenException
from pydantic import BaseModel, SecretStr, Field

# Store outside OneDrive/the repository, encrypted for the current Windows user.
SESSION_FILE = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "NiftyDashboard" / "kite-session.bin"
LOCK = RLock()
app = FastAPI(title="Local Kite Dashboard")

@app.middleware("http")
async def local_only(request: Request, call_next):
    # Vite proxies /api to this loopback-only server. Block cross-site browser calls.
    allowed = {"http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:8000", "http://127.0.0.1:8000", "http://localhost:4173", "http://127.0.0.1:4173"}
    origin = request.headers.get("origin")
    host = request.headers.get("host", "").split(":")[0]
    if host not in {"localhost", "127.0.0.1", "testserver"} or (origin and origin not in allowed) or request.headers.get("sec-fetch-site") == "cross-site":
        return JSONResponse({"detail": "Only local dashboard requests are allowed."}, status_code=403)
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    return response

class LoginInput(BaseModel):
    api_key: str = Field(min_length=1, max_length=200)
    api_secret: SecretStr
    request_token: SecretStr


def save_session(api_key, access_token):
    payload = json.dumps({"api_key": api_key, "access_token": access_token}).encode()
    encrypted = win32crypt.CryptProtectData(payload, "Kite session", None, None, None, 0)
    SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
    temporary = SESSION_FILE.with_suffix(".tmp")
    temporary.write_bytes(encrypted)
    temporary.replace(SESSION_FILE)


def load_client():
    if not SESSION_FILE.exists():
        raise HTTPException(401, "Log in to connect your Kite account.")
    try:
        payload = win32crypt.CryptUnprotectData(SESSION_FILE.read_bytes(), None, None, None, 0)[1]
        saved = json.loads(payload)
        kite = KiteConnect(api_key=saved["api_key"], timeout=15)
        kite.set_access_token(saved["access_token"])
        return kite
    except Exception:
        raise HTTPException(401, "Saved session could not be loaded. Please log in again.") from None


def public_profile(profile):
    # Only these fields may leave the backend. Never return the SDK/session object.
    return {key: profile.get(key, [] if key in {"products", "exchanges"} else "")
            for key in ("user_name", "user_id", "products", "exchanges")}

@app.post("/api/login")
def login(values: LoginInput):
    with LOCK:
        try:
            kite = KiteConnect(api_key=values.api_key.strip(), timeout=15)
            session = kite.generate_session(values.request_token.get_secret_value().strip(), api_secret=values.api_secret.get_secret_value().strip())
            kite.set_access_token(session["access_token"])
            profile = kite.profile()
        except TokenException:
            raise HTTPException(401, "Kite rejected this login. Authorize again and use a fresh request token.") from None
        except Exception:
            raise HTTPException(502, "Could not connect to Kite. Check your credentials and connection, then retry.") from None
        try:
            save_session(values.api_key.strip(), session["access_token"])
        except Exception:
            raise HTTPException(500, "Could not securely save the session on this computer.") from None
        return {"profile": public_profile(profile)}

@app.get("/api/profile")
def profile():
    with LOCK:
        kite = load_client()
        try:
            return public_profile(kite.profile())
        except TokenException:
            SESSION_FILE.unlink(missing_ok=True)
            raise HTTPException(401, "Your Kite session expired. Please authorize and log in again.") from None
        except Exception:
            raise HTTPException(502, "Kite is temporarily unavailable. Your saved session is retained; retry shortly.") from None

@app.post("/api/logout")
def logout():
    with LOCK:
        SESSION_FILE.unlink(missing_ok=True)
    return {"ok": True}


# One background scan at a time keeps requests responsive and rate limits bounded.
from threading import Thread
from copy import deepcopy
from pydantic import model_validator
from signals import scan

SCAN_LOCK = RLock()
SCAN_JOB = {"status": "idle", "completed": 0, "total": 0}

class ScanInput(BaseModel):
    short_sma: int = Field(default=6, ge=1, le=249, strict=True)
    long_sma: int = Field(default=30, ge=2, le=250, strict=True)
    lookback_days: int = Field(default=730, ge=1, le=3650, strict=True)
    max_stocks: int = Field(default=100, ge=1, le=100, strict=True)

    @model_validator(mode="after")
    def ordered_periods(self):
        if self.short_sma >= self.long_sma:
            raise ValueError("Short SMA must be smaller than Long SMA.")
        return self


def update_scan(**values):
    with SCAN_LOCK:
        SCAN_JOB.update(values)


def run_scan(kite, settings):
    try:
        result = scan(kite, settings, update_scan)
        update_scan(status="complete", message="Scan complete", result=result)
    except TokenException:
        update_scan(status="error", auth_expired=True, message="Kite session expired. Please sign in again.")
    except Exception:
        update_scan(status="error", message="Scan could not start. Check the official CSV connection and Kite data access, then retry.")

@app.post("/api/signals", status_code=202)
def generate_signals(settings: ScanInput):
    kite = load_client()
    with SCAN_LOCK:
        if SCAN_JOB["status"] == "running":
            raise HTTPException(409, "A scan is already running. Wait for it to finish.")
        SCAN_JOB.clear()
        SCAN_JOB.update(status="running", completed=0, total=settings.max_stocks,
                        message="Loading official Nifty 100 constituents…")
        Thread(target=run_scan, args=(kite, settings.model_dump()), daemon=True).start()
        return deepcopy(SCAN_JOB)

@app.get("/api/signals")
def signal_status():
    load_client()
    with SCAN_LOCK:
        return deepcopy(SCAN_JOB)


from overview import quote_data, history_data, macro_data
from stock import members, stock_data, stock_chart_data, ipo_data

@app.get("/api/overview/quotes")
def overview_quotes():
    kite=load_client()
    try: return quote_data(kite)
    except TokenException:
        raise HTTPException(401, "Kite session expired. Please sign in again.") from None
    except Exception:
        raise HTTPException(502, "Kite quotes are unavailable. Please retry.") from None

@app.get("/api/overview/history")
def overview_history():
    kite=load_client()
    try: return history_data(kite)
    except TokenException:
        raise HTTPException(401, "Kite session expired. Please sign in again.") from None
    except Exception:
        raise HTTPException(502, "Historical charts are temporarily unavailable.") from None

@app.get("/api/overview/macro")
def overview_macro():
    load_client()
    return macro_data()

@app.get("/api/overview/ipos")
def overview_ipos():
    load_client()
    return ipo_data()

@app.get("/api/stocks")
def stock_list():
    load_client()
    return {"items": members(), "source": "Official Nifty 100 constituent file"}

@app.get("/api/stocks/{symbol}")
def stock_detail(symbol: str, range: str = Query(default="1Y", pattern="^(1M|3M|6M|YTD|1Y|3Y|5Y|MAX)$")):
    kite = load_client()
    try:
        return stock_data(kite, symbol, range)
    except TokenException:
        SESSION_FILE.unlink(missing_ok=True)
        raise HTTPException(401, "Kite session expired. Please sign in again.") from None
    except ValueError as error:
        raise HTTPException(400, str(error)) from None
    except Exception:
        raise HTTPException(502, "Stock data is temporarily unavailable. Please retry.") from None

@app.get("/api/stocks/{symbol}/chart")
def stock_chart(symbol: str, range: str = Query(default="1Y", pattern="^(1M|3M|6M|YTD|1Y|3Y|5Y|MAX)$")):
    kite = load_client()
    try:
        return stock_chart_data(kite, symbol, range)
    except TokenException:
        SESSION_FILE.unlink(missing_ok=True)
        raise HTTPException(401, "Kite session expired. Please sign in again.") from None
    except ValueError as error:
        raise HTTPException(400, str(error)) from None
    except Exception:
        raise HTTPException(502, "Stock chart is temporarily unavailable. Please retry.") from None
