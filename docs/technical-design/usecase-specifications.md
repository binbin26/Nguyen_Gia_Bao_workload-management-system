# Đặc tả Use Case

Tài liệu này chỉ mô tả các usecase truy ngược được từ code hiện tại. Các điểm có trong PRD/rule nhưng chưa xuất hiện trong implementation, ví dụ `idempotency_key` trên `/next-step`, không được đưa vào luồng chính.

## UC00 - Vận hành hệ thống điều phối tải lượng nhân sự

| Trường | Nội dung |
|---|---|
| Mã UC | UC00 |
| Tên usecase | Vận hành hệ thống điều phối tải lượng nhân sự |
| Actor | Manager, Staff, APScheduler, Caller nội bộ có `X-Internal-Secret`, Monitoring client |
| Mô tả tóm tắt | Usecase tổng bao phủ các nhóm chức năng đã hiện thực: xác thực/phân quyền, giám sát tải lượng, quản lý hồ sơ, điều phối quá tải và tự động hóa ngày mới. |
| Điều kiện tiên quyết | Ứng dụng FastAPI khởi động, MongoDB kết nối được; từng usecase con có điều kiện xác thực/quyền riêng. |
| Luồng sự kiện chính | 1. Actor đi vào một nhóm nghiệp vụ phù hợp.<br>2. Nhóm xác thực xử lý login/JWT/RBAC.<br>3. Nhóm giám sát cung cấp health check, dashboard summary và danh sách nhân sự.<br>4. Nhóm hồ sơ cung cấp danh sách task, tạo task, chọn nhân sự, ghi overload và luân chuyển state machine.<br>5. Nhóm quá tải cung cấp cảnh báo, tính suggestion và resolve overload.<br>6. Nhóm tự động hóa chạy daily reset/chunking qua scheduler hoặc endpoint nội bộ. |
| Luồng thay thế/ngoại lệ | Ngoại lệ nằm ở từng usecase con: lỗi auth, role sai, task/category/log không tồn tại, không tìm được nhân sự, secret cron sai hoặc job đã chạy trong ngày. |
| Hậu điều kiện | Hệ thống trả kết quả đọc/ghi tương ứng với usecase con được kích hoạt. |
| Nguồn code liên quan | `app/main.py:99`, `app/main.py:118`, `app/main.py:123`, `app/api/v1/*.py`, `app/services/*.py`, `app/repositories/*.py`, `app/cron/daily_reset_job.py`, `src/App.jsx:24`. |

## UC01 - Đăng nhập và nhận JWT

| Trường | Nội dung |
|---|---|
| Mã UC | UC01 |
| Tên usecase | Đăng nhập và nhận JWT |
| Actor | Người dùng chưa xác thực |
| Mô tả tóm tắt | Người dùng gửi `username/password`, API kiểm tra collection `users`, xác thực bcrypt và trả `access_token`, `token_type`, thông tin user. |
| Điều kiện tiên quyết | Collection `users` có document `_id = username`; cấu hình `JWT_SECRET_KEY`, `JWT_ALGORITHM`, `JWT_EXPIRE_MINUTES` khả dụng. |
| Luồng sự kiện chính | 1. Actor nhập username/password trên form login.<br>2. Frontend gọi `POST /api/v1/auth/login`.<br>3. API tìm user theo `_id` trong `db.users`.<br>4. Service kiểm tra `password_hash` bằng bcrypt.<br>5. Service tạo JWT payload có `sub`, `role`, `exp`, và `staff_id` nếu có.<br>6. API trả `ApiResponse[LoginResponse]` với message `Đăng nhập thành công`.<br>7. Frontend lưu `auth_token`, `auth_user` vào `localStorage` và điều hướng theo role. |
| Luồng thay thế/ngoại lệ | User không tồn tại hoặc password sai: service raise `INVALID_CREDENTIALS`, API trả 401 với message `Tài khoản hoặc mật khẩu không chính xác`. Staff đăng nhập trên UI hiện bị đưa về `/` rồi redirect lại `/login` vì route ứng dụng chỉ mở các màn chính cho manager. |
| Hậu điều kiện | JWT được cấp; frontend lưu token và gắn `Authorization: Bearer <token>` cho request sau. |
| Nguồn code liên quan | `app/api/v1/auth.py:13`, `app/api/v1/auth.py:33`, `app/services/auth_service.py:13`, `app/services/auth_service.py:23`, `app/services/auth_service.py:38`, `src/services/auth_api.js:29`, `src/context/AuthContext.jsx`, `src/pages/Login.jsx`. |

## UC02 - Xác thực JWT và phân quyền

| Trường | Nội dung |
|---|---|
| Mã UC | UC02 |
| Tên usecase | Xác thực JWT và phân quyền |
| Actor | Người dùng đã xác thực, Manager, Staff |
| Mô tả tóm tắt | Dependency giải mã Bearer JWT và kiểm tra role trước khi cho endpoint nghiệp vụ chạy. |
| Điều kiện tiên quyết | Request có header `Authorization: Bearer <jwt>`; JWT được ký bằng cấu hình hiện tại. |
| Luồng sự kiện chính | 1. Endpoint khai báo `Depends(require_role(...))` hoặc `Depends(get_current_user)`.<br>2. `HTTPBearer` lấy credential từ header.<br>3. `get_current_user` decode JWT bằng `settings.JWT_SECRET_KEY` và `settings.JWT_ALGORITHM`.<br>4. `require_role` kiểm tra `payload.role` nằm trong danh sách role được phép.<br>5. Payload user được truyền vào endpoint/service. |
| Luồng thay thế/ngoại lệ | Token hết hạn: trả 401 `Token đã hết hạn`. Token sai/malformed: trả 401 `Token không hợp lệ`. Role không đúng: trả 403 `FORBIDDEN_ACCESS`. Với `next-step`, service còn kiểm tra object-level: staff phải là người đang giữ `current_assigned_to`, manager được phép thao tác thay. |
| Hậu điều kiện | Endpoint nghiệp vụ được chạy hoặc request bị chặn trước khi đụng logic chính. |
| Nguồn code liên quan | `app/api/dependencies.py:17`, `app/api/dependencies.py:141`, `app/api/dependencies.py:166`, `app/services/task_service.py:37`, `app/core/config.py:25`, `app/core/config.py:26`. |

## UC03 - Kiểm tra sức khỏe dịch vụ

| Trường | Nội dung |
|---|---|
| Mã UC | UC03 |
| Tên usecase | Kiểm tra sức khỏe dịch vụ |
| Actor | Monitoring client |
| Mô tả tóm tắt | Client gọi health check để biết FastAPI service còn chạy. |
| Điều kiện tiên quyết | Ứng dụng FastAPI đã khởi động. |
| Luồng sự kiện chính | 1. Actor gọi `GET /health`.<br>2. Handler tạo `ApiResponse` với `data.status = ok`.<br>3. API trả message `Service is running`. |
| Luồng thay thế/ngoại lệ | Không có nhánh nghiệp vụ riêng trong code. Lỗi chỉ xảy ra nếu service không chạy hoặc framework lỗi. |
| Hậu điều kiện | Monitoring client nhận trạng thái service. |
| Nguồn code liên quan | `app/main.py:125`. |

## UC04 - Xem tổng hợp tải lượng dashboard

| Trường | Nội dung |
|---|---|
| Mã UC | UC04 |
| Tên usecase | Xem tổng hợp tải lượng dashboard |
| Actor | Manager |
| Mô tả tóm tắt | Manager xem thống kê tải lượng theo phòng ban qua aggregation trên collection `staffs`. |
| Điều kiện tiên quyết | JWT hợp lệ với role `manager`; MongoDB đã kết nối. Query `department` nếu có phải thuộc `A/B/C`. |
| Luồng sự kiện chính | 1. Manager gọi `GET /api/v1/dashboard/summary` với optional query `department`.<br>2. Dependency kiểm tra role `manager`.<br>3. Repository tạo aggregation pipeline trên `db.staffs`.<br>4. Pipeline optional `$match` theo phòng ban, `$group` tổng tasks/hours, staff count, average hours, và tính `by_status`.<br>5. API map kết quả sang `DepartmentSummary` và trả `DashboardSummaryResponse`. |
| Luồng thay thế/ngoại lệ | Thiếu/sai token hoặc sai role: bị chặn bởi UC02. Query param sai enum: FastAPI/Pydantic trả 422 qua validation handler. |
| Hậu điều kiện | Không thay đổi dữ liệu; client nhận danh sách summary. |
| Nguồn code liên quan | `app/api/v1/dashboard.py:21`, `app/api/v1/dashboard.py:24`, `app/repositories/staff_repository.py:26`, `app/schemas/dashboard.py`. |

## UC05 - Xem danh sách nhân sự

| Trường | Nội dung |
|---|---|
| Mã UC | UC05 |
| Tên usecase | Xem danh sách nhân sự |
| Actor | Manager |
| Mô tả tóm tắt | Manager lấy toàn bộ nhân sự để hiển thị dashboard/heatmap. |
| Điều kiện tiên quyết | JWT hợp lệ với role `manager`; collection `staffs` tồn tại. |
| Luồng sự kiện chính | 1. Manager hoặc frontend gọi `GET /api/v1/staffs`.<br>2. Dependency kiểm tra role `manager`.<br>3. Repository query toàn bộ `db.staffs`, sort theo `department`, `fullname`.<br>4. API map từng document sang `StaffOut` và trả `StaffListResponse`. |
| Luồng thay thế/ngoại lệ | Thiếu/sai token hoặc sai role: bị chặn bởi UC02. |
| Hậu điều kiện | Không thay đổi dữ liệu; client nhận danh sách nhân sự. |
| Nguồn code liên quan | `app/api/v1/staffs.py:10`, `app/api/v1/staffs.py:13`, `app/repositories/staff_repository.py:15`, `app/schemas/staff.py`, `src/services/staff_api.jsx:21`, `src/pages/Dashboard.jsx`. |

## UC06 - Xem danh sách hồ sơ

| Trường | Nội dung |
|---|---|
| Mã UC | UC06 |
| Tên usecase | Xem danh sách hồ sơ |
| Actor | Manager |
| Mô tả tóm tắt | Manager lấy toàn bộ hồ sơ để xem bảng task và timeline chi tiết ở frontend. |
| Điều kiện tiên quyết | JWT hợp lệ với role `manager`; collection `tasks` tồn tại. |
| Luồng sự kiện chính | 1. Manager hoặc frontend gọi `GET /api/v1/tasks`.<br>2. Dependency kiểm tra role `manager`.<br>3. Repository query toàn bộ `db.tasks`, sort mới nhất trước theo `timestamps.created_at`.<br>4. API map document sang `TaskOut` và trả danh sách. |
| Luồng thay thế/ngoại lệ | Thiếu/sai token hoặc sai role: bị chặn bởi UC02. Frontend có bộ lọc status/phòng ban nhưng lọc tại client sau khi nhận danh sách. |
| Hậu điều kiện | Không thay đổi dữ liệu; client nhận danh sách hồ sơ. |
| Nguồn code liên quan | `app/api/v1/tasks.py:36`, `app/repositories/task_repository.py:69`, `app/schemas/task.py`, `src/services/task_api.js:21`, `src/pages/TaskCenter.jsx`, `src/components/tasks/TaskFilter.jsx`. |

## UC07 - Tạo hồ sơ mới và phân công tự động

| Trường | Nội dung |
|---|---|
| Mã UC | UC07 |
| Tên usecase | Tạo hồ sơ mới và phân công tự động |
| Actor | Staff, Manager |
| Mô tả tóm tắt | Actor gửi `task_code`; backend tìm SOP, lấy bước đầu tiên, chọn nhân sự phù hợp và tạo document `tasks` trong transaction. |
| Điều kiện tiên quyết | JWT hợp lệ với role `staff` hoặc `manager`; `task_code` có trong `task_categories`; MongoDB replica set/session hoạt động. |
| Luồng sự kiện chính | 1. Actor gọi `POST /api/v1/tasks` với body `{task_code}`.<br>2. API kiểm tra role `staff` hoặc `manager`.<br>3. Repository tìm category theo `task_code`.<br>4. Lấy `workflow_steps[0]` để xác định `department`, `duration_hours` và lấy `workload_score` từ `standard_metrics`.<br>5. Repository lấy staff cùng phòng ban.<br>6. UC08 chọn staff có ETC thấp nhất trong nhóm còn capacity.<br>7. Transaction sinh `_id` dạng `task_YYYYMMDD_XXXX`, insert task status `Đang xử lý`, workflow history bước 1, và `$inc` workload của staff được chọn.<br>8. API trả `TaskCreateResponse` gồm task và `assigned_to`. |
| Luồng thay thế/ngoại lệ | Không tìm thấy category: trả 404 `TASK_CATEGORY_NOT_FOUND`. Không có staff hợp lệ: code hiện tại vẫn tạo task status `Chờ xử lý`, `current_assigned_to = ""`, ghi `overload_logs` Pending và trả message hồ sơ đang chờ xử lý do quá tải. |
| Hậu điều kiện | Có document mới trong `tasks`; nếu có assignee thì `staffs.workload_caps.current_daily_tasks/current_daily_hours` tăng; nếu không có assignee thì có `overload_logs` Pending. |
| Nguồn code liên quan | `app/api/v1/tasks.py:50`, `app/api/v1/tasks.py:61`, `app/repositories/task_repository.py:35`, `app/repositories/task_repository.py:48`, `app/repositories/task_repository.py:113`, `app/repositories/task_repository.py:159`, `app/services/assignment_service.py:11`, `app/repositories/log_repository.py:23`. |

## UC08 - Chọn nhân sự theo ETC

| Trường | Nội dung |
|---|---|
| Mã UC | UC08 |
| Tên usecase | Chọn nhân sự theo ETC |
| Actor | Hệ thống |
| Mô tả tóm tắt | Logic nội bộ chọn staff rảnh nhất trong phòng ban cho tạo task và next-step. Resolve overload dùng `selected_staff_id` do manager gửi lên rồi kiểm tra hợp lệ theo code hiện tại. |
| Điều kiện tiên quyết | Có danh sách staff candidate và `duration_hours` của bước cần gán. |
| Luồng sự kiện chính | 1. Hệ thống nhận danh sách candidate.<br>2. Loại staff có `status = Nghỉ phép`.<br>3. Loại staff mà sau khi cộng việc mới sẽ vượt `max_daily_tasks` hoặc `max_daily_hours`.<br>4. Nếu còn candidate, chọn staff có `workload_caps.current_daily_hours` thấp nhất. |
| Luồng thay thế/ngoại lệ | Nếu không còn staff hợp lệ, trả `None`; caller quyết định tạo overload log hoặc tạm dừng task. |
| Hậu điều kiện | Không ghi DB trực tiếp; trả staff document hoặc `None`. |
| Nguồn code liên quan | `app/services/assignment_service.py:11`, `app/services/assignment_service.py:42`, `tests/unit_test/test_task_5.py`. |

## UC09 - Ghi cảnh báo quá tải Pending

| Trường | Nội dung |
|---|---|
| Mã UC | UC09 |
| Tên usecase | Ghi cảnh báo quá tải Pending |
| Actor | Hệ thống |
| Mô tả tóm tắt | Khi không gán được nhân sự hoặc capacity bị vượt, hệ thống tạo document trong `overload_logs` với `manager_action.action_taken = Pending`. |
| Điều kiện tiên quyết | Có MongoDB database/session; caller cung cấp `staff_id`, `trigger_reason`, và `details` nếu có. |
| Luồng sự kiện chính | 1. Caller gọi `create_pending_overload_log`.<br>2. Repository sinh `_id` dạng `log_YYYYMMDD_NNN`.<br>3. Tạo document gồm timestamp UTC, staff_id, trigger_reason, manager_action Pending, resolved_by rỗng và details.<br>4. Insert vào `db.overload_logs`. |
| Luồng thay thế/ngoại lệ | Nếu gọi từ `enforce_workload_capacity`, sau khi ghi log hệ thống raise 403 `WORKLOAD_CAP_EXCEEDED`. Trong create-task/next-step, log được ghi trong transaction nghiệp vụ. |
| Hậu điều kiện | Có cảnh báo Pending để manager xử lý qua UC11/UC13. |
| Nguồn code liên quan | `app/repositories/log_repository.py:8`, `app/repositories/log_repository.py:23`, `app/api/dependencies.py:68`, `app/repositories/task_repository.py:159`, `app/services/task_service.py:154`, `app/schemas/overload_log.py:8`. |

## UC10 - Hoàn thành bước và luân chuyển hồ sơ

| Trường | Nội dung |
|---|---|
| Mã UC | UC10 |
| Tên usecase | Hoàn thành bước và luân chuyển hồ sơ |
| Actor | Staff, Manager |
| Mô tả tóm tắt | Actor hoàn thành bước hiện tại của task; hệ thống cập nhật history, giải phóng slot task cũ, rồi hoàn thành toàn bộ hoặc gán bước kế tiếp. |
| Điều kiện tiên quyết | JWT hợp lệ với role `staff` hoặc `manager`; task tồn tại, status `Đang xử lý`; staff chỉ được thao tác nếu `staff_id == current_assigned_to`. |
| Luồng sự kiện chính | 1. Actor gọi `POST /api/v1/tasks/{task_id}/next-step`.<br>2. API kiểm tra role `staff` hoặc `manager`.<br>3. Service mở transaction, đọc task và category.<br>4. Service kiểm tra object-level bằng `assert_can_complete_step`.<br>5. Cập nhật entry `workflow_history` của bước hiện tại sang `Hoàn thành`, ghi `completed_at`, `actual_duration_hours`, có thể ghi `early_completion_hours`.<br>6. Giảm `workload_caps.current_daily_tasks` của assignee cũ, không giảm giờ theo nguyên tắc code hiện tại.<br>7. Nếu là bước cuối, set task `Hoàn thành`, `current_assigned_to = ""`, `control_flags.is_locked = true`, `timestamps.completed_at`.<br>8. Nếu còn bước, lấy next step, chạy UC08 để chọn staff.<br>9. Nếu có staff, cập nhật task sang bước mới, push workflow history mới, reset metrics bước, cập nhật due_at, và `$inc` workload staff mới.<br>10. API trả task cập nhật, `assigned_to`, và `overload_log_id` nếu có. |
| Luồng thay thế/ngoại lệ | Task không tồn tại: 404 `TASK_NOT_FOUND`. Task đã đóng: 409 `TASK_ALREADY_CLOSED`. Task không ở `Đang xử lý`: 409 `TASK_INVALID_STATUS`. Staff không phải assignee: 403 `FORBIDDEN_NOT_ASSIGNEE`. Category thiếu: 404 `CATEGORY_NOT_FOUND`. Không có staff ở phòng ban kế tiếp: set task `Tạm dừng`, ghi overload log Pending và trả `overload_log_id`. |
| Hậu điều kiện | Task chuyển bước, hoàn thành, hoặc tạm dừng; workload staff được cập nhật trong cùng transaction. |
| Nguồn code liên quan | `app/api/v1/tasks.py:99`, `app/api/v1/tasks.py:110`, `app/services/task_service.py:37`, `app/services/task_service.py:58`, `app/services/task_service.py:95`, `app/services/task_service.py:135`, `app/services/task_service.py:154`, `app/repositories/task_repository.py:75`, `app/repositories/task_repository.py:93`, `src/services/task_api.js:26`, `src/components/tasks/TaskDetailDrawer.jsx`. |

## UC11 - Xem cảnh báo quá tải

| Trường | Nội dung |
|---|---|
| Mã UC | UC11 |
| Tên usecase | Xem cảnh báo quá tải |
| Actor | Manager |
| Mô tả tóm tắt | Manager lấy danh sách overload log Pending kèm ngữ cảnh task và gợi ý nhân sự thay thế. |
| Điều kiện tiên quyết | JWT hợp lệ với role `manager`; collection `overload_logs` tồn tại. |
| Luồng sự kiện chính | 1. Manager hoặc frontend gọi `GET /api/v1/analytics/overloads`.<br>2. Dependency kiểm tra role `manager`.<br>3. Service query `db.overload_logs` với `manager_action.action_taken = Pending`.<br>4. Với mỗi log có `details.task_id`, service đọc task liên quan.<br>5. Nếu có task/phòng ban, service gọi UC12 để tính suggestions.<br>6. API trả `{items: [...]}`. |
| Luồng thay thế/ngoại lệ | Thiếu/sai token hoặc sai role: bị chặn bởi UC02. Log không có `task_id` vẫn được đưa vào response với task context null/None và suggestions rỗng. |
| Hậu điều kiện | Không thay đổi dữ liệu; manager nhận danh sách cảnh báo pending. |
| Nguồn code liên quan | `app/api/v1/analytics.py:18`, `app/services/analytics_service.py:60`, `app/repositories/task_repository.py:59`, `src/services/analytics_api.js:25`, `src/pages/OverloadAlerts.jsx`, `src/components/analytics/OverloadCard.jsx`. |

## UC12 - Tính gợi ý điều phối matching_score

| Trường | Nội dung |
|---|---|
| Mã UC | UC12 |
| Tên usecase | Tính gợi ý điều phối matching_score |
| Actor | Hệ thống |
| Mô tả tóm tắt | Hệ thống lọc candidate cùng phòng ban và xếp hạng theo `matching_score = 1 - current_daily_hours / max_daily_hours`. |
| Điều kiện tiên quyết | Có danh sách staff candidate và duration của task/bước cần điều phối. |
| Luồng sự kiện chính | 1. Loại staff `Nghỉ phép` hoặc vượt capacity sau khi cộng duration.<br>2. Với từng staff còn lại, tính matching_score.<br>3. Tạo suggestion gồm staff_id, fullname, department, current_daily_tasks, current_daily_hours, matching_score.<br>4. Sort giảm dần theo matching_score. |
| Luồng thay thế/ngoại lệ | `max_daily_hours <= 0` thì matching_score giữ 0. Nếu không có candidate hợp lệ, trả list rỗng. |
| Hậu điều kiện | Không ghi DB; response UC11 có danh sách suggestion. |
| Nguồn code liên quan | `app/services/analytics_service.py:15`, `app/services/analytics_service.py:50`, `tests/unit_test/test_analytics_service.py`, `src/components/analytics/AIResolutionModal.jsx`. |

## UC13 - Xử lý cảnh báo quá tải

| Trường | Nội dung |
|---|---|
| Mã UC | UC13 |
| Tên usecase | Xử lý cảnh báo quá tải |
| Actor | Manager |
| Mô tả tóm tắt | Manager resolve một overload log; với `Approved_Suggestion` hoặc `Manual_Override`, hệ thống gán task cho staff được chọn và cập nhật workload/log trong transaction. |
| Điều kiện tiên quyết | JWT hợp lệ với role `manager`; `log_id` tồn tại và đang Pending; nếu action cần staff thì `selected_staff_id` tồn tại và cùng phòng ban task hiện tại. |
| Luồng sự kiện chính | 1. Manager gọi `POST /api/v1/analytics/overloads/{log_id}/resolve` với `action_taken` và optional `selected_staff_id`.<br>2. API kiểm tra role `manager`.<br>3. Service mở transaction, đọc overload log và task liên quan từ `manager_action.details.task_id`.<br>4. Cập nhật `manager_action.action_taken`, `resolved_by`, và details bổ sung `resolved_at`, `selected_staff_id`, `action_taken`.<br>5. Nếu action là `Approved_Suggestion` hoặc `Manual_Override`, kiểm tra staff được chọn tồn tại và cùng department.<br>6. Nếu task đang `Tạm dừng` hoặc `Chờ xử lý`, set status về `Đang xử lý`.<br>7. Cập nhật `tasks.current_assigned_to`, tăng `control_flags.transfer_count`, cập nhật assigned_to trong workflow_history bước hiện tại.<br>8. Cập nhật workload của staff cũ nếu có và staff mới.<br>9. Update overload log và trả kết quả. |
| Luồng thay thế/ngoại lệ | Log không tồn tại: 404 `OVERLOAD_LOG_NOT_FOUND`. Log đã xử lý: 409 `OVERLOAD_LOG_ALREADY_RESOLVED`. Thiếu selected_staff khi cần: 400 `STAFF_NOT_SELECTED`. Staff không tồn tại: 404 `STAFF_NOT_FOUND`. Staff khác department: 400 `STAFF_DEPARTMENT_MISMATCH`. Nếu service raise `TASK_NOT_FOUND` hoặc `INVALID_DURATION`, endpoint hiện không map riêng nên lỗi sẽ nổi lên theo handler mặc định/runtime. |
| Hậu điều kiện | Overload log không còn Pending; task có thể được gán lại; workload staff và workflow history được cập nhật. |
| Nguồn code liên quan | `app/api/v1/analytics.py:32`, `app/api/v1/analytics.py:38`, `app/services/analytics_service.py:115`, `app/schemas/overload_log.py:8`, `app/schemas/overload_log.py:40`, `src/services/analytics_api.js:30`, `src/components/analytics/AIResolutionModal.jsx`. |

## UC14 - Kích hoạt tác vụ tái lập ngày mới nội bộ

| Trường | Nội dung |
|---|---|
| Mã UC | UC14 |
| Tên usecase | Kích hoạt tác vụ tái lập ngày mới nội bộ |
| Actor | Caller nội bộ có `X-Internal-Secret` |
| Mô tả tóm tắt | Endpoint vận hành gọi thủ công job reset/chunking, được bảo vệ bằng secret header riêng. |
| Điều kiện tiên quyết | `CRON_SECRET_KEY` hoặc `INTERNAL_CRON_SECRET` được cấu hình; request có header `X-Internal-Secret` đúng. |
| Luồng sự kiện chính | 1. Actor gọi `POST /api/v1/system/daily-reset` với header secret.<br>2. Dependency `require_internal_secret` so sánh header với secret cấu hình.<br>3. Endpoint gọi `run_daily_reset(db, client)`.<br>4. API trả kết quả job trong `ApiResponse`. |
| Luồng thay thế/ngoại lệ | Không cấu hình secret: 500 `CRON_SECRET_NOT_CONFIGURED`. Secret sai/thiếu: 403 `FORBIDDEN_INTERNAL_SECRET`. Nếu job đã chạy trong ngày, UC15 trả status `skipped`. |
| Hậu điều kiện | Job reset/chunking được chạy hoặc skip idempotent. |
| Nguồn code liên quan | `app/api/v1/system.py:14`, `app/api/v1/system.py:34`, `app/api/v1/system.py:41`, `app/core/config.py:30`, `app/cron/daily_reset_job.py:103`. |

## UC15 - Reset tải lượng và chunking hằng ngày

| Trường | Nội dung |
|---|---|
| Mã UC | UC15 |
| Tên usecase | Reset tải lượng và chunking hằng ngày |
| Actor | APScheduler, Caller nội bộ thông qua UC14 |
| Mô tả tóm tắt | Job ngày mới reset workload staff, chunk các task đang xử lý tối đa 4 giờ/ngày và ghi lock idempotency trong `system_state`. |
| Điều kiện tiên quyết | MongoDB replica set/session hoạt động; app lifespan đã kết nối DB; APScheduler được khởi động nếu chạy tự động. |
| Luồng sự kiện chính | 1. APScheduler kích hoạt lúc 00:00 Asia/Ho_Chi_Minh hoặc UC14 gọi thủ công.<br>2. `run_daily_reset` mở transaction.<br>3. `_acquire_daily_reset_lock` đọc/cập nhật `system_state` document `_id = daily_reset` theo `last_run_date`.<br>4. Nếu chưa chạy trong ngày, reset `staffs.workload_caps.current_daily_tasks = 0` và `current_daily_hours = 0.0`.<br>5. Query tasks có `status = Đang xử lý`.<br>6. Với từng task hợp lệ, `build_chunking_update_for_task` tính `chunked_hours = min(remaining_step_hours, 4.0)`, cập nhật `remaining_step_hours`, `last_chunked_date`, và gom workload theo staff.<br>7. Bulk write cập nhật tasks rồi bulk write cộng workload cho staffs.<br>8. Transaction commit và trả thống kê matched/reset/chunked/skipped/staff_ids_updated. |
| Luồng thay thế/ngoại lệ | Nếu lock cho ngày hiện tại đã có, trả `status = skipped`. Task bị skip nếu không `Đang xử lý`, bị `control_flags.is_locked`, không có assignee, đã chunk trong ngày, thiếu/không còn remaining hours hoặc remaining <= 0. |
| Hậu điều kiện | Tải lượng ngày mới của staff phản ánh các chunk task còn đang xử lý; job không cộng lặp trong cùng ngày. |
| Nguồn code liên quan | `app/main.py:75`, `app/main.py:76`, `app/cron/daily_reset_job.py:11`, `app/cron/daily_reset_job.py:17`, `app/cron/daily_reset_job.py:21`, `app/cron/daily_reset_job.py:69`, `app/cron/daily_reset_job.py:103`, `tests/unit_test/test_daily_reset_job.py`, `tests/unit_test/test_scheduler.py`. |
