import os, sys, time, signal, requests, json
from datetime import datetime, timedelta
sys.path.insert(0, '/app')
from models import get_db, init_db

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
BASE_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"
PROXY_URL = os.getenv("HTTP_PROXY", "")
PROXIES = {"https": PROXY_URL, "http": PROXY_URL} if PROXY_URL else {}

init_db()

def get_week_start():
    today = datetime.now()
    monday = today - timedelta(days=today.weekday())
    return monday.strftime("%Y-%m-%d")

def handle_callback(cb):
    cb_id = cb["id"]
    data = cb["data"]
    msg = cb.get("message", {})
    print(f"[{time.strftime('%H:%M:%S')}] CALLBACK: {data}", flush=True)

    if data.startswith("approve_") or data.startswith("reject_"):
        action = "approve" if data.startswith("approve_") else "reject"
        rid = int(data.split("_")[1])

        if rid == 0:
            # 旧按钮，忽略
            requests.post(f"{BASE_URL}/answerCallbackQuery",
                          json={"callback_query_id": cb_id, "text": "此申请已过期", "show_alert": True},
                          timeout=10, proxies=PROXIES)
            return

        conn = get_db()
        req = conn.execute("SELECT * FROM point_requests WHERE id=?", (rid,)).fetchone()
        if req and req["status"] == "pending":
            user = conn.execute("SELECT * FROM users WHERE id=?", (req["user_id"],)).fetchone()
            week_start = get_week_start()

            if action == "approve":
                # 更新周额度
                quota = conn.execute(
                    "SELECT * FROM weekly_quota WHERE user_id=? AND week_start=?",
                    (req["user_id"], week_start)
                ).fetchone()
                if not quota:
                    conn.execute(
                        "INSERT INTO weekly_quota (user_id, week_start) VALUES (?, ?)",
                        (req["user_id"], week_start)
                    )
                col = f"{req['request_type']}_used"
                conn.execute(
                    f"UPDATE weekly_quota SET {col}=1 WHERE user_id=? AND week_start=?",
                    (req["user_id"], week_start)
                )

                # 计算余额
                bal = conn.execute(
                    "SELECT COALESCE(SUM(CASE WHEN tx_type='earn' THEN points ELSE -points END),0) "
                    "FROM point_transactions WHERE user_id=?", (req["user_id"],)
                ).fetchone()[0] + req["points"]
                conn.execute(
                    "INSERT INTO point_transactions (user_id, tx_type, points, balance_after, description, request_id) "
                    "VALUES (?, 'earn', ?, ?, ?, ?)",
                    (req["user_id"], req["points"], bal, f"{req['request_type']}积分", rid)
                )
                conn.execute("UPDATE point_requests SET status='approved' WHERE id=?", (rid,))
                conn.commit()
                text = f"✅ 已同意 {user['display_name']} +{req['points']}积分"
            else:
                conn.execute("UPDATE point_requests SET status='rejected' WHERE id=?", (rid,))
                conn.commit()
                text = f"❌ 已拒绝 {user['display_name']} 的申请"
            conn.close()

            requests.post(f"{BASE_URL}/answerCallbackQuery",
                          json={"callback_query_id": cb_id, "text": text, "show_alert": True},
                          timeout=10, proxies=PROXIES)
            if msg.get("chat") and msg.get("message_id"):
                requests.post(f"{BASE_URL}/editMessageText",
                              json={"chat_id": msg["chat"]["id"], "message_id": msg["message_id"],
                                    "text": text, "parse_mode": "HTML"},
                              timeout=10, proxies=PROXIES)
            print(f"  -> {text}", flush=True)
        else:
            requests.post(f"{BASE_URL}/answerCallbackQuery",
                          json={"callback_query_id": cb_id, "text": "申请不存在或已处理", "show_alert": True},
                          timeout=10, proxies=PROXIES)
            conn.close()

def poll():
    for attempt in range(3):
        try:
            r = requests.get(f"{BASE_URL}/getUpdates?offset=-1&limit=1", timeout=10, proxies=PROXIES)
            d = r.json()
            offset = d["result"][-1]["update_id"] + 1 if d.get("result") else 0
            break
        except Exception as e:
            print(f"[{time.strftime('%H:%M:%S')}] Init error: {e}", flush=True)
            time.sleep(2)
    else:
        offset = 0

    print(f"[{time.strftime('%H:%M:%S')}] Polling from offset={offset}", flush=True)

    while True:
        try:
            r = requests.get(f"{BASE_URL}/getUpdates", params={
                "offset": offset, "timeout": 0,
                "allowed_updates": json.dumps(["callback_query"])
            }, timeout=10, proxies=PROXIES)
            d = r.json()
            if d.get("ok") and d.get("result"):
                print(f"[{time.strftime('%H:%M:%S')}] Got {len(d['result'])} update(s)", flush=True)
                for u in d["result"]:
                    offset = u["update_id"] + 1
                    if "callback_query" in u:
                        handle_callback(u["callback_query"])
            else:
                if int(time.time()) % 60 < 2:
                    print(f"[{time.strftime('%H:%M:%S')}] Waiting... (offset={offset})", flush=True)
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"[{time.strftime('%H:%M:%S')}] Error: {e}", flush=True)
            time.sleep(5)
        time.sleep(2)

if __name__ == "__main__":
    signal.signal(signal.SIGTERM, lambda s, f: sys.exit(0))
    poll()
