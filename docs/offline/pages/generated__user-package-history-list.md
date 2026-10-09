<!-- source: https://developers.wallex.ir/docs/generated/user-package-history-list -->

# User Package History List

```
GET

## /v1/prop/user/packages/history

```

# GET /v1/prop/user/packages/history

This endpoint retrieves the user packages history for a user.

## Headers

This request does not require any custom header.

## Request Body Parameters

This request does not require a request body.

## Query Parameters

This request does not require any query parameters.

## Response

-

`result` (array[object]):

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
-

`result_info` (object):

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
      "unique_id": 0,
      "source_client_id": "",
      "source_client_title": "",
      "destination_client_id": "",
      "destination_client_title": null,
      "source_user_type": "",
      "destination_user_type": "",
      "fa_source_user_type": "",
      "fa_destination_user_type": "",
      "currency": "",
      "value": "",
      "reason": "",
      "createdAt": ""
    }
  ],
  "message": "",
  "success": true,
  "result_info": {
    "page": 0,
    "per_page": 0,
    "count": 0,
    "total_count": 0
  }
}

```

## Responses

- 200

200**Response Headers**
**Connection****Content-Encoding****Date****Server****Transfer-Encoding****Vary****alt-svc****cache-control****vary****x-auth-cache-status****x-authenticated****x-envoy-upstream-service-time****x-ratelimit-limit****x-ratelimit-remaining**
