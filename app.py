# app.py
from flask import Flask, request, jsonify, Response
from flask_cors import CORS  # Enable CORS
import json
import os
import sys
from bs4 import BeautifulSoup
import requests
import time

app = Flask(__name__, static_folder='static')
CORS(app)  # Enable CORS for all routes

# Global cache for course data
ALL_COURSES = {}

def fetch_course(code):
    """Fetches and parses course information."""
    BASE_URL = "https://handbookpre2025.uts.edu.au/2024/subjects/details"
    url = f"{BASE_URL}/{code}.html"
    
    try:
        resp = requests.get(url)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, 'html.parser')

        # --- Helpers ---
        def get_section_header(tag, text):
            return tag.find(lambda t: t.name == 'h3' and text in t.get_text())

        # --- Basic Info ---
        title = soup.find('h1').get_text(strip=True) if soup.find('h1') else ''

        # Credit points & result type & requisites via <em> tags
        credit_points = ''
        result_type = ''
        requisites = ''
        for em in soup.find_all('em'):
            txt = em.get_text(strip=True)
            if txt.startswith('Credit points'):
                credit_points = em.next_sibling.strip() if em.next_sibling else ''
            elif txt.startswith('Result type'):
                result_type = em.next_sibling.strip() if em.next_sibling else ''
            elif txt.startswith('Requisite'):
                requisites = em.get_text(separator=' ', strip=True).replace('Requisite(s):', '').strip()

        # --- Overview ---
        overview = ''
        desc_hdr = get_section_header(soup, 'Description')
        if desc_hdr:
            p = desc_hdr.find_next('p')
            overview = p.get_text(strip=True) if p else ''

        # --- Learning Outcomes ---
        learning_outcomes = []
        slo_hdr = get_section_header(soup, 'Subject learning objectives')
        if slo_hdr:
            slo_table = slo_hdr.find_next('table', class_='SLOTable')
            if slo_table:
                for row in slo_table.select('tr'):
                    th = row.find('th')
                    td = row.find('td')
                    if th and td:
                        learning_outcomes.append({
                            'no': th.get_text(strip=True).rstrip('.'),
                            'text': td.get_text(strip=True)
                        })

        # --- Content and Other Sections ---
        def extract_section(soup, heading):
            hdr = get_section_header(soup, heading)
            blocks = []
            if hdr:
                for sib in hdr.find_next_siblings():
                    if sib.name == 'h3': break
                    if sib.name in ('p', 'ul', 'ol'):
                        blocks.append(sib.get_text("\n", strip=True))
            return '\n\n'.join(blocks)

        content_topics = extract_section(soup, 'Content (topics)')
        teaching_strategies = extract_section(soup, 'Teaching and learning strategies')
        minimum_requirements = extract_section(soup, 'Minimum requirements')
        recommended_texts = extract_section(soup, 'Recommended texts')

        # --- Assessment Tasks ---
        assessment = []
        assess_hdr = get_section_header(soup, 'Assessment')
        if assess_hdr:
            task = None
            for node in assess_hdr.find_all_next():
                if node.name == 'h3': break
                
                if node.name == 'h4':
                    if task: assessment.append(task)
                    task = {'title': node.get_text(strip=True), 'details': {}}
                
                elif task and node.name == 'table' and 'assessmentTaskTable' in (node.get('class') or []):
                    for row in node.select('tr'):
                        th = row.find('th')
                        td = row.find('td')
                        if th and td:
                            key = th.get_text(strip=True).rstrip(':')
                            value = td.get_text("\n", strip=True)
                            task['details'][key] = value
            
            if task: assessment.append(task)

        return {
            'code': code,
            'title': title,
            'credit_points': credit_points,
            'result_type': result_type,
            'requisites': requisites,
            'overview': overview,
            'learning_outcomes': learning_outcomes,
            'teaching_strategies': teaching_strategies,
            'content_topics': content_topics,
            'minimum_requirements': minimum_requirements,
            'recommended_texts': recommended_texts,
            'assessment': assessment
        }

    except Exception as e:
        app.logger.error(f"Error fetching {code}: {e}", exc_info=True)
        raise

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
                    results.append(course)
                
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