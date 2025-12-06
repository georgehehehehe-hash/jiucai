import io
import requests
from fastapi import FastAPI, HTTPException
from PIL import Image
from google.cloud import storage

# --- 配置 ---
GCS_BUCKET_NAME = "your-gcs-bucket-name"  # <-- 替换成您的 GCS 存储桶名称！
GRID_SIZE = 4  # 4x4 宫格

# 初始化 FastAPI 和 GCS 客户端
app = FastAPI()
storage_client = storage.Client()


@app.post("/slice")
async def slice_image(request_body: dict):
    """
    接收图片 URL，切割成 4x4 宫格，上传到 GCS，并返回 16 个 URL。
    """
    image_url = request_body.get("imageUrl")
    if not image_url:
        raise HTTPException(status_code=400, detail="Missing 'imageUrl' in request body.")

    # 1. 下载图片
    try:
        response = requests.get(image_url, stream=True)
        response.raise_for_status()
        original_img = Image.open(io.BytesIO(response.content))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to download or open image: {e}")

    # 确保图片是正方形，或者可以被 4 整除 (您的图片是 4x4)
    W, H = original_img.size
    w_slice = W // GRID_SIZE
    h_slice = H // GRID_SIZE

    if W % GRID_SIZE != 0 or H % GRID_SIZE != 0:
        raise HTTPException(status_code=400, detail="Image dimensions are not divisible by 4.")

    bucket = storage_client.bucket(GCS_BUCKET_NAME)
    results = []

    # 2. 切割并上传
    for i in range(GRID_SIZE):  # 行 (0, 1, 2, 3)
        for j in range(GRID_SIZE):  # 列 (0, 1, 2, 3)
            # 裁剪坐标 (left, upper, right, lower)
            left = j * w_slice
            upper = i * h_slice
            right = (j + 1) * w_slice
            lower = (i + 1) * h_slice

            cropped_img = original_img.crop((left, upper, right, lower))

            # 将图片保存到内存中，准备上传
            img_byte_arr = io.BytesIO()
            cropped_img.save(img_byte_arr, format="JPEG")  # 假设保存为 JPEG
            img_byte_arr.seek(0)

            # 文件名：使用时间戳和序号确保唯一性
            filename = f"slice_{W}x{H}_{i * GRID_SIZE + j + 1}.jpg"

            # 上传到 GCS
            blob = bucket.blob(filename)
            blob.upload_from_file(img_byte_arr, content_type='image/jpeg')

            # 设置公开访问权限 (如果存储桶策略允许)
            blob.make_public()

            results.append(blob.public_url)

    return {"status": "success", "urls": results}


# 用于健康检查
@app.get("/")
def read_root():
    return {"Hello": "Image Slicer API is running"}