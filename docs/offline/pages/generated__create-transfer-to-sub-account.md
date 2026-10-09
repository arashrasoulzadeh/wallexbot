<!-- source: https://developers.wallex.ir/docs/generated/create-transfer-to-sub-account -->

# Create Transfer To Sub Account

```
POST

## /sub-accounts/transfers

```

# POST /sub-accounts/transfers

This endpoint Submits Transfer from master account to sub-account.

## Headers

This request does not require any custom header.

## Request Body Parameters

-

`currency` (string)
-

`value` (number)
-

`subAccount_client_id` (string)

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

## Example Response

200

```
{
    "result": {
        "userId": 0,
        "title": "تست اولویت",
        "darkAvatarUrl": "https://s3.thr1.sotoon.ir/phinix-public-staging/packages/clHyoeip3vrFmJvxRbjMP42h8PYDSWcKeo0zkQZO.jpg",
        "lightAvatarUrl": "https://s3.thr1.sotoon.ir/phinix-public-staging/packages/clHyoeip3vrFmJvxRbjMP42h8PYDSWcKeo0zkQZO.jpg",
        "clientId": "CLIENTID",
        "isActive": true,
        "type": "prop",
        "createdAt": "2024-09-08T13:35:27Z",
        "isSuspend": false
    },
    "message": "عملیات با موفقیت انجام شد",
    "success": true
}

```

## 422

```
{
    "result": {
        "currency": [
            "انتقال ارز BTC به این اکانت مجاز نمی باشد."
        ]
    },
    "message": "اطلاعات وارد شده اشتباه است",
    "success": false,
    "code": 422
}

```

## Request

## Responses

- 200
- 422

200**Response Headers**
**Cache-Control****Connection****Content-Encoding****Date****Server****Transfer-Encoding****Vary****X-Robots-Tag****alt-svc**

422**Response Headers**
**Cache-Control****Connection****Date****Server****Transfer-Encoding****Vary****X-Robots-Tag**
