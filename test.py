import requests
from bs4 import BeautifulSoup
import json
import time
import logging
from typing import List, Dict, Optional
from pathlib import Path
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor, as_completed

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@dataclass
class CourseConfig:
    """Configuration for course scraping"""
    base_url: str = "https://handbookpre2025.uts.edu.au/2024/subjects/details"
    output_file: Path = Path("courses.json")
    request_delay: float = 0.1
    max_workers: int = 4

class CourseScraper:
    def __init__(self, config: CourseConfig):
        self.config = config
        self.session = requests.Session()
    
    def fetch_courses(self, codes: List[str]) -> List[Dict]:
        """Fetch multiple courses in parallel with rate limiting"""
        courses = []
        with ThreadPoolExecutor(max_workers=self.config.max_workers) as executor:
            future_to_code = {
                executor.submit(self._fetch_single_course, code): code 
                for code in codes
            }
            
            for future in as_completed(future_to_code):
                code = future_to_code[future]
                try:
                    course = future.result()
                    if course:
                        courses.append(course)
                        logger.info(f"Successfully fetched course {code}")
                    time.sleep(self.config.request_delay)
                except Exception as e:
                    logger.error(f"Error fetching course {code}: {e}")
        
        return courses
    
    def _fetch_single_course(self, code: str) -> Optional[Dict]:
        """Fetch and parse a single course"""
        try:
            url = f"{self.config.base_url}/{code}.html"
            response = self.session.get(url)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            return self._parse_course(soup, code)
        except Exception as e:
            logger.error(f"Error fetching {code}: {e}")
            return None

    def _parse_course(self, soup: BeautifulSoup, code: str) -> Dict:
        """Parse course details from soup"""
        return {
            'code': code,
            'title': self._extract_title(soup),
            'credit_points': self._extract_credit_points(soup),
            'requisites': self._extract_requisites(soup),
            'overview': self._extract_overview(soup),
            'learning_outcomes': self._extract_learning_outcomes(soup),
            'assessment': self._extract_assessment(soup)
        }

    def save_courses(self, courses: List[Dict]) -> None:
        """Save courses to JSON file"""
        self.config.output_file.write_text(
            json.dumps(courses, indent=2, ensure_ascii=False),
            encoding='utf-8'
        )
        logger.info(f"Saved {len(courses)} courses to {self.config.output_file}")

    def _extract_title(self, soup: BeautifulSoup) -> str:
        """Extract course title"""
        if title_elem := soup.find('h1'):
            return title_elem.get_text(strip=True)
        return ''

    def _extract_credit_points(self, soup: BeautifulSoup) -> str:
        """Extract credit points"""
        for em in soup.find_all('em'):
            if txt := em.get_text(strip=True):
                if txt.startswith('Credit points'):
                    return em.next_sibling.strip() if em.next_sibling else ''
        return ''

    def _extract_requisites(self, soup: BeautifulSoup) -> str:
        """Extract prerequisites"""
        for em in soup.find_all('em'):
            if txt := em.get_text(strip=True):
                if txt.startswith('Requisite'):
                    return em.get_text(separator=' ', strip=True).replace('Requisite(s):', '').strip()
        return ''

    def _extract_overview(self, soup: BeautifulSoup) -> Dict:
        """Extract course overview sections"""
        overview = {
            'description': '',
            'teaching_strategies': [],
            'topics': []
        }
        
        # Extract description
        if desc_section := self._find_section(soup, 'Description'):
            overview['description'] = self._extract_section_text(desc_section)
        
        # Extract teaching strategies
        if strategies_section := self._find_section(soup, 'Teaching and learning strategies'):
            overview['teaching_strategies'] = self._extract_section_list(strategies_section)
        
        # Extract topics
        if topics_section := self._find_section(soup, 'Content (topics)'):
            topics_text = self._extract_section_text(topics_section)
            if 'Topics include:' in topics_text:
                topics = topics_text.replace('Topics include:', '').split(';')
                overview['topics'] = [t.strip() for t in topics if t.strip()]
        
        return overview

    def _extract_learning_outcomes(self, soup: BeautifulSoup) -> List[Dict]:
        """Extract learning outcomes"""
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

    def _extract_assessment(self, soup: BeautifulSoup) -> List[Dict]:
        """Extract assessment tasks"""
        assessment = []
        
        if assess_section := self._find_section(soup, 'Assessment'):
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

    def _find_section(self, soup: BeautifulSoup, heading: str) -> Optional[BeautifulSoup]:
        """Find a section by its heading"""
        return soup.find(lambda t: t.name == 'h3' and heading in t.get_text())

    def _extract_section_text(self, section: BeautifulSoup) -> str:
        """Extract text content from a section"""
        parts = []
        for sibling in section.find_next_siblings():
            if sibling.name == 'h3':
                break
            if sibling.name == 'p':
                parts.append(sibling.get_text(strip=True))
        return ' '.join(parts)

    def _extract_section_list(self, section: BeautifulSoup) -> List[str]:
        """Extract list items from a section"""
        items = []
        for sibling in section.find_next_siblings():
            if sibling.name == 'h3':
                break
            if sibling.name in ('p', 'ul', 'ol'):
                text = sibling.get_text(strip=True)
                items.extend([item.strip() for item in text.split('\n') if item.strip()])
        return items

def main():
    # Example subject codes
    SUBJECT_CODES = ["33230"]
    
    # Create scraper instance
    config = CourseConfig()
    scraper = CourseScraper(config)
    
    try:
        # Fetch and save courses
        courses = scraper.fetch_courses(SUBJECT_CODES)
        scraper.save_courses(courses)
    except Exception as e:
        logger.error(f"Error in main: {e}")
        raise

if __name__ == '__main__':
    main()
