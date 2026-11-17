# Quy tắc gán nhãn cặp tin

Câu hỏi duy nhất: **Hai tin này có đang rao bán CÙNG MỘT CĂN HỘ không?**

## Trùng (label = 1)
- Cùng ảnh (hoặc ảnh cùng căn chụp góc khác: cùng nội thất, cùng view, cùng sàn/tường)
- Cùng tòa + tầng + mã căn
- Văn bản gần như giống hệt, kể cả khi giá đã đổi hoặc người đăng khác (copy tin)
- Người đăng giống nhau KHÔNG đủ để kết luận trùng: môi giới đăng nhiều căn khác nhau

## Không trùng (label = 0)
- Ảnh khác rõ ràng (nội thất khác, view khác, bố cục khác)
- Khác tòa, khác tầng hoặc khác mã căn
- Khác dự án
- Cùng dự án + cùng diện tích + cùng giá nhưng ảnh khác → vẫn là KHÔNG trùng (khác căn cùng layout)

## Không chắc (label = -1)
- Không có ảnh, hoặc ảnh không đủ để phân biệt (chỉ có ảnh phối cảnh dự án, ảnh sổ đỏ)
- Tin câu khách / tin chung chung không gắn với căn cụ thể ("liên hệ em để có giá tốt")
- Thiếu thông tin, bạn thật sự không quyết được

## Lưu ý
- Quyết định trong ~20–30 giây/cặp. Phân vân lâu → Không chắc.
- Không xem điểm giống văn bản khi gán (app đã ẩn) để tránh thiên lệch.
- Ghi chú các trường hợp đặc biệt vào ô "Ghi chú" (dùng làm ví dụ trong báo cáo).
- Các cặp "Không chắc" bị loại khi tính Precision/Recall; báo cáo tỷ lệ của chúng.

& C:\Users\Ruanw\anaconda3\shell\condabin\conda-hook.ps1

chạy: streamlit run app\label_app.py  

chạy riêng: Start-Process streamlit -ArgumentList "run app\label_app.py"