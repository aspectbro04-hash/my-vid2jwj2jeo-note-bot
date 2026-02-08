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

# FFmpeg ni sozlash
static_ffmpeg.add_paths()
bot = telebot.TeleBot(API_TOKEN)

# ==========================================
# 🗄 2. BAZA BILAN ULANISH
# ==========================================
# tlsAllowInvalidCertificates=True -> SSL xatosini oldini oladi
client = MongoClient(MONGO_URL, tlsAllowInvalidCertificates=True)
db = client['vid2note_bot_db']

users_col = db['users']       # Foydalanuvchilar
channels_col = db['channels'] # Majburiy obuna kanallari
settings_col = db['settings'] # Sozlamalar (Log guruh ID)

# --- Yordamchi funksiyalar ---
def save_user(uid, username):
    """Foydalanuvchini bazaga saqlash"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    users_col.update_one(
        {"user_id": uid},
        {"$set": {"last_active": now, "username": username}, 
         "$setOnInsert": {"joined": now}},
        upsert=True
    )

def get_log_group():
    """Log guruh ID sini olish"""
    res = settings_col.find_one({"key": "log_group"})
    return res['value'] if res else None

def check_subscription(user_id):
    """Foydalanuvchi kanallarga a'zo ekanligini tekshirish"""
    channels = list(channels_col.find())
    if not channels: return True # Agar kanallar bo'lmasa, ruxsat beramiz
    
    not_joined = []
    for ch in channels:
        try:
            status = bot.get_chat_member(ch['chat_id'], user_id).status
            if status not in ['creator', 'administrator', 'member']:
                not_joined.append(ch['chat_id'])
        except:
            # Agar bot kanalda admin bo'lmasa yoki xato bo'lsa, o'tkazib yuboramiz
            continue
    return len(not_joined) == 0

# ==========================================
# 🖥 3. ADMIN PANEL VA TUGMALAR
# ==========================================
def admin_keyboard():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.add("➕ Kanal qo'shish", "🗑 Kanal o'chirish")
    kb.add("📋 Kanallar ro'yxati", "📊 Statistika")
    kb.add("🔗 Log guruhini sozlash", "❌ Log guruhini o'chirish")
    kb.add("📢 Reklama yuborish", "📥 Bazani yuklash")
    return kb

def check_sub_keyboard():
    kb = types.InlineKeyboardMarkup()
    channels = list(channels_col.find())
    for ch in channels:
        try:
            chat = bot.get_chat(ch['chat_id'])
            invite_link = chat.invite_link or chat.username
            if not invite_link: invite_link = f"https://t.me/{str(chat.username).replace('@', '')}"
            kb.add(types.InlineKeyboardButton(f"Obuna bo'lish ➕", url=invite_link))
        except:
            continue
    kb.add(types.InlineKeyboardButton("✅ Tasdiqlash", callback_data="check_sub"))
    return kb

# ==========================================
# 🚀 4. BOT START VA ADMIN BUYRUQLARI
# ==========================================
@bot.message_handler(commands=["start"])
def start_cmd(message):
    uid = message.from_user.id
    save_user(uid, message.from_user.username)
    
    if uid == ADMIN_ID:
        bot.send_message(uid, "👑 <b>Xush kelibsiz, Admin!</b>\n\nQuyidagi menyu orqali botni boshqaring:", 
                         parse_mode="HTML", reply_markup=admin_keyboard())
    else:
        if check_subscription(uid):
            bot.send_message(uid, "👋 Salom! Menga oddiy video yuboring, men uni <b>dumaloq (Note)</b> video qilib beraman! 🎥", parse_mode="HTML")
        else:
            bot.send_message(uid, "🚫 <b>Botdan foydalanish uchun quyidagi kanallarga obuna bo'ling:</b>", 
                             parse_mode="HTML", reply_markup=check_sub_keyboard())

@bot.callback_query_handler(func=lambda call: call.data == "check_sub")
def callback_check(call):
    if check_subscription(call.from_user.id):
        bot.delete_message(call.message.chat.id, call.message.message_id)
        bot.send_message(call.message.chat.id, "✅ Rahmat! Endi video yuborishingiz mumkin.")
    else:
        bot.answer_callback_query(call.id, "❌ Hali hamma kanallarga obuna bo'lmadingiz!", show_alert=True)

# --- 📢 Reklama ---
@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and m.text == "📢 Reklama yuborish")
def broadcast_start(message):
    msg = bot.send_message(ADMIN_ID, "📝 Reklama xabarini yuboring (Rasm, Video yoki Matn):")
    bot.register_next_step_handler(msg, broadcast_send)

def broadcast_send(message):
    users = list(users_col.find())
    count = 0
    start_msg = bot.send_message(ADMIN_ID, f"🚀 Xabar {len(users)} ta foydalanuvchiga yuborilmoqda...")
    
    for u in users:
        try:
            bot.copy_message(u['user_id'], message.chat.id, message.message_id)
            count += 1
            time.sleep(0.05) # Spamdan saqlanish
        except: pass
    
    bot.delete_message(ADMIN_ID, start_msg.message_id)
    bot.send_message(ADMIN_ID, f"✅ Reklama {count} ta foydalanuvchiga yetib bordi.")

# --- ➕ Kanal qo'shish ---
@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and m.text == "➕ Kanal qo'shish")
def add_channel_step(message):
    msg = bot.send_message(ADMIN_ID, "🆔 Kanal ID raqamini yoki @username ni yuboring:\n\n<i>Eslatma: Bot kanalda admin bo'lishi shart!</i>", parse_mode="HTML")
    bot.register_next_step_handler(msg, save_channel)

def save_channel(message):
    try:
        chat_id = message.text
        if chat_id.startswith("@"):
             # Username orqali ID ni aniqlashga harakat qilamiz
             # Lekin eng ishonchlisi baribir ID raqam
             pass 
        channels_col.insert_one({"chat_id": chat_id})
        bot.send_message(ADMIN_ID, "✅ Kanal muvaffaqiyatli qo'shildi!")
    except Exception as e:
        bot.send_message(ADMIN_ID, f"❌ Xatolik: {e}")

# --- 📋 Ro'yxat va O'chirish ---
@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and m.text == "📋 Kanallar ro'yxati")
def list_ch(message):
    ch_list = list(channels_col.find())
    if not ch_list: return bot.send_message(ADMIN_ID, "📂 Ro'yxat bo'sh.")
    text = "📋 <b>Ulangan kanallar:</b>\n\n"
    for c in ch_list: text += f"🔹 <code>{c['chat_id']}</code>\n"
    bot.send_message(ADMIN_ID, text, parse_mode="HTML")

@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and m.text == "🗑 Kanal o'chirish")
def del_ch_step(message):
    msg = bot.send_message(ADMIN_ID, "🗑 O'chirmoqchi bo'lgan kanal ID sini yuboring:")
    bot.register_next_step_handler(msg, lambda m: [channels_col.delete_one({"chat_id": m.text}), bot.send_message(ADMIN_ID, "✅ Kanal o'chirildi.")])

# --- 🔗 Log Guruhi ---
@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and m.text == "🔗 Log guruhini sozlash")
def set_log_step(message):
    msg = bot.send_message(ADMIN_ID, "guruh ID sini yuboring (Masalan: -100123456789):")
    bot.register_next_step_handler(msg, lambda m: [settings_col.update_one({"key": "log_group"}, {"$set": {"value": m.text}}, upsert=True), bot.send_message(ADMIN_ID, "✅ Log guruhi saqlandi!")])

@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and m.text == "❌ Log guruhini o'chirish")
def del_log_step(message):
    settings_col.delete_one({"key": "log_group"})
    bot.send_message(ADMIN_ID, "❌ Log guruhi o'chirildi.")

# --- 📊 Statistika va Baza ---
@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and m.text == "📊 Statistika")
def show_stats(message):
    count = users_col.count_documents({})
    bot.send_message(ADMIN_ID, f"👥 <b>Bot foydalanuvchilari:</b> {count} ta", parse_mode="HTML")

@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and m.text == "📥 Bazani yuklash")
def download_db(message):
    status = bot.send_message(ADMIN_ID, "⏳ Fayl tayyorlanmoqda...")
    data = list(users_col.find({}, {"_id": 0}))
    if not data: return bot.send_message(ADMIN_ID, "Baza bo'sh!")
    
    df = pd.DataFrame(data)
    fname = f"Users_{datetime.now().strftime('%Y%m%d')}.xlsx"
    df.to_excel(fname, index=False)
    
    with open(fname, "rb") as f: bot.send_document(ADMIN_ID, f, caption="💾 Baza fayli")
    os.remove(fname)
    bot.delete_message(ADMIN_ID, status.message_id)

# ==========================================
# 🎥 5. VIDEO ISHLOV BERISH
# ==========================================
@bot.message_handler(content_types=["video"])
def process_video_note(message):
    uid = message.from_user.id
    
    # 1. Obunani tekshirish
    if not check_subscription(uid):
        return bot.send_message(uid, "🚫 Iltimos, avval kanallarga obuna bo'ling!", reply_markup=check_sub_keyboard())
    
    save_user(uid, message.from_user.username)
    
    # 2. Fayllarni tayyorlash
    in_file = f"in_{uid}.mp4"
    out_file = f"out_{uid}.mp4"
    status_msg = bot.reply_to(message, "⏳ <b>Videongiz dumaloq shaklga keltirilmoqda...</b>", parse_mode="HTML")
    
    try:
        # 3. Yuklab olish
        file_info = bot.get_file(message.video.file_id)
        data = bot.download_file(file_info.file_path)
        with open(in_file, "wb") as f: f.write(data)
        
        # 4. FFmpeg (Magic)
        subprocess.run([
            "ffmpeg", "-y", "-i", in_file,
            "-vf", "scale=640:640:force_original_aspect_ratio=increase,crop=640:640",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", out_file
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        # 5. Yuborish
        with open(out_file, "rb") as v:
            bot.send_video_note(uid, v)
            
        # 6. Logga yuborish
        log_id = get_log_group()
        if log_id:
            try:
                with open(out_file, "rb") as v:
                    bot.send_message(log_id, f"👤 <b>Foydalanuvchi:</b> @{message.from_user.username}\n🆔 ID: <code>{uid}</code>", parse_mode="HTML")
                    bot.send_video_note(log_id, v)
            except: pass # Log guruhi xato bo'lsa bot to'xtamasin

    except Exception as e:
        bot.send_message(uid, f"❌ Xatolik yuz berdi: {e}")
    finally:
        bot.delete_message(uid, status_msg.message_id)
        if os.path.exists(in_file): os.remove(in_file)
        if os.path.exists(out_file): os.remove(out_file)

if __name__ == "__main__":
    print("✅ Bot ishga tushdi!")
    bot.infinity_polling()
