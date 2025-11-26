# في ملف doctors/admin.py
import pandas as pd
from io import BytesIO
from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin
from django import forms
from dal import autocomplete 
from django.db import transaction
from django.core.exceptions import ValidationError
from .models import DoctorProfile, Course, Group, Student ,Lecture, AttendanceRecord, AttendanceStatus


# 1. Doctor Profile Admin
class DoctorProfileAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + ((None, {'fields': ('role',)}),)
    list_display = ('username', 'email', 'first_name', 'last_name', 'is_staff', 'role')
    list_filter = ('is_staff', 'is_superuser', 'is_active', 'groups', 'role')
admin.site.register(DoctorProfile, DoctorProfileAdmin)


# 2. Course Admin
@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'doctor')
    search_fields = ('code', 'name', 'doctor__username')
    list_filter = ('doctor',)


# 3. Group Admin
@admin.register(Group)
class GroupAdmin(admin.ModelAdmin):
    list_display = ('name', 'course')
    search_fields = ('name', 'course__name')
    list_filter = ('course',)


# 4. Student Upload Form (Custom Form)
class StudentUploadForm(forms.ModelForm):
    upload_excel = forms.FileField(
        required=False, 
        label='Upload Students via Excel/CSV',
        help_text='Upload an Excel or CSV file with columns: Student ID, Student Name, Group Name, Course Codes (comma-separated), GPA (optional).'
    )

    class Meta:
        model = Student
        fields = ('university_id', 'name', 'gpa', 'groups')
    
    # 💥 (التعديل الذي يسمح بتجاوز الحقول المطلوبة عند رفع ملف)
    def clean(self):
        cleaned_data = super().clean()
        excel_file = cleaned_data.get('upload_excel')

        # لو فيه ملف Excel ← تجاهل التحقق من باقي الحقول
        if excel_file:
            # تفريغ الحقول الفردية عشان Django ما يحاولش يحفظها
            cleaned_data['university_id'] = None
            cleaned_data['name'] = None
            cleaned_data['gpa'] = None
            cleaned_data['groups'] = []

            # مهم: نشيل أي errors اتضافت قبل كده
            self._errors.pop('university_id', None)
            self._errors.pop('name', None)
            self._errors.pop('gpa', None)
            return cleaned_data

        # لو مفيش Excel ← يبقى الإضافة فردية ولازم الحقول تكون موجودة
        if not cleaned_data.get('university_id'):
            self.add_error('university_id', 'This field is required for individual entry.')

        if not cleaned_data.get('name'):
            self.add_error('name', 'This field is required for individual entry.')

        return cleaned_data


try:
    admin.site.unregister(Student)
except admin.sites.NotRegistered:
    pass

# 5. Student Admin
@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    form = StudentUploadForm
    list_display = ('university_id', 'name', 'gpa', 'display_groups', 'display_courses')
    search_fields = ('university_id', 'name')
    
    # 💥 (التعديل الذي يحل مشكلة الاختيار المتعدد وظهور الحقل بشكل أفضل)
    filter_horizontal = ('groups',)

    fieldsets = (
        ('Bulk Student Upload', {'fields': ('upload_excel',), 'description': 'Ensure openpyxl is installed to read Excel files.'}),
        ('Individual Student Details', {'fields': ('university_id', 'name', 'gpa', 'groups')}), 
    )

    def display_groups(self, obj):
        # 🟢 (التعديل الذي يمنع تكرار اسم الجروب باستخدام set)
        group_names = set([group.name for group in obj.groups.all()])
        return ", ".join(sorted(list(group_names)))
    display_groups.short_description = 'Groups'

    def display_courses(self, obj):
        course_codes = set()
        for group in obj.groups.all():
            if group.course:
                course_codes.add(group.course.code)
        return ", ".join(course_codes)
    display_courses.short_description = 'Courses'
    
    
    def save_model(self, request, obj, form, change):
        excel_file = form.cleaned_data.get('upload_excel')
        
        # 1. Handle Bulk Upload
        if excel_file:
            try:
                file_content = BytesIO(excel_file.read())
                df = pd.read_csv(file_content) if excel_file.name.lower().endswith('.csv') else pd.read_excel(file_content, engine='openpyxl')
                df.columns = df.columns.str.lower().str.replace(' ', '').str.strip()
                
                required_cols = ['studentid', 'studentname', 'groupname', 'coursecodes']
                if not all(col in df.columns for col in required_cols):
                    raise ValidationError(
                        'Missing required columns. File must contain "Student ID", "Student Name", "Group Name", and "Course Codes".'
                    )

                new_students_count = 0
                updated_gpa_count = 0
                
                with transaction.atomic():
                    for index, row in df.iterrows():
                        student_id = str(row['studentid']).strip()
                        student_name = str(row['studentname']).strip()
                        group_name = str(row['groupname']).strip()
                        course_codes_string = str(row['coursecodes']).strip()
                        
                        gpa_value = float(row['gpa']) if 'gpa' in df.columns and pd.notna(row['gpa']) else None
                        
                        if not student_id or not student_name:
                            continue

                        student, created = Student.objects.get_or_create(
                            university_id=student_id,
                            defaults={'name': student_name, 'gpa': gpa_value}
                        )
                        
                        is_updated = False
                        if not created:
                            if student.name != student_name:
                                student.name = student_name
                                is_updated = True
                            if gpa_value is not None and student.gpa != gpa_value:
                                student.gpa = gpa_value
                                is_updated = True
                                updated_gpa_count += 1
                            if is_updated:
                                student.save()
                                
                        if created:
                            new_students_count += 1

                        if group_name and course_codes_string:
                            course_codes_list = [code.strip() for code in course_codes_string.split(',') if code.strip()]

                            for code in course_codes_list:
                                try:
                                    course = Course.objects.get(code__iexact=code)
                                except Course.DoesNotExist:
                                    continue
                                
                                group, _ = Group.objects.get_or_create(
                                    name__iexact=group_name,
                                    course=course,
                                    defaults={'name': group_name, 'course': course}
                                )
                                student.groups.add(group)
                            
                        
                messages.success(request, f'Successfully processed {len(df)} records. Added {new_students_count} new students and updated GPA for {updated_gpa_count} students, and linked them to groups based on the Excel data.')
                
                # العودة مباشرة لمنع سير العمل القياسي لـ Admin
                return 

            except Exception as e:
                self.message_user(request, f'Error during file processing: {e}', level=messages.ERROR)
                return 

        # 2. Handle Single Student Creation/Update
        super().save_model(request, obj, form, change)
    
    # 💥 (التعديل الذي يمنع الـ ValueError في حالة الرفع بالجملة)
    def save_related(self, request, form, formsets, change):
        excel_file = form.cleaned_data.get('upload_excel')
        
        # إذا كان هناك ملف Excel، نتجاوز حفظ العلاقات لمنع الـ ValueError
        if excel_file:
            return 
        
        # إذا كانت عملية حفظ يدوية (فردية)، نُكمل حفظ العلاقات
        super().save_related(request, form, formsets, change)


# 6. Attendance Record Admin
class AttendanceRecordAdminForm(forms.ModelForm):
    class Meta:
        model = AttendanceRecord
        fields = '__all__'
        widgets = {
            'student': autocomplete.ModelSelect2(url='student_autocomplete', forward=['lecture'])
        }

@admin.register(AttendanceRecord)
class AttendanceRecordAdmin(admin.ModelAdmin):
    list_display = ('student', 'lecture', 'status', 'timestamp')
    list_filter = ('status', 'lecture__course', 'lecture__group', 'lecture__date_time')
    search_fields = ('student__name', 'student__university_id', 'lecture__course__code')
    form = AttendanceRecordAdminForm


# 7. Lecture Admin
class LectureAdminForm(forms.ModelForm):
    class Meta:
        model = Lecture
        fields = '__all__'
        widgets = {
            'group': autocomplete.ModelSelect2(url='group_autocomplete', forward=['course'])
        }

@admin.register(Lecture)
class LectureAdmin(admin.ModelAdmin):
    list_display = ('course', 'group', 'date_time')
    list_filter = ('course', 'group')
    date_hierarchy = 'date_time'
    search_fields = ('course__name', 'group__name')
    form = LectureAdminForm