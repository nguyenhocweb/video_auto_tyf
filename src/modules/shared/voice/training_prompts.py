"""
Bộ câu đọc mẫu tiếng Việt cân bằng âm vị (Phonetically Balanced Dataset)
Được thiết kế chuẩn để mô hình AI học trọn vẹn ngữ âm, thanh điệu và ngữ điệu tự nhiên.
"""

from typing import List, Dict, Any

VIETNAMESE_TRAINING_PROMPTS: List[Dict[str, Any]] = [
    # --- PHẦN 1: CHÀO HỎI & CÂU CƠ BẢN (5 câu) ---
    {
        "id": 1,
        "category": "Chào hỏi & Tự nhiên",
        "text": "Xin chào các bạn, hôm nay chúng ta sẽ cùng khám phá một trải nghiệm công nghệ hoàn toàn mới.",
        "phonetic_focus": "Âm mở đầu, nhịp điệu tự nhiên, thanh sắc và huyền",
        "target_duration_sec": 5.5,
    },
    {
        "id": 2,
        "category": "Chào hỏi & Tự nhiên",
        "text": "Cảm ơn bạn đã luôn đồng hành và theo dõi những nội dung sáng tạo trên kênh của mình.",
        "phonetic_focus": "Âm vần 'anh', 'ơi', thanh hỏi và ngã",
        "target_duration_sec": 5.0,
    },
    {
        "id": 3,
        "category": "Chào hỏi & Tự nhiên",
        "text": "Chúc các bạn có một ngày làm việc thật nhiều năng lượng và gặt hái được nhiều thành công rực rỡ.",
        "phonetic_focus": "Âm đệm 'oa', 'uê', thanh ngã 'rực rỡ'",
        "target_duration_sec": 6.0,
    },
    {
        "id": 4,
        "category": "Chào hỏi & Tự nhiên",
        "text": "Bạn có bao giờ tự hỏi điều gì tạo nên sự khác biệt giữa ước mơ và hiện thực chưa?",
        "phonetic_focus": "Câu hỏi nghi vấn, ngữ điệu lên giọng cuối câu",
        "target_duration_sec": 5.2,
    },
    {
        "id": 5,
        "category": "Chào hỏi & Tự nhiên",
        "text": "Đừng quên nhấn nút theo dõi và chia sẻ video này nếu bạn thấy nó thực sự hữu ích nhé.",
        "phonetic_focus": "Âm cuối 'nh', 'ch', thanh nặng 'lợi ích'",
        "target_duration_sec": 5.8,
    },

    # --- PHẦN 2: LUYỆN 6 THANH ĐIỆU & NGUYÊN ÂM ĐÔI (8 câu) ---
    {
        "id": 6,
        "category": "Thanh điệu & Âm vị",
        "text": "Mỗi sớm mai thức dậy, ánh nắng ban mai rọi sáng qua từng kẽ lá xanh mướt trước hiên nhà.",
        "phonetic_focus": "Nguyên âm 'ơ', 'ư', vần 'ương', 'ướt', thanh sắc dứt khoát",
        "target_duration_sec": 6.2,
    },
    {
        "id": 7,
        "category": "Thanh điệu & Âm vị",
        "text": "Những giọt sương long lanh đọng lại trên ngọn cỏ non như những viên ngọc bích quý giá.",
        "phonetic_focus": "Phụ âm đầu 's', 'l', 'ng', thanh nặng 'ngọc bích'",
        "target_duration_sec": 5.8,
    },
    {
        "id": 8,
        "category": "Thanh điệu & Âm vị",
        "text": "Biển xanh bao la rì rào sóng vỗ, cuốn trôi đi những muộn phiền của những ngày đã qua.",
        "phonetic_focus": "Thanh huyền và thanh hỏi, vần 'iên', 'uôn'",
        "target_duration_sec": 6.0,
    },
    {
        "id": 9,
        "category": "Thanh điệu & Âm vị",
        "text": "Học cách kiên trì nhẫn nại là chìa khóa mở ra cánh cửa dẫn tới tương lai tươi sáng.",
        "phonetic_focus": "Phụ âm 'nh', 'kh', 'tr', thanh ngã 'nhẫn nại'",
        "target_duration_sec": 5.6,
    },
    {
        "id": 10,
        "category": "Thanh điệu & Âm vị",
        "text": "Cơn gió thoảng qua mang theo hương thơm ngào ngạt của hoa quỳnh nở rộ giữa đêm hè.",
        "phonetic_focus": "Âm đệm 'o' ('thoảng', 'quỳnh'), thanh nặng 'ngào ngạt'",
        "target_duration_sec": 6.1,
    },
    {
        "id": 11,
        "category": "Thanh điệu & Âm vị",
        "text": "Dù con đường phía trước có gập ghềnh khúc khuỷu, lòng dũng cảm sẽ giúp ta vượt qua.",
        "phonetic_focus": "Vần phức tạp 'úc khuỷu', thanh hỏi 'khuỷu', thanh ngã 'dũng cảm'",
        "target_duration_sec": 6.3,
    },
    {
        "id": 12,
        "category": "Thanh điệu & Âm vị",
        "text": "Tiếng chim hót líu lo rộn rã đón chào một mùa xuân tràn đầy hy vọng mới.",
        "phonetic_focus": "Thanh sắc liên hoàn 'líu lo rộn rã', vần 'oan', 'uân'",
        "target_duration_sec": 5.4,
    },
    {
        "id": 13,
        "category": "Thanh điệu & Âm vị",
        "text": "Hãy trân trọng từng khoảnh khắc giản đơn bên cạnh những người thân yêu nhất của bạn.",
        "phonetic_focus": "Thanh hỏi 'khoảnh khắc', âm cuối 'n', 'nh'",
        "target_duration_sec": 5.5,
    },

    # --- PHẦN 3: REVIEW CÔNG NGHỆ & NHỊP ĐIỆU SÔI NỔI (6 câu) ---
    {
        "id": 14,
        "category": "Review Công Nghệ",
        "text": "Thiết kế của sản phẩm này thực sự ấn tượng với khung viền kim loại vát phẳng vô cùng tinh xảo.",
        "phonetic_focus": "Ngữ điệu hiện đại, dứt khoát, âm 'v', 'ph', 'x'",
        "target_duration_sec": 6.2,
    },
    {
        "id": 15,
        "category": "Review Công Nghệ",
        "text": "Hiệu năng xử lý đồ họa trên con chip thế hệ mới mang lại trải nghiệm chơi game cực kỳ mượt mà.",
        "phonetic_focus": "Tốc độ đọc nhanh vừa, rõ các phụ âm 'ch', 'tr', 'm'",
        "target_duration_sec": 6.0,
    },
    {
        "id": 16,
        "category": "Review Công Nghệ",
        "text": "Thời lượng pin có thể sử dụng thoải mái suốt cả ngày dài mà không cần lo lắng về việc sạc lại.",
        "phonetic_focus": "Nhịp điệu tự tin, liền mạch",
        "target_duration_sec": 5.8,
    },
    {
        "id": 17,
        "category": "Review Công Nghệ",
        "text": "Màn hình hiển thị sắc nét với độ phân giải cao cùng tần số quét một trăm hai mươi héc.",
        "phonetic_focus": "Đọc số liệu và từ mượn ('héc', 'quét', 'phân giải')",
        "target_duration_sec": 5.9,
    },
    {
        "id": 18,
        "category": "Review Công Nghệ",
        "text": "Đây chắc chắn là một trong những lựa chọn hàng đầu trong phân khúc giá hiện nay.",
        "phonetic_focus": "Khẳng định, nhấn âm 'chắc chắn', 'hàng đầu'",
        "target_duration_sec": 5.2,
    },
    {
        "id": 19,
        "category": "Review Công Nghệ",
        "text": "Tính năng tự động hóa bằng trí tuệ nhân tạo giúp tiết kiệm hơn tám mươi phần trăm thời gian.",
        "phonetic_focus": "Thuật ngữ 'trí tuệ nhân tạo', nhịp điệu logic",
        "target_duration_sec": 6.0,
    },

    # --- PHẦN 4: KỂ CHUYỆN & TÂM SỰ TRẦM ẤM (6 câu) ---
    {
        "id": 20,
        "category": "Kể Chuyện & Tâm Sự",
        "text": "Có những buổi chiều tĩnh lặng, ngồi nhìn mưa rơi ngoài khung cửa sổ và lắng nghe tiếng lòng mình.",
        "phonetic_focus": "Trầm ấm, sâu lắng, ngắt nghỉ nhẹ",
        "target_duration_sec": 6.5,
    },
    {
        "id": 21,
        "category": "Kể Chuyện & Tâm Sự",
        "text": "Kỷ niệm ngày xưa như những thước phim quay chậm, đưa ta trở về với miền ký ức tuổi thơ êm đềm.",
        "phonetic_focus": "Luyến láy nhẹ nhàng, thanh điệu uyển chuyển",
        "target_duration_sec": 6.8,
    },
    {
        "id": 22,
        "category": "Kể Chuyện & Tâm Sự",
        "text": "Thành công không phải là điểm đến cuối cùng, mà là lòng dũng cảm bước tiếp trên từng chặng đường.",
        "phonetic_focus": "Nhấn giọng triết lý, truyền cảm hứng",
        "target_duration_sec": 6.4,
    },
    {
        "id": 23,
        "category": "Kể Chuyện & Tâm Sự",
        "text": "Thời gian trôi đi không bao giờ trở lại, điều quý giá nhất là những khoảnh khắc ta sống trọn vẹn.",
        "phonetic_focus": "Hạ giọng cuối câu, giọng trầm",
        "target_duration_sec": 6.0,
    },
    {
        "id": 24,
        "category": "Kể Chuyện & Tâm Sự",
        "text": "Mỗi người chúng ta đều là một câu chuyện riêng biệt, đáng được trân trọng và lắng nghe.",
        "phonetic_focus": "Âm vang thanh nhẹ, biểu cảm chân thành",
        "target_duration_sec": 5.8,
    },
    {
        "id": 25,
        "category": "Kể Chuyện & Tâm Sự",
        "text": "Hãy mỉm cười đón nhận ngày mai, bởi vì những điều tuyệt vời nhất vẫn đang chờ đợi bạn ở phía trước.",
        "phonetic_focus": "Ấm áp, truyền năng lượng tích cực",
        "target_duration_sec": 6.2,
    },

    # --- PHẦN 5: THUYẾT MINH BẢN TIN TRANG TRỌNG (5 câu) ---
    {
        "id": 26,
        "category": "Bản Tin & Thuyết Minh",
        "text": "Kính chào quý vị khán giả đang theo dõi chương trình thời sự được phát sóng trực tiếp hôm nay.",
        "phonetic_focus": "Khẩu hình mở rộng, phong thái biên tập viên truyền hình",
        "target_duration_sec": 5.9,
    },
    {
        "id": 27,
        "category": "Bản Tin & Thuyết Minh",
        "text": "Thị trường tài chính ghi nhận những bước chuyển mình tích cực sau những chính sách điều hành linh hoạt.",
        "phonetic_focus": "Thuật ngữ kinh tế, phát âm dứt khoát",
        "target_duration_sec": 6.1,
    },
    {
        "id": 28,
        "category": "Bản Tin & Thuyết Minh",
        "text": "Dự báo thời tiết các khu vực trên cả nước sẽ duy trì trạng thái nắng ráo trong những ngày tới.",
        "phonetic_focus": "Nhịp đọc đều đặn, chuyên nghiệp",
        "target_duration_sec": 5.7,
    },
    {
        "id": 29,
        "category": "Bản Tin & Thuyết Minh",
        "text": "Các chuyên gia khuyến cáo người dân cần chủ động theo dõi các bản tin cảnh báo để có phương án phòng ngừa.",
        "phonetic_focus": "Trang trọng, nhấn từ khóa 'khuyến cáo', 'chủ động'",
        "target_duration_sec": 6.5,
    },
    {
        "id": 30,
        "category": "Bản Tin & Thuyết Minh",
        "text": "Cảm ơn sự quan tâm theo dõi của quý vị, xin kính chào tạm biệt và hẹn gặp lại trong các bản tin tiếp theo.",
        "phonetic_focus": "Lời kết trang trọng, xuống giọng chuẩn mực",
        "target_duration_sec": 6.0,
    },
]

def get_training_prompts() -> List[Dict[str, Any]]:
    """Trả về danh sách 30 câu đọc mẫu cân bằng âm vị."""
    return VIETNAMESE_TRAINING_PROMPTS

