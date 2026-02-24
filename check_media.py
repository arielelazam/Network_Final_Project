import os

script_dir = os.path.dirname(os.path.abspath(__file__))
media_dir = os.path.join(script_dir, "media")

print(f"Project dir: {script_dir}")
print(f"Media dir:   {media_dir}")
print(f"Exists:      {os.path.exists(media_dir)}")
print()

if os.path.exists(media_dir):
    items = os.listdir(media_dir)
    if not items:
        print("media/ is EMPTY - put movie1.mp4, movie2.mp4 here")
    else:
        print(f"Found {len(items)} items:")
        for item in sorted(items):
            full = os.path.join(media_dir, item)
            if os.path.isdir(full):
                sub_items = os.listdir(full)
                print(f"  [DIR]  {item}/ ({len(sub_items)} files)")
            else:
                size_kb = os.path.getsize(full) / 1024
                size_mb = size_kb / 1024
                if size_mb >= 1:
                    print(f"  [FILE] {item} ({size_mb:.1f} MB)")
                else:
                    print(f"  [FILE] {item} ({size_kb:.0f} KB)")
else:
    print("media/ folder does not exist!")
