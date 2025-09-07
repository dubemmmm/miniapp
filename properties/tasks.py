from celery import shared_task
from django.core.files.base import ContentFile
import requests

@shared_task
def download_file_task(model_instance, url, field_name, filename_prefix):
    try:
        response = requests.get(url, timeout=30, stream=True)
        response.raise_for_status()
        content = response.content
        filename = f"{filename_prefix}_{model_instance.slug}.jpg" if 'image' in field_name else f"{filename_prefix}_{model_instance.slug}.pdf"
        setattr(model_instance, field_name, ContentFile(content, name=filename))
        model_instance.save()
        print(f"📎 Downloaded {field_name} for {model_instance.name}")
    except requests.RequestException as e:
        print(f"⚠️ Failed to download {field_name} for {model_instance.name}: {e}")

@shared_task
def download_image_task(image_obj, image_url):
    try:
        response = requests.get(image_url, timeout=30, stream=True)
        response.raise_for_status()
        content = response.content
        filename = f"image_{image_obj.property.slug}_{image_obj.order}.jpg"
        image_obj.image.save(filename, ContentFile(content), save=False)
        image_obj.save()
        print(f"🖼️ Downloaded image for {image_obj.property.name}")
    except requests.RequestException as e:
        print(f"⚠️ Failed to download image: {e}")