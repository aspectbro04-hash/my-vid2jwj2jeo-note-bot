# =========================================
#   TELEGRAM DUMALOQ VIDEO BOT (SAFE MODE)
# =========================================

import telebot
from telebot import types
import sqlite3
import os
import subprocess
import static_ffmpeg
from datetime import datetime
import time
import threading

# ========= SOZLAMALAR =========
API_TOKEN = "8426868102:AAFYMpizU_BI6mvLe-VES1A9pjhq45fNoEo"
ADMIN_ID = 5153414405       # Sizning ID
LOG_GROUP_ID = 3887837530   # Loglar keladigan joy (Sizning ID)

# FFmpeg yo'lini to'g'irlash
static_ffmpeg.add_paths()
bot = telebot.TeleBot(API_TOKEN, parse_mode="HTML")

# ========= DATABASE =========
os.makedirs("data", exist_ok=True)
DB_NAME = "data/bot_data.db"

def init_db():
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS users(
            user_id INTEGER PRIMARY KEY,
            username TEXT,
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
def save_user(uid, username):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    username = f"@{username}" if username else "No Username"
    try:
        with sqlite3.connect(DB_NAME) as conn:
            conn.execute("INSERT OR IGNORE INTO users VALUES (?, ?, ?, ?)", (uid, username, now, now))
            conn.execute("UPDATE users SET last_active=?, username=? WHERE user_id=?", (now, username, uid))
            conn.commit()
    except Exception as e:
        print(f"DB Error: {e}")

# ========= CHANNEL CHECK =========
def get_channels():
    with sqlite3.connect(DB_NAME) as conn:
        return conn.execute("SELECT id, url FROM channels").fetchall()

def is_subscribed(user_id):
    missing = []
    channels = get_channels()
    for ch_id, ch_url in channels:
        try:
            member = bot.get_chat_member(ch_id, user_id)
            if member.status in ["left", "kicked"]:
                missing.append((ch_id, ch_url))
        except Exception:
            # Agar bot kanalda admin bo'lmasa ham qo'shishni so'raymiz
            missing.append((ch_id, ch_url))
    return missing

# ========= KEYBOARDS =========
def admin_keyboard():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("➕ Kanal qo'shish", "🗑 Kanal o'chirish")
    kb.add("📊 Statistika", "📢 Reklama")
    kb.add("⬅️ Asosiy menyu") 
    return kb

def subscription_keyboard(missing):
    kb = types.InlineKeyboardMarkup()
    for i, (_, url) in enumerate(missing, 1):
        kb.add(types.InlineKeyboardButton(f"{i}-kanalga a'zo bo'lish", url=url))
    kb.add(types.InlineKeyboardButton("✅ Tekshirish", callback_data="check_subs"))
    return kb

# ========= ADMIN HANDLERS =========
@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and m.text == "➕ Kanal qo'shish")
def add_ch_start(message):
    msg = bot.send_message(ADMIN_ID, "Kanal ID raqamini yuboring (masalan: -100...):")
    bot.register_next_step_handler(msg, add_ch_url)

def add_ch_url(message):
    ch_id = message.text.strip()
    msg = bot.send_message(ADMIN_ID, "Endi kanal linkini yuboring:")
    bot.register_next_step_handler(msg, add_ch_final, ch_id)

def add_ch_final(message, ch_id):
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute("INSERT OR REPLACE INTO channels VALUES (?, ?)", (ch_id, message.text.strip()))
    bot.send_message(ADMIN_ID, "✅ Kanal qo'shildi", reply_markup=admin_keyboard())

@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and m.text == "🗑 Kanal o'chirish")
def del_ch_start(message):
    msg = bot.send_message(ADMIN_ID, "O'chirish uchun kanal ID raqamini yuboring:")
    bot.register_next_step_handler(msg, del_ch_final)

def del_ch_final(message):
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute("DELETE FROM channels WHERE id=?", (message.text.strip(),))
    bot.send_message(ADMIN_ID, "🗑 Kanal o'chirildi", reply_markup=admin_keyboard())

@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and m.text == "📊 Statistika")
def stats(message):
    with sqlite3.connect(DB_NAME) as conn:
        total = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        active_today = conn.execute("SELECT COUNT(*) FROM users WHERE last_active LIKE ?", (f"{datetime.now().strftime('%Y-%m-%d')}%",)).fetchone()[0]
    bot.send_message(ADMIN_ID, f"📊 <b>Statistika:</b>\n\n👥 Jami: {total}\n📅 Bugun aktiv: {active_today}")

@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and m.text == "📢 Reklama")
def ads_start(message):
    msg = bot.send_message(ADMIN_ID, "Reklama postini yuboring:")
    bot.register_next_step_handler(msg, ads_send)

def ads_send(message):
    threading.Thread(target=start_broadcast, args=(message.chat.id, message.message_id)).start()
    bot.send_message(ADMIN_ID, "✅ Reklama yuborish boshlandi...")

def start_broadcast(chat_id, message_id):
    with sqlite3.connect(DB_NAME) as conn:
        users = conn.execute("SELECT user_id FROM users").fetchall()
    
    sent = 0
    for (uid,) in users:
        try:
            bot.copy_message(uid, chat_id, message_id)
            sent += 1
            time.sleep(0.05) # Spamdan himoya
        except:
            pass
    bot.send_message(ADMIN_ID, f"📢 Reklama tugadi. {sent} kishiga bordi.")

@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and m.text == "⬅️ Asosiy menyu")
def admin_exit(message):
    bot.send_message(message.chat.id, "Oddiy rejim.", reply_markup=types.ReplyKeyboardRemove())

# ========= START COMMAND =========
@bot.message_handler(commands=["start"])
def start_cmd(message):
    uid = message.from_user.id
    save_user(uid, message.from_user.username)

    if uid == ADMIN_ID:
        bot.send_message(uid, "👑 Admin panel", reply_markup=admin_keyboard())
    
    missing = is_subscribed(uid)
    if missing:
        bot.send_message(uid, "❗ Botdan foydalanish uchun kanallarga a'zo bo'ling:",
                         reply_markup=subscription_keyboard(missing))
        return

    bot.send_message(uid, "👋 Salom! Menga <b>video</b> yuboring, men uni <b>dumaloq video</b> qilib beraman.")

@bot.callback_query_handler(func=lambda c: c.data == "check_subs")
def check_subs(call):
    missing = is_subscribed(call.from_user.id)
    if not missing:
        bot.delete_message(call.message.chat.id, call.message.message_id)
        bot.send_message(call.message.chat.id, "✅ Rahmat! Endi video yuboring.")
    else:
        bot.answer_callback_query(call.id, "❌ Hali a'zo bo'lmadingiz!", show_alert=True)

# ========= VIDEO PROCESSING (SAFE MODE) =========
@bot.message_handler(content_types=["video"])
def process_video_handler(message):
    # Bot qotib qolmasligi uchun alohida oqimda ishlatamiz
    threading.Thread(target=convert_video_thread, args=(message,)).start()

def convert_video_thread(message):
    uid = message.from_user.id
    username = message.from_user.username if message.from_user.username else "NoUsername"
    name = message.from_user.first_name
    
    save_user(uid, username)

    # Obuna tekshirish
    if is_subscribed(uid):
        bot.send_message(uid, "❗ Avval kanallarga a'zo bo'ling /start")
        return
    
    # Katta videolarni bloklash (20MB)
    if message.video.file_size > 20 * 1024 * 1024:
        bot.reply_to(message, "⚠️ Video hajmi juda katta! 20MB dan kichik video yuboring.")
        return

    # Unikal fayl nomlari
    timestamp = int(datetime.now().timestamp())
    in_file = f"in_{uid}_{timestamp}.mp4"
    out_file = f"out_{uid}_{timestamp}.mp4"

    status_msg = bot.reply_to(message, "⏳ Tayyorlanmoqda...")

    try:
        file_info = bot.get_file(message.video.file_id)
        data = bot.download_file(file_info.file_path)

        with open(in_file, "wb") as f:
            f.write(data)

        # FFMPEG: 60 sek limit, Crop (Qirqish), Square (Kvadrat)
        cmd = [
            "ffmpeg", "-y", "-i", in_file,
            "-t", "60", 
            "-vf", "scale=640:640:force_original_aspect_ratio=increase,crop=640:640",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "26",
            "-c:a", "aac", "-b:a", "128k", 
            out_file
        ]
        
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        if os.path.exists(out_file):
            # 1. Foydalanuvchiga videoni yuboramiz
            with open(out_file, "rb") as v:
                bot.send_video_note(uid, v)
            
            # 2. XAVFSIZ LOG (Sizga faqat xabar boradi, video emas)
            if uid != LOG_GROUP_ID:
                try:
                    caption = (
                        f"🚀 <b>Yangi foydalanish:</b>\n"
                        f"👤 Ism: {name}\n"
                        f"🔗 User: @{username}\n"
                        f"🆔 ID: <code>{uid}</code>"
                    )
                    bot.send_message(LOG_GROUP_ID, caption)
                except:
                    pass
        else:
            bot.send_message(uid, "❌ Konvertatsiya xatosi.")

    except Exception as e:
        print(f"Error: {e}")
        bot.send_message(uid, "❌ Tizim xatosi.")
    
    finally:
        # Fayllarni albatta o'chiramiz
        try:
            bot.delete_message(uid, status_msg.message_id)
            if os.path.exists(in_file): os.remove(in_file)
            if os.path.exists(out_file): os.remove(out_file)
        except:
            pass

# ========= RUN =========
if __name__ == "__main__":
    init_db()
    print("Bot ishga tushdi...")
    try:
        bot.infinity_polling(skip_pending=True)
    except Exception as e:
        print(f"Bot to'xtadi: {e}")
