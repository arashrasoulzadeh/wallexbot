<!-- source: https://developers.wallex.ir/docs/generated/active-user-package-details -->

# Active User Package Details

```
GET

## /v1/prop/user/packages/active

```

# GET /v1/prop/user/packages/active

This endpoint retrieves the details of a user package based on sub account.

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

`packageDetail` (object)

    -

`id` (number)
    -

`title` (string)
    -

`assurance` (string)
    -

`loan` (string)
    -

`currency` (string)
    -

`destination_currency` (null|string)
    -

`dailyFee` (string)
    -

`dailyFeeDiscount` (string)
    -

`dailyFeeAfterDiscount` (string)
    -

`darkImageUrl` (string)
    -

`lightImageUrl` (string)
    -

`startBalance` (string)
    -

`expireDays` (number)

  -

`userPackageDetail` (object)

    -

`id` (number)
    -

`status` (string)
    -

`createdAt` (string)
    -

`expireAt` (string)
    -

`type` (string)
    -

`openDays` (number)
    -

`totalDays` (number)
    -

`cyclesCount` (number)
    -

`debtCyclesCount` (number)
    -

`paidCyclesCount` (number)
    -

`warningLimit` (string)
    -

`liquidityLimit` (string)
    -

`profit` (string)
    -

`profitPercentage` (string)
    -

`connectToWallet` (null|string)
    -

`finalFeeAfterDiscount` (string)
    -

`finalFee` (string)
    -

`finalPayableFeeAmount` (string)
    -

`finalPayback` (string)

  -

`alertsData` (array[object])

    - `type` (string)

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
        "packageDetail": {
            "id": 69,
            "title": "طرح ۵",
            "assurance": "1000000",
            "loan": "200000000",
            "currency": "TMN",
            "destination_currency": null,
            "dailyFee": "2000000000",
            "dailyFeeDiscount": "5000",
            "dailyFeeAfterDiscount": "1999995000",
            "darkImageUrl": "https://s3.thr1.sotoon.ir/phinix-public-staging/packages/clHyoeip3vrFmJvxRbjMP42h8PYDSWcKeo0zkQZO.jpg",
            "lightImageUrl": "https://s3.thr1.sotoon.ir/phinix-public-staging/packages/clHyoeip3vrFmJvxRbjMP42h8PYDSWcKeo0zkQZO.jpg",
            "startBalance": "201000000",
            "expireDays": 30
        },
        "userPackageDetail": {
            "id": 339,
            "status": "liquid",
            "createdAt": "2025-04-06T11:50:11.000000Z",
            "expireAt": "2025-05-06T11:50:11.000000Z",
            "type": "prop-public",
            "openDays": 1,
            "totalDays": 1,
            "cyclesCount": 1,
            "debtCyclesCount": 1,
            "paidCyclesCount": 0,
            "warningLimit": "2200795000",
            "liquidityLimit": "2200495000",
            "profit": "-1999995000",
            "profitPercentage": "-995.02",
            "connectToWallet": null,
            "finalFeeAfterDiscount": "59999850000",
            "finalFee": "60000000000",
            "finalPayableFeeAmount": "1999995000",
            "finalPayback": "2199995000"
        },
        "alertsData": [
            {
                "type": "public_warning_low_credit"
            }
        ],
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
