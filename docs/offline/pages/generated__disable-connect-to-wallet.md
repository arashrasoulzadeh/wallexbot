<!-- source: https://developers.wallex.ir/docs/generated/disable-connect-to-wallet -->

# Disable Connect To Wallet

```
DELETE

## /v1/prop/user/packages/connect-to-wallet

```

# DELETE /v1/prop/user/packages/connect-to-wallet

This endpoint disables connect to wallet for a user package based on sub account.

## Headers

- `Sub-Account-Client-id` (string)

## Request Body Parameters

This request does not require a request body.

## Query Parameters

This request does not require any query parameters.

## Response

- `result` (array)
- `message` (string)
- `success` (boolean)

## Example Response

```
{
    "result": [],
    "message": "قطع اتصال کیف پول با موفقیت انجام شد",
    "success": true
}

```

## Request

## Responses

- 200

200**Response Headers**
**Cache-Control****Connection****Content-Encoding****Date****Server****Transfer-Encoding****Vary****X-RateLimit-Limit****X-RateLimit-Remaining****X-Robots-Tag****alt-svc**
