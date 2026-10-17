"""
Thống kê nhanh dữ liệu đã crawl (đọc toàn bộ snapshot bằng DuckDB).
Chạy: python summary.py
"""
import duckdb

SNAP = "data/snapshots/*/*.parquet"
con = duckdb.connect()
con.execute(f"""
    CREATE VIEW snap AS
    SELECT * FROM read_parquet('{SNAP}', hive_partitioning = true, union_by_name = true)
""")
# Mỗi list_id chỉ giữ bản mới nhất (lần crawl gần nhất)
con.execute("""
    CREATE VIEW listings AS
    SELECT * EXCLUDE (rn) FROM (
        SELECT *, row_number() OVER (PARTITION BY list_id ORDER BY crawl_date DESC) AS rn
        FROM snap) WHERE rn = 1
""")

def show(title, sql):
    print(f"\n=== {title} ===")
    print(con.sql(sql))

show("Số tin theo ngày crawl và khu vực", """
    SELECT crawl_date, region_name, count(*) AS so_tin
    FROM snap GROUP BY ALL ORDER BY ALL
""")

show("Tổng số tin khác nhau đã thu thập (cộng dồn mọi ngày)", """
    SELECT region_name, count(*) AS so_tin_unique,
           count(DISTINCT seller_hash) AS so_nguoi_dang
    FROM listings GROUP BY ALL
""")

show("Tỷ lệ có dữ liệu của các trường quan trọng (%)", """
    SELECT round(100 * avg((pty_project_name IS NOT NULL)::INT), 1) AS du_an,
           round(100 * avg((floornumber IS NOT NULL)::INT), 1)      AS tang,
           round(100 * avg((unitnumber IS NOT NULL)::INT), 1)       AS ma_can,
           round(100 * avg((block IS NOT NULL)::INT), 1)            AS toa,
           round(100 * avg((rooms IS NOT NULL)::INT), 1)            AS phong_ngu
    FROM listings
""")

show("Trùng tuyệt đối: cùng nội dung mô tả nhưng khác list_id", """
    SELECT count(*) AS so_nhom, sum(n) AS so_tin_lien_quan FROM (
        SELECT md5(lower(trim(body))) AS h, count(*) AS n
        FROM listings GROUP BY h HAVING n > 1)
""")

show("Ứng viên trùng: cùng dự án + diện tích + giá + số phòng ngủ", """
    SELECT pty_project_name, size, price, rooms, count(*) AS n,
           count(DISTINCT seller_hash) AS so_nguoi_dang
    FROM listings
    WHERE pty_project_name IS NOT NULL
    GROUP BY ALL HAVING n > 1
    ORDER BY n DESC LIMIT 10
""")

show("Top người đăng nhiều tin nhất", """
    SELECT seller_hash, count(*) AS so_tin,
           count(DISTINCT pty_project_name) AS so_du_an,
           bool_or(company_ad) AS la_moi_gioi
    FROM listings GROUP BY seller_hash ORDER BY so_tin DESC LIMIT 10
""")
