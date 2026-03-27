import socket
import json
import time
import urllib.request
import urllib.error
from typing import Dict, Optional
import ssl


DNS_IP = "127.0.0.1" # כתובת ה-IP של שרת ה-DNS
DNS_PORT = 9999 # ה-PORT עליו שרת ה-DNS יעבוד
ENCODING = "utf-8"
DOH_SERVER = "https://cloudflare-dns.com/dns-query" # שרת ה-DoH איתו נשתמש לבקשות DNS מבחוץ

# כתובות מקומיות לפרוייקט
LOCAL_RECORDS = {
    "mysite.local": "192.168.1.10",
    "server.local": "192.168.1.20",
    "db.local": "192.168.1.30",
    "app.local": "127.0.0.1",
}

# Cache פשוט: domain -> (ip, expiry_time)
dns_cache: Dict[str, tuple[str, float]] = {} # מפתח = שם הדומיין, ערך = כתובת ה-IP וזמן התפוגה
CACHE_TTL = 60  # TTL למשך 60 שניות

# פונקציית עזר שתאפשר לנו לצאת "החוצה" לבקש כתובות IP
def create_ssl_context():
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    return context

# פונקציה למחיקת הכתובות שפג תוקפן מה-cache
def cleanup_cache():
    current = time.time() # נדגום את הזמן הנוכחי
    expired = [] # נייצר מערך ריק שיכיל את הדומיינים שאנחנו מעוניינים למחוק, זאת מכיוון שבפייתון אסור למחוק ממילון תוך כדי לולאה (שגיאת runTime) ולכן רק נשמור אותם

    # נעבור בלולאה על כל הדומיינים ב-cache, כל דומיין שזמן התפוגה שלו חלף, יוכנס למערך
    for domain, (ip, expiry) in dns_cache.items():
        if expiry <= current:
            expired.append(domain)
    # נמחק מה-cache את כל אלה שנמצאים במערך
    for domain in expired:
        print(f"CACHE CLEANUP Expired: {domain}")
        del dns_cache[domain]

# פונקציה למימוש בקשות DoH
def query_doh(domain: str) -> tuple[Optional[str], Optional[int]]:
    try:
        url = f"{DOH_SERVER}?name={domain}&type=A" # ניצור כתובת המכילה את שם שרת ה-DoH ואת שם הדומיין ונרצה את התשובה בפורמט A

        request = urllib.request.Request(url) # ניצור את הבקשה עצמה אותה אנחנו הולכים לשלוח "החוצה"
        request.add_header("Accept", "application/dns-json") # נגדיר ב-header שאנחנו שרת DNS ונבקש את התשובה בפורמט JSON

        ssl_context = create_ssl_context()

        with urllib.request.urlopen(request, timeout=5, context= ssl_context) as response: # נתחיל את התקשורת מול השרת החיצוני
            data = json.loads(response.read().decode(ENCODING)) # נקלוט את המידע שהתקבל

        answers = data.get("Answer", []) # נקלוט את התשובות שהתקבלו מהמידע
        if not answers: # אם לא התקבל מידע נחזיר הודעה ללקוח
            print(f"DOH No answer for {domain}")
            return None, None

        for answer in answers: # נעבור על התשובות שהתקבלו
            if answer.get("type") == 1:  # אם אכן התקבל Type A כנדרש (מקובל לסמנו ב-1)
                ip = answer.get("data") # נשמור את כתובת ה-IP
                ttl = answer.get("TTL", CACHE_TTL) # נשמור את ה-TTL
                print(f"DOH {domain} -> {ip} (TTL: {ttl}s)")
                return ip, ttl # נחזיר את ה-IP שהתקבל

        return None, None # אם לא נמצאה תשובה שתואמת ל-Type A נחזיר None

    # תפיסת שגיאות אפשריות
    except urllib.error.URLError as e:
        print(f"DOH ERROR Connection failed: {e}")
        return None, None
    except json.JSONDecodeError as e:
        print(f"DOH ERROR Invalid JSON: {e}")
        return None, None
    except Exception as e:
        print(f"DOH ERROR {e}")
        return None, None

# פונקציה לשליפת הדומיין המבוקש
def resolve_domain(domain: str) -> tuple[Optional[str], Optional[str]]:
    domain = domain.lower().strip()

    # תחילה, ננסה לבדוק האם הוא במאגר הכתובות הסטטי
    if domain in LOCAL_RECORDS:
        ip = LOCAL_RECORDS[domain]
        print(f"LOCAL {domain} -> {ip}")
        return ip, "LOCAL"

    # אם הדומיין לא במאגר הכתובות הסטטי, נבדוק האם הוא קיים ב-Cache
    if domain in dns_cache:
        ip, expiry = dns_cache[domain]
        remaining = expiry - time.time()

        if remaining > 0: # במידה והדומיין ב-Cache נבדוק שזמן התפוגה שלו לא פג ואם זמנו לא פג, נחזיר אותו
            print(f"CACHE HIT {domain} -> {ip} (TTL: {int(remaining)}s)")
            return ip, "CACHE"
        else: # אם פג תוקפו, נמחק אותו מה-Cache והקוד ימשיך לשלב הבא
            print(f"CACHE Expired entry for {domain}")
            del dns_cache[domain]

    print(f"DOH Querying {domain}...") # הדומיין המבוקש לא נמצא אצלנו בשרת ולכן נצא "החוצה" לבקש אותו
    ip, ttl = query_doh(domain)

    # אם הצלחנו לקבל כתובת IP מהשרת החיצוני, נשמור אותו ב-Cache ונחזיר אותו
    if ip:
        if not isinstance(ttl, int) or ttl <= 0:
            ttl = CACHE_TTL
        dns_cache[domain] = (ip, time.time() + ttl)
        return ip, "DoH"

    return None, None

# פונקציה לניהול בקשות הלקוח
def handle_request(data: bytes, addr) -> dict:
    try:
        request = json.loads(data.decode(ENCODING)) # המרת הבתים שהתקבלו לפורמט JSON
        domain = request.get("domain", "") # ננסה לחלץ את שם הדומיין

        if not domain: # אם לא נמצא שם דומיין, נחזיר הודעה
            return {"status": "error", "reason": "MISSING_DOMAIN"}

        print(f"\nREQUEST from {addr}: {domain}")

        ip, method = resolve_domain(domain) # אם נמצא שם הדומיין, ננסה לשלוף את כתובת ה-IP שלו ואת המקור ממנו שלפנו אותו

    # אם הצלחנו לשלוף את כתובת ה-IP נחזיר ואם לא מצאנו נחזיר הודעה
        if ip:
            return {
                "status": "success",
                "domain": domain,
                "ip": ip,
                "method": method
            }
        else:
            return {
                "status": "error",
                "reason": "NXDOMAIN",
                "domain": domain
            }

# טיפול בשגיאות
    except json.JSONDecodeError:
        return {"status": "error", "reason": "INVALID_JSON"}
    except Exception as e:
        return {"status": "error", "reason": str(e)}

# פונקציית תצוגת המידע על ה-Cache
def display_cache():
    if not dns_cache: # אם ה-Cache ריק, לא יקרה כלום
        return

    print("\n--- Cache Status ---")
    current = time.time()
    # עבור כל דומיין ב-Cache נדפיס את הזמן שנותר לו
    for domain, (ip, expiry) in dns_cache.items():
        remaining = max(0, int(expiry - current))
        print(f"{domain} -> {ip} (TTL: {remaining}s)")
    print("--------------------\n")

# פונקציה ראשית
def main():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM) # ניצור סוקט UDP כך שיוכלו לפנות לשרת
    sock.bind((DNS_IP, DNS_PORT)) # נגדיר לו את ה-IP וה-PORT שאליו יפנה לקוח שירצה ליצור קשר
    sock.settimeout(1.0)

    print("=" * 30)
    print(f"DNS Server: {DNS_IP}:{DNS_PORT}")
    print(f"Upstream: Cloudflare DoH")
    print(f"Default fallback TTL: {CACHE_TTL}s")
    print("=" * 30)
    print("\nWaiting for queries...\n")

    while True:
        cleanup_cache() # ננקה מה-Cache דומיינים שפג תוקפם

        try:
            data, addr = sock.recvfrom(1024)  # נקבל מהלקוח את הבקשה אותה הוא מבקש ואת כתובת ה-IP שלו שאליה נחזיר לו תשובה

            response = handle_request(data, addr)  # נקבל מילון המכיל את התשובה ואת כתובת ה-IP ומאיפה שלפנו אותה (אם נמצאה)

            response_data = json.dumps(response).encode(ENCODING)  # נמיר חזרה לבתים
            sock.sendto(response_data, addr)  # נשלח את התשובה בחזרה ללקוח

            print(f"RESPONSE: {response['status']}")

            # הצגת cache כל כמה בקשות
            if len(dns_cache) > 0:
                display_cache()

        except socket.timeout:
            continue

        except json.JSONDecodeError:
            print("Received invalid data (not JSON)")
            continue

        except Exception as e:
            print(f"An unexpected error occurred: {e}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nDNS Server stopped. Goodbye!")