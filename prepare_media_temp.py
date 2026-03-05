import os
import json
import subprocess

# הגדרות כלליות
SOURCE_DIR = "Movies"  # התיקייה עם הסרטונים המקוריים
MEDIA_DIR = "media" # שם תיקיית היעד אליה נעביר את חתיכות הסרטונים שנוצרו
ENCODING = "utf-8"
SEGMENT_DURATION = 2  # כל סגמנט יהיה באורך של 2 שניות

# הגדרות איכות לכל סגמנט, כלומר ה-bitrate שזה בצם כמה קילוביטים יעברו בכל שנייה
QUALITIES = {
    "LOW": "500k",
    "MEDIUM": "1500k",
    "HIGH": "3000k"
}

# הפונקציה שאחראית לתת לנו את אורכו המלא הסרט
def get_video_duration(video_path):

    # נעזר ב-ffprobe על מנת לקבל את אורך הסרטון המבוקש
    cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", video_path]

    # נשתמש ב-subprocess.run בשביל להריץ את הפקודה בטרמינל דרך הפייתון וננסה לקבל את אורך הסרטון, אם הצלחנו נחזיר את אורכו ואם לא נדפיס הודעת שגיאה ונחזיר None
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True) # נקבל את התוצאה
        duration = float(result.stdout.strip()) # ננקה ממנה אפסים מיותרים
        return duration # נחזיר את אורך הסרטון
    except Exception as e:
        print(f"Error reading duration: {e}")
        return None

# הפונקציה האחראית לקבל סרטון ולחלק אותו לסגמנטים
def split_video_to_segments(input_path, output_dir, movie_name):

    print(f"{'=' * 60}\n")
    print(f"Processing: {movie_name}")
    print(f"{'=' * 60}\n")

    os.makedirs(output_dir, exist_ok=True) # ניצור את התיקייה אליה הסגמנטים ישלחו

    duration = get_video_duration(input_path) # נקבל את אורך הסרטון, אם לא התקבל אורך, נחזיר None
    if duration is None:
        return None

    num_segments = int(duration / SEGMENT_DURATION) # נחשב לכמה סגמנטים עלינו לחלק את הסרטון בהתאם לאורכו
    if duration % SEGMENT_DURATION > 0.5:  # אם יש שארית גדולה מדי, כלומר יצא לנו בחישוב כמות סגמנטים שבפועל לא תכיל את כל הסרטון ותפספס חלק קטן ממנו, נוסיף עוד סגמנט
        num_segments += 1

    print(f"Duration: {duration:.1f}s,  Segments: {num_segments} (every {SEGMENT_DURATION}s)\n")

    # עבור הסרטון הנוכחי, ניצור כל סגמנט שלו בכל אחת משלושת האיכויות
    for quality_name, bitrate in QUALITIES.items():
        print(f"\nCreating {quality_name} quality ({bitrate})")

        for seg_num in range(num_segments): # נעבור על כל הסגמנטים
            start_time = seg_num * SEGMENT_DURATION # השנייה בסרטון בה הסגמנט הנוכחי מתחיל
            output_file = os.path.join(output_dir, f"seg_{seg_num:03d}_{quality_name}.mp4") # נשמור את הסגמנט הנוכחי, באיכות הנוכחית בקובץ

            # נשתמש ב-ffmpeg על מנת למצוא את הסגמנט הנוכחי, "לגזור" אותו מהסרטון, לעשות אותו באיכות הנדרשת ולשמור אותו כקובץ בתיקייה המתאימה
            cmd = ["ffmpeg", "-y",
                "-i", input_path,
                "-ss", str(start_time),
                "-t", str(SEGMENT_DURATION),
                "-b:v", bitrate,
                "-c:v", "libx264",
                "-preset", "fast",
                "-c:a", "aac",
                "-b:a", "128k",
                "-movflags", "+faststart",
                output_file
            ]

            try:
                subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True) # הפעלת הפקודה דרך ה-cmd
                size = os.path.getsize(output_file) # נשמור את גודל הקובץ שנוצר בבתים
                print(f"seg_{seg_num:03d}_{quality_name}.mp4 ({size:,} bytes)") # במידה והכל צלח נדפיס הודעת הצלחה

            except subprocess.CalledProcessError as e: # במידה ולא הצלחנו להריץ את הפקודה כראוי נדפיס הודעת שגיאה ונחזיר None
                print(f"Failed to create seg_{seg_num:03d}_{quality_name}.mp4")
                return None

    return num_segments # במידה והכל צלח כראוי, נחזיר את מספר הסגמנטים שהומרו בהצלחה לכל אחת מהאיכויות


def create_catalog_from_videos():

    print("*" * 30)
    print("Real Video Processing Script")
    print("*" * 30 + "\n")

    # אם התיקייה עם הסרטונים לא קיימת, התוכנית לא תוכל לרוץ ולכן נבקש מהלקוח ליצור אותה ולחזור לנסות שוב
    if not os.path.exists(SOURCE_DIR):
        print(f"Source directory {SOURCE_DIR} not found. Create it and try again")
        return

    video_files = [f for f in os.listdir(SOURCE_DIR) if f.lower().endswith('.mp4')] # אם מצאנו את התיקייה, נחלץ ממנה את כל קבצי ה-mp4

    if not video_files: # אם לא נמצאו קבצי mp4 נחזיר הודעה ללקוח ונסיים את התוכנית
        print(f"No .mp4 files found in '{SOURCE_DIR}'")
        return

    print(f"Found {len(video_files)} videos!")

    # ניצור את מבנה הנתונים שיהיה בעצם הקטלוג שלנו. key = שם הסרט, value = הפרטים עליו
    catalog = {}

    video_number = 1 # ניצור מזהה לכל סרטון

    print(f"Processing video number: {video_number}/{len(video_files)}")

    for video_file in video_files: # נעבור על כל הסרטונים בתיקייה
        movie_number = f"movie{video_number}" # נשמור את השם המספרי של הסרטון הנוכחי
        movie_title = os.path.splitext(video_file)[0] # נשמור את שם הסרטון
        input_path = os.path.join(SOURCE_DIR, video_file) # הנתיב לסרטון הנוכחי
        output_dir = os.path.join(MEDIA_DIR, movie_number) # התיקייה בה ישמרו הסגמנטים של הסרטון הנוכחי
        num_segments = split_video_to_segments(input_path, output_dir, movie_title) # נחלק את הסרטון לסגמנטים

        # אם בוצעה חלוקה של הסרטון לסגמנטים, נוסיף לקטלוג את שמו המספרי של הסרטון כ-key ואת הפרטים כ-value
        if num_segments:
            catalog[movie_number] = {
                "title": movie_title,
                "segments": num_segments,
                "segment_duration_sec": SEGMENT_DURATION,
                "qualities": {
                    "LOW": 500,
                    "MEDIUM": 1500,
                    "HIGH": 3000
                }
            }

        video_number += 1

    if catalog: # אם הקטלוג לא ריק וכן יש בו סרטונים מפוצלים
        catalog_path = os.path.join(MEDIA_DIR, "catalog.json") # ניצור את הנתיב לקטלוג שיצרנו
        with open(catalog_path, "w", encoding=ENCODING) as catalog_file: # ניצור/נדרוס את הקובץ של הקטלוג
            json.dump(catalog, catalog_file, indent=2, ensure_ascii=False) # נייצג את הקטלוג בפורמט JSON ובצורה קריאה

        print(f"Catalog saved in path: {catalog_path}. Total movies in catalog: {len(catalog)}")

    else:
        print("No videos were processed successfully") # אם הקטלוג ריק נחזיר הודעה

if __name__ == "__main__":
    try:
        create_catalog_from_videos()
        print("Catalog file created successfully!")

    # טיפול בשגיאות
    except KeyboardInterrupt:
        print("Cancelled by user")
    except Exception as e:
        print(f"Error: {e}")