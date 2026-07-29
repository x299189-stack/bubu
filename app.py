from flask import Flask, render_template, request, abort, jsonify, redirect
import requests
from datetime import datetime, timedelta
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
import os
from datetime import datetime

app = Flask(__name__)

# Google Apps Script 雲端試算表網址
GOOGLE_SCRIPT_URL = "https://script.google.com/macros/s/AKfycby2Or4mWl1AAXr1U5znLGmTIdk5KuCtItnkxo2r62-JmmeJEKpia-aGyhMoRIsiYdlR/exec"

# ===========================================================================================================
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get('LINE_CHANNEL_ACCESS_TOKEN', '你的預設測試Token')
LINE_CHANNEL_SECRET = os.environ.get('LINE_CHANNEL_SECRET', '你的預設測試Secret')

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)
# ============================================================================================================

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
            target_id = "C70557a44f442c71e59e0ddb586b92c3a"
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
        target_id = "C70557a44f442c71e59e0ddb586b92c3a"
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
        target_id = "C70557a44f442c71e59e0ddb586b92c3a"
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
            target_id = "C70557a44f442c71e59e0ddb586b92c3a"
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
        tw_time = datetime.now() + timedelta(hours=8)
        live_drivers_locations[driver_name] = {
            "lat": float(lat),
            "lng": float(lng),
            "car_plate": car_plate,
            "time": tw_time.strftime("%H:%M:%S")
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

@app.route("/carpool/remove_location", methods=["POST"])
def remove_location():
    data = request.json
    driver_name = data.get("driver_name")
    if driver_name in live_drivers_locations:
        del live_drivers_locations[driver_name]
        return jsonify({"status": "success"})
    return jsonify({"status": "fail"}), 400

# 8-1. 顯示行事曆頁面與讀取活動
@app.route("/calendar")
def community_calendar():
    events = []
    try:
        # 記得帶入參數讀取 calender 分頁
        response = requests.get(GOOGLE_SCRIPT_URL + "?sheet=calender")
        data = response.json()
        
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict) and item.get("type") == "event":
                    time_str = str(item.get("time", ""))
                    
                    # --- 1. 把醜醜的時間字串變漂亮 ---
                    dt = None
                    display_time = time_str
                    try:
                        # 處理 '2027-12-14T17:00:00.000Z' 這種格式
                        if "T" in time_str:
                            # 拔掉小數點 .000Z 並把 T 換成空白
                            clean_time = time_str.split(".")[0].replace("T", " ")
                            if clean_time.count(":") == 2:
                                dt = datetime.strptime(clean_time, "%Y-%m-%d %H:%M:%S")
                            else:
                                dt = datetime.strptime(clean_time, "%Y-%m-%d %H:%M")
                            # 轉換成乾淨的顯示格式
                            dt = dt + timedelta(hours=8)
                            display_time = dt.strftime("%Y-%m-%d %H:%M")
                    except Exception:
                        # 如果出錯，就單純取代 T 讓它稍微好看一點
                        display_time = time_str.replace("T", " ").split(".")[0]
                    
                    events.append({
                        "time": display_time,
                        "title": item.get("title", ""),
                        "location": item.get("location", ""),
                        "description": item.get("description", ""),
                        "_dt": dt # 這個隱藏欄位用來給 Python 排序用
                    })
    except Exception as e:
        print(f"讀取行事曆失敗: {e}")

    # --- 2. 進行排序：未來的放上面，過去的沉底 ---
    now = datetime.now()
    future_events = []
    past_events = []
    
    for e in events:
        if e["_dt"]:
            # 判斷活動是否還沒過期
            if e["_dt"] >= now:
                future_events.append(e)
            else:
                # 活動時間小於現在，代表過期了
                # 幫過期的活動標題加上 [已結束] 提示
                e["title"] = "[已結束] " + e["title"]
                past_events.append(e)
        else:
            # 無法解析時間的預設放上面
            future_events.append(e)
            
    # 未來活動：由近到遠排序 (時間越近的越在上面)
    future_events.sort(key=lambda x: x["_dt"] if x["_dt"] else datetime.max)
    
    # 過去活動：由新到舊排序 (剛結束的在上面，很久以前的沉到最底)
    past_events.sort(key=lambda x: x["_dt"], reverse=True)
    
    # 將未來與過去的活動合併成一個清單
    sorted_events = future_events + past_events
        
    return render_template("calendar.html", events=sorted_events)
# 8-2. 接收新增活動表單與密碼驗證
@app.route("/calendar/add", methods=["POST"])
def add_calendar_event():
    # 🔐 設定你的管理員密碼
    ADMIN_PASSWORD = "1234" 
    
    password = request.form.get("admin_password")
    
    # 檢查密碼是否正確
    if password != ADMIN_PASSWORD:
        return "❌ 密碼錯誤！無法新增活動。<br><br><a href='/calendar'>回行事曆</a>"
    
    # 密碼正確，取得表單資料
    time_str = request.form.get("time")
    title = request.form.get("title")
    location = request.form.get("location")
    description = request.form.get("description")
    
    payload = {
        "action": "add_event",
        "type": "event",
        "time": time_str,
        "title": title,
        "location": location,
        "description": description
    }
    
    try:
        # 寫入 Google 試算表
        requests.post(GOOGLE_SCRIPT_URL, json=payload)
    except Exception as e:
        print(f"寫入行事曆失敗: {e}")
        
    return f"✅ 成功新增活動：{title}！<br><br><a href='/calendar'>回行事曆列表</a>"

# 9. 物資共享路由
@app.route("/sharing")
def community_sharing():
    # 從網址取得 LINE user_id，如果沒有就給個預設的訪客代號
    user_id = request.args.get("user_id", "GUEST_USER")
    
    items = []
    try:
        # 讀取 Google 試算表的 sharing 分頁
        response = requests.get(GOOGLE_SCRIPT_URL + "?sheet=sharing", timeout=20)
        data = response.json()
        
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict) and item.get("type") == "sharing_item":
                    items.append({
                        "provider_name": item.get("provider_name", ""),
                        "item_name": item.get("item_name", ""),
                        "want_item": item.get("want_item", ""),
                        "contact": item.get("contact", ""),
                        "user_id": item.get("user_id", ""),
                        "status": item.get("status", "架上交換中") # 👈 順便確保有讀到狀態
                    })
        
        # 👑 最關鍵的一步：直接用迴圈強制編號「真實行數」(從第 2 行開始)
        for index, item in enumerate(items):
            item["row_index"] = index + 2

    except Exception as e:
        print(f"讀取物資共享失敗: {e}")
        
    return render_template("sharing.html", items=items, user_id=user_id)
# 9-2. 接收里民上架物資的表單
@app.route("/sharing/add", methods=["POST"])
def add_sharing_item():
    user_id = request.form.get("user_id")
    provider_name = request.form.get("provider_name")
    item_name = request.form.get("item_name")
    want_item = request.form.get("want_item")
    contact = request.form.get("contact")
    
    payload = {
        "action": "add_sharing",
        "type": "sharing_item",
        "user_id": user_id,
        "provider_name": provider_name,
        "item_name": item_name,
        "want_item": want_item,
        "contact": contact
    }
    
    try:
        # 將資料送給 Google Apps Script 寫入試算表
        requests.post(GOOGLE_SCRIPT_URL, json=payload, timeout=15)
    except Exception as e:
        print(f"寫入物資失敗: {e}")
        
    return f"✅ 成功上架交換物資：{item_name}！<br><br><a href='/sharing?user_id={user_id}'>回物資共享列表</a>"

# 9-3. 更新物資狀態的路由
@app.route("/sharing/update_status", methods=["POST"])
def update_sharing_status():
    row_index = request.form.get("row_index")
    new_status = request.form.get("new_status")
    user_id = request.form.get("user_id")
    
    print(f"收到更新請求 -> 行數: {row_index}, 新狀態: {new_status}")
    
    # 確保 row_index 存在且可以轉成整數
    try:
        row_idx_int = int(row_index) if row_index else None
    except ValueError:
        row_idx_int = None

    payload = {
        "action": "update_sharing_status",
        "row_index": row_idx_int,
        "new_status": new_status
    }
    
    try:
        response = requests.post(GOOGLE_SCRIPT_URL, json=payload, timeout=15)
        print(f"GAS 回應: {response.text}")
    except Exception as e:
        print(f"更新物資狀態失敗: {e}")
        
    return redirect(f"/sharing?user_id={user_id}")

if __name__ == "__main__":
    app.run(debug=True)