#!/usr/bin/env python3
"""
WHO Data Update Script
Attempts to fetch updated WHO life expectancy data from available sources.
"""

import pandas as pd
import requests
import json
import gzip
from pathlib import Path
import logging
from datetime import datetime

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Base directory
DATA_DIR = Path(__file__).parent  # Script is now in the data/who directory

class WHODataUpdater:
    """WHO data updater using various available methods."""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'lost_years/0.4.0 (https://github.com/gojiplus/lost_years)'
        })
    
    def try_working_gho_api(self):
        """Try working GHO API endpoints."""
        logger.info("Attempting WHO GHO API with working endpoints...")
        
        # Working endpoints based on current WHO documentation
        endpoints = [
            # Current OData API
            "https://ghoapi.azureedge.net/api/WHOSIS_000001",
            # Athena API with correct format
            "https://apps.who.int/gho/athena/api/GHO/WHOSIS_000001?format=csv&profile=verbose",
            "https://apps.who.int/gho/athena/api/GHO/WHOSIS_000001.csv?profile=verbose",
        ]
        
        for url in endpoints:
            try:
                logger.info(f"Trying: {url}")
                response = self.session.get(url, timeout=30, allow_redirects=True)
                
                if response.status_code == 200:
                    logger.info(f"Success! Got response from {url}")
                    
                    # Check if it's JSON or CSV
                    content_type = response.headers.get('content-type', '').lower()
                    
                    if 'json' in content_type or url.endswith('/api/WHOSIS_000001'):
                        try:
                            data = response.json()
                            return self.process_odata_json(data)
                        except:
                            # If JSON fails, try as CSV
                            pass
                    
                    # Try as CSV
                    if 'csv' in content_type or 'csv' in url or response.text.startswith('GHO'):
                        logger.info("Processing as CSV data")
                        return self.process_who_csv(response.text)
                    
                else:
                    logger.warning(f"HTTP {response.status_code} from {url}")
                    
            except Exception as e:
                logger.warning(f"Failed to fetch from {url}: {e}")
                continue
                
        return None
    
    def try_new_who_platform(self):
        """Try new WHO platform API."""
        logger.info("Attempting new WHO platform...")
        
        # New platform endpoints (these may require authentication)
        endpoints = [
            "https://platform.who.int/api/mortality/data",
            "https://api.who.int/v1/data",
        ]
        
        for endpoint in endpoints:
            try:
                logger.info(f"Trying: {endpoint}")
                response = self.session.get(endpoint, timeout=30)
                
                if response.status_code == 200:
                    logger.info(f"Success! Got response from {endpoint}")
                    return response.json()
                    
                logger.warning(f"HTTP {response.status_code} from {endpoint}")
                
            except Exception as e:
                logger.warning(f"Failed to fetch from {endpoint}: {e}")
                
        return None
    
    def process_odata_json(self, data):
        """Process JSON data from OData API."""
        logger.info("Processing OData JSON response")
        
        if 'value' in data:
            df = pd.DataFrame(data['value'])
            logger.info(f"OData JSON DataFrame shape: {df.shape}")
            logger.info(f"Columns: {df.columns.tolist()}")
            
            # Map OData columns to package format
            df_mapped = df.copy()
            
            # Log dimension values to understand the structure
            logger.info(f"Sample Dim1 values (Sex): {df['Dim1'].unique()[:5] if 'Dim1' in df.columns else 'N/A'}")
            logger.info(f"Sample Dim2 values (Age): {df['Dim2'].unique()[:5] if 'Dim2' in df.columns else 'N/A'}")
            logger.info(f"Sample Dim3 values: {df['Dim3'].unique()[:5] if 'Dim3' in df.columns else 'N/A'}")
            logger.info(f"Sample SpatialDim values: {df['SpatialDim'].unique()[:5] if 'SpatialDim' in df.columns else 'N/A'}")
            
            # Map key columns - check which dimensions contain what data
            column_mapping = {
                'SpatialDim': 'COUNTRY (CODE)',
                'ParentLocation': 'COUNTRY (DISPLAY)', 
                'TimeDim': 'YEAR (CODE)',
                'Value': 'Display Value',
                'NumericValue': 'Numeric',
                'IndicatorCode': 'GHO (CODE)',
                'Low': 'Low',
                'High': 'High',
                'Comments': 'Comments'
            }
            
            # Determine which dimension contains sex and age group
            # WHO life expectancy often has sex in Dim1 and age groups might be in other dims
            if 'Dim1' in df.columns:
                # Check if Dim1 contains sex codes
                dim1_values = df['Dim1'].dropna().unique()
                if any('SEX' in str(val) or val in ['MLE', 'FMLE', 'BTSX'] for val in dim1_values):
                    column_mapping['Dim1'] = 'SEX (CODE)'
                else:
                    column_mapping['Dim1'] = 'AGEGROUP (CODE)'
                    
            if 'Dim2' in df.columns and 'SEX (CODE)' not in column_mapping.values():
                column_mapping['Dim2'] = 'SEX (CODE)'
            elif 'Dim2' in df.columns and 'AGEGROUP (CODE)' not in column_mapping.values():
                column_mapping['Dim2'] = 'AGEGROUP (CODE)'
                
            if 'Dim3' in df.columns and 'AGEGROUP (CODE)' not in column_mapping.values():
                column_mapping['Dim3'] = 'AGEGROUP (CODE)'
            
            # Apply column mapping
            for old_col, new_col in column_mapping.items():
                if old_col in df.columns:
                    df_mapped[new_col] = df[old_col]
                    logger.info(f"Mapped {old_col} -> {new_col}, sample values: {df[old_col].dropna().unique()[:3]}")
            
            # Set GHO code for life expectancy
            df_mapped['GHO (CODE)'] = 'LIFE_0000000035'
            
            # Handle missing age group - this WHO data appears to be life expectancy at birth
            if 'AGEGROUP (CODE)' in df_mapped.columns and df_mapped['AGEGROUP (CODE)'].isna().all():
                df_mapped['AGEGROUP (CODE)'] = 'AGELT1'  # Life expectancy at birth
                logger.info("Set age group to AGELT1 (life expectancy at birth) for all records")
            
            # Fix sex codes to match package expectations (remove SEX_ prefix)
            if 'SEX (CODE)' in df_mapped.columns:
                df_mapped['SEX (CODE)'] = df_mapped['SEX (CODE)'].str.replace('SEX_', '', regex=False)
                logger.info(f"Fixed sex codes, now: {df_mapped['SEX (CODE)'].unique()}")
            
            # Add missing display columns with placeholder values
            for col_prefix in ['COUNTRY', 'YEAR', 'SEX', 'AGEGROUP', 'GHO', 'REGION', 'PUBLISHSTATE']:
                for suffix in ['(DISPLAY)', '(URL)']:
                    col_name = f"{col_prefix} {suffix}"
                    if col_name not in df_mapped.columns:
                        df_mapped[col_name] = None
            
            # Add missing numeric columns
            for col in ['StdErr', 'StdDev']:
                if col not in df_mapped.columns:
                    df_mapped[col] = None
            
            logger.info(f"Mapped DataFrame shape: {df_mapped.shape}")
            logger.info(f"Mapped columns: {df_mapped.columns.tolist()}")
            
            return df_mapped
        
        return pd.DataFrame([data]) if isinstance(data, dict) else pd.DataFrame(data)
    
    def process_who_csv(self, csv_text):
        """Process CSV data from WHO API."""
        logger.info("Processing WHO CSV data")
        
        # Read CSV from string
        from io import StringIO
        df = pd.read_csv(StringIO(csv_text))
        
        logger.info(f"CSV DataFrame shape: {df.shape}")
        logger.info(f"CSV Columns: {df.columns.tolist()}")
        logger.info(f"First few rows:\n{df.head()}")
        
        # Map WHO CSV columns to package format
        column_mapping = {
            'GHO (CODE)': 'GHO (CODE)',
            'GHO (DISPLAY)': 'GHO (DISPLAY)', 
            'GHO (URL)': 'GHO (URL)',
            'PUBLISHSTATE (CODE)': 'PUBLISHSTATE (CODE)',
            'PUBLISHSTATE (DISPLAY)': 'PUBLISHSTATE (DISPLAY)',
            'PUBLISHSTATE (URL)': 'PUBLISHSTATE (URL)',
            'YEAR (CODE)': 'YEAR (CODE)',
            'YEAR (DISPLAY)': 'YEAR (DISPLAY)',
            'YEAR (URL)': 'YEAR (URL)',
            'REGION (CODE)': 'REGION (CODE)',
            'REGION (DISPLAY)': 'REGION (DISPLAY)',
            'REGION (URL)': 'REGION (URL)',
            'COUNTRY (CODE)': 'COUNTRY (CODE)',
            'COUNTRY (DISPLAY)': 'COUNTRY (DISPLAY)',
            'COUNTRY (URL)': 'COUNTRY (URL)',
            'SEX (CODE)': 'SEX (CODE)',
            'SEX (DISPLAY)': 'SEX (DISPLAY)',
            'SEX (URL)': 'SEX (URL)',
            'AGEGROUP (CODE)': 'AGEGROUP (CODE)',
            'AGEGROUP (DISPLAY)': 'AGEGROUP (DISPLAY)',
            'AGEGROUP (URL)': 'AGEGROUP (URL)',
            'Display Value': 'Display Value',
            'Numeric': 'Numeric',
            'Low': 'Low',
            'High': 'High',
            'StdErr': 'StdErr',
            'StdDev': 'StdDev',
            'Comments': 'Comments'
        }
        
        # Rename columns that exist
        df_renamed = df.copy()
        for old_col, new_col in column_mapping.items():
            if old_col in df.columns:
                df_renamed = df_renamed.rename(columns={old_col: new_col})
        
        # Ensure we have the GHO code for life expectancy
        if 'GHO (CODE)' not in df_renamed.columns:
            df_renamed['GHO (CODE)'] = 'WHOSIS_000001'
            
        return df_renamed
    
    def process_gho_json(self, data, indicator):
        """Process JSON data from GHO API."""
        logger.info(f"Processing GHO JSON data for {indicator}")
        
        if 'fact' not in data:
            logger.error("No 'fact' data found in response")
            return None
            
        facts = data['fact']
        logger.info(f"Found {len(facts)} records")
        
        # Convert to DataFrame
        df = pd.DataFrame(facts)
        
        # Required columns for the package
        required_cols = ['COUNTRY', 'YEAR', 'SEX', 'AGEGROUP', 'Display', 'Value']
        
        # Map API response to required format
        if 'dims' in df.columns:
            # Extract dimensions
            df_expanded = pd.json_normalize(df['dims'])
            df_expanded['Display Value'] = df['Value']
            df_expanded['GHO (CODE)'] = indicator
            
            # Rename columns to match package format
            column_mapping = {
                'COUNTRY': 'COUNTRY (CODE)',
                'YEAR': 'YEAR (CODE)', 
                'SEX': 'SEX (CODE)',
                'AGEGROUP': 'AGEGROUP (CODE)',
                'Display': 'Display Value'
            }
            
            df_expanded = df_expanded.rename(columns=column_mapping)
            logger.info(f"Processed DataFrame shape: {df_expanded.shape}")
            logger.info(f"Columns: {df_expanded.columns.tolist()}")
            
            return df_expanded
            
        return df
    
    def process_gho_csv(self, csv_text, indicator):
        """Process CSV data from GHO API."""
        logger.info(f"Processing GHO CSV data for {indicator}")
        
        # Read CSV from string
        from io import StringIO
        df = pd.read_csv(StringIO(csv_text))
        
        logger.info(f"CSV DataFrame shape: {df.shape}")
        logger.info(f"CSV Columns: {df.columns.tolist()}")
        
        # Add GHO code if not present
        if 'GHO (CODE)' not in df.columns:
            df['GHO (CODE)'] = indicator
            
        return df
    
    def save_who_data(self, df):
        """Save WHO data in clean schema format."""
        if df is None or df.empty:
            logger.error("No data to save")
            return False
            
        try:
            # Create clean schema-compliant dataframe
            clean_df = pd.DataFrame({
                'country_code': df.get('COUNTRY (CODE)', df.get('SpatialDim', '')),
                'country_name': df.get('COUNTRY (DISPLAY)', df.get('ParentLocation', '')),
                'year': df.get('YEAR (CODE)', df.get('TimeDim', 0)),
                'sex_code': df.get('SEX (CODE)', df.get('Dim1', '')),
                'life_expectancy': df.get('Numeric', df.get('NumericValue', 0.0)),
                'low_ci': df.get('Low', 0.0),
                'high_ci': df.get('High', 0.0)
            })
            
            # Clean data
            clean_df = clean_df.dropna(subset=['country_code', 'year', 'sex_code', 'life_expectancy'])
            clean_df = clean_df[clean_df['life_expectancy'] > 0]  # Remove invalid values
            
            # Fix sex codes (remove SEX_ prefix if present)
            clean_df['sex_code'] = clean_df['sex_code'].str.replace('SEX_', '', regex=False)
            
            logger.info(f"Clean DataFrame shape: {clean_df.shape}")
            logger.info(f"Fixed sex codes, now: {clean_df['sex_code'].unique()}")
            # Save both raw and clean formats
            raw_output_file = DATA_DIR / "who-lt.csv.gz"  # Keep raw for legacy
            clean_output_file = DATA_DIR / "who.csv.gz"   # New clean format
            backup_file = DATA_DIR / f"who-lt-backup-{datetime.now().strftime('%Y%m%d')}.csv.gz"
            
            # Backup original file
            if raw_output_file.exists():
                import shutil
                shutil.copy2(raw_output_file, backup_file)
                logger.info(f"Backed up original data to {backup_file}")
            
            # Save raw data (for legacy compatibility)
            df.to_csv(raw_output_file, index=False, compression='gzip')
            
            # Save clean data (for new schema)
            clean_df.to_csv(clean_output_file, index=False, compression='gzip')
            logger.info(f"Saved {len(clean_df)} records to {clean_output_file}")
            
            # Report data coverage
            years = clean_df['year'].dropna()
            if not years.empty:
                logger.info(f"Data covers years: {years.min()} to {years.max()}")
            
            countries = clean_df['country_code'].nunique()
            logger.info(f"Data covers {countries} countries/regions")
            
            return True
            
        except Exception as e:
            logger.error(f"Error saving data: {e}")
            return False
    
    def update_who_data(self):
        """Main method to update WHO data."""
        logger.info("Starting WHO data update...")
        
        # Try working GHO API first
        data = self.try_working_gho_api()
        
        if data is None:
            # Try new platform as fallback
            data = self.try_new_who_platform()
        
        if data is None:
            logger.error("Failed to fetch WHO data from all sources")
            return False
        
        # Process and save data
        if isinstance(data, dict):
            # Convert dict to DataFrame if needed
            data = pd.DataFrame([data])
        
        return self.save_who_data(data)

def main():
    """Main function."""
    print("WHO Data Updater v0.4.0")
    print("=" * 40)
    
    updater = WHODataUpdater()
    success = updater.update_who_data()
    
    if success:
        print("✅ WHO data updated successfully!")
    else:
        print("❌ WHO data update failed")
        print("Consider manual download from: https://platform.who.int/mortality")
        print("Contact: mortality@who.int for API access")

if __name__ == "__main__":
    main()