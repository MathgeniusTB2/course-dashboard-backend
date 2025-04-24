# app.py
from flask import Flask, request, jsonify
from test import fetch_course  # your existing code factored into fetch_course()
import json
from flask_cors import CORS  # Enable CORS
import os

app = Flask(__name__, static_folder='static')
CORS(app)  # Enable CORS for all routes

# Load pre-fetched data if available
try:
    with open('courses.json', encoding='utf-8') as f:
        ALL_COURSES = {c['code']: c for c in json.load(f)}
except FileNotFoundError:
    ALL_COURSES = None

# serve index.html at root
@app.route('/')
def index():
    return app.send_static_file('index.html')

@app.route('/api/courses', methods=['POST'])
def api_courses():
    data = request.get_json()
    codes = data.get('subject_codes', [])
    app.logger.info("→ received codes: %s", codes)
    results = []
    
    for c in codes:
        try:
            course = ALL_COURSES.get(c) if ALL_COURSES else fetch_course(c)
            app.logger.info(" • %s → %s", c, "FOUND" if course else "MISSING")
            
            # Ensure prerequisite information is included
            if course and 'requisites' not in course:
                course['requisites'] = "None specified"
                
            results.append(course or {"code": c, "error": "not found"})
        except Exception as e:
            app.logger.error(f"Error fetching {c}: {e}", exc_info=True)
            results.append({"code": c, "error": str(e)})
    
    return jsonify(results)

@app.after_request
def add_header(response):
    response.cache_control.max_age = 300  # 5 minutes
    return response

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)