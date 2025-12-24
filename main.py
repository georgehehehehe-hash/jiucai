import io
import requests
from fastapi import FastAPI, HTTPException
from PIL import Image
from google.cloud import storage
import os
from urllib.parse import urlparse

# --- 配置 ---
try:
    GCS_BUCKET_NAME = os.environ['GCS_BUCKET_NAME']
except KeyError:
    raise Exception("GCS_BUCKET_NAME environment variable not set. Deployment failed.")

GRID_SIZE = 6  # 切成 6x6

# 初始化
app = FastAPI()
storage_client = storage.Client()


@app.post("/slice")
async def slice_image(request_body: dict):
    image_url = request_body.get("imageUrl")

    if not image_url:
        raise HTTPException(status_code=400, detail="Missing 'imageUrl' in request body.")

    parsed = urlparse(image_url)
    basename = os.path.basename(parsed.path)
    unique_id = os.path.splitext(basename)[0]

    # 1. 下载图片
    try:
        resp = requests.get(image_url, stream=True)
        resp.raise_for_status()
        img = Image.open(io.BytesIO(resp.content))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to download or open image: {e}")

    W, H = img.size

    # ------------------------------------------------------
    # ⭐ 自动调整尺寸到可被 6 整除（自动裁剪）
    # ------------------------------------------------------
    new_w = W - (W % GRID_SIZE)
    new_h = H - (H % GRID_SIZE)

    if new_w != W or new_h != H:
        img = img.crop((0, 0, new_w, new_h))
        W, H = new_w, new_h
    # ------------------------------------------------------

    w_slice = W // GRID_SIZE
    h_slice = H // GRID_SIZE

    bucket = storage_client.bucket(GCS_BUCKET_NAME)
    results = []

    # 2. 切割并上传
    for i in range(GRID_SIZE):
        for j in range(GRID_SIZE):
            left = j * w_slice
            upper = i * h_slice
            right = left + w_slice
            lower = upper + h_slice

            cropped = img.crop((left, upper, right, lower))

            border = 5
            # 确保子图尺寸大于要裁掉的边界，避免报错
            if cropped.width > border * 2 and cropped.height > border * 2:
                cropped = cropped.crop((
                    border,          # 左边界向内缩
                    border,          # 上边界向内缩
                    cropped.width - border,  # 右边界向内缩
                    cropped.height - border  # 下边界向内缩
                ))

            img_bytes = io.BytesIO()
            cropped.save(img_bytes, format="JPEG")
            img_bytes.seek(0)

            index = i * GRID_SIZE + j + 1
            filename = f"{unique_id}_slice_{W}x{H}_{index}.jpg"

            blob = bucket.blob(filename)
            blob.upload_from_file(img_bytes, content_type="image/jpeg")

            results.append(blob.public_url)

    return {"status": "success", "urls": results}


@app.get("/")
def root():
    return {"Hello": "Image Slicer API is running"}
