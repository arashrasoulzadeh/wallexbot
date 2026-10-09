<!-- source: https://developers.wallex.ir/docs/generated/prop-package-details -->

# Prop Package Details

```
GET

## /v1/prop/packages/:id

```

# GET v1/prop/packages/{id}

This endpoint retrieves the details for a prop package.

## Headers

This request does not require any custom header.

## Request Body Parameters

This request does not require a request body.

## Query Parameters

This request does not require any query parameters.

## Response

The response for this request is a JSON object with the following properties:

-

`result` (object)

  -

`detail` (number)

    -

`id` (string)
    -

`title` (string)
    -

`currency` (string)
    -

`destination_currency` (string)
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

`unavailableMarkets` (array[string])
  -

faq (array[string])

-

`message` (string)
-

`success` (boolean)

## Example Response

```
{
    "result": {
        "detail": {
            "id": 147,
            "title": "600 میلیون اعتبار معاملاتی",
            "currency": "TMN",
            "destination_currency": null,
            "assurance": "60000000",
            "loan": "600000000",
            "warning_limit": "642000000",
            "liquidity_limit": "624000000",
            "status": "INACTIVE",
            "expire_days": 30,
            "dark_image_url": "https://s3.thr1.sotoon.ir/wallex-public/packages/QrOWJudTqCA4BxKlRZ99vFcnkUG5SEWNBoK5ayu2.png",
            "light_image_url": "https://s3.thr1.sotoon.ir/wallex-public/packages/ceY4TTn6yQXvmUHZvy2g3e5B8zt6sGsI2XAQuhFl.png",
            "daily_fee": "600000",
            "daily_fee_discount": "0",
            "daily_fee_after_discount": "600000",
            "final_fee": "18000000",
            "final_fee_discount": "0",
            "final_fee_after_discount": "18000000"
        },
        "unavailableMarkets": [
            "WTMN",
            "METMN",
            "WUSDT"
        ],
        "faq": []
    },
    "message": "عملیات با موفقیت انجام شد",
    "success": true
}

```

## Request

## Responses

- 200

200**Response Headers**
**Connection****Content-Encoding****Date****Server****Transfer-Encoding****Vary****alt-svc****cache-control****vary****x-auth-cache-status****x-authenticated****x-envoy-upstream-service-time**
