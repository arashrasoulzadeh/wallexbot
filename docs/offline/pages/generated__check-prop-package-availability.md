<!-- source: https://developers.wallex.ir/docs/generated/check-prop-package-availability -->

# Check Prop Package Availability

```
GET

## /v1/prop/user/packages/:id/check-availability

```

# GET /v1/prop/user/packages/{id}/check-availability

This endpoint checks the availability of a prop package for a user based on different criteria.

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

`key` (string)
  -

`isValid` (boolean)

-

`message` (string)
-

`success`

## Example Response

```
{
    "result": [
        {
            "key": "kyc",
            "isValid": true
        }
    ],
    "message": "عملیات با موفقیت انجام شد",
    "success": true
}

```

## Request

## Responses

- 200

200**Response Headers**
**Cache-Control****Connection****Content-Encoding****Date****Server****Transfer-Encoding****Vary****X-RateLimit-Limit****X-RateLimit-Remaining****X-Robots-Tag****alt-svc**
