import socket
import json
import time

# הגדרות כלליות לעבודה מול השרתים
DHCP_IP = "255.255.255.255"  # broadcast
KNOWN_DHCP_SERVER_IP = None  # אחרי החיבור הראשוני נשמור פה את הכתובת של השרת
DHCP_PORT = 6767
CLIENT_NAME = "my_client"
DNS_IP = "127.0.0.1"
DNS_PORT = 9999
ENCODING = "utf-8"
MY_SITE_DOMAIN = "ariel.ac.il"
TIMEOUT = 5
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
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)  #

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
                sock.sendto(encode_json(requested_msg), (DHCP_IP, DHCP_PORT))

                # מאזינים עד שמקבלים ACK/NAK רלוונטי(שייך ל client_id)
                while True:
                    data, addr = sock.recvfrom(1024)
                    ack = decode_json(data)

                    if ack.get("type") not in ("DHCP_ACK", "DHCP_NAK"):
                        print(f"Ignoring non-ACK/NAK DHCP message: {ack.get('type')}")
                        continue

                    # אם הגיע ACK שלא שייך ללקוח שלנו - להתעלם
                    if ack.get("type") == "DHCP_ACK" and ack.get("client_id") != client_id:
                        print(f"Ignoring ACK for different client_id: {ack.get('client_id')}")  # 🔴 ADDED
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

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(TIMEOUT)

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

        # אם לא התקבלה תשובה בזמן שהוגדר
        except socket.timeout:
            print("TIMEOUT ERROR during DHCP renew!!!")
            return None
        # טיפול בשגיאה לא צפויה
        except Exception as e:
            print(f"UNEXPECTED ERROR during DHCP renew!!! Reason: {e}")
            return None


# פונקציית קבלת כתובת מה-DNS
def dns_resolve():
    print(
        "Starting the process with DNS to resolve IP address\n")  # נגדיר זמן לזריקת שגיאה אם מידע לא הגיע ותוקע את התוכנית

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:  # ניצור סוקט ממשפחת IPv4 ומסוג UDP
        sock.settimeout(TIMEOUT)  # נגדיר זמן לזריקת שגיאה אם מידע לא הגיע ותוקע את התוכנית

        # עוד ניסיונות במקרה של איבוד חבילה (timeout/retry loop)
        for attempt in range(1, DNS_RETRIES + 1):
            # נשלח ל-DNS את הדומיין שאנחנו רוצים לקבל את ה-IP שלו
            try:
                query = {"domain": MY_SITE_DOMAIN}
                print(f"Sending query to DNS (attempt {attempt}/{DNS_RETRIES})\n")
                sock.sendto(encode_json(query), (DNS_IP, DNS_PORT))

                data, addr = sock.recvfrom(1024)
                response = decode_json(data)

                if response.get(
                        "status") != "success":  # אם מסיבה כלשהי ה-DNS לא החזיר לנו את ה-IP המבוקש נחזיר הדועת שגיאה ואת הסיבה שגרמה לה לקרות
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

                print(
                    f"The IP of the requested domain {resolved_domain} is: {resolved_ip} and the method is: {resolved_method}\n")
                return resolved_ip

            # תפיסת שגיאות TIMEOUT או שגיאות אחרות לא צפויות
            except socket.timeout:
                print(f"TIMEOUT ERROR on attempt {attempt}/{DNS_RETRIES}")
                if attempt == DNS_RETRIES:
                    return None

            except Exception as e:
                print(f"UNEXPECTED ERROR!!! Reason: {e}")


# פונקצייה ראשית
def main():
    print("Temp client is running!")

    # קבלת IP ראשונית
    my_ip = dhcp_get_ip()
    if not my_ip:
        print("Failed to get IP from DHCP")
        return

    app_ip = dns_resolve()  # נבקש מה-DNS את כתובת ה-IP של השרת מולו אנחנו רוצים לעבוד

    # אם לא הצלחנו לקבל את הכתובת מה-DNS נחזיר הודעת שגיאה
    if not app_ip:
        print("Failed to get IP from DNS")
        return

    print("\nEverything worked successfully!\n")
    print(f"My IP: {my_ip}, App IP: {app_ip}\n")

    # הזמן שנבקש לחדש את ה- IP
    time.sleep(540)

    renewed_ip = dhcp_renew_ip(my_ip)

    if renewed_ip:
        my_ip = renewed_ip
        print(f"Lease renewed successfully. Current IP: {my_ip}")
    else:
        # החידוש נכשל -> תהליך DHCP מלא מחדש
        print("Renew failed. Restarting full DHCP process...")
        my_ip = dhcp_get_ip()
        if not my_ip:
            print("Failed to reacquire IP after renew failure")
            return
        print(f"Reacquired IP: {my_ip}")


if __name__ == "__main__":
    main()
