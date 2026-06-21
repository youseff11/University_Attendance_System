# doctors/api_views.py
import os
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser, FormParser
from django.shortcuts import get_object_or_404
from django.db.models import Q, Count
from .models import Student, DoctorProfile, Announcement, Course
from .serializers import (
    StudentProfileSerializer,
    AnnouncementSerializer,
    AttendanceRecordSerializer,
)
from .serializers import WARNING_THRESHOLD

class StudentProfileView(APIView):
    permission_classes = [permissions.AllowAny] 
    
    def get(self, request, university_id, format=None):
        """
        جلب بيانات بروفايل الطالب عن طريق university_id.
        مثال: /api/student/profile/123456/
        """
        try:
            student = Student.objects.get(university_id=university_id)
        except Student.DoesNotExist:
            return Response(
                {"detail": "Student not found or Invalid ID."},
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = StudentProfileSerializer(student, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)


class StudentAnnouncementsView(APIView):
    """
    خاص بتطبيق الـ Flutter: جلب الإعلانات الخاصة بالدكاترة المسجل معهم الطالب فقط
    مسار الـ API: /api/student/announcements/123456/
    """
    permission_classes = [permissions.AllowAny]
    
    def get(self, request, university_id, format=None):
        try:
            student = Student.objects.get(university_id=university_id)
        except Student.DoesNotExist:
            return Response(
                {"detail": "Student not found."},
                status=status.HTTP_404_NOT_FOUND
            )
            
        # 🎯 اللوجيك الصحيح بناءً على علاقات الموديلز في مشروعك:
        # بنجيب المقررات اللي الطالب مسجل في مجموعاتها، ومنها بنطلع بالدكاترة المشرفين عليها
        registered_courses = Course.objects.filter(groups__students=student).distinct()
        
        # بنجيب الدكاترة المشرفين على هذه المقررات
        # ملاحظة: الـ related_name الصحيح على حقل doctor في موديل Course هو 'courses_taught'
        doctors = DoctorProfile.objects.filter(courses_taught__in=registered_courses).distinct()
        
        # بنجيب الإعلانات الخاصة بالدكاترة دول بس والأحدث أولاً
        announcements = Announcement.objects.filter(doctor__in=doctors).order_by('-created_at')
        
        # نمرر الـ context عشان روابط الصور والملفات تطلع كاملة بالـ IP والـ Port
        serializer = AnnouncementSerializer(announcements, many=True, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)

class StudentFullAttendanceView(APIView):
    """
    Returns the FULL attendance history for a student (not just the last 20).
    Optional query params:
        ?course=<course_code>  -> filter by course
        ?status=<P|A|L|E>      -> filter by status

    Example: /api/student/full-attendance/22010123/?status=A
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request, university_id, format=None):
        try:
            student = Student.objects.get(university_id=university_id)
        except Student.DoesNotExist:
            return Response(
                {"detail": "Student not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        qs = student.attendance_records.all().order_by('-lecture__date_time')

        course_filter = request.query_params.get('course')
        status_filter = request.query_params.get('status')
        if course_filter:
            qs = qs.filter(lecture__course__code=course_filter)
        if status_filter:
            qs = qs.filter(status=status_filter.upper())

        serializer = AttendanceRecordSerializer(qs, many=True)
        return Response({
            'count': qs.count(),
            'results': serializer.data,
        }, status=status.HTTP_200_OK)


class StudentStatisticsView(APIView):
    """
    Returns aggregated attendance statistics per course for the student,
    plus overall counts. The Flutter app can use this to draw charts
    without doing client-side aggregation.

    Example: /api/student/statistics/22010123/
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request, university_id, format=None):
        try:
            student = Student.objects.get(university_id=university_id)
        except Student.DoesNotExist:
            return Response(
                {"detail": "Student not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        records = student.attendance_records.all()

        # Overall counters
        total = records.count()
        present = records.filter(status='P').count()
        absent = records.filter(status='A').count()
        late = records.filter(status='L').count()
        excused = records.filter(status='E').count()
        attended = present + late
        attendance_rate = round((attended / total) * 100, 2) if total else 0.0

        # Per-course breakdown
        per_course = []
        course_codes = records.values_list(
            'lecture__course__code', flat=True
        ).distinct()
        for code in course_codes:
            sub = records.filter(lecture__course__code=code)
            sub_total = sub.count()
            sub_present = sub.filter(status='P').count()
            sub_absent = sub.filter(status='A').count()
            sub_late = sub.filter(status='L').count()
            sub_excused = sub.filter(status='E').count()
            sub_attended = sub_present + sub_late
            sub_rate = round((sub_attended / sub_total) * 100, 2) if sub_total else 0.0
            course = sub.first().lecture.course
            per_course.append({
                'course_code': code,
                'course_name': course.name,
                'total_lectures': sub_total,
                'present': sub_present,
                'absent': sub_absent,
                'late': sub_late,
                'excused': sub_excused,
                'attendance_rate': sub_rate,
                'is_at_risk': sub_absent >= WARNING_THRESHOLD,
            })

        return Response({
            'university_id': university_id,
            'overall': {
                'total_lectures': total,
                'attended': attended,
                'present': present,
                'absent': absent,
                'late': late,
                'excused': excused,
                'attendance_rate': attendance_rate,
            },
            'warning_threshold': WARNING_THRESHOLD,
            'per_course': per_course,
        }, status=status.HTTP_200_OK)


class StudentProfilePictureUploadView(APIView):
    """
    رفع/تحديث صورة البروفايل الخاصة بالطالب من تطبيق الفلاتر.
    مسار الـ API: POST /api/student/profile-picture/<university_id>/
    الفورم فيلد المطلوب: profile_picture (multipart/form-data)
    """
    permission_classes = [permissions.AllowAny]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, university_id, format=None):
        try:
            student = Student.objects.get(university_id=university_id)
        except Student.DoesNotExist:
            return Response(
                {"detail": "Student not found."},
                status=status.HTTP_404_NOT_FOUND
            )

        image_file = request.FILES.get('profile_picture')
        if not image_file:
            return Response(
                {"detail": "No image file provided. Use the 'profile_picture' form field."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # بعض الأجهزة/المكتبات ما بترسلش content_type سليم، فبنرجع كمان نتأكد من الامتداد
        content_type = (image_file.content_type or '')
        filename = (image_file.name or '').lower()
        allowed_extensions = ('.jpg', '.jpeg', '.png', '.webp', '.heic', '.heif', '.gif')
        is_valid_type = content_type.startswith('image/') or filename.endswith(allowed_extensions)

        if not is_valid_type:
            return Response(
                {"detail": "Invalid file type. Please upload an image."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # حذف الصورة القديمة من السيرفر لو موجودة قبل ما نحفظ الجديدة
        if student.profile_picture:
            try:
                if os.path.isfile(student.profile_picture.path):
                    os.remove(student.profile_picture.path)
            except Exception:
                pass

        student.profile_picture = image_file
        student.save()

        serializer = StudentProfileSerializer(student, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)


class ApiHealthCheckView(APIView):
    """Simple liveness probe for monitoring / Flutter offline detection."""
    permission_classes = [permissions.AllowAny]

    def get(self, request, format=None):
        return Response({'status': 'ok', 'service': 'academic-portal-api'})