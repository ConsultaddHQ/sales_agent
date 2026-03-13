#!/usr/bin/env python3
"""
Static Demo Page Generator
Clones client's page and injects Avatar Widget
"""

import os
import re
import argparse
import requests
from pathlib import Path
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class StaticPageGenerator:
    def __init__(self, output_dir: str = "./demo_pages"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True, parents=True)
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
    
    def generate_demo_page(
        self,
        url: str,
        store_id: str,
        widget_script_url: str,
        search_api_url: str
    ) -> str:
        """Generate static demo page from URL"""
        logger.info(f"Fetching page: {url}")
        
        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
        except Exception as e:
            logger.error(f"Failed to fetch page: {e}")
            raise
        
        base_url = f"{urlparse(url).scheme}://{urlparse(url).netloc}"
        
        # Remove scripts that might interfere
        self._clean_scripts(soup)
        
        # Fix relative URLs
        self._fix_urls(soup, base_url)
        
        # Inject widget
        self._inject_widget(soup, store_id, widget_script_url, search_api_url)
        
        # Save to file
        filename = self._generate_filename(url)
        output_path = self.output_dir / filename
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(str(soup.prettify()))
        
        logger.info(f"Demo page saved to: {output_path}")
        return str(output_path)
    
    def _clean_scripts(self, soup: BeautifulSoup):
        """Remove potentially problematic scripts"""
        # Remove analytics, tracking, and heavy JS frameworks
        remove_patterns = [
            'google-analytics',
            'googletagmanager',
            'facebook',
            'gtag',
            'analytics',
            'tracking',
            'tag-manager',
            'hotjar',
            'clarity',
            'mixpanel',
            # Be careful with these - might break layout
            # 'jquery',
            # 'react',
            # 'vue',
        ]
        
        for script in soup.find_all('script'):
            src = script.get('src', '')
            content = script.string or ''
            
            for pattern in remove_patterns:
                if pattern in src.lower() or pattern in content.lower():
                    logger.debug(f"Removing script: {src[:50]}")
                    script.decompose()
                    break
    
    def _fix_urls(self, soup: BeautifulSoup, base_url: str):
        """Convert relative URLs to absolute"""
        # Fix images
        for img in soup.find_all('img', src=True):
            src = img['src']
            if not src.startswith(('http://', 'https://', 'data:')):
                img['src'] = urljoin(base_url, src)
        
        # Fix links
        for link in soup.find_all('link', href=True):
            href = link['href']
            if not href.startswith(('http://', 'https://', 'data:')):
                link['href'] = urljoin(base_url, href)
        
        # Fix CSS background images
        for style in soup.find_all('style'):
            if style.string:
                style.string = re.sub(
                    r'url\([\'"]?(?!http|data:)([^\'"]+)[\'"]?\)',
                    lambda m: f"url({urljoin(base_url, m.group(1))})",
                    style.string
                )
    
    def _inject_widget(self, soup: BeautifulSoup, store_id: str, widget_script_url: str, search_api_url: str):
        """Inject Avatar Widget into page"""
        # Create widget container
        widget_div = soup.new_tag('div', id='avatar-widget-root')
        widget_div['data-store-id'] = store_id
        widget_div['data-search-api'] = search_api_url
        
        # Insert at end of body
        body = soup.find('body')
        if body:
            body.append(widget_div)
        else:
            logger.warning("No <body> tag found, appending to html")
            soup.append(widget_div)
        
        # Add widget script
        script = soup.new_tag('script')
        script['src'] = widget_script_url
        script['type'] = 'module'
        script['defer'] = True
        
        # Insert script before </body>
        if body:
            body.append(script)
        else:
            soup.append(script)
        
        # Add widget configuration script
        config_script = soup.new_tag('script')
        config_script.string = f"""
        window.AVATAR_WIDGET_CONFIG = {{
            storeId: '{store_id}',
            searchApiUrl: '{search_api_url}',
            agentId: 'default-agent'
        }};
        """
        
        head = soup.find('head')
        if head:
            head.append(config_script)
        else:
            soup.insert(0, config_script)
        
        logger.info("Widget injected successfully")
    
    def _generate_filename(self, url: str) -> str:
        """Generate filename from URL"""
        parsed = urlparse(url)
        path = parsed.path.strip('/').replace('/', '_')
        if not path:
            path = 'index'
        return f"demo_{path}.html"


def main():
    parser = argparse.ArgumentParser(description='Generate static demo page with widget')
    parser.add_argument('url', help='Client page URL to clone')
    parser.add_argument('store_id', help='Store ID from scraper')
    parser.add_argument('--widget-script', default='http://localhost:5173/src/main.jsx',
                       help='Widget script URL')
    parser.add_argument('--search-api', default='http://localhost:8006',
                       help='Search API URL')
    parser.add_argument('--output-dir', default='./demo_pages',
                       help='Output directory')
    args = parser.parse_args()
    
    generator = StaticPageGenerator(args.output_dir)
    output_path = generator.generate_demo_page(
        args.url,
        args.store_id,
        args.widget_script,
        args.search_api
    )
    
    logger.info(f"\n{'='*60}")
    logger.info(f"✅ DEMO PAGE GENERATED!")
    logger.info(f"File: {output_path}")
    logger.info(f"")
    logger.info(f"To serve:")
    logger.info(f"  cd {args.output_dir}")
    logger.info(f"  python3 -m http.server 8080")
    logger.info(f"  Visit: http://localhost:8080/{Path(output_path).name}")
    logger.info(f"{'='*60}\n")


if __name__ == '__main__':
    main()
