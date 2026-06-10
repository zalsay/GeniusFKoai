"""
GoPay Pure-Protocol Login & WhatsApp OTP Auto-Capture Console
Uses Pure Python Enhanced X-E1 Signer for adb-free signature generation.
Supports ADB auto-capture from Netease MuMu emulator WhatsApp notifications.
"""
import sys
import uuid
import json
import time
import re
import subprocess
from pathlib import Path

# Add current directory to sys.path
HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from gopay_protocol import GoPayProtocol, DeviceProfile, EnhancedPythonXESigner, pick_first

# ADB Configuration
ADB_PATH = r"C:\Program Files\Netease\MuMu\nx_main\adb.exe"
DEVICE_ID = "emulator-5556"

def run_adb_notification_dump():
    try:
        res = subprocess.run(
            [ADB_PATH, "-s", DEVICE_ID, "shell", "dumpsys", "notification"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="ignore",
            timeout=8
        )
        return res.stdout
    except Exception:
        return None

def parse_section(sec_lines):
    sec = "\n".join(sec_lines)
    id_m = re.search(r"NotificationRecord\((.*?)\)", sec)
    rec_id = id_m.group(1) if id_m else str(hash(sec))
    
    title_m = re.search(r"android\.title=String \((.*?)\)", sec)
    text_m = re.search(r"android\.text=String \((.*?)\)", sec)
    ticker_m = re.search(r"tickerText=(.*?)$", sec, re.MULTILINE)
    
    return {
        "id": rec_id,
        "title": title_m.group(1) if title_m else "",
        "text": text_m.group(1) if text_m else "",
        "ticker": ticker_m.group(1).strip() if ticker_m else ""
    }

def extract_whatsapp_records(dump):
    if not dump:
        return []
    lines = dump.splitlines()
    records = []
    current_sec = []
    in_whatsapp = False
    
    for line in lines:
        if "NotificationRecord" in line:
            if in_whatsapp:
                records.append(parse_section(current_sec))
            current_sec = [line]
            in_whatsapp = "com.whatsapp" in line
        else:
            if in_whatsapp:
                current_sec.append(line)
                
    if in_whatsapp:
        records.append(parse_section(current_sec))
    return records

def extract_notification_keys(dump):
    keys = set()
    for record in extract_whatsapp_records(dump):
        keys.add(record.get("id"))
    return keys

def auto_listen_whatsapp(timeout_sec=180):
    import xml.etree.ElementTree as ET
    import os
    
def dump_screen_texts():
    # Expand notification shade
    subprocess.run([ADB_PATH, "-s", DEVICE_ID, "shell", "cmd", "statusbar", "expand-notifications"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    time.sleep(1.5)
    
    # Dump UI hierarchy
    xml_path = HERE / "whatsapp_main.xml"
    res = subprocess.run(
        [ADB_PATH, "-s", DEVICE_ID, "shell", "uiautomator", "dump", "/sdcard/window_dump.xml"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )
    texts = []
    if "UI hierchary dumped to" in res.stdout:
        subprocess.run(
            [ADB_PATH, "-s", DEVICE_ID, "pull", "/sdcard/window_dump.xml", str(xml_path)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        if xml_path.exists():
            import xml.etree.ElementTree as ET
            import os
            try:
                root = ET.parse(str(xml_path)).getroot()
                for node in root.iter("node"):
                    t = node.get("text", "").strip()
                    d = node.get("content-desc", "").strip()
                    if t:
                        texts.append(t)
                    if d:
                        texts.append(d)
            except Exception as ex:
                print(f"[-] XML Parse Exception: {ex}")
            finally:
                try:
                    os.remove(str(xml_path))
                except Exception as ex:
                    print(f"[-] XML Remove Exception: {ex}")
        else:
            print("[-] XML file does not exist!")
    
    # Collapse notification shade
    subprocess.run([ADB_PATH, "-s", DEVICE_ID, "shell", "cmd", "statusbar", "collapse"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return list(set(texts))

def auto_listen_whatsapp(timeout_sec=180):
    print("\n" + "="*60)
    print(f"[*] [ADB Auto-Listen] Monitoring WhatsApp notifications on {DEVICE_ID} via UI dump...")
    print("="*60)
    
    start_time = time.time()
    while time.time() - start_time < timeout_sec:
        time.sleep(3)
        print(f"[*] Checking for new WhatsApp notifications ({int(time.time() - start_time)}s)...")
        current_texts = dump_screen_texts()
        
        for text in current_texts:
            # Look for EXACTLY 4 digit OTPs since Gojek login OTPs are 4 digits. 
            # This avoids falsely matching WhatsApp's own 6-digit login codes.
            otp_m = re.search(r"\b\d{4}\b", text)
            if otp_m:
                code = otp_m.group(0)
                
                # Check context keywords (GoPay, recovery, verification, WhatsApp)
                keywords = ["gopay", "kode", "pemulihan", "kata sandi", "whatsapp", "verification", "otp", "password"]
                has_keyword = any(kw in text.lower() for kw in keywords)
                
                # If GoPay or WhatsApp related, or contains actions like "复制密码"
                is_related = has_keyword or "复制密码" in current_texts or "GoPay" in current_texts
                
                if is_related:
                    print(f"\n\033[92m[+] [ADB Captured] New WhatsApp OTP intercepted: {code}\033[0m")
                    print(f"[+] Text content: {text}")
                    return code
                
    print("\n\033[93m[!] [ADB Timeout] No new WhatsApp OTP found in 90 seconds. Switching to manual input.\033[0m")
    return None

def normalize_phone(phone: str) -> tuple[str, str]:
    # Extract digits
    digits = re.sub(r"\D", "", phone)
    if digits.startswith("62"):
        return "+62", digits[2:]
    if digits.startswith("0"):
        return "+62", digits[1:]
    return "+62", digits

def main():
    import argparse
    parser = argparse.ArgumentParser(description="GoPay Protocol Login Console")
    parser.add_argument("--phone", type=str, default="+6285141462017", help="Target phone number")
    parser.add_argument("--method", type=str, default="otp_wa", choices=["otp_wa", "otp_sms"], help="OTP dispatch channel")
    parser.add_argument("--client-id", type=str, default="gopay:consumer:app", help="Client ID")
    parser.add_argument("--client-secret", type=str, default="raOUumeMRBNifqvZRFjvsgTnjAlaA9", help="Client Secret")
    parser.add_argument("--device-id", type=str, default=None, help="Device unique ID / android_id")
    args = parser.parse_args()

    phone_raw = args.phone
    method = args.method
    client_id = args.client_id
    client_secret = args.client_secret
    device_id = args.device_id

    country_code, phone_local = normalize_phone(phone_raw)
    phone_normalized = f"{country_code}{phone_local}"

    print("="*60)
    print("        GoPay Pure Protocol Interactive Login Console        ")
    print("="*60)
    print(f"[*] Target Phone: {phone_normalized}")
    print(f"[*] Verification Channel: {method}")
    print(f"[*] Client ID: {client_id}")
    print(f"[*] Device ID: {device_id}")
    print("-"*60)

    # 1. Check ADB connection
    is_connected = False
    try:
        res = subprocess.run([ADB_PATH, "devices"], stdout=subprocess.PIPE, text=True, timeout=5)
        if DEVICE_ID in res.stdout:
            is_connected = True
            print(f"[+] Device Detected: {DEVICE_ID} is ONLINE. Auto-capture ready!")
        else:
            print(f"[-] Device Detected: {DEVICE_ID} is OFFLINE. Manual input fallback enabled.")
    except Exception as e:
        print(f"[-] ADB Check Failed: {e}. Manual input fallback enabled.")

    # Initialize device profile & GoPay protocol
    device = DeviceProfile.default(unique_id=device_id)
    signer = EnhancedPythonXESigner()
    gp = GoPayProtocol(device=device, signer=signer, client_id=client_id, client_secret=client_secret, debug=True)

    try:
        # Step 1: Initiate Login Methods
        print("\n[*] [1/5] Initiating login methods request...")
        sc, data, headers = gp.login_methods(phone_local, country_code)
        if sc not in (200, 201, 202):
            print(f"[-] Login methods request failed (HTTP {sc}): {data}")
        verification_id = pick_first(data, ["verification_id", "challenge_id"])
        if not verification_id:
            print("[-] verification_id or challenge_id not found in response.")
            print(f"[-] Response: {data}")
            return
        
        default_method = data.get("data", {}).get("default_method", method)
        print(f"[+] Verification ID resolved: {verification_id}")

        if default_method == "goto_pin":
            print("\n[*] [2/5] Server requested PIN as default verification method.")
            pin = input("\033[93m请输入6位支付密码 (PIN) 进行强登: \033[0m").strip()
            
            print(f"\n[*] [3/5] Verifying PIN: {pin}...")
            sc, data, headers = gp.cvs_verify(
                phone_local,
                str(verification_id),
                otp=pin,
                method="goto_pin",
                flow="login_1fa",
                country_code=country_code
            )
            if sc not in (200, 201, 202, 204):
                print(f"[-] PIN verification failed (HTTP {sc}): {data}")
                return
            
            login_verification_token = pick_first(data, ["verification_token", "verificationToken"])
            print(f"[+] PIN successfully verified! Token: {login_verification_token}")
        else:
            # OTP Flow
            if is_connected and method == "otp_wa":
                pass

            # Step 2: Trigger OTP Dispatch
            print(f"\n[*] [2/5] Requesting OTP via {method}...")
            sc, data, headers = gp.cvs_initiate(
                phone_local,
                str(verification_id),
                method=method,
                flow="login_1fa",
                country_code=country_code
            )
            if sc not in (200, 201, 202, 204):
                print(f"[-] CVS initiate failed (HTTP {sc}): {data}")
                return

            otp_token = pick_first(data, ["otp_token", "otpToken"])
            print(f"[+] OTP successfully dispatched! OTP Token: {otp_token}")

            # Step 3: Capture OTP
            code = None
            if is_connected and method == "otp_wa":
                code = auto_listen_whatsapp()
            
            if not code:
                code = input("\033[93m请输入收到的验证码 (GoPay通常为 4 位): \033[0m").strip()

            print(f"\n[*] [3/5] Verifying OTP: {code}...")
            sc, data, headers = gp.cvs_verify(
                phone_local,
                str(verification_id),
                otp=code,
                method=method,
                flow="login_1fa",
                otp_token=str(otp_token),
                country_code=country_code
            )
            if sc not in (200, 201, 202, 204):
                print(f"[-] OTP verification failed (HTTP {sc}): {data}")
                return
            
            login_verification_token = pick_first(data, ["verification_token", "verificationToken"])
            print(f"[+] OTP successfully verified! Verification Token: {login_verification_token}")
        
        if not login_verification_token:
            print("[-] verification_token not found in verification response.")
            return
        print(f"[+] OTP Verified! Verification Token: {login_verification_token[:20]}...")

        # Step 5: Resolve Account ID & 1FA Token
        print("\n[*] [4/5] Resolving numeric account ID and 1FA token...")
        sc, data_acct, headers = gp.accountlist(str(login_verification_token))
        if sc not in (200, 201, 202):
            print(f"[-] Account list resolution failed (HTTP {sc}): {data_acct}")
            return

        account_id = pick_first(data_acct, ["account_id", "accountid", "customer_id", "userid", "user_id"])
        one_fa_token = pick_first(data_acct, ["1fa_token", "one_fa_token", "token"])
        if not account_id or not one_fa_token:
            # Try parsing recursively using utility from full_pure_signup_pin
            from full_pure_signup_pin import extract_account_id
            account_id = extract_account_id(data_acct)
            one_fa_token = pick_first(data_acct, ["token"]) or one_fa_token
        
        if not account_id or not one_fa_token:
            print("[-] Could not extract account_id or one_fa_token from accountlist response.")
            print(f"[-] Response: {data_acct}")
            return
        print(f"[+] Resolved Account ID: {account_id}")
        print(f"[+] Resolved 1FA Token: {one_fa_token[:20]}...")

        # Step 6: Final Token Exchange
        print("\n[*] [5/5] Performing final 1FA token exchange...")
        sc, data_tok, headers = gp.token(verification_token=str(one_fa_token), account_id=str(account_id))
        if sc not in (200, 201, 202):
            print(f"[-] Token exchange failed (HTTP {sc}): {data_tok}")
            return

        access_token = pick_first(data_tok, ["access_token", "accessToken"])
        refresh_token = pick_first(data_tok, ["refresh_token", "refreshToken"])
        if not access_token:
            print("[-] Access token not found in token exchange response.")
            return

        print("\n\033[92m" + "="*65)
        print("   GoPay Pure Protocol Interactive Login SUCCESS!")
        print("-" * 65)
        print(f" [★] Account ID: {account_id}")
        print(f" [★] Access Token: {access_token[:50]}...")
        print("=" * 65 + "\033[0m\n")

        # Save and synchronize token
        out_path_1 = Path("C:/Users/gool/repos/gopay/gopay-auto-protocol/latest_token.txt")
        out_path_2 = Path("C:/Users/gool/repos/chatgpt-gopay/chatgpt/latest_token.txt")
        out_path_3 = Path("C:/Users/gool/repos/gopay/latest_token.txt")
        
        out_path_1.parent.mkdir(parents=True, exist_ok=True)
        out_path_2.parent.mkdir(parents=True, exist_ok=True)
        out_path_3.parent.mkdir(parents=True, exist_ok=True)

        out_path_1.write_text(access_token, encoding="utf-8")
        out_path_2.write_text(access_token, encoding="utf-8")
        out_path_3.write_text(access_token, encoding="utf-8")

        print(f"[+] Access Token saved to: {out_path_1}")
        print(f"[+] Access Token synchronized to: {out_path_2}")
        print(f"[+] Access Token synchronized to: {out_path_3}")

    except Exception as e:
        print(f"\n[-] Exception occurred: {e}")
        import traceback
        traceback.print_exc()
    finally:
        gp.close()

if __name__ == "__main__":
    main()
