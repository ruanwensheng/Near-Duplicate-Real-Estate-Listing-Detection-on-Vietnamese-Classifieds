"""
Sinh các cặp tin ứng viên để gán nhãn  ->  labels/candidates.csv

Ý tưởng:
  1. BLOCKING: chỉ ghép cặp những tin "có thể là cùng căn":
       cùng khu vực + cùng quận + cùng số phòng ngủ
       + diện tích chênh <= 3 m²  + giá chênh <= 15%
     (không ghép bừa mọi cặp: 5.600 tin -> 15 triệu cặp, gần như toàn "không trùng")
  2. Tính độ giống văn bản (Jaccard trên cặp từ liên tiếp) cho mỗi cặp.
  3. LẤY MẪU PHÂN TẦNG theo độ giống: cao / trung bình / thấp + vài cặp ngẫu nhiên,
     để tập nhãn có đủ cả cặp dễ lẫn cặp khó.

Chạy (từ thư mục gốc):  python src\\label\\make_pairs.py
Đã có candidates.csv thì không ghi đè (vì nhãn tham chiếu pair_id). Muốn tạo lại: --force
"""
import argparse
import re
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

OUT = Path("labels/candidates.csv")
SEED = 42

# Số cặp muốn lấy cho từng tầng (tổng ~500)
QUOTA = {"high": 200, "mid": 200, "low": 70, "random": 30}
HIGH, LOW = 0.5, 0.2          # ngưỡng Jaccard: >=0.5 cao, <0.2 thấp, còn lại trung bình
MAX_SIZE_DIFF = 3             # m²
MAX_PRICE_RATIO = 0.15        # 15%


def load_listings() -> pd.DataFrame:
    con = duckdb.connect()
    return con.sql("""
        WITH snap AS (SELECT * FROM read_parquet('data/snapshots/*/*.parquet',
                         hive_partitioning = true, union_by_name = true)),
             latest AS (SELECT * EXCLUDE (rn) FROM (
                 SELECT *, row_number() OVER (PARTITION BY list_id ORDER BY crawl_date DESC) rn
                 FROM snap) WHERE rn = 1)
        SELECT list_id, region_v2, area_v2, coalesce(rooms, -1) AS rooms,
               size, price, subject, body
        FROM latest
        WHERE size > 0 AND price > 0
    """).df()


def shingles(text: str) -> set:
    """Tập các cặp từ liên tiếp (word bigram), đã viết thường, bỏ dấu câu/emoji."""
    words = re.findall(r"\w+", (text or "").lower())
    return {" ".join(words[i:i + 2]) for i in range(len(words) - 1)} or set(words)


def jaccard(a: set, b: set) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


def blocked_pairs(df: pd.DataFrame) -> pd.DataFrame:
    key = ["region_v2", "area_v2", "rooms"]
    cols = key + ["list_id", "size", "price"]
    p = df[cols].merge(df[cols], on=key, suffixes=("_a", "_b"))
    p = p[p.list_id_a < p.list_id_b]                                   # mỗi cặp 1 lần
    p = p[(p.size_a - p.size_b).abs() <= MAX_SIZE_DIFF]
    p = p[(p.price_a - p.price_b).abs() / p[["price_a", "price_b"]].max(axis=1)
          <= MAX_PRICE_RATIO]
    return p[["list_id_a", "list_id_b"]].rename(columns={"list_id_a": "id_a",
                                                         "list_id_b": "id_b"})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    if OUT.exists() and not args.force:
        print(f"{OUT} đã tồn tại. Dùng --force nếu muốn tạo lại (nhãn cũ sẽ không khớp).")
        return

    rng = np.random.default_rng(SEED)
    df = load_listings()
    print(f"Số tin hợp lệ: {len(df)}")

    pairs = blocked_pairs(df)
    print(f"Số cặp sau blocking: {len(pairs)}")
    if len(pairs) > 300_000:                       # giới hạn để tính nhanh
        pairs = pairs.sample(300_000, random_state=SEED)

    sh = {r.list_id: shingles(f"{r.subject} {r.body}") for r in df.itertuples()}
    pairs["jaccard"] = [jaccard(sh[a], sh[b]) for a, b in zip(pairs.id_a, pairs.id_b)]
    pairs["stratum"] = np.where(pairs.jaccard >= HIGH, "high",
                        np.where(pairs.jaccard < LOW, "low", "mid"))

    # Cặp ngẫu nhiên (không qua blocking) -> gần như chắc chắn "không trùng", dùng để kiểm tra
    ids = df.list_id.to_numpy()
    rnd = pd.DataFrame({"id_a": rng.choice(ids, QUOTA["random"] * 3),
                        "id_b": rng.choice(ids, QUOTA["random"] * 3)})
    rnd = rnd[rnd.id_a != rnd.id_b].head(QUOTA["random"])
    rnd["jaccard"] = [jaccard(sh[a], sh[b]) for a, b in zip(rnd.id_a, rnd.id_b)]
    rnd["stratum"] = "random"

    parts = []
    for s in ["high", "mid", "low"]:
        g = pairs[pairs.stratum == s]
        parts.append(g.sample(min(len(g), QUOTA[s]), random_state=SEED))
    parts.append(rnd)
    cand = pd.concat(parts).sample(frac=1, random_state=SEED)   # xáo trộn thứ tự
    cand.insert(0, "pair_id", range(1, len(cand) + 1))

    OUT.parent.mkdir(exist_ok=True)
    cand.to_csv(OUT, index=False)
    print(f"Đã lưu {len(cand)} cặp -> {OUT}")
    print("Số cặp có sẵn theo tầng:", pairs.stratum.value_counts().to_dict())
    print("Số cặp đã chọn theo tầng:", cand.stratum.value_counts().to_dict())


if __name__ == "__main__":
    main()
