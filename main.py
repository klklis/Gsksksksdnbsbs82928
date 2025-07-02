import os, csv, asyncio, random, json, time
from telethon import TelegramClient, events, Button
from telethon.errors import SessionPasswordNeededError, FloodWaitError
from telethon.tl.functions.channels import InviteToChannelRequest
from telethon.tl.types import InputPeerUser
from collections import defaultdict
from keep_alive import keep_alive

API_ID = 25053231
API_HASH = '74cf3c784b07be86735222255eadecce'
BOT_TOKEN = '7755866198:AAH2TzyWcmxwD8Se83x7T2kRVEWmGPtnM08'

OWNER_ID = 6455754723
ADMINS_FILE = "admins.json"
SESSIONS_DIR = "sessions"
SOURCE_FILE = "الاعضاء-المرشحون.csv"
ADDED_FILE = "الاعضاء-المضافون.csv"
FAILED_FILE = "الاعضاء-الفاشلون.csv"
ACTIVE_SESSION_FILE = "active_sessions.json"

def ensure_file(filename):
 if not os.path.exists(filename):
  with open(filename, 'w', encoding='utf-8', newline='') as f:
   csv.writer(f).writerow(['username', 'user_id', 'access_hash'])

def ensure_json(filename, default_value):
 if not os.path.exists(filename):
  with open(filename, "w", encoding="utf-8") as f:
   json.dump(default_value, f)

os.makedirs(SESSIONS_DIR, exist_ok=True)
ensure_file(SOURCE_FILE)
ensure_file(ADDED_FILE)
ensure_file(FAILED_FILE)
ensure_json(ADMINS_FILE, [OWNER_ID])
ensure_json(ACTIVE_SESSION_FILE, {})

def load_admins():
 if not os.path.exists(ADMINS_FILE):
  with open(ADMINS_FILE, "w") as f: json.dump([OWNER_ID], f)
 with open(ADMINS_FILE) as f:
  return json.load(f)

def save_admins(admins):
 with open(ADMINS_FILE, "w") as f:
  json.dump(admins, f)

def save_active_sessions():
 with open(ACTIVE_SESSION_FILE, "w") as f:
  json.dump(active_sessions, f)

def load_active_sessions():
 if os.path.exists(ACTIVE_SESSION_FILE):
  with open(ACTIVE_SESSION_FILE) as f:
   return json.load(f)
 return {}

ADMINS = load_admins()
sessions = {}
active_sessions = load_active_sessions()
states, stop_flags, counters, user_sessions = {}, {}, {}, {}
spam_tracker = defaultdict(list)
def load_csv(filename):
 if not os.path.exists(filename): return []
 with open(filename, encoding='utf-8') as f:
  return list(csv.DictReader(f))
def save_csv_row(filename, data):
 existing = load_csv(filename)
 if not any(x['user_id'] == data['user_id'] for x in existing):
  with open(filename, 'a', encoding='utf-8', newline='') as f:
   csv.DictWriter(f, fieldnames=['username', 'user_id', 'access_hash']).writerow(data)
def remove_from_source(user_id):
 data = [x for x in load_csv(SOURCE_FILE) if x['user_id'] != str(user_id)]
 with open(SOURCE_FILE, 'w', encoding='utf-8', newline='') as f:
  w = csv.DictWriter(f, fieldnames=['username', 'user_id', 'access_hash'])
  w.writeheader(); w.writerows(data)

def decorate_arabic(text):
 decorations = ['ً','ٌ','ٍ','َ','ُ','ِ','ْ']
 positions = [i for i, c in enumerate(text) if '\u0600' <= c <= '\u06FF']
 if not positions: return text
 count = min(3, len(positions))
 selected = random.sample(positions, count)
 decorated = list(text)
 for pos in selected:
  decorated.insert(pos, random.choice(decorations))
 return ''.join(decorated)

async def load_existing_sessions():
 for file in os.listdir(SESSIONS_DIR):
  if file.endswith(".session") and "_" in file:
   owner_id, _ = file.split("_", 1)
   try:
    path = os.path.join(SESSIONS_DIR, file)
    client = TelegramClient(path, API_ID, API_HASH)
    await client.connect()
    if await client.is_user_authorized():
     me = await client.get_me()
     if owner_id not in user_sessions:
      user_sessions[owner_id] = {}
     user_sessions[owner_id][me.id] = (client, me)
     sessions[me.id] = (client, me)
    else:
     await client.disconnect()
     os.remove(path)
   except: continue

bot = TelegramClient("bot", API_ID, API_HASH).start(bot_token=BOT_TOKEN)

@bot.on(events.NewMessage(pattern='/start'))
async def start(event):
    chat = event.chat_id

    if chat not in ADMINS:
        await event.reply("❌ هذا البوت خاص.\nلتفعيله تواصل مع المطور: @rrr1t1")
        return

    user = await event.get_sender()
    name = user.first_name or "مستخدم"

    await event.reply(
    f"""👋 مرحباً بك يا <a href='tg://user?id={user.id}'>{name}</a>.

📌 <b>طريقة استخدام البوت:</b>

1. ➕ أضف حسابك من زر "أضف حساب".
2. 🧬 اختر الحساب من "تغيير الحساب".
3. 📥 اجمع الأعضاء من مجموعة بالرابط.
4. 📤 اضافة الاعضاء يجب ان يكون الحساب الذي ستستخدمه مشرف بصلاحية اضافة اعضاء في المجموعة التي سترسل رابطها..
5. ✉️ أرسل رسالة مع رابطهم بخطوتين.
6. 🛑 أوقف أي عملية بزر الإيقاف.
7. 📂 إدارة الجلسات والحسابات.

👮 فقط المصرح لهم يمكنهم استخدام البوت.
مطور البوت: <a href='https://t.me/rrr1t1/6'>وهَــم•</a>""",
    parse_mode='html'
)

    states[chat] = 'idle'
    stop_flags[chat] = False
    counters[chat] = {'collect': 0, 'add': 0, 'send': 0}

    await menu(chat)
async def menu(chat):
 session_id = active_sessions.get(chat)
 session_name = ''
 if session_id and session_id in sessions:
  session_name = f"🗽 الحساب: {sessions[session_id][1].first_name}"
 c = counters.get(chat, {})
 buttons = [
  [Button.inline(f"📥 جمع الاعضاء ({c.get('collect', 0)})", b'collect')],
  [Button.inline(f"📤 اضافة الاعضاء ({c.get('add', 0)})", b'add')],
  [Button.inline(f"✉️ ارسال الرسائل ({c.get('send', 0)})", b'send')],
  [Button.inline("📊 إعادة الإرسال للفاشلين", b'send_failed')],
  [Button.inline("➕ أضف حساب", b'addsession')],
  [Button.inline("🧬 تغيير الحساب", b'changesession')],
  [Button.inline("📂 الحسابات", b'show_sessions')]
 ]
 if chat == OWNER_ID:
  buttons.append([Button.inline("👮 إدارة المشرفين", b'admin_manage')])
 await bot.send_message(chat, f"{session_name}\n\nاختر احد الحسابات قبل ان تبدأ اي عملية من خلال زر الحسابات 📂:", buttons=buttons)
@bot.on(events.CallbackQuery)
async def callback(event):
 chat = event.chat_id
 if chat not in ADMINS:
  await event.answer("❌ البوت غير مفعل لهذا المستخدم", alert=True)
  return
 data = event.data.decode()

 if data == 'addsession':
  states[chat] = 'awaiting_phone'
  await event.edit("📱 أرسل رقم الهاتف مع +", buttons=[[Button.inline("🔙 رجوع", b'back')]])

 elif data == 'changesession':
  user_sess = user_sessions.get(str(chat), {})
  rows = [[Button.inline(user.first_name, f"use_{cid}".encode())] for cid, (_, user) in user_sess.items()]
  if not rows: rows = [[Button.inline("❌ لا توجد حسابات", b'none')]]
  rows.append([Button.inline("🔙 رجوع", b'back')])
  await event.edit("👨‍💻 اختر الحساب:", buttons=rows)

 elif data.startswith("use_"):
  cid = int(data[4:])
  if cid in sessions:
   active_sessions[chat] = cid
   save_active_sessions()
   await event.edit("✅ تم اختيار الحساب.")
   await menu(chat)

 elif data == 'show_sessions':
  user_sess = user_sessions.get(str(chat), {})
  rows = [
   [Button.inline(user.first_name, f"use_{cid}".encode()), Button.inline("🗑 حذف", f"del_{cid}".encode())]
   for cid, (_, user) in user_sess.items()
  ]
  if not rows: rows = [[Button.inline("❌ لا توجد حسابات", b'none')]]
  rows.append([Button.inline("🔙 رجوع", b'back')])
  await event.edit("📂 الحسابات:", buttons=rows)

 elif data.startswith("del_"):
  cid = int(data[4:])
  if cid in sessions:
   await sessions[cid][0].disconnect()
  for file in os.listdir(SESSIONS_DIR):
   if file.startswith(f"{chat}_{cid}"):
    os.remove(os.path.join(SESSIONS_DIR, file))
  sessions.pop(cid, None)
  user_sessions.get(str(chat), {}).pop(cid, None)
  if active_sessions.get(chat) == cid:
   active_sessions.pop(chat)
   save_active_sessions()
  await event.edit("🗑️ تم حذف الحساب.")
  await menu(chat)

 elif data in ['send', 'send_failed']:
  if chat not in active_sessions:
    return await event.answer("❗ اختر الحساب أولاً", alert=True)
  states[chat] = {'state': 'awaiting_send_text', 'mode': data}
  await event.edit("✍️ أرسل الرسالة الآن:", buttons=[[Button.inline("🔙 رجوع", b'back')]])

 elif data in ['collect', 'add']:
  if chat not in active_sessions:
    return await event.answer("❗ اختر الحساب أولاً", alert=True)
  states[chat] = data
  await event.edit("📥 أرسل رابط المجموعة", buttons=[[Button.inline("🔙 رجوع", b'back')]])

 elif data.startswith("stop_"):
  stop_flags[chat] = True
  await event.edit("🛑 تم إيقاف العملية.")

 elif data == 'admin_manage' and chat == OWNER_ID:
  rows = []
  for admin_id in ADMINS:
    try:
      user = await bot.get_entity(admin_id)
      name = f"@{user.username}" if user.username else user.first_name
      rows.append([
        Button.inline(name, b'noop'),
        Button.inline("🗑 حذف", f"deladmin_{admin_id}".encode())
      ])
    except:
      rows.append([
        Button.inline(str(admin_id), b'noop'),
        Button.inline("🗑 حذف", f"deladmin_{admin_id}".encode())
      ])
  rows.append([Button.inline("➕ إضافة مشرف", b'admin_add')])
  rows.append([Button.inline("🔙 رجوع", b'back')])
  await event.edit("👮 قائمة المشرفين الحاليين:", buttons=rows)

 elif data == 'admin_add' and chat == OWNER_ID:
  states[chat] = 'awaiting_admin_add'
  await event.edit("📩 أرسل رقم ID الخاص بالمشرف الجديد:", buttons=[[Button.inline("🔙 رجوع", b'back')]])

 elif data.startswith("deladmin_") and chat == OWNER_ID:
  uid = int(data.split("_")[1])
  if uid == OWNER_ID:
   await event.answer("❌ لا يمكن حذف المالك", alert=True)
  elif uid in ADMINS:
   ADMINS.remove(uid)
   save_admins(ADMINS)
   await event.edit("🗑 تم حذف المشرف.")
  else:
   await event.answer("ℹ️ هذا المستخدم ليس مشرفًا", alert=True)

 elif data == 'back':
  states[chat] = 'idle'
  await event.delete()
  await menu(chat)
@bot.on(events.NewMessage)
async def handler(event):
 if event.is_group or event.is_channel: return
 chat = event.chat_id
 if chat not in ADMINS: return
 txt = event.raw_text.strip()
 state = states.get(chat)
 now = time.time()
 spam_tracker[chat] = [t for t in spam_tracker[chat] if now - t < 15]
 spam_tracker[chat].append(now)
 if len(spam_tracker[chat]) > 10: return

 if state == 'awaiting_admin_add' and chat == OWNER_ID:
  try:
   uid = int(txt)
   if uid not in ADMINS:
    ADMINS.append(uid)
    save_admins(ADMINS)
    await event.reply(f"✅ تم إضافة المشرف: {uid}")
   else:
    await event.reply("ℹ️ هذا المستخدم مشرف بالفعل.")
  except:
   await event.reply("❌ ID غير صحيح.")
  states[chat] = 'idle'
  return

 if state == 'awaiting_phone':
  phone = txt
  path = f"{SESSIONS_DIR}/{chat}_{phone}.session"
  if os.path.exists(path):
   await event.reply("⚠️ الجلسة موجودة مسبقًا.")
   return
  client = TelegramClient(path, API_ID, API_HASH)
  await client.connect()
  try:
   await client.send_code_request(phone)
   states[chat] = {'state': 'awaiting_code', 'client': client, 'phone': phone}
   await event.reply("📩 أرسل رمز التحقق بهذه الطريقة : 1.2.3.4.5")
  except:
   await event.reply("❌ فشل إرسال الكود.")

 elif isinstance(state, dict) and state.get('state') == 'awaiting_code':
  d = state
  try:
   await d['client'].sign_in(d['phone'], txt)
   me = await d['client'].get_me()
   sessions[me.id] = (d['client'], me)
   if str(chat) not in user_sessions: user_sessions[str(chat)] = {}
   user_sessions[str(chat)][me.id] = (d['client'], me)
   await event.reply("✅ تم تسجيل الدخول.")
   states[chat] = 'idle'
  except SessionPasswordNeededError:
   states[chat] = {'state': 'awaiting_2fa', 'client': d['client'], 'phone': d['phone']}
   await event.reply("🔐 أرسل كلمة المرور:")

 elif isinstance(state, dict) and state.get('state') == 'awaiting_2fa':
  try:
   await state['client'].sign_in(password=txt)
   me = await state['client'].get_me()
   sessions[me.id] = (state['client'], me)
   if str(chat) not in user_sessions: user_sessions[str(chat)] = {}
   user_sessions[str(chat)][me.id] = (state['client'], me)
   await event.reply("✅ الدخول تم.")
   states[chat] = 'idle'
  except:
   await event.reply("❌ خطأ في كلمة المرور.")

 elif isinstance(state, dict) and state.get('state') == 'awaiting_send_text':
  states[chat] = {'state': 'awaiting_send_link', 'text': txt, 'mode': state['mode']}
  await event.reply("📥 الآن أرسل رابط المجموعة:")

 elif isinstance(state, dict) and state.get('state') == 'awaiting_send_link':
  cid = active_sessions.get(chat)
  if not cid or cid not in sessions: return
  client, _ = sessions[cid]
  text = decorate_arabic(state['text'])
  link = txt
  final_message = f"{text}\n\n📎 {link}"
  msg = await bot.send_message(chat, "✉️ بدء الإرسال: 0", buttons=[
    [Button.inline("✉️ إرسال (0)", b'stop_send')]
  ])
  msg_id = msg.id
  counters[chat]['send'] = 0
  stop_flags[chat] = False
  members = load_csv(SOURCE_FILE if state['mode'] == 'send' else FAILED_FILE)
  await send(chat, client, final_message, msg_id, members)
  states[chat] = 'idle'
  await menu(chat)

 elif state in ['collect', 'add']:
  cid = active_sessions.get(chat)
  if not cid or cid not in sessions: return
  client, _ = sessions[cid]
  counters[chat][state] = 0
  stop_flags[chat] = False
  msg = await bot.send_message(chat, "🔄 جاري العملية...", buttons=[
    [Button.inline(f"{'📥 جمع' if state=='collect' else '📤 إضافة'} (0)", f"stop_{state}".encode())]
  ])
  msg_id = msg.id
  if state == 'collect':
    await collect(chat, client, txt, msg_id)
  elif state == 'add':
    await add(chat, client, txt, msg_id)
  states[chat] = 'idle'
  await menu(chat)

async def send(chat, client, final_message, msg_id, members):
 added_ids = {x['user_id'] for x in load_csv(ADDED_FILE)}
 for m in members:
  if stop_flags.get(chat): break
  if m['user_id'] in added_ids: continue
  try:
   entity = await client.get_entity(int(m['user_id']))
   if getattr(entity, 'bot', False): continue
   user = InputPeerUser(int(entity.id), int(entity.access_hash))
   await client.send_message(user, final_message)
   save_csv_row(ADDED_FILE, m)
   remove_from_source(m['user_id'])
   counters[chat]['send'] += 1
   await bot.edit_message(chat, msg_id, "✉️ جاري الإرسال...", buttons=[
    [Button.inline(f"✉️ إرسال ({counters[chat]['send']})", b'stop_send')]
   ])
   await asyncio.sleep(random.randint(35, 55))
  except FloodWaitError as e:
   await bot.send_message(chat, f"🚫 محظور {e.seconds} ثانية")
   break
  except:
   save_csv_row(FAILED_FILE, m)
   remove_from_source(m['user_id'])
 await bot.send_message(chat, "✅ تم الانتهاء من الإرسال.")

async def collect(chat, client, group, msg_id):
 ensure_file(SOURCE_FILE)
 added = load_csv(ADDED_FILE)
 failed = load_csv(FAILED_FILE)
 existing_ids = {x['user_id'] for x in added + failed}
 try:
  entity = await client.get_entity(group)
 except:
  return await bot.send_message(chat, "❌ رابط غير صالح.")
 async for msg in client.iter_messages(entity, limit=1000):
  if stop_flags.get(chat): break
  if msg.sender_id and str(msg.sender_id) not in existing_ids:
   try:
    user = await client.get_entity(msg.sender_id)
    save_csv_row(SOURCE_FILE, {
     'username': user.username or '',
     'user_id': str(user.id),
     'access_hash': str(user.access_hash)
    })
    counters[chat]['collect'] += 1
    await bot.edit_message(chat, msg_id, "📥 جاري الجمع...", buttons=[
     [Button.inline(f"📥 جمع ({counters[chat]['collect']})", b'stop_collect')]
    ])
   except: continue
 await bot.send_message(chat, "✅ تم الانتهاء من الجمع.")

async def add(chat, client, group, msg_id):
 try:
  entity = await client.get_entity(group)
 except:
  return await bot.send_message(chat, "❌ رابط غير صالح.")
 members = load_csv(SOURCE_FILE)
 added_ids = {x['user_id'] for x in load_csv(ADDED_FILE)}
 failed_ids = {x['user_id'] for x in load_csv(FAILED_FILE)}
 for m in members:
  if stop_flags.get(chat): break
  if m['user_id'] in added_ids or m['user_id'] in failed_ids: continue
  try:
   user = InputPeerUser(int(m['user_id']), int(m['access_hash']))
   await client(InviteToChannelRequest(entity, [user]))
   save_csv_row(ADDED_FILE, m)
   remove_from_source(m['user_id'])
   counters[chat]['add'] += 1
   await bot.edit_message(chat, msg_id, "📤 جاري الإضافة...", buttons=[
    [Button.inline(f"📤 إضافة ({counters[chat]['add']})", b'stop_add')]
   ])
   await asyncio.sleep(random.randint(35, 55))
  except FloodWaitError as e:
   await bot.send_message(chat, f"🚫 محظور {e.seconds} ثانية")
   break
  except:
   save_csv_row(FAILED_FILE, m)
   remove_from_source(m['user_id'])
 await bot.send_message(chat, "✅ تم الانتهاء من الإضافة.")

if __name__ == '__main__':
 os.makedirs(SESSIONS_DIR, exist_ok=True)
 ensure_file(SOURCE_FILE)
 ensure_file(ADDED_FILE)
 ensure_file(FAILED_FILE)
 asyncio.get_event_loop().run_until_complete(load_existing_sessions())
 bot.run_until_disconnected()
