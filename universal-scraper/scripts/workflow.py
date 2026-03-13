#!/usr/bin/env python3
"""
Complete Demo Setup Workflow
Orchestrates scraping, image serving, and demo page generation
"""

import os
import sys
import subprocess
import argparse
from pathlib import Path
import logging

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)


class DemoOrchestrator:
    def __init__(self):
        self.base_dir = Path(__file__).parent
        self.store_id = None
    
    def run_workflow(
        self,
        product_url: str,
        demo_url: str,
        max_products: int = 200,
        image_server_port: int = 8000,
        image_server_url: str = None
    ):
         # Validate max_products limit
        if max_products > 250:
            logger.warning(f"max_products ({max_products}) exceeds recommended limit of 250")
            logger.warning("Supabase free tier may have issues. Consider using filtered URL instead.")
            
            response = input("Continue anyway? (y/N): ")
            if response.lower() != 'y':
                logger.info("Aborted by user")
                return False
     
        """Run complete workflow"""
        
        logger.info("="*70)
        logger.info("  AI SHOPPING ASSISTANT - DEMO SETUP WORKFLOW")
        logger.info("="*70)
        logger.info("")
        
        # Determine image server URL
        if not image_server_url:
            image_server_url = f"http://localhost:{image_server_port}"
        
        # Step 1: Scrape products
        logger.info("STEP 1: Scraping products...")
        logger.info(f"  URL: {product_url}")
        logger.info(f"  Max products: {max_products}")
        logger.info("")
        
        try:
            result = subprocess.run(
                [
                    sys.executable,
                    'universal_scraper.py',
                    product_url,
                    '--max-products', str(max_products),
                    '--image-server', image_server_url
                ],
                check=True,
                capture_output=True,
                text=True
            )
            logger.info(result.stdout)
            
            # Read store_id
            with open('store_id.txt', 'r') as f:
                self.store_id = f.read().strip()
            
            logger.info(f"✅ Scraping complete! Store ID: {self.store_id}")
            logger.info("")
            
        except subprocess.CalledProcessError as e:
            logger.error(f"❌ Scraping failed: {e.stderr}")
            return False
        
        # Step 2: Generate demo page
        logger.info("STEP 2: Generating demo page...")
        logger.info(f"  Demo URL: {demo_url}")
        logger.info("")
        
        try:
            # Determine widget script URL based on environment
            widget_script = os.getenv('WIDGET_SCRIPT_URL', 'http://localhost:5173/src/main.jsx')
            search_api = os.getenv('SEARCH_API_URL', 'http://localhost:8006')
            
            result = subprocess.run(
                [
                    sys.executable,
                    'static_page_generator.py',
                    demo_url,
                    self.store_id,
                    '--widget-script', widget_script,
                    '--search-api', search_api
                ],
                check=True,
                capture_output=True,
                text=True
            )
            logger.info(result.stdout)
            logger.info("✅ Demo page generated!")
            logger.info("")
            
        except subprocess.CalledProcessError as e:
            logger.error(f"❌ Demo page generation failed: {e.stderr}")
            return False
        
        # Step 3: Instructions
        self._print_instructions(image_server_port)
        
        return True
    
    def _print_instructions(self, image_server_port: int):
        """Print next steps"""
        logger.info("="*70)
        logger.info("  ✅ SETUP COMPLETE!")
        logger.info("="*70)
        logger.info("")
        logger.info("NEXT STEPS:")
        logger.info("")
        logger.info("1. Start the image server (in a new terminal):")
        logger.info(f"   python image_server.py")
        logger.info(f"   # Runs on http://localhost:{image_server_port}")
        logger.info("")
        logger.info("2. Ensure search service is running (in a new terminal):")
        logger.info("   cd search-service")
        logger.info("   source .venv/bin/activate")
        logger.info("   uvicorn main:app --port 8006")
        logger.info("")
        logger.info("3. Ensure frontend widget is running (in a new terminal):")
        logger.info("   cd www.teampop/frontend")
        logger.info("   npm run dev")
        logger.info("")
        logger.info("4. Serve the demo page:")
        logger.info("   cd demo_pages")
        logger.info("   python3 -m http.server 8080")
        logger.info("   Visit: http://localhost:8080/demo_*.html")
        logger.info("")
        logger.info("DEPLOYMENT OPTIONS:")
        logger.info("")
        logger.info("Option A: Simple Python Server (Local testing)")
        logger.info("  - Already shown above")
        logger.info("")
        logger.info("Option B: GitHub Pages (Public hosting)")
        logger.info("  - See: deploy_github.sh")
        logger.info("")
        logger.info("Option C: Custom Domain")
        logger.info("  - Deploy image server + demo page to your server")
        logger.info("  - Update CORS settings in image_server.py")
        logger.info("  - Point DNS to your server")
        logger.info("")
        logger.info(f"Store ID: {self.store_id}")
        logger.info("="*70)


def main():
    parser = argparse.ArgumentParser(
        description='Complete demo setup workflow',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Small shop with 100-200 products
  python workflow.py https://example.com https://example.com
  
  # Large shop - use filtered page
  python workflow.py https://amazon.com/s?k=laptops https://amazon.com/s?k=laptops --max-products 150
  
  # Media Markt example
  python workflow.py https://mediamarkt.de/products?category=tv https://mediamarkt.de --max-products 200
        """
    )
    
    parser.add_argument('product_url', help='URL to scrape products from (homepage or filtered page)')
    parser.add_argument('demo_url', help='URL to create demo page from (can be same or different)')
    parser.add_argument('--max-products', type=int, default=200,
                       help='Maximum products to scrape (default: 200)')
    parser.add_argument('--image-server-port', type=int, default=8000,
                       help='Port for image server (default: 8000)')
    parser.add_argument('--image-server-url', 
                       help='Public URL for image server (default: http://localhost:PORT)')
    
    args = parser.parse_args()
    
    # Validate environment
    if not os.getenv('SUPABASE_URL') or not os.getenv('SUPABASE_KEY'):
        logger.error("❌ Missing environment variables!")
        logger.error("Please set SUPABASE_URL and SUPABASE_KEY")
        logger.error("")
        logger.error("Create a .env file:")
        logger.error("  SUPABASE_URL=https://xyz.supabase.co")
        logger.error("  SUPABASE_KEY=your-service-role-key")
        sys.exit(1)
    
    orchestrator = DemoOrchestrator()
    success = orchestrator.run_workflow(
        args.product_url,
        args.demo_url,
        args.max_products,
        args.image_server_port,
        args.image_server_url
    )
    
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
