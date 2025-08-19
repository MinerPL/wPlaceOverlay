# app.py
import os
import os.path
import json
import shutil
import threading
import time

from flask import Flask, jsonify
from PIL import Image
from curl_cffi import requests

# -------------------- Config --------------------
PORT = 8000
UPDATE_INTERVAL_SECONDS = 60  # matches the old httpd.timeout behavior

# --- Palette mapping: RGB -> color-id (from your palette snippet) ---
RGB_TO_ID = {
    (0, 0, 0): 1,
    (60, 60, 60): 2,
    (120, 120, 120): 3,
    (170, 170, 170): 32,
    (210, 210, 210): 4,
    (255, 255, 255): 5,
    (96, 0, 24): 6,
    (165, 14, 30): 33,
    (237, 28, 36): 7,
    (250, 128, 114): 34,
    (228, 92, 26): 35,
    (255, 127, 39): 8,
    (246, 170, 9): 9,
    (249, 221, 59): 10,
    (255, 250, 188): 11,
    (156, 132, 49): 37,
    (197, 173, 49): 38,
    (232, 212, 95): 39,
    (74, 107, 58): 40,
    (90, 148, 74): 41,
    (132, 197, 115): 42,
    (14, 185, 104): 12,
    (19, 230, 123): 13,
    (135, 255, 94): 14,
    (12, 129, 110): 15,
    (16, 174, 166): 16,
    (19, 225, 190): 17,
    (15, 121, 159): 43,
    (96, 247, 242): 20,
    (187, 250, 242): 44,
    (40, 80, 158): 18,
    (64, 147, 228): 19,
    (125, 199, 255): 45,
    (77, 49, 184): 46,
    (107, 80, 246): 21,
    (153, 177, 251): 22,
    (74, 66, 132): 47,
    (122, 113, 196): 48,
    (181, 174, 241): 49,
    (120, 12, 153): 23,
    (170, 56, 185): 24,
    (224, 159, 249): 25,
    (203, 0, 122): 26,
    (236, 31, 128): 27,
    (243, 141, 169): 28,
    (155, 82, 73): 53,
    (209, 128, 120): 54,
    (250, 182, 164): 55,
    (104, 70, 52): 29,
    (149, 104, 42): 30,
    (219, 164, 99): 50,
    (123, 99, 82): 56,
    (156, 132, 107): 57,
    (214, 181, 148): 36,
    (209, 128, 81): 51,
    (248, 178, 119): 31,
    (255, 197, 165): 52,
    (109, 100, 63): 61,
    (148, 140, 107): 62,
    (205, 197, 158): 63,
    (51, 57, 65): 58,
    (109, 117, 141): 59,
    (179, 185, 209): 60,
}

# -------------------- Globals --------------------
TILES = {}
stop_event = threading.Event()

# -------------------- Core Logic --------------------
def rgb_to_color_id(rgb):
    """Return palette color-id for an (R,G,B) tuple, or None if unknown."""
    return RGB_TO_ID.get(rgb)

def updateImage():
    """
    Downloads current tiles, ensures blueprints exist, computes diffs,
    writes highlighted base images, and updates global TILES payload.
    """
    global TILES

    with open("config.json") as f:
        tiles = json.load(f)

    TILES = {}
    missing_pix = 0

    for tile in tiles:
        # tile like [folder, filename] based on your original code
        folder, name = tile[0], tile[1]

        basepath = f'files/s0/tiles/{folder}/{name}.png'
        blueprintpath = f'blueprints/{folder}/{name}blueprint.png'

        # fetch image from remote
        image_url = f"https://backend.wplace.live/files/s0/tiles/{folder}/{name}.png"
        img_data = requests.get(image_url, impersonate="chrome", timeout=100000).content

        os.makedirs(os.path.dirname(basepath), exist_ok=True)
        with open(basepath, 'wb') as handler:
            handler.write(img_data)

        if not os.path.isfile(blueprintpath):
            os.makedirs(os.path.dirname(blueprintpath), exist_ok=True)
            shutil.copyfile(basepath, blueprintpath)

        basepic = Image.open(basepath).convert('RGBA')
        basepix = basepic.load()

        blueprint = Image.open(blueprintpath).convert('RGBA')
        blueprintpix = blueprint.load()

        width, height = basepic.size
        identical = True
        xmin, xmax, ymin, ymax = 999, 0, 999, 0
        diff = []  # [((x,y), (r,g,b,a))]

        for x in range(width):
            for y in range(height):
                bp = blueprintpix[x, y]  # (r,g,b,a)
                if bp != (0, 0, 0, 0) and bp != basepix[x, y]:
                    missing_pix += 1
                    identical = False
                    xmin = min(x, xmin)
                    xmax = max(x, xmax)
                    ymin = min(y, ymin)
                    ymax = max(y, ymax)
                    diff.append(((x, y), (bp[0], bp[1], bp[2], 255)))

                    # --- Add to public API payload (map to palette id) ---
                    color_id = rgb_to_color_id((bp[0], bp[1], bp[2]))
                    if color_id is not None:
                        TILES.setdefault(folder, {}).setdefault(name, {})
                        TILES[folder][name].setdefault("colors", [])
                        TILES[folder][name].setdefault("coords", [])
                        TILES[folder][name]["colors"].append(color_id)
                        TILES[folder][name]["coords"].extend([x, y])

        if not identical:
            # highlight bbox on the base image
            for x in range(xmin - 4, xmax + 5):
                for y in range(ymin - 4, ymax + 5):
                    if x < 0 or y < 0 or x > width - 1 or y > height - 1:
                        continue
                    basepix[x, y] = (255, 0, 255, 80)
            # set target pixels to blueprint colors
            for (x, y), rgba in diff:
                basepix[x, y] = rgba
            basepic.save(basepath, 'PNG')

        basepic.close()
        blueprint.close()

    print(
        "Updated diff. Missing pixels: {} ~ {} hours to regenerate".format(
            missing_pix, round(missing_pix / 2 / 60, 1)
        )
    )

# -------------------- Flask App --------------------
# Serve the working directory as static to mimic SimpleHTTPRequestHandler behavior
app = Flask(__name__, static_folder=".", static_url_path="")

@app.after_request
def add_cors_headers(resp):
    # Mirror the wildcard CORS header you added in the HTTP server
    resp.headers["Access-Control-Allow-Origin"] = "*"
    return resp

@app.route("/colors", methods=["GET"])
def colors():
    updateImage()
    # Just like your custom endpoint
    return jsonify(TILES)

@app.route("/update", methods=["POST", "GET"])
def manual_update():
    # Optional: manual trigger if you want an immediate refresh
    updateImage()
    return jsonify({"ok": True, "message": "Update complete."})

# -------------------- Background Updater --------------------
def updater_loop():
    # Run once on startup, then every UPDATE_INTERVAL_SECONDS
    try:
        updateImage()
    except Exception as e:
        print(f"Initial update failed: {e}")

    while not stop_event.wait(UPDATE_INTERVAL_SECONDS):
        try:
            updateImage()
        except Exception as e:
            print(f"Periodic update failed: {e}")

# -------------------- Entrypoint --------------------
if __name__ == "__main__":
    t = threading.Thread(target=updater_loop, name="tiles-updater", daemon=True)
    t.start()
    # Host/port compatible with your previous server defaults
    app.run(host="0.0.0.0", port=PORT)
