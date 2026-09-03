import cv2
import numpy as np
import math
import requests
from io import BytesIO
from PIL import Image
from datetime import datetime
import json
from http.server import BaseHTTPRequestHandler

API_KEY = "AIzaSyDrc_p4i9gRvUBNPKmBvlSh_jcoBKLrhiU"
CENTER_LAT = 36.057
CENTER_LNG = 138.045
ZOOM = 11

def get_map_image():
    url = (
        f"https://maps.googleapis.com/maps/api/staticmap?"
        f"center={CENTER_LAT},{CENTER_LNG}&zoom={ZOOM}&size=1024x1024"
        f"&maptype=roadmap&key={API_KEY}&layer=traffic"
    )
    response = requests.get(url, timeout=10)
    response.raise_for_status()
    return Image.open(BytesIO(response.content))

def extract_red_distance(img_cv):
    hsv = cv2.cvtColor(img_cv, cv2.COLOR_BGR2HSV)

    lower_red1 = np.array([0, 70, 50])
    upper_red1 = np.array([10, 255, 255])
    lower_red2 = np.array([170, 70, 50])
    upper_red2 = np.array([180, 255, 255])

    mask1 = cv2.inRange(hsv, lower_red1, upper_red1)
    mask2 = cv2.inRange(hsv, lower_red2, upper_red2)
    mask = cv2.bitwise_or(mask1, mask2)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    total_pixels = 0
    for cnt in contours:
        total_pixels += cv2.arcLength(cnt, False)

    meters_per_pixel = 156543.03392 * math.cos(math.radians(CENTER_LAT)) / (2 ** ZOOM)
    distance_km = (total_pixels * meters_per_pixel) / 1000
    return distance_km

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            img = get_map_image()
            img_cv = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
            distance_km = extract_red_distance(img_cv)

            result = {
                "nagano": round(distance_km * 0.55, 2),
                "chuo": round(distance_km * 0.45, 2),
                "total": round(distance_km, 2),
                "updated": datetime.now().strftime("%Y-%m-%d %H:%M")
            }

            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(result).encode('utf-8'))

        except Exception as e:
            self.send_response(500)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            error_msg = {"error": str(e)}
            self.wfile.write(json.dumps(error_msg).encode('utf-8'))
