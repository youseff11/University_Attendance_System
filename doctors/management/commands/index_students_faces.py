import environ
import boto3
from django.core.management.base import BaseCommand
from doctors.models import Student

# تهيئة مكتبة environ لقراءة المتغيرات
env = environ.Env()
environ.Env.read_env() # تقرأ ملف .env تلقائياً

class Command(BaseCommand):
    help = 'Indexes student faces using AWS Rekognition'

    def handle(self, *args, **options):
        # استدعاء المتغيرات بأمان
        client = boto3.client(
            'rekognition',
            aws_access_key_id=env('AWS_ACCESS_KEY_ID'),
            aws_secret_access_key=env('AWS_SECRET_ACCESS_KEY'),
            region_name=env('AWS_REGION_NAME', default='eu-west-1')
        )

        collection_id = 'smart_attendance_collection'

        try:
            client.create_collection(CollectionId=collection_id)
            self.stdout.write(self.style.SUCCESS(f"Collection '{collection_id}' created."))
        except client.exceptions.ResourceAlreadyExistsException:
            pass

        all_students = Student.objects.all()
        batch_size = 10

        for i in range(0, len(all_students), batch_size):
            batch = all_students[i:i + batch_size]
            for student in batch:
                if student.image and hasattr(student.image, 'path'):
                    try:
                        with open(student.image.path, 'rb') as image_file:
                            response = client.index_faces(
                                CollectionId=collection_id,
                                Image={'Bytes': image_file.read()},
                                ExternalImageId=str(student.university_id),
                                MaxFaces=1,
                                QualityFilter="AUTO"
                            )
                            
                            if response['FaceRecords']:
                                aws_face_id = response['FaceRecords'][0]['Face']['FaceId']
                                student.face_id = aws_face_id
                                student.save()
                                self.stdout.write(self.style.SUCCESS(f"✅ {student.name} - FaceId: {aws_face_id}"))
                            else:
                                self.stdout.write(self.style.WARNING(f"⚠️ {student.name}: No face detected in image."))
                                
                    except Exception as e:
                        self.stdout.write(self.style.ERROR(f"❌ {student.name} : {e}"))
                else:
                    self.stdout.write(f"⏩ {student.name}: No Image Found")