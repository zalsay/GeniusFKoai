# GoPay Protocol Flow & API Specification

This document details the chronological sequence, request/response formats, headers, and cryptographic requirements of the GoPay App and Midtrans GoPay payment integration flows, compiled from actual traffic logs and captured protocol dumps.

---

## 🗺️ Chronological Architecture Flow

The GoPay integration consists of three main stages:
1. **Login & Registration Flow**: Phone submission, OTP verification via WhatsApp/SMS, and token exchange.
2. **Post-Token App Initialization**: Parallel batch sync of user states, push configurations, payment methods, and privacy consents.
3. **Midtrans SNAP GoPay Payment (Linking & Settlement)**: External merchant linking, charge, PIN-challenge processing, and validation.

```mermaid
sequenceDiagram
    autonumber
    actor User as App/User
    participant AUTH as accounts.goto-products.com
    participant API as api.gojekapi.com
    participant CUST as customer.gopayapi.com
    participant MID as app.midtrans.com
    participant GWA as gwa.gopayapi.com

    %% Stage 1: Auth & Login
    Note over User, AUTH: Stage 1: Registration / Login
    User->>CUST: POST /v1/support/customer/initiate (Device Fingerprint)
    CUST-->>User: HTTP 201 Created (Init Success)
    User->>AUTH: POST /goto-auth/login/methods (Get Login Methods)
    AUTH-->>User: HTTP 200 OK (Allowed Methods)
    User->>AUTH: POST /cvs/v1/methods (Determine Flow Context)
    AUTH-->>User: HTTP 200 OK (Flow Methods & Verification ID)
    User->>AUTH: POST /cvs/v1/initiate (Send OTP)
    AUTH-->>User: HTTP 200 OK (OTP Sent + Token)
    User->>AUTH: POST /cvs/v1/verify (Verify OTP)
    AUTH-->>User: HTTP 200 OK (returns verification_token)
    Note over User, API: If New User: POST /v7/customers/signup
    User->>AUTH: POST /goto-auth/token (Exchange for Access Token)
    AUTH-->>User: HTTP 200 OK (Access Token + Refresh Token)

    %% Stage 2: Post-Token Batch Init
    Note over User, API: Stage 2: Post-Token Batch Init (Parallelized)
    par Parallel Batch Requests
        User->>API: GET /gojek/v2/customer
        API-->>User: QR ID & Pin Setup Flag
    and
        User->>CUST: GET /v1/users/profile
        CUST-->>User: User Profile Data
    and
        User->>API: GET /v1/payment-options/profiles
        API-->>User: Active Profiles (GOPAY_WALLET, etc.)
    and
        User->>API: POST /api/v2/consents/accept (Accept Terms)
        API-->>User: HTTP 200 OK + MQTT Broker Token
    and
        User->>API: GET /v1/payment-options/balances
        API-->>User: Wallet/Coin Balance
    and
        User->>API: GET /v2/users/kyc/status
        API-->>User: KYC Status
    and
        User->>CUST: POST /api/v1/users/pins/allowed (Verify PIN status)
        CUST-->>User: Status OK
    and
        User->>API: GET /v1/users/security-meter
        API-->>User: Security Score Details
    and
        User->>AUTH: POST /paylater/auth/partner/v1/auth/gofin-token
        AUTH-->>User: Partner Token ID
    and
        User->>API: PUT /v1/devices/push_token
        API-->>User: FCM Register Confirm
    end

    %% Stage 3: Midtrans SNAP Payment Flow
    Note over User, MID: Stage 3: Midtrans SNAP GoPay Payment Flow
    User->>MID: POST /snap/v3/accounts/{snap}/linking (Merchant Link)
    MID-->>User: Link URL + Activation Reference
    User->>GWA: POST /v1/linking/validate-reference
    GWA-->>User: Reference Validated
    User->>GWA: POST /v1/linking/user-consent
    GWA-->>User: Consent Granted
    User->>GWA: POST /v1/linking/resend-otp (Force SMS)
    GWA-->>User: OTP Sent
    User->>GWA: POST /v1/linking/validate-otp (Submit OTP)
    GWA-->>User: Challenge ID
    User->>CUST: POST /api/v1/users/pin/tokens/nb (Verify PIN - MGUPA)
    CUST-->>User: JWT pin_token
    User->>GWA: POST /v1/linking/validate-pin (Submit pin_token)
    GWA-->>User: Linking Complete (HTTP 200)
    User->>MID: GET /snap/v3/accounts/{snap}/gopay (Poll Status)
    MID-->>User: Account ENABLED
    User->>MID: POST /snap/v2/transactions/{snap}/charge (Deduct request)
    MID-->>User: Transaction Status Capture/Challenge Ref
    User->>GWA: GET /v1/payment/validate (Validate Payment Challenge)
    GWA-->>User: Payment Challenge ID
    User->>GWA: POST /v1/payment/confirm (Confirm Request)
    GWA-->>User: OK
    User->>CUST: POST /api/v1/users/pin/tokens/nb (Verify PIN - GWC)
    CUST-->>User: JWT pay_pin_token
    User->>GWA: POST /v1/payment/process (Final Process with pin_token)
    GWA-->>User: Payment Processed OK
    User->>MID: GET /snap/v1/transactions/{snap}/status (Final Status Check)
    MID-->>User: Transaction Settle/Capture Status
```

---

## 🔒 Security & Cryptographic Headers

GoPay requests enforce several cryptographic signatures on the headers to prevent tampering and replay attacks.

### 1. `X-E1` (App Signature)
The signature format in the GoPay App leverages `HMAC-SHA256` built over device indicators and request attributes.

Runtime verification on `2026-06-02` against GoPay v5.60.1 on `192.168.2.232` confirmed:

- **Frida target**: process name `GoPay`, package `com.gojek.gopay`.
- **Native module**: `libbatteryOpt.so`, size `602112`.
- **Exported bridge**: `getAppCodec`.
- **Signing HMAC hook**: `libbatteryOpt.so + 0x76150`.
- **Nonce-chain HMAC hook**: `libbatteryOpt.so + 0x82774`.
- **Signer Key**: `4&G6DbV&j8QZs~{)(Ila_w_|v@aqJq]E-;*(J9PanZ8sm01kTi{X<iG``]d7P&L`.
- **Signature Assembly**: `hmac_sha256_hex(message):nonce_hex:D:timestamp_ms`.
- **Key-origin status**: final HMAC key is captured at runtime, but the seed-to-key transform is not fully reimplemented yet.

Observed enhanced message layout:

```text
GOPAY;
{x-phonemodel}:{auth_token};
{x-uniqueid}:{d1};
{md5(body)}:{host_path};
{method}:{timestamp_ms};
{x-deviceos}:{x-appversion};
{x-m1}:{x-appid};
{nonce_hex}:{x-phonemake};
{x-device_os_family}
```

The app can also emit a semicolon-delimited variant where the same fields are rotated:

```text
{nonce_hex};
{md5(body)}:{x-deviceos};
{host_path}:{x-device_os_family};
{x-appid}:{x-phonemake};
{auth_token}:{timestamp_ms};
{x-phonemodel}:{x-uniqueid};
{x-appversion}:GOPAY;
{method}:{x-m1}
```

Both variants are signed with the same `HMAC_SHA256(key_str, msg_str)` rule. Preserve the captured `msg_str` byte-for-byte; do not rebuild it by loosely sorting fields.

Capture command:

```powershell
python -u .\capture_new_algorithm.py --seconds 20 --refreshes 0 --tab-rounds 2
```

Outputs are written to `captures/new_algorithm_*.jsonl`. These files contain live tokens and must stay local.

#### X-E1 Key-Origin Trace Progress

Current transparent boundary as of `2026-06-02`:

- `libbatteryOpt.so + 0x79f54` initializes a global key/config object with three string slots:
  - enhanced seed, stored as a base64-like 84-byte string.
  - fallback support key, 32 bytes.
  - reserved empty string.
- Active probe evidence is saved in `captures/key_init_probe_20260602_1138.json`.
- The enhanced seed base64 decodes to 63 printable bytes, but that decoded value is not the final signing key.
- The final signing key is passed to `libbatteryOpt.so + 0x76150` as a 63-byte HMAC key from anonymous `rw-` memory, not from static `.so` rodata.
- Static and runtime evidence point to `libbatteryOpt.so + 0x703d4` as the derive/pre-sign function. Its direct HMAC call site is around `libbatteryOpt.so + 0x718ec`.
- Real signing backtrace observed in `captures/key_origin_20260602_112240.jsonl`:

```text
libbatteryOpt.so+0x718ec
libbatteryOpt.so+0x79690
libbatteryOpt.so+0x77b3c
libapp.so+0xae15e0
...
```

The next verification target is to passively capture `0x703d4_enter` / `0x703d4_leave` on a real request and compare:

```text
enhanced_seed/base64_decoded_seed -> derived 63-byte HMAC key
```

Do not active-call `0x703d4` with dummy arguments; it depends on real app context and can abort the native process.

#### Device Hygiene During Trace

GoPay may crash or show environment-abnormal behavior when obvious instrumentation files remain on the device. Keep the device state minimal:

- Allowed Frida service name for this workflow: `/data/local/tmp/.fsrv`.
- Remove or avoid obvious names: `frida-server*`, `frida-inject`, `frida.log`, `zygiskfrida*`, `re.zyg.fri`, `gopay_late_attach.js`, `gopay_libc_hook.js`, `flutter_capture.js`.
- After cleanup on `2026-06-02`, GoPay stayed foreground on `com.gojek.gopay/.MainActivity` and rendered the normal home page.

### 2. `X-M1` (Device Fingerprint Metadata)
Passed in the format:
`3:{timestamp_ms}-{random_int_64},4:{mac_address_hash},5:{chipset_info},6:<wifi_ssid>,7:<wifi_bssid>,8:1080x2400,10:0,11:{widevine_id_base64},15:{fingerprint_md5},16:{device_uuid}`

### 3. `X-Snap-Signature` (Midtrans Signature)
Applied on Midtrans Snap requests:
- **Signing Key**: `1feab063-bf3f-4025-90bf-3be6fa4f4cc2`
- **Payload String**: `{absolute_path}:{timestamp}:{compact_minified_json_body}`
- **HMAC Calculation**: `sig_hex = HMAC-SHA256(SigningKey, PayloadString)`
- **Mangling algorithm**: Swaps every 4 character boundaries: `[c0, c1, c2, c3] -> [c2, c3, c0, c1]`

### 4. PIN Tokenization (`tokenizePin` / `tokenize_pin_aes_ecb`)
- **Algorithm**: `AES-128/ECB/PKCS7Padding` (Note: standard PKCS5Padding defaults to PKCS7 on 16-byte blocks).
- **Key Material**: Injected `pin_token` repeated up to 16 bytes.
- **Output**: Base64 encoded ciphertext.

---

## 📞 Stage 1: Auth & Login Flow Details

### 1. Pre-login Fingerprint
- **Endpoint**: `POST https://customer.gopayapi.com/v1/support/customer/initiate`
- **Description**: Registers the device verification session.
- **Request Body**:
  ```json
  {
    "support_lang": "a4e17125da...",
    "support_code": "9d20bea5f6..."
  }
  ```
- **Response**: `HTTP 201 Created`

### 2. Check Login Methods
- **Endpoint**: `POST https://accounts.goto-products.com/goto-auth/login/methods`
- **Request Body**:
  ```json
  {
    "phone_number": "83168621957",
    "country_code": "+62",
    "email": "",
    "device_verification_token_id": "",
    "client_id": "gopay:consumer:app",
    "client_secret": "raOUumeMRBNifqvZRFjvsgTnjAlaA9"
  }
  ```
- **Response**:
  ```json
  {
    "data": {
      "allowed_methods": ["otp_wa", "otp_sms", "goto_pin"]
    },
    "success": true
  }
  ```

### 3. Determine Verification Flow
- **Endpoint**: `POST https://accounts.goto-products.com/cvs/v1/methods`
- **Request Body**:
  ```json
  {
    "country_code": "+62",
    "email_address": null,
    "client_id": "gopay:consumer:app",
    "phone_number": "83168621957",
    "client_secret": "raOUumeMRBNifqvZRFjvsgTnjAlaA9",
    "flow": "login_1fa",
    "device_verification_token_id": ""
  }
  ```
- **Response**:
  ```json
  {
    "data": {
      "default_method": "otp_wa",
      "methods": ["otp_wa", "otp_sms"],
      "verification_id": "14588284-087f-4082-a651-dbc45e826fe1"
    },
    "success": true
  }
  ```

### 4. Send Verification Code (OTP)
- **Endpoint**: `POST https://accounts.goto-products.com/cvs/v1//initiate`
- **Request Body**:
  ```json
  {
    "verification_id": "14588284-087f-4082-a651-dbc45e826fe1",
    "flow": "login_1fa",
    "verification_method": "otp_wa",
    "country_code": "+62",
    "email_address": null,
    "client_id": "gopay:consumer:app",
    "phone_number": "83168621957",
    "client_secret": "raOUumeMRBNifqvZRFjvsgTnjAlaA9",
    "is_multiple_method": null,
    "device_verification_token_id": null
  }
  ```
- **Response**:
  ```json
  {
    "data": {
      "otp_token": "468edc53-0537-4ecc-87f5-f605a75eb788",
      "otp_length": 4,
      "retry_timer_in_seconds": [30, 60, 90],
      "metadata": {
        "phone": "+62*******7177",
        "whatsapp_deeplink": "https://chat.whatsapp.com"
      }
    },
    "success": true
  }
  ```

### 5. Verify OTP
- **Endpoint**: `POST https://accounts.goto-products.com/cvs/v1/verify`
- **Request Body**:
  ```json
  {
    "client_id": "gopay:consumer:app",
    "client_secret": "raOUumeMRBNifqvZRFjvsgTnjAlaA9",
    "flow": "login_1fa",
    "verification_method": "otp_wa",
    "verification_id": "14588284-087f-4082-a651-dbc45e826fe1",
    "data": {
      "otp": "3958",
      "otp_token": "468edc53-0537-4ecc-87f5-f605a75eb788"
    }
  }
  ```
- **Response**:
  ```json
  {
    "data": {
      "verification_token": "eyJhbGciOiJkaXIi..."
    },
    "success": true
  }
  ```

### 6. Signup (For Unregistered Users Only)
- **Endpoint**: `POST https://api.gojekapi.com/v7//customers/signup`
- **Headers**:
  - `Verification-Token`: `Bearer <verification_token>`
  - `Authorization`: `Basic YmI2NDg0MTMtYjYzNy00NDNhLThlYmYtMTc2Y2Y5YjVkYzMy`
- **Request Body**:
  ```json
  {
    "client_name": "gopay:consumer:app",
    "client_secret": "raOUumeMRBNifqvZRFjvsgTnjAlaA9",
    "data": {
      "name": "Indra Wijaya",
      "phone": "6283168621957",
      "email": "gojektest2026@gmail.com",
      "signed_up_country": "62",
      "onboarding_partner": "gopay_consumer_app"
    }
  }
  ```
- **Response**: `HTTP 201 Created`

### 7. Token Exchange
- **Endpoint**: `POST https://accounts.goto-products.com/goto-auth/token`
- **Request Body**:
  ```json
  {
    "grant_type": "cvs",
    "account_id": "01-70c86603ec214541b8e564cf07b7b15b-24",
    "token": "eyJhbGciOiJkaXIi...",
    "client_id": "gopay:consumer:app",
    "client_secret": "raOUumeMRBNifqvZRFjvsgTnjAlaA9"
  }
  ```
- **Response**:
  ```json
  {
    "access_token": "eyJhbGciOiJkaXIiLCJjdHkiOiJKV1QiLCJlbmMi...",
    "refresh_token": "eyJhbGciOiJkaXIiLCJjdHkiOiJKV1Qi...",
    "expires_in": 15552000,
    "token_type": "Bearer"
  }
  ```

---

## 🔄 Stage 2: Post-Token Initialization Batch

This batch is fired simultaneously upon successful login using parallelized network workers.

### 1. Fetch Customer Detail
- **Endpoint**: `GET https://api.gojekapi.com/gojek/v2/customer`
- **Response**:
  ```json
  {
    "data": {
      "qr_id": "061ca365-65b2-45ee-970a-14e97a2da0cb",
      "blocked": false,
      "is_pin_setup": true
    },
    "success": true
  }
  ```

### 2. Fetch User Profile
- **Endpoint**: `GET https://customer.gopayapi.com/v1/users/profile`
- **Response**: Returns full details of phone, KYC type, and user attributes.

### 3. Fetch Payment Options Profiles
- **Endpoint**: `GET https://api.gojekapi.com/v1/payment-options/profiles`
- **Response**:
  ```json
  {
    "data": [
      {
        "type": "GOPAY_WALLET",
        "additional_details": {
          "kyc_name": "",
          "kyc_status": "SET_NOW",
          "group_id": "CGOJEK"
        }
      }
    ],
    "success": true
  }
  ```

### 4. Accept Privacy Consents
- **Endpoint**: `POST https://api.gojekapi.com/api/v2/consents/accept`
- **Request Body**:
  ```json
  {
    "consents": [
      { "consent_name": "gopay_app_tnc", "user_type": "CUSTOMER", "flow": "signUp" },
      { "consent_name": "gopay_app_privacy_note", "user_type": "CUSTOMER", "flow": "signUp" },
      { "consent_name": "gojek_app_tnc", "user_type": "CUSTOMER", "flow": "signUp" },
      { "consent_name": "gojek_app_privacy_note", "user_type": "CUSTOMER", "flow": "signUp" }
    ]
  }
  ```
- **Response**: Returns the background websocket sync auth token (Courier/MQTT config):
  ```json
  {
    "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    "expiry_in_sec": 21600,
    "broker": {
      "host": "tcc-mqtt-customer-prd.gojekapi.com",
      "port": 443
    }
  }
  ```

### 5. Fetch Payment Options Balances
- **Endpoint**: `GET https://api.gojekapi.com/v1/payment-options/balances`
- **Response**:
  ```json
  {
    "data": [
      {
        "balance": { "value": 0, "currency": "IDR", "display_value": "0" },
        "type": "GOPAY_WALLET",
        "token": "eyJ0eXBlIjoiR09QQVlfV...",
        "country_code": "ID"
      }
    ],
    "success": true
  }
  ```

### 6. Fetch KYC Status
- **Endpoint**: `GET https://api.gojekapi.com/v2/users/kyc/status`
- **Response**:
  ```json
  {
    "data": {
      "status": "NOT_SUBMITTED"
    },
    "success": true
  }
  ```

### 7. PIN Allowed Status
- **Endpoint**: `POST https://customer.gopayapi.com/api/v1/users/pins/allowed`
- **Request Body**:
  ```json
  {
    "pin": "303384"
  }
  ```
- **Response**:
  ```json
  {
    "success": true,
    "errors": []
  }
  ```

### 8. Fetch GoFin Token (PayLater Auth)
- **Endpoint**: `POST https://customer.gopayapi.com/paylater/auth/partner/v1/auth/gofin-token`
- **Request Body**: Empty
- **Response**:
  ```json
  {
    "data": {
      "id": "3453abcb-1bdc-4fea-b3f3-eb97efe5d0b9"
    },
    "success": true,
    "errors": []
  }
  ```

### 9. Register Push Token
- **Endpoint**: `PUT https://api.gojekapi.com/v1/devices/push_token`
- **Request Body**:
  ```json
  {
    "push_token_type": "FCM",
    "push_token": "fTwJyb5-TvGL4j2zb0KooH:APA91bFOpcy5DH-XlOd4mK0YEKHNrvLRD5et3f7L9AfXJW4g_Z0D16gS_LngQJZqobCs3WUcQSvS1A008DvRSTOHKDfLWTLo4mh4sDw4VZYLlEFYgObxKJE"
  }
  ```
- **Response**: Returns security metrics for verification.

### 10. Report Push Notification Callback
- **Endpoint**: `POST https://api.gojekapi.com/v2/push-notification/callback`
- **Request Body**:
  ```json
  {
    "push_notification_details": [
      { "id": "", "app_state": "Background", "notification_source": "fcm", "delivered_time": "2026-05-31T03:00:03.326Z" },
      { "id": "efe62261-7f59-4036-8575-10e4302b710d", "app_state": "Foreground", "notification_source": "fcm", "delivered_time": "2026-05-31T08:21:16.201Z" }
    ]
  }
  ```
- **Response**: `HTTP 204 No Content`

---

## 💳 Stage 3: Midtrans SNAP GoPay Payment Flow

### Phase A: Account Linking

#### 1. Initiate Linking
- **Endpoint**: `POST https://app.midtrans.com/snap/v3/accounts/{snap}/linking`
- **Headers**:
  - `Authorization`: `Basic <base64(client_key:)>`
- **Request Body**:
  ```json
  {
    "type": "gopay",
    "country_code": "62",
    "phone_number": "83168621957"
  }
  ```
- **Response**:
  ```json
  {
    "activation_link_url": "https://gwa.gopayapi.com/v1/linking?reference=8b7b10e0-5be6-11f1-8065-af58d8b69530"
  }
  ```

#### 2. Validate Reference
- **Endpoint**: `POST https://gwa.gopayapi.com/v1/linking/validate-reference`
- **Request Body**:
  ```json
  {
    "reference_id": "8b7b10e0-5be6-11f1-8065-af58d8b69530"
  }
  ```
- **Response**: `HTTP 200 OK`

#### 3. User Consent
- **Endpoint**: `POST https://gwa.gopayapi.com/v1/linking/user-consent`
- **Request Body**:
  ```json
  {
    "reference_id": "8b7b10e0-5be6-11f1-8065-af58d8b69530"
  }
  ```
- **Response**: `HTTP 200 OK`

#### 4. Resend OTP
- **Endpoint**: `POST https://gwa.gopayapi.com/v1/linking/resend-otp`
- **Request Body**:
  ```json
  {
    "reference_id": "8b7b10e0-5be6-11f1-8065-af58d8b69530",
    "otp_channel": "SMS"
  }
  ```
- **Response**: `HTTP 200 OK`

#### 5. Validate OTP
- **Endpoint**: `POST https://gwa.gopayapi.com/v1/linking/validate-otp`
- **Request Body**:
  ```json
  {
    "reference_id": "8b7b10e0-5be6-11f1-8065-af58d8b69530",
    "otp": "4569"
  }
  ```
- **Response**: Returns a redirects link containing `challengeId`.
  ```json
  {
    "redirect_url": "https://pin-web-client.gopayapi.com/?challengeId=ea1155bf-a3ed-4871-9b8f-49bac33377e3"
  }
  ```

#### 6. PIN Tokenization (Linking Stage - Outer MGUPA)
- **Endpoint**: `POST https://customer.gopayapi.com/api/v1/users/pin/tokens/nb`
- **Request Body**:
  ```json
  {
    "challenge_id": "ea1155bf-a3ed-4871-9b8f-49bac33377e3",
    "client_id": "51b5f09a-3813-11ee-be56-0242ac120002-MGUPA",
    "pin": "303384"
  }
  ```
- **Response**:
  ```json
  {
    "data": {
      "token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiJ9..."
    }
  }
  ```

#### 7. Submit Linked PIN Token
- **Endpoint**: `POST https://gwa.gopayapi.com/v1/linking/validate-pin`
- **Request Body**:
  ```json
  {
    "reference_id": "8b7b10e0-5be6-11f1-8065-af58d8b69530",
    "token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiJ9..."
  }
  ```
- **Response**: `HTTP 200 OK`

### Phase B: Charge

#### 8. Poll Account Status
- **Endpoint**: `GET https://app.midtrans.com/snap/v3/accounts/{snap}/gopay`
- **Response**: Returns status `ENABLED` when linked successfully.

#### 9. Charge Transaction
- **Endpoint**: `POST https://app.midtrans.com/snap/v2/transactions/{snap}/charge`
- **Request Body**:
  ```json
  {
    "payment_type": "gopay",
    "tokenization": "true",
    "promo_details": null
  }
  ```
- **Response**: Returns challenge payload if biometric/PIN verification is needed:
  ```json
  {
    "status_code": "201",
    "transaction_status": "pending",
    "gopay_verification_link_url": "https://gwa.gopayapi.com/v1/payment?reference=943dd998ca5c758eec49f..."
  }
  ```

### Phase C: Payment Challenge

#### 10. Payment Validate
- **Endpoint**: `GET https://gwa.gopayapi.com/v1/payment/validate?reference_id={challenge_ref}`
- **Response**:
  ```json
  {
    "challenge_id": "d236bf89-2048-428c-8de5-b39613fb68ac"
  }
  ```

#### 11. Confirm Payment
- **Endpoint**: `POST https://gwa.gopayapi.com/v1/payment/confirm?reference_id={challenge_ref}`
- **Request Body**:
  ```json
  {
    "payment_instructions": []
  }
  ```
- **Response**: `HTTP 200 OK`

#### 12. PIN Tokenization (Payment Stage - GWC)
- **Endpoint**: `POST https://customer.gopayapi.com/api/v1/users/pin/tokens/nb`
- **Request Body**:
  ```json
  {
    "challenge_id": "d236bf89-2048-428c-8de5-b39613fb68ac",
    "client_id": "47180a8e-f56e-11ed-a05b-0242ac120003-GWC",
    "pin": "303384"
  }
  ```
- **Response**: Returns `pay_pin_token`.

#### 13. Process Payment
- **Endpoint**: `POST https://gwa.gopayapi.com/v1/payment/process?reference_id={challenge_ref}`
- **Request Body**:
  ```json
  {
    "challenge": {
      "type": "GOPAY_PIN_CHALLENGE",
      "value": {
        "pin_token": "pay_pin_token"
      }
    }
  }
  ```
- **Response**: `HTTP 200 OK`

### Phase D: Verification

#### 14. Query SNAP Status
- **Endpoint**: `GET https://app.midtrans.com/snap/v1/transactions/{snap}/status`
- **Response**:
  ```json
  {
    "transaction_status": "settlement"
  }
  ```
