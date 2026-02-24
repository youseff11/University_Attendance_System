# doctors/admin.py

import pandas as pd
from io import BytesIO
from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin
from django import forms
from dal import autocomplete 
from django.db import transaction
from django.core.exceptions import ValidationError
from django.utils.html import format_html 
from django.http import HttpResponseRedirect
from django.urls import reverse

# استيراد الموديلات
from .models import DoctorProfile, Course, Group, Student, Lecture, AttendanceRecord

# ==============================================================================
# 1. Doctor Profile Admin
# ==============================================================================
class DoctorProfileAdmin(UserAdmin):
    list_display = ('display_avatar', 'username', 'display_schedule', 'role', 'is_staff')
    list_filter = ('is_staff', 'is_superuser', 'is_active', 'groups', 'role')

    fieldsets = UserAdmin.fieldsets + (
        ('Extra Profile Info & Media', {
            'fields': ('role', 'image', 'schedule_image'),
        }),
    )

    add_fieldsets = UserAdmin.add_fieldsets + (
        (None, {
            'classes': ('wide',),
            'fields': ('role', 'image', 'schedule_image'),
        }),
    )

    def display_avatar(self, obj):
        if obj.image:
            return format_html('<img src="{}" style="width: 35px; height: 35px; border-radius: 50%; object-fit: cover;" />', obj.image.url)
        return format_html('<div style="width: 35px; height: 35px; border-radius: 50%; background: #ddd; display: flex; align-items: center; justify-content: center; font-size: 10px; color: #666;">No IMG</div>')
    
    def display_schedule(self, obj):
        if obj.schedule_image:
            return format_html('<span style="color: #28a745;"><i class="fas fa-check-circle"></i> Uploaded</span>')
        return format_html('<span style="color: #dc3545;"><i class="fas fa-times-circle"></i> No Schedule</span>')

    display_avatar.short_description = 'Avatar'
    display_schedule.short_description = 'Schedule Status'

admin.site.register(DoctorProfile, DoctorProfileAdmin)

# ==============================================================================
# 2. Course & Group Admin
# ==============================================================================
@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'doctor')
    search_fields = ('code', 'name', 'doctor__username')
    list_filter = ('doctor',)

@admin.register(Group)
class GroupAdmin(admin.ModelAdmin):
    list_display = ('name', 'course')
    search_fields = ('name', 'course__name')
    list_filter = ('course',)

# ==============================================================================
# 3. Student Admin (The Final Fix)
# ==============================================================================
class StudentUploadForm(forms.ModelForm):
    upload_excel = forms.FileField(
        required=False, 
        label='Upload Students via Excel/CSV',
        help_text='Required columns: Student ID, Student Name, Group Name, Course Codes.'
    )

    class Meta:
        model = Student
        fields = ('university_id', 'name', 'image', 'gpa', 'groups')
    
    def clean(self):
        cleaned_data = super().clean()
        excel_file = cleaned_data.get('upload_excel')

        if excel_file:
            # تنظيف الأخطاء للسماح بالرفع الجماعي
            self._errors.pop('university_id', None)
            self._errors.pop('name', None)
            return cleaned_data

        if not cleaned_data.get('university_id') and not self.instance.pk:
            self.add_error('university_id', 'This field is required for individual entry.')
        return cleaned_data

@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    form = StudentUploadForm
    list_display = ('university_id', 'name', 'display_face_status', 'display_courses', 'display_groups', 'gpa')
    search_fields = ('university_id', 'name')
    list_filter = ('groups__course', 'groups')
    filter_horizontal = ('groups',)

    fieldsets = (
        ('Bulk Student Upload', {'fields': ('upload_excel',)}),
        ('Individual Student Data', {'fields': ('university_id', 'name', 'image', 'face_id', 'gpa', 'groups')}), 
    )
    readonly_fields = ('face_id',)

    def display_face_status(self, obj):
        if obj.image:
            return format_html('<img src="{}" style="width: 30px; height: 30px; border-radius: 4px; object-fit: cover;" />', obj.image.url)
        return format_html('<span style="color: #999;">No Image</span>')

    def display_groups(self, obj):
        if not obj.pk: return "-"
        return ", ".join(sorted([g.name for g in obj.groups.all()]))

    def display_courses(self, obj):
        if not obj.pk: return "-"
        courses = set([g.course.code for g in obj.groups.all()])
        return format_html('<strong>{}</strong>', ", ".join(sorted(list(courses)))) if courses else "-"

    def save_model(self, request, obj, form, change):
        excel_file = form.cleaned_data.get('upload_excel')
        if excel_file:
            try:
                file_content = BytesIO(excel_file.read())
                df = pd.read_csv(file_content) if excel_file.name.lower().endswith('.csv') else pd.read_excel(file_content, engine='openpyxl')
                df.columns = df.columns.str.lower().str.replace(' ', '').str.strip()
                
                with transaction.atomic():
                    for _, row in df.iterrows():
                        sid = str(row['studentid']).strip()
                        sname = str(row['studentname']).strip()
                        gname = str(row['groupname']).strip()
                        ccodes = str(row['coursecodes']).strip()
                        gpa = float(row['gpa']) if 'gpa' in df.columns and pd.notna(row['gpa']) else None
                        
                        if not sid or sid == 'nan': continue
                        
                        student, _ = Student.objects.update_or_create(
                            university_id=sid, 
                            defaults={'name': sname, 'gpa': gpa}
                        )
                        
                        if gname and ccodes:
                            for code in [c.strip() for c in ccodes.split(',')]:
                                try:
                                    course = Course.objects.get(code__iexact=code)
                                    group, _ = Group.objects.get_or_create(
                                        name__iexact=gname, course=course,
                                        defaults={'name': gname, 'course': course}
                                    )
                                    student.groups.add(group)
                                except Course.DoesNotExist: continue
                
                messages.success(request, 'تم الرفع الجماعي بنجاح.')
                self._bulk_done = True
                return 
            except Exception as e:
                messages.error(request, f'Error: {e}')
                return
        super().save_model(request, obj, form, change)

    # الحل النهائي لمنع الـ ValueError عند حفظ العلاقات
    def save_related(self, request, form, formsets, change):
        if hasattr(self, '_bulk_done'):
            return 
        super().save_related(request, form, formsets, change)

    def response_add(self, request, obj, post_url_continue=None):
        if hasattr(self, '_bulk_done'):
            return HttpResponseRedirect(reverse('admin:doctors_student_changelist'))
        return super().response_add(request, obj, post_url_continue)

    def response_change(self, request, obj):
        if hasattr(self, '_bulk_done'):
            return HttpResponseRedirect(reverse('admin:doctors_student_changelist'))
        return super().response_change(request, obj)

# ==============================================================================
# 4. Attendance & Lecture Admin
# ==============================================================================
@admin.register(AttendanceRecord)
class AttendanceRecordAdmin(admin.ModelAdmin):
    list_display = ('student', 'lecture', 'status', 'timestamp')
    list_filter = ('status', 'lecture__course', 'lecture__group')
    search_fields = ('student__name', 'student__university_id')
    form = forms.modelform_factory(AttendanceRecord, fields='__all__', widgets={'student': autocomplete.ModelSelect2(url='student_autocomplete')})

@admin.register(Lecture)
class LectureAdmin(admin.ModelAdmin):
    list_display = ('course', 'group', 'date_time')
    list_filter = ('course', 'group')
    form = forms.modelform_factory(Lecture, fields='__all__', widgets={'group': autocomplete.ModelSelect2(url='group_autocomplete', forward=['course'])})