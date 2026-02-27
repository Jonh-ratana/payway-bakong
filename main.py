import os
import base64
from datetime import UTC, datetime, timedelta
import asyncio

from bakong_khqr import KHQR
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

load_dotenv(dotenv_path=".env")

API_TOKEN = os.getenv("TOKEN")
if not API_TOKEN:
    raise RuntimeError("Missing TOKEN in .env")

BASE_URL = os.getenv("BASE_URL", "").rstrip("/")
DEFAULT_BANK_ACCOUNT = os.getenv("DEFAULT_BANK_ACCOUNT", "pisethnorak_cheav@aclb")
DEFAULT_MERCHANT_NAME = os.getenv("DEFAULT_MERCHANT_NAME", "TECHEY")
DEFAULT_MERCHANT_CITY = os.getenv("DEFAULT_MERCHANT_CITY", "Phnom Penh")
DEFAULT_CURRENCY = os.getenv("DEFAULT_CURRENCY", "USD")
DEFAULT_STORE_LABEL = os.getenv("DEFAULT_STORE_LABEL", "IRCT SHOP")
DEFAULT_PHONE_NUMBER = os.getenv("DEFAULT_PHONE_NUMBER", "060535771")
DEFAULT_TERMINAL_LABEL = os.getenv("DEFAULT_TERMINAL_LABEL", "WebQR")
DEFAULT_CALLBACK_BASE = os.getenv(
    "DEFAULT_CALLBACK_BASE",
    "https://chanrithshop.com/payment",
).rstrip("/")
DEFAULT_APP_ICON_URL = os.getenv(
    "DEFAULT_APP_ICON_URL",
    "https://chanrithshop.com/assets/images/logo.png",
)
DEFAULT_APP_NAME = os.getenv("DEFAULT_APP_NAME", "IRCT SHOP")
QR_DURATION_MINUTES = int(os.getenv("QR_DURATION_MINUTES", "5"))

khqr = KHQR(API_TOKEN)

app = FastAPI(title="Bakong PayWay API", version="1.0.0")

ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv("ALLOWED_ORIGINS", "*").split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

PAYMENT_STORE: dict[str, dict] = {}


class PaywayRequest(BaseModel):
    bank_account: str = Field(default=DEFAULT_BANK_ACCOUNT, example="pisethnorak_cheav@aclb")
    merchant_name: str = Field(default=DEFAULT_MERCHANT_NAME, example="TECHEY")
    merchant_city: str = Field(default=DEFAULT_MERCHANT_CITY, example="Phnom Penh")
    amount: float = Field(..., gt=0  )
    currency: str = Field(default=DEFAULT_CURRENCY, pattern="^(USD|KHR)$", example="USD")
    store_label: str = Field(default=DEFAULT_STORE_LABEL, example="IRCT SHOP")
    phone_number: str = Field(default=DEFAULT_PHONE_NUMBER, example="060535771")
    bill_number: str = Field(..., example="TRX123457")
    terminal_label: str = Field(default=DEFAULT_TERMINAL_LABEL, example="WebQR")
    static: bool = False
    callback: str | None = Field(default=None, example="https://chanrithshop.com/payment/trx123457/callback")
    appIconUrl: str = Field(default=DEFAULT_APP_ICON_URL, example="https://chanrithshop.com/assets/images/logo.png")
    appName: str = Field(default=DEFAULT_APP_NAME, example="IRCT SHOP")


class PaywayResponse(BaseModel):
    qr_string: str
    qr_base64: str
    deeplink: str | None
    md5: str
    expires_at: str
    status_url: str
    ws_status_url: str
    warning: str | None = None


class PaymentStatusResponse(BaseModel):
    md5: str
    status: str
    expires_at: str | None = None
    is_expired: bool | None = None
    payment_data: dict | None = None
    warning: str | None = None


@app.get("/")
def healthcheck():
    return {"status": "ok", "service": "bakong-payway-api"}


def resolve_payment_status(md5: str) -> PaymentStatusResponse:
    payment_info = PAYMENT_STORE.get(md5)
    now = datetime.now(UTC)
    expires_at = payment_info["expires_at"] if payment_info else None

    try:
        status = khqr.check_payment(md5=md5)
    except Exception as exc:
        return PaymentStatusResponse(
            md5=md5,
            status="UNKNOWN",
            expires_at=expires_at.isoformat() if expires_at else None,
            is_expired=(now > expires_at) if expires_at else None,
            warning=f"Status check failed: {exc}",
        )

    if status == "PAID":
        payment_data = khqr.get_payment(md5=md5)
        return PaymentStatusResponse(
            md5=md5,
            status="PAID",
            expires_at=expires_at.isoformat() if expires_at else None,
            is_expired=(now > expires_at) if expires_at else None,
            payment_data=payment_data,
        )

    if expires_at and now > expires_at:
        return PaymentStatusResponse(
            md5=md5,
            status="EXPIRED",
            expires_at=expires_at.isoformat(),
            is_expired=True,
        )

    return PaymentStatusResponse(
        md5=md5,
        status="UNPAID",
        expires_at=expires_at.isoformat() if expires_at else None,
        is_expired=(now > expires_at) if expires_at else None,
    )


@app.post("/api/payway/create", response_model=PaywayResponse)
def create_payway(payload: PaywayRequest):
    callback_url = payload.callback or f"{DEFAULT_CALLBACK_BASE}/{payload.bill_number}/callback"

    try:
        qr_string = khqr.create_qr(
            bank_account=payload.bank_account,
            merchant_name=payload.merchant_name,
            merchant_city=payload.merchant_city,
            amount=payload.amount,
            currency=payload.currency,
            store_label=payload.store_label,
            phone_number=payload.phone_number,
            bill_number=payload.bill_number,
            terminal_label=payload.terminal_label,
            static=payload.static,
        )
        md5 = khqr.generate_md5(qr=qr_string)
        qr_temp_path = khqr.qr_image(qr=qr_string)
        with open(qr_temp_path, "rb") as qr_file:
            qr_base64 = base64.b64encode(qr_file.read()).decode("ascii")
        try:
            os.remove(qr_temp_path)
        except OSError:
            pass
        expires_at = datetime.now(UTC) + timedelta(minutes=QR_DURATION_MINUTES)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Unable to generate QR payload: {exc}") from exc

    deeplink = None
    warning = None
    try:
        deeplink = khqr.generate_deeplink(
            qr=qr_string,
            callback=callback_url,
            appIconUrl=payload.appIconUrl,
            appName=payload.appName,
        )
    except Exception as exc:
        warning = f"Deeplink generation failed: {exc}"

    PAYMENT_STORE[md5] = {
        "bill_number": payload.bill_number,
        "expires_at": expires_at,
    }

    return PaywayResponse(
        qr_string=qr_string,
        qr_base64=f"data:image/png;base64,{qr_base64}",
        deeplink=deeplink,
        md5=md5,
        expires_at=expires_at.isoformat(),
        status_url=(
            f"{BASE_URL}/api/payway/status/{md5}"
            if BASE_URL
            else f"/api/payway/status/{md5}"
        ),
        ws_status_url=(
            f"{BASE_URL.replace('https://', 'wss://').replace('http://', 'ws://')}/ws/payway/status/{md5}"
            if BASE_URL
            else f"/ws/payway/status/{md5}"
        ),
        warning=warning,
    )


@app.get("/api/payway/status/{md5}", response_model=PaymentStatusResponse)
def check_payway_status(md5: str):
    return resolve_payment_status(md5)


@app.websocket("/ws/payway/status/{md5}")
async def watch_payway_status(websocket: WebSocket, md5: str):
    await websocket.accept()
    previous_status = None
    try:
        while True:
            status_response = resolve_payment_status(md5)
            if status_response.status != previous_status:
                await websocket.send_json(status_response.model_dump())
                previous_status = status_response.status
            if status_response.status in {"PAID", "EXPIRED"}:
                break
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        return
    finally:
        await websocket.close()
