import os, re, subprocess, tempfile, requests

TOKEN = os.environ["BOT_TOKEN"]
CHANNEL = os.environ["CHANNEL"]

# آیدی خودت (از Secret) + آیدی ادمین
OWNERS = {int(os.environ["OWNER_ID"].split(",")[0])}
OWNERS |= {268366064}

API = f"https://api.telegram.org/bot{TOKEN}"
FILE_API = f"https://api.telegram.org/file/bot{TOKEN}"

FOOTER = "Channel: @music_chet666"
DEFAULT_TOP = "{title}"

def api(method, **kw):
    r = requests.post(f"{API}/{method}", timeout=300, **kw)
    r.raise_for_status()
    return r.json()["result"]

def say(user, text):
    try:
        api("sendMessage", data={"chat_id": user, "text": text})
    except Exception as ex:
        print("say failed:", ex)

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
    print("pending updates:", len(updates))
    pending = {}   # آیدی فرستنده -> آهنگی که منتظر پیام بازه است
    last_id = None
    for up in updates:
        last_id = up["update_id"]
        m = up.get("message")
        if not m:
            continue
        user = m.get("from", {}).get("id")
        if user not in OWNERS:
            continue
        if "audio" in m:
            pending[user] = m["audio"]
        elif "text" in m and user in pending:
            audio = pending.pop(user)
            try:
                process(audio, m["text"])
                say(user, "✅ فرستاده شد")
            except Exception as ex:
                say(user, "❌ خطا: بازه رو درست بفرست (مثل 1:10-1:35) و آهنگ رو دوباره فوروارد کن.")
                print("error:", ex)
    for user in pending:
        say(user, "⚠️ آهنگت رسید ولی پیام بازه نرسید. آهنگ رو دوباره بفرست و بعدش بازه رو بنویس.")
    if last_id is not None:
        api("getUpdates", data={"offset": last_id + 1, "timeout": 0})

main()
