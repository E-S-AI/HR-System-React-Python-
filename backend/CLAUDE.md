# Centralized HRMS - Context & Rules (DO NOT SCAN COMPLETED FILES UNLESS ASKED)

## 1. Tech Stack & Style
- Python 3.13, FastAPI, Async SQLAlchemy 2.x (`Mapped`, `mapped_column`, `AsyncSession`), Pydantic v2, Alembic, PostgreSQL.
- Follow existing patterns: async DB queries, row locking (`with_for_update`), Arabic HTTPException messages, scope filtering via `app.services.scope.get_scope`.
- **Arabic-first (DONE)**:
  - `app/core/text.py`: `clean_text` (NFKC + zero-width/BiDi strip + tatweel + NBSP + whitespace collapse), `to_ascii_digits` (٠-٩/۰-۹ → 0-9), `norm_search` (diacritics/tatweel/alef/ya/ta-marbuta unified, punctuation → space, lowercase), `normalize_gender` (→ "ذكر"/"أنثى"/None).
  - `app/core/labels_ar.py`: `*_LABELS_AR` maps (leave status/action/transaction/entry source, import status/error type, assignment action) + `FIELD_LABELS_AR`, `CHANGE_FIELD_LABELS_AR`, `label_for(code, mapping)`. `CHANGE_FIELD_LABELS_AR`/`FIELD_LABELS_AR` are built from `employee_export.EXPORT_COLUMNS`.
  - `app/core/errors.py`: registered in `main.py`; Arabic 422 with per-field `{field,label,message}` and summary `detail`; framework 404/403/405/401 translated; unhandled → 500 Arabic (raw pydantic errors never leak).
  - Read schemas carry `*_label_ar` fields filled by `model_validator(mode="after")` via `label_for` (so services need only pass codes): `LeaveRequestRead` (`status_label_ar`, `entry_source_label_ar`), `ApprovalLogRead` (`from/to_status_label_ar`, `action_type_label_ar`), `TransactionRead` (`transaction_type_label_ar`), `AssignmentRead` (`action_type_label_ar`), `ImportJobRead` (`status_label_ar`), `ImportErrorRead` (`error_type_label_ar`). Codes stay English in the API; Arabic is additive.
  - Input schemas run `clean_text` (free text) and `to_ascii_digits` (IDs/phones/decision numbers/years) in `mode="before"` validators; `gender` is normalised to ذكر/أنثى.
  - Import (`services/employee_import.py`): `"gender"` column kind → `normalize_gender`, unknown raises `ValueError("الجنس يجب أن يكون ذكر أو أنثى")` recorded as `INVALID_VALUE`. `services/excel_utils.py` now delegates to `core.text` (`norm_text = norm_search`, `to_ascii_digits` replaces local digit table, `clean_cell` uses `clean_text`).
  - Search: `services/arabic_search.py` — `norm_sql(column)` (lower + regexp_replace diacritics/tatweel + translate alef/ya/ta-marbuta + collapse spaces) and `name_search_conditions(search, column)` (multi-word AND, each word ILIKE-normalised). `employee_export.build_conditions` uses it: `(all name words match) OR (national_id/employee_code/phone ILIKE)`.
  - `GET /employees` accepts `sort_by` (`id` default | `name`); `name` orders by `full_name_spaced COLLATE "ar-x-icu"` and falls back to `id` if the collation is unavailable. `GET /lookups/labels?group=...` returns `{group: [{code,label_ar}]}`; `GET /lookups/employee-field-values/{field}` returns distinct values (whitelisted fields, HR scope-filtered) as `[{code,label_ar}]`.
  - Tests: `tests/test_arabic.py` (pure functions, no DB). Dev deps in `requirements-dev.txt`. Run `python -m pytest tests -q` and `python -m compileall app`.

## 2. Completed Modules (DO NOT RE-READ OR MODIFY UNLESS NECESSARY)
- **Auth & 2FA**: `models/user.py`, `models/role.py`, `services/auth.py`, `services/twofa.py`, `services/users.py` (Employees use 6-digit PIN; HR/Admin use Google Auth).
- **Org & Scopes**: `models/org.py`, `services/org.py`, `services/scope.py` (5 levels, governorate/org_unit isolation).
- **Employees & Code**: `models/employee.py`, `models/employee_extra.py`, `models/employee_change_log.py`, `services/employees.py`, `services/employee_files.py`, `services/assignments.py` (14 Governorates incl. `QU`, 6 Categories `Aa,A,B,Bb,Cc,C`, immutable code `DM-Cc-0001`, qualifications, trainings, assignments).
- **Excel Import/Export**: `models/imports.py`, `models/export_log.py`, `services/employee_import.py`, `services/employee_export.py`.
- **Work Schedules & Holidays**: `models/work_schedule.py`, `models/holiday.py`, `services/work_schedules.py`, `services/holidays.py`.
- **Leaves & Balances**: `models/leave.py`, `models/leave_request.py`, `services/leave_balances.py`, `services/leave_requests.py`, `services/leave_rules.py` (No electronic manager; employee prints PDF -> signs on paper -> uploads within 72h for ADMIN/HOURLY -> HR approves. HOURLY: 60-120m. MISSION: no 72h rule, no balance deduction).
- **Dashboard**: `schemas/dashboard.py`, `services/dashboard.py`, `api/dashboard.py`.

- **Task A - HR Direct Decisions & Paper Form Templates (DONE)**:
  - Part 1: `POST /leave-requests/hr-decisions` (`create_hr_decision` in `services/leave_requests.py`) records `UNPAID, SICK, MARRIAGE, DEATH, HAJJ` with `entry_source='HR_DIRECT_DECISION'`, `status='APPROVED'`, `hr_decision_number`, uploaded decision paper, no balance deduction. Shared `_validate_paper` helper.
  - Part 2: client-supplied PDF templates, NOT generated. `schemas/leave_form.py`, `services/leave_form_templates.py`, `api/leave_forms.py` (`/leave-forms`: POST upload+`page_map` split via pypdf [CENTRAL_ADMIN/CENTRAL_HR], GET list, GET `/{code}` download, DELETE `/{code}`). Paths stored relative to `upload_dir` in `leave_types.printable_pdf_template_path` under `leave_forms/templates/`. Employee prints, signs, uploads scan via existing `POST /leave-requests/{id}/paper`.
  - The generated-form code (`services/leave_forms.py`, `/leave-requests/{id}/printable`, fpdf2/uharfbuzz) was REMOVED ON PURPOSE. Do not reintroduce it. `leave_requests.generated_printable_pdf_path` is intentionally left unused (no migration).

## 3. Remaining Backend Tasks (Build ONLY when requested one by one)
2. **Task B (Biometrics & Attendance - 3 Tables)**:
   - `biometric_devices` (`id, device_name, platform_url, org_unit_id, last_sync_at, last_sync_status, is_active`).
   - `attendance_sync_logs` (`id, device_id, sync_source, started_at, finished_at, records_fetched, records_inserted, records_duplicated, unmapped_users_count, error_details`).
   - `attendance_records`: 7 platform columns (`biometric_user_id, biometric_employee_name, attendance_date, first_in, last_out, platform_status, platform_directorate`) + `work_schedule_id, employee_id, linked_leave_request_id, late_minutes, early_leave_minutes, is_late_beyond_cutoff, is_early_leave_beyond_cutoff, counted_as_hourly_leave, hourly_leave_minutes_charged, final_system_status, source_type, import_job_id, reviewed_by_user_id, reviewed_at, review_notes, created_at`. Unique `(biometric_user_id, attendance_date)`.
   - Business rule: Late after `late_cutoff_time` (08:20) or early leave before `early_leave_cutoff_time` (14:40/15:40) creates a `BIOMETRIC_DEDUCT` in `leave_transactions` linked to `attendance_record_id` (subtracting any approved `HOURLY` leave on the same day to avoid double deduction; 0 deduction if `ON_MISSION` or `ON_LEAVE` or holiday).
   - Smart Arabic name matching (`norm_text`) to link `biometric_user_id` to `employees.biometric_code`.
3. **Task C (Audit Logs & Background Scheduler)**:
   - `audit_logs` table (`id, user_id, org_unit_id, action_type, target_table, target_record_id, old_data, new_data, ip_address, created_at`).
   - Celery/Scheduler tasks for `auto_reject_overdue` (every 10m) and `grant_year` (Jan 1st).