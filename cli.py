import click
import socketio
import requests
import logging

# Enable logging for debugging
logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

# Standard Python socketio client
sio = socketio.Client(logger=True, engineio_logger=True)

# Replace with your server's domain
MBSA_SERVER = 'http://localhost:5000'

@click.group()
def cli():
    pass

@cli.command()
@click.argument('port', type=int)
def expose(port):
    """
    Exposes a local port to a public URL.
    """
    # --- Event handlers are now defined INSIDE expose ---
    # This gives them access to the 'port' variable and keeps the session self-contained.

    @sio.event
    def connect():
        log.info("Connection established with mbsa.in. Requesting tunnel...")
        sio.emit('start_tunnel', {'port': port})

    @sio.event
    def disconnect():
        log.info("Disconnected from mbsa.in")

    @sio.on('tunnel_created')
    def on_tunnel_created(data):
        public_url = data['url']
        # This f-string will now work correctly!
        print("-" * 50)
        print(f"Public URL: {public_url}")
        print(f"Forwarding traffic to -> http://localhost:{port}")
        print("-" * 50)

    @sio.on('forward_request')
    def forward_request(data):
        request_id = data['request_id']
        log.info(f"[{request_id}] Received request to forward to local port {port}")

        try:
            log.info(f"[{request_id}] Making request to http://localhost:{port}{data['path']}")
            response = requests.request(
                method=data['method'],
                url=f"http://localhost:{port}/mbsa",
                headers={k: v for k, v in data['headers'].items() if k.lower() != 'host'},
                data=data.get('body'),
                timeout=29  # Timeout slightly less than server's timeout
            )
            log.info(f"[{request_id}] Got local response with status {response.status_code}")

            sio.emit('forward_response', {
                'response_body': response.text,
                'response_headers': dict(response.headers),
                'status_code': response.status_code,
                'request_id': request_id
            })
            log.info(f"[{request_id}] Sent response back to server")

        except requests.exceptions.RequestException as e:
            log.error(f"[{request_id}] Could not connect to localhost:{port}. Error: {e}")
            sio.emit('forward_response', {
                'response_body': f"<h1>Error</h1><p>mbsa.in could not connect to your local server on port {port}.</p><p>Please ensure your local server is running.</p>",
                'status_code': 502, # Bad Gateway
                'request_id': request_id
            })

    try:
        sio.connect(MBSA_SERVER, transports=['websocket'])
        sio.wait()
    except socketio.exceptions.ConnectionError as e:
        log.error(f"Could not connect to the mbsa.in server: {e}")
    except Exception as e:
        log.error(f"An unexpected error occurred: {e}")
    finally:
        log.info("CLI tool shutting down.")

if __name__ == '__main__':
    cli()