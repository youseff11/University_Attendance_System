# doctors/models.py

from django.contrib.auth.models import AbstractUser
from django.db import models

## 1. Defining Roles (UserRole)
class UserRole(models.TextChoices):
    ADMIN = 'ADMIN', 'Admin'
    DOCTOR = 'DOCTOR', 'Doctor'

## 2. Custom User Model (DoctorProfile)
class DoctorProfile(AbstractUser):
    role = models.CharField(
        max_length=10,
        choices=UserRole.choices,
        default=UserRole.DOCTOR,
        verbose_name="Role/Permission"
    )

    def is_admin(self):
        return self.role == UserRole.ADMIN
    
    def is_doctor(self):
        return self.role == UserRole.DOCTOR

    class Meta:
        verbose_name = 'System User'
        verbose_name_plural = 'System Users'

# ---

## 3. Course Model
class Course(models.Model):
    name = models.CharField(max_length=100, verbose_name="Course Name")
    code = models.CharField(max_length=20, unique=True, verbose_name="Course Code")
    
    # Link course to doctor
    doctor = models.ForeignKey(
        DoctorProfile, 
        on_delete=models.CASCADE,
        limit_choices_to={'role': UserRole.DOCTOR}, 
        related_name='courses_taught', 
        verbose_name="Responsible Doctor"
    )

    def __str__(self):
        return f"{self.code} - {self.name}"

    class Meta:
        verbose_name = 'Course'
        verbose_name_plural = 'Courses'
        unique_together = ('code', 'doctor')

# ---

## 4. Group Model
class Group(models.Model):
    name = models.CharField(max_length=50, verbose_name="Group Name (e.g., Group A, Section 1)")
    course = models.ForeignKey(
        Course, 
        on_delete=models.CASCADE, 
        related_name='groups', 
        verbose_name="Affiliated Course"
    )

    def __str__(self):
        return f"{self.course.code} - {self.name}"

    class Meta:
        verbose_name = 'Study Group'
        verbose_name_plural = 'Study Groups'
        unique_together = ('name', 'course')

# ---

## 5. Student Model
class Student(models.Model):
    name = models.CharField(
        max_length=150,
        verbose_name="Student Name",
        blank=True  # ← بقت اختيارية
    )

    university_id = models.CharField(
        max_length=50,
        unique=True,
        verbose_name="University ID",
        blank=True  # ← بقت اختيارية
    )
    
    groups = models.ManyToManyField(
        Group,
        related_name='students',
        verbose_name="Enrolled Groups",
        blank=True  # ← لازم تبقى optional
    )

    gpa = models.DecimalField(
        max_digits=3,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Grade Point Average (GPA)"
    )

    def __str__(self):
        return f"{self.university_id} - {self.name}"

    class Meta:
        verbose_name = 'Student'
        verbose_name_plural = 'Students'

# ---

## 6. Lecture Model (تم تصحيح related_name)
class Lecture(models.Model):
    course = models.ForeignKey(
        Course, 
        on_delete=models.CASCADE, 
        related_name='lectures', # الاسم الصحيح للوصول من Course
        verbose_name="Course"
    )
    group = models.ForeignKey(
        Group, 
        on_delete=models.CASCADE, 
        related_name='group_lectures', # <--- تم التعديل هنا لتجنب التعارض
        verbose_name="Group"
    )
    date_time = models.DateTimeField(verbose_name="Lecture Date and Time")
    topic = models.CharField(max_length=200, default='Unspecified Topic', verbose_name="Lecture Topic") # إضافة حقل Topic الذي استخدمته في views.py

    def __str__(self):
        return f"Lecture: {self.course.code} ({self.group.name}) - {self.date_time.strftime('%Y-%m-%d %H:%M')}"

    class Meta:
        verbose_name = 'Lecture Session'
        verbose_name_plural = 'Lecture Sessions'
        ordering = ['-date_time']

# ---

## 7. Attendance Record Status
class AttendanceStatus(models.TextChoices):
    PRESENT = 'P', 'Present'
    ABSENT = 'A', 'Absent'
    LATE = 'L', 'Late'
    EXCUSED = 'E', 'Excused'

## 8. AttendanceRecord Model
class AttendanceRecord(models.Model):
    lecture = models.ForeignKey(
        Lecture, 
        on_delete=models.CASCADE, 
        related_name='attendance_records', 
        verbose_name="Lecture"
    )
    student = models.ForeignKey(
        Student, 
        on_delete=models.CASCADE, 
        related_name='attendance_records', 
        verbose_name="Student"
    )
    status = models.CharField(
        max_length=1,
        choices=AttendanceStatus.choices,
        default=AttendanceStatus.ABSENT,
        verbose_name="Status"
    )
    timestamp = models.DateTimeField(auto_now_add=True, verbose_name="Actual Recording Time")

    def __str__(self):
        return f"{self.student.name} - {self.status} in {self.lecture.course.code} on {self.lecture.date_time.date()}"

    class Meta:
        verbose_name = 'Attendance Record'
        verbose_name_plural = 'Attendance Records'
        unique_together = ('lecture', 'student')