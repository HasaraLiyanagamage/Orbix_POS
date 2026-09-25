"""ORBIX Technologies local SQLite server. Run: python3 server.py."""

import csv
import hashlib
import hmac
import io
import json
import os
import re
import secrets
import sqlite3
import struct
import sys
import zlib
import base64
import shutil
from datetime import datetime
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

RESOURCE_DIR = Path(getattr(sys, '_MEIPASS', Path(__file__).parent))
APP_VARIANT = os.environ.get('ORBIX_APP_VARIANT', 'pos').strip().lower()
IS_IT_APP = APP_VARIANT == 'it'
APP_NAME = 'ORBIX Technologies (IT)' if IS_IT_APP else 'ORBIX Technologies POS'
DATA_FOLDER_NAME = 'ORBIX Technologies IT' if IS_IT_APP else 'ORBIX Technologies POS'
if getattr(sys, 'frozen', False) and sys.platform == 'win32':
    # Business data belongs outside Program Files. Prefer D: so a Windows
    # re-install of C: does not remove the shop database or saved invoices.
    LEGACY_DATA_DIR = None if IS_IT_APP else Path(os.environ.get('LOCALAPPDATA', Path.home())) / DATA_FOLDER_NAME
    preferred_data_dir = Path('D:/') / DATA_FOLDER_NAME
    try:
        preferred_data_dir.mkdir(parents=True, exist_ok=True)
        DATA_DIR = preferred_data_dir
    except OSError:
        # Some PCs have no D: drive. Keep the app usable and let the startup
        # message/log identify the fallback location rather than failing.
        fallback_data_dir = Path(os.environ.get('LOCALAPPDATA', Path.home())) / DATA_FOLDER_NAME
        fallback_data_dir.mkdir(parents=True, exist_ok=True)
        DATA_DIR = fallback_data_dir
else:
    LEGACY_DATA_DIR = None
    DATA_DIR = Path(__file__).parent
DB = DATA_DIR / 'orbix.db'
SESSIONS = {}
SEED = [
    ("Laptop RAM 8GB DDR4", "RAM-8-DDR4", "Computer Parts", 12500, 12, "90 Days"),
    ("SSD 256GB SATA", "SSD-256-SATA", "Storage", 14500, 10, "90 Days"),
    ("Wireless Keyboard", "KB-WL-001", "Accessories", 4500, 15, "90 Days"),
    ("USB Optical Mouse", "MS-USB-001", "Accessories", 1800, 20, "90 Days"),
    ("A4 Glossy Photo Paper", "PP-A4-GLOSS", "Printing Supplies", 3200, 8, "No Warranty"),
    ("Photo Frame 8 x 10", "FRAME-8X10", "Photo Frames", 2500, 18, "30 Days"),
]
SERVICE_SEED = [
    ("Laptop / Desktop Repair", "REP-PC-001", 3500, "Diagnostic and repair"),
    ("Windows & Software Installation", "SVC-SW-001", 2500, "1 - 2 hours"),
    ("Graphic Design Service", "DESIGN-001", 3000, "Per design"),
    ("Photo Frame Design & Print", "FRAME-DESIGN-001", 1800, "Per frame"),
    ("Printer Repair Service", "REP-PRINT-001", 3000, "Diagnostic and repair"),
]

PASSWORD_ITERATIONS = 210_000

def password_hash(password):
    """Use PBKDF2 for all newly stored passwords."""
    if not isinstance(password, str) or len(password) < 8:
        raise ValueError('Password must contain at least 8 characters')
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, PASSWORD_ITERATIONS)
    return f'pbkdf2_sha256${PASSWORD_ITERATIONS}${salt.hex()}${digest.hex()}'

def password_matches(password, stored):
    """Supports existing SHA-256 accounts once, then upgrades them at login."""
    if stored.startswith('pbkdf2_sha256$'):
        _, iterations, salt, digest = stored.split('$', 3)
        actual = hashlib.pbkdf2_hmac(
            'sha256', password.encode(), bytes.fromhex(salt), int(iterations)
        ).hex()
        return hmac.compare_digest(actual, digest)
    return hmac.compare_digest(hashlib.sha256(password.encode()).hexdigest(),stored)

def valid_username(value):
    return bool(re.fullmatch(r'[A-Za-z0-9._-]{3,40}',value or ''))

def money(value, label='Amount'):
    """Convert a supplied amount to a non-negative, two-decimal value."""
    try:
        amount = round(float(value), 2)
    except (TypeError, ValueError):
        raise ValueError(f'{label} must be a valid amount')
    if amount < 0:
        raise ValueError(f'{label} cannot be negative')
    return amount

def required_text(value, label, maximum=120):
    """Trim required form fields and keep accidental oversized values out of SQLite."""
    text = ' '.join(str(value or '').split())
    if not text:
        raise ValueError(f'{label} is required')
    if len(text) > maximum:
        raise ValueError(f'{label} must be {maximum} characters or fewer')
    return text

def optional_text(value, label, maximum=250):
    text = ' '.join(str(value or '').split())
    if len(text) > maximum:
        raise ValueError(f'{label} must be {maximum} characters or fewer')
    return text

def valid_code(value, label):
    code = required_text(value, label, 60)
    if not re.fullmatch(r'[A-Za-z0-9._/-]{2,60}', code):
        raise ValueError(f'{label} may use letters, numbers, dots, hyphens, underscores or slashes only')
    return code

def whole_number(value, label, minimum=0, maximum=1000000):
    try:
        number = int(str(value))
    except (TypeError, ValueError):
        raise ValueError(f'{label} must be a whole number')
    if number < minimum or number > maximum:
        raise ValueError(f'{label} must be between {minimum:,} and {maximum:,}')
    return number

def optional_phone(value):
    phone = optional_text(value, 'Phone number', 30)
    if phone and not re.fullmatch(r'[0-9+()\- ]{7,30}', phone):
        raise ValueError('Phone number contains invalid characters')
    return phone

def optional_email(value):
    email = optional_text(value, 'Email address', 120)
    if email and not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email):
        raise ValueError('Enter a valid email address')
    return email

def customer_duplicate(con, name, phone, exclude_id=None):
    """Reject a repeated customer while still allowing same-name people with different phones."""
    normalized_name = name.casefold()
    if phone:
        query = 'SELECT id,name,phone FROM customers WHERE lower(trim(phone))=lower(trim(?))'
        params = [phone]
    else:
        query = 'SELECT id,name,phone FROM customers WHERE lower(trim(name))=? AND (phone IS NULL OR trim(phone)=\'\')'
        params = [normalized_name]
    if exclude_id is not None:
        query += ' AND id<>?'
        params.append(exclude_id)
    return con.execute(query + ' LIMIT 1', params).fetchone()

def db():
    """Open the application SQLite database with dictionary-style rows."""
    connection = sqlite3.connect(DB)
    connection.row_factory = sqlite3.Row
    connection.execute('PRAGMA foreign_keys=ON')
    return connection

def audit(con, actor, action, entity_type, entity_id='', details=''):
    """Record material business actions without storing passwords or secrets."""
    con.execute(
        'INSERT INTO audit_logs(logged_at,actor,action,entity_type,entity_id,details) VALUES(?,?,?,?,?,?)',
        (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), actor or 'System', action, entity_type, str(entity_id or ''), details[:1000]),
    )

def approved_return_filter(alias='r'):
    """Old return records are treated as approved after the approval feature upgrade."""
    return f"COALESCE({alias}.status,'Approved')='Approved'"

def automatic_backup():
    """Keep one SQLite-safe daily copy alongside the live database for recovery."""
    backup_dir = DATA_DIR / 'backups'
    backup_dir.mkdir(parents=True, exist_ok=True)
    target = backup_dir / f"orbix-auto-{datetime.now():%Y-%m-%d}.db"
    if target.exists():
        return
    source = db()
    destination = sqlite3.connect(target)
    try:
        source.backup(destination)
    finally:
        destination.close()
        source.close()

def daily_report(day, employee_name=None):
    """Build one reconciled closing report for a date and optional cashier.

    Sale totals are stored after discount, while item prices are stored before
    discount.  The report therefore allocates each invoice discount across its
    own lines in cents before any product/service figures are added.  This keeps
    the item breakdown, returns and Net Sales mathematically consistent.
    """
    con = db()
    try:
        sale_where = "sold_at LIKE ? AND business_context='computer_creative' AND COALESCE(status,'Completed')='Completed'"
        sale_params = [day + '%']
        item_where = "s.sold_at LIKE ? AND s.business_context='computer_creative' AND COALESCE(s.status,'Completed')='Completed'"
        item_params = [day + '%']
        if employee_name:
            sale_where += ' AND employee_name=?'
            sale_params.append(employee_name)
            item_where += ' AND s.employee_name=?'
            item_params.append(employee_name)

        return_where = "r.returned_at LIKE ? AND COALESCE(r.status,'Approved')='Approved'"
        return_params = [day + '%']
        if employee_name:
            return_where += ' AND r.processed_by=?'
            return_params.append(employee_name)

        totals = con.execute(
            f'''SELECT COUNT(*) bills, COALESCE(SUM(subtotal), 0) before_discount_total,
                       COALESCE(SUM(discount), 0) discount_total, COALESCE(SUM(total), 0) total
                FROM sales WHERE {sale_where}''', sale_params
        ).fetchone()
        payments = con.execute(
            f'''SELECT COALESCE(SUM(CASE
                         WHEN method='Cash' THEN total
                         WHEN method='Credit' THEN payment_received
                         ELSE 0 END), 0) cash_total,
                       COALESCE(SUM(CASE WHEN method='Card' THEN total ELSE 0 END), 0) card_total
                FROM sales WHERE {sale_where}''', sale_params
        ).fetchone()

        credit_where = 'paid_at LIKE ?'
        credit_params = [day + '%']
        if employee_name:
            credit_where += ' AND received_by=?'
            credit_params.append(employee_name)
        credit_collections = con.execute(
            f'''SELECT COUNT(*) payment_count,
                       COALESCE(SUM(CASE WHEN method='Cash' THEN amount ELSE 0 END), 0) cash_total,
                       COALESCE(SUM(CASE WHEN method='Card' THEN amount ELSE 0 END), 0) card_total
                FROM credit_payments WHERE {credit_where}''', credit_params
        ).fetchone()
        initial_credit = con.execute(
            f'''SELECT COUNT(*) payment_count, COALESCE(SUM(payment_received), 0) total
                FROM sales WHERE {sale_where} AND method='Credit' AND payment_received>0''', sale_params
        ).fetchone()
        credit_payments = con.execute(
            f'''SELECT sold_at paid_at, invoice, customer_name, employee_name received_by,
                       payment_received amount, 'Cash' method, 'Initial part payment' note
                FROM sales WHERE {sale_where} AND method='Credit' AND payment_received>0
                UNION ALL
                SELECT paid_at, invoice, '' customer_name, received_by, amount, method, note
                FROM credit_payments WHERE {credit_where}
                ORDER BY paid_at''', sale_params + credit_params
        ).fetchall()

        returned = con.execute(
            f'''SELECT COUNT(*) return_count, COALESCE(SUM(r.refund_total), 0) return_total,
                       COALESCE(SUM(CASE WHEN s.method='Cash' THEN r.refund_total ELSE 0 END), 0) return_cash_total,
                       COALESCE(SUM(CASE WHEN s.method='Card' THEN r.refund_total ELSE 0 END), 0) return_card_total
                FROM returns r JOIN sales s ON s.id=r.sale_id WHERE {return_where}''', return_params
        ).fetchone()
        returned_products = con.execute(
            f'''SELECT ri.product_name name, SUM(ri.quantity) quantity, SUM(ri.refund_amount) amount
                FROM return_items ri JOIN returns r ON r.id=ri.return_id
                WHERE {return_where} GROUP BY ri.product_name ORDER BY ri.product_name''', return_params
        ).fetchall()

        # Item discounts are retained on each line. Any remaining bill-level
        # discount is shared across the already-discounted lines in cents so
        # service and product income remain accurate in the daily report.
        sale_lines = con.execute(
            f'''SELECT s.id sale_id, s.subtotal, s.discount, si.id line_id, si.product_name,
                       si.quantity, si.unit_price, COALESCE(si.item_type, 'product') item_type,
                       COALESCE(si.line_discount, 0) line_discount
                FROM sale_items si JOIN sales s ON s.id=si.sale_id
                WHERE {item_where} ORDER BY s.id, si.id''', item_params
        ).fetchall()
        lines_by_sale = {}
        for line in sale_lines:
            lines_by_sale.setdefault(line['sale_id'], []).append(line)

        service_rows, part_rows = {}, {}
        for lines in lines_by_sale.values():
            line_discount_cents = sum(round(float(line['line_discount'] or 0) * 100) for line in lines)
            invoice_discount_cents = round(float(lines[0]['discount'] or 0) * 100)
            bill_discount_cents = max(0, invoice_discount_cents - line_discount_cents)
            discounted_subtotal_cents = sum(max(0, round(float(line['quantity']) * float(line['unit_price']) * 100) - round(float(line['line_discount'] or 0) * 100)) for line in lines)
            applied_bill_discount = 0
            for index, line in enumerate(lines):
                line_cents = round(float(line['quantity']) * float(line['unit_price']) * 100)
                item_discount_cents = min(line_cents, round(float(line['line_discount'] or 0) * 100))
                net_line_cents = line_cents - item_discount_cents
                if index == len(lines) - 1:
                    bill_line_discount = bill_discount_cents - applied_bill_discount
                elif discounted_subtotal_cents:
                    bill_line_discount = round(net_line_cents * bill_discount_cents / discounted_subtotal_cents)
                    applied_bill_discount += bill_line_discount
                else:
                    bill_line_discount = 0
                bucket = service_rows if line['item_type'] == 'service' else part_rows
                entry = bucket.setdefault(line['product_name'], {'name': line['product_name'], 'quantity': 0, 'amount_cents': 0})
                entry['quantity'] += int(line['quantity'])
                entry['amount_cents'] += net_line_cents - bill_line_discount

        # A returned product reduces the net product income on the day the
        # return is processed. Services cannot be returned through this flow.
        for row in returned_products:
            entry = part_rows.setdefault(row['name'], {'name': row['name'], 'quantity': 0, 'amount_cents': 0})
            entry['quantity'] -= int(row['quantity'])
            entry['amount_cents'] -= round(float(row['amount']) * 100)

        def report_rows(entries):
            return [
                {'name': entry['name'], 'quantity': entry['quantity'], 'amount': round(entry['amount_cents'] / 100, 2)}
                for entry in sorted(entries.values(), key=lambda item: item['name'].lower())
                if entry['quantity'] or entry['amount_cents']
            ]

        services = report_rows(service_rows)
        parts = report_rows(part_rows)
        sales_after_discount = round(float(totals['total']), 2)
        return_total = round(float(returned['return_total']), 2)
        net_sales = round(sales_after_discount - return_total, 2)
        service_total = round(sum(row['amount'] for row in services), 2)
        # Use the reconciled headline total for the product balance. This avoids
        # a one-cent display difference caused by allocating invoice discounts.
        part_total = round(net_sales - service_total, 2)

        return {
            'date': day,
            'cashier': employee_name or 'All Cashiers',
            'bills': totals['bills'],
            'sales_before_discount': round(float(totals['before_discount_total']), 2),
            'discount_total': round(float(totals['discount_total']), 2),
            'gross_total': sales_after_discount,
            'total': net_sales,
            'cash_total': round(float(payments['cash_total']) + float(credit_collections['cash_total']) - float(returned['return_cash_total']), 2),
            'card_total': round(float(payments['card_total']) + float(credit_collections['card_total']) - float(returned['return_card_total']), 2),
            'credit_payment_count': initial_credit['payment_count'] + credit_collections['payment_count'],
            'credit_received_total': round(float(initial_credit['total']) + float(credit_collections['cash_total']) + float(credit_collections['card_total']), 2),
            'credit_received_cash': round(float(initial_credit['total']) + float(credit_collections['cash_total']), 2),
            'credit_received_card': round(float(credit_collections['card_total']), 2),
            'credit_payments': [dict(row) for row in credit_payments],
            'return_count': returned['return_count'],
            'return_total': return_total,
            'service_total': service_total,
            'parts_total': part_total,
            'service_count': sum(row['quantity'] for row in services),
            'services': services,
            'parts': parts,
            'returned_products': [dict(row) for row in returned_products],
        }
    finally:
        con.close()

def pdf_escape(value):
    return str(value).replace('\\','\\\\').replace('(','\\(').replace(')','\\)')

def public_user(row):
    return {'id':row['id'],'username':row['username'],'display_name':row['display_name'],'role':row['role']}

def revoke_user_sessions(user_id, except_token=None):
    for token,session in list(SESSIONS.items()):
        if session.get('id') == user_id and token != except_token: SESSIONS.pop(token,None)

def png_logo_pdf_objects(path):
    """Convert the transparent ORBIX PNG into PDF image and alpha-mask objects."""
    raw=Path(path).read_bytes()
    if raw[:8] != b'\x89PNG\r\n\x1a\n': raise ValueError('Logo must be a PNG file')
    chunks=[]; offset=8
    while offset < len(raw):
        size=struct.unpack('>I',raw[offset:offset+4])[0]; kind=raw[offset+4:offset+8]
        chunks.append((kind,raw[offset+8:offset+8+size])); offset += 12 + size
        if kind == b'IEND': break
    header=next(data for kind,data in chunks if kind == b'IHDR')
    width,height,depth,color_type,compression,filter_method,interlace=struct.unpack('>IIBBBBB',header)
    if (depth,color_type,compression,filter_method,interlace) != (8,6,0,0,0): raise ValueError('Logo must be an 8-bit RGBA non-interlaced PNG')
    packed=zlib.decompress(b''.join(data for kind,data in chunks if kind == b'IDAT'))
    stride=width*4; previous=bytearray(stride); rgb=bytearray(); alpha=bytearray(); cursor=0
    def paeth(a,b,c):
        p=a+b-c; pa=abs(p-a); pb=abs(p-b); pc=abs(p-c)
        return a if pa<=pb and pa<=pc else (b if pb<=pc else c)
    for _ in range(height):
        filter_type=packed[cursor]; cursor += 1; source=packed[cursor:cursor+stride]; cursor += stride; row=bytearray(stride)
        for i,value in enumerate(source):
            left=row[i-4] if i>=4 else 0; up=previous[i]
            if filter_type == 0: row[i]=value
            elif filter_type == 1: row[i]=(value+left)&255
            elif filter_type == 2: row[i]=(value+up)&255
            elif filter_type == 3: row[i]=(value+((left+up)//2))&255
            elif filter_type == 4: row[i]=(value+paeth(left,up,previous[i-4] if i>=4 else 0))&255
            else: raise ValueError('Unsupported PNG filter')
        for pixel in range(0,stride,4): rgb.extend(row[pixel:pixel+3]); alpha.append(row[pixel+3])
        previous=row
    image=(b'<< /Type /XObject /Subtype /Image /Width '+str(width).encode()+b' /Height '+str(height).encode()+b' /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /FlateDecode /SMask 8 0 R /Length '+str(len(zlib.compress(bytes(rgb)))).encode()+b' >>\nstream\n'+zlib.compress(bytes(rgb))+b'\nendstream')
    mask=(b'<< /Type /XObject /Subtype /Image /Width '+str(width).encode()+b' /Height '+str(height).encode()+b' /ColorSpace /DeviceGray /BitsPerComponent 8 /Filter /FlateDecode /Length '+str(len(zlib.compress(bytes(alpha)))).encode()+b' >>\nstream\n'+zlib.compress(bytes(alpha))+b'\nendstream')
    return image,mask

def daily_report_pdf(report):
    """Create a polished, dependency-free A4 daily report PDF."""
    # ORBIX visual palette: deep navy, electric blue and silver/ash.
    navy=(0.02,0.12,0.27); blue=(0.00,0.36,0.68); accent=(0.12,0.52,0.78)
    ash=(0.92,0.95,0.98); text=(0.04,0.12,0.24); white=(1,1,1)
    commands=[]
    def color(c): return f'{c[0]:.3f} {c[1]:.3f} {c[2]:.3f} rg'
    def box(x,y,w,h,c): commands.extend(['q',color(c),f'{x:.1f} {y:.1f} {w:.1f} {h:.1f} re f','Q'])
    def line(x1,y1,x2,y2,c,width=1): commands.extend(['q',f'{width:.1f} w',f'{c[0]:.3f} {c[1]:.3f} {c[2]:.3f} RG',f'{x1:.1f} {y1:.1f} m {x2:.1f} {y2:.1f} l S','Q'])
    def label(value,x,y,size=10,font='F1',c=text):
        commands.extend(['BT',f'/{font} {size:.1f} Tf',color(c),f'1 0 0 1 {x:.1f} {y:.1f} Tm',f'({pdf_escape(value)}) Tj','ET'])
    def fit(value, limit=44):
        value=str(value)
        return value if len(value)<=limit else value[:limit-3]+'...'

    # Header styled after the supplied Daily Status Report reference.
    box(0,620,595,222,navy)
    # Transparent ORBIX logo: no white frame behind it.
    commands.extend(['q','112 0 0 74 42 690 cm','/Logo Do','Q'])
    label('DAILY SALES REPORT',170,752,30,'F2',white)
    label('ORBIX TECHNOLOGIES',172,720,14,'F1',white)
    label('Computer Parts, Repairs, Photo Frames & Graphic Design',172,696,10,'F1',(0.85,0.91,0.98))
    label('No. 08, Naiwala Jct., Veyangoda | 0707080855',54,654,9,'F1',(0.88,0.92,0.97))
    label('orbixtechnologies24x7@gmail.com | WhatsApp: 0707080855',54,638,9,'F1',(0.88,0.92,0.97))
    label(f"Report Date: {report['date']}",392,654,9,'F2',white)
    label(f"Cashier: {fit(report['cashier'],24)}",392,638,8,'F1',(0.88,0.92,0.97))

    # Summary cards.
    cards=[('NET SALES',f"LKR {report['total']:,.2f}",blue),('BILLS CREATED',str(report['bills']),navy),('CASH TO BALANCE',f"LKR {report['cash_total']:,.2f}",accent)]
    for index,(title,value,shade) in enumerate(cards):
        x=42+index*172; box(x,546,158,55,ash); box(x,584,158,17,shade); label(title,x+10,589,7.5,'F2',white); label(value,x+10,560,14,'F2',text)
    # This short reconciliation row makes the discount calculation visible in
    # the PDF without changing the cash-to-balance figure.
    box(42,505,511,26,ash); label('Sales Before Discounts',55,514,10,'F2',text); label(f"LKR {report['sales_before_discount']:,.2f}",178,514,10,'F2',blue)
    label('Discounts Given',310,514,10,'F2',text); label(f"LKR {report['discount_total']:,.2f}",438,514,10,'F2',(0.75,0.12,0.20))
    box(42,473,511,24,ash); label('Service Income',55,481,10,'F2',text); label(f"LKR {report['service_total']:,.2f}",175,481,10,'F2',blue)
    label('Products & Print Income',300,481,10,'F2',text); label(f"LKR {report['parts_total']:,.2f}",440,481,10,'F2',blue)
    box(42,441,511,24,(1.0,0.94,0.95)); label('Product Return Amount',55,449,10,'F2',(0.60,0.10,0.17)); label(f"LKR {report['return_total']:,.2f}",205,449,10,'F2',(0.75,0.12,0.20)); label('Returns Processed',350,449,10,'F2',text); label(str(report['return_count']),495,449,10,'F2',text)
    box(42,409,511,24,(0.90,0.96,0.92)); label('Credit Payments Collected',55,417,10,'F2',(0.07,0.36,0.20)); label(f"LKR {report['credit_received_total']:,.2f}",220,417,10,'F2',(0.05,0.45,0.25)); label('Payments',390,417,10,'F2',text); label(str(report['credit_payment_count']),495,417,10,'F2',text)

    y=374
    def section(title, rows, empty):
        nonlocal y
        box(42,y,511,26,navy); label(title,55,y+8,11,'F2',white); y-=26
        headers=[('DESCRIPTION',55),('QTY',380),('AMOUNT (LKR)',445)]
        box(42,y,511,22,(0.86,0.89,0.93))
        for heading,x in headers: label(heading,x,y+7,7.5,'F2',text)
        y-=22
        # Keep the A4 PDF clean and uncut. Full item details remain in the CSV export.
        display=(rows[:3] if rows else [{'name':empty,'quantity':'-','amount':0}])
        for row in display:
            box(42,y,511,12,white)
            label(fit(row['name'],46),55,y+3.5,6.8,'F1',text)
            label(str(row['quantity']),386,y+3.5,6.8,'F1',text)
            label(f"{float(row['amount']):,.2f}" if rows else '-',445,y+3.5,6.8,'F1',text)
            line(42,y,553,y,(0.85,0.88,0.92),.5); y-=12
        # The next section header is 26pt tall, so leave enough vertical space
        # to keep it clear of the last 12pt data row.
        y-=14
    section('SERVICES — NET SALES',report['services'],'No services were recorded for this date')
    section('PRODUCTS & PRINT ITEMS — NET SALES',report['parts'],'No product or print item activity for this date')
    section('PRODUCTS RETURNED',report['returned_products'],'No products were returned on this date')
    line(42,44,553,44,(0.75,0.80,0.87),.7)
    label(APP_NAME,42,28,8,'F2',navy)
    label('Daily report - confidential business record',354,28,8,'F1',(0.35,0.41,0.48))

    stream='\n'.join(commands).encode('latin-1','replace')
    logo,logo_mask=png_logo_pdf_objects(RESOURCE_DIR / 'assets' / 'Orbix.png')
    objects=[b'<< /Type /Catalog /Pages 2 0 R >>',b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 5 0 R /F2 6 0 R >> /XObject << /Logo 7 0 R >> >> /Contents 4 0 R >>',b'<< /Length '+str(len(stream)).encode()+b' >>\nstream\n'+stream+b'\nendstream',b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>',logo,logo_mask]
    output=b'%PDF-1.4\n%\xe2\xe3\xcf\xd3\n'; offsets=[0]
    for number,obj in enumerate(objects,1):
        offsets.append(len(output)); output+=f'{number} 0 obj\n'.encode()+obj+b'\nendobj\n'
    start=len(output); output+=f'xref\n0 {len(objects)+1}\n0000000000 65535 f \n'.encode(); output+=b''.join(f'{offset:010d} 00000 n \n'.encode() for offset in offsets[1:])
    return output+f'trailer\n<< /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{start}\n%%EOF\n'.encode()
def init():
    # Schema setup and safe migrations preserve existing sales when a shop
    # starts a newer version of the POS for the first time.
    # Keep this value before SQLite opens the file.  It lets us add the demo
    # catalogue only to a truly new database, never after staff delete records.
    new_database = not DB.exists()
    con = db()
    con.executescript('''
      CREATE TABLE IF NOT EXISTS products(id INTEGER PRIMARY KEY,name TEXT NOT NULL,sku TEXT UNIQUE NOT NULL,category TEXT,price REAL NOT NULL,wholesale_price REAL,stock INTEGER NOT NULL,warranty TEXT DEFAULT '90 Days');
      CREATE TABLE IF NOT EXISTS customers(id INTEGER PRIMARY KEY,name TEXT NOT NULL,phone TEXT,vehicle TEXT,email TEXT,price_group TEXT NOT NULL DEFAULT 'normal');
      CREATE TABLE IF NOT EXISTS employees(id INTEGER PRIMARY KEY,name TEXT NOT NULL,role TEXT NOT NULL,phone TEXT,active INTEGER DEFAULT 1);
      CREATE TABLE IF NOT EXISTS sales(id INTEGER PRIMARY KEY,invoice TEXT UNIQUE NOT NULL,sold_at TEXT NOT NULL,customer_id INTEGER,customer_name TEXT,employee_name TEXT,method TEXT,subtotal REAL,discount REAL,tax REAL,total REAL);
      CREATE TABLE IF NOT EXISTS sale_items(id INTEGER PRIMARY KEY,sale_id INTEGER,product_id INTEGER,product_name TEXT,quantity INTEGER,unit_price REAL,warranty TEXT DEFAULT '',line_discount REAL NOT NULL DEFAULT 0);
      CREATE TABLE IF NOT EXISTS returns(id INTEGER PRIMARY KEY,return_no TEXT UNIQUE NOT NULL,sale_id INTEGER NOT NULL,invoice TEXT NOT NULL,returned_at TEXT NOT NULL,customer_name TEXT,processed_by TEXT NOT NULL,reason TEXT DEFAULT '',refund_total REAL NOT NULL DEFAULT 0);
      CREATE TABLE IF NOT EXISTS return_items(id INTEGER PRIMARY KEY,return_id INTEGER NOT NULL,sale_item_id INTEGER NOT NULL,product_id INTEGER,product_name TEXT NOT NULL,quantity INTEGER NOT NULL,unit_price REAL NOT NULL,refund_amount REAL NOT NULL);
      CREATE TABLE IF NOT EXISTS credit_payments(id INTEGER PRIMARY KEY,sale_id INTEGER NOT NULL,invoice TEXT NOT NULL,paid_at TEXT NOT NULL,amount REAL NOT NULL,method TEXT NOT NULL,received_by TEXT NOT NULL,note TEXT DEFAULT '');
      CREATE TABLE IF NOT EXISTS services(id INTEGER PRIMARY KEY,name TEXT NOT NULL,code TEXT UNIQUE NOT NULL,price REAL NOT NULL,wholesale_price REAL,duration TEXT DEFAULT '',active INTEGER DEFAULT 1);
      CREATE TABLE IF NOT EXISTS customer_prices(customer_id INTEGER NOT NULL,item_type TEXT NOT NULL,item_id INTEGER NOT NULL,price REAL NOT NULL,PRIMARY KEY(customer_id,item_type,item_id));
      CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY,username TEXT UNIQUE NOT NULL,password_hash TEXT NOT NULL,role TEXT NOT NULL,display_name TEXT NOT NULL DEFAULT '');
      CREATE TABLE IF NOT EXISTS app_settings(setting_key TEXT PRIMARY KEY, setting_value TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS audit_logs(id INTEGER PRIMARY KEY,logged_at TEXT NOT NULL,actor TEXT NOT NULL,action TEXT NOT NULL,entity_type TEXT NOT NULL,entity_id TEXT,details TEXT DEFAULT '');
      CREATE TABLE IF NOT EXISTS stock_movements(id INTEGER PRIMARY KEY,product_id INTEGER NOT NULL,product_name TEXT NOT NULL,quantity_change INTEGER NOT NULL,stock_after INTEGER NOT NULL,movement_type TEXT NOT NULL,reason TEXT DEFAULT '',recorded_at TEXT NOT NULL,recorded_by TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS cash_closings(id INTEGER PRIMARY KEY,closing_date TEXT NOT NULL,cashier_name TEXT NOT NULL,expected_cash REAL NOT NULL,counted_cash REAL NOT NULL,difference REAL NOT NULL,note TEXT DEFAULT '',closed_at TEXT NOT NULL,closed_by TEXT NOT NULL,UNIQUE(closing_date,cashier_name));
    ''')
    user_columns = [row[1] for row in con.execute("PRAGMA table_info(users)")]
    if 'display_name' not in user_columns:
        con.execute("ALTER TABLE users ADD COLUMN display_name TEXT NOT NULL DEFAULT ''")
    if con.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
        con.execute(
            "INSERT INTO users(username,password_hash,role,display_name) VALUES(?,?,?,?)",
            ('admin', password_hash('Admin@123'), 'admin', 'Administrator'),
        )
    if not con.execute("SELECT 1 FROM users WHERE username='counter'").fetchone():
        con.execute(
            "INSERT INTO users(username,password_hash,role,display_name) VALUES(?,?,?,?)",
            ('counter', password_hash('Counter@123'), 'counter', 'Counter Operator'),
        )
    con.execute("UPDATE users SET display_name=CASE username WHEN 'admin' THEN 'Administrator' WHEN 'counter' THEN 'Counter Operator' ELSE username END WHERE display_name IS NULL OR display_name='' ")
    columns = [row[1] for row in con.execute("PRAGMA table_info(sales)")]
    if 'payment_received' not in columns:
        con.execute("ALTER TABLE sales ADD COLUMN payment_received REAL DEFAULT 0")
    if 'payment_change' not in columns:
        con.execute("ALTER TABLE sales ADD COLUMN payment_change REAL DEFAULT 0")
    if 'business_context' not in columns:
        con.execute("ALTER TABLE sales ADD COLUMN business_context TEXT DEFAULT 'legacy_motor'")
    if 'status' not in columns:
        con.execute("ALTER TABLE sales ADD COLUMN status TEXT NOT NULL DEFAULT 'Completed'")
    if 'voided_at' not in columns:
        con.execute("ALTER TABLE sales ADD COLUMN voided_at TEXT DEFAULT ''")
    if 'voided_by' not in columns:
        con.execute("ALTER TABLE sales ADD COLUMN voided_by TEXT DEFAULT ''")
    if 'void_reason' not in columns:
        con.execute("ALTER TABLE sales ADD COLUMN void_reason TEXT DEFAULT ''")
    product_columns = [row[1] for row in con.execute("PRAGMA table_info(products)")]
    if 'wholesale_price' not in product_columns:
        con.execute("ALTER TABLE products ADD COLUMN wholesale_price REAL")
    if 'warranty' not in product_columns:
        con.execute("ALTER TABLE products ADD COLUMN warranty TEXT DEFAULT '90 Days'")
    service_columns = [row[1] for row in con.execute("PRAGMA table_info(services)")]
    if 'wholesale_price' not in service_columns:
        con.execute("ALTER TABLE services ADD COLUMN wholesale_price REAL")
    customer_columns = [row[1] for row in con.execute("PRAGMA table_info(customers)")]
    if 'price_group' not in customer_columns:
        con.execute("ALTER TABLE customers ADD COLUMN price_group TEXT NOT NULL DEFAULT 'normal'")
    if 'customer_id' not in columns:
        con.execute("ALTER TABLE sales ADD COLUMN customer_id INTEGER")
    # Existing catalogue items keep working after the upgrade. Managers can
    # subsequently set a lower wholesale value in Product or Service settings.
    con.execute("UPDATE products SET wholesale_price=price WHERE wholesale_price IS NULL")
    con.execute("UPDATE services SET wholesale_price=price WHERE wholesale_price IS NULL")
    con.execute("UPDATE products SET warranty=CASE sku WHEN 'PP-A4-GLOSS' THEN 'No Warranty' WHEN 'FRAME-8X10' THEN '30 Days' ELSE COALESCE(NULLIF(warranty,''),'90 Days') END WHERE sku IN ('PP-A4-GLOSS','FRAME-8X10') OR warranty IS NULL OR warranty=''")
    sale_item_columns = [row[1] for row in con.execute("PRAGMA table_info(sale_items)")]
    if 'item_type' not in sale_item_columns:
        con.execute("ALTER TABLE sale_items ADD COLUMN item_type TEXT DEFAULT 'product'")
    if 'warranty' not in sale_item_columns:
        con.execute("ALTER TABLE sale_items ADD COLUMN warranty TEXT DEFAULT ''")
    if 'line_discount' not in sale_item_columns:
        con.execute("ALTER TABLE sale_items ADD COLUMN line_discount REAL NOT NULL DEFAULT 0")
    return_columns = [row[1] for row in con.execute("PRAGMA table_info(returns)")]
    if 'status' not in return_columns:
        con.execute("ALTER TABLE returns ADD COLUMN status TEXT NOT NULL DEFAULT 'Approved'")
    if 'approved_by' not in return_columns:
        con.execute("ALTER TABLE returns ADD COLUMN approved_by TEXT DEFAULT ''")
    if 'approved_at' not in return_columns:
        con.execute("ALTER TABLE returns ADD COLUMN approved_at TEXT DEFAULT ''")
    # One-time safe business conversion: legacy vehicle sales are retained in the database,
    # but hidden from the new shop's reports. The old sample catalogue is replaced.
    converted = con.execute("SELECT 1 FROM app_settings WHERE setting_key='computer_creative_conversion'").fetchone()
    old_skus = ('EO-1030', 'OF-TY14', 'AF-HD22', 'BP-FR09', 'SP-NGK5', 'BT-45AH')
    if not converted and con.execute("SELECT 1 FROM products WHERE sku IN (?,?,?,?,?,?)",old_skus).fetchone():
        con.execute("UPDATE sales SET business_context='legacy_motor' WHERE business_context IS NULL OR business_context='' OR business_context='computer_creative'")
        con.execute("DELETE FROM products WHERE sku IN (?,?,?,?,?,?)",old_skus)
        con.execute("DELETE FROM services")
        con.execute("INSERT INTO app_settings(setting_key,setting_value) VALUES('computer_creative_conversion','done')")
    # Demo records make a new install usable immediately.  They must not be
    # re-created merely because an administrator intentionally deleted all
    # records in one of these tables.
    if new_database and con.execute('SELECT COUNT(*) FROM products').fetchone()[0] == 0:
        con.executemany('INSERT INTO products(name,sku,category,price,stock,warranty) VALUES(?,?,?,?,?,?)', SEED)
    if new_database and con.execute("SELECT COUNT(*) FROM services").fetchone()[0] == 0:
        con.executemany("INSERT INTO services(name,code,price,duration) VALUES(?,?,?,?)", SERVICE_SEED)
    if new_database and con.execute("SELECT COUNT(*) FROM customers").fetchone()[0] == 0:
        con.execute("INSERT INTO customers(name) VALUES('Walk-in Customer')")
    if new_database and con.execute("SELECT COUNT(*) FROM employees").fetchone()[0] == 0:
        con.execute("INSERT INTO employees(name,role) VALUES('Counter Operator','Cashier')")
    con.commit()
    con.close()
    automatic_backup()

def customer_item_price(con, customer_id, item_type, item_id, standard_price):
    """Use an admin-defined customer price when one exists, otherwise retail price."""
    row = con.execute(
        'SELECT price FROM customer_prices WHERE customer_id=? AND item_type=? AND item_id=?',
        (customer_id, item_type, item_id),
    ).fetchone()
    return row['price'] if row else standard_price

def canonical_category(con, value):
    """Keep the saved spelling when a category already exists in the catalogue."""
    category = ' '.join(str(value or '').split()) or 'General'
    existing = con.execute(
        'SELECT category FROM products WHERE lower(category)=lower(?) LIMIT 1',
        (category,),
    ).fetchone()
    return existing['category'] if existing else category

def canonical_employee_role(con, value):
    """Reuse an existing role's spelling so cashier and staff labels stay consistent."""
    role = ' '.join(str(value or '').split())
    if not role:
        raise ValueError('Employee role is required')
    existing = con.execute('SELECT role FROM employees WHERE lower(role)=lower(?) LIMIT 1', (role,)).fetchone()
    return existing['role'] if existing else role

class Handler(SimpleHTTPRequestHandler):
    # The local browser interface and API use the same process, keeping the
    # Windows deployment self-contained without separate CORS configuration.
    # A POS page must always use the latest local scripts after an upgrade.
    # This prevents Chrome from using an old export handler that saved JSON as PDF/CSV.
    def end_headers(self):
        self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0')
        self.send_header('Pragma', 'no-cache')
        super().end_headers()
    def json(self,data,status=200):
        body=json.dumps(data).encode();self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',len(body));self.end_headers();self.wfile.write(body)
    def body(self): return json.loads(self.rfile.read(int(self.headers.get('Content-Length',0))) or b'{}')
    def session(self): return SESSIONS.get(self.headers.get('X-Admin-Token'))
    def authenticated(self): return bool(self.session())
    def admin(self): return bool(self.session() and self.session()['role']=='admin')
    def do_GET(self):
        # Read routes check the session too, so counter users cannot request
        # administrator-only records through the browser developer tools.
        if not self.path.startswith('/api/'): return super().do_GET()
        if self.path.startswith('/api/qr'):
            value=parse_qs(urlparse(self.path).query).get('value',[APP_NAME])[0]
            try:
                import qrcode
                image=qrcode.make(value).convert('RGB'); payload=io.BytesIO(); image.save(payload,'PNG'); data=payload.getvalue()
                self.send_response(200); self.send_header('Content-Type','image/png'); self.send_header('Content-Length',len(data)); self.end_headers(); self.wfile.write(data)
            except Exception:
                # Keeps the A4 invoice printable even before optional QR support is installed.
                safe_value=value.replace('&','&amp;').replace('<','&lt;').replace('>','&gt;')[:48]
                data=f'<svg xmlns="http://www.w3.org/2000/svg" width="120" height="120"><rect width="120" height="120" fill="white" stroke="#174b8f" stroke-width="3"/><text x="60" y="45" text-anchor="middle" font-family="Arial" font-size="18" font-weight="bold" fill="#174b8f">ORBIX</text><text x="60" y="68" text-anchor="middle" font-family="Arial" font-size="10" fill="#334155">Invoice Verification</text><text x="60" y="89" text-anchor="middle" font-family="Arial" font-size="8" fill="#334155">{safe_value}</text></svg>'.encode()
                self.send_response(200); self.send_header('Content-Type','image/svg+xml'); self.send_header('Content-Length',len(data)); self.end_headers(); self.wfile.write(data)
            return
        if self.path == '/api/app-info':
            return self.json({'name': APP_NAME, 'variant': 'it' if IS_IT_APP else 'pos'})
        if not self.authenticated(): return self.json({'error':'Login required'},403)
        if self.path.startswith('/api/daily-report.'):
            parsed=urlparse(self.path); query=parse_qs(parsed.query); day=query.get('date',[datetime.now().strftime('%Y-%m-%d')])[0]; cashier=(query.get('cashier',[''])[0].strip() or None) if self.admin() else self.session()['display_name']; report=daily_report(day, cashier)
            if parsed.path.endswith('.csv'):
                data=io.StringIO(); writer=csv.writer(data); writer.writerow([APP_NAME + ' Daily Report']); writer.writerow(['Date', report['date']]); writer.writerow(['Cashier',report['cashier']]); writer.writerow([]); writer.writerow(['Summary','Value']); writer.writerows([['Sales Before Discounts',f"{report['sales_before_discount']:.2f}"],['Total Discounts Given',f"{report['discount_total']:.2f}"],['Sales After Discounts',f"{report['gross_total']:.2f}"],['Net Sales',f"{report['total']:.2f}"],['Return Amount',f"{report['return_total']:.2f}"],['Returns Processed',report['return_count']],['Credit Payments Collected',f"{report['credit_received_total']:.2f}"],['Credit Cash Collected',f"{report['credit_received_cash']:.2f}"],['Credit Card Collected',f"{report['credit_received_card']:.2f}"],['Credit Payments Count',report['credit_payment_count']],['Cash to Balance',f"{report['cash_total']:.2f}"],['Card Sales',f"{report['card_total']:.2f}"],['Bills Created',report['bills']],['Services Completed',report['service_count']],['Service Income',f"{report['service_total']:.2f}"],['Parts and Print Income',f"{report['parts_total']:.2f}"]]); writer.writerow([]); writer.writerow(['Credit Payments Collected']); writer.writerow(['Date','Invoice','Collected By','Method','Note','Amount (LKR)']); writer.writerows([[row['paid_at'],row['invoice'],row['received_by'],row['method'],row['note'],f"{row['amount']:.2f}"] for row in report['credit_payments']]); writer.writerow([]); writer.writerow(['Services Completed']); writer.writerow(['Name','Qty','Amount (LKR)']); writer.writerows([[row['name'],row['quantity'],f"{row['amount']:.2f}"] for row in report['services']]); writer.writerow([]); writer.writerow(['Products and Print Items Sold']); writer.writerow(['Name','Qty','Amount (LKR)']); writer.writerows([[row['name'],row['quantity'],f"{row['amount']:.2f}"] for row in report['parts']]); writer.writerow([]); writer.writerow(['Products Returned']); writer.writerow(['Name','Qty','Refund Amount (LKR)']); writer.writerows([[row['name'],row['quantity'],f"{row['amount']:.2f}"] for row in report['returned_products']]); payload=data.getvalue().encode('utf-8-sig'); filename=f'orbix-daily-report-{day}.csv'; content_type='text/csv; charset=utf-8'
            else:
                payload=daily_report_pdf(report); filename=f'orbix-daily-report-{day}.pdf'; content_type='application/pdf'
            self.send_response(200); self.send_header('Content-Type',content_type); self.send_header('Content-Disposition',f'attachment; filename="{filename}"'); self.send_header('Content-Length',len(payload)); self.end_headers(); self.wfile.write(payload); return
        if self.path == '/api/backup':
            if not self.admin(): return self.json({'error':'Admin login required'},403)
            payload = DB.read_bytes()
            self.send_response(200); self.send_header('Content-Type','application/octet-stream'); self.send_header('Content-Disposition','attachment; filename="orbix-technologies-backup.db"'); self.send_header('Content-Length',len(payload)); self.end_headers(); self.wfile.write(payload); return
        if self.path == '/api/dashboard':
            if not self.admin(): return self.json({'error':'Admin access required'},403)
            today = datetime.now().strftime('%Y-%m-%d')
            con = db()
            try:
                daily = daily_report(today)
                month_prefix = today[:7] + '%'
                monthly_sales = con.execute(
                    "SELECT COALESCE(SUM(total),0) FROM sales WHERE sold_at LIKE ? AND business_context='computer_creative' AND COALESCE(status,'Completed')='Completed'",
                    (month_prefix,)
                ).fetchone()[0]
                monthly_returns = con.execute(
                    "SELECT COALESCE(SUM(refund_total),0) FROM returns WHERE returned_at LIKE ? AND COALESCE(status,'Approved')='Approved'",
                    (month_prefix,)
                ).fetchone()[0]
                best = [dict(row) for row in con.execute(
                    """SELECT product_name, SUM(quantity) quantity
                       FROM sale_items si JOIN sales s ON s.id=si.sale_id
                       WHERE s.business_context='computer_creative' AND COALESCE(s.status,'Completed')='Completed'
                       GROUP BY product_name ORDER BY quantity DESC LIMIT 5"""
                )]
                low = [dict(row) for row in con.execute(
                    "SELECT name, stock FROM products WHERE stock<=5 ORDER BY stock, name"
                )]
                customer_count = con.execute('SELECT COUNT(*) FROM customers').fetchone()[0]
                credit_total = con.execute(
                    """SELECT COALESCE(SUM(s.total-s.payment_received-COALESCE(collected.amount,0)),0)
                       FROM sales s
                       LEFT JOIN (SELECT sale_id, SUM(amount) amount FROM credit_payments GROUP BY sale_id) collected
                       ON collected.sale_id=s.id
                       WHERE s.business_context='computer_creative' AND s.method='Credit' AND COALESCE(s.status,'Completed')='Completed'"""
                ).fetchone()[0]
                return self.json({
                    'daily_sales': daily['total'],
                    'daily_bills': daily['bills'],
                    'cash_to_balance': daily['cash_total'],
                    'monthly_sales': round(float(monthly_sales) - float(monthly_returns), 2),
                    'best_selling': best,
                    'low_stock': low,
                    'customer_count': customer_count,
                    'credit_outstanding': max(0, round(float(credit_total), 2)),
                })
            finally:
                con.close()
        if self.path.startswith('/api/daily-report'):
            query=parse_qs(urlparse(self.path).query); day=query.get('date',[datetime.now().strftime('%Y-%m-%d')])[0]; cashier=(query.get('cashier',[''])[0].strip() or None) if self.admin() else self.session()['display_name']; return self.json(daily_report(day, cashier))
        con=db(); parsed=urlparse(self.path)
        if parsed.path == '/api/audit-logs':
            if not self.admin(): con.close(); return self.json({'error':'Admin access required'},403)
            rows=[dict(row) for row in con.execute('SELECT * FROM audit_logs ORDER BY id DESC LIMIT 250')]
            con.close(); return self.json(rows)
        if parsed.path == '/api/stock-movements':
            if not self.admin(): con.close(); return self.json({'error':'Admin access required'},403)
            rows=[dict(row) for row in con.execute('SELECT * FROM stock_movements ORDER BY id DESC LIMIT 250')]
            con.close(); return self.json(rows)
        if parsed.path == '/api/cash-closings':
            query='SELECT * FROM cash_closings'
            params=[]
            if not self.admin():
                query+=' WHERE cashier_name=?'; params.append(self.session()['display_name'])
            rows=[dict(row) for row in con.execute(query+' ORDER BY closing_date DESC, id DESC',params)]
            con.close(); return self.json(rows)
        if parsed.path == '/api/system-status':
            if not self.admin(): con.close(); return self.json({'error':'Admin access required'},403)
            integrity = con.execute('PRAGMA integrity_check').fetchone()[0]
            backups = sorted((DATA_DIR / 'backups').glob('orbix-auto-*.db'), reverse=True)
            con.close(); return self.json({'database':str(DB),'integrity':integrity,'latest_backup':backups[0].name if backups else None})
        if parsed.path.startswith('/api/sales/') and parsed.path.endswith('/items'):
            invoice=parsed.path.split('/')[3]; sale=con.execute("SELECT * FROM sales WHERE invoice=? AND business_context='computer_creative'",(invoice,)).fetchone()
            # A counter operator may re-open only invoices recorded under their
            # own name; administrators can review every invoice.
            if not sale or (not self.admin() and sale['employee_name'] != self.session()['display_name']): con.close(); return self.json({'error':'Invoice not found'},404)
            rows=[]
            for item in con.execute("SELECT si.*, COALESCE(SUM(ri.quantity),0) returned_quantity FROM sale_items si LEFT JOIN return_items ri ON ri.sale_item_id=si.id WHERE si.sale_id=? GROUP BY si.id ORDER BY si.id",(sale['id'],)):
                row=dict(item); row['remaining_quantity']=max(0,row['quantity']-row['returned_quantity']); rows.append(row)
            con.close(); return self.json({'sale':dict(sale),'items':rows})
        if parsed.path=='/api/returns':
            query="SELECT r.*, COUNT(ri.id) item_count FROM returns r LEFT JOIN return_items ri ON ri.return_id=r.id"; params=[]
            if not self.admin(): query+=' WHERE r.processed_by=?'; params.append(self.session()['display_name'])
            result=[dict(x) for x in con.execute(query+' GROUP BY r.id ORDER BY r.id DESC',params)]; con.close(); return self.json(result)
        if parsed.path=='/api/credits':
            query="SELECT s.*, COALESCE(SUM(cp.amount),0) credit_paid FROM sales s LEFT JOIN credit_payments cp ON cp.sale_id=s.id WHERE s.business_context='computer_creative' AND s.method='Credit' AND COALESCE(s.status,'Completed')='Completed'"; params=[]
            if not self.admin(): query+=' AND s.employee_name=?'; params.append(self.session()['display_name'])
            rows=[]
            for row in con.execute(query+' GROUP BY s.id HAVING s.total-s.payment_received-COALESCE(SUM(cp.amount),0)>0.004 ORDER BY s.id DESC',params):
                item=dict(row); item['credit_balance']=round(item['total']-item['payment_received']-item['credit_paid'],2); rows.append(item)
            con.close(); return self.json(rows)
        if parsed.path.startswith('/api/customers/') and parsed.path.endswith('/prices'):
            parts=parsed.path.strip('/').split('/')
            try: customer_id=int(parts[2])
            except (ValueError, IndexError): con.close(); return self.json({'error':'Invalid customer'},400)
            rows=[dict(row) for row in con.execute('SELECT item_type,item_id,price FROM customer_prices WHERE customer_id=?',(customer_id,))]
            con.close(); return self.json(rows)
        table={'/api/products':'products','/api/services':'services','/api/customers':'customers','/api/employees':'employees','/api/sales':'sales','/api/users':'users'}.get(self.path)
        if not table: con.close();return self.json({'error':'Not found'},404)
        if table=='users' and not self.admin(): con.close();return self.json({'error':'Admin access required'},403)
        if table=='users':
            result=[public_user(row) for row in con.execute('SELECT id,username,display_name,role FROM users ORDER BY role,username')];con.close();return self.json(result)
        if table=='sales':
            query="SELECT * FROM sales WHERE business_context='computer_creative'"; params=[]
            if not self.admin(): query+=' AND employee_name=?'; params.append(self.session()['display_name'])
            result=[dict(x) for x in con.execute(query+' ORDER BY id DESC',params)];con.close();return self.json(result)
        if table == 'customers':
            result=[dict(x) for x in con.execute('SELECT * FROM customers ORDER BY id DESC')]
        else:
            query=f'SELECT * FROM {table} '+('WHERE active=1 ' if table=='employees' else '')+'ORDER BY id DESC'
            result=[dict(x) for x in con.execute(query)]
        con.close();self.json(result)
    def do_POST(self):
        # The server repeats important business validation; browser prices,
        # stock values and permissions are never trusted by themselves.
        data=self.body();con=db()
        try:
            if self.path=='/api/login':
                username=data.get('username','').strip(); password=data.get('password','')
                row=con.execute('SELECT * FROM users WHERE username=?',(username,)).fetchone()
                if not row or not password_matches(password,row['password_hash']): raise ValueError('Invalid username or password')
                # Preserve existing accounts while transparently upgrading legacy hashes.
                if not row['password_hash'].startswith('pbkdf2_sha256$'):
                    con.execute('UPDATE users SET password_hash=? WHERE id=?',(password_hash(password),row['id'])); con.commit()
                token=secrets.token_urlsafe(32); SESSIONS[token]={'id':row['id'],'username':row['username'],'display_name':row['display_name'],'role':row['role']}; return self.json({'token':token,'username':row['username'],'display_name':row['display_name'],'role':row['role']})
            if not self.authenticated(): return self.json({'error':'Login required'},403)
            if self.path=='/api/logout':
                SESSIONS.pop(self.headers.get('X-Admin-Token'),None); return self.json({'ok':True})
            if self.path == '/api/backup/restore':
                if not self.admin(): return self.json({'error':'Admin access required'},403)
                encoded = data.get('database','')
                try:
                    uploaded = base64.b64decode(encoded.encode('ascii'), validate=True)
                except Exception:
                    raise ValueError('Select a valid ORBIX database backup file')
                if len(uploaded) < 100 or len(uploaded) > 500 * 1024 * 1024:
                    raise ValueError('The backup file size is invalid')
                restore_file = DATA_DIR / 'restore-upload.db'
                restore_file.write_bytes(uploaded)
                source = sqlite3.connect(restore_file)
                try:
                    if source.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                        raise ValueError('This database backup failed its integrity check')
                    if not source.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='sales'").fetchone():
                        raise ValueError('This is not an ORBIX database backup')
                    con.close()
                    target = sqlite3.connect(DB)
                    source.backup(target)
                    target.close()
                    init()
                finally:
                    source.close()
                    restore_file.unlink(missing_ok=True)
                SESSIONS.clear()
                return self.json({'ok':True,'message':'Backup restored. Please sign in again.'})
            if self.path == '/api/stock-movements':
                if not self.admin(): return self.json({'error':'Admin access required'},403)
                product_id = whole_number(data.get('product_id', 0), 'Product', 1)
                change = whole_number(data.get('quantity_change', 0), 'Quantity change', -1000000, 1000000)
                movement_type = data.get('movement_type', 'Adjustment')
                if change == 0 or movement_type not in ('Stock In', 'Adjustment', 'Damaged'):
                    raise ValueError('Enter a valid stock adjustment')
                product = con.execute('SELECT * FROM products WHERE id=?', (product_id,)).fetchone()
                if not product: raise ValueError('Product not found')
                new_stock = int(product['stock']) + change
                if new_stock < 0: raise ValueError('Stock cannot become negative')
                con.execute('UPDATE products SET stock=? WHERE id=?', (new_stock, product_id))
                reason = required_text(data.get('reason'),'Stock movement reason',250)
                cur = con.execute('INSERT INTO stock_movements(product_id,product_name,quantity_change,stock_after,movement_type,reason,recorded_at,recorded_by) VALUES(?,?,?,?,?,?,?,?)', (product_id,product['name'],change,new_stock,movement_type,reason,datetime.now().strftime('%Y-%m-%d %H:%M'),self.session()['display_name']))
                audit(con,self.session()['display_name'],'Stock adjusted','Product',product_id,f'{movement_type}: {change:+d}; stock now {new_stock}')
                con.commit(); return self.json({'id':cur.lastrowid,'stock':new_stock},201)
            if self.path == '/api/cash-closings':
                closing_date = data.get('date') or datetime.now().strftime('%Y-%m-%d')
                cashier = self.session()['display_name'] if not self.admin() else data.get('cashier','').strip()
                if not cashier: raise ValueError('Select a cashier before closing the counter')
                expected = daily_report(closing_date, cashier)['cash_total']
                counted = money(data.get('counted_cash'), 'Counted cash')
                note = data.get('note','').strip()
                existing = con.execute('SELECT id FROM cash_closings WHERE closing_date=? AND cashier_name=?',(closing_date,cashier)).fetchone()
                if existing: raise ValueError('This cashier already has a closing record for the selected date')
                difference = round(counted - expected, 2)
                cur = con.execute('INSERT INTO cash_closings(closing_date,cashier_name,expected_cash,counted_cash,difference,note,closed_at,closed_by) VALUES(?,?,?,?,?,?,?,?)',(closing_date,cashier,expected,counted,difference,note,datetime.now().strftime('%Y-%m-%d %H:%M'),self.session()['display_name']))
                audit(con,self.session()['display_name'],'Counter closed','Cash closing',cur.lastrowid,f'{cashier}: expected {expected:.2f}, counted {counted:.2f}, difference {difference:.2f}')
                con.commit(); return self.json({'id':cur.lastrowid,'expected_cash':expected,'difference':difference},201)
            if self.path.startswith('/api/sales/') and self.path.endswith('/void'):
                if not self.admin(): return self.json({'error':'Admin access required'},403)
                invoice = self.path.split('/')[3]
                sale = con.execute("SELECT * FROM sales WHERE invoice=? AND business_context='computer_creative'",(invoice,)).fetchone()
                if not sale: raise ValueError('Invoice not found')
                if sale['status'] == 'Voided': raise ValueError('This invoice is already voided')
                if con.execute('SELECT 1 FROM credit_payments WHERE sale_id=? LIMIT 1',(sale['id'],)).fetchone(): raise ValueError('This invoice has collected credit payments and cannot be voided')
                if con.execute("SELECT 1 FROM returns WHERE sale_id=? AND COALESCE(status,'Approved')='Approved'",(sale['id'],)).fetchone(): raise ValueError('An invoice with approved returns cannot be voided')
                reason=data.get('reason','').strip()
                if not reason: raise ValueError('Enter a reason for voiding this invoice')
                for item in con.execute("SELECT * FROM sale_items WHERE sale_id=? AND item_type='product'",(sale['id'],)):
                    con.execute('UPDATE products SET stock=stock+? WHERE id=?',(item['quantity'],item['product_id']))
                    product=con.execute('SELECT stock FROM products WHERE id=?',(item['product_id'],)).fetchone()
                    con.execute('INSERT INTO stock_movements(product_id,product_name,quantity_change,stock_after,movement_type,reason,recorded_at,recorded_by) VALUES(?,?,?,?,?,?,?,?)',(item['product_id'],item['product_name'],item['quantity'],product['stock'],'Invoice Void',reason,datetime.now().strftime('%Y-%m-%d %H:%M'),self.session()['display_name']))
                con.execute("UPDATE sales SET status='Voided',voided_at=?,voided_by=?,void_reason=? WHERE id=?",(datetime.now().strftime('%Y-%m-%d %H:%M'),self.session()['display_name'],reason,sale['id']))
                audit(con,self.session()['display_name'],'Invoice voided','Sale',invoice,reason)
                con.commit(); return self.json({'ok':True})
            if self.path.startswith('/api/returns/') and self.path.endswith('/approve'):
                if not self.admin(): return self.json({'error':'Admin access required'},403)
                return_id = int(self.path.split('/')[3])
                returned = con.execute('SELECT * FROM returns WHERE id=?',(return_id,)).fetchone()
                if not returned: raise ValueError('Return not found')
                if returned['status'] != 'Pending': raise ValueError('This return is already processed')
                for item in con.execute('SELECT * FROM return_items WHERE return_id=?',(return_id,)):
                    con.execute('UPDATE products SET stock=stock+? WHERE id=?',(item['quantity'],item['product_id']))
                    product=con.execute('SELECT stock FROM products WHERE id=?',(item['product_id'],)).fetchone()
                    con.execute('INSERT INTO stock_movements(product_id,product_name,quantity_change,stock_after,movement_type,reason,recorded_at,recorded_by) VALUES(?,?,?,?,?,?,?,?)',(item['product_id'],item['product_name'],item['quantity'],product['stock'],'Return Approved',returned['reason'],datetime.now().strftime('%Y-%m-%d %H:%M'),self.session()['display_name']))
                con.execute("UPDATE returns SET status='Approved',approved_by=?,approved_at=? WHERE id=?",(self.session()['display_name'],datetime.now().strftime('%Y-%m-%d %H:%M'),return_id))
                audit(con,self.session()['display_name'],'Return approved','Return',returned['return_no'],f'Refund {returned["refund_total"]:.2f}')
                con.commit(); return self.json({'ok':True})
            if self.path == '/api/returns':
                invoice=required_text(data.get('invoice'),'Invoice number',40); requested=data.get('items',[]); reason=optional_text(data.get('reason'),'Return reason',250)
                sale=con.execute("SELECT * FROM sales WHERE invoice=? AND business_context='computer_creative'",(invoice,)).fetchone()
                if not sale: raise ValueError('Invoice not found')
                if sale['status'] == 'Voided': raise ValueError('A voided invoice cannot be returned')
                if not requested: raise ValueError('Select at least one product to return')
                # Refund the actual discount on the returned line first, then
                # its fair share of any whole-bill discount. This avoids using
                # a single average discount rate for every product.
                original_lines=con.execute('SELECT quantity,unit_price,COALESCE(line_discount,0) line_discount FROM sale_items WHERE sale_id=?',(sale['id'],)).fetchall()
                saved_line_discounts=sum(float(line['line_discount'] or 0) for line in original_lines)
                bill_discount=max(0, float(sale['discount'] or 0)-saved_line_discounts)
                discounted_subtotal=sum(max(0, float(line['quantity'])*float(line['unit_price'])-float(line['line_discount'] or 0)) for line in original_lines)
                verified=[]; refund_total=0
                for requested_item in requested:
                    quantity=int(requested_item.get('quantity',0)); sale_item_id=int(requested_item.get('sale_item_id',0))
                    if quantity <= 0: continue
                    item=con.execute("SELECT si.*, COALESCE(SUM(ri.quantity),0) returned_quantity FROM sale_items si LEFT JOIN return_items ri ON ri.sale_item_id=si.id WHERE si.id=? AND si.sale_id=? GROUP BY si.id",(sale_item_id,sale['id'])).fetchone()
                    if not item: raise ValueError('Invalid invoice item')
                    if item['item_type']=='service' or item['product_id'] is None: raise ValueError(item['product_name']+' is a service and cannot be returned as stock')
                    remaining=item['quantity']-item['returned_quantity']
                    if quantity>remaining: raise ValueError(item['product_name']+' can only return '+str(remaining)+' unit(s)')
                    line_total=float(item['quantity'])*float(item['unit_price'])
                    item_discount=float(item['line_discount'] or 0)*(quantity/float(item['quantity']))
                    net_line_total=max(0, line_total-float(item['line_discount'] or 0))
                    bill_share=(net_line_total*bill_discount/discounted_subtotal)*(quantity/float(item['quantity'])) if discounted_subtotal else 0
                    refund=round(quantity*float(item['unit_price'])-item_discount-bill_share,2); refund_total+=refund
                    verified.append((item,quantity,refund))
                if not verified: raise ValueError('Select a return quantity')
                return_no=f"RET-{datetime.now():%Y}-{con.execute('SELECT COUNT(*) FROM returns').fetchone()[0]+1:05d}"
                status = 'Approved' if self.admin() else 'Pending'
                approved_by = self.session()['display_name'] if self.admin() else ''
                approved_at = datetime.now().strftime('%Y-%m-%d %H:%M') if self.admin() else ''
                cur=con.execute('INSERT INTO returns(return_no,sale_id,invoice,returned_at,customer_name,processed_by,reason,refund_total,status,approved_by,approved_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)',(return_no,sale['id'],sale['invoice'],datetime.now().strftime('%Y-%m-%d %H:%M'),sale['customer_name'],self.session()['display_name'],reason,refund_total,status,approved_by,approved_at))
                for item,quantity,refund in verified:
                    con.execute('INSERT INTO return_items(return_id,sale_item_id,product_id,product_name,quantity,unit_price,refund_amount) VALUES(?,?,?,?,?,?,?)',(cur.lastrowid,item['id'],item['product_id'],item['product_name'],quantity,item['unit_price'],refund))
                    if status == 'Approved':
                        con.execute('UPDATE products SET stock=stock+? WHERE id=?',(quantity,item['product_id']))
                        product=con.execute('SELECT stock FROM products WHERE id=?',(item['product_id'],)).fetchone()
                        con.execute('INSERT INTO stock_movements(product_id,product_name,quantity_change,stock_after,movement_type,reason,recorded_at,recorded_by) VALUES(?,?,?,?,?,?,?,?)',(item['product_id'],item['product_name'],quantity,product['stock'],'Return Approved',reason,datetime.now().strftime('%Y-%m-%d %H:%M'),self.session()['display_name']))
                audit(con,self.session()['display_name'],'Return '+status.lower(),'Return',return_no,f'Refund {refund_total:.2f}; {reason}')
                con.commit(); return self.json({'id':cur.lastrowid,'return_no':return_no,'refund_total':refund_total,'status':status},201)
            if self.path == '/api/credits/payments':
                invoice=required_text(data.get('invoice'),'Invoice number',40); amount=money(data.get('amount',0),'Payment amount'); method=data.get('method','Cash')
                if amount<=0 or method not in ('Cash','Card'): raise ValueError('Enter a valid Cash or Card payment amount')
                sale=con.execute("SELECT * FROM sales WHERE invoice=? AND method='Credit' AND business_context='computer_creative'",(invoice,)).fetchone()
                if not sale: raise ValueError('Credit invoice not found')
                paid=con.execute('SELECT COALESCE(SUM(amount),0) FROM credit_payments WHERE sale_id=?',(sale['id'],)).fetchone()[0]
                balance=round(sale['total']-sale['payment_received']-paid,2)
                if amount>balance+0.004: raise ValueError('Payment cannot exceed the credit balance of LKR '+f'{balance:,.2f}')
                cur=con.execute('INSERT INTO credit_payments(sale_id,invoice,paid_at,amount,method,received_by,note) VALUES(?,?,?,?,?,?,?)',(sale['id'],invoice,datetime.now().strftime('%Y-%m-%d %H:%M'),amount,method,self.session()['display_name'],data.get('note','').strip()))
                audit(con,self.session()['display_name'],'Credit payment collected','Sale',invoice,f'{method} LKR {amount:.2f}')
                con.commit(); return self.json({'id':cur.lastrowid,'invoice':invoice,'remaining_balance':round(balance-amount,2)},201)
            if self.path.startswith('/api/customers/') and self.path.endswith('/prices'):
                if not self.admin(): return self.json({'error':'Admin access required'},403)
                parts=self.path.strip('/').split('/')
                try: customer_id=int(parts[2])
                except (ValueError, IndexError): raise ValueError('Invalid customer')
                if not con.execute('SELECT 1 FROM customers WHERE id=?',(customer_id,)).fetchone(): raise ValueError('Customer not found')
                entries=data.get('prices',[])
                if not isinstance(entries,list): raise ValueError('Invalid customer prices')
                con.execute('DELETE FROM customer_prices WHERE customer_id=?',(customer_id,))
                for entry in entries:
                    item_type=entry.get('item_type')
                    item_id=int(entry.get('item_id',0))
                    price=money(entry.get('price'),'Customer price')
                    if item_type not in ('product','service') or item_id<1: raise ValueError('Invalid customer price')
                    table='products' if item_type=='product' else 'services'
                    if not con.execute(f'SELECT 1 FROM {table} WHERE id=?',(item_id,)).fetchone(): raise ValueError('Selected item no longer exists')
                    con.execute('INSERT INTO customer_prices(customer_id,item_type,item_id,price) VALUES(?,?,?,?)',(customer_id,item_type,item_id,price))
                con.commit(); return self.json({'ok':True,'count':len(entries)})
            if self.path == '/api/users':
                if not self.admin(): return self.json({'error':'Admin access required'},403)
                username=data.get('username','').strip(); display_name=required_text(data.get('display_name',''),'Full name'); password=data.get('password','')
                role=data.get('role','counter').lower()
                if not valid_username(username): raise ValueError('Username must use 3-40 letters, numbers, dots, hyphens or underscores')
                if role not in ('admin','counter'): raise ValueError('Invalid user role')
                cur=con.execute('INSERT INTO users(username,password_hash,role,display_name) VALUES(?,?,?,?)',(username,password_hash(password),role,display_name)); res=public_user(con.execute('SELECT * FROM users WHERE id=?',(cur.lastrowid,)).fetchone())
                con.commit(); return self.json(res,201)
            if self.path in ('/api/products','/api/services','/api/employees') and not self.admin(): return self.json({'error':'Admin login required'},403)
            if self.path=='/api/products':
                name=required_text(data.get('name'),'Product name'); sku=valid_code(data.get('sku'),'SKU / barcode'); price=money(data.get('price'),'Product price'); wholesale=money(data.get('wholesale_price') or price,'Wholesale price'); stock=whole_number(data.get('stock'),'Stock'); warranty=required_text(data.get('warranty','90 Days'),'Warranty',80)
                if price == 0: raise ValueError('Product price must be greater than zero')
                cur=con.execute('INSERT INTO products(name,sku,category,price,wholesale_price,stock,warranty) VALUES(?,?,?,?,?,?,?)',(name,sku,canonical_category(con,data.get('category','General')),price,wholesale,stock,warranty));res=dict(con.execute('SELECT * FROM products WHERE id=?',(cur.lastrowid,)).fetchone())
            elif self.path=='/api/services':
                name=required_text(data.get('name'),'Service name'); code=valid_code(data.get('code'),'Service code'); price=money(data.get('price'),'Service price'); wholesale=money(data.get('wholesale_price') or price,'Wholesale price')
                if price == 0: raise ValueError('Service price must be greater than zero')
                cur=con.execute('INSERT INTO services(name,code,price,wholesale_price,duration) VALUES(?,?,?,?,?)',(name,code,price,wholesale,optional_text(data.get('duration'),'Estimated duration',120)));res=dict(con.execute('SELECT * FROM services WHERE id=?',(cur.lastrowid,)).fetchone())
            elif self.path=='/api/customers':
                name=required_text(data.get('name'),'Customer name')
                phone=optional_phone(data.get('phone',''))
                duplicate=customer_duplicate(con,name,phone)
                if duplicate: raise ValueError(f'Customer already exists: {duplicate["name"]}{" — " + duplicate["phone"] if duplicate["phone"] else ""}. Search and select that customer instead.')
                cur=con.execute('INSERT INTO customers(name,phone,vehicle,email) VALUES(?,?,?,?)',(name,phone,optional_text(data.get('vehicle'),'Device / job reference',120),optional_email(data.get('email',''))));res=dict(con.execute('SELECT * FROM customers WHERE id=?',(cur.lastrowid,)).fetchone())
            elif self.path=='/api/employees':
                cur=con.execute('INSERT INTO employees(name,role,phone) VALUES(?,?,?)',(required_text(data.get('name'),'Employee name'),canonical_employee_role(con,data.get('role','')),optional_phone(data.get('phone',''))));res=dict(con.execute('SELECT * FROM employees WHERE id=?',(cur.lastrowid,)).fetchone())
            elif self.path=='/api/sales':
                requested_items=data.get('items',[])
                if not isinstance(requested_items,list) or not requested_items: raise ValueError('Add at least one product or service to the bill')
                if len(requested_items)>100: raise ValueError('A bill cannot contain more than 100 line items')
                # A bill is always linked to a saved customer.  Resolve the ID
                # here rather than trusting a previously displayed name.
                try:
                    customer_id = int(data.get('customer_id'))
                except (TypeError, ValueError):
                    raise ValueError('Select or add a customer before creating a bill')
                customer = con.execute('SELECT id,name FROM customers WHERE id=?', (customer_id,)).fetchone()
                if not customer:
                    raise ValueError('The selected customer no longer exists. Select or add a customer again.')
                verified_items=[]; subtotal=0; line_discount_total=0
                for item in requested_items:
                    try: quantity=int(item.get('qty',0))
                    except (TypeError,ValueError): raise ValueError('Each item quantity must be a whole number')
                    if quantity < 1 or quantity > 999: raise ValueError('Item quantity must be between 1 and 999')
                    if item.get('type') == 'service':
                        service=con.execute('SELECT * FROM services WHERE id=? AND active=1',(item.get('service_id'),)).fetchone()
                        if not service: raise ValueError('Selected service is unavailable')
                        price = customer_item_price(con, customer['id'], 'service', service['id'], service['price'])
                        verified_items.append({'id':None,'name':service['name'],'quantity':quantity,'price':money(price,'Service price'),'type':'service','warranty':'-'})
                    else:
                        product=con.execute('SELECT * FROM products WHERE id=?',(item.get('id'),)).fetchone()
                        if not product: raise ValueError('Selected product is unavailable')
                        if product['stock'] < quantity: raise ValueError('Insufficient stock for '+product['name'])
                        price = customer_item_price(con, customer['id'], 'product', product['id'], product['price'])
                        verified_items.append({'id':product['id'],'name':product['name'],'quantity':quantity,'price':money(price,'Product price'),'type':'product','warranty':product['warranty'] or '90 Days'})
                    line_total=verified_items[-1]['price']*quantity
                    line_type=item.get('line_discount_type','percent')
                    if line_type not in ('percent','amount'): raise ValueError('Invalid item discount type')
                    line_value=money(item.get('line_discount_value',0),'Item discount')
                    line_discount=min(line_total, line_total*min(line_value,100)/100 if line_type=='percent' else line_value)
                    verified_items[-1]['line_discount']=round(line_discount,2)
                    subtotal+=line_total; line_discount_total+=verified_items[-1]['line_discount']
                subtotal=round(subtotal,2)
                bill_discount=money(data.get('discount',0),'Bill discount')
                if bill_discount>subtotal-line_discount_total: raise ValueError('Bill discount cannot exceed the remaining subtotal')
                discount=round(line_discount_total+bill_discount,2)
                total=round(subtotal-discount,2)
                method=data.get('method','Cash')
                if method not in ('Cash','Card','Credit'): raise ValueError('Select a valid payment method')
                received=money(data.get('payment_received',total),'Payment received')
                if method=='Cash':
                    if received<total: raise ValueError('Cash received must be equal to or greater than the total')
                    change=round(received-total,2)
                elif method=='Card':
                    received=total; change=0
                else:
                    if received>=total: raise ValueError('Credit payment must be less than the bill total')
                    change=0
                invoice=f"INV-{datetime.now():%Y}-{con.execute('SELECT COUNT(*) FROM sales').fetchone()[0]+128:05d}"
                cashier=self.session()['display_name'] if self.session()['role']=='counter' else data.get('employee_name','').strip()
                if not cashier: raise ValueError('Select a cashier before completing this sale')
                if self.session()['role']=='admin' and not con.execute('SELECT 1 FROM employees WHERE name=? AND active=1',(cashier,)).fetchone():
                    raise ValueError('Select an active cashier from the employee list')
                cur=con.execute('INSERT INTO sales(invoice,sold_at,customer_id,customer_name,employee_name,method,subtotal,discount,tax,total,payment_received,payment_change,business_context) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',(invoice,datetime.now().strftime('%Y-%m-%d %H:%M'),customer['id'],customer['name'],cashier,method,subtotal,discount,0,total,received,change,'computer_creative'))
                for item in verified_items:
                    if item['type'] == 'product':
                        con.execute('UPDATE products SET stock=stock-? WHERE id=?',(item['quantity'],item['id']))
                        product=con.execute('SELECT stock FROM products WHERE id=?',(item['id'],)).fetchone()
                        con.execute('INSERT INTO stock_movements(product_id,product_name,quantity_change,stock_after,movement_type,reason,recorded_at,recorded_by) VALUES(?,?,?,?,?,?,?,?)',(item['id'],item['name'],-item['quantity'],product['stock'],'Sale',invoice,datetime.now().strftime('%Y-%m-%d %H:%M'),cashier))
                    con.execute('INSERT INTO sale_items(sale_id,product_id,product_name,quantity,unit_price,item_type,warranty,line_discount) VALUES(?,?,?,?,?,?,?,?)',(cur.lastrowid,item['id'],item['name'],item['quantity'],item['price'],item['type'],item['warranty'],item['line_discount']))
                audit(con,self.session()['display_name'],'Invoice completed','Sale',invoice,f'Customer: {customer["name"]}; total LKR {total:.2f}')
                res={'id':cur.lastrowid,'invoice':invoice,'subtotal':subtotal,'discount':discount,'total':total,'payment_received':received,'payment_change':change}
            else: raise LookupError()
            con.commit();self.json(res,201)
        except (KeyError,ValueError,RuntimeError,sqlite3.IntegrityError) as e: con.rollback();self.json({'error':str(e)},400)
        except LookupError: self.json({'error':'Not found'},404)
        finally: con.close()

    def do_PUT(self):
        if not self.admin(): return self.json({'error':'Admin login required'},403)
        data=self.body(); parts=self.path.strip('/').split('/')
        if len(parts)!=3 or parts[0]!='api' or parts[1] not in ('products','services','customers','employees','users'): return self.json({'error':'Not found'},404)
        table,ident=parts[1],parts[2]; con=db()
        try:
            if table=='users':
                target=con.execute('SELECT * FROM users WHERE id=?',(ident,)).fetchone()
                if not target: raise ValueError('User account not found')
                username=data.get('username','').strip(); display_name=required_text(data.get('display_name',''),'Full name'); role=data.get('role','counter').lower(); password=data.get('password','')
                if not valid_username(username): raise ValueError('Username must use 3-40 letters, numbers, dots, hyphens or underscores')
                if role not in ('admin','counter'): raise ValueError('Invalid user role')
                if self.session()['id']==target['id'] and role!='admin': raise ValueError('You cannot remove your own admin privilege')
                con.execute('UPDATE users SET username=?,display_name=?,role=? WHERE id=?',(username,display_name,role,ident))
                if password:
                    con.execute('UPDATE users SET password_hash=? WHERE id=?',(password_hash(password),ident))
                con.commit(); revoke_user_sessions(target['id'],self.headers.get('X-Admin-Token')); return self.json({'ok':True})
            if table=='products':
                name=required_text(data.get('name'),'Product name'); sku=valid_code(data.get('sku'),'SKU / barcode'); price=money(data.get('price'),'Product price'); wholesale=money(data.get('wholesale_price') or price,'Wholesale price'); stock=whole_number(data.get('stock'),'Stock'); warranty=required_text(data.get('warranty','90 Days'),'Warranty',80)
                if price == 0: raise ValueError('Product price must be greater than zero')
                con.execute('UPDATE products SET name=?,sku=?,category=?,price=?,wholesale_price=?,stock=?,warranty=? WHERE id=?',(name,sku,canonical_category(con,data.get('category','General')),price,wholesale,stock,warranty,ident))
            elif table=='services':
                name=required_text(data.get('name'),'Service name'); code=valid_code(data.get('code'),'Service code'); price=money(data.get('price'),'Service price'); wholesale=money(data.get('wholesale_price') or price,'Wholesale price')
                if price == 0: raise ValueError('Service price must be greater than zero')
                con.execute('UPDATE services SET name=?,code=?,price=?,wholesale_price=?,duration=? WHERE id=?',(name,code,price,wholesale,optional_text(data.get('duration'),'Estimated duration',120),ident))
            elif table=='customers':
                name=required_text(data.get('name'),'Customer name'); phone=optional_phone(data.get('phone',''))
                duplicate=customer_duplicate(con,name,phone,ident)
                if duplicate: raise ValueError(f'Customer already exists: {duplicate["name"]}{" — " + duplicate["phone"] if duplicate["phone"] else ""}.')
                con.execute('UPDATE customers SET name=?,phone=?,vehicle=?,email=? WHERE id=?',(name,phone,optional_text(data.get('vehicle'),'Device / job reference',120),optional_email(data.get('email','')),ident))
            else: con.execute('UPDATE employees SET name=?,role=?,phone=? WHERE id=?',(required_text(data.get('name'),'Employee name'),canonical_employee_role(con,data.get('role','')),optional_phone(data.get('phone','')),ident))
            con.commit();self.json({'ok':True})
        except (KeyError,ValueError,sqlite3.IntegrityError) as e: con.rollback();self.json({'error':str(e)},400)
        finally: con.close()

    def do_DELETE(self):
        # User deletion preserves at least one administrator to prevent an
        # installation from being permanently locked out of management access.
        if not self.admin(): return self.json({'error':'Admin login required'},403)
        parts=self.path.strip('/').split('/')
        if len(parts)!=3 or parts[0]!='api' or parts[1] not in ('products','services','customers','employees','users'): return self.json({'error':'Not found'},404)
        con=db();table,ident=parts[1],parts[2]
        try:
            if table=='users':
                target=con.execute('SELECT * FROM users WHERE id=?',(ident,)).fetchone()
                if not target: raise ValueError('User account not found')
                if self.session()['id']==target['id']: raise ValueError('You cannot delete your own account')
                if target['role']=='admin' and con.execute("SELECT COUNT(*) FROM users WHERE role='admin'").fetchone()[0] <= 1: raise ValueError('At least one admin account must remain')
                con.execute('DELETE FROM users WHERE id=?',(ident,));con.commit();revoke_user_sessions(target['id']);return self.json({'ok':True})
            if table == 'products' and (con.execute('SELECT 1 FROM sale_items WHERE product_id=? LIMIT 1',(ident,)).fetchone() or con.execute('SELECT 1 FROM stock_movements WHERE product_id=? LIMIT 1',(ident,)).fetchone()):
                raise ValueError('This product has sales or stock history and cannot be deleted. Edit it instead.')
            if table == 'services' and con.execute("SELECT 1 FROM sale_items WHERE item_type='service' AND product_name=(SELECT name FROM services WHERE id=?) LIMIT 1",(ident,)).fetchone():
                raise ValueError('This service has sales history and cannot be deleted. Edit it instead.')
            if table == 'customers' and con.execute('SELECT 1 FROM sales WHERE customer_id=? LIMIT 1',(ident,)).fetchone():
                raise ValueError('This customer has invoice history and cannot be deleted. Edit it instead.')
            if table == 'employees' and con.execute('SELECT 1 FROM sales WHERE employee_name=(SELECT name FROM employees WHERE id=?) LIMIT 1',(ident,)).fetchone():
                raise ValueError('This employee has sales history and cannot be deleted. Set them inactive instead.')
            if table=='customers': con.execute('DELETE FROM customer_prices WHERE customer_id=?',(ident,))
            con.execute(f'DELETE FROM {table} WHERE id=?',(ident,));audit(con,self.session()['display_name'],'Record deleted',table.title(),ident,'Deleted from management screen');con.commit();self.json({'ok':True})
        except (ValueError,sqlite3.IntegrityError) as e: con.rollback();self.json({'error':str(e) if isinstance(e,ValueError) else 'This record is in use and cannot be deleted'},400)
        finally: con.close()

if __name__=='__main__':
    init();print(f'{APP_NAME}: http://localhost:8080');ThreadingHTTPServer(('',8080),Handler).serve_forever()
