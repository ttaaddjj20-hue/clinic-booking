from flask import Flask, render_template, request, redirect, session, flash
import sqlite3
from datetime import datetime
import qrcode
import io
import os
import base64




app = Flask(__name__)
app.secret_key = "secret123"
DB = "database.db"

ADMIN_PASSWORD = "1234"

EXAM_PRICES = {
    "Scanner": 7000,
    "Échographie": 3000,
    "Radiographie": 2000,
    "Mammographie": 5000,
    "Panoramique": 2500
}
EXAM_LIMITS = {
    "Échographie": 2,
    "Mammographie": 1,
    "Scanner": 2,
    "Radiographie": None,   # غير محدود
    "Panoramique": None     # غير محدود
}
# ================== INIT DATABASE ==================

def init_db():
    conn = sqlite3.connect(DB)
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS bookings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        fullname TEXT,
        phone TEXT,
        exam TEXT,
        created_at TEXT,
        price REAL DEFAULT 0,
        paid REAL DEFAULT 0,
        remaining REAL DEFAULT 0
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS exam_types (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        exam_name TEXT,
        subtype TEXT,
        price REAL
    )
    """)

    try:
        cur.execute("ALTER TABLE bookings ADD COLUMN price REAL DEFAULT 0")
        cur.execute("ALTER TABLE bookings ADD COLUMN paid REAL DEFAULT 0")
        cur.execute("ALTER TABLE bookings ADD COLUMN remaining REAL DEFAULT 0")
    except:
        pass
    try:
        cur.execute("ALTER TABLE bookings ADD COLUMN status TEXT DEFAULT 'pending'")
    except:
        pass
    cur.execute("SELECT COUNT(*) FROM exam_types")
    if cur.fetchone()[0] == 0:

        data = [
            ("Scanner", "Brain", 7000),
            ("Scanner", "Abdomen", 6500),
            ("Scanner", "Thorax", 6000),

            ("Radiographie", "Standard", 2000),
            ("Radiographie", "Spine", 3000),

            ("Échographie", "Échographie Abdominal", 3000),
            ("Échographie", "Échographie Pelvic", 3500)
        ]

        cur.executemany(
            "INSERT INTO exam_types(exam_name, subtype, price) VALUES (?, ?, ?)",
            data
        )

    conn.commit()
    conn.close()


# ================== CHECK TIME (6 - 8) ==================
def is_open():
    now = datetime.now()
    return 6 <= now.hour < 24


# ================== COUNT TODAY ==================
def count_today():
    conn = sqlite3.connect(DB)
    cur = conn.cursor()

    today = datetime.now().date().isoformat()

    cur.execute("""
        SELECT COUNT(*) FROM bookings
        WHERE date(created_at)=?
    """, (today,))

    count = cur.fetchone()[0]
    conn.close()

    return count


# ================== HOME PAGE ==================
@app.route("/")
def index():
    return render_template(
        "index.html",
        open=is_open(),
        count=count_today()
    )


# ================== BOOKING ==================
@app.route("/book", methods=["POST"])
def book():

    # إذا الوقت مغلق
    if not is_open():
        return "❌ الحجز مغلق (من 06:00 إلى 08:00)"

    

    fullname = request.form["fullname"]
    phone = request.form["phone"]
    exam = request.form["exam"]

    limit = EXAM_LIMITS.get(exam)

    if limit is not None:
        conn = sqlite3.connect(DB)
        cur = conn.cursor()

        today = datetime.now().date().isoformat()

        cur.execute("""
            SELECT COUNT(*) FROM bookings
            WHERE exam=? AND date(created_at)=?
        """, (exam, today))

        count = cur.fetchone()[0]
        conn.close()

        if count >= limit:
            return f"❌ تم الوصول للحد الأقصى لهذا الفحص ({exam})"
    subtype = request.form.get("subtype", None)
    conn = sqlite3.connect(DB)

    cur = conn.cursor()

    cur.execute("""
        SELECT price FROM exam_types
        WHERE exam_name=? AND subtype=?
    """, (exam, subtype))

    result = cur.fetchone()
    price = result[0] if result else 0

    try:
        paid = float(request.form.get("paid", 0))
    except:
        paid = 0

    remaining = price - paid
    now = datetime.now().isoformat(sep=" ")

    

    cur.execute("""
        INSERT INTO bookings(fullname, phone, exam, created_at, status, price, paid, remaining)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (fullname, phone, exam, now, "pending", price, paid, remaining))

    conn.commit()
    conn.close()

    flash("✅ تم إرسال طلبك بنجاح، سيتم الاتصال بك لاحقًا")
    return redirect("/")

@app.route("/stats")
def stats():
    conn = sqlite3.connect(DB)
    cur = conn.cursor()

    cur.execute("""
        SELECT exam, COUNT(*)
        FROM bookings
        GROUP BY exam
    """)

    data = cur.fetchall()
    conn.close()

    return render_template("stats.html", data=data)
def get_exam_usage():
    conn = sqlite3.connect(DB)
    cur = conn.cursor()

    today = datetime.now().date().isoformat()

    cur.execute("""
        SELECT exam, COUNT(*)
        FROM bookings
        WHERE date(created_at)=?
        GROUP BY exam
    """, (today,))

    data = dict(cur.fetchall())
    conn.close()
    return data



# ================== ADMIN PANEL ==================
@app.route("/admin-login", methods=["GET", "POST"])
def admin_login():

    # إذا مسجل دخول مسبقاً
    if session.get("admin"):
        return redirect("/admin-dashboard")

    if request.method == "POST":
        password = request.form["password"]

        if password == ADMIN_PASSWORD:
            session["admin"] = True
            return redirect("/admin-dashboard")

        return "❌ كلمة السر خاطئة"

    return '''
    <form method="POST">
        <input type="password" name="password" placeholder="Password">
        <button>دخول</button>
    </form>
    '''
  
@app.route("/admin-dashboard")
def admin_dashboard():

    if not session.get("admin"):
        return redirect("/admin-login")

    conn = sqlite3.connect(DB)
    cur = conn.cursor()

    # 🧾 كل الحجوزات
    today = datetime.now().date().isoformat()

    cur.execute("""
        SELECT * FROM bookings
        WHERE date(created_at)=?
        ORDER BY created_at DESC
    """, (today,))
    bookings = cur.fetchall()

    # 📊 الإحصائيات
    cur.execute("""
        SELECT exam, COUNT(*)
        FROM bookings
        WHERE date(created_at)=?
        GROUP BY exam
    """, (today,))
    stats = cur.fetchall()

    conn.close()
    usage = get_exam_usage()


    return render_template("admin.html", bookings=bookings, usage=usage)
def logout():
    session.pop("admin", None)
    return redirect("/admin-login")
@app.route("/delete/<int:id>")
def delete(id):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("DELETE FROM bookings WHERE id=?", (id,))
    conn.commit()
    conn.close()
    return redirect("/admin-login")
@app.route("/edit/<int:id>", methods=["GET", "POST"])
def edit(id):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()

    if request.method == "POST":
        fullname = request.form["fullname"]
        phone = request.form["phone"]
        exam = request.form["exam"]

        cur.execute("""
            UPDATE bookings
            SET fullname=?, phone=?, exam=?
            WHERE id=?
        """, (fullname, phone, exam, id))

        conn.commit()
        conn.close()

        return redirect("/admin-login")

    # GET: عرض البيانات داخل النموذج
    cur.execute("SELECT * FROM bookings WHERE id=?", (id,))
    data = cur.fetchone()
    conn.close()

    return render_template("edit.html", b=data)
@app.route("/status/<int:id>/<state>")
def change_status(id, state):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()

    cur.execute("""
        UPDATE bookings
        SET status=?
        WHERE id=?
    """, (state, id))

    conn.commit()
    conn.close()

    return redirect("/admin-dashboard")
@app.route("/search", methods=["GET"])
def search():
    query = request.args.get("q", "")

    conn = sqlite3.connect(DB)
    cur = conn.cursor()

    cur.execute("""
        SELECT * FROM bookings
        WHERE fullname LIKE ?
        OR phone LIKE ?
        ORDER BY created_at DESC
    """, (f"%{query}%", f"%{query}%"))

    results = cur.fetchall()
    conn.close()

    return render_template("search.html", results=results, query=query)
@app.route("/patient/<int:id>")
def patient_profile(id):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()

    # معلومات المريض
    cur.execute("SELECT * FROM bookings WHERE id=?", (id,))
    patient = cur.fetchone()

    # كل زياراته (نفس المريض حسب الاسم أو الهاتف)
    cur.execute("""
        SELECT * FROM bookings
        WHERE phone = ?
        ORDER BY created_at DESC
    """, (patient[2],))

    history = cur.fetchall()

    conn.close()

    return render_template("patient.html", patient=patient, history=history)
@app.route("/new-visit/<int:id>", methods=["GET", "POST"])
def new_visit(id):

    conn = sqlite3.connect(DB)
    cur = conn.cursor()

    # جلب معلومات المريض
    cur.execute("SELECT * FROM bookings WHERE id=?", (id,))
    patient = cur.fetchone()

    if request.method == "POST":

        exam = request.form["exam"]
        now = datetime.now().isoformat(sep=" ")

        cur.execute("""
            INSERT INTO bookings(fullname, phone, exam, created_at, status)
            VALUES (?, ?, ?, ?, ?)
        """, (
            patient[1],
            patient[2],
            exam,
            now,
            "pending"
        ))

        conn.commit()
        conn.close()

        return redirect(f"/patient/{id}")

    conn.close()

    return render_template("new_visit.html", patient=patient)
@app.route("/update-payment/<int:id>", methods=["POST"])
def update_payment(id):
    price = float(request.form.get("price", 0))
    paid = float(request.form.get("paid", 0))
    remaining = price - paid

    conn = sqlite3.connect(DB)
    cur = conn.cursor()

    cur.execute("""
        UPDATE bookings
        SET price=?, paid=?, remaining=?
        WHERE id=?
    """, (price, paid, remaining, id))

    conn.commit()
    conn.close()

    return "OK"
@app.route("/get-subtypes")
def get_subtypes():
    exam = request.args.get("exam")

    conn = sqlite3.connect(DB)
    cur = conn.cursor()

    cur.execute("""
        SELECT subtype FROM exam_types
        WHERE exam_name=?
    """, (exam,))

    data = [row[0] for row in cur.fetchall()]
    conn.close()

    return {"subtypes": data}
@app.route("/set-exam/<int:id>", methods=["GET", "POST"])
def set_exam(id):

    conn = sqlite3.connect(DB)
    cur = conn.cursor()

    cur.execute("SELECT * FROM bookings WHERE id=?", (id,))
    booking = cur.fetchone()
    cur.execute("""
        SELECT subtype, price
        FROM exam_types
        WHERE exam_name=?
    """, (booking[3],))

    exams = cur.fetchall()

    if request.method == "POST":

        subtype = request.form["subtype"]
        price = float(request.form["price"])

        cur.execute("""
            UPDATE bookings
            SET exam=?, price=?, remaining=price-paid
            WHERE id=?
        """, (subtype, price, id))

        conn.commit()
        conn.close()

        return redirect("/admin-dashboard")

    conn.close()

    return render_template("set_exam.html", b=booking, exams=exams)


@app.route("/print/<int:id>")
def print_receipt(id):

    conn = sqlite3.connect(DB)
    cur = conn.cursor()

    cur.execute("SELECT * FROM bookings WHERE id=?", (id,))
    b = cur.fetchone()
    conn.close()

    # تجهيز البيانات
    text = f"""
Clinique El Harrach Radiologie
Nom: {b[1]}
Téléphone: {b[2]}
Examen: {b[3]}
Prix: {b[5]}
Payé: {b[6]}
Restant: {b[7]}
"""

    # QR Code
    qr = qrcode.make(text)
    buf = io.BytesIO()
    qr.save(buf, format="PNG")
    qr_b64 = base64.b64encode(buf.getvalue()).decode()

    return render_template("receipt.html", b=b, qr=qr_b64)
@app.route("/print-direct/<int:id>")
def print_direct(id):

    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("SELECT * FROM bookings WHERE id=?", (id,))
    b = cur.fetchone()
    conn.close()

    # توليد QR
    qr_data = f"""
Clinique El Harrach
Nom: {b[1]}
Tel: {b[2]}
Examen: {b[3]}
Prix: {b[5]}
Payé: {b[6]}
Restant: {b[7]}
"""

    qr = qrcode.make(qr_data)
    buf = io.BytesIO()
    qr.save(buf, format="PNG")

    qr_img = buf.getvalue()

    # حفظ QR مؤقتاً
    with open("qr_temp.png", "wb") as f:
        f.write(qr_img)

    # نص الطباعة
    text = f"""
Clinique El Harrach Radiologie

Nom: {b[1]}
Tel: {b[2]}
Examen: {b[3]}

Prix: {b[5]}
Payé: {b[6]}
Restant: {b[7]}

Merci pour votre visite
"""

    print_receipt_text(text)

    flash("🖨️ تم الطباعة بنجاح")
    return redirect(f"/print/{id}")

    
# ================== START SERVER ==================


if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)