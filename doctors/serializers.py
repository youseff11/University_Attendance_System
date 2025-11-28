# doctors/serializers.py
from rest_framework import serializers
from .models import Student, AttendanceRecord, Course, Lecture, Group, AttendanceStatus

# --- 1. Serializer للحالة التفصيلية للحضور في محاضرة واحدة
class AttendanceRecordSerializer(serializers.ModelSerializer):
    lecture_topic = serializers.ReadOnlyField(source='lecture.topic')
    lecture_date = serializers.DateTimeField(source='lecture.date_time', format="%Y-%m-%d %H:%M")
    course_name = serializers.ReadOnlyField(source='lecture.course.name')
    course_code = serializers.ReadOnlyField(source='lecture.course.code')
    group_name = serializers.ReadOnlyField(source='lecture.group.name')
    status_text = serializers.SerializerMethodField()

    class Meta:
        model = AttendanceRecord
        # لا نحتاج 'student' لأنه محدد سلفاً عند الاستعلام
        fields = ('id', 'lecture_topic', 'lecture_date', 'course_name', 'course_code', 'group_name', 'status', 'status_text', 'timestamp')

    def get_status_text(self, obj):
        # لتحويل الكود 'P' إلى 'Present' للعرض
        return obj.get_status_display()

# --- 2. Serializer لملف تعريف الطالب (Student Profile)
class StudentProfileSerializer(serializers.ModelSerializer):
    # جلب تفاصيل مجموعات الطالب
    groups_info = serializers.SerializerMethodField()
    # جلب إجمالي سجلات الحضور الأخيرة للطالب (مثلاً آخر 20 سجل)
    recent_attendance = serializers.SerializerMethodField()

    class Meta:
        model = Student
        fields = ('id', 'name', 'university_id', 'gpa', 'groups_info', 'recent_attendance')
        # لا تعرض جميع الحقول إذا كانت حساسة، لكن هذه هي الأساسية المطلوبة

    def get_groups_info(self, obj):
        # إرجاع قائمة بالمقررات والمجموعات المسجل بها الطالب
        groups_list = []
        for group in obj.groups.all():
            groups_list.append({
                'group_name': group.name,
                'course_name': group.course.name,
                'course_code': group.course.code,
            })
        return groups_list

    def get_recent_attendance(self, obj):
        # جلب آخر 20 سجل حضور وغياب للطالب
        recent_records = obj.attendance_records.all().order_by('-lecture__date_time')[:20]
        # استخدام AttendanceRecordSerializer لتحويل السجلات إلى JSON
        return AttendanceRecordSerializer(recent_records, many=True).data