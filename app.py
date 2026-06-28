import os
import re
import base64
import requests
import urllib3
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage, QuickReply, QuickReplyButton, MessageAction

# ปิดแจ้งเตือนเรื่อง SSL Certificate ของเว็บรัฐ
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)

# ระบบจัดเก็บสถานะ
user_states = {}

# ตั้งค่า LINE API Keys
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get('LINE_CHANNEL_ACCESS_TOKEN', 'ใส่_CHANNEL_ACCESS_TOKEN_ของคุณที่นี่')
LINE_CHANNEL_SECRET = os.environ.get('LINE_CHANNEL_SECRET', 'ใส่_CHANNEL_SECRET_ของคุณที่นี่')

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

def extract_and_decode(text):
    """ ถอดรหัส qrcodeToken """
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
    """ ยิง API ไปที่ระบบ LandsMaps พร้อมส่ง Error กลับมาวิเคราะห์ """
    api_url = "https://landsmaps.dol.go.th/api/getParcelData" 
    payload = {
        "provid": provid,
        "amphurid": amphurid,
        "parcelno": parcelno
    }
    
    # ใช้ Session เพื่อเก็บ Cookie จำลองการเข้าเว็บจริงๆ แบบต่อเนื่อง
    session = requests.Session()
    
    # Header ชุดใหญ่เพื่อหลอก Firewall
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://landsmaps.dol.go.th/",
        "Origin": "https://landsmaps.dol.go.th",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "th-TH,th;q=0.9,en-US;q=0.8,en;q=0.7",
        "X-Requested-With": "XMLHttpRequest", # บ่งบอกว่าเป็น AJAX Request สำคัญมาก
        "Connection": "keep-alive",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin"
    }
    
    try:
        # 1. แกล้งเข้าไปที่หน้าแรกของเว็บก่อน 1 ครั้ง เพื่อให้ได้ Session/Cookie จาก Firewall
        session.get("https://landsmaps.dol.go.th/", headers={"User-Agent": headers["User-Agent"]}, timeout=10, verify=False)
        
        # 2. ยิง API ขอดึงข้อมูล โดยพก Cookie และ Header ชุดใหญ่ไปด้วย
        response = session.get(api_url, params=payload, headers=headers, timeout=15, verify=False)
        
        if response.status_code == 200:
            try:
                return response.json(), None
            except ValueError:
                # กรณีที่ระบบไม่ได้ตอบกลับเป็น JSON (อาจจะติดหน้า Firewall)
                return None, f"ระบบไม่ได้คืนค่าเป็น JSON (อาจติด Firewall):\n{response.text[:150]}..."
        else:
            return None, f"HTTP Error {response.status_code}:\n{response.text[:150]}..."
            
    except requests.exceptions.Timeout:
        return None, "Connection Timeout: เซิร์ฟเวอร์กรมที่ดินตอบสนองช้าเกินไป"
    except Exception as e:
        return None, f"Connection Error: {str(e)}"

@app.route("/webhook", methods=['POST'])
def callback():
    """ Webhook สำหรับรับข้อมูลจาก LINE """
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    """ จัดการข้อความที่ส่งมา """
    user_text = event.message.text.strip()
    user_id = event.source.user_id
    
    # เช็คว่าส่งลิงก์มาหรือไม่
    if "qrcodeToken=" in user_text or len(user_text) > 20: 
        provid, amphurid, parcelno = extract_and_decode(user_text)
        if provid:
            reply_api_data(event.reply_token, provid, amphurid, parcelno)
            return

    state = user_states.get(user_id, {"step": 0})

    if state["step"] == 0 or user_text == "เมนู":
        send_menu(event.reply_token)
        user_states[user_id] = {"step": 1}

    elif state["step"] == 1:
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
        parts = user_text.split(',')
        if len(parts) == 2 and parts[0].strip().isdigit() and parts[1].strip().isdigit():
            provid = parts[0].strip()
            amphurid = parts[1].strip()
            user_states[user_id] = {"step": 3, "provid": provid, "amphurid": amphurid}
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"✅ ตั้งค่าพื้นที่: จ.{provid} อ.{amphurid} สำเร็จ\n\n📝 ขั้นสอง: กรุณาพิมพ์ 'เลขโฉนด' ที่ต้องการค้นหาครับ"))
        else:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="❌ รูปแบบไม่ถูกต้อง กรุณาพิมพ์ใหม่ให้ถูกต้อง (เช่น 30,21)"))

    elif state["step"] == 3:
        parcelno = user_text
        provid = state["provid"]
        amphurid = state["amphurid"]
        reply_api_data(event.reply_token, provid, amphurid, parcelno)
        user_states.pop(user_id, None)

def send_menu(reply_token):
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
    parcel_data, error_msg = fetch_parcel_data(provid, amphurid, parcelno)
    
    if parcel_data:
        # ป้องกันกรณีที่ API อาจคืนค่ากลับมาเป็น List 
        data = parcel_data[0] if isinstance(parcel_data, list) and len(parcel_data) > 0 else parcel_data
        
        # สร้างลิงก์ LandsMaps ด้วยการเข้ารหัส Base64 ของ provid,amphurid,parcelno
        token_string = f"{provid},{amphurid},{parcelno}"
        token_base64 = base64.b64encode(token_string.encode('utf-8')).decode('utf-8')
        landsmaps_url = f"https://landsmaps.dol.go.th?qrcodeToken={token_base64}"
        
        # ดึงค่าต่างๆ ออกมาจาก JSON (ปรับปรุงชื่อฟิลด์ให้ตรงตามที่ LandsMaps มักจะใช้)
        rawang = data.get('rawang', '-') 
        tambon = data.get('tambonName', '-') 
        amphur = data.get('amphurName', '-')
        province = data.get('provinceName', '-')
        rai = data.get('rai', '0')
        ngan = data.get('ngan', '0')
        wa = data.get('wa', '0')
        price = data.get('price', '-') 
        
        # พิกัดแปลง
        lat = data.get('lat', '') 
        lon = data.get('lon', '')
        
        if lat and lon:
            google_maps_url = f"https://www.google.com/maps?q={lat},{lon}"
            location_display = f"{lat},{lon}\n({google_maps_url})"
        else:
            location_display = "-"
            
        reply_text = (
            f"✅ ดึงข้อมูลสำเร็จ\n\n"
            f"ลิ้งแปลงที่ดิน :\n{landsmaps_url}\n\n"
            f"ระวาง : {rawang}\n"
            f"ตำบล : {tambon}\n"
            f"อำเภอ : {amphur}\n"
            f"จังหวัด : {province}\n"
            f"เนื้อที่ : {rai} ไร่ {ngan} งาน {wa} ตารางวา\n"
            f"ราคาประเมินที่ดิน : {price} บาท/ตร.วา\n"
            f"ค่าพิกัดแปลง : {location_display}\n"
            f"----------------------\n"
            f"หากต้องการค้นหาที่อื่นต่อ ให้พิมพ์ 'เมนู'"
        )
    else:
        reply_text = (
            f"❌ ไม่พบข้อมูล หรือไม่สามารถเชื่อมต่อระบบ LandsMaps ได้\n"
            f"(จังหวัด: {provid}, อำเภอ: {amphurid}, เลขโฉนด: {parcelno})\n\n"
            f"🔍 ข้อมูลทางเทคนิค (สำหรับตรวจสอบ):\n{error_msg}\n\n"
            f"หากต้องการค้นหาใหม่ ให้พิมพ์ 'เมนู'"
        )
    
    line_bot_api.reply_message(reply_token, TextSendMessage(text=reply_text))

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
