<!-- source: https://developers.wallex.ir/docs/generated/sub-account-transfer -->

# List Sub Account Transfers

```
GET

## /sub-accounts/transfers

```

# GET /sub-accounts/transfers

This endpoint retrieves transfer details for a sub-account.

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

`unique_id` (number)
  -

`source_client_id` (string)
  -

`source_client_title` (string)
  -

`destination_client_id` (string)
  -

`destination_client_title` (string)
  -

`source_user_type` (string)
  -

`destination_user_type` (string)
  -

`fa_source_user_type` (string)
  -

`fa_destination_user_type` (string)
  -

`currency` (string)
  -

`value` (string)
  -

`reason` (string)
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

## Request

## Responses

- 200

200**Response Headers**
**Connection****Content-Encoding****Date****Server****Transfer-Encoding****Vary****alt-svc****cache-control****vary****x-auth-cache-status****x-authenticated****x-envoy-upstream-service-time**
