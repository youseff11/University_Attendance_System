# doctors/api_views.py
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from django.shortcuts import get_object_or_404
from django.db.models import Q
from .models import Student, DoctorProfile, Announcement, Course
from .serializers import StudentProfileSerializer, AnnouncementSerializer

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

        serializer = StudentProfileSerializer(student)
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