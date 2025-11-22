#!/usr/bin/env python3
"""
SSA Data Update Script
Scrapes updated SSA life table data from the SSA website.
"""

import pandas as pd
import requests
from bs4 import BeautifulSoup
import re
import gzip
from pathlib import Path
import logging
from datetime import datetime
import time

# Optional Selenium imports
try:
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.common.exceptions import TimeoutException, WebDriverException
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Base directory
DATA_DIR = Path(__file__).parent  # Script is now in the data/ssa directory

class SSADataUpdater:
    """SSA data updater using web scraping."""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
    
    def scrape_ssa_table4c6(self):
        """Scrape SSA actuarial life table from table4c6.html."""
        logger.info("Attempting to scrape SSA table4c6.html...")
        
        url = "https://www.ssa.gov/oact/STATS/table4c6.html"
        
        try:
            response = self.session.get(url, timeout=30)
            
            if response.status_code == 200:
                logger.info(f"Successfully retrieved SSA page")
                return self.parse_ssa_html_table(response.text)
            else:
                logger.error(f"HTTP {response.status_code} from {url}")
                return None
                
        except Exception as e:
            logger.error(f"Failed to fetch from {url}: {e}")
            return None
    
    def parse_ssa_html_table(self, html_content):
        """Parse HTML content to extract life table data."""
        logger.info("Parsing SSA HTML table...")
        
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Look for the main data table
        tables = soup.find_all('table')
        
        if not tables:
            logger.error("No tables found in HTML content")
            return None
        
        logger.info(f"Found {len(tables)} table(s) in HTML")
        
        # Find the table with life expectancy data
        target_table = None
        for i, table in enumerate(tables):
            headers = table.find_all(['th', 'td'])
            header_text = ' '.join([h.get_text().strip() for h in headers[:20]])  # Get more text
            logger.info(f"Table {i} header text: {header_text[:200]}...")
            
            if any(keyword in header_text.lower() for keyword in ['age', 'male', 'female', 'life expectancy']):
                target_table = table
                logger.info(f"Selected table {i} as target")
                break
        
        if not target_table:
            logger.error("Could not find life table data in HTML")
            return None
        
        # Extract table data with more detailed debugging
        rows = target_table.find_all('tr')
        data = []
        
        logger.info(f"Found {len(rows)} rows in target table")
        
        for i, row in enumerate(rows):
            cells = row.find_all(['td', 'th'])
            if len(cells) >= 1:  # Get any row with data
                cell_text = [cell.get_text().strip() for cell in cells]
                data.append(cell_text)
                
                # Log first few rows for debugging
                if i < 5:
                    logger.info(f"Row {i}: {cell_text}")
        
        if not data:
            logger.error("No data rows found in table")
            return None
        
        logger.info(f"Extracted {len(data)} rows from HTML table")
        return self.process_scraped_data(data)
    
    def process_scraped_data(self, raw_data):
        """Process scraped data into the expected format."""
        logger.info("Processing scraped SSA data...")
        
        # Find header row and data rows
        header_row = None
        for i, row in enumerate(raw_data[:5]):  # Check first few rows for headers
            row_text = ' '.join(row).lower()
            if 'age' in row_text and ('male' in row_text or 'female' in row_text):
                header_row = i
                break
        
        if header_row is None:
            logger.warning("Could not find header row, assuming first row contains headers")
            header_row = 0
        
        headers = [h.strip() for h in raw_data[header_row]]
        data_rows = raw_data[header_row + 1:]
        
        logger.info(f"Found headers: {headers}")
        logger.info(f"Processing {len(data_rows)} data rows")
        
        # Create DataFrame - handle column mismatch
        if data_rows:
            max_cols = max(len(row) for row in data_rows)
            # Ensure headers match the data columns
            if len(headers) != max_cols:
                logger.warning(f"Header count ({len(headers)}) != data columns ({max_cols}), adjusting...")
                if max_cols > len(headers):
                    # Add generic column names for extra columns
                    headers.extend([f'col_{i}' for i in range(len(headers), max_cols)])
                else:
                    # Truncate headers if there are fewer data columns
                    headers = headers[:max_cols]
            
            # Pad rows that have fewer columns
            padded_rows = []
            for row in data_rows:
                if len(row) < max_cols:
                    padded_row = row + [''] * (max_cols - len(row))
                else:
                    padded_row = row[:max_cols]
                padded_rows.append(padded_row)
            
            df = pd.DataFrame(padded_rows, columns=headers)
        else:
            df = pd.DataFrame()
        
        # Clean and standardize the data
        return self.standardize_ssa_data(df)
    
    def standardize_ssa_data(self, df):
        """Standardize scraped data to match package format."""
        logger.info("Standardizing SSA data format...")
        
        # Expected columns: age, male_death_prob, male_n_lives, male_life_expectancy, 
        #                  female_death_prob, female_n_lives, female_life_expectancy, year
        
        # Map columns based on actual SSA table structure
        column_mapping = {}
        
        logger.info(f"Available columns: {df.columns.tolist()}")
        
        # Find age column
        for col in df.columns:
            col_lower = col.lower()
            if 'age' in col_lower or 'exact' in col_lower:
                column_mapping['age'] = col
                break
        
        # Find male and female columns
        # SSA tables typically have just "Male" and "Female" columns with life expectancy values
        for col in df.columns:
            col_lower = col.lower()
            if col_lower == 'male':
                column_mapping['male_life_expectancy'] = col
            elif col_lower == 'female':
                column_mapping['female_life_expectancy'] = col
            elif 'male' in col_lower and len(col_lower) < 10:  # Simple male column
                column_mapping['male_life_expectancy'] = col
            elif 'female' in col_lower and len(col_lower) < 10:  # Simple female column
                column_mapping['female_life_expectancy'] = col
        
        if len(column_mapping) < 3:
            logger.error(f"Could not map required columns. Available: {df.columns.tolist()}")
            return None
        
        # Map the correct columns based on the actual SSA table structure:
        # Col 0: Age, Col 1: Male death prob, Col 2: Male lives, Col 3: Male life expectancy
        # Col 4: Female death prob, Col 5: Female lives, Col 6: Female life expectancy
        
        result_data = []
        current_year = datetime.now().year  # Use current year for new data
        
        for _, row in df.iterrows():
            try:
                # Based on actual table structure
                if len(row) >= 7:  # Full 7-column structure
                    age_val = self.clean_numeric(row.iloc[0])
                    male_death_prob = self.clean_numeric(row.iloc[1])
                    male_n_lives = self.clean_numeric(row.iloc[2])
                    male_le = self.clean_numeric(row.iloc[3])  # Column 3 is male life expectancy
                    female_death_prob = self.clean_numeric(row.iloc[4])
                    female_n_lives = self.clean_numeric(row.iloc[5])
                    female_le = self.clean_numeric(row.iloc[6])  # Column 6 is female life expectancy
                elif len(row) >= 3:  # Fallback for simpler structure
                    age_val = self.clean_numeric(row.get(column_mapping.get('age', ''), ''))
                    male_le = self.clean_numeric(row.get(column_mapping.get('male_life_expectancy', ''), ''))
                    female_le = self.clean_numeric(row.get(column_mapping.get('female_life_expectancy', ''), ''))
                    male_death_prob = None
                    male_n_lives = None
                    female_death_prob = None
                    female_n_lives = None
                else:
                    continue
                
                if age_val is not None and (male_le is not None or female_le is not None):
                    # Clean up comma-separated numbers
                    if male_n_lives and isinstance(male_n_lives, str):
                        male_n_lives = self.clean_numeric(male_n_lives.replace(',', ''))
                    if female_n_lives and isinstance(female_n_lives, str):
                        female_n_lives = self.clean_numeric(female_n_lives.replace(',', ''))
                    
                    result_data.append({
                        'age': int(age_val),
                        'male_death_prob': male_death_prob,
                        'male_n_lives': male_n_lives,
                        'male_life_expectancy': male_le,
                        'female_death_prob': female_death_prob,
                        'female_n_lives': female_n_lives, 
                        'female_life_expectancy': female_le,
                        'year': current_year
                    })
            except Exception as e:
                logger.warning(f"Error processing row: {e}")
                continue
        
        if not result_data:
            logger.error("No valid data rows processed")
            return None
        
        result_df = pd.DataFrame(result_data)
        logger.info(f"Standardized {len(result_df)} rows of SSA data")
        return result_df
    
    def clean_numeric(self, value):
        """Clean and convert string values to numeric."""
        if pd.isna(value) or value == '':
            return None
        
        # Remove common formatting
        cleaned = str(value).strip()
        cleaned = re.sub(r'[,$%"]', '', cleaned)
        
        try:
            return float(cleaned)
        except:
            return None
    
    def try_alternative_ssa_sources(self):
        """Try alternative SSA data sources if main scraping fails."""
        logger.info("Trying alternative SSA data sources...")
        
        # Try historical table4c6 URLs with specific years and trustees reports
        historical_urls = [
            # Recent historical data
            "https://www.ssa.gov/oact/STATS/table4c6_2021_TR2024.html",
            "https://www.ssa.gov/oact/STATS/table4c6_2022_TR2025.html", 
            "https://www.ssa.gov/oact/STATS/table4c6_2020_TR2023.html",
            "https://www.ssa.gov/oact/STATS/table4c6_2019_TR2022.html",
            "https://www.ssa.gov/oact/STATS/table4c6_2018_TR2021.html",
            
            # Trustees report life expectancy pages
            "https://www.ssa.gov/oact/tr/2025/lr5a4.html",
            "https://www.ssa.gov/oact/TR/2024/lr5a4.html", 
            "https://www.ssa.gov/oact/TR/2023/lr5a4.html",
            
            # 2024 cohort life tables
            "https://www.ssa.gov/OACT/HistEst/CohLifeTables/2024/CohLifeTables2024.html",
            
            # Period life tables
            "https://www.ssa.gov/oact/HistEst/PerLifeTables/2024/PerLifeTables2024.html"
        ]
        
        for url in historical_urls:
            try:
                logger.info(f"Trying historical URL: {url}")
                response = self.session.get(url, timeout=30)
                if response.status_code == 200:
                    logger.info(f"Successfully retrieved data from {url}")
                    result = self.parse_ssa_html_table(response.text)
                    if result is not None:
                        # Extract year from URL if possible
                        year_match = None
                        import re
                        year_patterns = [r'(\d{4})_TR\d{4}', r'/(\d{4})/', r'_(\d{4})\.html']
                        for pattern in year_patterns:
                            match = re.search(pattern, url)
                            if match:
                                year_match = int(match.group(1))
                                break
                        
                        if year_match and year_match >= 2018:
                            # Update the year in the result DataFrame
                            result['year'] = year_match
                            logger.info(f"Updated data year to {year_match}")
                        
                        return result
                else:
                    logger.warning(f"HTTP {response.status_code} from {url}")
                    
            except Exception as e:
                logger.warning(f"Failed to access {url}: {e}")
                continue
        
        return None
    
    def try_selenium_scraping(self):
        """Try using Selenium to bypass 403 errors."""
        if not SELENIUM_AVAILABLE:
            logger.warning("Selenium not available - install with: pip install selenium")
            return None
        
        logger.info("Attempting to use Selenium for SSA data scraping...")
        
        # URLs to try with Selenium
        selenium_urls = [
            "https://www.ssa.gov/oact/STATS/table4c6.html",
            "https://www.ssa.gov/oact/STATS/table4c6_2021_TR2024.html",
            "https://www.ssa.gov/oact/STATS/table4c6_2022_TR2025.html"
        ]
        
        driver = None
        try:
            # Setup Chrome options
            chrome_options = Options()
            chrome_options.add_argument("--headless")  # Run in background
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--disable-gpu")
            chrome_options.add_argument("--window-size=1920,1080")
            chrome_options.add_argument("--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
            
            # Try to create driver (this will fail if ChromeDriver is not installed)
            try:
                driver = webdriver.Chrome(options=chrome_options)
            except Exception as e:
                logger.warning(f"Could not create Chrome driver: {e}")
                logger.info("Install ChromeDriver from: https://chromedriver.chromium.org/")
                return None
            
            for url in selenium_urls:
                try:
                    logger.info(f"Selenium trying: {url}")
                    driver.get(url)
                    
                    # Wait for page to load
                    WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located((By.TAG_NAME, "body"))
                    )
                    
                    # Check for dropdown/select elements and iterate through recent options
                    combined_data = []
                    try:
                        dropdowns = driver.find_elements(By.TAG_NAME, "select")
                        if dropdowns:
                            logger.info(f"Found {len(dropdowns)} dropdown(s) on page")
                            
                            for i, dropdown in enumerate(dropdowns):
                                options = dropdown.find_elements(By.TAG_NAME, "option")
                                option_values = [opt.text for opt in options]
                                logger.info(f"Dropdown {i}: {option_values}")
                                
                                # Try the most recent few years
                                for j, option in enumerate(options[:3]):  # Get top 3 most recent
                                    try:
                                        logger.info(f"Selecting dropdown option: {option.text}")
                                        option.click()
                                        time.sleep(2)  # Wait for page to update
                                        
                                        # Wait for table to refresh
                                        WebDriverWait(driver, 10).until(
                                            EC.presence_of_element_located((By.TAG_NAME, "table"))
                                        )
                                        
                                        # Get updated page source
                                        updated_page_source = driver.page_source
                                        
                                        if "life table" in updated_page_source.lower() or "life expectancy" in updated_page_source.lower():
                                            logger.info(f"Got data for option: {option.text}")
                                            result = self.parse_ssa_html_table(updated_page_source)
                                            
                                            if result is not None:
                                                # Extract year from option text
                                                year_match = re.search(r'(\d{4})', option.text)
                                                if year_match:
                                                    year = int(year_match.group(1))
                                                    result['year'] = year
                                                    logger.info(f"Set data year to {year}")
                                                
                                                combined_data.append(result)
                                                
                                                # Use the first successful result for now
                                                if j == 0:  # Return the most recent year's data
                                                    return result
                                        
                                    except Exception as e:
                                        logger.warning(f"Error with dropdown option {option.text}: {e}")
                                        continue
                        
                        # If no dropdown found, proceed with default page
                        if not dropdowns:
                            logger.info("No dropdowns found, using default page")
                            
                            # Wait for table to be present
                            WebDriverWait(driver, 10).until(
                                EC.presence_of_element_located((By.TAG_NAME, "table"))
                            )
                            
                            # Get page source and check if we got the actual page
                            page_source = driver.page_source
                            
                            if "life table" in page_source.lower() or "life expectancy" in page_source.lower():
                                logger.info(f"Successfully loaded SSA page with Selenium: {url}")
                                result = self.parse_ssa_html_table(page_source)
                                
                                if result is not None:
                                    # Extract year from URL 
                                    year_match = None
                                    year_patterns = [r'(\d{4})_TR\d{4}', r'/(\d{4})/', r'_(\d{4})\.html']
                                    for pattern in year_patterns:
                                        match = re.search(pattern, url)
                                        if match:
                                            year_match = int(match.group(1))
                                            break
                                    
                                    if year_match and year_match >= 2018:
                                        result['year'] = year_match
                                        logger.info(f"Updated data year to {year_match}")
                                    
                                    return result
                            else:
                                logger.warning(f"Page does not contain life table data: {url}")
                                
                    except Exception as e:
                        logger.warning(f"Error checking dropdowns: {e}")
                        
                except TimeoutException:
                    logger.warning(f"Timeout waiting for page to load: {url}")
                except Exception as e:
                    logger.warning(f"Error with Selenium for {url}: {e}")
                    continue
            
            logger.error("Failed to get SSA data with Selenium from all URLs")
            return None
            
        except Exception as e:
            logger.error(f"General Selenium error: {e}")
            return None
            
        finally:
            if driver:
                try:
                    driver.quit()
                except:
                    pass
    
    def save_ssa_data(self, df, overwrite=False):
        """Save SSA data in the package format."""
        if df is None or df.empty:
            logger.error("No data to save")
            return False
            
        try:
            # Save as CSV (uncompressed like the original)
            output_file = DATA_DIR / "ssa.csv"
            backup_file = DATA_DIR / f"ssa-backup-{datetime.now().strftime('%Y%m%d')}.csv"
            
            # Check if we should overwrite
            if output_file.exists() and not overwrite:
                new_file = DATA_DIR / f"ssa-new-{datetime.now().strftime('%Y%m%d')}.csv"
                logger.info(f"File exists and overwrite=False. Saving to {new_file}")
                df.to_csv(new_file, index=False)
                logger.info(f"Saved {len(df)} records to {new_file}")
                logger.info("To replace the main data file, run with --overwrite or manually copy the file")
                return True
            
            # Backup original file before overwriting
            if output_file.exists():
                import shutil
                shutil.copy2(output_file, backup_file)
                logger.info(f"Backed up original data to {backup_file}")
            
            # Save new data
            df.to_csv(output_file, index=False)
            logger.info(f"Saved {len(df)} records to {output_file}")
            
            # Report data coverage
            years = df['year'].unique()
            logger.info(f"Data covers years: {years}")
            
            ages = df['age'].unique()
            logger.info(f"Data covers ages: {ages.min()} to {ages.max()}")
            
            return True
            
        except Exception as e:
            logger.error(f"Error saving data: {e}")
            return False
    
    def update_ssa_data(self, overwrite=False):
        """Main method to update SSA data."""
        logger.info("Starting SSA data update...")
        
        # Try main SSA table first
        data = self.scrape_ssa_table4c6()
        
        if data is None:
            # Try alternative sources
            data = self.try_alternative_ssa_sources()
        
        if data is None:
            # Try Selenium as final fallback
            logger.info("Trying Selenium as fallback...")
            data = self.try_selenium_scraping()
        
        if data is None:
            logger.error("Failed to fetch SSA data from all sources (requests + Selenium)")
            return False
        
        return self.save_ssa_data(data, overwrite=overwrite)

def main():
    """Main function."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Update SSA life table data')
    parser.add_argument('--overwrite', action='store_true',
                        help='Overwrite existing data file (default: save to new file)')
    parser.add_argument('--verbose', '-v', action='store_true',
                        help='Verbose output')
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    print("SSA Data Updater v1.0.0")
    print("=" * 40)
    
    if not args.overwrite:
        print("📁 Data preservation mode: Will not overwrite existing files")
        print("   Use --overwrite to replace the main data file")
        print()
    
    updater = SSADataUpdater()
    success = updater.update_ssa_data(overwrite=args.overwrite)
    
    if success:
        print("✅ SSA data updated successfully!")
    else:
        print("❌ SSA data update failed")
        print("Consider manual download from: https://www.ssa.gov/oact/STATS/table4c6.html")

if __name__ == "__main__":
    main()