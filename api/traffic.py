import os
import datetime
import urllib.parse
from http.server import BaseHTTPRequestHandler
import requests
import googlemaps


def get_route_duration_and_url(gmaps_client, origin, destination, avoid=None, via=None):
    """Google Maps API から所要時間（分）と地図リンクを一括取得"""
    now = datetime.datetime.now()
    
    # パラメータ組み立て
    waypoints = [f"via:{via}"] if via else None
    
    directions_result = gmaps_client.directions(
        origin=origin,
        destination=destination,
        mode="driving",
        departure_time=now,
        avoid=avoid,
        waypoints=waypoints
    )

    if not directions_result:
        raise ValueError(f"'{origin}' から '{destination}' へのルートが見つかりませんでした。")

    # 全 leg の所要時間を合算
    leg_sum_sec = 0
    for leg in directions_result[0]["legs"]:
        if "duration_in_traffic" in leg:
            leg_sum_sec += leg["duration_in_traffic"]["value"]
        else:
            leg_sum_sec += leg["duration"]["value"]

    duration_min = round(leg_sum_sec / 60)

    # Google Maps URLの生成
    base_url = "https://www.google.com/maps/dir/?"
    params = {
        "api": "1",
        "origin": origin,
        "destination": destination,
        "travelmode": "driving"
    }
    if via:
        params["waypoints"] = via
    if avoid:
        params["avoid"] = avoid

    map_url = base_url + urllib.parse.urlencode(params)

    return duration_min, map_url


def calculate_realtime_traffic(origin="塩尻北IC", destination="諏訪IC", via="岡谷JCT"):
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise ValueError("環境変数 GOOGLE_API_KEY が設定されていません。")

    gmaps = googlemaps.Client(key=api_key)

    # 1. ①全高速
    time_r1, url_r1 = get_route_duration_and_url(gmaps, origin, destination, avoid=None)

    # 2. ②-1 経由地（岡谷JCTなど）を経由した一般道・高速併用ルート
    time_r2, url_r2 = get_route_duration_and_url(gmaps, origin, destination, via=via)

    # 3. ③全一般道
    time_r3, url_r3 = get_route_duration_and_url(gmaps, origin, destination, avoid="tolls")

    routes = [
        {"name": "①全高速", "time": time_r1, "url": url_r1},
        {"name": f"②併用ルート({via}経由)", "time": time_r2, "url": url_r2},
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
        f"🚗【リアルタイム移動時間見積り ({origin} ➔ {destination})】\n"
        f"経由ポイント: {via}\n\n"
        f"・①全高速ルート: 約 {time_r1} 分\n"
        f"・②一般道・高速併用ルート: 約 {time_r2} 分\n"
        f"・③全一般道ルート: 約 {time_r3} 分\n"
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
            # 1. プリフェッチ / favicon 遮断
            purpose = self.headers.get('Purpose') or self.headers.get('Sec-Purpose')
            parsed_path = urllib.parse.urlparse(self.path)
            if purpose in ['prefetch', 'preview'] or parsed_path.path == '/favicon.ico':
                self.send_response(204)
                self.end_headers()
                return

            query_params = urllib.parse.parse_qs(parsed_path.query)

            # 2. 実行確定フラグ（send=1）判定
            should_send = query_params.get("send", ["0"])[0] == "1"

            default_origin = os.environ.get("MAPS_ORIGIN", "塩尻北IC")
            default_destination = os.environ.get("MAPS_DESTINATION", "諏訪IC")
            default_via = os.environ.get("MAPS_VIA", "岡谷JCT")

            origin = query_params.get("origin", [default_origin])[0]
            destination = query_params.get("destination", [default_destination])[0]
            via = query_params.get("via", [default_via])[0]

            is_reverse = query_params.get("reverse", ["false"])[0].lower() in ["true", "1"]
            if is_reverse:
                origin, destination = destination, origin

            # 送信フラグがない場合: JavaScriptで一度だけ再リクエスト
            if not should_send:
                current_url = self.path
                sep = "&" if "?" in current_url else "?"
                confirm_url = f"{current_url}{sep}send=1"

                html = f"""
                <html>
                <head><meta charset="utf-8"><title>送信処理中</title></head>
                <body style="font-family:sans-serif; text-align:center; padding-top:50px;">
                    <h3>交通情報を計算中...</h3>
                    <p>自動的にLINEへ通知されます。</p>
                    <script>
                        setTimeout(function() {{
                            window.location.replace("{confirm_url}");
                        }}, 300);
                    </script>
                </body>
                </html>
                """
                self.send_response(200)
                self.send_header('Content-type', 'text/html; charset=utf-8')
                self.end_headers()
                self.wfile.write(html.encode('utf-8'))
                return

            # 送信フラグあり: 交通情報計算 & LINE送信
            msg = calculate_realtime_traffic(origin=origin, destination=destination, via=via)
            line_status = send_line_push(msg)
            body_text = f"{msg}\n\n[Status]: {line_status}"

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
