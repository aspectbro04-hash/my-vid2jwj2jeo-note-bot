# =========================================
#   TELEGRAM DUMALOQ VIDEO BOT (CLEAN)
# =========================================

import telebot
from telebot import types
import sqlite3
import os
import subprocess
import static_ffmpeg
import threading
from datetime import datetime
import time

# ========= SOZLAMALAR =========
API_TOKEN = "8426868102:AAFYMpizU_BI6mvLe-VES1A9pjhq45fNoEo"
ADMIN_ID = 5153414405

static_ffmpeg.add_paths()
bot = telebot.TeleBot(API_TOKEN, parse_mode="HTML")

# ========= DATABASE =========
os.makedirs("data", exist_ok=True)
DB = "data/bot.db"


def init_db():
    with sqlite3.connect(DB) as conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS users(
            user_id INTEGER PRIMARY KEY
        )
        """)

        conn.execute("""
        CREATE TABLE IF NOT EXISTS channels(
            id TEXT PRIMARY KEY,
            url TEXT
        )
        """)


# ========= USER SAVE =========
def save_user(uid):
    with sqlite3.connect(DB) as conn:
        conn.execute("INSERT OR IGNORE INTO users VALUES(?)", (uid,))


# ========= CHANNELS =========
def get_channels():
    with sqlite3.connect(DB) as conn:
        return conn.execute("SELECT id, url FROM channels").fetchall()


def check_sub(user_id):
    missing = []

    for ch_id, url in get_channels():
        try:
            member = bot.get_chat_member(ch_id, user_id)
            if member.status in ["left", "kicked"]:
                missing.append(url)
        except:
            missing.append(url)

    return missing


def sub_keyboard(urls):
    kb = types.InlineKeyboardMarkup()

    for u in urls:
        kb.add(types.InlineKeyboardButton("📢 Obuna bo'lish", url=u))

    kb.add(types.InlineKeyboardButton("✅ Tekshirish", callback_data="check"))
    return kb


# ========= ADMIN MENU =========
def admin_kb():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("➕ Kanal", "🗑 Kanal")
    kb.add("📊 Statistika", "📢 Reklama")
    return kb


# ========= START =========
@bot.message_handler(commands=["start"])
def start(m):
    uid = m.from_user.id
    save_user(uid)

    if uid == ADMIN_ID:
        bot.send_message(uid, "👑 Admin panel", reply_markup=admin_kb())

    miss = check_sub(uid)

    if miss:
        bot.send_message(uid, "❗ Avval kanallarga obuna bo'ling",
                         reply_markup=sub_keyboard(miss))
        return

    bot.send_message(uid, "🎥 Video yubor → dumaloq qilib beraman")


# ========= SUB CHECK =========
@bot.callback_query_handler(func=lambda c: c.data == "check")
def check_callback(c):
    miss = check_sub(c.from_user.id)

    if not miss:
        bot.delete_message(c.message.chat.id, c.message.message_id)
        bot.send_message(c.message.chat.id, "✅ Rahmat, video yuboring")
    else:
        bot.answer_callback_query(c.id, "Hali obuna bo'lmadingiz!", show_alert=True)


# ========= ADMIN =========
@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and m.text == "➕ Kanal")
def add_channel(m):
    msg = bot.send_message(ADMIN_ID, "Kanal ID yubor (-100...)")
    bot.register_next_step_handler(msg, add_channel_url)


def add_channel_url(m):
    ch_id = m.text
    msg = bot.send_message(ADMIN_ID, "Link yubor")
    bot.register_next_step_handler(msg, add_channel_save, ch_id)


def add_channel_save(m, ch_id):
    with sqlite3.connect(DB) as conn:
        conn.execute("INSERT OR REPLACE INTO channels VALUES (?,?)", (ch_id, m.text))
    bot.send_message(ADMIN_ID, "✅ Qo'shildi", reply_markup=admin_kb())


@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and m.text == "🗑 Kanal")
def delete_channel(m):
    msg = bot.send_message(ADMIN_ID, "O'chirish uchun ID yubor")
    bot.register_next_step_handler(msg, delete_channel_done)


def delete_channel_done(m):
    with sqlite3.connect(DB) as conn:
        conn.execute("DELETE FROM channels WHERE id=?", (m.text,))
    bot.send_message(ADMIN_ID, "🗑 O'chirildi", reply_markup=admin_kb())


# ========= STATISTIKA =========
@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and m.text == "📊 Statistika")
def stats(m):
    with sqlite3.connect(DB) as conn:
        total = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]

    bot.send_message(ADMIN_ID, f"👥 Jami foydalanuvchi: <b>{total}</b>")


# ========= REKLAMA =========
@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and m.text == "📢 Reklama")
def ad_start(m):
    msg = bot.send_message(ADMIN_ID, "Postni yubor (text/photo/video)")
    bot.register_next_step_handler(msg, ad_send)


def ad_send(m):
    threading.Thread(target=broadcast, args=(m.chat.id, m.message_id)).start()
    bot.send_message(ADMIN_ID, "🚀 Yuborilmoqda...")


def broadcast(chat_id, msg_id):
    with sqlite3.connect(DB) as conn:
        users = conn.execute("SELECT user_id FROM users").fetchall()

    sent = 0

    for (uid,) in users:
        try:
            bot.copy_message(uid, chat_id, msg_id)
            sent += 1
            time.sleep(0.05)
        except:
            pass

    bot.send_message(ADMIN_ID, f"✅ Reklama {sent} ta odamga bordi")


# ========= VIDEO CONVERT =========
@bot.message_handler(content_types=["video"])
def video_handler(m):
    threading.Thread(target=convert, args=(m,)).start()


def convert(m):
    uid = m.from_user.id
    save_user(uid)

    if check_sub(uid):
        bot.send_message(uid, "❗ Avval /start bosib obuna bo'ling")
        return

    if m.video.file_size > 20 * 1024 * 1024:
        bot.reply_to(m, "❌ 20MB dan kichik video yubor")
        return

    in_f = f"in_{uid}.mp4"
    out_f = f"out_{uid}.mp4"

    msg = bot.reply_to(m, "⏳ Tayyorlanmoqda...")

    try:
        file = bot.get_file(m.video.file_id)
        data = bot.download_file(file.file_path)

        with open(in_f, "wb") as f:
            f.write(data)

        subprocess.run([
            "ffmpeg", "-y", "-i", in_f,
            "-t", "60",
            "-vf", "scale=640:640:force_original_aspect_ratio=increase,crop=640:640",
            out_f
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        with open(out_f, "rb") as v:
            bot.send_video_note(uid, v)

    except:
        bot.send_message(uid, "❌ Xato")

    finally:
        bot.delete_message(uid, msg.message_id)
        if os.path.exists(in_f): os.remove(in_f)
        if os.path.exists(out_f): os.remove(out_f)


# ========= RUN =========
if __name__ == "__main__":
    init_db()
    print("Bot ishga tushdi...")
    bot.infinity_polling(skip_pending=True)
