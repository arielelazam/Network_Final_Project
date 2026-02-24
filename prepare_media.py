"""
סקריפט הכנת מדיה לפרויקט DASH
================================
שלב 1: הרצת הסקריפט יוצרת את מבנה התיקיות
שלב 2: שמים סרטונים מקוריים בתיקיית media/ (שם: movie1.mp4, movie2.mp4, ...)
שלב 3: מריצים שוב - הסקריפט חותך לסגמנטים ב-3 איכויות

דרישות: FFmpeg מותקן (winget install ffmpeg)
"""

import os, json, subprocess, sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
MEDIA_DIR = os.path.join(SCRIPT_DIR, "media")
DOWNLOADS_DIR = os.path.join(SCRIPT_DIR, "downloads")

SEGMENT_DURATION = 3

QUALITIES = {
    "HIGH":   {"scale": "1920:1080", "bitrate": "5M"},
    "MEDIUM": {"scale": "640:360",   "bitrate": "1M"},
    "LOW":    {"scale": "320:180",   "bitrate": "400k"},
}


def create_directories():
    os.makedirs(MEDIA_DIR, exist_ok=True)
    os.makedirs(DOWNLOADS_DIR, exist_ok=True)
    print(f"[OK] media/     -> {MEDIA_DIR}")
    print(f"[OK] downloads/ -> {DOWNLOADS_DIR}")


def check_ffmpeg():
    try:
        result = subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            first_line = result.stdout.split("\n")[0]
            print(f"[OK] FFmpeg found: {first_line}")
            return True
    except FileNotFoundError:
        pass

    print("[!] FFmpeg not found!")
    print("    Install: winget install ffmpeg")
    print("    Or download from: https://ffmpeg.org/download.html")
    return False


def find_source_videos():
    """מחפש סרטונים מקוריים בתיקיית media/ (movie1.mp4, movie2.mp4, ...)"""
    videos = []
    for f in sorted(os.listdir(MEDIA_DIR)):
        if f.endswith(".mp4") and not os.path.isdir(os.path.join(MEDIA_DIR, f)):
            name = os.path.splitext(f)[0]
            if not any(q in name for q in ["HIGH", "MEDIUM", "LOW"]):
                videos.append(f)
    return videos


def get_video_duration(filepath):
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", filepath],
        capture_output=True, text=True
    )
    try:
        return float(result.stdout.strip())
    except ValueError:
        return 0


def process_video(source_file):
    movie_name = os.path.splitext(source_file)[0]
    source_path = os.path.join(MEDIA_DIR, source_file)
    movie_dir = os.path.join(MEDIA_DIR, movie_name)

    os.makedirs(movie_dir, exist_ok=True)

    duration = get_video_duration(source_path)
    expected_segments = int(duration / SEGMENT_DURATION) + (1 if duration % SEGMENT_DURATION > 0 else 0)
    print(f"\n{'='*50}")
    print(f"  Processing: {source_file}")
    print(f"  Duration: {duration:.1f}s -> ~{expected_segments} segments of {SEGMENT_DURATION}s")
    print(f"{'='*50}")

    for quality, settings in QUALITIES.items():
        print(f"\n  [{quality}] Converting to {settings['scale']} @ {settings['bitrate']}...")

        temp_file = os.path.join(movie_dir, f"_temp_{quality}.mp4")
        cmd_convert = [
            "ffmpeg", "-y", "-i", source_path,
            "-vf", f"scale={settings['scale']}",
            "-b:v", settings["bitrate"],
            "-an",
            temp_file
        ]
        subprocess.run(cmd_convert, capture_output=True, text=True)

        print(f"  [{quality}] Splitting into {SEGMENT_DURATION}s segments...")
        seg_pattern = os.path.join(movie_dir, f"seg_%03d_{quality}.mp4")
        cmd_segment = [
            "ffmpeg", "-y", "-i", temp_file,
            "-c", "copy",
            "-f", "segment",
            "-segment_time", str(SEGMENT_DURATION),
            "-reset_timestamps", "1",
            seg_pattern
        ]
        subprocess.run(cmd_segment, capture_output=True, text=True)

        os.remove(temp_file)

        seg_count = len([f for f in os.listdir(movie_dir) if f.endswith(f"_{quality}.mp4")])
        print(f"  [{quality}] Done! {seg_count} segments created.")

    return movie_name, expected_segments


def build_catalog(processed_movies):
    catalog = {}
    for movie_name, seg_count in processed_movies:
        movie_dir = os.path.join(MEDIA_DIR, movie_name)

        actual_seg_count = 0
        for f in os.listdir(movie_dir):
            if f.endswith("_HIGH.mp4"):
                actual_seg_count += 1

        quality_info = {}
        for quality in QUALITIES:
            sizes = []
            for f in sorted(os.listdir(movie_dir)):
                if f.endswith(f"_{quality}.mp4"):
                    size_kb = os.path.getsize(os.path.join(movie_dir, f)) / 1024
                    sizes.append(size_kb)

            avg_size = sum(sizes) / len(sizes) if sizes else 0
            quality_info[quality] = {
                "resolution": QUALITIES[quality]["scale"].replace(":", "x"),
                "bitrate_kbps": int(QUALITIES[quality]["bitrate"].replace("M", "000").replace("k", "")),
                "avg_segment_kb": round(avg_size, 1)
            }

        catalog[movie_name] = {
            "title": movie_name.replace("_", " ").title(),
            "segments": actual_seg_count,
            "segment_duration_sec": SEGMENT_DURATION,
            "total_duration_sec": actual_seg_count * SEGMENT_DURATION,
            "qualities": quality_info
        }

    catalog_path = os.path.join(MEDIA_DIR, "catalog.json")
    with open(catalog_path, "w", encoding="utf-8") as f:
        json.dump(catalog, f, indent=4, ensure_ascii=False)

    print(f"\n[OK] Catalog saved to: {catalog_path}")
    return catalog


def print_summary(catalog):
    print(f"\n{'='*60}")
    print("  SUMMARY")
    print(f"{'='*60}")
    for name, info in catalog.items():
        print(f"\n  {info['title']} ({name}/)")
        print(f"    Segments: {info['segments']} x {info['segment_duration_sec']}s = {info['total_duration_sec']}s total")
        for q, qinfo in info["qualities"].items():
            print(f"    {q:8s} {qinfo['resolution']:>10s}  avg: {qinfo['avg_segment_kb']:>8.1f} KB/segment")
    print(f"\n{'='*60}")


def main():
    print("="*60)
    print("  DASH Media Preparation Tool")
    print("="*60)

    create_directories()

    if not check_ffmpeg():
        print("\n[!] Install FFmpeg and run again.")
        return

    videos = find_source_videos()

    if not videos:
        print(f"\n[!] No source videos found in: {MEDIA_DIR}")
        print(f"    Put your videos there as: movie1.mp4, movie2.mp4, ...")
        print(f"    Then run this script again.")
        print(f"\n    Where to get free videos:")
        print(f"      https://www.pexels.com/videos/")
        print(f"      https://pixabay.com/videos/")
        return

    print(f"\n[OK] Found {len(videos)} source video(s): {', '.join(videos)}")

    processed = []
    for video in videos:
        movie_name, seg_count = process_video(video)
        processed.append((movie_name, seg_count))

    catalog = build_catalog(processed)
    print_summary(catalog)

    print("\n[DONE] Media is ready! You can now run app_server.py")


if __name__ == "__main__":
    main()
