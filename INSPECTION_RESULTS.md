# TDF.org Inspection Results

## Executive Summary
Attempted to inspect TDF.org pages using Playwright (Chromium and Firefox) to identify HTML structure and CSS selectors. The inspection was blocked by Imperva Incapsula Web Application Firewall (WAF).

## Inspection Attempts
- **Tools Used**: Playwright (Python), curl
- **Browsers**: Chromium (headless), Firefox (headless)
- **Techniques**: 
  - Standard automation
  - `playwright-stealth` (to mask automation signals)
  - Custom User-Agents and Viewports
  - Direct navigation to deep links (`https://nycgw47.tdf.org/TDFCustomOfferings/Current`)
  - Navigation via Homepage (`https://www.tdf.org/`)

## Findings
1. **WAF Protection**: The site is protected by Imperva Incapsula. All automated requests from the inspection environment were intercepted.
2. **Response Content**: The WAF returns an HTML page containing an iframe with the source `/_Incapsula_Resource`.
3. **Error Message**: Inside the iframe, the message "Request unsuccessful. Incapsula incident ID: [ID]" is displayed.
4. **Behavior**: 
   - Requests to `https://my.tdf.org/account/login` are blocked.
   - Requests to `https://nycgw47.tdf.org/TDFCustomOfferings/Current` are blocked.
   - Even `curl` requests are blocked.

## Implications for Development
- **Selector Verification**: Unable to verify or update CSS selectors due to lack of access.
- **Bot Detection**: The scraper will likely fail in production environments if they have similar IP reputation or fingerprinting characteristics as the development environment, unless WAF bypass techniques (e.g., residential proxies, solving CAPTCHAs, or using a headful browser with human interaction) are implemented.

## Current Selectors (from Codebase)
The existing codebase uses generic/heuristic selectors which suggests they were either guessed or are intended to be robust against minor changes. However, without inspection, we cannot confirm if they match the current site structure.

**Login Page:**
- Email Input: `input[type="email"], input[name="email"], input[id*="email"]`
- Password Input: `input[type="password"], input[name="password"], input[id*="password"]`
- Submit Button: `button[type="submit"], input[type="submit"]`

**Offerings Page:**
- Search Input: `input[type="search"], input[type="text"], input[placeholder*="search"]`
- Date Filter: `input[type="date"], input[placeholder*="date"], input[name*="date"]`
- Title Listing: Uses Playwright text selector `text=/[Title]/i`
- View Button: `a:has-text("View"), button:has-text("View")`

**Detail Page:**
- Dates: `.date, [class*="date"], [class*="performance"], time, [datetime], .availability`

## Recommendation
To proceed with accurate selector replacement:
1. Obtain access from a residential IP or permitted environment.
2. Or, use a tool that can solve the Incapsula JS challenge (requiring headful mode or advanced stealth).
3. If this is for a refactoring task, note that the current selectors are "best-effort" generics.
