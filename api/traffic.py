import os
import sys
import datetime
import requests

# Vercel環境変数から取得
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "YOUR_LINE_CHANNEL_ACCESS_TOKEN")
LINE_USER_ID = os.environ.get("LINE_USER_ID", "YOUR_LINE_USER_ID")


def calculate_traffic_estimate(jam_general_km=0.0, jam_nagano_km=0.0, jam_chuo_km=0.0):
    """
    Excel「渋滞見積り.xlsx」の計算ロジックに基づき、各ルートの所要時間・最適ルート・倍率を算出
    """
    # ----------------------------------------------------
    # 1. 基礎パラメータ設定（Excelの入力テーブル・速度設定）
    # ----------------------------------------------------
    speed_general_normal = 40.0   # 一般道 通常速度 (km/h)
    speed_express_normal = 80.0   # 高速道 通常速度 (km/h) - AVERAGE(80, 80)
    speed_jam = 12.0              # 渋滞時速度 (km/h)

    # 全高速Ref（通常時参照値）
    dist_ref_general = 3.4       # 一般道区間 (km)
    dist_ref_express = 27.8      # 高速区間 (km)
    
    # 全高速Refの通常所要時間 (分) [Excel D12]
    time_ref_min = round((dist_ref_general / speed_general_normal * 60) + 
                         (dist_ref_express / speed_express_normal * 60), 0)

    # ----------------------------------------------------
    # 2. 各ルートの計算ロジック
    # ----------------------------------------------------
    
    # --- ① 全高速ルート ---
    # 渋滞距離: 長野道 + 中央道
    jam_express_total = jam_nagano_km + jam_chuo_km
    dist_r1_general = dist_ref_general
    dist_r1_express_jam = jam_express_total
    dist_r1_express_normal = max(0.0, dist_ref_express - dist_r1_express_jam)
    
    time_r1 = round(
        (dist_r1_general / speed_general_normal * 60) +
        (dist_r1_express_normal / speed_express_normal * 60) +
        (dist_r1_express_jam / speed_jam * 60), 0
    )

    # --- ② 一般道併用ルート ---
    dist_r2_general = 15.4
    dist_r2_express_total = 14.0
    dist_r2_jam = jam_general_km  # 一般道側の渋滞
    dist_r2_express_normal = max(0.0, dist_r2_express_total - dist_r2_jam)
    
    time_r2 = round(
        (dist_r2_general / speed_general_normal * 60) +
        (dist_r2_express_normal / speed_express_normal * 60) +
        (dist_r2_jam / speed_jam * 60), 0
    )

    # --- ③ 全一般道ルート ---
    dist_r3_general = 31.6
    dist_r3_jam = jam_general_km
    dist_r3_normal = max(0.0, dist_r3_general - dist_r3_jam)
    
    time_r3 = round(
        (dist_r3_normal / speed_general_normal * 60) +
        (dist_r3_jam / speed_jam * 60), 0
    )

    # ----------------------------------------------------
    # 3. 判定ロジック（適正ルートの選出）
    # ----------------------------------------------------
    routes = [
        {"name": "①全高速", "time": time_r1},
        {"name": "②一般道併用", "time": time_r2},
        {"name": "③全一般道", "time": time_r3}
    ]

    # 最低所要時間のルートを取得 [Excel MIN(D13:D15)]
    best_route = min(routes, key=lambda x: x["time"])
    best_time = int(best_route["time"])
    best_name = best_route["name"]

    # 倍率計算（通常時Refに対する比率） [Excel ROUND(XLOOKUP(...)/D12, 2)]
    ratio = round(best_time / time_ref_min, 2)

    # 到着見込み時刻の計算 (JST)
    now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9)))
    eta = now + datetime.timedelta(minutes=best_time)
    eta_str = eta.strftime("%Y-%m-%d %H:%M:%S")

    # ----------------------------------------------------
    # 4. メッセージ構築
    # ----------------------------------------------------
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

    return {
        "best_name": best_name,
        "best_time": best_time,
        "ratio": ratio,
        "eta": eta_str,
        "message": msg
    }


def send_line_push(text_content):
    url = "https://api.line.me/v2/bot/message/push"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"
    }
    payload = {
        "to": LINE_USER_ID,
        "messages": [{"type": "text", "text": text_content}]
    }
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        response.raise_for_status()
        return True
    except Exception as e:
        print(f"LINE送信エラー: {e}", file=sys.stderr)
        return False


# Vercel Serverless Function エントリーポイント
def handler(request):
    # 画像解析やAPI等から取得した各区間の渋滞距離(km)を入力
    # 例: 一般道 3km, 長野道 6km, 中央道 2km
    jam_general = 3.0
    jam_nagano = 6.0
    jam_chuo = 2.0

    # Excelのロジックに基づく見積り計算
    result = calculate_traffic_estimate(
        jam_general_km=jam_general, 
        jam_nagano_km=jam_nagano, 
        jam_chuo_km=jam_chuo
    )
    
    # LINEへ結果を送信
    send_line_push(result["message"])

    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json; charset=utf-8"},
        "body": {
            "status": "success",
            "data": result
        }
    }
