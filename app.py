from flask import Flask, render_template, request, redirect, url_for, flash
import os
from pypdf import PdfReader
from google import genai
from werkzeug.utils import secure_filename


# ============================================================
# FLASK SETUP
# ============================================================

app = Flask(__name__)

app.secret_key = "studymate-ai-project-key"


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
# This stores the extracted text of the uploaded PDF.
#
# The PDF is extracted only ONCE after the first feature
# button is clicked.
#
# Summary, Questions, Quiz and AI Tutor can all reuse
# this same extracted text.
# ------------------------------------------------------------

current_pdf_text = None

current_summary = None
current_questions = None


# ------------------------------------------------------------
# AI TUTOR CHAT HISTORY
#
# Each question and answer is stored here.
#
# Example:
#
# [
#     {
#         "question": "What is a data structure?",
#         "answer": "A data structure is..."
#     },
#     {
#         "question": "What are arrays?",
#         "answer": "An array is..."
#     }
# ]
#
# This allows the AI Tutor page to behave like chat history.
# ------------------------------------------------------------

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

    IMPORTANT:
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

        # ----------------------------------------------------
        # IMPORTANT:
        #
        # Store the extracted text.
        #
        # From this point onward, Summary, Questions,
        # Quiz and AI Tutor will reuse this text.
        # ----------------------------------------------------

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

    return redirect(url_for("login"))


# ============================================================
# LOGIN
# ============================================================

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        return redirect(url_for("dashboard"))

    return render_template("login.html")


# ============================================================
# DASHBOARD
# ============================================================

@app.route("/dashboard")
def dashboard():

    return render_template(
        "dashboard.html",
        current_pdf=current_pdf
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

    file = request.files.get("pdf_file")

    if not file or file.filename == "":

        flash("Please select a PDF file.")

        return redirect(url_for("dashboard"))

    # --------------------------------------------------------
    # Check file extension
    # --------------------------------------------------------

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
    # IMPORTANT:
    # We intentionally DO NOT read the PDF here.
    #
    # The PDF will be read when the user clicks their first
    # feature such as Summary, Quiz or AI Tutor.
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

    # --------------------------------------------------------
    # Set new current PDF
    # --------------------------------------------------------

    current_pdf = filename

    # --------------------------------------------------------
    # Reset extracted text
    #
    # Because this is a NEW PDF.
    # --------------------------------------------------------

    current_pdf_text = None

    # --------------------------------------------------------
    # Reset old AI results
    # --------------------------------------------------------

    current_summary = None
    current_questions = None

    # --------------------------------------------------------
    # Reset old AI Tutor chat history
    # --------------------------------------------------------

    current_chat_history = []

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

    # --------------------------------------------------------
    # Reset current study session
    # --------------------------------------------------------

    current_pdf = filename

    current_pdf_text = None

    current_summary = None

    current_questions = None

    # --------------------------------------------------------
    # Reset AI Tutor history because this is a new PDF
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # Clear everything related to the current PDF
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # If summary already exists, show it immediately.
    # --------------------------------------------------------

    if current_summary:

        return render_template(
            "study_summary.html",
            summary=current_summary,
            questions=None,
            pdf_name=current_pdf
        )

    # --------------------------------------------------------
    # Get extracted PDF text.
    #
    # If another feature already extracted it,
    # the cached text is reused.
    # --------------------------------------------------------

    text = get_current_pdf_text()

    if not text:

        flash(
            "The PDF could not be read. "
            "Please upload a readable PDF."
        )

        return redirect(url_for("dashboard"))

    # --------------------------------------------------------
    # FINALIZED SUMMARY PROMPT
    # --------------------------------------------------------

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
        Example:
        Address = Base Address + W × (i - Lower Bound)

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

    The final result should look like a professionally prepared
    college exam revision note, with clear headings, readable
    sections, bullet points, tables, formulas and diagrams where
    appropriate.

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

    # --------------------------------------------------------
    # Get cached PDF text.
    # --------------------------------------------------------

    text = get_current_pdf_text()

    if not text:

        flash(
            "The PDF could not be read. "
            "Please upload a readable PDF."
        )

        return redirect(url_for("dashboard"))

    # --------------------------------------------------------
    # If questions already exist, display them.
    # --------------------------------------------------------

    if current_questions:

        return render_template(
            "study_summary.html",
            summary=current_summary,
            questions=current_questions,
            pdf_name=current_pdf
        )

    # --------------------------------------------------------
    # QUESTIONS PROMPT
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # GET REQUEST
    #
    # Show the AI Tutor page.
    #
    # IMPORTANT:
    # Existing chat history is sent to the template.
    # Therefore, clicking "Ask Another Question" does
    # NOT erase previous questions and answers.
    # --------------------------------------------------------

    if request.method == "GET":

        return render_template(
            "ask_question.html",
            pdf_name=current_pdf,
            chat_history=current_chat_history
        )

    # --------------------------------------------------------
    # POST REQUEST
    # --------------------------------------------------------

    question = request.form.get("question", "").strip()

    if not question:

        flash("Please enter a question.")

        return render_template(
            "ask_question.html",
            pdf_name=current_pdf,
            chat_history=current_chat_history
        )

    # --------------------------------------------------------
    # Get cached PDF text.
    #
    # If Summary, Questions or Quiz already extracted it,
    # this will NOT read the PDF again.
    #
    # If AI Tutor is the FIRST feature clicked, the PDF
    # will be extracted here ONCE.
    # --------------------------------------------------------

    text = get_current_pdf_text()

    if not text:

        flash(
            "The PDF could not be read. "
            "Please upload a readable PDF."
        )

        return redirect(url_for("dashboard"))

    # --------------------------------------------------------
    # AI TUTOR PROMPT
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # SAVE QUESTION + ANSWER TO CHAT HISTORY
    #
    # IMPORTANT:
    # We append instead of replacing the previous answer.
    # Therefore, every question remains visible.
    # --------------------------------------------------------

    current_chat_history.append(
        {
            "question": question,
            "answer": answer
        }
    )

    # --------------------------------------------------------
    # SHOW THE COMPLETE CHAT HISTORY
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # Get cached PDF text.
    # --------------------------------------------------------

    text = get_current_pdf_text()

    if not text:

        flash(
            "The PDF could not be read. "
            "Please upload a readable PDF."
        )

        return redirect(url_for("dashboard"))

    # --------------------------------------------------------
    # AI TUTOR PROMPT
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # ADD NEW QUESTION + ANSWER TO CHAT HISTORY
    # --------------------------------------------------------

    current_chat_history.append(
        {
            "question": question,
            "answer": answer
        }
    )

    # --------------------------------------------------------
    # SHOW COMPLETE CHAT HISTORY
    # --------------------------------------------------------

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