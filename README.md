# Final Destination Flask App

This is a simple Flask web application deployed on Render.com.

## 📁 Project Structure

/static          → Static files (CSS, JS, Images)  
/templates       → HTML Templates  
app.py           → Main Flask Application  
database.db      → SQLite Database  
requirements.txt → Python dependencies  

## 🚀 How to Run Locally

1. Install dependencies:

   pip install -r requirements.txt

2. Run the app:

   python app.py

3. Open your browser and go to:

   http://localhost:5000

## 🌐 Deployment

This app is deployed on **Render.com** using Gunicorn.  

The start command for Render is:

   gunicorn app:app
