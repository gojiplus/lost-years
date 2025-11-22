#!/usr/bin/env python3
"""
HLD Data Update Script - Manual Download Process
Human Life-Table Database from lifetable.de

Since automated download is challenging due to site protection,
this script provides instructions for manual download and processing.
"""

import pandas as pd
import zipfile
from pathlib import Path
import logging
from datetime import datetime
import os

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Base directory
DATA_DIR = Path(__file__).parent


class HLDDataUpdater:
    """HLD data updater with manual download instructions."""
    
    def __init__(self):
        self.hld_url = "https://www.lifetable.de/"
        self.download_url = "https://www.lifetable.de/File/GetDocument/data/hld.zip"
    
    def check_for_downloaded_data(self):
        """Check if HLD data has been manually downloaded."""
        logger.info("Checking for manually downloaded HLD data...")
        
        # Look for common download files
        potential_files = [
            DATA_DIR / "hld.zip",
            DATA_DIR / "res",  # Extracted CSV
            DATA_DIR / "hld.csv.gz",  # Processed data
        ]
        
        for file_path in potential_files:
            if file_path.exists():
                logger.info(f"Found: {file_path}")
                return file_path
        
        return None
    
    def process_hld_zip(self, zip_path):
        """Process downloaded HLD zip file."""
        logger.info(f"Processing HLD zip file: {zip_path}")
        
        try:
            with zipfile.ZipFile(zip_path, 'r') as zf:
                # Extract the main data file (usually 'res')
                files = zf.namelist()
                logger.info(f"Zip contains: {files}")
                
                # Find the main data file
                data_file = None
                for fname in files:
                    if fname in ['res', 'data.csv'] or fname.endswith('.csv'):
                        data_file = fname
                        break
                
                if data_file:
                    logger.info(f"Extracting: {data_file}")
                    zf.extract(data_file, DATA_DIR)
                    return DATA_DIR / data_file
                else:
                    logger.error("No recognizable data file found in zip")
                    return None
                    
        except Exception as e:
            logger.error(f"Error processing zip file: {e}")
            return None
    
    def clean_and_save_hld_data(self, csv_path):
        """Clean and save HLD data in standardized format."""
        logger.info(f"Cleaning HLD data from: {csv_path}")
        
        try:
            # Read in chunks to handle large file and potential parsing errors
            logger.info("Reading HLD data in chunks...")
            chunks = []
            chunk_size = 50000
            total_rows = 0
            
            for chunk in pd.read_csv(csv_path, chunksize=chunk_size, low_memory=False, on_bad_lines='skip'):
                chunks.append(chunk)
                total_rows += len(chunk)
                if len(chunks) % 20 == 0:
                    logger.info(f"Processed {total_rows:,} rows...")
            
            # Combine all chunks
            logger.info("Combining data chunks...")
            df = pd.concat(chunks, ignore_index=True)
            
            logger.info(f"Loaded {len(df):,} HLD records")
            logger.info(f"Countries: {df['Country'].nunique()}")
            logger.info(f"Years: {df['Year1'].min()}-{df['Year1'].max()}")
            
            # Save as compressed CSV
            output_file = DATA_DIR / "hld.csv.gz"
            backup_file = DATA_DIR / f"hld-backup-{datetime.now().strftime('%Y%m%d')}.csv.gz"
            
            # Backup existing file
            if output_file.exists():
                import shutil
                shutil.copy2(output_file, backup_file)
                logger.info(f"Backed up original data to {backup_file}")
            
            # Save new clean data
            df.to_csv(output_file, compression='gzip', index=False)
            logger.info(f"Saved clean HLD data: {output_file}")
            logger.info(f"File size: {output_file.stat().st_size / 1024**2:.1f} MB")
            
            return True
            
        except Exception as e:
            logger.error(f"Error processing HLD data: {e}")
            return False
    
    def show_manual_download_instructions(self):
        """Show instructions for manual download."""
        print("\n" + "="*60)
        print("📋 HLD MANUAL DOWNLOAD INSTRUCTIONS")
        print("="*60)
        print(f"1. Visit: {self.hld_url}")
        print("2. Look for 'All HLD data' download button")
        print("3. Download the hld.zip file to this directory:")
        print(f"   {DATA_DIR}")
        print("4. Run this script again to process the downloaded file")
        print()
        print("💡 The file should be named 'hld.zip' or 'res' (if extracted)")
        print()
        print("Alternative direct download (if working):")
        print(f"   {self.download_url}")
        print("="*60)
    
    def update_hld_data(self):
        """Main method to update HLD data."""
        logger.info("Starting HLD data update...")
        
        # Check for existing downloaded data
        existing_file = self.check_for_downloaded_data()
        
        if existing_file:
            if existing_file.suffix == '.zip':
                # Process zip file
                logger.info("Found zip file, extracting...")
                csv_file = self.process_hld_zip(existing_file)
                if csv_file:
                    return self.clean_and_save_hld_data(csv_file)
                    
            elif existing_file.name == 'res' or existing_file.suffix == '.csv':
                # Process CSV file directly
                return self.clean_and_save_hld_data(existing_file)
                
            elif existing_file.suffix == '.gz':
                # Already processed
                logger.info(f"Clean HLD data already exists: {existing_file}")
                return True
        
        else:
            # Show download instructions
            logger.warning("No HLD data files found")
            self.show_manual_download_instructions()
            return False


def main():
    """Main function."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Update HLD life table data (manual download)')
    parser.add_argument('--verbose', '-v', action='store_true',
                        help='Verbose output')
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    print("HLD Data Updater v1.0.0")
    print("=" * 40)
    print("Human Life-Table Database (lifetable.de)")
    print("Manual download process")
    print()
    
    updater = HLDDataUpdater()
    success = updater.update_hld_data()
    
    if success:
        print("✅ HLD data updated successfully!")
    else:
        print("⚠️  Manual download required")


if __name__ == "__main__":
    main()