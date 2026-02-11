import telebot
from telebot import types
import os
import subprocess
import static_ffmpeg
from datetime import datetime
from pymongo import MongoClient
import pandas as pd
import time

# ==========================================
# ⚙️ 1. ASOSIY SOZLAMALAR
# ==========================================
API_TOKEN = "8426868102:AAFYMpizU_BI6mvLe-VES1A9pjhq45fNoEo"
MONGO_URL = "mongodb+srv://aspectbro04_db_user:Gz6C9Wf8FDcRaWzb@cluster0.d5jmju6.mongodb.net/?appName=Cluster0"
ADMIN_ID = 5153414405

static_ffmpeg.add_paths()
bot = telebot.TeleBot(API_TOKEN)

client = MongoClient(MONGO_URL, tlsAllowInvalidCertificates=True)
db = client['vid2note_bot_db']

users_col = db['users']       
channels_col = db['channels'] 
s_channels_col = db['s_channels'] # So'rov talab qilinadigan kanallar
requests_col = db['requests']     # So'rov yuborganlar bazasi
settings_col = db['settings'] 

# --- Yordamchi funksiyalar ---
def save_user(uid, username):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    users_col.update_one(
        {"user_id": uid},
        {"$set": {"last_active": now, "username": username}, 
         "$setOnInsert": {"joined": now}},
        upsert=True
    )

def check_subscription(user_id):
    """A'zolik va So'rovni tekshirish"""
    # 1. Oddiy majburiy obuna kanallari
    channels = list(channels_col.find())
    for ch in channels:
        try:
            status = bot.get_chat_member(ch['chat_id'], user_id).status
            if status not in ['creator', 'administrator', 'member']:
                return False
        except: continue

    # 2. So'rov yuborilishi shart bo'lgan kanallar
    s_channels = list(s_channels_col.find())
    for sch in s_channels:
        # Agar foydalanuvchi bazada bo'lmasa (so'rov yubormagan bo'lsa)
        is_requested = requests_col.find_one({"user_id": user_id, "chat_id": str(sch['chat_id'])})
        if not is_requested:
            # Qo'shimcha tekshiruv: balki so'rov yubormasdan oldin a'zo bo'lgandir
            try:
                status = bot.get_chat_member(sch['chat_id'], user_id).status
                if status not in ['creator', 'administrator', 'member']:
                    return False
            except: return False
    return True

# ==========================================
# 📩 SO'ROVLARNI TUTISH (JOIN REQUEST)
# ==========================================
@bot.chat_join_request_handler()
def handle_join_request(update: types.ChatJoinRequest):
    user_id = update.from_user.id
    chat_id = str(update.chat.id)
    
    # So'rov yuborganini bazaga saqlaymiz
    requests_col.update_one(
        {"user_id": user_id, "chat_id": chat_id},
        {"$set": {"status": "requested", "date": datetime.now()}},
        upsert=True
    )
    # Foydalanuvchiga bildirishnoma (ixtiyoriy)
    try:
        bot.send_message(user_id, "✅ Kanalga qo'shilish so'rovingiz qabul qilindi. Endi botdan foydalanishingiz mumkin!")
    except: pass

# ==========================================
# 🖥 3. ADMIN PANEL
# ==========================================
def admin_keyboard():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.add("➕ Kanal qo'shish", "🗑 Kanal o'chirish", "📋 Kanallar ro'yxati")
    kb.add("➕ [S] Kanal qo'shish", "🗑 [S] Kanal o'chirish", "📋 [S] Kanallar ro'yxati")
    kb.add("📊 Statistika", "📢 Reklama yuborish")
    kb.add("🔗 Log guruhini sozlash", "📥 Bazani yuklash")
    return kb

def check_sub_keyboard():
    kb = types.InlineKeyboardMarkup()
    # Oddiy kanallar
    for ch in channels_col.find():
        try:
            chat = bot.get_chat(ch['chat_id'])
            kb.add(types.InlineKeyboardButton(f"Obuna bo'lish ➕", url=chat.invite_link or f"https://t.me/{chat.username}"))
        except: continue
    # So'rovli kanallar
    for sch in s_channels_col.find():
        try:
            chat = bot.get_chat(sch['chat_id'])
            # So'rovli havola uchun admin panelda link yaratilgan bo'lishi kerak
            kb.add(types.InlineKeyboardButton(f"Qo'shilishni so'rash 📩", url=chat.invite_link or f"https://t.me/{chat.username}"))
        except: continue
    kb.add(types.InlineKeyboardButton("✅ Tasdiqlash", callback_data="check_sub"))
    return kb

# ==========================================
# 🚀 BUYRUQLAR
# ==========================================
@bot.message_handler(commands=["start"])
def start_cmd(message):
    uid = message.from_user.id
    save_user(uid, message.from_user.username)
    
    if uid == ADMIN_ID:
        bot.send_message(uid, "👑 Admin Panel", reply_markup=admin_keyboard())
    else:
        if check_subscription(uid):
            bot.send_message(uid, "👋 Salom! Video yuboring, dumaloq qilib beraman!")
        else:
            bot.send_message(uid, "🚫 Botdan foydalanish uchun kanallarga a'zo bo'ling yoki qo'shilish so'rovini yuboring:", reply_markup=check_sub_keyboard())

# --- [S] Kanal Boshqaruvi ---
@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and "[S] Kanal" in m.text)
def s_channel_manager(message):
    if "qo'shish" in message.text:
        msg = bot.send_message(ADMIN_ID, "🆔 [S] Kanal ID sini yuboring (Masalan: -100...):")
        bot.register_next_step_handler(msg, save_s_channel)
    elif "o'chirish" in message.text:
        msg = bot.send_message(ADMIN_ID, "🗑 O'chirmoqchi bo'lgan [S] kanal ID sini yuboring:")
        bot.register_next_step_handler(msg, lambda m: [s_channels_col.delete_one({"chat_id": m.text}), bot.send_message(ADMIN_ID, "✅ [S] Kanal o'chirildi.")])
    elif "ro'yxati" in message.text:
        ch_list = list(s_channels_col.find())
        text = "📋 <b>So'rovli kanallar:</b>\n\n"
        for c in ch_list: text += f"🔹 <code>{c['chat_id']}</code>\n"
        bot.send_message(ADMIN_ID, text if ch_list else "Bo'sh", parse_mode="HTML")

def save_s_channel(message):
    try:
        s_channels_col.insert_one({"chat_id": message.text})
        bot.send_message(ADMIN_ID, "✅ [S] Kanal muvaffaqiyatli qo'shildi!")
    except Exception as e: bot.send_message(ADMIN_ID, f"❌ Xato: {e}")

# Callback va boshqa funksiyalar (Original koddagidek qoladi...)
@bot.callback_query_handler(func=lambda call: call.data == "check_sub")
def callback_check(call):
    if check_subscription(call.from_user.id):
        bot.delete_message(call.message.chat.id, call.message.message_id)
        bot.send_message(call.message.chat.id, "✅ Rahmat! Endi video yuborishingiz mumkin.")
    else:
        bot.answer_callback_query(call.id, "❌ Hali so'rov yubormadingiz yoki obuna bo'lmadingiz!", show_alert=True)

# Video ishlov berish qismi (Original kod bilan bir xil, check_subscription yangilangan versiyada ishlaydi)
@bot.message_handler(content_types=["video"])
def process_video_note(message):
    uid = message.from_user.id
    if not check_subscription(uid):
        return bot.send_message(uid, "🚫 Iltimos, avval kanallarga obuna bo'ling yoki so'rov yuboring!", reply_markup=check_sub_keyboard())
    
    # ... (Original video ishlov berish kodi shu yerda davom etadi)
    in_file = f"in_{uid}.mp4"
    out_file = f"out_{uid}.mp4"
    status_msg = bot.reply_to(message, "⏳ <b>Videongiz dumaloq shaklga keltirilmoqda...</b>", parse_mode="HTML")
    
    try:
        file_info = bot.get_file(message.video.file_id)
        data = bot.download_file(file_info.file_path)
        with open(in_file, "wb") as f: f.write(data)
        
        subprocess.run([
            "ffmpeg", "-y", "-i", in_file,
            "-vf", "scale=640:640:force_original_aspect_ratio=increase,crop=640:640",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", out_file
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        with open(out_file, "rb") as v:
            bot.send_video_note(uid, v)
    except Exception as e:
        bot.send_message(uid, f"❌ Xatolik: {e}")
    finally:
        bot.delete_message(uid, status_msg.message_id)
        if os.path.exists(in_file): os.remove(in_file)
        if os.path.exists(out_file): os.remove(out_file)

if __name__ == "__main__":
    bot.infinity_polling(allowed_updates=['message', 'callback_query', 'chat_join_request'])
