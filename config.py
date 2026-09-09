"""积分系统配置"""
import os

# 数据库
DB_PATH = "/app/data/points.db"

# 管理员密码
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")

# Kid Monitor API
KID_MONITOR_URL = os.getenv("KID_MONITOR_URL", "http://127.0.0.1:18089")

# 平板配置（MAC地址从环境变量读取）
TABLETS = {
    "lisa": {
        "name": os.getenv("LISA_NAME", "周楷依"),
        "mac": os.getenv("LISA_MAC", ""),
        "points_config": {
            "tutoring": 60,  # 补课（2门）
            "homework": 30,
            "other": 30,
        }
    },
    "huawei": {
        "name": os.getenv("HUAWEI_NAME", "周芓翕"),
        "mac": os.getenv("HUAWEI_MAC", ""),
        "points_config": {
            "tutoring": 30,  # 补课（1门）
            "homework": 30,
            "other": 30,
        }
    }
}

# 兑换比例：1积分 = 1分钟
EXCHANGE_RATE = 1

# QQ通知（预留）
QQ_NOTIFY_ENABLED = os.getenv("QQ_NOTIFY", "true").lower() == "true"
