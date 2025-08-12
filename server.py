from flask import Flask, request, Response
from flask_socketio import SocketIO, emit
import random
import string
import threading
import logging

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app, logger=True, engineio_logger=True, ping_timeout=20, ping_interval=10)

tunnels = {}
responses = {}
response_events = {}

def generate_random_string(length=8):
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))

@app.route('/<path:subpath>', methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH'])
def proxy(subpath):
    full_path = f"/{subpath}"
    log.info(f"Received request for path: {full_path}")
    if full_path in tunnels:
        client_sid = tunnels[full_path]['sid']
        local_port = tunnels[full_path]['port']
        request_id = generate_random_string(16)
        response_events[request_id] = threading.Event()

        log.info(f"[{request_id}] Forwarding request to client {client_sid}")
        socketio.emit('forward_request', {
            'path': request.full_path,
            'method': request.method,
            'headers': dict(request.headers),
            'body': request.get_data().decode('utf-8', 'ignore'),
            'local_port': local_port,
            'request_id': request_id
        }, to=client_sid)

        log.info(f"[{request_id}] Waiting for response from client...")
        if response_events[request_id].wait(timeout=30):
            log.info(f"[{request_id}] Response received from client.")
            response_data = responses.pop(request_id)
            del response_events[request_id]
            return Response(
                response_data['response_body'],
                status=response_data['status_code'],
                headers=response_data['response_headers']
            )
        else:
            log.warning(f"[{request_id}] Request timed out waiting for client response.")
            del response_events[request_id]
            return "Request timed out.", 504

    return "This mbsa.in URL is not active.", 404

@socketio.on('connect')
def handle_connect():
    log.info(f"Client connected: {request.sid}")

@socketio.on('disconnect')
def handle_disconnect():
    log.info(f"Client disconnected: {request.sid}")
    for path, details in list(tunnels.items()):
        if details['sid'] == request.sid:
            del tunnels[path]
            log.info(f"Closed tunnel: {path}")

@socketio.on('start_tunnel')
def handle_start_tunnel(data):
    port = data['port']
    path = f"/{generate_random_string()}"
    tunnels[path] = {'sid': request.sid, 'port': port}
    public_url = f"http://{request.host}{path}"
    emit('tunnel_created', {'url': public_url})
    log.info(f"Created tunnel for {request.sid}: {public_url} -> http://localhost:{port}")

@socketio.on('forward_response')
def handle_forward_response(data):
    request_id = data['request_id']
    log.info(f"[{request_id}] Received forwarded response from client.")
    if request_id in response_events:
        responses[request_id] = data
        response_events[request_id].set()

if __name__ == '__main__':
    socketio.run(app, debug=True, use_reloader=False) # use_reloader=False is better for socketio dev