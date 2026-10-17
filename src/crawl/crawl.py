"""
Crawler tin đăng căn hộ trên Chợ Tốt Nhà.

Mỗi lần chạy:
  1. Với mỗi khu vực trong REGIONS, gọi API lần lượt o=0, 20, 40... đến khi hết tin.
  2. Lưu JSON gốc của từng trang  -> data/raw/<ngày>/<region>/o_<offset>.json
     (đã xoá tên thật, id người đăng đã hash)
  3. Gộp các trường cần thiết thành 1 bảng -> data/snapshots/crawl_date=<ngày>/<region>.parquet

Chạy:  python crawl.py                 (mặc định Hà Nội + TP.HCM)
       python crawl.py --regions 12000 (chỉ Hà Nội)
Chạy lại trong cùng ngày sẽ bỏ qua các trang đã tải (resume).
"""
import argparse
import hashlib
import json
import random
import secrets
import time
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests

# ---------------- Cấu hình ----------------
URL = "https://gateway.chotot.com/v1/public/ad-listing"
HEADERS = {"User-Agent": "Mozilla/5.0", "Referer": "https://www.nhatot.com/"}
CATEGORY = 1010                      # Căn hộ/Chung cư
AD_TYPE = "s"                        # s = cần bán
REGIONS = {12000: "hanoi", 13000: "hcm"}
LIMIT = 20                           # số tin mỗi request
SLEEP = (1.0, 2.0)                   # nghỉ ngẫu nhiên 1-2 giây giữa các request
MAX_RETRIES = 4

DATA = Path("data")
SALT_FILE = DATA / ".salt"           # khoá bí mật để hash, KHÔNG chia sẻ/commit file này

# Trường chứa thông tin cá nhân -> xoá trước khi lưu
PII_FIELDS = ["account_name", "full_name", "avatar", "account_id", "seller_info"]

# Trường giữ lại trong bảng Parquet
KEEP = [
    "list_id", "ad_id", "subject", "body",
    "price", "original_price", "price_diff", "price_million_per_m2",
    "size", "rooms", "toilets", "floornumber", "unitnumber", "block",
    "direction", "balconydirection", "furnishing_sell",
    "property_legal_document", "property_status", "apartment_type",
    "projectid", "pty_project_name",
    "region_v2", "region_name", "area_v2", "area_name", "ward", "ward_name",
    "street_name", "street_number", "latitude", "longitude",
    "company_ad", "list_time", "orig_list_time", "number_of_images",
]


# ---------------- Hàm tiện ích ----------------
def get_salt() -> str:
    """Tạo (lần đầu) hoặc đọc khoá bí mật dùng để hash id người đăng."""
    DATA.mkdir(exist_ok=True)
    if not SALT_FILE.exists():
        SALT_FILE.write_text(secrets.token_hex(16))
    return SALT_FILE.read_text().strip()


def hash_id(value, salt: str):
    if value is None:
        return None
    return hashlib.sha256(f"{salt}:{value}".encode()).hexdigest()[:16]


def sanitize(ad: dict, salt: str) -> dict:
    """Xoá thông tin cá nhân, thay id người đăng bằng mã hash."""
    ad = dict(ad)
    live_ads = (ad.get("seller_info") or {}).get("live_ads")
    ad["seller_hash"] = hash_id(ad.get("account_oid"), salt)
    ad["seller_live_ads"] = live_ads
    ad.pop("account_oid", None)
    for f in PII_FIELDS:
        ad.pop(f, None)
    return ad


def fetch(params: dict) -> dict:
    """Gọi API, tự thử lại khi lỗi mạng / bị chặn tạm thời (429, 5xx)."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            r = requests.get(URL, params=params, headers=HEADERS, timeout=20)
            if r.status_code == 200:
                return r.json()
            print(f"    HTTP {r.status_code} (lần {attempt})")
        except requests.RequestException as e:
            print(f"    Lỗi mạng: {e} (lần {attempt})")
        time.sleep(5 * attempt)       # chờ lâu dần: 5s, 10s, 15s...
    raise RuntimeError(f"Thất bại sau {MAX_RETRIES} lần: {params}")


def to_row(ad: dict) -> dict:
    row = {k: ad.get(k) for k in KEEP}
    row["seller_hash"] = ad.get("seller_hash")
    row["seller_live_ads"] = ad.get("seller_live_ads")
    row["images"] = ad.get("images") or []
    return row


# Kiểu dữ liệu cố định cho từng cột, để mọi file Parquet có cùng schema
INT_COLS = ["list_id", "ad_id", "list_time", "orig_list_time"]
STR_COLS = ["subject", "body", "unitnumber", "block", "pty_project_name", "region_name",
            "area_name", "ward_name", "street_name", "street_number", "seller_hash"]
BOOL_COLS = ["company_ad"]


def fix_types(df: pd.DataFrame) -> pd.DataFrame:
    for c in df.columns:
        if c == "images":
            continue
        if c in STR_COLS:
            df[c] = df[c].astype("string").str.strip().replace("", pd.NA)  # "" -> rỗng thật
        elif c in BOOL_COLS:
            df[c] = df[c].astype("boolean")
        elif c in INT_COLS:
            df[c] = pd.to_numeric(df[c], errors="coerce").astype("Int64")
        else:                                   # các cột số còn lại
            df[c] = pd.to_numeric(df[c], errors="coerce").astype("Float64")
    return df


# ---------------- Crawl 1 khu vực ----------------
def crawl_region(region: int, name: str, crawl_date: str, salt: str) -> pd.DataFrame:
    raw_dir = DATA / "raw" / crawl_date / name
    raw_dir.mkdir(parents=True, exist_ok=True)
    rows, offset, total = [], 0, None

    while True:
        page_file = raw_dir / f"o_{offset:05d}.json"
        if page_file.exists():                       # đã tải trong lần chạy trước -> dùng lại
            page = json.loads(page_file.read_text(encoding="utf-8"))
        else:
            params = {"cg": CATEGORY, "region_v2": region, "st": AD_TYPE,
                      "limit": LIMIT, "o": offset}
            page = fetch(params)
            page["ads"] = [sanitize(a, salt) for a in page.get("ads", [])]
            page_file.write_text(json.dumps(page, ensure_ascii=False), encoding="utf-8")
            time.sleep(random.uniform(*SLEEP))

        ads = page.get("ads", [])
        total = total or page.get("total")
        if not ads:                                   # hết tin
            break
        rows.extend(to_row(a) for a in ads)
        offset += LIMIT
        print(f"  [{name}] {offset}/{total}", end="\r")

    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df = fix_types(df)
    # Trong lúc crawl có tin mới chen lên đầu -> 1 tin có thể bị lấy 2 lần. Bỏ bản lặp.
    df = df.drop_duplicates("list_id", keep="first")
    print(f"  [{name}] xong: {len(df)} tin (API báo total={total})      ")
    return df


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--regions", type=int, nargs="+", default=list(REGIONS))
    args = ap.parse_args()

    salt = get_salt()
    crawl_date = datetime.now().strftime("%Y-%m-%d")
    out_dir = DATA / "snapshots" / f"crawl_date={crawl_date}"
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Crawl ngày {crawl_date}")
    for region in args.regions:
        name = REGIONS.get(region, str(region))
        df = crawl_region(region, name, crawl_date, salt)
        if not df.empty:
            df.to_parquet(out_dir / f"{name}.parquet", index=False)
    print("Hoàn tất. Chạy `python summary.py` để xem thống kê.")


if __name__ == "__main__":
    main()
