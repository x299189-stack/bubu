from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage

app = Flask(__name__)

# 這裡之後會填入你們從 LINE 開發者後台拿到的金鑰
LINE_CHANNEL_ACCESS_TOKEN = '你的_Channel_Access_Token'
LINE_CHANNEL_SECRET = '你的_Channel_Secret'

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_string=True)
    
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    
    return 'OK'

# 當有人在 LINE 裡面跟機器人說話時會觸發這裡
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_message = event.message.text
    
    # 簡單的示範：如果司機打「認領」或相關指令
    if "認領" in user_message:
        reply_text = "收到！系統正在為您安排該筆共乘訂單，並已同步更新 Google 試算表！"
    else:
        reply_text = f"您剛剛說的是：「{user_message}」？我是貢寮共乘小幫手，隨時準備幫大家轉發預約資訊！"

    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=reply_text)
    )

if __name__ == "__main__":
    app.run(port=5000)