"""
seed_workforce_db.py
=====================
Script khoi tao MongoDB database cho he thong AI-powered Workforce Management.

Collections:
  1. task_categories  - Danh muc & quy trinh chuan (workflow template)
  2. staffs           - Han muc & tai luong nhan su theo ngay
  3. tasks            - Ho so thuc te (state machine dong)
  4. overload_logs    - Nhat ky dieu phoi qua tai

Cach dung:
  pip install pymongo
  export MONGO_URI="mongodb://localhost:27017"   # (tuy chon, mac dinh localhost)
  python seed_workforce_db.py

Mac dinh script se DROP va tao lai toan bo collection (idempotent).
Neu chi muon tao moi (khong xoa du lieu cu), doi RESET_DB = False ben duoi.
"""

import os
from datetime import datetime, timezone

import bcrypt
from pymongo import MongoClient, ASCENDING
from pymongo.errors import CollectionInvalid

# --------------------------------------------------------------------------
# CAU HINH KET NOI
# --------------------------------------------------------------------------
MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017")
DB_NAME = os.environ.get("MONGO_DB_NAME", "vnpt_ai_performance")
RESET_DB = True  # True: xoa & tao lai collection moi lan chay script

# Ghi chu: A / B / C la ma phong ban vi du (Phap che / Cong tac hoc vu - ky
# luat / Dao tao). Doi ten cho khop voi 3 team thuc te cua ban neu can,
# logic script khong phu thuoc vao ten cu the.


def dt(iso_str):
    """Chuyen chuoi ISO 8601 (vd '2026-07-07T09:00:00Z') sang datetime UTC."""
    if iso_str is None:
        return None
    return datetime.fromisoformat(iso_str.replace("Z", "+00:00"))


def hash_password(plain_password):
    """Hash mat khau bang bcrypt truoc khi seed vao MongoDB."""
    return bcrypt.hashpw(plain_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


# ==========================================================================
# 1. JSON SCHEMA VALIDATORS
# ==========================================================================

TASK_CATEGORIES_VALIDATOR = {
    "$jsonSchema": {
        "bsonType": "object",
        "title": "task_categories validator",
        "required": ["_id", "task_code", "title", "department",
                     "standard_metrics", "workflow_steps"],
        "properties": {
            "_id": {"bsonType": "string"},
            "task_code": {"bsonType": "string", "description": "Ma quy trinh, vd B4"},
            "title": {"bsonType": "string"},
            "department": {"bsonType": "string", "enum": ["A", "B", "C"]},
            "standard_metrics": {
                "bsonType": "object",
                "required": ["total_steps", "total_duration_hours", "complexity",
                             "urgency", "coordination", "workload_score"],
                "properties": {
                    "total_steps": {"bsonType": "int", "minimum": 1},
                    "total_duration_hours": {"bsonType": "double", "minimum": 0},
                    "complexity": {"bsonType": "int", "minimum": 1, "maximum": 5},
                    "urgency": {"bsonType": "int", "minimum": 1, "maximum": 5},
                    "coordination": {"bsonType": "int", "minimum": 1, "maximum": 5},
                    "workload_score": {"bsonType": "double", "minimum": 0},
                },
            },
            "workflow_steps": {
                "bsonType": "array",
                "minItems": 1,
                "items": {
                    "bsonType": "object",
                    "required": ["step_number", "department", "duration_hours", "desc"],
                    "properties": {
                        "step_number": {"bsonType": "int", "minimum": 1},
                        "department": {"bsonType": "string", "enum": ["A", "B", "C"]},
                        "duration_hours": {"bsonType": "double", "minimum": 0},
                        "desc": {"bsonType": "string"},
                    },
                },
            },
        },
    }
}

STAFFS_VALIDATOR = {
    "$jsonSchema": {
        "bsonType": "object",
        "title": "staffs validator",
        "required": ["_id", "fullname", "department", "workload_caps", "status"],
        "properties": {
            "_id": {"bsonType": "string"},
            "fullname": {"bsonType": "string"},
            "department": {"bsonType": "string", "enum": ["A", "B", "C"]},
            "workload_caps": {
                "bsonType": "object",
                "required": ["max_daily_tasks", "max_daily_hours",
                             "current_daily_tasks", "current_daily_hours"],
                "properties": {
                    "max_daily_tasks": {"bsonType": "int", "minimum": 1},
                    "max_daily_hours": {"bsonType": "double", "minimum": 0},
                    "current_daily_tasks": {"bsonType": "int", "minimum": 0},
                    "current_daily_hours": {"bsonType": "double", "minimum": 0},
                },
            },
            "status": {
                "bsonType": "string",
                "enum": ["Sẵn sàng", "Bận", "Quá tải", "Nghỉ phép"],
            },
        },
    }
}

TASKS_VALIDATOR = {
    "$jsonSchema": {
        "bsonType": "object",
        "title": "tasks validator",
        "required": ["_id", "task_code", "status", "current_step",
                     "current_department", "current_assigned_to",
                     "metrics", "workflow_history",
                     "control_flags", "timestamps"],
        "properties": {
            "_id": {"bsonType": "string"},
            "task_code": {"bsonType": "string"},
            "status": {
                "bsonType": "string",
                "enum": ["Chờ xử lý", "Đang xử lý", "Hoàn thành", "Tạm dừng", "Hủy"],
            },
            "current_step": {"bsonType": "int", "minimum": 1},
            "current_department": {"bsonType": "string", "enum": ["A", "B", "C"]},
            "current_assigned_to": {"bsonType": "string"},
            "metrics": {
                "bsonType": "object",
                "required": ["workload_score", "step_duration_hours",
                             "actual_duration_hours", "early_completion_hours"],
                "properties": {
                    "workload_score": {"bsonType": "double"},
                    "step_duration_hours": {"bsonType": "double"},
                    "actual_duration_hours": {"bsonType": ["double", "null"]},
                    "early_completion_hours": {"bsonType": ["double", "null"]},
                },
            },
            "workflow_history": {
                "bsonType": "array",
                "minItems": 1,
                "items": {
                    "bsonType": "object",
                    "required": ["step_number", "department", "assigned_to",
                                 "status", "completed_at"],
                    "properties": {
                        "step_number": {"bsonType": "int", "minimum": 1},
                        "department": {"bsonType": "string", "enum": ["A", "B", "C"]},
                        "assigned_to": {"bsonType": "string"},
                        "status": {
                            "bsonType": "string",
                            "enum": ["Chờ xử lý", "Đang xử lý", "Hoàn thành", "Tạm dừng", "Hủy"],
                        },
                        "completed_at": {"bsonType": ["date", "null"]},
                    },
                },
            },
            "control_flags": {
                "bsonType": "object",
                "required": ["is_locked", "transfer_count"],
                "properties": {
                    "is_locked": {"bsonType": "bool"},
                    "transfer_count": {"bsonType": "int", "minimum": 0},
                },
            },
            "timestamps": {
                "bsonType": "object",
                "required": ["created_at", "due_at"],
                "properties": {
                    "created_at": {"bsonType": "date"},
                    "due_at": {"bsonType": "date"},
                    "completed_at": {"bsonType": ["date", "null"]},
                },
            },
        },
    }
}

OVERLOAD_LOGS_VALIDATOR = {
    "$jsonSchema": {
        "bsonType": "object",
        "title": "overload_logs validator",
        "required": ["_id", "timestamp", "staff_id", "trigger_reason", "manager_action"],
        "properties": {
            "_id": {"bsonType": "string"},
            "timestamp": {"bsonType": "date"},
            "staff_id": {"bsonType": "string"},
            "trigger_reason": {"bsonType": "string"},
            "manager_action": {
                "bsonType": "object",
                "required": ["action_taken", "resolved_by", "details"],
                "properties": {
                    "action_taken": {
                        "bsonType": "string",
                        "enum": [
                            "Pending",
                            "Approved_Suggestion",
                            "Rejected_Suggestion",
                            "Manual_Override",
                        ],
                    },
                    "resolved_by": {"bsonType": "string"},
                    "details": {"bsonType": "object"},
                },
            },
        },
    }
}

USERS_VALIDATOR = {
    "$jsonSchema": {
        "bsonType": "object",
        "title": "users validator",
        "required": ["_id", "password_hash", "role", "staff_id"],
        "properties": {
            "_id": {
                "bsonType": "string",
                "description": "Username dang nhap, vd manager_01 hoac staff_a2",
            },
            "password_hash": {
                "bsonType": "string",
                "description": "Mat khau da bam bang bcrypt",
            },
            "role": {"bsonType": "string", "enum": ["manager", "staff"]},
            "staff_id": {
                "bsonType": ["string", "null"],
                "description": "Tro toi staffs._id neu role=staff; null neu role=manager",
            },
        },
    }
}


def create_collection_with_validator(db, name, validator):
    """Xoa (neu RESET_DB) va tao lai collection voi schema validator."""
    if RESET_DB and name in db.list_collection_names():
        db.drop_collection(name)
        print(f"  - Da xoa collection cu: {name}")
    try:
        db.create_collection(
            name,
            validator=validator,
            validationLevel="moderate",
            validationAction="error",
        )
        print(f"  - Da tao collection: {name} (voi validator)")
    except CollectionInvalid:
        # Da ton tai (truong hop RESET_DB=False) -> ap validator qua collMod
        db.command({
            "collMod": name,
            "validator": validator,
            "validationLevel": "moderate",
            "validationAction": "error",
        })
        print(f"  - Collection {name} da ton tai, da cap nhat validator")


# ==========================================================================
# 2. DU LIEU MAU: task_categories (12 muc, tu don gian -> phuc tap)
#    workload_score = complexity*0.3 + urgency*0.3 + coordination*0.4
# ==========================================================================

TASK_CATEGORIES = [
    # ---------- DON GIAN (4 muc: 1 phong ban, 1-2 buoc) ----------
    {
        "_id": "cat_a1", "task_code": "A1", "title": "Xin nghỉ phép",
        "department": "A",
        "standard_metrics": {
            "total_steps": 1, "total_duration_hours": 0.25,
            "complexity": 1, "urgency": 1, "coordination": 1, "workload_score": 1.0,
        },
        "workflow_steps": [
            {"step_number": 1, "department": "A", "duration_hours": 0.25,
             "desc": "Nộp đơn xin nghỉ phép"},
        ],
    },
    {
        "_id": "cat_b1", "task_code": "B1", "title": "Xác nhận thông tin sinh viên",
        "department": "B",
        "standard_metrics": {
            "total_steps": 1, "total_duration_hours": 0.25,
            "complexity": 1, "urgency": 1, "coordination": 1, "workload_score": 1.0,
        },
        "workflow_steps": [
            {"step_number": 1, "department": "B", "duration_hours": 0.25,
             "desc": "Tiếp nhận và xác nhận thông tin"},
        ],
    },
    {
        "_id": "cat_c1", "task_code": "C1", "title": "Đăng ký học phần bổ sung",
        "department": "C",
        "standard_metrics": {
            "total_steps": 2, "total_duration_hours": 0.5,
            "complexity": 1, "urgency": 2, "coordination": 1, "workload_score": 1.3,
        },
        "workflow_steps": [
            {"step_number": 1, "department": "C", "duration_hours": 0.25,
             "desc": "Kiểm tra điều kiện đăng ký"},
            {"step_number": 2, "department": "C", "duration_hours": 0.25,
             "desc": "Xác nhận đăng ký học phần"},
        ],
    },
    {
        "_id": "cat_a2", "task_code": "A2", "title": "Cấp giấy giới thiệu",
        "department": "A",
        "standard_metrics": {
            "total_steps": 2, "total_duration_hours": 0.5,
            "complexity": 2, "urgency": 1, "coordination": 1, "workload_score": 1.3,
        },
        "workflow_steps": [
            {"step_number": 1, "department": "A", "duration_hours": 0.25,
             "desc": "Soạn thảo giấy giới thiệu"},
            {"step_number": 2, "department": "A", "duration_hours": 0.25,
             "desc": "Ký duyệt và cấp giấy"},
        ],
    },
    # ---------- TRUNG BINH (4 muc: 2-3 buoc, co the phoi hop nhe) ----------
    {
        "_id": "cat_b2", "task_code": "B2", "title": "Xử lý đơn khiếu nại nhẹ",
        "department": "B",
        "standard_metrics": {
            "total_steps": 2, "total_duration_hours": 1.0,
            "complexity": 2, "urgency": 2, "coordination": 2, "workload_score": 2.0,
        },
        "workflow_steps": [
            {"step_number": 1, "department": "B", "duration_hours": 0.5,
             "desc": "Tiếp nhận đơn khiếu nại"},
            {"step_number": 2, "department": "B", "duration_hours": 0.5,
             "desc": "Phản hồi và xử lý"},
        ],
    },
    {
        "_id": "cat_c2", "task_code": "C2", "title": "Điều chỉnh lịch học",
        "department": "C",
        "standard_metrics": {
            "total_steps": 3, "total_duration_hours": 0.75,
            "complexity": 2, "urgency": 2, "coordination": 2, "workload_score": 2.0,
        },
        "workflow_steps": [
            {"step_number": 1, "department": "C", "duration_hours": 0.25,
             "desc": "Tiếp nhận yêu cầu điều chỉnh"},
            {"step_number": 2, "department": "C", "duration_hours": 0.25,
             "desc": "Kiểm tra lịch trống"},
            {"step_number": 3, "department": "C", "duration_hours": 0.25,
             "desc": "Cập nhật lịch học"},
        ],
    },
    {
        "_id": "cat_a3", "task_code": "A3", "title": "Thẩm định hồ sơ pháp lý",
        "department": "A",
        "standard_metrics": {
            "total_steps": 2, "total_duration_hours": 1.0,
            "complexity": 2, "urgency": 3, "coordination": 2, "workload_score": 2.3,
        },
        "workflow_steps": [
            {"step_number": 1, "department": "A", "duration_hours": 0.5,
             "desc": "Rà soát hồ sơ pháp lý"},
            {"step_number": 2, "department": "A", "duration_hours": 0.5,
             "desc": "Kết luận thẩm định"},
        ],
    },
    {
        "_id": "cat_b3", "task_code": "B3", "title": "Giải quyết tranh chấp nội bộ",
        "department": "B",
        "standard_metrics": {
            "total_steps": 3, "total_duration_hours": 1.5,
            "complexity": 3, "urgency": 2, "coordination": 2, "workload_score": 2.3,
        },
        "workflow_steps": [
            {"step_number": 1, "department": "B", "duration_hours": 0.5,
             "desc": "Ghi nhận tranh chấp"},
            {"step_number": 2, "department": "C", "duration_hours": 0.5,
             "desc": "Tham vấn học vụ liên quan"},
            {"step_number": 3, "department": "B", "duration_hours": 0.5,
             "desc": "Ra quyết định hòa giải"},
        ],
    },
    # ---------- PHUC TAP (4 muc: 4-5 buoc, PHOI HOP >= 2 PHONG BAN) ----------
    {
        "_id": "cat_b4", "task_code": "B4", "title": "Xử lý vi phạm kỷ luật khẩn cấp",
        "department": "B",
        "standard_metrics": {
            "total_steps": 4, "total_duration_hours": 2.0,
            "complexity": 3, "urgency": 5, "coordination": 3, "workload_score": 3.6,
        },
        "workflow_steps": [
            {"step_number": 1, "department": "B", "duration_hours": 0.5, "desc": "Lập biên bản"},
            {"step_number": 2, "department": "A", "duration_hours": 0.75, "desc": "Pháp chế rà soát"},
            {"step_number": 3, "department": "B", "duration_hours": 0.5, "desc": "Hội đồng phỏng vấn"},
            {"step_number": 4, "department": "B", "duration_hours": 0.25, "desc": "Ra quyết định"},
        ],
    },
    {
        "_id": "cat_a4", "task_code": "A4", "title": "Xử lý khiếu nại pháp lý phức tạp",
        "department": "A",
        "standard_metrics": {
            "total_steps": 4, "total_duration_hours": 2.0,
            "complexity": 3, "urgency": 4, "coordination": 3, "workload_score": 3.3,
        },
        "workflow_steps": [
            {"step_number": 1, "department": "A", "duration_hours": 0.5,
             "desc": "Tiếp nhận đơn khiếu nại pháp lý"},
            {"step_number": 2, "department": "B", "duration_hours": 0.5,
             "desc": "Xác minh thực tế tại đơn vị"},
            {"step_number": 3, "department": "C", "duration_hours": 0.5,
             "desc": "Đối chiếu quy chế đào tạo"},
            {"step_number": 4, "department": "A", "duration_hours": 0.5,
             "desc": "Ra kết luận pháp lý"},
        ],
    },
    {
        "_id": "cat_c4", "task_code": "C4", "title": "Xử lý vi phạm học vụ nghiêm trọng",
        "department": "C",
        "standard_metrics": {
            "total_steps": 5, "total_duration_hours": 2.25,
            "complexity": 4, "urgency": 4, "coordination": 3, "workload_score": 3.6,
        },
        "workflow_steps": [
            {"step_number": 1, "department": "C", "duration_hours": 0.5,
             "desc": "Ghi nhận vi phạm học vụ"},
            {"step_number": 2, "department": "B", "duration_hours": 0.5,
             "desc": "Xác minh nhân thân sinh viên"},
            {"step_number": 3, "department": "A", "duration_hours": 0.5,
             "desc": "Rà soát quy định pháp lý"},
            {"step_number": 4, "department": "C", "duration_hours": 0.5,
             "desc": "Hội đồng kỷ luật họp xét"},
            {"step_number": 5, "department": "C", "duration_hours": 0.25,
             "desc": "Ra quyết định xử lý"},
        ],
    },
    {
        "_id": "cat_b5", "task_code": "B5", "title": "Xử lý khủng hoảng truyền thông sinh viên",
        "department": "B",
        "standard_metrics": {
            "total_steps": 5, "total_duration_hours": 3.0,
            "complexity": 4, "urgency": 5, "coordination": 4, "workload_score": 4.3,
        },
        "workflow_steps": [
            {"step_number": 1, "department": "B", "duration_hours": 0.5,
             "desc": "Tiếp nhận thông tin khủng hoảng"},
            {"step_number": 2, "department": "A", "duration_hours": 0.5,
             "desc": "Đánh giá rủi ro pháp lý"},
            {"step_number": 3, "department": "C", "duration_hours": 0.5,
             "desc": "Rà soát ảnh hưởng học vụ"},
            {"step_number": 4, "department": "B", "duration_hours": 0.75,
             "desc": "Họp ban xử lý khủng hoảng"},
            {"step_number": 5, "department": "A", "duration_hours": 0.75,
             "desc": "Phê duyệt phương án phản hồi"},
        ],
    },
]

# ==========================================================================
# 3. DU LIEU MAU: staffs (12 nguoi, chia deu 4 nguoi / 3 phong ban)
# ==========================================================================

STAFFS = [
    # --- Phong ban A ---
    {"_id": "staff_a1", "fullname": "Lê Văn An", "department": "A",
     "workload_caps": {"max_daily_tasks": 5, "max_daily_hours": 8.0,
                        "current_daily_tasks": 2, "current_daily_hours": 3.0},
     "status": "Sẵn sàng"},
    {"_id": "staff_a2", "fullname": "Phạm Thị Ánh", "department": "A",
     "workload_caps": {"max_daily_tasks": 5, "max_daily_hours": 8.0,
                        "current_daily_tasks": 4, "current_daily_hours": 7.0},
     "status": "Bận"},
    {"_id": "staff_a3", "fullname": "Nguyễn Văn Bình", "department": "A",
     "workload_caps": {"max_daily_tasks": 5, "max_daily_hours": 8.0,
                        "current_daily_tasks": 1, "current_daily_hours": 1.5},
     "status": "Sẵn sàng"},
    {"_id": "staff_a4", "fullname": "Hoàng Thị Cúc", "department": "A",
     "workload_caps": {"max_daily_tasks": 5, "max_daily_hours": 8.0,
                        "current_daily_tasks": 5, "current_daily_hours": 8.0},
     "status": "Quá tải"},
    # --- Phong ban B ---
    {"_id": "staff_b1", "fullname": "Đỗ Văn Bảo", "department": "B",
     "workload_caps": {"max_daily_tasks": 5, "max_daily_hours": 8.0,
                        "current_daily_tasks": 2, "current_daily_hours": 3.5},
     "status": "Sẵn sàng"},
    {"_id": "staff_b2", "fullname": "Nguyễn Thị B", "department": "B",
     "workload_caps": {"max_daily_tasks": 5, "max_daily_hours": 8.0,
                        "current_daily_tasks": 3, "current_daily_hours": 5.5},
     "status": "Sẵn sàng"},
    {"_id": "staff_b3", "fullname": "Trần Thị Dung", "department": "B",
     "workload_caps": {"max_daily_tasks": 5, "max_daily_hours": 8.0,
                        "current_daily_tasks": 4, "current_daily_hours": 6.5},
     "status": "Bận"},
    {"_id": "staff_b4", "fullname": "Vũ Văn Đức", "department": "B",
     "workload_caps": {"max_daily_tasks": 5, "max_daily_hours": 8.0,
                        "current_daily_tasks": 1, "current_daily_hours": 2.0},
     "status": "Sẵn sàng"},
    # --- Phong ban C ---
    {"_id": "staff_c1", "fullname": "Ngô Thị Hoa", "department": "C",
     "workload_caps": {"max_daily_tasks": 5, "max_daily_hours": 8.0,
                        "current_daily_tasks": 3, "current_daily_hours": 4.5},
     "status": "Sẵn sàng"},
    {"_id": "staff_c2", "fullname": "Bùi Văn Hùng", "department": "C",
     "workload_caps": {"max_daily_tasks": 5, "max_daily_hours": 8.0,
                        "current_daily_tasks": 2, "current_daily_hours": 3.0},
     "status": "Sẵn sàng"},
    {"_id": "staff_c3", "fullname": "Lý Thị Lan", "department": "C",
     "workload_caps": {"max_daily_tasks": 5, "max_daily_hours": 8.0,
                        "current_daily_tasks": 5, "current_daily_hours": 7.5},
     "status": "Bận"},
    {"_id": "staff_c4", "fullname": "Phan Văn Minh", "department": "C",
     "workload_caps": {"max_daily_tasks": 5, "max_daily_hours": 8.0,
                        "current_daily_tasks": 0, "current_daily_hours": 0.0},
     "status": "Sẵn sàng"},
]


def build_seed_users(default_password="password123"):
    password_hash = hash_password(default_password)
    users = [
        {
            "_id": "manager_01",
            "password_hash": password_hash,
            "role": "manager",
            "staff_id": None,
        }
    ]
    users.extend(
        {
            "_id": staff["_id"],
            "password_hash": hash_password(default_password),
            "role": "staff",
            "staff_id": staff["_id"],
        }
        for staff in STAFFS
    )
    return users

# ==========================================================================
# 4. DU LIEU MAU: tasks (minh hoa state machine o nhieu trang thai khac nhau)
# ==========================================================================

TASKS = [
    {
        "_id": "task_20260707_0001", "task_code": "B4", "status": "Đang xử lý",
        "current_step": 2, "current_department": "A", "current_assigned_to": "staff_a2",
        "metrics": {"workload_score": 3.6, "step_duration_hours": 0.75,
                    "actual_duration_hours": None, "early_completion_hours": None},
        "workflow_history": [
            {"step_number": 1, "department": "B", "assigned_to": "staff_b2",
             "status": "Hoàn thành", "completed_at": dt("2026-07-07T09:00:00Z")},
            {"step_number": 2, "department": "A", "assigned_to": "staff_a2",
             "status": "Đang xử lý", "completed_at": None},
        ],
        "control_flags": {"is_locked": False, "transfer_count": 1},
        "timestamps": {
            "created_at": dt("2026-07-07T08:30:00Z"),
            "due_at": dt("2026-07-07T10:30:00Z"),
            "completed_at": None,
        },
    },
    {
        "_id": "task_20260707_0002", "task_code": "A1", "status": "Hoàn thành",
        "current_step": 1, "current_department": "A", "current_assigned_to": "staff_a1",
        "metrics": {"workload_score": 1.0, "step_duration_hours": 0.25,
                    "actual_duration_hours": 0.2, "early_completion_hours": 0.05},
        "workflow_history": [
            {"step_number": 1, "department": "A", "assigned_to": "staff_a1",
             "status": "Hoàn thành", "completed_at": dt("2026-07-07T08:15:00Z")},
        ],
        "control_flags": {"is_locked": True, "transfer_count": 0},
        "timestamps": {
            "created_at": dt("2026-07-07T08:00:00Z"),
            "due_at": dt("2026-07-07T08:15:00Z"),
            "completed_at": dt("2026-07-07T08:15:00Z"),
        },
    },
    {
        "_id": "task_20260707_0003", "task_code": "C4", "status": "Chờ xử lý",
        "current_step": 1, "current_department": "C", "current_assigned_to": "staff_c1",
        "metrics": {"workload_score": 3.6, "step_duration_hours": 0.5,
                    "actual_duration_hours": None, "early_completion_hours": None},
        "workflow_history": [
            {"step_number": 1, "department": "C", "assigned_to": "staff_c1",
             "status": "Chờ xử lý", "completed_at": None},
        ],
        "control_flags": {"is_locked": False, "transfer_count": 0},
        "timestamps": {
            "created_at": dt("2026-07-07T13:00:00Z"),
            "due_at": dt("2026-07-07T15:15:00Z"),
            "completed_at": None,
        },
    },
    {
        "_id": "task_20260707_0004", "task_code": "B2", "status": "Hoàn thành",
        "current_step": 2, "current_department": "B", "current_assigned_to": "staff_b1",
        "metrics": {"workload_score": 2.0, "step_duration_hours": 0.5,
                    "actual_duration_hours": 0.9, "early_completion_hours": 0.1},
        "workflow_history": [
            {"step_number": 1, "department": "B", "assigned_to": "staff_b3",
             "status": "Hoàn thành", "completed_at": dt("2026-07-07T09:30:00Z")},
            {"step_number": 2, "department": "B", "assigned_to": "staff_b1",
             "status": "Hoàn thành", "completed_at": dt("2026-07-07T10:15:00Z")},
        ],
        "control_flags": {"is_locked": True, "transfer_count": 0},
        "timestamps": {
            "created_at": dt("2026-07-07T09:00:00Z"),
            "due_at": dt("2026-07-07T10:30:00Z"),
            "completed_at": dt("2026-07-07T10:15:00Z"),
        },
    },
    {
        "_id": "task_20260707_0005", "task_code": "A4", "status": "Đang xử lý",
        "current_step": 3, "current_department": "C", "current_assigned_to": "staff_c2",
        "metrics": {"workload_score": 3.3, "step_duration_hours": 0.5,
                    "actual_duration_hours": None, "early_completion_hours": None},
        "workflow_history": [
            {"step_number": 1, "department": "A", "assigned_to": "staff_a3",
             "status": "Hoàn thành", "completed_at": dt("2026-07-07T08:00:00Z")},
            {"step_number": 2, "department": "B", "assigned_to": "staff_b4",
             "status": "Hoàn thành", "completed_at": dt("2026-07-07T08:45:00Z")},
            {"step_number": 3, "department": "C", "assigned_to": "staff_c2",
             "status": "Đang xử lý", "completed_at": None},
        ],
        "control_flags": {"is_locked": False, "transfer_count": 0},
        "timestamps": {
            "created_at": dt("2026-07-07T07:45:00Z"),
            "due_at": dt("2026-07-07T09:45:00Z"),
            "completed_at": None,
        },
    },
    {
        "_id": "task_20260707_0006", "task_code": "B5", "status": "Chờ xử lý",
        "current_step": 1, "current_department": "B", "current_assigned_to": "staff_b3",
        "metrics": {"workload_score": 4.3, "step_duration_hours": 0.5,
                    "actual_duration_hours": None, "early_completion_hours": None},
        "workflow_history": [
            {"step_number": 1, "department": "B", "assigned_to": "staff_b3",
             "status": "Chờ xử lý", "completed_at": None},
        ],
        "control_flags": {"is_locked": False, "transfer_count": 0},
        "timestamps": {
            "created_at": dt("2026-07-07T16:00:00Z"),
            "due_at": dt("2026-07-07T19:00:00Z"),
            "completed_at": None,
        },
    },
]

# ==========================================================================
# 5. DU LIEU MAU: overload_logs
# ==========================================================================

OVERLOAD_LOGS = [
    {
        "_id": "log_20260707_001",
        "timestamp": dt("2026-07-07T14:00:00Z"),
        "staff_id": "staff_b2",
        "trigger_reason": "Total hours reached 8.5 (Max: 8.0)",
        "manager_action": {
            "action_taken": "Approved_Suggestion",
            "resolved_by": "manager_01",
            "details": {"task_id": "task_20260707_0001",
                        "moved_from": "staff_b2", "moved_to": "staff_b4"},
        },
    },
    {
        "_id": "log_20260707_002",
        "timestamp": dt("2026-07-07T15:30:00Z"),
        "staff_id": "staff_c3",
        "trigger_reason": "Daily task count reached 6 (Max: 5)",
        "manager_action": {
            "action_taken": "Rejected_Suggestion",
            "resolved_by": "manager_02",
            "details": {"task_id": "task_20260707_0003", "moved_from": "staff_c3",
                        "moved_to": None,
                        "reason": "Nhân sự đề xuất không phù hợp chuyên môn"},
        },
    },
]


# ==========================================================================
# 6. MAIN
# ==========================================================================

def main():
    client = MongoClient(MONGO_URI)
    db = client[DB_NAME]

    print(f"Ket noi: {MONGO_URI}  |  Database: {DB_NAME}")
    print("Dang tao collections + schema validation...")
    create_collection_with_validator(db, "task_categories", TASK_CATEGORIES_VALIDATOR)
    create_collection_with_validator(db, "staffs", STAFFS_VALIDATOR)
    create_collection_with_validator(db, "tasks", TASKS_VALIDATOR)
    create_collection_with_validator(db, "overload_logs", OVERLOAD_LOGS_VALIDATOR)
    create_collection_with_validator(db, "users", USERS_VALIDATOR)

    print("Dang tao indexes...")
    db.task_categories.create_index([("task_code", ASCENDING)], unique=True)
    db.task_categories.create_index([("department", ASCENDING)])

    db.staffs.create_index([("department", ASCENDING)])
    db.staffs.create_index([("status", ASCENDING)])

    db.tasks.create_index([("task_code", ASCENDING)])
    db.tasks.create_index([("status", ASCENDING)])
    db.tasks.create_index([("current_department", ASCENDING)])
    db.tasks.create_index([("current_assigned_to", ASCENDING)])

    db.overload_logs.create_index([("staff_id", ASCENDING)])
    db.overload_logs.create_index([("timestamp", ASCENDING)])

    db.users.create_index([("role", ASCENDING)])
    db.users.create_index([("staff_id", ASCENDING)])

    print("Dang chen du lieu mau...")
    db.task_categories.insert_many(TASK_CATEGORIES)
    db.staffs.insert_many(STAFFS)
    db.tasks.insert_many(TASKS)
    db.overload_logs.insert_many(OVERLOAD_LOGS)
    db.users.insert_many(build_seed_users())

    print("\n=== TOM TAT ===")
    for name in ["task_categories", "staffs", "tasks", "overload_logs", "users"]:
        print(f"  {name:<16}: {db[name].count_documents({})} documents")

    client.close()
    print("\nHoan tat khoi tao database.")


if __name__ == "__main__":
    main()
