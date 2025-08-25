# Server Commands
> `gunicorn --worker-class eventlet -w 1 --bind 127.0.0.1:5000 --limit-request-line 0 --limit-request-fields 32768 server:app`

# CLI Commands
> `mbsa expose <port-number>`