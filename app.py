from flask import Flask, request, jsonify, Response
from flask_cors import CORS
import json
import logging
from bs4 import BeautifulSoup
import requests
from typing import Dict, List, Optional
import os

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__, static_folder='static')

# Configure CORS with environment-based origins
ALLOWED_ORIGINS = ['https://mathgeniustb2.github.io']
if os.environ.get('FLASK_ENV') == 'development':
    ALLOWED_ORIGINS.append('http://localhost:*')

CORS(app, resources={
    r"/*": {
        "origins": ALLOWED_ORIGINS,
        "methods": ["GET", "POST", "OPTIONS"],
        "allow_headers": ["Content-Type"],
        "max_age": 3600,
        "supports_credentials": True
    }
})

# Global cache for course data
course_cache: Dict[str, dict] = {}

def fetch_course(code: str) -> dict:
    """Fetches and parses course information."""
    BASE_URL = "https://handbookpre2025.uts.edu.au/2024/subjects/details"
    
    try:
        response = requests.get(f"{BASE_URL}/{code}.html")
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Extract course data using helper functions
        course_data = {
            'code': code,
            'title': _extract_title(soup),
            'credit_points': _extract_credit_points(soup),
            'requisites': _extract_requisites(soup),
            'overview': _extract_overview(soup),
            'learning_outcomes': _extract_learning_outcomes(soup),
            'assessment': _extract_assessment(soup)
        }
        
        return course_data
    except Exception as e:
        logger.error(f"Error fetching course {code}: {e}")
        raise

def _extract_title(soup: BeautifulSoup) -> str:
    """Extract course title from soup"""
    if title_elem := soup.find('h1'):
        return title_elem.get_text(strip=True)
    return ''

def _extract_credit_points(soup: BeautifulSoup) -> str:
    """Extract credit points from soup"""
    for em in soup.find_all('em'):
        if txt := em.get_text(strip=True):
            if txt.startswith('Credit points'):
                return em.next_sibling.strip() if em.next_sibling else ''
    return ''

def _extract_requisites(soup: BeautifulSoup) -> str:
    """Extract requisites from soup"""
    for em in soup.find_all('em'):
        if txt := em.get_text(strip=True):
            if txt.startswith('Requisite'):
                return em.get_text(separator=' ', strip=True).replace('Requisite(s):', '').strip()
    return ''

def _extract_overview(soup: BeautifulSoup) -> Dict:
    """Extract course overview sections"""
    overview = {
        'description': '',
        'teaching_strategies': [],
        'topics': []
    }
    
    if desc_section := _find_section(soup, 'Description'):
        overview['description'] = _extract_section_text(desc_section)
    
    if strategies_section := _find_section(soup, 'Teaching and learning strategies'):
        overview['teaching_strategies'] = _extract_section_list(strategies_section)
    
    if topics_section := _find_section(soup, 'Content (topics)'):
        topics_text = _extract_section_text(topics_section)
        if 'Topics include:' in topics_text:
            topics = topics_text.replace('Topics include:', '').split(';')
            overview['topics'] = [t.strip() for t in topics if t.strip()]
    
    return overview

def _extract_learning_outcomes(soup: BeautifulSoup) -> List[Dict]:
    """Extract learning outcomes from soup"""
    outcomes = []
    seen_outcomes = set()
    
    if slo_table := soup.find('table', class_='SLOTable'):
        for row in slo_table.select('tr'):
            if (th := row.find('th')) and (td := row.find('td')):
                outcome_text = td.get_text(strip=True)
                if outcome_text not in seen_outcomes:
                    outcomes.append({
                        'no': th.get_text(strip=True).rstrip('.'),
                        'text': outcome_text
                    })
                    seen_outcomes.add(outcome_text)
    
    return outcomes

def _extract_assessment(soup: BeautifulSoup) -> List[Dict]:
    """Extract assessment tasks from soup"""
    assessment = []
    
    if assess_section := _find_section(soup, 'Assessment'):
        current_task = None
        
        for node in assess_section.find_all_next():
            if node.name == 'h3':
                break
            
            if node.name == 'h4':
                if current_task:
                    assessment.append(current_task)
                current_task = {'title': node.get_text(strip=True), 'details': {}}
            
            elif current_task and node.name == 'table' and 'assessmentTaskTable' in (node.get('class') or []):
                for row in node.select('tr'):
                    if (th := row.find('th')) and (td := row.find('td')):
                        key = th.get_text(strip=True).rstrip(':')
                        current_task['details'][key] = td.get_text("\n", strip=True)
        
        if current_task:
            assessment.append(current_task)
    
    return assessment

def _find_section(soup: BeautifulSoup, heading: str) -> Optional[BeautifulSoup]:
    """Find a section by its heading"""
    return soup.find(lambda t: t.name == 'h3' and heading in t.get_text())

def _extract_section_text(section: BeautifulSoup) -> str:
    """Extract text content from a section"""
    parts = []
    for sibling in section.find_next_siblings():
        if sibling.name == 'h3':
            break
        if sibling.name == 'p':
            parts.append(sibling.get_text(strip=True))
    return ' '.join(parts)

def _extract_section_list(section: BeautifulSoup) -> List[str]:
    """Extract list items from a section"""
    items = []
    for sibling in section.find_next_siblings():
        if sibling.name == 'h3':
            break
        if sibling.name in ('p', 'ul', 'ol'):
            text = sibling.get_text(strip=True)
            items.extend([item.strip() for item in text.split('\n') if item.strip()])
    return items

@app.route('/api/courses', methods=['POST'])
def api_courses():
    try:
        data = request.get_json()
        codes = data.get('subject_codes', [])
        logger.info(f"Received request for courses: {codes}")
        
        def generate():
            results = []
            total = len(codes)
            completed = 0
            
            for code in codes:
                try:
                    # Try cache first
                    course = course_cache.get(code) or fetch_course(code)
                    course_cache[code] = course
                    results.append(course)
                    
                    completed += 1
                    yield json.dumps({
                        "type": "progress",
                        "completed": completed,
                        "total": total,
                        "code": code
                    }) + "\n"
                    
                except Exception as e:
                    logger.error(f"Error processing course {code}: {e}")
                    yield json.dumps({
                        "type": "progress",
                        "completed": completed,
                        "total": total,
                        "code": code,
                        "error": str(e)
                    }) + "\n"
            
            yield json.dumps({
                "type": "complete",
                "results": results
            }) + "\n"
        
        return Response(generate(), mimetype='application/x-ndjson')
        
    except Exception as e:
        logger.error(f"API error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/warmup')
def warmup():
    """Health check endpoint"""
    return jsonify({"status": "ready"})

@app.after_request
def add_header(response):
    """Add cache control headers"""
    response.cache_control.max_age = 300  # 5 minutes
    return response

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)