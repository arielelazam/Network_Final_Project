import json, ssl, socket, os


# הגדרות שרת DNS(שנדע ממי לבקש בקשות DNS)
DNS_Server_IP = "127.0.0.2"
DNS_Server_PORT = 5300
ENCODING = "utf-8"

CERT_FILE = "server.crt" # תעודת הזדהות של השרת

# בודקים האם השרת DNS רץ(כשהוא רץ הוא אמור ליצור את התעודה server.crt)
if not os.path.exists(CERT_FILE):
    print(f"ERROR Certificate file '{CERT_FILE}' not found!")
    print("  The DNS server creates this file when it starts.")
    print("  Please run DNS_Server.py first, then try again.")
    exit(1) # יציאה מהתוכנית

ssl_context = ssl.create_default_context(cafile=CERT_FILE) # התעודה קיימת - טוענים רק אותה בלבד(בודק את התעודה)
ssl_context.check_hostname = False # סומך על בדיקת התעודה ולא על hostname
print(f"[SSL] Certificate loaded successfully from {CERT_FILE}")

# רשומות DNS לפי תקן RFC 1035
RECORD_TYPES = {
    "A" : 1,        # IPv4
    "AAAA" : 28,    # IPv6
    "CNAME" : 5,    # תן לי את השם האמיתי(הפניה משם אחד לאחר)
    "MX" : 15,      # שרת המייל של הדומיין
    "TXT" : 16,     # רשומת טקסט
    "NS" : 2        # שרת השמות שאחראי על הדומיין
}
# מיפוי הפוך(מקבלים מספר -> שם)
RECORD_TYPE_NAMES = {v : k for k, v in RECORD_TYPES.items()}

REQUEST_TIMEOUT = 5 # כמה שניות לחכות
BUFFER_SIZE = 4096 # כמה לקרוא בכל פעם

#
def send_https_request(path):
    #שלב 1: יצירת סוקט
    raw_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    raw_socket.settimeout(REQUEST_TIMEOUT)

    # שלב 2: עטיפה ב - SSL(הצפנה)
    secure_socket = ssl_context.wrap_socket(raw_socket, server_hostname=DNS_Server_IP)

    # שלב 3: התחברות לשרת(TCP)
    try:
        secure_socket.connect((DNS_Server_IP,DNS_Server_PORT))

        # בניית בקשה HTTP GET ידנית
        http_request = (
            f"GET {path} HTTP/1.1\r\n"                         # השיטה - GET, הנתיב - {path}, גרסת הפרוטוקול HTTP/1.1 (שורת הבקשה)
            f"Host: {DNS_Server_IP}:{DNS_Server_PORT}\r\n"     # אומר לשרת באיזה כתובת הוא פנה איליו(של השרת). כי שרת יכול לארח כמה אתרים
            f"Accept: application/dns-json\r\n"                # איזה פורמט אנחנו רוצים את התשובה(אצלנו זה JSON)
            f"Connection: close\r\n"                           # אומרת לשרת לסגור את החיבור אחרי התשובה(ב TCP הוא יכול להשאיר פתוח ולחכות לעוד הודעות)
            f"\r\n"                                            #ב http חובה להשאיר שורה ריקה
        )

        # שליחת הבקשה דרך החיבור המוצפן
        secure_socket.sendall(http_request.encode(ENCODING))

        # קראית התשובה מהשרת
        response_data = b"" # מתחילים ממחרוזרת בתים ריקה וצוברים אליה את כל החתיכות
        while True:
            chunk = secure_socket.recv(BUFFER_SIZE)
            if not chunk: # השרת סיים לשלוח וסגר את החיבור
                break
            response_data += chunk

        # הפרדה בין הכותרות לגוף HTTP
        raw_text = response_data.decode(ENCODING)
        header_part, body_part = raw_text.split("\r\n\r\n", 1)

        # המרת הגוף מ- JSON ל- dictionary
        return json.loads(body_part)

    except socket.timeout:
        print("ERROR Connection timed out - the server is not responding.")
        return None
    except ConnectionError:
        print("ERROR Connection refused - is the DNS server running?")
        return None
    except Exception as e:
        print(f"ERROR {e}")
        return None
    finally:
        secure_socket.close()

# שולחת שאילתת DNS לשרת ומדפיסה את התוצאות
def dns_query(domain, record_type= "A"):
    # בדיקה שסוג הרשומה תקין
    if record_type not in RECORD_TYPES:
        print(f"ERROR Unknown record type '{record_type}'.")
        print(f"Available types: {', '.join(RECORD_TYPES.keys())}")
        return

    # בניית הנתיב לבקשה
    path = f"/dns-query?name={domain}&type={record_type}"
    print(f"\nQUERY {domain} ({record_type})")
    print(f" sending: GET {path}")

    # שליחת הקשה וקבלת התשובה
    result = send_https_request(path)

    # בדיקה אם קיבלנו תשובה
    if result is None:
        print("No response from server.")
        return

    # בדיקת סטטוס התשובה( הצלחה = 0, דומיין לא נמצא = 3)
    # get(מה להחזיר אם לא מצאנו, מה מחפשים)
    status = result.get("Status", -1)
    if status != 0:
        error = result.get("error", "UNKNOWN")
        print(f" Server returned error: {error} (Status: {status})")
        return

    # הדפסת התוצאות
    answers = result.get("Answer", [])       # שולף את רשחמת התשובות(אם אין מפתח מחזיר רשימה ריקה)
    source = result.get("source", "unknown") # שולף מאיפה הגיעה התשובה(אם אין מקור מחזיר unknown)
    print(f" Source: {source} | {len(answers)} record found") # מדפיס כמה רשומות חזרו ואת המקור

    for record in answers:
        rtype_name = RECORD_TYPE_NAMES.get(record.get("type"), "?") # מחפש את 1(A)(אם המספר לא קיים הוא מחזיר ?)
        ttl = record.get("TTL", 0)
        data = record.get("data", "")
        print(f"{record.get('name')} -> {data} [{rtype_name}, TTL: {ttl}s]")

def main():
    # מדפיס הוראות מה לכתוב ואיך
    print("=" * 50)
    print("DNS Client (DoH - DNS over HTTPS)")
    print("=" * 50)
    print(f"Server: {DNS_Server_IP}:{DNS_Server_PORT}")
    print(f"Available types: {', '.join(RECORD_TYPES.keys())}")
    print("-" * 50)
    print("Usage:  domain [type]")
    print("Examples:")
    print("google.com")
    print("google.com AAAA")
    print("mysite.local A")
    print("Type 'exit' to quit.")
    print("=" * 50)

    while True:
        # קלט מהמשתמש
        user_input = input("\nDNS> ").strip()

        #יציאה מהתוכנית
        if user_input.lower() == "exit":
            print("Goodbye!")
            break

        # דילוג על קלט ריק
        if not user_input:
            continue

        # פיצול הקלט לחלקים(שם דומיין + סוג רשומה)
        parts = user_input.split()
        domain = parts[0]
        record_type = parts[1].upper() if len(parts) > 1 else "A" # אם המשתמש כתב סוג רשומה, לוקח אותה. אחרת - ברירת מחדל = "A"

        # שליחת השאילתא
        dns_query(domain, record_type)

if __name__ == "__main__":
    main()