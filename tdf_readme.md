# TDF Title Monitor

A Python application that monitors TDF.org (Theatre Development Fund) for available show titles and sends alerts when your desired shows become available.

## Features

- 🎭 **Automated Monitoring**: Continuously checks TDF.org for specified show titles
- 📅 **Date Filtering**: Optionally filter by specific performance dates
- 🔔 **Multiple Notification Methods**: Email, Telegram, Discord, Slack, Pushbullet
- 💾 **Smart State Management**: Only alerts on new availability (avoids duplicate notifications)
- 🔒 **Secure Credential Management**: Support for environment variables
- 📊 **Comprehensive Logging**: Detailed logs for debugging and monitoring
- ⚡ **Async/Await**: Efficient asynchronous web scraping with Playwright

## Installation

### Prerequisites

- Python 3.8 or higher
- pip (Python package manager)

### Step 1: Clone or Download

Save all the project files to a directory:
```bash
mkdir tdf-monitor
cd tdf-monitor
```

### Step 2: Install Dependencies

```bash
pip install -r requirements.txt
```

### Step 3: Install Playwright Browsers

```bash
playwright install chromium
```

### Step 4: Configure

1. Copy `config.yaml` and edit it with your settings:
   - Update TDF credentials
   - Add the show titles you want to monitor
   - Configure your preferred notification method

## Configuration

### Basic Configuration

Edit `config.yaml`:

```yaml
tdf_credentials:
  email: "your-email@example.com"
  password: "your-password"

titles:
  - "Hamilton"
  - "The Lion King"
  - "Wicked"

notifications:
  method: "email"  # or telegram, discord, slack, pushbullet, console
```

### Security Best Practices

**⚠️ IMPORTANT: Never commit credentials to version control!**

Instead of storing credentials in `config.yaml`, use environment variables:

```bash
# Linux/Mac
export TDF_EMAIL="your-email@example.com"
export TDF_PASSWORD="your-password"

# Windows (PowerShell)
$env:TDF_EMAIL="your-email@example.com"
$env:TDF_PASSWORD="your-password"
```

For permanent storage, add to your shell profile (`~/.bashrc`, `~/.zshrc`, etc.)

### Date Filtering

To check availability for a specific date:

```yaml
filter_date: "12/25/2025"  # MM/DD/YYYY format
```

Leave it as `null` or omit it to check all available dates.

### Notification Methods

#### Email

```yaml
notifications:
  method: "email"
  email:
    smtp_server: "smtp.gmail.com"
    smtp_port: 587
    sender: "your-email@gmail.com"
    password: "your-app-password"  # Use App Password for Gmail
    recipient: "recipient@example.com"
```

**Gmail Setup**:
1. Enable 2-Factor Authentication
2. Generate an App Password: https://myaccount.google.com/apppasswords
3. Use the App Password in the config or `EMAIL_PASSWORD` environment variable

#### Telegram

```yaml
notifications:
  method: "telegram"
  telegram:
    bot_token: "your-bot-token"
    chat_id: "your-chat-id"
```

**Telegram Setup**:
1. Create a bot with [@BotFather](https://t.me/botfather)
2. Get your chat ID from [@userinfobot](https://t.me/userinfobot)
3. Store bot token in `TELEGRAM_BOT_TOKEN` environment variable

#### Discord

```yaml
notifications:
  method: "discord"
  discord:
    webhook_url: "https://discord.com/api/webhooks/..."
```

**Discord Setup**:
1. Server Settings → Integrations → Webhooks → New Webhook
2. Copy the webhook URL
3. Store in `DISCORD_WEBHOOK` environment variable

#### Slack

```yaml
notifications:
  method: "slack"
  slack:
    webhook_url: "https://hooks.slack.com/services/..."
```

**Slack Setup**:
1. Create an Incoming Webhook: https://api.slack.com/messaging/webhooks
2. Store in `SLACK_WEBHOOK` environment variable

#### Pushbullet

```yaml
notifications:
  method: "pushbullet"
  pushbullet:
    api_key: "your-api-key"
```

**Pushbullet Setup**:
1. Get API key from: https://www.pushbullet.com/#settings/account
2. Store in `PUSHBULLET_API_KEY` environment variable

## Usage

### Manual Run

```bash
python tdf_monitor.py
```

### Scheduled Execution with Cron

For automated monitoring, set up a cron job:

```bash
# Edit crontab
crontab -e

# Run every 12 hours at 8 AM and 8 PM
0 8,20 * * * cd /path/to/tdf-monitor && /usr/bin/python3 tdf_monitor.py >> tdf_monitor.log 2>&1

# Run daily at 9 AM
0 9 * * * cd /path/to/tdf-monitor && /usr/bin/python3 tdf_monitor.py >> tdf_monitor.log 2>&1

# Run every 6 hours
0 */6 * * * cd /path/to/tdf-monitor && /usr/bin/python3 tdf_monitor.py >> tdf_monitor.log 2>&1
```

**Cron Tips**:
- Use full paths to Python and the script
- Redirect output to a log file for debugging
- Test the command manually before adding to cron

### Windows Task Scheduler

1. Open Task Scheduler
2. Create Basic Task
3. Set trigger (daily, specific time, etc.)
4. Action: Start a program
   - Program: `python.exe`
   - Arguments: `C:\path\to\tdf_monitor.py`
   - Start in: `C:\path\to\tdf-monitor`

## Testing

Run the unit tests:

```bash
# Run all tests
pytest test_tdf_monitor.py -v

# Run with coverage report
pytest test_tdf_monitor.py -v --cov=tdf_monitor --cov-report=term-missing

# Run specific test class
pytest test_tdf_monitor.py::TestConfigManager -v
```

## File Structure

```
tdf-monitor/
├── tdf_monitor.py          # Main application
├── config.yaml             # Configuration file
├── requirements.txt        # Python dependencies
├── test_tdf_monitor.py     # Unit tests
├── state.json              # Persistent state (auto-generated)
├── tdf_monitor.log         # Log file (auto-generated)
└── README.md               # This file
```

## How It Works

1. **Login**: The application logs into TDF.org using your credentials
2. **Search**: Searches for your specified titles on the offerings page
3. **Extract**: Retrieves available dates for each found title
4. **Compare**: Checks against previous runs to identify new availability
5. **Notify**: Sends alerts only when new dates are found
6. **Update**: Saves the current state to avoid duplicate alerts

## State Management

The application maintains a `state.json` file to track what has been alerted:

- **New titles**: Always trigger an alert
- **Existing titles with new dates**: Trigger an alert
- **Existing titles with same dates**: No alert
- **Dates removed**: No alert (only new dates matter)

To reset and get all alerts again:
```bash
rm state.json
```

## Troubleshooting

### Login Issues

1. Verify credentials are correct
2. Check if TDF.org is accessible
3. Review logs in `tdf_monitor.log`
4. Try running with `headless=False` in the code to see the browser

### No Notifications Received

1. Test notification method manually
2. Check notification service credentials
3. Verify `state.json` isn't blocking new alerts
4. Check logs for error messages

### Titles Not Found

1. Verify exact title names on TDF.org
2. Title search is case-insensitive but must match
3. Check if the show is currently available on TDF
4. Review the HTML selectors in the code (may need updates if TDF changes their site)

### Playwright Issues

```bash
# Reinstall browsers
playwright install chromium

# Update Playwright
pip install --upgrade playwright
```

## Logs

Logs are written to both console and `tdf_monitor.log`:

- **INFO**: Normal operations
- **WARNING**: Non-critical issues
- **ERROR**: Problems that prevent operation

## Security Considerations

1. **Never commit `config.yaml` with credentials to version control**
2. Use environment variables for sensitive data
3. Use `.gitignore` to exclude:
   ```
   config.yaml
   state.json
   *.log
   __pycache__/
   ```
4. Change your TDF password after testing
5. Use unique, strong passwords
6. For email, use app-specific passwords, not your main password

## Customization

### Adjusting Selectors

If TDF.org changes their website structure, you may need to update CSS selectors in `tdf_monitor.py`:

- Login form fields: `input[type="email"]`, `input[type="password"]`
- Search input: `input[type="search"]`
- Date input: `input[type="date"]`
- View buttons: `a:has-text("View")`
- Date elements: `.date`, `[class*="date"]`

### Timeout Adjustments

Modify timeouts in the code if needed:
```python
await page.goto(url, wait_until='networkidle', timeout=30000)  # 30 seconds
```

## Performance Tips

1. Use date filtering when possible to reduce scraping time
2. Run during off-peak hours to be respectful of TDF's servers
3. Don't run more frequently than every few hours
4. Monitor log file size and rotate if needed

## Contributing

Feel free to submit issues and enhancement requests!

## License

This is a personal automation tool. Respect TDF.org's terms of service and rate limits.

## Disclaimer

This tool is for personal use only. Be respectful of TDF.org's servers and don't abuse their service. The author is not responsible for any misuse or violations of TDF's terms of service.

## Support

For issues or questions:
1. Check the logs in `tdf_monitor.log`
2. Review this README
3. Run tests to verify setup: `pytest test_tdf_monitor.py -v`

## Changelog

### Version 1.0.0
- Initial release
- Support for multiple notification methods
- Smart state management
- Comprehensive error handling
- Full test coverage