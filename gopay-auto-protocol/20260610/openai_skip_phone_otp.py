"""
email_otp_send路线 — 唯一能触发app导航的page type
"""

from reqable import *
import re
import os

SF = os.path.join(os.environ.get('TEMP', '/tmp'), 'reqable_state.txt')


def _s(v):
    try:
        with open(SF, 'w') as f:
            f.write(v)
    except:
        pass


def _l():
    try:
        with open(SF, 'r') as f:
            return f.read().strip()
    except:
        return None


def onRequest(context, request):
    return request


def onResponse(context, response):
    url = context.url

    if '/oauth/authorize' in url and 'state=' in url:
        m = re.search(r'state=([^&\s]+)', url)
        if m:
            _s(m.group(1))

    # ---- email-otp/send: 拦截错误 → 302到email-verification页 ----
    if '/api/accounts/email-otp/send' in url:
        if response.code >= 300:
            response.code = 302
            response.headers.add('Location', 'https://auth.openai.com/email-verification')
        return response

    # ---- email-otp/validate: 拦截→直接跳到consent ----
    if '/api/accounts/email-otp/validate' in url:
        if response.code >= 400:
            response.code = 200
            response.body.text('{"continue_url":"https://auth.openai.com/sign-in-with-chatgpt/codex/consent","method":"GET","page":{"type":"external_url","backstack_behavior":"default","payload":{"url":"https://auth.openai.com/sign-in-with-chatgpt/codex/consent"}},"oai-client-auth-session":{"email":"FrankieBoyd794876@outlook.com","name":"FrankieBoyd","workspaces":[{"id":"ab5ec664-7f7f-4c6d-b09f-3f69083a3185","name":null,"kind":"personal"}]}}')
        return response

    # ---- consent.data 400→200 ----
    if 'consent.data' in url and 'SIGN_IN_WITH_CHATGPT_CODEX_CONSENT' in url:
        if response.code >= 400:
            response.code = 200
            response.body.text('[{"_1":2},"SIGN_IN_WITH_CHATGPT_CODEX_CONSENT",{"_3":-5},"data"]')
        return response

    # ---- workspace/select: true state callback ----
    if '/api/accounts/workspace/select' in url:
        if response.code >= 400:
            state = _l() or 'unknown'
            response.code = 200
            response.body.text('{"continue_url":"http://localhost:1455/auth/callback?code=bypass&scope=openid+profile+email+offline_access+api.connectors.read+api.connectors.invoke&state=' + state + '","method":"GET","page":{"type":"external_url","backstack_behavior":"default","payload":{"url":"http://localhost:1455/auth/callback?code=bypass&scope=openid+profile+email+offline_access+api.connectors.read+api.connectors.invoke&state=' + state + '"}}}')
        return response

    if not response.body.isText:
        return response

    body = response.body.payload

    # session/select: add_phone → email_otp_verification (直接进邮箱验证页)
    if '/api/accounts/session/select' in url:
        body = body.replace('"type": "add_phone"', '"type": "email_otp_verification"')
        body = body.replace('"type":"add_phone"', '"type":"email_otp_verification"')
        body = body.replace('"type": "phone_otp_select_channel"', '"type": "email_otp_verification"')
        body = body.replace('"type":"phone_otp_select_channel"', '"type":"email_otp_verification"')
        body = body.replace('"type": "phone_otp_send"', '"type": "email_otp_verification"')
        body = body.replace('"type":"phone_otp_send"', '"type":"email_otp_verification"')
        body = re.sub(r'"continue_url"\s*:\s*"[^"]*"',
                      '"continue_url":"https://auth.openai.com/email-verification"', body)
        body = body.replace('"method": "POST"', '"method": "GET"')
        body = body.replace('"method":"POST"', '"method":"GET"')
        body = re.sub(r',\s*"multi_channel_allowed"\s*:\s*(?:true|false)', '', body)
        body = re.sub(r',\s*"phone_number"\s*:\s*"[^"]*"', '', body)
        body = re.sub(r',\s*"phone_verification_channel"\s*:\s*"[^"]*"', '', body)

    response.body.text(body)
    return response
