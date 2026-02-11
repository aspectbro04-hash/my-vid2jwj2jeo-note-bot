import telebot
from telebot import types
import os
import subprocess
import static_ffmpeg
from datetime import datetime
from pymongo import MongoClient
import csv
import time

# ==========================================
# ⚙️ ASOSIY SOZLAMALAR
# ==========================================
API_TOKEN = "TOKENINGIZ"
MONGO_URL = "MONGO_URLINGIZ"
ADMIN_ID = 5153414405

static_ffmpeg.add_paths()

bot = telebot.TeleBot(API_TOKEN, parse_mode="HTML")

# ==========================================
# 🗄 DATABASE
# ==========================================
client = MongoClient(MONGO_URL)
db = client['vid2note_bot_db']

users_col = db['users']
channels_col = db['channels']
s_channels_col = db['s_channels']
requests_col = db['requests']
settings_col = db['settings']

print("✅ DB ulandi")

# ==========================================
# YORDAMCHI
# ==========================================
def save_user(uid, username):
    now = datetime.now()
    users_col.update_one(
        {"user_id": uid},
        {"$set": {"last_active": now, "username": username},
         "$setOnInsert": {"joined": now}},
        upsert=True
    )

def get_log_group():
    res = settings_col.find_one({"key": "log_group"})
    return res["value"] if res else None


# ==========================================
# OBUNA TEKSHIRISH
# ==========================================
def check_subscription(uid):

    for ch in channels_col.find():
        try:
            st = bot.get_chat_member(ch["chat_id"], uid).status
            if st not in ["member","administrator","creator"]:
                return False
        except:
            return False

    for sch in s_channels_col.find():
        if not requests_col.find_one({"user_id": uid, "chat_id": str(sch["chat_id"])}):
            return False

    return True


# ==========================================
# JOIN REQUEST
# ==========================================
@bot.chat_join_request_handler()
def join_req(u):
    requests_col.update_one(
        {"user_id": u.from_user.id, "chat_id": str(u.chat.id)},
        {"$set": {"date": datetime.now()}},
        upsert=True
    )
    try:
        bot.send_message(u.from_user.id, "✅ So'rov qabul qilindi!")
    except:
        pass


# ==========================================
# KEYBOARDS
# ==========================================
def admin_keyboard():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("➕ Kanal qo'shish", "🗑 Kanal o'chirish")
    kb.add("➕ [S] Kanal qo'shish", "🗑 [S] Kanal o'chirish")
    kb.add("📋 Kanallar ro'yxati", "📊 Statistika")
    kb.add("🔗 Log guruhini sozlash", "📥 Bazani yuklash")
    kb.add("📢 Reklama yuborish")
    return kb

def check_sub_keyboard():
    kb = types.InlineKeyboardMarkup()

    for ch in channels_col.find():
        chat = bot.get_chat(ch["chat_id"])
        link = chat.invite_link or f"https://t.me/{chat.username}"
        kb.add(types.InlineKeyboardButton("➕ Obuna", url=link))

    for sch in s_channels_col.find():
        chat = bot.get_chat(sch["chat_id"])
        link = chat.invite_link or f"https://t.me/{chat.username}"
        kb.add(types.InlineKeyboardButton("📩 So'rov", url=link))

    kb.add(types.InlineKeyboardButton("✅ Tekshirish", callback_data="check_sub"))
    return kb


# ==========================================
# START
# ==========================================
@bot.message_handler(commands=["start"])
def start_cmd(m):
    uid = m.from_user.id
    save_user(uid, m.from_user.username)

    if uid == ADMIN_ID:
        bot.send_message(uid, "👑 Admin Panel", reply_markup=admin_keyboard())
    else:
        if check_subscription(uid):
            bot.send_message(uid, "🎥 Video yuboring")
        else:
            bot.send_message(uid, "🚫 Kanallarga qo'shiling", reply_markup=check_sub_keyboard())


@bot.callback_query_handler(func=lambda c: c.data == "check_sub")
def check_btn(c):
    if check_subscription(c.from_user.id):
        bot.edit_message_text("✅ Rahmat!", c.message.chat.id, c.message.id)
    else:
        bot.answer_callback_query(c.id, "❌ Obuna bo'lmagansiz", show_alert=True)


# ==========================================
# ADMIN FUNKSIYALAR
# ==========================================
@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and m.text == "📊 Statistika")
def stats(m):
    bot.send_message(ADMIN_ID, f"👥 Users: {users_col.count_documents({})}")


@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and m.text == "📥 Bazani yuklash")
def export_users(m):

    filename = "users.csv"

    with open(filename, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["user_id","username","joined"])
        for u in users_col.find():
            w.writerow([u.get("user_id"), u.get("username"), u.get("joined")])

    bot.send_document(ADMIN_ID, open(filename,"rb"))
    os.remove(filename)


# ==========================================
# VIDEO PROCESS (tez)
# ==========================================
@bot.message_handler(content_types=["video"])
def process_video(m):

    uid = m.from_user.id

    if not check_subscription(uid):
        return bot.send_message(uid, "🚫 Obuna bo'ling", reply_markup=check_sub_keyboard())

    in_f = f"{uid}.mp4"
    out_f = f"{uid}_o.mp4"

    msg = bot.reply_to(m, "⏳ Tayyorlanmoqda...")

    try:
        file = bot.get_file(m.video.file_id)
        data = bot.download_file(file.file_path)

        with open(in_f, "wb") as f:
            f.write(data)

        subprocess.run([
            "ffmpeg","-y","-i",in_f,
            "-vf","scale=640:640:force_original_aspect_ratio=increase,crop=640:640",
            "-preset","veryfast","-crf","28",
            out_f
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        with open(out_f,"rb") as v:
            bot.send_video_note(uid,v)

    finally:
        bot.delete_message(uid, msg.message_id)
        if os.path.exists(in_f): os.remove(in_f)
        if os.path.exists(out_f): os.remove(out_f)


# ==========================================
print("🚀 Bot ishga tushdi...")
bot.infinity_polling(allowed_updates=["message","callback_query","chat_join_request"]
