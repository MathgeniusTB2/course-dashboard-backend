import requests
from bs4 import BeautifulSoup
import json
import time

# --- Configuration ---
BASE_URL = "https://handbookpre2025.uts.edu.au/2024/subjects/details"
OUTPUT_FILE = "courses.json"
SUBJECT_CODES = [
    "33230",
]
REQUEST_DELAY = 0.1


def fetch_course(code):
    """
    Fetches and parses the course page for the given subject code.
    Returns a dictionary of extracted fields.
    """
    url = f"{BASE_URL}/{code}.html"
    resp = requests.get(url)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, 'html.parser')

    # --- Helpers ---
    def get_section_header(tag, text):
        return tag.find(lambda t: t.name == 'h3' and text in t.get_text())

    # --- Metadata ---
    title = soup.find('h1').get_text(strip=True) if soup.find('h1') else ''

    # Credit points & result type & requisites via <em> tags
    credit_points = ''
    result_type = ''
    requisites = ''
    for em in soup.find_all('em'):
        txt = em.get_text(strip=True)
        if txt.startswith('Credit points'):
            # next_sibling may be whitespace/text then value
            credit_points = em.next_sibling.strip() if em.next_sibling else ''
        elif txt.startswith('Result type'):
            result_type = em.next_sibling.strip() if em.next_sibling else ''
        elif txt.startswith('Requisite'):
            # entire em contains links and text
            requisites = em.get_text(separator=' ', strip=True).replace('Requisite(s):', '').strip()

    # Description/Overview
    overview = ''
    desc_hdr = get_section_header(soup, 'Description')
    if desc_hdr:
        p = desc_hdr.find_next('p')
        overview = p.get_text(strip=True) if p else ''

    # Subject Learning Objectives (SLOs)
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

    # Course Intended Learning Outcomes (CILOs)
    cilos = []
    cilo_hdr = get_section_header(soup, 'Course intended learning outcomes')
    if cilo_hdr:
        cilo_ul = cilo_hdr.find_next('ul', class_='CILOList')
        if cilo_ul:
            cilos = [li.get_text(strip=True) for li in cilo_ul.find_all('li')]

    # Content, teaching, minimum, recommended
    def extract_section(soup, heading):
        hdr = get_section_header(soup, heading)
        blocks = []
        if hdr:
            for sib in hdr.find_next_siblings():
                if sib.name == 'h3':
                    break
                if sib.name in ('p', 'ul', 'ol'):
                    blocks.append(sib.get_text("\n", strip=True))
        return '\n\n'.join(blocks)

    teaching_strategies = extract_section(soup, 'Teaching and learning strategies')
    content_topics = extract_section(soup, 'Content (topics)')
    minimum_requirements = extract_section(soup, 'Minimum requirements')
    recommended_texts = extract_section(soup, 'Recommended texts')

    # Assessment tasks
    assessment = []
    assess_hdr = get_section_header(soup, 'Assessment')
    if assess_hdr:
        for node in assess_hdr.find_all_next():
            if node.name == 'h3':
                break
            if node.name == 'h4':
                task = {'title': node.get_text(strip=True), 'details': {}}
                tbl = node.find_next('table', class_='assessmentTaskTable')
                if tbl:
                    for row in tbl.select('tr'):
                        th = row.find('th')
                        td = row.find('td')
                        if th and td:
                            key = th.get_text(strip=True).rstrip(':')
                            task['details'][key] = td.get_text("\n", strip=True)
                assessment.append(task)

    return {
        'code': code,
        'title': title,
        'credit_points': credit_points,
        'result_type': result_type,
        'requisites': requisites,
        'overview': overview,
        'learning_outcomes': learning_outcomes,
        'CILOs': cilos,
        'teaching_strategies': teaching_strategies,
        'content_topics': content_topics,
        'assessment': assessment,
        'minimum_requirements': minimum_requirements,
        'recommended_texts': recommended_texts
    }


def main():
    all_courses = []
    for code in SUBJECT_CODES:
        try:
            print(f"Fetching {code}...")
            all_courses.append(fetch_course(code))
        except Exception as e:
            print(f"Error fetching {code}: {e}")
        time.sleep(REQUEST_DELAY)

    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(all_courses, f, indent=2, ensure_ascii=False)
    print(f"Saved {len(all_courses)} courses to {OUTPUT_FILE}")


if __name__ == '__main__':
    main()
