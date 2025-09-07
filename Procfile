web: gunicorn --config gunicorn.conf.py miniapp.wsgi
release: ./manage.py migrate --no-input
worker: celery -A miniapp worker --loglevel=info