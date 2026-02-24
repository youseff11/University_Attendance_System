# doctors/api_views.py
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from django.shortcuts import get_object_or_404
from .models import Student
from .serializers import StudentProfileSerializer

# ⚠️ ملاحظة: هذا مجرد مثال. في بيئة العمل الحقيقية، ستحتاج إلى نظام مصادقة آمن (مثل Token Auth)
# Django REST Framework يُسهّل عليك استخدام Token Authentication.

# --- 1. مصادقة وتسجيل الدخول (Login - يتطلب المزيد من الإعداد لـ DRF)
# لتبسيط العملية الآن، سنفترض أن الطالب يُرسل الـ university_id كمعرف له

class StudentProfileView(APIView):
    # ⚠️ في الواقع، يجب استخدام permissions.IsAuthenticated
    permission_classes = [permissions.AllowAny] 
    
    def get(self, request, university_id, format=None):
        """
        جلب بيانات بروفايل الطالب عن طريق university_id.
        مثال: /api/student/profile/123456/
        """
        try:
            # يجب أن يكون university_id حقل فريد (Unique) ليعمل البحث بشكل صحيح
            student = Student.objects.get(university_id=university_id)
        except Student.DoesNotExist:
            return Response(
                {"detail": "Student not found or Invalid ID."},
                status=status.HTTP_404_NOT_FOUND
            )

        # 🎯 استخدم السيريالايزر لتحويل البيانات
        serializer = StudentProfileSerializer(student)
        return Response(serializer.data, status=status.HTTP_200_OK)