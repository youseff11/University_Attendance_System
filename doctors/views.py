# Doctors/Views
import io
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import models
from django.http import JsonResponse
from dal import autocomplete 
from .models import Course, Group, Student, Lecture, UserRole, AttendanceStatus, AttendanceRecord
from datetime import datetime
import pandas as pd
from io import BytesIO
from django.db.models import Count, Q, F 
import json
import base64
import boto3
from django.conf import settings
from django.core.files.base import ContentFile
from django.shortcuts import get_object_or_404
from django.http import HttpResponse
from django.template.loader import get_template
from xhtml2pdf import pisa
from .models import Lecture
# ==============================================
# 0. دوال مساعدة (Helper Functions)
# ==============================================

def is_doctor(user):
    return user.is_authenticated and user.role == UserRole.DOCTOR

def _annotate_student_warnings(students_queryset, warning_threshold):
    students_queryset = students_queryset.annotate(
        total_absences=Count(
            'attendance_records',
            filter=Q(attendance_records__status=AttendanceStatus.ABSENT) 
        )
    )
    return students_queryset

# دالة للاتصال بـ AWS (Reusable Client)
def get_rekognition_client():
    return boto3.client(
        'rekognition',
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        region_name=settings.AWS_REGION_NAME
    )

# ==============================================
# 1. دوال Autocomplete (DAL Views)
# ==============================================

class GroupAutocomplete(autocomplete.Select2QuerySetView):
    def get_queryset(self):
        if not self.request.user.is_authenticated:
            return Group.objects.none()
        qs = Group.objects.all()
        course_id = None
        if self.forwarded:
            course_id = self.forwarded.get('course')            
        if course_id:
            qs = qs.filter(course_id=course_id)
        else:
            if not self.request.user.is_superuser:
                 return Group.objects.none()        
        if self.q:
            qs = qs.filter(name__icontains=self.q)
        if self.request.user.role == UserRole.DOCTOR and not course_id:
            qs = qs.filter(course__doctor=self.request.user)            
        return qs

class StudentAutocomplete(autocomplete.Select2QuerySetView):
    def get_queryset(self):
        if not self.request.user.is_authenticated:
            return Student.objects.none()
        qs = Student.objects.all()
        if self.forwarded:
            lecture_id = self.forwarded.get('lecture')            
            if lecture_id:
                try:
                    lecture = Lecture.objects.get(pk=lecture_id)
                    group_id = lecture.group.id
                    qs = qs.filter(groups__id=group_id)
                except Lecture.DoesNotExist:
                    return Student.objects.none()
        if self.q:
            qs = qs.filter(Q(name__icontains=self.q) | Q(university_id__icontains=self.q))
        return qs


# ==============================================
# 2. دوال لوحة التحكم (Dashboard)
# ==============================================

@login_required
def doctor_dashboard(request):
    if not is_doctor(request.user):
        messages.error(request, 'You do not have permission to access this page.')
        return redirect('login') 
    courses = Course.objects.filter(doctor=request.user)
    num_courses = courses.count()    
    warning_threshold = 3    
    warnings_list = []
    students_with_absences = Student.objects.filter(groups__course__in=courses).distinct().annotate(
        total_absences_overall=Count(
            'attendance_records', 
            filter=Q(attendance_records__status=AttendanceStatus.ABSENT, attendance_records__lecture__course__in=courses)
        )
    )

    for student in students_with_absences:
        student_warning_details = []
        for course in courses:
            absences_in_course = student.attendance_records.filter(
                lecture__course=course, 
                status=AttendanceStatus.ABSENT
            ).count()
            
            if absences_in_course >= warning_threshold:
                student_warning_details.append({
                    'course_name': course.name,
                    'course_code': course.code,
                    'absences': absences_in_course
                })
        
        if student_warning_details: 
             warnings_list.append({
                'name': student.name,
                'university_id': student.university_id,
                'total_absences': student.total_absences_overall, 
                'warning_courses': student_warning_details
            })

    last_lecture = Lecture.objects.filter(course__in=courses).order_by('-date_time').first()

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
    if not is_doctor(request.user):
        messages.error(request, 'Access Denied.')
        return redirect('dashboard')
    course = get_object_or_404(Course, pk=course_id, doctor=request.user)
    groups = course.groups.all().annotate(student_count=models.Count('students')) 
    context = {'course': course, 'groups': groups}
    return render(request, 'doctors/group_list.html', context)


@login_required
def student_upload_excel(request, group_id):
    if not is_doctor(request.user):
        messages.error(request, 'Access Denied.')
        return redirect('dashboard')    
    group = get_object_or_404(Group, pk=group_id, course__doctor=request.user)
    
    if request.method == 'POST':
        if 'excel_file' in request.FILES:
            excel_file = request.FILES['excel_file']
            
            if not excel_file.name.lower().endswith(('.xlsx', '.xls', '.csv')):
                messages.error(request, 'Invalid file format. Please upload an Excel (.xlsx/.xls) or CSV file.')
                return render(request, 'doctors/student_upload.html', {'group': group})
            try:
                if excel_file.name.lower().endswith('.csv'):
                    df = pd.read_csv(BytesIO(excel_file.read()))
                else:
                    df = pd.read_excel(BytesIO(excel_file.read()), engine='openpyxl')
                df.columns = df.columns.str.strip().str.title()
                required_cols = ['Student Id', 'Student Name']
                if not all(col in df.columns for col in required_cols):
                    messages.error(request, 'Missing required columns. Ensure the column headers are "Student ID" and "Student Name".')
                    return render(request, 'doctors/student_upload.html', {'group': group})
                new_students_count = 0
                linked_students_count = 0
                updated_gpa_count = 0
                for index, row in df.iterrows():
                    student_id = str(row['Student Id']).strip()
                    student_name = str(row['Student Name']).strip()
                    
                    gpa_value = None
                    if 'Gpa' in df.columns and pd.notna(row['Gpa']):
                        try:
                            gpa_value = float(row['Gpa'])
                        except ValueError:
                            gpa_value = None                    
                    if not student_id or not student_name:
                        continue
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
    if not is_doctor(request.user):
        messages.error(request, 'Access Denied.')
        return redirect('dashboard')
    
    courses = Course.objects.filter(doctor=request.user).prefetch_related('groups')
    
    context = {'courses': courses}
    return render(request, 'doctors/attendance_select_group.html', context)


@login_required
def take_attendance(request, group_id):
    if not is_doctor(request.user):
        messages.error(request, 'Access Denied.')
        return redirect('dashboard')
    group = get_object_or_404(Group, pk=group_id, course__doctor=request.user)
    if request.method == 'POST':
        lecture_topic = request.POST.get('lecture_topic', 'Unspecified Topic')
        if 'attendance_file' in request.FILES:
            attendance_file = request.FILES['attendance_file']
            try:
                lecture = Lecture.objects.create(
                    course=group.course,
                    group=group,
                    topic=lecture_topic,
                    date_time=datetime.now()
                )
                attended_ids = set()
                file_content = attendance_file.read().decode('utf-8')
                if attendance_file.name.lower().endswith('.csv'):
                    df = pd.read_csv(BytesIO(file_content.encode('utf-8')))
                    id_col = next((col for col in df.columns if 'id' in col.lower()), None)
                    if id_col:
                        attended_ids = {str(id).strip() for id in df[id_col].dropna()}
                else: # ملف نصي (TXT)
                    attended_ids = {line.strip() for line in file_content.splitlines() if line.strip()}
                group_students = group.students.all()
                present_count = 0
                for student in group_students:
                    is_present = student.university_id in attended_ids
                    AttendanceRecord.objects.create(
                        lecture=lecture,
                        student=student,
                        status=AttendanceStatus.PRESENT if is_present else AttendanceStatus.ABSENT 
                    )
                    if is_present:
                        present_count += 1
                abs_count = group_students.count() - present_count
                messages.success(request, f'Attendance recorded. Present: {present_count}, Absent: {abs_count}.')
                return redirect('dashboard')

            except Exception as e:
                messages.error(request, f'Error: {e}')
        else:
            messages.error(request, 'Please select a file.')

    context = {'group': group}
    return render(request, 'doctors/take_attendance.html', context)

# ----------------------------------------------
# ميزة بصمة الوجه الجديدة (Face Recognition Add-on)
# ----------------------------------------------

@login_required
def face_attendance_check(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            image_data = data.get('image')
            group_id = data.get('group_id')
            lecture_topic = data.get('lecture_topic', 'Unspecified Topic') 
            format, imgstr = image_data.split(';base64,')
            image_file = ContentFile(base64.b64decode(imgstr))
            client = get_rekognition_client()
            response = client.search_faces_by_image(
                CollectionId='smart_attendance_collection',
                Image={'Bytes': image_file.read()},
                MaxFaces=1,
                FaceMatchThreshold=85
            )
            if response['FaceMatches']:
                u_id = response['FaceMatches'][0]['Face']['ExternalImageId']
                student = get_object_or_404(Student, university_id=u_id)
                group = get_object_or_404(Group, id=group_id)

                from django.utils import timezone
                today = timezone.now().date()
                lecture, created = Lecture.objects.get_or_create(
                    group=group,
                    course=group.course,
                    date_time__date=today,
                    topic=lecture_topic,
                    defaults={
                        'date_time': timezone.now()
                    }
                )
                if created:
                    all_students = group.students.all()
                    attendance_records = []
                    for s in all_students:
                        attendance_records.append(AttendanceRecord(
                            lecture=lecture,
                            student=s,
                            status=AttendanceStatus.ABSENT 
                        ))
                    AttendanceRecord.objects.bulk_create(attendance_records)
                AttendanceRecord.objects.update_or_create(
                    lecture=lecture,
                    student=student,
                    defaults={'status': AttendanceStatus.PRESENT}
                )

                return JsonResponse({
                    'success': True, 
                    'student_name': student.name,
                    'university_id': student.university_id,
                    'image_url': student.image.url if student.image else ''
                })
            
            return JsonResponse({'success': False, 'message': 'وجه غير معروف'})
        except Exception as e:
            import traceback
            print(traceback.format_exc()) 
            return JsonResponse({'success': False, 'message': f'حدث خطأ: {str(e)}'})
            
    return JsonResponse({'success': False, 'message': 'طلب غير صالح'})

@login_required
def index_students_to_aws(request):
    client = get_rekognition_client()
    try:
        client.create_collection(CollectionId='smart_attendance_collection')
    except:
        pass

    students = Student.objects.exclude(image='')
    success_count = 0
    for student in students:
        try:
            with open(student.image.path, 'rb') as img:
                client.index_faces(
                    CollectionId='smart_attendance_collection',
                    Image={'Bytes': img.read()},
                    ExternalImageId=str(student.university_id),
                    MaxFaces=1
                )
                success_count += 1
        except Exception:
            continue
            
    messages.success(request, f"تمت مزامنة {success_count} طالب مع نظام بصمة الوجه.")
    return redirect('dashboard')


# ==============================================
# 5. دوال التقارير (Reports Views)
# ==============================================

@login_required
def report_home(request):
    if not is_doctor(request.user):
        messages.error(request, 'Access Denied.')
        return redirect('dashboard')
    courses = Course.objects.filter(doctor=request.user).prefetch_related('groups')
    context = {'courses': courses}
    return render(request, 'doctors/report_home.html', context)

@login_required
def course_report(request, course_id):
    if not is_doctor(request.user):
        messages.error(request, 'Access Denied.')
        return redirect('dashboard')    
    course = get_object_or_404(Course, pk=course_id, doctor=request.user)    
    total_lectures = course.lectures.count() 
    student_data = []
    students_in_course = Student.objects.filter(groups__course=course).distinct()
    for student in students_in_course:
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
    if not is_doctor(request.user):
        messages.error(request, 'Access Denied.')
        return redirect('dashboard')
    warning_threshold = 3
    search_query = request.GET.get('query', '').strip()
    searched_student = None
    students_qs = Student.objects.all().order_by('name')
    final_student_list = []
    if search_query:
        specific_student = students_qs.filter(university_id=search_query).first()
        if specific_student:
            searched_student = specific_student
            enrolled_courses = Course.objects.filter(groups__students=searched_student).distinct()
            searched_student.enrolled_courses = enrolled_courses
            warning_courses = []
            total_absences_overall = 0
            all_course_absences = []
            for course in enrolled_courses:
                absences_in_course = searched_student.attendance_records.filter(
                    lecture__course=course,
                    status=AttendanceStatus.ABSENT 
                ).count()
                
                total_absences_overall += absences_in_course
                
                if absences_in_course > 0: 
                    all_course_absences.append({
                        'course_name': course.name,
                        'course_code': course.code,
                        'absences': absences_in_course,
                        'is_warning': absences_in_course >= warning_threshold
                    })
                
                if absences_in_course >= warning_threshold:
                    warning_courses.append({
                        'course_name': course.name,
                        'course_code': course.code,
                        'absences': absences_in_course
                    })

            searched_student.total_absences = total_absences_overall
            searched_student.all_course_absences = all_course_absences
            
            if len(warning_courses) > 1:
                searched_student.warning_status_text = f"High Risk ({len(warning_courses)} Courses)"
            elif len(warning_courses) == 1:
                searched_student.warning_status_text = f"High Risk ({warning_courses[0]['absences']} Absences in {warning_courses[0]['course_code']})"
            else:
                searched_student.warning_status_text = "Safe (0)"

            searched_student.has_warning = len(warning_courses) > 0
            searched_student.warning_courses = warning_courses

            final_student_list = [searched_student]
            
        else:
            students_qs = students_qs.filter(
                Q(name__icontains=search_query) | Q(university_id__icontains=search_query)
            )
            if not students_qs.exists():
                messages.warning(request, f'No students found matching "{search_query}".')
            
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
            
    else:
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

    context = {
        'students': final_student_list,
        'search_query': search_query,
        'searched_student': searched_student,
        'warning_threshold': warning_threshold, 
    }
    
    return render(request, 'doctors/student_search.html', context)

@login_required
def group_student_list(request, group_id):
    group = get_object_or_404(Group, id=group_id, course__doctor=request.user)
    warning_threshold = 3
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
    if not is_doctor(request.user):
        messages.error(request, 'Access Denied.')
        return redirect('dashboard')    
    from django.contrib.auth import get_user_model
    User = get_user_model() 
    related_name = 'courses_taught' 
    
    doctors = User.objects.filter(role=UserRole.DOCTOR).order_by('username').annotate(
        course_count=Count(related_name) 
    ).prefetch_related(
        models.Prefetch(
            related_name, 
            queryset=Course.objects.all().order_by('name').annotate(
                groups_count=Count('groups') 
            ),
            to_attr='taught_courses' 
        )
    )
    context = {
        'doctors': doctors,
    }
    return render(request, 'doctors/doctor_list.html', context)

@login_required
def update_profile_image(request):
    if request.method == 'POST' and request.FILES.get('new_image'):
        user = request.user 
        try:
            user.image = request.FILES['new_image']
            user.save()
            messages.success(request, "تم تحديث الصورة الشخصية بنجاح!")
        except Exception as e:
            messages.error(request, f"حدث خطأ أثناء الحفظ: {str(e)}")
    return redirect('dashboard')

@login_required
def update_schedule_image(request):
    if request.method == 'POST' and request.FILES.get('schedule_image'):
        user = request.user
        new_schedule = request.FILES.get('schedule_image')
        if not new_schedule.content_type.startswith('image/'):
            messages.error(request, "Please upload a valid image file.")
            return redirect('doctor_dashboard')
        user.schedule_image = new_schedule
        user.save()
        messages.success(request, "Academic Schedule has been synced successfully!")
        return redirect('doctor_dashboard')
    messages.error(request, "No image selected.")
    return redirect('doctor_dashboard')
    
def export_attendance_pdf(request, lecture_id):
    lecture = get_object_or_404(Lecture, id=lecture_id)
    attendance_records = lecture.attendance_records.all()
    html_string = f"""
    <html>
    <head>
        <meta charset="UTF-8">
        <style>
            body {{ font-family: sans-serif; padding: 20px; }}
            h2 {{ text-align: center; color: #333; }}
            table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
            th, td {{ border: 1px solid #ddd; padding: 10px; text-align: left; }}
            th {{ background-color: #f4f4f4; }}
            .present {{ color: green; font-weight: bold; }}
            .absent {{ color: red; font-weight: bold; }}
        </style>
    </head>
    <body>
        <h2>Attendance Report</h2>
        <p><strong>Course:</strong> {lecture.course.name}</p>
        <p><strong>Lecture:</strong> {lecture.topic or 'Regular Lecture'}</p>
        <p><strong>Date:</strong> {lecture.date_time.strftime('%Y-%m-%d %H:%M')}</p>
        <p><strong>Group:</strong> {lecture.group.name}</p>
        
        <table>
            <thead>
                <tr>
                    <th>Student Name</th>
                    <th>ID</th>
                    <th>Status</th>
                </tr>
            </thead>
            <tbody>
    """    
    for record in attendance_records:
        status_text = "Present" if record.status in ['P', 'Present'] else "Absent"
        status_class = "present" if record.status in ['P', 'Present'] else "absent"
        
        html_string += f"""
            <tr>
                <td>{record.student.name}</td>
                <td>{record.student.university_id}</td>
                <td class="{status_class}">{status_text}</td>
            </tr>
        """
        
    html_string += """
            </tbody>
        </table>
    </body>
    </html>
    """
    result = io.BytesIO()
    pdf = pisa.pisaDocument(io.BytesIO(html_string.encode("UTF-8")), result)
    
    if not pdf.err:
        response = HttpResponse(result.getvalue(), content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="Attendance_{lecture.id}.pdf"'
        return response
    
    return HttpResponse("Error generating PDF", status=400)