import os
import datetime
import urllib.parse
from http.server import BaseHTTPRequestHandler
import requests
import googlemaps

# 一般道検索用の座標マッピング
IC_TO_LOCAL_COORDS = {
    "諏訪IC": "35.9868,138.1256",    # 諏訪IC前交差点（国道20号）
    "岡谷IC": "36.0700,138.0460",    # 岡谷IC前交差点（国道20号/142号）
    "塩尻北IC": "36.1603,137.9542",  # 塩尻北IC入口交差点（国道19号）
    "塩尻IC": "36.1264,137.9731",    # 塩尻IC入口交差点
    "伊北IC": "35.9421,137.9867"     # 伊北IC入口交差点
}

# 高速道路本線上の座標マッピング（進行方向の本線上にピンポイント設定）
IC_TO_EXPRESSWAY_COORDS = {
    # 塩尻北IC -> 諏訪IC（上り方向：名古屋・東京方面）
    ("塩尻北IC", "諏訪IC"): {
        "origin": "36.1565,137.9538",      # 塩尻北IC上り本線合流部
        "destination": "36.0028,138.1290", # 諏訪IC本線付近
        "via": "36.0664,138.0441"         # 岡谷IC本線
    },
    # 諏訪IC -> 塩尻北IC（下り方向：長野・松本方面）
    ("諏訪IC", "塩尻北IC"): {
        "origin": "36.0028,138.1290",      # 諏訪IC下り本線
        "destination": "36.1565,137.9538", # 塩尻北IC下り本線合流部
        "via": "36.0664,138.0441"         # 岡谷IC本線
    }
}


def get_local_spot(spot_name):
    """一般道検索用の地点を取得"""
    clean_name = spot_name.strip()
    return IC_TO_LOCAL_COORDS.get(clean_name, clean_name)


def get_leg_duration(gmaps_client, origin, destination, avoid=None):
    """単一区間の所要時間（分）を取得"""
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
    duration_sec = leg.get("duration_in_traffic", leg.get("duration", {})).get("value", 0)
    return round(duration_sec / 60)


def make_map_url(origin, destination, via=None, avoid=None):
    """Google Maps URL生成（表示・共有用は名称を使用）"""
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
    return base_url + urllib.parse.urlencode(params)


def calculate_realtime_traffic(origin="塩尻北IC", destination="諏訪IC", via="岡谷IC"):
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise ValueError("環境変数 GOOGLE_API_KEY が設定されていません。")

    gmaps = googlemaps.Client(key=api_key)

    # 1. 高速道路用の検索座標を取得
    pair_key = (origin.strip(), destination.strip())
    if pair_key in IC_TO_EXPRESSWAY_COORDS:
        exp_coords = IC_TO_EXPRESSWAY_COORDS[pair_key]
        origin_express = exp_coords["origin"]
        destination_express = exp_coords["destination"]
        via_express = exp_coords["via"]
    else:
        # 万が一定義外の区間の場合はIC名にプレフィックスを付与して本線優先探索
        origin_express = f"side_of_road:{origin.strip()}"
        destination_express = f"side_of_road:{destination.strip()}"
        via_express = f"side_of_road:{via.strip()}"

    # 2. 一般道用の検索座標を取得
    origin_local = get_local_spot(origin)
    destination_local = get_local_spot(destination)
    via_local = get_local_spot(via)

    # --- ルート計算 ---
    # ①全高速ルート
    time_r1 = get_leg_duration(gmaps, origin_express, destination_express, avoid=None)
    url_r1 = make_map_url(origin, destination, avoid=None)

    # ②-1 前半一般道(origin➔via) + 後半高速(via➔destination)
    t2_1_part1 = get_leg_duration(gmaps, origin_local, via_local, avoid=["tolls", "highways"])
    t2_1_part2 = get_leg_duration(gmaps, via_express, destination_express, avoid=None)
    time_r2_1 = t2_1_part1 + t2_1_part2
    url_r2_1 = make_map_url(origin, destination, via=via)

    # ②-2 前半高速(origin➔via) + 後半一般道(via➔destination)
    t2_2_part1 = get_leg_duration(gmaps, origin_express, via_express, avoid=None)
    t2_2_part2 = get_leg_duration(gmaps, via_local, destination_local, avoid=["tolls", "highways"])
    time_r2_2 = t2_2_part1 + t2_2_part2
    url_r2_2 = make_map_url(origin, destination, via=via)

    # ③全一般道ルート
    time_r3 = get_leg_duration(gmaps, origin_local, destination_local, avoid=["tolls", "highways"])
    url_r3 = make_map_url(origin, destination, avoid="tolls")

    label_2_1 = f"②-1一般道({origin}➔{via})➔高速({via}➔{destination})"
    label_2_2 = f"②-2高速({origin}➔{via})➔一般道({via}➔{destination})"

    routes = [
        {"name": "①全高速", "time": time_r1, "url": url_r1},
        {"name": label_2_1, "time": time_r2_1, "url": url_r2_1},
        {"name": label_2_2, "time": time_r2_2, "url": url_r2_2},
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
        f"経由地: {via}\n\n"
        f"・①全高速ルート: 約 {time_r1} 分\n"
        f"・{label_2_1}: 約 {time_r2_1} 分\n"
        f"・{label_2_2}: 約 {time_r2_2} 分\n"
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
            purpose = self.headers.get('Purpose') or self.headers.get('Sec-Purpose')
            parsed_path = urllib.parse.urlparse(self.path)
            if purpose in ['prefetch', 'preview'] or parsed_path.path == '/favicon.ico':
                self.send_response(204)
                self.end_headers()
                return

            query_params = urllib.parse.parse_qs(parsed_path.query)

            should_send = query_params.get("send", ["0"])[0] == "1"

            default_origin = os.environ.get("MAPS_ORIGIN", "塩尻北IC")
            default_destination = os.environ.get("MAPS_DESTINATION", "諏訪IC")
            default_via = os.environ.get("MAPS_VIA", "岡谷IC")

            origin = query_params.get("origin", [default_origin])[0]
            destination = query_params.get("destination", [default_destination])[0]
            via = query_params.get("via", [default_via])[0]

            is_reverse = query_params.get("reverse", ["false"])[0].lower() in ["true", "1"]
            if is_reverse:
                origin, destination = destination, origin

            if not should_send:
                current_url = self.path
                sep = "&" if "?" in current_url else "?"
                confirm_url = f"{current_url}{sep}send=1"

                html = f"""
                <html>
                <head><meta charset="utf-8"><title>送信処理中</title></head>
                <body style="font-family:sans-serif; text-align:center; padding-top:50px;">
                    <h3>4ルートの交通情報を計算中...</h3>
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
