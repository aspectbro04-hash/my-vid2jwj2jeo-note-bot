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
API_TOKEN = "8426868102:AAFYMpizU_BI6mvLe-VES1A9pjhq45fNoEo"  # ⚠️ Tokenni shu yerga yozing
MONGO_URL = "mongodb+srv://aspectbro04_db_user:Gz6C9Wf8FDcRaWzb@cluster0.d5jmju6.mongodb.net/?appName=Cluster0" # ⚠️ Mongo URLni shu yerga yozing
ADMIN_ID = 5153414405

# FFmpeg ni sozlash
static_ffmpeg.add_paths()

bot = telebot.TeleBot(API_TOKEN, parse_mode="HTML")

# ==========================================
# 🗄 DATABASE
# ==========================================
try:
    client = MongoClient(MONGO_URL)
    db = client['vid2note_bot_db']
    users_col = db['users']
    channels_col = db['channels']
    s_channels_col = db['s_channels']
    requests_col = db['requests']
    settings_col = db['settings']
    print("✅ DB ulandi")
except Exception as e:
    print(f"❌ DB Xatolik: {e}")

# ==========================================
# 🛠 YORDAMCHI OZGARUVCHILAR (STATE)
# ==========================================
admin_state = {} # Adminning hozirgi holatini saqlash uchun

# ==========================================
# 👤 USER FUNKSIYALARI
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
    # 1. Oddiy kanallarni tekshirish
    for ch in channels_col.find():
        try:
            st = bot.get_chat_member(ch["chat_id"], uid).status
            if st not in ["member", "administrator", "creator"]:
                return False
        except Exception as e:
            # Agar bot kanaldan chiqarib yuborilgan bo'lsa, uni o'chirmaymiz, lekin userga o'tishga ruxsat beramiz (admin uchun signal)
            print(f"Kanal xatosi: {e}")
            continue

    # 2. So'rovli (Private) kanallarni tekshirish
    for sch in s_channels_col.find():
        if not requests_col.find_one({"user_id": uid, "chat_id": str(sch["chat_id"])}):
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
    kb.add("🔗 Log guruh", "🔙 Bekor qilish")
    return kb

def cancel_keyboard():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("🔙 Bekor qilish")
    return kb

def check_sub_keyboard():
    kb = types.InlineKeyboardMarkup(row_width=1)
    
    # Oddiy kanallar
    for ch in channels_col.find():
        try:
            chat = bot.get_chat(ch["chat_id"])
            link = chat.invite_link or f"https://t.me/{chat.username}"
            kb.add(types.InlineKeyboardButton(f"➕ {chat.title}", url=link))
        except:
            pass

    # So'rovli kanallar
    for sch in s_channels_col.find():
        try:
            chat = bot.get_chat(sch["chat_id"])
            link = chat.invite_link
            if link:
                kb.add(types.InlineKeyboardButton(f"🔒 {chat.title} (So'rov)", url=link))
        except:
            pass

    kb.add(types.InlineKeyboardButton("✅ Tekshirish", callback_data="check_sub"))
    return kb

# ==========================================
# 🚀 START & JOIN REQUEST
# ==========================================
@bot.chat_join_request_handler()
def join_req(u):
    requests_col.update_one(
        {"user_id": u.from_user.id, "chat_id": str(u.chat.id)},
        {"$set": {"date": datetime.now()}},
        upsert=True
    )
    # Log guruhga xabar (agar bor bo'lsa)
    log_id = settings_col.find_one({"key": "log_group"})
    if log_id:
        try:
            bot.send_message(log_id['value'], f"🆕 Yangi so'rov:\nUser: {u.from_user.full_name}\nID: <code>{u.from_user.id}</code>")
        except: pass

@bot.message_handler(commands=["start"])
def start_cmd(m):
    uid = m.from_user.id
    save_user(uid, m.from_user.username)

    if uid == ADMIN_ID:
        admin_state[uid] = None
        bot.send_message(uid, "👑 <b>Admin Panelga xush kelibsiz!</b>", reply_markup=admin_keyboard())
    else:
        if check_subscription(uid):
            bot.send_message(uid, "👋 Assalomu alaykum!\n\n🎥 Menga <b>video</b> yuboring, men uni dumaloq (video note) qilib beraman.")
        else:
            bot.send_message(uid, "🚫 Botdan foydalanish uchun quyidagi kanallarga obuna bo'ling:", reply_markup=check_sub_keyboard())

@bot.callback_query_handler(func=lambda c: c.data == "check_sub")
def check_btn(c):
    if check_subscription(c.from_user.id):
        bot.delete_message(c.message.chat.id, c.message.id)
        bot.send_message(c.message.chat.id, "✅ Rahmat! Endi video yuborishingiz mumkin.")
    else:
        bot.answer_callback_query(c.id, "❌ Hali hamma kanalga obuna bo'lmadingiz!", show_alert=True)

# ==========================================
# 👑 ADMIN PANEL LOGIKASI
# ==========================================

@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and m.text == "🔙 Bekor qilish")
def cancel_action(m):
    admin_state[m.from_user.id] = None
    bot.send_message(m.chat.id, "🚫 Bekor qilindi.", reply_markup=admin_keyboard())

# --- STATISTIKA ---
@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and m.text == "📊 Statistika")
def stats(m):
    users = users_col.count_documents({})
    active_24 = users_col.count_documents({"last_active": {"$gte": datetime.now().replace(hour=0, minute=0)}})
    bot.send_message(m.chat.id, f"📊 <b>Bot Statistikasi:</b>\n\n👥 Jami foydalanuvchilar: <b>{users}</b>\n⚡️ Bugungi faollar: <b>{active_24}</b>")

# --- KANALLAR RO'YXATI ---
@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and m.text == "📋 Kanallar ro'yxati")
def list_channels(m):
    txt = "<b>📢 Oddiy Kanallar:</b>\n"
    for x in channels_col.find():
        txt += f"🆔 <code>{x['chat_id']}</code>\n"
    
    txt += "\n<b>🔒 [S] So'rovli Kanallar:</b>\n"
    for x in s_channels_col.find():
        txt += f"🆔 <code>{x['chat_id']}</code>\n"
        
    bot.send_message(m.chat.id, txt or "Kanallar yo'q")

# --- KANAL QO'SHISH ---
@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and m.text == "➕ Kanal qo'shish")
def add_ch_step1(m):
    admin_state[m.from_user.id] = "add_channel"
    bot.send_message(m.chat.id, "🆔 Kanal ID raqamini yuboring (yoki postni forward qiling):", reply_markup=cancel_keyboard())

@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and m.text == "➕ [S] Kanal qo'shish")
def add_sch_step1(m):
    admin_state[m.from_user.id] = "add_s_channel"
    bot.send_message(m.chat.id, "🆔 [S] Kanal ID raqamini yuboring (Invite Linki bor bo'lishi shart):", reply_markup=cancel_keyboard())

# --- KANAL O'CHIRISH ---
@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and m.text == "🗑 Kanal o'chirish")
def del_ch_step1(m):
    admin_state[m.from_user.id] = "del_channel"
    bot.send_message(m.chat.id, "🗑 O'chiriladigan Kanal ID sini yuboring:", reply_markup=cancel_keyboard())

@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and m.text == "🗑 [S] Kanal o'chirish")
def del_sch_step1(m):
    admin_state[m.from_user.id] = "del_s_channel"
    bot.send_message(m.chat.id, "🗑 O'chiriladigan [S] Kanal ID sini yuboring:", reply_markup=cancel_keyboard())

# --- REKLAMA ---
@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and m.text == "📢 Reklama yuborish")
def broadcast_step1(m):
    admin_state[m.from_user.id] = "broadcast"
    bot.send_message(m.chat.id, "📩 Reklama xabarini yuboring (Rasm, Video, Text...):", reply_markup=cancel_keyboard())

# --- LOG GURUH ---
@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and m.text == "🔗 Log guruh")
def log_step1(m):
    admin_state[m.from_user.id] = "set_log"
    bot.send_message(m.chat.id, "📂 Loglar tushadigan guruh ID sini yuboring:", reply_markup=cancel_keyboard())

# --- BAZA YUKLASH ---
@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and m.text == "📥 Bazani yuklash")
def export_db(m):
    msg = bot.send_message(m.chat.id, "⏳ Tayyorlanmoqda...")
    filename = "users.csv"
    with open(filename, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["user_id","username","joined"])
        for u in users_col.find():
            w.writerow([u.get("user_id"), u.get("username"), u.get("joined")])
    bot.send_document(m.chat.id, open(filename,"rb"))
    os.remove(filename)
    bot.delete_message(m.chat.id, msg.message_id)

# ==========================================
# ⚙️ ADMIN INPUT HANDLER (STATE BO'YICHA)
# ==========================================
@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and admin_state.get(m.from_user.id))
def admin_input_handler(m):
    state = admin_state[m.from_user.id]
    
    # KANAL QO'SHISH
    if state == "add_channel":
        try:
            cid = m.forward_from_chat.id if m.forward_from_chat else int(m.text)
            channels_col.update_one({"chat_id": cid}, {"$set": {"added": datetime.now()}}, upsert=True)
            bot.send_message(m.chat.id, f"✅ Kanal qo'shildi: {cid}", reply_markup=admin_keyboard())
        except:
            bot.send_message(m.chat.id, "❌ ID xato. Qayta urinib ko'ring.")
            return
    
    # [S] KANAL QO'SHISH
    elif state == "add_s_channel":
        try:
            cid = int(m.text)
            s_channels_col.update_one({"chat_id": cid}, {"$set": {"added": datetime.now()}}, upsert=True)
            bot.send_message(m.chat.id, f"✅ [S] Kanal qo'shildi: {cid}", reply_markup=admin_keyboard())
        except:
            bot.send_message(m.chat.id, "❌ ID raqam bo'lishi kerak.")
            return

    # KANAL O'CHIRISH
    elif state == "del_channel":
        try:
            cid = int(m.text)
            channels_col.delete_one({"chat_id": cid})
            bot.send_message(m.chat.id, f"🗑 Kanal o'chirildi: {cid}", reply_markup=admin_keyboard())
        except:
            bot.send_message(m.chat.id, "❌ ID xato.")

    # [S] KANAL O'CHIRISH
    elif state == "del_s_channel":
        try:
            cid = int(m.text)
            s_channels_col.delete_one({"chat_id": cid})
            bot.send_message(m.chat.id, f"🗑 [S] Kanal o'chirildi: {cid}", reply_markup=admin_keyboard())
        except:
            bot.send_message(m.chat.id, "❌ ID xato.")
            
    # LOG GURUH
    elif state == "set_log":
        try:
            cid = int(m.text)
            settings_col.update_one({"key": "log_group"}, {"$set": {"value": cid}}, upsert=True)
            bot.send_message(m.chat.id, f"✅ Log guruh sozlandi: {cid}", reply_markup=admin_keyboard())
        except:
            bot.send_message(m.chat.id, "❌ ID xato.")

    # REKLAMA (BROADCAST)
    elif state == "broadcast":
        msg_id = m.message_id
        chat_id = m.chat.id
        
        def send_ad():
            success = 0
            fail = 0
            users = users_col.find()
            bot.send_message(chat_id, "🚀 Reklama yuborish boshlandi...", reply_markup=admin_keyboard())
            
            for u in users:
                try:
                    bot.copy_message(u['user_id'], chat_id, msg_id)
                    success += 1
                    time.sleep(0.05) # Spamdan himoya
                except:
                    fail += 1
            
            bot.send_message(chat_id, f"🏁 <b>Reklama tugadi!</b>\n\n✅ Yetib bordi: {success}\n❌ Bloklaganlar: {fail}")

        threading.Thread(target=send_ad).start()
        
    admin_state[m.from_user.id] = None # Statenni tozalash

# ==========================================
# 🎥 VIDEO PROCESS
# ==========================================
@bot.message_handler(content_types=["video"])
def process_video(m):
    uid = m.from_user.id

    if not check_subscription(uid):
        return bot.send_message(uid, "🚫 Iltimos, oldin kanallarga obuna bo'ling!", reply_markup=check_sub_keyboard())

    if m.video.file_size > 20 * 1024 * 1024: # 20MB limit
        return bot.reply_to(m, "❌ Video hajmi juda katta! (Max: 20MB)")

    in_f = f"{uid}.mp4"
    out_f = f"{uid}_o.mp4"
    msg = bot.reply_to(m, "⏳ Video yuklanmoqda va qayta ishlanmoqda...")

    try:
        file_info = bot.get_file(m.video.file_id)
        data = bot.download_file(file_info.file_path)

        with open(in_f, "wb") as f:
            f.write(data)

        # VideoNote (Dumaloq) uchun maxsus sozlamalar
        # Kvadrat qirqish va siqish
        cmd = [
            "ffmpeg", "-y", "-i", in_f,
            "-vf", "scale=640:640:force_original_aspect_ratio=increase,crop=640:640,setsar=1",
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "28",
            "-c:a", "aac", "-b:a", "128k",
            "-t", "60", # 1 daqiqadan oshmasligi kerak
            out_f
        ]
        
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        if os.path.exists(out_f):
            with open(out_f, "rb") as v:
                bot.send_video_note(uid, v)
            bot.delete_message(uid, msg.message_id)
            
            # Logga yuborish
            log = settings_col.find_one({"key": "log_group"})
            if log:
                bot.send_message(log['value'], f"📹 VideoNote yasaldi.\nUser: {m.from_user.full_name} ({uid})")
        else:
            bot.edit_message_text("❌ Konvertatsiya xatosi.", uid, msg.message_id)

    except Exception as e:
        bot.send_message(uid, f"❌ Xatolik yuz berdi: {e}")
    finally:
        if os.path.exists(in_f): os.remove(in_f)
        if os.path.exists(out_f): os.remove(out_f)

print("🚀 Bot ishga tushdi...")
bot.infinity_polling(allowed_updates=["message", "callback_query", "chat_join_request"])
