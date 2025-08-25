from flask import Flask, request, Response
from flask_socketio import SocketIO, emit
import random
import string
import threading
import logging

# --- Basic Configuration ---
# Set up logging to see detailed output in your terminal
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
log = logging.getLogger(__name__)

# --- Flask & SocketIO App Initialization ---
app = Flask(__name__, static_folder=None)
app.config['SECRET_KEY'] = 'a-very-secret-key-that-you-should-change'

# IMPORTANT: This setting is crucial for subdomain logic.
# For local testing, it must match the host and port you are running on.
# For production, change this to your actual domain (e.g., 'mbsa.in').
app.config['SERVER_NAME'] = 'mbsa.in'

socketio = SocketIO(app, logger=False, engineio_logger=False)

# --- In-Memory State Management ---
# In a real production app, you might replace these with a database like Redis.
tunnels = {}        # Maps a subdomain to client details: {'sub': {'sid': '...', 'port': 8000}}
responses = {}      # Temporarily stores responses from the CLI: {'request_id': {...}}
response_events = {} # Uses threading events to signal when a response arrives: {'request_id': Event()}

# --- Helper Function ---
def generate_random_string(length=7):
    """Generates a random string for subdomains or request IDs."""
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))

# --- Core HTTP Routing Logic ---
@app.route('/', defaults={'path': ''}, methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH'])
@app.route('/<path:path>', methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH'])
def proxy(path):
    """
    This is the main entry point for all HTTP traffic.
    It inspects the request's subdomain to route traffic.
    """
    # --- CORRECTED SUBDOMAIN DETECTION ---
    # Use request.host and manually strip the port. This is the most reliable method.
    host = request.host
    hostname = host.split(':')[0] # e.g., 'sicbxxh.localhost:5000' -> 'sicbxxh.localhost'

    # Get the base domain (e.g., 'localhost') from our server's configuration
    base_domain = app.config['SERVER_NAME'].split(':')[0]
    
    # Correctly identify if a valid subdomain is being used
    if hostname != base_domain and hostname.endswith('.' + base_domain):
        # Extract the subdomain part
        # e.g., 'sicbxxh.localhost'.replace('.localhost', '') -> 'sicbxxh'
        subdomain = hostname.replace('.' + base_domain, '')
    else:
        # This is a request to the base domain (e.g., localhost:5000), so show a welcome page.
        return "<h1>Welcome to mbsa.in Tunneling Service</h1><p>This is the base domain. Your tunnels will appear on randomly generated subdomains.</p>", 200
    
    log.info(f"Identified subdomain request for: '{subdomain}'")
    
    if subdomain in tunnels:
        # A client is connected for this subdomain; forward the request.
        client_sid = tunnels[subdomain]['sid']
        request_id = generate_random_string(16)
        response_events[request_id] = threading.Event()

        log.info(f"[{request_id}] Forwarding request for '{subdomain}' to client {client_sid}")
        socketio.emit('forward_request', {
            'path': request.full_path,
            'method': request.method,
            'headers': dict(request.headers),
            'body': request.get_data().decode('utf-8', 'ignore'),
            'request_id': request_id
        }, to=client_sid)

        # Wait for the client to send back a response, with a 30-second timeout
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
            del response_events[request_id] # Clean up the event
            return "<h1>504 Gateway Timeout</h1><p>The mbsa.in server did not receive a timely response from the local client.</p>", 504

    return f"<h1>404 Not Found</h1><p>The subdomain '<strong>{subdomain}</strong>' is not active or does not exist.</p>", 404

# --- WebSocket Event Handlers ---
@socketio.on('connect')
def handle_connect():
    log.info(f"Client connected: {request.sid}")

@socketio.on('disconnect')
def handle_disconnect():
    log.info(f"Client disconnected: {request.sid}")
    # Clean up any tunnels that were associated with this client
    for subdomain, details in list(tunnels.items()):
        if details['sid'] == request.sid:
            del tunnels[subdomain]
            log.info(f"Closed tunnel for subdomain: {subdomain}")
            break # A client can only have one tunnel at a time

@socketio.on('start_tunnel')
def handle_start_tunnel(data):
    """
    Handles a request from a CLI tool to create a new tunnel.
    """
    port = data.get('port', 80) # Default to port 80 if not provided
    subdomain = generate_random_string()
    
    # Ensure the generated subdomain is unique (highly unlikely to collide, but good practice)
    while subdomain in tunnels:
        subdomain = generate_random_string()

    tunnels[subdomain] = {'sid': request.sid, 'port': port}
    
    # Construct the full public URL
    base_domain = app.config['SERVER_NAME']
    public_url = f"http://{subdomain}.{base_domain}"

    # Send the public URL back to the client
    emit('tunnel_created', {'url': public_url})
    log.info(f"Created tunnel for {request.sid}: {public_url} -> http://localhost:{port}")

@socketio.on('forward_response')
def handle_forward_response(data):
    """
    Receives the HTTP response from the CLI and sends it to the waiting HTTP request.
    """
    request_id = data['request_id']
    log.info(f"[{request_id}] Received forwarded response from client.")
    if request_id in response_events:
        responses[request_id] = data
        response_events[request_id].set() # Signal that the response has arrived

# --- Main Execution ---
if __name__ == '__main__':
    log.info("Starting mbsa.in server...")
    # Use socketio.run() to correctly start the server with WebSocket support
    # use_reloader=False prevents the server from restarting on code changes, which is more stable for WebSocket dev
    socketio.run(app, host='0.0.0.0', debug=True, use_reloader=False, port=5000)