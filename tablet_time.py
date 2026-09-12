"""获取孩子当前可用时间"""
import sys
sys.path.insert(0, '/app')
from config import KID_MONITOR_URL

def get_tablet_remaining_time():
    """获取每个孩子今天的剩余可用时间"""
    import requests
    try:
        resp = requests.get(f"{KID_MONITOR_URL}/api/data", timeout=10)
        data = resp.json()
        today = data.get('dates', [])[-1] if data.get('dates') else None
        if not today:
            return {}
        result = {}
        # Build name map from history
        name_map = {}
        for h in data.get('history', []):
            name_map[h.get('mac')] = h.get('name')
        for mac, limit_info in data.get('device_limits', {}).items():
            limit = limit_info.get(today, 0)
            daily = data.get('device_daily', {}).get(mac, {}).get(today, {})
            used = daily.get('usage_sec', 0)
            remaining = max(0, limit - used)
            name = name_map.get(mac, mac)
            result[name] = {
                'limit_min': limit // 60,
                'used_min': used // 60,
                'remaining_min': remaining // 60
            }
        return result
    except Exception as e:
        print(f"Error getting tablet time: {e}")
        return {}

if __name__ == "__main__":
    result = get_tablet_remaining_time()
    for name, info in result.items():
        print(f"{name}: limit={info['limit_min']}min used={info['used_min']}min remaining={info['remaining_min']}min")
