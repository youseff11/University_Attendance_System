import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = 'django-insecure-kh(^24qgd()sqjc3-ndj#cb$4-uyy(dj1w&bvsyan6qz33+j@0'

DEBUG = True

ALLOWED_HOSTS = ["*"]

# Application definition
INSTALLED_APPS = [
    # Jazzmin must be before admin
    'jazzmin', 
    
    'dal',
    'dal_select2',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    
    # Custom Apps
    'doctors',
    'rest_framework',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'core.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [os.path.join(BASE_DIR, 'templates')],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'core.wsgi.application'

# Database
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# Regional Settings
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Africa/Cairo'
USE_I18N = True
USE_TZ = True

# Static files
STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [os.path.join(BASE_DIR, 'static')] if os.path.exists(os.path.join(BASE_DIR, 'static')) else []

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
AUTH_USER_MODEL = 'doctors.DoctorProfile'

LOGIN_URL = '/login/' 
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = 'login'

# ==============================================================================
# JAZZMIN SETTINGS (Professional Dashboard Config)
# ==============================================================================
JAZZMIN_SETTINGS = {
    "site_title": "AMS Admin",
    "site_header": "Attendance System",
    "site_brand": "Smart Attendance",
    "site_logo": None,
    "welcome_sign": "Welcome to Attendance Management System",
    "copyright": "Smart Attendance Ltd",
    "search_model": ["doctors.DoctorProfile", "doctors.Course"],
    "user_avatar": "image",
    
    # Top Menu Links
    "topmenu_links": [
        {"name": "Home",  "url": "admin:index", "permissions": ["auth.view_user"]},
        # زر العودة للموقع الرئيسي
        {"name": "View Site", "url": "/", "new_window": False, "icon": "fas fa-eye"},
        {"name": "Support", "url": "https://github.com/yourproject", "new_window": True},
    ],

    # Side Menu Config
    "show_sidebar": True,
    "navigation_expanded": True,
    "hide_apps": [],
    "hide_models": [],
    
    # تحسين الأيقونات لتكون أكثر عصرية ووضوحاً
    "icons": {
        "auth": "fas fa-shield-alt",
        "auth.Group": "fas fa-users-cog",
        "doctors.DoctorProfile": "fas fa-user-tie",
        "doctors.Course": "fas fa-graduation-cap",
        "doctors.Attendance": "fas fa-clipboard-check",
        "doctors.Student": "fas fa-user-graduate",
        "doctors.StudyGroup": "fas fa-layer-group",
        "doctors.LectureSession": "fas fa-chalkboard-teacher",
        "doctors.AttendanceRecord": "fas fa-id-badge",
    },
    
    "default_icon_parents": "fas fa-folder",
    "default_icon_children": "fas fa-file-alt",
    
    # UI Customizer
    "show_ui_builder": False, 
}

JAZZMIN_UI_TWEAKS = {
    "navbar_small_text": False,
    "footer_small_text": False,
    "body_small_text": False,
    "brand_small_text": False,
    "brand_colour": "navbar-dark",
    "accent": "accent-primary",
    "navbar": "navbar-primary navbar-dark",
    "no_navbar_border": False,
    "navbar_fixed": True,
    "layout_boxed": False,
    "footer_fixed": False,
    "sidebar_fixed": True,
    "sidebar": "sidebar-dark-primary",
    "sidebar_nav_small_text": False,
    "sidebar_disable_expand": False,
    "sidebar_nav_child_indent": True,
    "sidebar_nav_compact_style": False,
    "sidebar_nav_legacy_style": False,
    "sidebar_nav_flat_style": False,
    "theme": "flatly",  # ثيم "Flatly" يعطي مظهر أنيق واحترافي
    "dark_mode_theme": None,
    "button_classes": {
        "primary": "btn-primary",
        "secondary": "btn-secondary",
        "info": "btn-info",
        "warning": "btn-warning",
        "danger": "btn-danger",
        "success": "btn-success"
    }
}

# ==============================================================================
# MEDIA FILES (Uploads Config)
# ==============================================================================

# الرابط الذي سيستخدم في المتصفح للوصول للصور
MEDIA_URL = '/media/'

# المجلد الفعلي الذي ستخزن فيه الصور داخل المشروع
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')


AWS_ACCESS_KEY_ID = os.environ.get('AWS_ACCESS_KEY_ID')
AWS_SECRET_ACCESS_KEY = os.environ.get('AWS_SECRET_ACCESS_KEY')
# 