#!/usr/bin/env python3
"""
Static Demo Page Generator with Agent Support
Clones client's page and injects Avatar Widget with ElevenLabs agent
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
        agent_id: str,
        widget_script_url: str,
        search_api_url: str
    ) -> str:
        """Generate static demo page from URL"""
        logger.info(f"📄 Fetching page: {url}")
        
        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
        except Exception as e:
            logger.error(f"❌ Failed to fetch page: {e}")
            raise
        
        base_url = f"{urlparse(url).scheme}://{urlparse(url).netloc}"
        
        # Clean and prepare page
        logger.info("🧹 Cleaning scripts...")
        self._clean_scripts(soup)
        
        logger.info("🔗 Fixing URLs...")
        self._fix_urls(soup, base_url)
        
        logger.info("🤖 Injecting widget...")
        self._inject_widget(soup, store_id, agent_id, widget_script_url, search_api_url)
        
        # Save to file
        filename = f"test_{store_id[:8]}.html"
        output_path = self.output_dir / filename
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(str(soup.prettify()))
        
        logger.info(f"✅ Demo page saved to: {output_path}")
        return str(output_path)
    
    def _clean_scripts(self, soup: BeautifulSoup):
        """Remove potentially problematic scripts"""
        # Scripts to remove (can break widget)
        remove_patterns = [
            'google-analytics',
            'googletagmanager',
            'gtag',
            'analytics',
            'facebook',
            'fb-pixel',
            'tracking',
            'tag-manager',
            'hotjar',
            'clarity',
            'mixpanel',
            'doubleclick',
            'intercom',
            'drift',
            'zendesk',
            'tawk',
            'livechat',
        ]
        
        # Scripts to keep (needed for site functionality)
        keep_patterns = [
            'jquery',
            'bootstrap',
            'shopify',
            'cdn.shopify.com',
            'theme',
            'product',
            'cart',
            'checkout',
        ]
        
        scripts_removed = 0
        for script in soup.find_all('script'):
            src = script.get('src', '')
            content = script.string or ''
            combined = (src + ' ' + content).lower()
            
            # Check if should remove
            should_remove = any(pattern in combined for pattern in remove_patterns)
            should_keep = any(pattern in combined for pattern in keep_patterns)
            
            if should_remove and not should_keep:
                script.decompose()
                scripts_removed += 1
        
        logger.info(f"  Removed {scripts_removed} analytics/tracking scripts")
    
    def _fix_urls(self, soup: BeautifulSoup, base_url: str):
        """Convert relative URLs to absolute"""
        # Fix image sources
        for img in soup.find_all('img'):
            if img.get('src'):
                img['src'] = urljoin(base_url, img['src'])
            if img.get('srcset'):
                # Fix srcset URLs
                srcset_parts = []
                for part in img['srcset'].split(','):
                    url_part = part.strip().split()[0]
                    descriptor = ' '.join(part.strip().split()[1:])
                    absolute_url = urljoin(base_url, url_part)
                    srcset_parts.append(f"{absolute_url} {descriptor}".strip())
                img['srcset'] = ', '.join(srcset_parts)
        
        # Fix CSS links
        for link in soup.find_all('link', rel='stylesheet'):
            if link.get('href'):
                link['href'] = urljoin(base_url, link['href'])
        
        # Fix links
        for a in soup.find_all('a'):
            if a.get('href') and not a['href'].startswith(('http', 'https', 'mailto', 'tel', '#')):
                a['href'] = urljoin(base_url, a['href'])
        
        # Fix inline CSS url() references
        for style in soup.find_all('style'):
            if style.string:
                style.string = re.sub(
                    r'url\([\'"]?(?!http|data:)([^\'"]+)[\'"]?\)',
                    lambda m: f"url({urljoin(base_url, m.group(1))})",
                    style.string
                )
    
    def _inject_widget(
        self,
        soup: BeautifulSoup,
        store_id: str,
        agent_id: str,
        widget_script_url: str,
        search_api_url: str
    ):
        """Inject Avatar Widget with agent configuration"""
        
        # 1. Create widget root div
        widget_root = soup.new_tag('div', id='avatar-widget-root')
        
        # 2. Add widget configuration script BEFORE widget loads
        config_script = soup.new_tag('script')
        config_script.string = f"""
        // TeamPop Widget Configuration
        window.AVATAR_WIDGET_CONFIG = {{
            agentId: "{agent_id}",
            storeId: "{store_id}",
            searchApiUrl: "{search_api_url}"
        }};
        console.log('TeamPop Widget Config Loaded:', window.AVATAR_WIDGET_CONFIG);
        """
        
        # 3. Add widget script
        widget_script = soup.new_tag('script')
        widget_script['src'] = widget_script_url
        widget_script['type'] = 'module'
        widget_script['defer'] = True
        
        # 4. Insert into page
        body = soup.find('body')
        head = soup.find('head')
        
        if not body:
            logger.warning("⚠️ No <body> tag found, creating one")
            body = soup.new_tag('body')
            soup.append(body)
        
        if not head:
            logger.warning("⚠️ No <head> tag found, creating one")
            head = soup.new_tag('head')
            soup.insert(0, head)
        
        # Add config to head (loads first)
        head.append(config_script)
        
        # Add widget root to body
        body.append(widget_root)
        
        # Add widget script to end of body
        body.append(widget_script)
        
        logger.info(f"  Widget injected with agent: {agent_id}")
    
    def _generate_filename(self, store_id: str) -> str:
        """Generate filename from store_id"""
        return f"test_{store_id[:8]}.html"


def main():
    parser = argparse.ArgumentParser(
        description='Generate static demo page with AI widget',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Example:
  python static_page_generator.py \\
    https://sensesindia.in \\
    abc123-uuid \\
    --agent-id elevenlabs_agent_xyz \\
    --widget-script http://localhost:5173/src/main.jsx \\
    --search-api http://localhost:8006
        """
    )
    
    parser.add_argument('url', help='Client page URL to clone')
    parser.add_argument('store_id', help='Store ID (UUID)')
    parser.add_argument('--agent-id', required=True, help='ElevenLabs agent ID')
    parser.add_argument('--widget-script', default='http://localhost:5173/src/main.jsx',
                       help='Widget script URL (default: localhost dev server)')
    parser.add_argument('--search-api', default='http://localhost:8006',
                       help='Search API URL (default: localhost)')
    parser.add_argument('--output-dir', default='./demo_pages',
                       help='Output directory (default: ./demo_pages)')
    
    args = parser.parse_args()
    
    logger.info("\n" + "="*60)
    logger.info("TeamPop Static Demo Page Generator")
    logger.info("="*60 + "\n")
    
    generator = StaticPageGenerator(args.output_dir)
    
    try:
        output_path = generator.generate_demo_page(
            args.url,
            args.store_id,
            args.agent_id,
            args.widget_script,
            args.search_api
        )
        
        logger.info("\n" + "="*60)
        logger.info("✅ SUCCESS!")
        logger.info("="*60)
        logger.info(f"Test page: {output_path}")
        logger.info(f"\nTo test:")
        logger.info(f"  cd demo_pages")
        logger.info(f"  python3 -m http.server 8080")
        logger.info(f"  Open: http://localhost:8080/{Path(output_path).name}")
        logger.info("="*60 + "\n")
        
        return 0
        
    except Exception as e:
        logger.error(f"\n❌ Failed: {e}")
        return 1


if __name__ == '__main__':
    import sys
    sys.exit(main())
