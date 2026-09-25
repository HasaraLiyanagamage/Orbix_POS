"""Windows desktop launcher shared by the ORBIX POS and IT editions."""
import os
import base64
import html
import re
import shutil
import sys
import threading
import traceback
from pathlib import Path
from http.server import ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import server


def bundled_file(name):
    return Path(getattr(sys, '_MEIPASS', Path(__file__).parent)) / name


def verify_frontend_files():
    """Stop startup with a clear message if an installer missed web assets."""
    required_files = (
        'index.html',
        'app.js',
        'enterprise.js',
        'payment-ui.js',
        'daily-report.js',
        'assets/Orbix.png',
    )
    missing = [name for name in required_files if not bundled_file(name).is_file()]
    if missing:
        raise RuntimeError(
            'The installed application is missing: ' + ', '.join(missing) +
            '. Rebuild and install the latest setup file.'
        )


def prepare_windows_data():
    """Place data on D: and migrate the earlier C: database when available."""
    if not getattr(sys, 'frozen', False):
        return
    for filename in ('orbix.db',):
        source = bundled_file(filename)
        destination = server.DATA_DIR / filename
        if destination.exists():
            continue
        legacy_source = (server.LEGACY_DATA_DIR / filename) if server.LEGACY_DATA_DIR else None
        if legacy_source and legacy_source.exists():
            # Existing shops keep all sales, customers and settings after this
            # version changes the live data location from C: to D:.
            shutil.copy2(legacy_source, destination)
        elif source.exists():
            shutil.copy2(source, destination)


def write_startup_error(error):
    """Keep the startup error where a Windows user can send it for support."""
    log_file = server.DATA_DIR / 'startup-error.log'
    log_file.write_text(traceback.format_exc(), encoding='utf-8')
    return log_file


def show_startup_error(error, log_file):
    """Show a useful Windows message instead of silently closing the app."""
    message = (
        f'{server.APP_NAME} could not start.\n\n'
        f'{error}\n\n'
        'Install Microsoft Edge WebView2 Runtime, then open the app again.\n'
        f'Error details: {log_file}'
    )
    if sys.platform == 'win32':
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, message, server.APP_NAME, 0x10)
    else:
        print(message, file=sys.stderr)


class DesktopFileApi:
    """Save downloads and launch invoices without relying on WebView pop-ups."""

    @staticmethod
    def safe_filename(filename):
        """Prevent a browser value from writing outside the intended folders."""
        return Path(filename or 'orbix-download').name

    @staticmethod
    def decode_content(encoded_content):
        """Decode the base64 data sent by the local POS interface."""
        return base64.b64decode(encoded_content.encode('ascii'), validate=True)

    @staticmethod
    def image_data_url(path):
        """Keep an invoice image available after its local server is closed."""
        return 'data:image/png;base64,' + base64.b64encode(path.read_bytes()).decode('ascii')

    @staticmethod
    def qr_data_url(value):
        """Generate the invoice QR locally rather than linking to localhost."""
        import io
        import qrcode

        image = qrcode.make(value).convert('RGB')
        output = io.BytesIO()
        image.save(output, 'PNG')
        return 'data:image/png;base64,' + base64.b64encode(output.getvalue()).decode('ascii')

    def embed_invoice_images(self, invoice_html):
        """Replace localhost logo/QR links with portable image data URLs.

        The invoice is opened as a file after printing. Embedding both images
        means reopening an old invoice works even when the POS is not running.
        """
        logo_path = bundled_file('assets/Orbix.png')
        if logo_path.is_file():
            logo_url = self.image_data_url(logo_path)
            invoice_html = re.sub(
                r'src="(?:https?://[^\"]+)?/?assets/Orbix\.png"',
                f'src="{logo_url}"',
                invoice_html,
            )

        def replace_qr(match):
            source = html.unescape(match.group(2))
            value = parse_qs(urlparse(source).query).get('value', ['ORBIX'])[0]
            try:
                return match.group(1) + self.qr_data_url(value) + match.group(3)
            except Exception:
                # A logo-less fallback is preferable to blocking a completed bill.
                return match.group(0)

        return re.sub(r'(<img class="qr" src=")([^\"]+)(")', replace_qr, invoice_html)

    @staticmethod
    def downloads_directory():
        directory = Path.home() / 'Downloads'
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    def save_download(self, filename, encoded_content):
        """Save a PDF, CSV or database backup to the user's Downloads folder."""
        destination = self.downloads_directory() / self.safe_filename(filename)
        destination.write_bytes(self.decode_content(encoded_content))
        return {'path': str(destination)}

    def print_invoice(self, filename, encoded_html):
        """Open the invoice in the default Windows browser for standard printing."""
        invoice_directory = server.DATA_DIR / 'invoices'
        invoice_directory.mkdir(parents=True, exist_ok=True)
        destination = invoice_directory / self.safe_filename(filename)
        invoice_html = self.decode_content(encoded_html).decode('utf-8')
        destination.write_text(self.embed_invoice_images(invoice_html), encoding='utf-8')
        if sys.platform == 'win32':
            os.startfile(str(destination))
        else:
            import webbrowser
            webbrowser.open(destination.as_uri())
        return {'path': str(destination)}


def main():
    httpd = None
    try:
        os.chdir(bundled_file('.'))
        verify_frontend_files()
        prepare_windows_data()
        server.init()
        # Importing here lets the application report a missing WebView runtime.
        import webview

        # The desktop shell is the intended client, so do not expose the API on LAN.
        httpd = ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        window = webview.create_window(
            server.APP_NAME,
            f'http://127.0.0.1:{httpd.server_port}',
            width=1440,
            height=900,
            min_size=(1100, 700),
            js_api=DesktopFileApi(),
        )
        # The old MSHTML renderer behaves like Internet Explorer and cannot
        # reliably run the modern JavaScript used by the POS interface.
        # EdgeChromium gives the desktop app the same browser engine as Chrome.
        webview.start(gui='edgechromium')
    except Exception as error:
        log_file = write_startup_error(error)
        show_startup_error(error, log_file)
    finally:
        if httpd:
            httpd.shutdown()
            httpd.server_close()


if __name__ == '__main__':
    main()
