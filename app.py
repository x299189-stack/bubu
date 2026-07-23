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

        try:
            # 💡 獨立將 time_formatted 減 8 小時供 LINE 顯示使用
            dt_line = datetime.strptime(time_formatted, "%Y-%m-%d %H:%M") - timedelta(hours=8)
            line_time_str = dt_line.strftime("%Y-%m-%d %H:%M")
        except:
            line_time_str = time_formatted
        
        # 2. 🚀 自動推播通知到 LINE
        try:
            line_message = (
                f"📢 【新共乘預約通知】\n"
                f"👤 乘客：{name}\n"
                f"📞 電話：{phone}\n"
                f"📍 起點：{start}\n"
                f"🏁 目的地：{destination}\n"
                f"⏰ 時間：{line_time_str}\n\n"
                f"請各位志工司機確認是否有人能順路接送！"
            )
            target_id = "U0e2e5d60b807d9085e7c287c2d69d8c9"
            line_bot_api.push_message(target_id, TextSendMessage(text=line_message))
        except Exception as e:
            print(f"LINE 推播失敗: {e}")

        return f"感謝 {name}！您的共乘車預約已成功送達雲端試算表並已發送 LINE 通知。<br><br><a href='/carpool'>回共乘選單</a>"
    
    return render_template("booking.html")


# ================= 🔗 LINE Webhook 接收與互動 =================
# ================= 🔗 LINE Webhook 接收與互動 =================
@app.route("/callback", methods=['POST'])
def callback():
    try:
        # 嘗試正常處理
        signature = request.headers.get('X-Line-Signature', '')
        body = request.get_data(as_string=True)
        
        # 如果是 LINE 在做 Verify 測試，或有收到訊息，我們都印出來看看
        print(f"收到 LINE 請求 body: {body}")
        
        if body:
            handler.handle(body, signature)
    except Exception as e:
        print(f"發生例外但直接忽略: {e}")
    
    # 💡 無論如何，強制一定要回傳 200 OK 給 LINE 平台！
    return 'OK', 200

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


# 4. 預約紀錄與順風車頁面（加強防呆與時區對齊）
# 4. 預約紀錄與順風車頁面
@app.route("/carpool/records")
def carpool_records():
    records = []
    try:
        response = requests.get(GOOGLE_SCRIPT_URL)
        data = response.json()
        
        if isinstance(data, list):
            now_str = (datetime.now() - timedelta(hours=8)).strftime("%Y-%m-%d %H:%M")
            filtered_records = []
            
            # 💡 加上 enumerate(data, start=2) 來精準計算 Google 試算表的真實行號 (Row Index)
            for index, item in enumerate(data):
                if not isinstance(item, dict):
                    continue
                try:
                    raw_time = str(item.get("預約時間", ""))
                    
                    if "T" in raw_time:
                        clean_time = raw_time.replace("T", " ").split(".")[0].replace("Z", "")
                    else:
                        clean_time = raw_time
                        
                    standard_time = clean_time[:16]
                    
                    clean_item = {
                        "row_index": index + 2,  # 👈 把真實行號帶進去！(第1行是標題，資料從第2行開始)
                        "time": standard_time,
                        "name": str(item.get("姓名", "")),
                        "phone": str(item.get("電話", "")),
                        "start": str(item.get("上車地點", "")),
                        "destination": str(item.get("下車地點", "")),
                        "status": str(item.get("狀態", "待安排"))
                    }
                    
                    if len(standard_time) >= 16 and standard_time >= now_str:
                        filtered_records.append(clean_item)
                except Exception as inner_e:
                    print(f"單筆資料解析錯誤跳過: {inner_e}")
                    
            records = sorted(filtered_records, key=lambda x: x.get("time", ""))
            
    except Exception as e:
        print(f"讀取試算表失敗: {e}")
        records = []

    return render_template("records.html", records=records)
# 7. 司機接單 / 更新狀態路由
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


# 7-2. 乘客登記搭乘順風車路由
@app.route("/carpool/join", methods=["POST"])
def carpool_join():
    driver_trip_name = request.form.get("name")
    time_str = request.form.get("time")
    row_index = request.form.get("row_index")
    passenger_name = request.form.get("passenger_name", "熱心居民")
    
    status_text = f"已登記搭乘 (乘客: {passenger_name})"
    
    payload = {
        "action": "update_status",
        "sheet_name": "Bookings",
        "row_index": int(row_index) if row_index else None,
        "name": driver_trip_name,
        "time": time_str,
        "status": status_text,
        "is_join": True,
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
        
        payload = {
            "sheet_name": "Bookings",
            "timestamp": timestamp,
            "name": f"【司機】{driver_name}",
            "phone": driver_phone,
            "start": start,
            "destination": destination,
            "time": time_formatted,
            "status": f"可載人數:{seats}"
        }
        
        requests.post(GOOGLE_SCRIPT_URL, json=payload)

        try:
            dt_line = datetime.strptime(time_formatted, "%Y-%m-%d %H:%M") - timedelta(hours=8)
            line_time_str = dt_line.strftime("%Y-%m-%d %H:%M")
        except:
            line_time_str = time_formatted

        
        try:
            line_message = (
                f"🚙 【司機發布順風車通知】\n"
                f"👨‍✈️ 司機：{driver_name}\n"
                f"📞 電話：{driver_phone}\n"
                f"📍 起點：{start}\n"
                f"🏁 目的地：{destination}\n"
                f"⏰ 時間：{line_time_str}\n"
                f"💺 可載人數：{seats} 位\n\n"
                f"有需要的長輩或居民可以聯繫司機預約！"
            )
            target_id = "U0e2e5d60b807d9085e7c287c2d69d8c9"
            line_bot_api.push_message(target_id, TextSendMessage(text=line_message))
        except Exception as e:
            print(f"LINE 推播失敗: {e}")

        return f"感謝 {driver_name} 司機！您的順風車行程已成功發布並推播通知。<br><br><a href='/carpool'>回共乘選單</a>"
    
    return render_template("driver_booking.html")

# 6. GPS 即時現況頁面
live_drivers_locations = {}

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

@app.route("/carpool/api/locations")
def api_locations():
    return jsonify(live_drivers_locations)

@app.route("/carpool/driver_gps")
def driver_gps():
    return render_template("driver_gps.html")

@app.route("/carpool/live_map")
def live_map():
    return render_template("live_map.html")

@app.route("/carpool/gps")
def carpool_gps():
    return render_template("carpool_gps.html")


if __name__ == "__main__":
    app.run(debug=True)