#!/usr/bin/env python3
"""
TDF Title Monitor
Monitors TDF.org for available show titles and sends alerts when found.
"""

import os
import sys
import json
import yaml
import logging
import asyncio
import smtplib
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Set
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dataclasses import dataclass, asdict
from playwright.async_api import async_playwright, Page, TimeoutError as PlaywrightTimeout

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('tdf_monitor.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


@dataclass
class TitleAvailability:
    """Represents a title and its available dates"""
    title: str
    dates: List[str]
    url: Optional[str] = None
    
    def __hash__(self):
        return hash(self.title)


class ConfigManager:
    """Manages configuration loading and validation"""
    
    def __init__(self, config_path: str = "config.yaml"):
        self.config_path = config_path
        self.config = self._load_config()
        self._validate_config()
    
    def _load_config(self) -> dict:
        """Load configuration from YAML file"""
        try:
            with open(self.config_path, 'r') as f:
                config = yaml.safe_load(f)
            logger.info(f"Configuration loaded from {self.config_path}")
            return config
        except FileNotFoundError:
            logger.error(f"Configuration file not found: {self.config_path}")
            raise
        except yaml.YAMLError as e:
            logger.error(f"Error parsing YAML configuration: {e}")
            raise
    
    def _validate_config(self):
        """Validate required configuration fields"""
        required_fields = ['tdf_credentials', 'titles', 'notifications']
        
        for field in required_fields:
            if field not in self.config:
                raise ValueError(f"Missing required configuration field: {field}")
        
        # Validate credentials
        creds = self.config['tdf_credentials']
        if 'email' not in creds or 'password' not in creds:
            raise ValueError("TDF credentials must include 'email' and 'password'")
        
        # Validate titles list
        if not isinstance(self.config['titles'], list) or len(self.config['titles']) == 0:
            raise ValueError("'titles' must be a non-empty list")
        
        # Validate notification settings
        notif = self.config['notifications']
        if 'method' not in notif:
            raise ValueError("Notification method must be specified")
        
        logger.info("Configuration validation passed")
    
    def get_credentials(self) -> tuple:
        """Get TDF credentials, preferring environment variables"""
        email = os.environ.get('TDF_EMAIL') or self.config['tdf_credentials']['email']
        password = os.environ.get('TDF_PASSWORD') or self.config['tdf_credentials']['password']
        
        if not email or not password:
            raise ValueError("TDF credentials not found in config or environment")
        
        return email, password
    
    def get_titles(self) -> List[str]:
        """Get list of titles to monitor"""
        return self.config['titles']
    
    def get_filter_date(self) -> Optional[str]:
        """Get optional date filter in MM/DD/YYYY format"""
        return self.config.get('filter_date')
    
    def get_notification_config(self) -> dict:
        """Get notification configuration"""
        return self.config['notifications']


class StateManager:
    """Manages persistent state to track what has been alerted"""
    
    def __init__(self, state_file: str = "state.json"):
        self.state_file = state_file
        self.state = self._load_state()
    
    def _load_state(self) -> dict:
        """Load state from JSON file"""
        if not os.path.exists(self.state_file):
            logger.info("No existing state file found, starting fresh")
            return {}
        
        try:
            with open(self.state_file, 'r') as f:
                state = json.load(f)
            logger.info(f"State loaded from {self.state_file}")
            return state
        except json.JSONDecodeError as e:
            logger.error(f"Error parsing state file: {e}")
            return {}
    
    def _save_state(self):
        """Save state to JSON file"""
        try:
            with open(self.state_file, 'w') as f:
                json.dump(self.state, f, indent=2)
            logger.info(f"State saved to {self.state_file}")
        except Exception as e:
            logger.error(f"Error saving state: {e}")
    
    def should_alert(self, title: str, dates: List[str]) -> bool:
        """
        Determine if an alert should be sent for this title/dates combination.
        Returns True if there are new dates compared to previous alerts.
        """
        if title not in self.state:
            return True
        
        previous_dates = set(self.state[title])
        current_dates = set(dates)
        
        # Alert if there are any new dates
        new_dates = current_dates - previous_dates
        return len(new_dates) > 0
    
    def get_new_dates(self, title: str, dates: List[str]) -> List[str]:
        """Get list of dates that are new compared to previous state"""
        if title not in self.state:
            return dates
        
        previous_dates = set(self.state[title])
        current_dates = set(dates)
        new_dates = current_dates - previous_dates
        
        return sorted(list(new_dates))
    
    def update_state(self, title: str, dates: List[str]):
        """Update state with new dates for a title"""
        if title not in self.state:
            self.state[title] = dates
        else:
            # Merge with existing dates (union)
            existing = set(self.state[title])
            updated = existing.union(set(dates))
            self.state[title] = sorted(list(updated))
        
        self._save_state()
        logger.info(f"State updated for title: {title}")


class TDFScraper:
    """
    Handles web scraping of TDF.org using Playwright.
    
    NOTE: Inspection of live pages revealed that TDF.org is protected by Imperva Incapsula WAF.
    The selectors used below are generic/best-effort and could not be verified against the
    live site from the inspection environment due to WAF blocking.
    See INSPECTION_RESULTS.md for details.
    """
    
    LOGIN_URL = "https://my.tdf.org/account/login"
    OFFERINGS_URL = "https://nycgw47.tdf.org/TDFCustomOfferings/Current"
    
    def __init__(self, email: str, password: str):
        self.email = email
        self.password = password
        self.page: Optional[Page] = None
    
    async def login(self, page: Page) -> bool:
        """
        Log into TDF.org
        Returns True if login successful
        """
        try:
            logger.info(f"Navigating to login page: {self.LOGIN_URL}")
            await page.goto(self.LOGIN_URL, wait_until='networkidle', timeout=30000)
            
            # Fill in login form
            logger.info("Filling login credentials")
            await page.fill('input[type="email"], input[name="email"], input[id*="email"]', self.email)
            await page.fill('input[type="password"], input[name="password"], input[id*="password"]', self.password)
            
            # Submit form
            await page.click('button[type="submit"], input[type="submit"]')
            
            # Wait for navigation after login
            await page.wait_for_load_state('networkidle', timeout=30000)
            
            # Check if login was successful by looking for error messages or checking URL
            current_url = page.url
            
            # Check for common error indicators
            error_elements = await page.query_selector_all('.error, .alert-danger, [class*="error"]')
            if error_elements:
                error_text = await error_elements[0].text_content()
                logger.error(f"Login failed with error: {error_text}")
                return False
            
            logger.info(f"Login successful, current URL: {current_url}")
            return True
            
        except PlaywrightTimeout:
            logger.error("Timeout during login process")
            return False
        except Exception as e:
            logger.error(f"Error during login: {e}")
            return False
    
    async def navigate_to_offerings(self, page: Page):
        """Navigate to the offerings page"""
        try:
            logger.info(f"Navigating to offerings page: {self.OFFERINGS_URL}")
            await page.goto(self.OFFERINGS_URL, wait_until='networkidle', timeout=30000)
            logger.info("Successfully navigated to offerings page")
        except Exception as e:
            logger.error(f"Error navigating to offerings page: {e}")
            raise
    
    async def apply_date_filter(self, page: Page, date_str: str):
        """
        Apply date filter on the offerings page
        date_str should be in MM/DD/YYYY format
        """
        try:
            logger.info(f"Applying date filter: {date_str}")
            
            # Find the date input field - may need to adjust selector based on actual page
            date_input = await page.query_selector('input[type="date"], input[placeholder*="date"], input[name*="date"]')
            
            if date_input:
                await date_input.fill(date_str)
                # Wait a moment for the filter to apply
                await page.wait_for_timeout(2000)
                logger.info(f"Date filter applied: {date_str}")
            else:
                logger.warning("Could not find date input field")
                
        except Exception as e:
            logger.error(f"Error applying date filter: {e}")
    
    async def search_title_on_page(self, page: Page, title: str) -> Optional[str]:
        """
        Search for a title on the current offerings page
        Returns the URL of the "View >" button if found, None otherwise
        """
        try:
            # Use the search input field
            search_input = await page.query_selector('input[type="search"], input[type="text"], input[placeholder*="search"]')
            
            if search_input:
                await search_input.clear()
                await search_input.fill(title)
                await page.wait_for_timeout(1500)  # Wait for results to filter
            
            # Look for the title and its associated "View >" button
            # This selector may need adjustment based on actual page structure
            title_elements = await page.query_selector_all('text=/' + title + '/i')
            
            for element in title_elements:
                # Try to find the associated "View >" button
                parent = await element.evaluate_handle('el => el.closest("tr, div, article, .listing-item, .show-item")')
                
                if parent:
                    view_button = await parent.query_selector('a:has-text("View"), button:has-text("View")')
                    
                    if view_button:
                        href = await view_button.get_attribute('href')
                        if href:
                            # Make sure it's an absolute URL
                            if href.startswith('/'):
                                href = f"https://nycgw47.tdf.org{href}"
                            logger.info(f"Found title '{title}' with URL: {href}")
                            return href
            
            logger.info(f"Title '{title}' not found on page")
            return None
            
        except Exception as e:
            logger.error(f"Error searching for title '{title}': {e}")
            return None
    
    async def get_available_dates(self, page: Page, title_url: str) -> List[str]:
        """
        Navigate to a title's page and extract available dates
        """
        try:
            logger.info(f"Fetching dates from: {title_url}")
            await page.goto(title_url, wait_until='networkidle', timeout=30000)
            
            # Extract dates - this selector will need to be adjusted based on actual page structure
            # Looking for date elements in various common formats
            date_elements = await page.query_selector_all(
                '.date, [class*="date"], [class*="performance"], '
                'time, [datetime], .availability'
            )
            
            dates = []
            for element in date_elements:
                date_text = await element.text_content()
                if date_text:
                    date_text = date_text.strip()
                    # Basic validation - check if it looks like a date
                    if any(month in date_text.lower() for month in 
                          ['jan', 'feb', 'mar', 'apr', 'may', 'jun', 
                           'jul', 'aug', 'sep', 'oct', 'nov', 'dec']) or \
                       any(char.isdigit() for char in date_text):
                        dates.append(date_text)
            
            logger.info(f"Found {len(dates)} dates for title")
            return dates
            
        except Exception as e:
            logger.error(f"Error fetching dates from {title_url}: {e}")
            return []
    
    async def scrape_with_date_filter(self, titles: List[str], filter_date: str) -> List[TitleAvailability]:
        """
        Scrape titles with a specific date filter applied
        """
        results = []
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context()
            page = await context.new_page()
            
            try:
                # Login
                if not await self.login(page):
                    logger.error("Login failed, aborting scrape")
                    return results
                
                # Navigate to offerings
                await self.navigate_to_offerings(page)
                
                # Apply date filter
                await self.apply_date_filter(page, filter_date)
                
                # Search for each title
                for title in titles:
                    logger.info(f"Searching for title: {title}")
                    title_url = await self.search_title_on_page(page, title)
                    
                    if title_url:
                        # Title found on the filtered date
                        result = TitleAvailability(
                            title=title,
                            dates=[filter_date],
                            url=title_url
                        )
                        results.append(result)
                        logger.info(f"Title '{title}' found for date {filter_date}")
                    
                    # Small delay between searches
                    await page.wait_for_timeout(1000)
                
            except Exception as e:
                logger.error(f"Error during scraping with date filter: {e}")
            finally:
                await browser.close()
        
        return results
    
    async def scrape_without_date_filter(self, titles: List[str]) -> List[TitleAvailability]:
        """
        Scrape titles without date filter, getting all available dates for each
        """
        results = []
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context()
            page = await context.new_page()
            
            try:
                # Login
                if not await self.login(page):
                    logger.error("Login failed, aborting scrape")
                    return results
                
                # Navigate to offerings
                await self.navigate_to_offerings(page)
                
                # Search for each title and get dates
                for title in titles:
                    logger.info(f"Searching for title: {title}")
                    title_url = await self.search_title_on_page(page, title)
                    
                    if title_url:
                        # Get available dates
                        dates = await self.get_available_dates(page, title_url)
                        
                        if dates:
                            result = TitleAvailability(
                                title=title,
                                dates=dates,
                                url=title_url
                            )
                            results.append(result)
                            logger.info(f"Title '{title}' found with {len(dates)} dates")
                        
                        # Navigate back to offerings page for next search
                        await self.navigate_to_offerings(page)
                    
                    # Small delay between searches
                    await page.wait_for_timeout(1000)
                
            except Exception as e:
                logger.error(f"Error during scraping without date filter: {e}")
            finally:
                await browser.close()
        
        return results


class NotificationHandler:
    """Handles sending notifications via various methods"""
    
    def __init__(self, config: dict):
        self.config = config
        self.method = config.get('method', 'email').lower()
    
    def format_alert_message(self, results: List[TitleAvailability], filter_date: Optional[str] = None) -> str:
        """Format the alert message"""
        if not results:
            return "No titles found."
        
        message_lines = ["TDF Title Alert", "=" * 50, ""]
        
        if filter_date:
            message_lines.append(f"Filter Date: {filter_date}")
            message_lines.append("")
            message_lines.append("Available Titles:")
            for result in results:
                message_lines.append(f"  • {result.title}")
                if result.url:
                    message_lines.append(f"    URL: {result.url}")
        else:
            message_lines.append("Titles with Available Dates:")
            for result in results:
                message_lines.append(f"\n• {result.title}")
                if result.url:
                    message_lines.append(f"  URL: {result.url}")
                message_lines.append(f"  Available Dates:")
                for date in result.dates:
                    message_lines.append(f"    - {date}")
        
        message_lines.append("")
        message_lines.append(f"Alert generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        return "\n".join(message_lines)
    
    async def send_notification(self, results: List[TitleAvailability], filter_date: Optional[str] = None):
        """Send notification using configured method"""
        if not results:
            logger.info("No results to notify")
            return
        
        message = self.format_alert_message(results, filter_date)
        
        if self.method == 'email':
            await self._send_email(message)
        elif self.method == 'telegram':
            await self._send_telegram(message)
        elif self.method == 'discord':
            await self._send_discord(message)
        elif self.method == 'slack':
            await self._send_slack(message)
        elif self.method == 'pushbullet':
            await self._send_pushbullet(message)
        elif self.method == 'console':
            # For testing
            print("\n" + message + "\n")
            logger.info("Notification sent to console")
        else:
            logger.error(f"Unknown notification method: {self.method}")
    
    async def _send_email(self, message: str):
        """Send email notification"""
        try:
            email_config = self.config.get('email', {})
            
            smtp_server = email_config.get('smtp_server')
            smtp_port = email_config.get('smtp_port', 587)
            sender = email_config.get('sender')
            password = os.environ.get('EMAIL_PASSWORD') or email_config.get('password')
            recipient = email_config.get('recipient')
            
            if not all([smtp_server, sender, password, recipient]):
                logger.error("Incomplete email configuration")
                return
            
            msg = MIMEMultipart()
            msg['From'] = sender
            msg['To'] = recipient
            msg['Subject'] = "TDF Title Alert"
            
            msg.attach(MIMEText(message, 'plain'))
            
            with smtplib.SMTP(smtp_server, smtp_port) as server:
                server.starttls()
                server.login(sender, password)
                server.send_message(msg)
            
            logger.info(f"Email notification sent to {recipient}")
            
        except Exception as e:
            logger.error(f"Error sending email: {e}")
    
    async def _send_telegram(self, message: str):
        """Send Telegram notification"""
        try:
            import aiohttp
            
            telegram_config = self.config.get('telegram', {})
            bot_token = os.environ.get('TELEGRAM_BOT_TOKEN') or telegram_config.get('bot_token')
            chat_id = telegram_config.get('chat_id')
            
            if not bot_token or not chat_id:
                logger.error("Incomplete Telegram configuration")
                return
            
            url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json={
                    'chat_id': chat_id,
                    'text': message
                }) as response:
                    if response.status == 200:
                        logger.info("Telegram notification sent")
                    else:
                        logger.error(f"Telegram API error: {response.status}")
                        
        except ImportError:
            logger.error("aiohttp not installed, cannot send Telegram notification")
        except Exception as e:
            logger.error(f"Error sending Telegram notification: {e}")
    
    async def _send_discord(self, message: str):
        """Send Discord webhook notification"""
        try:
            import aiohttp
            
            discord_config = self.config.get('discord', {})
            webhook_url = os.environ.get('DISCORD_WEBHOOK') or discord_config.get('webhook_url')
            
            if not webhook_url:
                logger.error("Discord webhook URL not configured")
                return
            
            async with aiohttp.ClientSession() as session:
                async with session.post(webhook_url, json={
                    'content': f"```\n{message}\n```"
                }) as response:
                    if response.status in [200, 204]:
                        logger.info("Discord notification sent")
                    else:
                        logger.error(f"Discord webhook error: {response.status}")
                        
        except ImportError:
            logger.error("aiohttp not installed, cannot send Discord notification")
        except Exception as e:
            logger.error(f"Error sending Discord notification: {e}")
    
    async def _send_slack(self, message: str):
        """Send Slack webhook notification"""
        try:
            import aiohttp
            
            slack_config = self.config.get('slack', {})
            webhook_url = os.environ.get('SLACK_WEBHOOK') or slack_config.get('webhook_url')
            
            if not webhook_url:
                logger.error("Slack webhook URL not configured")
                return
            
            async with aiohttp.ClientSession() as session:
                async with session.post(webhook_url, json={
                    'text': f"```\n{message}\n```"
                }) as response:
                    if response.status == 200:
                        logger.info("Slack notification sent")
                    else:
                        logger.error(f"Slack webhook error: {response.status}")
                        
        except ImportError:
            logger.error("aiohttp not installed, cannot send Slack notification")
        except Exception as e:
            logger.error(f"Error sending Slack notification: {e}")
    
    async def _send_pushbullet(self, message: str):
        """Send Pushbullet notification"""
        try:
            import aiohttp
            
            pb_config = self.config.get('pushbullet', {})
            api_key = os.environ.get('PUSHBULLET_API_KEY') or pb_config.get('api_key')
            
            if not api_key:
                logger.error("Pushbullet API key not configured")
                return
            
            url = "https://api.pushbullet.com/v2/pushes"
            headers = {
                'Access-Token': api_key,
                'Content-Type': 'application/json'
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json={
                    'type': 'note',
                    'title': 'TDF Title Alert',
                    'body': message
                }) as response:
                    if response.status == 200:
                        logger.info("Pushbullet notification sent")
                    else:
                        logger.error(f"Pushbullet API error: {response.status}")
                        
        except ImportError:
            logger.error("aiohttp not installed, cannot send Pushbullet notification")
        except Exception as e:
            logger.error(f"Error sending Pushbullet notification: {e}")


async def main():
    """Main application logic"""
    try:
        logger.info("=" * 60)
        logger.info("TDF Title Monitor Starting")
        logger.info("=" * 60)
        
        # Load configuration
        config_manager = ConfigManager()
        email, password = config_manager.get_credentials()
        titles = config_manager.get_titles()
        filter_date = config_manager.get_filter_date()
        notification_config = config_manager.get_notification_config()
        
        logger.info(f"Monitoring {len(titles)} title(s)")
        if filter_date:
            logger.info(f"Using date filter: {filter_date}")
        
        # Initialize components
        state_manager = StateManager()
        scraper = TDFScraper(email, password)
        notifier = NotificationHandler(notification_config)
        
        # Scrape TDF
        if filter_date:
            results = await scraper.scrape_with_date_filter(titles, filter_date)
            
            # For date-filtered searches, send single alert if any titles found
            if results:
                await notifier.send_notification(results, filter_date)
                
                # Update state
                for result in results:
                    state_manager.update_state(result.title, [filter_date])
            else:
                logger.info("No titles found for the specified date")
        else:
            results = await scraper.scrape_without_date_filter(titles)
            
            # For non-date-filtered, check each result against state
            results_to_alert = []
            
            for result in results:
                if state_manager.should_alert(result.title, result.dates):
                    new_dates = state_manager.get_new_dates(result.title, result.dates)
                    
                    # Create a result with only new dates for the alert
                    alert_result = TitleAvailability(
                        title=result.title,
                        dates=new_dates,
                        url=result.url
                    )
                    results_to_alert.append(alert_result)
                    
                    # Update state with all dates
                    state_manager.update_state(result.title, result.dates)
            
            if results_to_alert:
                await notifier.send_notification(results_to_alert)
            else:
                logger.info("No new dates to alert")
        
        logger.info("=" * 60)
        logger.info("TDF Title Monitor Complete")
        logger.info("=" * 60)
        
    except Exception as e:
        logger.error(f"Fatal error in main: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())