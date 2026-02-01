SwiftServe v3 — PGAdmin (psycopg2) • Swiggy-like UI • Real-time Updates • Dual Video Modes
==========================================================================================

SwiftServe is a full-stack food delivery application featuring real-time order tracking and a modern UI.

Features:
- Customer, Restaurant, and Delivery Agent roles.
- Real-time order status updates using Flask-SocketIO.
- Dual video modes (Online URLs or Local storage).
- Responsive Swiggy-like interface.

Setup Instructions:
1) Database Setup:
   - Create a PostgreSQL database named `swiftserve`.
   - Run the provided `db.sql` script in pgAdmin or your preferred SQL client.

2) Configuration:
   - Edit the DB connection details at the top of `app.py` (DB_HOST, DB_NAME, DB_USER, DB_PASS, etc.).
   - Alternatively, use environment variables.

3) Install Dependencies:
   pip install -r requirements.txt

4) Run the Application:
   python app.py

5) Access:
   Open http://localhost:5000 in your browser.

Video Modes:
- Online Mode (Default): Uses URLs from `menu_items.video_url` (Set VIDEO_SOURCE_MODE=online).
- Local Mode: Set VIDEO_SOURCE_MODE=local, upload .mp4 files to `static/uploads`, and set `menu_items.video_path`.
