import os
import sys
import datetime
import requests
from http.server import BaseHTTPRequestHandler

def calculate_traffic_estimate(jam_general_km=0.0, jam_nagano_km=0.0, jam_chuo_km=0.0):
    speed_general_normal = 40.0
    speed_express_normal = 80.0
    speed_jam = 12.0

    dist_ref_general = 3.4
    dist_ref_express = 27.8
    
    time_ref_min = round((dist_ref_general / speed_general_normal * 60) + 
                         (dist_ref_express / speed_express_normal * 60), 0)

    # ① 全高速
    jam_express_total = jam_nagano_km + jam_chuo_km
    dist_r1_general = dist_ref_general
    dist_r1_express_jam = jam_express_total
    dist_r1_express_normal = max(0.0, dist_ref_express - dist_r1_express_jam)
    
    time_r1 = round(
        (dist_r1_general / speed_general_normal * 60) +
        (dist_r1_express_normal / speed_express_normal * 60) +
        (dist_r1_express_jam / speed_jam * 60), 0
    )

    # ② 一般道併用
    dist_r2_general = 15.4
    dist_r2_express_total = 14.0
    dist_r2_jam = jam_general_km
    dist_r2_express_normal = max(0.0, dist_r2_express_total - dist_r2_jam)
    
    time_r2 = round(
        (dist_r2_general / speed_general_normal * 60) +
        (dist_r2_express_normal / speed_express_normal * 60) +
        (dist_r2_jam / speed_jam * 60), 0
    )

    # ③ 全一般道
    dist_r3_general = 31.6
    dist_r3_jam = jam_general_km
    dist_r3_normal = max(0.0, dist_r3_general - dist_r3_jam)
    
    time_r3 = round(
        (dist_r3_normal / speed_general_normal * 60) +
        (dist_r3_jam / speed_jam * 60), 0
    )

    routes = [
        {"name": "①全高速", "time": time_r1},
        {"name": "②一般道併用", "time": time_r2},
        {"name": "③全一般道", "time": time_r3}
    ]

    best_route = min(routes, key=lambda x: x["time"])
    best_time = int(best_route["time"])
    best_name = best_route["name"]

    ratio = round(best_time / time_ref_min, 2) if time_ref_min > 0 else 1.0

    now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9)))
    eta = now + datetime.timedelta(minutes=best_time)
    eta_str = eta.strftime("%Y-%m-%d %H:%M:%S")

    msg = (
        "🚗【通勤・移動時間見積り（渋滞解析）】\n\n"
        f"・全高速ルート: 約 {int(time_r1)} 分\n"
        f"・一般道併用ルート: 約 {int(time_r2)} 分\n"
        f"・全一般道ルート: 約 {int(time_r3)} 分\n"
        "----------------------\n"
        f"◇適正ルートは、【{best_name}】です。\n"
        f"所要時間は {best_time} 分で、通常時（{int(time_ref_min)}分）の約 {ratio:.2f} 倍かかります。\n\n"
        f"📱到着時刻は {eta_str} の見込みです。"
    )

    return msg


def send_line_push(text_content):
    token = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
    user_id = os.environ.get("LINE_USER_ID")
    
    if not token or not user_id:
        return "LINE token or user ID is missing."
        
    url = "https://api.line.me/v2/bot/message/push"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"
    }
    payload = {
        "to": user_id,
        "messages": [{"type": "text", "text": text_content}]
    }
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        response.raise_for_status()
        return "LINE push succeeded."
    except Exception as e:
        return f"LINE push error: {str(e)}"


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            msg = calculate_traffic_estimate(jam_general_km=3.0, jam_nagano_km=6.0, jam_chuo_km=2.0)
            line_status = send_line_push(msg)
            body_text = f"{msg}\n\n[Status]: {line_status}"
            
            self.send_response(200)
            self.send_header('Content-type', 'text/plain; charset=utf-8')
            self.end_headers()
            self.wfile.write(body_text.encode('utf-8'))
        except Exception as e:
            self.send_response(500)
            self.send_header('Content-type', 'text/plain; charset=utf-8')
            self.end_headers()
            self.wfile.write(f"Error: {str(e)}".encode('utf-8'))
