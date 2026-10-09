<!-- source: https://developers.wallex.ir/docs/generated/prop-packages-list -->

# Prop Packages List

```
GET

## /v1/prop/packages

```

# GET v1/prop/packages

This endpoint retrieves a list of existing prop packages.

## Headers

This request does not require any custom header.

## Request Body Parameters

This request does not require a request body.

## Query Parameters

This request does not require any query parameters.

## Response

The response for this request is a JSON object with the following properties:

-

`result` (array[object])

  -

`id` (number)
  -

`title` (string)
  -

`currency` (string)
  -

`destination_currency` (string|null)
  -

`assurance` (string)
  -

`loan` (string)
  -

`warning_limit` (string)
  -

`liquidity_limit` (string)
  -

`status` (string)
  -

`expire_days` (number)
  -

`dark_image_url` (string)
  -

`light_image_url` (string)
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

`message` (string)
-

`success` (boolean)

## Example Response

```
{
    "result": [
        {
            "id": 81,
            "title": "طرح ۱۷",
            "currency": "TMN",
            "destination_currency": null,
            "assurance": "20000000",
            "loan": "200000000",
            "warning_limit": "250000000",
            "liquidity_limit": "240000000",
            "status": "INACTIVE",
            "expire_days": 30,
            "dark_image_url": "https://s3.thr1.sotoon.ir/phinix-public-staging/packages/clHyoeip3vrFmJvxRbjMP42h8PYDSWcKeo0zkQZO.jpg",
            "light_image_url": "https://s3.thr1.sotoon.ir/phinix-public-staging/packages/clHyoeip3vrFmJvxRbjMP42h8PYDSWcKeo0zkQZO.jpg",
            "daily_fee": "300000",
            "daily_fee_discount": "0",
            "daily_fee_after_discount": "300000",
            "final_fee": "9000000",
            "final_fee_discount": "0",
            "final_fee_after_discount": "9000000"
        },
    ],
    "message": "عملیات با موفقیت انجام شد",
    "success": true
}

```

## Request

## Responses

- 200

200**Response Headers**
**Connection****Content-Encoding****Date****Server****Transfer-Encoding****Vary****alt-svc****cache-control****vary****x-auth-cache-status****x-authenticated****x-envoy-upstream-service-time**
