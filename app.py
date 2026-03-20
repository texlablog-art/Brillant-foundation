import os
import random
import string
import datetime
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from flask_pymongo import PyMongo
from werkzeug.utils import secure_filename
from bson.objectid import ObjectId
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv
from datetime import datetime
import base64
import requests

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY")
app.config["MONGO_URI"] = os.getenv("MONGO_URI")
app.config['UPLOAD_FOLDER'] = os.getenv("UPLOAD_FOLDER", "static/uploads")

# ফোল্ডার চেক
if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

mongo = PyMongo(app)

def generate_numbers():
    reg = ''.join(random.choices(string.digits, k=8))
    roll = ''.join(random.choices(string.digits, k=5))
    return reg, roll

@app.route('/')
def landing():
    return render_template('landing.html')

# ImgBB আপলোড ফাংশন
def upload_to_imgbb(file):
    api_key = "0bb1747f7045ccee9cc03c792b828a67"
    # ফাইলটিকে Base64 এ কনভার্ট করা
    img_data = base64.b64encode(file.read()).decode('utf-8')
    
    try:
        response = requests.post(
            "https://api.imgbb.com/1/upload",
            data={"key": api_key, "image": img_data}
        )
        res_json = response.json()
        if response.status_code == 200:
            return res_json['data']['url'] # সরাসরি ইমেজের লিঙ্ক রিটার্ন করবে
        else:
            print(f"ImgBB Error: {res_json}")
            return None
    except Exception as e:
        print(f"Upload Exception: {e}")
        return None

@app.route('/apply', methods=['GET', 'POST'])
def apply():
    if request.method == 'POST':
        try:
            # ১. পাসওয়ার্ড ভ্যালিডেশন
            password = request.form.get('password')
            confirm_password = request.form.get('confirm_password')

            if not password or password != confirm_password:
                flash("Passwords do not match!", "danger")
                return redirect(request.url)

            # ২. শুধুমাত্র ফটো রিসিভ করা (Signature বাদ দেওয়া হয়েছে)
            photo_file = request.files.get('photo')

            if not photo_file:
                flash("Student Photo is required!", "danger")
                return redirect(request.url)

            # ৩. ImgBB-তে ইমেজ আপলোড (শুধুমাত্র ফটো)
            photo_url = upload_to_imgbb(photo_file)

            if not photo_url:
                flash("Image upload failed! Please try again.", "danger")
                return redirect(request.url)

            # ৪. রোল এবং রেজিস্ট্রেশন নম্বর জেনারেট করা
            reg_no, roll_no = generate_numbers()

            # ৫. ডাটাবেস অবজেক্ট তৈরি (Signature এবং Inst_BN রিমুভ করা হয়েছে)
            student_data = {
                "roll_no": str(roll_no),
                "reg_no": str(reg_no),
                "student_class": request.form.get('student_class'),
                "category": request.form.get('category', 'General'),
                "center_code": request.form.get('center_code'),
                "gender": request.form.get('gender'),
                
                "name_en": request.form.get('name_en', '').upper().strip(),
                "name_bn": request.form.get('name_bn', '').strip(),
                
                "father_en": request.form.get('father_en', '').strip(),
                "father_bn": request.form.get('father_bn', '').strip(),
                
                "mother_en": request.form.get('mother_en', '').strip(),
                "mother_bn": request.form.get('mother_bn', '').strip(),
                
                "mobile": request.form.get('mobile'),
                "dob": request.form.get('dob'),
                "institute_en": request.form.get('institute_en'),
                # "institute_bn": request.form.get('institute_bn'), # এটি রিমুভ করা হয়েছে
                "password": generate_password_hash(password),
                
                "address_present": {
                    "village": request.form.get('pre_v'),
                    "upazila": request.form.get('pre_t'),
                    "district": request.form.get('pre_d')
                },
                "address_permanent": {
                    "village": request.form.get('per_v'),
                    "upazila": request.form.get('per_t'),
                    "district": request.form.get('per_d')
                },
                "photo_url": photo_url,
                "status": "Pending",
                "applied_at": datetime.utcnow()
            }

            mongo.db.students.insert_one(student_data)
            
            flash("Application Submitted Successfully!", "success")
            return render_template("success.html", roll=roll_no, reg=reg_no, mobile=student_data["mobile"])

        except Exception as e:
            print(f"Submission Error: {e}")
            flash("An error occurred. Please try again.", "danger")
            return redirect(request.url)

    # GET Method
    all_centers = list(mongo.db.centers.find().sort("center_code", 1))
    
    # Institution লিস্ট পাঠানোর সময় শুধুমাত্র ইংরেজি নাম পাঠালেই হবে
    inst_docs = list(mongo.db.institutions.find().sort("name", 1))
    institutes_list = [{"name": doc.get("name"), "bn": doc.get("bn")} for doc in inst_docs]
    
    return render_template("apply.html", centers=all_centers, institutes=institutes_list)

# Update your public notices route to pull from the database
@app.route('/notices')
def notices():
    all_notices = mongo.db.notices.find().sort("_id", -1)
    return render_template('notices.html', notices=all_notices)

from werkzeug.security import check_password_hash

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        roll = request.form.get('roll')
        pw = request.form.get('password')

        if not roll or not pw:
            flash("Please enter both Roll and Password.", "danger")
            return redirect(url_for('login'))

        # ১. শুধু রোল নম্বর দিয়ে ইউজারকে খুঁজুন (পাসওয়ার্ড ছাড়া)
        # কারণ পাসওয়ার্ড হ্যাশ করা থাকলে কুয়েরিতে সরাসরি চেক করা যায় না
        user = mongo.db.students.find_one({
            "$or": [
                {"roll_no": roll}, 
                {"roll_no": int(roll) if roll.isdigit() else None}
            ]
        })
        
        # ২. ইউজার পাওয়া গেলে পাসওয়ার্ড চেক করুন
        if user:
            # যদি রেজিস্ট্রেশনের সময় generate_password_hash ব্যবহার করে থাকেন:
            is_valid = check_password_hash(user['password'], pw)
            
            # যদি রেজিস্ট্রেশনের সময় সাধারণ টেক্সটে সেভ করে থাকেন, তবে নিচের লাইনটি ব্যবহার করুন:
            # is_valid = (user['password'] == pw)

            if is_valid:
                session.permanent = True
                session['user_id'] = str(user['_id'])
                session['roll'] = user['roll_no'] # ড্যাশবোর্ডের জন্য রোল সেভ রাখা ভালো
                flash("Welcome back!", "success")
                return redirect(url_for('dashboard'))
            else:
                flash("Invalid Password.", "danger")
        else:
            flash("Roll Number not found.", "danger")
            
        return redirect(url_for('login'))
            
    return render_template('login.html')

@app.route('/dashboard', methods=['GET', 'POST'])
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    student = mongo.db.students.find_one({"_id": ObjectId(session['user_id'])})
    
    if not student:
        session.clear()
        flash("Account error. Please login again.", "danger")
        return redirect(url_for('login'))
    
    # পেমেন্ট ভেরিফিকেশন স্ট্যাটাস
    is_verified = student.get('verification', False)

    # রেজাল্ট পাবলিশ স্ট্যাটাস চেক (অ্যাডমিন প্যানেল থেকে যা সেট করা হবে)
    setting = mongo.db.settings.find_one({"key": "result_published"})
    is_published = setting['value'] if setting else False

    if request.method == 'POST':
        tran_id = request.form.get('tran_id')
        mongo.db.students.update_one(
            {"_id": ObjectId(session['user_id'])},
            {"$set": {"tran_id": tran_id}}
        )
        flash("Transaction ID submitted! Waiting for approval.", "info")
        return redirect(url_for('dashboard'))

    return render_template('dashboard.html', 
                           student=student, 
                           is_verified=is_verified, 
                           is_published=is_published)

@app.route('/download-slip')
def download_slip():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    student = mongo.db.students.find_one({"_id": ObjectId(session['user_id'])})
    
    if not student or not student.get('verification'):
        flash("Access Denied: Account not verified.", "danger")
        return redirect(url_for('dashboard'))

    return render_template('payment_slip.html', student=student)

@app.route('/download-admit')
def download_admit():
    # ১. ইউজার লগইন করা আছে কি না চেক করুন
    if 'user_id' not in session:
        flash("Please login first.", "warning")
        return redirect(url_for('login'))
    
    # ২. ডাটাবেস থেকে শিক্ষার্থীর ডাটা সংগ্রহ করুন
    student = mongo.db.students.find_one({"_id": ObjectId(session['user_id'])})
    
    # ৩. ভেরিফিকেশন চেক
    if not student or not student.get('verification', False):
        flash("Your account is not verified. Admit card is locked.", "danger")
        return redirect(url_for('dashboard'))

    # --- নতুন পরিবর্তন শুরু ---
    # ৪. সেন্টারের কোড দিয়ে সেন্টারের নাম খুঁজে আনা
    center_info = mongo.db.centers.find_one({"center_code": student.get('center_code')})
    
    # যদি নাম পাওয়া যায় তবে সেটি দেখাবে, না হলে কোডই দেখাবে
    center_name = center_info['center_name'] if center_info else student.get('center_code')
    # --- নতুন পরিবর্তন শেষ ---
    
    # ৫. টেমপ্লেটে student এবং center_name দুটোই পাস করুন
    return render_template('admit_card.html', student=student, center_name=center_name)

@app.route('/view-result')
def view_result():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    # স্টুডেন্ট ডাটা আনা
    student = mongo.db.students.find_one({"_id": ObjectId(session['user_id'])})
    
    # পাবলিশ স্ট্যাটাস চেক
    setting = mongo.db.settings.find_one({"key": "result_published"})
    is_published = setting['value'] if setting else False
    
    # রেজাল্ট পাবলিশ না হলে বা ভেরিফাইড না হলে ঢুকতে দিবে না
    if not is_published or not student.get('verification'):
        flash("Result is not available yet.", "warning")
        return redirect(url_for('dashboard'))
    
    return render_template('result_card.html', student=student)

@app.route('/logout')
def logout():
    session.clear() # অথবা session.pop('student_id', None)
    flash('You have been logged out successfully.', 'info')
    return redirect(url_for('login'))

@app.route('/contact', methods=['GET', 'POST'])
def contact():
    if request.method == 'POST':
        name = request.form.get('name')
        message = request.form.get('message')
        return render_template('contact.html', success=True)
    return render_template('contact.html')

@app.errorhandler(404)
def page_not_found(e):
    return render_template('error.html', 
        code=404, 
        message="Page Not Found", 
        description="The page you are looking for might have been removed, had its name changed, or is temporarily unavailable."), 404

@app.errorhandler(500)
def internal_server_error(e):
    return render_template('error.html', 
        code=500, 
        message="Internal Server Error", 
        description="Oops! Something went wrong on our end. Please try again later or contact support."), 500

@app.errorhandler(403)
def forbidden(e):
    return render_template('error.html', 
        code=403, 
        message="Access Forbidden", 
        description="You don't have permission to access this page. Please make sure you are logged in."), 403

# --- ADMIN LOGIN ---
@app.route('/admin-login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        user = request.form.get('username')
        pw = request.form.get('password')
        
        # Hardcoded credentials as requested
        if os.getenv("ADMIN_USER") and pw == os.getenv("ADMIN_PASS"):
            session['admin_logged_in'] = True
            flash("Welcome back, Admin!", "success")
            return redirect(url_for('admin_dashboard'))
        else:
            flash("Invalid Admin Credentials", "danger")
            
    return render_template('admin_login.html')

# --- ADMIN DASHBOARD ---
@app.route('/admin/dashboard')
def admin_dashboard():
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))
    
    search_query = request.args.get('search', '').strip()
    center_filter = request.args.get('center', '').strip()
    class_filter = request.args.get('class', '').strip()
    
    # ডাটাবেস থেকে বিদ্যমান সকল ইউনিক সেন্টার কোড সংগ্রহ করা
    # এটি রেজিস্ট্রেশন এবং সিট প্ল্যান পেজের সাথে অটো সিঙ্ক থাকবে
    available_centers = mongo.db.students.distinct("center_code")
    available_classes = mongo.db.students.distinct("student_class")

    query = {}
    if search_query:
        query["$or"] = [
            {"name": {"$regex": search_query, "$options": "i"}},
            {"roll_no": {"$regex": search_query, "$options": "i"}},
            {"institute_bn": {"$regex": search_query, "$options": "i"}}
        ]
    
    if center_filter:
        query["center_code"] = center_filter
    if class_filter:
        query["student_class"] = class_filter

    students = list(mongo.db.students.find(query).sort("roll_no", 1))
    
    stats = {
        "total": mongo.db.students.count_documents({}),
        "pending": mongo.db.students.count_documents({"status": {"$ne": "Verified"}}),
        "verified": mongo.db.students.count_documents({"status": "Verified"})
    }
    
    return render_template('admin_panel.html', 
                           students=students, 
                           stats=stats,
                           available_centers=available_centers,
                           available_classes=available_classes,
                           current_search=search_query,
                           current_center=center_filter,
                           current_class=class_filter)

# --- DIRECT DATABASE UPDATE API (Point 2) ---
@app.route('/admin/api/update_status', methods=['POST'])
def update_status():
    if not session.get('admin_logged_in'): return jsonify({"error": "Unauthorized"}), 403
    
    data = request.json
    roll = data.get('roll')
    new_status = data.get('status')
    
    verification = True if new_status == "Verified" else False
    
    mongo.db.students.update_one(
        {"roll_no": roll},
        {"$set": {"status": new_status, "verification": verification}}
    )
    return jsonify({"success": True})


# --- ATTENDANCE SHEET (One clean route) ---
@app.route('/admin/attendance-sheet')
def attendance_sheet():
    if not session.get('admin_logged_in'): 
        return redirect(url_for('admin_login'))
    
    # URL থেকে ফিল্টারগুলো নেওয়া
    center_code = request.args.get('center', '')
    student_class = request.args.get('student_class', '') # ক্লাস ফিল্টার নেওয়া
    
    # ড্রপডাউনের জন্য সব ইউনিক সেন্টার লিস্ট
    all_centers = mongo.db.students.distinct("center_code")
    
    # কুয়েরি সেটআপ: শুধুমাত্র ভেরিফাইড স্টুডেন্ট
    query = {"status": "Verified"}
    
    if center_code:
        query["center_code"] = center_code
        
    if student_class:
        query["student_class"] = student_class # ক্লাস অনুযায়ী ফিল্টার যোগ করা
    
    # ডাটাবেস থেকে সর্ট করে স্টুডেন্ট আনা
    students = list(mongo.db.students.find(query).sort("roll_no", 1))
    
    # টেমপ্লেট রেন্ডার (এখানে now ভেরিয়েবলটি পাস করা হয়েছে)
    return render_template('admin_attendance.html', 
                           students=students, 
                           all_centers=all_centers,
                           current_center=center_code or "All Centers",
                           now=datetime.now()) # 'now' undefined এরর সমাধান করবে এটি
    
# --- SEAT PLAN ---
@app.route('/admin/seat-plan')
def seat_plan():
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))
    
    # ফিল্টার ভ্যালু গ্রহণ
    center = request.args.get('center', '')
    student_class = request.args.get('class', '')
    
    # ড্রপডাউনের জন্য ডাইনামিক সেন্টার লিস্ট
    all_centers = mongo.db.students.distinct("center_code")

    # ডাটাবেস কুয়েরি
    query = {"status": "Verified"}
    if center: 
        query["center_code"] = center
    if student_class: 
        query["student_class"] = student_class

    # রোল নম্বর অনুযায়ী সর্ট করা (আসন বিন্যাসের জন্য জরুরি)
    students = list(mongo.db.students.find(query).sort("roll_no", 1))
    
    return render_template('admin_seat_plan.html', 
                           students=students, 
                           all_centers=all_centers)

# --- SEARCH-FIRST MARK ENTRY (The one you requested) ---
from flask import Flask, render_template, request, redirect, url_for, session, flash

# ... (আপনার অন্যান্য কনফিগারেশন যেমন: mongo = PyMongo(app))

@app.route('/admin/entry-marks', methods=['GET'])
def entry_marks():
    """স্টুডেন্ট লিস্ট ফিল্টার করে দেখানোর রুট"""
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))
    
    # ড্রপডাউনের জন্য ইনস্টিটিউট লিস্ট আনা
    institutes = list(mongo.db.institutions.find().sort("name", 1))
    
    # URL প্যারামিটার থেকে ক্লাস এবং ইনস্টিটিউট নেওয়া
    f_class = request.args.get('class')
    f_inst = request.args.get('institute')
    
    students = []
    if f_class:
        # শুধুমাত্র ভেরিফাইড স্টুডেন্টদের জন্য কোয়েরি
        query = {"student_class": f_class, "status": "Verified"}
        if f_inst:
            query["institute_en"] = f_inst
            
        # রোল নম্বর অনুযায়ী সিরিয়াল করা
        students = list(mongo.db.students.find(query).sort("roll_no", 1))

    return render_template('admin_marks_entry.html', 
                           students=students, 
                           institutes=institutes)


@app.route('/admin/save-bulk-marks', methods=['POST'])
def save_bulk_marks():
    """টেবিল থেকে আসা সব ডাটা একসাথে ডাটাবেসে সেভ করার রুট"""
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))

    # HTML name[] থেকে সব ডাটা লিস্ট আকারে আনা
    rolls = request.form.getlist('roll_no[]')
    bans = request.form.getlist('ban[]')
    engs = request.form.getlist('eng[]')
    maths = request.form.getlist('math[]')
    gks = request.form.getlist('gk[]')
    grades = request.form.getlist('scholarship_grade[]')

    if not rolls:
        flash("No data submitted!", "warning")
        return redirect(url_for('entry_marks'))

    try:
        # ডেটাবেস অপারেশন শুরু
        for i in range(len(rolls)):
            # ইনপুট খালি থাকলে (None/Empty) সেটাকে ০ হিসেবে ধরার ফাংশন
            def get_val(val_list, index):
                try:
                    v = val_list[index].strip()
                    return float(v) if v else 0.0
                except (ValueError, IndexError):
                    return 0.0

            m_ban = get_val(bans, i)
            m_eng = get_val(engs, i)
            m_math = get_val(maths, i)
            m_gk = get_val(gks, i)
            
            # টোটাল মার্কস ক্যালকুলেশন
            total = m_ban + m_eng + m_math + m_gk
            
            # স্কলারশিপ গ্রেড (লিস্টের বাইরে ইনডেক্স গেলে ডিফল্ট 'Nothing')
            s_grade = grades[i] if i < len(grades) else "Nothing"

            # MongoDB আপডেট করা
            mongo.db.students.update_one(
                {"roll_no": rolls[i]},
                {"$set": {
                    "marks": {
                        "bangla": m_ban, 
                        "english": m_eng, 
                        "math": m_math, 
                        "gk": m_gk, 
                        "total": total
                    },
                    "scholarship_grade": s_grade,
                    "result_published": True
                }}
            )
        
        flash(f"Successfully updated marks for {len(rolls)} students.", "success")
        
    except Exception as e:
        flash(f"Error occurred: {str(e)}", "danger")

    # ডাটা সেভ হওয়ার পর আগের ফিল্টার করা পেজেই ফেরত যাবে
    return redirect(request.referrer or url_for('entry_marks'))

#admin view all results
@app.route('/admin/toggle-result-publish', methods=['POST'])
def toggle_result_publish():
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))
    
    # settings কালেকশনে স্ট্যাটাস সেভ করা
    setting = mongo.db.settings.find_one({"key": "result_published"})
    current_status = setting['value'] if setting else False
    new_status = not current_status
    
    mongo.db.settings.update_one(
        {"key": "result_published"},
        {"$set": {"value": new_status}},
        upsert=True
    )
    
    flash(f"Results are now {'Public' if new_status else 'Hidden'}", "success")
    return redirect(url_for('manage_results'))

# ২. অ্যাডমিন রেজাল্ট ম্যানেজমেন্ট পেজ
@app.route('/admin/manage-results')
def manage_results():
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))
    
    # ১. URL প্যারামিটার থেকে ফিল্টারগুলো নেওয়া
    f_class = request.args.get('class', '')
    f_center = request.args.get('center', '')
    f_grade = request.args.get('grade', '')
    f_sort = request.args.get('sort', 'merit')

    # ২. পাবলিশ স্ট্যাটাস আনা
    setting = mongo.db.settings.find_one({"key": "result_published"})
    is_published = setting['value'] if setting else False

    # ৩. ডাটাবেস কোয়েরি বিল্ড করা
    # শুধুমাত্র যাদের মার্কস এন্ট্রি করা হয়েছে তাদের আনা হচ্ছে
    query = {"marks": {"$exists": True}}
    
    if f_class: 
        query["student_class"] = f_class # ডাটাবেসে 'student_class' ফিল্ড চেক করুন
    if f_center: 
        query["center_code"] = f_center
    if f_grade:
        if f_grade == 'Nothing':
            query["scholarship_grade"] = {"$exists": False}
        else:
            query["scholarship_grade"] = f_grade

    # ৪. সর্টিং লজিক
    sort_logic = [("marks.total", -1)] # ডিফল্ট: মেরিট লিস্ট (বেশি থেকে কম)
    if f_sort == 'roll':
        sort_logic = [("roll_no", 1)]
    elif f_sort == 'name':
        sort_logic = [("name_en", 1)]

    # ৫. ডাটা ফেচ করা
    results = list(mongo.db.students.find(query).sort(sort_logic))
    
    # ৬. ড্রপডাউনের জন্য সব সেন্টারের লিস্ট
    all_centers = mongo.db.students.distinct("center_code")

    # ৭. স্ট্যাটিস্টিক্স হিসাব
    total_count = len(results)
    sum_marks = sum((s.get('marks') or {}).get('total', 0) for s in results)
    avg_score = (sum_marks / total_count) if total_count > 0 else 0

    return render_template('admin_manage_results.html', 
                           results=results, 
                           is_published=is_published,
                           total_count=total_count,
                           sum_marks=sum_marks, # এটি টেমপ্লেটে দরকার হতে পারে
                           avg_score=avg_score,
                           centers=all_centers) # সেন্টার লিস্ট পাঠানো হলো

# --- ADMIN: APPROVE ADMIT CARDS ---
@app.route('/admin/approve-admits', methods=['GET', 'POST'])
def approve_admits():
    # ১. সিকিউরিটি চেক
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))

    if request.method == 'POST':
        # ২. HTML এর name="selected_students" থেকে লিস্ট নেওয়া
        student_ids = request.form.getlist('selected_students')
        action = request.form.get('action') # 'approve' অথবা 'revoke'
        
        if not student_ids:
            flash("দয়া করে অন্তত একজন ছাত্র সিলেক্ট করুন!", "warning")
            return redirect(url_for('approve_admits'))

        try:
            status = True if action == 'approve' else False
            
            # ৩. ডাটাবেস আপডেট (মেইন পার্ট)
            result = mongo.db.students.update_many(
                {"_id": {"$in": [ObjectId(sid) for sid in student_ids]}},
                {"$set": {"admit_approved": status}}
            )
            
            if result.modified_count > 0:
                flash(f"সফলভাবে {len(student_ids)} জন ছাত্রের এডমিট কার্ড আপডেট হয়েছে।", "success")
            else:
                flash("কোনো পরিবর্তন করা হয়নি। হয়তো তারা আগে থেকেই এই অবস্থায় ছিল।", "info")

        except Exception as e:
            flash(f"সিস্টেম এরর: {str(e)}", "danger")
        
        return redirect(url_for('approve_admits'))

    # ৪. ছাত্রদের লিস্ট রিড করা
    students = list(mongo.db.students.find().sort("roll_no", 1))
    return render_template('admin_approve_admits.html', students=students)

@app.route('/admin/scholarship/labels')
def scholarship_labels():
    # ফিল্টার ডেটা নেওয়া
    center_query = request.args.get('center', '')
    roll_query = request.args.get('roll', '')
    school_query = request.args.get('school', '')
    class_query = request.args.get('student_class', '') # ক্লাস ফিল্টার

    # বেসিক কোয়েরি (শুধুমাত্র ভেরিফাইড স্টুডেন্টদের জন্য)
    query = {"status": "Verified"} 

    # ফিল্টার লজিক যুক্ত করা
    if center_query: 
        query["center_code"] = center_query
    if roll_query: 
        query["roll_no"] = roll_query
    if class_query:
        query["student_class"] = class_query
    if school_query: 
        # স্কুল নামের আংশিক মিল খোঁজার জন্য Regex (Case-insensitive)
        query["institute_en"] = {"$regex": school_query, "$options": "i"}

    # ডাটাবেস থেকে সর্ট করে ডেটা ফেচ করা
    students_list = list(mongo.db.students.find(query).sort("roll_no", 1))
    
    # ড্রপডাউনের জন্য সব সেন্টারের লিস্ট
    all_centers = mongo.db.students.distinct("center_code")

    return render_template('admin_labels.html', 
                           students=students_list, 
                           all_centers=all_centers)

# --- Manage Centers (View All) ---
@app.route('/admin/centers')
def manage_centers():
    # অ্যাডমিন লগইন সিকিউরিটি চেক
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))
    
    # ডাটাবেস থেকে সব সেন্টার সংগ্রহ এবং সর্টিং (A-Z)
    centers = list(mongo.db.centers.find().sort("center_code", 1))
    
    return render_template('admin_center.html', centers=centers)

@app.route('/admin/add_center', methods=['POST'])
def add_center():
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))

    # ইনপুট ডাটা ক্লিন করা
    center_code = request.form.get('center_code', '').strip().upper()
    center_name = request.form.get('center_name', '').strip()
    
    if not center_code or not center_name:
        flash("Both Center Code and Name are required!", "danger")
        return redirect(url_for('manage_centers'))

    # চেক করা হচ্ছে এই কোডটি আগে থেকে আছে কিনা
    existing = mongo.db.centers.find_one({"center_code": center_code})
    
    if not existing:
        mongo.db.centers.insert_one({
            "center_code": center_code,
            "center_name": center_name
        })
        flash(f"Success! Center {center_code} has been added.", "success")
    else:
        flash(f"Error! Center code {center_code} already exists.", "danger")
    
    return redirect(url_for('manage_centers'))

from bson import ObjectId

@app.route('/admin/delete_center/<center_id>')
def delete_center(center_id):
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))

    try:
        # প্রথমে সেন্টারটির নাম খুঁজে বের করা
        center_to_delete = mongo.db.centers.find_one({"_id": ObjectId(center_id)})
        
        if center_to_delete:
            # চেক করা হচ্ছে এই সেন্টারে কোনো স্টুডেন্ট রেজিস্ট্রেশন করেছে কি না
            student_count = mongo.db.students.count_documents({"center_code": center_to_delete['center_code']})
            
            if student_count > 0:
                flash(f"Cannot delete! There are {student_count} students registered in this center.", "danger")
            else:
                mongo.db.centers.delete_one({"_id": ObjectId(center_id)})
                flash("Center deleted successfully!", "info")
        else:
            flash("Center not found!", "warning")
            
    except Exception as e:
        flash(f"Error occurred: {str(e)}", "danger")
    
    return redirect(url_for('manage_centers'))

# --- ADMIN NOTICES ---
@app.route('/admin/notices')
def admin_notices():
    # Fetch all notices from MongoDB, sorted by newest first
    notices = mongo.db.notices.find().sort("_id", -1)
    return render_template('admin_notices.html', notices=notices)

@app.route('/admin/add_notice', methods=['POST'])
def add_notice():
    import datetime
    notice_data = {
        "title": request.form.get('title'),
        "content": request.form.get('content'),
        "category": request.form.get('category'),
        "date": datetime.datetime.now().strftime("%b %d, %Y")
    }
    mongo.db.notices.insert_one(notice_data)
    return redirect(url_for('admin_notices'))

@app.route('/admin/delete_notice/<notice_id>')
def delete_notice(notice_id):
    mongo.db.notices.delete_one({"_id": ObjectId(notice_id)})
    return redirect(url_for('admin_notices'))

# --- ADMIN INSTITUTES ---
@app.route('/admin/institutions')
def manage_institutions():
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))
    
    # সব প্রতিষ্ঠানের নাম সংগ্রহ এবং সর্টিং (A-Z)
    institutes = list(mongo.db.institutions.find().sort("name", 1))
    return render_template('admin_institutes.html', institutes=institutes)

# --- Add New Institution ---
@app.route('/admin/add_institute', methods=['POST'])
def add_institute():
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))

    inst_name = request.form.get('name', '').strip()
    
    if not inst_name:
        flash("Institution name cannot be empty!", "danger")
        return redirect(url_for('manage_institutions'))

    # চেক করা হচ্ছে এই নাম আগে থেকে আছে কিনা
    existing = mongo.db.institutions.find_one({"name": inst_name})
    if not existing:
        mongo.db.institutions.insert_one({"name": inst_name})
        flash(f"Successfully added: {inst_name}", "success")
    else:
        flash(f"Error! {inst_name} is already in the list.", "danger")
    
    return redirect(url_for('manage_institutions'))

# --- Delete Institution ---
@app.route('/admin/delete_institute/<inst_id>')
def delete_institute(inst_id):
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))

    try:
        # কোনো স্টুডেন্ট এই স্কুল থেকে রেজিস্ট্রেশন করেছে কি না চেক করা (নিরাপত্তার জন্য)
        inst = mongo.db.institutions.find_one({"_id": ObjectId(inst_id)})
        student_exists = mongo.db.students.find_one({"institute_en": inst['name']})
        
        if student_exists:
            flash("Cannot delete! Some students are already registered from this institution.", "danger")
        else:
            mongo.db.institutions.delete_one({"_id": ObjectId(inst_id)})
            flash("Institution deleted successfully.", "info")
    except Exception as e:
        flash(f"Error: {str(e)}", "danger")
    
    return redirect(url_for('manage_institutions'))

@app.route('/admin/serial-allocation', methods=['GET', 'POST'])
def serial_allocation():
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))

    centers_list = [
        {"code": "1", "name": "Sariakandi"},
        {"code": "2", "name": "Gabtali"},
        {"code": "3", "name": "Khottapara"},
        {"code": "4", "name": "Aria Bajar"},
        {"code": "5", "name": "Dhunat"},
        {"code": "6", "name": "Summit (Sherpur)"},
        {"code": "7", "name": "Sonka (Sherpur)"},
        {"code": "8", "name": "Sukhanpukur"},
        {"code": "9", "name": "Sonatola"}
    ]

    if request.method == 'POST':
        try:
            target_class = request.form.get('student_class')
            c_code = request.form.get('center_code')
            start_roll = int(request.form.get('start_roll'))
            start_reg = int(request.form.get('start_reg'))

            # গুরুত্বপূর্ণ: $in ব্যবহার করা হয়েছে যাতে center_code String "1" বা Number 1 যাই হোক না কেন খুঁজে পায়
            query = {
                "student_class": target_class, 
                "center_code": {"$in": [c_code, int(c_code) if c_code.isdigit() else c_code]},
                "status": "Verified" 
            }
            
            # ইউনিফর্ম সর্টিং: স্কুল (institute_en) -> নাম (name_en)
            students = list(mongo.db.students.find(query).sort([
                ("institute_en", 1), 
                ("name_en", 1)
            ]))

            # ডিবাগিং এর জন্য আপনার টার্মিনালে প্রিন্ট হবে কতজন পাওয়া গেল
            print(f"Query: {query}, Found: {len(students)} students")

            if not students:
                flash(f"সতর্কতা: Class {target_class}-এ এই সেন্টারে কোনো ভেরিফাইড ছাত্র পাওয়া যায়নি। ডাটাবেসে 'status' ফিল্ডটি 'Verified' আছে কি না চেক করুন।", "warning")
                return redirect(request.url)

            # সিরিয়াল আপডেট
            for index, student in enumerate(students):
                mongo.db.students.update_one(
                    {"_id": student["_id"]},
                    {"$set": {
                        "roll_no": str(start_roll + index),
                        "reg_no": str(start_reg + index)
                    }}
                )

            flash(f"সফল! {len(students)} জন ছাত্রের রোল ({start_roll} থেকে শুরু) আপডেট করা হয়েছে।", "success")
            
        except Exception as e:
            flash(f"Error: {str(e)}", "danger")

    return render_template('admin_serial.html', centers=centers_list)

@app.route('/admin/print-result')
def print_result():
    summary_data = []
    # ডেটাবেস আইডি এবং ডিসপ্লে নাম
    classes = [
        {'id': '5', 'name': 'Five'},
        {'id': '6', 'name': 'Six'},
        {'id': '7', 'name': 'Seven'},
        {'id': '8', 'name': 'Eight'},
        {'id': '9', 'name': 'Nine'}
    ]
    
    # আপনার HTML select option থেকে নেওয়া হুবহু ভ্যালু
    target_grades = ['Talentpool', 'General', 'Suveccha', 'Quata']

    for cls in classes:
        cls_row = {'class_display': cls['name']}
        
        for grade in target_grades:
            # ক্লাস এবং গ্রেড অনুযায়ী সার্চ (String এবং Integer উভয় ফরম্যাট চেক করা হয়েছে)
            students = mongo.db.students.find(
                {
                    'student_class': {'$in': [cls['id'], int(cls['id'])]}, 
                    'scholarship_grade': grade
                },
                {'roll_no': 1, '_id': 0}
            ).sort('roll_no', 1)
            
            # রোলগুলোকে কমা দিয়ে জয়েন করা
            rolls = [str(s['roll_no']) for s in students]
            cls_row[grade] = ", ".join(rolls)
            
        summary_data.append(cls_row)

    return render_template('print_result.html', summary_data=summary_data)

@app.route('/forgot-serial', methods=['GET', 'POST'])
def forgot_serial():
    student_data = None
    if request.method == 'POST':
        # ফরম থেকে মোবাইল নম্বর নেওয়া
        input_mobile = request.form.get('phone').strip()
        
        # আপনার ডাটাবেস অনুযায়ী "mobile" ফিল্ডে সার্চ করা
        # এখানে স্ট্রিং এবং ইন্টিজার উভয়ই চেক করা হচ্ছে
        student = mongo.db.students.find_one({"mobile": input_mobile})
        
        if not student and input_mobile.isdigit():
            student = mongo.db.students.find_one({"mobile": int(input_mobile)})
            
        if student:
            student_data = {
                'serial': student.get('roll_no'), # roll_no কে সিরিয়াল হিসেবে নেওয়া
                'name': student.get('name_en')
            }
        else:
            flash('এই মোবাইল নম্বর দিয়ে কোনো শিক্ষার্থী পাওয়া যায়নি!', 'danger')
            
    return render_template('forgot_serial.html', student=student_data)

# ১. সার্টিফিকেট লিস্ট এবং সার্চ রাউট
@app.route('/admin/certificates', methods=['GET', 'POST'])
def admin_certificates():
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))

    students = []
    search_query = ""

    if request.method == 'POST':
        search_query = request.form.get('search_query', '').strip()
        
        if search_query:
            # শুধুমাত্র Verified স্টুডেন্টদের মধ্যে সার্চ করবে (রোল বা নাম দিয়ে)
            query = {
                "status": "Verified",
                "$or": [
                    {"roll_no": search_query},
                    {"name_en": {"$regex": search_query, "$options": "i"}}
                ]
            }
            students = list(mongo.db.students.find(query).sort("roll_no", 1))
            
            if not students:
                flash(f"No verified student found for '{search_query}'", "warning")
        else:
            flash("Please enter a Roll No or Name to search.", "info")

    return render_template('admin_certificates.html', students=students, search_query=search_query)


# ২. নির্দিষ্ট সার্টিফিকেট প্রিন্ট করার রাউট (যা আপনি 'print_certificate' নামে খুঁজছেন)
@app.route('/admin/print-certificate/<student_id>')
def print_certificate(student_id):
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))

    try:
        # স্টুডেন্ট ডেটা ফেচ করা
        student = mongo.db.students.find_one({"_id": ObjectId(student_id)})
        
        if not student:
            flash("Student not found!", "danger")
            return redirect(url_for('admin_certificates'))

        # সেন্টার ম্যাপিং (আপনার কোড অনুযায়ী আপডেট করুন)
        centers_mapping = {
            "1": "Sariakandi", "2": "Gabtali", "3": "Khottapara",
            "4": "Aria Bajar", "5": "Dhunat", "6": "Summit",
            "7": "Sonka", "8": "Sukhanpukur", "9": "Sonatola"
        }
        
        center_code = str(student.get('center_code', ''))
        center_name = centers_mapping.get(center_code, "Unknown Center")

        # তারিখ চেক (যদি ডেটাবেসে না থাকে তবে ডিফল্ট তারিখ)
        if 'result_publication_date' not in student:
            student['result_publication_date'] = "30-03-2026"

        return render_template('certificate_design.html', 
                               student=student, 
                               center_name=center_name)

    except Exception as e:
        flash(f"Error: {str(e)}", "danger")
        return redirect(url_for('admin_certificates'))


# --- ADMIN LOGOUT ---
@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_logged_in', None)
    flash("You have been logged out.", "info")
    return redirect(url_for('admin_login'))


if __name__ == '__main__':
    app.run(debug=True)