import os
import datetime
import urllib.parse
from http.server import BaseHTTPRequestHandler
import requests
import googlemaps


def get_realtime_route_info(gmaps_client, origin, destination, avoid=None):
    now = datetime.datetime.now()
    directions_result = gmaps_client.directions(
        origin=origin,
        destination=destination,
        mode="driving",
        departure_time=now,
        avoid=avoid
    )

    if not directions_result:
        raise ValueError(f"'{origin}' から '{destination}' へのルートが見つかりませんでした。")

    leg = directions_result[0]["legs"][0]
    
    if "duration_in_traffic" in leg:
        duration_sec = leg["duration_in_traffic"]["value"]
    else:
        duration_sec = leg["duration"]["value"]

    duration_min = round(duration_sec / 60)
    
    base_url = "https://www.google.com/maps/dir/?"
    params = {
        "api": "1",
        "origin": origin,
        "destination": destination,
        "travelmode": "driving"
    }
    if avoid:
        params["avoid"] = avoid
    map_url = base_url + urllib.parse.urlencode(params)

    return duration_min, map_url


def calculate_realtime_traffic(origin="塩尻北IC", destination="諏訪IC"):
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise ValueError("環境変数 GOOGLE_API_KEY が設定されていません。")

    gmaps = googlemaps.Client(key=api_key)

    time_r1, url_r1 = get_realtime_route_info(gmaps, origin, destination, avoid=None)
    time_r3, url_r3 = get_realtime_route_info(gmaps, origin, destination, avoid="tolls")

    time_r2 = round((time_r1 + time_r3) / 2) if time_r3 > time_r1 else time_r1
    url_r2 = url_r1

    routes = [
        {"name": "①全高速", "time": time_r1, "url": url_r1},
        {"name": "②一般道併用", "time": time_r2, "url": url_r2},
        {"name": "③全一般道", "time": time_r3, "url": url_r3}
    ]

    best_route = min(routes, key=lambda x: x["time"])
    best_time = int(best_route["time"])
    best_name = best_route["name"]
    best_url = best_route["url"]

    now_jst = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9)))
    eta = now_jst + datetime.timedelta(minutes=best_time)
    eta_str = eta.strftime("%Y-%m-%d %H:%M:%S")

    app_url = os.environ.get("APP_URL", "https://traffic-api-27wr.vercel.app")

    msg = (
        f"🚗【リアルタイム移動時間見積り ({origin} ➔ {destination})】\n\n"
        f"・全高速ルート: 約 {time_r1} 分\n"
        f"・一般道併用ルート: 約 {time_r2} 分\n"
        f"・全一般道ルート: 約 {time_r3} 分\n"
        "----------------------\n"
        f"◇現在の最速ルートは、【{best_name}】です。\n"
        f"所要時間は約 {best_time} 分を見込んでいます。\n\n"
        f"📱到着予定時刻: {eta_str}\n\n"
        f"🗺️ Google Maps ルート（{best_name}）:\n{best_url}\n\n"
        f"🔗 Web詳細確認ページ:\n{app_url}"
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
            # --------------------------------------------------
            # ガード1: Safariの事前読み込み（プリフェッチ）を検知してブロック
            # --------------------------------------------------
            purpose = self.headers.get('Purpose') or self.headers.get('Sec-Purpose')
            if purpose in ['prefetch', 'preview']:
                self.send_response(204)  # No Content（LINE送信せず即座に終了）
                self.end_headers()
                return

            # --------------------------------------------------
            # ガード2: ブラウザの favicon.ico 自動アクセスをブロック
            # --------------------------------------------------
            parsed_path = urllib.parse.urlparse(self.path)
            if parsed_path.path == '/favicon.ico':
                self.send_response(204)
                self.end_headers()
                return

            # --------------------------------------------------
            # 通常処理（パラメータ解析＆送信）
            # --------------------------------------------------
            default_origin = os.environ.get("MAPS_ORIGIN", "塩尻北IC")
            default_destination = os.environ.get("MAPS_DESTINATION", "諏訪IC")

            query_params = urllib.parse.parse_qs(parsed_path.query)

            origin = query_params.get("origin", [default_origin])[0]
            destination = query_params.get("destination", [default_destination])[0]
            
            is_reverse = query_params.get("reverse", ["false"])[0].lower() in ["true", "1"]
            if is_reverse:
                origin, destination = destination, origin

            msg = calculate_realtime_traffic(origin=origin, destination=destination)
            line_status = send_line_push(msg)
            body_text = f"{msg}\n\n[Status]: {line_status}"
            
            # HTML形式でレスポンスを返却（ファイルダウンロード化を防止）
            self.send_response(200)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.end_headers()
            
            html_content = f"<html><body><pre style='font-size:16px; white-space:pre-wrap;'>{body_text}</pre></body></html>"
            self.wfile.write(html_content.encode('utf-8'))

        except Exception as e:
            error_msg = f"Runtime Error Details:\n{str(e)}"
            self.send_response(200)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.end_headers()
            err_html = f"<html><body><pre style='font-size:16px; color:red;'>{error_msg}</pre></body></html>"
            self.wfile.write(err_html.encode('utf-8'))
