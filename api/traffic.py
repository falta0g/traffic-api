import os
import requests
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

# 環境変数から設定を取得
GOOGLE_MAPS_API_KEY = os.environ.get("GOOGLE_MAPS_API_KEY")
LINE_NOTIFY_TOKEN = os.environ.get("LINE_NOTIFY_TOKEN")  # または LINE Messaging API Token

def get_traffic_info(origin, destination):
    """Google Maps Distance Matrix APIから所要時間を取得"""
    url = "https://maps.googleapis.com/maps/api/distancematrix/json"
    params = {
        "origins": origin,
        "destinations": destination,
        "mode": "driving",
        "departure_time": "now",
        "key": GOOGLE_MAPS_API_KEY
    }
    res = requests.get(url, params=params).json()
    
    try:
        element = res["rows"][0]["elements"][0]
        duration = element["duration_in_traffic"]["text"]
        distance = element["distance"]["text"]
        return f"{origin} → {destination}\n所要時間: {duration}\n距離: {distance}"
    except Exception as e:
        return f"交通情報の取得に失敗しました: {e}"

def send_line_notification(message):
    """LINEへ通知を送信"""
    url = "https://notify-api.line.me/api/notify"
    headers = {"Authorization": f"Bearer {LINE_NOTIFY_TOKEN}"}
    data = {"message": message}
    requests.post(url, headers=headers, data=data)

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        # --------------------------------------------------
        # 1. Safari等の事前読み込み（プリフェッチ）をブロック
        # --------------------------------------------------
        purpose = self.headers.get('Purpose') or self.headers.get('Sec-Purpose')
        if purpose in ['prefetch', 'preview']:
            self.send_response(204)  # No Content（処理をスキップ）
            self.end_headers()
            return

        # --------------------------------------------------
        # 2. ブラウザの favicon.ico 自動取得をブロック
        # --------------------------------------------------
        parsed_path = urlparse(self.path)
        if parsed_path.path == '/favicon.ico':
            self.send_response(204)
            self.end_headers()
            return

        # --------------------------------------------------
        # 3. クエリパラメータ（?reverse=true）の判定
        # --------------------------------------------------
        query = parse_qs(parsed_path.query)
        is_reverse = query.get('reverse', ['false'])[0].lower() == 'true'

        # デフォルト（行き）と反転（帰り）の地点設定
        default_origin = "塩尻北IC"
        default_destination = "諏訪IC"

        if is_reverse:
            origin = default_destination
            destination = default_origin
        else:
            origin = default_origin
            destination = default_destination

        # --------------------------------------------------
        # 4. 交通情報取得 ＆ LINE送信処理
        # --------------------------------------------------
        message = get_traffic_info(origin, destination)
        send_line_notification(message)

        # レスポンス返却
        self.send_response(200)
        self.send_header('Content-type', 'text/plain; charset=utf-8')
        self.end_headers()
        response_text = f"送信完了: {origin} -> {destination}"
        self.wfile.write(response_text.encode('utf-8'))
