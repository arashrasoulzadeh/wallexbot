<!-- source: https://developers.wallex.ir/docs/generated/activate-user-package -->

# Activate User Package

```
POST

## /v1/prop/user/packages

```

# POST /v1/prop/user/packages

This endpoint retrieves transfer details for sub-accounts.

## Headers

This request does not require any custom header.

## Request Body Parameters

- `prop_package_id` (string)

## Query Parameters

This request does not require any query parameters.

## Response

-

`result` (object)

  -

`userId` (string)
  -

`title` (string)
  -

`darkAvatarUrl` (string)
  -

`lightAvatarUrl` (string)
  -

`clientId` (string)
  -

`isActive` (boolean)
  -

`type` (string)
  -

`createdAt` (string)
  -

`isSuspend` (boolean)

-

`message` (string)
-

`success` (boolean)

## Example Response

```
{
    "result": {
        "userId": "0",
        "title": "تست اولیه عادی",
        "darkAvatarUrl": "https://s3.thr1.sotoon.ir/phinix-public-staging/packages/clHyoeip3vrFmJvxRbjMP42h8PYDSWcKeo0zkQZO.jpg",
        "lightAvatarUrl": "https://s3.thr1.sotoon.ir/phinix-public-staging/packages/clHyoeip3vrFmJvxRbjMP42h8PYDSWcKeo0zkQZO.jpg",
        "clientId": "CLIENTID",
        "isActive": true,
        "type": "prop",
        "createdAt": "2025-04-06T11:53:18Z",
        "isSuspend": false
    },
    "message": "عملیات با موفقیت انجام شد",
    "success": true
}

```

## Request

## Responses

- 201

201**Response Headers**
**Connection****Date****Server****Transfer-Encoding****alt-svc****cache-control****vary****x-auth-cache-status****x-authenticated****x-envoy-upstream-service-time****x-ratelimit-limit****x-ratelimit-remaining**
