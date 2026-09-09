"""积分系统主应用"""
import os
from flask import Flask, request, jsonify, render_template, session, redirect, url_for, make_response
from werkzeug.security import check_password_hash

import requests
import logging

os.environ["NO_PROXY"] = "127.0.0.1,localhost,10.0.0.0/8"
os.environ["no_proxy"] = os.environ["NO_PROXY"]

from config import TABLETS, KID_MONITOR_URL, EXCHANGE_RATE
from models import get_db, init_db, init_default_users
from tablet_time import get_tablet_remaining_time
from datetime import datetime, timezone, timedelta


app = Flask(__name__)
_secret_file = os.path.join(os.path.dirname(__file__), ".secret_key")
if os.path.exists(_secret_file):
    with open(_secret_file, "rb") as f: _sk = f.read()
else:
    _sk = os.urandom(32)
    with open(_secret_file, "wb") as f: f.write(_sk)
app.secret_key = _sk

CST = timezone(timedelta(hours=8))

@app.template_filter('cst_time')
def cst_time_filter(s):
    if isinstance(s, str):
        try:
            dt = datetime.strptime(s, '%Y-%m-%d %H:%M:%S')
        except:
            return s
    elif isinstance(s, datetime):
        dt = s
    else:
            return s
    dt = dt.replace(tzinfo=timezone.utc).astimezone(CST)
    return dt.strftime('%m-%d %H:%M')

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 初始化数据库
init_db()
init_default_users()
logger.info("Database initialized")

# 辅助函数
def get_current_user():
    """获取当前登录用户"""
    if "user_id" not in session:
        return None
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE id = ?", (session["user_id"],)).fetchone()
    conn.close()
    return dict(user) if user else None

def get_week_start():
    """获取本周一日期"""
    today = datetime.now()
    monday = today - timedelta(days=today.weekday())
    return monday.strftime("%Y-%m-%d")

def get_user_points(user_id: int) -> int:
    """获取用户当前积分余额"""
    conn = get_db()
    result = conn.execute(
        "SELECT SUM(CASE WHEN tx_type='earn' THEN points ELSE -points END) as balance "
        "FROM point_transactions WHERE user_id = ?", (user_id,)
    ).fetchone()
    conn.close()
    return result["balance"] if result and result["balance"] else 0

def get_weekly_quota(user_id: int) -> dict:
    """获取用户本周额度使用情况"""
    week_start = get_week_start()
    conn = get_db()
    quota = conn.execute(
        "SELECT * FROM weekly_quota WHERE user_id = ? AND week_start = ?",
        (user_id, week_start)
    ).fetchone()
    
    if not quota:
        conn.execute(
            "INSERT INTO weekly_quota (user_id, week_start) VALUES (?, ?)",
            (user_id, week_start)
        )
        conn.commit()
        quota = conn.execute(
            "SELECT * FROM weekly_quota WHERE user_id = ? AND week_start = ?",
            (user_id, week_start)
        ).fetchone()
    
    conn.close()
    return dict(quota) if quota else {"tutoring_used": 0, "homework_used": 0, "other_used": 0}

def is_weekend() -> bool:
    today = datetime.now()
    if today.weekday() >= 5:
        return True
    try:
        import requests as _req
        r = _req.get(KID_MONITOR_URL + '/api/config', timeout=3, proxies={'http': None, 'https': None})
        day_type = r.json().get('day_type', 'workday')
        if day_type != 'workday':
            return True
    except Exception:
        pass
    return False

# 路由
@app.route("/")
def index():
    """首页"""
    user = get_current_user()
    if not user:
        return redirect(url_for("login"))
    
    if user["role"] == "admin":
        return redirect(url_for("admin_dashboard"))
    else:
        resp = make_response(redirect(url_for("child_dashboard", child=user["username"])))
        resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
        return resp

@app.route("/login", methods=["GET", "POST"])
def login():
    """登录页面"""
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        
        conn = get_db()
        user = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        conn.close()
        
        if user:
            # 孩子无需密码，直接进入
            if user["role"] in ["lisa", "huawei"]:
                session["user_id"] = user["id"]
                return redirect(url_for("child_dashboard", child=username))
            # 管理员需要密码
            elif user["role"] == "admin" and user["password_hash"] and check_password_hash(user["password_hash"], password):
                session["user_id"] = user["id"]
                return redirect(url_for("admin_dashboard"))
        else:
            return render_template("login.html", error="用户名或密码错误")
    
    resp = make_response(render_template("login.html"))
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    return resp

@app.route("/logout")
def logout():
    """登出"""
    session.clear()
    return redirect(url_for("login"))

# 孩子端路由
@app.route("/child/<child>")
def child_dashboard(child: str):
    """孩子积分页面"""
    user = get_current_user()
    if not user or user["username"] != child:
        return redirect(url_for("login"))
    
    points = get_user_points(user["id"])
    quota = get_weekly_quota(user["id"])
    tablet_config = TABLETS.get(user["tablet_key"], {})
    points_config = tablet_config.get("points_config", {})
    
    # 获取待审批申请
    conn = get_db()
    pending = conn.execute(
        "SELECT * FROM point_requests WHERE user_id = ? AND status = 'pending' ORDER BY created_at DESC",
        (user["id"],)
    ).fetchall()
    pending = [dict(r) for r in pending]
    conn.close()
    
    return render_template(
        "child_dashboard.html",
        user=user,
        points=points,
        quota=quota,
        points_config=points_config,
        pending=pending,
        is_weekend=is_weekend()
    )

@app.route("/api/apply", methods=["POST"])
def apply_points():
    """申请积分"""
    user = get_current_user()
    if not user or user["role"] not in ["lisa", "huawei", "admin"]:
        return jsonify({"ok": False, "error": "无权限"}), 403
    
    if not is_weekend():
        return jsonify({"ok": False, "error": "仅限周末申请积分"}), 400
    
    request_type = request.json.get("type")
    if request_type not in ["tutoring", "homework", "other"]:
        return jsonify({"ok": False, "error": "无效的申请类型"}), 400
    
    # 检查本周额度
    quota = get_weekly_quota(user["id"])
    tablet_config = TABLETS.get(user["tablet_key"], {})
    points_config = tablet_config.get("points_config", {})
    
    if request_type == "tutoring" and quota["tutoring_used"] > 0:
        return jsonify({"ok": False, "error": "本周补课积分已领取"}), 400
    elif request_type == "homework" and quota["homework_used"] > 0:
        return jsonify({"ok": False, "error": "本周作业积分已领取"}), 400
    elif request_type == "other" and quota["other_used"] > 0:
        return jsonify({"ok": False, "error": "本周其他积分已领取"}), 400
    
    # 创建申请
    points = points_config.get(request_type, 0)
    conn = get_db()
    conn.execute(
        "INSERT INTO point_requests (user_id, request_type, points) VALUES (?, ?, ?)",
        (user["id"], request_type, points)
    )
    conn.commit()
    req_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.close()
    
    # 发送Telegram通知
    try:
        from telegram_notify import send_approval_request
        send_approval_request(user["display_name"], request_type, points, request_id=req_id)
    except Exception as e:
        logger.error(f"Telegram notification failed: {e}")
    
    return jsonify({"ok": True, "message": "申请已提交，等待审批"})

# 管理员端路由
@app.route("/admin")
def admin_dashboard():
    """管理员页面"""
    user = get_current_user()
    if not user or user["role"] != "admin":
        return redirect(url_for("login"))
    
    conn = get_db()
    
    # 获取所有孩子积分
    children = conn.execute(
        "SELECT u.*, COALESCE(SUM(CASE WHEN t.tx_type='earn' THEN t.points ELSE -t.points END), 0) as balance "
        "FROM users u LEFT JOIN point_transactions t ON u.id = t.user_id "
        "WHERE u.role IN ('lisa', 'huawei') GROUP BY u.id"
    ).fetchall()
    children = [dict(c) for c in children]
    
    # 获取待审批申请
    pending = conn.execute(
        "SELECT pr.*, u.display_name as child_name FROM point_requests pr "
        "JOIN users u ON pr.user_id = u.id WHERE pr.status = 'pending' ORDER BY pr.created_at DESC"
    ).fetchall()
    pending = [dict(r) for r in pending]
    
    # 获取最近交易
    recent = conn.execute(
        "SELECT pt.*, u.display_name as child_name FROM point_transactions pt "
        "JOIN users u ON pt.user_id = u.id ORDER BY pt.created_at DESC LIMIT 20"
    ).fetchall()
    recent = [dict(r) for r in recent]
    
    conn.close()
    
    return render_template(
        "admin_dashboard.html",
        children=children,
        pending=pending,
        recent=recent
    )

@app.route("/api/approve", methods=["POST"])
def approve_request():
    """审批积分申请"""
    user = get_current_user()
    if not user or user["role"] != "admin":
        return jsonify({"ok": False, "error": "无权限"}), 403
    
    request_id = request.json.get("request_id")
    action = request.json.get("action")  # 'approve' or 'reject'
    note = request.json.get("note", "")
    
    conn = get_db()
    req = conn.execute("SELECT * FROM point_requests WHERE id = ?", (request_id,)).fetchone()
    
    if not req or req["status"] != "pending":
        conn.close()
        return jsonify({"ok": False, "error": "申请不存在或已处理"}), 400
    
    if action == "approve":
        # 更新额度
        week_start = get_week_start()
        if req["request_type"] == "tutoring":
            conn.execute(
                "UPDATE weekly_quota SET tutoring_used = 1 WHERE user_id = ? AND week_start = ?",
                (req["user_id"], week_start)
            )
        elif req["request_type"] == "homework":
            conn.execute(
                "UPDATE weekly_quota SET homework_used = 1 WHERE user_id = ? AND week_start = ?",
                (req["user_id"], week_start)
            )
        elif req["request_type"] == "other":
            conn.execute(
                "UPDATE weekly_quota SET other_used = 1 WHERE user_id = ? AND week_start = ?",
                (req["user_id"], week_start)
            )
        
        # 记录交易
        balance = get_user_points(req["user_id"]) + req["points"]
        conn.execute(
            "INSERT INTO point_transactions (user_id, tx_type, points, balance_after, description, request_id) "
            "VALUES (?, 'earn', ?, ?, ?, ?)",
            (req["user_id"], req["points"], balance, f"{req['request_type']}积分", request_id)
        )
    
    # 更新申请状态
    conn.execute(
        "UPDATE point_requests SET status = ?, admin_note = ?, processed_at = CURRENT_TIMESTAMP WHERE id = ?",
        ("approved" if action == "approve" else "rejected", note, request_id)
    )
    
    conn.commit()
    conn.close()
    
    return jsonify({"ok": True, "message": "已审批"})

@app.route("/api/exchange", methods=["POST"])
def exchange_points():
    """兑换积分"""
    user = get_current_user()
    logger.info(f"exchange: user={user}, session_user_id={session.get('user_id')}")
    if not user or user["role"] not in ["lisa", "huawei", "admin"]:
        return jsonify({"ok": False, "error": "无权限"}), 403
    
    points_to_use = request.json.get("points", 30)
    
    # 检查积分
    current_balance = get_user_points(user["id"])
    if current_balance < points_to_use:
        return jsonify({"ok": False, "error": f"积分不足，当前{current_balance}积分"}), 400
    
    minutes = points_to_use * EXCHANGE_RATE
    tablet_config = TABLETS.get(user["tablet_key"], {})
    mac = tablet_config.get("mac", "")
    
    if not mac:
        return jsonify({"ok": False, "error": "未配置平板MAC地址"}), 400
    
    # 调用kid-monitor API
    try:
        resp = requests.post(
            f"{KID_MONITOR_URL}/kid-adjust",
            json={"mac": mac, "delta": minutes * 60},
            timeout=10
        )
        result = resp.json()
        
        if not result.get("ok"):
            return jsonify({"ok": False, "error": f"Kid Monitor错误: {result.get('error', '未知')}"}), 500
    except Exception as e:
        logger.error(f"Kid Monitor调用失败: {e}")
        return jsonify({"ok": False, "error": "Kid Monitor连接失败"}), 500
    
    # 记录兑换
    conn = get_db()
    balance = current_balance - points_to_use
    conn.execute(
        "INSERT INTO point_transactions (user_id, tx_type, points, balance_after, description) "
        "VALUES (?, 'exchange', ?, ?, ?)",
        (user["id"], points_to_use, balance, f"兑换{minutes}分钟平板时间")
    )
    conn.execute(
        "INSERT INTO point_exchanges (user_id, points_spent, minutes_granted, tablet_mac, status) "
        "VALUES (?, ?, ?, ?, 'success')",
        (user["id"], points_to_use, minutes, mac)
    )
    conn.commit()
    conn.close()
    
    return jsonify({"ok": True, "message": f"兑换成功！获得{minutes}分钟平板时间", "minutes": minutes})

@app.route("/api/set_points", methods=["POST"])
def set_points():
    """管理员设置积分"""
    user = get_current_user()
    if not user or user["role"] != "admin":
        return jsonify({"ok": False, "error": "无权限"}), 403
    
    target_user_id = request.json.get("user_id")
    points = request.json.get("points")
    
    if not isinstance(points, int):
        return jsonify({"ok": False, "error": "积分必须是整数"}), 400
    
    conn = get_db()
    current_balance = get_user_points(target_user_id)
    diff = points - current_balance
    tx_type = "earn" if diff > 0 else "exchange"
    
    conn.execute(
        "INSERT INTO point_transactions (user_id, tx_type, points, balance_after, description) "
        "VALUES (?, ?, ?, ?, ?)",
        (target_user_id, tx_type, abs(diff), points, "管理员调整")
    )
    conn.commit()
    conn.close()
    
    return jsonify({"ok": True, "message": f"积分已设置为{points}"})

if __name__ == "__main__":
    init_db()
    init_default_users()
    app.run(host="0.0.0.0", port=18090, debug=True)

