"""代理连通性测试脚本 — 测试 OpenAI HTTP Client 通过代理访问各目标。

用法:
    python tools/test_proxy_connection.py <proxy_url>

示例:
    python tools/test_proxy_connection.py http://user:pass@host:port
    python tools/test_proxy_connection.py http://sisu:Cqlzy1277@154.201.75.164:1082
"""

import subprocess
import sys
from pathlib import Path

# 确保项目根目录在 sys.path 中
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

DEFAULT_PROXY = "http://sisu:Cqlzy1277@154.201.75.164:1082"

TARGETS = [
    ("Cloudflare trace (IP 位置)", "https://cloudflare.com/cdn-cgi/trace"),
    ("httpbin.org/ip (出口IP)", "https://httpbin.org/ip"),
    ("chatgpt.com          ", "https://chatgpt.com"),
    ("api.openai.com       ", "https://api.openai.com"),
    ("auth0.openai.com     ", "https://auth0.openai.com"),
    ("ab.chatgpt.com       ", "https://ab.chatgpt.com"),
]


def test_with_http_client(proxy: str) -> dict:
    """通过 OpenAIHTTPClient 测试。"""
    from platforms.chatgpt.http_client import OpenAIHTTPClient

    client = OpenAIHTTPClient(proxy_url=proxy)
    results = {}

    # 1. IP 位置检测（内置方法）
    ok, loc = client.check_ip_location()
    results["Cloudflare trace (IP 位置)"] = {"ok": ok, "detail": f"loc={loc}"}

    # 2-N. HTTP 连通性
    for name, url in TARGETS[1:]:
        try:
            resp = client.get(url, timeout=15)
            results[name] = {"ok": True, "detail": f"HTTP {resp.status_code}"}
        except Exception as e:
            msg = str(e)
            # 精简错误信息
            if "Connection reset by peer" in msg:
                short = "Connection reset by peer"
            elif "timed out" in msg.lower() or "timeout" in msg.lower():
                short = "Timeout"
            else:
                short = msg[:120]
            results[name] = {"ok": False, "detail": short}

    # 额外：取 httpbin 出口 IP
    try:
        resp = client.get("https://httpbin.org/ip", timeout=15)
        data = resp.json()
        results["httpbin.org/ip (出口IP)"]["detail"] = data.get("origin", "?")
    except Exception:
        pass

    return results


def test_with_curl(proxy: str) -> dict:
    """通过 curl 直连测试，作为对照组。"""
    results = {}
    for name, url in TARGETS:
        r = subprocess.run(
            [
                "curl", "-x", proxy,
                "-s", "-o", "/dev/null", "-w", "%{http_code}",
                "--connect-timeout", "8", "--max-time", "12",
                url,
            ],
            capture_output=True, text=True, timeout=15,
        )
        code = r.stdout.strip()
        results[f"curl → {name}"] = {
            "ok": code.startswith("2") or code.startswith("3"),
            "detail": f"HTTP {code}" if code else "无响应",
        }
    return results


def main():
    proxy = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_PROXY
    print(f"代理: {proxy}")
    print(f"{'=' * 60}")

    # === OpenAIHTTPClient 测试 ===
    print("\n[OpenAIHTTPClient]")
    print("-" * 40)
    results = test_with_http_client(proxy)
    for name, r in results.items():
        status = "✅" if r["ok"] else "❌"
        print(f"  {status}  {name.strip():<30s} {r['detail']}")

    # === curl 对照组 ===
    print("\n[curl 对照组]")
    print("-" * 40)
    curl_results = test_with_curl(proxy)
    for name, r in curl_results.items():
        status = "✅" if r["ok"] else "❌"
        print(f"  {status}  {name.strip():<35s} {r['detail']}")

    # === 汇总 ===
    http_ok = sum(1 for r in results.values() if r["ok"])
    http_total = len(results)
    curl_ok = sum(1 for r in curl_results.values() if r["ok"])
    curl_total = len(curl_results)

    print(f"\n{'=' * 60}")
    print(f"汇总: HTTP Client {http_ok}/{http_total}   curl {curl_ok}/{curl_total}")

    openai_fail = [n for n, r in results.items() if not r["ok"] and "openai" in n.lower() or "chatgpt" in n.lower()]
    if openai_fail:
        print("⚠️  OpenAI 域名全部不通，该代理可能不适用于 OpenAI 业务。")


if __name__ == "__main__":
    main()
