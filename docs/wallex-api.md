# Wallex API Reference (local notes)

Source: https://developers.wallex.ir/docs (fetched 2026-10-09). Swagger downloads are linked from the
"basic-services" and "spot-intro" pages of that site. Items marked **[UNVERIFIED]** were not confirmed in the docs.

## 1. General

- Base URL: `https://api.wallex.ir` (the only official domain)
- WebSocket: `wss://api.wallex.ir/ws`
- All bodies and responses are JSON. Send `Content-Type: application/json` on every request.
- Number-like values are often **strings** (`"82494"`). Send price/quantity as strings.
- Timestamps: ISO-8601 datetime, or unix (seconds for REST candles, ms in WS private events).
- Typical response envelope: `{ "result": ..., "message": "...", "success": true }`
- Official SDKs: Node.js, PHP, Go, JavaScript, Python, Java. Support: Telegram `@wallexapi`, api@wallex.ir.

## 2. Authentication

- Create keys at https://wallex.ir/app/my-account/api-management (login + SMS/code confirm).
- Max **3 API keys** per account. A key is shown **only once**, so store it immediately.
- Each key has: name, expiry date ("active until"), permissions, optional IP whitelist.
  - Read: default.
  - Trade: needed to place/cancel orders.
  - Withdraw: needs the request IP to match the whitelisted IP. **Never enable for a bot.**
- The key goes in the request header **`x-api-key: <your key>`** (confirmed from the spot Swagger `securityDefinitions`).
- Swagger lists host `api.wallex.com`, while the prose docs say `api.wallex.ir` is the only official domain. Use `.ir`.
- Main account and each trade-credit (sub-)account have **separate** API keys.
  - Sub-account spot trading also needs header `sub-account-client-id: <id>`.
- Public endpoints (markets, depth, trades, candles) need no key. Private ones (`/v1/account/*`) do.

## 3. Rate limits

| Scope | Limit |
|---|---|
| Place order (`POST /v1/account/orders`) | **20 requests / 10 s** |
| Depth (`/v1/depth`), trades (`/v1/trades`) | Not published; docs warn repeated polling gets rate-limited. Use WebSocket instead. |
| Other REST | Not published |
| WebSocket | Server drops the connection after **30 min**; max **50 messages per channel**; server PINGs every 20 s, reply PONG to add 30 s (max 100 PONGs). Plan for auto-reconnect/resubscribe. |

## 4. Public REST endpoints

### GET `/hector/web/v1/markets`
All markets. Trade spot where `is_spot == true`.
Fields: `symbol, base_asset, quote_asset, fa_base_asset, fa_quote_asset, en_base_asset, en_quote_asset,
categories, price, change_24h, volume_24h, change_7D, quote_volume_24h, spot_is_new, otc_is_new, is_new,
is_spot, is_otc, is_margin, is_tmn_based, is_usdt_based, is_zero_fee, leverage_step, max_leverage,
created_at, amount_precision, price_precision, flags`.
Use `amount_precision` / `price_precision` to round orders. Min order size is not in these docs (**[UNVERIFIED]**).

### GET `/v1/depth?symbol=BTCUSDT`
`result.ask[]` = sellers, `result.bid[]` = buyers; each `{price, quantity, sum}`.

### GET `/v1/trades?symbol=BTCUSDT`
`result.latestTrades[]`: `{symbol, quantity, price, sum, isBuyOrder, timestamp}`.

### GET `/v1/udf/history` (candles / OHLC, TradingView UDF style)

**Observed behaviour differs from the documented resolutions (checked 2026-10-12 against the live API):**
`resolution=15` returns **1-minute** bars, `240` returns **hourly** bars, `60` hourly and `1D` daily bars are as
asked, and `1` returns 1-minute bars for windows up to about a day but `no_data` for a 3-day window. Do not rely on
the resolution number meaning minutes; check the spacing of `t` in the response.

Query: `symbol` (e.g. `BTCUSDT`), `resolution` (`1,15,60,240,480,720,1D,2D,3D`), `from`, `to` (unix seconds).
Response (parallel arrays): `{ s, t[], o[], h[], l[], c[], v[] }`.

## 5. Private REST endpoints (need API key)

### GET `/v1/account/balances`
`result.balances.<ASSET> = { asset, faName, value, locked, fiat, is_dust, is_digital_gold, ... }`.
`value` = total, `locked` = in open orders. (Main wallet only; separate from credit sub-accounts.)

### GET `/v1/account/fee`
`result.<SYMBOL> = { makerFeeRate, takerFeeRate, recent_days_sum }`. Fee tier depends on 30-day volume.

### POST `/v1/account/orders` : create order (201 on success)
| Field | Type | Req | Notes |
|---|---|---|---|
| `symbol` | string | yes | e.g. `BTCUSDT`, `USDTTMN` |
| `side` | string | yes | `BUY` \| `SELL` |
| `type` | string | yes | `LIMIT` \| `MARKET` \| `STOP_LIMIT` \| `STOP_MARKET` |
| `price` | string | yes | per docs required for all types (send it even for MARKET; **[UNVERIFIED]** whether ignored) |
| `quantity` | string | yes | base-asset amount |
| `stop_Price` | string | conditional | required only for STOP_* types, must NOT be sent otherwise (note capital P) |
| `client_id` | string | no | `A-Z`, `_`, `0-9`; must be unique or the order is rejected. Auto-generated if omitted. |

Response `result`: `clientOrderId, symbol, side, type, status, active, price, stopPrice, stopPriceCondition,
origQty, executedQty, executedPrice, executedSum, executedPercent, sum, fee, fills[], created_at, updated_at, transactTime`.
`fills[]`: `{price, quantity, sum, fee, feeAsset, feeCoefficient, makerFeeCoefficient, takerFeeCoefficient, isBuyer, symbol, timestamp}`.
Status codes: 201 ok, 400 bad params, 401 unauthorized, 422 validation error.
Status values seen: `NEW`; also FINISHED (fully executed). Others **[UNVERIFIED]**.

### DELETE `/v1/account/orders/{client_id}` : cancel
Only while not FINISHED (partially filled orders can be cancelled). Returns the order object.

### GET `/v1/account/orders/{client_id}` : order detail
Same order object (status, fills, fees).

### GET `/v1/account/orders` : order history
Query: `from`, `to` (`YYYY-MM-DD`), `page` (>=1), `per_page` (>=1), `type`, `side`, `market`.
Response `result` is a map `symbol -> order[]`, plus `result_info` (pagination).

### GET `/v1/account/openOrders` : active orders
Query: `symbol`, `page`, `per_page`. Same grouped shape.

## 6. Order type semantics

- **LIMIT**: rests in the book at your price.
- **MARKET**: fills immediately at best prices, possibly in multiple fills.
  **Auto-cancelled if quantity exceeds book depth or would move the last price by more than 2%.**
- **STOP_LIMIT**: not in the book until the last trade price crosses `stop_Price`
  (stop < last price: triggers when last <= stop; stop > last price: triggers when last >= stop),
  then behaves as LIMIT.
- **STOP_MARKET**: same trigger rule, then behaves as MARKET.

## 7. WebSocket

Connect `wss://api.wallex.ir/ws`, then send subscribe frames as JSON arrays:

```json
["subscribe", { "channel": "USDTTMN@buyDepth" }]
```

| Channel | Payload |
|---|---|
| `<MARKET>@buyDepth` | `["USDTTMN@buyDepth", [{quantity, price, sum}, ...]]` (bids) |
| `<MARKET>@sellDepth` | same shape (asks) |
| `<MARKET>@trade` | `["USDTTMN@trade", {isBuyOrder, quantity, price, timestamp}]` |
| `all@price` | `["all@price", {symbol, price, "24h_ch"}]` all markets, no per-market subscribe needed |
| `<STREAMKEY>` (private) | events `balanceUpdated`, `orderSaved` |
| `<STREAMKEY>@tradeDetails` | per-fill event: `{clientOrderID, feeAmount, feeCurrency, isMaker, price, quantity, side, sum, symbol}` |

Private events:
- `balanceUpdated`: `data.<ASSET> = {asset, faName, value, locked}`
- `orderSaved`: `data = {symbol, side, clientOrderId, price, origQty, executedQty, status, active}`

`STREAMKEY` (`stream_key`) comes from the **login API response**, i.e. a user session, not the API key.
**[UNVERIFIED]** whether it can be obtained with an API key alone; for a bot, plan to poll `openOrders` instead.

## 7b. Extra facts from the Swagger files

Swagger JSON URLs (relative to https://developers.wallex.ir), swagger 2.0:
- basic: `/assets/files/basic-services-89626420b5f06e4d7a2dc9206cdeb192.json`
- spot: `/assets/files/spot-b9d06896d1009adc9ebc69b9a5495e7e.json`
- margin: `/assets/files/margin-c709e1f52cb44387a2e35ffd678c6dfa.json`
- otc: `/assets/files/otc-8e321a32f4509cbf103b3127bf7c9918.json`
- trade-credit: no Swagger link found

Additional endpoints:
- `GET /depth/all`: depth for all markets in one call. `result` is a map `symbol -> {ask[], bid[]}`.
- `GET /v1/account/wallets/{symbol}`: wallet for a single coin (deposit info).
- `DELETE /v1/account/orders` with JSON body `{"clientOrderId": "..."}` also cancels (alternative to the path form).
- Sub-account order bodies (trade credit) add `subAccount_client_id`; cancel body uses
  `{client_order_id, subAccount_client_id}`.

Schema details:
- Create-order body: only `side`, `symbol`, `type` are marked required in Swagger. `price`/`quantity` are
  optional by schema but the prose says required; always send `quantity`, and `price` for LIMIT/STOP_LIMIT.
- Order enums: `type` in `STOP_LIMIT, STOP_MARKET, LIMIT, MARKET`; `side` in `BUY, SELL`.
  `status` is a free string in Swagger (no enum published).
- Order list query: `market, type, side, page, per_page, from, to`.
- **Error body** (`ErrorResponse`): `{ "code": int, "message": string, "result": {field: [errors]}, "success": false }`.
  Error codes: 400 bad params, 401 unauthorized, 422 validation, 500 server.

## 8. Other services (summary of endpoints)

Margin (`/margin-trade/v1/...`): `GET orders`, `GET|POST positions`, `GET positions/{id}`,
`PATCH positions/{id}/close|collateral|sltp`, `POST positions/{id}/profit`, `POST public/loan`,
`POST public/dry-run`, `GET public/markets`, `GET public/ratio/{market}`, `GET user/levels[/{market}]`, `GET user/pnl`.

OTC: `GET /v1/otc/markets`, `GET /v1/account/otc/price`, `POST /v1/account/easy-trade/orders`.

Banking (do not use from a bot): `POST|GET /v1/account/ibans`, `POST /v1/account/money-withdrawal`, `GET /v1/account/card-numbers`.

Full request/response detail for these is in the Swagger files above (not transcribed).

### Page slugs (not read in detail)

Doc pages exist for these; read them when needed (`https://developers.wallex.ir/docs/<slug>`):
- **Margin**: `margin-active-markets, margin-calculate-loan, margin-dry-run, margin-open-position,
  margin-get-positions, margin-edit-collateral, margin-sltp-edit, margin-close-position`
- **Trade credit (sub-accounts / prop packages)**: `trade-credit-active-packages, -package-details,
  -condition-check, -activate-sub-account, -connect-wallet, -disconnect-wallet, -close-sub-account,
  -sub-account-history, -active-sub-account-list`
- **OTC**: `otc-markets, otc-price, otc-create-order`
- **Banking**: `basic-services-add-iban, -iban-numbers, -card-numbers, -withdraw-toman, -coin-wallets`
  (withdrawals: do not use from a bot)

## 9. Notes for the bot

- Symbols are concatenated, no separator: `BTCUSDT`, `USDTTMN`.
- Always round price/quantity to the market's `price_precision` / `amount_precision`.
- Use `client_id` as an idempotency key: generate it before sending, so a timeout can be resolved by GET-ing that id.
- Prefer WebSocket for prices/depth; REST depth/trades polling risks rate limits.
- Budget order placement under 20 per 10 s (grid rebuilds can hit this).
- Fees: read `/v1/account/fee`; account for maker+taker in every profit calculation.
- Still unknown (not in docs): min order size/notional, full order `status` enum, rate limits for non-order
  endpoints. Determine these empirically (small dry orders) or by asking api@wallex.ir / @wallexapi.
- Trade-credit (prop packages) endpoints are only known by name; no Swagger was published for them.
