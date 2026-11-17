"""
App gán nhãn cặp tin.  Chạy (từ thư mục gốc):
    streamlit run app\\label_app.py

Đọc  labels/candidates.csv  (từ make_pairs.py)
Ghi  labels/pairs.csv       (mỗi lần bấm nút ghi thêm 1 dòng; tắt app giữa chừng không mất)
"""
from datetime import datetime
from pathlib import Path

import duckdb
import pandas as pd
import streamlit as st

CAND = Path("labels/candidates.csv")
OUT = Path("labels/pairs.csv")
LABELS = {1: "Trùng", 0: "Không trùng", -1: "Không chắc"}

st.set_page_config(page_title="Gán nhãn tin trùng", layout="wide")


@st.cache_data
def load_listings() -> pd.DataFrame:
    df = duckdb.connect().sql("""
        WITH snap AS (SELECT * FROM read_parquet('data/snapshots/*/*.parquet',
                         hive_partitioning = true, union_by_name = true))
        SELECT * EXCLUDE (rn) FROM (
            SELECT *, row_number() OVER (PARTITION BY list_id ORDER BY crawl_date DESC) rn
            FROM snap) WHERE rn = 1
    """).df()
    return df.set_index("list_id")


def load_labels() -> pd.DataFrame:
    if OUT.exists():
        return pd.read_csv(OUT)
    return pd.DataFrame(columns=["pair_id", "id_a", "id_b", "label", "note", "labeled_at"])


def save_label(row, label: int, note: str):
    rec = pd.DataFrame([{"pair_id": row.pair_id, "id_a": row.id_a, "id_b": row.id_b,
                         "label": label, "note": note,
                         "labeled_at": datetime.now().isoformat(timespec="seconds")}])
    rec.to_csv(OUT, mode="a", header=not OUT.exists(), index=False)


def undo_last():
    lab = load_labels()
    if len(lab):
        lab.iloc[:-1].to_csv(OUT, index=False)


# ---------- hiển thị ----------
def fmt(v, kind=None):
    if v is None or (isinstance(v, float) and pd.isna(v)) or v is pd.NA:
        return "—"
    if kind == "price":
        return f"{v / 1e9:.2f} tỷ"
    if kind == "time":
        return pd.to_datetime(int(v), unit="ms").strftime("%Y-%m-%d")
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


FIELDS = [("Giá", "price", "price"), ("Diện tích (m²)", "size", None),
          ("Phòng ngủ", "rooms", None), ("WC", "toilets", None),
          ("Dự án", "pty_project_name", None), ("Tòa", "block", None),
          ("Tầng", "floornumber", None), ("Mã căn", "unitnumber", None),
          ("Quận", "area_name", None), ("Phường", "ward_name", None),
          ("Đường", "street_name", None), ("Người đăng", "seller_hash", None),
          ("Đăng lần đầu", "orig_list_time", "time"), ("Số ảnh", "number_of_images", None)]


def compare_table(a, b) -> pd.DataFrame:
    rows = []
    for name, col, kind in FIELDS:
        va, vb = fmt(a.get(col), kind), fmt(b.get(col), kind)
        same = "" if "—" in (va, vb) else ("✅" if va == vb else "❌")
        rows.append({"Trường": name, "Tin A": va, "Tin B": vb, "Giống?": same})
    return pd.DataFrame(rows)


def show_listing(col, title, lid, r):
    with col:
        st.subheader(f"{title} · {lid}")
        st.markdown(f"**{r.get('subject') or ''}**")
        imgs = r.get("images")
        imgs = list(imgs) if imgs is not None else []
        if imgs:
            st.image(imgs[:8], width=170)
        else:
            st.caption("(không có ảnh)")
        st.text_area("Mô tả", r.get("body") or "", height=260, disabled=True,
                     key=f"body_{title}_{lid}")


# ---------- main ----------
if not CAND.exists():
    st.error(f"Chưa có {CAND}. Chạy trước: python src\\label\\make_pairs.py")
    st.stop()

cand = pd.read_csv(CAND)
labels = load_labels()
listings = load_listings()
todo = cand[~cand.pair_id.isin(labels.pair_id)]

done = len(cand) - len(todo)
st.progress(done / len(cand), text=f"Đã gán {done}/{len(cand)} cặp")
if len(labels):
    st.caption(" · ".join(f"{LABELS[k]}: {v}" for k, v in
                          labels.label.value_counts().sort_index(ascending=False).items()))

if todo.empty:
    st.success("Xong toàn bộ! Kết quả ở labels/pairs.csv")
    st.stop()

row = todo.iloc[0]
if row.id_a not in listings.index or row.id_b not in listings.index:
    st.warning(f"Cặp {row.pair_id}: không tìm thấy tin trong dữ liệu -> đánh 'Không chắc'.")
    save_label(row, -1, "missing listing")
    st.rerun()

a, b = listings.loc[row.id_a], listings.loc[row.id_b]
st.markdown(f"### Cặp #{row.pair_id}")

# Nút bấm đặt trên cùng để không phải cuộn
note = st.text_input("Ghi chú (tùy chọn)", key=f"note_{row.pair_id}")
c1, c2, c3, c4 = st.columns(4)
if c1.button("✅ Trùng (cùng 1 căn)", width="stretch", type="primary"):
    save_label(row, 1, note); st.rerun()
if c2.button("❌ Không trùng", width="stretch"):
    save_label(row, 0, note); st.rerun()
if c3.button("❓ Không chắc", width="stretch"):
    save_label(row, -1, note); st.rerun()
if c4.button("↩ Hoàn tác cặp trước", width="stretch", disabled=labels.empty):
    undo_last(); st.rerun()

st.dataframe(compare_table(a, b), hide_index=True, width="stretch")

left, right = st.columns(2)
show_listing(left, "Tin A", row.id_a, a)
show_listing(right, "Tin B", row.id_b, b)
