"""数据库模型"""
import sqlite3
import os
from datetime import datetime, timezone
from config import DB_PATH

def get_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn

def init_db():
    """初始化数据库"""
    conn = get_db()
    cursor = conn.cursor()
    
    # 用户表
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        display_name TEXT NOT NULL,
        role TEXT NOT NULL,  -- 'admin', 'lisa', 'huawei'
        password_hash TEXT,
        tablet_key TEXT,     -- 对应TABLETS配置的key
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    
    # 积分申请表
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS point_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        request_type TEXT NOT NULL,  -- 'tutoring', 'homework', 'other'
        points INTEGER NOT NULL,
        status TEXT DEFAULT 'pending',  -- 'pending', 'approved', 'rejected'
        admin_note TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        processed_at TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id)
    )
    """)
    
    # 积分交易表（审批通过后记录）
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS point_transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        tx_type TEXT NOT NULL,  -- 'earn', 'exchange'
        points INTEGER NOT NULL,
        balance_after INTEGER NOT NULL,
        description TEXT,
        request_id INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id),
        FOREIGN KEY (request_id) REFERENCES point_requests(id)
    )
    """)
    
    # 积分兑换表
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS point_exchanges (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        points_spent INTEGER NOT NULL,
        minutes_granted INTEGER NOT NULL,
        tablet_mac TEXT,
        status TEXT DEFAULT 'pending',  -- 'pending', 'success', 'failed'
        error_msg TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id)
    )
    """)
    
    # 周积分额度表
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS weekly_quota (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        week_start DATE NOT NULL,  -- 该周的周一日期
        tutoring_used INTEGER DEFAULT 0,
        homework_used INTEGER DEFAULT 0,
        other_used INTEGER DEFAULT 0,
        UNIQUE(user_id, week_start),
        FOREIGN KEY (user_id) REFERENCES users(id)
    )
    """)
    
    conn.commit()
    conn.close()

def get_or_create_user(username: str, display_name: str, role: str, password_hash: str = None, tablet_key: str = None):
    """获取或创建用户"""
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    
    if not user:
        conn.execute(
            "INSERT INTO users (username, display_name, role, password_hash, tablet_key) VALUES (?, ?, ?, ?, ?)",
            (username, display_name, role, password_hash, tablet_key)
        )
        conn.commit()
        user = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    
    conn.close()
    return dict(user)

def init_default_users():
    """初始化默认用户"""
    from werkzeug.security import generate_password_hash
    admin_pw = os.getenv("ADMIN_PASSWORD", "2024")
    admin_hash = generate_password_hash(admin_pw)
    # 同步 admin 密码（防止旧数据库 hash 不匹配）
    conn = get_db()
    conn.execute("UPDATE users SET password_hash=? WHERE username=? AND role=?", (admin_hash, "admin", "admin"))
    conn.commit()
    conn.close()
    get_or_create_user("admin", "管理员", "admin", admin_hash)
    get_or_create_user("lisa", "周楷依", "lisa", None, "lisa")
    get_or_create_user("huawei", "周芓翕", "huawei", None, "huawei")

if __name__ == "__main__":
    init_db()
    init_default_users()
    print("Database initialized!")
