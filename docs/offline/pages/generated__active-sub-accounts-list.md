<!-- source: https://developers.wallex.ir/docs/generated/active-sub-accounts-list -->

# Active Sub Accounts List

```
GET

## /sub-accounts

```

# GET /sub-accounts

This endpoint retrieves the list of active sub-accounts.

## Headers

This request does not require any custom header.

## Request Body Parameters

This request does not require a request body.

## Query Parameters

This request does not require any query parameters.

## Response

-

`result` (array[object])

  -

`userId` (number)
  -

`title` (string)
  -

`darkAvatarUrl` (string)
  -

`lightAvatarUrl` (string)
  -

`clientId` (string)
  -

`isActive` (bool)
  -

`type` (string)
  -

`isSuspend` (bool)
  -

`createdAt` (string)

-

`message` (string)
-

`success` (boolean)
-

`result_info` (object)

  -

`page` (number)
  -

`per_page` (number)
  -

`count` (number)
  -

`total_count` (number)

## Example Response

```
{
    "result": [
        {
            "userId": 0,
            "title": "تست اولیه عادی",
            "darkAvatarUrl": "https://s3.thr1.sotoon.ir/phinix-public-staging/packages/clHyoeip3vrFmJvxRbjMP42h8PYDSWcKeo0zkQZO.jpg",
            "lightAvatarUrl": "https://s3.thr1.sotoon.ir/phinix-public-staging/packages/clHyoeip3vrFmJvxRbjMP42h8PYDSWcKeo0zkQZO.jpg",
            "clientId": "CLIENTID",
            "isActive": true,
            "type": "prop",
            "createdAt": "2025-04-06T11:53:18Z",
            "isSuspend": false
        },
        {
            "userId": 0,
            "title": null,
            "darkAvatarUrl": "https://s3.thr1.sotoon.ir/phinix-public-staging/packages/clHyoeip3vrFmJvxRbjMP42h8PYDSWcKeo0zkQZO.jpg",
            "lightAvatarUrl": "https://s3.thr1.sotoon.ir/phinix-public-staging/packages/clHyoeip3vrFmJvxRbjMP42h8PYDSWcKeo0zkQZO.jpg",
            "clientId": "CLIENTID",
            "isActive": true,
            "type": "trading_bot_trade",
            "createdAt": "2024-11-19T09:20:37Z",
            "isSuspend": false
        }
    ],
    "message": "عملیات با موفقیت انجام شد",
    "success": true,
    "result_info": {
        "page": 1,
        "per_page": 11,
        "count": 11,
        "total_count": 11
    }
}

```

## Responses

- 200

200**Response Headers**
**Connection****Content-Encoding****Date****Server****Transfer-Encoding****Vary****alt-svc****cache-control****vary****x-auth-cache-status****x-authenticated****x-envoy-upstream-service-time**
