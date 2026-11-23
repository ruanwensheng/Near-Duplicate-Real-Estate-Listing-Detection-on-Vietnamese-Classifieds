import argparse
import sys

import duckdb

sys.path.insert(0, "src/label")
from make_pairs import blocked_pairs  # noqa: E402


def load_listings(until: str | None):
    where = f"WHERE CAST(crawl_date AS DATE) <= DATE '{until}'" if until else ""
    return duckdb.connect().sql(f"""
        WITH snap AS (SELECT * FROM read_parquet('data/snapshots/*/*.parquet',
                         hive_partitioning = true, union_by_name = true) {where}),
             latest AS (SELECT * EXCLUDE (rn) FROM (
                 SELECT *, row_number() OVER (PARTITION BY list_id ORDER BY crawl_date DESC) rn
                 FROM snap) WHERE rn = 1)
        SELECT list_id, region_v2, area_v2, coalesce(rooms, -1) AS rooms,
               size, price, subject, body
        FROM latest
        WHERE size > 0 AND price > 0
    """).df()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--until", default=None, help="YYYY-MM-DD, ngày chạy make_pairs.py")
    args = ap.parse_args()

    df = load_listings(args.until)
    pairs = blocked_pairs(df)
    print(f"Snapshot đến ngày: {args.until or 'tất cả'}")
    print(f"Số tin hợp lệ (size > 0, price > 0): {len(df)}")
    print(f"Số cặp sau blocking: {len(pairs)}")
    print(f"Số cặp nếu so toàn bộ: {len(df) * (len(df) - 1) // 2}")


if __name__ == "__main__":
    main()