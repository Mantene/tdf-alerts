"""
Script to inspect TDF.org pages.
NOTE: This script currently fails in this environment due to Imperva Incapsula WAF blocking.
It is kept for reference of inspection logic.
"""

import asyncio
import logging
from playwright.async_api import async_playwright
from playwright_stealth import Stealth

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("TDFInspector")

EMAIL = "mhood@princeton.edu"
PASSWORD = "mez8GHJ4jhd7hwk!bhx"
LOGIN_URL = "https://my.tdf.org/account/login"
OFFERINGS_URL = "https://nycgw47.tdf.org/TDFCustomOfferings/Current"

async def inspect():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
             user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
             viewport={"width": 1920, "height": 1080},
             locale="en-US",
             timezone_id="America/New_York"
        )
        page = await context.new_page()
        
        # Skipping stealth for this run
        # stealth = Stealth()
        # await stealth.apply_stealth_async(page)
        
        try:
            # 1. Inspect Login Page
            logger.info("Navigating to login page...")
            await page.goto(LOGIN_URL, wait_until='networkidle', timeout=60000)
            
            # Wait for any challenge to clear
            await page.wait_for_timeout(5000)
            
            logger.info("Inspecting login page structure...")
            
            # Check if we are still on the challenge page
            content = await page.content()
            if "Pardon Our Interruption" in content:
                logger.error("Still blocked by WAF. Waiting longer...")
                await page.wait_for_timeout(10000)
            
            # Dump the form HTML
            form_html = await page.evaluate("""() => {
                const forms = document.querySelectorAll('form');
                if (forms.length > 0) {
                    return forms[0].outerHTML;
                }
                return document.body.innerHTML;
            }""")
            logger.info(f"Login Page Form HTML fragment:\n{form_html[:2000]}") # Truncate to avoid huge logs
            
            # Find specific inputs
            email_inputs = await page.evaluate("""() => {
                return Array.from(document.querySelectorAll('input')).map(i => ({
                    id: i.id,
                    name: i.name,
                    type: i.type,
                    placeholder: i.placeholder,
                    class: i.className
                }));
            }""")
            logger.info(f"Inputs found on login page: {email_inputs}")
            
            buttons = await page.evaluate("""() => {
                return Array.from(document.querySelectorAll('button')).map(b => ({
                    id: b.id,
                    type: b.type,
                    text: b.innerText,
                    class: b.className
                }));
            }""")
            logger.info(f"Buttons found on login page: {buttons}")

            # 2. Perform Login
            logger.info("Attempting login...")
            # Try to guess selectors based on findings or use generic ones to proceed
            # Based on common patterns:
            try:
                if len(email_inputs) > 0:
                     # Use the first visible input if generic selector fails, but try generic first
                     await page.fill('input[type="email"], input[name="email"], input[id*="email"]', EMAIL)
                     await page.fill('input[type="password"], input[name="password"], input[id*="password"]', PASSWORD)
                     await page.click('button[type="submit"], input[type="submit"]')
                else:
                    logger.warning("No inputs found, cannot login.")
                    return
            except Exception as e:
                logger.error(f"Login interaction failed: {e}")
                return

            await page.wait_for_load_state('networkidle')
            logger.info(f"URL after login: {page.url}")
            
            # 3. Inspect Offerings Page
            logger.info("Navigating to offerings page...")
            await page.goto(OFFERINGS_URL, wait_until='networkidle')
            logger.info(f"Current URL: {page.url}")
            
            logger.info("Inspecting offerings page structure...")
            # Search input
            search_inputs = await page.evaluate("""() => {
                return Array.from(document.querySelectorAll('input[type="text"], input[type="search"]')).map(i => ({
                    id: i.id,
                    name: i.name,
                    placeholder: i.placeholder,
                    class: i.className
                }));
            }""")
            logger.info(f"Search inputs found: {search_inputs}")
            
            # Dump a sample listing
            listing_html = await page.evaluate("""() => {
                // Try to find a table or list of shows
                const tables = document.querySelectorAll('table');
                if (tables.length > 0) return tables[0].outerHTML;
                
                const showItems = document.querySelectorAll('.show-item, .listing-item, .offering');
                if (showItems.length > 0) return showItems[0].outerHTML;
                
                return "No obvious listing container found. Dumping first 1000 chars of body: " + document.body.innerHTML.substring(0, 1000);
            }""")
            logger.info(f"Sample listing HTML fragment:\n{listing_html[:2000]}")

            # Look for "View" buttons
            view_links = await page.evaluate("""() => {
                return Array.from(document.querySelectorAll('a, button')).filter(el => 
                    el.innerText.includes('View') || el.innerText.includes('More Info')
                ).map(el => ({
                    tag: el.tagName,
                    text: el.innerText,
                    href: el.href,
                    class: el.className,
                    id: el.id
                })).slice(0, 5);
            }""")
            logger.info(f"Possible 'View' buttons/links: {view_links}")
            
            # 4. Inspect Detail Page (if possible)
            if view_links and view_links[0].get('href'):
                detail_url = view_links[0]['href']
                if not detail_url.startswith('http'):
                    detail_url = "https://nycgw47.tdf.org" + detail_url
                    
                logger.info(f"Navigating to detail page: {detail_url}")
                await page.goto(detail_url, wait_until='networkidle')
                
                logger.info("Inspecting detail page structure...")
                # Dump date elements
                date_html = await page.evaluate("""() => {
                    // Look for date containers
                    const potentialDates = document.querySelectorAll('.date, .performance, .time, .schedule');
                    if (potentialDates.length > 0) return Array.from(potentialDates).map(e => e.outerHTML).join('\\n');
                    
                    return document.body.innerHTML.substring(0, 2000);
                }""")
                logger.info(f"Detail page HTML fragment (dates):\n{date_html[:2000]}")

                all_classes = await page.evaluate("""() => {
                    return Array.from(document.querySelectorAll('*')).map(e => e.className).filter(c => c).join(' ');
                }""")
                logger.info(f"All classes on detail page (sample): {all_classes[:500]}...")

        except Exception as e:
            logger.error(f"Error during inspection: {e}")
            # Dump current page content for debugging
            try:
                content = await page.content()
                logger.info(f"Page content at error:\n{content[:2000]}")
            except:
                pass
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(inspect())
