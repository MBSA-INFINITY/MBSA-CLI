# cli.py

import click
import socketio
import requests
import logging

# --- Basic Configuration ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
log = logging.getLogger(__name__)

# --- Socket.IO Client Initialization ---
sio = socketio.Client(logger=False, engineio_logger=False)

# --- Server Configuration ---
MBSA_SERVER = 'http://mbsa.in'

# --- CLI Command Structure ---
@click.group()
def cli():
    """mbsa - Expose your local servers to the internet."""
    pass

@cli.command()
@click.argument('port', type=int)
def expose(port):
    """
    Exposes a local port to a public URL.

    PORT: The port number of your local server (e.g., 3000).
    """
    
    @sio.event
    def connect():
        log.info(f"Connection established with {MBSA_SERVER}. Requesting tunnel for port {port}...")
        sio.emit('start_tunnel', {'port': port})

    @sio.event
    def disconnect():
        log.info(f"Disconnected from {MBSA_SERVER}. Reconnecting...")

    @sio.on('tunnel_created')
    def on_tunnel_created(data):
        public_url = data['url']
        print("-" * 60)
        print(f"  Public URL: {public_url}")
        print(f"  Forwarding traffic to -> http://localhost:{port}")
        print("-" * 60)
        print("Press Ctrl+C to stop.")

    @sio.on('forward_request')
    def forward_request(data):
        request_id = data['request_id']
        log.info(f"[{request_id}] Received request for {data['method']} {data['path']}")

        try:
            response = requests.request(
                method=data['method'],
                url=f"http://localhost:{port}{data['path']}",
                headers={k: v for k, v in data['headers'].items() if k.lower() != 'host'},
                data=data.get('body'),
                timeout=29
            )
            log.info(f"[{request_id}] Got local response: {response.status_code}")

            excluded_headers = ['content-encoding', 'content-length', 'transfer-encoding', 'connection']
            forward_headers = {
                key: value for key, value in response.headers.items()
                if key.lower() not in excluded_headers
            }

            # --- THE CRITICAL FIX ---
            # Use `response.content` to pass through the raw bytes of the file,
            # instead of `response.text` which can corrupt non-text files.
            sio.emit('forward_response', {
                'response_body': response.content,
                'response_headers': forward_headers,
                'status_code': response.status_code,
                'request_id': request_id
            })
            # --- END OF FIX ---

        except requests.exceptions.RequestException as e:
            log.error(f"[{request_id}] Could not connect to localhost:{port}. Please ensure your local server is running.")
            sio.emit('forward_response', {
                'response_body': f"<h1>502 Bad Gateway</h1><p>mbsa.in could not connect to your local server on port {port}.</p><p>Error: {e}</p>",
                'status_code': 502,
                'request_id': request_id
            })

    # --- Main Connection Logic ---
    try:
        log.info(f"Connecting to {MBSA_SERVER}...")
        sio.connect(MBSA_SERVER, transports=['websocket'])
        sio.wait()
    except socketio.exceptions.ConnectionError:
        log.error(f"Fatal: Could not connect to the server at {MBSA_SERVER}.")
    except Exception as e:
        log.error(f"An unexpected error occurred: {e}")
    finally:
        log.info("CLI tool shutting down.")

if __name__ == '__main__':
    cli()