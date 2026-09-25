# ORBIX Technologies POS

Local database-backed POS for computer parts, repairs, photo-frame work and graphic design services.

## Install as a Windows application (recommended)

On the Windows 10/11 PC, install these free tools once:

1. [Python 3](https://www.python.org/downloads/windows/) — select **Add Python to PATH** during setup.
2. [Inno Setup 7](https://jrsoftware.org/isdl.php) — required only to create the installer. Inno Setup 6 is also supported.

Then open this project folder and double-click:

```text
create_installer.bat
```

It creates two installable files:

```text
release\ORBIX-Technologies-POS-Setup.exe
release\ORBIX-Technologies-IT-Setup.exe
```

Copy the required setup file(s) to the shop PC. Run the POS setup for **ORBIX Technologies POS**, and run the IT setup for **ORBIX Technologies (IT)**. Each opens from its own Start menu or desktop shortcut; no Chrome tab or localhost address is needed.

The two installers create independent applications on the same PC:

- **ORBIX Technologies POS** — data is saved in `D:\ORBIX Technologies POS\orbix.db`.
- **ORBIX Technologies (IT)** — data is saved in `D:\ORBIX Technologies IT\orbix.db`.

They can run at the same time and their products, customers, sales and user
accounts do not mix. The IT edition starts with its own new database and has
the same POS, management and reporting features.

The installed desktop app uses the modern **Microsoft Edge WebView2 Runtime**.
Install it once on the Windows 10/11 computer before opening the app. This
prevents the obsolete Internet Explorer renderer from showing a non-working page.

## If the installed app does not open

1. Install the Microsoft Edge WebView2 Runtime, then restart Windows.
2. Open the app again from the Start menu.
3. If it still does not open, send the file below to support; it contains the
   exact startup error:

```text
D:\ORBIX Technologies POS\startup-error.log
```

The sales database is stored safely outside the installed application in:

```text
D:\ORBIX Technologies POS\
```

If the PC has no usable D: drive, the application falls back to
`%LOCALAPPDATA%\ORBIX Technologies POS\`.

Upgrading or uninstalling the application does not delete that database.

## Run without installing

For a desktop window without making an installer, double-click `run_windows_app.bat`.

To create portable application folders only, run `build_windows.bat`. The output is:

```text
dist\ORBIX Technologies POS\ORBIX Technologies POS.exe
dist\ORBIX Technologies IT\ORBIX Technologies IT.exe
```

After changing the project source code, run `create_installer.bat` again and
install the newly created POS and/or IT setup file. Older setup files do not
contain the new screen or application fixes.

## Upgrade an existing shop PC without losing data

1. Close **ORBIX Technologies POS** on the shop PC.
2. Make a safety copy of the existing `orbix.db` file to a USB drive.
3. Run the new `ORBIX-Technologies-POS-Setup.exe` on that same PC and choose
   the existing installation when Windows asks. If the IT edition is installed,
   run `ORBIX-Technologies-IT-Setup.exe` as well. Each setup replaces only its
   own application files; neither replaces the live database.
4. Open ORBIX POS. If the old database is already in
   `D:\ORBIX Technologies POS\orbix.db`, no copy is needed.
5. If the old version used the C: drive instead, copy its `orbix.db` to
   `D:\ORBIX Technologies POS\orbix.db` **only when that destination does not
   already contain the shop's newer database**. The first launch also imports
   the legacy `%LOCALAPPDATA%\ORBIX Technologies POS\orbix.db` automatically
   when D: has no database.

Never copy a database while ORBIX POS is open. Keep the USB backup until the
new installation has opened and the products, customers and recent invoices
have been checked.

## First login

- Administrator: `admin` / `Admin@123`
- Counter operator: `counter` / `Counter@123`

Change these default passwords from **User Accounts** before using the system for daily business.

## Safety and daily use

- Back up the SQLite database from **Dashboard → Database Backup** every day.
- The app also creates one automatic SQLite-safe backup each day in
  `D:\ORBIX Technologies POS\backups\`. Use **Operations → Restore Backup**
  only after confirming that the selected backup is the correct shop database.
- The installed app stores `orbix.db` in `D:\ORBIX Technologies POS\`; it contains all products, customers, sales, returns and credit payments.
- Always close the server with `Ctrl + C` before copying the database file.
- Credit bills require a named customer, so the outstanding balance can be collected later.
- Prices, stock, payment totals and discounts are verified by the server when a bill is saved.

## Professional controls

- **Counter Closing** compares the cash counted by a cashier with the system’s
  expected cash balance and keeps a permanent closing record.
- **Operations** gives administrators inventory movement history, pending
  return approval, audit activity, database integrity status, and backup restore.
- A counter-created return stays pending until an administrator approves it;
  only then are stock and daily return figures updated.
- Administrators can void an invoice with a reason. This restores product stock
  and excludes the voided invoice from sales and daily reports.

## Printing invoices

The POS uses the normal Windows print dialog for the PC printer already connected
to the computer. Select **A4 Invoice** or **A5 Invoice** before confirming a
payment, then choose the installed printer in the Windows print dialog. No cash
drawer, thermal printer, barcode scanner or QR reader setup is required.

Each invoice includes an offline-generated QR code containing its invoice
reference. It is included automatically in every new setup build.

## Files in the Windows desktop app

- **Download PDF**, **Export CSV** and **Database Backup** save files directly
  to the signed-in Windows user's `Downloads` folder.
- **Confirm Payment & Print Receipt** opens the completed A4/A5 invoice in the
  default Windows browser, where the normal printer dialog is shown.
