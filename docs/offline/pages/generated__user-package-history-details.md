<!-- source: https://developers.wallex.ir/docs/generated/user-package-history-details -->

# User Package History Details

```
GET

## /v1/prop/user/packages/history/:subAccountClientId

```

# GET /v1/prop/user/packages/history/{subAccountClientId}

This endpoint retrieves the details for a historical user package.

## Headers

This request does not require any custom header.

## Request Body Parameters

This request does not require a request body.

## Query Parameters

This request does not require any query parameters.

## Response

-

`result` (object):

  -

`user_id` (number)
  -

`client_id` (string)
  -

`package_title` (string)
  -

`dark_image_url` (string)
  -

`light_image_url` (string)
  -

`currency` (string)
  -

`destination_currency` (string)
  -

`assurance` (string)
  -

`loan` (string)
  -

`final_balance` (string)
  -

`final_balance_without_transfers` (string)
  -

`start_balance` (string)
  -

`warning_limit` (string)
  -

`liquidity_limit` (string)
  -

`created_at` (string)
  -

`finished_at` (string)
  -

`expire_at` (string)
  -

`close_reason` (string)
  -

`status` (string)
  -

`expire_days` (number)
  -

`daily_fee` (string)
  -

`daily_fee_discount` (string)
  -

`daily_fee_after_discount` (string)
  -

`final_fee` (string)
  -

`final_fee_discount` (string)
  -

`final_fee_after_discount` (string)
  -

`open_days` (number)
  -

`total_days` (number)
  -

`applicable_daily_fee` (string)
  -

`applicable_daily_fee_discount` (string)
  -

`applicable_daily_fee_after_discount` (string)
  -

`profit` (string)
  -

`profit_percentage` (string)
  -

`final_assurance` (string)
  -

`final_payBack` (string)

-

`message` (string)
-

`success` (boolean)

## Example Response

```
{
    "result": {
        "user_id": testUserId,
        "client_id": "testClientId",
        "package_title": "طرح ۱۰",
        "dark_image_url": "https://s3.thr1.sotoon.ir/phinix-public-staging/packages/clHyoeip3vrFmJvxRbjMP42h8PYDSWcKeo0zkQZO.jpg",
        "light_image_url": "https://s3.thr1.sotoon.ir/phinix-public-staging/packages/clHyoeip3vrFmJvxRbjMP42h8PYDSWcKeo0zkQZO.jpg",
        "currency": "USDT",
        "destination_currency": "USDT",
        "assurance": "300",
        "loan": "1000",
        "final_balance": "1298.62",
        "final_balance_without_transfers": "1298.62",
        "start_balance": "1300",
        "warning_limit": "1001",
        "liquidity_limit": "1081",
        "created_at": "2025-02-08T08:47:00.000000Z",
        "finished_at": "2025-02-08T09:05:49.000000Z",
        "expire_at": "2025-03-10T08:47:00.000000Z",
        "close_reason": "بستن طرح",
        "status": "SUSPEND",
        "expire_days": 30,
        "daily_fee": "1",
        "daily_fee_discount": "0",
        "daily_fee_after_discount": "1",
        "final_fee": "30",
        "final_fee_discount": "0",
        "final_fee_after_discount": "30",
        "open_days": 1,
        "total_days": 1,
        "applicable_daily_fee": "1",
        "applicable_daily_fee_discount": "0",
        "applicable_daily_fee_after_discount": "1",
        "profit": "-2.38",
        "profit_percentage": "-0.18",
        "final_assurance": "297.62",
        "final_payBack": "1001"
    },
    "message": "عملیات با موفقیت انجام شد",
    "success": true
}

```

## Request

## Responses

- 200

200**Response Headers**
**Connection****Content-Encoding****Date****Server****Transfer-Encoding****Vary****alt-svc****cache-control****vary****x-auth-cache-status****x-authenticated****x-envoy-upstream-service-time****x-ratelimit-limit****x-ratelimit-remaining**
