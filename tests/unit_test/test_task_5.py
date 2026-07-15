from app.services.assignment_service import pick_best_staff

# Giả lập danh sách ứng viên từ Database
mock_candidates = [
    # Người 1: Rảnh rỗi, có 2 giờ làm việc (ETC = 2.0)
    {"_id": "staff_1", "status": "Sẵn sàng", "workload_caps": {"current_daily_tasks": 1, "max_daily_tasks": 5, "current_daily_hours": 2.0, "max_daily_hours": 8.0}},
    
    # Người 2: Đang nghỉ phép, số giờ cực thấp (ETC = 0.0) -> Hệ thống phải tự loại
    {"_id": "staff_2", "status": "Nghỉ phép", "workload_caps": {"current_daily_tasks": 0, "max_daily_tasks": 5, "current_daily_hours": 0.0, "max_daily_hours": 8.0}},
    
    # Người 3: Sắp đầy tải, đã làm 7.5 tiếng -> Sẽ bị chặn nếu việc mới > 0.5 tiếng
    {"_id": "staff_3", "status": "Đang xử lý", "workload_caps": {"current_daily_tasks": 4, "max_daily_tasks": 5, "current_daily_hours": 7.5, "max_daily_hours": 8.0}},
    
    # Người 4: Người tối ưu nhất hiện tại (ETC = 1.0)
    {"_id": "staff_4", "status": "Sẵn sàng", "workload_caps": {"current_daily_tasks": 1, "max_daily_tasks": 5, "current_daily_hours": 1.0, "max_daily_hours": 8.0}},
]

def run_tests():
    print("🚀 Bắt đầu test Task 5...\n")

    # Kịch bản 1: Giao 1 việc tốn 1.0 giờ
    # Kỳ vọng: Chọn staff_4 vì ETC thấp nhất (1.0), bỏ qua staff_2 vì Nghỉ phép.
    result_1 = pick_best_staff(mock_candidates, 1.0)
    assert result_1["_id"] == "staff_4", f"❌ Lỗi KB1: Mong đợi staff_4, nhưng nhận được {result_1.get('_id') if result_1 else 'None'}"
    print("✅ Kịch bản 1 Pass: Thuật toán chọn đúng người tối ưu nhất và bỏ qua người Nghỉ phép.")

    # Kịch bản 2: Giao 1 việc tốn 7.0 giờ
    # Kỳ vọng: staff_3 và staff_4 đều vượt max_daily_hours. Chỉ còn staff_1 gánh được (2.0 + 7.0 <= 8.0 là SAI). 
    # Đợi đã, 2.0 + 7.0 = 9.0 -> Vượt! Vậy không ai gánh được! Trả về None.
    # Kịch bản 2: Giao 1 việc tốn 8.0 giờ (Tăng lên để ép quá tải)
    # Kỳ vọng: staff_3 và staff_4 đều vượt max_daily_hours. Không ai gánh được! Trả về None.
    result_2 = pick_best_staff(mock_candidates, 8.0)
    assert result_2 is None, f"❌ Lỗi KB2: Đáng lẽ phải trả về None vì không ai đủ slot giờ, nhưng lại trả về {result_2.get('_id') if result_2 else 'None'}"
    print("✅ Kịch bản 2 Pass: Thuật toán chặn chuẩn xác điều kiện thời gian kịch khung.")
    
    # Kịch bản 3: Giao 1 việc tốn 0.1 giờ cho 1 danh sách chỉ có staff_3
    # Mặc dù staff_3 đủ giờ (7.5 + 0.1 < 8), nhưng nếu truyền vào current_daily_tasks = 5 thì sao?
    mock_staff_3_full_tasks = [{"_id": "staff_3", "status": "Sẵn sàng", "workload_caps": {"current_daily_tasks": 5, "max_daily_tasks": 5, "current_daily_hours": 1.0, "max_daily_hours": 8.0}}]
    result_3 = pick_best_staff(mock_staff_3_full_tasks, 0.1)
    assert result_3 is None, "❌ Lỗi KB3: Đáng lẽ phải trả về None vì chạm trần số lượng việc (5 việc)!"
    print("✅ Kịch bản 3 Pass: Thuật toán chặn chuẩn xác điều kiện số lượng việc.")

    print("\n🎉 XUẤT SẮC! Thuật toán Greedy MVP của bạn chạy hoàn hảo!")

if __name__ == "__main__":
    run_tests()