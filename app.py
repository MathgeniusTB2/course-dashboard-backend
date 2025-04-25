# app.py
from flask import Flask, request, jsonify, Response
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
    
    def generate():
        results = []
        total = len(codes)
        completed = 0
        
        for code in codes:
            try:
                course = ALL_COURSES.get(code) if ALL_COURSES else fetch_course(code)
                app.logger.info(" • %s → %s", code, "FOUND" if course else "MISSING")
                
                if course:
                    # Format course data properly with all details
                    formatted_course = {
                        "code": course['code'],
                        "title": course['title'],
                        "requisites": course.get('requisites', "None specified"),
                        "overview": course.get('overview', ''),
                        "credit_points": course.get('credit_points', ''),
                        "result_type": course.get('result_type', ''),
                        "content_topics": course.get('content_topics', ''),
                        "teaching_strategies": course.get('teaching_strategies', ''),
                        "minimum_requirements": course.get('minimum_requirements', ''),
                        "recommended_texts": course.get('recommended_texts', ''),
                        "learning_outcomes": course.get('learning_outcomes', []),
                        "CILOs": course.get('CILOs', []),
                        "assessment": []
                    }
                    
                    # Format assessment data
                    for task in course.get('assessment', []):
                        if task.get('title') and task.get('details'):
                            details = task['details']
                            formatted_course['assessment'].append({
                                "title": task['title'],
                                "details": {
                                    "Type": details.get('Type', 'Unknown'),
                                    "Weight": details.get('Weight', '0%'),
                                    "Groupwork": details.get('Groupwork', 'Individual'),
                                    "Length": details.get('Length', 'Not specified'),
                                    "Intent": details.get('Intent', '')
                                }
                            })
                    
                    results.append(formatted_course)
                
                completed += 1
                yield json.dumps({
                    "type": "progress",
                    "completed": completed,
                    "total": total,
                    "code": code
                }) + "\n"
                
            except Exception as e:
                app.logger.error(f"Error fetching {code}: {e}", exc_info=True)
                error_result = {"code": code, "error": str(e)}
                results.append(error_result)
                completed += 1
                yield json.dumps({
                    "type": "progress",
                    "completed": completed,
                    "total": total,
                    "code": code,
                    "error": str(e)
                }) + "\n"
        
        # Send final results
        yield json.dumps({
            "type": "complete",
            "results": results
        }) + "\n"
    
    return Response(generate(), mimetype='application/x-ndjson')

@app.after_request
def add_header(response):
    response.cache_control.max_age = 300  # 5 minutes
    return response

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)