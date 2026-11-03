from datetime import datetime

from openpyxl import Workbook

from app.services.employee_import import COLUMNS


def label(f):
    return COLUMNS[f][1][0]


rows = [
    # A صالح، أدنى حقول، هاتف كرقم ضاع صفره وتاريخ كنص
    {"first_name": "سامر", "last_name": "درويش", "work_governorate": "دمشق",
     "phone_number": 933000010, "state_start_date": "01/03/2015",
     "appointment_category": "Cc"},
    # B صالح، بحقول أكثر
    {"first_name": "رنا", "father_name": "علي", "last_name": "الشامي",
     "hiring_qualification": "إجازة في الحقوق",
     "qualifications_excel_raw": "إجازة في الحقوق\nدبلوم تأهيل تربوي",
     "trainings_raw": "دورة الحاسوب ICDL\nدورة الإدارة الحديثة",
     "national_id": "05050505050", "work_governorate": "حلب",
     "phone_number": "0933000011", "state_start_date": datetime(2017, 6, 1),
     "appointment_category": "B", "marital_status": "متزوجة", "children_count": 2,
     "birth_date": datetime(1990, 4, 12), "org_level_1": "الوزارة", "org_level_2": "مديرية حلب"},
    # C خطأ: بلا رقم هاتف
    {"first_name": "نبيل", "last_name": "زيدان", "work_governorate": "دمشق",
     "state_start_date": "2016-02-01", "appointment_category": "Cc"},
    {},  # صف فارغ يُتجاهل
    # D خطأ: محافظة غير معروفة
    {"first_name": "لما", "last_name": "قاسم", "work_governorate": "مدينة الخيال",
     "phone_number": "0933000013", "state_start_date": "2016-02-01", "appointment_category": "Cc"},
    # E خطأ: تاريخ غير صالح
    {"first_name": "فراس", "last_name": "عيسى", "work_governorate": "حمص",
     "phone_number": "0933000014", "state_start_date": "31/31/2020", "appointment_category": "C"},
    # F مكرر في القاعدة (الموظف رقم 1 من اختبار سابق، إن كان موجوداً)
    {"first_name": "خالد", "last_name": "سعد", "national_id": "01010101010",
     "work_governorate": "دمشق", "phone_number": "0933000015",
     "state_start_date": "2016-02-01", "appointment_category": "Cc"},
    # G مكرر في الملف مع B
    {"first_name": "منى", "last_name": "حداد", "national_id": "05050505050",
     "work_governorate": "حلب", "phone_number": "0933000016",
     "state_start_date": "2016-02-01", "appointment_category": "B"},
    # I صالح: اسم ثلاثي فقط
    {"full_name_spaced": "هدى سمير خوري", "work_governorate": "حمص",
     "phone_number": "0933000012", "state_start_date": "2019-01-15",
     "appointment_category": "Bb"},
]

fields = list(COLUMNS)
wb = Workbook()
ws = wb.active
ws.append(["الاسم_الثلاثي"] + [label(f) for f in fields])
for r in rows:
    ws.append(["اسم_مشتق_خاطئ"] + [r.get(f) for f in fields])
wb.save("test_employees.xlsx")
print("created test_employees.xlsx")