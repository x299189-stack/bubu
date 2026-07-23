from flask import Flask, render_template, request, abort, jsonify
import requests
from datetime import datetime, timedelta
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
import os

app = Flask(__name__)

# Google Apps Script 雲端試算表網址
GOOGLE_SCRIPT_URL = "https://script.google.com/macros/s/AKfycby2Or4mWl1AAXr1U5znLGmTIdk5KuCtItnkxo2r62-JmmeJEKpia-aGyhMoRIsiYdlR/exec"

# ================= 🚀 LINE 機器人正式金鑰 =================
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get('LINE_CHANNEL_ACCESS_TOKEN', '你的預設測試Token')
LINE_CHANNEL_SECRET = os.environ.get('LINE_CHANNEL_SECRET', '你的預設測試Secret')

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)
# ===================================================

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/carpool")
def carpool_menu():
    return render_template("carpool_menu.html")

@app.route("/carpool/book", methods=["GET", "POST"])
def carpool_book():
    if request.method == "POST":
        name = request.form.get("name")
        phone = request.form.get("phone")
        start = request.form.get("start")
        destination = request.form.get("destination")
        time_str = request.form.get("time")
        
        if time_str:
            dt = datetime.fromisoformat(time_str.replace("Z", ""))
            dt_tw = dt + timedelta(hours=8)
            time_formatted = dt_tw.strftime("%Y-%m-%d %H:%M")
        else:
            time_formatted = time_str

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        payload = {
            "timestamp": timestamp,
            "name": name,
            "phone": phone,
            "start": start,
            "destination": destination,
            "time": time_formatted,
            "status": "待安排"
        }
        
        # 1. 寫入 Google 試算表
        requests.post(GOOGLE_SCRIPT_URL, json=payload)
        
        # 2. 🚀 自動推播通知到 LINE
        try:
            line_message = (
                f"📢 【新共乘預約通知】\n"
                f"👤 乘客：{name}\n"
                f"📞 電話：{phone}\n"
                f"📍 起點：{start}\n"
                f"🏁 目的地：{destination}\n"
                f"⏰ 時間：{time_formatted}\n\n"
                f"請各位志工司機確認是否有人能順路接送！"
            )
            # 目前設定為你的個人 User ID 進行測試推播
            target_id = "U0e2e5d60b807d9085e7c287c2d69d8c9"
            line_bot_api.push_message(target_id, TextSendMessage(text=line_message))
        except Exception as e:
            print(f"LINE 推播失敗: {e}")

        return f"感謝 {name}！您的共乘車預約已成功送達雲端試算表並已發送 LINE 通知。<br><br><a href='/carpool'>回共乘選單</a>"
    
    return render_template("booking.html")


# ================= 🔗 LINE Webhook 接收與互動 =================
@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_string=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    # 安全取得來源 ID（支援群組或個人）
    if isinstance(event.source.group_id, str):
        source_id = event.source.group_id
    elif isinstance(event.source.room_id, str):
        source_id = event.source.room_id
    else:
        source_id = event.source.user_id
    
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=f"目前的聊天室/用戶 ID 是: {source_id}")
    )
# =============================================================


# 4. 預約紀錄與順風車頁面
@app.route("/carpool/records")
def carpool_records():
    try:
        response = requests.get(GOOGLE_SCRIPT_URL)
        records = response.json()
        
        now_str = (datetime.now() + timedelta(hours=8)).strftime("%Y-%m-%d %H:%M")
        filtered_records = []
        
        for item in records:
            raw_time = str(item.get("預約時間", ""))
            
            if "T" in raw_time:
                clean_time = raw_time.replace("T", " ").split(".")[0].replace("Z", "")
            else:
                clean_time = raw_time
                
            standard_time = clean_time[:16]
            
            # 💡 確保每一欄的中文都正確對應到前端變數！
            item["time"] = standard_time
            item["name"] = item.get("姓名", "")
            item["phone"] = item.get("電話", "")
            item["start"] = item.get("上車地點", "")         # 確保抓到上車地點
            item["destination"] = item.get("下車地點", "") # 確保抓到下車地點
            item["status"] = item.get("狀態", "待安排")
            
            # 保留 Google 試算表的真實行號供接單更新使用
            # (如果 GAS 回傳的 row_index 存在就用它)
            
            if standard_time >= now_str:
                filtered_records.append(item)
                
        records = sorted(filtered_records, key=lambda x: x.get("time", ""))
        
    except Exception as e:
        print(f"讀取試算表失敗: {e}")
        records = []

    return render_template("records.html", records=records)
####################################################################
# 7. 司機接單 / 更新狀態路由
# 7-1. 司機接單路由（原有）
@app.route("/carpool/accept", methods=["POST"])
def carpool_accept():
    name = request.form.get("name")
    time_str = request.form.get("time")
    row_index = request.form.get("row_index")
    driver_name = request.form.get("driver_name", "熱心志工")
    car_plate = request.form.get("car_plate", "未填車牌")
    seats = request.form.get("seats", "3")
    
    status_text = f"已安排 (司機: {driver_name}, 車牌: {car_plate}, 可載: {seats}人)"
    
    payload = {
        "action": "update_status",
        "sheet_name": "Bookings",
        "row_index": int(row_index) if row_index else None,
        "name": name,
        "time": time_str,
        "status": status_text
    }
    
    try:
        requests.post(GOOGLE_SCRIPT_URL, json=payload)
        line_message = (
            f"✅ 【共乘預約已被認領】\n"
            f"👤 乘客：{name}\n"
            f"⏰ 時間：{time_str}\n"
            f"👨‍✈️ 認領司機：{driver_name}\n"
            f"🚙 車牌號碼：{car_plate}\n"
            f"💺 可載人數：{seats} 人\n\n"
            f"感謝司機熱心協助！"
        )
        target_id = "U0e2e5d60b807d9085e7c287c2d69d8c9"
        line_bot_api.push_message(target_id, TextSendMessage(text=line_message))
    except Exception as e:
        print(f"接單更新失敗: {e}")
        
    return f"成功為 {name} 的行程接單！<br><br><a href='/carpool/records'>回預約紀錄列表</a>"


# 7-2. 🆕 乘客登記搭乘順風車路由
@app.route("/carpool/join", methods=["POST"])
def carpool_join():
    driver_trip_name = request.form.get("name")
    time_str = request.form.get("time")
    row_index = request.form.get("row_index")
    passenger_name = request.form.get("passenger_name", "熱心居民")
    
    # 組合新狀態文字
    status_text = f"已登記搭乘 (乘客: {passenger_name})"
    
    payload = {
        "action": "update_status",
        "sheet_name": "Bookings",
        "row_index": int(row_index) if row_index else None,
        "name": driver_trip_name,
        "time": time_str,
        "status": status_text,
        "is_join": True,  # 👈 加上這個標記讓 GAS 知道要累加
        "passenger_name": passenger_name
    }
    
    try:
        requests.post(GOOGLE_SCRIPT_URL, json=payload)
        line_message = (
            f"🙋‍♂️ 【有人登記搭乘順風車】\n"
            f"🚗 行程：{driver_trip_name}\n"
            f"⏰ 時間：{time_str}\n"
            f"👤 登記搭乘者：{passenger_name}\n\n"
            f"請司機與乘客互相聯繫！"
        )
        target_id = "U0e2e5d60b807d9085e7c287c2d69d8c9"
        line_bot_api.push_message(target_id, TextSendMessage(text=line_message))
    except Exception as e:
        print(f"登記搭車失敗: {e}")
        
    return f"成功登記搭乘！已通知司機。<br><br><a href='/carpool/records'>回預約紀錄列表</a>"
###################################################################
# 5. 司機開放共乘頁面
# 5. 司機開放共乘頁面
# 5. 司機開放共乘頁面
@app.route("/carpool/driver", methods=["GET", "POST"])
def carpool_driver():
    if request.method == "POST":
        driver_name = request.form.get("driver_name")
        driver_phone = request.form.get("driver_phone")
        start = request.form.get("start")
        destination = request.form.get("destination")
        time_str = request.form.get("time")
        seats = request.form.get("seats")
        
        if time_str:
            dt = datetime.fromisoformat(time_str.replace("Z", ""))
            dt_tw = dt + timedelta(hours=8)
            time_formatted = dt_tw.strftime("%Y-%m-%d %H:%M")
        else:
            time_formatted = time_str

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # ==========================================
        # 💡 關鍵修改區：寫回 Bookings，並加上【司機】標籤
        # ==========================================
        payload = {
            "sheet_name": "Bookings",  # 👈 寫回 Bookings，讓清單統一抓取！
            "timestamp": timestamp,
            "name": f"【司機】{driver_name}", # 👈 加上標籤，清單上一目了然
            "phone": driver_phone,
            "start": start,
            "destination": destination,
            "time": time_formatted,
            "status": f"可載人數:{seats}"
        }
        
        # 1. 寫入 Google 試算表
        requests.post(GOOGLE_SCRIPT_URL, json=payload)
        
        # 2. 🚀 自動推播通知到 LINE
        try:
            line_message = (
                f"🚙 【司機發布順風車通知】\n"
                f"👨‍✈️ 司機：{driver_name}\n"
                f"📞 電話：{driver_phone}\n"
                f"📍 起點：{start}\n"
                f"🏁 目的地：{destination}\n"
                f"⏰ 時間：{time_formatted}\n"
                f"💺 可載人數：{seats} 位\n\n"
                f"有需要的長輩或居民可以聯繫司機預約！"
            )
            target_id = "U0e2e5d60b807d9085e7c287c2d69d8c9" # 你的測試 ID
            line_bot_api.push_message(target_id, TextSendMessage(text=line_message))
        except Exception as e:
            print(f"LINE 推播失敗: {e}")

        return f"感謝 {driver_name} 司機！您的順風車行程已成功發布並推播通知。<br><br><a href='/carpool'>回共乘選單</a>"
    
    return render_template("driver_booking.html")
# 6. GPS 即時現況頁面
# 記憶體字典，用來暫存目前在線司機的即時位置
# 記憶體字典，用來暫存目前在線司機的即時位置
live_drivers_locations = {}

# 1. 接收司機手機回報 GPS 位置的路由
@app.route("/carpool/update_location", methods=["POST"])
def update_location():
    data = request.json
    driver_name = data.get("driver_name")
    lat = data.get("lat")
    lng = data.get("lng")
    car_plate = data.get("car_plate", "未填車牌")
    
    if driver_name and lat and lng:
        live_drivers_locations[driver_name] = {
            "lat": float(lat),
            "lng": float(lng),
            "car_plate": car_plate,
            "time": datetime.now().strftime("%H:%M:%S")
        }
        return jsonify({"status": "success"})
    return jsonify({"status": "fail"}), 400

# 2. 提供給前端地圖抓取所有司機位置的 API
@app.route("/carpool/api/locations")
def api_locations():
    return jsonify(live_drivers_locations)

# 3. 司機回報定位頁面
@app.route("/carpool/driver_gps")
def driver_gps():
    return render_template("driver_gps.html")

# 4. 即時地圖看板頁面
@app.route("/carpool/live_map")
def live_map():
    return render_template("live_map.html")

# 5. 共乘現況選擇頁面（連接選單按鈕）
@app.route("/carpool/gps")
def carpool_gps():
    return render_template("carpool_gps.html")


if __name__ == "__main__":
    app.run(debug=True)