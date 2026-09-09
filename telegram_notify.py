import requests, os

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
PROXIES = {"https": "http://10.1.1.141:7890"}

def send_approval_request(child_name, request_type, points):
    type_names = {"tutoring": "补课", "homework": "作业", "other": "其他"}
    type_name = type_names.get(request_type, request_type)
    
    msg = f"�� <b>积分申请</b>\n\n"
    msg += f"<b>{child_name}</b> 申请 <b>{type_name}</b> +<b>{points}</b>积分\n\n"
    msg += f"�� <a href=\"https://points.zhouzhiang.com:777/admin\">点击审批</a>"
    
    try:
        resp = requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", json={
            "chat_id": CHAT_ID, "text": msg, "parse_mode": "HTML", "disable_web_page_preview": True
        }, timeout=10, proxies=PROXIES)
        return resp.json().get("ok", False)
    except Exception as e:
        print(f"Telegram error: {e}")
        return False

def send_exchange_notification(child_name, minutes):
    msg = f"�� <b>积分兑换成功</b>\n\n"
    msg += f"<b>{child_name}</b> 兑换了 <b>{minutes}</b> 分钟平板时间"
    try:
        resp = requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", json={
            "chat_id": CHAT_ID, "text": msg, "parse_mode": "HTML"
        }, timeout=10, proxies=PROXIES)
        return resp.json().get("ok", False)
    except:
        return False

