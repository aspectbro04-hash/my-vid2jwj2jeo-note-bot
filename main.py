import telebot
from telebot import types
import os
import subprocess
import static_ffmpeg
from datetime import datetime
from pymongo import MongoClient
import pandas as pd
import uuid

# ==========================================
# 1. SOZLAMALAR (SECRET O'ZGARMADI)
# ==========================================
API_TOKEN = "7917719602:AAH96v6T8D-Nsc7Sj-w0GvP7_j9_6y9Q8mQ"
MONGO_URL = "mongodb+srv://aspectbro04_db_user:Gz6C9Wf8FDcRaWzb@cluster0.d5jmju6.mongodb.net/?appName=Cluster0"
ADMIN_ID = 5153414405
LOG_GROUP_ID = -1003494598525

static_ffmpeg.add_paths()
bot = telebot.TeleBot(API_TOKEN, parse_mode="HTML")

# ==========================================
# 2. MONGODB
# ==========================================
client = MongoClient(MONGO_URL)
db = client["vid2note_bot_db"]
users_col = db["users"]


def save_user(uid, username):
    username = username or "NoUsername"
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    users_col.update_one(
        {"user_id": uid},
        {
            "$set": {
                "last_active": now,
                "username": username
            },
            "$setOnInsert": {"joined": now}
        },
        upsert=True
    )


# ==========================================
# 3. ADMIN PANEL
# ==========================================
def admin_keyboard():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("📊 Statistika", "📥 Bazani yuklash")
    return kb


@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and m.text == "📥 Bazani yuklash")
def export_database(message):
    status = bot.send_message(ADMIN_ID, "⏳ Baza tayyorlanmoqda...")

    try:
        users = list(users_col.find({}, {"_id": 0}))

        if not users:
            bot.send_message(ADMIN_ID, "Baza bo'sh!")
            return

        df = pd.DataFrame(users)

        file_name = f"users_backup_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
        df.to_excel(file_name, index=False)

        with open(file_name, "rb") as f:
            bot.send_document(ADMIN_ID, f, caption="💾 Backup tayyor!")

        os.remove(file_name)

    except Exception as e:
        bot.send_message(ADMIN_ID, f"❌ Xato: {e}")

    finally:
        bot.delete_message(ADMIN_ID, status.message_id)


# ==========================================
# 4. START
# ==========================================
@bot.message_handler(commands=["start"])
def start_cmd(message):
    uid = message.from_user.id
    save_user(uid, message.from_user.username)

    if uid == ADMIN_ID:
        bot.send_message(uid, "👑 Admin panel", reply_markup=admin_keyboard())
    else:
        bot.send_message(uid, "🎥 Video yuboring — dumaloq qilib beraman!")


# ==========================================
# 5. STATISTIKA
# ==========================================
@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and m.text == "📊 Statistika")
def stats(message):
    total = users_col.count_documents({})
    bot.send_message(ADMIN_ID, f"👥 Jami foydalanuvchilar: <b>{total}</b>")


# ==========================================
# 6. VIDEO PROCESSOR
# ==========================================
@bot.message_handler(content_types=["video"])
def process_video(message):
    uid = message.from_user.id
    username = message.from_user.username or "NoUsername"
    save_user(uid, username)

    unique = str(uuid.uuid4())[:8]
    in_file = f"in_{unique}.mp4"
    out_file = f"out_{unique}.mp4"

    status = bot.reply_to(message, "⏳ Ishlov berilmoqda...")

    try:
        file_info = bot.get_file(message.video.file_id)
        data = bot.download_file(file_info.file_path)

        with open(in_file, "wb") as f:
            f.write(data)

        cmd = [
            "ffmpeg", "-y",
            "-i", in_file,
            "-vf", "scale=640:640:force_original_aspect_ratio=increase,crop=640:640",
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            out_file
        ]

        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

        with open(out_file, "rb") as v:
            bot.send_video_note(uid, v)

        with open(out_file, "rb") as v:
            bot.send_message(LOG_GROUP_ID, f"👤 @{username} | ID: {uid}")
            bot.send_video_note(LOG_GROUP_ID, v)

    except Exception as e:
        bot.send_message(uid, f"❌ Xato: {e}")

    finally:
        bot.delete_message(uid, status.message_id)

        if os.path.exists(in_file):
            os.remove(in_file)
        if os.path.exists(out_file):
            os.remove(out_file)


# ==========================================
# 7. RUN
# ==========================================
if __name__ == "__main__":
    print("Bot ishga tushdi...")
    while True:
        try:
            bot.infinity_polling(timeout=60, long_polling_timeout=30)
        except Exception as e:
            print("Restart:", e)
