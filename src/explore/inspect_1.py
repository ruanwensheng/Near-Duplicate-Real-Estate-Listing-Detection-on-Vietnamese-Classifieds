"""
Điều tra nhanh 3 điểm từ summary.py:
  A. Tài khoản đăng ~1000 tin là ai?
  B. Trùng tuyệt đối: cùng người đăng lại hay nhiều người copy?
  C. Một nhóm ứng viên trùng nhìn cụ thể ra sao?
Chạy: python inspect_1.py > inspect_1.txt   rồi gửi file inspect_1.txt
"""
import duckdb

con = duckdb.connect()
con.execute("""
    CREATE VIEW snap AS SELECT * FROM read_parquet('data/snapshots/*/*.parquet',
        hive_partitioning = true, union_by_name = true);
    CREATE VIEW listings AS SELECT * EXCLUDE (rn) FROM (
        SELECT *, row_number() OVER (PARTITION BY list_id ORDER BY crawl_date DESC) AS rn
        FROM snap) WHERE rn = 1;
""")

def show(title, sql, max_width=250):
    print(f"\n=== {title} ===")
    con.sql(sql).show(max_width=max_width, max_rows=40)

# ---------- A. Tài khoản lớn nhất ----------
top = con.sql("""SELECT seller_hash FROM listings GROUP BY 1
                 ORDER BY count(*) DESC LIMIT 1""").fetchone()[0]
con.execute(f"CREATE VIEW top_seller AS SELECT * FROM listings WHERE seller_hash = '{top}'")

show("A1. Tài khoản lớn nhất: phân bố khu vực & thông tin chung", """
    SELECT region_name, 
           count(*) AS so_tin,
           any_value(seller_live_ads) AS live_ads, 
           bool_or(company_ad) AS moi_gioi,
           round(avg(number_of_images), 1) AS anh_tb,
           count(DISTINCT md5(body)) AS so_mo_ta_khac_nhau,
           round(100 * avg((pty_project_name IS NOT NULL)::INT), 1) AS pct_co_du_an
    FROM top_seller GROUP BY 1
""")
show("A2. Tài khoản lớn nhất: 8 tin mẫu", """
    SELECT list_id, area_name, size, price / 1e9 AS gia_ty, rooms,
           left(subject, 60) AS tieu_de,
           left(replace(body, chr(10), ' '), 140) AS mo_ta
    FROM top_seller USING SAMPLE 8 ROWS (reservoir, 42)
""")
show("A3. Tài khoản lớn nhất: thời gian đăng gốc", """
    SELECT min(epoch_ms(orig_list_time::BIGINT))::DATE AS som_nhat,
           max(epoch_ms(orig_list_time::BIGINT))::DATE AS muon_nhat
    FROM top_seller
""")

# ---------- B. Trùng tuyệt đối ----------
show("B1. Trùng tuyệt đối: cùng người hay khác người?", """
    WITH g AS (
        SELECT md5(lower(trim(body))) AS h, count(*) AS n,
               count(DISTINCT seller_hash) AS so_nguoi
        FROM listings GROUP BY h HAVING n > 1)
    SELECT CASE WHEN so_nguoi = 1 THEN 'cung 1 nguoi dang lai'
                ELSE 'nhieu nguoi cung noi dung' END AS loai,
           count(*) AS so_nhom, sum(n) AS so_tin
    FROM g GROUP BY 1
""")
show("B2. Trùng tuyệt đối: có thuộc tài khoản lớn nhất không?", f"""
    WITH g AS (SELECT md5(lower(trim(body))) AS h FROM listings
               GROUP BY h HAVING count(*) > 1)
    SELECT (seller_hash = '{top}') AS la_tai_khoan_lon, count(*) AS so_tin
    FROM listings WHERE md5(lower(trim(body))) IN (SELECT h FROM g) GROUP BY 1
""")
show("B3. Ví dụ 1 nhóm trùng tuyệt đối do nhiều người đăng", """
    WITH g AS (SELECT md5(lower(trim(body))) AS h FROM listings GROUP BY h
               HAVING count(DISTINCT seller_hash) > 1 LIMIT 1)
    SELECT list_id, seller_hash, price / 1e9 AS gia_ty, size,
           left(subject, 60) AS tieu_de,
           left(replace(body, chr(10), ' '), 100) AS mo_ta
    FROM listings WHERE md5(lower(trim(body))) IN (SELECT h FROM g)
""")

# ---------- C. Nhóm ứng viên trùng lớn nhất ----------
show("C. Nhóm ứng viên lớn nhất (cùng dự án + diện tích + giá + phòng ngủ)", """
    WITH g AS (SELECT pty_project_name p, size s, price pr, rooms r
               FROM listings WHERE pty_project_name IS NOT NULL
               GROUP BY ALL ORDER BY count(*) DESC LIMIT 1)
    SELECT l.list_id, l.seller_hash, l.floornumber AS tang, l.block AS toa,
           l.unitnumber AS ma_can, l.number_of_images AS so_anh,
           left(l.subject, 50) AS tieu_de,
           left(replace(l.body, chr(10), ' '), 120) AS mo_ta
    FROM listings l JOIN g ON l.pty_project_name = g.p AND l.size = g.s
         AND l.price = g.pr AND l.rooms = g.r
""")

show("q8", """
WITH top AS (SELECT seller_hash FROM listings GROUP BY 1 ORDER BY count(*) DESC LIMIT 1)
SELECT count(*) AS so_tin,
       count(DISTINCT (latitude, longitude)) AS so_diem,
       count(DISTINCT ward_name)             AS so_phuong
FROM listings WHERE seller_hash IN (SELECT seller_hash FROM top);
""")