from flask import Flask, render_template, request, redirect, url_for, flash, session
import os
from pypdf import PdfReader
from google import genai
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
import mysql.connector


# ============================================================
# FLASK SETUP
# ============================================================

app = Flask(__name__)

app.secret_key = os.getenv(
    "FLASK_SECRET_KEY",
    "dev-secret-key-change-later"
)


# ============================================================
# MYSQL DATABASE SETUP
# ============================================================

# IMPORTANT:
# Your MySQL password is NOT stored in this file.
# It will be provided through the MYSQL_PASSWORD
# environment variable.

DB_CONFIG = {
    "host": "127.0.0.1",
    "user": "root",
    "password": os.getenv("MYSQL_PASSWORD"),
    "database": "studymate_ai",
    "use_pure": True
}


def get_db_connection():
    """
    Creates and returns a connection to the StudyMate AI
    MySQL database.
    """

    if not DB_CONFIG["password"]:
        print("MySQL password is not configured.")
        return None

    try:

        connection = mysql.connector.connect(
            host=DB_CONFIG["host"],
            user=DB_CONFIG["user"],
            password=DB_CONFIG["password"],
            database=DB_CONFIG["database"],
            use_pure=True
        )

        return connection

    except Exception as e:

        print("MySQL connection error:", e)

        return None


# ============================================================
# UPLOAD FOLDER
# ============================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER


# ============================================================
# GEMINI SETUP
# ============================================================

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if GEMINI_API_KEY:
    client = genai.Client(api_key=GEMINI_API_KEY)
else:
    client = None

GEMINI_MODEL = "gemini-3.6-flash"


# ============================================================
# CURRENT STUDY SESSION
# ============================================================

current_pdf = None

# ------------------------------------------------------------
# IMPORTANT:
#
# The uploaded PDF is extracted only ONCE after the first
# feature button is clicked.
#
# Summary, Questions, Quiz and AI Tutor can reuse
# the same extracted text.
# ------------------------------------------------------------

current_pdf_text = None

current_summary = None
current_questions = None


# ============================================================
# AI TUTOR CHAT HISTORY
# ============================================================

current_chat_history = []


# ============================================================
# PDF READING
# ============================================================

def read_pdf(file_path):
    """
    Reads all pages of a PDF and returns the extracted text.
    """

    reader = PdfReader(file_path)

    text_parts = []

    for page in reader.pages:

        page_text = page.extract_text()

        if page_text:
            text_parts.append(page_text)

    return "\n".join(text_parts)


# ============================================================
# CLEAN PDF TEXT
# ============================================================

def clean_text(text):
    """
    Cleans unnecessary spaces and blank lines
    from extracted PDF text.
    """

    if not text:
        return ""

    lines = []

    for line in text.splitlines():

        line = line.strip()

        if line:
            lines.append(line)

    return "\n".join(lines)


# ============================================================
# GET CURRENT PDF TEXT
# ============================================================

def get_current_pdf_text():
    """
    Returns the extracted text of the currently uploaded PDF.

    The PDF is read only the FIRST time this function is called
    after a new PDF is uploaded.

    After that, the already extracted text is reused.
    """

    global current_pdf
    global current_pdf_text

    if not current_pdf:
        return None

    # --------------------------------------------------------
    # If text has already been extracted, reuse it.
    # --------------------------------------------------------

    if current_pdf_text is not None:
        return current_pdf_text

    # --------------------------------------------------------
    # First time:
    # Read the PDF and store the extracted text.
    # --------------------------------------------------------

    file_path = os.path.join(
        app.config["UPLOAD_FOLDER"],
        current_pdf
    )

    if not os.path.exists(file_path):
        return None

    try:

        text = read_pdf(file_path)

        text = clean_text(text)

        if not text:
            return None

        current_pdf_text = text

        return current_pdf_text

    except Exception as e:

        print("PDF reading error:", e)

        return None


# ============================================================
# GEMINI HELPER
# ============================================================

def ask_gemini(prompt):
    """
    Sends a prompt to Gemini and returns the response text.
    """

    if not client:

        return None, (
            "Gemini API is not configured. "
            "Please set the GEMINI_API_KEY environment variable."
        )

    try:

        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt
        )

        if not response or not response.text:

            return None, "Gemini returned an empty response."

        return response.text.strip(), None

    except Exception as e:

        error_message = str(e)

        print("Gemini error:", error_message)

        if "401" in error_message or "403" in error_message:

            return None, (
                "Gemini API authorization failed. "
                "Please check your API key."
            )

        return None, (
            "Unable to generate the AI response right now. "
            "Please try again."
        )


# ============================================================
# HOME
# ============================================================

@app.route("/")
def home():

    return render_template("index.html")


# ============================================================
# ACCOUNT CHOICE
# ============================================================

@app.route("/account-choice")
def account_choice():

    return render_template("account_choice.html")


# ============================================================
# LOGIN
# ============================================================

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")

        # Check that both fields are filled
        if not email or not password:
            flash("Please enter your email and password.")
            return redirect(url_for("login"))

        connection = get_db_connection()

        if connection is None:
            flash("Unable to connect to the database.")
            return redirect(url_for("login"))

        try:

            cursor = connection.cursor(dictionary=True)

            query = """
                SELECT user_id, name, email, password_hash
                FROM users
                WHERE email = %s
            """

            cursor.execute(query, (email,))

            user = cursor.fetchone()

            cursor.close()
            connection.close()

            # Check if account exists
            if user is None:
                flash("Invalid email or password.")
                return redirect(url_for("login"))

            # Check password
            if not check_password_hash(
                user["password_hash"],
                password
            ):
                flash("Invalid email or password.")
                return redirect(url_for("login"))

            # Login successful
            session["user_id"] = user["user_id"]
            session["user_name"] = user["name"]
            session["user_email"] = user["email"]

            return redirect(url_for("dashboard"))

        except Exception as e:

            print("Login error:", e)

            if connection:
                connection.close()

            flash("Unable to login.")

            return redirect(url_for("login"))

    return render_template("login.html")


# ============================================================
# REGISTER
# ============================================================

@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        # Check that all fields are filled
        if not name or not email or not password or not confirm_password:

            flash("Please fill in all fields.")

            return redirect(url_for("register"))

        # Check that passwords match
        if password != confirm_password:

            flash("Passwords do not match.")

            return redirect(url_for("register"))

        # Create a secure password hash
        password_hash = generate_password_hash(password)

        connection = get_db_connection()

        if connection is None:

            flash("Unable to connect to the database.")

            return redirect(url_for("register"))

        try:

            cursor = connection.cursor()

            query = """
                INSERT INTO users
                (name, email, password_hash)
                VALUES (%s, %s, %s)
            """

            cursor.execute(
                query,
                (name, email, password_hash)
            )

            connection.commit()

            cursor.close()
            connection.close()

            flash("Account created successfully!")

            return redirect(url_for("dashboard"))

        except mysql.connector.IntegrityError:

            if connection:
                connection.close()

            flash("An account with this email already exists.")

            return redirect(url_for("register"))

        except Exception as e:

            print("Registration error:", e)

            if connection:
                connection.close()

            flash("Unable to create the account.")

            return redirect(url_for("register"))

    return render_template("register.html")


# ============================================================
# DASHBOARD
# ============================================================

@app.route("/dashboard")
def dashboard():

    # Check if the user is logged in
    if "user_id" not in session:
        return redirect(url_for("login"))

    # Get the user's latest uploaded PDF from the database
    connection = get_db_connection()

    if connection is None:
        flash("Unable to connect to the database.")
        return redirect(url_for("login"))

    user_pdf = None

    try:

        cursor = connection.cursor(dictionary=True)

        query = """
            SELECT filename
            FROM study_materials
            WHERE user_id = %s
            ORDER BY uploaded_at DESC
            LIMIT 1
        """

        cursor.execute(
            query,
            (session["user_id"],)
        )

        material = cursor.fetchone()

        cursor.close()
        connection.close()

        if material:
            user_pdf = material["filename"]

    except Exception as e:

        print("Dashboard database error:", e)

        if connection:
            connection.close()

        flash("Unable to load your study materials.")
        return redirect(url_for("login"))

    return render_template(
        "dashboard.html",
        current_pdf=user_pdf,
        user_name=session.get("user_name")
    )


# ============================================================
# UPLOAD PDF
# ============================================================

@app.route("/upload", methods=["POST"])
def upload():

    global current_pdf
    global current_pdf_text
    global current_summary
    global current_questions
    global current_chat_history

    # Make sure the user is logged in
    if "user_id" not in session:
        return redirect(url_for("login"))

    file = request.files.get("pdf_file")

    if not file or file.filename == "":

        flash("Please select a PDF file.")

        return redirect(url_for("dashboard"))

    filename = secure_filename(file.filename)

    if not filename.lower().endswith(".pdf"):

        flash("Please upload a PDF file.")

        return redirect(url_for("dashboard"))

    # --------------------------------------------------------
    # Delete previously uploaded PDF
    # --------------------------------------------------------

    if current_pdf:

        old_file_path = os.path.join(
            app.config["UPLOAD_FOLDER"],
            current_pdf
        )

        if os.path.exists(old_file_path):

            try:

                os.remove(old_file_path)

            except Exception as e:

                print("Could not delete old PDF:", e)

    # --------------------------------------------------------
    # Save new PDF
    #
    # PDF is NOT read here.
    # --------------------------------------------------------

    file_path = os.path.join(
        app.config["UPLOAD_FOLDER"],
        filename
    )

    try:

        file.save(file_path)

    except Exception as e:

        print("Upload error:", e)

        flash("Unable to upload the PDF.")

        return redirect(url_for("dashboard"))

    current_pdf = filename

    current_pdf_text = None

    current_summary = None
    current_questions = None

    current_chat_history = []

    # --------------------------------------------------------
    # Save PDF information for the logged-in user
    # --------------------------------------------------------

    connection = get_db_connection()

    if connection is None:

        flash("PDF uploaded, but could not save it to the database.")

        return redirect(url_for("dashboard"))

    try:

        cursor = connection.cursor()

        query = """
            INSERT INTO study_materials
            (user_id, filename)
            VALUES (%s, %s)
        """

        cursor.execute(
            query,
            (session["user_id"], filename)
        )

        connection.commit()

        cursor.close()
        connection.close()

    except Exception as e:

        print("Study material database error:", e)

        if connection:
            connection.close()

        flash("PDF uploaded, but could not save its information.")

        return redirect(url_for("dashboard"))

    flash("PDF uploaded successfully!")

    return redirect(url_for("dashboard"))

# ============================================================
# REPLACE PDF
# ============================================================

@app.route("/replace", methods=["POST"])
def replace():

    global current_pdf
    global current_pdf_text
    global current_summary
    global current_questions
    global current_chat_history

    file = request.files.get("pdf_file")

    if not file or file.filename == "":

        flash("Please select a PDF file.")

        return redirect(url_for("dashboard"))

    filename = secure_filename(file.filename)

    if not filename.lower().endswith(".pdf"):

        flash("Please upload a PDF file.")

        return redirect(url_for("dashboard"))

    # --------------------------------------------------------
    # Delete old PDF
    # --------------------------------------------------------

    if current_pdf:

        old_file_path = os.path.join(
            app.config["UPLOAD_FOLDER"],
            current_pdf
        )

        if os.path.exists(old_file_path):

            try:

                os.remove(old_file_path)

            except Exception as e:

                print("Could not delete old PDF:", e)

    # --------------------------------------------------------
    # Save replacement PDF
    # --------------------------------------------------------

    file_path = os.path.join(
        app.config["UPLOAD_FOLDER"],
        filename
    )

    try:

        file.save(file_path)

    except Exception as e:

        print("Replacement upload error:", e)

        flash("Unable to replace the PDF.")

        return redirect(url_for("dashboard"))

    current_pdf = filename

    current_pdf_text = None

    current_summary = None
    current_questions = None

    current_chat_history = []

    flash("PDF replaced successfully!")

    return redirect(url_for("dashboard"))


# ============================================================
# CLEAR PDF
# ============================================================

@app.route("/clear-pdf", methods=["POST"])
def clear_pdf():

    global current_pdf
    global current_pdf_text
    global current_summary
    global current_questions
    global current_chat_history

    if current_pdf:

        file_path = os.path.join(
            app.config["UPLOAD_FOLDER"],
            current_pdf
        )

        if os.path.exists(file_path):

            try:

                os.remove(file_path)

            except Exception as e:

                print("Could not delete PDF:", e)

    current_pdf = None

    current_pdf_text = None

    current_summary = None

    current_questions = None

    current_chat_history = []

    flash("PDF removed successfully!")

    return redirect(url_for("dashboard"))


# ============================================================
# SUMMARY
# ============================================================

@app.route("/summary")
def summary():

    global current_summary

    if not current_pdf:

        flash("Please upload a PDF first.")

        return redirect(url_for("dashboard"))

    if current_summary:

        return render_template(
            "study_summary.html",
            summary=current_summary,
            questions=None,
            pdf_name=current_pdf
        )

    text = get_current_pdf_text()

    if not text:

        flash(
            "The PDF could not be read. "
            "Please upload a readable PDF."
        )

        return redirect(url_for("dashboard"))

    prompt = f"""
You are StudyMate AI, an AI-powered smart study
assistant for college students.

Read the study material below and create a clear,
well-organized, simple and exam-friendly study summary.

IMPORTANT FORMATTING RULES:

1. Return the entire summary in clean Markdown.

2. Use Markdown headings properly:
   # for the main title
   ## for major sections
   ### for subsections

3. Do NOT use LaTeX at all.

4. Do NOT use dollar signs for mathematical expressions.
   Never use $...$ or $$...$$.

5. Write formulas in simple plain text.

6. Do not place unnecessary #, $, or other Markdown symbols
   inside normal sentences.

7. Use bullet points for important information.

8. Use numbered lists when explaining steps, procedures,
   types, rules, or algorithms.

9. Use Markdown tables for comparisons whenever the
   study material contains comparison information.

10. For tree structures, classification diagrams,
    flow-like structures, or ASCII diagrams, use a
    Markdown code block so that spacing and structure
    are preserved.

11. Preserve important diagrams and structures from the
    study material whenever they can be represented using
    text.

12. Keep important definitions exactly in meaning,
    but rewrite them in simple student-friendly language
    when necessary.

13. Keep important technical terms, formulas, examples,
    characteristics, advantages, disadvantages,
    applications, algorithms and comparisons.

14. Explain difficult concepts in simple language suitable
    for a BCA college student.

15. Do not remove important information from the
    study material.

16. Do not add facts that are not present in the
    study material.

17. Organize the summary logically so that a student can
    easily revise it before an examination.

18. Use short paragraphs instead of large blocks of text.

19. For comparisons, prefer a clean table with proper
    column headings.

20. For classifications, prefer a simple structured
    diagram or hierarchy when appropriate.

21. Do not include HTML, CSS, JavaScript, or programming
    code unless it is actually part of the study material.

22. Do not write introductory comments about how you
    generated the summary.

23. Return ONLY the final study summary in Markdown.

Study Material:

{text}
"""

    summary_text, error_message = ask_gemini(prompt)

    if error_message:

        flash(error_message)

        return redirect(url_for("dashboard"))

    current_summary = summary_text

    return render_template(
        "study_summary.html",
        summary=current_summary,
        questions=None,
        pdf_name=current_pdf
    )


# ============================================================
# IMPORTANT QUESTIONS
# ============================================================

@app.route("/questions")
def questions():

    global current_questions
    global current_summary

    if not current_pdf:

        flash("Please upload a PDF first.")

        return redirect(url_for("dashboard"))

    text = get_current_pdf_text()

    if not text:

        flash(
            "The PDF could not be read. "
            "Please upload a readable PDF."
        )

        return redirect(url_for("dashboard"))

    if current_questions:

        return render_template(
            "study_summary.html",
            summary=current_summary,
            questions=current_questions,
            pdf_name=current_pdf
        )

    prompt = f"""
You are StudyMate AI, an exam preparation assistant
for college students.

Read the study material below and generate important
exam questions strictly from the provided material.

Rules:

1. Create 10 important questions.
2. Include short-answer and long-answer questions.
3. Focus on definitions, concepts, differences,
   characteristics, applications, algorithms,
   and important technical topics.
4. Do not create questions about information that
   is not present in the study material.
5. Keep the wording simple and student-friendly.
6. Number every question clearly.
7. Do not provide answers.
8. Organize the output under:

Short Answer Questions

Long Answer Questions

Study Material:

{text}
"""

    questions_text, error_message = ask_gemini(prompt)

    if error_message:

        flash(error_message)

        return redirect(url_for("summary"))

    current_questions = questions_text

    return render_template(
        "study_summary.html",
        summary=current_summary,
        questions=current_questions,
        pdf_name=current_pdf
    )


# ============================================================
# AI TUTOR
# ============================================================

@app.route("/ask", methods=["GET", "POST"])
def ask():

    global current_chat_history

    if not current_pdf:

        flash("Please upload a PDF first.")

        return redirect(url_for("dashboard"))

    if request.method == "GET":

        return render_template(
            "ask_question.html",
            pdf_name=current_pdf,
            chat_history=current_chat_history
        )

    question = request.form.get("question", "").strip()

    if not question:

        flash("Please enter a question.")

        return render_template(
            "ask_question.html",
            pdf_name=current_pdf,
            chat_history=current_chat_history
        )

    text = get_current_pdf_text()

    if not text:

        flash(
            "The PDF could not be read. "
            "Please upload a readable PDF."
        )

        return redirect(url_for("dashboard"))

    prompt = f"""
You are StudyMate AI, an AI tutor.

Answer the student's question using ONLY the
uploaded study material below.

Rules:

1. Give a clear and student-friendly answer.
2. Explain the concept simply.
3. Keep the answer useful for college exams.
4. Do not invent information that is not supported
   by the uploaded study material.
5. If the answer cannot be found in the uploaded
   study material, clearly say that the information
   is not available in the uploaded material.

IMPORTANT FORMATTING RULES:

6. Return the answer in clean Markdown.
7. Use headings such as ## or ### only when useful.
8. Do not use unnecessary # symbols.
9. Do not use HTML.
10. Use bullet points or numbered lists when they
    make the explanation easier to understand.
11. Keep the answer clear and well organized.
12. Do not include an introduction about being an AI.

Uploaded Study Material:

{text}

Student Question:

{question}
"""

    answer, error_message = ask_gemini(prompt)

    if error_message:

        flash(error_message)

        return render_template(
            "ask_question.html",
            pdf_name=current_pdf,
            chat_history=current_chat_history
        )

    current_chat_history.append(
        {
            "question": question,
            "answer": answer
        }
    )

    return render_template(
        "ask_question.html",
        pdf_name=current_pdf,
        chat_history=current_chat_history
    )


# ============================================================
# AI TUTOR ALTERNATIVE ROUTE
# ============================================================

@app.route("/ask-question", methods=["POST"])
def ask_question():

    global current_chat_history

    if not current_pdf:

        flash("Please upload a PDF first.")

        return redirect(url_for("dashboard"))

    question = request.form.get("question", "").strip()

    if not question:

        flash("Please enter a question.")

        return redirect(url_for("ask"))

    text = get_current_pdf_text()

    if not text:

        flash(
            "The PDF could not be read. "
            "Please upload a readable PDF."
        )

        return redirect(url_for("dashboard"))

    prompt = f"""
You are StudyMate AI, an AI tutor.

Answer the student's question using ONLY the
uploaded study material below.

Rules:

1. Give a clear and student-friendly answer.
2. Explain the concept simply.
3. Keep the answer useful for college exams.
4. Do not invent information that is not supported
   by the uploaded study material.
5. If the answer cannot be found in the uploaded
   study material, clearly say that the information
   is not available in the uploaded material.

IMPORTANT FORMATTING RULES:

6. Return the answer in clean Markdown.
7. Use headings such as ## or ### only when useful.
8. Do not use unnecessary # symbols.
9. Do not use HTML.
10. Use bullet points or numbered lists when they
    make the explanation easier to understand.
11. Keep the answer clear and well organized.
12. Do not include an introduction about being an AI.

Uploaded Study Material:

{text}

Student Question:

{question}
"""

    answer, error_message = ask_gemini(prompt)

    if error_message:

        flash(error_message)

        return redirect(url_for("ask"))

    current_chat_history.append(
        {
            "question": question,
            "answer": answer
        }
    )

    return render_template(
        "ask_question.html",
        pdf_name=current_pdf,
        chat_history=current_chat_history
    )


# ============================================================
# RUN APPLICATION
# ============================================================

if __name__ == "__main__":

    app.run(
        debug=True
    )