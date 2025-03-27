from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_from_directory, session
import requests
import os
from datetime import datetime
from werkzeug.utils import secure_filename
from flask_sqlalchemy import SQLAlchemy
import base64
import pytz
import cloudinary
import cloudinary.uploader
import cloudinary.api

# Initialize Flask app
app = Flask(__name__)
app.secret_key = "your_secret_key_here"  # For flash messages

ADMIN_PASSWORD = "royal25"

LOCAL_TZ = pytz.timezone("America/Chicago")

#configure Database
#use Heroku's database_url if available, otherwise use SQLite
database_url = os.environ.get('DATABASE_URL', 'sqlite:///visitors.db')

# Heroku's PostgreSQL URL starts with 'postgres://', but SQLAlchemy expects 'postgresql://'
if database_url and database_url.startswith('postgres://'):
    database_url = database_url.replace('postgres://', 'postgresql://', 1)


app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# Configure upload folders
UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "uploads")
QR_FOLDER = os.path.join(os.path.dirname(__file__), "static/images")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(QR_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

#configure cloudinary for cloud image storage
cloudinary.config(
    cloud_name = "duu3rjz8f",
    api_key = "361137226743648",
    api_secret= "93RyNOaqDgZ-Jsq158J8WvQysj4"
)

# Allowed file extensions
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif"}

# SMTP2Go API Parameters
SMTP2GO_API_URL = "https://api.smtp2go.com/v3/email/send"
SMTP2GO_API_KEY = "api-43E83469CC704967918416A4701A050C"  # Replace with your SMTP2Go API key
SENDER_EMAIL = 'receptionist@royalexpressinc.com'
DEFAULT_DEPARTMENT_EMAIL = 'hr_TEST_@royalexpressinc.com'  # Default HR email

class Visitor(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    company_name = db.Column(db.String(100), nullable=False)
    purpose = db.Column(db.String(200), nullable=False)
    department = db.Column(db.String(50), nullable=False)
    personnel = db.Column(db.String(100), nullable=False) 
    photo_path = db.Column(db.String(200), nullable=True)
    badge_number = db.Column(db.Integer, nullable=True)  # Assigned badge number
    check_in_time = db.Column(db.DateTime, default=lambda: datetime.now(pytz.utc).astimezone(LOCAL_TZ).replace(microsecond=0))
    check_out_time = db.Column(db.DateTime, nullable=True)  # Set check_out_time as nullable

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_available_badge():
    assigned_badges = [visitor.badge_number for visitor in Visitor.query.filter(Visitor.badge_number.isnot(None)).all()]
    for badge in range(5, 10):  # Checking badges 1-5
        if badge not in assigned_badges:
            return badge
    return None  # No available badge

def save_photo(photo_data, identifier, folder_name='visitor_photos'):
    if not photo_data:
        print("No photo data provided.")
        return None
    
    # Create uploads directory if it doesn't exist
    upload_dir = os.path.join(app.static_folder, 'uploads')
    if not os.path.exists(upload_dir):
        os.makedirs(upload_dir)
    
    # Extract image data from base64 string
    try:
        print(" Decoding Base64 image data....")

        #exctract base64 data
        if ',' in photo_data:
            base64_data = photo_data.split(',')[1]
        else:
            base64_data = photo_data
        
        print("Base64 data extracted. Decoding...")  # Debugging print
        
        image_data = base64.b64decode(base64_data)

        #create url-friendly filename without spaces or special characters
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        #Replace spaces with underscores and remove special characters
        safe_identifier = "".join(c for c in identifier if c.isalnum() or c in "_-").replace(" ", "_")
        filename = f"{safe_identifier}_{timestamp}.jpg"
        
        #upload image to cloudinary
        upload_result = cloudinary.uploader.upload(
            f"data:image/jpeg;base64,{base64_data}",
            public_id = f"{folder_name}/{filename}",
            folder = "visitor_app",
            upload_preset="Royal-30days",
            invalidate=True,
            invalidate_after=2592000  # 30 days in seconds
        )
        
        print(f"Image uploaded to Cloudinary: {upload_result['secure_url']}")

        #return the Cloudinary URL
        return upload_result['secure_url']
    

    
    except Exception as e:
        print(f"Error saving photo: {e}")
        return None


def send_email(recipient_email, visitor_name, company_name, purpose, department):
    try:
        print(f"Attempting to send email to {recipient_email} about {visitor_name}")
        # List of CC recipients
        cc_recipients = ["patricia.rodriguez@royalexpressinc.com", "hr.assistant@royalexpressinc.com"]

        # Prepare email data
        email_data = {
            "api_key": SMTP2GO_API_KEY,
            "to": [recipient_email],
            "cc": cc_recipients,  # Add CC recipients
            "sender": SENDER_EMAIL,
            "subject": f"⚠️Visitor Alert - {visitor_name} has arrived",
            "text_body": (
                f"Visitor Name: {visitor_name}\n"
                f"Company Name: {company_name}\n"
                f"Purpose: {purpose}\n"
                f"Department: {department}\n"
            ),
            "html_body": (
                f"<h2>A visitor has arrived to see you</h2>"
                f"<p><strong>Visitor Name:</strong> {visitor_name}</p>"
                f"<p><strong>Company Name:</strong> {company_name}</p>"
                f"<p><strong>Purpose:</strong> {purpose}</p>"
                f"<p><strong>Department:</strong> {department}</p>"
            ),
        }

        response = requests.post(SMTP2GO_API_URL, json=email_data)
        result = response.status_code == 200

        if result:
            print(f"Email sent successfully to {recipient_email}")
        else:
            print(f"Failed to send email. Status Code: {response.status_code}")
            print(f'Response Content: {response.text}')

        # Handle API response
        return result
    except Exception as e:
        print(f"Error sending email: {e}")
        return False


@app.route("/get_personnel", methods=["GET"])
def get_personnel():
    department = request.args.get("department")
    print(f"Received request for personnel in department: {department}")
    personnel = {
        "HR": [
            {"name": "Patricia Rodriguez", "email": "patricia.rodriguez@royalexpressinc.com"},
            {"name": "Cristal Sanchez", "email": "hr.assistant@royalexpressinc.com"}
        ],
        "IT": [
            {"name": "Ivan Ramirez", "email": "ivan.ramirez@royalexpressinc.com"},
            {"name": "IT-Departament", "email": "wotickets@royalexpressinc.com"},
            {"name": "Carlos Lopez", "email": "revigor5@gmail.com"}
        ],
        "Accounting": [
            {"name": "Lesly Espinoza", "email": "carriersmx@royalexpressinc.com"},
            {"name": "David Mata", "email": "accounting1@royalexpressinc.com"},
            {"name": "Saul Alcorta", "email": "salcorta@royalexpressinc.com"},
            {"name": "Janett Vargas", "email": "janett.vargas@thegymlegacy.com"},
            {"name": "Erika lopez", "email": "erika.lopez@royalexpressinc.com"},
            {"name": "Karen Maldonado", "email": "kmaldonado@royalexpressinc.com"}
        ],
        "Settlements": [
            {"name": "Edith Ochoa", "email": "edith@royalexpressinc.com"},
            {"name": "Arleen", "email": "arleen@royalexpressinc.com"}
        ],
        "Fuel": [
            {"name": "Brenda Ceballos", "email": "brendac@royalexpressinc.com"}
        ],
        "Safety": [
            {"name": "Vanesa Uribe", "email": "vanessau@royalexpressinc.com"},
            {"name": "Mauricio", "email": "safety.recruiter@royalexpressinc.com"},
            {"name": "Joyce Zavala", "email": "insurance.handler@royalexpressinc.com"},
            {"name": "Magaly", "email": "safety.clerk@royalexpressinc.com"}
        ],
        "Shop": [
            {"name": "Oscar Garcia", "email": "ogarcia@royalexpressinc.com"},
            {"name": "Mariam Treviño", "email": "mariamt@royalexpressinc.com"}
        ],
        "Operations": [
            {"name": "Joe Varela", "email": "jvarela@royalexpressinc.com"}
        ],
        "Process": [
            {"name": "Maritza Canales", "email": "maritza.canales@royalexpressinc.com"}
        ]
    }
    personnel_list = personnel.get(department, [])
    print(f"Returning {len(personnel_list)} personnel for {department}")
    return jsonify(personnel_list)

# Visitor Check-In Route
@app.route("/", methods=["GET", "POST"])
def visitor():
   # if not session.get("ipad_authenticated"):  # If not logged in, redirect to login page
        #return redirect(url_for("visitor"))

    if request.method == "POST":
        visitor_name = request.form.get("visitor_name")
        company_name = request.form.get("company_name")
        purpose = request.form.get("purpose")
        department_name = request.form.get("department")  # Directly from the form
        point_of_contact_email = request.form.get("personnel")  # This now contains the selected email
        photo_data = request.form.get("photo_data")

        # Handle photo upload
        #photo_path = None
        #if photo and allowed_file(photo.filename):
            #filename = secure_filename(photo.filename)
            #photo_path = filename  # Store only 'filename.jpg'
            #full_photo_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)  # Full path for saving the file
            #photo.save(full_photo_path)

         # 🔥 Assign an available badge
        badge_number = get_available_badge()
        if badge_number is None:
            flash("No visitor badges available. Please wait for one to be returned.", "danger")
            return redirect(url_for("visitor"))
        
          # Save photos if provided
        photo_path = None
        #plate_photo_path = None

        if photo_data:
            print("📌 Calling save_photo() for driver's license...")
            photo_path = save_photo(photo_data, visitor_name, "visitor_photos")
            if photo_path:
                print(f"✅ Driver's License Photo saved at: {photo_path}\n")
            else:
                print("❌ Failed to save driver's license photo\n")
        
          # 📌 Debugging: Print received data
        print("\n📌 Received Form Data:")
        print(f"Name: {visitor_name}")
        print(f"Company Name: {company_name}")
        print(f"Purpose: {purpose}")
        print(f"Departmetn: {department_name}")
        print(f"Point of contact: {point_of_contact_email}")
        print(f"Photo Data (first 100 chars): {photo_data[:100] if photo_data else 'No photo received'}")
        

        # Save visitor to database
        visitor = Visitor(
            name=visitor_name,
            company_name=company_name,
            purpose=purpose,
            department=department_name,
            personnel=point_of_contact_email,  # Save the email of the point of contact
            photo_path=photo_path,
            badge_number=badge_number,  # Store assigned badge
            check_in_time=datetime.now(pytz.utc).astimezone(LOCAL_TZ).replace(microsecond=0),
            check_out_time=None  # ✅ Ensure this is explicitly set to None
        )
        db.session.add(visitor)
        db.session.commit()

        # Send email notification
        email_sent = send_email(
        recipient_email=point_of_contact_email,  # Send the email to the selected contact
        visitor_name=visitor_name,
        company_name=company_name,
        purpose=purpose,
        department=department_name
)
        if email_sent:
            flash(f"Visitor {visitor_name} checked in successfully! Email notification sent to {point_of_contact_email}", "success")
            flash(f'<span class="badge-number">Assigned Visitor Badge: {badge_number}</span>', "success")
        else:
            flash(f"Visitor {visitor_name} checked in, but we couldn't notify {point_of_contact_email}. Please call them at their extension.", "warning")
            flash(f'<span class="badge-number">Assigned Visitor Badge: {badge_number}</span>', "success")
        
        return redirect(url_for("visitor"))
    
    # Fetch only visitors that are still checked in
    visitors = Visitor.query.filter(Visitor.check_out_time.is_(None)).all()

    return render_template("visitor.html", visitors=visitors)

@app.route("/visitor_checkout/<int:visitor_id>", methods=["POST"])
def visitor_checkout(visitor_id):
    visitor = Visitor.query.get(visitor_id)
    
    if visitor:
        if visitor.check_out_time is None:
            visitor.check_out_time = datetime.now(pytz.utc).astimezone(LOCAL_TZ).replace(microsecond=0)  # Set check-out time
            badge_number = visitor.badge_number  # Save the badge number before releasing it
            visitor.badge_number = None  # Release badge number
            db.session.commit()
            flash(f"Visitor {visitor.name} checked out successfully! Badge {badge_number} is now available.", "success")
        else:
            flash(f"Visitor {visitor.name} has already checked out.", "info")
    else:
        flash("Visitor not found.", "danger")

    return redirect(url_for("visitor"))

@app.route("/admin_login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        entered_password = request.form.get("password")
        if entered_password == ADMIN_PASSWORD:
            session["admin_authenticated"] = True
            flash("Admin authenticated successfully!", "success")
            return redirect(url_for("visitor_logs"))
        else:
            flash("Invalid password. Try again.", "danger")
    return render_template("admin_login.html")  # Create this template for admin login

@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("admin_login"))



@app.route("/visitor_logs")
def visitor_logs():
    if not session.get("admin_authenticated"):  # Protect logs page
        return redirect(url_for("admin_login"))

    visitors = Visitor.query.all()
    return render_template("visitor_logs.html", visitors=visitors)

if __name__ == "__main__":
     # Get the port from an environment variable or use 5000 as default
    port = int(os.environ.get('PORT', 5001))
    
    # Initialize your database tables
    with app.app_context():
        db.create_all()
    
    # Set debug mode based on environment
    in_development = os.environ.get('FLASK_ENV') == 'development'
    
    # Run the app with the dynamic port, debug off for production
    app.run(debug=in_development, host="0.0.0.0", port=port)