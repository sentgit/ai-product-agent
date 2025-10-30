from http.server import HTTPServer, SimpleHTTPRequestHandler
import os
import sys
from pathlib import Path

class CORSRequestHandler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization, X-Session-Id')
        self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate')
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

    def log_message(self, format, *args):
        sys.stdout.write("%s - - [%s] %s\n" %
                         (self.address_string(),
                          self.log_date_time_string(),
                          format % args))

def run_server(port=8000, directory=None):
    if directory:
        os.chdir(directory)
    
    server_address = ('', port)
    httpd = HTTPServer(server_address, CORSRequestHandler)
    
    print(f"\n{'='*60}")
    print(f"🚀 SKF Product Assistant UI Server")
    print(f"{'='*60}")
    print(f"\n✅ Server running at: http://localhost:{port}")
    print(f"📁 Serving files from: {os.getcwd()}")
    print(f"\n📖 Instructions:")
    print(f"   1. Open http://localhost:{port}/agent_ui.html in your browser")
    print(f"   2. Make sure your Azure Function is running (func start)")
    print(f"   3. Enter API endpoint in the UI (e.g., http://localhost:7071/api/chat)")
    print(f"\n⏹️  Press Ctrl+C to stop the server")
    print(f"{'='*60}\n")
    
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n\n🛑 Server stopped")
        httpd.server_close()

if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Run HTTP server for SKF Product Assistant UI')
    parser.add_argument('-p', '--port', type=int, default=8000, help='Port to run server on (default: 8000)')
    parser.add_argument('-d', '--directory', type=str, help='Directory to serve files from (default: current directory)')
    
    args = parser.parse_args()
    
    if args.directory and not Path(args.directory).exists():
        print(f"❌ Error: Directory '{args.directory}' does not exist")
        sys.exit(1)
    
    run_server(port=args.port, directory=args.directory)