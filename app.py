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
        
        for i, c in enumerate(codes):
            try:
                # Start fetching message
                yield json.dumps({
                    "type": "progress",
                    "current": i,
                    "total": total,
                    "code": c,
                    "status": "fetching"
                }) + "\n"
                
                course = ALL_COURSES.get(c) if ALL_COURSES else fetch_course(c)
                app.logger.info(" • %s → %s", c, "FOUND" if course else "MISSING")
                
                if course:
                    # Format course data properly
                    formatted_course = {
                        "code": course['code'],
                        "title": course['title'],
                        "requisites": course.get('requisites', "None specified"),
                        "assessment": []
                    }
                    
                    # Format assessment data
                    for task in course.get('assessment', []):
                        if task.get('title') and task.get('details'):
                            formatted_course['assessment'].append({
                                "title": task['title'],
                                "details": {
                                    "Type": task['details'].get('Type', 'Unknown'),
                                    "Weight": task['details'].get('Weight', '0%'),
                                    "Groupwork": task['details'].get('Groupwork', 'Individual'),
                                    "Length": task['details'].get('Length', 'Not specified'),
                                    "Intent": task['details'].get('Intent', '')
                                }
                            })
                    
                    results.append(formatted_course)
                    yield json.dumps({
                        "type": "progress",
                        "current": i + 1,
                        "total": total,
                        "code": c,
                        "status": "success"
                    }) + "\n"
                else:
                    results.append({"code": c, "error": "not found"})
                    yield json.dumps({
                        "type": "progress",
                        "current": i + 1,
                        "total": total,
                        "code": c,
                        "status": "error",
                        "error": "Course not found"
                    }) + "\n"
                
            except Exception as e:
                app.logger.error(f"Error fetching {c}: {e}", exc_info=True)
                error_result = {"code": c, "error": str(e)}
                results.append(error_result)
                yield json.dumps({
                    "type": "progress",
                    "current": i + 1,
                    "total": total,
                    "code": c,
                    "status": "error",
                    "error": str(e)
                }) + "\n"
        
        # Send final results
        yield json.dumps({
            "type": "complete",
            "results": results
        })
    
    return Response(generate(), mimetype='application/x-ndjson')

@app.after_request
def add_header(response):
    response.cache_control.max_age = 300  # 5 minutes
    return response

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)