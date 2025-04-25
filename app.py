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
        total_steps = len(codes)
        current_step = 0
        
        for i, c in enumerate(codes):
            try:
                # Send progress update at start of fetching
                current_step = i
                yield json.dumps({
                    "type": "progress",
                    "current": current_step,
                    "total": total_steps,
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
                
                # Send progress update after processing
                yield json.dumps({
                    "type": "progress",
                    "current": current_step + 1,
                    "total": total_steps,
                    "code": c,
                    "status": "success" if course else "error"
                }) + "\n"
                
                # Update for next iteration
                current_step += 1
                
            except Exception as e:
                app.logger.error(f"Error fetching {c}: {e}", exc_info=True)
                error_result = {"code": c, "error": str(e)}
                results.append(error_result)
                # Send error progress update
                yield json.dumps({
                    "type": "progress",
                    "current": current_step + 1,
                    "total": total_steps,
                    "code": c,
                    "status": "error",
                    "error": str(e)
                }) + "\n"
                # Update for next iteration
                current_step += 1
        
        # Send the final complete message
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