<!-- source: https://developers.wallex.ir/docs/generated/enable-user-package-renew -->

# Enable User Package Renew

```
POST

## /v1/prop/user/packages/enable-renew

```

# POST /v1/prop/user/packages/enable-renew

This endpoint enables renewal for a user package based on sub account.

## Headers

- `Sub-Account-Client-id` (string)

## Request Body Parameters

This request does not require any body parameters.

## Query Parameters

This request does not require any query parameters.

## Response

-

`result` (array)
-

`message` (string)
-

`success` (boolean)

## Example Response

```
{
    "result": [],
    "message": "عملیات با موفقیت انجام شد",
    "success": true
}

```

## Request

## Responses

- 200

200**Response Headers**
**Cache-Control****Connection****Content-Encoding****Date****Server****Transfer-Encoding****Vary****X-RateLimit-Limit****X-RateLimit-Remaining****X-Robots-Tag****alt-svc**
