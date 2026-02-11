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

# FFmpeg yo'llarini qo'shish
static_ffmpeg.add_paths()

bot = telebot.TeleBot(API_TOKEN)

# ==========================================
# 🗄 2. BAZA BILAN ULANISH
# ==========================================
try:
    client = MongoClient(MONGO_URL, tlsAllowInvalidCertificates=True)
    db = client['vid2note_bot_db']

    users_col = db['users']         # Barcha foydalanuvchilar
    channels_col = db['channels']   # Oddiy majburiy kanallar
    s_channels_col = db['s_channels'] # "Join Request" talab qilinadigan kanallar
    requests_col = db['requests']   # So'rov yuborganlar ro'yxati
    settings_col = db['settings']   # Sozlamalar
    print("✅ Baza bilan aloqa o'rnatildi!")
except Exception as e:
    print(f"❌ Bazaga ulanishda xatolik: {e}")

# ==========================================
# 🛠 YORDAMCHI FUNKSIYALAR
# ==========================================

def save_user(uid, username):
    """Foydalanuvchini bazaga saqlash"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    users_col.update_one(
        {"user_id": uid},
        {"$set": {"last_active": now, "username": username}, 
         "$setOnInsert": {"joined": now}},
        upsert=True
    )

def check_subscription(user_id):
    """
    Foydalanuvchi kanallarga a'zo ekanligini yoki 
    so'rov yuborganligini tekshiradi.
    """
    # 1. Oddiy kanallarni tekshirish
    regular_channels = list(channels_col.find())
    for ch in regular_channels:
        try:
            status = bot.get_chat_member(ch['chat_id'], user_id).status
            if status not in ['creator', 'administrator', 'member']:
                return False
        except Exception as e:
            # Agar bot kanalda admin bo'lmasa yoki xato bo'lsa, o'tkazib yuboramiz
            print(f"Kanal tekshirishda xato: {e}")
            continue

    # 2. "So'rov" (Request) kanallarini tekshirish
    request_channels = list(s_channels_col.find())
    for sch in request_channels:
        chat_id = str(sch['chat_id'])
        
        # A) Avval bazadan "so'rov yuborganmi" deb tekshiramiz
        is_requested = requests_col.find_one({"user_id": user_id, "chat_id": chat_id})
        
        # B) Agar so'rov yubormagan bo'lsa, balki allaqachon a'zodir?
        if not is_requested:
            try:
                status = bot.get_chat_member(chat_id, user_id).status
                if status not in ['creator', 'administrator', 'member']:
                    return False
            except:
                return False # Na a'zo, na so'rov yuborgan
            
    return True

def get_log_group():
    res = settings_col.find_one({"key": "log_group"})
    return res['value'] if res else None

# ==========================================
# 📩 JOIN REQUEST HANDLER (ENG MUHIM QISM)
# ==========================================
@bot.chat_join_request_handler()
def handle_join_request(update: types.ChatJoinRequest):
    """
    Foydalanuvchi kanalga qo'shilish so'rovini yuborganda ishlaydi.
    """
    user_id = update.from_user.id
    chat_id = str(update.chat.id)
    username = update.from_user.username

    # 1. Bazaga "bu odam so'rov yubordi" deb yozib qo'yamiz
    requests_col.update_one(
        {"user_id": user_id, "chat_id": chat_id},
        {"$set": {
            "status": "requested", 
            "username": username,
            "date": datetime.now()
        }},
        upsert=True
    )
    
    # 2. Foydalanuvchiga botdan xabar yuborish (ixtiyoriy)
    try:
        bot.send_message(user_id, "✅ So'rovingiz qabul qilindi! Endi botdan bemalol foydalanishingiz mumkin.")
    except:
        pass # Agar foydalanuvchi botni bloklagan bo'lsa

# ==========================================
# 🖥 3. KEYBOARDLAR (TUGMALAR)
# ==========================================
def admin_keyboard():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    # Oddiy kanallar
    kb.add("➕ Kanal qo'shish", "🗑 Kanal o'chirish")
    # So'rovli kanallar (Yangi funksiya)
    kb.add("➕ [S] Kanal qo'shish", "🗑 [S] Kanal o'chirish")
    # Umumiy
    kb.add("📋 Kanallar ro'yxati", "📊 Statistika")
    kb.add("🔗 Log guruhini sozlash", "📥 Bazani yuklash")
    kb.add("📢 Reklama yuborish")
    return kb

def check_sub_keyboard():
    kb = types.InlineKeyboardMarkup(row_width=1)
    
    # Oddiy kanallar
    for ch in channels_col.find():
        try:
            chat = bot.get_chat(ch['chat_id'])
            link = chat.invite_link or f"https://t.me/{chat.username}"
            kb.add(types.InlineKeyboardButton(f"Obuna bo'lish ➕", url=link))
        except: continue
        
    # So'rovli kanallar ([S])
    for sch in s_channels_col.find():
        try:
            chat = bot.get_chat(sch['chat_id'])
            # So'rov uchun maxsus link (Admin Approval yoqilgan link bo'lishi kerak)
            link = chat.invite_link or f"https://t.me/{chat.username}"
            kb.add(types.InlineKeyboardButton(f"So'rov yuborish 📩", url=link))
        except: continue
        
    kb.add(types.InlineKeyboardButton("✅ Tekshirish", callback_data="check_sub"))
    return kb

# ==========================================
# 🚀 4. COMMAND HANDLERS
# ==========================================
@bot.message_handler(commands=["start"])
def start_cmd(message):
    uid = message.from_user.id
    save_user(uid, message.from_user.username)
    
    if uid == ADMIN_ID:
        bot.send_message(uid, "👑 <b>Admin Panel</b>", parse_mode="HTML", reply_markup=admin_keyboard())
    else:
        if check_subscription(uid):
            bot.send_message(uid, "👋 Salom! Menga video yuboring, dumaloq (Note) qilib beraman!")
        else:
            bot.send_message(uid, "🚫 <b>Botdan foydalanish uchun kanallarga qo'shiling:</b>", 
                             parse_mode="HTML", reply_markup=check_sub_keyboard())

@bot.callback_query_handler(func=lambda call: call.data == "check_sub")
def callback_check(call):
    if check_subscription(call.from_user.id):
        bot.delete_message(call.message.chat.id, call.message.message_id)
        bot.send_message(call.message.chat.id, "✅ Rahmat! Endi video yuborishingiz mumkin.")
    else:
        bot.answer_callback_query(call.id, "❌ Hali hamma shartlarni bajarmadingiz!", show_alert=True)

# ==========================================
# 👮‍♂️ ADMIN BUYRUQLARI
# ==========================================

# --- Oddiy Kanal ---
@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and m.text == "➕ Kanal qo'shish")
def add_ch(m):
    msg = bot.send_message(ADMIN_ID, "🆔 Kanal ID yoki Username yuboring:")
    bot.register_next_step_handler(msg, lambda m: [channels_col.insert_one({"chat_id": m.text}), bot.send_message(ADMIN_ID, "✅ Kanal qo'shildi")])

@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and m.text == "🗑 Kanal o'chirish")
def del_ch(m):
    msg = bot.send_message(ADMIN_ID, "🗑 ID yuboring:")
    bot.register_next_step_handler(msg, lambda m: [channels_col.delete_one({"chat_id": m.text}), bot.send_message(ADMIN_ID, "✅ O'chirildi")])

# --- [S] So'rovli Kanal (YANGI) ---
@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and m.text == "➕ [S] Kanal qo'shish")
def add_s_ch(m):
    msg = bot.send_message(ADMIN_ID, "📩 <b>[Request]</b> Kanal ID sini yuboring:\n<i>Bot bu kanalda admin bo'lishi shart!</i>", parse_mode="HTML")
    bot.register_next_step_handler(msg, lambda m: [s_channels_col.insert_one({"chat_id": m.text}), bot.send_message(ADMIN_ID, "✅ [S] Kanal qo'shildi")])

@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and m.text == "🗑 [S] Kanal o'chirish")
def del_s_ch(m):
    msg = bot.send_message(ADMIN_ID, "🗑 [S] Kanal ID sini yuboring:")
    bot.register_next_step_handler(msg, lambda m: [s_channels_col.delete_one({"chat_id": m.text}), bot.send_message(ADMIN_ID, "✅ [S] Kanal o'chirildi")])

# --- Ro'yxat ---
@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and m.text == "📋 Kanallar ro'yxati")
def list_all(m):
    text = "<b>📌 Oddiy Kanallar:</b>\n"
    for c in channels_col.find(): text += f"▫️ {c['chat_id']}\n"
    
    text += "\n<b>📩 So'rovli ([S]) Kanallar:</b>\n"
    for c in s_channels_col.find(): text += f"▫️ {c['chat_id']}\n"
    
    bot.send_message(ADMIN_ID, text, parse_mode="HTML")

# --- Log Guruhi ---
@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and m.text == "🔗 Log guruhini sozlash")
def set_log(m):
    msg = bot.send_message(ADMIN_ID, "Log guruh ID sini yuboring:")
    bot.register_next_step_handler(msg, lambda m: [settings_col.update_one({"key": "log_group"}, {"$set": {"value": m.text}}, upsert=True), bot.send_message(ADMIN_ID, "✅ Saqlandi")])

# --- Statistika va Baza ---
@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and m.text == "📊 Statistika")
def stats(m):
    u = users_col.count_documents({})
    bot.send_message(ADMIN_ID, f"👥 Foydalanuvchilar: {u} ta")

@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and m.text == "📥 Bazani yuklash")
def dl_db(m):
    data = list(users_col.find({}, {"_id": 0}))
    if not data: return bot.send_message(ADMIN_ID, "Baza bo'sh")
    df = pd.DataFrame(data)
    df.to_excel("users.xlsx", index=False)
    with open("users.xlsx", "rb") as f: bot.send_document(ADMIN_ID, f)
    os.remove("users.xlsx")

# --- Reklama ---
@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and m.text == "📢 Reklama yuborish")
def broadcast(m):
    msg = bot.send_message(ADMIN_ID, "Xabarni yuboring (Forward mumkin):")
    bot.register_next_step_handler(msg, send_broad)

def send_broad(m):
    users = users_col.find()
    count = 0
    for u in users:
        try:
            bot.copy_message(u['user_id'], m.chat.id, m.message_id)
            count += 1
            time.sleep(0.05)
        except: pass
    bot.send_message(ADMIN_ID, f"✅ {count} kishiga yuborildi.")

# ==========================================
# 🎥 5. VIDEO PROCESS
# ==========================================
@bot.message_handler(content_types=["video"])
def process_video(message):
    uid = message.from_user.id
    
    # Obuna tekshiruvi
    if not check_subscription(uid):
        return bot.send_message(uid, "🚫 Iltimos, kanallarga obuna bo'ling!", reply_markup=check_sub_keyboard())
    
    save_user(uid, message.from_user.username)
    
    in_file = f"in_{uid}.mp4"
    out_file = f"out_{uid}.mp4"
    status_msg = bot.reply_to(message, "⏳ <b>Tayyorlanmoqda...</b>", parse_mode="HTML")
    
    try:
        # Yuklash
        file_info = bot.get_file(message.video.file_id)
        data = bot.download_file(file_info.file_path)
        with open(in_file, "wb") as f: f.write(data)
        
        # Konvertatsiya
        subprocess.run([
            "ffmpeg", "-y", "-i", in_file,
            "-vf", "scale=640:640:force_original_aspect_ratio=increase,crop=640:640",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", out_file
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        # Yuborish
        with open(out_file, "rb") as v:
            bot.send_video_note(uid, v)
        
        # Log
        log_id = get_log_group()
        if log_id:
            with open(out_file, "rb") as v:
                bot.send_message(log_id, f"👤: {message.from_user.first_name} (@{message.from_user.username})")
                bot.send_video_note(log_id, v)

    except Exception as e:
        bot.send_message(uid, f"Xatolik: {e}")
    finally:
        bot.delete_message(uid, status_msg.message_id)
        if os.path.exists(in_file): os.remove(in_file)
        if os.path.exists(out_file): os.remove(out_file)

# ==========================================
# 🔥 BOTNI ISHGA TUSHIRISH
# ==========================================
if __name__ == "__main__":
    print("🚀 Bot ishga tushdi...")
    # allowed_updates juda muhim, aks holda requestlar kelmaydi
    bot.infinity_polling(allowed_updates=['message', 'callback_query', 'chat_join_request'])
