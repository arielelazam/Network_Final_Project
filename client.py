import socket, json, time, os, ipaddress
from random import choice

# הגדרות כלליות לעבודה מול השרתים
DHCP_IP = "255.255.255.255"  # broadcast
KNOWN_DHCP_SERVER_IP = None  # אחרי החיבור הראשוני נשמור פה את הכתובת של השרת
DHCP_PORT = 6767
CLIENT_NAME = "my_client"
DNS_IP = "127.0.0.1"
DNS_PORT = 9999
ENCODING = "utf-8"
MY_SITE_DOMAIN = "app.local"
TIMEOUT = 5
APP_TCP_PORT = 9000
APP_UDP_PORT = 9001

# ב UDP חבילות יכולות ללכת לאיבוד אז שולחים 3 פעמים
DHCP_RETRIES = 3
DNS_RETRIES = 3

# פונקציות להמרת קוד ל-JSON ולהיפך
def encode_json(msg: dict) -> bytes:
    return json.dumps(msg).encode(ENCODING)

def decode_json(data: bytes) -> dict:
    return json.loads(data.decode(ENCODING))

# פונקציית בקשת כתובת מה-DHCP
def dhcp_get_ip():
    print("Starting the process with DHCP to get IP address")

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:  # ניצור סוקט ממשפחת IPv4 מסוג UDP
        sock.settimeout(TIMEOUT)  # נגדיר זמן לזריקת שגיאה אם מידע לא הגיע ותוקע את התוכנית
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

        # עוד ניסיונות במקרה של איבוד חבילה (timeout/retry loop)
        for attempt in range(1, DHCP_RETRIES + 1):
            try:
                discover_msg = {
                    "type": "DHCP_DISCOVER",
                    "client_name": CLIENT_NAME
                }

                print(f"Sending DISCOVER message to DHCP (attempt {attempt}/{DHCP_RETRIES})\n")
                sock.sendto(encode_json(discover_msg), (DHCP_IP, DHCP_PORT))

                # נקלוט מה-DHCP את כתובת ה-IP שהוא מציע לנו
                print("Waiting for DHCP OFFER\n")

                # מחכה להודעה רלוונטית (לא לקחת על עיוור)
                offer = None
                while True:
                    data, addr = sock.recvfrom(1024)
                    candidate = decode_json(data)

                    # אם קיבלנו offer אפשר להתקדם
                    if candidate.get("type") == "DHCP_OFFER":

                        # שמירת הכתובת IP של השרת DHCP
                        global KNOWN_DHCP_SERVER_IP  # global - תפנה למשתמש מחוץ לפונקציה(הגדרנו אותו למעלה בקבועים)
                        KNOWN_DHCP_SERVER_IP = addr[0]
                        print(f"Learned DHCP server IP: {KNOWN_DHCP_SERVER_IP}")

                        offer = candidate
                        break

                    if candidate.get("type") == "DHCP_NAK":
                        print("Didn't receive DHCP OFFER - ERROR!!!")
                        if candidate.get("reason"):
                            print(f"The reason for the ERROR is : {candidate.get('reason')}")
                        return None

                    # הודעה לא רלוונטית - מתעלמים וממשיכים להאזין
                    print(f"Ignoring non-OFFER DHCP message: {candidate.get('type')}")

                print("DHCP OFFER received from DHCP\n")

                client_id = offer.get("client_id")
                offered_ip = offer.get("offered_ip")
                subnet_mask = offer.get("subnet_mask")
                offer_timeout = offer.get("offer_timeout")

                if client_id is None or not offered_ip:
                    print("Invalid DHCP OFFER - missing client_id/offered_ip")
                    continue

                print(f"Client ID: {client_id},Offered IP: {offered_ip}, Subnet mask: {subnet_mask}, Time to take the offered IP: {offer_timeout} seconds\n")

                # קיבלנו את הצעת ה-DHCP וכעת נשלח לו REQUEST ונאשר לו שאנחנו רוצים את ההצעה
                requested_msg = {
                    "type": "DHCP_REQUEST",
                    "client_name": CLIENT_NAME,
                    "requested_ip": offered_ip
                }
                print("Sending REQUEST message to DHCP\n")

                request_target_ip = KNOWN_DHCP_SERVER_IP if KNOWN_DHCP_SERVER_IP else DHCP_IP
                sock.sendto(encode_json(requested_msg), (request_target_ip, DHCP_PORT))

                # מאזינים עד שמקבלים ACK/NAK רלוונטי(שייך ל client_id)
                while True:
                    data, addr = sock.recvfrom(1024)
                    ack = decode_json(data)

                    if ack.get("type") not in ("DHCP_ACK", "DHCP_NAK"):
                        print(f"Ignoring non-ACK/NAK DHCP message: {ack.get('type')}")
                        continue

                    # אם הגיע ACK שלא שייך ללקוח שלנו - להתעלם
                    if ack.get("type") == "DHCP_ACK" and ack.get("client_id") != client_id:
                        print(f"Ignoring ACK for different client_id: {ack.get('client_id')}")
                        continue

                    break  # הגיע ACK/NAK רלוונטי

                if ack.get("type") != "DHCP_ACK":  # אם המידע שהתקבל הוא לא ACK נחזיר שגיאה ואת הסיבה שבגללה היא קרתה
                    print("Didn't receive DHCP ACK - ERROR!!!")
                    if ack.get("reason"):
                        print(f"The reason for the ERROR is : {ack.get('reason')}")
                    return None

                my_ip = ack.get("your_ip")  # נשמור את ה-IP שהוקצה לנו
                lease_time_in_seconds = ack.get("lease_seconds")  # נשמור את הזמן שיש לנו להשתמש בכתובת ה-IP שקיבלנו

                if not my_ip:
                    print("Invalid DHCP ACK - missing your_ip")
                    continue

                print(f"Client IP: {my_ip}, Time to use the IP: {lease_time_in_seconds} seconds\n")
                return my_ip

            # תפיסת שגיאות TIMEOUT או שגיאות אחרות לא צפויות
            except socket.timeout:
                #
                print(f"TIMEOUT ERROR on attempt {attempt}/{DHCP_RETRIES}")
                if attempt == DHCP_RETRIES:
                    return None

            except Exception as e:
                print(f"UNEXPECTED ERROR!!! Reason: {e}")
                return None

# פונקציית לחידוש IP קיים
def dhcp_renew_ip(current_ip: str):
    print("Starting DHCP lease renewal process\n")

    # אם אנחנו לא יודעים את הכתובת של השרת - אי אפשר להעריך חוזה
    if not KNOWN_DHCP_SERVER_IP:
        print("No known DHCP server IP. Run initial DHCP flow first.")
        return None

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock: # ניצור סוקט ממשפחת IPv4 ומסוג UDP
        sock.settimeout(TIMEOUT)

        # נכין את הודעת ה-Renew ונשלח אותה לשרת ה-DHCP
        try:
            renew_msg = {
                "type": "DHCP_RENEW",
                "client_name": CLIENT_NAME,
                "current_ip": current_ip
            }

            print(f"Sending RENEW message to DHCP server {KNOWN_DHCP_SERVER_IP}\n")

            sock.sendto(encode_json(renew_msg), (KNOWN_DHCP_SERVER_IP, DHCP_PORT))

            data, addr = sock.recvfrom(1024)
            renew_response = decode_json(data)

            # אם לא קיבלנו ACK, החידוש נכשל
            if renew_response.get("type") != "DHCP_ACK":
                print("Didn't receive DHCP ACK for renew - ERROR!!!")
                if renew_response.get("reason"):
                    # אם השרת שלח reason, מדפיסים למה נכשל
                    print(f"The reason for the ERROR is : {renew_response.get('reason')}")
                return None

            # ה- IP שהשרת החזיר לאחר החידוש
            renewed_ip = renew_response.get("your_ip")
            # והזמן החדש
            renewed_lease = renew_response.get("lease_seconds")

            if not renewed_ip:
                print("Invalid DHCP ACK for renew - missing your_ip")
                return None
            # אם זה לא אותו IP שהיה לנו - מחזירים None
            if renewed_ip != current_ip:
                print(f"Renew returned different IP ({renewed_ip}) - expected {current_ip}")
                return None

            print(f"Renew success! IP: {renewed_ip}, New lease: {renewed_lease} seconds\n")

            return renewed_ip

        # טיפול בשגיאות timeout או שגיאות אחרות לא צפויות
        except socket.timeout:
            print("TIMEOUT ERROR during DHCP renew!!!")
            return None

        except Exception as e:
            print(f"UNEXPECTED ERROR during DHCP renew!!! Reason: {e}")
            return None

# פונקציית קבלת כתובת מה-DNS
def dns_resolve(requested_domain : str):
    print("Starting the process with DNS to resolve IP address\n")

   # נבצע "ניקוי" של הדומיין המבוקש
    requested_domain = requested_domain.strip()
    if not requested_domain:
        print("Empty domain is not allowed")
        return None

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:  # ניצור סוקט ממשפחת IPv4 ומסוג UDP
        sock.settimeout(TIMEOUT)  # נגדיר זמן לזריקת שגיאה אם מידע לא הגיע ותוקע את התוכנית

        # עוד ניסיונות במקרה של איבוד חבילה (timeout/retry loop)
        for attempt in range(1, DNS_RETRIES + 1):
            # נשלח ל-DNS את הדומיין שאנחנו רוצים לקבל את ה-IP שלו
            try:
                query = {"domain": requested_domain}
                print(f"Sending query to DNS for '{requested_domain}' (attempt {attempt}/{DNS_RETRIES})\n")
                sock.sendto(encode_json(query), (DNS_IP, DNS_PORT))

                data, addr = sock.recvfrom(1024)
                response = decode_json(data)

                if response.get("status") != "success":  # אם מסיבה כלשהי ה-DNS לא החזיר לנו את ה-IP המבוקש נחזיר הדועת שגיאה ואת הסיבה שגרמה לה לקרות
                    print(f"DNS is not responding - ERROR!!!")
                    if response.get("reason"):
                        print(f"The reason for the ERROR is : {response.get('reason')}")
                    # אם נשארו ניסיונות ננסה שוב
                    if attempt < DNS_RETRIES:
                        continue
                    return None

                # נקלוט מהמידע שהתקבל את הדומיין עבורו ביקשנו IP, את כתובת ה-IP שהתקבלה ומאיפה ה-DNS שלף לנו את הכתובת הזאת
                resolved_domain = response.get("domain")
                resolved_ip = response.get("ip")
                resolved_method = response.get("method")

                if not resolved_ip:
                    print("DNS response missing IP")
                    if attempt < DNS_RETRIES:
                        continue
                    return None

                print(f"The IP of the requested domain {resolved_domain} is: {resolved_ip} and the method is: {resolved_method}\n")
                return resolved_ip

            # תפיסת שגיאות TIMEOUT או שגיאות אחרות לא צפויות
            except socket.timeout:
                print(f"TIMEOUT ERROR on attempt {attempt}/{DNS_RETRIES}")
                if attempt == DNS_RETRIES:
                    return None

            except Exception as e:
                print(f"UNEXPECTED ERROR!!! Reason: {e}")

# פונקציית עזר שתסייע לנו להבין האם יש צורך לפנות לשרת ה-DNS
def is_not_ip_input(user_input: str) -> bool:
    normalized = user_input.strip()
    if not normalized:
        return False

    try:
        ipaddress.ip_address(normalized)  # אם הצליח, זה IP
        return False
    except ValueError: # אחרת, זה שם דומיין
        return True

# פונקציית עזר לקבלת הודעות tcp משרת האפליקציה
def tcp_recv(sock):

    length_in_bytes = sock.recv(4) # נקלוט את 4 הבתים הראשונים בהודעה שיגידו לנו כמה בתים יש בתוכן ההודעה
    if not length_in_bytes: # אם לא התקבל אורך, נחזיר דיקשנרי ריק
        return {}

    length = int.from_bytes(length_in_bytes, byteorder="big") # נמיר את אורך ההודעת ל-int

    data = b"" # נגדיר את ה-buffer שיאסוף את חתיכות המידע שיגיעו (מגיעות בבתים)
    while len(data) < length: # כל עוד ה-buffer שלא מכיל את כל תכולת ההודעה
        chunk = sock.recv(length - len(data)) # ננסה לקלוט בתים עד לאורך הנדרש שנדע שקיבלנו את כל המידע
        if not chunk: # אם לא קיבלנו פיסת מידע, יש בעיה ונחזיר דיקשנרי ריק
            return {}
        data += chunk # נוסיף ל-buffer את המידע שהצלחנו לאסוף באינטרציה הנוכחית

    return decode_json(data) # נחזיר את המידע שנאסף ב-JSON

# פונקציית החיבור לשרת האפליקציה
def connect_to_app(app_ip):

    # טיפול בחלק של בקשות ה-TCP
    print("Connecting to Application Server by TCP...\n")
    print("Getting the movies list...\n")

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as tcp_sock: # ניצור סוקט ממשפחת IPv4 ומסוג tcp
            tcp_sock.settimeout(TIMEOUT) # נגדיר לסוקט TIMEOUT לקבלת מידע
            tcp_sock.connect((app_ip, APP_TCP_PORT)) # נתחבר לשרת האפליקציה בעזרת הכתובת שלו שאותה קיבלנו מה-DNS ובעזרת הפורט שלו

            list_request = {"type": "LIST"} # נגדיר את הדיקשנרי לבקשת קבלת רשימת הסרטים מהשרת
            list_data = encode_json(list_request) # נמיר את הדיקשנרי ל-JSON ואז לרצף של בתים
            tcp_sock.sendall(len( list_data).to_bytes(4, byteorder="big") + list_data)  # נשלח את המידע בצורה כזאת כך שמספר הבתים של המידע (ב-big endian) ולאחר מכן את המידע עצמו

            list_response = tcp_recv(tcp_sock) # נקבל את רשימת הסרטים בעזרת פונקציית העזר

            # נציג למשתמש את רשימת הסרטים הזמינה לו
            movies_to_select = [] # נגדיר מערך עם שמות מייצגים של הסרטים שמהם יוכל המשתמש לבחור
            print("Available movies:")
            movies_index = 1
            for movie_number, movie_info in list_response.get("movies", {}).items():
                movies_to_select.append(movie_number) # נוסיף את השם המייצג של הסרט למערך הבחירות
                print(f"{movies_index}. Movie number: {movie_number}, Movie Title: {movie_info['title']}, Movie Segments Length: {movie_info['segments']}")
                movies_index += 1 # נוסיף מונה שבכל הדפסה של שם הסרט "יצמיד" לו מספר שיהיה ללקוח נוח לבחור

            if not movies_to_select: # אם התקבל קטלוג ריק נחזיר הודעה שאין סרטים זמינים
                print("No Available movies... Try later")
                return None

            # נקלוט מהשתמש את מספר הסרט שהוא רוצה לקבל
            choice = input(f"Select from the list the movie you want (range: 1-{len(movies_to_select)}):\n")

            # אם הקלט מהמשתמש היה לא תקין, נציע לו לבחור שוב מהרשימת הסרטים שהצענו לו לפני כן
            while not choice.isdigit() or int(choice) <= 0 or int(choice) > len(movies_to_select):
                print("Invalid selection. Please try again.")
                choice = input(f"Select from the list above the movie you want (range: 1-{len(movies_to_select)}):\n")

            # "נסמן" את הסרט שהלקוח בחר
            choice_index = int(choice) - 1
            selected_movie = movies_to_select[choice_index]
            print(f"Selected Movie: {selected_movie}. Great Choice!")

            select_request = {"type": "SELECT", "movie": selected_movie} # נכין את הדיקשנרי לבקשת ה-REQUEST לשרת האפליקציה
            select_data = encode_json(select_request) # נמיר את הדיקשנרי ל-JSON ואז לרצף של בתים
            tcp_sock.sendall(len(select_data).to_bytes(4, byteorder="big") + select_data) # נשלח את המידע בצורה כזאת כך שמספר הבתים של המידע (ב-big endian) ולאחר מכן את המידע עצמו

            select_response = tcp_recv(tcp_sock) # נקבל את התגובה על בחירת הסרט משרת האפליקציה

            # אם השרת לא החזיר הודעה שהוא קיבל את בחירת הסרט שלנו נחזיר הודעת שגיאה ונסגור את התוכנית
            if select_response.get("type") != "SELECT_OK":
                print("Failed from Application Server to select the movie")
                return None

            total_number_of_segments = select_response["total_segments"] # נשמור את מספר הסגמנטים שמרכיבים את הסרט שבחרנו
            qualities = select_response["qualities"] # נשמור את אפשרויות האיכויות שסרט מציע

            print(f"The movie contains {total_number_of_segments} segments and the available qualities are: {', '.join(qualities)}")

    # טיפול בשיגאות לא צפויות
    except Exception as e:
        print(f"UNEXPECTED ERROR!!! Reason: {e}")
        return None

    # טיפול בחלק של בקשות ה-UDP
    print("Downloading the movie segments by UDP...")

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp_sock: # נגדיר סוקט ממשפחת IPv4 ומסוג ucp
        udp_sock.settimeout(30) # נגדיר לסוקט TIMEOUT לקבלת מידע

        downloading_segments = 0 # ניצור מונה שיספור כמה סגמנטים הורדנו
        current_quality = "MEDIUM" # נשמור את האיכות המבוקשת וכברירת מחדל נאתחל אותה ל-MEDIUM
        HIGH_TRESHOLD = 200000 # נגדיר סף להעלאת רמה
        LOW_TRESHOLD = 50000 # נגדיר סף להורדת רמה

        for segment in range(total_number_of_segments):
            print(f"Segment number: {segment + 1}/{total_number_of_segments}. Downloaing in {current_quality} Quality: \n")

            start_time = time.time() # נשמור את הזמן התחלת ההורדה

            # נייצר דיקשנרי שיכיל את הבקשה לקבלת הסגמנט המבוקש
            request = {
                "movie": selected_movie,
                "segment": segment,
                "quality": current_quality
            }

            udp_sock.sendto(encode_json(request), (app_ip, APP_UDP_PORT)) # נשלח את בקשת ה-udp לשרת האפליקציה

            received_chunks = {} # נאתחל דיקשנרי ריק שיכיל את חתיכות הסרטון שקיבלנו
            last_seq = None # נשמור את מספר החבילה האחרונה שהתקבלה
            chunk_count = 0 # נאתחל מונה שיספור כמה חבילות אספנו עד כה

            try:
                while True:
                    data, server_addr = udp_sock.recvfrom(65000) # נשמור את המידע שהתקבל ואת כתובת השרת ששלח לנו את המידע
                    packet = decode_json(data) # נבצע פענוח והמרה ל-JSON של החבילה שהתקבלה
                    seq = packet.get("seq") # נשמור את מספר הרצף שהתקבל
                    chunk_data = bytes.fromhex(packet.get("data", "")) # נשמור את המידע בבינארי
                    is_last = packet.get("last", False) # דגל שיגיד לנו האם אנחנו בחבילה האחרונה של הסגמנט המבוקש
                    received_chunks[seq] = chunk_data # נשמור את המידע שהתקבל בדיקשנרי
                    chunk_count += 1

                    ack = {"type": "ACK", "seq": seq} # ניצור את הודעת ה-ACK לשרת שקיבלנו את החבילה הנוכחית
                    udp_sock.sendto(encode_json(ack), server_addr) # נשלח את ה-ACK לשרת

                    if is_last: # אם החבילה הנוכחית היא גם אחרונה של הסגמנט, קראנו את כל המידע הרלוונטי לעת עתה ונצא מהלולאה
                        last_seq = seq
                        break

                end_time = time.time() # נשמור את זמן סיום ההורדה
                download_time = end_time - start_time # נשמור כמה זמן לקח לנו לבצע את הורדת הסגמנט האחרון בסך הכל

                # נסדר את חתיכות הסגמנט
                if last_seq is not None: # אם אכן סיימנו לאסוף את החבילות וקיבלנו את החבילה האחרונה

                    missing_chunks = [seq for seq in range(last_seq + 1) if seq not in received_chunks] # נשמור את כל חתיכות הסגמנט שלא ירדו על מנת למנוע תקיעה של התוכנית

                    # אם חסרה חתיכת סגמנט, נדפיס הודעה ללקוח על כך ונוריד את האיכות ל-LOW בשביל להפחית את הסיכוי שזה יקרה גם בסגמנט הבא ונדלג על הסגמנט
                    if missing_chunks:
                        print(f"Missing Chunks {missing_chunks} in segment {segment}. Segment download incomplete - skipping this segment")
                        current_quality = "LOW"
                        continue

                    ordered_chunks = [received_chunks[seq] for seq in range(last_seq + 1)]
                    segment_data = b"".join(ordered_chunks) # נשמור את המידע של הסגמנט בצורה מסודרת ובבתים
                    segment_size = len(segment_data) # נשמור את גודל הסגמנט בשביל שנדע להוריד/להעלות את איכות הסגמנט הבא

                    downloads_dir = "network_project_downloads" # נגדיר את כתובת התיקייה אליה נרצה לשמור את ההורדה
                    os.makedirs(downloads_dir, exist_ok=True) # ניצור את התיקייה אם היא לא קיימת
                    movie_dir = os.path.join(downloads_dir, selected_movie)
                    os.makedirs(movie_dir, exist_ok=True)
                    file_name = f"seg_{segment:03d}_{current_quality}.mp4"
                    file_path = os.path.join(movie_dir, file_name)

                    with open(file_path, "wb") as file:
                        file.write(segment_data)

                    print("Saved successfully!")

                    # נחשב את ה-Throughput בשביל לדעת האם עלינו להוריד או להעלות את המירות בסגמנט הבא
                    if download_time > 0:
                        throughput = segment_size/download_time
                    else:
                        throughput = segment_size

                    print(f"Downloaded {segment_size} bytes in {download_time:.2f} seconds. Throughput: {throughput/1000:.1f} KB/s ({chunk_count} chunks)")

                    if throughput > HIGH_TRESHOLD: # אם קיבלנו שמהירות ההורדה הייתה גבוהה, נסיק שהקו פנוי ונעלה את האיכות ל-HIGH
                        next_quality = "HIGH"
                        reason = "Fast network"
                    elif throughput > LOW_TRESHOLD: # אם קיבלנו שמהירות ההורדה יחסית גבוהה אבל לא מספיק בשביל HIGH, נשנה את האיכות ל-MEDIUM
                        next_quality = "MEDIUM"
                        reason = "Moderate network"
                    else: # אחרת, נסיק שהקו עמוס ונשנה את האיכות ל-LOW
                        next_quality = "LOW"
                        reason = "Slow network"

                    if segment < total_number_of_segments - 1: # אם הסגמנט האחרון שהורדנו הוא לא הסגמנט האחרון של הסרט, כלומר יש לנו עוד סגמנטים להוריד
                        if next_quality != current_quality: # אם הסגמנט הבא יהיה באיכות שונה עקב אילוצי עומס, נדפיס הודעת עדכון
                            print(f"Quality changed from {current_quality} to {next_quality} because {reason}")
                        else:
                            print(f"Quality stay as {current_quality} because {reason}")

                        current_quality = next_quality # נעדכן את האיכות המבוקשת לסגמנט הבא

                    downloading_segments += 1 # בסוף כל הורדת סגמנט נוסיף 1 למונה שסופר כמה סגמנטים הורדנו

                else: # אחרת, אם לא הצלחנו להוריד סגמנט, נדפיס הודעת שגיאה
                    print("Download Failed")
            # טיפול בשיגאות TIMEOUT
            except socket.timeout:
                print("Download TimedOut! The network is too slow! Changing the quality to LOW")
                current_quality = "LOW"


    print("\n" + "*"*60)
    print(f"Download {downloading_segments}/{total_number_of_segments} segments")

    return downloading_segments


def main():
    print("Client is running!\n")

    my_ip = dhcp_get_ip()

    if not my_ip:
        print("Failed to get IP from DHCP")
        return

    time.sleep(1)
    next_renew_time = time.time() + 540

    while True:

        if time.time() >= next_renew_time:
            renewed_ip = dhcp_renew_ip(my_ip)
            if renewed_ip:
                my_ip = renewed_ip
                print(f"Lease renewed successfully before DNS. Current IP: {my_ip}")
                next_renew_time = time.time() + 540
            else:
                print("Renew failed before DNS. Restarting full DHCP process...")
                my_ip = dhcp_get_ip()
                if not my_ip:
                    print("Failed to reacquire IP after renew failure")
                    return
                next_renew_time = time.time() + 540

        user_domain = input("Enter domain (not IP), or 'exit':\n").strip()

        if user_domain.lower() == "exit":
            print("GoodBye! -> Connection closed")
            break

        if not is_not_ip_input(user_domain):
            print("Invalid input: please enter a domain, not an IP.\n")
            continue

        resolved_ip = dns_resolve(user_domain)

        if not resolved_ip:
            print("Failed to resolve via DNS. Try again.\n")
            continue

        if user_domain != "app.local":
            print(f"General DNS query result: {user_domain} -> {resolved_ip}\n")
            continue

        while True:
            result = connect_to_app(resolved_ip)
            if result is None:
                print("Failed to connect the application... Returning to DNS menu.\n")
                break

            print("\nWhat next?\n1. Download another movie.\n2. Back to DNS menu.\n3. Exit.")

            choice = input("choose 1/2/3: ").strip()

            while choice not in("1", "2", "3"):
                print("Invalid choice. Please choose 1, 2, or 3.")
                choice = input("Choose 1/2/3: ").strip()

            if choice == "1":
                continue

            elif choice == "2":
                break

            else:
                print("GoodBye! -> Connection closed")
                exit(0)

if __name__ == "__main__":
    main()