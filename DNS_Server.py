import json, time, ssl, os, subprocess, threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
from typing import Dict, List, Tuple, Any, Optional


SERVER_IP = "127.0.0.2"       # הכתובת שעליה השרת מאזין
SERVER_PORT = 5300            # פורט HTTPS
ENCODING = "utf-8"            # קידוד לטקסט

# SSL - תעודה של השרת (בשביל ההזדהות)
CERT_FILE = "server.crt" # קובץ התעודה
KEY_FILE  = "server.key" # קובץ המפתח

# יציאה לשרת DNS דרך Cloudflare
EXTERNAL_DNS_URL = "https://cloudflare-dns.com/dns-query"
# https://dns.google/dns-query - אפשרות יציאה דרך גוגל

# TTL ברירת מחדל לרשומות שמגיעות מבחוץ (בשניות)
DEFAULT_EXTERNAL_TTL = 60

# type (סוג), value (ערך) - רשומות מקומיות
LOCAL_RECORDS: Dict[str, List[Dict[str, Any]]] = {
    "mysite.local":  [{"type": "A", "value": "192.168.1.10"}],
    "server.local":  [{"type": "A", "value": "192.168.1.20"}],
    "db.local":      [{"type": "A", "value": "192.168.1.30"}],
    "app.local":     [{"type": "A", "value": "192.168.1.40"}],
}

# מיפוי סוגי רשומות DNS למספרים (לפי תקן RFC 1035)
RECORD_TYPE_MAP = {"A": 1, "AAAA": 28, "CNAME": 5, "MX": 15, "TXT": 16, "NS": 2}


# יצירת תעודת SSL עצמית
def generate_self_signed_cert() -> bool: 
    if os.path.exists(CERT_FILE) and os.path.exists(KEY_FILE): # אם הקבצים קיימים
        print("  SSL Using existing certificate files.") 
        return True

    # אם הקבצים לא קיימים, יוצרים חדשים
    print("  SSL - Generating self-signed certificate...") 
    try:
        subprocess.run([ "openssl", "req", "-x509", "-newkey", "rsa:2048", "-keyout", KEY_FILE, "-out", CERT_FILE, "-days", "365", "-nodes", "-subj", f"/CN={SERVER_IP}" ], check=True, capture_output=True)
        print("  [SSL] Certificate generated successfully!")
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("  [!] openssl not found. Cannot generate SSL certificate.")
        print(f"      Generate manually with:")
        print(f'      openssl req -x509 -newkey rsa:2048 -keyout {KEY_FILE} -out {CERT_FILE} -days 365 -nodes -subj "/CN={SERVER_IP}"')
        print(f"      Or install openssl: https://slproweb.com/products/Win32OpenSSL.html")
        return False


# DNS מטמון
class DNSCache:

    #אתחול מטמון
    def __init__(self):
        # מפתח: (שם_דומיין, סוג_רשומה)
        self._cache: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}

    #מחפש רשומות במטמון
    def get(self, domain: str, record_type: str) -> Optional[List[Dict[str, Any]]]:
        key = (domain.lower(), record_type)
        if key not in self._cache:
            return None

        current = time.time()
        
        # שומרים רק רשומות שעדיין לא פג תוקפן
        valid = []
        for entry in self._cache[key]:
            remaining = int(entry["expiry"] - current) 
            if remaining > 0:
                valid.append({"value": entry["value"], "ttl": remaining})

        if not valid: # אם אין רשומות תקופתיות 
            del self._cache[key]  # מוחקים את המפתח
            return None

        return valid

    #מוסיף רשומה למטמון
    def put(self, domain: str, record_type: str, value: str, ttl: int):
        key = (domain.lower(), record_type)
        expiry = time.time() + ttl  # הזמן שבו הרשומה תפוג
        
        #אם המפתח לא קיים, יוצרים רשימה ריקה
        if key not in self._cache:
            self._cache[key] = []

        #הסרת כפילויותו (אם הערך כבר קיים, מחליפים אותו)
        self._cache[key] = [e for e in self._cache[key]
            if e["value"] != value and e["expiry"] > time.time()
        ]
        self._cache[key].append({"value": value, "expiry": expiry}) # מוסיפים את הרשומה למטמון

    #מנקה את כל הרשומות שפג תוקפן
    def cleanup(self):
        current = time.time()
        expired_keys = [] # רשימה שמכילה את המפתחות שפגו
        
        #עובר על כל המפתחות במטמון
        for key in self._cache:
            self._cache[key] = [e for e in self._cache[key] if e["expiry"] > current]

            #אם הרשימה ריקה, מוסיפים את המפתח לרשימה של המפתחות שפגו
            if not self._cache[key]:
                expired_keys.append(key)
        
        #מוחקים את המפתחות שפגו
        for k in expired_keys:
            del self._cache[k]

    #(לצורך דיבוג) מדפיס את תוכן המטמון למסך
    def display(self):
        current = time.time()
        print("\n+---------- Cache Contents ----------+") 
        if not self._cache:
            print("|           (cache is empty)         |")
        else:
            for (domain, rtype), entries in self._cache.items(): # עובר על כל הרשומות במטמון
                for entry in entries:
                    remaining = max(0, int(entry["expiry"] - current)) # מחשב את הזמן שנותר לה להיות בשימוש
                    print(f"|  {domain} ({rtype}) -> {entry['value']}  [TTL: {remaining}s]")
        print("+------------------------------------------+\n")


#  פנייה ישירה ל-DNS חיצוני (Cloudflare)
def resolve_external(domain: str, record_type: str) -> Optional[List[Dict[str, Any]]]:
    try:
        # בניית ה-URL עם פרמטרים – שם הדומיין וסוג הרשומה
        url = f"{EXTERNAL_DNS_URL}?name={domain}&type={record_type}"

        # יצירת בקשת HTTPS עם הכותרת
        req = Request(url)
        req.add_header("Accept", "application/dns-json")

        # יצירת SSL context לחיבור מאובטח ל-Cloudflare
        # ננסה קודם עם תעודות המערכת, אם לא עובד (בעיה נפוצה ב-Windows)
        # ננסה עם certifi, ואם גם זה לא – נדלג על אימות (לפיתוח בלבד)
        try:
            import certifi
            ctx = ssl.create_default_context(cafile=certifi.where())
        except ImportError:
            ctx = ssl.create_default_context()
            # אם תעודות המערכת לא עובדות, מבטלים אימות (לא מומלץ בייצור!)
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE

        # שליחת הבקשה וקבלת התשובה
        with urlopen(req, context=ctx, timeout=5) as response:
            data = json.loads(response.read().decode(ENCODING))

        # פענוח התשובה – מחזיר JSON בפורמט תקני
        answers = data.get("Answer", [])
        if not answers:
            return None

        # סינון לפי סוג הרשומה (A=1, AAAA=28, וכו')
        expected_type = RECORD_TYPE_MAP.get(record_type, 0)
        seen = set()
        records = []
        for ans in answers:
            if ans.get("type") != expected_type:
                continue  # דילוג על רשומות מסוג אחר (למשל CNAME)
            value = ans.get("data", "").strip('"')
            ttl = ans.get("TTL", DEFAULT_EXTERNAL_TTL)
            if value and value not in seen:
                seen.add(value)
                records.append({"value": value, "ttl": ttl})

        return records if records else None

    except (URLError, HTTPError) as e:
        print(f"  [!] External query failed: {e}")
        return None
    except Exception as e:
        print(f"  [!] Error in external resolution: {e}")
        return None


# פונקציה ראשית של DNS
def resolve_query(domain: str, record_type: str, cache: DNSCache) -> Dict[str, Any]:
    type_int = RECORD_TYPE_MAP.get(record_type, 0)

    # שלב 1: בדיקה ברשומות המקומיות
    local_entries = LOCAL_RECORDS.get(domain)
    if local_entries:
        # סינון רק הרשומות שמתאימות לסוג שהלקוח ביקש
        matching = [e for e in local_entries if e["type"] == record_type]
        if matching:
            print(f"  [LOCAL] Found in local records!")
            return {
                "Status": 0,  # NO ERROR
                "Question": [{"name": domain, "type": type_int}],
                "Answer": [
                    {"name": domain, "type": type_int, "TTL": 0, "data": r["value"]}
                    for r in matching
                ],
                "source": "local",
            }

    # שלב 2: בדיקה במטמון
    cached = cache.get(domain, record_type)
    if cached:
        print(f"  CACHE HIT Found in cache!")
        return {
            "Status": 0,
            "Question": [{"name": domain, "type": type_int}],
            "Answer": [
                {"name": domain, "type": type_int, "TTL": r["ttl"], "data": r["value"]}
                for r in cached
            ],
            "source": "cache",
        }

    # שלב 3: פנייה ישירה לשרת DNS חיצוני
    print(f"  [FORWARD] Querying external DNS (Cloudflare)...")
    external_records = resolve_external(domain, record_type)

    if external_records:
        # שמירת כל התוצאות במטמון לפעם הבאה
        for rec in external_records:
            cache.put(domain, record_type, rec["value"], rec["ttl"])
            print(f"  [CACHED] {domain} -> {rec['value']} (TTL: {rec['ttl']}s)")

        return {
            "Status": 0,
            "Question": [{"name": domain, "type": type_int}],
            "Answer": [
                {"name": domain, "type": type_int, "TTL": r["ttl"], "data": r["value"]}
                for r in external_records
            ],
            "source": "external",
        }

    # הדומיין לא נמצא בשום מקום
    print(f"  [NXDOMAIN] Domain '{domain}' not found!")
    return {
        "Status": 3,  # NXDOMAIN
        "Question": [{"name": domain, "type": type_int}],
        "Answer": [],
        "error": "NXDOMAIN",
    }


# מטפל בבקשות DNS
class DNSHandler(BaseHTTPRequestHandler):

    cache: DNSCache = None

    def do_GET(self):
       #טיפול בבקשת GET
        parsed = urlparse(self.path)

        # רק נתיב /dns-query תקין
        if parsed.path != "/dns-query":
            self.send_error(404, "Not Found - use /dns-query")
            return

        # שליפת פרמטרים
        params = parse_qs(parsed.query)
        domain = params.get("name", [""])[0].strip().lower()
        record_type = params.get("type", ["A"])[0].strip().upper()

        if not domain:
            self._send_json(400, {"Status": 2, "error": "MISSING_DOMAIN"})
            return

        print(f"\n>> [GET] Query: {domain} ({record_type}) from {self.client_address}")

        #החזרת תשובה
        result = resolve_query(domain, record_type, self.cache) 
        self._send_json(200, result)
        self.cache.display()

    # [תאימות לאחור – UDP] כל הפונקציה הזו קיימת רק בשביל לקוחות ישנים
    # שהיו שולחים JSON בגוף ההודעה (מהגרסה שעבדה על UDP).
    def do_POST(self):
        content_len = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_len).decode(ENCODING)

        try:
            msg = json.loads(body)
        except json.JSONDecodeError:
            self._send_json(400, {"Status": 2, "error": "INVALID_JSON"})
            return

        # [תאימות לאחור – UDP] הפורמט הישן: {"type":"DNS_QUERY","domain":"...","record_type":"A"}
        # הפורמט החדש (תקני):                {"name":"...","type":"A"}
        if msg.get("type") == "DNS_QUERY":  #  פורמט ישן (UDP)
            domain = msg.get("domain", "").strip().lower()
            record_type = msg.get("record_type", "A").strip().upper()
        else:  # פורמט חדש (תקני)
            domain = msg.get("name", "").strip().lower()
            record_type = str(msg.get("type", "A")).strip().upper()

        if not domain:
            self._send_json(400, {"Status": 2, "error": "MISSING_DOMAIN"})
            return

        print(f"\n>> [POST] Query: {domain} ({record_type}) from {self.client_address}")

        result = resolve_query(domain, record_type, self.cache)
        self._send_json(200, result)
        self.cache.display()

    #
    def _send_json(self, status_code: int, data: dict):                  
        body = json.dumps(data, ensure_ascii=False).encode(ENCODING)               # הופכת את המילון לבתים
        self.send_response(status_code)                                            # קוד הסטטוס
        self.send_header("Content-Type", "application/dns-json")      # כותרת תוכן
        self.send_header("Content-Length", str(len(body)))                 #גודל התוכן
        self.send_header("Access-Control-Allow-Origin", "*")          # כותרת שיקוף
        self.end_headers()                                                        # סוגר את הכותרות
        self.wfile.write(body)                                                    # שולח את התוכן(התשובה עצמה) ללקוח


#  ניקוי מטמון
def cache_cleanup_worker(cache: DNSCache, interval: float = 1.0):
    while True:
        time.sleep(interval)
        cache.cleanup()


# הפעלת השרת
def main():
    #יצירת תעודת SSL
    has_ssl = generate_self_signed_cert()

    #יצירת מטמון חדש (ריק)
    cache = DNSCache()
    DNSHandler.cache = cache  # מעבירים את המטמון למטפל הבקשות

    # תהליכון ניקוי מטמון ברקע (כל שנייה)
    cleanup_thread = threading.Thread(
        target=cache_cleanup_worker, args=(cache,), daemon=True
    )
    cleanup_thread.start()

    # יצירת שרת HTTP(S)
    server = HTTPServer((SERVER_IP, SERVER_PORT), DNSHandler)

    # עטיפת הסוקט ב-SSL אם יש תעודה (הופך HTTP ל-HTTPS)
    protocol = "http"
    if has_ssl:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(CERT_FILE, KEY_FILE)
        server.socket = ctx.wrap_socket(server.socket, server_side=True)
        protocol = "https"

    # הדפסת מידע על השרת
    base_url = f"{protocol}://{SERVER_IP}:{SERVER_PORT}"
    print("=" * 60)
    print("        Local DNS Server (DoH - DNS over HTTPS)")
    print("=" * 60)
    print(f"  Listening on:     {base_url}")
    print(f"  Protocol:         DoH ({protocol.upper()} + JSON)")
    print(f"  External DNS:     Cloudflare DoH (direct, not via OS)")
    print(f"  Local records:    {len(LOCAL_RECORDS)}")
    print("-" * 60)
    print("  Local records:")
    for domain, entries in LOCAL_RECORDS.items():
        for rec in entries:
            print(f"    {domain:<25} {rec['type']:<6} -> {rec['value']}")
    print("-" * 60)
    print("  Example queries:")
    print(f"    GET:  curl -k \"{base_url}/dns-query?name=google.com&type=A\"")
    print(f"    POST: curl -k -X POST -H \"Content-Type: application/json\" \\")
    print(f"          -d '{{\"domain\":\"google.com\",\"record_type\":\"A\"}}' \\")
    print(f"          \"{base_url}/dns-query\"")
    if not has_ssl:
        print()
        print("  [!] WARNING: Running in HTTP mode (no SSL certificate).")
        print("      In production, DoH requires HTTPS!")
    print("=" * 60)
    print("\nWaiting for queries...\n")

    # לולאה ראשית – מאזין לבקשות HTTPS
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n\nDNS Server stopped. Goodbye!")
        server.server_close()


if __name__ == "__main__":
    main()
