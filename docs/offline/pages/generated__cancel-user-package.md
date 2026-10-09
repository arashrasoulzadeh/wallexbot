<!-- source: https://developers.wallex.ir/docs/generated/cancel-user-package -->

# Cancel User Package

```
DELETE

## /v1/prop/user/packages

```

# DELETE /v1/prop/user/packages

This endpoint cancels a user package based on sub account.

## Headers

- `Sub-Account-Client-id` (string)

## Request Body Parameters

This request does not require a request body.

## Query Parameters

This request does not require any query parameters.

## Response

-

`result` (object)

  -

`client_id` (string)
  -

`start_balance` (string)
  -

`final_balance` (string)
  -

`final_balance_without_transfers` (string)
  -

`currency` (string)
  -

`prop_package_id` (number)
  -

`user_id` (string)

-

`message` (string)
-

`success` (boolean)

## Example Response

```
{
    "result": {
        "client_id": "testClientId",
        "start_balance": "201000000",
        "final_balance": "201000000",
        "final_balance_without_transfers": "201000000",
        "currency": "TMN",
        "prop_package_id": 69,
        "user_id": "testUserId"
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
