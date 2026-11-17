"""
Mở giao diện web của DuckDB để xem và query dữ liệu như một bảng.

Chạy (từ thư mục gốc E:\\DM_2026.1):
    python src\\explore\\explore_ui.py
Trình duyệt sẽ mở http://localhost:4213
  - Cột trái: danh sách bảng (snap, listings) -> bấm vào để xem cột + thống kê nhanh
  - Ô notebook: gõ SQL, Ctrl+Enter để chạy
Nhấn Enter trong terminal để tắt.

Lần đầu chạy cần có Internet (DuckDB tải extension "ui").
"""
import duckdb

DB = "data/explore.duckdb"   # file database nhỏ, chỉ chứa định nghĩa VIEW, không chứa dữ liệu

con = duckdb.connect(DB)
con.execute("""
    -- snap: mọi lần crawl, mỗi dòng = 1 tin trong 1 ngày crawl
    CREATE OR REPLACE VIEW snap AS
    SELECT * FROM read_parquet('data/snapshots/*/*.parquet',
                               hive_partitioning = true, union_by_name = true);

    -- listings: mỗi list_id chỉ giữ bản crawl mới nhất
    CREATE OR REPLACE VIEW listings AS
    SELECT * EXCLUDE (rn) FROM (
        SELECT *, row_number() OVER (PARTITION BY list_id ORDER BY crawl_date DESC) AS rn
        FROM snap) WHERE rn = 1;
""")
print("Đã tạo view: snap, listings  ->", DB)

con.execute("CALL start_ui()")
input("UI đang chạy tại http://localhost:4213 — nhấn Enter để tắt...")