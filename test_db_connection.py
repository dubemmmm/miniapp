# test_db_connection.py
import os
import django

# Setup Django (replace 'your_project' with your actual project name)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'miniapp.settings')  # or whatever your project is called
django.setup()

from django.db import connection
from django.conf import settings

def test_database_connection():
    try:
        print(f"Attempting to connect to: {settings.DATABASES['default']['HOST']}")
        print(f"Database: {settings.DATABASES['default']['NAME']}")
        print(f"User: {settings.DATABASES['default']['USER']}")
        
        # Test the connection
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            result = cursor.fetchone()
            
        if result:
            print("✅ Database connection successful!")
            return True
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        return False

if __name__ == "__main__":
    test_database_connection()