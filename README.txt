SwiftServe v3 — PGAdmin (psycopg2) • Swiggy-like UI • BOTH video modes
=====================================================================
1) Create DB `swiftserve_db` and run db.sql in pgAdmin.
2) Edit DB_* at the top of app.py (DB_PASS etc.).
3) pip install -r requirements.txt
4) python app.py
5) Open http://localhost:5000

Videos:
- Default uses ONLINE URLs in menu_items.video_url (VIDEO_SOURCE_MODE=online).
- To use LOCAL .mp4s, set VIDEO_SOURCE_MODE=local and upload .mp4 into static/uploads,
  then set menu_items.video_path (e.g., 'uploads/myclip.mp4').
