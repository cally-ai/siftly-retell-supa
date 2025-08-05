# Gunicorn configuration file
import multiprocessing
import os

# Environment-specific worker configuration
if os.getenv('RENDER'):
    # Render environment - optimize for cost
    if os.getenv('RENDER_PLAN') == 'free':
        # Free tier - conservative settings
        workers = 2  # Reduced from 4 to fit in 512MB
        worker_connections = 100  # Reduced connection pool
        timeout = 30  # Shorter timeout
    elif os.getenv('RENDER_PLAN') == 'starter':
        # Starter plan ($7/month) - 512MB RAM, 0.5 CPU
        workers = 2  # Respect 0.5 CPU limit (2 workers × 0.25 CPU each)
        worker_connections = 200  # Moderate connection pool
        timeout = 45  # Balanced timeout
    else:
        # Standard+ plans - more resources available
        workers = 4
        worker_connections = 500
        timeout = 60
else:
    # Local development
    cpu_count = multiprocessing.cpu_count()
    workers = min(cpu_count * 2 + 1, 8)

# Worker class - use gevent for better async handling
worker_class = 'gevent'

# Maximum requests per worker before restart
max_requests = 1000
max_requests_jitter = 50

# Timeout settings
if os.getenv('RENDER_PLAN') == 'free':
    timeout = 30
    keepalive = 2
elif os.getenv('RENDER_PLAN') == 'starter':
    timeout = 45
    keepalive = 3
else:
    timeout = 60
    keepalive = 5

# Logging
accesslog = '-'
errorlog = '-'
loglevel = 'info'

# Process naming
proc_name = 'siftly'

# Bind address
bind = '0.0.0.0:10000'

# Preload app for better performance
preload_app = True

# Worker lifecycle
graceful_timeout = 30
worker_exit_on_app_exit = True

# Memory management
max_requests_jitter = 50

# Connection pooling
backlog = 2048 