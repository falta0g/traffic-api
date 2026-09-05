import os
import requests
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

# 環境変数を自動検出する関数
def get_env_variable(possible_keys):
    for key in possible_keys:
        val = os.environ.get(key)
        if val:
            return val
    # 部分一致で探索（GOOGLE や MAPS、API_KEY を含む変数を拾う）
    for env_key, env_val in os.environ.items():
        if "GOOGLE" in env_key.upper() or "MAPS" in env_key.upper():
            if "KEY" in env_key.upper() and env_val:
                return env_val
    return None

def get_line_token():
    for key in ["LINE_NOTIFY_TOKEN", "LINE_ACCESS_TOKEN", "LINE_TOKEN"]:
        val = os.environ.get(key)
        if val:
            return val
    for env_key, env_val in os.environ.items():
        if "LINE" in env_key.upper() and env_val:
            return env_val
    return None

GOOGLE_MAPS_API_KEY = get_env_variable(["GOOGLE_MAPS_API_KEY", "GOOGLE_API_KEY", "MAPS_API_KEY"])
LINE_NOTIFY_TOKEN = get_line_token()

def get_traffic_info(origin, destination):
    """Google Maps API から所要時間を取得"""
    if not GOOGLE_MAPS_API_KEY:
        # 登録されている環境変数のキー名一覧を出力して原因特定を容易にする
        keys_found = [k for k in os.environ.keys() if not k.startswith("VERCEL")]
        return None, f"Google APIキーが見つかりません。現在検出された環境変数: {keys_found}"

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

        api_status = res.get("status")
        if api_status != "OK":
            error_details = res.get("error_message", "詳細なし")
            return None, f"Google Maps API エラー ({api_status}): {error_details}"

        rows = res.get("rows", [])
        if not rows:
            return None, "Google Maps API からのデータが空です。"

        elements = rows[0].get("elements", [])
        if not elements:
            return None, "要素データが存在しません。"

        element = elements[0]
        element_status = element.get("status")

        if element_status == "OK":
            duration = element.get("duration_in_traffic", element.get("duration", {})).get("text", "不明")
            distance = element.get("distance", {}).get("text", "不明")
            return f"\n【交通情報】\n{origin} → {destination}\n所要時間: {duration}\n距離: {distance}", None
        else:
            return None, f"ルート検索失敗 ({element_status})"

    except Exception as e:
        return None, f"Google Maps 通信例外エラー: {str(e)}"

def send_line_notification(message):
    """LINE Notify へ通知を送信"""
    if not LINE_NOTIFY_TOKEN:
        return False, "LINEトークンが設定されていません。"

    try:
        url = "https://notify-api.line.me/api/notify"
        headers = {"Authorization": f"Bearer {LINE_NOTIFY_TOKEN}"}
        data = {"message": message}
        res = requests.post(url, headers=headers, data=data, timeout=10)

        if res.status_code == 200:
            return True, "LINE送信完了"
        else:
            return False, f"LINE API エラー (Status: {res.status_code}): {res.text}"
    except Exception as e:
        return False, f"LINE 通信例外エラー: {str(e)}"

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            # 1. Safari等の事前読み込み（プリフェッチ）をブロック（二重送信防止）
            purpose = self.headers.get('Purpose') or self.headers.get('Sec-Purpose')
            if purpose in ['prefetch', 'preview']:
                self.send_response(204)
                self.end_headers()
                return

            # 2. favicon.ico 自動アクセスをブロック（二重送信防止）
            parsed_path = urlparse(self.path)
            if parsed_path.path == '/favicon.ico':
                self.send_response(204)
                self.end_headers()
                return

            # 3. パラメータ判定 (?reverse=true)
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

            # 4. 交通情報取得 ＆ LINE送信
            traffic_msg, error_msg = get_traffic_info(origin, destination)

            if error_msg:
                result_text = f"取得エラー:\n{error_msg}"
            else:
                success, line_msg = send_line_notification(traffic_msg)
                if success:
                    result_text = f"送信成功!\nルート: {origin} -> {destination}\n\n内容:\n{traffic_msg}"
                else:
                    result_text = f"LINE送信失敗:\n{line_msg}"

            # レスポンス返却
            self.send_response(200)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.end_headers()

            html_content = f"<html><body><pre style='font-size:16px;'>{result_text}</pre></body></html>"
            self.wfile.write(html_content.encode('utf-8'))

        except Exception as e:
            self.send_response(200)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.end_headers()
            err_html = f"<html><body><pre style='font-size:16px;'>システム例外エラー: {str(e)}</pre></body></html>"
            self.wfile.write(err_html.encode('utf-8'))
