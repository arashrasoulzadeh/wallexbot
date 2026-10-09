<!-- source: https://developers.wallex.ir/docs/generated/sub-account-balances-details -->

# Sub Account Balances Details

```
GET

## /v1/account/balances-detail

```

# GET /v1/account/balances-detail

This endpoint retrieves the detailed balance information for the account.

## Headers

This request does not require any custom header.

## Request Body Parameters

This request does not require a request body.

## Query Parameters

This request does not require any query parameters.

## Response

-

`result` (object)

  -

`CURRENCY` (object) // balance currency symbol

    -

`symbol` (string)
    -

`total` (string)
    -

`freeze` (string)
    -

`available` (string)
    -

`stats` (object)

      -

`BTC` (object)

        -

`baseMarketName` (string)
        -

`changePercentage` (string)
        -

`estimatedValue` (string)
        -

`last24HoursEstimatedValueChange` (string)

      -

`USDT` (object)

        -

`baseMarketName` (string)
        -

`changePercentage` (string)
        -

`estimatedValue` (string)
        -

`last24HoursEstimatedValueChange` (string)

      -

`TMN` (object)

        -

`changePercentage` (string)
        -

`estimatedValue` (string)
        -

`last24HoursEstimatedValueChange` (string)

-

`message` (string)
-

`success` (boolean)

## Example Response

```
{
    "result": {
        "TMN": {
            "symbol": "TMN",
            "total": "0",
            "freeze": "0",
            "available": "0",
            "stats": {
                "BTC": {
                    "baseMarketName": "BTC",
                    "changePercentage": "7.69",
                    "estimatedValue": "0.00",
                    "last24HoursEstimatedValueChange": "0.00"
                },
                "USDT": {
                    "baseMarketName": "USDT",
                    "changePercentage": "-1.00",
                    "estimatedValue": "0.00",
                    "last24HoursEstimatedValueChange": "0.00"
                },
                "TMN": {
                    "changePercentage": "0.00",
                    "estimatedValue": "0",
                    "last24HoursEstimatedValueChange": "0"
                }
            }
        },
        "USDT": {
            // similar to TMN
        },
        "BTC": {
            // similar to BTC
        }
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
