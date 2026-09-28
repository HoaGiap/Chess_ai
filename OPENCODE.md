# Project Core Guidelines: Superpowers + Karpathy + Ponytail + CodeGraph

Dự án này tuân thủ nghiêm ngặt các nguyên tắc và công cụ cốt lõi:

---

## 1. Plugin Superpowers (Quy trình & Kỷ luật phát triển)
- **Invoke Skills First**: Luôn kiểm tra và kích hoạt skill phù hợp trước khi đưa ra phản hồi hoặc thực thi hành động (`using-superpowers`).
- **Brainstorming trước khi làm**: Luôn làm rõ mục tiêu, yêu cầu, giải pháp thay thế và ranh giới thiết kế (`brainstorming`) trước khi bước vào giai đoạn thực thi.
- **Lập kế hoạch rõ ràng**: Tạo plan chi tiết với các bước độc lập, tiêu chí đo lường rõ ràng (`writing-plans`).
- **Phát triển hướng kiểm thử & kiểm chứng**: TDD (`test-driven-development`), debug có hệ thống (`systematic-debugging`), và luôn xác minh kết quả bằng bằng chứng cụ thể trước khi kết luận hoàn thành (`verification-before-completion`).
- **Role Delegation**: Khi gặp bài toán chuyên môn sâu (bảo mật, kiến trúc, cơ sở dữ liệu, devops, review...), chủ động kích hoạt skill chuyên gia phù hợp từ bộ `agency-agents` theo nhu cầu thực tế.

---

## 2. Karpathy Guidelines (Tư duy & Tính phẫu thuật trong code)
- **Think Before Coding**: Nêu rõ các giả định, làm rõ sự mơ hồ, chỉ ra các đánh đổi (tradeoffs). Nếu có cách đơn giản hơn, luôn thẳng thắn đề xuất.
- **Simplicity First**: Đoạn code tối thiểu giải quyết triệt để vấn đề. Không suy đoán tương lai (không speculative abstraction), không tạo framework/interface cho code chỉ dùng 1 lần.
- **Surgical Changes**: Chỉ chạm vào những gì bắt buộc phải sửa. Không tái cấu trúc (refactor) lan man xung quanh, giữ nguyên phong cách code sẵn có, dọn dẹp sạch sẽ những biến/import thừa do chính mình tạo ra.
- **Goal-Driven Execution**: Mọi nhiệm vụ đều có tiêu chí hoàn thành kiểm chứng được: `[Bước] → verify: [lệnh/kiểm tra]`.

---

## 3. Ponytail (Tối giản & Đòn bẩy tối đa - Lazy Senior Dev)
- **The Ladder (Thang ưu tiên)**:
  1. *Có thực sự cần tồn tại không?* (YAGNI - bỏ qua nếu mang tính suy đoán).
  2. *Codebase đã có sẵn chưa?* Tái sử dụng helper/util/type sẵn có trong repo.
  3. *Thư viện chuẩn (stdlib) có sẵn không?* Dùng stdlib thay vì cài dependency mới.
  4. *Nền tảng / ngôn ngữ gốc (native) có sẵn không?* Ưu tiên native feature / platform API.
  5. *Dependency đã cài có giải quyết được không?* Tránh cài thêm thư viện thứ ba cho việc chỉ cần vài dòng code.
  6. *Có thể viết ngắn gọn, súc tích không?* Giải pháp ngắn nhất, bền vững nhất.
- **Root Cause**: Sửa tận gốc nguyên nhân, không vá ngọn (symptom patching).
- **Thực dụng & Rõ ràng**: Đánh dấu các quyết định đơn giản hóa có chủ đích bằng comment `// ponytail: ...` (hoặc `# ponytail: ...`).
- **Output súc tích**: Code trước, giải thích ngắn gọn, không viết văn hoa dài dòng thừa thãi.

---

## 4. Codebase Navigation (CodeGraph MCP)
- **Hiểu rõ luồng trước khi sửa**: Với codebase đã có sẵn hoặc dự án đa file, ưu tiên dùng `codegraph_explore` để khảo sát kiến trúc, symbol và call-path (truy vết các hàm gọi/liên quan) trong 1 lượt gọi trước khi can thiệp code.
- **YAGNI**: Không gọi CodeGraph cho repo rỗng hoặc dự án mới tinh chưa có code.
