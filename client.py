import socket
import json
import time
import os

# הגדרות כלליות לעבודה מול השרתים
DHCP_IP = "127.0.0.1"
DHCP_PORT = 6767
CLIENT_NAME = "my_client"
DNS_IP = "127.0.0.1"
DNS_PORT = 9999
ENCODING = "utf-8"
MY_SITE_DOMAIN = "app.local"
TIMEOUT = 5
APP_TCP_PORT = 9000
APP_UDP_PORT = 9001

# פונקציות להמרת קוד ל-JSON ולהיפך
def encode_json(msg: dict) -> bytes:
    return json.dumps(msg).encode(ENCODING)

def decode_json(data: bytes) -> dict:
    return json.loads(data.decode(ENCODING))

# פונקציית בקשת כתובת מה-DHCP
def dhcp_get_ip():
    print("Starting the process with DHCP to get IP address")

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock: # ניצור סוקט ממשפחת IPv4 מסוג UDP
        sock.settimeout(TIMEOUT) # נגדיר זמן לזריקת שגיאה אם מידע לא הגיע ותוקע את התוכנית

        # נשלח לשרת ה-DHCP חבילת מידע עם השם שלנו ונגדיר שזאת בקשת DISCOVER
        try:
            discover_msg = {
                "type": "DHCP_DISCOVER",
                "client_name": CLIENT_NAME
            }

            print("Sending DISCOVER message to DHCP\n")
            sock.sendto(encode_json(discover_msg), (DHCP_IP, DHCP_PORT))

            # נקלוט מה-DHCP את כתובת ה-IP שהוא מציע לנו
            print("Waiting for DHCP OFFER\n")
            data, addr = sock.recvfrom(1024)
            offer = decode_json(data)

            print("DHCP OFFER received from DHCP\n")
            if offer.get("type") != "DHCP_OFFER": # אם החבילה שהתקבלה היא לא OFFER
                print("Didn't receive DHCP OFFER - ERROR!!!")
                if offer.get("reason"):
                    print(f"The reason for the ERROR is : {offer.get('reason')}") # נדפיס מה הסיבה שבגללה שקרתה השגיאה
                return None

            client_id = offer.get("client_id")
            offered_ip = offer.get("offered_ip")
            subnet_mask = offer.get("subnet_mask")
            offer_timeout = offer.get("offer_timeout")

            print(f"Client ID: {client_id},Offered IP: {offered_ip}, Subnet mask: {subnet_mask}, Time to take the offered IP: {offer_timeout} seconds\n")

            # קיבלנו את הצעת ה-DHCP וכעת נשלח לו REQUEST ונאשר לו שאנחנו רוצים את ההצעה
            requested_msg = {
                "type": "DHCP_REQUEST",
                "client_name": CLIENT_NAME,
                "requested_ip": offered_ip
            }
            print("Sending REQUEST message to DHCP\n")
            sock.sendto(encode_json(requested_msg), (DHCP_IP, DHCP_PORT))

            data, addr = sock.recvfrom(1024)
            ack = decode_json(data)

            if ack.get("type") != "DHCP_ACK": # אם המידע שהתקבל הוא לא ACK נחזיר שגיאה ואת הסיבה שבגללה היא קרתה
                print("Didn't receive DHCP ACK - ERROR!!!")
                if ack.get("reason"):
                    print(f"The reason for the ERROR is : {ack.get('reason')}")
                return None

            my_ip = ack.get("your_ip") # נשמור את ה-IP שהוקצה לנו
            lease_time_in_seconds = ack.get("lease_seconds") # נשמור את הזמן שיש לנו להשתמש בכתובת ה-IP שקיבלנו

            print(f"Client IP: {my_ip}, Time to use the IP: {lease_time_in_seconds} seconds\n")

            return my_ip

        #תפיסת שגיאות TIMEOUT או שגיאות אחרות לא צפויות
        except socket.timeout:
            print("TIMEOUT ERROR!!!")
            return None

        except Exception as e:
            print(f"UNEXPECTED ERROR!!! Reason: {e}")
            return None

# פונקציית קבלת כתובת מה-DNS
def dns_resolve():
    print("Starting the process with DNS to resolve IP address\n") # נגדיר זמן לזריקת שגיאה אם מידע לא הגיע ותוקע את התוכנית

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock: # ניצור סוקט ממשפחת IPv4 ומסוג UDP
        sock.settimeout(TIMEOUT) # נגדיר זמן לזריקת שגיאה אם מידע לא הגיע ותוקע את התוכנית

        # נשלח ל-DNS את הדומיין שאנחנו רוצים לקבל את ה-IP שלו
        try:
            query = {"domain": MY_SITE_DOMAIN}
            print("Sending query to DNS\n")
            sock.sendto(encode_json(query), (DNS_IP, DNS_PORT))

            data, addr = sock.recvfrom(1024)
            response = decode_json(data)

            if response.get("status") != "success": # אם מסיבה כלשהי ה-DNS לא החזיר לנו את ה-IP המבוקש נחזיר הדועת שגיאה ואת הסיבה שגרמה לה לקרות
                print(f"DNS is not responding - ERROR!!!")
                if response.get("reason"):
                    print(f"The reason for the ERROR is : {response.get('reason')}")
                return None

            # נקלוט מהמידע שהתקבל את הדומיין עבורו ביקשנו IP, את כתובת ה-IP שהתקבלה ומאיפה ה-DNS שלף לנו את הכתובת הזאת
            resolved_domain = response.get("domain")
            resolved_ip = response.get("ip")
            resolved_method = response.get("method")

            print(f"The IP of the requested domain {resolved_domain} is: {resolved_ip} and the method is: {resolved_method}\n")

            return resolved_ip

        # תפיסת שגיאות TIMEOUT או שגיאות אחרות לא צפויות
        except socket.timeout:
            print("TIMEOUT ERROR!!!")
            return None

        except Exception as e:
            print(f"UNEXPECTED ERROR!!! Reason: {e}")

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
        udp_sock.settimeout(10) # נגדיר לסוקט TIMEOUT לקבלת מידע

        downloading_segments = 0 # ניצור מונה שיספור כמה סגמנטים הורדנו
        current_quality = "MEDIUM" # נשמור את האיכות המבוקשת וכברירת מחדל נאתחל אותה ל-MEDIUM
        HIGH_TRESHOLD = 800000 # נגדיר סף להעלאת רמה
        LOW_TRESHOLD = 500000 # נגדיר סף להורדת רמה

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



# פונקצייה ראשית
def main():
    print("Temp client is running!\n")

    my_ip = dhcp_get_ip() # נפנה ל-DHCP לקבל IP

    # אם לא הצלחנו לקבל כתובת IP מה-DHCP נחזיר הודעת שגיאה
    if not my_ip:
        print("Failed to get IP from DHCP")
        return

    time.sleep(1)

    app_ip = dns_resolve() # נבקש מה-DNS את כתובת ה-IP של השרת מולו אנחנו רוצים לעבוד

    # אם לא הצלחנו לקבל את הכתובת מה-DNS נחזיר הודעת שגיאה
    if not app_ip:
        print("Failed to get IP from DNS")
        return

    print("\nEverything worked successfully!\n")
    print(f"My IP: {my_ip}, App IP: {app_ip}\n")
    print("Ready to connect to application!\n")

    # לולאת הממשק של הלקוח מול האפליקציה
    while True:
        result = connect_to_app(app_ip) # נבצע את החיבור לשרת האפליקציה שיכלול את בחירת הסרט הראשונה שהלקוח רוצה להוריד

        if result is None: # אם החיבור לשרת האפליקציה כשל, נדפיס הודעה ונסגור את ההתקשרות
            print("Failed to connect the application... Exiting")
            break

        print("\n" + "*"*60)
        choice = input("What would you want to do now? \n1. Download another movie.\n2. Exit.") # לאחר סיום ההורדה, נשאל את הלקוח מה הוא רוצה לעשות להמשך

        while choice not in ["1", "2"]: # אם הבחירה לא טובה, נבקש ממנו שוב
            print("Invalid choice. Please choose 1 or 2.")
            choice = input("What would you want to do now? \n1. Download another movie.\n2. Exit.")

        # אם הוא בחר לסגור את התקשורת עם האפליקציה, נחזיר הודעה ונסגור
        if choice == "2":
            print("GoodBye! -> Connection closed")
            break

if __name__ == "__main__":
    main()