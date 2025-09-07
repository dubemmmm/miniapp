# gunicorn.conf.py
bind = '0.0.0.0:8000'  # Bind to all interfaces, port 8000
workers = 1           # Use 1 worker for low memory (512 MB Droplet)
timeout = 120         # Increase timeout to 120 seconds for sync tasks
loglevel = 'info'     # Log level for debugging
accesslog = '-'       # Log access to stdout
errorlog = '-'        # Log errors to stdout