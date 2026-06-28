# สคริปต์สำหรับ LINE Bot (Python + Flask)
# สิ่งที่ต้องติดตั้ง: pip install flask line-bot-sdk requests

import os
import re
import base64
import requests
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage, QuickReply, QuickReplyButton, MessageAction

app = Flask(__name__)

# ==========================================
# เพิ่มระบบจัดเก็บสถานะ (State) การใช้งานของแต่ละบุคคล (แยกตาม User ID)
# หมายเหตุ: ในโปรเจกต์สเกลใหญ่ ควรใช้ Database (เช่น Redis) แต่สำหรับการเริ่มต้น ใช้ Dictionary ในหน่วยความจำได้ครับ
# ==========================================
user_states = {}

# ==========================================
# 1. ตั้งค่า LINE API Keys (เอามาจาก LINE Developers Console)
# ==========================================
# ในการใช้งานจริง แนะนำให้ตั้งเป็น Environment Variables แทนการใส่ค่าตรงๆ ในโค้ด
#LINE_CHANNEL_ACCESS_TOKEN = os.environ.get('W02MmWStdnN0adL6Gg3d0XQ2Pn2Sen1FgUhEchrgJEiOY1MWmbCs/zXo2U5CgzEM8SJXujGe/iR8g2GZWAUIUrfOj2i1nalcOzFSWhIFoStH2Y7pI0msGP1r/4RKi00rhYdJxrq45/Pv6XH9FH9PaAdB04t89/1O/w1cDnyilFU=')
#LINE_CHANNEL_SECRET = os.environ.get('f73369e3afd0c6ddd500c10046812868')
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get('LINE_CHANNEL_ACCESS_TOKEN', 'ใส่_CHANNEL_ACCESS_TOKEN_ของคุณที่นี่')
LINE_CHANNEL_SECRET = os.environ.get('LINE_CHANNEL_SECRET', 'ใส่_CHANNEL_SECRET_ของคุณที่นี่')

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

# ==========================================
# 2. ฟังก์ชันถอดรหัสและดึงข้อมูลจาก LandsMaps
# ==========================================
def extract_and_decode(text):
    """ ค้นหา qrcodeToken จากข้อความและถอดรหัส """
    # ถอดจาก URL กรณีที่ส่งมาเป็นลิงก์เต็ม
    match = re.search(r'qrcodeToken=([A-Za-z0-9+/=]+)', text)
    token = match.group(1) if match else text.strip()
    
    try:
        decoded_bytes = base64.b64decode(token)
        decoded_str = decoded_bytes.decode('utf-8')
        parts = decoded_str.split(',')
        if len(parts) == 3:
            return parts[0].strip(), parts[1].strip(), parts[2].strip()
    except Exception:
        return None, None, None
    return None, None, None

def fetch_parcel_data(provid, amphurid, parcelno):
    """ ยิง API ไปที่ระบบ LandsMaps """
    api_url = "https://landsmaps.dol.go.th/api/getParcelData" 
    payload = {
        "provid": provid,
        "amphurid": amphurid,
        "parcelno": parcelno
    }
headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://landsmaps.dol.go.th/",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "th-TH,th;q=0.9,en-US;q=0.8,en;q=0.7",
        "Connection": "keep-alive"
    }
    
    try:
        response = requests.get(api_url, params=payload, headers=headers, timeout=10)
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        print(f"API Error: {e}")
    return None

# ==========================================
# 3. สร้าง Webhook สำหรับรับข้อความจาก LINE
# ==========================================
@app.route("/webhook", methods=['POST'])
def callback():
    # รับ signature จาก Header เพื่อยืนยันว่า LINE เป็นคนส่งมา
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

# ==========================================
# 4. จัดการข้อความที่ส่งเข้ามาใน Bot (อัปเดตใหม่เป็น Step-by-Step)
# ==========================================
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_text = event.message.text.strip()
    user_id = event.source.user_id
    
    # ถ้าระบบตรวจพบลิงก์ qrcodeToken ให้ทำงานแบบเดิมทันที (ลัดคิว)
    if "qrcodeToken=" in user_text or len(user_text) > 20: 
        provid, amphurid, parcelno = extract_and_decode(user_text)
        if provid:
            reply_api_data(event.reply_token, provid, amphurid, parcelno)
            return

    # ดึงสถานะปัจจุบันของผู้ใช้ (ถ้าไม่มีให้เริ่มที่ step 0)
    state = user_states.get(user_id, {"step": 0})

    if state["step"] == 0 or user_text == "เมนู":
        # ขั้นที่ 0 -> ส่งเมนูให้เลือก
        send_menu(event.reply_token)
        user_states[user_id] = {"step": 1}

    elif state["step"] == 1:
        # ขั้นที่ 1 -> รับค่าตัวเลือกพื้นที่ 1, 2, หรือ 3
        if user_text == "1":
            user_states[user_id] = {"step": 3, "provid": "30", "amphurid": "21"}
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="✅ เลือก: อ.ปากช่อง จ.นครราชสีมา\n\n📝 ขั้นสอง: กรุณาพิมพ์ 'เลขโฉนด' ที่ต้องการค้นหาครับ"))
        elif user_text == "2":
            user_states[user_id] = {"step": 3, "provid": "71", "amphurid": "10"}
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="✅ เลือก: อ.เลาขวัญ จ.กาญจนบุรี\n\n📝 ขั้นสอง: กรุณาพิมพ์ 'เลขโฉนด' ที่ต้องการค้นหาครับ"))
        elif user_text == "3":
            user_states[user_id] = {"step": 2}
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="⚙️ เลือก: ตั้งค่าเอง\n\n📝 กรุณาพิมพ์ 'รหัสจังหวัด,รหัสอำเภอ' (คั่นด้วยลูกน้ำ)\n👉 ตัวอย่าง: 30,21"))
        else:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="❌ เลือกไม่ถูกต้อง กรุณาพิมพ์ 1, 2 หรือ 3 ครับ"))

    elif state["step"] == 2:
        # ขั้นที่ 2 -> กรณีตั้งค่าเอง รับค่า (provid, amphurid)
        parts = user_text.split(',')
        if len(parts) == 2 and parts[0].strip().isdigit() and parts[1].strip().isdigit():
            provid = parts[0].strip()
            amphurid = parts[1].strip()
            user_states[user_id] = {"step": 3, "provid": provid, "amphurid": amphurid}
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"✅ ตั้งค่าพื้นที่: จ.{provid} อ.{amphurid} สำเร็จ\n\n📝 ขั้นสอง: กรุณาพิมพ์ 'เลขโฉนด' ที่ต้องการค้นหาครับ"))
        else:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="❌ รูปแบบไม่ถูกต้อง กรุณาพิมพ์ใหม่ให้ถูกต้อง (เช่น 30,21)"))

    elif state["step"] == 3:
        # ขั้นที่ 3 -> รับค่าเลขโฉนด แล้วยิง API ดึงข้อมูล
        parcelno = user_text
        provid = state["provid"]
        amphurid = state["amphurid"]
        
        # เรียกฟังก์ชันยิง API และตอบกลับ
        reply_api_data(event.reply_token, provid, amphurid, parcelno)
        
        # เคลียร์ State กลับไปเริ่มต้นใหม่ (ให้พร้อมสำหรับการค้นหาครั้งต่อไป)
        user_states.pop(user_id, None)

def send_menu(reply_token):
    """ ส่งเมนูตัวเลือก (เพิ่ม Quick Reply Button ให้กดจากหน้าจอมือถือได้เลย) """
    text_message = TextSendMessage(
        text="ขั้นแรก: เลือกพื้นที่ที่ต้องการค้นหา 👇",
        quick_reply=QuickReply(items=[
            QuickReplyButton(action=MessageAction(label="1. ปากช่อง โคราช", text="1")),
            QuickReplyButton(action=MessageAction(label="2. เลาขวัญ กาญฯ", text="2")),
            QuickReplyButton(action=MessageAction(label="3. ตั้งค่าเอง", text="3"))
        ])
    )
    line_bot_api.reply_message(reply_token, text_message)

def reply_api_data(reply_token, provid, amphurid, parcelno):
    """ ยิง API ไปที่ระบบ LandsMaps และสร้างข้อความตอบกลับ """
    parcel_data = fetch_parcel_data(provid, amphurid, parcelno)
    
    if parcel_data:
        reply_text = (
            f"✅ ดึงข้อมูลสำเร็จ\n\n"
            f"📍 จังหวัด: {provid}\n"
            f"📍 อำเภอ: {amphurid}\n"
            f"📄 เลขโฉนด: {parcelno}\n"
            f"----------------------\n"
            f"หากต้องการค้นหาที่อื่นต่อ ให้พิมพ์ 'เมนู'"
        )
    else:
        reply_text = (
            f"❌ ไม่พบข้อมูล หรือไม่สามารถเชื่อมต่อระบบ LandsMaps ได้\n"
            f"(จังหวัด: {provid}, อำเภอ: {amphurid}, เลขโฉนด: {parcelno})\n\n"
            f"หากต้องการค้นหาใหม่ ให้พิมพ์ 'เมนู'"
        )
    
    line_bot_api.reply_message(reply_token, TextSendMessage(text=reply_text))

if __name__ == "__main__":
    # รันเซิร์ฟเวอร์
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
