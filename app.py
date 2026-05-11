from flask import Flask, render_template, request, redirect, url_for, session
from flask_mail import Mail, Message
import mysql.connector
import os
import torch
from transformers import BertTokenizer, BertForSequenceClassification
import base64
import requests
from bs4 import BeautifulSoup
from PIL import Image
import pytesseract
from pydub import AudioSegment
import speech_recognition as sr
from deep_translator import GoogleTranslator
from itsdangerous import URLSafeTimedSerializer

app = Flask(__name__)
app.secret_key = os.urandom(24)

pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'benhettalmaryem@gmail.com'
app.config['MAIL_PASSWORD'] = 'maryem2222'
mail = Mail(app)

serializer = URLSafeTimedSerializer(app.secret_key)


MODEL_PATH = "fine_tuned_bert"
tokenizer = BertTokenizer.from_pretrained(MODEL_PATH)
model = BertForSequenceClassification.from_pretrained(MODEL_PATH)
model.eval()

def get_db_connection():
    return mysql.connector.connect(
        host='localhost',
        user='root',
        password='',
        database='PFE'
    )

def add_user(username, email, password):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO users (username, email, password) VALUES (%s, %s, %s)", (username, email, password))
        conn.commit()
        return True
    except mysql.connector.IntegrityError:
        return False
    finally:
        cursor.close()
        conn.close()

def check_user(email, password):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE email = %s AND password = %s", (email, password))
    user = cursor.fetchone()
    cursor.close()
    conn.close()
    return user

def add_analysis_to_history(user_id, texte):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO analyses (user_id, texte) VALUES (%s, %s)", (user_id, texte))
    conn.commit()
    cursor.close()
    conn.close()

def get_user_analyses(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT texte FROM analyses WHERE user_id = %s ORDER BY id DESC", (user_id,))
    results = cursor.fetchall()
    cursor.close()
    conn.close()
    return results

def clean_content(text):
    return ' '.join(text.strip().split())

def process_url(url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=15)
        soup = BeautifulSoup(response.content, 'html.parser')
        text = ' '.join([p.get_text() for p in soup.find_all('p')])
        return clean_content(text)
    except Exception as e:
        return f"Erreur URL: {e}"

def process_image(image_path):
    try:
        img = Image.open(image_path)
        text = pytesseract.image_to_string(img)
        return clean_content(text)
    except Exception as e:
        return f"Erreur OCR: {e}"

def audio_to_text(audio_path):
    try:
        wav_path = "converted_audio.wav"
        audio = AudioSegment.from_file(audio_path)
        audio.export(wav_path, format="wav")
        recognizer = sr.Recognizer()
        with sr.AudioFile(wav_path) as source:
            audio_data = recognizer.record(source)
        text = recognizer.recognize_google(audio_data)
        return clean_content(text)
    except Exception as e:
        return f"Erreur audio: {e}"

def process_input(input_data):
    if isinstance(input_data, str) and input_data.startswith('http'):
        return process_url(input_data)
    elif isinstance(input_data, str) and input_data.lower().endswith(('jpg', 'jpeg', 'png')):
        return process_image(input_data)
    elif isinstance(input_data, str) and input_data.lower().endswith(('wav', 'mp3', 'flac', 'm4a', 'webm')):
        return audio_to_text(input_data)
    else:
        return clean_content(input_data)

def translate_to_english(text, max_chunk_length=500):
    if not text or not isinstance(text, str):
        return "❌ Aucun texte à traduire."
    chunks = [text[i:i+max_chunk_length] for i in range(0, len(text), max_chunk_length)]
    translated_chunks = []
    for i, chunk in enumerate(chunks):
        try:
            translated = GoogleTranslator(source='auto', target='en').translate(chunk)
            translated_chunks.append(translated)
        except Exception as e:
            print(f"[❌ Erreur de traduction au chunk {i}] : {e}")
            translated_chunks.append("[[Traduction échouée]]")
    return " ".join(translated_chunks)

def predict_fake_news(text):
    inputs = tokenizer(text, return_tensors="pt", truncation=True, padding=True, max_length=512)
    with torch.no_grad():
        outputs = model(**inputs)
        prediction = torch.argmax(outputs.logits, dim=1).item()
        return "❌ L'article semble faux." if prediction == 1 else "✅ L'article semble fiable."

def model_predict(text):
    return predict_fake_news(text)

@app.before_request
def setup_visitor_analysis_limit():
    if 'user_id' not in session:
        session.setdefault('visitor_analyses', 0)

@app.route('/')
def home():
    return render_template('principal.html')


@app.route('/a_propos')
def a_propos():
    return render_template('apropos.html')

@app.route('/fonctionnalite')
def fonctionnalite():
    return render_template('fonctionnalite.html')

@app.route('/contact')
def contact():
    return render_template('contact.html')

@app.route('/oublie')
def oublie():
    return render_template('oublie.html')

@app.route('/principal')
def principal():
    return render_template('principal.html')

@app.route('/commencer')
def commencer():
    return render_template('commencer.html')


@app.route('/inscription', methods=['GET', 'POST'])
def inscription():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        confirm = request.form['confirm_password']
        if password != confirm:
            return "❌ Les mots de passe ne correspondent pas."
        if not add_user(username, email, password):
            return "❌ Cet email est déjà utilisé."
        return redirect(url_for('connexion'))
    return render_template('inscription.html')

@app.route('/connexion', methods=['GET', 'POST'])
def connexion():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        user = check_user(email, password)
        if user:
            session['user_id'] = user[0]
            session['username'] = user[1]
            return redirect(url_for('analyse'))
        return "❌ Identifiants incorrects."
    return render_template('connexion.html')



NEWSAPI_KEY = 'ea51b7e3334847ca807c677f97f1700f'

def get_news_links(query, max_results=5):
    if not query or query.strip() == '':
        return []
    url = 'https://newsapi.org/v2/everything'
    params = {
        'q': query,
        'pageSize': max_results,
        'apiKey': NEWSAPI_KEY,
        'language': 'fr'  
    }
    try:
        response = requests.get(url, params=params)
        data = response.json()
        if data.get('status') == 'ok':
            articles = data.get('articles', [])
            return [(art['title'], art['url']) for art in articles if art.get('title') and art.get('url')]
        else:
            print("NewsAPI error:", data.get('message'))
            return []
    except Exception as e:
        print(f"Erreur API News: {e}")
        return []

@app.route('/analyse', methods=['GET', 'POST'])
def analyse():
    if not os.path.exists('uploads'):
        os.makedirs('uploads')

    result = None
    analyses = []
    texte_original = None
    texte_traduit = None
    image_base64 = None
    user_logged_in = 'user_id' in session
    max_visitor_analyses = 3
    visitor_analyses = session.get('visitor_analyses', 0)

    contenu = None
    texte = request.form.get('texte', '').strip()
    url = request.form.get('url', '').strip()
    audio_data = request.form.get('audio_blob')
    image = request.files.get('image')
    audio_file = request.files.get('audio')

    if request.method == 'POST':
        if user_logged_in or visitor_analyses < max_visitor_analyses:
            if texte:
                contenu = process_input(texte)
            elif url and user_logged_in:
                contenu = process_input(url)
            elif image and image.filename != '' and user_logged_in:
                image_path = os.path.join('uploads', image.filename)
                image.save(image_path)
                contenu = process_input(image_path)
                with open(image_path, 'rb') as img_file:
                    image_base64 = base64.b64encode(img_file.read()).decode('utf-8')
            elif audio_file and audio_file.filename != '' and user_logged_in:
                audio_path = os.path.join('uploads', audio_file.filename)
                audio_file.save(audio_path)
                contenu = process_input(audio_path)
            elif audio_data and user_logged_in:
                audio_path = 'uploads/recorded_audio.webm'
                header, encoded = audio_data.split(',', 1)
                audio_bytes = base64.b64decode(encoded)
                with open(audio_path, 'wb') as f:
                    f.write(audio_bytes)
                contenu = process_input(audio_path)

            if contenu:
                texte_original = contenu if isinstance(contenu, str) else str(contenu)
                texte_traduit = translate_to_english(texte_original)
                
                news_links = get_news_links(texte_original[:100]) 
                
                if user_logged_in:
                    add_analysis_to_history(session['user_id'], texte_original)
                    result = model_predict(texte_traduit)
                    analyses = get_user_analyses(session['user_id'])
                else:
                    session['visitor_analyses'] = visitor_analyses + 1
                    result = model_predict(texte_traduit)
            else:
                news_links = []
        else:
            result = "❌ Limite atteinte. Veuillez vous connecter pour accéder à tous les modes."
            news_links = []
    else:
        news_links = []

    return render_template('commencer.html',
                           username=session.get('username'),
                           result=result,
                           analyses=analyses,
                           texte_original=texte_original,
                           texte_traduit=texte_traduit,
                           image_base64=image_base64,
                           logged_in=user_logged_in,
                           news_links=news_links,
                           visitor_analyses=session.get('visitor_analyses', 0),
                           max_visitor_analyses=max_visitor_analyses)


@app.route('/logout')
def logout():
    session.clear()  
    return redirect(url_for('principal'))  


if __name__ == '__main__':
    app.run(debug=True)
