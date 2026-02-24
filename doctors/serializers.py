# doctors/serializers.py

from rest_framework import serializers
from django.db.models import Count, Q 
from .models import Student, AttendanceRecord, Course, Lecture, Group, AttendanceStatus

# --- ثابت حد الإنذار (WARNING_THRESHOLD)
WARNING_THRESHOLD = 3 # حد الإنذار: 3 غيابات

# --- 1. AttendanceRecord Serializer
class AttendanceRecordSerializer(serializers.ModelSerializer):
    lecture_topic = serializers.ReadOnlyField(source='lecture.topic')
    lecture_date = serializers.DateTimeField(source='lecture.date_time', format="%Y-%m-%d %H:%M")
    course_name = serializers.ReadOnlyField(source='lecture.course.name')
    course_code = serializers.ReadOnlyField(source='lecture.course.code')
    group_name = serializers.ReadOnlyField(source='lecture.group.name')
    status_text = serializers.SerializerMethodField()

    class Meta:
        model = AttendanceRecord
        fields = ('id', 'lecture_topic', 'lecture_date', 'course_name', 'course_code', 'group_name', 'status', 'status_text', 'timestamp')

    def get_status_text(self, obj):
        return obj.get_status_display()

# --- 2. StudentProfile Serializer (المحدث)
class StudentProfileSerializer(serializers.ModelSerializer):
    groups_info = serializers.SerializerMethodField()
    recent_attendance = serializers.SerializerMethodField()
    
    # 🚀 حقول الإنذار الجديدة
    is_under_warning = serializers.SerializerMethodField()
    warning_courses_details = serializers.SerializerMethodField() 

    class Meta:
        model = Student
        # إضافة الحقول الجديدة
        fields = ('id', 'name', 'university_id', 'gpa', 'groups_info', 'recent_attendance', 'is_under_warning', 'warning_courses_details')

    # دالة مساعدة لحساب الغيابات وتفاصيل الإنذار
    def _get_warning_details(self, obj):
        """حساب الغيابات في كل مقرر ومقارنتها بحد الإنذار."""
        warning_details = []
        
        # تجميع الغيابات حسب المقرر. يفترض أن رمز الغياب هو 'A' (Absent)
        absence_counts = obj.attendance_records.filter(
            Q(status='A')
        ).values(
            'lecture__course__code', 
            'lecture__course__name'
        ).annotate(
            absences_count=Count('lecture__course__code')
        )
        
        # مقارنة كل مقرر بحد الإنذار
        for item in absence_counts:
            if item['absences_count'] >= WARNING_THRESHOLD:
                warning_details.append({
                    'course_code': item['lecture__course__code'],
                    'course_name': item['lecture__course__name'],
                    'absences_count': item['absences_count'],
                    'threshold': WARNING_THRESHOLD,
                })
        
        return warning_details

    # 🚀 Serializer Method Field: هل يوجد إنذار؟
    def get_is_under_warning(self, obj):
        warning_details = self._get_warning_details(obj)
        return len(warning_details) > 0

    # 🚀 Serializer Method Field: تفاصيل المقررات التي بها إنذار
    def get_warning_courses_details(self, obj):
        return self._get_warning_details(obj)
        
    # دوال existing
    def get_groups_info(self, obj):
        groups_list = []
        for group in obj.groups.all():
            groups_list.append({
                'group_name': group.name,
                'course_name': group.course.name,
                'course_code': group.course.code,
            })
        return groups_list

    def get_recent_attendance(self, obj):
        recent_records = obj.attendance_records.all().order_by('-lecture__date_time')[:20]
        return AttendanceRecordSerializer(recent_records, many=True).data