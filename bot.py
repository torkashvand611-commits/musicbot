import os, re, subprocess, tempfile, requests

TOKEN = os.environ["BOT_TOKEN"]
CHANNEL = os.environ["CHANNEL"]
OWNER = int(os.environ["OWNER_ID"])
API = f"https://api.telegram.org/bot{TOKEN}"
FILE_API = f"https://api.telegram.org/file/bot{TOKEN}"

FOOTER = "Channel: @music_chet666"
DEFAULT_TOP = "{title}"

def api(method, **kw):
    r = requests.post(f"{API}/{method}", timeout=300, **kw)
    r.raise_for_status()
    return r.json()["result"]

def say(text):
    api("sendMessage", data={"chat_id": OWNER, "text": text})

def to_sec(t):
    sec = 0
    for p in t.strip().split(":"):
        sec = sec * 60 + int(p)
    return sec

def build_caption(title, performer, extra):
    default = DEFAULT_TOP.format(title=title, performer=performer)
    extra = extra.strip()
    if extra.startswith("+"):
        top = (default + "\n" + extra[1:].strip()).strip()
    elif extra:
        top = extra
    else:
        top = default
    return (top + "\n" + FOOTER).strip()

def get_cover(d):
    # اول عکس پروفایل خود ربات، اگه نشد cover.jpg
    try:
        me = api("getMe")
        res = api("getUserProfilePhotos", data={"user_id": me["id"], "limit": 1})
        if res["total_count"] > 0:
            fid = res["photos"][0][-1]["file_id"]
            p = api("getFile", data={"file_id": fid})["file_path"]
            out = f"{d}/cover_bot.jpg"
            with open(out, "wb") as f:
                f.write(requests.get(f"{FILE_API}/{p}", timeout=60).content)
            return out
    except Exception as ex:
        print("profile photo failed:", ex)
    return "cover.jpg" if os.path.exists("cover.jpg") else None

def process(audio, text):
    lines = text.strip().split("\n")
    s, e = re.split(r"\s*[-–]\s*", lines[0].strip())
    start, end = to_sec(s), to_sec(e)
    if audio.get("duration"):
        end = min(end, audio["duration"])
    assert end > start
    title = audio.get("title", "")
    performer = audio.get("performer", "")
    caption = build_caption(title, performer, "\n".join(lines[1:]))

    path = api("getFile", data={"file_id": audio["file_id"]})["file_path"]
    with tempfile.TemporaryDirectory() as d:
        src, voice, thumb = f"{d}/song.mp3", f"{d}/v.ogg", f"{d}/t.jpg"
        with open(src, "wb") as f:
            f.write(requests.get(f"{FILE_API}/{path}", timeout=300).content)
        subprocess.run(["ffmpeg", "-y", "-ss", str(start), "-t", str(end - start),
            "-i", src, "-vn", "-c:a", "libopus", "-b:a", "48k",
            "-ar", "48000", "-ac", "1", voice], check=True)
        files = {"audio": (audio.get("file_name") or "song.mp3", open(src, "rb"))}
        cover = get_cover(d)
        if cover:
            subprocess.run(["ffmpeg", "-y", "-i", cover, "-vf",
                "scale=320:320:force_original_aspect_ratio=increase,crop=320:320",
                "-q:v", "6", thumb], check=True)
            files["thumbnail"] = ("t.jpg", open(thumb, "rb"))
        api("sendAudio", data={"chat_id": CHANNEL, "caption": caption,
            "title": title, "performer": performer,
            "duration": audio.get("duration", 0)}, files=files)
        api("sendVoice", data={"chat_id": CHANNEL}, files={"voice": open(voice, "rb")})

def main():
    updates = api("getUpdates", data={"timeout": 0})
    song = None
    confirm_to = None
    for up in updates:
        uid = up["update_id"]
        m = up.get("message")
        if not m or m.get("from", {}).get("id") != OWNER:
            if song is None:
                confirm_to = uid
            continue
        if "audio" in m:
            if song is not None:
                confirm_to = uid - 1
            song = m["audio"]
            continue
        if "text" in m and song is not None:
            try:
                process(song, m["text"])
                say("✅ فرستاده شد")
            except Exception as ex:
                say("❌ خطا: بازه رو درست بفرست (مثل 1:10-1:35) و آهنگ رو دوباره فوروارد کن.")
                print(ex)
            song = None
            confirm_to = uid
        elif song is None:
            confirm_to = uid
    if confirm_to is not None:
        api("getUpdates", data={"offset": confirm_to + 1, "timeout": 0})

main()
