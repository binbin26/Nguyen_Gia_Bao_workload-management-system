from datetime import datetime, timedelta, timezone
from jose import jwt

# Nhập cấu hình bảo mật của dự án
from app.core.config import settings

def create_test_token(user_id: str, role: str) -> str:
    """Tạo JWT token sống 30 ngày phục vụ quá trình test local"""
    expire = datetime.now(timezone.utc) + timedelta(days=30)
    
    # Payload chuẩn
    payload = {
        "sub": str(user_id),
        "role": role,
        "exp": expire
    }
    
    # SỬA LỖI TẠI ĐÂY: Dùng settings.JWT_SECRET_KEY
    # Lấy thuật toán mã hóa (mặc định là HS256 nếu Cursor không tạo biến ALGORITHM)
    algorithm = getattr(settings, "ALGORITHM", "HS256")
    
    token = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=algorithm)
    return token

if __name__ == "__main__":
    print("🚀 ĐANG TẠO TOKEN TEST...\n")
    
    # 1. Sinh token cho nhân viên kỹ thuật
    token_staff = create_test_token(user_id="staff_tech_01", role="staff")
    print("🔑 TOKEN CHO CÁN BỘ (staff_tech_01 - Role: staff):")
    print(token_staff)
    print("-" * 50)
    
    # 2. Sinh token cho cấp quản lý
    token_manager = create_test_token(user_id="manager_01", role="manager")
    print("🔑 TOKEN CHO QUẢN LÝ (manager_01 - Role: manager):")
    print(token_manager)
    print("\n✅ Đã tạo xong! Hãy copy các mã trên (bắt đầu bằng chữ 'ey...') để sử dụng trên Swagger UI.")