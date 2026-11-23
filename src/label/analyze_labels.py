from pathlib import Path

import pandas as pd

CAND = Path("labels/candidates.csv")
LAB = Path("labels/pairs.csv")
RELABEL_CAND = Path("labels/relabel_cand.csv")
RELABEL_OUT = Path("labels/pairs_relabel.csv")
NAMES = {1: "trung", 0: "khong_trung", -1: "khong_chac"}
SEED = 42

pd.set_option("display.width", 200)
pd.set_option("display.max_colwidth", 60)


def section(t):
    print(f"\n=== {t} ===")


def load_labels(path: Path) -> pd.DataFrame:
    lab = pd.read_csv(path)
    return lab.drop_duplicates("pair_id", keep="last")      # gán lại -> giữ lần cuối


cand = pd.read_csv(CAND)
raw = pd.read_csv(LAB)

# ---------- 1. Toàn vẹn dữ liệu ----------
section("1. Kiểm tra toàn vẹn")
lab = load_labels(LAB)
print(f"Số dòng trong pairs.csv: {len(raw)} | pair_id gán >1 lần: {len(raw) - len(lab)}")
print(f"Cặp trong candidates chưa có nhãn: {len(set(cand.pair_id) - set(lab.pair_id))}")
print(f"Cặp bị tự đánh 'missing listing': {(lab.note == 'missing listing').sum()}")

df = cand.merge(lab[["pair_id", "label", "note"]], on="pair_id")
df["nhan"] = df.label.map(NAMES)

# ---------- 2. Phân bố nhãn theo tầng ----------
section("2a. Số cặp theo tầng x nhãn")
print(pd.crosstab(df.stratum, df.nhan, margins=True))
section("2b. Tỷ lệ nhãn trong từng tầng")
print(pd.crosstab(df.stratum, df.nhan, normalize="index").round(3))

# ---------- 3. Jaccard theo nhãn ----------
section("3. Phân bố Jaccard theo nhãn")
print(df.groupby("nhan").jaccard.describe().round(3))

# ---------- 4. Ca khó: bằng chứng cho bảng 2x2 ----------
sure = df[df.label != -1]
hard_pos = sure[(sure.label == 1) & (sure.jaccard < 0.3)]   # ô ③: cùng căn, chữ khác
hard_neg = sure[(sure.label == 0) & (sure.jaccard >= 0.7)]  # ô ②: chữ giống, khác căn
section(f"4a. Trùng nhưng Jaccard < 0.3 (ô 3): {len(hard_pos)} cặp")
print(hard_pos[["pair_id", "id_a", "id_b", "jaccard", "note"]].head(10).to_string(index=False))
section(f"4b. Không trùng nhưng Jaccard >= 0.7 (ô 2): {len(hard_neg)} cặp")
print(hard_neg[["pair_id", "id_a", "id_b", "jaccard", "note"]].head(10).to_string(index=False))

# ---------- 5. Baseline: ngưỡng Jaccard ----------
section("5. Baseline Jaccard >= t (trên MẪU phân tầng, chưa trọng số -> chỉ để tham khảo)")
for t in [0.3, 0.5, 0.7, 0.9]:
    pred, y = sure.jaccard >= t, sure.label == 1
    tp, fp, fn = (pred & y).sum(), (pred & ~y).sum(), (~pred & y).sum()
    p = tp / (tp + fp) if tp + fp else float("nan")
    r = tp / (tp + fn) if tp + fn else float("nan")
    f = 2 * p * r / (p + r) if p + r else float("nan")
    print(f"t={t:.1f}  P={p:.3f}  R={r:.3f}  F1={f:.3f}  (TP={tp} FP={fp} FN={fn})")

# ---------- 6. Ghi chú đã viết ----------
notes = df[df.note.notna() & (df.note != "missing listing")]
section(f"6. Các cặp có ghi chú: {len(notes)}")
print(notes[["pair_id", "nhan", "jaccard", "note"]].to_string(index=False))

# ---------- 7. Độ nhất quán khi gán lại ----------
section("7. Gán lại để đo độ nhất quán")
if not RELABEL_CAND.exists():
    pool = df[df.note != "missing listing"]
    # pandas 3: groupby().apply() bỏ cột nhóm khỏi kết quả -> lấy mẫu từng nhóm rồi nối lại
    sample = pd.concat(g.sample(min(len(g), 15), random_state=SEED)
                       for _, g in pool.groupby("stratum"))
    sample = sample.sample(frac=1, random_state=SEED)       # xáo trộn
    sample[["pair_id", "id_a", "id_b", "jaccard", "stratum"]].to_csv(RELABEL_CAND, index=False)
    print(f"Đã tạo {RELABEL_CAND} ({len(sample)} cặp). Gán lại SAU ~1 tuần.")
elif not RELABEL_OUT.exists():
    print(f"Đã có {RELABEL_CAND}, chưa có {RELABEL_OUT} -> chưa gán lại.")
else:
    re = load_labels(RELABEL_OUT)[["pair_id", "label"]].rename(columns={"label": "label2"})
    m = df[["pair_id", "label"]].merge(re, on="pair_id")
    po = (m.label == m.label2).mean()
    pe = sum(m.label.value_counts(normalize=True).get(k, 0) *
             m.label2.value_counts(normalize=True).get(k, 0) for k in NAMES)
    kappa = (po - pe) / (1 - pe) if pe < 1 else float("nan")
    print(f"{len(m)} cặp | đồng ý {po:.3f} | Cohen's kappa = {kappa:.3f}")
    print(pd.crosstab(m.label.map(NAMES), m.label2.map(NAMES),
                      rownames=["lần 1"], colnames=["lần 2"]))