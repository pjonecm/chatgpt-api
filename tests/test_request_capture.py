from chatgpt_api.providers.chatgpt.auth import ChatGPTAuthConfig
from chatgpt_api.providers.chatgpt.request_capture import CapturedRequest


def test_parse_copied_request_summary():
    text = """
Summary
URL: https://chatgpt.com/backend-api/f/conversation
Status: 200

Request
Accept: text/event-stream
Authorization: Bearer fake-token
Cookie: oai-did=device-1; __Secure-next-auth.session-token.0=session-1
OpenAI-Sentinel-Chat-Requirements-Token: req-token
OpenAI-Sentinel-Proof-Token: proof-token
OpenAI-Sentinel-Turnstile-Token: turnstile-token
x-conduit-token: conduit-token
OAI-Device-Id: device-1

Request Data
MIME Type: application/json
Request Data: {"action":"next","model":"gpt-5.5"}
"""

    capture = CapturedRequest.from_text(text)

    assert capture.url == "https://chatgpt.com/backend-api/f/conversation"
    assert capture.status == 200
    assert capture.headers["authorization"] == "Bearer fake-token"
    assert capture.cookies["oai-did"] == "device-1"
    assert capture.request_json == {"action": "next", "model": "gpt-5.5"}
    assert capture.redacted_headers()["authorization"] == "<redacted>"


def test_auth_config_from_copied_request():
    capture = CapturedRequest.from_text(
        """
URL: https://chatgpt.com/backend-api/f/conversation
Authorization: Bearer fake-token
Cookie: oai-did=device-1
OpenAI-Sentinel-Proof-Token: proof-token
OpenAI-Sentinel-Turnstile-Token: turnstile-token
"""
    )

    config = ChatGPTAuthConfig.from_captured_request(capture)

    assert config.access_token == "fake-token"
    assert config.proof_token == "proof-token"
    assert config.turnstile_token == "turnstile-token"
    assert config.cookies["oai-did"] == "device-1"


def test_parser_ignores_response_headers():
    capture = CapturedRequest.from_text(
        """
Request
Content-Type: application/json
Authorization: Bearer fake-token

Response
Content-Type: text/event-stream; charset=utf-8
Set-Cookie: ignored=yes
"""
    )

    assert capture.headers["content-type"] == "application/json"
    assert "set-cookie" not in capture.headers


def test_cookie_parser_handles_chrome_json_cookie_and_response_updates():
    capture = CapturedRequest.from_text(
        """
Request URL
https://chatgpt.com/backend-api/f/conversation
content-type
application/json
cookie
oai-did=device-1; g_state={"i_l":0,"i_ll":1782322235556}; __Secure-next-auth.session-token.0=session-0; cf_clearance=clearance-1
set-cookie
_uasid="uasid-1"; expires=Wed, 24 Jun 2026 20:33:51 GMT; HttpOnly; Path=/; SameSite=none; Secure
set-cookie
_umsid="umsid-1"; expires=Wed, 24 Jun 2026 20:33:51 GMT; HttpOnly; Path=/; SameSite=none; Secure
x-oai-is-update
ois1.updated
{"action":"next","messages":[],"model":"auto","parent_message_id":"client-created-root"}
"""
    )

    assert capture.cookies["g_state"] == '{"i_l":0,"i_ll":1782322235556}'
    assert capture.cookies["__Secure-next-auth.session-token.0"] == "session-0"
    assert capture.cookies["cf_clearance"] == "clearance-1"
    assert capture.cookies["_uasid"] == "uasid-1"
    assert capture.cookies["_umsid"] == "umsid-1"
    assert capture.cookies["__Secure-oai-is"] == "ois1.updated"
    assert "set-cookie" not in capture.headers
    assert "x-oai-is-update" not in capture.headers


def test_parse_chrome_devtools_request_details():
    capture = CapturedRequest.from_text(
        """
Request URL
https://chatgpt.com/backend-api/f/conversation
Request Method
POST
Status Code
200 OK
authorization
Bearer chrome-token
content-type
application/json
cookie
oai-did=device-2; __Secure-next-auth.session-token.0=session-2
openai-sentinel-proof-token
proof-token
oai-device-id
device-2
Request Payload
{"action":"next","model":"auto"}
"""
    )

    assert capture.url == "https://chatgpt.com/backend-api/f/conversation"
    assert capture.status == 200
    assert capture.headers["authorization"] == "Bearer chrome-token"
    assert capture.headers["openai-sentinel-proof-token"] == "proof-token"
    assert "https" not in capture.headers
    assert "post" not in capture.headers
    assert capture.cookies["oai-did"] == "device-2"
    assert capture.request_json == {"action": "next", "model": "auto"}


def test_parse_chrome_devtools_details_with_embedded_payload_without_marker():
    capture = CapturedRequest.from_text(
        """
Request URL
https://chatgpt.com/backend-api/f/conversation
Request Method
POST
Status Code
200 OK
authorization
Bearer chrome-token
content-type
application/json
cookie
oai-did=device-3; g_state={"i_l":0}; __Secure-next-auth.session-token.0=session-3
openai-sentinel-chat-requirements-token
req-token
openai-sentinel-proof-token
proof-token
openai-sentinel-turnstile-token
turnstile-token
x-oai-turn-trace-id
trace-1
x-openai-target-route
/backend-api/f/conversation{
  "action": "next",
  "messages": [
    {
      "author": {"role": "user"},
      "content": {"content_type": "text", "parts": ["hello"]}
    }
  ],
  "parent_message_id": "client-created-root",
  "model": "auto",
  "client_prepare_state": "success"
}
"""
    )

    assert capture.url == "https://chatgpt.com/backend-api/f/conversation"
    assert capture.status == 200
    assert capture.headers["authorization"] == "Bearer chrome-token"
    assert capture.headers["openai-sentinel-chat-requirements-token"] == "req-token"
    assert capture.cookies["oai-did"] == "device-3"
    assert capture.request_json is not None
    assert capture.request_json["action"] == "next"
    assert capture.request_json["model"] == "auto"


def test_parse_chrome_devtools_ignores_response_headers_before_request_headers():
    capture = CapturedRequest.from_text(
        """
Request URL
https://chatgpt.com/backend-api/f/conversation
Request Method
POST
Status Code
200 OK
access-control-allow-origin
https://chatgpt.com
cf-ray
a10e726a4b922721-BKK
server
cloudflare
x-build
5a883967c416-convo
:authority
chatgpt.com
:method
POST
:path
/backend-api/f/conversation
:scheme
https
accept
text/event-stream
authorization
Bearer chrome-token
content-length
951
content-type
application/json
cookie
oai-did=device-4; __Secure-next-auth.session-token.0=session-4
oai-client-build-number
7780290
openai-sentinel-chat-requirements-token
req-token
openai-sentinel-proof-token
proof-token
x-conduit-token
conduit-token
x-oai-turn-trace-id
trace-1
x-openai-target-route
/backend-api/f/conversation
{"action":"next","model":"auto","client_prepare_state":"success"}
"""
    )

    assert capture.headers["authorization"] == "Bearer chrome-token"
    assert capture.headers["openai-sentinel-chat-requirements-token"] == "req-token"
    assert capture.cookies["oai-did"] == "device-4"
    assert capture.request_json == {"action": "next", "model": "auto", "client_prepare_state": "success"}
    assert "server" not in capture.headers
    assert "cf-ray" not in capture.headers
    assert "x-build" not in capture.headers
    assert "chatgpt.com" not in capture.headers


def test_parse_copy_as_curl_bash_capture():
    capture = CapturedRequest.from_text(
        r"""curl 'https://chatgpt.com/backend-api/f/conversation' \
-X 'POST' \
-H 'Referer: https://chatgpt.com/' \
-H 'Cookie: oai-did=device-5; __Secure-next-auth.session-token.0=session-5; cf_clearance=clearance-5' \
-H 'User-Agent: Mozilla/5.0 Test Browser' \
-H 'Origin: https://chatgpt.com' \
-H 'Authorization: Bearer curl-token' \
-H 'Accept: text/event-stream' \
-H 'Content-Type: application/json' \
-H 'X-OpenAI-Target-Path: /backend-api/f/conversation' \
-H 'OAI-Session-Id: session-id-5' \
-H 'OAI-Device-Id: device-5' \
-H 'x-oai-turn-trace-id: trace-5' \
-H 'X-OpenAI-Target-Route: /backend-api/f/conversation' \
-H 'OpenAI-Sentinel-Chat-Requirements-Token: req-token' \
-H 'OpenAI-Sentinel-Turnstile-Token: turnstile-token' \
-H 'x-conduit-token: conduit-token' \
-H 'OAI-Language: en-US' \
-H 'OpenAI-Sentinel-Proof-Token: proof-token' \
--data-raw '{"action":"next","messages":[{"id":"message-5","author":{"role":"user"},"content":{"content_type":"text","parts":["hello"]}}],"parent_message_id":"client-created-root","model":"auto","client_prepare_state":"success"}'"""
    )

    assert capture.url == "https://chatgpt.com/backend-api/f/conversation"
    assert capture.headers["authorization"] == "Bearer curl-token"
    assert capture.headers["cookie"].startswith("oai-did=device-5;")
    assert capture.headers["x-conduit-token"] == "conduit-token"
    assert capture.headers["openai-sentinel-proof-token"] == "proof-token"
    assert capture.headers["oai-device-id"] == "device-5"
    assert capture.cookies["oai-did"] == "device-5"
    assert capture.cookies["__Secure-next-auth.session-token.0"] == "session-5"
    assert capture.request_json is not None
    assert capture.request_json["action"] == "next"
    assert capture.request_json["model"] == "auto"
    assert capture.request_json["messages"][0]["content"]["parts"] == ["hello"]


def test_parse_copy_as_curl_with_cookie_option_and_lowercase_headers():
    capture = CapturedRequest.from_text(
        r"""curl 'https://chatgpt.com/backend-api/f/conversation' \
  -H 'accept: text/event-stream' \
  -H 'authorization: Bearer lowercase-token' \
  -H 'content-type: application/json' \
  -b 'oai-did=device-6; __Secure-next-auth.session-token.0=session-6; cf_clearance=clearance-6' \
  -H 'oai-client-build-number: 7780290' \
  -H 'oai-device-id: device-6' \
  -H 'openai-sentinel-chat-requirements-token: req-token' \
  -H 'openai-sentinel-proof-token: proof-token' \
  -H 'openai-sentinel-turnstile-token: turnstile-token' \
  -H 'origin: https://chatgpt.com' \
  -H 'x-conduit-token: conduit-token' \
  -H 'x-openai-target-path: /backend-api/f/conversation' \
  -H 'x-openai-target-route: /backend-api/f/conversation' \
  --data-raw '{"action":"next","messages":[{"id":"message-6","author":{"role":"user"},"content":{"content_type":"text","parts":["สวัสดี"]}}],"parent_message_id":"client-created-root","model":"auto","client_prepare_state":"sent"}'"""
    )

    assert capture.url == "https://chatgpt.com/backend-api/f/conversation"
    assert capture.headers["authorization"] == "Bearer lowercase-token"
    assert capture.headers["cookie"].startswith("oai-did=device-6;")
    assert capture.headers["openai-sentinel-chat-requirements-token"] == "req-token"
    assert capture.headers["x-conduit-token"] == "conduit-token"
    assert capture.cookies["oai-did"] == "device-6"
    assert capture.cookies["__Secure-next-auth.session-token.0"] == "session-6"
    assert capture.cookies["cf_clearance"] == "clearance-6"
    assert capture.request_json is not None
    assert capture.request_json["client_prepare_state"] == "sent"
    assert capture.request_json["messages"][0]["content"]["parts"] == ["สวัสดี"]
