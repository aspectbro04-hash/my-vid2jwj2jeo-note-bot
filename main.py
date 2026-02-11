import telebot
from telebot import types
import os
import subprocess
import static_ffmpeg
from datetime import datetime
from pymongo import MongoClient
import csv
import time
import threading

# ==========================================
# ⚙️ ASOSIY SOZLAMALAR
# ==========================================
API_TOKEN = "8426868102:AAFYMpizU_BI6mvLe-VES1A9pjhq45fNoEo" 
MONGO_URL = "mongodb+srv://aspectbro04_db_user:Gz6C9Wf8FDcRaWzb@cluster0.d5jmju6.mongodb.net/?appName=Cluster0"
ADMIN_ID = 5153414405

static_ffmpeg.add_paths()
bot = telebot.TeleBot(API_TOKEN, parse_mode="HTML")

# ==========================================
# 🗄 DATABASE ULanish
# ==========================================
client = MongoClient(MONGO_URL)
db = client['vid2note_bot_db']
users_col = db['users']
channels_col = db['channels']
s_channels_col = db['s_channels']
settings_col = db['settings']

admin_state = {}

# ==========================================
# 👤 YORDAMCHI FUNKSIYALAR
# ==========================================
def save_user(uid, username):
    now = datetime.now()
    users_col.update_one(
        {"user_id": uid},
        {"$set": {"last_active": now, "username": username},
         "$setOnInsert": {"joined": now}},
        upsert=True
    )

def check_subscription(uid):
    # Bot faqat 'channels' bazasidagi majburiy kanallarni tekshiradi
    for ch in channels_col.find():
        try:
            chat_id = int(ch["chat_id"])
            st = bot.get_chat_member(chat_id, uid).status
            if st not in ["member", "administrator", "creator"]:
                return False
        except:
            return False
    return True

# ==========================================
# ⌨️ KEYBOARDS
# ==========================================
def admin_keyboard():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.add("➕ Kanal qo'shish", "🗑 Kanal o'chirish")
    kb.add("➕ [S] Kanal qo'shish", "🗑 [S] Kanal o'chirish")
    kb.add("📋 Kanallar ro'yxati", "📊 Statistika")
    kb.add("📢 Reklama yuborish", "📥 Bazani yuklash")
    kb.add("🔥 Hammasini tozalash", "🔙 Bekor qilish")
    return kb

def cancel_keyboard():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("🔙 Bekor qilish")
    return kb

def confirm_clear_keyboard():
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("✅ HA, Hammasini o'chir!", callback_data="confirm_clear_all"))
    kb.add(types.InlineKeyboardButton("❌ YO'Q, Bekor qil", callback_data="cancel_clear"))
    return kb

def check_sub_keyboard():
    kb = types.InlineKeyboardMarkup(row_width=1)
    # 1. Majburiy (Oddiy) kanallar
    for ch in channels_col.find():
        try:
            chat = bot.get_chat(ch["chat_id"])
            link = chat.invite_link or f"https://t.me/{chat.username}"
            kb.add(types.InlineKeyboardButton(f"➕ Obuna bo'lish", url=link))
        except: pass
    
    # 2. [S] Kanallar (Faqat havola sifatida, tekshirilmaydi)
    for sch in s_channels_col.find():
        try:
            # Agar bazada invite_link saqlangan bo'lsa o'shani, bo'lmasa get_chat orqali oladi
            link = sch.get("link")
            kb.add(types.InlineKeyboardButton(f"📩 So'rov yuborish", url=link))
        except: pass
        
    kb.add(types.InlineKeyboardButton("✅ Tekshirish", callback_data="check_sub"))
    return kb

# ==========================================
# 🏠 START & CALLBACK
# ==========================================
@bot.message_handler(commands=["start"])
def start_cmd(m):
    uid = m.from_user.id
    save_user(uid, m.from_user.username)
    if uid == ADMIN_ID:
        admin_state[uid] = None
        bot.send_message(uid, "👑 <b>Admin Panel</b>", reply_markup=admin_keyboard())
    else:
        if check_subscription(uid):
            bot.send_message(uid, "🎥 Video yuboring, men uni Video Note qilib beraman!")
        else:
            bot.send_message(uid, "🚫 Botdan foydalanish uchun kanallarga a'zo bo'ling:", reply_markup=check_sub_keyboard())

@bot.callback_query_handler(func=lambda c: True)
def callback_handler(c):
    if c.data == "check_sub":
        if check_subscription(c.from_user.id):
            bot.delete_message(c.message.chat.id, c.message.id)
            bot.send_message(c.message.chat.id, "✅ Rahmat! Endi video yuborishingiz mumkin.")
        else:
            bot.answer_callback_query(c.id, "❌ Hali hamma kanalga a'zo emassiz!", show_alert=True)
    
    elif c.data == "confirm_clear_all":
        if c.from_user.id == ADMIN_ID:
            channels_col.delete_many({})
            s_channels_col.delete_many({})
            bot.edit_message_text("🔥 Barcha kanallar bazadan o'chirildi!", c.message.chat.id, c.message.id)
    
    elif c.data == "cancel_clear":
        bot.delete_message(c.message.chat.id, c.message.id)
        bot.send_message(c.message.chat.id, "Bekor qilindi.")

# ==========================================
# 👑 ADMIN PANEL FUNKSIYALARI
# ==========================================
@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and m.text == "🔙 Bekor qilish")
def cancel(m):
    admin_state[m.from_user.id] = None
    bot.send_message(m.chat.id, "Bekor qilindi.", reply_markup=admin_keyboard())

@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and m.text == "🔥 Hammasini tozalash")
def clear_all_cmd(m):
    bot.send_message(m.chat.id, "⚠️ <b>DIQQAT!</b>\n\nBarcha kanallarni bazadan butunlay o'chirib tashlamoqchimisiz?", 
                     reply_markup=confirm_clear_keyboard(), parse_mode="HTML")

@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and m.text == "📊 Statistika")
def stats(m):
    count = users_col.count_documents({})
    bot.send_message(m.chat.id, f"👥 Jami foydalanuvchilar: {count}")

@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and m.text == "📋 Kanallar ro'yxati")
def list_ch(m):
    text = "<b>Majburiy kanallar (Tekshiriladi):</b>\n"
    for c in channels_col.find(): text += f"<code>{c['chat_id']}</code>\n"
    text += "\n<b>[S] Kanallar (Faqat reklama):</b>\n"
    for c in s_channels_col.find(): text += f"🔗 {c['link']}\n"
    bot.send_message(m.chat.id, text or "Ro'yxat bo'sh")

@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and m.text in ["➕ Kanal qo'shish", "➕ [S] Kanal qo'shish", "🗑 Kanal o'chirish", "🗑 [S] Kanal o'chirish", "📢 Reklama yuborish"])
def admin_actions(m):
    txt = m.text
    uid = m.from_user.id
    if txt == "➕ Kanal qo'shish": 
        admin_state[uid] = "add_ch"
        bot.send_message(m.chat.id, "Kanal ID raqamini yuboring:", reply_markup=cancel_keyboard())
    elif txt == "➕ [S] Kanal qo'shish": 
        admin_state[uid] = "add_sch"
        bot.send_message(m.chat.id, "Kanal havolasini (linkini) yuboring:", reply_markup=cancel_keyboard())
    elif txt == "🗑 Kanal o'chirish": 
        admin_state[uid] = "del_ch"
        bot.send_message(m.chat.id, "O'chiriladigan kanal ID sini yuboring:", reply_markup=cancel_keyboard())
    elif txt == "🗑 [S] Kanal o'chirish": 
        admin_state[uid] = "del_sch"
        bot.send_message(m.chat.id, "O'chiriladigan kanal linkini yuboring:", reply_markup=cancel_keyboard())
    elif txt == "📢 Reklama yuborish": 
        admin_state[uid] = "reklama"
        bot.send_message(m.chat.id, "Reklama xabarini yuboring:", reply_markup=cancel_keyboard())

@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and admin_state.get(m.from_user.id))
def handle_admin_input(m):
    uid = m.from_user.id
    state = admin_state[uid]
    text = m.text.strip()
    
    try:
        if state == "add_ch":
            channels_col.update_one({"chat_id": int(text)}, {"$set": {"added": True}}, upsert=True)
            bot.send_message(m.chat.id, "✅ Majburiy kanal qo'shildi")
        elif state == "add_sch":
            s_channels_col.update_one({"link": text}, {"$set": {"added": True}}, upsert=True)
            bot.send_message(m.chat.id, "✅ [S] Kanal linki qo'shildi")
        elif state == "del_ch":
            channels_col.delete_many({"chat_id": {"$in": [int(text), text]}})
            bot.send_message(m.chat.id, "🗑 Kanal o'chirildi")
        elif state == "del_sch":
            s_channels_col.delete_one({"link": text})
            bot.send_message(m.chat.id, "🗑 [S] Kanal linki o'chirildi")
        elif state == "reklama":
            def send_rec():
                for u in users_col.find():
                    try: bot.copy_message(u['user_id'], m.chat.id, m.message_id); time.sleep(0.05)
                    except: pass
                bot.send_message(m.chat.id, "🏁 Reklama tugadi")
            threading.Thread(target=send_rec).start()
            bot.send_message(m.chat.id, "🚀 Reklama boshlandi")
    except:
        bot.send_message(m.chat.id, "❌ Xatolik yuz berdi. Ma'lumotni to'g'ri yuborganingizga ishonch hosil qiling.")
    
    admin_state[uid] = None
    bot.send_message(m.chat.id, "Admin Panel", reply_markup=admin_keyboard())

# ==========================================
# 🎥 VIDEO PROCESS
# ==========================================
@bot.message_handler(content_types=["video"])
def process_video(m):
    uid = m.from_user.id
    if not check_subscription(uid):
        return bot.send_message(uid, "🚫 Obuna bo'ling", reply_markup=check_sub_keyboard())

    msg = bot.reply_to(m, "⏳ Tayyorlanmoqda...")
    in_f, out_f = f"i_{uid}.mp4", f"o_{uid}.mp4"

    try:
        file_info = bot.get_file(m.video.file_id)
        with open(in_f, "wb") as f: f.write(bot.download_file(file_info.file_path))

        subprocess.run([
            "ffmpeg", "-y", "-i", in_f,
            "-vf", "scale=640:640:force_original_aspect_ratio=increase,crop=640:640",
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "28", out_f
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        with open(out_f, "rb") as v: bot.send_video_note(uid, v)
        bot.delete_message(uid, msg.message_id)
    except:
        bot.send_message(uid, "❌ Xatolik yuz berdi")
    finally:
        for f in [in_f, out_f]:
            if os.path.exists(f): os.remove(f)

print("🚀 Bot ishga tushdi...")
bot.infinity_polling(allowed_updates=["message", "callback_query"])
