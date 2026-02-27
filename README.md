# PayWay API (Frontend Endpoints)

Base URL:
`https://monica-fancy-hits-dancing.trycloudflare.com`

## 1) Create QR
- Method: `POST`
- URL: `/api/payway/create`
- Full URL: `https://monica-fancy-hits-dancing.trycloudflare.com/api/payway/create`
- Headers: `Content-Type: application/json`

Request body (frontend minimal):
```json
{
  "amount": 275.7,
  "bill_number": "TRX123457"
}
```

Response example:
```json
{
  "qr_string": "000201010212...",
  "qr_base64": "data:image/png;base64,iVBORw0K...",
  "deeplink": "bakong://...",
  "md5": "c8ebefab66cfc01280e4b93b463c316c",
  "expires_at": "2026-02-27T08:15:00+00:00",
  "status_url": "https://monica-fancy-hits-dancing.trycloudflare.com/api/payway/status/c8ebefab66cfc01280e4b93b463c316c",
  "ws_status_url": "wss://monica-fancy-hits-dancing.trycloudflare.com/ws/payway/status/c8ebefab66cfc01280e4b93b463c316c",
  "warning": null
}
```

Frontend display QR:
- Use `qr_base64` directly in `<img src="..." />`.

## 2) Check Payment Status (HTTP)
- Method: `GET`
- URL: `/api/payway/status/{md5}`
- Full URL example:
`https://monica-fancy-hits-dancing.trycloudflare.com/api/payway/status/c8ebefab66cfc01280e4b93b463c316c`

Response example:
```json
{
  "md5": "c8ebefab66cfc01280e4b93b463c316c",
  "status": "UNPAID",
  "expires_at": "2026-02-27T08:15:00+00:00",
  "is_expired": false,
  "payment_data": null,
  "warning": null
}
```

Possible `status` values:
- `UNPAID`
- `PAID`
- `EXPIRED`
- `UNKNOWN`

## 3) Real-time Status (WebSocket)
- Method: `WS`
- URL: `/ws/payway/status/{md5}`
- Full URL example:
`wss://monica-fancy-hits-dancing.trycloudflare.com/ws/payway/status/c8ebefab66cfc01280e4b93b463c316c`

Message example:
```json
{
  "md5": "c8ebefab66cfc01280e4b93b463c316c",
  "status": "PAID",
  "expires_at": "2026-02-27T08:15:00+00:00",
  "is_expired": false,
  "payment_data": {},
  "warning": null
}
```

## Frontend flow
1. `POST /api/payway/create`.
2. Show QR using `qr_base64`.
3. Connect `ws_status_url` for instant update.
4. Optional fallback: poll `status_url` every 1 second.
5. If `status === "PAID"`, show success.
6. If `status === "EXPIRED"`, ask user to regenerate QR.
