import os
import requests
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

GOOGLE_MAPS_API_KEY = os.environ.get("GOOGLE_MAPS_API_KEY")
LINE_NOTIFY_TOKEN = os.environ.get("LINE_NOTIFY_TOKEN")

def get_traffic_info(origin, destination):
    """Google Maps API から所要時間を取得"""
    try:
        url = "https://maps.googleapis.com/maps/api/distancematrix/json"
        params = {
            "origins": origin,
            "destinations": destination,
            "mode": "driving",
            "departure_time": "now",
            "key": GOOGLE_MAPS_API_KEY
        }
        res = requests.get(url, params=params, timeout=10).json()
        
        element = res["rows"][0]["elements"][0]
        if element.get("status") == "OK":
            duration = element.get("duration_in_traffic", element.get("duration", {})).get("text", "不明")
            distance = element.get("distance", {}).get("text", "不明")
            return f"\n【交通情報】\n{origin} → {destination}\n所要時間: {duration}\n距離: {distance}"
        else:
            return f"\n【交通情報】\n{origin} → {destination}\nルートが見つかりませんでした。"
    except Exception as e:
        return f"\n【交通情報取得エラー】\n{e}"

def send_line_notification(message):
    """LINE Notify へ通知を送信"""
    if not LINE_NOTIFY_TOKEN:
        return
    try:
        url = "https://notify-api.line.me/api/notify"
        headers = {"Authorization": f"Bearer {LINE_NOTIFY_TOKEN}"}
        data = {"message": message}
        requests.post(url, headers=headers, data=data, timeout=10)
    except Exception as e:
        print(f"LINE Error: {e}")

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            # 1. Safari等の事前読み込み（プリフェッチ）をブロック
            purpose = self.headers.get('Purpose') or self.headers.get('Sec-Purpose')
            if purpose in ['prefetch', 'preview']:
                self.send_response(204)
                self.end_headers()
                return

            # 2. favicon.ico をブロック
            parsed_path = urlparse(self.path)
            if parsed_path.path == '/favicon.ico':
                self.send_response(204)
                self.end_headers()
                return

            # 3. パラメータ判定
            query = parse_qs(parsed_path.query)
            is_reverse = query.get('reverse', ['false'])[0].lower() == 'true'

            default_origin = "塩尻北IC"
            default_destination = "諏訪IC"

            if is_reverse:
                origin = default_destination
                destination = default_origin
            else:
                origin = default_origin
                destination = default_destination

            # 4. 処理実行
            message = get_traffic_info(origin, destination)
            send_line_notification(message)

            # レスポンス返却
            self.send_response(200)
            self.send_header('Content-type', 'text/plain; charset=utf-8')
            self.end_headers()
            response_text = f"送信完了: {origin} -> {destination}"
            self.wfile.write(response_text.encode('utf-8'))

        except Exception as e:
            # 万が一のエラー時もクラッシュさせずに200でエラー内容を返す
            self.send_response(200)
            self.send_header('Content-type', 'text/plain; charset=utf-8')
            self.end_headers()
            self.wfile.write(f"Error: {str(e)}".encode('utf-8'))
