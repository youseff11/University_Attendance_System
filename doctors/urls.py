from django.urls import path
from . import views
from django.contrib.auth import views as auth_views
from .views import GroupAutocomplete, StudentAutocomplete
from .api_views import StudentProfileView

urlpatterns = [
    # 1. لوحة التحكم الرئيسية
    path('', views.doctor_dashboard, name='dashboard'), 
    path('doctor/dashboard/', views.doctor_dashboard, name='doctor_dashboard'), # مسار إضافي للاحتياط

    # 2. إدارة الدخول والخروج (Authentication)
    path('login/', auth_views.LoginView.as_view(template_name='doctors/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='login'), name='logout'),

    # 3. استعادة كلمة المرور (Password Reset)
    path('password_reset/', auth_views.PasswordResetView.as_view(template_name='doctors/password_reset_form.html'), name='password_reset'),
    path('password_reset/done/', auth_views.PasswordResetDoneView.as_view(template_name='doctors/password_reset_done.html'), name='password_reset_done'),
    path('reset/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(template_name='doctors/password_reset_confirm.html'), name='password_reset_confirm'),
    path('reset/done/', auth_views.PasswordResetCompleteView.as_view(template_name='doctors/password_reset_complete.html'), name='password_reset_complete'),
    
    # 4. إدارة المقررات والمجموعات والطلاب
    path('courses/', views.course_list, name='course_list'), 
    path('course/<int:course_id>/groups/', views.group_list, name='group_list'),
    path('group/<int:group_id>/students/upload/', views.student_upload_excel, name='student_upload_excel'),
    path('group/<int:group_id>/students/list/', views.group_student_list, name='group_student_list'),
    path('students/', views.student_search, name='student_search'),

    # 5. تسجيل الحضور (Attendance)
    path('attendance/select-group/', views.select_group_for_attendance, name='select_group_for_attendance'), 
    path('attendance/group/<int:group_id>/take/', views.take_attendance, name='take_attendance'),

    # 6. ميزات بصمة الوجه (Face Recognition)
    # ملاحظة: هذا المسار هو الذي يتم استدعاؤه من الـ JavaScript في صفحة الكاميرا
    path('attendance/verify-face/', views.face_attendance_check, name='face_attendance_check'),
    path('attendance/sync-aws/', views.index_students_to_aws, name='sync_students_aws'),

    # 7. التقارير والإحصائيات
    path('reports/', views.report_home, name='report_home'),
    path('reports/course/<int:course_id>/', views.course_report, name='course_report'), 
    path('doctors/', views.doctor_list, name='doctor_list'),

    # 8. الملف الشخصي والجدول الأكاديمي
    path('profile/update-image/', views.update_profile_image, name='update_profile_image'),
    path('update-schedule/', views.update_schedule_image, name='update_schedule_image'),

    # 9. أدوات البحث التلقائي (Autocomplete)
    path('group-autocomplete/', GroupAutocomplete.as_view(), name='group_autocomplete'),
    path('student-autocomplete/', StudentAutocomplete.as_view(), name='student_autocomplete'),

    # 10. واجهة برمجة التطبيقات (API)
    path('api/student/profile/<str:university_id>/', StudentProfileView.as_view(), name='student_profile_api'),
    path('lecture/<int:lecture_id>/pdf/', views.export_attendance_pdf, name='export_attendance_pdf'),
]