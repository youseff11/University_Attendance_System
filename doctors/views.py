# Doctors/Views
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import models
from django.http import JsonResponse
from dal import autocomplete # 🚨 استيراد DAL
from .models import Course, Group, Student, Lecture, UserRole, AttendanceStatus 
from datetime import datetime
import pandas as pd
from io import BytesIO
from django.db.models import Count, Q, F 

# ==============================================
# 0. دوال مساعدة (Helper Functions)
# ==============================================

def is_doctor(user):
    """Checks if the user is authenticated and has the DOCTOR role."""
    return user.is_authenticated and user.role == UserRole.DOCTOR

def _annotate_student_warnings(students_queryset, warning_threshold):
    students_queryset = students_queryset.annotate(
        total_absences=Count(
            'attendance_records',
            filter=Q(attendance_records__status=AttendanceStatus.ABSENT) 
        )
    )
    return students_queryset
    

# ==============================================
# 1. دوال Autocomplete (DAL Views)
# ==============================================

class GroupAutocomplete(autocomplete.Select2QuerySetView):
    def get_queryset(self):
        # 1. التأكد من صلاحيات المستخدم
        if not self.request.user.is_authenticated:
            return Group.objects.none()

        qs = Group.objects.all()

        # 2. التصفية الأساسية: بناءً على المقرر المختار (forwarded from Admin form)
        course_id = None
        if self.forwarded:
            course_id = self.forwarded.get('course')
            
        if course_id:
            qs = qs.filter(course_id=course_id)
        else:
            # إذا لم يتم تحديد مقرر (عند فتح النموذج لأول مرة)
            if not self.request.user.is_superuser:
                 return Group.objects.none()
        
        # 3. تصفية نتائج البحث النصي
        if self.q:
            qs = qs.filter(name__icontains=self.q)

        # 4. تصفية الدكتور (إذا لم يتم تحديد مقرر بعد)
        if self.request.user.role == UserRole.DOCTOR and not course_id:
            qs = qs.filter(course__doctor=self.request.user)
            
        return qs

class StudentAutocomplete(autocomplete.Select2QuerySetView):
    """
    View لتمكين البحث والتصفية الآلية للطلاب بناءً على المحاضرة المحددة (لتصفية طلاب المجموعة فقط).
    """
    def get_queryset(self):
        if not self.request.user.is_authenticated:
            return Student.objects.none()

        qs = Student.objects.all()

        # 1. التصفية بناءً على المحاضرة المحددة
        if self.forwarded:
            lecture_id = self.forwarded.get('lecture')
            
            if lecture_id:
                try:
                    # جلب المجموعة المرتبطة بالمحاضرة المحددة
                    lecture = Lecture.objects.get(pk=lecture_id)
                    group_id = lecture.group.id
                    
                    # تصفية الطلاب: جلب الطلاب المسجلين في هذه المجموعة (الحل لمشكلة خالد يوسف)
                    qs = qs.filter(groups__id=group_id)
                except Lecture.DoesNotExist:
                    return Student.objects.none()
        
        # 2. تصفية نتائج البحث النصي
        if self.q:
            qs = qs.filter(Q(name__icontains=self.q) | Q(university_id__icontains=self.q))

        return qs


# ==============================================
# 2. دوال لوحة التحكم (Dashboard)
# ==============================================

@login_required
def doctor_dashboard(request):
    """
    عرض لوحة تحكم الدكتور: عدد المقررات، آخر حضور مسجل، وإنذارات الغياب.
    """
    if not is_doctor(request.user):
        messages.error(request, 'You do not have permission to access this page.')
        return redirect('login') 

    # 1. جلب بيانات المقررات
    courses = Course.objects.filter(doctor=request.user)
    num_courses = courses.count()
    
    # 2. إحصائيات الإنذارات
    warning_threshold = 3
    warnings_list = []
    
    # جلب جميع الطلاب المسجلين في مقررات هذا الدكتور بشكل فريد
    students_in_all_courses = Student.objects.filter(groups__course__in=courses).distinct()
    
    for student in students_in_all_courses:
        student_warning_details = []
        total_absences_overall = 0
        
        # المرور على كل مقرر من مقررات الدكتور الحالي التي يدرسها الطالب
        for course in courses.filter(groups__students=student).distinct():
            # حساب غيابات الطالب في هذا المقرر بالتحديد
            absences_in_course = student.attendance_records.filter(
                lecture__course=course, 
                status=AttendanceStatus.ABSENT
            ).count()
            
            total_absences_overall += absences_in_course
            
            if absences_in_course >= warning_threshold:
                student_warning_details.append({
                    'course_name': course.name,
                    'course_code': course.code,
                    'absences': absences_in_course
                })
        
        # يُعرض الإنذار إذا كان الطالب واخد إنذار في أي مادة يدرسها الدكتور
        if student_warning_details: 
             warnings_list.append({
                'name': student.name,
                'university_id': student.university_id,
                'total_absences': total_absences_overall, 
                'warning_courses': student_warning_details
            })

    # 3. آخر محاضرة مسجلة
    last_lecture = Lecture.objects.filter(
        course__in=courses
    ).order_by('-date_time').first()

    context = {
        'num_courses': num_courses,
        'last_lecture': last_lecture,
        'courses': courses,
        'warnings': warnings_list, 
        'warning_threshold': warning_threshold,
    }
    
    return render(request, 'doctors/dashboard.html', context)



# ==============================================
# 3. دوال المقررات والمجموعات (Courses & Groups Views)
# ==============================================

@login_required
def course_list(request):
    """
    عرض جميع المقررات التي يدرسها الدكتور الحالي، مع إحصائية عدد الطلاب لكل مقرر.
    """
    if not is_doctor(request.user):
        messages.error(request, 'Access Denied.')
        return redirect('dashboard')
    
    courses = Course.objects.filter(doctor=request.user).prefetch_related('groups').annotate(
        total_students=Count('groups__students', distinct=True) 
    )
    
    context = {'courses': courses}
    return render(request, 'doctors/course_list.html', context)

@login_required
def group_list(request, course_id):
    """
    عرض جميع المجموعات التابعة لمقرر معين، مع إحصائية عدد الطلاب لكل مجموعة.
    """
    if not is_doctor(request.user):
        messages.error(request, 'Access Denied.')
        return redirect('dashboard')
    
    course = get_object_or_404(Course, pk=course_id, doctor=request.user)
    
    # groups هي العلاقة العكسية لـ ForeignKey في Group الذي يشير إلى Course
    groups = course.groups.all().annotate(student_count=models.Count('students')) 
    
    context = {'course': course, 'groups': groups}
    return render(request, 'doctors/group_list.html', context)


import pandas as pd
from django.db import IntegrityError
from django.shortcuts import get_object_or_404, redirect, render
from django.contrib import messages
from io import BytesIO

# تأكد من استيراد النماذج (Group, Student) والدالة المساعدة (is_doctor) من الأعلى

@login_required
def student_upload_excel(request, group_id):
    """
    معالجة رفع ملف Excel/CSV لتسجيل الطلاب وربطهم بالمجموعة المحددة.
    (تم تحسينها لمعالجة حقل GPA بشكل سليم وتحديثه للطلاب الموجودين)
    """
    if not is_doctor(request.user):
        messages.error(request, 'Access Denied.')
        return redirect('dashboard')
    
    # تأكد من أن الدكتور هو مدرس المقرر
    group = get_object_or_404(Group, pk=group_id, course__doctor=request.user)
    
    if request.method == 'POST':
        if 'excel_file' in request.FILES:
            excel_file = request.FILES['excel_file']
            
            # 1. Check file type
            if not excel_file.name.lower().endswith(('.xlsx', '.xls', '.csv')):
                messages.error(request, 'Invalid file format. Please upload an Excel (.xlsx/.xls) or CSV file.')
                return render(request, 'doctors/student_upload.html', {'group': group})

            try:
                # 2. Read the file 
                if excel_file.name.lower().endswith('.csv'):
                    df = pd.read_csv(BytesIO(excel_file.read()))
                else:
                    # يجب أن تكون مكتبة openpyxl مثبتة هنا
                    df = pd.read_excel(BytesIO(excel_file.read()), engine='openpyxl')
                
                # Normalize column names 
                df.columns = df.columns.str.strip().str.title()
                
                required_cols = ['Student Id', 'Student Name']
                if not all(col in df.columns for col in required_cols):
                    messages.error(request, 'Missing required columns. Ensure the column headers are "Student ID" and "Student Name".')
                    return render(request, 'doctors/student_upload.html', {'group': group})
                
                new_students_count = 0
                linked_students_count = 0
                updated_gpa_count = 0
                
                # 3. Process data row by row
                for index, row in df.iterrows():
                    student_id = str(row['Student Id']).strip()
                    student_name = str(row['Student Name']).strip()
                    
                    gpa_value = None
                    if 'Gpa' in df.columns and pd.notna(row['Gpa']):
                        try:
                            # 💥 تحويل القيمة إلى float صراحة لضمان التخزين السليم
                            gpa_value = float(row['Gpa'])
                        except ValueError:
                            # تجاهل GPA إذا كان غير رقمي
                            gpa_value = None
                    
                    if not student_id or not student_name:
                        continue

                    # Find or create student based on unique university_id
                    try:
                        student, created = Student.objects.get_or_create(
                            university_id=student_id,
                            defaults={
                                'name': student_name,
                                'gpa': gpa_value
                            }
                        )
                    except IntegrityError:
                        messages.warning(request, f'Skipped student with ID {student_id}: Could not create/find student due to data error.')
                        continue
                    
                    # 💥 التعديل الأهم: تحديث الاسم والـ GPA للطلاب الموجودين 
                    is_updated = False
                    if not created:
                        # تحديث الاسم إذا كان مختلفاً
                        if student.name != student_name:
                            student.name = student_name
                            is_updated = True
                            
                        # تحديث GPA إذا كانت القيمة الجديدة موجودة ومختلفة عن القديمة
                        if gpa_value is not None and student.gpa != gpa_value:
                            student.gpa = gpa_value
                            is_updated = True
                            updated_gpa_count += 1
                        
                        if is_updated:
                            student.save()
                    
                    # 4. Link student to the group
                    if created:
                        new_students_count += 1
                        
                    if not student.groups.filter(id=group.id).exists():
                        student.groups.add(group)
                        linked_students_count += 1
                        
                success_message = (
                    f'Successfully processed {len(df)} records. '
                    f'Added {new_students_count} new students '
                    f'and linked {linked_students_count} students to Group {group.name}.'
                )
                if updated_gpa_count > 0:
                     success_message += f' Updated GPA for {updated_gpa_count} existing students.'
                     
                messages.success(request, success_message)
                return redirect('group_list', course_id=group.course.id)

            except Exception as e:
                # يمكنك طباعة الخطأ الكامل في Console لسهولة التصحيح
                import traceback
                print(f"Error in student_upload_excel: {traceback.format_exc()}") 
                messages.error(request, f'An error occurred during file processing: {e}')
                
        else:
            messages.error(request, 'Please select a file to upload.')

    return render(request, 'doctors/student_upload.html', {'group': group})


# ==============================================
# 4. دوال تسجيل الحضور (Attendance Taking Views)
# ==============================================

@login_required
def select_group_for_attendance(request):
    """
    عرض قائمة المقررات والمجموعات ليختار الدكتور المجموعة لبدء تسجيل الحضور.
    """
    if not is_doctor(request.user):
        messages.error(request, 'Access Denied.')
        return redirect('dashboard')
    
    courses = Course.objects.filter(doctor=request.user).prefetch_related('groups')
    
    context = {'courses': courses}
    return render(request, 'doctors/attendance_select_group.html', context)


@login_required
def take_attendance(request, group_id):
    """
    معالجة رفع ملف الحضور (Text/CSV) وتسجيل الحضور والغياب للطلاب في المجموعة.
    """
    if not is_doctor(request.user):
        messages.error(request, 'Access Denied.')
        return redirect('dashboard')
    
    group = get_object_or_404(Group, pk=group_id, course__doctor=request.user)
    
    if request.method == 'POST':
        lecture_topic = request.POST.get('lecture_topic', 'Unspecified Topic')
        
        if 'attendance_file' in request.FILES:
            attendance_file = request.FILES['attendance_file']
            
            try:
                # 1. إنشاء سجل المحاضرة (Lecture Record)
                lecture = Lecture.objects.create(
                    course=group.course,
                    group=group, # إضافة المجموعة لتسهيل الفلترة
                    topic=lecture_topic,
                    date_time=datetime.now()
                )

                # 2. قراءة ملف الحضور
                attended_ids = set()
                file_content = attendance_file.read().decode('utf-8')
                
                if attendance_file.name.lower().endswith('.csv'):
                    df = pd.read_csv(BytesIO(file_content.encode('utf-8')))
                    id_col = next((col for col in df.columns if 'id' in col.lower()), None)
                    if id_col:
                        # تحويل الـ IDs إلى سلاسل نصية والتعامل مع القيم الفارغة
                        attended_ids = {str(id).strip() for id in df[id_col].dropna()}
                else: # ملف نصي (TXT)
                    attended_ids = {line.strip() for line in file_content.splitlines() if line.strip()}
                
                # 3. معالجة وتحديث الحضور
                group_students = group.students.all()
                present_count = 0
                
                # إنشاء سجلات حضور لكل طالب
                for student in group_students:
                    is_present = student.university_id in attended_ids
                    
                    lecture.attendance_records.create(
                        student=student,
                        status=AttendanceStatus.PRESENT if is_present else AttendanceStatus.ABSENT 
                    )
                    
                    if is_present:
                        present_count += 1

                # 4. إرسال رسالة نجاح
                absent_count = group_students.count() - present_count
                messages.success(request, f'Attendance recorded successfully for {lecture_topic} ({lecture.date_time.strftime("%Y-%m-%d %H:%M")}). Present: {present_count}, Absent: {absent_count}.')
                return redirect('dashboard')

            except Exception as e:
                messages.error(request, f'An error occurred while processing the attendance file: {e}')
                
        else:
            messages.error(request, 'Please select an attendance file to upload.')

    context = {'group': group}
    return render(request, 'doctors/take_attendance.html', context)


# ==============================================
# 5. دوال التقارير (Reports Views)
# ==============================================

@login_required
def report_home(request):
    """
    عرض قائمة المقررات التي يدرسها الدكتور ليختار المقرر الذي يريد تقريره.
    """
    if not is_doctor(request.user):
        messages.error(request, 'Access Denied.')
        return redirect('dashboard')
    
    courses = Course.objects.filter(doctor=request.user).prefetch_related('groups')
    
    context = {'courses': courses}
    return render(request, 'doctors/report_home.html', context)


@login_required
def course_report(request, course_id):
    """
    عرض تقرير مفصل لمقرر معين، يشمل ملخص حضور الطلاب ونسبة الغياب.
    """
    if not is_doctor(request.user):
        messages.error(request, 'Access Denied.')
        return redirect('dashboard')
    
    # تم إصلاح 'Course' object has no attribute 'lecture_set' باستخدام 'lectures'
    course = get_object_or_404(Course, pk=course_id, doctor=request.user)
    
    # افتراض أن related_name='lectures' في نموذج Lecture
    total_lectures = course.lectures.count() 

    # 2. إحصائيات الطلاب 
    student_data = []
    
    students_in_course = Student.objects.filter(groups__course=course).distinct()
    
    for student in students_in_course:
        # إصلاح FieldError: Cannot resolve field 'is_present' باستخدام status=AttendanceStatus.ABSENT
        absent_count = student.attendance_records.filter( 
            lecture__course=course, 
            status=AttendanceStatus.ABSENT
        ).count()
        
        attendance_percentage = (total_lectures - absent_count) / total_lectures * 100 if total_lectures > 0 else 0
        
        is_warning = absent_count >= 3
        
        student_data.append({
            'name': student.name,
            'id': student.university_id,
            'absent_count': absent_count,
            'attendance_percentage': f'{attendance_percentage:.1f}%',
            'is_warning': is_warning
        })

    student_data.sort(key=lambda x: x['absent_count'], reverse=True)

    context = {
        'course': course,
        'total_lectures': total_lectures,
        'student_data': student_data,
        'warning_threshold': 3,
    }
    
    return render(request, 'doctors/course_report.html', context)


# ==============================================
# 6. دوال الطلاب والبحث (Student Views)
# ==============================================
@login_required
def student_search(request):
    """
    عرض قائمة بجميع الطلاب والتعامل مع البحث برقم الهوية أو الاسم، وإظهار تفاصيل الإنذارات.
    """
    if not is_doctor(request.user):
        messages.error(request, 'Access Denied.')
        return redirect('dashboard')
    
    warning_threshold = 3
    search_query = request.GET.get('query', '').strip()
    searched_student = None
    
    students_qs = Student.objects.all().order_by('name')
    final_student_list = [] # قائمة الطلاب النهائية التي سيتم إرسالها للقالب

    if search_query:
        # 1. حالة البحث الدقيق برقم الهوية (ID)
        specific_student = students_qs.filter(university_id=search_query).first()
        
        if specific_student:
            searched_student = specific_student
            
            # (الكود الحالي لحساب تفاصيل الإنذار للطالب الواحد يبقى كما هو - وهو ممتاز)
            enrolled_courses = Course.objects.filter(groups__students=searched_student).distinct()
            searched_student.enrolled_courses = enrolled_courses
            
            warning_courses = []
            total_absences_overall = 0
            
            for course in enrolled_courses:
                absences_in_course = searched_student.attendance_records.filter(
                    lecture__course=course,
                    status=AttendanceStatus.ABSENT 
                ).count()
                
                total_absences_overall += absences_in_course
                
                if absences_in_course >= warning_threshold:
                    warning_courses.append({
                        'course_name': course.name,
                        'course_code': course.code,
                        'absences': absences_in_course
                    })

            searched_student.total_absences = total_absences_overall
            # التعديل هنا: تحديد ما إذا كان لديه إنذار واحد أو أكثر
            if len(warning_courses) > 1:
                searched_student.warning_status_text = f"High Risk ({len(warning_courses)} Courses)"
            elif len(warning_courses) == 1:
                searched_student.warning_status_text = f"High Risk ({warning_courses[0]['absences']} Absences in {warning_courses[0]['course_code']})"
            else:
                 searched_student.warning_status_text = "Safe (0)"

            searched_student.has_warning = len(warning_courses) > 0
            searched_student.warning_courses = warning_courses

            final_student_list = [searched_student] # عرض الطالب المحدد فقط
            
        else:
            # 2. حالة البحث بالاسم أو ID غير دقيق (عرض قائمة نتائج)
            students_qs = students_qs.filter(
                Q(name__icontains=search_query) | Q(university_id__icontains=search_query)
            )
            if not students_qs.exists():
                messages.warning(request, f'No students found matching "{search_query}".')
            
            # المرور على كل طالب في قائمة النتائج وحساب إنذاراته
            for student in students_qs:
                student_warning_details = []
                enrolled_courses = Course.objects.filter(groups__students=student).distinct()
                
                for course in enrolled_courses:
                     absences = student.attendance_records.filter(
                        lecture__course=course,
                        status=AttendanceStatus.ABSENT
                    ).count()
                    
                     if absences >= warning_threshold:
                        student_warning_details.append({
                             'absences': absences,
                             'course_code': course.code
                        })
                
                if len(student_warning_details) > 1:
                    student.warning_status_text = f"High Risk ({len(student_warning_details)} Courses)"
                    student.has_warning = True
                elif len(student_warning_details) == 1:
                    # الرقم بجانب الإنذار هو عدد الغيابات في تلك المادة
                    absences = student_warning_details[0]['absences']
                    course_code = student_warning_details[0]['course_code']
                    student.warning_status_text = f"High Risk ({absences} in {course_code})"
                    student.has_warning = True
                else:
                    student.warning_status_text = "Safe (0)"
                    student.has_warning = False

                final_student_list.append(student)
            
    else:
        # 3. عرض جميع الطلاب (في حالة عدم وجود بحث)
        for student in students_qs:
             student_warning_details = []
             enrolled_courses = Course.objects.filter(groups__students=student).distinct()
             
             for course in enrolled_courses:
                 absences = student.attendance_records.filter(
                    lecture__course=course,
                    status=AttendanceStatus.ABSENT
                ).count()
                
                 if absences >= warning_threshold:
                     student_warning_details.append({
                         'absences': absences,
                         'course_code': course.code
                     })
             
             if len(student_warning_details) > 1:
                 student.warning_status_text = f"High Risk ({len(student_warning_details)} Courses)"
                 student.has_warning = True
             elif len(student_warning_details) == 1:
                 absences = student_warning_details[0]['absences']
                 course_code = student_warning_details[0]['course_code']
                 student.warning_status_text = f"High Risk ({absences} in {course_code})"
                 student.has_warning = True
             else:
                 student.warning_status_text = "Safe (0)"
                 student.has_warning = False

             final_student_list.append(student)

    # 4. إعداد الـ Context
    context = {
        'students': final_student_list,
        'search_query': search_query,
        'searched_student': searched_student,
        'warning_threshold': warning_threshold, 
    }
    
    return render(request, 'doctors/student_search.html', context)

@login_required
def group_student_list(request, group_id):
    """
    عرض قائمة الطلاب المسجلين في مجموعة محددة، مع حالة الإنذار الخاصة بهم.
    """
    group = get_object_or_404(Group, id=group_id, course__doctor=request.user)
    
    warning_threshold = 3

    # حساب إجمالي الغيابات لكل طالب باستخدام Annotation 
    students = group.students.all().order_by('university_id').annotate(
        total_absences=Count(
            'attendance_records',
            filter=Q(attendance_records__status=AttendanceStatus.ABSENT)
        )
    )

    context = {
        'group': group,
        'students': students,
        'warning_threshold': warning_threshold, 
    }
    return render(request, 'doctors/group_student_list.html', context)

# ==============================================
# 7. دوال الأطباء (Doctor Views)
# ==============================================

@login_required
def doctor_list(request):
    """
    عرض قائمة بجميع الأطباء والمقررات التي يدرسها كل منهم.
    """
    if not is_doctor(request.user):
        messages.error(request, 'Access Denied.')
        return redirect('dashboard')
    
    # 1. جلب نموذج المستخدم
    from django.contrib.auth import get_user_model
    User = get_user_model() 

    # 2. جلب الأطباء وتجميع مقرراتهم
    # التصحيح: استخدام 'courses_taught' بدلاً من 'course' في Count و Prefetch
    
    # اسم related_name الصحيح لعلاقة Course -> Doctor هو 'courses_taught' (من قائمة Choices في الخطأ)
    related_name = 'courses_taught' 
    
    doctors = User.objects.filter(role=UserRole.DOCTOR).order_by('username').annotate(
        # 💥 التصحيح الأول: استخدام related_name الصحيح لحساب عدد المقررات
        course_count=Count(related_name) 
    ).prefetch_related(
        models.Prefetch(
            # 💥 التصحيح الثاني: استخدام related_name الصحيح في Prefetch
            related_name, 
            queryset=Course.objects.all().order_by('name').annotate(
                # جلب عدد المجموعات لكل مقرر مسبقاً
                groups_count=Count('groups') 
            ),
            to_attr='taught_courses' # لتبسيط الوصول في القالب
        )
    )
    
    context = {
        'doctors': doctors,
    }
    
    return render(request, 'doctors/doctor_list.html', context)