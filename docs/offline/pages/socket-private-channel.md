<!-- source: https://developers.wallex.ir/docs/socket-private-channel -->

### event های خصوصی کاربران

کانال‌های خصوصی WebSocket در والکس به کاربران احراز هویت‌شده اجازه می‌دهند تا تغییرات شخصی مربوط به حساب خود را به‌صورت **لحظه ای** دریافت کنند.
این event ها شامل به‌روزرسانی موجودی، وضعیت سفارش‌ها، و پیام‌های اطلاع‌رسانی هستند.

### آدرس اتصال WebSocket

برای اتصال باید از آدرس زیر استفاده کنید

```
wss://api.wallex.ir/ws

```

### فرمت پیام Subscribe

برای دریافت ایونت های خصوصی باید پیام خود را با فرمت زیر ارسال کنید

```
["subscribe", { "channel": "STREAMKEY" }]

```

توجه داشته باشید در هنگام لاگین به والکس در مرحله ی آخر یک کلید به نام `stream_key` در پاسخ ای پی آی دریافت میکنید که باید جایگزین STREAMKEY قرار دهید

### event های بروزرسانی موجودی کیف پول(balanceUpdated)

پس از هرگونه واریز ، برداشت ، یا ساخت سفارش و انجام معامله که در پی آن موجودی کیف پول شما آپدیت میشود ، شما یک ایونت دریافت میکنید

| فیلد | نوع | توضیح |
| --- | --- | --- |
| event | string | balanceUpdated |
| timestamp | timestamp | زمان بروزرسانی موجودی |
| price | String (decimal) | قیمت انجام معامله |
| asset | String | ارز اپدیت شده در کیف پول کاربر |
| value | String | مقدار موجود در کیف پول |
| locked | String | میزان دارایی فریز شده کاربر(زمان برداشت یا انجام یک معامله) |

```
[
  "STREAMKEY",
  {
    "event": "balanceUpdated",
    "timestamp": 1748773416376,
    "data": {
      "TMN": {
        "asset": "TMN",
        "faName": "تومان",
        "value": "16033085",
        "locked": "2507491"
      }
    }
  }
]

```

### ثبت سفارش جدید یا بروزرسانی سفارش (orderSaved)

پس از ثبت سفارش جدید و یا بروزرسانی سفارش ها ، eventهایی که در خصوص آن دریافت میکنید به شرح زیر میباشد.

| فیلد | نوع | توضیح |
| --- | --- | --- |
| event | string | orderSaved |
| timestamp | timestamp | زمان بوجود آمدن اوردر جدید |
| price | String (decimal) | قیمت هر واحد |
| symbol | String | نام مارکت |
| side | String | BUY , SELL |
| origiQty | String | حجم سفارش |
| executedQty | String | مقدار معامله شده |
| status | String | NEW |
| active | Boolean | وضعیت فعال بودن سفارش گذاشته شده |

```
[
  "streamKey",
  {
    "event": "orderSaved",
    "timestamp": 1748773416414,
    "data": {
      "symbol": "USDTTMN",
      "side": "BUY",
      "clientOrderId": "LIMIT-xxxx",
      "price": "82102.0000000000000000",
      "origQty": "10.0000000000000000",
      "executedQty": "0.0000000000000000",
      "status": "NEW",
      "active": true
    }
  }
]

```

### جزئیات معاملات (tradeDetails)

این کانال اطلاعات مربوط به هر معامله انجام‌شده روی سفارش‌های شما را به‌صورت لحظه‌ای ارسال می‌کند. با هر بار انجام شدن بخشی یا تمام یک سفارش، یک رویداد `tradeDetails` دریافت خواهید کرد که شامل اطلاعات معامله انجام‌شده، کارمزد، قیمت و مقدار معامله است.

#### فرمت پیام Subscribe

برای دریافت رویدادهای جزئیات معاملات، پیام زیر را ارسال کنید:

```
["subscribe", { "channel": "STREAMKEY@tradeDetails" }]

```

در این پیام، مقدار `STREAMKEY` همان `stream_key` دریافتی در پاسخ API لاگین است.

#### رویداد جزئیات معامله (tradeDetails)

پس از انجام هر معامله روی سفارش‌های شما، رویدادی با مشخصات زیر ارسال می‌شود.

| فیلد | نوع | توضیح |
| --- | --- | --- |
| event | String | مقدار ثابت `tradeDetails` |
| timestamp | Timestamp | زمان انجام معامله |
| symbol | String | نام مارکت |
| side | String | سمت سفارش (`BUY` یا `SELL`) |
| price | String (decimal) | قیمت انجام معامله |
| quantity | String (decimal) | مقدار معامله انجام‌شده |
| sum | String (decimal) | ارزش کل معامله |
| feeAmount | String (decimal) | مقدار کارمزد معامله |
| feeCurrency | String | ارز کارمزد |
| isMaker | Boolean | مشخص می‌کند معامله از نوع Maker بوده یا Taker |
| clientOrderID | String | شناسه سفارش کاربر |

#### نمونه پیام

```
[
  "STREAMKEY@tradeDetails",
  {
    "event": "tradeDetails",
    "timestamp": 1782663892725,
    "user_id": "3464",
    "data": {
      "clientOrderID": "LIMIT-e441b494-730d-11f1-8a2a-9afca993d5d3",
      "feeAmount": "0.003",
      "feeCurrency": "USDT",
      "isMaker": false,
      "price": "172000",
      "quantity": "2",
      "side": "BUY",
      "sum": "344000",
      "symbol": "USDTTMN"
    }
  }
]

```
