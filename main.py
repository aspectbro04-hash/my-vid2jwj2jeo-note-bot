# =========================================
#   TELEGRAM DUMALOQ VIDEO BOT (FULL PRO)
# =========================================

import telebot
from telebot import types
import sqlite3
import os
import subprocess
import static_ffmpeg
from datetime import datetime

# ========= SOZLAMALAR =========
API_TOKEN = "8426868102:AAFYMpizU_BI6mvLe-VES1A9pjhq45fNoEo
ADMIN_ID = 5153414405
LOG_GROUP_ID = -1005186355139  # maxsus guruh id

static_ffmpeg.add_paths()
bot = telebot.TeleBot(API_TOKEN)

# ========= DATABASE =========
os.makedirs("data", exist_ok=True)
DB_NAME = "data/bot_data.db"


def init_db():
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS users(
            user_id INTEGER PRIMARY KEY,
            joined TEXT,
            last_active TEXT
        )
        """)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS channels(
            id TEXT PRIMARY KEY,
            url TEXT
        )
        """)
        conn.commit()


# ========= USER SAVE =========
def save_user(uid):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute("INSERT OR IGNORE INTO users VALUES (?, ?, ?)", (uid, now, now))
        conn.execute("UPDATE users SET last_active=? WHERE user_id=?", (now, uid))
        conn.commit()


# ========= CHANNEL FUNKSIYA =========
def get_channels():
    with sqlite3.connect(DB_NAME) as conn:
        return conn.execute("SELECT id, url FROM channels").fetchall()


def is_subscribed(user_id):
    missing = []

    for ch_id, ch_url in get_channels():
        try:
            member = bot.get_chat_member(ch_id, user_id)
            if member.status in ["left", "kicked"]:
                missing.append((ch_id, ch_url))
        except:
            missing.append((ch_id, ch_url))

    return missing


# ========= KEYBOARD =========
def admin_keyboard():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("➕ Kanal qo'shish", "🗑 Kanal o'chirish")
    kb.add("📊 Statistika", "📢 Reklama")
    return kb


def subscription_keyboard(missing):
    kb = types.InlineKeyboardMarkup()
    for i, (_, url) in enumerate(missing, 1):
        kb.add(types.InlineKeyboardButton(f"{i}-kanalga a'zo bo'lish", url=url))

    kb.add(types.InlineKeyboardButton("✅ Tekshirish", callback_data="check_subs"))
    return kb


# ========= AUTO SAVE =========
@bot.message_handler(func=lambda m: True, content_types=[
    "text", "video", "photo", "audio", "document", "voice"
])
def auto_save(message):
    save_user(message.from_user.id)


# ========= ADMIN =========
@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and m.text == "➕ Kanal qo'shish")
def add_ch_start(message):
    msg = bot.send_message(ADMIN_ID, "Kanal ID yoki @username yubor:")
    bot.register_next_step_handler(msg, add_ch_url)


def add_ch_url(message):
    ch_id = message.text.strip()
    msg = bot.send_message(ADMIN_ID, "Endi kanal link yubor:")
    bot.register_next_step_handler(msg, add_ch_final, ch_id)


def add_ch_final(message, ch_id):
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute("INSERT OR REPLACE INTO channels VALUES (?, ?)", (ch_id, message.text.strip()))
    bot.send_message(ADMIN_ID, "✅ Kanal qo'shildi", reply_markup=admin_keyboard())


@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and m.text == "🗑 Kanal o'chirish")
def del_ch_start(message):
    msg = bot.send_message(ADMIN_ID, "O'chirish uchun kanal ID yubor:")
    bot.register_next_step_handler(msg, del_ch_final)


def del_ch_final(message):
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute("DELETE FROM channels WHERE id=?", (message.text.strip(),))
    bot.send_message(ADMIN_ID, "🗑 O'chirildi", reply_markup=admin_keyboard())


@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and m.text == "📊 Statistika")
def stats(message):
    with sqlite3.connect(DB_NAME) as conn:
        total = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    bot.send_message(ADMIN_ID, f"👥 Jami foydalanuvchi: {total}")


@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and m.text == "📢 Reklama")
def ads_start(message):
    msg = bot.send_message(ADMIN_ID, "Reklama yubor:")
    bot.register_next_step_handler(msg, ads_send)


def ads_send(message):
    with sqlite3.connect(DB_NAME) as conn:
        users = conn.execute("SELECT user_id FROM users").fetchall()

    sent = 0
    for (uid,) in users:
        try:
            bot.copy_message(uid, message.chat.id, message.message_id)
            sent += 1
        except:
            pass

    bot.send_message(ADMIN_ID, f"✅ {sent} ta userga yuborildi")


# ========= START (MAJBURIY OBUNA) =========
@bot.message_handler(commands=["start"])
def start_cmd(message):
    uid = message.from_user.id
    save_user(uid)

    if uid == ADMIN_ID:
        bot.send_message(uid, "Admin panel", reply_markup=admin_keyboard())
        return

    missing = is_subscribed(uid)

    if missing:
        bot.send_message(uid, "❗ Avval kanallarga a'zo bo'ling:",
                         reply_markup=subscription_keyboard(missing))
        return

    bot.send_message(uid, "🎥 Video yubor → dumaloq qilib beraman")


@bot.callback_query_handler(func=lambda c: c.data == "check_subs")
def check_subs(call):
    missing = is_subscribed(call.from_user.id)

    if not missing:
        bot.edit_message_text("✅ Endi video yuborishingiz mumkin",
                              call.message.chat.id,
                              call.message.message_id)
    else:
        bot.answer_callback_query(call.id, "Hali obuna emassiz ❌", show_alert=True)


# ========= VIDEO =========
@bot.message_handler(content_types=["video"])
def process_video(message):
    uid = message.from_user.id
    save_user(uid)

    if is_subscribed(uid):
        return bot.send_message(uid, "❗ Avval kanallarga a'zo bo'ling")

    in_file = "in.mp4"
    out_file = "out.mp4"

    status = bot.reply_to(message, "⏳ Tayyorlanmoqda...")

    try:
        file_info = bot.get_file(message.video.file_id)
        data = bot.download_file(file_info.file_path)

        with open(in_file, "wb") as f:
            f.write(data)

        subprocess.run([
            "ffmpeg", "-y", "-i", in_file,
            "-vf", "scale=640:640:force_original_aspect_ratio=increase,crop=640:640",
            out_file
        ])

        with open(out_file, "rb") as v:
            bot.send_video_note(uid, v)

        with open(out_file, "rb") as v:
            bot.send_video_note(LOG_GROUP_ID, v)

    finally:
        bot.delete_message(uid, status.message_id)
        for f in [in_file, out_file]:
            if os.path.exists(f):
                os.remove(f)


# ========= RUN =========
if __name__ == "__main__":
    init_db()
    print("Bot ishga tushdi...")
    bot.infinity_polling()