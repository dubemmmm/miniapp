from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('properties', '0007_propertyprogress_propertyprogressimage_and_more'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='PropertyFavorite',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('property', models.ForeignKey(on_delete=models.deletion.CASCADE, related_name='favourited_by', to='properties.property')),
                ('user', models.ForeignKey(on_delete=models.deletion.CASCADE, related_name='favourite_properties', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_at'],
                'unique_together': {('user', 'property')},
                'indexes': [
                    models.Index(fields=['user'], name='properties_fav_user_idx'),
                    models.Index(fields=['property'], name='properties_fav_prop_idx'),
                ],
            },
        ),
    ]
