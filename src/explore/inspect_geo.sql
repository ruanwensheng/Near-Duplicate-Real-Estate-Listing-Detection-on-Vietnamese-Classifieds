-- =====================================================================
-- EDA cho latitude / longitude
-- Chạy trong DuckDB UI (python src\explore\explore_ui.py), từng khối một.
-- 0.01 độ ≈ 1,1 km  | 0.001 độ ≈ 110 m  | 0.0001 độ ≈ 11 m
-- =====================================================================

-- Hàm tính khoảng cách (km) giữa 2 tọa độ (công thức haversine)
CREATE OR REPLACE MACRO dist_km(lat1, lon1, lat2, lon2) AS
    2 * 6371 * asin(sqrt(
        pow(sin(radians(lat2 - lat1) / 2), 2) +
        cos(radians(lat1)) * cos(radians(lat2)) * pow(sin(radians(lon2 - lon1) / 2), 2)));


-- Q1. Chất lượng cơ bản: thiếu? bằng 0? nằm ngoài thành phố?
--     Khung: Hà Nội lat 20.5–21.4, lon 105.3–106.1  | TP.HCM lat 10.3–11.2, lon 106.3–107.1
SELECT region_name,
       count(*)                                              AS so_tin,
       count(*) FILTER (latitude IS NULL OR latitude = 0)    AS thieu_hoac_0,
       count(*) FILTER (
           (region_v2 = 12000 AND NOT (latitude BETWEEN 20.5 AND 21.4 AND longitude BETWEEN 105.3 AND 106.1))
        OR (region_v2 = 13000 AND NOT (latitude BETWEEN 10.3 AND 11.2 AND longitude BETWEEN 106.3 AND 107.1))
       )                                                     AS ngoai_thanh_pho
FROM listings GROUP BY 1;


-- Q2. Tọa độ chính xác tới đâu? Số chữ số thập phân (5 chữ số ≈ 1 m, 2 chữ số ≈ 1 km)
SELECT length(split_part(latitude::VARCHAR, '.', 2)) AS so_chu_so_thap_phan,
       count(*) AS so_tin
FROM listings GROUP BY 1 ORDER BY 1;


-- Q3. Bao nhiêu tin dùng CHUNG một điểm tọa độ?
--     Nếu rất ít điểm khác nhau so với số tin -> tọa độ là của dự án / phường, không phải từng căn
SELECT count(*) AS so_tin,
       count(DISTINCT (latitude, longitude)) AS so_diem_khac_nhau,
       round(count(*) / count(DISTINCT (latitude, longitude)), 1) AS tin_moi_diem_tb
FROM listings;


-- Q4. Top 15 điểm có nhiều tin nhất: các tin ở đó có cùng dự án/phường không?
--     so_du_an = 1  -> điểm = vị trí dự án
--     so_du_an > 1 và cùng 1 phường -> điểm = tâm phường (mặc định)
SELECT latitude, longitude, count(*) AS so_tin,
       count(DISTINCT pty_project_name) AS so_du_an,
       count(DISTINCT ward_name)        AS so_phuong,
       any_value(pty_project_name)      AS vd_du_an,
       any_value(ward_name)             AS vd_phuong,
       count(DISTINCT seller_hash)      AS so_nguoi_dang
FROM listings GROUP BY 1, 2 ORDER BY so_tin DESC LIMIT 15;


-- Q5. Trong cùng 1 dự án, tọa độ có giống nhau không?
--     so_diem = 1 hoặc ban_kinh_m nhỏ -> tọa độ gắn theo dự án (dùng thay tên dự án được)
SELECT pty_project_name, count(*) AS so_tin,
       count(DISTINCT (latitude, longitude)) AS so_diem,
       round(1000 * max(dist_km(latitude, longitude, lat_tb, lon_tb)), 0) AS ban_kinh_m
FROM (SELECT *, avg(latitude)  OVER (PARTITION BY pty_project_name) AS lat_tb,
                avg(longitude) OVER (PARTITION BY pty_project_name) AS lon_tb
      FROM listings WHERE pty_project_name IS NOT NULL)
GROUP BY 1 HAVING count(*) >= 5
ORDER BY so_tin DESC LIMIT 20;


-- Q6. Tóm tắt Q5 cho TOÀN BỘ dự án: bao nhiêu % dự án có mọi tin nằm trong bán kính 200 m?
WITH p AS (
    SELECT pty_project_name,
           max(dist_km(latitude, longitude, lat_tb, lon_tb)) AS r_km
    FROM (SELECT *, avg(latitude)  OVER (PARTITION BY pty_project_name) AS lat_tb,
                    avg(longitude) OVER (PARTITION BY pty_project_name) AS lon_tb
          FROM listings WHERE pty_project_name IS NOT NULL)
    GROUP BY 1 HAVING count(*) >= 3)
SELECT count(*) AS so_du_an,
       round(100 * avg((r_km <= 0.2)::INT), 1) AS pct_trong_200m,
       round(100 * avg((r_km > 2)::INT), 1)    AS pct_lech_hon_2km
FROM p;


-- Q7. Tọa độ có khớp với quận được ghi không? (tin cách tâm quận > 5 km = nghi ghim sai)
WITH c AS (SELECT *, median(latitude)  OVER (PARTITION BY area_v2) AS lat_q,
                     median(longitude) OVER (PARTITION BY area_v2) AS lon_q
           FROM listings)
SELECT area_name, count(*) AS so_tin,
       count(*) FILTER (dist_km(latitude, longitude, lat_q, lon_q) > 5) AS lech_hon_5km
FROM c GROUP BY 1 ORDER BY lech_hon_5km DESC LIMIT 15;


-- Q8. Tài khoản sàn môi giới (không ghi tên dự án): tọa độ của họ có phân biệt được dự án không?
WITH top AS (SELECT seller_hash FROM listings GROUP BY 1 ORDER BY count(*) DESC LIMIT 1)
SELECT count(*) AS so_tin,
       count(DISTINCT (latitude, longitude)) AS so_diem,
       count(DISTINCT ward_name)             AS so_phuong
FROM listings WHERE seller_hash IN (SELECT seller_hash FROM top);


-- Q9. Quan hệ với giá: giá/m² theo khoảng cách tới trung tâm
--     (Hà Nội: Hồ Gươm 21.0285,105.8542  | TP.HCM: chợ Bến Thành 10.7725,106.6980)
WITH d AS (
    SELECT region_name, price_million_per_m2 AS gia_m2,
           CASE region_v2 WHEN 12000 THEN dist_km(latitude, longitude, 21.0285, 105.8542)
                          WHEN 13000 THEN dist_km(latitude, longitude, 10.7725, 106.6980) END AS km
    FROM listings
    WHERE price_million_per_m2 BETWEEN 10 AND 500)            -- bỏ giá vô lý
SELECT region_name, floor(km / 2) * 2 AS cach_tt_km, count(*) AS so_tin,
       round(median(gia_m2), 1) AS gia_m2_trung_vi
FROM d WHERE km IS NOT NULL
GROUP BY 1, 2 ORDER BY 1, 2;


-- Q10. Hệ số tương quan khoảng cách ↔ giá/m² (âm = càng xa càng rẻ)
WITH d AS (
    SELECT region_name, price_million_per_m2 AS gia_m2,
           CASE region_v2 WHEN 12000 THEN dist_km(latitude, longitude, 21.0285, 105.8542)
                          WHEN 13000 THEN dist_km(latitude, longitude, 10.7725, 106.6980) END AS km
    FROM listings WHERE price_million_per_m2 BETWEEN 10 AND 500)
SELECT region_name, round(corr(km, gia_m2), 3) AS tuong_quan, count(*) AS so_tin
FROM d GROUP BY 1;


-- Q11. QUAN TRỌNG CHO DEDUP: các cặp trùng tuyệt đối (cùng mô tả) có cùng tọa độ không?
--      Nếu hầu hết cặp trùng cách nhau < 100 m -> dùng tọa độ để blocking được
WITH t AS (SELECT list_id, latitude, longitude, md5(lower(trim(body))) AS h FROM listings),
     pairs AS (SELECT dist_km(a.latitude, a.longitude, b.latitude, b.longitude) * 1000 AS m
               FROM t a JOIN t b ON a.h = b.h AND a.list_id < b.list_id)
SELECT count(*) AS so_cap,
       count(*) FILTER (m = 0)    AS trung_toa_do,
       count(*) FILTER (m < 100)  AS duoi_100m,
       count(*) FILTER (m > 1000) AS tren_1km,
       round(median(m), 0)        AS trung_vi_m
FROM pairs;


-- Q12. Ô lưới ~1 km: mật độ tin và giá/m² (dùng để vẽ heatmap trên dashboard sau này)
SELECT region_name,
       round(latitude, 2) AS lat_o, round(longitude, 2) AS lon_o,
       count(*) AS so_tin, round(median(price_million_per_m2), 1) AS gia_m2
FROM listings GROUP BY ALL HAVING count(*) >= 10
ORDER BY so_tin DESC LIMIT 20;