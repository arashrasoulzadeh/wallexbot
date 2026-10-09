<!-- source: https://developers.wallex.ir/docs/generated/active-user-packages-overview -->

# Active User Packages Overview

```
GET

## /v1/prop/user/packages/overview

```

# GET /v1/prop/user/packages/overview

This endpoint retrieves an overview of active user packages

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

`aggregatedDetail` (object)

    -

`currency` (string)
    -

`assurance` (string)
    -

`loan` (string)
    -

`profit` (string)
    -

`profitPercentage` (string)

  -

`userPackages` (array[object])

    -

`packageDetail` (object)

      -

`title` (string)
      -

`assurance` (string)
      -

`loan` (string)
      -

`currency` (string)
      -

`darkImageUrl` (string)
      -

`lightImageUrl` (string)
      -

`expireDays` (number)

  -

`userPackageDetail` (object)

    -

`id` (number)
    -

`subAccountClientId` (string)
    -

`status` (string)
    -

`createdAt` (string)
    -

`expireAt` (string)
    -

`profit` (string)
    -

`profitPercentage` (string)

  -

`balancesHistory` (object)

    -

`total` (object)

      -

`TMN` (number)
      -

`USDT` (number)
      -

`BTC` (number)

    -

`perDay` (object)

      -

(object)

        -

`TMN` (number)
        -

`USDT` (number)
        -

`BTC` (number)

-

`message` (string)
-

`success` (boolean)

## Example Response

```
{
    "result": {
        "aggregatedDetail": {
            "currency": "TMN",
            "assurance": "1000000",
            "loan": "200000000",
            "profit": "-1999995000",
            "profitPercentage": "-995.02"
        },
        "userPackages": [
            {
                "packageDetail": {
                    "title": "طرح ۵",
                    "assurance": "1000000",
                    "loan": "200000000",
                    "currency": "TMN",
                    "darkImageUrl": "https://s3.thr1.sotoon.ir/phinix-public-staging/packages/clHyoeip3vrFmJvxRbjMP42h8PYDSWcKeo0zkQZO.jpg",
                    "lightImageUrl": "https://s3.thr1.sotoon.ir/phinix-public-staging/packages/clHyoeip3vrFmJvxRbjMP42h8PYDSWcKeo0zkQZO.jpg",
                    "expireDays": 30
                },
                "userPackageDetail": {
                    "id": 339,
                    "subAccountClientId": "CLIENTID",
                    "status": "liquid",
                    "createdAt": "2025-04-06T11:50:11.000000Z",
                    "expireAt": "2025-05-06T11:50:11.000000Z",
                    "profit": "-1999995000",
                    "profitPercentage": "-995.02"
                },
                "balancesHistory": {
                    "total": {
                        "TMN": 201000000,
                        "USDT": 1939.087567651003,
                        "BTC": 0.023551144650712032
                    },
                    "perDay": {
                        "2025-04-06": {
                            "TMN": 201000000,
                            "USDT": 1939.087567651003,
                            "BTC": 0.023551144650712032
                        }
                    }
                }
            }
        ]
    },
    "message": "عملیات با موفقیت انجام شد",
    "success": true
}

```

## Responses

- 200

200**Response Headers**
**Connection****Content-Encoding****Date****Server****Transfer-Encoding****Vary****alt-svc****cache-control****vary****x-auth-cache-status****x-authenticated****x-envoy-upstream-service-time****x-ratelimit-limit****x-ratelimit-remaining**
