<!-- source: https://developers.wallex.ir/docs/generated/enable-connect-to-wallet -->

# Enable Connect To Wallet

```
POST

## /v1/prop/user/packages/connect-to-wallet

```

# POST /v1/prop/user/packages/connect-to-wallet

This endpoint enables connect to wallet for a user package based on sub account.

## Headers

- `Sub-Account-Client-id` (string)

## Request Body Parameters

- `credit` (string)
- `usageCount` (number)
- `currency` (string)

## Query Parameters

This request does not require any query parameters.

## Response

-

`result` (object)

  -

`currency` (string)
  -

`credit` (string)
  -

`usageCount` (number)
  -

`usedCount` (number)
  -

`status` (string)

-

`message` (string)
-

`success` (boolean)

## Example Response

```
{
    "result": {
        "currency": "USDT",
        "credit": "10000",
        "usageCount": 3,
        "usedCount": 0,
        "status": "active"
    },
    "message": "اتصال کیف پول با موفقیت انجام شد",
    "success": true
}

```

## Request

## Responses

- 200

200**Response Headers**
**Cache-Control****Connection****Content-Encoding****Date****Server****Transfer-Encoding****Vary****X-RateLimit-Limit****X-RateLimit-Remaining****X-Robots-Tag****alt-svc**
