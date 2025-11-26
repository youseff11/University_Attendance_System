# doctors/urls.py

from django.urls import path
from . import views
from django.contrib.auth import views as auth_views
from .views import GroupAutocomplete , StudentAutocomplete

urlpatterns = [
    path('', views.doctor_dashboard, name='dashboard'), 

    # 2. Login & Logout
    path('login/', auth_views.LoginView.as_view(template_name='doctors/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='login'), name='logout'),

    # 3. Password Reset (لإكمال الـ Authentication)
    path('password_reset/', auth_views.PasswordResetView.as_view(template_name='doctors/password_reset_form.html'), name='password_reset'),
    path('password_reset/done/', auth_views.PasswordResetDoneView.as_view(template_name='doctors/password_reset_done.html'), name='password_reset_done'),
    path('reset/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(template_name='doctors/password_reset_confirm.html'), name='password_reset_confirm'),
    path('reset/done/', auth_views.PasswordResetCompleteView.as_view(template_name='doctors/password_reset_complete.html'), name='password_reset_complete'),
    
    # 4. Attendance Management (سنضيفها لاحقاً)
    path('courses/', views.course_list, name='course_list'), 
    path('course/<int:course_id>/groups/', views.group_list, name='group_list'),
    path('group/<int:group_id>/students/upload/', views.student_upload_excel, name='student_upload_excel'),

    path('attendance/select-group/', views.select_group_for_attendance, name='select_group_for_attendance'), 
    path('attendance/group/<int:group_id>/take/', views.take_attendance, name='take_attendance'),

    #  Paths for Reports
    path('reports/', views.report_home, name='report_home'),
    path('reports/course/<int:course_id>/', views.course_report, name='course_report'), 
    path('students/', views.student_search, name='student_search'),
    path('group/<int:group_id>/students/list/', views.group_student_list, name='group_student_list'),
    path('group-autocomplete/', GroupAutocomplete.as_view(), name='group_autocomplete'),
    path('student-autocomplete/', StudentAutocomplete.as_view(), name='student_autocomplete'),
    path('doctors/', views.doctor_list, name='doctor_list'),

]